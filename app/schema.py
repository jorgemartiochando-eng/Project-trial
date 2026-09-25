"""Input data contract, validation and derived pay fields.

Directive (EU) 2023/970 compares pay on a like-for-like basis (Art. 3 & 9) and
splits it into "ordinary basic wage or salary" and "complementary or variable
components". Everything downstream works off the derived pay_* columns
produced by :func:`prepare_employees` (monthly FTE or hourly).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

WEEKS_PER_YEAR = 52.0

# name -> (required, description)
EMPLOYEE_COLUMNS: dict[str, tuple[bool, str]] = {
    "employee_id": (True, "Unique, stable identifier (pseudonymised is fine)."),
    "sex": (True, "F, M, or X (X/other is counted but excluded from binary gap maths)."),
    "job_title": (True, "Role name. Must match job_title in the job evaluation file if one is used."),
    "job_family": (True, "e.g. Engineering, Sales, Operations."),
    "job_level": (True, "Integer grade/level (1 = most junior)."),
    "legal_entity": (True, "Reporting unit, usually one per member state (e.g. 'DE GmbH')."),
    "country": (True, "ISO country code of the employment contract."),
    "department": (False, "Free text."),
    "fte": (True, "Contracted working time as a fraction of full time (0 < fte <= 1)."),
    "full_time_weekly_hours": (True, "Full-time weekly hours for this contract (e.g. 40)."),
    "base_salary": (True, "Annual ordinary basic salary at 100% FTE, reporting currency."),
    "variable_pay": (False, "Annual variable pay actually paid (bonus, commission). Default 0."),
    "allowances": (False, "Annual fixed complementary pay actually paid (allowances, shift premia). Default 0."),
    "benefits_in_kind": (False, "Annual value of benefits in kind (car, housing...). Default 0."),
    "hire_date": (True, "YYYY-MM-DD."),
    "birth_year": (False, "Used only as an optional control in the adjusted gap model."),
    "performance_rating": (False, "Numeric rating, used only as an optional control."),
}

JOB_EVALUATION_COLUMNS: dict[str, tuple[bool, str]] = {
    "job_title": (True, "Role name, matching the employee file."),
    "skills": (True, "Score 1-5: education, experience, soft & technical skills required."),
    "effort": (True, "Score 1-5: mental, physical and psychological effort."),
    "responsibility": (True, "Score 1-5: responsibility for people, budget, outcomes, safety."),
    "working_conditions": (True, "Score 1-5: environment, hazards, unsocial hours, stress."),
}

NUMERIC_EMPLOYEE_COLS = [
    "job_level", "fte", "full_time_weekly_hours", "base_salary", "variable_pay",
    "allowances", "benefits_in_kind", "birth_year", "performance_rating",
]
OPTIONAL_ZERO_COLS = ["variable_pay", "allowances", "benefits_in_kind"]


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings}


# Your HR system's column names -> the names this app expects.
# Add a line here if your export uses a different header (matching ignores
# upper/lower case and treats spaces like underscores).
COLUMN_ALIASES: dict[str, str] = {
    "id": "employee_id",
    "employee_number": "employee_id",
    "personnel_number": "employee_id",
    "gender": "sex",
    "position": "job_title",
    "title": "job_title",
    "job_function": "job_family",
    "grade": "job_level",
    "level": "job_level",
    "company": "legal_entity",
    "entity": "legal_entity",
    "fte_%": "fte",
    "weekly_hours": "full_time_weekly_hours",
    "annual_base_salary": "base_salary",
    "base_pay": "base_salary",
    "bonus": "variable_pay",
    "start_date": "hire_date",
    "date_of_hire": "hire_date",
}


def _normalise_headers(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    cols = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    df.columns = [COLUMN_ALIASES.get(c, c) for c in cols]
    return df


def validate_employees(raw: pd.DataFrame) -> tuple[pd.DataFrame, ValidationResult]:
    """Coerce types and collect data-quality issues. Never silently drops rows
    without reporting it."""
    res = ValidationResult()
    df = _normalise_headers(raw)

    missing = [c for c, (req, _) in EMPLOYEE_COLUMNS.items() if req and c not in df.columns]
    if missing:
        res.errors.append(f"Missing required columns: {', '.join(missing)}")
        return df, res

    for col in OPTIONAL_ZERO_COLS:
        if col not in df.columns:
            df[col] = 0.0
    for col in ("department", "birth_year", "performance_rating"):
        if col not in df.columns:
            df[col] = np.nan

    df["employee_id"] = df["employee_id"].astype(str).str.strip()
    dupes = df["employee_id"][df["employee_id"].duplicated()].unique()
    if len(dupes):
        res.errors.append(f"Duplicate employee_id values: {', '.join(map(str, dupes[:10]))}")

    df["sex"] = df["sex"].astype(str).str.strip().str.upper().replace(
        {"FEMALE": "F", "WOMAN": "F", "W": "F", "MALE": "M", "MAN": "M", "H": "M"}
    )
    bad_sex = ~df["sex"].isin(["F", "M", "X"])
    if bad_sex.any():
        res.warnings.append(f"{int(bad_sex.sum())} rows with unrecognised sex value were set to X.")
        df.loc[bad_sex, "sex"] = "X"
    n_x = int((df["sex"] == "X").sum())
    if n_x:
        res.warnings.append(
            f"{n_x} employees with sex X are included in headcounts but excluded from "
            "female/male gap calculations, as the Directive defines gaps between female and male workers."
        )

    for col in NUMERIC_EMPLOYEE_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in OPTIONAL_ZERO_COLS:
        df[col] = df[col].fillna(0.0)
    if df["fte"].max() > 1.5:  # FTE given as a percentage (e.g. 80) rather than a fraction
        df["fte"] = df["fte"] / 100
        res.warnings.append("fte looked like a percentage (values above 1), so it was divided by 100.")

    for col in ("job_title", "job_family", "legal_entity", "country"):
        df[col] = df[col].astype(str).str.strip()
    df["department"] = df["department"].fillna("").astype(str)

    df["hire_date"] = pd.to_datetime(df["hire_date"], errors="coerce")

    invalid = (
        df["base_salary"].isna() | (df["base_salary"] <= 0)
        | df["fte"].isna() | (df["fte"] <= 0) | (df["fte"] > 1.0001)
        | df["full_time_weekly_hours"].isna() | (df["full_time_weekly_hours"] <= 0)
        | df["job_level"].isna() | df["hire_date"].isna()
    )
    if invalid.any():
        ids = df.loc[invalid, "employee_id"].head(10).tolist()
        res.warnings.append(
            f"{int(invalid.sum())} rows excluded for invalid base_salary / fte / hours / level / hire_date "
            f"(e.g. {', '.join(ids)})."
        )
        df = df.loc[~invalid].copy()

    neg = (df[OPTIONAL_ZERO_COLS] < 0).any(axis=1)
    if neg.any():
        res.warnings.append(f"{int(neg.sum())} rows have negative complementary pay; check for clawbacks.")

    df["job_level"] = df["job_level"].astype(int)
    return df.reset_index(drop=True), res


def validate_job_evaluation(raw: pd.DataFrame) -> tuple[pd.DataFrame, ValidationResult]:
    res = ValidationResult()
    df = _normalise_headers(raw)
    missing = [c for c, (req, _) in JOB_EVALUATION_COLUMNS.items() if req and c not in df.columns]
    if missing:
        res.errors.append(f"Job evaluation file missing columns: {', '.join(missing)}")
        return df, res
    df["job_title"] = df["job_title"].astype(str).str.strip()
    for col in ("skills", "effort", "responsibility", "working_conditions"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
        out = df[col].isna() | (df[col] < 1) | (df[col] > 5)
        if out.any():
            res.errors.append(f"Column {col} must be numeric between 1 and 5 ({int(out.sum())} bad rows).")
    if df["job_title"].duplicated().any():
        res.errors.append("Duplicate job_title rows in job evaluation file.")
    return df, res


PAY_BASES = ("monthly", "hourly")


def prepare_employees(df: pd.DataFrame, reference_date: pd.Timestamp | None = None,
                      pay_basis: str = "monthly") -> pd.DataFrame:
    """Add derived pay fields used by all metrics.

    All comparisons use *full-time-equivalent* pay so that part-time and
    full-time workers are comparable, as the Directive requires. The unit is
    either gross monthly FTE pay (default) or gross hourly pay (the Directive's
    reference unit). Within one employer both give the same gap percentages,
    because full-time hours are the same for everyone.

    Basis-neutral columns (in the chosen unit):
      pay_basic, pay_complementary, pay_variable, pay_total
      pay_to_annual    multiply a pay amount by this to get the annual cost for this person
      pay_to_base_fte  multiply a pay amount by this to get the annual FTE base salary change
    """
    if pay_basis not in PAY_BASES:
        raise ValueError(f"pay_basis must be one of {PAY_BASES}")
    out = df.copy()
    ref = reference_date or pd.Timestamp.today().normalize()

    annual_hours_full_time = out["full_time_weekly_hours"] * WEEKS_PER_YEAR
    annual_hours_paid = annual_hours_full_time * out["fte"]

    complementary = out["variable_pay"] + out["allowances"] + out["benefits_in_kind"]

    out["annual_hours_paid"] = annual_hours_paid
    # base_salary is quoted at 100% FTE, so the hourly rate does not depend on FTE.
    out["hourly_basic"] = out["base_salary"] / annual_hours_full_time
    # Complementary amounts are actually-paid amounts, so divide by hours actually paid.
    out["hourly_complementary"] = complementary / annual_hours_paid
    out["hourly_variable"] = out["variable_pay"] / annual_hours_paid
    out["hourly_total"] = out["hourly_basic"] + out["hourly_complementary"]

    # Monthly full-time-equivalent pay: actually-paid amounts are scaled up by 1/fte.
    out["monthly_basic"] = out["base_salary"] / 12
    out["monthly_complementary"] = complementary / (12 * out["fte"])
    out["monthly_variable"] = out["variable_pay"] / (12 * out["fte"])
    out["monthly_total"] = out["monthly_basic"] + out["monthly_complementary"]

    prefix = "monthly" if pay_basis == "monthly" else "hourly"
    for part in ("basic", "complementary", "variable", "total"):
        out[f"pay_{part}"] = out[f"{prefix}_{part}"]
    if pay_basis == "monthly":
        out["pay_to_annual"] = 12 * out["fte"]
        out["pay_to_base_fte"] = 12.0
    else:
        out["pay_to_annual"] = annual_hours_paid
        out["pay_to_base_fte"] = annual_hours_full_time

    out["annual_complementary"] = complementary
    out["annual_total_fte"] = out["base_salary"] + complementary / out["fte"]
    out["receives_complementary"] = complementary > 0
    out["receives_variable"] = out["variable_pay"] > 0
    out["tenure_years"] = ((ref - out["hire_date"]).dt.days / 365.25).clip(lower=0)
    return out


def template_csv(columns: dict[str, tuple[bool, str]]) -> str:
    return ",".join(columns.keys()) + "\n"
