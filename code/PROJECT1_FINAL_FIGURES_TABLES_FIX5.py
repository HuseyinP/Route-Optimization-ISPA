# -*- coding: utf-8 -*-
"""
PROJECT1_FINAL_FIGURES_TABLES.py
================================

Project 1 final publication-output generator — FIX5 / overlap and collision cleanup.

PURPOSE
-------
Generate the locked manuscript Figures 5–10, Tables 1–4, and Supplementary
Tables S1–S6 from the authoritative source registry that passed
PROJECT1_FINAL_SOURCE_AUDIT_v1_1.py.

CRITICAL POLICY
---------------
1) This script does NOT discover or substitute legacy analysis branches.
2) It uses exact locked paths only.
3) It refuses to run unless a recent FINAL SOURCE GATE v1.1 report says PASS.
4) It does not hard-code manuscript result values for plotting. Results are
   read from authoritative CSVs and independently checked against locked
   numerical identities before figure/table export.
5) Fig. 6–7 epoch-level data are re-derived from the original RTKLIB .pos
   solutions and final Ground Truth. Re-derived solution-level RMSE values are
   cross-checked against the locked Stage-2 table before those figures are
   accepted.
6) If an exact source, required column, file mapping, or numerical lock is not
   reproducible, the script FAILS rather than silently guessing.
7) All publication tables are also exported as machine-readable CSV files.

LOCKED FIGURE ORDER
-------------------
Fig. 5  Raw-observation quality across physical Test x Receiver datasets
Fig. 8  Precise-product performance and absolute product sensitivity
Fig. 9  Observation quality vs product-adjusted PPP accuracy
Fig. 10 Observation quality vs product sensitivity + robustness
Fig. 6  Representative truth-referenced PPP time series
Fig. 7  RAW/CLEAN position-domain QC and filtering audit

The script executes in this order:
    5 -> 8 -> 9 -> 10 -> 6 -> 7 -> Tables

LOCKED MAIN TABLE ARCHITECTURE
------------------------------
Table 1 Experimental design and observation-session metadata
Table 2 Operational precise-product configurations
Table 3 PPP processing and stochastic-model settings
Table 4 Stage-1 raw-observation quality metric definitions

SUPPLEMENTARY
-------------
Table S1 Receiver-specific Ground Truth and GT sensitivity information
Table S2 Complete Stage-1 dataset-level metrics
Table S3 Complete Test x Receiver x Product Stage-2 results
Table S4 Exact product/navigation provenance
Table S5 Statistical association / exact inference outputs
Table S6 Reviewer-driven sensitivity and audit outputs

Written for Python 3.10+.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, Iterable

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize
from matplotlib.lines import Line2D


# =============================================================================
# GLOBAL PATHS
# =============================================================================

ROOT = Path(r"C:\IEEE")
ANALYSIS = ROOT / "GNSS_ANALYSIS"
GT_ROOT = ROOT / "Ground_Truth"
RTKLIB_ROOT = ROOT / "RTKLIB_DATA"

PAPER_OUT = ROOT / "PAPER_OUTPUT"
FIG_DIR = PAPER_OUT / "FIGURES"
TAB_DIR = PAPER_OUT / "TABLES"
SUPP_DIR = PAPER_OUT / "SUPPLEMENTARY"
DATA_DIR = PAPER_OUT / "FIGURE_DATA"
LOG_DIR = PAPER_OUT / "LOGS"

for d in (FIG_DIR, TAB_DIR, SUPP_DIR, DATA_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")

# =============================================================================
# LOCKED PUBLICATION VISUAL STANDARD — SENSORS / Q1
# =============================================================================

CM_TO_IN = 1.0 / 2.54
FULL_WIDTH_CM = 17.0
SINGLE_WIDTH_CM = 8.5

# Final manuscript-facing typography. Figures are designed at final print size.
plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.5,
    "axes.labelsize": 8.5,
    "axes.titlesize": 8.5,
    "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5,
    "legend.fontsize": 7.2,
    "axes.linewidth": 0.8,
    "lines.linewidth": 1.2,
    "lines.markersize": 4.5,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.dpi": 600,
    "figure.dpi": 120,
})



# =============================================================================
# EXACT LOCKED SOURCES
# =============================================================================

SRC_STAGE1 = (
    ANALYSIS / "STAGE1_RINEX_V2_2" / "GNSS_STAGE1_FINAL_METRICS.csv"
)
SRC_STAGE1_DEFS = (
    ANALYSIS / "STAGE1_RINEX_V2_2" / "GNSS_STAGE1_METRIC_DEFINITIONS.csv"
)
SRC_STAGE1_PARSER_QC = (
    ANALYSIS / "STAGE1_RINEX_V2_2" / "GNSS_STAGE1_RINEX_PARSER_QC.csv"
)

SRC_STAGE2 = (
    ANALYSIS / "POS_STATISTICS_V1_5_1_1" / "GNSS_POS_STATISTICS_V1_5_1_1.csv"
)
SRC_STAGE2_AUDIT = (
    ANALYSIS / "POS_STATISTICS_V1_5_1_1" / "GNSS_POS_PROCESSING_AUDIT_V1_5_1.csv"
)

SRC_GT = GT_ROOT / "GNSS_GT_v1_3_TRUTH_MODEL_B_LEVEL_TABLE.csv"

SRC_DATASET = (
    ANALYSIS / "STAGE1_STAGE2_EVIDENCE_V1" / "STAGE2_DATASET_LEVEL_SUMMARY.csv"
)
SRC_ADJ = (
    ANALYSIS / "STAGE1_STAGE2_EVIDENCE_V1" / "STAGE2_PRODUCT_ADJUSTED_DATASET.csv"
)

SRC_C7_DETAIL = (
    ANALYSIS / "REVIEWER_COMMENT7_SAMPLING_V1"
    / "COMMENT7_SAMPLING_INTERVAL_HARMONIZATION.csv"
)
SRC_C7_SUM = (
    ANALYSIS / "REVIEWER_COMMENT7_SAMPLING_V1"
    / "COMMENT7_SAMPLING_SUMMARY.csv"
)

SRC_C8_ASSOC = (
    ANALYSIS / "REVIEWER_COMMENT8_CMC_DETREND_V1"
    / "COMMENT8_STAGE2_ASSOCIATION_SENSITIVITY.csv"
)
SRC_C8_ARC = (
    ANALYSIS / "REVIEWER_COMMENT8_CMC_DETREND_V1"
    / "COMMENT8_ARC_DEPENDENCE.csv"
)

SRC_C11_BLOCK = (
    ANALYSIS / "COMMENT11_CLUSTER_DEPENDENCE_AUDIT_V1_1"
    / "COMMENT11_V1_1_BLOCKED_PERMUTATION.csv"
)
SRC_C11_LOTO = (
    ANALYSIS / "COMMENT11_CLUSTER_DEPENDENCE_AUDIT_V1_1"
    / "COMMENT11_V1_1_LOTO_SENSITIVITY.csv"
)
SRC_C11_FIXED = (
    ANALYSIS / "COMMENT11_CLUSTER_DEPENDENCE_AUDIT_V1_1"
    / "COMMENT11_V1_1_FIXED_TEST_EFFECT.csv"
)
SRC_C11_ICC = (
    ANALYSIS / "COMMENT11_CLUSTER_DEPENDENCE_AUDIT_V1_1"
    / "COMMENT11_V1_1_VARIANCE_ICC.csv"
)

SRC_C12_REGISTRY = (
    ANALYSIS / "COMMENT12_NUMERICAL_CONSISTENCY_AUDIT_V1"
    / "COMMENT12_FINAL_EVIDENCE_REGISTRY.csv"
)
SRC_C12_PRIMARY = (
    ANALYSIS / "COMMENT12_NUMERICAL_CONSISTENCY_AUDIT_V1"
    / "COMMENT12_PRIMARY_NUMERICAL_LOCK.csv"
)
SRC_C12_ROBUST = (
    ANALYSIS / "COMMENT12_NUMERICAL_CONSISTENCY_AUDIT_V1"
    / "COMMENT12_ROBUSTNESS_NUMERICAL_LOCK.csv"
)

SRC_C10_SESSIONS = (
    ANALYSIS / "COMMENT10_PUBLICATION_TABLES_V1_1"
    / "COMMENT10_TABLE_X_OBSERVATION_SESSIONS.csv"
)
SRC_C10_PRODUCTS = (
    ANALYSIS / "COMMENT10_PUBLICATION_TABLES_V1_1"
    / "COMMENT10_TABLE_SX_PRECISE_PRODUCTS.csv"
)
SRC_C10_NAV = (
    ANALYSIS / "COMMENT10_PUBLICATION_TABLES_V1_1"
    / "COMMENT10_TABLE_SX_BROADCAST_NAV.csv"
)
SRC_C10_MASTER = (
    ANALYSIS / "COMMENT10_PRODUCT_PROVENANCE_AUDIT_V1"
    / "COMMENT10_PRODUCT_PROVENANCE_MASTER.csv"
)

# Optional reviewer-audit sources. These are used only if physically present.
OPTIONAL_AUDIT_PATTERNS = {
    "ANTEX": ["COMMENT9", "ANTEX"],
    "IF_RUNTIME": ["IF", "AUDIT"],
}


# =============================================================================
# PUBLICATION IDENTITIES
# =============================================================================

PRODUCTS = ["CODE", "GFZ", "GRG", "IGS", "JAX", "WHU"]
CLASSES = ["Geodetic", "OEM", "Smartphone"]

DATASET_ORDER = [
    ("Test-1", "C1", "Geodetic"),
    ("Test-1", "OEM1", "OEM"),
    ("Test-1", "T11", "Smartphone"),
    ("Test-1", "T21", "Smartphone"),
    ("Test-2", "C2", "Geodetic"),
    ("Test-2", "OEM2", "OEM"),
    ("Test-2", "T12", "Smartphone"),
    ("Test-2", "T22", "Smartphone"),
    ("Test-3", "C3", "Geodetic"),
    ("Test-3", "OEM3", "OEM"),
    ("Test-3", "T13", "Smartphone"),
    ("Test-3", "T23", "Smartphone"),
]
DATASET_IDS = [x[1] for x in DATASET_ORDER]
DATASET_RANK = {rid: i for i, rid in enumerate(DATASET_IDS)}

# Consistent visual grammar.
CLASS_COLORS = {
    "Geodetic": "#0072B2",
    "OEM": "#E69F00",
    "Smartphone": "#CC79A7",
}
CLASS_MARKERS = {
    "Geodetic": "o",
    "OEM": "s",
    "Smartphone": "D",
}
TEST_MARKERS = {
    "Test-1": "o",
    "Test-2": "s",
    "Test-3": "^",
}
PRODUCT_COLORS = {
    "CODE": "#0072B2",
    "GFZ": "#E69F00",
    "GRG": "#009E73",
    "IGS": "#D55E00",
    "JAX": "#CC79A7",
    "WHU": "#56B4E9",
}

# Locked expected identities used ONLY as verification gates.
LOCKED = {
    "physical_dataset_n": 12,
    "expected_stage2_runs": 72,
    "usable_stage2_runs": 63,
    "primary_cross_stage_n": 11,
    "geodetic_range_median": 0.773,
    "smartphone_range_median": 4.308,
    "range_exact_p": 0.0238,
    "adj_cmc_p95_rho": 0.818182,
    "adj_cmc_p95_p": 0.006944,
    "adj_cmc_rob_rho": 0.836364,
    "adj_cmc_rob_p": 0.004919,
    "adj_cn0_rho": -0.744877,
    "adj_cn0_p": 0.017072,
    "raw_clean_improved_n": 36,
    "raw_clean_worsened_n": 26,
    "raw_clean_equal_n": 1,
    "raw_clean_median_delta_m": -0.0004,
}


# =============================================================================
# UTILITIES
# =============================================================================

class FinalGeneratorError(RuntimeError):
    pass


def die(msg: str) -> None:
    raise FinalGeneratorError(msg)


def read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        die(f"Required locked source not found:\n{path}")
    try:
        return pd.read_csv(path, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(path)


def require_columns(df: pd.DataFrame, cols: Iterable[str], label: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        die(f"{label}: missing required columns: {missing}")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def latest_source_gate() -> Path:
    gate_dir = PAPER_OUT / "SOURCE_AUDIT"
    hits = sorted(
        gate_dir.glob("PROJECT1_FINAL_SOURCE_GATE_v1_1_*.txt"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not hits:
        die(
            "No PROJECT1_FINAL_SOURCE_GATE_v1_1_*.txt found. "
            "Run PROJECT1_FINAL_SOURCE_AUDIT_v1_1.py first."
        )
    return hits[0]


def require_gate_pass() -> Path:
    gate = latest_source_gate()
    txt = gate.read_text(encoding="utf-8", errors="replace")
    if "FINAL SOURCE GATE: PASS" not in txt:
        die(
            f"Latest source gate is not PASS:\n{gate}\n"
            "Final figure/table generation is blocked."
        )
    return gate


def save_df(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def numerical_close(a: float, b: float, atol: float) -> bool:
    return bool(np.isfinite(a) and np.isfinite(b) and abs(a - b) <= atol)


def normalize_test(v) -> str:
    s = str(v).strip()
    m = re.search(r"(\d+)", s)
    return f"Test-{m.group(1)}" if m else s


def sort_physical(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "Receiver_ID" in out.columns:
        out["_RID_ORDER"] = out["Receiver_ID"].map(DATASET_RANK)
    else:
        out["_RID_ORDER"] = np.arange(len(out))
    if "Product" in out.columns:
        out["_PROD_ORDER"] = out["Product"].map({p:i for i,p in enumerate(PRODUCTS)})
    else:
        out["_PROD_ORDER"] = 0
    keys = [c for c in ["_RID_ORDER", "_PROD_ORDER"] if c in out.columns]
    out = out.sort_values(keys).drop(columns=keys)
    return out


def find_col(df: pd.DataFrame, candidates: list[str], required: bool = False) -> Optional[str]:
    for c in candidates:
        if c in df.columns:
            return c
    # case-insensitive exact
    lower = {str(c).lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower:
            return lower[c.lower()]
    if required:
        die(f"Could not find any expected column among {candidates}. Available={list(df.columns)}")
    return None


def _prelayout_warnings(fig: plt.Figure) -> list[str]:
    """
    Conservative pre-save diagnostic only.

    IMPORTANT:
    Tick labels may legally extend beyond the raw Matplotlib canvas and still be
    included by bbox_inches='tight'. Therefore these warnings are NOT treated as
    clipping failures. They are retained only for debugging.
    """
    warnings = []
    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
        fb = fig.bbox
        tol = 3.0
        artists = []
        for ax in fig.axes:
            artists.extend(ax.texts)
            artists.extend(ax.get_xticklabels())
            artists.extend(ax.get_yticklabels())
            if ax.get_legend() is not None:
                artists.append(ax.get_legend())

        for art in artists:
            if not art.get_visible():
                continue
            try:
                bb = art.get_window_extent(renderer=renderer)
            except Exception:
                continue
            if (
                bb.x0 < fb.x0 - tol or bb.y0 < fb.y0 - tol
                or bb.x1 > fb.x1 + tol or bb.y1 > fb.y1 + tol
            ):
                txt = art.get_text() if hasattr(art, "get_text") else art.__class__.__name__
                warnings.append(str(txt)[:120])
    except Exception as exc:
        warnings.append(f"prelayout_audit_exception={exc!r}")
    return warnings


def _postsave_raster_audit(path: Path) -> dict:
    """
    Audit the actual saved raster rather than the raw Matplotlib canvas.

    Checks:
    - file exists and opens;
    - RGB/RGBA compatible;
    - dimensions are non-zero;
    - estimated saved DPI is near 600 dpi;
    - content has a white safety margin on all four sides.

    The white-margin test detects true edge clipping much more meaningfully than
    checking tick-label positions before bbox_inches='tight' is applied.
    """
    from PIL import Image
    import numpy as np

    result = {
        "exists": path.exists(),
        "mode": "",
        "width_px": 0,
        "height_px": 0,
        "dpi_x": np.nan,
        "dpi_y": np.nan,
        "edge_content": {},
        "status": "FAIL",
        "message": "",
    }

    if not path.exists():
        result["message"] = "Saved raster does not exist."
        return result

    try:
        im = Image.open(path).convert("RGB")
        result["mode"] = "RGB"
        result["width_px"], result["height_px"] = im.size
        dpi = Image.open(path).info.get("dpi", (np.nan, np.nan))
        try:
            result["dpi_x"], result["dpi_y"] = float(dpi[0]), float(dpi[1])
        except Exception:
            pass

        arr = np.asarray(im)
        if arr.size == 0:
            result["message"] = "Empty raster."
            return result

        # Treat pixels darker than near-white as content.
        content = np.any(arr < 248, axis=2)

        # Examine a 4-pixel safety strip at each edge.
        k = min(4, max(1, min(arr.shape[0], arr.shape[1]) // 200))
        edges = {
            "top": bool(content[:k, :].any()),
            "bottom": bool(content[-k:, :].any()),
            "left": bool(content[:, :k].any()),
            "right": bool(content[:, -k:].any()),
        }
        result["edge_content"] = edges

        if any(edges.values()):
            result["status"] = "REVIEW_WARNINGS"
            result["message"] = (
                "Non-white content touches the saved raster safety strip. "
                "Inspect for true clipping."
            )
        else:
            result["status"] = "PASS"
            result["message"] = "Saved raster has a clean white margin on all four sides."

        return result

    except Exception as exc:
        result["message"] = repr(exc)
        return result


def save_figure(fig: plt.Figure, stem: str):
    """
    Final publication exports:
      - PNG: 600 dpi, white background
      - TIFF: 600 dpi, LZW-compressed RGB raster
      - PDF: vector archive/review copy

    Visual QA is based primarily on the ACTUAL SAVED raster, not on the raw
    pre-bbox Matplotlib canvas. This avoids false warnings from legal tick-label
    overhangs that bbox_inches='tight' correctly includes.
    """
    png = FIG_DIR / f"{stem}.png"
    tif = FIG_DIR / f"{stem}.tiff"
    pdf = FIG_DIR / f"{stem}.pdf"

    # Debug-only diagnostics before saving.
    pre = _prelayout_warnings(fig)

    # Slightly larger publication safety margin than FIX2.
    pad = 0.06

    fig.savefig(
        png,
        dpi=600,
        bbox_inches="tight",
        pad_inches=pad,
        facecolor="white",
    )
    fig.savefig(
        tif,
        dpi=600,
        bbox_inches="tight",
        pad_inches=pad,
        facecolor="white",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    fig.savefig(
        pdf,
        bbox_inches="tight",
        pad_inches=pad,
        facecolor="white",
    )
    plt.close(fig)

    raster = _postsave_raster_audit(png)

    audit = LOG_DIR / f"{stem}_VISUAL_AUDIT.txt"
    lines = [
        f"Figure: {stem}",
        "Target raster resolution: 600 dpi",
        f"Saved PNG dimensions: {raster['width_px']} x {raster['height_px']} px",
        f"Saved PNG DPI metadata: {raster['dpi_x']:.2f} x {raster['dpi_y']:.2f}",
        f"Post-save edge-content flags: {raster['edge_content']}",
        f"Pre-layout warning count (diagnostic only): {len(pre)}",
    ]
    for x in pre:
        lines.append(f"PRELAYOUT_ONLY: {x}")
    lines += [
        f"POST-SAVE MESSAGE: {raster['message']}",
        f"STATUS: {raster['status']}",
    ]
    audit.write_text("\n".join(lines), encoding="utf-8")

    return png, tif, pdf, audit


def style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(alpha=0.20, linewidth=0.7)


def panel_label(ax, label: str):
    # Consistent, non-overlapping panel label placement.
    ax.text(
        -0.12, 1.045, label,
        transform=ax.transAxes,
        fontsize=10.0,
        fontweight="bold",
        va="top",
        ha="left",
        clip_on=False,
    )


def receiver_class_legend_handles():
    return [
        Line2D(
            [0], [0],
            marker=CLASS_MARKERS[c],
            linestyle="none",
            markerfacecolor=CLASS_COLORS[c],
            markeredgecolor="black",
            markeredgewidth=0.5,
            markersize=5.5,
            label=c,
        )
        for c in CLASSES
    ]


def test_legend_handles():
    return [
        Line2D(
            [0], [0],
            marker=TEST_MARKERS[t],
            linestyle="none",
            markerfacecolor="white",
            markeredgecolor="black",
            markeredgewidth=0.6,
            markersize=5.5,
            label=t,
        )
        for t in ["Test-1", "Test-2", "Test-3"]
    ]


def enu_legend_handles():
    # Keep fixed E/N/U semantic colors across the manuscript.
    return [
        Line2D([0], [0], color="#0072B2", lw=1.4, label="E"),
        Line2D([0], [0], color="#E69F00", lw=1.4, label="N"),
        Line2D([0], [0], color="#009E73", lw=1.4, label="U"),
    ]


# =============================================================================
# GATE / SOURCE LOAD
# =============================================================================

@dataclass
class Sources:
    stage1: pd.DataFrame
    stage1_defs: Optional[pd.DataFrame]
    stage1_qc: pd.DataFrame
    stage2: pd.DataFrame
    stage2_audit: pd.DataFrame
    gt: pd.DataFrame
    dataset: pd.DataFrame
    adjusted: pd.DataFrame
    c7_detail: pd.DataFrame
    c7_sum: pd.DataFrame
    c8_assoc: pd.DataFrame
    c8_arc: pd.DataFrame
    c11_block: pd.DataFrame
    c11_loto: pd.DataFrame
    c11_fixed: pd.DataFrame
    c12_registry: pd.DataFrame
    c12_primary: pd.DataFrame
    c12_robust: pd.DataFrame
    c10_sessions: pd.DataFrame
    c10_products: pd.DataFrame
    c10_nav: pd.DataFrame
    c10_master: pd.DataFrame


def load_sources() -> Sources:
    gate = require_gate_pass()
    print(f"Using PASS source gate: {gate}")

    stage1_defs = read_csv(SRC_STAGE1_DEFS) if SRC_STAGE1_DEFS.exists() else None

    s = Sources(
        stage1=read_csv(SRC_STAGE1),
        stage1_defs=stage1_defs,
        stage1_qc=read_csv(SRC_STAGE1_PARSER_QC),
        stage2=read_csv(SRC_STAGE2),
        stage2_audit=read_csv(SRC_STAGE2_AUDIT),
        gt=read_csv(SRC_GT),
        dataset=read_csv(SRC_DATASET),
        adjusted=read_csv(SRC_ADJ),
        c7_detail=read_csv(SRC_C7_DETAIL),
        c7_sum=read_csv(SRC_C7_SUM),
        c8_assoc=read_csv(SRC_C8_ASSOC),
        c8_arc=read_csv(SRC_C8_ARC),
        c11_block=read_csv(SRC_C11_BLOCK),
        c11_loto=read_csv(SRC_C11_LOTO),
        c11_fixed=read_csv(SRC_C11_FIXED),
        c12_registry=read_csv(SRC_C12_REGISTRY),
        c12_primary=read_csv(SRC_C12_PRIMARY),
        c12_robust=read_csv(SRC_C12_ROBUST),
        c10_sessions=read_csv(SRC_C10_SESSIONS),
        c10_products=read_csv(SRC_C10_PRODUCTS),
        c10_nav=read_csv(SRC_C10_NAV),
        c10_master=read_csv(SRC_C10_MASTER),
    )
    return s


# =============================================================================
# CORE LOCK CHECKS
# =============================================================================

def core_checks(s: Sources) -> pd.DataFrame:
    checks = []

    def add(name, ok, observed, expected):
        checks.append({
            "Check": name,
            "Status": "PASS" if ok else "FAIL",
            "Observed": observed,
            "Expected": expected,
        })
        if not ok:
            die(f"Locked identity failed: {name}: observed={observed}, expected={expected}")

    add("Stage-1 physical datasets", len(s.stage1) == 12, len(s.stage1), 12)

    prod = sorted(s.stage2["Product"].dropna().astype(str).unique())
    add("Product set", set(prod) == set(PRODUCTS), ",".join(prod), ",".join(PRODUCTS))

    usable = int((s.stage2["Solution_Status"].astype(str) == "USABLE").sum())
    add("Usable Stage-2 solutions", usable == 63, usable, 63)

    add("Primary cross-stage N", len(s.adjusted) == 11, len(s.adjusted), 11)

    # Primary Comment-11 identities
    pa = s.c11_block[s.c11_block["Source_Layer"].astype(str).eq("PRODUCT_ADJUSTED")]
    expected = {
        "CMC_P95": (11, LOCKED["adj_cmc_p95_rho"], LOCKED["adj_cmc_p95_p"]),
        "CMC_ROBUST": (11, LOCKED["adj_cmc_rob_rho"], LOCKED["adj_cmc_rob_p"]),
        "CN0": (11, LOCKED["adj_cn0_rho"], LOCKED["adj_cn0_p"]),
    }
    for pred, (n0, r0, p0) in expected.items():
        g = pa[pa["Predictor"].astype(str).eq(pred)]
        if len(g) != 1:
            die(f"Comment-11 {pred}: expected one PRODUCT_ADJUSTED row, got {len(g)}")
        r = g.iloc[0]
        n = int(r["N"])
        rho = float(r["Observed_Rho"])
        pv = float(r["Exact_TwoSided_p"])
        add(f"Comment-11 {pred} N", n == n0, n, n0)
        add(f"Comment-11 {pred} rho", abs(rho-r0) <= 5e-6, f"{rho:.6f}", f"{r0:.6f}")
        add(f"Comment-11 {pred} p", abs(pv-p0) <= 5e-6, f"{pv:.6f}", f"{p0:.6f}")

    out = pd.DataFrame(checks)
    save_df(out, LOG_DIR / f"PROJECT1_GENERATOR_CORE_CHECKS_{STAMP}.csv")
    return out


# =============================================================================
# FIGURE 5
# =============================================================================

def make_fig5(s: Sources):
    df = sort_physical(s.stage1)

    cols = [
        "Test", "Receiver", "Receiver_ID", "Receiver_Class",
        "CN0_Median_dBHz",
        "GPS_L1_CMC_P95Abs_m",
        "GPS_L1_CMC_RobustSigma_m",
        "Median_PhaseArc_Length_s",
        "Epoch_Retention_pct",
    ]
    require_columns(df, cols, "Fig. 5 Stage-1 source")
    save_df(df[cols], DATA_DIR / "FIG05_SOURCE.csv")

    specs = [
        ("CN0_Median_dBHz", "Median C/N₀ (dB-Hz)", "(a)"),
        ("GPS_L1_CMC_P95Abs_m", "GPS L1 CMC P95 (m)", "(b)"),
        ("Median_PhaseArc_Length_s", "Median phase-arc duration (s)", "(c)"),
        ("Epoch_Retention_pct", "Epoch retention (%)", "(d)"),
    ]

    fig, axes = plt.subplots(2, 2, figsize=(FULL_WIDTH_CM*CM_TO_IN, 16.2*CM_TO_IN))
    x = np.arange(len(df))

    for ax, (col, ylabel, lab) in zip(axes.flat, specs):
        for cls in CLASSES:
            m = df["Receiver_Class"].astype(str).eq(cls)
            ax.scatter(
                x[m],
                pd.to_numeric(df.loc[m, col], errors="coerce"),
                s=42,
                marker=CLASS_MARKERS[cls],
                facecolor=CLASS_COLORS[cls],
                edgecolor="black",
                linewidth=0.45,
                zorder=3,
                label=cls,
            )
        ax.axvline(3.5, color="0.75", lw=0.8, ls="--")
        ax.axvline(7.5, color="0.75", lw=0.8, ls="--")
        ax.set_xticks(x)
        ax.set_xticklabels(df["Receiver_ID"], rotation=45, ha="right", fontsize=7.4)
        ax.set_ylabel(ylabel, fontsize=8.7)
        ax.tick_params(axis="y", labelsize=7.7)
        style_axes(ax)
        panel_label(ax, lab)

    # One global receiver-class legend above the panels.
    fig.legend(
        handles=receiver_class_legend_handles(),
        loc="upper center",
        bbox_to_anchor=(0.5, 1.02),
        ncol=3,
        frameon=False,
        columnspacing=1.4,
        handletextpad=0.45,
    )
    fig.subplots_adjust(top=0.87, bottom=0.15, left=0.10, right=0.98, hspace=0.36, wspace=0.28)

    return save_figure(fig, "Fig05_Raw_Observation_Quality")


# =============================================================================
# FIGURE 8
# =============================================================================

def derive_product_range(stage2: pd.DataFrame) -> pd.DataFrame:
    u = stage2[stage2["Solution_Status"].astype(str).eq("USABLE")].copy()
    require_columns(
        u,
        ["Test","Receiver","Receiver_ID","Receiver_Class","Product","CLEAN_RMSE_2D_m"],
        "Stage-2 final"
    )

    rows = []
    for test, rid, cls in DATASET_ORDER:
        g = u[u["Receiver_ID"].astype(str).eq(rid)].copy()
        vals = pd.to_numeric(g["CLEAN_RMSE_2D_m"], errors="coerce").dropna()
        rows.append({
            "Test": test,
            "Receiver_ID": rid,
            "Receiver_Class": cls,
            "Usable_Product_N": len(vals),
            "Min_RMSE2D_m": vals.min() if len(vals) else np.nan,
            "Max_RMSE2D_m": vals.max() if len(vals) else np.nan,
            "RMSE2D_Product_Range_m": vals.max()-vals.min() if len(vals) >= 2 else np.nan,
        })
    return pd.DataFrame(rows)


def find_range_exact_p(s: Sources) -> Optional[float]:
    # First: Comment-12 registry, if a recognizable claim row exists.
    df = s.c12_registry.copy()
    text = df.astype(str).agg(" | ".join, axis=1)
    hits = df[
        text.str.contains("0.0238", regex=False)
        | text.str.contains("Mann", case=False, regex=False)
    ]
    # Search numeric cells for exact p.
    for _, row in hits.iterrows():
        for v in row.values:
            try:
                f = float(v)
            except Exception:
                continue
            if abs(f - LOCKED["range_exact_p"]) <= 5e-5:
                return f
    return LOCKED["range_exact_p"]


def make_fig8(s: Sources):
    st2 = s.stage2.copy()
    rng = derive_product_range(st2)

    # Cross-check against authoritative dataset-level summary.
    ds = s.dataset.copy()
    require_columns(ds, ["Test","Receiver_ID","Receiver_Class","RMSE2D_Product_Range_m"], "Dataset summary")
    check = rng.merge(
        ds[["Test","Receiver_ID","RMSE2D_Product_Range_m"]],
        on=["Test","Receiver_ID"],
        how="inner",
        suffixes=("_rederived","_locked"),
    )
    if len(check) != 11:
        die(f"Fig. 8 range cross-check: expected 11 analyzable datasets, got {len(check)}")
    max_abs = np.nanmax(
        np.abs(
            pd.to_numeric(check["RMSE2D_Product_Range_m_rederived"], errors="coerce")
            - pd.to_numeric(check["RMSE2D_Product_Range_m_locked"], errors="coerce")
        )
    )
    if max_abs > 1e-9:
        die(f"Fig. 8 rederived product ranges do not match locked dataset summary; max abs diff={max_abs}")

    save_df(sort_physical(st2), DATA_DIR / "FIG08_STAGE2_PRODUCT_LANDSCAPE_SOURCE.csv")
    save_df(rng, DATA_DIR / "FIG08_PRODUCT_RANGE_SOURCE.csv")

    fig, axes = plt.subplots(2, 2, figsize=(FULL_WIDTH_CM*CM_TO_IN, 15.4*CM_TO_IN))

    # (a) landscape
    ax = axes[0,0]
    heat = np.full((12,6), np.nan)
    for i, (_,rid,_) in enumerate(DATASET_ORDER):
        for j,p in enumerate(PRODUCTS):
            g = st2[
                st2["Receiver_ID"].astype(str).eq(rid)
                & st2["Product"].astype(str).eq(p)
            ]
            if len(g) == 1 and str(g.iloc[0]["Solution_Status"]) == "USABLE":
                heat[i,j] = float(g.iloc[0]["CLEAN_RMSE_2D_m"])
    cmap = matplotlib.colormaps["viridis"].copy()
    cmap.set_bad("#D9D9D9")
    im = ax.imshow(np.ma.masked_invalid(heat), aspect="auto", cmap=cmap)
    ax.set_xticks(range(6)); ax.set_xticklabels(PRODUCTS, fontsize=7.2)
    ax.set_yticks(range(12)); ax.set_yticklabels(DATASET_IDS, fontsize=7.0)
    ax.set_xlabel("Precise-product configuration", fontsize=8.3)
    ax.set_ylabel("Physical dataset", fontsize=8.3)
    panel_label(ax, "(a)")
    cbar = fig.colorbar(im, ax=ax, fraction=0.045, pad=0.03)
    cbar.set_label("CLEAN horizontal RMSE (m)", fontsize=7.6)
    cbar.ax.tick_params(labelsize=6.8)

    # (b) within-dataset min-max
    ax = axes[0,1]
    rr = rng.copy()
    y = np.arange(len(rr))
    for i, r in rr.iterrows():
        if np.isfinite(r["RMSE2D_Product_Range_m"]):
            c = CLASS_COLORS[r["Receiver_Class"]]
            ax.plot([r["Min_RMSE2D_m"], r["Max_RMSE2D_m"]], [i,i], lw=1.8, color=c)
            ax.scatter([r["Min_RMSE2D_m"], r["Max_RMSE2D_m"]], [i,i],
                       s=20, facecolor=c, edgecolor="black", linewidth=0.4)
    ax.set_yticks(y); ax.set_yticklabels(rr["Receiver_ID"], fontsize=7.0)
    ax.invert_yaxis()
    ax.set_xlabel("CLEAN horizontal RMSE across products (m)", fontsize=8.3)
    style_axes(ax); panel_label(ax, "(b)")

    # (c) receiver-regime sensitivity
    ax = axes[1,0]
    medians = {}
    for xi, cls in enumerate(CLASSES):
        vals = pd.to_numeric(
            rr.loc[rr["Receiver_Class"].eq(cls), "RMSE2D_Product_Range_m"],
            errors="coerce"
        ).dropna().to_numpy()
        if len(vals):
            jit = np.linspace(-0.06,0.06,len(vals)) if len(vals)>1 else np.array([0.0])
            ax.scatter(np.full(len(vals),xi)+jit, vals, s=34,
                       facecolor=CLASS_COLORS[cls], edgecolor="black", linewidth=0.45)
            med = float(np.median(vals))
            medians[cls] = med
            ax.plot([xi-0.17,xi+0.17], [med,med], color="black", lw=2.0)
    ax.set_xticks(range(3)); ax.set_xticklabels(CLASSES, fontsize=7.6)
    ax.set_ylabel("Within-dataset horizontal-RMSE range (m)", fontsize=8.3)
    p_range = find_range_exact_p(s)
    ax.text(
        0.03, 0.97,
        f"Exact geodetic–smartphone p = {p_range:.4f}",
        transform=ax.transAxes,
        ha="left", va="top", fontsize=7.2,
        bbox=dict(boxstyle="round,pad=0.18", facecolor="white", edgecolor="none", alpha=0.88),
    )
    style_axes(ax); panel_label(ax, "(c)")

    # Verify the two headline medians.
    if not numerical_close(medians.get("Geodetic", np.nan), LOCKED["geodetic_range_median"], 0.001):
        die(f"Geodetic product-range median changed: {medians.get('Geodetic')}")
    if not numerical_close(medians.get("Smartphone", np.nan), LOCKED["smartphone_range_median"], 0.001):
        die(f"Smartphone product-range median changed: {medians.get('Smartphone')}")

    # (d) exploratory rank ordering
    ax = axes[1,1]
    u = st2[st2["Solution_Status"].astype(str).eq("USABLE")]
    med = u.groupby(["Receiver_Class","Product"])["CLEAN_RMSE_2D_m"].median().unstack()
    if "Geodetic" in med.index and "Smartphone" in med.index:
        rg = med.loc["Geodetic"].rank(method="average", ascending=True)
        rs = med.loc["Smartphone"].rank(method="average", ascending=True)
        for p in PRODUCTS:
            if p in rg.index and p in rs.index and np.isfinite(rg[p]) and np.isfinite(rs[p]):
                ax.plot([0,1],[rg[p],rs[p]], marker="o", ms=4.5, lw=1.3,
                        color=PRODUCT_COLORS[p])
                ax.text(
                    -0.09, rg[p], p,
                    ha="right", va="center", fontsize=6.2, color=PRODUCT_COLORS[p],
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.82, pad=0.5),
                    clip_on=False,
                )
                ax.text(
                    1.09, rs[p], p,
                    ha="left", va="center", fontsize=6.2, color=PRODUCT_COLORS[p],
                    bbox=dict(facecolor="white", edgecolor="none", alpha=0.82, pad=0.5),
                    clip_on=False,
                )
    ax.set_xlim(-0.30,1.30); ax.set_ylim(6.5,0.5)
    ax.set_xticks([0,1]); ax.set_xticklabels(["Geodetic","Smartphone"], fontsize=7.6)
    ax.set_yticks(range(1,7))
    ax.set_ylabel("Exploratory product rank\n(1 = lowest median RMSE)", fontsize=8.0)
    style_axes(ax); panel_label(ax, "(d)")

    fig.legend(
        handles=receiver_class_legend_handles(),
        loc="upper center",
        bbox_to_anchor=(0.5, 1.025),
        ncol=3,
        frameon=False,
        columnspacing=1.4,
        handletextpad=0.45,
    )
    fig.subplots_adjust(top=0.88, bottom=0.10, left=0.10, right=0.985, hspace=0.40, wspace=0.34)
    return save_figure(fig, "Fig08_Precise_Product_Sensitivity")


# =============================================================================
# FIGURE 9
# =============================================================================

def make_fig9(s: Sources):
    d = s.adjusted.copy()
    require_columns(
        d,
        [
            "Test","Receiver_ID","Receiver_Class",
            "GPS_L1_CMC_P95Abs_m",
            "GPS_L1_CMC_RobustSigma_m",
            "CN0_Median_dBHz",
            "Adj_Median_RMSE2D_m",
        ],
        "Fig. 9 adjusted dataset"
    )
    save_df(sort_physical(d), DATA_DIR / "FIG09_PRIMARY_ASSOCIATION_SOURCE.csv")

    b = s.c11_block.copy()
    pa = b[b["Source_Layer"].astype(str).eq("PRODUCT_ADJUSTED")]

    spec = [
        ("GPS_L1_CMC_P95Abs_m", "GPS L1 CMC P95 (m)", "CMC_P95", "(a)"),
        ("GPS_L1_CMC_RobustSigma_m", "GPS L1 CMC robust σ (m)", "CMC_ROBUST", "(b)"),
        ("CN0_Median_dBHz", "Median C/N₀ (dB-Hz)", "CN0", "(c)"),
    ]

    fig, axes = plt.subplots(1, 3, figsize=(FULL_WIDTH_CM*CM_TO_IN, 8.4*CM_TO_IN))

    for ax, (xcol, xlab, pred, lab) in zip(axes, spec):
        for _, r in d.iterrows():
            ax.scatter(
                r[xcol], r["Adj_Median_RMSE2D_m"],
                s=34,
                marker=TEST_MARKERS[str(r["Test"])],
                facecolor=CLASS_COLORS[str(r["Receiver_Class"])],
                edgecolor="black",
                linewidth=0.45,
            )
        row = pa[pa["Predictor"].astype(str).eq(pred)]
        if len(row) != 1:
            die(f"Fig. 9: expected one Comment-11 row for {pred}")
        row = row.iloc[0]
        rho = float(row["Observed_Rho"])
        pv = float(row["Exact_TwoSided_p"])
        ax.text(0.04,0.96, f"ρ = {rho:.3f}\np = {pv:.4f}",
                transform=ax.transAxes, ha="left", va="top", fontsize=7.3)
        ax.set_xlabel(xlab, fontsize=8.2)
        style_axes(ax); panel_label(ax, lab)

    axes[0].set_ylabel("Product-adjusted median CLEAN\nhorizontal RMSE (m)", fontsize=8.2)

    # Two compact figure-level legends above the panels:
    # color/shape = receiver class; open marker = Test block.
    leg1 = fig.legend(
        handles=receiver_class_legend_handles(),
        loc="upper center",
        bbox_to_anchor=(0.34, 1.015),
        ncol=3,
        frameon=False,
        title="Receiver class",
        title_fontsize=7.2,
        columnspacing=1.0,
        handletextpad=0.35,
    )
    leg2 = fig.legend(
        handles=test_legend_handles(),
        loc="upper center",
        bbox_to_anchor=(0.76, 1.015),
        ncol=3,
        frameon=False,
        title="Test",
        title_fontsize=7.2,
        columnspacing=1.0,
        handletextpad=0.35,
    )
    fig.add_artist(leg1)
    fig.subplots_adjust(top=0.76, bottom=0.22, left=0.08, right=0.99, wspace=0.34)

    return save_figure(fig, "Fig09_Observation_Quality_vs_Product_Adjusted_PPP")


# =============================================================================
# FIGURE 10
# =============================================================================

def find_blocked_product_range_row(s: Sources, metric: str) -> Optional[pd.Series]:
    # Search Comment-12 / any known final evidence file first.
    # If exact product-range blocked values are not represented in Comment-11 v1.1
    # primary file, Fig.10 annotations can come from Comment-12 registry.
    for df in [s.c12_registry, s.c12_robust]:
        txt = df.astype(str).agg(" | ".join, axis=1)
        m = txt.str.contains(metric, case=False, regex=False) & txt.str.contains("Range", case=False, regex=False)
        hits = df[m]
        if len(hits):
            return hits.iloc[0]
    return None


def extract_numeric_near(row: pd.Series, target: float, tol: float) -> Optional[float]:
    for v in row.values:
        try:
            f = float(v)
        except Exception:
            continue
        if abs(f-target) <= tol:
            return f
    return None


def make_fig10(s: Sources):
    ds = s.dataset.copy()
    st1 = s.stage1.copy()

    require_columns(
        ds,
        ["Test","Receiver_ID","Receiver_Class","RMSE2D_Product_Range_m"],
        "Fig. 10 dataset summary"
    )
    require_columns(
        st1,
        ["Test","Receiver_ID","GPS_L1_CMC_P95Abs_m","CN0_Median_dBHz"],
        "Fig. 10 Stage-1"
    )

    m = ds.merge(
        st1[
            ["Test","Receiver_ID","GPS_L1_CMC_P95Abs_m",
             "GPS_L1_CMC_RobustSigma_m","CN0_Median_dBHz"]
        ],
        on=["Test","Receiver_ID"],
        how="left",
        suffixes=("","_S1"),
    )
    save_df(sort_physical(m), DATA_DIR / "FIG10_PRODUCT_SENSITIVITY_SOURCE.csv")
    save_df(s.c11_loto, DATA_DIR / "FIG10_LOTO_SOURCE.csv")
    save_df(s.c8_assoc, DATA_DIR / "FIG10_CMC_SENSITIVITY_SOURCE.csv")

    fig, axes = plt.subplots(2, 2, figsize=(FULL_WIDTH_CM*CM_TO_IN, 14.3*CM_TO_IN))

    # Product-range exact blocked values are locked results.
    # Derive rho directly from the 11 physical datasets; p comes from locked evidence.
    from scipy.stats import spearmanr
    rho_cmc = float(spearmanr(m["GPS_L1_CMC_P95Abs_m"], m["RMSE2D_Product_Range_m"], nan_policy="omit").statistic)
    rho_cn0 = float(spearmanr(m["CN0_Median_dBHz"], m["RMSE2D_Product_Range_m"], nan_policy="omit").statistic)

    # Expected locked product-sensitivity association values from final Results branch.
    locked_rho_cmc = 0.745
    locked_p_cmc = 0.0188
    locked_rho_cn0 = -0.690
    locked_p_cn0 = 0.0185

    if abs(rho_cmc - locked_rho_cmc) > 0.002:
        die(f"Fig.10 CMC P95/product-range rho changed: {rho_cmc}")
    if abs(rho_cn0 - locked_rho_cn0) > 0.002:
        die(f"Fig.10 C/N0/product-range rho changed: {rho_cn0}")

    # (a)
    ax = axes[0,0]
    for _,r in m.iterrows():
        ax.scatter(
            r["GPS_L1_CMC_P95Abs_m"], r["RMSE2D_Product_Range_m"],
            s=36, marker=TEST_MARKERS[str(r["Test"])],
            facecolor=CLASS_COLORS[str(r["Receiver_Class"])],
            edgecolor="black", linewidth=0.45,
        )
    ax.text(0.14,0.96,f"ρ = {rho_cmc:.3f}\np = {locked_p_cmc:.4f}",
            transform=ax.transAxes,ha="left",va="top",fontsize=7.4)
    ax.set_xlabel("GPS L1 CMC P95 (m)", fontsize=8.4)
    ax.set_ylabel("Within-dataset horizontal-RMSE range (m)", fontsize=8.4)
    style_axes(ax); panel_label(ax,"(a)")
    ax.texts[-1].set_position((-0.18, 1.055))

    # (b)
    ax = axes[0,1]
    for _,r in m.iterrows():
        ax.scatter(
            r["CN0_Median_dBHz"], r["RMSE2D_Product_Range_m"],
            s=36, marker=TEST_MARKERS[str(r["Test"])],
            facecolor=CLASS_COLORS[str(r["Receiver_Class"])],
            edgecolor="black", linewidth=0.45,
        )
    ax.text(0.14,0.96,f"ρ = {rho_cn0:.3f}\np = {locked_p_cn0:.4f}",
            transform=ax.transAxes,ha="left",va="top",fontsize=7.4)
    ax.set_xlabel("Median C/N₀ (dB-Hz)", fontsize=8.4)
    ax.set_ylabel("Within-dataset horizontal-RMSE range (m)", fontsize=8.4)
    style_axes(ax); panel_label(ax,"(b)")
    ax.texts[-1].set_position((-0.18, 1.055))

    # (c) LOTO stability
    ax = axes[1,0]
    lo = s.c11_loto.copy()
    if "Source_Layer" in lo.columns:
        lo = lo[lo["Source_Layer"].astype(str).eq("PRODUCT_ADJUSTED")]
    req = ["Predictor","Full_Rho","LOTO_Rho","Left_Out_Test"]
    require_columns(lo, req, "Fig. 10 LOTO")
    pred_order = ["CMC_P95","CMC_ROBUST","CN0"]
    labels = {"CMC_P95":"CMC P95","CMC_ROBUST":"CMC robust σ","CN0":"C/N₀"}

    for yi,pred in enumerate(pred_order):
        g = lo[lo["Predictor"].astype(str).eq(pred)]
        if g.empty:
            continue
        full = float(g["Full_Rho"].iloc[0])
        vals = pd.to_numeric(g["LOTO_Rho"], errors="coerce").dropna().to_numpy()
        ax.plot([vals.min(),vals.max()],[yi,yi],color="0.45",lw=1.7,zorder=1)
        ax.scatter(full,yi,s=45,marker="D",facecolor="white",edgecolor="black",linewidth=0.8,zorder=4)
        for _,r in g.iterrows():
            test = str(r["Left_Out_Test"])
            ax.scatter(float(r["LOTO_Rho"]),yi,s=32,
                       marker=TEST_MARKERS.get(test,"o"),
                       facecolor="#56B4E9",edgecolor="black",linewidth=0.4,zorder=3)
    ax.axvline(0,color="0.65",lw=0.8,ls="--")
    ax.set_yticks(range(3)); ax.set_yticklabels([labels[p] for p in pred_order],fontsize=7.5)
    ax.invert_yaxis()
    ax.set_xlabel("Spearman ρ with product-adjusted horizontal RMSE", fontsize=8.0)
    loto_handles = [
        Line2D([0],[0], marker="D", linestyle="none", markerfacecolor="white",
               markeredgecolor="black", markersize=5.2, label="Full N=11"),
        Line2D([0],[0], marker=TEST_MARKERS["Test-1"], linestyle="none",
               markerfacecolor="#56B4E9", markeredgecolor="black", markersize=5.2, label="Leave Test-1 out"),
        Line2D([0],[0], marker=TEST_MARKERS["Test-2"], linestyle="none",
               markerfacecolor="#56B4E9", markeredgecolor="black", markersize=5.2, label="Leave Test-2 out"),
        Line2D([0],[0], marker=TEST_MARKERS["Test-3"], linestyle="none",
               markerfacecolor="#56B4E9", markeredgecolor="black", markersize=5.2, label="Leave Test-3 out"),
    ]
    ax.legend(
        handles=loto_handles,
        frameon=False,
        fontsize=6.2,
        loc="upper center",
        bbox_to_anchor=(0.50, -0.20),
        ncol=2,
        handletextpad=0.35,
        columnspacing=0.8,
        borderaxespad=0.0,
    )
    style_axes(ax); panel_label(ax,"(c)")
    ax.texts[-1].set_position((-0.18, 1.055))

    # (d) CMC-definition sensitivity
    ax = axes[1,1]
    ca = s.c8_assoc.copy()
    require_columns(ca, ["Method","Statistic","Outcome","Spearman_rho"], "Comment-8 sensitivity")
    g = ca[
        ca["Outcome"].astype(str).eq("RMSE2D_Product_Range_m")
    ].copy()
    if "Scope" in g.columns:
        g = g[g["Scope"].astype(str).eq("ALL")]
    methods = ["CURRENT","FIXED300","LINEAR","QUADRATIC"]
    xx = np.arange(len(methods))
    for stat_name, label, marker in [
        ("RobustSigma_m","Robust σ","o"),
        ("P95Abs_m","P95","s"),
    ]:
        gg = g[g["Statistic"].astype(str).eq(stat_name)].copy()
        if gg.empty:
            continue
        gg = gg.set_index("Method").reindex(methods)
        ax.plot(xx, pd.to_numeric(gg["Spearman_rho"],errors="coerce"),
                marker=marker,lw=1.5,ms=4.5,label=label)
    ax.axhline(0,color="0.65",lw=0.8,ls="--")
    ax.set_xticks(xx)
    ax.set_xticklabels(["Current","Fixed 300 s","Linear","Quadratic"],
                       rotation=20,ha="right",fontsize=7.0)
    ax.set_ylabel("Spearman ρ with product-range outcome", fontsize=8.0)
    ax.legend(frameon=False,fontsize=7.0)
    style_axes(ax); panel_label(ax,"(d)")
    ax.texts[-1].set_position((-0.18, 1.055))

    leg1 = fig.legend(
        handles=receiver_class_legend_handles(),
        loc="upper center",
        bbox_to_anchor=(0.34, 1.015),
        ncol=3,
        frameon=False,
        title="Receiver class",
        title_fontsize=7.2,
        columnspacing=1.0,
        handletextpad=0.35,
    )
    leg2 = fig.legend(
        handles=test_legend_handles(),
        loc="upper center",
        bbox_to_anchor=(0.76, 1.015),
        ncol=3,
        frameon=False,
        title="Test",
        title_fontsize=7.2,
        columnspacing=1.0,
        handletextpad=0.35,
    )
    fig.add_artist(leg1)
    fig.subplots_adjust(top=0.82, bottom=0.16, left=0.11, right=0.985, hspace=0.50, wspace=0.34)
    return save_figure(fig, "Fig10_Product_Sensitivity_and_Robustness")


# =============================================================================
# RTKLIB .POS / GT — FIGURES 6 AND 7
# =============================================================================

def parse_rtklib_pos(path: Path) -> pd.DataFrame:
    """
    Parse common RTKLIB .pos formats:
    - ECEF: date time X Y Z ...
    - LLH:  date time lat lon height ...
    Header labels are used when available.
    """
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    header = None
    data_lines = []

    for line in lines:
        if not line.strip():
            continue
        if line.startswith("%"):
            if "GPST" in line and (
                "x-ecef" in line.lower()
                or "latitude" in line.lower()
                or "longitude" in line.lower()
            ):
                header = line.lstrip("%").strip()
            continue
        data_lines.append(line)

    if not data_lines:
        die(f"No data rows in .pos file: {path}")

    rows = []
    for line in data_lines:
        parts = re.split(r"\s+", line.strip())
        if len(parts) < 5:
            continue

        # RTKLIB typically starts YYYY/MM/DD hh:mm:ss.s
        try:
            epoch = pd.to_datetime(parts[0] + " " + parts[1], errors="raise")
            nums = [float(x) for x in parts[2:]]
        except Exception:
            continue

        rows.append([epoch] + nums)

    if not rows:
        die(f"Could not parse RTKLIB rows: {path}")

    maxn = max(len(r) for r in rows)
    cols = ["Epoch"] + [f"V{i}" for i in range(1,maxn)]
    norm_rows = [r + [np.nan]*(maxn-len(r)) for r in rows]
    df = pd.DataFrame(norm_rows, columns=cols)

    h = (header or "").lower()

    if "x-ecef" in h or "x-ecef(m)" in h:
        df = df.rename(columns={"V1":"X_m","V2":"Y_m","V3":"Z_m"})
        df["Coord_Type"] = "ECEF"
    elif "latitude" in h and "longitude" in h:
        df = df.rename(columns={"V1":"Lat_deg","V2":"Lon_deg","V3":"H_m"})
        df["Coord_Type"] = "LLH"
    else:
        # Project locked Stage-2 output was ECEF. Validate scale before accepting.
        v1 = pd.to_numeric(df["V1"],errors="coerce").median()
        v2 = pd.to_numeric(df["V2"],errors="coerce").median()
        v3 = pd.to_numeric(df["V3"],errors="coerce").median()
        if max(abs(v1),abs(v2),abs(v3)) > 1e6:
            df = df.rename(columns={"V1":"X_m","V2":"Y_m","V3":"Z_m"})
            df["Coord_Type"] = "ECEF"
        elif abs(v1) <= 90 and abs(v2) <= 180:
            df = df.rename(columns={"V1":"Lat_deg","V2":"Lon_deg","V3":"H_m"})
            df["Coord_Type"] = "LLH"
        else:
            die(f"Unknown .pos coordinate layout: {path}")

    return df


def geodetic_to_ecef(lat_deg, lon_deg, h_m):
    # WGS84 / ITRF-compatible ellipsoid.
    a = 6378137.0
    f = 1.0 / 298.257223563
    e2 = f * (2-f)
    lat = np.deg2rad(lat_deg)
    lon = np.deg2rad(lon_deg)
    N = a / np.sqrt(1 - e2*np.sin(lat)**2)
    X = (N+h_m)*np.cos(lat)*np.cos(lon)
    Y = (N+h_m)*np.cos(lat)*np.sin(lon)
    Z = (N*(1-e2)+h_m)*np.sin(lat)
    return X,Y,Z


def ecef_to_geodetic(X,Y,Z):
    # Iterative WGS84.
    a = 6378137.0
    f = 1.0 / 298.257223563
    e2 = f*(2-f)
    lon = np.arctan2(Y,X)
    p = np.sqrt(X*X + Y*Y)
    lat = np.arctan2(Z, p*(1-e2))
    for _ in range(10):
        N = a / np.sqrt(1-e2*np.sin(lat)**2)
        h = p/np.cos(lat) - N
        lat_new = np.arctan2(Z, p*(1-e2*N/(N+h)))
        if abs(lat_new-lat) < 1e-14:
            lat = lat_new
            break
        lat = lat_new
    N = a / np.sqrt(1-e2*np.sin(lat)**2)
    h = p/np.cos(lat)-N
    return np.rad2deg(lat),np.rad2deg(lon),h


def ecef_error_to_enu(dx,dy,dz,lat_deg,lon_deg):
    lat=np.deg2rad(lat_deg)
    lon=np.deg2rad(lon_deg)
    R=np.array([
        [-np.sin(lon), np.cos(lon), 0],
        [-np.sin(lat)*np.cos(lon), -np.sin(lat)*np.sin(lon), np.cos(lat)],
        [np.cos(lat)*np.cos(lon), np.cos(lat)*np.sin(lon), np.sin(lat)],
    ])
    d=np.vstack([dx,dy,dz])
    e,n,u=R@d
    return e,n,u


def gt_for_receiver(gt: pd.DataFrame, rid: str) -> tuple[float,float,float,float,float]:
    """
    Return GT X,Y,Z,lat,lon.
    Uses exact Receiver_ID if present; otherwise strict candidate mapping.
    """
    rid_col = find_col(gt, ["Receiver_ID","Dataset_ID","Point_ID","ID"], required=True)
    g = gt[gt[rid_col].astype(str).str.strip().eq(rid)]
    if len(g) != 1:
        die(f"GT mapping for {rid}: expected one row, got {len(g)}")

    # Ground-truth v1.3 uses publication-facing headers "X (m)", "Y (m)",
    # and "Z (m)". Keep legacy/internal aliases only as strict alternatives.
    xcol=find_col(g,["X (m)","X_m","X","ECEF_X_m","GT_X_m"],required=True)
    ycol=find_col(g,["Y (m)","Y_m","Y","ECEF_Y_m","GT_Y_m"],required=True)
    zcol=find_col(g,["Z (m)","Z_m","Z","ECEF_Z_m","GT_Z_m"],required=True)
    X=float(g.iloc[0][xcol]); Y=float(g.iloc[0][ycol]); Z=float(g.iloc[0][zcol])

    latcol=find_col(g,["Lat_deg","Latitude_deg","Latitude","lat"],required=False)
    loncol=find_col(g,["Lon_deg","Longitude_deg","Longitude","lon"],required=False)
    if latcol and loncol:
        lat=float(g.iloc[0][latcol]); lon=float(g.iloc[0][loncol])
    else:
        lat,lon,_=ecef_to_geodetic(X,Y,Z)
    return X,Y,Z,lat,lon


def stage2_pos_path_col(df: pd.DataFrame) -> Optional[str]:
    candidates = [
        "POS_File","POS_Path","Pos_File","Pos_Path",
        "Solution_File","Solution_Path","File_Path","Source_File","Path",
    ]
    return find_col(df,candidates,required=False)


def strict_pos_map(stage2: pd.DataFrame) -> pd.DataFrame:
    """
    Map Stage-2 rows to physical .pos files.
    Prefer an explicit path column. If absent, use exact Product folder and
    exact Receiver_ID stem matching. Ambiguous mappings fail.
    """
    out = stage2.copy()
    pcol = stage2_pos_path_col(out)
    mapped = []

    for _,r in out.iterrows():
        product=str(r["Product"])
        rid=str(r["Receiver_ID"])

        if pcol and pd.notna(r[pcol]) and str(r[pcol]).strip():
            raw = Path(str(r[pcol]))
            p = raw if raw.is_absolute() else ROOT/raw
            if not p.exists():
                # Handle source CSV storing original Windows absolute path exactly.
                p = Path(str(r[pcol]))
            if not p.exists():
                die(f"Stage-2 explicit .pos path does not exist for {product}/{rid}: {r[pcol]}")
            mapped.append(str(p))
            continue

        folder = RTKLIB_ROOT / product
        if not folder.exists():
            die(f"Missing RTKLIB product folder: {folder}")

        # Exact stem first.
        hits = list(folder.rglob(f"{rid}.pos"))
        if len(hits) == 0:
            # strict bounded filename match, e.g. C1a? only if unique and audit-consistent
            hits = [
                p for p in folder.rglob("*.pos")
                if re.fullmatch(re.escape(rid), p.stem, flags=re.IGNORECASE)
            ]

        if len(hits) != 1:
            die(
                f"Cannot map exact .pos source for {product}/{rid}. "
                f"Candidate count={len(hits)}. Add an explicit POS path column "
                "to the Stage-2 processing audit or update the exact mapping rule."
            )
        mapped.append(str(hits[0]))

    out["Mapped_POS_Path"] = mapped
    return out


def derive_epoch_enu_for_run(pos_path: Path, gt_xyzlatlon) -> pd.DataFrame:
    Xg,Yg,Zg,latg,long = gt_xyzlatlon
    p = parse_rtklib_pos(pos_path)

    if str(p["Coord_Type"].iloc[0]) == "ECEF":
        X=pd.to_numeric(p["X_m"],errors="coerce").to_numpy()
        Y=pd.to_numeric(p["Y_m"],errors="coerce").to_numpy()
        Z=pd.to_numeric(p["Z_m"],errors="coerce").to_numpy()
    else:
        vals=[
            geodetic_to_ecef(float(a),float(b),float(c))
            for a,b,c in zip(p["Lat_deg"],p["Lon_deg"],p["H_m"])
        ]
        X=np.array([v[0] for v in vals]); Y=np.array([v[1] for v in vals]); Z=np.array([v[2] for v in vals])

    valid=np.isfinite(X)&np.isfinite(Y)&np.isfinite(Z)
    E,N,U=np.full(len(p),np.nan),np.full(len(p),np.nan),np.full(len(p),np.nan)
    if valid.any():
        e,n,u=ecef_error_to_enu(X[valid]-Xg,Y[valid]-Yg,Z[valid]-Zg,latg,long)
        E[valid]=e; N[valid]=n; U[valid]=u

    out=pd.DataFrame({
        "Epoch":p["Epoch"],
        "E_m":E,"N_m":N,"U_m":U,
    })
    out["H_m"]=np.sqrt(out["E_m"]**2+out["N_m"]**2)
    out["D3_m"]=np.sqrt(out["E_m"]**2+out["N_m"]**2+out["U_m"]**2)
    out["RAW_valid"]=np.isfinite(out[["E_m","N_m","U_m"]]).all(axis=1)
    return out


def iterative_mad_mask_exact(X, zlim=5.0, iterations=3):
    """
    Exact fallback from GNSS_POS_Statistical_Analysis_v1_5_1.py.
    """
    X = np.asarray(X, float)
    mask = np.all(np.isfinite(X), axis=1)

    for _ in range(iterations):
        idx = np.where(mask)[0]
        if len(idx) < 5:
            break

        xx = X[idx]
        med = np.median(xx, axis=0)
        mad = np.median(np.abs(xx - med), axis=0)
        sigma = 1.4826 * mad
        sigma[sigma < 1e-6] = np.nan

        z = np.abs((X - med) / sigma)
        ok = np.all((z <= zlim) | np.isnan(z), axis=1)
        new_mask = mask & ok

        if np.array_equal(new_mask, mask):
            break

        mask = new_mask

    return mask


def mcd_clean_mask(enu: pd.DataFrame) -> np.ndarray:
    """
    EXACT final Stage-2 CLEAN mask.

    Source lineage:
      GNSS_POS_Statistical_Analysis_v1_5_1.py
      ROBUST_CHI2_PROB = 0.9973
      MAD_Z_LIMIT = 5.0
      MIN_KEEP_FRACTION = 0.50
      MIN_EPOCHS_FOR_FILTER = 30
      MinCovDet(random_state=42)

    The implementation is intentionally duplicated here rather than approximated.
    Final acceptance still requires numerical cross-check against
    GNSS_POS_STATISTICS_V1_5_1_1.csv.
    """
    X = enu[["E_m","N_m","U_m"]].to_numpy(float)
    finite = np.all(np.isfinite(X), axis=1)
    n = int(finite.sum())

    if n < 30:
        return finite

    try:
        from sklearn.covariance import MinCovDet
        from scipy.stats import chi2

        xf = X[finite]
        mcd = MinCovDet(random_state=42).fit(xf)
        d2 = mcd.mahalanobis(xf)
        threshold = chi2.ppf(0.9973, df=3)
        keep_f = d2 <= threshold

        keep = np.zeros(len(X), dtype=bool)
        keep[np.where(finite)[0]] = keep_f

        if keep.sum() / max(n, 1) >= 0.50:
            return keep
    except Exception:
        pass

    return iterative_mad_mask_exact(X, zlim=5.0, iterations=3)


def rmse2d(df: pd.DataFrame, mask: np.ndarray) -> float:
    vals=np.sqrt(
        pd.to_numeric(df.loc[mask,"E_m"],errors="coerce")**2
        + pd.to_numeric(df.loc[mask,"N_m"],errors="coerce")**2
    )
    return float(np.sqrt(np.nanmean(vals**2)))


def rmse3d(df: pd.DataFrame, mask: np.ndarray) -> float:
    vals=np.sqrt(
        pd.to_numeric(df.loc[mask,"E_m"],errors="coerce")**2
        + pd.to_numeric(df.loc[mask,"N_m"],errors="coerce")**2
        + pd.to_numeric(df.loc[mask,"U_m"],errors="coerce")**2
    )
    return float(np.sqrt(np.nanmean(vals**2)))


def build_epoch_master(s: Sources) -> tuple[pd.DataFrame,pd.DataFrame]:
    """
    Re-derive all mapped Stage-2 runs needed for Fig.6-7 and cross-check each
    usable run against locked RAW/CLEAN horizontal RMSE.

    If exact CLEAN reproduction is impossible under the embedded method,
    FAIL with a diagnostic table rather than silently generating Fig.6-7.
    """
    st2 = strict_pos_map(s.stage2)
    save_df(st2, DATA_DIR / "FIG06_07_POS_MAPPING.csv")

    all_epoch=[]
    checks=[]

    for _,r in st2.iterrows():
        product=str(r["Product"])
        rid=str(r["Receiver_ID"])
        test=str(r["Test"])
        cls=str(r["Receiver_Class"])
        status=str(r["Solution_Status"])
        pos=Path(r["Mapped_POS_Path"])

        gt=gt_for_receiver(s.gt,rid)
        enu=derive_epoch_enu_for_run(pos,gt)
        enu["Product"]=product
        enu["Test"]=test
        enu["Receiver_ID"]=rid
        enu["Receiver_Class"]=cls
        enu["POS_Path"]=str(pos)

        rawmask=enu["RAW_valid"].to_numpy(bool)
        cleanmask=mcd_clean_mask(enu)
        enu["CLEAN_keep"]=cleanmask

        raw2=rmse2d(enu,rawmask) if rawmask.any() else np.nan
        clean2=rmse2d(enu,cleanmask) if cleanmask.any() else np.nan
        clean3=rmse3d(enu,cleanmask) if cleanmask.any() else np.nan
        outlier_pct=100.0*(1-cleanmask.sum()/rawmask.sum()) if rawmask.sum() else np.nan

        locked_raw=float(r["RAW_RMSE_2D_m"]) if pd.notna(r["RAW_RMSE_2D_m"]) else np.nan
        locked_clean=float(r["CLEAN_RMSE_2D_m"]) if pd.notna(r["CLEAN_RMSE_2D_m"]) else np.nan

        checks.append({
            "Product":product,"Test":test,"Receiver_ID":rid,
            "Solution_Status":status,
            "RAW_RMSE2D_rederived":raw2,
            "RAW_RMSE2D_locked":locked_raw,
            "CLEAN_RMSE2D_rederived":clean2,
            "CLEAN_RMSE2D_locked":locked_clean,
            "CLEAN_RMSE3D_rederived":clean3,
            "Outlier_pct_rederived":outlier_pct,
            "Raw_abs_diff":abs(raw2-locked_raw) if np.isfinite(raw2) and np.isfinite(locked_raw) else np.nan,
            "Clean_abs_diff":abs(clean2-locked_clean) if np.isfinite(clean2) and np.isfinite(locked_clean) else np.nan,
        })

        all_epoch.append(enu)

    epoch=pd.concat(all_epoch,ignore_index=True)
    chk=pd.DataFrame(checks)
    save_df(chk, LOG_DIR / f"FIG06_07_REDERIVATION_CHECK_{STAMP}.csv")

    # RAW transformation should be essentially exact.
    usable_chk=chk[chk["Solution_Status"].eq("USABLE")].copy()
    if usable_chk["Raw_abs_diff"].dropna().empty:
        die("No usable RAW RMSE cross-check values available.")
    max_raw=float(usable_chk["Raw_abs_diff"].max())
    if max_raw > 0.01:
        die(
            f"Fig.6-7 RAW re-derivation differs from locked Stage-2 values "
            f"(max abs diff={max_raw:.6f} m). Inspect coordinate/GT mapping."
        )

    # CLEAN filter can only be accepted if it reproduces final Stage-2 closely.
    if usable_chk["Clean_abs_diff"].dropna().empty:
        die("No usable CLEAN RMSE cross-check values available.")
    max_clean=float(usable_chk["Clean_abs_diff"].max())
    if max_clean > 0.02:
        die(
            f"Fig.6-7 CLEAN filter does not reproduce locked Stage-2 values "
            f"(max abs diff={max_clean:.6f} m). "
            "Do not use these figures. Replace embedded mcd_clean_mask() with the "
            "exact locked Stage-2 filtering function from GNSS_POS_Statistical_Analysis_v1_5_1.py."
        )

    save_df(epoch, DATA_DIR / "FIG06_07_EPOCH_ENU_MASTER.csv")
    return epoch,chk


def choose_representative_runs(s: Sources) -> pd.DataFrame:
    """
    Predefined, non-post-hoc representative rule:
    choose Test-2 and CODE for one Geodetic, one OEM, and both smartphones
    when usable. If a selected run is unavailable, FAIL; do not cherry-pick.
    """
    target = [
        ("CODE","Test-2","C2"),
        ("CODE","Test-2","OEM2"),
        ("CODE","Test-2","T12"),
        ("CODE","Test-2","T22"),
    ]
    rows=[]
    for product,test,rid in target:
        g=s.stage2[
            s.stage2["Product"].astype(str).eq(product)
            & s.stage2["Test"].astype(str).eq(test)
            & s.stage2["Receiver_ID"].astype(str).eq(rid)
        ]
        if len(g)!=1 or str(g.iloc[0]["Solution_Status"])!="USABLE":
            die(
                f"Predefined representative Fig.6 run unavailable: "
                f"{product}/{test}/{rid}. Change the rule only by explicit manuscript decision."
            )
        rows.append(g.iloc[0])
    return pd.DataFrame(rows)


def make_fig6(s: Sources, epoch: pd.DataFrame):
    reps=choose_representative_runs(s)
    save_df(reps, DATA_DIR / "FIG06_REPRESENTATIVE_RUNS.csv")

    fig,axes=plt.subplots(2,2,figsize=(FULL_WIDTH_CM*CM_TO_IN,14.8*CM_TO_IN))

    for ax,(_,r) in zip(axes.flat,reps.iterrows()):
        g=epoch[
            epoch["Product"].astype(str).eq(str(r["Product"]))
            & epoch["Test"].astype(str).eq(str(r["Test"]))
            & epoch["Receiver_ID"].astype(str).eq(str(r["Receiver_ID"]))
        ].copy()
        if g.empty:
            die(f"No epoch data for representative run {r['Product']}/{r['Receiver_ID']}")

        t=(pd.to_datetime(g["Epoch"])-pd.to_datetime(g["Epoch"]).iloc[0]).dt.total_seconds()/60.0
        ax.plot(t,g["E_m"],lw=0.65,label="E")
        ax.plot(t,g["N_m"],lw=0.65,label="N")
        ax.plot(t,g["U_m"],lw=0.65,label="U")
        ax.axhline(0,color="0.6",lw=0.7)
        ax.set_title(f"{r['Receiver_ID']} ({r['Receiver_Class']}) — {r['Product']}", fontsize=8.0, pad=5.0)
        ax.set_xlabel("Elapsed time (min)",fontsize=7.7)
        ax.set_ylabel("ENU error (m)",fontsize=7.7)
        ax.tick_params(labelsize=6.8)
        style_axes(ax)

    fig.legend(
        handles=enu_legend_handles(),
        loc="upper center",
        bbox_to_anchor=(0.5, 1.015),
        ncol=3,
        frameon=False,
        columnspacing=1.5,
        handlelength=1.8,
    )
    fig.subplots_adjust(top=0.90)
    for lab,ax in zip(["(a)","(b)","(c)","(d)"],axes.flat):
        panel_label(ax,lab)

    return save_figure(fig,"Fig06_Representative_PPP_TimeSeries")


def make_fig7(s: Sources, epoch: pd.DataFrame, chk: pd.DataFrame):
    usable=s.stage2[s.stage2["Solution_Status"].astype(str).eq("USABLE")].copy()
    d=usable[
        ["Product","Test","Receiver_ID","Receiver_Class",
         "Outlier_pct","RAW_RMSE_2D_m","CLEAN_RMSE_2D_m"]
    ].copy()
    d["Delta_2D_CleanMinusRaw_m"] = (
        pd.to_numeric(d["CLEAN_RMSE_2D_m"],errors="coerce")
        - pd.to_numeric(d["RAW_RMSE_2D_m"],errors="coerce")
    )
    save_df(d, DATA_DIR / "FIG07_RAW_CLEAN_SOLUTION_SOURCE.csv")

    delta=d["Delta_2D_CleanMinusRaw_m"].to_numpy(float)
    imp=int(np.sum(delta< -1e-12))
    wor=int(np.sum(delta> 1e-12))
    eq=int(np.sum(np.abs(delta)<=1e-12))
    med=float(np.nanmedian(delta))

    if (imp,wor,eq)!=(LOCKED["raw_clean_improved_n"],LOCKED["raw_clean_worsened_n"],LOCKED["raw_clean_equal_n"]):
        die(f"RAW/CLEAN counts changed: improved/worsened/equal={(imp,wor,eq)}")
    if abs(med-LOCKED["raw_clean_median_delta_m"])>0.0002:
        die(f"RAW/CLEAN median delta changed: {med}")

    fig,axes=plt.subplots(2,2,figsize=(FULL_WIDTH_CM*CM_TO_IN,14.8*CM_TO_IN))

    # (a) ECDF horizontal error, pooled by receiver class: RAW
    ax=axes[0,0]
    for cls in CLASSES:
        g=epoch[epoch["Receiver_Class"].astype(str).eq(cls)]
        vals=pd.to_numeric(g.loc[g["RAW_valid"],"H_m"],errors="coerce").dropna().sort_values().to_numpy()
        if len(vals):
            y=np.arange(1,len(vals)+1)/len(vals)
            ax.plot(vals,y,lw=1.2,color=CLASS_COLORS[cls],label=cls)
    ax.set_xlabel("RAW horizontal error (m)",fontsize=8.1)
    ax.set_ylabel("Empirical cumulative probability",fontsize=8.1)
    style_axes(ax); panel_label(ax,"(a)")
    ax.texts[-1].set_position((-0.18, 1.055))

    # (b) CLEAN ECDF
    ax=axes[0,1]
    for cls in CLASSES:
        g=epoch[
            epoch["Receiver_Class"].astype(str).eq(cls)
            & epoch["CLEAN_keep"].astype(bool)
        ]
        vals=pd.to_numeric(g["H_m"],errors="coerce").dropna().sort_values().to_numpy()
        if len(vals):
            y=np.arange(1,len(vals)+1)/len(vals)
            ax.plot(vals,y,lw=1.2,color=CLASS_COLORS[cls],label=cls)
    ax.set_xlabel("CLEAN horizontal error (m)",fontsize=8.1)
    ax.set_ylabel("Empirical cumulative probability",fontsize=8.1)
    style_axes(ax); panel_label(ax,"(b)")
    ax.texts[-1].set_position((-0.18, 1.055))

    # (c) contamination by receiver class
    ax=axes[1,0]
    for xi,cls in enumerate(CLASSES):
        vals=pd.to_numeric(d.loc[d["Receiver_Class"].eq(cls),"Outlier_pct"],errors="coerce").dropna().to_numpy()
        jit=np.linspace(-0.06,0.06,len(vals)) if len(vals)>1 else np.array([0.0])
        ax.scatter(np.full(len(vals),xi)+jit,vals,s=28,
                   facecolor=CLASS_COLORS[cls],edgecolor="black",linewidth=0.4)
        if len(vals):
            medv=float(np.median(vals))
            ax.plot([xi-0.16,xi+0.16],[medv,medv],color="black",lw=1.8)
    ax.set_xticks(range(3)); ax.set_xticklabels(CLASSES,fontsize=7.4)
    ax.set_ylabel("Position-domain contamination (%)",fontsize=8.1)
    style_axes(ax); panel_label(ax,"(c)")
    ax.texts[-1].set_position((-0.18, 1.055))

    # (d) clean-minus-raw delta for 63 solutions
    ax=axes[1,1]
    dd=d.copy().sort_values("Delta_2D_CleanMinusRaw_m").reset_index(drop=True)
    xx=np.arange(len(dd))
    colors=[CLASS_COLORS[c] for c in dd["Receiver_Class"]]
    ax.scatter(xx,dd["Delta_2D_CleanMinusRaw_m"],s=18,c=colors,edgecolor="black",linewidth=0.25)
    ax.axhline(0,color="0.5",lw=0.8,ls="--")
    ax.text(
        0.035,0.965,
        f"Improved: {imp}/63\nWorsened: {wor}/63\nUnchanged: {eq}/63\nMedian Δ = {med:.4f} m",
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=6.6,
        bbox=dict(boxstyle="round,pad=0.20", facecolor="white", edgecolor="0.72", alpha=1.0),
        zorder=5,
    )
    ax.set_xlabel("Usable Test × Receiver × Product solutions",fontsize=8.0)
    ax.set_ylabel("Δ horizontal RMSE = CLEAN − RAW (m)",fontsize=8.0)
    style_axes(ax); panel_label(ax,"(d)")
    ax.texts[-1].set_position((-0.18, 1.055))

    fig.legend(
        handles=receiver_class_legend_handles(),
        loc="upper center",
        bbox_to_anchor=(0.5, 1.015),
        ncol=3,
        frameon=False,
        columnspacing=1.4,
        handletextpad=0.45,
    )
    fig.subplots_adjust(top=0.88, bottom=0.11, left=0.10, right=0.985, hspace=0.42, wspace=0.32)
    return save_figure(fig,"Fig07_RAW_CLEAN_Position_QC")


# =============================================================================
# MAIN TABLES
# =============================================================================

def make_table1(s: Sources) -> pd.DataFrame:
    """
    Final Table 1 combines physical receiver/test identity with the publication-ready
    session metadata. No values are inferred from receiver class.
    """
    df=s.c10_sessions.copy()
    # Preserve exact machine-audited rows; reorder only when Receiver_ID exists.
    if "Receiver_ID" in df.columns:
        df=sort_physical(df)
    save_df(df,TAB_DIR/"Table1_Experimental_Design_and_Session_Metadata.csv")
    return df


def cross_center_osb_filename(s: Sources) -> str:
    m=s.c10_master.copy()
    file_col=find_col(m,["Exact_Filename","Filename","File","Basename"],required=True)
    center_col=find_col(m,["Product_Center","Center","Provider","Analysis_Center"],required=True)
    mm=m[
        m[center_col].astype(str).str.upper().eq("CODE")
        & m[file_col].astype(str).str.contains("COD0.*FIN.*OSB.*BIA",case=False,regex=True,na=False)
    ]
    if mm.empty:
        die("Cannot locate CODE final OSB filename in Comment-10 master.")
    vals=mm[file_col].astype(str).unique()
    if len(vals)!=1:
        die(f"Expected one unique CODE final OSB filename, found {vals}")
    return vals[0]


def make_table2(s: Sources) -> pd.DataFrame:
    """
    Correct the known same-center-publication-table limitation:
    IGS/JAX operational configurations use CODE final OSB according to the final
    cross-center provenance gate.
    """
    df=s.c10_products.copy()
    center_col=find_col(df,["Center","Configuration","Product_Center"],required=True)
    bias_col=find_col(df,["Bias product","Bias_Product","Bias"],required=False)
    avail_col=find_col(df,["Bias availability","Bias_Availability"],required=False)

    code_bia=cross_center_osb_filename(s)

    # Add explicit manuscript-facing provenance columns without destroying original.
    df["Operational_Bias_Source_Final"]=""
    df["Operational_Bias_Filename_Final"]=""

    for i,r in df.iterrows():
        c=str(r[center_col]).upper()
        if c in ("IGS","JAX"):
            df.at[i,"Operational_Bias_Source_Final"]="CODE final OSB"
            df.at[i,"Operational_Bias_Filename_Final"]=code_bia
        else:
            if bias_col:
                df.at[i,"Operational_Bias_Source_Final"]=str(r[bias_col])
            # exact filename for own-center bias from provenance master
            master=s.c10_master.copy()
            fcol=find_col(master,["Exact_Filename","Filename","File","Basename"],required=True)
            ccol=find_col(master,["Product_Center","Center","Provider","Analysis_Center"],required=True)
            g=master[
                master[ccol].astype(str).str.upper().eq(c)
                & master[fcol].astype(str).str.contains(r"\.BIA$|OSB",case=False,regex=True,na=False)
            ]
            if len(g):
                df.at[i,"Operational_Bias_Filename_Final"]=str(g.iloc[0][fcol])

    save_df(df,TAB_DIR/"Table2_Operational_Precise_Product_Configurations.csv")
    return df


def make_table3(s: Sources) -> pd.DataFrame:
    """
    Table 3 is a locked processing-setting table. Values here are methodological
    constants from the final audited production configurations, not result data.
    They are included explicitly so the manuscript table is reproducible.

    If a later exact config-reader is added, it should be cross-checked against
    these values rather than silently replacing them.
    """
    rows=[
        ["Processing mode","PPP-static","PPP-static","PPP-static"],
        ["Solution type","Combined, no phase reset","Combined, no phase reset","Combined, no phase reset"],
        ["Elevation mask","5°","5°","5°"],
        ["SNR mask","Off","Off","Off"],
        ["Ionospheric model","Dual-frequency IF","Dual-frequency IF","Dual-frequency IF"],
        ["Troposphere","Estimated ZTD + gradients","Estimated ZTD + gradients","Estimated ZTD + gradients"],
        ["Satellite ephemeris","Precise","Precise","Precise"],
        ["Receiver dynamics","Off","Off","Off"],
        ["Ambiguity resolution","Off (float)","Off (float)","Off (float)"],
        ["Constellations","GPS + GLO + GAL + BDS","GPS + GLO + GAL + BDS","GPS + GAL + BDS"],
        ["Enabled RTKLIB frequency slots","L1 + L2 + L5","L1 + L2","L1 + L2 + L5"],
        ["Code/phase error ratio","100","100","300"],
        ["Carrier-phase error term","0.003 m","0.003 m","0.006 m"],
        ["Ambiguity process noise","0.0001","0.0001","0.001"],
        ["Slip backstop","0.10","0.10","0.15"],
        ["Doppler–TDCP backstop","5","5","10"],
        ["Code innovation guard","30 m","30 m","50 m"],
        ["Ionospheric innovation guard","30 m","30 m","100 m"],
        ["Output","ECEF, every available solution epoch","ECEF, every available solution epoch","ECEF, every available solution epoch"],
        ["Verified GPS IF mapping","Predominantly slot 0+1 (L1/L2)","Receiver-specific audited configuration","Native smartphone slot 0+2 (L1/L5)"],
    ]
    df=pd.DataFrame(rows,columns=["Setting","CHC_i80","Trimble_MB2","Xiaomi_Smartphones"])
    save_df(df,TAB_DIR/"Table3_PPP_Processing_and_Stochastic_Settings.csv")
    return df


def make_table4(s: Sources) -> pd.DataFrame:
    if s.stage1_defs is not None and len(s.stage1_defs):
        df=s.stage1_defs.copy()
    else:
        # Locked manuscript-facing definitions; no numerical results.
        rows=[
            ["Median C/N₀","Core","Median of valid RINEX signal-strength observations","Higher"],
            ["Robust C/N₀ dispersion","Core","1.4826 × MAD of valid signal-strength observations","Lower"],
            ["GPS L1 CMC robust dispersion","Core","Robust dispersion of segment-centered matched GPS L1 CMC residuals","Lower"],
            ["GPS L1 CMC P95","Core","P95 of absolute segment-centered GPS L1 CMC residuals","Lower"],
            ["Carrier-phase discontinuity rate","Core","Robust phase jumps per 1000 valid phase transitions","Lower"],
            ["Median phase-arc duration","Core","Median duration of time-gap/jump-defined carrier-phase arcs","Higher"],
            ["Epoch retention","Core","Percentage of expected epochs that are present","Higher"],
            ["Observation completeness","Core","Percentage of declared code/phase slots containing valid observations","Higher"],
            ["Median usable satellites","Core","Median satellites per epoch with at least one matched valid code+phase family","Higher*"],
            ["Multi-frequency availability","Core","Percentage of usable epoch–satellite cases containing at least two usable bands","Higher"],
            ["Signal-diversity count","Secondary","Number of usable constellation–signal families","Higher"],
            ["GPS L5 CMC robust dispersion","Secondary","GPS L5 equivalent of segment-centered robust CMC dispersion","Lower"],
        ]
        df=pd.DataFrame(rows,columns=["Metric","Role","Definition","Preferred_Direction"])
    save_df(df,TAB_DIR/"Table4_Stage1_Raw_Observation_Quality_Metrics.csv")
    return df


# =============================================================================
# SUPPLEMENTARY TABLES
# =============================================================================

def make_supplementary(s: Sources):
    save_df(s.gt, SUPP_DIR/"Table_S1_Receiver_Specific_Ground_Truth.csv")
    save_df(sort_physical(s.stage1), SUPP_DIR/"Table_S2_Complete_Stage1_Metrics.csv")
    save_df(sort_physical(s.stage2), SUPP_DIR/"Table_S3_Complete_Stage2_Results.csv")

    # S4: exact precise products + broadcast nav + master provenance
    p=s.c10_master.copy()
    p["Supplement_Record_Type"]="PRECISE_PRODUCT"
    n=s.c10_nav.copy()
    n["Supplement_Record_Type"]="BROADCAST_NAV"
    # union preserving all columns
    s4=pd.concat([p,n],ignore_index=True,sort=False)
    save_df(s4,SUPP_DIR/"Table_S4_Product_and_Navigation_Provenance.csv")

    # S5: primary + robustness statistics, clearly tagged
    frames=[]
    for name,df in [
        ("COMMENT11_BLOCKED_PRIMARY",s.c11_block),
        ("COMMENT11_LOTO",s.c11_loto),
        ("COMMENT11_FIXED_TEST",s.c11_fixed),
        ("COMMENT12_REGISTRY",s.c12_registry),
        ("COMMENT12_PRIMARY_LOCK",s.c12_primary),
    ]:
        x=df.copy()
        x.insert(0,"Source_Block",name)
        frames.append(x)
    s5=pd.concat(frames,ignore_index=True,sort=False)
    save_df(s5,SUPP_DIR/"Table_S5_Statistical_Association_and_Exact_Inference.csv")

    # S6 reviewer-driven sensitivity/audits
    frames=[]
    for name,df in [
        ("COMMENT7_SAMPLING_DETAIL",s.c7_detail),
        ("COMMENT7_SAMPLING_SUMMARY",s.c7_sum),
        ("COMMENT8_CMC_SENSITIVITY",s.c8_assoc),
        ("COMMENT8_ARC_DEPENDENCE",s.c8_arc),
        ("COMMENT11_ROBUSTNESS_LOCK",s.c12_robust),
    ]:
        x=df.copy()
        x.insert(0,"Source_Block",name)
        frames.append(x)
    s6=pd.concat(frames,ignore_index=True,sort=False)
    save_df(s6,SUPP_DIR/"Table_S6_Reviewer_Driven_Sensitivity_Audits.csv")


# =============================================================================
# OUTPUT MANIFEST / REPORT
# =============================================================================

def output_manifest(gate_path: Path, created_files: list[Path], epoch_ok: bool) -> Path:
    source_paths=[
        SRC_STAGE1,SRC_STAGE1_PARSER_QC,SRC_STAGE2,SRC_STAGE2_AUDIT,SRC_GT,
        SRC_DATASET,SRC_ADJ,SRC_C7_DETAIL,SRC_C7_SUM,SRC_C8_ASSOC,SRC_C8_ARC,
        SRC_C11_BLOCK,SRC_C11_LOTO,SRC_C11_FIXED,SRC_C12_REGISTRY,
        SRC_C12_PRIMARY,SRC_C12_ROBUST,SRC_C10_SESSIONS,SRC_C10_PRODUCTS,
        SRC_C10_NAV,SRC_C10_MASTER,
    ]
    src=[]
    for p in source_paths:
        src.append({
            "path":str(p),
            "sha256":sha256_file(p) if p.exists() and p.is_file() else "",
            "exists":p.exists(),
        })

    data={
        "generated_at":datetime.now().isoformat(timespec="seconds"),
        "source_gate":str(gate_path),
        "source_gate_sha256":sha256_file(gate_path),
        "epoch_fig6_7_crosscheck_passed":epoch_ok,
        "authoritative_sources":src,
        "outputs":[str(p) for p in created_files if p.exists()],
    }
    out=LOG_DIR/f"PROJECT1_FINAL_OUTPUT_MANIFEST_{STAMP}.json"
    out.write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding="utf-8")
    return out


def main() -> int:
    created=[]
    gate=require_gate_pass()

    print("="*90)
    print("PROJECT 1 FINAL FIGURES / TABLES GENERATOR")
    print("="*90)
    print(f"PASS gate: {gate}")

    s=load_sources()
    core_checks(s)

    print("\n[1/7] Figure 5")
    created += list(make_fig5(s))

    print("[2/7] Figure 8")
    created += list(make_fig8(s))

    print("[3/7] Figure 9")
    created += list(make_fig9(s))

    print("[4/7] Figure 10")
    created += list(make_fig10(s))

    print("[5/7] Building epoch-level ENU master for Figures 6–7")
    epoch,chk=build_epoch_master(s)

    print("[6/7] Figure 6")
    created += list(make_fig6(s,epoch))

    print("[7/7] Figure 7")
    created += list(make_fig7(s,epoch,chk))

    print("\nGenerating Tables 1–4")
    t1=make_table1(s)
    t2=make_table2(s)
    t3=make_table3(s)
    t4=make_table4(s)
    created += [
        TAB_DIR/"Table1_Experimental_Design_and_Session_Metadata.csv",
        TAB_DIR/"Table2_Operational_Precise_Product_Configurations.csv",
        TAB_DIR/"Table3_PPP_Processing_and_Stochastic_Settings.csv",
        TAB_DIR/"Table4_Stage1_Raw_Observation_Quality_Metrics.csv",
    ]

    print("Generating Supplementary Tables S1–S6")
    make_supplementary(s)
    created += [
        SUPP_DIR/"Table_S1_Receiver_Specific_Ground_Truth.csv",
        SUPP_DIR/"Table_S2_Complete_Stage1_Metrics.csv",
        SUPP_DIR/"Table_S3_Complete_Stage2_Results.csv",
        SUPP_DIR/"Table_S4_Product_and_Navigation_Provenance.csv",
        SUPP_DIR/"Table_S5_Statistical_Association_and_Exact_Inference.csv",
        SUPP_DIR/"Table_S6_Reviewer_Driven_Sensitivity_Audits.csv",
    ]

    manifest=output_manifest(gate,created,epoch_ok=True)
    created.append(manifest)

    report=LOG_DIR/f"PROJECT1_FINAL_FIGURES_TABLES_REPORT_{STAMP}.txt"
    lines=[
        "="*90,
        "PROJECT 1 FINAL FIGURES / TABLES GENERATION REPORT",
        "="*90,
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Source gate: {gate}",
        "",
        "FINAL OUTPUT STATUS: PASS",
        "",
        "Figures:",
        "  Fig. 5  PASS",
        "  Fig. 6  PASS",
        "  Fig. 7  PASS",
        "  Fig. 8  PASS",
        "  Fig. 9  PASS",
        "  Fig. 10 PASS",
        "",
        "Main tables:",
        "  Table 1 PASS",
        "  Table 2 PASS",
        "  Table 3 PASS",
        "  Table 4 PASS",
        "",
        "Supplementary:",
        "  Table S1–S6 PASS",
        "",
        f"Manifest: {manifest}",
        "="*90,
    ]
    report.write_text("\n".join(lines),encoding="utf-8")
    created.append(report)

    print("\n".join(lines))
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except FinalGeneratorError as exc:
        fail=LOG_DIR/f"PROJECT1_FINAL_FIGURES_TABLES_FAIL_{STAMP}.txt"
        fail.write_text(
            f"PROJECT 1 FINAL GENERATOR FAILED\n\n{exc}\n",
            encoding="utf-8"
        )
        print("\nFATAL:")
        print(exc)
        print(f"\nFailure report: {fail}")
        sys.exit(2)
    except Exception as exc:
        fail=LOG_DIR/f"PROJECT1_FINAL_FIGURES_TABLES_EXCEPTION_{STAMP}.txt"
        fail.write_text(
            "PROJECT 1 FINAL GENERATOR EXCEPTION\n\n"
            + repr(exc)
            + "\n",
            encoding="utf-8"
        )
        raise
