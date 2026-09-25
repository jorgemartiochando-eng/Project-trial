"""Synthetic workforce generator for demos and tests.

Deliberately bakes in the patterns seen in real EU data so the dashboard has
something to find: vertical segregation (fewer women at senior levels),
more part-time work among women, an unexplained base-pay penalty in some job
families, and lower variable pay for women in Sales.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FAMILIES = {
    #              titles by level 1..6                                               base@L1  female share  bonus
    "Engineering": (["Junior Engineer", "Engineer", "Senior Engineer", "Staff Engineer",
                     "Principal Engineer", "Engineering Director"], 42000, 0.25, 0.08),
    "Sales": (["Sales Associate", "Account Executive", "Senior Account Executive",
               "Sales Manager", "Regional Sales Director", "VP Sales"], 34000, 0.45, 0.30),
    "Operations": (["Warehouse Operative", "Shift Lead", "Operations Supervisor",
                    "Operations Manager", "Site Director", "Head of Operations"], 28000, 0.35, 0.05),
    "Customer Support": (["Support Agent", "Senior Support Agent", "Support Team Lead",
                          "Support Manager", "Head of Support", "VP Customer Experience"], 29000, 0.65, 0.05),
    "Finance": (["Finance Assistant", "Accountant", "Senior Accountant", "Finance Manager",
                 "Finance Director", "CFO"], 36000, 0.55, 0.10),
    "People": (["HR Assistant", "HR Generalist", "HR Business Partner", "HR Manager",
                "HR Director", "Chief People Officer"], 33000, 0.75, 0.08),
}

ENTITIES = {
    # entity: (country, pay multiplier, full-time weekly hours, weight)
    "DE GmbH": ("DE", 1.10, 40, 0.30),
    "FR SAS": ("FR", 1.00, 35, 0.20),
    "ES SL": ("ES", 0.75, 40, 0.20),
    "NL BV": ("NL", 1.05, 38, 0.15),
    "IE Ltd": ("IE", 1.05, 39, 0.15),
}

LEVEL_WEIGHTS = np.array([0.24, 0.28, 0.22, 0.14, 0.08, 0.04])
LEVEL_STEP = 1.28  # pay growth per level

# Factor scores (1-5) by family, adjusted by level in job_evaluation().
FAMILY_FACTORS = {
    #                    skills effort resp working_conditions
    "Engineering":       (2.4, 2.0, 1.4, 1.2),
    "Sales":             (1.8, 2.2, 1.5, 1.6),
    "Operations":        (1.4, 2.8, 1.5, 3.0),
    "Customer Support":  (1.5, 2.4, 1.3, 2.2),
    "Finance":           (2.2, 2.0, 1.5, 1.2),
    "People":            (1.9, 2.1, 1.5, 1.4),
}


def job_evaluation() -> pd.DataFrame:
    rows = []
    for fam, (titles, *_rest) in FAMILIES.items():
        s, e, r, w = FAMILY_FACTORS[fam]
        for lvl, title in enumerate(titles, start=1):
            rows.append({
                "job_title": title,
                "skills": min(5.0, round(s + 0.5 * (lvl - 1), 1)),
                "effort": min(5.0, round(e + 0.3 * (lvl - 1), 1)),
                "responsibility": min(5.0, round(r + 0.7 * (lvl - 1), 1)),
                "working_conditions": min(5.0, round(w + 0.1 * (lvl - 1), 1)),
            })
    return pd.DataFrame(rows)


def generate(n: int = 900, seed: int = 7, reference_year: int = 2026) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    fam_names = list(FAMILIES)
    fam_weights = np.array([0.22, 0.18, 0.2, 0.18, 0.1, 0.12])
    ent_names = list(ENTITIES)
    ent_weights = np.array([v[3] for v in ENTITIES.values()])

    rows = []
    for i in range(n):
        fam = rng.choice(fam_names, p=fam_weights / fam_weights.sum())
        titles, base_l1, female_share, bonus_target = FAMILIES[fam]
        level = int(rng.choice(np.arange(1, 7), p=LEVEL_WEIGHTS))
        # vertical segregation: women's share shrinks with seniority
        p_f = np.clip(female_share * (1.15 - 0.09 * level), 0.05, 0.95)
        u = rng.random()
        sex = "X" if u < 0.01 else ("F" if u < 0.01 + p_f * 0.99 else "M")
        entity = rng.choice(ent_names, p=ent_weights / ent_weights.sum())
        country, mult, ft_hours, _ = ENTITIES[entity]

        tenure = float(np.clip(rng.gamma(2.0, 2.2) + level * 0.6, 0.1, 30))
        hire_date = pd.Timestamp(f"{reference_year}-06-30") - pd.Timedelta(days=int(tenure * 365.25))
        age = int(np.clip(22 + level * 3.5 + tenure * 0.6 + rng.normal(0, 4), 19, 66))
        perf = int(np.clip(round(rng.normal(3.1, 0.8)), 1, 5))

        base = base_l1 * LEVEL_STEP ** (level - 1) * mult
        base *= 1 + 0.012 * min(tenure, 15)
        base *= 1 + 0.02 * (perf - 3)
        base *= rng.lognormal(0, 0.07)
        if sex == "F" and fam in ("Engineering", "Sales", "Operations"):
            base *= 0.94  # unexplained penalty the tool should surface
        elif sex == "F":
            base *= 0.985

        p_pt = 0.28 if sex == "F" else 0.06
        fte = float(rng.choice([0.5, 0.6, 0.8])) if rng.random() < p_pt else 1.0

        gets_bonus = rng.random() < (0.9 if fam == "Sales" else 0.55 + 0.07 * level)
        bonus = 0.0
        if gets_bonus:
            b = bonus_target * rng.lognormal(0, 0.35) * (1 + 0.1 * (perf - 3))
            if sex == "F" and fam == "Sales":
                b *= 0.8
            bonus = base * fte * b
        allowance = 0.0
        if fam == "Operations" and level <= 3 and rng.random() < 0.7:
            allowance = 2400 * fte * mult * rng.lognormal(0, 0.2)  # shift premium
        if level >= 5:
            allowance += 6000 * fte  # car allowance
        bik = 1500.0 if level >= 4 and rng.random() < 0.5 else 0.0

        rows.append({
            "employee_id": f"E{i + 1:05d}",
            "sex": sex,
            "job_title": titles[level - 1],
            "job_family": fam,
            "job_level": level,
            "legal_entity": entity,
            "country": country,
            "department": fam,
            "fte": fte,
            "full_time_weekly_hours": ft_hours,
            "base_salary": round(base, 0),
            "variable_pay": round(bonus, 0),
            "allowances": round(allowance, 0),
            "benefits_in_kind": bik,
            "hire_date": hire_date.date().isoformat(),
            "birth_year": reference_year - age,
            "performance_rating": perf,
        })
    return pd.DataFrame(rows)
