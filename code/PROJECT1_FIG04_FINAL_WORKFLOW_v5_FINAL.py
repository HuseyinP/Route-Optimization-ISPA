# -*- coding: utf-8 -*-
"""
PROJECT1_FIG04_FINAL_WORKFLOW_v5_TEXTLOCK.py
==================================

Final Publication Workflow for Project 1 — Figure 4 (Q1 Publication Ready — text-corrected).

Design Improvements (v4)
------------------------
- Mathematically balanced grid architecture: 17.5 cm x 22.5 cm.
- Modern card layout: Badge pill + Bold title + Subtle divider line + Styled bullets.
- Eliminated text overlapping & clipping in multi-line stages (Stage 4A/4B).
- Balanced 8-stage flow with clean split/convergence geometry (Stage 4A/4B).
- Full-card representation for Stage 8 (Scientific Synthesis).
- High-contrast academic color palette compliant with IEEE/Sensors standards.

Outputs
-------
C:\\IEEE\\PAPER_OUTPUT\\FIGURES\\
    Fig04_Overall_Experimental_Analysis_Workflow_v4.pdf
    Fig04_Overall_Experimental_Analysis_Workflow_v4.png
    Fig04_Overall_Experimental_Analysis_Workflow_v4.tiff

Note: This is a strictly methodological workflow figure (no result values plotted).
"""

from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

# ---------------------------------------------------------------------
# Output Directory
# ---------------------------------------------------------------------
OUT = Path(r"C:\IEEE\PAPER_OUTPUT\FIGURES")
OUT.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# Publication Dimensions & Typography
# ---------------------------------------------------------------------
CM = 1.0 / 2.54
FIG_W_CM = 17.5
FIG_H_CM = 22.5

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "font.size": 8.0,
    "axes.linewidth": 0.8,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "savefig.dpi": 600,
})

# ---------------------------------------------------------------------
# Q1 Academic Color Palette
# ---------------------------------------------------------------------
PALETTE = {
    # Typography
    "title":      "#0F172A",
    "subtitle":   "#475569",
    "text":       "#1E293B",
    "muted":      "#64748B",
    "white":      "#FFFFFF",
    "line":       "#64748B",

    # Stage 01: Ground Truth (Emerald / Forest)
    "s1_fill":    "#F0FDF4",
    "s1_edge":    "#16A34A",
    "s1_badge":   "#15803D",

    # Stage 02: Experimental Design (Slate / Navy)
    "s2_fill":    "#F8FAFC",
    "s2_edge":    "#475569",
    "s2_badge":   "#334155",

    # Stage 03: Raw GNSS Obs (Steel / Blue-Grey)
    "s3_fill":    "#F1F5F9",
    "s3_edge":    "#64748B",
    "s3_badge":   "#475569",

    # Stage 04A: Stage 1 Quality (Warm Amber / Ochre)
    "s4a_fill":   "#FFFBEB",
    "s4a_edge":   "#D97706",
    "s4a_badge":  "#B45309",

    # Stage 04B: Stage 2 PPP (Indigo / Royal)
    "s4b_fill":   "#EEF2FF",
    "s4b_edge":   "#4F46E5",
    "s4b_badge":  "#4338CA",

    # Stage 05: Association (Teal / Cyan)
    "s5_fill":    "#F0FDFA",
    "s5_edge":    "#0D9488",
    "s5_badge":   "#0F766E",

    # Stage 06: Dependence Control (Violet / Purple)
    "s6_fill":    "#FAF5FF",
    "s6_edge":    "#7C3AED",
    "s6_badge":   "#6D28D9",

    # Stage 07: Audits (Rose / Carmine)
    "s7_fill":    "#FFF1F2",
    "s7_edge":    "#E11D48",
    "s7_badge":   "#BE123C",

    # Stage 08: Scientific Synthesis (Cobalt / Deep Blue)
    "s8_fill":    "#EFF6FF",
    "s8_edge":    "#2563EB",
    "s8_badge":   "#1D4ED8",
}

