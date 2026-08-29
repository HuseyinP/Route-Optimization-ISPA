# -*- coding: utf-8 -*-
r"""
GNSS_STAGE1_STAGE2_EVIDENCE_v1_2_MODEL_ONLY.py

Two final patches before the Evidence Matrix:

1) Correct claim-evidence selection:
   supporting evidence must have the hypothesized direction, not merely
   the largest absolute correlation.

2) Product-fixed-effect repeated analysis without statsmodels:
   Frisch-Waugh-Lovell residualization + dataset-level permutation.
   The inferential unit remains the physical Test×Receiver dataset.

INPUTS
------
Reads existing EVIDENCE v1 CSV outputs. No raw RINEX/POS reprocessing.

OUTPUTS
-------
STAGE1_STAGE2_REPEATED_MODEL_V1_2.csv
CLAIM_EVIDENCE_SUMMARY_V1_2.csv
EVIDENCE_DIRECTION_AUDIT_V1_2.csv
"""

from pathlib import Path
import time
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(r"C:\IEEE")
ANALYSIS_ROOT = ROOT / "GNSS_ANALYSIS"

INPUT_DIR_CANDIDATES = [
    ANALYSIS_ROOT / "STAGE1_STAGE2_EVIDENCE_V1",
    ANALYSIS_ROOT / "STAGE1_STAGE2_EVIDENCE_V1_1_FAST",
]
OUT_DIR = ANALYSIS_ROOT / "STAGE1_STAGE2_EVIDENCE_V1_2_MODEL_ONLY"
OUT_DIR.mkdir(parents=True, exist_ok=True)

RANDOM_SEED = 20260816
PERM_N = 10000
rng = np.random.default_rng(RANDOM_SEED)

CORE_METRICS = [
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
}

# All listed Stage-2 endpoints are "lower is better".
# Therefore a SUPPORTING quality-oriented association is rho_Q < 0.
LOWER_IS_BETTER_OUTCOMES = {
    "Median_RMSE2D_m",
    "Median_RMSE3D_m",
    "Median_Contamination_pct",
    "Median_AbsBiasU_m",
    "Adj_Median_RMSE2D_m",
    "Adj_Median_RMSE3D_m",
    "Adj_Median_Contamination_pct",
    "Adj_Median_AbsBiasU_m",
    "RMSE2D_Product_Range_m",
    "RMSE2D_Product_IQR_m",
    "RMSE2D_Product_CV_pct",
    "RMSE2D_Product_MaxMinRatio",
}

MODEL_OUTCOMES = [
    "CLEAN_RMSE_2D_m",
    "CLEAN_RMSE_3D_m",
    "Outlier_pct",
    "Abs_Bias_U_m",
]

USABLE_LABEL = "USABLE"


def locate_input_dir():
    for d in INPUT_DIR_CANDIDATES:
        if (d / "STAGE1_STAGE2_MERGED_LONG.csv").exists():
            return d

    hits = list(ANALYSIS_ROOT.rglob("STAGE1_STAGE2_MERGED_LONG.csv"))
    if hits:
        return hits[0].parent

    raise FileNotFoundError("STAGE1_STAGE2_MERGED_LONG.csv not found.")


def robust_z_numpy(x):
    x = np.asarray(x, float)
    med = np.nanmedian(x)
    mad = np.nanmedian(np.abs(x - med))
    scale = 1.4826 * mad
    if not np.isfinite(scale) or scale <= 1e-12:
        return np.full_like(x, np.nan)
    return (x - med) / scale


def product_design(products):
    s = pd.Series(products).astype(str)
    levels = sorted(s.unique())
    X = np.ones((len(s), 1), float)
    for level in levels[1:]:
        X = np.column_stack([X, (s.to_numpy() == level).astype(float)])
    return X


def residualize(v, X):
    beta, *_ = np.linalg.lstsq(X, np.asarray(v, float), rcond=None)
    return np.asarray(v, float) - X @ beta


def fwl_coef(y, x, Xprod):
    yr = residualize(y, Xprod)
    xr = residualize(x, Xprod)
    den = float(xr @ xr)
    return float((xr @ yr) / den) if den > 1e-15 else np.nan


