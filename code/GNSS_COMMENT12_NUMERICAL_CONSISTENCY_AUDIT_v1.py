# -*- coding: utf-8 -*-
"""
GNSS_COMMENT12_NUMERICAL_CONSISTENCY_AUDIT_v1.py
================================================

Reviewer Comment 12 — Numerical consistency / single source of truth

Purpose
-------
Create a machine-readable numerical evidence registry before auditing the
manuscript itself. The registry separates:

PRIMARY INFERENCE
    product-adjusted + exact Test-blocked permutation

ROBUSTNESS EVIDENCE
    unadjusted + exact Test-blocked permutation
    LOTO
    fixed-Test-effect residual analysis

DESCRIPTIVE CLUSTERING DIAGNOSTICS
    within/between-Test variance + ICC(Test)

The script does not silently recompute or overwrite the final statistics.
It reads the finalized Comment-11 outputs and locks exact source values,
source files, and source rows. This prevents CMC P95 vs robust sigma,
adjusted vs unadjusted, and 2D vs other outcomes from being mixed in the
manuscript.

Expected input directory
------------------------
C:\\IEEE\\GNSS_ANALYSIS\\COMMENT11_CLUSTER_DEPENDENCE_AUDIT_V1_1

Required inputs
---------------
COMMENT11_V1_1_BLOCKED_PERMUTATION.csv
COMMENT11_V1_1_LOTO_SENSITIVITY.csv
COMMENT11_V1_1_FIXED_TEST_EFFECT.csv
COMMENT11_V1_1_VARIANCE_ICC.csv

Outputs
-------
C:\\IEEE\\GNSS_ANALYSIS\\COMMENT12_NUMERICAL_CONSISTENCY_AUDIT_V1\\

COMMENT12_FINAL_EVIDENCE_REGISTRY.csv
COMMENT12_PRIMARY_NUMERICAL_LOCK.csv
COMMENT12_ROBUSTNESS_NUMERICAL_LOCK.csv
COMMENT12_DESCRIPTIVE_DIAGNOSTIC_LOCK.csv
COMMENT12_NUMERICAL_CONSISTENCY_SUMMARY.txt
COMMENT12_BLOCKERS.csv                         # only if needed

Important
---------
v1 answers: "What are the authoritative final numbers?"
A later manuscript-audit step can compare Abstract/Results/Discussion/
Conclusions/Tables against this registry.
"""

from pathlib import Path
import csv
import math
import pandas as pd
import numpy as np

ROOT = Path(r"C:\IEEE")
SRC = ROOT / "GNSS_ANALYSIS" / "COMMENT11_CLUSTER_DEPENDENCE_AUDIT_V1_1"
OUT = ROOT / "GNSS_ANALYSIS" / "COMMENT12_NUMERICAL_CONSISTENCY_AUDIT_V1"
OUT.mkdir(parents=True, exist_ok=True)

F_PERM = SRC / "COMMENT11_V1_1_BLOCKED_PERMUTATION.csv"
F_LOTO = SRC / "COMMENT11_V1_1_LOTO_SENSITIVITY.csv"
F_FIXED = SRC / "COMMENT11_V1_1_FIXED_TEST_EFFECT.csv"
F_ICC = SRC / "COMMENT11_V1_1_VARIANCE_ICC.csv"

EXPECTED_PREDICTORS = ["CMC_P95", "CMC_ROBUST", "CN0"]
EXPECTED_LAYERS = ["PRODUCT_ADJUSTED", "UNADJUSTED"]


