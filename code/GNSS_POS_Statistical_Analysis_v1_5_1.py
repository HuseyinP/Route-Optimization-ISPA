# -*- coding: utf-8 -*-
"""
GNSS_POS_Statistical_Analysis_v1_4.py

Scientific RTKLIB positioning analysis with:
  1) 72-solution processing audit,
  2) RAW + robust CLEAN statistics,
  3) two-axis QC: USABLE/FAILED solution status + contamination class,
  4) exclusion of *_events.pos files,
  5) support for Model-B final ground truth CSV.

Primary GT:
C:\IEEE\Ground_Truth\GNSS_GT_v1_3_TRUTH_MODEL_B_LEVEL_TABLE.csv

Primary POS root:
C:\IEEE\RTKLIB_DATA

Final paper-reporting outputs:
C:\IEEE\GNSS_ANALYSIS\POS_STATISTICS_V1_5_1_1\
    GNSS_POS_STATISTICS_V1_5_1_1.csv
    GNSS_POS_PROCESSING_AUDIT_V1_5_1.csv
    GNSS_POS_STATUS_SUMMARY_V1_5_1.csv
    GNSS_POS_PRODUCT_SUMMARY_V1_5_1.csv
    GNSS_POS_RECEIVER_SUMMARY_V1_5_1.csv
    GNSS_POS_STATISTICS_V1_5_1_1.xlsx

Methodological note:
Outliers are not hidden. RAW and CLEAN statistics are both retained.
Solution availability and epoch contamination are treated as separate scientific dimensions.
"""

from pathlib import Path
import math
import re
import numpy as np
import pandas as pd
from pyproj import Transformer

try:
    from sklearn.covariance import MinCovDet
    from scipy.stats import chi2
    HAVE_ROBUST_COV = True
except Exception:
    HAVE_ROBUST_COV = False


# =====================================================================
# CONFIGURATION
# =====================================================================

ROOT = Path(r"C:\IEEE")
POS_ROOT = ROOT / "RTKLIB_DATA"
GT_DIR = ROOT / "Ground_Truth"
OUT_DIR = ROOT / "GNSS_ANALYSIS" / "POS_STATISTICS_V1_5_1_1"
OUT_DIR.mkdir(parents=True, exist_ok=True)

GT_CANDIDATES = [
    GT_DIR / "GNSS_GT_v1_3_TRUTH_MODEL_B_LEVEL_TABLE.csv",
    GT_DIR / "Truth_Final_ITRF96_2023p5.csv",
    GT_DIR / "Truth.csv",
    GT_DIR / "GNSS_GT_v1_3_TRUTH_MODEL_B_LEVEL_TABLE.xlsx",
    GT_DIR / "Grund_Truth.xlsx",
    GT_DIR / "Ground_Truth.xlsx",
    GT_DIR / "Truth.xlsx",
]

PRODUCTS = ["CODE", "GFZ", "GRG", "IGS", "JAX", "WHU"]

FILE_MAP = {
    "CHC1": ("Test-1", "CHC I80", "C1"),
    "OEM1": ("Test-1", "TRIMBLE OEM MB2", "OEM1"),
    "T11":  ("Test-1", "XIAOMI-1", "T11"),
    "T21":  ("Test-1", "XIAOMI-2", "T21"),

    "CHC2": ("Test-2", "CHC I80", "C2"),
    "OEM2": ("Test-2", "TRIMBLE OEM MB2", "OEM2"),
    "T12":  ("Test-2", "XIAOMI-1", "T12"),
    "T22":  ("Test-2", "XIAOMI-2", "T22"),

    "CHC3": ("Test-3", "CHC I80", "C3"),
    "OEM3": ("Test-3", "TRIMBLE OEM MB2", "OEM3"),
    "T13":  ("Test-3", "XIAOMI-1", "T13"),
    "T23":  ("Test-3", "XIAOMI-2", "T23"),
}

RECEIVER_CLASS = {
    "CHC I80": "Geodetic",
    "TRIMBLE OEM MB2": "OEM",
    "XIAOMI-1": "Smartphone",
    "XIAOMI-2": "Smartphone",
}

# Robust filtering
ROBUST_CHI2_PROB = 0.9973
MAD_Z_LIMIT = 5.0
MIN_KEEP_FRACTION = 0.50
MIN_EPOCHS_FOR_FILTER = 30

# Two-axis QC thresholds.
# These are explicit study rules, not universal GNSS standards.

# Axis 1 — Solution status
MIN_USABLE_EPOCHS = 300

# Catastrophic-solution guards. Such solutions remain fully documented
# in the audit, but are not treated as usable positioning solutions.
FAIL_MAX_RMSE_3D_M = 20.0
FAIL_MAX_ABS_BIAS_U_M = 20.0

# Axis 2 — Epoch contamination / robust-rejection class
# Applied independently of solution usability.
CONTAMINATION_LOW_MAX_PCT = 20.0
CONTAMINATION_MODERATE_MAX_PCT = 35.0
CONTAMINATION_HIGH_MAX_PCT = 50.0

ECEF_TO_GEO = Transformer.from_crs(4978, 4979, always_xy=True)
GEO_TO_ECEF = Transformer.from_crs(4979, 4978, always_xy=True)


# =====================================================================
# GROUND TRUTH
# =====================================================================

def _norm_col(s):
    return str(s).strip().lower().replace("_", " ").replace("(", " ").replace(")", " ")


def _read_table(path):
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    return pd.read_excel(path)


