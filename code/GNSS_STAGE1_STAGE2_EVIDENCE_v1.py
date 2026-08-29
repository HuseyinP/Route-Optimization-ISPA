# -*- coding: utf-8 -*-
r"""
GNSS_STAGE1_STAGE2_EVIDENCE_v1.py

Final Stage-1 -> Stage-2 evidence engine for the Sensors manuscript.

PURPOSE
-------
Merge the frozen 12-row Stage-1 observation-quality dataset with the final
Stage-2 multi-product positioning dataset and quantify whether receiver-level
observation quality is associated with:

    - positioning accuracy,
    - vertical bias,
    - epoch-level contamination,
    - product sensitivity / product-to-product spread.

The script is designed specifically to AVOID pseudo-replication.

PRIMARY ANALYSIS UNIT
---------------------
One physical dataset = Test × Receiver.

Stage-1 has 12 rows.
Stage-2 has up to 72 expected Product × Test × Receiver runs.

The same Stage-1 value is repeated across products only for merge/modeling
purposes. It is NOT treated as 6 independent Stage-1 observations.

SCIENTIFIC STRATEGY
-------------------
A) PRIMARY, conservative dataset-level analysis
   1. Collapse Stage-2 across usable products for each Test×Receiver:
         Median RMSE2D
         Median RMSE3D
         Median contamination
         Median |Bias_U|
         Product sensitivity range/IQR/CV
   2. Associate these 12 dataset-level outcomes with the 10 pre-specified
      Stage-1 core metrics using Spearman rho.
   3. Bootstrap 95% CI at the dataset level.
   4. Apply Benjamini-Hochberg FDR within each outcome family.

B) PRODUCT-ADJUSTED dataset-level analysis
   For each Stage-2 outcome, remove product location effects:
       residual = value - median(value within product)
   Then collapse residuals by Test×Receiver (median across products).
   This asks whether poorer Stage-1 quality is still associated with
   systematically poorer-than-product-typical positioning.

C) SECONDARY repeated-measures model
   If statsmodels is available:
       outcome ~ Stage1_metric + C(Product)
   with cluster-robust standard errors by Test×Receiver.

   Additionally, a dataset-level permutation test is used for the Stage-1
   coefficient while preserving all product rows belonging to a dataset.

D) PRODUCT-SENSITIVITY ANALYSIS
   For each physical dataset:
       RMSE2D_Range
       RMSE2D_IQR
       RMSE2D_CV
       RMSE2D_MaxMinRatio
   are computed across products.

   This directly tests the manuscript hypothesis:
       worse observation quality may be associated not only with worse
       accuracy, but also with greater sensitivity to precise-product choice.

IMPORTANT INTERPRETATION
------------------------
- Associations are observational and cross-class; they are NOT causal.
- With only 12 physical datasets, effect size and consistency are primary.
- P-values are secondary.
- Receiver class strongly structures several Stage-1 metrics; therefore
  associations should be described as receiver-conditioned/cross-class
  evidence rather than independent causal effects.
- No satellite or epoch sample count is used as inferential n.

EXPECTED INPUTS
---------------
Stage-1:
C:\IEEE\GNSS_ANALYSIS\STAGE1_RINEX_V2_2\GNSS_STAGE1_FINAL_METRICS.csv

Stage-2:
C:\IEEE\GNSS_ANALYSIS\POS_STATISTICS_V1_5_1\GNSS_POS_STATISTICS_V1_5_1.csv

The script has filename-discovery fallbacks if the exact names differ.

OUTPUT
------
C:\IEEE\GNSS_ANALYSIS\STAGE1_STAGE2_EVIDENCE_V1\

    STAGE1_STAGE2_MERGED_LONG.csv
    STAGE2_DATASET_LEVEL_SUMMARY.csv
    STAGE2_PRODUCT_ADJUSTED_DATASET.csv
    STAGE1_STAGE2_SPEARMAN_PRIMARY.csv
    STAGE1_STAGE2_SPEARMAN_PRODUCT_ADJUSTED.csv
    STAGE1_PRODUCT_SENSITIVITY_ASSOCIATIONS.csv
    STAGE1_STAGE2_REPEATED_MODEL.csv
    STAGE1_RECEIVER_CLASS_PROFILE.csv
    CLAIM_EVIDENCE_SUMMARY.csv
    GNSS_STAGE1_STAGE2_EVIDENCE_v1.xlsx
"""

from pathlib import Path
import math
import time
import warnings
import itertools

import numpy as np
import pandas as pd
from scipy.stats import spearmanr, rankdata

try:
    import statsmodels.formula.api as smf
    HAVE_STATSMODELS = True
except Exception:
    HAVE_STATSMODELS = False


# ======================================================================
# CONFIGURATION
# ======================================================================

ROOT = Path(r"C:\IEEE")
ANALYSIS_ROOT = ROOT / "GNSS_ANALYSIS"
OUT_DIR = ANALYSIS_ROOT / "STAGE1_STAGE2_EVIDENCE_V1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 20260816
rng = np.random.default_rng(RANDOM_SEED)

BOOT_N = 10000
PERM_N = 10000
ALPHA = 0.05