# ---------------------------------------------------------------------
# Modern Card Drawing Function
# ---------------------------------------------------------------------
def workflow_card(ax, x, y, w, h, *,
                  stage_no: str,
                  title: str,
                  items: list[str],
                  fill_color: str,
                  edge_color: str,
                  badge_color: str,
                  title_fs: float = 8.0,
                  body_fs: float = 6.6,
                  stage_fs: float = 7.6,
                  radius: float = 0.012,
                  lw: float = 1.1):
    """
    Renders a modern, publication-grade workflow card with:
    - Rounded outer card
    - Top-left badge pill for stage number
    - Upper header line and title
    - Structured bullet list with precise vertical line budgeting
    """
    # 1. Main Background Card
    card = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad=0.003,rounding_size={radius}",
        facecolor=fill_color,
        edgecolor=edge_color,
        linewidth=lw,
        zorder=2
    )
    ax.add_patch(card)

    # 2. Stage Badge Pill
    badge_w = 0.048 if len(stage_no) <= 2 else 0.062
    badge_h = 0.022
    bx = x + 0.012
    by = y + h - badge_h - 0.010

    badge = FancyBboxPatch(
        (bx, by), badge_w, badge_h,
        boxstyle="round,pad=0.002,rounding_size=0.006",
        facecolor=badge_color,
        edgecolor=badge_color,
        linewidth=0,
        zorder=3
    )
    ax.add_patch(badge)

    ax.text(
        bx + badge_w / 2.0, by + badge_h / 2.0,
        stage_no,
        ha="center", va="center",
        fontsize=stage_fs,
        fontweight="bold",
        color=PALETTE["white"],
        zorder=4
    )

    # 3. Header Title
    tx = bx + badge_w + 0.010
    ty = by + badge_h / 2.0
    ax.text(
        tx, ty,
        title,
        ha="left", va="center",
        fontsize=title_fs,
        fontweight="bold",
        color=badge_color,
        zorder=4
    )

    # 4. Subtle Header Divider Line
    div_y = y + h - 0.038
    ax.plot(
        [x + 0.012, x + w - 0.012],
        [div_y, div_y],
        color=edge_color,
        linewidth=0.6,
        alpha=0.45,
        zorder=3
    )

    # 5. Bullet Items (Evenly spaced & wrapped cleanly)
    num_items = len(items)
    if num_items > 0:
        available_h = div_y - y - 0.010
        item_gap = available_h / float(num_items)
        start_y = div_y - 0.012

        for idx, text in enumerate(items):
            cur_y = start_y - (idx * item_gap)
            ax.text(
                x + 0.014, cur_y,
                "•",
                ha="left", va="top",
                fontsize=body_fs + 1.0,
                fontweight="bold",
                color=badge_color,
                zorder=4
            )
            ax.text(
                x + 0.028, cur_y - 0.001,
                text,
                ha="left", va="top",
                fontsize=body_fs,
                color=PALETTE["text"],
                linespacing=1.20,
                zorder=4
            )

    return card


# ---------------------------------------------------------------------
# Connectors
# ---------------------------------------------------------------------
def draw_v_arrow(ax, x, y_start, y_end, color=None, lw=1.3):
    ax.add_patch(FancyArrowPatch(
        (x, y_start), (x, y_end),
        arrowstyle="-|>",
        mutation_scale=10.5,
        linewidth=lw,
        color=color or PALETTE["line"],
        shrinkA=0, shrinkB=0,
        zorder=1
    ))


def draw_line(ax, x1, y1, x2, y2, color=None, lw=1.15):
    ax.plot([x1, x2], [y1, y2],
            color=color or PALETTE["line"],
            linewidth=lw,
            solid_capstyle="round",
            zorder=1)


# ---------------------------------------------------------------------
# Figure Construction
# ---------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(FIG_W_CM * CM, FIG_H_CM * CM))
fig.patch.set_facecolor("white")
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")

# Top Header Title
ax.text(
    0.040, 0.985,
    "Overall Experimental and Analysis Workflow",
    ha="left", va="top",
    fontsize=10.5,
    fontweight="bold",
    color=PALETTE["title"]
)

# Horizontal Separator Below Header
draw_line(ax, 0.040, 0.965, 0.960, 0.965, color="#CBD5E1", lw=1.0)

# Card Grid Parameters
W_FULL = 0.880
X_FULL = 0.060
W_HALF = 0.425
X_LEFT = 0.060
X_RIGHT = 0.515

# =====================================================================
# STAGE 01: GROUND TRUTH
# =====================================================================
y_s1 = 0.872
h_s1 = 0.076
workflow_card(
    ax, X_FULL, y_s1, W_FULL, h_s1,
    stage_no="01",
    title="INDEPENDENT GROUND TRUTH",
    items=[
        "Geodetic network adjustment and GNSS/terrestrial coordinate validation",
        "Receiver-specific coordinate transfer → 12 ITRF2020 ECEF reference positions"
    ],
    fill_color=PALETTE["s1_fill"],
    edge_color=PALETTE["s1_edge"],
    badge_color=PALETTE["s1_badge"],
    title_fs=8.2, body_fs=6.8, stage_fs=7.6
)

