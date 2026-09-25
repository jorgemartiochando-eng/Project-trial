"""Remediation simulator (Art. 10(2)(f)/(g): measures to address unjustified
differences).

For every category whose gap breaches the target and has no objective
justification, compute the minimum total hourly increase that brings the
female mean to (1 - target) x male mean, and distribute it by "water-filling":
lowest-paid women are raised first, up to a common floor. This minimises the
largest individual shortfall and never raises anyone above the male mean.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Settings
from .metrics import _clean, assessment_key, gap


def _water_fill(values: np.ndarray, budget: float, cap: float) -> np.ndarray:
    """Raise the smallest values to a common level L (<= cap) so that
    sum(max(L - v, 0)) == budget. Returns per-item increases."""
    order = np.argsort(values)
    v = values[order]
    inc = np.zeros_like(v)
    remaining = budget
    level = v[0]
    for i in range(len(v)):
        nxt = min(v[i + 1] if i + 1 < len(v) else cap, cap)
        width = i + 1
        need = (nxt - level) * width
        if need >= remaining:
            level += remaining / width
            remaining = 0
            break
        remaining -= need
        level = nxt
        if level >= cap:
            break
    inc_sorted = np.clip(level - v, 0, None)
    inc[:] = inc_sorted
    out = np.zeros_like(values)
    out[order] = inc
    return out


def simulate(df: pd.DataFrame, settings: Settings, target_gap: float | None = None,
             include_justified: bool = False) -> dict:
    target = settings.gap_threshold * 0.98 if target_gap is None else target_gap
    adjustments = []
    categories = []
    for (entity, cid, label), grp in df.groupby(["legal_entity", "category_id", "category_label"]):
        key = assessment_key(entity, cid)
        m = grp[grp["sex"] == "M"]
        f = grp[grp["sex"] == "F"]
        g = gap(m["hourly_total"], f["hourly_total"])
        if g is None or g <= target:
            continue
        justified = bool(settings.justifications.get(key, "").strip())
        if justified and not include_justified:
            continue
        mean_m = m["hourly_total"].mean()
        required_mean_f = (1 - target) * mean_m
        budget_hourly = (required_mean_f - f["hourly_total"].mean()) * len(f)
        inc = _water_fill(f["hourly_total"].to_numpy(dtype=float), budget_hourly, cap=mean_m)
        annual_cost = 0.0
        for (_, r), di in zip(f.iterrows(), inc):
            if di <= 1e-9:
                continue
            # Implement as a basic salary increase: FTE salary rises by di * full-time hours.
            new_base = r["base_salary"] + di * r["full_time_weekly_hours"] * 52
            cost = di * r["annual_hours_paid"]
            annual_cost += cost
            adjustments.append({
                "employee_id": r["employee_id"],
                "category_id": cid,
                "job_title": r["job_title"],
                "legal_entity": r["legal_entity"],
                "current_base_salary": _clean(r["base_salary"]),
                "proposed_base_salary": _clean(round(new_base, 0)),
                "increase_pct": _clean(di / r["hourly_basic"]),
                "annual_cost": _clean(cost),
            })
        new_f = f["hourly_total"].to_numpy() + inc
        categories.append({
            "key": key,
            "legal_entity": entity,
            "category_id": cid,
            "category_label": label,
            "gap_before": g,
            "gap_after": _clean((mean_m - new_f.mean()) / mean_m),
            "women_adjusted": int((inc > 1e-9).sum()),
            "annual_cost": _clean(annual_cost),
            "justified": justified,
        })

    total_payroll = float((df["hourly_total"] * df["annual_hours_paid"]).sum())
    total_cost = float(sum(c["annual_cost"] or 0 for c in categories))
    return {
        "target_gap": target,
        "categories": categories,
        "adjustments": sorted(adjustments, key=lambda a: -(a["annual_cost"] or 0)),
        "total_annual_cost": total_cost,
        "total_payroll": total_payroll,
        "cost_share_of_payroll": _clean(total_cost / total_payroll) if total_payroll else None,
    }