# Frozen v2.2 Stage-1 core definitions.
STAGE1_CORE_METRICS = [
    "CN0_Median_dBHz",
    "CN0_RobustSigma_dB",
    "GPS_L1_CMC_RobustSigma_m",
    "GPS_L1_CMC_P95Abs_m",
    "PhaseDiscontinuity_Rate_per1000",
    "Median_PhaseArc_Length_s",
    "Epoch_Retention_pct",
    "Observation_Completeness_pct",
    "Median_Usable_Satellites",
    "MultiFrequency_Availability_pct",
]

STAGE1_SECONDARY_METRICS = [
    "Signal_Diversity_Count",
    "GPS_L5_CMC_RobustSigma_m",
]

# Direction is defined so a positive standardized quality score means
# "better observation quality".
QUALITY_DIRECTION = {
    "CN0_Median_dBHz": +1,
    "CN0_RobustSigma_dB": -1,
    "GPS_L1_CMC_RobustSigma_m": -1,
    "GPS_L1_CMC_P95Abs_m": -1,
    "PhaseDiscontinuity_Rate_per1000": -1,
    "Median_PhaseArc_Length_s": +1,
    "Epoch_Retention_pct": +1,
    "Observation_Completeness_pct": +1,
    "Median_Usable_Satellites": +1,
    "MultiFrequency_Availability_pct": +1,
    "Signal_Diversity_Count": +1,
    "GPS_L5_CMC_RobustSigma_m": -1,
}

# Primary Stage-2 endpoints.
STAGE2_PRIMARY_OUTCOMES = {
    "Median_RMSE2D_m": "CLEAN_RMSE_2D_m",
    "Median_RMSE3D_m": "CLEAN_RMSE_3D_m",
    "Median_Contamination_pct": "Outlier_pct",
    "Median_AbsBiasU_m": "Abs_Bias_U_m",
}

# Product sensitivity outcomes computed across products per physical dataset.
PRODUCT_SENSITIVITY_OUTCOMES = [
    "RMSE2D_Product_Range_m",
    "RMSE2D_Product_IQR_m",
    "RMSE2D_Product_CV_pct",
    "RMSE2D_Product_MaxMinRatio",
]

# Only USABLE Stage-2 solutions enter accuracy association analyses.
USABLE_LABEL = "USABLE"


# ======================================================================
# FILE DISCOVERY
# ======================================================================

def find_stage1_file():
    candidates = [
        ANALYSIS_ROOT / "STAGE1_RINEX_V2_2" / "GNSS_STAGE1_FINAL_METRICS.csv",
        ANALYSIS_ROOT / "STAGE1_RINEX_V2_2" / "GNSS_STAGE1_FINAL_METRICS(3).csv",
        ANALYSIS_ROOT / "STAGE1_FINAL" / "GNSS_STAGE1_FINAL_METRICS.csv",
    ]

    for p in candidates:
        if p.exists():
            return p

    hits = list(ANALYSIS_ROOT.rglob("GNSS_STAGE1_FINAL_METRICS*.csv"))

    # Prefer v2_2 folder.
    hits.sort(
        key=lambda p: (
            "STAGE1_RINEX_V2_2" not in str(p).upper(),
            len(str(p)),
            str(p)
        )
    )

    if hits:
        return hits[0]

    raise FileNotFoundError(
        "Stage-1 final metrics file not found under "
        f"{ANALYSIS_ROOT}"
    )


def find_stage2_file():
    candidates = [
        ANALYSIS_ROOT / "POS_STATISTICS_V1_5_1" / "GNSS_POS_STATISTICS_V1_5_1.csv",
        ANALYSIS_ROOT / "POS_STATISTICS_V1_5_1" / "GNSS_POS_STATISTICS_V1_5_1_1.csv",
    ]

    for p in candidates:
        if p.exists():
            return p

    hits = list(ANALYSIS_ROOT.rglob("*POS_STATISTICS*V1_5_1*.csv"))
    hits = [
        p for p in hits
        if "AUDIT" not in p.name.upper()
        and "SUMMARY" not in p.name.upper()
        and "PAPER_TABLE" not in p.name.upper()
        and "INTERACTION" not in p.name.upper()
    ]

    if hits:
        return sorted(hits)[0]

    raise FileNotFoundError(
        "Stage-2 GNSS_POS_STATISTICS_V1_5_1*.csv not found under "
        f"{ANALYSIS_ROOT}"
    )


# ======================================================================
# HELPERS
# ======================================================================

def finite(values):
    x = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(float)
    return x[np.isfinite(x)]


def median_safe(values):
    x = finite(values)
    return float(np.median(x)) if len(x) else np.nan


def mean_safe(values):
    x = finite(values)
    return float(np.mean(x)) if len(x) else np.nan


def sd_safe(values):
    x = finite(values)
    return float(np.std(x, ddof=1)) if len(x) > 1 else np.nan


def iqr_safe(values):
    x = finite(values)
    if not len(x):
        return np.nan
    return float(np.percentile(x, 75) - np.percentile(x, 25))


def cv_safe(values):
    x = finite(values)
    if len(x) < 2:
        return np.nan
    m = np.mean(x)
    if not np.isfinite(m) or abs(m) < 1e-12:
        return np.nan
    return float(100.0 * np.std(x, ddof=1) / abs(m))


def robust_z(series):
    x = pd.to_numeric(series, errors="coerce").astype(float)
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med))
    scale = 1.4826 * mad

    if not np.isfinite(scale) or scale <= 1e-12:
        return pd.Series(np.nan, index=series.index)

    return (x - med) / scale