def dataset_permutation_model(df, outcome, metric, perm_n=PERM_N):
    d = df[["Dataset_ID", "Product", outcome, metric]].copy()
    d[outcome] = pd.to_numeric(d[outcome], errors="coerce")
    d[metric] = pd.to_numeric(d[metric], errors="coerce")
    d = d.dropna()

    ds = d[["Dataset_ID", metric]].drop_duplicates("Dataset_ID").sort_values("Dataset_ID")
    if len(ds) < 4:
        return None

    ids = ds["Dataset_ID"].astype(str).tolist()
    vals = ds[metric].to_numpy(float)
    idmap = {k: i for i, k in enumerate(ids)}
    row_idx = np.array([idmap[str(v)] for v in d["Dataset_ID"]], int)

    zds = robust_z_numpy(vals)
    if not np.all(np.isfinite(zds)):
        return None

    x = zds[row_idx]
    y = d[outcome].to_numpy(float)
    Xp = product_design(d["Product"])
    yres = residualize(y, Xp)
    xres = residualize(x, Xp)
    den = float(xres @ xres)
    if den <= 1e-15:
        return None

    coef = float((xres @ yres) / den)

    # R2 increment attributable to the Stage-1 metric after product FE.
    sse0 = float(yres @ yres)
    resid_full = yres - coef * xres
    sse1 = float(resid_full @ resid_full)
    partial_r2 = (sse0 - sse1) / sse0 if sse0 > 1e-15 else np.nan

    extreme = 0
    valid = 0
    for _ in range(perm_n):
        zp = robust_z_numpy(rng.permutation(vals))
        xp = zp[row_idx]
        xpr = residualize(xp, Xp)
        denp = float(xpr @ xpr)
        if denp <= 1e-15:
            continue
        cp = float((xpr @ yres) / denp)
        valid += 1
        if abs(cp) >= abs(coef):
            extreme += 1

    pperm = (extreme + 1) / (valid + 1) if valid else np.nan

    return {
        "Outcome": outcome,
        "Stage1_Metric": metric,
        "N_Rows": len(d),
        "N_Datasets": d["Dataset_ID"].nunique(),
        "N_Products": d["Product"].nunique(),
        "Coef_per_RobustSD_rawMetric": coef,
        "Coef_quality_oriented": coef * QUALITY_DIRECTION[metric],
        "Partial_R2_after_ProductFE": partial_r2,
        "DatasetPermutation_p": pperm,
        "Permutation_N": valid,
        "Model": f"{outcome} ~ robust_z({metric}) + Product fixed effects",
        "Status": "OK",
    }


def direction_audit(table, source):
    rows = []
    if table is None or table.empty:
        return pd.DataFrame()

    for _, r in table.iterrows():
        outcome = r.get("Outcome")
        rhoq = pd.to_numeric(pd.Series([r.get("Spearman_rho_quality_oriented")]),
                             errors="coerce").iloc[0]
        if not np.isfinite(rhoq):
            status = "NOT_ESTIMABLE"
        elif outcome in LOWER_IS_BETTER_OUTCOMES:
            status = "SUPPORTING" if rhoq < 0 else "OPPOSING"
        else:
            status = "UNSPECIFIED"

        row = r.to_dict()
        row["Source_Table"] = source
        row["Hypothesized_Direction"] = (
            "rho_quality_oriented < 0" if outcome in LOWER_IS_BETTER_OUTCOMES
            else "not pre-specified"
        )
        row["Evidence_Direction"] = status
        rows.append(row)
    return pd.DataFrame(rows)


def strongest_supporting(audit_df, outcome):
    g = audit_df[
        (audit_df["Outcome"] == outcome) &
        (audit_df["Evidence_Direction"] == "SUPPORTING")
    ].copy()
    if g.empty:
        return None

    # Prefer FDR q, then p, then largest |rho|.
    g["_q"] = pd.to_numeric(g.get("FDR_BH_q"), errors="coerce")
    g["_p"] = pd.to_numeric(g.get("Spearman_p"), errors="coerce")
    g["_absrho"] = pd.to_numeric(
        g.get("Spearman_rho_quality_oriented"), errors="coerce"
    ).abs()

    g["_qsort"] = g["_q"].fillna(np.inf)
    g["_psort"] = g["_p"].fillna(np.inf)

    return g.sort_values(
        ["_qsort", "_psort", "_absrho"],
        ascending=[True, True, False]
    ).iloc[0]


def evidence_text(r):
    if r is None:
        return "No directionally supporting estimable association."
    return (
        f"{r['Stage1_Metric']}: "
        f"rhoQ={r['Spearman_rho_quality_oriented']:.3f}, "
        f"n={int(r['N_Datasets'])}, "
        f"p={r['Spearman_p']:.4g}, "
        f"q={r['FDR_BH_q']:.4g}"
    )


