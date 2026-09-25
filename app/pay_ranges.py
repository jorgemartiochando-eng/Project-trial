"""Pay ranges per category (Art. 5 pre-employment transparency, Art. 6
pay-setting criteria) and Art. 7 right-to-information responses."""
from __future__ import annotations

import pandas as pd

from .config import Settings
from .metrics import _clean


def _round(x: float, step: int = 500) -> float:
    return float(round(x / step) * step)


def pay_ranges(df: pd.DataFrame) -> list[dict]:
    """Suggested advertised range = P25..P75 of FTE base salary in the
    category, rounded. Also reports how many incumbents sit outside it."""
    rows = []
    for (entity, cid, label), grp in df.groupby(["legal_entity", "category_id", "category_label"]):
        base = grp["base_salary"]
        p = base.quantile([0.1, 0.25, 0.5, 0.75, 0.9])
        lo, hi = _round(p[0.25]), _round(p[0.75])
        below = grp[grp["base_salary"] < lo]
        rows.append({
            "legal_entity": entity,
            "category_id": cid,
            "category_label": label,
            "headcount": len(grp),
            "p10": _clean(p[0.1]), "p25": _clean(p[0.25]), "median": _clean(p[0.5]),
            "p75": _clean(p[0.75]), "p90": _clean(p[0.9]),
            "suggested_min": lo, "suggested_max": hi,
            "spread": _clean(hi / lo - 1) if lo else None,
            "below_range": {"F": int((below["sex"] == "F").sum()), "M": int((below["sex"] == "M").sum())},
            "above_range": int((grp["base_salary"] > hi).sum()),
            "roles": sorted(grp["job_title"].unique().tolist()),
        })
    return rows


def right_to_information(df: pd.DataFrame, employee_id: str, settings: Settings) -> dict | None:
    """Art. 7: a worker may request their individual pay level and the average
    pay levels, broken down by sex, for their category of workers. The employer
    must answer within two months."""
    match = df[df["employee_id"] == str(employee_id)]
    if match.empty:
        return None
    me = match.iloc[0]
    # Comparators: same category of workers at the same employer.
    peers = df[(df["category_id"] == me["category_id"]) & (df["legal_entity"] == me["legal_entity"])]
    by_sex = {}
    warnings = []
    for sex in ("F", "M"):
        grp = peers[peers["sex"] == sex]
        n = len(grp)
        by_sex[sex] = {
            "headcount": n,
            "mean_hourly_total": _clean(grp["hourly_total"].mean()) if n else None,
            "mean_hourly_basic": _clean(grp["hourly_basic"].mean()) if n else None,
            "mean_annual_total_fte": _clean(grp["annual_total_fte"].mean()) if n else None,
        }
        if 0 < n < settings.min_group_size:
            warnings.append(
                f"Only {n} {'women' if sex == 'F' else 'men'} in this category: the average may allow "
                "individual pay to be inferred. Consult your DPO on how to disclose it (Art. 7 & 12)."
            )
    letter = (
        f"Dear colleague,\n\n"
        f"In response to your request under Article 7 of Directive (EU) 2023/970, please find below "
        f"your individual pay level and the average pay levels, broken down by sex, for the category "
        f"of workers performing the same work or work of equal value as you at {me['legal_entity']} ({me['category_label']}).\n\n"
        f"Your pay: {me['hourly_total']:.2f} per hour "
        f"(basic {me['hourly_basic']:.2f}, complementary {me['hourly_complementary']:.2f}); "
        f"annual FTE-equivalent total {me['annual_total_fte']:,.0f}.\n"
    )
    for sex, label in (("F", "Women"), ("M", "Men")):
        s = by_sex[sex]
        if s["headcount"]:
            letter += (f"{label} in your category ({s['headcount']}): average {s['mean_hourly_total']:.2f} per hour; "
                       f"annual FTE-equivalent {s['mean_annual_total_fte']:,.0f}.\n")
        else:
            letter += f"{label} in your category: no comparator.\n"
    letter += (
        "\nThe criteria used to determine pay, pay levels and pay progression are available on request "
        "(Article 6). You may request clarification of this information, and you are free to disclose your "
        "own pay for the purpose of enforcing the principle of equal pay.\n"
    )
    return {
        "employee": {
            "employee_id": me["employee_id"],
            "sex": me["sex"],
            "job_title": me["job_title"],
            "legal_entity": me["legal_entity"],
            "category_id": me["category_id"],
            "category_label": me["category_label"],
            "hourly_total": _clean(me["hourly_total"]),
            "hourly_basic": _clean(me["hourly_basic"]),
            "hourly_complementary": _clean(me["hourly_complementary"]),
            "annual_total_fte": _clean(me["annual_total_fte"]),
        },
        "category_averages": by_sex,
        "warnings": warnings,
        "response_deadline_days": 60,
        "letter": letter,
    }