def normalize_receiver_id(df):
    if "Receiver_ID" in df.columns:
        df["Receiver_ID"] = df["Receiver_ID"].astype(str).str.strip()
    return df


def ensure_abs_bias_u(df):
    if "Abs_Bias_U_m" not in df.columns:
        if "CLEAN_Bias_U_m" not in df.columns:
            raise KeyError(
                "Stage-2 requires Abs_Bias_U_m or CLEAN_Bias_U_m"
            )
        df["Abs_Bias_U_m"] = pd.to_numeric(
            df["CLEAN_Bias_U_m"], errors="coerce"
        ).abs()
    return df


# ======================================================================
# INPUT VALIDATION
# ======================================================================

def load_inputs(stage1_path, stage2_path):
    st1 = pd.read_csv(stage1_path)
    st2 = pd.read_csv(stage2_path)

    required_ids = ["Test", "Receiver", "Receiver_ID", "Receiver_Class"]

    for c in required_ids:
        if c not in st1.columns:
            raise KeyError(f"Stage-1 missing identifier column: {c}")

    for c in ["Test", "Receiver", "Receiver_ID", "Receiver_Class",
              "Product", "Solution_Status"]:
        if c not in st2.columns:
            raise KeyError(f"Stage-2 missing required column: {c}")

    missing_metrics = [
        m for m in STAGE1_CORE_METRICS
        if m not in st1.columns
    ]
    if missing_metrics:
        raise KeyError(
            "Stage-1 v2.2 core metrics missing: "
            + ", ".join(missing_metrics)
        )

    for c in ["CLEAN_RMSE_2D_m", "CLEAN_RMSE_3D_m", "Outlier_pct"]:
        if c not in st2.columns:
            raise KeyError(f"Stage-2 missing outcome column: {c}")

    st1 = normalize_receiver_id(st1.copy())
    st2 = normalize_receiver_id(st2.copy())
    st2 = ensure_abs_bias_u(st2)

    # Keep only one Stage-1 row per physical dataset.
    dup = st1.duplicated(["Test", "Receiver_ID"], keep=False)
    if dup.any():
        raise ValueError(
            "Stage-1 has duplicate Test×Receiver_ID rows:\n"
            + st1.loc[dup, ["Test", "Receiver_ID"]].to_string(index=False)
        )

    return st1, st2


# ======================================================================
# QUALITY-ORIENTED STAGE-1 VARIABLES
# ======================================================================

def add_quality_oriented_metrics(st1):
    out = st1.copy()

    for metric in STAGE1_CORE_METRICS + STAGE1_SECONDARY_METRICS:
        if metric not in out.columns:
            continue

        z = robust_z(out[metric])
        out[f"QZ_{metric}"] = QUALITY_DIRECTION[metric] * z

    return out


# ======================================================================
# LONG MERGE
# ======================================================================

def build_long_merge(st1, st2):
    merged = st2.merge(
        st1,
        on=["Test", "Receiver_ID"],
        how="left",
        suffixes=("_Stage2", "_Stage1"),
        validate="many_to_one"
    )

    # Harmonize identifier names after suffixing.
    if "Receiver_Stage2" in merged.columns:
        merged["Receiver"] = merged["Receiver_Stage2"]
    if "Receiver_Class_Stage2" in merged.columns:
        merged["Receiver_Class"] = merged["Receiver_Class_Stage2"]

    merged["Dataset_ID"] = (
        merged["Test"].astype(str) + "|" +
        merged["Receiver_ID"].astype(str)
    )

    return merged


# ======================================================================
# DATASET-LEVEL STAGE-2 SUMMARY
# ======================================================================

def build_dataset_summary(long_df):
    usable = long_df[
        long_df["Solution_Status"] == USABLE_LABEL
    ].copy()

    rows = []

    # Expected product count is 6, but usable may be smaller for OEM.
    for (test, rid), g in long_df.groupby(["Test", "Receiver_ID"], dropna=False):
        gu = g[g["Solution_Status"] == USABLE_LABEL].copy()

        receiver = g["Receiver"].iloc[0]
        rclass = g["Receiver_Class"].iloc[0]

        rmse2 = finite(gu["CLEAN_RMSE_2D_m"])
        rmse3 = finite(gu["CLEAN_RMSE_3D_m"])
        cont = finite(gu["Outlier_pct"])
        bu = finite(gu["Abs_Bias_U_m"])

        row = {
            "Test": test,
            "Receiver_ID": rid,
            "Receiver": receiver,
            "Receiver_Class": rclass,
            "Dataset_ID": f"{test}|{rid}",

            "Expected_Product_N": int(g["Product"].nunique()),
            "USABLE_Product_N": int(gu["Product"].nunique()),
            "FAILED_Product_N":
                int(g["Product"].nunique() - gu["Product"].nunique()),
            "Product_Availability_pct":
                100.0 * gu["Product"].nunique() / g["Product"].nunique()
                if g["Product"].nunique() else np.nan,

            "Median_RMSE2D_m": median_safe(rmse2),
            "Median_RMSE3D_m": median_safe(rmse3),
            "Median_Contamination_pct": median_safe(cont),
            "Median_AbsBiasU_m": median_safe(bu),

            # Product sensitivity endpoints.
            "RMSE2D_Product_Range_m":
                float(np.max(rmse2) - np.min(rmse2))
                if len(rmse2) >= 2 else np.nan,

            "RMSE2D_Product_IQR_m":
                iqr_safe(rmse2),

            "RMSE2D_Product_CV_pct":
                cv_safe(rmse2),

            "RMSE2D_Product_MaxMinRatio":
                (
                    float(np.max(rmse2) / np.min(rmse2))
                    if len(rmse2) >= 2 and np.min(rmse2) > 0
                    else np.nan
                ),

            "Best_Product_RMSE2D":
                (
                    gu.loc[
                        gu["CLEAN_RMSE_2D_m"].idxmin(),
                        "Product"
                    ]
                    if len(gu) and gu["CLEAN_RMSE_2D_m"].notna().any()
                    else ""
                ),

            "Worst_Product_RMSE2D":
                (
                    gu.loc[
                        gu["CLEAN_RMSE_2D_m"].idxmax(),
                        "Product"
                    ]
                    if len(gu) and gu["CLEAN_RMSE_2D_m"].notna().any()
                    else ""
                ),
        }

        # Add Stage-1 metrics from first merged row.
        for metric in STAGE1_CORE_METRICS + STAGE1_SECONDARY_METRICS:
            if metric in g.columns:
                row[metric] = pd.to_numeric(
                    g[metric], errors="coerce"
                ).iloc[0]

            q = f"QZ_{metric}"
            if q in g.columns:
                row[q] = pd.to_numeric(
                    g[q], errors="coerce"
                ).iloc[0]

        rows.append(row)

    return pd.DataFrame(rows)