def write_csv(path, rows, fields=None):
    if fields is None:
        fields = list(rows[0].keys()) if rows else ["Status"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def finite(x):
    try:
        return math.isfinite(float(x))
    except Exception:
        return False


def source_row(df, idx):
    # Header is line 1, first data row line 2.
    return int(idx) + 2


def fmt(x, n=6):
    if not finite(x):
        return "NA"
    return f"{float(x):.{n}f}"


def require_files():
    missing = [str(p) for p in [F_PERM, F_LOTO, F_FIXED, F_ICC] if not p.exists()]
    if missing:
        write_csv(
            OUT / "COMMENT12_BLOCKERS.csv",
            [{"Issue": "MISSING_INPUT", "Detail": x} for x in missing],
            ["Issue", "Detail"],
        )
        raise RuntimeError("Missing Comment-11 input(s). See COMMENT12_BLOCKERS.csv.")


def main():
    require_files()

    perm = pd.read_csv(F_PERM)
    loto = pd.read_csv(F_LOTO)
    fixed = pd.read_csv(F_FIXED)
    icc = pd.read_csv(F_ICC)

    blockers = []

    # ------------------------------------------------------------------
    # Strict schema / uniqueness checks
    # ------------------------------------------------------------------
    for layer in EXPECTED_LAYERS:
        for pred in EXPECTED_PREDICTORS:
            g = perm[
                (perm["Source_Layer"].astype(str) == layer)
                & (perm["Predictor"].astype(str) == pred)
            ]
            if len(g) != 1:
                blockers.append({
                    "Issue": "PERMUTATION_ROW_NOT_UNIQUE",
                    "Detail": f"{layer}/{pred}: rows={len(g)}"
                })

    # Exact permutation count should be 3456 for final 3/4/4 design.
    if "Admissible_Permutations" in perm.columns:
        bad = perm[pd.to_numeric(perm["Admissible_Permutations"], errors="coerce") != 3456]
        for i, r in bad.iterrows():
            blockers.append({
                "Issue": "PERMUTATION_COUNT_MISMATCH",
                "Detail": (
                    f"{r.get('Source_Layer')}/{r.get('Predictor')}: "
                    f"{r.get('Admissible_Permutations')}"
                )
            })

    # Primary N should be 11.
    if "N" in perm.columns:
        bad = perm[pd.to_numeric(perm["N"], errors="coerce") != 11]
        for i, r in bad.iterrows():
            blockers.append({
                "Issue": "PRIMARY_N_MISMATCH",
                "Detail": f"{r.get('Source_Layer')}/{r.get('Predictor')}: N={r.get('N')}"
            })

    if blockers:
        write_csv(OUT / "COMMENT12_BLOCKERS.csv", blockers, ["Issue", "Detail"])
        raise RuntimeError("Comment-12 numerical lock failed. See COMMENT12_BLOCKERS.csv.")

    registry = []
    primary_rows = []
    robust_rows = []
    diag_rows = []

    # ------------------------------------------------------------------
    # 1) PRIMARY + UNADJUSTED exact blocked permutation
    # ------------------------------------------------------------------
    claim_no = 1

    for layer in EXPECTED_LAYERS:
        for pred in EXPECTED_PREDICTORS:
            idx = perm[
                (perm["Source_Layer"].astype(str) == layer)
                & (perm["Predictor"].astype(str) == pred)
            ].index[0]
            r = perm.loc[idx]

            role = "PRIMARY_INFERENCE" if layer == "PRODUCT_ADJUSTED" else "ROBUSTNESS_EVIDENCE"
            adjustment = "Product-adjusted" if layer == "PRODUCT_ADJUSTED" else "Unadjusted"

            rec = {
                "Claim_ID": f"C12-{claim_no:03d}",
                "Evidence_Role": role,
                "Metric": pred,
                "Predictor": pred,
                "Outcome": "Horizontal_RMSE_2D",
                "Population": "Final_11_dataset_level_evidence_set",
                "Adjustment": adjustment,
                "Statistical_Test": "Spearman + exact Test-blocked permutation",
                "N": int(r["N"]),
                "Rho": float(r["Observed_Rho"]),
                "P": float(r["Exact_TwoSided_p"]),
                "Q": "",
                "Permutation_N": int(r["Admissible_Permutations"]),
                "Source_CSV": str(F_PERM),
                "Source_Row": source_row(perm, idx),
                "Manuscript_Role": (
                    "Primary Results/Abstract/Discussion value"
                    if role == "PRIMARY_INFERENCE"
                    else "Robustness only; do not substitute for primary value"
                ),
                "Lock_Status": "LOCKED",
            }
            claim_no += 1
            registry.append(rec)

            if role == "PRIMARY_INFERENCE":
                primary_rows.append(rec.copy())
            else:
                robust_rows.append(rec.copy())

    # ------------------------------------------------------------------
    # 2) LOTO robustness lock
    # ------------------------------------------------------------------
    for pred in EXPECTED_PREDICTORS:
        g = loto[
            (loto["Source_Layer"].astype(str) == "PRODUCT_ADJUSTED")
            & (loto["Predictor"].astype(str) == pred)
        ].copy()

        if len(g) != 3:
            blockers.append({
                "Issue": "LOTO_EXPECTED_THREE_TESTS",
                "Detail": f"{pred}: rows={len(g)}"
            })
            continue

        vals = pd.to_numeric(g["LOTO_Rho"], errors="coerce")
        full = pd.to_numeric(g["Full_Rho"], errors="coerce")
        dirs = g["Direction_Preserved"].astype(str).str.lower().isin(["true", "1", "yes"])

        rec = {
            "Claim_ID": f"C12-{claim_no:03d}",
            "Evidence_Role": "ROBUSTNESS_EVIDENCE",
            "Metric": pred,
            "Predictor": pred,
            "Outcome": "Horizontal_RMSE_2D",
            "Population": "Leave_one_Test_out",
            "Adjustment": "Product-adjusted",
            "Statistical_Test": "LOTO Spearman sensitivity",
            "N": "",
            "Rho": "",
            "P": "",
            "Q": "",
            "Permutation_N": "",
            "LOTO_Rho_Min": float(vals.min()),
            "LOTO_Rho_Max": float(vals.max()),
            "Direction_Preserved_Count": int(dirs.sum()),
            "Direction_Total": 3,
            "Source_CSV": str(F_LOTO),
            "Source_Row": "multiple",
            "Manuscript_Role": "Robustness statement/range only",
            "Lock_Status": "LOCKED",
        }
        claim_no += 1
        registry.append(rec)
        robust_rows.append(rec.copy())

    # ------------------------------------------------------------------
    # 3) Fixed-Test-effect residual robustness
    # ------------------------------------------------------------------
    for pred in EXPECTED_PREDICTORS:
        g = fixed[
            (fixed["Source_Layer"].astype(str) == "PRODUCT_ADJUSTED")
            & (fixed["Predictor"].astype(str) == pred)
        ]
        if len(g) != 1:
            blockers.append({
                "Issue": "FIXED_EFFECT_ROW_NOT_UNIQUE",
                "Detail": f"{pred}: rows={len(g)}"
            })
            continue

        idx = g.index[0]
        r = fixed.loc[idx]

        rec = {
            "Claim_ID": f"C12-{claim_no:03d}",
            "Evidence_Role": "ROBUSTNESS_EVIDENCE",
            "Metric": pred,
            "Predictor": pred,
            "Outcome": "Horizontal_RMSE_2D",
            "Population": "Within_Test_residuals",
            "Adjustment": "Product-adjusted + Test fixed-effect residualization",
            "Statistical_Test": "Spearman correlation of within-Test residuals",
            "N": int(r["N"]),
            "Rho": float(r["Spearman_WithinTestResidual"]),
            "P": "",
            "Q": "",
            "Permutation_N": "",
            "Source_CSV": str(F_FIXED),
            "Source_Row": source_row(fixed, idx),
            "Manuscript_Role": "Robustness only",
            "Lock_Status": "LOCKED",
        }
        claim_no += 1
        registry.append(rec)
        robust_rows.append(rec.copy())

    # ------------------------------------------------------------------
    # 4) Descriptive ICC(Test)
    # ------------------------------------------------------------------
    for metric in EXPECTED_PREDICTORS + ["Outcome"]:
        g = icc[
            (icc["Source_Layer"].astype(str) == "PRODUCT_ADJUSTED")
            & (icc["Metric"].astype(str) == metric)
        ]
        if len(g) != 1:
            blockers.append({
                "Issue": "ICC_ROW_NOT_UNIQUE",
                "Detail": f"{metric}: rows={len(g)}"
            })
            continue

        idx = g.index[0]
        r = icc.loc[idx]

        metric_name = "Horizontal_RMSE_2D" if metric == "Outcome" else metric

        rec = {
            "Claim_ID": f"C12-{claim_no:03d}",
            "Evidence_Role": "DESCRIPTIVE_CLUSTERING_DIAGNOSTIC",
            "Metric": metric_name,
            "Predictor": "",
            "Outcome": "",
            "Population": "Final_11_dataset_level_evidence_set",
            "Adjustment": "Product-adjusted layer",
            "Statistical_Test": "Descriptive Test-level variance decomposition / ICC",
            "N": int(r["N"]),
            "Rho": "",
            "P": "",
            "Q": "",
            "Permutation_N": "",
            "Between_SS_Fraction": float(r["Between_SS_Fraction"]),
            "ICC_Test": float(r["ICC_Test_Descriptive"]),
            "Source_CSV": str(F_ICC),
            "Source_Row": source_row(icc, idx),
            "Manuscript_Role": "Descriptive diagnostic only; not proof of independence",
            "Lock_Status": "LOCKED",
        }
        claim_no += 1
        registry.append(rec)
        diag_rows.append(rec.copy())

    if blockers:
        write_csv(OUT / "COMMENT12_BLOCKERS.csv", blockers, ["Issue", "Detail"])
        raise RuntimeError("Comment-12 downstream lock failed. See blockers CSV.")

    # ------------------------------------------------------------------
    # 5) q-value policy
    # ------------------------------------------------------------------
    # Comment-11 primary inference uses exact blocked permutation p-values.
    # We do NOT invent q-values here. Any manuscript q-value must come from
    # a separately identified multiple-testing procedure/source.
    for rec in registry:
        if rec.get("Q", "") == "":
            rec["Q_Status"] = "NOT_DEFINED_IN_COMMENT11_SOURCE"
            rec["Q_Policy"] = (
                "Do not report a q-value for this claim unless a named final "
                "multiple-testing source/procedure is explicitly linked."
            )

    # Save locks.
    pd.DataFrame(registry).to_csv(
        OUT / "COMMENT12_FINAL_EVIDENCE_REGISTRY.csv",
        index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(primary_rows).to_csv(
        OUT / "COMMENT12_PRIMARY_NUMERICAL_LOCK.csv",
        index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(robust_rows).to_csv(
        OUT / "COMMENT12_ROBUSTNESS_NUMERICAL_LOCK.csv",
        index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(diag_rows).to_csv(
        OUT / "COMMENT12_DESCRIPTIVE_DIAGNOSTIC_LOCK.csv",
        index=False, encoding="utf-8-sig"
    )

    # ------------------------------------------------------------------
    # Human-readable summary
    # ------------------------------------------------------------------
    primary_df = pd.DataFrame(primary_rows)
    unadj_df = pd.DataFrame(
        [r for r in robust_rows
         if r.get("Statistical_Test") == "Spearman + exact Test-blocked permutation"]
    )

    summary = OUT / "COMMENT12_NUMERICAL_CONSISTENCY_SUMMARY.txt"
    with summary.open("w", encoding="utf-8") as f:
        f.write("GNSS Comment 12 — Numerical Consistency Audit v1\n")
        f.write("=" * 96 + "\n\n")

        f.write("NUMERICAL SOURCE-OF-TRUTH POLICY\n")
        f.write("-" * 96 + "\n")
        f.write(
            "PRIMARY INFERENCE:\n"
            "  Product-adjusted + exact Test-blocked permutation.\n\n"
            "ROBUSTNESS EVIDENCE:\n"
            "  Unadjusted exact Test-blocked permutation; LOTO; "
            "fixed-Test-effect residual analysis.\n\n"
            "DESCRIPTIVE CLUSTERING DIAGNOSTIC:\n"
            "  Within/between-Test variance + ICC(Test).\n\n"
        )

        f.write("PRIMARY NUMERICAL LOCK\n")
        f.write("-" * 96 + "\n")
        for _, r in primary_df.iterrows():
            f.write(
                f"{r['Metric']} -> horizontal RMSE: "
                f"rho={float(r['Rho']):.6f} | "
                f"exact p={float(r['P']):.6f} | "
                f"N={int(r['N'])} | permutations={int(r['Permutation_N'])}\n"
            )

        f.write("\nUNADJUSTED ROBUSTNESS LOCK\n")
        f.write("-" * 96 + "\n")
        for _, r in unadj_df.iterrows():
            f.write(
                f"{r['Metric']} -> horizontal RMSE: "
                f"rho={float(r['Rho']):.6f} | "
                f"exact p={float(r['P']):.6f}\n"
            )

        f.write("\nQ-VALUE POLICY\n")
        f.write("-" * 96 + "\n")
        f.write(
            "No q-value is created by this script. The finalized Comment-11 "
            "dependence-aware source contains exact blocked-permutation p-values. "
            "Any rho/q pair elsewhere in the manuscript must be linked to a "
            "separate, explicitly named final multiple-testing source. Otherwise "
            "the q-value must not be copied into the final text.\n"
        )

        f.write("\nCONSISTENCY GATE FOR THE NEXT STEP\n")
        f.write("-" * 96 + "\n")
        f.write(
            "1) CMC_P95 must never be substituted for CMC_ROBUST.\n"
            "2) PRODUCT_ADJUSTED primary values must never be silently replaced "
            "by UNADJUSTED robustness values.\n"
            "3) The locked outcome here is horizontal / 2D RMSE.\n"
            "4) Abstract, Results, Discussion and Conclusions must use the same "
            "primary rho/p pair when making the same primary claim.\n"
            "5) LOTO/fixed-effect/ICC numbers must be labelled as robustness or "
            "descriptive diagnostics, not primary inference.\n"
            "6) A q-value requires an explicit final source and correction method; "
            "it is not inferred from p.\n"
        )

        f.write("\nSOURCE FILES\n")
        f.write("-" * 96 + "\n")
        for p in [F_PERM, F_LOTO, F_FIXED, F_ICC]:
            f.write(str(p) + "\n")

    print(summary.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