def load_ground_truth():
    found = next((p for p in GT_CANDIDATES if p.exists()), None)
    if found is None:
        raise FileNotFoundError(
            "Ground truth not found. Checked:\n" +
            "\n".join(str(p) for p in GT_CANDIDATES)
        )

    gt = _read_table(found).copy()
    cm = {_norm_col(c): c for c in gt.columns}

    def pick(tokens, optional=False):
        for n, original in cm.items():
            if all(t in n for t in tokens):
                return original
        if optional:
            return None
        raise KeyError(
            f"GT column not found for tokens={tokens}; "
            f"columns={list(gt.columns)}"
        )

    c_test = pick(["test"])
    c_rec = pick(["receiver"], optional=True)
    c_rid = pick(["receiver", "id"], optional=True)
    c_x = pick(["x", "m"])
    c_y = pick(["y", "m"])
    c_z = pick(["z", "m"])

    rename = {
        c_test: "Test",
        c_x: "X_GT",
        c_y: "Y_GT",
        c_z: "Z_GT",
    }

    if c_rec is not None:
        rename[c_rec] = "Receiver"

    if c_rid is not None and c_rid != c_rec:
        rename[c_rid] = "Receiver_ID"

    gt = gt.rename(columns=rename)

    if "Receiver" not in gt.columns:
        gt["Receiver"] = ""
    if "Receiver_ID" not in gt.columns:
        gt["Receiver_ID"] = ""

    for c in ["X_GT", "Y_GT", "Z_GT"]:
        gt[c] = pd.to_numeric(gt[c], errors="coerce")

    gt = gt.dropna(subset=["X_GT", "Y_GT", "Z_GT"]).copy()
    return gt, found


def lookup_gt(gt, test, receiver, receiver_id):
    q = gt[
        (gt["Test"].astype(str) == test) &
        (gt["Receiver"].astype(str) == receiver)
    ]
    if len(q) == 1:
        return q.iloc[0]

    q = gt[
        (gt["Test"].astype(str) == test) &
        (gt["Receiver_ID"].astype(str) == receiver_id)
    ]
    if len(q) == 1:
        return q.iloc[0]

    raise KeyError(
        f"GT not uniquely matched: {test} | {receiver} | {receiver_id}"
    )


# =====================================================================
# RTKLIB POS PARSER
# =====================================================================

def parse_rtklib_pos(path):
    rows = []
    header = []

    if not path.exists():
        return pd.DataFrame(), "MISSING"

    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue

            if line.startswith("%"):
                header.append(line.rstrip())
                continue

            tok = line.split()
            if len(tok) < 5:
                continue

            dt = pd.to_datetime(tok[0] + " " + tok[1], errors="coerce")
            if pd.isna(dt):
                continue

            try:
                a, b, c = map(float, tok[2:5])
            except Exception:
                continue

            rec = {
                "Epoch": dt,
                "A": a,
                "B": b,
                "C": c,
            }

            try:
                rec["Q"] = int(float(tok[5])) if len(tok) > 5 else np.nan
            except Exception:
                rec["Q"] = np.nan

            try:
                rec["NS"] = int(float(tok[6])) if len(tok) > 6 else np.nan
            except Exception:
                rec["NS"] = np.nan

            rows.append(rec)

    df = pd.DataFrame(rows)

    if df.empty:
        return df, "EMPTY_OR_UNPARSEABLE"

    hs = " ".join(header).lower()

    is_llh = (
        ("latitude" in hs and "longitude" in hs) or
        (
            df["A"].abs().median() <= 90.0 and
            df["B"].abs().median() <= 180.0
        )
    )

    if is_llh:
        xyz = np.array([
            GEO_TO_ECEF.transform(lon, lat, h)
            for lat, lon, h in zip(df["A"], df["B"], df["C"])
        ])
        df["X"] = xyz[:, 0]
        df["Y"] = xyz[:, 1]
        df["Z"] = xyz[:, 2]
        fmt = "LLH"
    else:
        df["X"] = df["A"]
        df["Y"] = df["B"]
        df["Z"] = df["C"]
        fmt = "ECEF"

    df["POS_Format"] = fmt
    return df, "OK"


# =====================================================================
# GEODESY
# =====================================================================

def gt_geodetic(x, y, z):
    lon, lat, h = ECEF_TO_GEO.transform(x, y, z)
    return lat, lon, h


def ecef_to_enu(dx, dy, dz, lat_deg, lon_deg):
    lat = np.deg2rad(lat_deg)
    lon = np.deg2rad(lon_deg)

    slat, clat = np.sin(lat), np.cos(lat)
    slon, clon = np.sin(lon), np.cos(lon)

    E = -slon * dx + clon * dy
    N = -slat * clon * dx - slat * slon * dy + clat * dz
    U =  clat * clon * dx + clat * slon * dy + slat * dz
    return E, N, U


# =====================================================================
# ROBUST FILTER
# =====================================================================

def iterative_mad_mask(X, zlim=MAD_Z_LIMIT, iterations=3):
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


def robust_mask(X):
    X = np.asarray(X, float)
    finite = np.all(np.isfinite(X), axis=1)
    n = finite.sum()

    if n < MIN_EPOCHS_FOR_FILTER:
        return finite, "NONE_SMALL_SAMPLE"

    if HAVE_ROBUST_COV:
        try:
            xf = X[finite]
            mcd = MinCovDet(random_state=42).fit(xf)
            d2 = mcd.mahalanobis(xf)
            threshold = chi2.ppf(ROBUST_CHI2_PROB, df=3)
            keep_f = d2 <= threshold

            keep = np.zeros(len(X), dtype=bool)
            keep[np.where(finite)[0]] = keep_f

            if keep.sum() / max(n, 1) >= MIN_KEEP_FRACTION:
                return keep, "MCD_CHI2_99.73"
        except Exception:
            pass

    return iterative_mad_mask(X), f"ITERATIVE_MAD_Z{MAD_Z_LIMIT:g}"


# =====================================================================
# STATISTICS
# =====================================================================

def _finite(x):
    a = np.asarray(x, float)
    return a[np.isfinite(a)]