# ======================================================================
# PRODUCT-ADJUSTED DATASET SUMMARY
# ======================================================================

def build_product_adjusted_dataset(long_df):
    usable = long_df[
        long_df["Solution_Status"] == USABLE_LABEL
    ].copy()

    outcome_cols = [
        "CLEAN_RMSE_2D_m",
        "CLEAN_RMSE_3D_m",
        "Outlier_pct",
        "Abs_Bias_U_m",
    ]

    # Product-median centering.
    for col in outcome_cols:
        med_by_product = usable.groupby("Product")[col].transform("median")
        usable[f"ADJ_{col}"] = usable[col] - med_by_product

    agg = (
        usable.groupby(
            ["Test", "Receiver_ID", "Receiver", "Receiver_Class", "Dataset_ID"],
            as_index=False
        )
        .agg(
            Adj_Median_RMSE2D_m=("ADJ_CLEAN_RMSE_2D_m", "median"),
            Adj_Median_RMSE3D_m=("ADJ_CLEAN_RMSE_3D_m", "median"),
            Adj_Median_Contamination_pct=("ADJ_Outlier_pct", "median"),
            Adj_Median_AbsBiasU_m=("ADJ_Abs_Bias_U_m", "median"),
            USABLE_Product_N=("Product", "nunique"),
        )
    )

    # Reattach Stage-1 once per dataset.
    stage1_cols = [
        "Test", "Receiver_ID"
    ] + [
        c for c in long_df.columns
        if c in STAGE1_CORE_METRICS
        or c in STAGE1_SECONDARY_METRICS
        or c.startswith("QZ_")
    ]

    st1_unique = long_df[stage1_cols].drop_duplicates(
        ["Test", "Receiver_ID"]
    )

    return agg.merge(
        st1_unique,
        on=["Test", "Receiver_ID"],
        how="left",
        validate="one_to_one"
    )


# ======================================================================
# SPEARMAN + BOOTSTRAP
# ======================================================================

def bootstrap_spearman(x, y, boot_n=BOOT_N, alpha=ALPHA):
    x = np.asarray(x, float)
    y = np.asarray(y, float)

    mask = np.isfinite(x) & np.isfinite(y)
    x = x[mask]
    y = y[mask]

    n = len(x)

    if n < 4:
        return np.nan, np.nan

    vals = []
    attempts = 0
    max_attempts = boot_n * 4

    while len(vals) < boot_n and attempts < max_attempts:
        idx = rng.integers(0, n, n)
        xb = x[idx]
        yb = y[idx]
        attempts += 1

        if len(np.unique(xb)) < 2 or len(np.unique(yb)) < 2:
            continue

        rho, _ = spearmanr(xb, yb)

        if np.isfinite(rho):
            vals.append(rho)

    if len(vals) < 100:
        return np.nan, np.nan

    return (
        float(np.percentile(vals, 100 * alpha / 2)),
        float(np.percentile(vals, 100 * (1 - alpha / 2))),
    )


def bh_fdr(pvalues):
    """
    Benjamini-Hochberg adjusted p-values.
    """
    p = np.asarray(pvalues, float)
    out = np.full(len(p), np.nan)

    valid = np.where(np.isfinite(p))[0]

    if len(valid) == 0:
        return out

    pv = p[valid]
    order = np.argsort(pv)
    ranked = pv[order]

    m = len(ranked)
    adj = ranked * m / np.arange(1, m + 1)

    # Monotonicity from largest to smallest.
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    adj = np.minimum(adj, 1.0)

    original = np.empty(m)
    original[order] = adj
    out[valid] = original

    return out


