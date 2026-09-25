"""Gender-neutral job evaluation -> "categories of workers" (Art. 4 & Art. 3(1)(h)).

The Directive requires comparing workers performing *the same work or work of
equal value*, even across job families. We score every role on the four
Art. 4(4) factors, compute a weighted 0-100 score and group roles with similar
scores into categories. A nurse and a technician with the same score end up
in the same category and must be paid comparably.

If no job evaluation is supplied we fall back to job_level as a (weaker) proxy
and say so in the output.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import Settings

FACTORS = ["skills", "effort", "responsibility", "working_conditions"]


def score_roles(job_eval: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    w = settings.weights.normalised()
    df = job_eval.copy()
    # each factor is 1..5 -> map to 0..1 then weight -> 0..100
    df["evaluation_score"] = sum(((df[f] - 1) / 4) * w[f] for f in FACTORS) * 100
    df["evaluation_score"] = df["evaluation_score"].round(1)
    band = np.floor(df["evaluation_score"] / settings.band_width).astype(int)
    lo = band * settings.band_width
    hi = lo + settings.band_width
    df["category_id"] = [f"C{b + 1:02d}" for b in band]
    df["category_label"] = [f"C{b + 1:02d} ({l:g}-{h:g} pts)" for b, l, h in zip(band, lo, hi)]
    return df


def assign_categories(
    employees: pd.DataFrame, job_eval: pd.DataFrame | None, settings: Settings
) -> tuple[pd.DataFrame, dict]:
    """Return employees with category_id/category_label and metadata about the method."""
    emp = employees.copy()
    if job_eval is None or job_eval.empty:
        emp["category_id"] = [f"L{lvl:02d}" for lvl in emp["job_level"]]
        emp["category_label"] = [f"Level {lvl}" for lvl in emp["job_level"]]
        emp["evaluation_score"] = np.nan
        return emp, {
            "method": "job_level_proxy",
            "note": "No job evaluation supplied: categories are job levels. This does not capture "
                    "work of equal value across job families; upload a job evaluation to comply with Art. 4.",
            "unmatched_titles": [],
        }

    scored = score_roles(job_eval, settings)
    emp = emp.merge(
        scored[["job_title", "evaluation_score", "category_id", "category_label"]],
        on="job_title", how="left",
    )
    unmatched = sorted(emp.loc[emp["category_id"].isna(), "job_title"].unique().tolist())
    if unmatched:
        # Keep them visible rather than dropping: bucket by level and report.
        mask = emp["category_id"].isna()
        emp.loc[mask, "category_id"] = [f"U-L{lvl:02d}" for lvl in emp.loc[mask, "job_level"]]
        emp.loc[mask, "category_label"] = [f"Unevaluated, level {lvl}" for lvl in emp.loc[mask, "job_level"]]
    return emp, {
        "method": "job_evaluation",
        "note": "Categories derived from weighted gender-neutral job evaluation scores.",
        "weights": settings.weights.normalised(),
        "band_width": settings.band_width,
        "unmatched_titles": unmatched,
    }


def roles_by_category(employees: pd.DataFrame) -> list[dict]:
    g = employees.groupby(["category_id", "category_label"])
    out = []
    for (cid, label), grp in g:
        roles = (
            grp.groupby(["job_title", "job_family"]).size().reset_index(name="headcount")
            .sort_values("headcount", ascending=False)
        )
        out.append({
            "category_id": cid,
            "category_label": label,
            "job_families": sorted(grp["job_family"].unique().tolist()),
            "roles": roles.to_dict(orient="records"),
        })
    return sorted(out, key=lambda r: r["category_id"])