def mean(x):
    a = _finite(x)
    return np.mean(a) if len(a) else np.nan


def median(x):
    a = _finite(x)
    return np.median(a) if len(a) else np.nan


def std(x):
    a = _finite(x)
    return np.std(a, ddof=1) if len(a) > 1 else np.nan


def mae(x):
    a = _finite(x)
    return np.mean(np.abs(a)) if len(a) else np.nan


def rmse(x):
    a = _finite(x)
    return np.sqrt(np.mean(a*a)) if len(a) else np.nan


def percentile(x, p):
    a = _finite(x)
    return np.percentile(a, p) if len(a) else np.nan


def stats_block(df, prefix):
    if df.empty:
        return {
            f"{prefix}_N": 0,
            f"{prefix}_Bias_E_m": np.nan,
            f"{prefix}_Bias_N_m": np.nan,
            f"{prefix}_Bias_U_m": np.nan,
            f"{prefix}_Bias_2D_m": np.nan,
            f"{prefix}_Bias_3D_m": np.nan,
            f"{prefix}_SD_E_m": np.nan,
            f"{prefix}_SD_N_m": np.nan,
            f"{prefix}_SD_U_m": np.nan,
            f"{prefix}_MAE_E_m": np.nan,
            f"{prefix}_MAE_N_m": np.nan,
            f"{prefix}_MAE_U_m": np.nan,
            f"{prefix}_RMSE_E_m": np.nan,
            f"{prefix}_RMSE_N_m": np.nan,
            f"{prefix}_RMSE_U_m": np.nan,
            f"{prefix}_RMSE_2D_m": np.nan,
            f"{prefix}_RMSE_3D_m": np.nan,
            f"{prefix}_P95_2D_m": np.nan,
            f"{prefix}_P95_3D_m": np.nan,
            f"{prefix}_P99_2D_m": np.nan,
            f"{prefix}_P99_3D_m": np.nan,
        }

    E = df["E_err"].to_numpy(float)
    N = df["N_err"].to_numpy(float)
    U = df["U_err"].to_numpy(float)

    H = np.hypot(E, N)
    D3 = np.sqrt(E*E + N*N + U*U)

    bE, bN, bU = mean(E), mean(N), mean(U)

    return {
        f"{prefix}_N": len(df),

        f"{prefix}_Bias_E_m": bE,
        f"{prefix}_Bias_N_m": bN,
        f"{prefix}_Bias_U_m": bU,
        f"{prefix}_Bias_2D_m": math.hypot(bE, bN),
        f"{prefix}_Bias_3D_m": math.sqrt(bE*bE + bN*bN + bU*bU),

        f"{prefix}_SD_E_m": std(E),
        f"{prefix}_SD_N_m": std(N),
        f"{prefix}_SD_U_m": std(U),

        f"{prefix}_MAE_E_m": mae(E),
        f"{prefix}_MAE_N_m": mae(N),
        f"{prefix}_MAE_U_m": mae(U),

        f"{prefix}_RMSE_E_m": rmse(E),
        f"{prefix}_RMSE_N_m": rmse(N),
        f"{prefix}_RMSE_U_m": rmse(U),
        f"{prefix}_RMSE_2D_m": rmse(H),
        f"{prefix}_RMSE_3D_m": rmse(D3),

        f"{prefix}_P95_2D_m": percentile(H, 95),
        f"{prefix}_P95_3D_m": percentile(D3, 95),
        f"{prefix}_P99_2D_m": percentile(H, 99),
        f"{prefix}_P99_3D_m": percentile(D3, 99),
    }


# =====================================================================
# TWO-AXIS QC CLASSIFICATION
# =====================================================================

def classify_solution_status(parse_status, clean_n, clean_rmse_3d, clean_bias_u):
    """
    Axis 1: solution usability.

    USABLE
        Parsed solution with sufficient retained epochs and no catastrophic
        3D/vertical failure.

    FAILED
        Missing/empty/unparseable, insufficient retained epochs, or a
        catastrophic positioning solution.

    This status is intentionally independent of the outlier percentage.
    """
    if parse_status != "OK":
        return "FAILED", parse_status

    if clean_n < MIN_USABLE_EPOCHS:
        return "FAILED", "INSUFFICIENT_CLEAN_EPOCHS"

    if np.isfinite(clean_rmse_3d) and clean_rmse_3d > FAIL_MAX_RMSE_3D_M:
        return "FAILED", "CATASTROPHIC_3D_RMSE"

    if np.isfinite(clean_bias_u) and abs(clean_bias_u) > FAIL_MAX_ABS_BIAS_U_M:
        return "FAILED", "CATASTROPHIC_VERTICAL_BIAS"

    return "USABLE", "MEETS_SOLUTION_QC"


def classify_contamination(outlier_pct, parse_status="OK"):
    """
    Axis 2: fraction of epochs rejected by the robust ENU filter.

        LOW       : <= 20%
        MODERATE  : >20% to 35%
        HIGH      : >35% to 50%
        EXTREME   : >50%

    For missing/empty solutions the class is NOT_APPLICABLE.
    """
    if parse_status != "OK" or not np.isfinite(outlier_pct):
        return "NOT_APPLICABLE"

    if outlier_pct <= CONTAMINATION_LOW_MAX_PCT:
        return "LOW"
    if outlier_pct <= CONTAMINATION_MODERATE_MAX_PCT:
        return "MODERATE"
    if outlier_pct <= CONTAMINATION_HIGH_MAX_PCT:
        return "HIGH"
    return "EXTREME"


# =====================================================================
# EXPECTED MANIFEST
# =====================================================================