def run_spearman_table(
    df,
    outcomes,
    analysis_label,
    metrics=STAGE1_CORE_METRICS,
):
    rows = []

    for outcome in outcomes:
        if outcome not in df.columns:
            continue

        for metric in metrics:
            if metric not in df.columns:
                continue

            x = pd.to_numeric(df[metric], errors="coerce").to_numpy(float)
            y = pd.to_numeric(df[outcome], errors="coerce").to_numpy(float)

            mask = np.isfinite(x) & np.isfinite(y)
            n = int(mask.sum())

            if n >= 3 and len(np.unique(x[mask])) >= 2:
                rho, p = spearmanr(x[mask], y[mask])
                lo, hi = bootstrap_spearman(x[mask], y[mask])
            else:
                rho = p = lo = hi = np.nan

            # Quality-oriented interpretation:
            # positive QZ = better observation quality.
            direction = QUALITY_DIRECTION[metric]
            rho_quality = (
                float(rho) * direction
                if np.isfinite(rho)
                else np.nan
            )

            rows.append({
                "Analysis": analysis_label,
                "Outcome": outcome,
                "Stage1_Metric": metric,
                "N_Datasets": n,
                "Spearman_rho_raw": rho,
                "Spearman_rho_quality_oriented": rho_quality,
                "Spearman_p": p,
                "Bootstrap95CI_Low_raw": lo,
                "Bootstrap95CI_High_raw": hi,
                "Quality_Direction":
                    "Higher=better" if direction > 0 else "Lower=better",
                "Interpretation":
                    (
                        "Negative quality-oriented rho means better observation "
                        "quality is associated with lower/worse-coded endpoint."
                    )
            })

    out = pd.DataFrame(rows)

    if not out.empty:
        # FDR within each outcome family.
        out["FDR_BH_q"] = np.nan

        for outcome, idx in out.groupby("Outcome").groups.items():
            out.loc[idx, "FDR_BH_q"] = bh_fdr(
                out.loc[idx, "Spearman_p"].to_numpy(float)
            )

    return out


# ======================================================================
# PRODUCT-SENSITIVITY ASSOCIATIONS
# ======================================================================

def run_product_sensitivity_associations(dataset_df):
    return run_spearman_table(
        dataset_df,
        PRODUCT_SENSITIVITY_OUTCOMES,
        analysis_label="PRODUCT_SENSITIVITY",
        metrics=STAGE1_CORE_METRICS,
    )


# ======================================================================
# REPEATED-MEASURES MODEL + CLUSTER PERMUTATION
# ======================================================================

def _fit_product_adjusted_ols(data, outcome, metric):
    """
    Fit outcome ~ standardized metric + C(Product).
    Returns coefficient and model object.
    """
    d = data[
        ["Dataset_ID", "Product", outcome, metric]
    ].copy()

    d[outcome] = pd.to_numeric(d[outcome], errors="coerce")
    d[metric] = pd.to_numeric(d[metric], errors="coerce")
    d = d.dropna()

    if len(d) < 8:
        return np.nan, None, d

    # Standardize Stage-1 metric at DATASET level so repeating across products
    # does not change its scale.
    metric_by_dataset = (
        d[["Dataset_ID", metric]]
        .drop_duplicates("Dataset_ID")
        .copy()
    )

    z = robust_z(metric_by_dataset[metric])

    metric_by_dataset["_metric_z"] = z

    d = d.drop(columns=[metric]).merge(
        metric_by_dataset[["Dataset_ID", "_metric_z"]],
        on="Dataset_ID",
        how="left"
    )

    d = d.dropna(subset=["_metric_z"])

    if len(d) < 8 or d["Dataset_ID"].nunique() < 4:
        return np.nan, None, d

    # Positive z means raw metric is high, not necessarily quality-oriented.
    formula = f'Q("{outcome}") ~ _metric_z + C(Product)'

    model = smf.ols(formula, data=d).fit(
        cov_type="cluster",
        cov_kwds={"groups": d["Dataset_ID"]}
    )

    coef = float(model.params.get("_metric_z", np.nan))

    return coef, model, d


def _permutation_p_dataset_level(
    data,
    outcome,
    metric,
    observed_coef,
    perm_n=PERM_N,
):
    """
    Permute Stage-1 metric labels across physical datasets, then repeat the
    permuted metric across all product rows belonging to that dataset.
    This preserves the repeated-measures/product structure.
    """
    if not HAVE_STATSMODELS or not np.isfinite(observed_coef):
        return np.nan

    base = data[
        ["Dataset_ID", "Product", outcome, metric]
    ].copy()

    base[outcome] = pd.to_numeric(base[outcome], errors="coerce")
    base[metric] = pd.to_numeric(base[metric], errors="coerce")
    base = base.dropna()

    ds_metric = (
        base[["Dataset_ID", metric]]
        .drop_duplicates("Dataset_ID")
        .sort_values("Dataset_ID")
        .reset_index(drop=True)
    )

    if len(ds_metric) < 4:
        return np.nan

    original_values = ds_metric[metric].to_numpy(float)
    count_extreme = 0
    valid_perm = 0

    for _ in range(perm_n):
        permuted = rng.permutation(original_values)

        pm = ds_metric[["Dataset_ID"]].copy()
        pm["_perm_metric"] = permuted

        d = base.drop(columns=[metric]).merge(
            pm,
            on="Dataset_ID",
            how="left"
        )

        # robust z of the permuted dataset-level metric
        unique_pm = pm.copy()
        z = robust_z(unique_pm["_perm_metric"])
        unique_pm["_metric_z"] = z

        d = d.drop(columns=["_perm_metric"]).merge(
            unique_pm[["Dataset_ID", "_metric_z"]],
            on="Dataset_ID",
            how="left"
        )
        d = d.dropna(subset=["_metric_z"])

        if len(d) < 8:
            continue

        try:
            m = smf.ols(
                f'Q("{outcome}") ~ _metric_z + C(Product)',
                data=d
            ).fit()

            coef = float(m.params.get("_metric_z", np.nan))

            if np.isfinite(coef):
                valid_perm += 1
                if abs(coef) >= abs(observed_coef):
                    count_extreme += 1
        except Exception:
            continue

    if valid_perm == 0:
        return np.nan

    return float((count_extreme + 1) / (valid_perm + 1))