# =====================================================================
# STAGE 02: EXPERIMENTAL DESIGN
# =====================================================================
y_s2 = 0.766
h_s2 = 0.076
draw_v_arrow(ax, 0.500, y_s1, y_s2 + h_s2, color=PALETTE["s1_edge"])

workflow_card(
    ax, X_FULL, y_s2, W_FULL, h_s2,
    stage_no="02",
    title="EXPERIMENTAL DESIGN",
    items=[
        "3 static observation campaigns (Tests 1–3) × 4 simultaneous receiver stations",
        "3 distinct observation regimes: Geodetic (CHC) • OEM (MB2) • Smartphone (Xiaomi)"
    ],
    fill_color=PALETTE["s2_fill"],
    edge_color=PALETTE["s2_edge"],
    badge_color=PALETTE["s2_badge"],
    title_fs=8.2, body_fs=6.8, stage_fs=7.6
)

# =====================================================================
# STAGE 03: RAW GNSS OBSERVATIONS
# =====================================================================
y_s3 = 0.660
h_s3 = 0.076
draw_v_arrow(ax, 0.500, y_s2, y_s3 + h_s3, color=PALETTE["s2_edge"])

workflow_card(
    ax, X_FULL, y_s3, W_FULL, h_s3,
    stage_no="03",
    title="RAW GNSS OBSERVATIONS",
    items=[
        "12 multi-GNSS RINEX datasets with synchronized 1-s temporal support",
        "Simultaneous observations within each Test block (GPS • GLO • GAL • BDS)"
    ],
    fill_color=PALETTE["s3_fill"],
    edge_color=PALETTE["s3_edge"],
    badge_color=PALETTE["s3_badge"],
    title_fs=8.2, body_fs=6.8, stage_fs=7.6
)

# Split Connector from Stage 03 -> Stage 04A / 04B
y_split_top = y_s3
y_split_mid = 0.635
y_split_bot = 0.612

x_center_left = X_LEFT + W_HALF / 2.0   # 0.2725
x_center_right = X_RIGHT + W_HALF / 2.0 # 0.7275

draw_line(ax, 0.500, y_split_top, 0.500, y_split_mid, color=PALETTE["line"])
draw_line(ax, x_center_left, y_split_mid, x_center_right, y_split_mid, color=PALETTE["line"])
draw_v_arrow(ax, x_center_left, y_split_mid, y_split_bot, color=PALETTE["s4a_edge"])
draw_v_arrow(ax, x_center_right, y_split_mid, y_split_bot, color=PALETTE["s4b_edge"])

# =====================================================================
# STAGE 04A: STAGE-1 OBSERVATION QUALITY (Left)
# =====================================================================
y_s4 = 0.468
h_s4 = 0.144

workflow_card(
    ax, X_LEFT, y_s4, W_HALF, h_s4,
    stage_no="04A",
    title="STAGE 1 | RAW QUALITY",
    items=[
        "10 core + 2 secondary quality metrics",
        "C/N₀ distribution & MAD robust dispersion",
        "GPS L1 CMC residuals (P95 & robust σ)",
        "Phase arcs • jumps • retention • completeness"
    ],
    fill_color=PALETTE["s4a_fill"],
    edge_color=PALETTE["s4a_edge"],
    badge_color=PALETTE["s4a_badge"],
    title_fs=7.4, body_fs=6.45, stage_fs=7.2
)

# =====================================================================
# STAGE 04B: STAGE-2 PPP & POSITION DOMAIN (Right)
# =====================================================================
workflow_card(
    ax, X_RIGHT, y_s4, W_HALF, h_s4,
    stage_no="04B",
    title="STAGE 2 | PPP & POSITION",
    items=[
        "6 operational precise-product configurations",
        "Audited receiver-specific float PPP / IF",
        "Truth-referenced ENU epoch errors",
        "Robust filtering → RAW/CLEAN RMSE & sensitivity"
    ],
    fill_color=PALETTE["s4b_fill"],
    edge_color=PALETTE["s4b_edge"],
    badge_color=PALETTE["s4b_badge"],
    title_fs=7.4, body_fs=6.45, stage_fs=7.2
)

# Rejoin Connector from Stage 04A / 04B -> Stage 05
y_join_top = y_s4
y_join_mid = 0.443
y_join_bot = 0.420

draw_line(ax, x_center_left, y_join_top, x_center_left, y_join_mid, color=PALETTE["s4a_edge"])
draw_line(ax, x_center_right, y_join_top, x_center_right, y_join_mid, color=PALETTE["s4b_edge"])
draw_line(ax, x_center_left, y_join_mid, x_center_right, y_join_mid, color=PALETTE["line"])
draw_v_arrow(ax, 0.500, y_join_mid, y_join_bot, color=PALETTE["s5_edge"])

