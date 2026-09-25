"""Article 9(1)(a)-(g) pay gap indicators, with the exact formulas shown to users.

Definitions used (per the company's reporting methodology):
  remuneration  = total pay (basic + variable + allowances + benefits in kind),
                  full-time equivalent, in the configured unit (monthly or hourly)
  variable pay  = bonus / commission, full-time equivalent, computed among the
                  workers who received variable pay in the reference period
  gap           = (men - women) / men x 100; positive means men are paid more
"""
from __future__ import annotations

import pandas as pd

from .config import Settings
from .metrics import _clean, quartile_bands

FORMULAS = {
    "a": "(mean remuneration of men − mean remuneration of women) / mean remuneration of men × 100",
    "b": "(mean variable pay of men − mean variable pay of women) / mean variable pay of men × 100",
    "c": "(median pay of men − median pay of women) / median pay of men × 100",
    "d": "(median variable pay of men − median variable pay of women) / median variable pay of men × 100",
    "e": "men who received variable pay / total men × 100; women who received variable pay / total women × 100",
    "f": "Rank all workers by total pay from lowest to highest, split into four equal groups, "
         "and report the % of women and men in each group",
    "g": "Indicators a), b), c) and d) for each category of workers (or job level), within each legal entity",
}
TITLES = {
    "a": "Overall gender pay gap",
    "b": "Gap in complementary / variable pay",
    "c": "Median pay gap",
    "d": "Median gap in variable pay",
    "e": "Proportion of men and women receiving variable pay",
    "f": "Proportion of men and women in each pay quartile",
    "g": "Gender pay gap by category of workers",
}


def _gap(m: float | None, f: float | None) -> float | None:
    if m is None or f is None or not m:
        return None
    return _clean((m - f) / m * 100)


def _stat(s: pd.Series, how: str) -> float | None:
    if s.empty:
        return None
    return _clean(s.mean() if how == "mean" else s.median())


def core(df: pd.DataFrame) -> dict:
    """Indicators a)-e) for one population."""
    m = df[df["sex"] == "M"]
    f = df[df["sex"] == "F"]
    vm = m[m["receives_variable"]]
    vf = f[f["receives_variable"]]
    out = {}
    for key, col, how, pm, pf in (
        ("a", "pay_total", "mean", m, f),
        ("b", "pay_variable", "mean", vm, vf),
        ("c", "pay_total", "median", m, f),
        ("d", "pay_variable", "median", vm, vf),
    ):
        men, women = _stat(pm[col], how), _stat(pf[col], how)
        out[key] = {"men": men, "women": women, "n_men": len(pm), "n_women": len(pf), "gap_pct": _gap(men, women)}
    out["e"] = {
        "men_pct": _clean(len(vm) / len(m) * 100) if len(m) else None,
        "women_pct": _clean(len(vf) / len(f) * 100) if len(f) else None,
        "men_receiving": len(vm), "men_total": len(m),
        "women_receiving": len(vf), "women_total": len(f),
    }
    return out


def indicators(df: pd.DataFrame, settings: Settings, group_by: str = "category") -> dict:
    headline = core(df)
    quartiles = []
    for q in quartile_bands(df):
        quartiles.append({
            "quartile": q["quartile"], "label": q["label"], "headcount": q["headcount"],
            "women_pct": _clean(q["share_F"] * 100) if q["share_F"] is not None else None,
            "men_pct": _clean(q["share_M"] * 100) if q["share_M"] is not None else None,
            "min_pay": q["min_pay"], "max_pay": q["max_pay"],
        })

    if group_by == "job_level":
        keys, label_of = ["legal_entity", "job_level"], lambda k: f"Level {k[1]}"
    else:
        keys, label_of = ["legal_entity", "category_id", "category_label"], lambda k: k[2]
    groups = []
    for k, grp in df.groupby(keys):
        c = core(grp)
        groups.append({
            "legal_entity": k[0],
            "group": label_of(k),
            "women": c["a"]["n_women"], "men": c["a"]["n_men"],
            "small_group": min(c["a"]["n_women"], c["a"]["n_men"]) < settings.min_group_size,
            **{f"{x}_gap_pct": c[x]["gap_pct"] for x in "abcd"},
            **{f"{x}_men": c[x]["men"] for x in "abcd"},
            **{f"{x}_women": c[x]["women"] for x in "abcd"},
        })

    return {
        "pay_basis": settings.pay_basis,
        "group_by": group_by,
        "titles": TITLES,
        "formulas": FORMULAS,
        "a": headline["a"], "b": headline["b"], "c": headline["c"], "d": headline["d"], "e": headline["e"],
        "f": quartiles,
        "g": groups,
    }