def run_repeated_models(long_df):
    if not HAVE_STATSMODELS:
        return pd.DataFrame([{
            "Status": "STATSMODELS_NOT_AVAILABLE"
        }])

    usable = long_df[
        long_df["Solution_Status"] == USABLE_LABEL
    ].copy()

    outcomes = [
        "CLEAN_RMSE_2D_m",
        "CLEAN_RMSE_3D_m",
        "Outlier_pct",
        "Abs_Bias_U_m",
    ]

    rows = []

    for outcome in outcomes:
        for metric in STAGE1_CORE_METRICS:
            if metric not in usable.columns:
                continue

            try:
                coef, model, d = _fit_product_adjusted_ols(
                    usable, outcome, metric
                )

                if model is None:
                    rows.append({
                        "Outcome": outcome,
                        "Stage1_Metric": metric,
                        "Status": "INSUFFICIENT_DATA",
                    })
                    continue

                se = float(model.bse.get("_metric_z", np.nan))
                p = float(model.pvalues.get("_metric_z", np.nan))

                ci = model.conf_int().loc["_metric_z"]
                ci_lo = float(ci.iloc[0])
                ci_hi = float(ci.iloc[1])

                perm_p = _permutation_p_dataset_level(
                    usable,
                    outcome,
                    metric,
                    observed_coef=coef,
                    perm_n=PERM_N,
                )

                qcoef = coef * QUALITY_DIRECTION[metric]

                rows.append({
                    "Outcome": outcome,
                    "Stage1_Metric": metric,
                    "N_Rows": len(d),
                    "N_Datasets": d["Dataset_ID"].nunique(),
                    "N_Products": d["Product"].nunique(),

                    "Coef_per_RobustSD_rawMetric": coef,
                    "Coef_quality_oriented": qcoef,
                    "ClusterRobust_SE": se,
                    "ClusterRobust_p": p,
                    "ClusterRobust_CI_Low": ci_lo,
                    "ClusterRobust_CI_High": ci_hi,
                    "DatasetPermutation_p": perm_p,

                    "Model":
                        f"{outcome} ~ robust_z({metric}) + C(Product)",
                    "Status": "OK",
                })

            except Exception as exc:
                rows.append({
                    "Outcome": outcome,
                    "Stage1_Metric": metric,
                    "Status":
                        f"ERROR:{type(exc).__name__}:{exc}",
                })

    out = pd.DataFrame(rows)

    if not out.empty and "ClusterRobust_p" in out.columns:
        out["FDR_BH_q_cluster"] = np.nan

        ok = out["Status"] == "OK"

        for outcome, idx in out[ok].groupby("Outcome").groups.items():
            out.loc[idx, "FDR_BH_q_cluster"] = bh_fdr(
                out.loc[idx, "ClusterRobust_p"].to_numpy(float)
            )

    return out


# ======================================================================
# RECEIVER-CLASS STAGE-1 PROFILE
# ======================================================================

def build_receiver_class_profile(st1):
    rows = []

    for rclass, g in st1.groupby("Receiver_Class"):
        for metric in STAGE1_CORE_METRICS:
            x = finite(g[metric])

            rows.append({
                "Receiver_Class": rclass,
                "Metric": metric,
                "N": len(x),
                "Median": median_safe(x),
                "Mean": mean_safe(x),
                "SD": sd_safe(x),
                "IQR": iqr_safe(x),
                "Quality_Direction":
                    "Higher=better"
                    if QUALITY_DIRECTION[metric] > 0
                    else "Lower=better",
            })

    return pd.DataFrame(rows)


# ======================================================================
# CLAIM-EVIDENCE SUMMARY
# ======================================================================