# =====================================================================
# STAGE 05: ASSOCIATION
# =====================================================================
y_s5 = 0.344
h_s5 = 0.076
workflow_card(
    ax, X_FULL, y_s5, W_FULL, h_s5,
    stage_no="05",
    title="STAGE-1 / STAGE-2 ASSOCIATION",
    items=[
        "Stage-1 observation metrics ↔ product-adjusted median CLEAN horizontal RMSE",
        "Spearman rank association evaluated across physical Test × Receiver datasets"
    ],
    fill_color=PALETTE["s5_fill"],
    edge_color=PALETTE["s5_edge"],
    badge_color=PALETTE["s5_badge"],
    title_fs=8.2, body_fs=6.8, stage_fs=7.6
)

# =====================================================================
# STAGE 06: STATISTICAL DEPENDENCE CONTROL
# =====================================================================
y_s6 = 0.238
h_s6 = 0.076
draw_v_arrow(ax, 0.500, y_s5, y_s6 + h_s6, color=PALETTE["s5_edge"])

workflow_card(
    ax, X_FULL, y_s6, W_FULL, h_s6,
    stage_no="06",
    title="STATISTICAL DEPENDENCE CONTROL",
    items=[
        "Inferential unit locked to physical Test × Receiver dataset (N = 11 analyzable)",
        "Exact Test-blocked permutation inference"
    ],
    fill_color=PALETTE["s6_fill"],
    edge_color=PALETTE["s6_edge"],
    badge_color=PALETTE["s6_badge"],
    title_fs=8.2, body_fs=6.8, stage_fs=7.6
)

# =====================================================================
# STAGE 07: REPRODUCIBILITY & SENSITIVITY AUDITS
# =====================================================================
y_s7 = 0.132
h_s7 = 0.076
draw_v_arrow(ax, 0.500, y_s6, y_s7 + h_s7, color=PALETTE["s6_edge"])

workflow_card(
    ax, X_FULL, y_s7, W_FULL, h_s7,
    stage_no="07",
    title="REPRODUCIBILITY & SENSITIVITY AUDITS",
    items=[
        "Common 1-s sampling support & CMC treatment sensitivity",
        "Runtime IF mapping • LOTO stability • processing / product / OSB provenance"
    ],
    fill_color=PALETTE["s7_fill"],
    edge_color=PALETTE["s7_edge"],
    badge_color=PALETTE["s7_badge"],
    title_fs=8.2, body_fs=6.8, stage_fs=7.6
)

# =====================================================================
# STAGE 08: SCIENTIFIC SYNTHESIS & INTERPRETATION
# =====================================================================
y_s8 = 0.026
h_s8 = 0.076
draw_v_arrow(ax, 0.500, y_s7, y_s8 + h_s8, color=PALETTE["s7_edge"])

workflow_card(
    ax, X_FULL, y_s8, W_FULL, h_s8,
    stage_no="08",
    title="SCIENTIFIC SYNTHESIS & INTERPRETATION",
    items=[
        "Receiver-dependent PPP sensitivity to operational precise-product configurations",
        "Association between raw-observation quality and PPP positioning performance"
    ],
    fill_color=PALETTE["s8_fill"],
    edge_color=PALETTE["s8_edge"],
    badge_color=PALETTE["s8_badge"],
    title_fs=8.2, body_fs=6.8, stage_fs=7.6
)

# ---------------------------------------------------------------------
# Export Multi-format High-Res Files
# ---------------------------------------------------------------------
stem = OUT / "Fig04_Overall_Experimental_Analysis_Workflow_v5_FINAL"

fig.savefig(
    stem.with_suffix(".pdf"),
    bbox_inches="tight",
    pad_inches=0.04,
    facecolor="white"
)

fig.savefig(
    stem.with_suffix(".png"),
    dpi=600,
    bbox_inches="tight",
    pad_inches=0.04,
    facecolor="white"
)

fig.savefig(
    stem.with_suffix(".tiff"),
    dpi=600,
    bbox_inches="tight",
    pad_inches=0.04,
    facecolor="white",
    pil_kwargs={"compression": "tiff_lzw"}
)

plt.close(fig)

print("Generated Successfully:")
print(f"  [PDF]  {stem.with_suffix('.pdf')}")
print(f"  [PNG]  {stem.with_suffix('.png')}")
print(f"  [TIFF] {stem.with_suffix('.tiff')}")
