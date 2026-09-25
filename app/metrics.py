"""Article 9 pay-gap indicators.

Gap convention (Art. 3(1)(c)): (male - female) / male. Positive = men paid more.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import Settings


def _clean(x):
    """Make numpy / NaN values JSON friendly."""
    if x is None:
        return None
    if isinstance(x, (np.floating, float)):
        return None if math.isnan(x) or math.isinf(x) else float(x)
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def gap(male: pd.Series, female: pd.Series, how: str = "mean") -> float | None:
    if len(male) == 0 or len(female) == 0:
        return None
    m = male.mean() if how == "mean" else male.median()
    f = female.mean() if how == "mean" else female.median()
    if not m:
        return None
    return _clean((m - f) / m)


def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    return df[df["sex"] == "M"], df[df["sex"] == "F"]


def headline_indicators(df: pd.DataFrame) -> dict:
    """Art. 9(1)(a)-(f)."""
    m, f = _split(df)
    comp_m = m[m["receives_complementary"]]
    comp_f = f[f["receives_complementary"]]
    return {
        "headcount": {"F": len(f), "M": len(m), "X": int((df["sex"] == "X").sum()), "total": len(df)},
        # (a) and (c): total pay (basic + complementary)
        "mean_gap": gap(m["pay_total"], f["pay_total"], "mean"),
        "median_gap": gap(m["pay_total"], f["pay_total"], "median"),
        "mean_gap_basic": gap(m["pay_basic"], f["pay_basic"], "mean"),
        "median_gap_basic": gap(m["pay_basic"], f["pay_basic"], "median"),
        # (b) and (d): among those receiving complementary/variable components
        "mean_gap_complementary": gap(comp_m["pay_complementary"], comp_f["pay_complementary"], "mean"),
        "median_gap_complementary": gap(comp_m["pay_complementary"], comp_f["pay_complementary"], "median"),
        # (e)
        "share_receiving_complementary": {
            "F": _clean(f["receives_complementary"].mean()) if len(f) else None,
            "M": _clean(m["receives_complementary"].mean()) if len(m) else None,
        },
        "share_receiving_variable": {
            "F": _clean(f["receives_variable"].mean()) if len(f) else None,
            "M": _clean(m["receives_variable"].mean()) if len(m) else None,
        },
        "mean_pay": {
            "F": _clean(f["pay_total"].mean()) if len(f) else None,
            "M": _clean(m["pay_total"].mean()) if len(m) else None,
        },
    }


def quartile_bands(df: pd.DataFrame) -> list[dict]:
    """Art. 9(1)(f): proportion of women/men in each pay quartile band.

    Workers are ranked by total pay (monthly FTE or hourly) and split into four equally sized
    groups (ties broken by order, as rank(method='first'))."""
    binary = df[df["sex"].isin(["F", "M"])].copy()
    if len(binary) < 4:
        return []
    binary["q"] = pd.qcut(binary["pay_total"].rank(method="first"), 4, labels=[1, 2, 3, 4])
    out = []
    names = {1: "Lower", 2: "Lower middle", 3: "Upper middle", 4: "Upper"}
    for q in [1, 2, 3, 4]:
        grp = binary[binary["q"] == q]
        n = len(grp)
        out.append({
            "quartile": q,
            "label": names[q],
            "headcount": n,
            "share_F": _clean((grp["sex"] == "F").mean()) if n else None,
            "share_M": _clean((grp["sex"] == "M").mean()) if n else None,
            "min_pay": _clean(grp["pay_total"].min()),
            "max_pay": _clean(grp["pay_total"].max()),
        })
    return out


def assessment_key(legal_entity: str, category_id: str) -> str:
    """Art. 9/10 obligations apply per employer, so a category is always
    assessed within one legal entity."""
    return f"{legal_entity}|{category_id}"


def category_gaps(df: pd.DataFrame, settings: Settings) -> list[dict]:
    """Art. 9(1)(g) and the Art. 10 trigger test per category of workers,
    within each legal entity."""
    rows = []
    thr = settings.gap_threshold
    for (entity, cid, label), grp in df.groupby(["legal_entity", "category_id", "category_label"]):
        key = assessment_key(entity, cid)
        m, f = _split(grp)
        mean_gap_total = gap(m["pay_total"], f["pay_total"], "mean")
        mean_gap_basic = gap(m["pay_basic"], f["pay_basic"], "mean")
        mean_gap_comp = gap(m["pay_complementary"], f["pay_complementary"], "mean")
        small = min(len(m), len(f)) < settings.min_group_size
        exceeds = mean_gap_total is not None and abs(mean_gap_total) >= thr
        justification = settings.justifications.get(key, "").strip()
        if mean_gap_total is None:
            status = "not_comparable"
        elif not exceeds:
            status = "ok"
        elif justification:
            status = "justified"
        else:
            status = "assessment_required"
        rows.append({
            "key": key,
            "legal_entity": entity,
            "category_id": cid,
            "category_label": label,
            "headcount_F": len(f),
            "headcount_M": len(m),
            "headcount_X": int((grp["sex"] == "X").sum()),
            "mean_pay_F": _clean(f["pay_total"].mean()) if len(f) else None,
            "mean_pay_M": _clean(m["pay_total"].mean()) if len(m) else None,
            "mean_gap": mean_gap_total,
            "median_gap": gap(m["pay_total"], f["pay_total"], "median"),
            "mean_gap_basic": mean_gap_basic,
            "mean_gap_complementary": mean_gap_comp,
            "job_families": sorted(grp["job_family"].unique().tolist()),
            "small_group": small,
            "exceeds_threshold": exceeds,
            "justification": justification,
            "status": status,
        })
    return sorted(rows, key=lambda r: (r["legal_entity"], r["category_id"]))


def breakdown(df: pd.DataFrame, by: str) -> list[dict]:
    rows = []
    for key, grp in df.groupby(by):
        m, f = _split(grp)
        rows.append({
            by: key,
            "headcount_F": len(f),
            "headcount_M": len(m),
            "share_F": _clean(len(f) / max(len(f) + len(m), 1)),
            "mean_gap": gap(m["pay_total"], f["pay_total"], "mean"),
            "median_gap": gap(m["pay_total"], f["pay_total"], "median"),
            "part_time_share_F": _clean((f["fte"] < 1).mean()) if len(f) else None,
            "part_time_share_M": _clean((m["fte"] < 1).mean()) if len(m) else None,
        })
    return rows


def outliers(df: pd.DataFrame, max_ratio: float = 0.9) -> list[dict]:
    """Individuals paid well below peers of the other sex in the same category:
    pay below `max_ratio` x the other sex's category median.
    Comparisons stay within one legal entity (the employer), so country pay
    levels don't create false positives at group level."""
    out = []
    for (_, cid), grp in df.groupby(["legal_entity", "category_id"]):
        med = grp.groupby("sex")["pay_total"].median()
        if "F" not in med or "M" not in med:
            continue
        for sex, other in (("F", "M"), ("M", "F")):
            peers = grp[grp["sex"] == sex]
            low = peers[peers["pay_total"] < max_ratio * med[other]]
            for _, r in low.iterrows():
                out.append({
                    "employee_id": r["employee_id"],
                    "sex": sex,
                    "category_id": cid,
                    "job_title": r["job_title"],
                    "legal_entity": r["legal_entity"],
                    "pay_total": _clean(r["pay_total"]),
                    "other_sex_median": _clean(med[other]),
                    "compa_ratio": _clean(r["pay_total"] / med[other]),
                })
    return sorted(out, key=lambda r: r["compa_ratio"])