def build_claim_evidence_summary(
    primary_assoc,
    adjusted_assoc,
    sensitivity_assoc,
    repeated_models,
    dataset_summary,
):
    rows = []

    def strongest(table, outcome):
        if table.empty:
            return None

        g = table[table["Outcome"] == outcome].copy()

        if g.empty:
            return None

        g = g.dropna(subset=["Spearman_rho_quality_oriented"])

        if g.empty:
            return None

        return g.iloc[
            np.argmax(np.abs(g["Spearman_rho_quality_oriented"].to_numpy()))
        ]

    s_rmse2 = strongest(primary_assoc, "Median_RMSE2D_m")
    s_cont = strongest(primary_assoc, "Median_Contamination_pct")
    s_sens = strongest(
        sensitivity_assoc,
        "RMSE2D_Product_Range_m"
    )

    def fmt_strong(s):
        if s is None:
            return "No estimable association"
        return (
            f"{s['Stage1_Metric']}: "
            f"rhoQ={s['Spearman_rho_quality_oriented']:.3f}, "
            f"n={int(s['N_Datasets'])}, "
            f"p={s['Spearman_p']:.3g}, "
            f"q={s['FDR_BH_q']:.3g}"
        )

    rows.append({
        "Claim_ID": "C8A",
        "Claim":
            "Observation quality is associated with downstream horizontal "
            "positioning accuracy across the 12 physical datasets.",
        "Evidence": fmt_strong(s_rmse2),
        "Primary_Table": "STAGE1_STAGE2_SPEARMAN_PRIMARY.csv",
        "Interpretation_Level": "ASSOCIATION_NOT_CAUSATION",
    })

    rows.append({
        "Claim_ID": "C8B",
        "Claim":
            "Observation quality is associated with epoch-level positioning "
            "contamination.",
        "Evidence": fmt_strong(s_cont),
        "Primary_Table": "STAGE1_STAGE2_SPEARMAN_PRIMARY.csv",
        "Interpretation_Level": "ASSOCIATION_NOT_CAUSATION",
    })

    rows.append({
        "Claim_ID": "C8C",
        "Claim":
            "Observation quality is associated with sensitivity to precise "
            "product choice.",
        "Evidence": fmt_strong(s_sens),
        "Primary_Table":
            "STAGE1_PRODUCT_SENSITIVITY_ASSOCIATIONS.csv",
        "Interpretation_Level": "PRIMARY_NOVELTY_SUPPORT",
    })

    # Availability pattern.
    avail = (
        dataset_summary.groupby("Receiver_Class")
        .agg(
            Dataset_N=("Dataset_ID", "count"),
            Median_Product_Availability_pct=(
                "Product_Availability_pct", "median"
            )
        )
        .reset_index()
    )

    rows.append({
        "Claim_ID": "C2",
        "Claim":
            "Availability and accuracy are distinct dimensions.",
        "Evidence":
            "; ".join(
                f"{r.Receiver_Class} median product availability="
                f"{r.Median_Product_Availability_pct:.1f}%"
                for r in avail.itertuples()
            ),
        "Primary_Table": "STAGE2_DATASET_LEVEL_SUMMARY.csv",
        "Interpretation_Level": "DESCRIPTIVE_STRONG",
    })

    return pd.DataFrame(rows)


# ======================================================================
# MAIN
# ======================================================================