def expected_manifest():
    rows = []

    for product in PRODUCTS:
        for base, (test, receiver, rid) in FILE_MAP.items():
            p = POS_ROOT / product / f"{base}.pos"

            rows.append({
                "Product": product,
                "Test": test,
                "Receiver": receiver,
                "Receiver_ID": rid,
                "POS_Basename": base,
                "Expected_POS": str(p),
                "Exists": p.exists(),
                "Bytes": p.stat().st_size if p.exists() else 0,
            })

    return pd.DataFrame(rows)


# =====================================================================
# MAIN
# =====================================================================

def main():
    gt, gt_source = load_ground_truth()
    expected = expected_manifest()

    all_pos = sorted(POS_ROOT.rglob("*.pos"))
    events = [p for p in all_pos if p.name.lower().endswith("_events.pos")]
    analysis_files = [p for p in all_pos if not p.name.lower().endswith("_events.pos")]

    print("=" * 132)
    print("GNSS POS STATISTICAL ANALYSIS v1.5.1")
    print("=" * 132)
    print(f"Ground truth        : {gt_source}")
    print(f"Expected solutions  : {len(expected)}")
    print(f"All .pos files      : {len(all_pos)}")
    print(f"Excluded *_events   : {len(events)}")
    print(f"Candidate solutions : {len(analysis_files)}")
    print("=" * 132)

    result_rows = []
    audit_rows = []

    # Process the expected 72 solutions deterministically.
    for i, exp in expected.iterrows():
        product = exp["Product"]
        test = exp["Test"]
        receiver = exp["Receiver"]
        rid = exp["Receiver_ID"]
        path = Path(exp["Expected_POS"])

        audit = {
            "Product": product,
            "Test": test,
            "Receiver": receiver,
            "Receiver_ID": rid,
            "POS_File": str(path),
            "Exists": path.exists(),
            "Bytes": path.stat().st_size if path.exists() else 0,
        }

        if not path.exists():
            audit.update({
                "Parse_Status": "MISSING",
                "Solution_Status": "FAILED",
                "Status_Reason": "MISSING_POS",
                "Contamination_Class": "NOT_APPLICABLE",
                "Raw_N": 0,
                "Clean_N": 0,
            })
            audit_rows.append(audit)
            print(f"[{i+1:02d}/72] {product:6s} {test:6s} {receiver:16s} FAILED: MISSING_POS")
            continue

        df, parse_status = parse_rtklib_pos(path)
        audit["Parse_Status"] = parse_status

        if parse_status != "OK" or df.empty:
            audit.update({
                "Solution_Status": "FAILED",
                "Status_Reason": parse_status,
                "Contamination_Class": "NOT_APPLICABLE",
                "Raw_N": 0,
                "Clean_N": 0,
            })
            audit_rows.append(audit)
            print(f"[{i+1:02d}/72] {product:6s} {test:6s} {receiver:16s} FAILED: {parse_status}")
            continue

        try:
            g = lookup_gt(gt, test, receiver, rid)
        except Exception as exc:
            audit.update({
                "Solution_Status": "FAILED",
                "Status_Reason": "GT_LOOKUP_FAILED",
                "Contamination_Class": "NOT_APPLICABLE",
                "GT_Error": str(exc),
                "Raw_N": len(df),
                "Clean_N": 0,
            })
            audit_rows.append(audit)
            print(f"[{i+1:02d}/72] {product:6s} {test:6s} {receiver:16s} FAILED: GT_LOOKUP")
            continue

        xg, yg, zg = float(g["X_GT"]), float(g["Y_GT"]), float(g["Z_GT"])
        latg, long, hg = gt_geodetic(xg, yg, zg)

        df["dX"] = df["X"] - xg
        df["dY"] = df["Y"] - yg
        df["dZ"] = df["Z"] - zg

        E, N, U = ecef_to_enu(
            df["dX"].to_numpy(),
            df["dY"].to_numpy(),
            df["dZ"].to_numpy(),
            latg, long
        )

        df["E_err"] = E
        df["N_err"] = N
        df["U_err"] = U
        df["Err_2D"] = np.hypot(E, N)
        df["Err_3D"] = np.sqrt(E*E + N*N + U*U)

        keep, filter_method = robust_mask(
            df[["E_err", "N_err", "U_err"]].to_numpy()
        )

        clean = df[keep].copy()

        raw_n = len(df)
        clean_n = len(clean)
        outlier_n = raw_n - clean_n
        outlier_pct = 100.0 * outlier_n / raw_n if raw_n else np.nan

        raw_stats = stats_block(df, "RAW")
        clean_stats = stats_block(clean, "CLEAN")

        status, reason = classify_solution_status(
            parse_status="OK",
            clean_n=clean_n,
            clean_rmse_3d=clean_stats["CLEAN_RMSE_3D_m"],
            clean_bias_u=clean_stats["CLEAN_Bias_U_m"],
        )

        # Contamination is a robustness descriptor only for usable solutions.
        # A parsed but statistically insufficient/catastrophic solution is FAILED;
        # assigning LOW/MODERATE/HIGH/EXTREME to such a solution would imply
        # unsupported robustness information (e.g., only a few retained epochs).
        if status == "FAILED":
            contamination_class = "NOT_APPLICABLE"
        else:
            contamination_class = classify_contamination(
                outlier_pct,
                parse_status="OK"
            )

        row = {
            "Product": product,
            "Test": test,
            "Receiver": receiver,
            "Receiver_ID": rid,
            "Receiver_Class": RECEIVER_CLASS.get(receiver, "Unknown"),

            "Solution_Status": status,
            "Status_Reason": reason,
            "Contamination_Class": contamination_class,

            "POS_File": str(path),
            "POS_Bytes": path.stat().st_size,
            "POS_Format": df["POS_Format"].iloc[0],

            "GT_Source": str(gt_source),
            "GT_X_m": xg,
            "GT_Y_m": yg,
            "GT_Z_m": zg,
            "GT_Lat_deg": latg,
            "GT_Lon_deg": long,
            "GT_h_m": hg,

            "Start_Epoch": df["Epoch"].min(),
            "End_Epoch": df["Epoch"].max(),
            "Duration_min": (
                (df["Epoch"].max() - df["Epoch"].min()).total_seconds() / 60.0
                if len(df) > 1 else 0.0
            ),

            "Filter_Method": filter_method,
            "Outlier_N": outlier_n,
            "Outlier_pct": outlier_pct,
            "Retention_pct": 100.0 * clean_n / raw_n if raw_n else np.nan,
        }

        row.update(raw_stats)
        row.update(clean_stats)

        row["Delta_RMSE_2D_RAW_minus_CLEAN_m"] = (
            raw_stats["RAW_RMSE_2D_m"] - clean_stats["CLEAN_RMSE_2D_m"]
        )
        row["Delta_RMSE_3D_RAW_minus_CLEAN_m"] = (
            raw_stats["RAW_RMSE_3D_m"] - clean_stats["CLEAN_RMSE_3D_m"]
        )

        row["RMSE_2D_Reduction_pct"] = (
            100.0 * row["Delta_RMSE_2D_RAW_minus_CLEAN_m"] /
            raw_stats["RAW_RMSE_2D_m"]
            if np.isfinite(raw_stats["RAW_RMSE_2D_m"]) and
               raw_stats["RAW_RMSE_2D_m"] != 0 else np.nan
        )
        row["RMSE_3D_Reduction_pct"] = (
            100.0 * row["Delta_RMSE_3D_RAW_minus_CLEAN_m"] /
            raw_stats["RAW_RMSE_3D_m"]
            if np.isfinite(raw_stats["RAW_RMSE_3D_m"]) and
               raw_stats["RAW_RMSE_3D_m"] != 0 else np.nan
        )

        result_rows.append(row)

        audit.update({
            "Parse_Status": "OK",
            "Raw_N": raw_n,
            "Clean_N": clean_n,
            "Outlier_N": outlier_n,
            "Outlier_pct": outlier_pct,
            "Solution_Status": status,
            "Status_Reason": reason,
            "Contamination_Class": contamination_class,
            "Filter_Method": filter_method,
            "RAW_RMSE_2D_m": raw_stats["RAW_RMSE_2D_m"],
            "RAW_RMSE_3D_m": raw_stats["RAW_RMSE_3D_m"],
            "CLEAN_RMSE_2D_m": clean_stats["CLEAN_RMSE_2D_m"],
            "CLEAN_RMSE_3D_m": clean_stats["CLEAN_RMSE_3D_m"],
        })
        audit_rows.append(audit)

        print(
            f"[{i+1:02d}/72] "
            f"{product:6s} {test:6s} {receiver:16s} "
            f"{status:6s} "
            f"{contamination_class:8s} "
            f"N={raw_n:5d}->{clean_n:5d} "
            f"out={outlier_pct:6.2f}% "
            f"RAW2D={raw_stats['RAW_RMSE_2D_m']:7.3f} "
            f"CLN2D={clean_stats['CLEAN_RMSE_2D_m']:7.3f} "
            f"CLN3D={clean_stats['CLEAN_RMSE_3D_m']:7.3f}"
        )

    results = pd.DataFrame(result_rows)
    audit = pd.DataFrame(audit_rows)

    # -----------------------------------------------------------------
    # Product / receiver summaries under two-axis QC
    # -----------------------------------------------------------------
    usable = (
        results[results["Solution_Status"] == "USABLE"].copy()
        if not results.empty else pd.DataFrame()
    )

    # Product summary
    product_rows = []

    for product in PRODUCTS:
        a = audit[audit["Product"] == product].copy()
        u = usable[usable["Product"] == product].copy() if not usable.empty else pd.DataFrame()

        product_rows.append({
            "Product": product,
            "Expected_N": len(a),
            "USABLE_N": int((a["Solution_Status"] == "USABLE").sum()),
            "FAILED_N": int((a["Solution_Status"] == "FAILED").sum()),
            "Solution_Success_pct":
                100.0 * (a["Solution_Status"] == "USABLE").mean(),

            "LOW_N": int((a["Contamination_Class"] == "LOW").sum()),
            "MODERATE_N": int((a["Contamination_Class"] == "MODERATE").sum()),
            "HIGH_N": int((a["Contamination_Class"] == "HIGH").sum()),
            "EXTREME_N": int((a["Contamination_Class"] == "EXTREME").sum()),

            "Median_Outlier_pct_USABLE":
                u["Outlier_pct"].median() if len(u) else np.nan,

            "Median_RAW_RMSE_2D_m_USABLE":
                u["RAW_RMSE_2D_m"].median() if len(u) else np.nan,
            "Median_CLEAN_RMSE_2D_m_USABLE":
                u["CLEAN_RMSE_2D_m"].median() if len(u) else np.nan,

            "Median_RAW_RMSE_3D_m_USABLE":
                u["RAW_RMSE_3D_m"].median() if len(u) else np.nan,
            "Median_CLEAN_RMSE_3D_m_USABLE":
                u["CLEAN_RMSE_3D_m"].median() if len(u) else np.nan,

            "Median_CLEAN_Bias_E_m_USABLE":
                u["CLEAN_Bias_E_m"].median() if len(u) else np.nan,
            "Median_CLEAN_Bias_N_m_USABLE":
                u["CLEAN_Bias_N_m"].median() if len(u) else np.nan,
            "Median_CLEAN_Bias_U_m_USABLE":
                u["CLEAN_Bias_U_m"].median() if len(u) else np.nan,

            "Median_RMSE_2D_Reduction_pct_USABLE":
                u["RMSE_2D_Reduction_pct"].median() if len(u) else np.nan,
            "Median_RMSE_3D_Reduction_pct_USABLE":
                u["RMSE_3D_Reduction_pct"].median() if len(u) else np.nan,
        })

    product_summary = pd.DataFrame(product_rows)

    # Receiver-class summary — IMPORTANT: availability denominator comes from
    # the expected 72-run audit, not only from successfully parsed RESULTS.
    receiver_rows = []

    for rclass in ["Geodetic", "OEM", "Smartphone"]:
        aa = audit[audit["Receiver"].map(RECEIVER_CLASS).fillna("Unknown") == rclass].copy()
        a = results[results["Receiver_Class"] == rclass].copy() if not results.empty else pd.DataFrame()
        u = a[a["Solution_Status"] == "USABLE"].copy() if len(a) else pd.DataFrame()

        receiver_rows.append({
            "Receiver_Class": rclass,
            "Expected_N": len(aa),
            "Parsed_N": len(a),
            "USABLE_N": int((aa["Solution_Status"] == "USABLE").sum()) if len(aa) else 0,
            "FAILED_N": int((aa["Solution_Status"] == "FAILED").sum()) if len(aa) else 0,
            "Solution_Success_pct": 100.0 * (aa["Solution_Status"] == "USABLE").mean() if len(aa) else np.nan,
            "LOW_N": int((aa["Contamination_Class"] == "LOW").sum()) if len(aa) else 0,
            "MODERATE_N": int((aa["Contamination_Class"] == "MODERATE").sum()) if len(aa) else 0,
            "HIGH_N": int((aa["Contamination_Class"] == "HIGH").sum()) if len(aa) else 0,
            "EXTREME_N": int((aa["Contamination_Class"] == "EXTREME").sum()) if len(aa) else 0,
            "Median_Outlier_pct_USABLE": u["Outlier_pct"].median() if len(u) else np.nan,
            "Median_RAW_RMSE_2D_m_USABLE": u["RAW_RMSE_2D_m"].median() if len(u) else np.nan,
            "Median_CLEAN_RMSE_2D_m_USABLE": u["CLEAN_RMSE_2D_m"].median() if len(u) else np.nan,
            "Median_RAW_RMSE_3D_m_USABLE": u["RAW_RMSE_3D_m"].median() if len(u) else np.nan,
            "Median_CLEAN_RMSE_3D_m_USABLE": u["CLEAN_RMSE_3D_m"].median() if len(u) else np.nan,
            "Median_Abs_CLEAN_Bias_E_m_USABLE": u["CLEAN_Bias_E_m"].abs().median() if len(u) else np.nan,
            "Median_Abs_CLEAN_Bias_N_m_USABLE": u["CLEAN_Bias_N_m"].abs().median() if len(u) else np.nan,
            "Median_Abs_CLEAN_Bias_U_m_USABLE": u["CLEAN_Bias_U_m"].abs().median() if len(u) else np.nan,
        })

    receiver_summary = pd.DataFrame(receiver_rows)

    # Product x receiver-class interaction table
    interaction_rows = []

    for product in PRODUCTS:
        for rclass in ["Geodetic", "OEM", "Smartphone"]:
            a = results[
                (results["Product"] == product) &
                (results["Receiver_Class"] == rclass)
            ].copy() if not results.empty else pd.DataFrame()

            # Use audit to include missing/empty expected runs in success rate.
            aa = audit[
                (audit["Product"] == product) &
                (audit["Receiver"].map(RECEIVER_CLASS).fillna("Unknown") == rclass)
            ].copy()

            u = a[a["Solution_Status"] == "USABLE"].copy() if len(a) else pd.DataFrame()

            interaction_rows.append({
                "Product": product,
                "Receiver_Class": rclass,

                "Expected_N": len(aa),
                "USABLE_N": int((aa["Solution_Status"] == "USABLE").sum()) if len(aa) else 0,
                "FAILED_N": int((aa["Solution_Status"] == "FAILED").sum()) if len(aa) else 0,
                "Solution_Success_pct":
                    100.0 * (aa["Solution_Status"] == "USABLE").mean() if len(aa) else np.nan,

                "LOW_N": int((aa["Contamination_Class"] == "LOW").sum()) if len(aa) else 0,
                "MODERATE_N": int((aa["Contamination_Class"] == "MODERATE").sum()) if len(aa) else 0,
                "HIGH_N": int((aa["Contamination_Class"] == "HIGH").sum()) if len(aa) else 0,
                "EXTREME_N": int((aa["Contamination_Class"] == "EXTREME").sum()) if len(aa) else 0,

                "Median_Outlier_pct_USABLE":
                    u["Outlier_pct"].median() if len(u) else np.nan,

                "Median_RAW_RMSE_2D_m_USABLE":
                    u["RAW_RMSE_2D_m"].median() if len(u) else np.nan,
                "Median_CLEAN_RMSE_2D_m_USABLE":
                    u["CLEAN_RMSE_2D_m"].median() if len(u) else np.nan,

                "Median_RAW_RMSE_3D_m_USABLE":
                    u["RAW_RMSE_3D_m"].median() if len(u) else np.nan,
                "Median_CLEAN_RMSE_3D_m_USABLE":
                    u["CLEAN_RMSE_3D_m"].median() if len(u) else np.nan,

                "Median_CLEAN_Bias_E_m_USABLE":
                    u["CLEAN_Bias_E_m"].median() if len(u) else np.nan,
                "Median_CLEAN_Bias_N_m_USABLE":
                    u["CLEAN_Bias_N_m"].median() if len(u) else np.nan,
                "Median_CLEAN_Bias_U_m_USABLE":
                    u["CLEAN_Bias_U_m"].median() if len(u) else np.nan,

                "Median_RMSE_2D_Reduction_pct_USABLE":
                    u["RMSE_2D_Reduction_pct"].median() if len(u) else np.nan,
            })

    interaction_summary = pd.DataFrame(interaction_rows)

    # -----------------------------------------------------------------
    # PAPER-READY Product x Receiver table
    # Availability, accuracy and contamination are deliberately separated.
    # -----------------------------------------------------------------
    paper_rows = []
    for product in PRODUCTS:
        for rclass in ["Geodetic", "OEM", "Smartphone"]:
            aa = audit[(audit["Product"] == product) &
                       (audit["Receiver"].map(RECEIVER_CLASS).fillna("Unknown") == rclass)].copy()
            u = usable[(usable["Product"] == product) &
                       (usable["Receiver_Class"] == rclass)].copy() if not usable.empty else pd.DataFrame()
            paper_rows.append({
                "Product": product, "Receiver_Class": rclass,
                "Expected_N": len(aa),
                "Usable_N": int((aa["Solution_Status"] == "USABLE").sum()) if len(aa) else 0,
                "Failed_N": int((aa["Solution_Status"] == "FAILED").sum()) if len(aa) else 0,
                "Success_pct": 100.0*(aa["Solution_Status"] == "USABLE").mean() if len(aa) else np.nan,
                "Median_RAW_RMSE_2D_m": u["RAW_RMSE_2D_m"].median() if len(u) else np.nan,
                "Median_CLEAN_RMSE_2D_m": u["CLEAN_RMSE_2D_m"].median() if len(u) else np.nan,
                "Median_CLEAN_RMSE_3D_m": u["CLEAN_RMSE_3D_m"].median() if len(u) else np.nan,
                "Median_Abs_Bias_E_m": u["CLEAN_Bias_E_m"].abs().median() if len(u) else np.nan,
                "Median_Abs_Bias_N_m": u["CLEAN_Bias_N_m"].abs().median() if len(u) else np.nan,
                "Median_Abs_Bias_U_m": u["CLEAN_Bias_U_m"].abs().median() if len(u) else np.nan,
                "Median_Contamination_pct": u["Outlier_pct"].median() if len(u) else np.nan,
                "LOW_N": int((aa["Contamination_Class"] == "LOW").sum()) if len(aa) else 0,
                "MODERATE_N": int((aa["Contamination_Class"] == "MODERATE").sum()) if len(aa) else 0,
                "HIGH_N": int((aa["Contamination_Class"] == "HIGH").sum()) if len(aa) else 0,
                "EXTREME_N": int((aa["Contamination_Class"] == "EXTREME").sum()) if len(aa) else 0,
            })
    paper_summary = pd.DataFrame(paper_rows)

    # -----------------------------------------------------------------
    # Test-to-test repeatability / consistency.
    # For each Product x Receiver_ID-family, summarize the spread of test-level
    # CLEAN RMSE and biases. Smartphone-1 and Smartphone-2 remain separate.
    # -----------------------------------------------------------------
    repeat_rows = []
    if not usable.empty:
        for (product, receiver), g in usable.groupby(["Product", "Receiver"], dropna=False):
            vals2 = g["CLEAN_RMSE_2D_m"].dropna()
            vals3 = g["CLEAN_RMSE_3D_m"].dropna()
            repeat_rows.append({
                "Product": product,
                "Receiver": receiver,
                "Receiver_Class": RECEIVER_CLASS.get(receiver, "Unknown"),
                "Usable_Test_N": len(g),
                "Tests": ";".join(sorted(g["Test"].astype(str).unique())),
                "Mean_CLEAN_RMSE_2D_m": vals2.mean() if len(vals2) else np.nan,
                "SD_CLEAN_RMSE_2D_m": vals2.std(ddof=1) if len(vals2)>1 else np.nan,
                "Range_CLEAN_RMSE_2D_m": vals2.max()-vals2.min() if len(vals2)>1 else np.nan,
                "CV_CLEAN_RMSE_2D_pct": 100.0*vals2.std(ddof=1)/vals2.mean() if len(vals2)>1 and vals2.mean()!=0 else np.nan,
                "Mean_CLEAN_RMSE_3D_m": vals3.mean() if len(vals3) else np.nan,
                "SD_CLEAN_RMSE_3D_m": vals3.std(ddof=1) if len(vals3)>1 else np.nan,
                "Range_CLEAN_RMSE_3D_m": vals3.max()-vals3.min() if len(vals3)>1 else np.nan,
                "SD_Bias_E_m": g["CLEAN_Bias_E_m"].std(ddof=1) if len(g)>1 else np.nan,
                "SD_Bias_N_m": g["CLEAN_Bias_N_m"].std(ddof=1) if len(g)>1 else np.nan,
                "SD_Bias_U_m": g["CLEAN_Bias_U_m"].std(ddof=1) if len(g)>1 else np.nan,
                "Median_Contamination_pct": g["Outlier_pct"].median(),
            })
    repeatability = pd.DataFrame(repeat_rows)

    # -----------------------------------------------------------------
    # Test-level paper table: preserves all usable individual solutions.
    # -----------------------------------------------------------------
    cols = [
        "Product","Test","Receiver","Receiver_Class","Solution_Status",
        "Contamination_Class","RAW_N","CLEAN_N","Outlier_pct",
        "RAW_RMSE_2D_m","CLEAN_RMSE_2D_m","CLEAN_RMSE_3D_m",
        "CLEAN_Bias_E_m","CLEAN_Bias_N_m","CLEAN_Bias_U_m",
        "CLEAN_P95_2D_m","CLEAN_P95_3D_m"
    ]
    paper_test_level = results[[c for c in cols if c in results.columns]].copy() if not results.empty else pd.DataFrame()

    status_summary = (
        audit.groupby(
            ["Product", "Solution_Status", "Contamination_Class"],
            dropna=False
        )
        .size()
        .reset_index(name="N")
    )

    # -----------------------------------------------------------------
    # Export
    # -----------------------------------------------------------------
    results_csv = OUT_DIR / "GNSS_POS_STATISTICS_V1_5_1_1.csv"
    audit_csv = OUT_DIR / "GNSS_POS_PROCESSING_AUDIT_V1_5_1.csv"
    status_csv = OUT_DIR / "GNSS_POS_STATUS_SUMMARY_V1_5_1.csv"
    product_csv = OUT_DIR / "GNSS_POS_PRODUCT_SUMMARY_V1_5_1.csv"
    receiver_csv = OUT_DIR / "GNSS_POS_RECEIVER_SUMMARY_V1_5_1.csv"
    interaction_csv = OUT_DIR / "GNSS_POS_PRODUCT_RECEIVER_INTERACTION_V1_5_1.csv"
    paper_csv = OUT_DIR / "GNSS_POS_PAPER_TABLE_PRODUCT_RECEIVER_V1_5_1.csv"
    repeat_csv = OUT_DIR / "GNSS_POS_TEST_REPEATABILITY_V1_5_1.csv"
    testlevel_csv = OUT_DIR / "GNSS_POS_PAPER_TABLE_TEST_LEVEL_V1_5_1.csv"
    xlsx = OUT_DIR / "GNSS_POS_STATISTICS_V1_5_1_1.xlsx"

    results.to_csv(results_csv, index=False, encoding="utf-8-sig")
    audit.to_csv(audit_csv, index=False, encoding="utf-8-sig")
    status_summary.to_csv(status_csv, index=False, encoding="utf-8-sig")
    product_summary.to_csv(product_csv, index=False, encoding="utf-8-sig")
    receiver_summary.to_csv(receiver_csv, index=False, encoding="utf-8-sig")
    interaction_summary.to_csv(interaction_csv, index=False, encoding="utf-8-sig")
    paper_summary.to_csv(paper_csv, index=False, encoding="utf-8-sig")
    repeatability.to_csv(repeat_csv, index=False, encoding="utf-8-sig")
    paper_test_level.to_csv(testlevel_csv, index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
        results.to_excel(writer, sheet_name="RESULTS_RAW_CLEAN", index=False)
        audit.to_excel(writer, sheet_name="PROCESSING_AUDIT", index=False)
        status_summary.to_excel(writer, sheet_name="STATUS_SUMMARY", index=False)
        product_summary.to_excel(writer, sheet_name="PRODUCT_SUMMARY", index=False)
        receiver_summary.to_excel(writer, sheet_name="RECEIVER_SUMMARY", index=False)
        interaction_summary.to_excel(writer, sheet_name="PRODUCT_X_RECEIVER", index=False)
        paper_summary.to_excel(writer, sheet_name="PAPER_PRODUCT_RECEIVER", index=False)
        repeatability.to_excel(writer, sheet_name="TEST_REPEATABILITY", index=False)
        paper_test_level.to_excel(writer, sheet_name="PAPER_TEST_LEVEL", index=False)
        expected.to_excel(writer, sheet_name="EXPECTED_72", index=False)
        gt.to_excel(writer, sheet_name="GROUND_TRUTH", index=False)

    # -----------------------------------------------------------------
    # Console final summary
    # -----------------------------------------------------------------
    print("\n" + "=" * 132)
    print("FINAL PROCESSING AUDIT")
    print("=" * 132)

    print(f"Expected       : {len(expected)}")
    print(f"USABLE         : {(audit['Solution_Status']=='USABLE').sum()}")
    print(f"FAILED         : {(audit['Solution_Status']=='FAILED').sum()}")
    print(f"Total audited  : {len(audit)}")

    print("\nCONTAMINATION CLASSES")
    for cls in ["LOW", "MODERATE", "HIGH", "EXTREME", "NOT_APPLICABLE"]:
        print(f"{cls:14s}: {(audit['Contamination_Class']==cls).sum()}")

    print("\nFAILED SOLUTIONS")
    failed = audit[audit["Solution_Status"] == "FAILED"]
    if len(failed):
        print(
            failed[
                ["Product", "Test", "Receiver", "Receiver_ID",
                 "Parse_Status", "Raw_N", "Clean_N", "Status_Reason"]
            ].to_string(index=False)
        )
    else:
        print("None")

    print("\nPRODUCT SUMMARY")
    with pd.option_context(
        "display.width", 220,
        "display.max_columns", 30,
        "display.float_format", lambda x: f"{x:.4f}"
    ):
        print(product_summary.to_string(index=False))

    print("\nPRODUCT x RECEIVER-CLASS SUMMARY")
    with pd.option_context(
        "display.width", 240,
        "display.max_columns", 40,
        "display.float_format", lambda x: f"{x:.4f}"
    ):
        print(interaction_summary.to_string(index=False))

    print("\nPAPER-READY PRODUCT x RECEIVER TABLE")
    with pd.option_context("display.width", 260, "display.max_columns", 40,
                           "display.float_format", lambda x: f"{x:.4f}"):
        print(paper_summary.to_string(index=False))

    print("\nOUTPUT FILES")
    for p in [
        results_csv, audit_csv, status_csv,
        product_csv, receiver_csv, interaction_csv,
        paper_csv, repeat_csv, testlevel_csv, xlsx
    ]:
        print(p)

    print("\nSCIENTIFIC INTERPRETATION RULE:")
    print(
        "Primary accuracy comparisons should use USABLE solutions. "
        "Contamination class is reported independently and must not be "
        "interpreted as solution failure. FAILED solutions contribute to "
        "solution-success statistics but must not be averaged into product "
        "accuracy metrics."
    )


if __name__ == "__main__":
    main()