def main():
    t0 = time.perf_counter()
    inp = locate_input_dir()

    print("=" * 120)
    print("GNSS STAGE1-STAGE2 EVIDENCE v1.2 MODEL-ONLY")
    print("=" * 120)
    print("Input :", inp)
    print("Output:", OUT_DIR)
    print("Permutation N:", PERM_N)

    long_df = pd.read_csv(inp / "STAGE1_STAGE2_MERGED_LONG.csv")
    primary = pd.read_csv(inp / "STAGE1_STAGE2_SPEARMAN_PRIMARY.csv")
    adjusted = pd.read_csv(inp / "STAGE1_STAGE2_SPEARMAN_PRODUCT_ADJUSTED.csv")
    sens = pd.read_csv(inp / "STAGE1_PRODUCT_SENSITIVITY_ASSOCIATIONS.csv")
    dataset = pd.read_csv(inp / "STAGE2_DATASET_LEVEL_SUMMARY.csv")

    if "Dataset_ID" not in long_df.columns:
        long_df["Dataset_ID"] = (
            long_df["Test"].astype(str) + "|" +
            long_df["Receiver_ID"].astype(str)
        )

    if "Abs_Bias_U_m" not in long_df.columns:
        long_df["Abs_Bias_U_m"] = pd.to_numeric(
            long_df["CLEAN_Bias_U_m"], errors="coerce"
        ).abs()

    usable = long_df[long_df["Solution_Status"] == USABLE_LABEL].copy()

    # 1) Product-FE repeated model
    model_rows = []
    total = len(MODEL_OUTCOMES) * len(CORE_METRICS)
    k = 0
    for outcome in MODEL_OUTCOMES:
        for metric in CORE_METRICS:
            k += 1
            print(f"[{k:02d}/{total:02d}] {outcome} ~ {metric}")
            if outcome not in usable.columns or metric not in usable.columns:
                continue
            res = dataset_permutation_model(usable, outcome, metric)
            if res is not None:
                model_rows.append(res)

    models = pd.DataFrame(model_rows)

    # 2) Direction audit
    audit = pd.concat([
        direction_audit(primary, "PRIMARY"),
        direction_audit(adjusted, "PRODUCT_ADJUSTED"),
        direction_audit(sens, "PRODUCT_SENSITIVITY"),
    ], ignore_index=True)

    # 3) Corrected claim summary
    p2 = strongest_supporting(audit[audit["Source_Table"] == "PRIMARY"],
                              "Median_RMSE2D_m")
    p3 = strongest_supporting(audit[audit["Source_Table"] == "PRIMARY"],
                              "Median_RMSE3D_m")
    pc = strongest_supporting(audit[audit["Source_Table"] == "PRIMARY"],
                              "Median_Contamination_pct")
    ps = strongest_supporting(audit[audit["Source_Table"] == "PRODUCT_SENSITIVITY"],
                              "RMSE2D_Product_Range_m")

    claims = pd.DataFrame([
        {
            "Claim_ID": "C8A",
            "Claim": "Better raw-observation quality is associated with lower horizontal positioning error.",
            "Evidence": evidence_text(p2),
            "Status": "SUPPORTED" if p2 is not None else "NOT_SUPPORTED",
            "Rule": "Only directionally supporting associations eligible."
        },
        {
            "Claim_ID": "C8A-3D",
            "Claim": "Better raw-observation quality is associated with lower 3D positioning error.",
            "Evidence": evidence_text(p3),
            "Status": "SUPPORTED" if p3 is not None else "NOT_SUPPORTED",
            "Rule": "Only directionally supporting associations eligible."
        },
        {
            "Claim_ID": "C8B",
            "Claim": "Better raw-observation quality is associated with lower epoch-level contamination.",
            "Evidence": evidence_text(pc),
            "Status": "SUPPORTED" if pc is not None else "NOT_SUPPORTED",
            "Rule": "Only directionally supporting associations eligible."
        },
        {
            "Claim_ID": "C8C",
            "Claim": "Better raw-observation quality is associated with lower absolute precise-product sensitivity.",
            "Evidence": evidence_text(ps),
            "Status": "SUPPORTED" if ps is not None else "NOT_SUPPORTED",
            "Rule": "Primary sensitivity endpoint = RMSE2D product range."
        },
    ])

    models.to_csv(
        OUT_DIR / "STAGE1_STAGE2_REPEATED_MODEL_V1_2.csv",
        index=False, encoding="utf-8-sig"
    )
    audit.to_csv(
        OUT_DIR / "EVIDENCE_DIRECTION_AUDIT_V1_2.csv",
        index=False, encoding="utf-8-sig"
    )
    claims.to_csv(
        OUT_DIR / "CLAIM_EVIDENCE_SUMMARY_V1_2.csv",
        index=False, encoding="utf-8-sig"
    )

    print("\nCORRECTED CLAIM SUMMARY")
    print(claims.to_string(index=False))

    if not models.empty:
        print("\nTOP PRODUCT-FE MODELS BY PERMUTATION p")
        print(
            models.sort_values("DatasetPermutation_p")
            .head(15)[[
                "Outcome", "Stage1_Metric", "N_Datasets",
                "Coef_quality_oriented",
                "Partial_R2_after_ProductFE",
                "DatasetPermutation_p"
            ]].to_string(index=False)
        )

    print(f"\nElapsed: {time.perf_counter()-t0:.1f} s")
    print("Done.")


if __name__ == "__main__":
    main()