def main():
    t0 = time.perf_counter()

    stage1_path = find_stage1_file()
    stage2_path = find_stage2_file()

    print("=" * 146)
    print("GNSS STAGE-1 -> STAGE-2 EVIDENCE v1")
    print("=" * 146)
    print(f"Stage-1 input : {stage1_path}")
    print(f"Stage-2 input : {stage2_path}")
    print(f"statsmodels   : {'AVAILABLE' if HAVE_STATSMODELS else 'NOT AVAILABLE'}")
    print("Inference n   : physical Test×Receiver datasets, not epochs/satellites")

    st1, st2 = load_inputs(stage1_path, stage2_path)
    st1 = add_quality_oriented_metrics(st1)

    long_df = build_long_merge(st1, st2)

    # Merge QC
    missing_stage1 = long_df[
        STAGE1_CORE_METRICS
    ].isna().all(axis=1)

    print(f"\nStage-1 rows           : {len(st1)}")
    print(f"Stage-2 rows           : {len(st2)}")
    print(f"Merged long rows       : {len(long_df)}")
    print(
        f"Rows with all core Stage-1 metrics missing : "
        f"{int(missing_stage1.sum())}"
    )

    dataset_summary = build_dataset_summary(long_df)
    adjusted_dataset = build_product_adjusted_dataset(long_df)

    primary_assoc = run_spearman_table(
        dataset_summary,
        outcomes=list(STAGE2_PRIMARY_OUTCOMES.keys()),
        analysis_label="PRIMARY_DATASET_LEVEL",
        metrics=STAGE1_CORE_METRICS,
    )

    adjusted_assoc = run_spearman_table(
        adjusted_dataset,
        outcomes=[
            "Adj_Median_RMSE2D_m",
            "Adj_Median_RMSE3D_m",
            "Adj_Median_Contamination_pct",
            "Adj_Median_AbsBiasU_m",
        ],
        analysis_label="PRODUCT_ADJUSTED_DATASET_LEVEL",
        metrics=STAGE1_CORE_METRICS,
    )

    sensitivity_assoc = run_product_sensitivity_associations(
        dataset_summary
    )

    repeated_models = run_repeated_models(long_df)
    class_profile = build_receiver_class_profile(st1)

    claim_summary = build_claim_evidence_summary(
        primary_assoc,
        adjusted_assoc,
        sensitivity_assoc,
        repeated_models,
        dataset_summary,
    )

    # -----------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------
    outputs = {
        "LONG": OUT_DIR / "STAGE1_STAGE2_MERGED_LONG.csv",
        "DATASET": OUT_DIR / "STAGE2_DATASET_LEVEL_SUMMARY.csv",
        "ADJUSTED": OUT_DIR / "STAGE2_PRODUCT_ADJUSTED_DATASET.csv",
        "PRIMARY": OUT_DIR / "STAGE1_STAGE2_SPEARMAN_PRIMARY.csv",
        "ADJ_ASSOC": OUT_DIR / "STAGE1_STAGE2_SPEARMAN_PRODUCT_ADJUSTED.csv",
        "SENS": OUT_DIR / "STAGE1_PRODUCT_SENSITIVITY_ASSOCIATIONS.csv",
        "MODEL": OUT_DIR / "STAGE1_STAGE2_REPEATED_MODEL.csv",
        "PROFILE": OUT_DIR / "STAGE1_RECEIVER_CLASS_PROFILE.csv",
        "CLAIMS": OUT_DIR / "CLAIM_EVIDENCE_SUMMARY.csv",
        "XLSX": OUT_DIR / "GNSS_STAGE1_STAGE2_EVIDENCE_v1.xlsx",
    }

    long_df.to_csv(outputs["LONG"], index=False, encoding="utf-8-sig")
    dataset_summary.to_csv(
        outputs["DATASET"], index=False, encoding="utf-8-sig"
    )
    adjusted_dataset.to_csv(
        outputs["ADJUSTED"], index=False, encoding="utf-8-sig"
    )
    primary_assoc.to_csv(
        outputs["PRIMARY"], index=False, encoding="utf-8-sig"
    )
    adjusted_assoc.to_csv(
        outputs["ADJ_ASSOC"], index=False, encoding="utf-8-sig"
    )
    sensitivity_assoc.to_csv(
        outputs["SENS"], index=False, encoding="utf-8-sig"
    )
    repeated_models.to_csv(
        outputs["MODEL"], index=False, encoding="utf-8-sig"
    )
    class_profile.to_csv(
        outputs["PROFILE"], index=False, encoding="utf-8-sig"
    )
    claim_summary.to_csv(
        outputs["CLAIMS"], index=False, encoding="utf-8-sig"
    )

    with pd.ExcelWriter(outputs["XLSX"], engine="openpyxl") as writer:
        dataset_summary.to_excel(
            writer, sheet_name="DATASET_LEVEL", index=False
        )
        adjusted_dataset.to_excel(
            writer, sheet_name="PRODUCT_ADJUSTED", index=False
        )
        primary_assoc.to_excel(
            writer, sheet_name="SPEARMAN_PRIMARY", index=False
        )
        adjusted_assoc.to_excel(
            writer, sheet_name="SPEARMAN_ADJUSTED", index=False
        )
        sensitivity_assoc.to_excel(
            writer, sheet_name="PRODUCT_SENSITIVITY", index=False
        )
        repeated_models.to_excel(
            writer, sheet_name="REPEATED_MODEL", index=False
        )
        class_profile.to_excel(
            writer, sheet_name="CLASS_PROFILE", index=False
        )
        claim_summary.to_excel(
            writer, sheet_name="CLAIM_SUMMARY", index=False
        )

    # -----------------------------------------------------------------
    # Console summary
    # -----------------------------------------------------------------
    pd.set_option("display.width", 260)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")

    print("\n" + "=" * 146)
    print("DATASET-LEVEL STAGE-2 SUMMARY")
    print("=" * 146)
    print(
        dataset_summary[
            [
                "Test", "Receiver_ID", "Receiver_Class",
                "USABLE_Product_N", "Product_Availability_pct",
                "Median_RMSE2D_m", "Median_RMSE3D_m",
                "Median_Contamination_pct", "Median_AbsBiasU_m",
                "RMSE2D_Product_Range_m",
                "RMSE2D_Product_CV_pct",
            ]
        ].to_string(index=False)
    )

    print("\nTOP PRIMARY ASSOCIATIONS BY |rho|")
    if not primary_assoc.empty:
        tmp = primary_assoc.copy()
        tmp["AbsRho"] = tmp["Spearman_rho_raw"].abs()
        print(
            tmp.sort_values("AbsRho", ascending=False)
            .head(20)[
                [
                    "Outcome", "Stage1_Metric", "N_Datasets",
                    "Spearman_rho_raw",
                    "Spearman_rho_quality_oriented",
                    "Spearman_p", "FDR_BH_q",
                    "Bootstrap95CI_Low_raw",
                    "Bootstrap95CI_High_raw",
                ]
            ].to_string(index=False)
        )

    print("\nTOP PRODUCT-SENSITIVITY ASSOCIATIONS BY |rho|")
    if not sensitivity_assoc.empty:
        tmp = sensitivity_assoc.copy()
        tmp["AbsRho"] = tmp["Spearman_rho_raw"].abs()
        print(
            tmp.sort_values("AbsRho", ascending=False)
            .head(20)[
                [
                    "Outcome", "Stage1_Metric", "N_Datasets",
                    "Spearman_rho_raw",
                    "Spearman_rho_quality_oriented",
                    "Spearman_p", "FDR_BH_q",
                ]
            ].to_string(index=False)
        )

    print("\nCLAIM-EVIDENCE SUMMARY")
    print(claim_summary.to_string(index=False))

    print("\nOUTPUT FILES")
    for p in outputs.values():
        print(p)

    elapsed = time.perf_counter() - t0
    print(f"\nElapsed time: {elapsed:.1f} s ({elapsed/60.0:.2f} min)")

    print("\nINTERPRETATION RULES")
    print(
        "1) Primary inference n is the physical Test×Receiver dataset.\n"
        "2) Product-adjusted results are a sensitivity analysis, not a "
        "replacement for raw product-stratified results.\n"
        "3) Repeated-product models use cluster-robust SE and dataset-level "
        "permutation where available.\n"
        "4) FDR-adjusted q-values are secondary to effect size/CI because n=12.\n"
        "5) Receiver class structures Stage-1 quality; associations are not "
        "causal effects."
    )


if __name__ == "__main__":
    main()
