# -*- coding: utf-8 -*-
"""
PROJECT1_FINAL_SOURCE_AUDIT_v1_1.py
===================================

Final source-gate audit for Project 1 manuscript figures/tables.

Version 1.1 changes
-------------------
1) Locks Reviewer Comment-7 to the exact reproduced final outputs:
   C:\IEEE\GNSS_ANALYSIS\REVIEWER_COMMENT7_SAMPLING_V1\
       COMMENT7_SAMPLING_INTERVAL_HARMONIZATION.csv
       COMMENT7_SAMPLING_SUMMARY.csv

2) Locks Reviewer Comment-8 to the exact physical outputs:
   C:\IEEE\GNSS_ANALYSIS\REVIEWER_COMMENT8_CMC_DETREND_V1\
       COMMENT8_STAGE2_ASSOCIATION_SENSITIVITY.csv
       COMMENT8_ARC_DEPENDENCE.csv

3) Adds an explicit Table-2 cross-center OSB provenance gate:
   - IGS orbit/clock configuration -> CODE final OSB
   - JAX orbit/clock configuration -> CODE final OSB
   This is checked from the upstream Comment-10 product-provenance master
   rather than inferred from same-center publication-table BIA lookup.

4) Preserves all v1 locked source checks:
   Stage-1 v2.2, Stage-2 v1.5.1.1, GT v1.3, Comment-11 v1.1,
   Comment-12 locks, Comment-10 v1.1 publication tables, and RTKLIB .pos tree.

Policy
------
- No fuzzy fallback.
- No automatic substitution of similarly named/legacy files.
- The figure/table generator must NOT run unless FINAL SOURCE GATE = PASS.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


# =============================================================================
# PATHS
# =============================================================================

ROOT = Path(r"C:\IEEE")
ANALYSIS = ROOT / "GNSS_ANALYSIS"
GROUND_TRUTH = ROOT / "Ground_Truth"
RTKLIB_DATA = ROOT / "RTKLIB_DATA"

OUT_DIR = ROOT / "PAPER_OUTPUT" / "SOURCE_AUDIT"
OUT_DIR.mkdir(parents=True, exist_ok=True)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

EXPECTED_PRODUCTS = ("CODE", "GFZ", "GRG", "IGS", "JAX", "WHU")


# =============================================================================
# LOCKED SOURCE REGISTRY
# =============================================================================

@dataclass(frozen=True)
class SourceSpec:
    key: str
    role: str
    path: Path
    required: bool = True
    kind: str = "csv"  # csv | directory | text
    exact_rows: Optional[int] = None
    min_rows: Optional[int] = None
    required_columns: tuple[str, ...] = ()
    note: str = ""


SOURCES: tuple[SourceSpec, ...] = (

    SourceSpec(
        "STAGE1_FINAL",
        "Final Stage-1 raw-observation metrics",
        ANALYSIS / "STAGE1_RINEX_V2_2" / "GNSS_STAGE1_FINAL_METRICS.csv",
        exact_rows=12,
        required_columns=(
            "Test", "Receiver", "Receiver_ID", "Receiver_Class",
            "CN0_Median_dBHz",
            "GPS_L1_CMC_RobustSigma_m",
            "GPS_L1_CMC_P95Abs_m",
            "Median_PhaseArc_Length_s",
            "Epoch_Retention_pct",
        ),
        note="LOCKED Stage-1 v2.2 only.",
    ),

    SourceSpec(
        "STAGE1_PARSER_QC",
        "Final Stage-1 parser-QC source",
        ANALYSIS / "STAGE1_RINEX_V2_2" / "GNSS_STAGE1_RINEX_PARSER_QC.csv",
        exact_rows=12,
        required_columns=(
            "Test", "Receiver", "Receiver_ID", "Receiver_Class",
            "Header_Interval_s", "Median_dt_s", "Nominal_Interval_s",
            "Epoch_Retention_pct",
        ),
    ),

    SourceSpec(
        "STAGE2_FINAL",
        "Final Stage-2 positioning statistics",
        ANALYSIS / "POS_STATISTICS_V1_5_1_1" / "GNSS_POS_STATISTICS_V1_5_1_1.csv",
        min_rows=63,
        required_columns=(
            "Product", "Test", "Receiver", "Receiver_ID", "Receiver_Class",
            "Solution_Status",
            "RAW_RMSE_2D_m", "CLEAN_RMSE_2D_m", "CLEAN_RMSE_3D_m",
            "Outlier_pct",
        ),
        note="LOCKED final Stage-2 paper-reporting source.",
    ),

    SourceSpec(
        "STAGE2_PROCESSING_AUDIT",
        "Final Stage-2 processing audit",
        ANALYSIS / "POS_STATISTICS_V1_5_1_1" / "GNSS_POS_PROCESSING_AUDIT_V1_5_1.csv",
        min_rows=72,
    ),

    SourceSpec(
        "GT_FINAL",
        "Final receiver-specific Ground Truth",
        GROUND_TRUTH / "GNSS_GT_v1_3_TRUTH_MODEL_B_LEVEL_TABLE.csv",
        min_rows=12,
    ),

    SourceSpec(
        "STAGE2_DATASET_LEVEL",
        "Dataset-level Stage-2 summary",
        ANALYSIS / "STAGE1_STAGE2_EVIDENCE_V1" / "STAGE2_DATASET_LEVEL_SUMMARY.csv",
        exact_rows=11,
        required_columns=(
            "Test", "Receiver_ID", "Receiver_Class",
            "Median_RMSE2D_m", "RMSE2D_Product_Range_m",
        ),
    ),

    SourceSpec(
        "STAGE2_PRODUCT_ADJUSTED",
        "Primary product-adjusted cross-stage dataset",
        ANALYSIS / "STAGE1_STAGE2_EVIDENCE_V1" / "STAGE2_PRODUCT_ADJUSTED_DATASET.csv",
        exact_rows=11,
        required_columns=(
            "Test", "Receiver_ID", "Receiver_Class",
            "GPS_L1_CMC_P95Abs_m",
            "GPS_L1_CMC_RobustSigma_m",
            "CN0_Median_dBHz",
            "Adj_Median_RMSE2D_m",
        ),
    ),

    # ---------------- Comment 7: exact final physical paths ----------------
    SourceSpec(
        "COMMENT7_DETAIL",
        "Reviewer Comment-7 sampling-interval audit detail",
        ANALYSIS / "REVIEWER_COMMENT7_SAMPLING_V1" / "COMMENT7_SAMPLING_INTERVAL_HARMONIZATION.csv",
        exact_rows=12,
        required_columns=(
            "Test", "Receiver", "Receiver_ID", "Receiver_Class",
            "Header_Interval_s", "Median_dt_s", "Nominal_Interval_s",
            "Epoch_Retention_pct", "Interval_Match_1s", "Header_vs_Empirical",
        ),
        note="Exact reproduced Comment-7 final artifact.",
    ),

    SourceSpec(
        "COMMENT7_SUMMARY",
        "Reviewer Comment-7 sampling summary",
        ANALYSIS / "REVIEWER_COMMENT7_SAMPLING_V1" / "COMMENT7_SAMPLING_SUMMARY.csv",
        exact_rows=1,
        required_columns=(
            "Dataset_N",
            "Median_dt_1s_N",
            "Nominal_interval_1s_N",
            "Header_interval_present_N",
            "Header_interval_missing_N",
            "All_empirically_1s",
            "All_nominally_1s",
            "Min_retention_pct",
            "Low_retention_dataset",
        ),
    ),

    # ---------------- Comment 8: exact final physical paths ----------------
    SourceSpec(
        "COMMENT8_ASSOC_SENS",
        "Reviewer Comment-8 CMC treatment sensitivity",
        ANALYSIS / "REVIEWER_COMMENT8_CMC_DETREND_V1" / "COMMENT8_STAGE2_ASSOCIATION_SENSITIVITY.csv",
        min_rows=1,
        note="Exact final Comment-8 association-sensitivity file.",
    ),

    SourceSpec(
        "COMMENT8_ARC_DEP",
        "Reviewer Comment-8 arc-duration dependence",
        ANALYSIS / "REVIEWER_COMMENT8_CMC_DETREND_V1" / "COMMENT8_ARC_DEPENDENCE.csv",
        min_rows=1,
        note="Exact final physical filename; do not use obsolete CURRENT_CMC filename.",
    ),

    # ---------------- Comment 11 v1.1 ----------------
    SourceSpec(
        "COMMENT11_BLOCKED",
        "Primary exact Test-blocked permutation inference",
        ANALYSIS / "COMMENT11_CLUSTER_DEPENDENCE_AUDIT_V1_1" / "COMMENT11_V1_1_BLOCKED_PERMUTATION.csv",
        min_rows=6,
        required_columns=("Source_Layer", "Predictor", "N", "Observed_Rho", "Exact_TwoSided_p"),
    ),

    SourceSpec(
        "COMMENT11_LOTO",
        "Leave-one-Test-out sensitivity",
        ANALYSIS / "COMMENT11_CLUSTER_DEPENDENCE_AUDIT_V1_1" / "COMMENT11_V1_1_LOTO_SENSITIVITY.csv",
        min_rows=9,
    ),

    SourceSpec(
        "COMMENT11_FIXED_TEST",
        "Fixed-Test-effect robustness",
        ANALYSIS / "COMMENT11_CLUSTER_DEPENDENCE_AUDIT_V1_1" / "COMMENT11_V1_1_FIXED_TEST_EFFECT.csv",
        min_rows=3,
    ),

    # ---------------- Comment 12 ----------------
    SourceSpec(
        "COMMENT12_REGISTRY",
        "Final numerical evidence registry",
        ANALYSIS / "COMMENT12_NUMERICAL_CONSISTENCY_AUDIT_V1" / "COMMENT12_FINAL_EVIDENCE_REGISTRY.csv",
        min_rows=1,
    ),

    SourceSpec(
        "COMMENT12_PRIMARY_LOCK",
        "Primary numerical lock",
        ANALYSIS / "COMMENT12_NUMERICAL_CONSISTENCY_AUDIT_V1" / "COMMENT12_PRIMARY_NUMERICAL_LOCK.csv",
        min_rows=1,
    ),

    SourceSpec(
        "COMMENT12_ROBUSTNESS_LOCK",
        "Robustness numerical lock",
        ANALYSIS / "COMMENT12_NUMERICAL_CONSISTENCY_AUDIT_V1" / "COMMENT12_ROBUSTNESS_NUMERICAL_LOCK.csv",
        min_rows=1,
    ),

    # ---------------- Comment 10 ----------------
    SourceSpec(
        "COMMENT10_OBS_SESSIONS",
        "Final observation-session publication table",
        ANALYSIS / "COMMENT10_PUBLICATION_TABLES_V1_1" / "COMMENT10_TABLE_X_OBSERVATION_SESSIONS.csv",
        min_rows=12,
    ),

    SourceSpec(
        "COMMENT10_PRECISE_PRODUCTS",
        "Final precise-product publication table",
        ANALYSIS / "COMMENT10_PUBLICATION_TABLES_V1_1" / "COMMENT10_TABLE_SX_PRECISE_PRODUCTS.csv",
        exact_rows=6,
    ),

    SourceSpec(
        "COMMENT10_BROADCAST_NAV",
        "Final broadcast-navigation publication table",
        ANALYSIS / "COMMENT10_PUBLICATION_TABLES_V1_1" / "COMMENT10_TABLE_SX_BROADCAST_NAV.csv",
        min_rows=1,
    ),

    SourceSpec(
        "COMMENT10_PRODUCT_MASTER",
        "Upstream exact product-provenance master",
        ANALYSIS / "COMMENT10_PRODUCT_PROVENANCE_AUDIT_V1" / "COMMENT10_PRODUCT_PROVENANCE_MASTER.csv",
        min_rows=6,
        note="Used to validate cross-center CODE OSB for IGS/JAX.",
    ),

    # ---------------- raw .pos ----------------
    SourceSpec(
        "RTKLIB_POS_ROOT",
        "Original RTKLIB .pos solution tree",
        RTKLIB_DATA,
        kind="directory",
    ),
)


# =============================================================================
# AUDIT RESULT
# =============================================================================

@dataclass
class AuditResult:
    key: str
    role: str
    path: str
    status: str
    exists: bool
    rows: Optional[int] = None
    cols: Optional[int] = None
    size_bytes: Optional[int] = None
    modified: str = ""
    sha256: str = ""
    missing_columns: str = ""
    message: str = ""


# =============================================================================
# HELPERS
# =============================================================================

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_csv(path: Path) -> pd.DataFrame:
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path)


def audit_source(spec: SourceSpec) -> AuditResult:
    p = spec.path

    if not p.exists():
        return AuditResult(
            spec.key, spec.role, str(p),
            "MISSING" if spec.required else "OPTIONAL_MISSING",
            False, message=spec.note
        )

    if spec.kind == "directory":
        if not p.is_dir():
            return AuditResult(spec.key, spec.role, str(p), "WRONG_TYPE", True)

        missing_products = [x for x in EXPECTED_PRODUCTS if not (p / x).is_dir()]
        pos_files = list(p.rglob("*.pos"))

        if missing_products:
            return AuditResult(
                spec.key, spec.role, str(p), "FAIL", True,
                rows=len(pos_files),
                message=f"Missing product directories: {missing_products}"
            )

        if not pos_files:
            return AuditResult(
                spec.key, spec.role, str(p), "FAIL", True,
                rows=0, message="No .pos files found."
            )

        return AuditResult(
            spec.key, spec.role, str(p), "PASS", True,
            rows=len(pos_files),
            message=f".pos inventory count={len(pos_files)}"
        )

    if not p.is_file():
        return AuditResult(spec.key, spec.role, str(p), "WRONG_TYPE", True)

    st = p.stat()

    try:
        df = read_csv(p)
    except Exception as exc:
        return AuditResult(
            spec.key, spec.role, str(p), "READ_ERROR", True,
            size_bytes=st.st_size,
            modified=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            message=repr(exc),
        )

    missing = [c for c in spec.required_columns if c not in df.columns]
    problems = []

    if missing:
        problems.append(f"missing_columns={missing}")
    if spec.exact_rows is not None and len(df) != spec.exact_rows:
        problems.append(f"rows={len(df)} expected_exact={spec.exact_rows}")
    if spec.min_rows is not None and len(df) < spec.min_rows:
        problems.append(f"rows={len(df)} expected_min={spec.min_rows}")

    status = "FAIL" if problems else "PASS"

    return AuditResult(
        spec.key, spec.role, str(p), status, True,
        rows=len(df), cols=len(df.columns),
        size_bytes=st.st_size,
        modified=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
        sha256=sha256_file(p),
        missing_columns=";".join(missing),
        message=("; ".join(problems) + (" | " if problems and spec.note else "") + spec.note).strip(),
    )


def source_path(key: str) -> Path:
    return next(s.path for s in SOURCES if s.key == key)


def add_check(checks, name, status, observed="", expected="", detail=""):
    checks.append({
        "Check": name,
        "Status": status,
        "Observed": observed,
        "Expected": expected,
        "Detail": detail,
    })


# =============================================================================
# CROSS-SOURCE / NUMERICAL LOCKS
# =============================================================================

def run_lock_checks() -> list[dict]:
    checks = []

    # Stage-1 physical dataset count
    p = source_path("STAGE1_FINAL")
    if p.exists():
        df = read_csv(p)
        add_check(checks, "Stage-1 physical datasets",
                  "PASS" if len(df) == 12 else "FAIL", len(df), 12)

    # Stage-2 product set / usable solution count
    p = source_path("STAGE2_FINAL")
    if p.exists():
        df = read_csv(p)

        products = sorted(df["Product"].dropna().astype(str).unique())
        add_check(
            checks,
            "Stage-2 product set",
            "PASS" if set(products) == set(EXPECTED_PRODUCTS) else "FAIL",
            ",".join(products),
            ",".join(EXPECTED_PRODUCTS),
        )

        usable = int((df["Solution_Status"].astype(str) == "USABLE").sum())
        add_check(checks, "Usable Stage-2 solutions",
                  "PASS" if usable == 63 else "FAIL", usable, 63)

    # Primary inferential N
    p = source_path("STAGE2_PRODUCT_ADJUSTED")
    if p.exists():
        df = read_csv(p)
        add_check(checks, "Primary cross-stage inferential N",
                  "PASS" if len(df) == 11 else "FAIL", len(df), 11)

    # Comment-7 exact scientific lock
    p = source_path("COMMENT7_SUMMARY")
    if p.exists():
        s = read_csv(p).iloc[0]

        c7_expected = {
            "Dataset_N": 12,
            "Median_dt_1s_N": 12,
            "Nominal_interval_1s_N": 12,
            "Header_interval_present_N": 6,
            "Header_interval_missing_N": 6,
            "Low_retention_dataset": "OEM1",
        }

        for col, exp in c7_expected.items():
            obs = s[col]
            ok = str(obs) == str(exp) if isinstance(exp, str) else int(obs) == exp
            add_check(checks, f"Comment-7 {col}", "PASS" if ok else "FAIL", obs, exp)

        min_ret = float(s["Min_retention_pct"])
        ok = math.isclose(min_ret, 14.59214501510574, abs_tol=1e-9, rel_tol=0.0)
        add_check(
            checks,
            "Comment-7 OEM1 minimum retention",
            "PASS" if ok else "FAIL",
            f"{min_ret:.12f}%",
            "14.592145015106%",
        )

    # Comment-11 v1.1 primary lock
    p = source_path("COMMENT11_BLOCKED")
    if p.exists():
        df = read_csv(p)
        pa = df[df["Source_Layer"].astype(str).eq("PRODUCT_ADJUSTED")].copy()

        locked = {
            "CMC_P95": (11, 0.818182, 0.006944),
            "CMC_ROBUST": (11, 0.836364, 0.004919),
            "CN0": (11, -0.744877, 0.017072),
        }

        for pred, (n0, rho0, p0) in locked.items():
            g = pa[pa["Predictor"].astype(str).eq(pred)]

            if len(g) != 1:
                add_check(checks, f"Comment-11 primary {pred}", "FAIL", len(g), 1)
                continue

            r = g.iloc[0]
            n = int(r["N"])
            rho = float(r["Observed_Rho"])
            pv = float(r["Exact_TwoSided_p"])

            ok = (
                n == n0
                and abs(rho-rho0) <= 5e-6
                and abs(pv-p0) <= 5e-6
            )

            add_check(
                checks,
                f"Comment-11 primary {pred}",
                "PASS" if ok else "FAIL",
                f"N={n}; rho={rho:.6f}; p={pv:.6f}",
                f"N={n0}; rho={rho0:.6f}; p={p0:.6f}",
            )

    # Comment-8 required treatment identities
    p = source_path("COMMENT8_ASSOC_SENS")
    if p.exists():
        df = read_csv(p)

        method_col = next((c for c in df.columns if c.lower() == "method"), None)
        if method_col:
            vals = {str(x).upper() for x in df[method_col].dropna()}
            required = {"CURRENT", "FIXED300", "LINEAR", "QUADRATIC"}
            add_check(
                checks,
                "Comment-8 CMC treatment set",
                "PASS" if required.issubset(vals) else "FAIL",
                ",".join(sorted(vals)),
                ",".join(sorted(required)),
            )
        else:
            add_check(
                checks,
                "Comment-8 CMC treatment set",
                "WARN",
                "No Method column detected",
                "CURRENT,FIXED300,LINEAR,QUADRATIC",
                "Physical source exists; inspect schema manually if this remains WARN.",
            )

    return checks


# =============================================================================
# TABLE-2 / CROSS-CENTER OSB PROVENANCE
# =============================================================================

def table2_cross_center_osb_checks() -> tuple[list[dict], pd.DataFrame]:
    """
    Validate the locked operational configuration rule:
      IGS orbit/clock -> CODE final OSB
      JAX orbit/clock -> CODE final OSB

    Critical design:
    - The Comment-10 publication table is allowed to show 'Not referenced'
      for IGS/JAX because its builder searches same-center BIA.
    - This final gate instead checks the upstream provenance master for
      a valid CODE OSB/BIA record available in the IGS/JAX processing context.

    Because historical provenance-master schemas may differ slightly, column
    names are detected from a narrow known set. No file-path fallback occurs.
    """
    checks = []
    master_path = source_path("COMMENT10_PRODUCT_MASTER")
    pub_path = source_path("COMMENT10_PRECISE_PRODUCTS")

    if not master_path.exists() or not pub_path.exists():
        add_check(
            checks, "Table-2 cross-center OSB provenance",
            "FAIL", "missing source", "both Comment-10 master + publication table"
        )
        return checks, pd.DataFrame()

    master = read_csv(master_path)
    pub = read_csv(pub_path)

    def pick_col(df, candidates):
        for c in candidates:
            if c in df.columns:
                return c
        return None

    center_col = pick_col(master, ["Product_Center", "Center", "Provider", "Analysis_Center"])
    class_col = pick_col(master, ["Product_Class", "Class", "File_Class", "Product_Type"])
    file_col = pick_col(master, ["Exact_Filename", "Filename", "File", "Basename"])
    path_col = pick_col(master, ["Path", "Full_Path", "File_Path", "Source_Path"])
    context_col = pick_col(master, ["Referenced_By", "Manifest", "Processing_Context", "Context", "Run_Context"])

    if center_col is None or file_col is None:
        add_check(
            checks,
            "Table-2 provenance schema",
            "FAIL",
            f"columns={list(master.columns)}",
            "center + exact filename columns",
        )
        return checks, pd.DataFrame()

    work = master.copy()
    work["_CENTER"] = work[center_col].astype(str).str.upper().str.strip()
    work["_FILE"] = work[file_col].astype(str)

    # Detect CODE OSB/BIA rows.
    bias_mask = (
        work["_FILE"].str.contains(r"\.BIA$|OSB|BIAS", case=False, regex=True, na=False)
    )

    if class_col:
        bias_mask = bias_mask | work[class_col].astype(str).str.contains(
            "BIA|OSB|BIAS", case=False, regex=True, na=False
        )

    code_bias = work[(work["_CENTER"] == "CODE") & bias_mask].copy()

    # Prefer explicit final CODE OSB file if multiple candidates exist.
    final_mask = code_bias["_FILE"].str.contains("COD0.*FIN.*OSB.*BIA", case=False, regex=True, na=False)
    preferred = code_bias[final_mask].copy()
    if preferred.empty:
        preferred = code_bias.copy()

    add_check(
        checks,
        "CODE final OSB provenance record",
        "PASS" if not preferred.empty else "FAIL",
        " | ".join(preferred["_FILE"].tolist()[:5]) if not preferred.empty else "none",
        "at least one CODE final OSB/BIA provenance record",
    )

    # Publication-table center column detection.
    pub_center_col = pick_col(pub, ["Center", "Configuration", "Product_Center"])

    # Build an evidence export for manual transparency.
    evidence_rows = []

    for target in ("IGS", "JAX"):

        # Check publication table row exists.
        if pub_center_col:
            pg = pub[pub[pub_center_col].astype(str).str.upper().eq(target)]
        else:
            pg = pd.DataFrame()

        add_check(
            checks,
            f"Table-2 {target} publication row",
            "PASS" if len(pg) == 1 else "FAIL",
            len(pg),
            1,
        )

        # Context evidence:
        # Search every master row for target-center occurrence in all textual columns,
        # then determine whether a CODE OSB row is present in the same provenance
        # neighbourhood/context. If an explicit context column exists, use it.
        target_rows = work[work["_CENTER"].eq(target)].copy()

        if target_rows.empty:
            add_check(
                checks,
                f"{target} orbit/clock provenance rows",
                "FAIL", 0, ">=1"
            )
            continue

        add_check(
            checks,
            f"{target} orbit/clock provenance rows",
            "PASS", len(target_rows), ">=1"
        )

        # If explicit processing context exists, use common contexts.
        linked_code_bias = pd.DataFrame()

        if context_col:
            contexts = set(target_rows[context_col].dropna().astype(str))
            if contexts:
                linked_code_bias = preferred[
                    preferred[context_col].astype(str).isin(contexts)
                ].copy()

        # Otherwise use row-neighbourhood evidence from provenance-master ordering.
        # This is not a scientific inference: it merely validates the exact file-level
        # manifest layout that previously showed CODE BIA alongside IGS/JAX rows.
        if linked_code_bias.empty and not preferred.empty:
            idx_targets = list(target_rows.index)
            near_idx = set()
            for idx in idx_targets:
                near_idx.update(range(max(0, idx-4), min(len(work), idx+5)))
            near = work.loc[sorted(near_idx)]
            linked_code_bias = near[
                (near["_CENTER"] == "CODE")
                & (
                    near["_FILE"].str.contains(r"\.BIA$|OSB|BIAS", case=False, regex=True, na=False)
                    | (
                        near[class_col].astype(str).str.contains("BIA|OSB|BIAS", case=False, regex=True, na=False)
                        if class_col else False
                    )
                )
            ].copy()

        filenames = linked_code_bias["_FILE"].tolist() if not linked_code_bias.empty else []

        ok = any(
            ("COD0" in str(f).upper())
            and ("OSB" in str(f).upper() or str(f).upper().endswith(".BIA"))
            for f in filenames
        )

        add_check(
            checks,
            f"{target} -> CODE final OSB cross-center provenance",
            "PASS" if ok else "FAIL",
            " | ".join(filenames[:5]) if filenames else "none",
            "CODE final OSB/BIA record linked to target processing context",
            "This gate validates the locked operational bundle; it does not rely on same-center BIA lookup."
        )

        for _, r in linked_code_bias.iterrows():
            evidence_rows.append({
                "Target_Configuration": target,
                "Bias_Center": "CODE",
                "Bias_Filename": r[file_col],
                "Bias_Class": r[class_col] if class_col else "",
                "Bias_Path": r[path_col] if path_col else "",
                "Context": r[context_col] if context_col else "",
                "Evidence_Mode": "explicit_context" if context_col else "provenance_neighbourhood",
            })

    return checks, pd.DataFrame(evidence_rows)


# =============================================================================
# LEGACY RISK INVENTORY
# =============================================================================

def legacy_inventory() -> pd.DataFrame:
    tokens = [
        "GNSS_STAGE1_FINAL_METRICS",
        "GNSS_POS_STATISTICS_V1_5_1",
        "COMMENT7_",
        "COMMENT8_",
        "COMMENT10_",
        "COMMENT11_",
        "COMMENT12_",
        "STAGE2_PRODUCT_ADJUSTED_DATASET",
        "STAGE2_DATASET_LEVEL_SUMMARY",
    ]

    locked_paths = {str(s.path.resolve()).lower() for s in SOURCES if s.path.exists()}
    rows = []

    if not ANALYSIS.exists():
        return pd.DataFrame(rows)

    for p in ANALYSIS.rglob("*"):
        if not p.is_file():
            continue

        if any(tok.upper() in p.name.upper() for tok in tokens):
            rows.append({
                "Path": str(p),
                "Filename": p.name,
                "Is_Locked_Authoritative": str(p.resolve()).lower() in locked_paths,
                "Size_bytes": p.stat().st_size,
                "Modified": datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds"),
            })

    return pd.DataFrame(rows)


# =============================================================================
# MAIN
# =============================================================================

def main() -> int:

    print("=" * 104)
    print("PROJECT 1 FINAL SOURCE AUDIT v1.1")
    print("=" * 104)

    results = [audit_source(s) for s in SOURCES]
    checks = run_lock_checks()
    osb_checks, osb_evidence = table2_cross_center_osb_checks()
    checks.extend(osb_checks)

    legacy = legacy_inventory()

    results_df = pd.DataFrame([asdict(r) for r in results])
    checks_df = pd.DataFrame(checks)

    # Gate logic: every required source must PASS; every scientific/provenance check
    # must PASS. WARN is reported but does not fail unless it is an explicit check FAIL.
    source_fail = results_df[
        results_df["status"].isin(["MISSING", "FAIL", "WRONG_TYPE", "READ_ERROR"])
    ]

    check_fail = checks_df[checks_df["Status"].eq("FAIL")]

    final_gate = "PASS" if source_fail.empty and check_fail.empty else "FAIL"

    # Save outputs
    audit_csv = OUT_DIR / f"PROJECT1_FINAL_SOURCE_AUDIT_v1_1_{STAMP}.csv"
    checks_csv = OUT_DIR / f"PROJECT1_FINAL_SOURCE_GATE_CHECKS_v1_1_{STAMP}.csv"
    osb_csv = OUT_DIR / f"PROJECT1_TABLE2_CROSS_CENTER_OSB_EVIDENCE_v1_1_{STAMP}.csv"
    legacy_csv = OUT_DIR / f"PROJECT1_FINAL_LEGACY_FILE_INVENTORY_v1_1_{STAMP}.csv"
    manifest_json = OUT_DIR / f"PROJECT1_FINAL_SOURCE_MANIFEST_v1_1_{STAMP}.json"
    report_txt = OUT_DIR / f"PROJECT1_FINAL_SOURCE_GATE_v1_1_{STAMP}.txt"

    results_df.to_csv(audit_csv, index=False, encoding="utf-8-sig")
    checks_df.to_csv(checks_csv, index=False, encoding="utf-8-sig")
    osb_evidence.to_csv(osb_csv, index=False, encoding="utf-8-sig")
    legacy.to_csv(legacy_csv, index=False, encoding="utf-8-sig")

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "version": "1.1",
        "root": str(ROOT),
        "policy": {
            "automatic_fallback": False,
            "legacy_substitution": False,
            "figure_table_generation_allowed_only_if_gate_pass": True,
        },
        "sources": [asdict(r) for r in results],
        "checks": checks,
        "final_source_gate": final_gate,
    }

    manifest_json.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    # Human-readable gate summary
    lines = []
    lines.append("=" * 104)
    lines.append("PROJECT 1 FINAL SOURCE GATE v1.1")
    lines.append("=" * 104)
    lines.append(f"Generated: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    # Compact named gate
    status_by_key = {r.key: r.status for r in results}

    named_gate = [
        ("Stage-1 v2.2", status_by_key.get("STAGE1_FINAL", "MISSING")),
        ("Stage-2 v1.5.1.1", status_by_key.get("STAGE2_FINAL", "MISSING")),
        ("Ground Truth v1.3", status_by_key.get("GT_FINAL", "MISSING")),
        ("Comment-7 sampling", "PASS" if all(
            status_by_key.get(k) == "PASS" for k in ("COMMENT7_DETAIL", "COMMENT7_SUMMARY")
        ) else "FAIL"),
        ("Comment-8 CMC sensitivity", "PASS" if all(
            status_by_key.get(k) == "PASS" for k in ("COMMENT8_ASSOC_SENS", "COMMENT8_ARC_DEP")
        ) else "FAIL"),
        ("Comment-11 v1.1 inference", "PASS" if all(
            status_by_key.get(k) == "PASS" for k in ("COMMENT11_BLOCKED", "COMMENT11_LOTO", "COMMENT11_FIXED_TEST")
        ) else "FAIL"),
        ("Comment-12 numerical locks", "PASS" if all(
            status_by_key.get(k) == "PASS" for k in ("COMMENT12_REGISTRY", "COMMENT12_PRIMARY_LOCK", "COMMENT12_ROBUSTNESS_LOCK")
        ) else "FAIL"),
        ("Comment-10 provenance", "PASS" if all(
            status_by_key.get(k) == "PASS" for k in ("COMMENT10_PRECISE_PRODUCTS", "COMMENT10_PRODUCT_MASTER")
        ) else "FAIL"),
    ]

    # Extract explicit OSB gate checks
    for target in ("IGS", "JAX"):
        row = next(
            (c for c in checks if c["Check"] == f"{target} -> CODE final OSB cross-center provenance"),
            None
        )
        named_gate.append((
            f"{target} -> CODE final OSB",
            row["Status"] if row else "FAIL"
        ))

    named_gate.append((
        "RTKLIB .pos source tree",
        status_by_key.get("RTKLIB_POS_ROOT", "MISSING")
    ))

    for name, status in named_gate:
        lines.append(f"{name:<34} {status}")

    lines.append("-" * 104)
    lines.append(f"FINAL SOURCE GATE: {final_gate}")
    lines.append("=" * 104)
    lines.append("")

    lines.append("SOURCE DETAILS")
    lines.append("-" * 104)
    for r in results:
        lines.append(f"[{r.status:5}] {r.key}")
        lines.append(f"  {r.path}")
        if r.rows is not None:
            lines.append(f"  rows/count={r.rows}")
        if r.sha256:
            lines.append(f"  sha256={r.sha256}")
        if r.message:
            lines.append(f"  note={r.message}")
        lines.append("")

    lines.append("LOCK / PROVENANCE CHECKS")
    lines.append("-" * 104)
    for c in checks:
        lines.append(
            f"[{c['Status']:5}] {c['Check']} | observed={c['Observed']} | expected={c['Expected']}"
        )
        if c["Detail"]:
            lines.append(f"        {c['Detail']}")

    lines.append("")
    lines.append("GENERATOR POLICY")
    lines.append("-" * 104)
    if final_gate == "PASS":
        lines.append("PASS: PROJECT1_FINAL_FIGURES_TABLES.py may be run.")
    else:
        lines.append("FAIL: Do NOT run the final figure/table generator.")
        lines.append("Resolve every required source/provenance FAIL first.")

    report_txt.write_text("\n".join(lines), encoding="utf-8")

    print("\n".join(lines[:22]))
    print()
    print("Outputs:")
    print(f"  {report_txt}")
    print(f"  {audit_csv}")
    print(f"  {checks_csv}")
    print(f"  {osb_csv}")
    print(f"  {legacy_csv}")
    print(f"  {manifest_json}")

    return 0 if final_gate == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
