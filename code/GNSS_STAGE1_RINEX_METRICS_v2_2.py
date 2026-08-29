# -*- coding: utf-8 -*-
r"""
GNSS_STAGE1_RINEX_METRICS_v2_2.py

Publication-grade Stage-1 extractor for the Sensors manuscript.

PURPOSE
-------
Recompute the canonical Stage-1 observation-quality metrics DIRECTLY from
the 12 original RINEX observation files under:

    C:\IEEE\RAW_DATA\Test1
    C:\IEEE\RAW_DATA\Test2
    C:\IEEE\RAW_DATA\Test3

No previous QC/CMC/observation-analysis output folders are scanned.

ANALYSIS UNIT
-------------
Exactly one row per Test × Receiver dataset (12 rows total).

FINAL SCIENTIFIC METRIC SET
---------------------------
10 CORE METRICS
1.  CN0_Median_dBHz
2.  CN0_RobustSigma_dB
3.  GPS_L1_CMC_RobustSigma_m
4.  GPS_L1_CMC_P95Abs_m
5.  PhaseDiscontinuity_Rate_per1000
6.  Median_PhaseArc_Length_s
7.  Epoch_Retention_pct
8.  Observation_Completeness_pct
9.  Median_Usable_Satellites
10. MultiFrequency_Availability_pct

2 SECONDARY METRICS
11. Signal_Diversity_Count
12. GPS_L5_CMC_RobustSigma_m

DIAGNOSTIC-ONLY (NOT CORE INFERENCE)
------------------------------------
- LLI_FlagRate_per1000
- CodePhase_Continuity_Ratio_pct
- AllGNSS_CMC_RobustSigma_m / P95
- GPS_L5_CMC_P95Abs_m

HARMONIZED DEFINITIONS
----------------------
A) C/N0
   All valid RINEX S-observations are pooled at dataset level.

       Median = median(S)
       RobustSigma = 1.4826 * MAD(S)

B) CMC -- final common-signal definition
   For matched pseudorange and carrier phase:

       CMC(t) = P(t) - lambda * L(t)      [m]

   Arcs are segmented by data gaps and robust carrier-phase jumps; receiver
   LLI flags are NOT used to define the scientific phase arcs. Within every
   accepted segment:

       CMC_detrended(t) = CMC(t) - median_segment(CMC)

   The PRIMARY CMC metrics are restricted to GPS L1 matched signal families
   so receiver comparisons are made in a common constellation/frequency
   domain rather than being confounded by different GNSS signal mixtures.

   GPS L5 is retained as a secondary metric when coverage exists.
   All-GNSS pooled CMC is exported for diagnostic use only.

C) Carrier-discontinuity indicators
   The FINAL core discontinuity metric is receiver-LLI-independent:

       PhaseDiscontinuity_Rate_per1000
       = 1000 * N_robust_phase_jumps / N_valid_phase_transitions

   RINEX LLI bit-0 is retained separately as LLI_FlagRate_per1000 for
   diagnostic interpretation only. This prevents receiver-specific LLI
   encoding behavior from dominating the scientific continuity metric.

   The robust phase-jump indicator is a single-frequency discontinuity
   diagnostic; it is not claimed to be a full geometry-free/Melbourne-Wubbena
   cycle-slip detector.

D) Carrier-phase arcs
   Scientific phase arcs are broken by:
       - a temporal data gap, or
       - a robust carrier-phase jump.

   Receiver LLI flags are NOT used to segment the final scientific arc metric.
   Median_PhaseArc_Length_s is the median duration of these harmonized arcs.

E) Epoch retention
       observed epochs / expected epochs * 100

   Expected epochs are derived from FIRST/LAST observed epoch and:
       header INTERVAL, if valid;
       otherwise robust median epoch interval.

F) Observation completeness
   Only declared CODE + PHASE observables are considered.
   For every observed satellite epoch:

       completeness =
       number of non-missing declared C/P observation values
       ----------------------------------------------------- * 100
       number of declared C/P observation slots

G) Usable satellite
   A satellite is "usable" at an epoch if it contains at least one matched
   signal family with BOTH valid code and phase.

H) Code/phase continuity ratio
   Across matched signal families:

       100 * N_simultaneous_valid_code_and_phase / N_valid_code

   This is bounded to [0,100] by construction and measures the fraction of
   valid code observations for which a simultaneous valid carrier phase exists.

I) Signal diversity
   Number of distinct constellation + signal families with matched C/L and
   at least MIN_SIGNAL_PAIR_OBS valid simultaneous code-phase observations.

J) Multi-frequency availability
   Among epoch-satellite instances with at least one usable code-phase band:

       percentage having >= 2 distinct usable frequency bands.

SUPPORTED RINEX
---------------
- RINEX 3 observation files
- RINEX 2 observation files (best-effort harmonized support)

OUTPUT
------
C:\IEEE\GNSS_ANALYSIS\STAGE1_RINEX_V2_2\
    GNSS_STAGE1_FINAL_METRICS.csv
    GNSS_STAGE1_FINAL_METRICS.xlsx
    GNSS_STAGE1_RINEX_PARSER_QC.csv
    GNSS_STAGE1_SIGNAL_PAIR_INVENTORY.csv
    GNSS_STAGE1_PHASE_ARC_SUMMARY.csv
    GNSS_STAGE1_CMC_SUMMARY.csv
    GNSS_STAGE1_METRIC_DEFINITIONS.csv
    GNSS_STAGE1_STANDARDIZED_PROFILE.csv

NOTES
-----
- Missing metrics remain NaN; no imputation is performed.
- The standardized profile is visualization-only.
- Statistics used for inference must use the physical metric values.
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass
from collections import defaultdict, Counter
from datetime import datetime, timedelta
import math
import re
import time
import warnings

import numpy as np
import pandas as pd


# ======================================================================
# CONFIGURATION
# ======================================================================

ROOT = Path(r"C:\IEEE")
RAW_ROOT = ROOT / "RAW_DATA"
OUT_DIR = ROOT / "GNSS_ANALYSIS" / "STAGE1_RINEX_V2_2"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TEST_DIRS = {
    "Test-1": RAW_ROOT / "Test1",
    "Test-2": RAW_ROOT / "Test2",
    "Test-3": RAW_ROOT / "Test3",
}

# Canonical raw RINEX basenames.
# A flexible discovery fallback is also implemented.
DATASETS = {
    "Test-1": {
        "CHC1": ("CHC I80", "C1", "Geodetic"),
        "OEM1": ("TRIMBLE OEM MB2", "OEM1", "OEM"),
        "T11":  ("XIAOMI-1", "T11", "Smartphone"),
        "T21":  ("XIAOMI-2", "T21", "Smartphone"),
    },
    "Test-2": {
        "CHC2": ("CHC I80", "C2", "Geodetic"),
        "OEM2": ("TRIMBLE OEM MB2", "OEM2", "OEM"),
        "T12":  ("XIAOMI-1", "T12", "Smartphone"),
        "T22":  ("XIAOMI-2", "T22", "Smartphone"),
    },
    "Test-3": {
        "CHC3": ("CHC I80", "C3", "Geodetic"),
        "OEM3": ("TRIMBLE OEM MB2", "OEM3", "OEM"),
        "T13":  ("XIAOMI-1", "T13", "Smartphone"),
        "T23":  ("XIAOMI-2", "T23", "Smartphone"),
    },
}

SUPPORTED_EXTENSIONS = {
    ".23o", ".23O", ".obs", ".OBS", ".rnx", ".RNX", ".o", ".O"
}

# Arc/CMC controls
GAP_FACTOR = 3.0
ABSOLUTE_GAP_LIMIT_S = 5.0
MIN_ARC_POINTS = 10
MIN_ARC_DURATION_S = 5.0
MIN_SIGNAL_PAIR_OBS = 20

# Robust CMC cleaning / jump segmentation
CMC_JUMP_MAD_MULT = 8.0
CMC_MIN_JUMP_M = 20.0
CMC_MAX_ABS_RESIDUAL_M = 500.0
CMC_MIN_SEGMENT_POINTS = 8

# Robust phase-jump indicator
PHASE_JUMP_MAD_MULT = 10.0
PHASE_JUMP_MIN_CYCLES = 100.0

# Plausibility filters.
# These do NOT "improve" data; they reject physically impossible parser values.
CN0_MIN_DBHZ = 1.0
CN0_MAX_DBHZ = 80.0
CODE_MIN_M = 1.0e6
CODE_MAX_M = 6.0e7
PHASE_ABS_MAX_CYCLES = 1.0e10

# Speed / memory
PROGRESS_EVERY_EPOCHS = 2000

C_LIGHT = 299792458.0


# ======================================================================
# FREQUENCY MODEL
# ======================================================================

# Carrier frequencies [Hz] by constellation and RINEX frequency digit.
# GLONASS FDMA requires channel-specific frequencies and is intentionally
# excluded from CMC unless a reliable channel number is available.
FREQ_HZ = {
    "G": {  # GPS
        "1": 1575.42e6,
        "2": 1227.60e6,
        "5": 1176.45e6,
    },
    "E": {  # Galileo
        "1": 1575.42e6,
        "5": 1176.45e6,  # E5a
        "7": 1207.14e6,  # E5b
        "8": 1191.795e6, # E5 AltBOC
        "6": 1278.75e6,  # E6
    },
    "C": {  # BeiDou (RINEX convention, practical mapping)
        "1": 1575.42e6,  # B1C
        "2": 1561.098e6, # B1I
        "5": 1176.45e6,  # B2a
        "6": 1268.52e6,  # B3I
        "7": 1207.14e6,  # B2I/B2b
        "8": 1191.795e6, # B2ab
    },
    "J": {  # QZSS
        "1": 1575.42e6,
        "2": 1227.60e6,
        "5": 1176.45e6,
        "6": 1278.75e6,
    },
    "I": {  # NavIC / IRNSS
        "5": 1176.45e6,
        "9": 2492.028e6,
    },
    "S": {  # SBAS
        "1": 1575.42e6,
        "5": 1176.45e6,
    },
}

# RINEX 2 global types are ambiguous in tracking attribute.
# These mappings are used only for band matching.
RINEX2_BAND_MAP = {
    "C1": "1", "P1": "1", "L1": "1", "S1": "1", "D1": "1",
    "C2": "2", "P2": "2", "L2": "2", "S2": "2", "D2": "2",
    "C5": "5", "P5": "5", "L5": "5", "S5": "5", "D5": "5",
    "C6": "6", "P6": "6", "L6": "6", "S6": "6", "D6": "6",
    "C7": "7", "P7": "7", "L7": "7", "S7": "7", "D7": "7",
    "C8": "8", "P8": "8", "L8": "8", "S8": "8", "D8": "8",
}


# ======================================================================
# BASIC HELPERS
# ======================================================================

def finite(values):
    if values is None:
        return np.asarray([], dtype=float)
    x = pd.to_numeric(pd.Series(list(values)), errors="coerce").to_numpy(float)
    return x[np.isfinite(x)]


def robust_sigma(values):
    x = finite(values)
    if len(x) < 2:
        return np.nan
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    return float(1.4826 * mad)


def p95_abs(values):
    x = finite(values)
    if len(x) == 0:
        return np.nan
    return float(np.percentile(np.abs(x), 95))


def safe_median(values):
    x = finite(values)
    return float(np.median(x)) if len(x) else np.nan


def safe_mean(values):
    x = finite(values)
    return float(np.mean(x)) if len(x) else np.nan


def parse_float(field):
    try:
        s = field.strip()
        return float(s) if s else np.nan
    except Exception:
        return np.nan


def parse_int_char(ch):
    try:
        return int(ch) if str(ch).strip() else 0
    except Exception:
        return 0


def normalize_sat(sat):
    sat = str(sat).strip().upper()
    if len(sat) == 2 and sat.isdigit():
        return "G" + sat
    if len(sat) == 3 and sat[0].isalpha():
        return sat
    return sat


def signal_family(obs_type, rinex_major):
    """
    Return a harmonized signal-family key.

    RINEX3:
      C1C / L1C -> family "1C"
      C5Q / L5Q -> family "5Q"

    RINEX2:
      C1/P1/L1 -> family "1"
      C2/P2/L2 -> family "2"
    """
    o = str(obs_type).strip().upper()

    if rinex_major >= 3:
        if len(o) >= 2 and o[0] in "CPLDS":
            return o[1:]
        return None

    # RINEX2
    if o in RINEX2_BAND_MAP:
        return RINEX2_BAND_MAP[o]

    if len(o) >= 2 and o[0] in "CPLDS" and o[1].isdigit():
        return o[1]

    return None


def frequency_band(obs_type, rinex_major):
    fam = signal_family(obs_type, rinex_major)
    if not fam:
        return None
    return fam[0] if fam[0].isdigit() else None


def wavelength(system, obs_type, rinex_major):
    band = frequency_band(obs_type, rinex_major)
    if not band:
        return np.nan

    f = FREQ_HZ.get(system, {}).get(band)

    if not f:
        return np.nan

    return C_LIGHT / f



# ======================================================================
# ROBUST SEGMENTATION HELPERS
# ======================================================================

def robust_mad_threshold(values, mad_mult, absolute_floor):
    """
    Return median and robust threshold based on first differences.
    """
    x = finite(values)
    if len(x) < 3:
        return np.nan, absolute_floor

    med = np.median(x)
    sigma = robust_sigma(x)

    if not np.isfinite(sigma) or sigma <= 0:
        return med, absolute_floor

    return med, max(absolute_floor, mad_mult * sigma)


def split_indices_by_jump(values, mad_mult, absolute_floor):
    """
    Split a 1-D series when consecutive differences exceed a robust threshold.
    Returns inclusive-exclusive index segments.
    """
    x = np.asarray(values, float)

    if len(x) <= 1:
        return [(0, len(x))]

    d = np.diff(x)
    med, thr = robust_mad_threshold(d, mad_mult, absolute_floor)

    if not np.isfinite(med):
        return [(0, len(x))]

    cut_after = np.where(np.abs(d - med) > thr)[0]

    starts = [0]
    ends = []

    for idx in cut_after:
        ends.append(idx + 1)
        starts.append(idx + 1)

    ends.append(len(x))

    return [(s, e) for s, e in zip(starts, ends) if e > s]


# ======================================================================
# DATA STRUCTURES
# ======================================================================

@dataclass
class ObsValue:
    value: float
    lli: int
    ssi: int


@dataclass
class EpochRecord:
    time: datetime
    sats: dict  # sat -> {obs_type: ObsValue}


@dataclass
class RinexHeader:
    version: float
    major: int
    interval: float
    obs_types_by_system: dict
    approx_xyz: tuple | None
    antenna_delta_hen: tuple | None
    marker_name: str
    receiver_type: str
    antenna_type: str


# ======================================================================
# RINEX FILE DISCOVERY
# ======================================================================

def discover_rinex(test, base):
    folder = TEST_DIRS[test]

    if not folder.exists():
        return None

    # Exact stem first.
    candidates = []

    for p in folder.iterdir():
        if not p.is_file():
            continue

        name_u = p.name.upper()
        stem_u = p.stem.upper()

        # Reject obvious navigation / generated files.
        if any(tok in name_u for tok in [
            "_EVENTS", ".POS", ".NAV", ".GNAV", ".HNAV", ".LNAV",
            "CORRECT", "OUTPUT"
        ]):
            continue

        if (
            stem_u == base.upper() or
            name_u.startswith(base.upper() + ".")
        ):
            candidates.append(p)

    if not candidates:
        # Flexible prefix fallback.
        for p in folder.iterdir():
            if not p.is_file():
                continue

            name_u = p.name.upper()

            if name_u.startswith(base.upper()):
                if any(tok in name_u for tok in [
                    "_EVENTS", ".POS", ".NAV", "CORRECT"
                ]):
                    continue
                candidates.append(p)

    if not candidates:
        return None

    # Prefer classic observation extensions.
    def score(p):
        n = p.name.upper()
        s = 0
        if re.search(r"\.\d{2}O$", n):
            s += 10
        if n.endswith(".OBS") or n.endswith(".RNX"):
            s += 8
        if "_EVENTS" in n:
            s -= 100
        return (-s, len(n), n)

    candidates.sort(key=score)
    return candidates[0]


# ======================================================================
# HEADER PARSER
# ======================================================================

def parse_header(lines):
    version = np.nan
    interval = np.nan
    obs_types_by_system = {}
    approx_xyz = None
    antenna_delta_hen = None
    marker_name = ""
    receiver_type = ""
    antenna_type = ""

    # Temporary accumulators for RINEX3 SYS / # / OBS TYPES
    sys_obs_acc = defaultdict(list)
    rinex2_obs = []
    rinex2_expected = None

    header_end_idx = None

    for i, line in enumerate(lines):
        label = line[60:80].strip() if len(line) >= 60 else ""

        if i == 0 and "RINEX VERSION / TYPE" in line:
            version = parse_float(line[:9])

        if label == "MARKER NAME":
            marker_name = line[:60].strip()

        elif label == "REC # / TYPE / VERS":
            receiver_type = line[20:40].strip()

        elif label == "ANT # / TYPE":
            antenna_type = line[20:40].strip()

        elif label == "APPROX POSITION XYZ":
            vals = line[:60].split()
            if len(vals) >= 3:
                try:
                    approx_xyz = tuple(map(float, vals[:3]))
                except Exception:
                    pass

        elif label == "ANTENNA: DELTA H/E/N":
            vals = line[:60].split()
            if len(vals) >= 3:
                try:
                    antenna_delta_hen = tuple(map(float, vals[:3]))
                except Exception:
                    pass

        elif label == "INTERVAL":
            v = parse_float(line[:10])
            if np.isfinite(v) and v > 0:
                interval = float(v)

        elif label == "SYS / # / OBS TYPES":
            system = line[0].strip()
            try:
                n = int(line[3:6])
            except Exception:
                n = None

            obs = line[7:60].split()

            if system:
                sys_obs_acc[system].extend(obs)

            # continuation lines may have blank system; infer last system
            elif sys_obs_acc:
                last_sys = list(sys_obs_acc.keys())[-1]
                sys_obs_acc[last_sys].extend(obs)

        elif label in {"# / TYPES OF OBSERV", "TYPES OF OBSERV"}:
            if rinex2_expected is None:
                try:
                    rinex2_expected = int(line[:6])
                except Exception:
                    rinex2_expected = None

            # RINEX2 observation type slots occupy cols 10:60 typically.
            obs = line[6:60].split()
            rinex2_obs.extend(obs)

        elif label == "END OF HEADER":
            header_end_idx = i
            break

    if header_end_idx is None:
        raise ValueError("END OF HEADER not found")

    major = int(version) if np.isfinite(version) else 0

    if major >= 3:
        obs_types_by_system = {
            sys: obs
            for sys, obs in sys_obs_acc.items()
        }
    else:
        # RINEX2 global obs types. Use '*' pseudo-system.
        if rinex2_expected:
            rinex2_obs = rinex2_obs[:rinex2_expected]
        obs_types_by_system = {"*": rinex2_obs}

    return (
        RinexHeader(
            version=float(version) if np.isfinite(version) else np.nan,
            major=major,
            interval=float(interval) if np.isfinite(interval) else np.nan,
            obs_types_by_system=obs_types_by_system,
            approx_xyz=approx_xyz,
            antenna_delta_hen=antenna_delta_hen,
            marker_name=marker_name,
            receiver_type=receiver_type,
            antenna_type=antenna_type,
        ),
        header_end_idx + 1,
    )


# ======================================================================
# OBSERVATION FIELD PARSING
# ======================================================================

def parse_obs_fields(text, obs_types):
    """
    Parse RINEX observation fields, 16 chars each:
      14-char value + 1-char LLI + 1-char SSI
    """
    out = {}

    needed = 16 * len(obs_types)

    if len(text) < needed:
        text = text.ljust(needed)

    for i, obs_type in enumerate(obs_types):
        field = text[i*16:(i+1)*16]

        if not field:
            out[obs_type] = ObsValue(np.nan, 0, 0)
            continue

        val = parse_float(field[:14])
        lli = parse_int_char(field[14:15])
        ssi = parse_int_char(field[15:16])

        out[obs_type] = ObsValue(val, lli, ssi)

    return out


# ======================================================================
# RINEX 3 BODY PARSER
# ======================================================================

def parse_rinex3(lines, start_idx, header):
    epochs = []
    i = start_idx

    while i < len(lines):
        line = lines[i]

        if not line.startswith(">"):
            i += 1
            continue

        # > yyyy mm dd hh mm ss.sssssss flag nsat ...
        toks = line[1:].split()

        if len(toks) < 8:
            i += 1
            continue

        try:
            year, month, day = map(int, toks[0:3])
            hour, minute = map(int, toks[3:5])
            secf = float(toks[5])
            flag = int(toks[6])
            nsat = int(toks[7])

            sec = int(math.floor(secf))
            micro = int(round((secf - sec) * 1e6))

            if micro >= 1000000:
                sec += 1
                micro -= 1000000

            epoch_time = datetime(
                year, month, day, hour, minute, sec, micro
            )
        except Exception:
            i += 1
            continue

        i += 1

        # Ignore special/event epochs except ordinary observation flags 0/1.
        if flag not in (0, 1):
            # Consume nominal nsat/event lines.
            i += max(nsat, 0)
            continue

        sats = {}

        sat_count = 0

        while sat_count < nsat and i < len(lines):
            first = lines[i]

            # If a malformed file jumps to next epoch early, stop safely.
            if first.startswith(">"):
                break

            sat = normalize_sat(first[:3])

            if len(sat) != 3 or not sat[0].isalpha():
                i += 1
                continue

            system = sat[0]
            obs_types = header.obs_types_by_system.get(system, [])

            if not obs_types:
                # Unknown system: still count one satellite line and move on.
                i += 1
                sat_count += 1
                continue

            # First line includes satellite ID in cols 1:3, obs starts at col 4.
            payload = first[3:].rstrip("\n")
            i += 1

            needed = 16 * len(obs_types)

            # RINEX3 continuation lines are typically indented.
            while len(payload) < needed and i < len(lines):
                nxt = lines[i]

                if nxt.startswith(">"):
                    break

                # A new satellite line has a nonblank system char in col 1.
                possible = normalize_sat(nxt[:3])

                if (
                    len(possible) == 3 and
                    possible[0].isalpha() and
                    possible != sat
                ):
                    break

                # Continuation obs content starts at col 4.
                payload += nxt[3:].rstrip("\n")
                i += 1

            sats[sat] = parse_obs_fields(payload, obs_types)
            sat_count += 1

        epochs.append(EpochRecord(epoch_time, sats))

    return epochs


# ======================================================================
# RINEX 2 BODY PARSER
# ======================================================================

def _rinex2_epoch_time(line):
    try:
        yy = int(line[1:3])
        year = 1900 + yy if yy >= 80 else 2000 + yy
        month = int(line[4:6])
        day = int(line[7:9])
        hour = int(line[10:12])
        minute = int(line[13:15])
        secf = float(line[15:26])

        sec = int(math.floor(secf))
        micro = int(round((secf - sec) * 1e6))

        if micro >= 1000000:
            sec += 1
            micro -= 1000000

        flag = int(line[28:29])
        nsat = int(line[29:32])

        return datetime(
            year, month, day, hour, minute, sec, micro
        ), flag, nsat
    except Exception:
        return None, None, None


def parse_rinex2(lines, start_idx, header):
    obs_types = header.obs_types_by_system.get("*", [])
    nobs = len(obs_types)
    obs_lines_per_sat = int(math.ceil(nobs / 5.0)) if nobs else 0

    epochs = []
    i = start_idx

    while i < len(lines):
        line = lines[i]

        epoch_time, flag, nsat = _rinex2_epoch_time(line)

        if epoch_time is None:
            i += 1
            continue

        # Satellite list starts col 33, up to 12 sats per epoch line.
        sat_text = line[32:68]
        sats_list = [
            normalize_sat(sat_text[j:j+3])
            for j in range(0, len(sat_text), 3)
            if sat_text[j:j+3].strip()
        ]

        i += 1

        while len(sats_list) < nsat and i < len(lines):
            cont = lines[i]
            more = cont[32:68]

            sats_list.extend([
                normalize_sat(more[j:j+3])
                for j in range(0, len(more), 3)
                if more[j:j+3].strip()
            ])

            i += 1

        sats_list = sats_list[:nsat]

        if flag not in (0, 1):
            # Event records may contain nsat special lines.
            i += max(nsat, 0)
            continue

        sats = {}

        for sat in sats_list:
            payload = ""

            for _ in range(obs_lines_per_sat):
                if i >= len(lines):
                    break
                payload += lines[i].rstrip("\n")
                i += 1

            sats[sat] = parse_obs_fields(payload, obs_types)

        epochs.append(EpochRecord(epoch_time, sats))

    return epochs


# ======================================================================
# FULL RINEX READ
# ======================================================================

def read_rinex(path):
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    header, start = parse_header(lines)

    if header.major >= 3:
        epochs = parse_rinex3(lines, start, header)
    else:
        epochs = parse_rinex2(lines, start, header)

    return header, epochs


# ======================================================================
# MATCHED CODE/PHASE/SNR SIGNAL PAIRS
# ======================================================================

def build_signal_pairs(header, observed_systems):
    """
    Return:
      system -> family -> dict(code=..., phase=..., snr=..., band=...)

    Pairing policy:
    - RINEX3: same full signal family after first char, e.g. C1C ↔ L1C.
      If exact tracking-code match is unavailable, same-band fallback is
      NOT used for CMC because it can mix different signal tracking modes.
    - RINEX2: same frequency band, preferring C over P pseudorange if both.
    """
    result = {}

    systems = observed_systems or set(header.obs_types_by_system.keys())

    for system in systems:
        obs_types = (
            header.obs_types_by_system.get(system, [])
            if header.major >= 3
            else header.obs_types_by_system.get("*", [])
        )

        fams = defaultdict(dict)

        for obs in obs_types:
            o = obs.upper()
            if not o:
                continue

            kind = o[0]
            fam = signal_family(o, header.major)

            if not fam:
                continue

            if kind in {"C", "P"}:
                # Prefer C over P when both map to same RINEX2 band.
                if "code" not in fams[fam] or kind == "C":
                    fams[fam]["code"] = o

            elif kind == "L":
                fams[fam]["phase"] = o

            elif kind == "S":
                fams[fam]["snr"] = o

            fams[fam]["band"] = frequency_band(o, header.major)

        result[system] = {
            fam: d
            for fam, d in fams.items()
            if "code" in d and "phase" in d
        }

    return result


# ======================================================================
# METRIC EXTRACTION
# ======================================================================

def analyze_dataset(
    test,
    receiver,
    receiver_id,
    receiver_class,
    path,
    header,
    epochs,
):
    if not epochs:
        raise ValueError("No observation epochs parsed")

    epochs = sorted(epochs, key=lambda e: e.time)

    times = np.array(
        [(e.time - epochs[0].time).total_seconds() for e in epochs],
        dtype=float
    )

    dts = np.diff(times)
    positive_dts = dts[dts > 0]

    dt_median = (
        float(np.median(positive_dts))
        if len(positive_dts)
        else np.nan
    )

    nominal_interval = (
        header.interval
        if np.isfinite(header.interval) and header.interval > 0
        else dt_median
    )

    if not np.isfinite(nominal_interval) or nominal_interval <= 0:
        nominal_interval = 1.0

    duration_s = (
        (epochs[-1].time - epochs[0].time).total_seconds()
        if len(epochs) > 1
        else 0.0
    )

    expected_epochs = (
        int(round(duration_s / nominal_interval)) + 1
        if duration_s >= 0
        else len(epochs)
    )

    epoch_retention = (
        100.0 * len(epochs) / expected_epochs
        if expected_epochs > 0
        else np.nan
    )

    observed_systems = {
        sat[0]
        for e in epochs
        for sat in e.sats.keys()
        if sat
    }

    pairs_by_sys = build_signal_pairs(header, observed_systems)

    # --------------------------------------------------------------
    # Dataset accumulators
    # --------------------------------------------------------------
    cn0_values = []

    declared_cp_total = 0
    declared_cp_present = 0

    valid_code_count = 0
    valid_phase_count = 0
    simultaneous_code_phase_count = 0

    epoch_usable_sat_count = []
    multifreq_den = 0
    multifreq_num = 0

    signal_pair_simultaneous_counts = Counter()

    # sat/family series for phase arcs and CMC
    # key -> list of (time, code, phase, lli, lambda)
    series = defaultdict(list)

    # LLI / phase-transition accounting
    lli_flag_count = 0
    phase_jump_flag_count = 0
    combined_slip_flag_count = 0
    phase_transition_count = 0
    lli_nonzero_count = 0
    lli_field_valid_phase_count = 0

    # Track previous valid phase time by sat/family.
    prev_phase_time = {}

    # All declared C/P obs types by system for completeness.
    cp_declared = {}

    for system in observed_systems:
        obs_types = (
            header.obs_types_by_system.get(system, [])
            if header.major >= 3
            else header.obs_types_by_system.get("*", [])
        )

        cp_declared[system] = [
            o for o in obs_types
            if str(o).upper().startswith(("C", "P", "L"))
        ]

    # --------------------------------------------------------------
    # Main epoch scan
    # --------------------------------------------------------------
    for epoch_idx, epoch in enumerate(epochs, 1):
        usable_sats_this_epoch = 0

        for sat, obs_map in epoch.sats.items():
            system = sat[0] if sat else "G"

            # C/N0 from all declared S observations, not just paired families.
            for obs_type, ov in obs_map.items():
                if str(obs_type).upper().startswith("S"):
                    v = ov.value

                    if (
                        np.isfinite(v) and
                        CN0_MIN_DBHZ <= v <= CN0_MAX_DBHZ
                    ):
                        cn0_values.append(v)

            # Observation completeness over declared C/P fields.
            for obs_type in cp_declared.get(system, []):
                declared_cp_total += 1
                ov = obs_map.get(obs_type)

                if ov is not None and np.isfinite(ov.value):
                    declared_cp_present += 1

            usable_bands = set()
            sat_has_usable_pair = False

            for fam, pair in pairs_by_sys.get(system, {}).items():
                code_obs = pair["code"]
                phase_obs = pair["phase"]
                band = pair.get("band")

                code = obs_map.get(code_obs)
                phase = obs_map.get(phase_obs)

                code_valid = (
                    code is not None and
                    np.isfinite(code.value) and
                    CODE_MIN_M <= abs(code.value) <= CODE_MAX_M
                )

                phase_valid = (
                    phase is not None and
                    np.isfinite(phase.value) and
                    abs(phase.value) <= PHASE_ABS_MAX_CYCLES
                )

                if code_valid:
                    valid_code_count += 1

                if phase_valid:
                    valid_phase_count += 1
                    lli_field_valid_phase_count += 1

                key = (sat, fam)

                if phase_valid:
                    if key in prev_phase_time:
                        dt = (epoch.time - prev_phase_time[key]).total_seconds()

                        # A valid "transition" requires temporal continuity.
                        if (
                            dt > 0 and
                            dt <= max(
                                GAP_FACTOR * nominal_interval,
                                ABSOLUTE_GAP_LIMIT_S
                            )
                        ):
                            phase_transition_count += 1

                    prev_phase_time[key] = epoch.time

                    if phase.lli & 1:
                        lli_flag_count += 1
                        lli_nonzero_count += 1

                if code_valid and phase_valid:
                    simultaneous_code_phase_count += 1
                    sat_has_usable_pair = True

                    if band:
                        usable_bands.add(band)

                    signal_pair_simultaneous_counts[(system, fam)] += 1

                    lam = wavelength(system, phase_obs, header.major)

                    series[key].append(
                        (
                            epoch.time,
                            float(code.value),
                            float(phase.value),
                            int(phase.lli),
                            float(lam) if np.isfinite(lam) else np.nan,
                            system,
                            fam,
                            band,
                        )
                    )

            if sat_has_usable_pair:
                usable_sats_this_epoch += 1

            if len(usable_bands) >= 1:
                multifreq_den += 1

                if len(usable_bands) >= 2:
                    multifreq_num += 1

        epoch_usable_sat_count.append(usable_sats_this_epoch)

        if (
            PROGRESS_EVERY_EPOCHS and
            epoch_idx % PROGRESS_EVERY_EPOCHS == 0
        ):
            print(
                f"      parsed metrics through epoch "
                f"{epoch_idx}/{len(epochs)}"
            )

    # --------------------------------------------------------------
    # FINAL SCIENTIFIC ARCS + COMMON-SIGNAL CMC
    # --------------------------------------------------------------
    arc_rows = []
    cmc_residuals_all = []
    cmc_residuals_gps_l1 = []
    cmc_residuals_gps_l5 = []
    cmc_summary_rows = []

    gap_limit = max(
        GAP_FACTOR * nominal_interval,
        ABSOLUTE_GAP_LIMIT_S
    )

    # Recompute phase transition / jump counts consistently with the final
    # scientific arc definition (gap + robust phase jump, not LLI).
    final_phase_transition_count = 0
    final_phase_jump_count = 0

    for (sat, fam), records in series.items():
        records = sorted(records, key=lambda r: r[0])

        # Step 1: temporal segmentation ONLY. LLI does not break arcs.
        temporal_arcs = []
        current = []

        for rec in records:
            t = rec[0]

            if not current:
                current = [rec]
                continue

            dt = (t - current[-1][0]).total_seconds()

            if dt <= 0 or dt > gap_limit:
                temporal_arcs.append(current)
                current = [rec]
            else:
                current.append(rec)

        if current:
            temporal_arcs.append(current)

        refined_arcs = []

        # Step 2: robust carrier-phase jump segmentation.
        for arc in temporal_arcs:
            phases = np.asarray([r[2] for r in arc], float)

            if len(phases) <= 1:
                refined_arcs.append(arc)
                continue

            dphase = np.diff(phases)
            final_phase_transition_count += len(dphase)

            med_dp = np.median(dphase)
            sig_dp = robust_sigma(dphase)

            jump_thr = max(
                PHASE_JUMP_MIN_CYCLES,
                PHASE_JUMP_MAD_MULT * sig_dp
                if np.isfinite(sig_dp) else PHASE_JUMP_MIN_CYCLES
            )

            jump_after = np.where(
                np.abs(dphase - med_dp) > jump_thr
            )[0]

            final_phase_jump_count += len(jump_after)

            starts = [0]
            ends = []

            for idx in jump_after:
                ends.append(idx + 1)
                starts.append(idx + 1)

            ends.append(len(arc))

            refined_arcs.extend([
                arc[s:e]
                for s, e in zip(starts, ends)
                if e > s
            ])

        pair_cmc_residuals = []

        for arc_id, arc in enumerate(refined_arcs, 1):
            times_arc = [r[0] for r in arc]
            duration = (
                (times_arc[-1] - times_arc[0]).total_seconds()
                if len(times_arc) > 1 else 0.0
            )

            system = arc[0][5]
            fam_here = arc[0][6]
            band = arc[0][7]

            cmc_raw = []

            for rec in arc:
                _, code, phase, _, lam, _, _, _ = rec
                cmc_raw.append(
                    code - lam * phase
                    if np.isfinite(lam)
                    else np.nan
                )

            cmc_raw = np.asarray(cmc_raw, float)
            valid_cmc = np.isfinite(cmc_raw)

            # CMC-specific jump segmentation protects against code/phase
            # discontinuities not fully represented by carrier jump alone.
            cmc_subsegments = []

            if valid_cmc.sum() >= 3:
                valid_idx = np.where(valid_cmc)[0]
                raw_valid = cmc_raw[valid_cmc]

                segs = split_indices_by_jump(
                    raw_valid,
                    CMC_JUMP_MAD_MULT,
                    CMC_MIN_JUMP_M
                )

                for s, e in segs:
                    cmc_subsegments.append(valid_idx[s:e])
            else:
                cmc_subsegments = [np.where(valid_cmc)[0]]

            accepted_any = False
            accepted_points_total = 0

            for idx_sub in cmc_subsegments:
                if len(idx_sub) == 0:
                    continue

                sub_vals = cmc_raw[idx_sub]
                sub_times = [times_arc[k] for k in idx_sub]

                sub_duration = (
                    (sub_times[-1] - sub_times[0]).total_seconds()
                    if len(sub_times) > 1 else 0.0
                )

                accepted = (
                    len(sub_vals) >= max(
                        MIN_ARC_POINTS,
                        CMC_MIN_SEGMENT_POINTS
                    ) and
                    sub_duration >= MIN_ARC_DURATION_S
                )

                if not accepted:
                    continue

                med = float(np.median(sub_vals))
                resid = sub_vals - med

                resid = resid[
                    np.isfinite(resid) &
                    (np.abs(resid) <= CMC_MAX_ABS_RESIDUAL_M)
                ]

                if len(resid) < CMC_MIN_SEGMENT_POINTS:
                    continue

                accepted_any = True
                accepted_points_total += len(resid)

                cmc_residuals_all.extend(resid.tolist())
                pair_cmc_residuals.extend(resid.tolist())

                # PRIMARY common-signal domain.
                if system == "G" and str(band) == "1":
                    cmc_residuals_gps_l1.extend(resid.tolist())

                # SECONDARY common-signal domain.
                if system == "G" and str(band) == "5":
                    cmc_residuals_gps_l5.extend(resid.tolist())

            arc_rows.append({
                "Test": test,
                "Receiver": receiver,
                "Receiver_ID": receiver_id,
                "Receiver_Class": receiver_class,
                "Satellite": sat,
                "System": system,
                "Signal_Family": fam_here,
                "Band": band,
                "Arc_ID": arc_id,
                "Start": times_arc[0],
                "End": times_arc[-1],
                "Duration_s": duration,
                "Point_N": len(arc),
                "CMC_Valid_N": int(valid_cmc.sum()),
                "CMC_Accepted_N": accepted_points_total,
                "Accepted_For_CMC": accepted_any,
                "Scientific_Arc_Definition": "TIME_GAP_PLUS_ROBUST_PHASE_JUMP",
            })

        if pair_cmc_residuals:
            cmc_summary_rows.append({
                "Test": test,
                "Receiver": receiver,
                "Receiver_ID": receiver_id,
                "Satellite": sat,
                "System": sat[0],
                "Signal_Family": fam,
                "Band": records[0][7] if records else None,
                "CMC_Residual_N": len(pair_cmc_residuals),
                "CMC_RobustSigma_m":
                    robust_sigma(pair_cmc_residuals),
                "CMC_P95Abs_m":
                    p95_abs(pair_cmc_residuals),
                "CMC_Role":
                    (
                        "PRIMARY_GPS_L1"
                        if sat[0] == "G" and str(records[0][7]) == "1"
                        else "SECONDARY_GPS_L5"
                        if sat[0] == "G" and str(records[0][7]) == "5"
                        else "DIAGNOSTIC"
                    ),
            })

    accepted_arc_durations = [
        r["Duration_s"]
        for r in arc_rows
        if r["Point_N"] >= 2 and r["Duration_s"] >= 0
    ]

    phase_discontinuity_rate = (
        1000.0 * final_phase_jump_count /
        final_phase_transition_count
        if final_phase_transition_count > 0
        else np.nan
    )

    lli_flag_rate = (
        1000.0 * lli_flag_count / phase_transition_count
        if phase_transition_count > 0
        else np.nan
    )

    # --------------------------------------------------------------
    # Final metrics
    # --------------------------------------------------------------
    metrics = {
        "Test": test,
        "Receiver": receiver,
        "Receiver_ID": receiver_id,
        "Receiver_Class": receiver_class,
        "RINEX_File": str(path),

        # CORE
        "CN0_Median_dBHz": safe_median(cn0_values),
        "CN0_RobustSigma_dB": robust_sigma(cn0_values),

        "GPS_L1_CMC_RobustSigma_m":
            robust_sigma(cmc_residuals_gps_l1),

        "GPS_L1_CMC_P95Abs_m":
            p95_abs(cmc_residuals_gps_l1),

        "PhaseDiscontinuity_Rate_per1000":
            phase_discontinuity_rate,

        "Median_PhaseArc_Length_s":
            safe_median(accepted_arc_durations),

        "Epoch_Retention_pct":
            epoch_retention,

        "Observation_Completeness_pct":
            (
                100.0 * declared_cp_present / declared_cp_total
                if declared_cp_total > 0 else np.nan
            ),

        "Median_Usable_Satellites":
            safe_median(epoch_usable_sat_count),

        "MultiFrequency_Availability_pct":
            (
                100.0 * multifreq_num / multifreq_den
                if multifreq_den > 0 else np.nan
            ),

        # SECONDARY
        "Signal_Diversity_Count":
            float(sum(
                count >= MIN_SIGNAL_PAIR_OBS
                for count in signal_pair_simultaneous_counts.values()
            )),

        "GPS_L5_CMC_RobustSigma_m":
            robust_sigma(cmc_residuals_gps_l5),

        # DIAGNOSTIC-ONLY
        "GPS_L5_CMC_P95Abs_m":
            p95_abs(cmc_residuals_gps_l5),

        "LLI_FlagRate_per1000":
            lli_flag_rate,

        "CodePhase_Continuity_Ratio_pct":
            (
                100.0 * simultaneous_code_phase_count / valid_code_count
                if valid_code_count > 0 else np.nan
            ),

        "AllGNSS_CMC_RobustSigma_m":
            robust_sigma(cmc_residuals_all),

        "AllGNSS_CMC_P95Abs_m":
            p95_abs(cmc_residuals_all),
    }

    parser_qc = {
        "Test": test,
        "Receiver": receiver,
        "Receiver_ID": receiver_id,
        "Receiver_Class": receiver_class,
        "RINEX_File": str(path),

        "RINEX_Version": header.version,
        "Epoch_N": len(epochs),
        "Expected_Epoch_N": expected_epochs,
        "Duration_min": duration_s / 60.0,
        "Header_Interval_s": header.interval,
        "Median_dt_s": dt_median,
        "Nominal_Interval_s": nominal_interval,
        "Epoch_Retention_pct": epoch_retention,

        "Observed_System_N": len(observed_systems),
        "Observed_Systems": ",".join(sorted(observed_systems)),

        "Declared_CP_Slots": declared_cp_total,
        "Present_CP_Slots": declared_cp_present,

        "Valid_Code_N": valid_code_count,
        "Valid_Phase_N": valid_phase_count,
        "Simultaneous_CodePhase_N": simultaneous_code_phase_count,
        "Valid_Phase_Transitions_N": phase_transition_count,

        "LLI_SlipFlag_N": lli_flag_count,
        "PhaseJump_Flag_N": final_phase_jump_count,
        "CombinedSlip_Flag_N": np.nan,
        "LLI_SlipRate_per1000":
            (
                1000.0 * lli_flag_count / phase_transition_count
                if phase_transition_count > 0 else np.nan
            ),
        "PhaseJump_Rate_per1000":
            phase_discontinuity_rate,
        "Final_Phase_Transitions_N":
            final_phase_transition_count,
        "LLI_Nonzero_N": lli_nonzero_count,
        "LLI_ValidPhase_N": lli_field_valid_phase_count,

        "CN0_Value_N": len(cn0_values),
        "CMC_Residual_N": len(cmc_residuals_all),
        "GPS_L1_CMC_Residual_N": len(cmc_residuals_gps_l1),
        "GPS_L5_CMC_Residual_N": len(cmc_residuals_gps_l5),

        "Phase_Series_N": len(series),
        "Phase_Arc_N": len(arc_rows),

        "MultiFreq_Den_N": multifreq_den,
        "MultiFreq_Num_N": multifreq_num,

        "Marker_Name": header.marker_name,
        "Receiver_Type_Header": header.receiver_type,
        "Antenna_Type_Header": header.antenna_type,

        "Antenna_Delta_H_m":
            header.antenna_delta_hen[0]
            if header.antenna_delta_hen else np.nan,

        "Antenna_Delta_E_m":
            header.antenna_delta_hen[1]
            if header.antenna_delta_hen else np.nan,

        "Antenna_Delta_N_m":
            header.antenna_delta_hen[2]
            if header.antenna_delta_hen else np.nan,
    }

    pair_inventory_rows = []

    for system, fams in pairs_by_sys.items():
        for fam, d in fams.items():
            pair_inventory_rows.append({
                "Test": test,
                "Receiver": receiver,
                "Receiver_ID": receiver_id,
                "Receiver_Class": receiver_class,
                "System": system,
                "Signal_Family": fam,
                "Band": d.get("band"),
                "Code_Obs": d.get("code"),
                "Phase_Obs": d.get("phase"),
                "SNR_Obs": d.get("snr"),
                "Simultaneous_CodePhase_N":
                    signal_pair_simultaneous_counts.get(
                        (system, fam), 0
                    ),
                "Counts_Toward_Diversity":
                    signal_pair_simultaneous_counts.get(
                        (system, fam), 0
                    ) >= MIN_SIGNAL_PAIR_OBS,
                "CMC_Frequency_Hz":
                    FREQ_HZ.get(system, {}).get(
                        d.get("band"), np.nan
                    ),
                "CMC_Supported":
                    np.isfinite(
                        FREQ_HZ.get(system, {}).get(
                            d.get("band"), np.nan
                        )
                    ),
            })

    return (
        metrics,
        parser_qc,
        pair_inventory_rows,
        arc_rows,
        cmc_summary_rows,
    )


# ======================================================================
# STANDARDIZED QUALITY PROFILE
# ======================================================================

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

SECONDARY_METRICS = [
    "Signal_Diversity_Count",
    "GPS_L5_CMC_RobustSigma_m",
]

DIAGNOSTIC_METRICS = [
    "GPS_L5_CMC_P95Abs_m",
    "LLI_FlagRate_per1000",
    "CodePhase_Continuity_Ratio_pct",
    "AllGNSS_CMC_RobustSigma_m",
    "AllGNSS_CMC_P95Abs_m",
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
    "Signal_Diversity_Count": +1,
    "GPS_L5_CMC_RobustSigma_m": -1,
}

ALL_METRICS = CORE_METRICS + SECONDARY_METRICS



def build_standardized_profile(df):
    out = df[
        ["Test", "Receiver", "Receiver_ID", "Receiver_Class"]
    ].copy()

    for metric in ALL_METRICS:
        x = pd.to_numeric(df[metric], errors="coerce")
        med = np.nanmedian(x)

        mad = np.nanmedian(np.abs(x - med))
        scale = 1.4826 * mad

        if not np.isfinite(scale) or scale <= 1e-12:
            z = pd.Series(np.nan, index=x.index)
        else:
            z = (x - med) / scale

        out[f"ZQ_{metric}"] = QUALITY_DIRECTION[metric] * z

    return out


# ======================================================================
# METRIC DEFINITIONS TABLE
# ======================================================================

def metric_definitions():
    rows = [
        ("CN0_Median_dBHz", "CORE",
         "Median of all valid RINEX S-observations.",
         "Higher is generally better."),
        ("CN0_RobustSigma_dB", "CORE",
         "1.4826×MAD of valid RINEX S-observations.",
         "Lower indicates more stable signal strength."),
        ("GPS_L1_CMC_RobustSigma_m", "CORE",
         "1.4826×MAD of arc-detrended GPS L1 CMC residuals using matched same-family code and phase.",
         "Primary common-signal CMC dispersion; lower is better."),
        ("GPS_L1_CMC_P95Abs_m", "CORE",
         "95th percentile of |arc-detrended GPS L1 CMC residuals|.",
         "Primary common-signal CMC tail metric; lower is better."),
        ("PhaseDiscontinuity_Rate_per1000", "CORE",
         "1000×robust carrier-phase jump flags / temporally continuous valid phase transitions; independent of receiver LLI.",
         "Lower indicates stronger carrier continuity."),
        ("Median_PhaseArc_Length_s", "CORE",
         "Median carrier-phase arc duration segmented by time gaps and robust phase jumps; LLI is excluded.",
         "Higher indicates stronger harmonized carrier continuity."),
        ("Epoch_Retention_pct", "CORE",
         "Observed epochs / expected epochs from session span and nominal interval ×100.",
         "Higher is better."),
        ("Observation_Completeness_pct", "CORE",
         "Present declared C/P values / declared C/P slots over observed satellite epochs ×100.",
         "Higher indicates more complete observation records."),
        ("Median_Usable_Satellites", "CORE",
         "Median per-epoch satellites having at least one simultaneous matched code+phase signal family.",
         "Higher generally supports stronger positioning."),
        ("MultiFrequency_Availability_pct", "CORE",
         "Percent of usable epoch-satellite instances containing at least two usable frequency bands.",
         "Higher indicates stronger multi-frequency availability."),
        ("Signal_Diversity_Count", "SECONDARY",
         f"Distinct constellation+signal families with >= {MIN_SIGNAL_PAIR_OBS} simultaneous code-phase observations.",
         "Describes usable signal diversity."),
        ("GPS_L5_CMC_RobustSigma_m", "SECONDARY",
         "1.4826×MAD of arc-detrended GPS L5 CMC residuals when coverage exists.",
         "Secondary common-signal CMC metric."),
        ("GPS_L5_CMC_P95Abs_m", "DIAGNOSTIC",
         "P95 absolute GPS L5 CMC residual.",
         "Diagnostic tail metric."),
        ("LLI_FlagRate_per1000", "DIAGNOSTIC",
         "1000×RINEX LLI bit-0 flags / valid temporally continuous phase transitions.",
         "Receiver-dependent tracking-state diagnostic; not the core slip metric."),
        ("CodePhase_Continuity_Ratio_pct", "DIAGNOSTIC",
         "100×simultaneous valid code+phase / valid code observations over matched families.",
         "QC diagnostic; may be non-discriminatory when uniformly 100%."),
        ("AllGNSS_CMC_RobustSigma_m", "DIAGNOSTIC",
         "Robust sigma of accepted CMC residuals pooled across all supported GNSS signals.",
         "Diagnostic only because signal-mixture differences can confound receiver comparison."),
        ("AllGNSS_CMC_P95Abs_m", "DIAGNOSTIC",
         "P95 absolute accepted CMC residual pooled across all supported GNSS signals.",
         "Diagnostic only."),
    ]

    return pd.DataFrame(
        rows,
        columns=["Metric", "Role", "Definition", "Interpretation"]
    )


# ======================================================================
# MAIN
# ======================================================================

def main():
    t0 = time.perf_counter()

    print("=" * 142)
    print("GNSS STAGE-1 RINEX METRICS v2.2")
    print("Direct harmonized extraction from the 12 original RINEX files")
    print("=" * 142)
    print(f"RAW root   : {RAW_ROOT}")
    print(f"Output dir : {OUT_DIR}")
    print("Old analysis/QC output folders are NOT scanned.\n")

    metric_rows = []
    parser_rows = []
    pair_rows = []
    arc_rows_all = []
    cmc_rows_all = []

    total = sum(len(v) for v in DATASETS.values())
    counter = 0

    for test, mapping in DATASETS.items():
        for base, (receiver, receiver_id, receiver_class) in mapping.items():
            counter += 1

            path = discover_rinex(test, base)

            print(
                f"[{counter:02d}/{total:02d}] "
                f"{test} | {receiver:<16s} | expected stem={base}"
            )

            if path is None:
                print("    [MISSING] RINEX file not found.")

                metric_rows.append({
                    "Test": test,
                    "Receiver": receiver,
                    "Receiver_ID": receiver_id,
                    "Receiver_Class": receiver_class,
                    "RINEX_File": "",
                    **{m: np.nan for m in (ALL_METRICS + DIAGNOSTIC_METRICS)}
                })

                parser_rows.append({
                    "Test": test,
                    "Receiver": receiver,
                    "Receiver_ID": receiver_id,
                    "Receiver_Class": receiver_class,
                    "RINEX_File": "",
                    "Parser_Status": "MISSING",
                    "Parser_Error": "RINEX file not found",
                })

                continue

            print(f"    File: {path}")

            try:
                header, epochs = read_rinex(path)

                print(
                    f"    RINEX v{header.version:.2f} | "
                    f"epochs={len(epochs)} | "
                    f"header interval={header.interval}"
                )

                (
                    metrics,
                    parser_qc,
                    pair_inventory,
                    arc_rows,
                    cmc_rows,
                ) = analyze_dataset(
                    test=test,
                    receiver=receiver,
                    receiver_id=receiver_id,
                    receiver_class=receiver_class,
                    path=path,
                    header=header,
                    epochs=epochs,
                )

                parser_qc["Parser_Status"] = "OK"
                parser_qc["Parser_Error"] = ""

                metric_rows.append(metrics)
                parser_rows.append(parser_qc)
                pair_rows.extend(pair_inventory)
                arc_rows_all.extend(arc_rows)
                cmc_rows_all.extend(cmc_rows)

                print(
                    "    Metrics: "
                    f"CN0={metrics['CN0_Median_dBHz']:.3f} | "
                    f"GPS-L1 CMCσ={metrics['GPS_L1_CMC_RobustSigma_m']:.3f} m | "
                    f"GPS-L1 CMC95={metrics['GPS_L1_CMC_P95Abs_m']:.3f} m | "
                    f"PhaseDisc/1000={metrics['PhaseDiscontinuity_Rate_per1000']:.3f} | "
                    f"Arc={metrics['Median_PhaseArc_Length_s']:.1f}s | "
                    f"Retention={metrics['Epoch_Retention_pct']:.2f}% | "
                    f"Sat={metrics['Median_Usable_Satellites']:.1f}"
                )

            except Exception as exc:
                print(f"    [ERROR] {type(exc).__name__}: {exc}")

                metric_rows.append({
                    "Test": test,
                    "Receiver": receiver,
                    "Receiver_ID": receiver_id,
                    "Receiver_Class": receiver_class,
                    "RINEX_File": str(path),
                    **{m: np.nan for m in (ALL_METRICS + DIAGNOSTIC_METRICS)}
                })

                parser_rows.append({
                    "Test": test,
                    "Receiver": receiver,
                    "Receiver_ID": receiver_id,
                    "Receiver_Class": receiver_class,
                    "RINEX_File": str(path),
                    "Parser_Status": "ERROR",
                    "Parser_Error":
                        f"{type(exc).__name__}: {exc}",
                })

    df_metrics = pd.DataFrame(metric_rows)
    df_parser = pd.DataFrame(parser_rows)
    df_pairs = pd.DataFrame(pair_rows)
    df_arcs = pd.DataFrame(arc_rows_all)
    df_cmc = pd.DataFrame(cmc_rows_all)
    df_defs = metric_definitions()
    df_profile = build_standardized_profile(df_metrics)

    # --------------------------------------------------------------
    # Export
    # --------------------------------------------------------------
    p_metrics = OUT_DIR / "GNSS_STAGE1_FINAL_METRICS.csv"
    p_xlsx = OUT_DIR / "GNSS_STAGE1_FINAL_METRICS.xlsx"
    p_parser = OUT_DIR / "GNSS_STAGE1_RINEX_PARSER_QC.csv"
    p_pairs = OUT_DIR / "GNSS_STAGE1_SIGNAL_PAIR_INVENTORY.csv"
    p_arcs = OUT_DIR / "GNSS_STAGE1_PHASE_ARC_SUMMARY.csv"
    p_cmc = OUT_DIR / "GNSS_STAGE1_CMC_SUMMARY.csv"
    p_defs = OUT_DIR / "GNSS_STAGE1_METRIC_DEFINITIONS.csv"
    p_profile = OUT_DIR / "GNSS_STAGE1_STANDARDIZED_PROFILE.csv"

    df_metrics.to_csv(p_metrics, index=False, encoding="utf-8-sig")
    df_parser.to_csv(p_parser, index=False, encoding="utf-8-sig")
    df_pairs.to_csv(p_pairs, index=False, encoding="utf-8-sig")
    df_arcs.to_csv(p_arcs, index=False, encoding="utf-8-sig")
    df_cmc.to_csv(p_cmc, index=False, encoding="utf-8-sig")
    df_defs.to_csv(p_defs, index=False, encoding="utf-8-sig")
    df_profile.to_csv(p_profile, index=False, encoding="utf-8-sig")

    with pd.ExcelWriter(p_xlsx, engine="openpyxl") as writer:
        df_metrics.to_excel(
            writer, sheet_name="FINAL_METRICS", index=False
        )
        df_parser.to_excel(
            writer, sheet_name="PARSER_QC", index=False
        )
        df_pairs.to_excel(
            writer, sheet_name="SIGNAL_PAIRS", index=False
        )
        df_cmc.to_excel(
            writer, sheet_name="CMC_SUMMARY", index=False
        )
        df_defs.to_excel(
            writer, sheet_name="DEFINITIONS", index=False
        )
        df_profile.to_excel(
            writer, sheet_name="STANDARDIZED_PROFILE", index=False
        )

        # Excel sheet row limit protection.
        if len(df_arcs) <= 1_000_000:
            df_arcs.to_excel(
                writer, sheet_name="PHASE_ARCS", index=False
            )

    # --------------------------------------------------------------
    # Final QC console
    # --------------------------------------------------------------
    elapsed = time.perf_counter() - t0

    pd.set_option("display.width", 280)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")

    print("\n" + "=" * 142)
    print("FINAL STAGE-1 METRICS")
    print("=" * 142)
    print(df_metrics.to_string(index=False))

    print("\nPARSER STATUS")
    cols = [
        c for c in [
            "Test", "Receiver_ID", "Receiver",
            "Parser_Status", "RINEX_Version",
            "Epoch_N", "Expected_Epoch_N",
            "Median_dt_s", "Epoch_Retention_pct",
            "Valid_Code_N", "Valid_Phase_N",
            "Simultaneous_CodePhase_N",
            "LLI_SlipFlag_N", "PhaseJump_Flag_N",
            "Final_Phase_Transitions_N", "CN0_Value_N",
            "CMC_Residual_N", "Parser_Error"
        ]
        if c in df_parser.columns
    ]
    print(df_parser[cols].to_string(index=False))

    print("\nMETRIC COVERAGE")
    for metric in ALL_METRICS:
        n = int(df_metrics[metric].notna().sum())
        print(f"  {metric:<38s} {n:2d}/12")

    print("\nOUTPUT FILES")
    for p in [
        p_metrics, p_xlsx, p_parser, p_pairs,
        p_arcs, p_cmc, p_defs, p_profile
    ]:
        print(p)

    print(
        f"\nElapsed time: {elapsed:.1f} s "
        f"({elapsed/60.0:.2f} min)"
    )

    print("\nIMPORTANT:")
    print(
        "v2.2 freezes the Stage-1 scientific definitions. Verify 12/12 parser "
        "success and GPS-L1 CMC coverage before Stage-1→Stage-2 inference. "
        "LLI and pooled All-GNSS CMC remain diagnostic-only."
    )


if __name__ == "__main__":
    main()
