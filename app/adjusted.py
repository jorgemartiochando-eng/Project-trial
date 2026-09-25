"""Adjusted ("unexplained") pay gap and Oaxaca-Blinder decomposition.

Not required by Art. 9 reporting, but essential for the Art. 10 joint pay
assessment: it separates the part of the raw gap explained by legitimate,
gender-neutral factors (role category, tenure, location...) from the part
that remains unexplained.

Caveat surfaced in the UI: controls such as job category can themselves be
shaped by discrimination (e.g. women not being promoted). A small adjusted
gap does not prove the absence of structural inequality.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .metrics import _clean


def _design(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, list[str]]]:
    parts: list[pd.DataFrame] = []
    groups: dict[str, list[str]] = {}

    def add_dummies(col: str, group: str) -> None:
        if df[col].nunique() < 2:
            return
        d = pd.get_dummies(df[col].astype(str), prefix=col, drop_first=True, dtype=float)
        parts.append(d)
        groups[group] = list(d.columns)

    add_dummies("category_id", "Job category (equal value)")
    add_dummies("job_family", "Job family")
    add_dummies("legal_entity", "Legal entity / country")

    tenure = pd.DataFrame({
        "tenure": df["tenure_years"],
        "tenure_sq": df["tenure_years"] ** 2 / 10.0,
    })
    parts.append(tenure)
    groups["Tenure"] = list(tenure.columns)

    pt = pd.DataFrame({"part_time": (df["fte"] < 1).astype(float)})
    if pt["part_time"].nunique() > 1:
        parts.append(pt)
        groups["Part-time"] = ["part_time"]

    if df["performance_rating"].notna().mean() > 0.5:
        perf = df["performance_rating"].fillna(df["performance_rating"].mean())
        parts.append(pd.DataFrame({"performance": perf}))
        groups["Performance rating"] = ["performance"]

    if df["birth_year"].notna().mean() > 0.5:
        age = (pd.Timestamp.today().year - df["birth_year"]).fillna(df["birth_year"].mean())
        parts.append(pd.DataFrame({"age": age}))
        groups["Age"] = ["age"]

    X = pd.concat(parts, axis=1) if parts else pd.DataFrame(index=df.index)
    return X, groups


def adjusted_gap(df: pd.DataFrame) -> dict:
    data = df[df["sex"].isin(["F", "M"])].reset_index(drop=True)
    n_f = int((data["sex"] == "F").sum())
    n_m = int((data["sex"] == "M").sum())
    if n_f < 5 or n_m < 5:
        return {"available": False, "reason": "Need at least 5 women and 5 men for a regression."}

    y = np.log(data["hourly_total"].to_numpy())
    female = (data["sex"] == "F").astype(float).to_numpy()
    X, groups = _design(data)
    cols = ["const", "female"] + list(X.columns)
    M = np.column_stack([np.ones(len(data)), female, X.to_numpy(dtype=float)])

    n, k = M.shape
    if n <= k + 1:
        return {"available": False, "reason": "Too few employees for the number of controls."}

    xtx_inv = np.linalg.pinv(M.T @ M)
    beta = xtx_inv @ M.T @ y
    resid = y - M @ beta
    dof = n - np.linalg.matrix_rank(M)
    sigma2 = float(resid @ resid) / max(dof, 1)
    se = np.sqrt(np.clip(np.diag(xtx_inv) * sigma2, 0, None))
    r2 = 1 - float(resid @ resid) / float(((y - y.mean()) ** 2).sum())

    b_f, se_f = float(beta[1]), float(se[1])
    # Express in the Directive's convention: positive = women paid less.
    adj = 1 - math.exp(b_f)
    ci = (1 - math.exp(b_f + 1.96 * se_f), 1 - math.exp(b_f - 1.96 * se_f))
    t = b_f / se_f if se_f > 0 else float("inf")

    # Oaxaca-Blinder (pooled model incl. group indicator, Fortin/Jann):
    # raw = explained + unexplained
    is_m, is_f = data["sex"] == "M", data["sex"] == "F"
    raw_log = float(y[is_m.to_numpy()].mean() - y[is_f.to_numpy()].mean())
    coef = dict(zip(cols, beta))
    xm = X[is_m].mean()
    xf = X[is_f].mean()
    contributions = []
    explained_total = 0.0
    for group, gcols in groups.items():
        c = float(sum((xm[col] - xf[col]) * coef[col] for col in gcols))
        explained_total += c
        contributions.append({"factor": group, "log_points": c})
    unexplained = raw_log - explained_total
    for c in contributions:
        c["share_of_raw"] = _clean(c["log_points"] / raw_log) if raw_log else None
        c["log_points"] = _clean(c["log_points"])
    contributions.sort(key=lambda c: -abs(c["log_points"] or 0))

    return {
        "available": True,
        "n": n, "n_F": n_f, "n_M": n_m,
        "r_squared": _clean(r2),
        "adjusted_gap": _clean(adj),
        "ci95": [_clean(ci[0]), _clean(ci[1])],
        "significant": bool(abs(t) > 1.96),
        "controls": list(groups.keys()),
        "decomposition": {
            "raw_log_gap": _clean(raw_log),
            "raw_gap_pct": _clean(1 - math.exp(-raw_log)),
            "explained_log": _clean(explained_total),
            "unexplained_log": _clean(unexplained),
            "explained_share": _clean(explained_total / raw_log) if raw_log else None,
            "contributions": contributions,
        },
    }
