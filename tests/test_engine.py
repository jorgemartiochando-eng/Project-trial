import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import synthetic
from app.adjusted import adjusted_gap
from app.config import Settings
from app.job_evaluation import assign_categories
from app.main import app
from app.metrics import category_gaps, gap, headline_indicators, quartile_bands
from app.remediation import _water_fill, simulate
from app.schema import prepare_employees, validate_employees


def _emp(rows):
    base = {
        "job_family": "Ops", "job_level": 1, "legal_entity": "DE GmbH", "country": "DE",
        "fte": 1.0, "full_time_weekly_hours": 40, "variable_pay": 0, "allowances": 0,
        "hire_date": "2020-01-01", "job_title": "Clerk",
    }
    df = pd.DataFrame([{**base, **r} for r in rows])
    df, res = validate_employees(df)
    assert res.ok, res.errors
    df = prepare_employees(df, pd.Timestamp("2026-01-01"))
    df, _ = assign_categories(df, None, Settings())
    return df


def test_gap_formula_matches_directive_definition():
    # (male - female) / male
    assert gap(pd.Series([100.0]), pd.Series([80.0])) == pytest.approx(0.2)
    assert gap(pd.Series([100.0]), pd.Series([]), "mean") is None


def test_hourly_pay_normalises_part_time():
    df = _emp([
        {"employee_id": "1", "sex": "F", "base_salary": 52000, "fte": 0.5, "variable_pay": 5200},
        {"employee_id": "2", "sex": "M", "base_salary": 52000, "fte": 1.0, "variable_pay": 10400},
    ])
    # identical FTE salary and pro-rata bonus -> identical hourly pay, zero gap
    assert df.loc[0, "hourly_total"] == pytest.approx(df.loc[1, "hourly_total"])
    assert headline_indicators(df)["mean_gap"] == pytest.approx(0.0)


def test_validation_reports_missing_columns_and_normalises_sex():
    df, res = validate_employees(pd.DataFrame({"employee_id": [1]}))
    assert not res.ok and "Missing required columns" in res.errors[0]
    df = synthetic.generate(n=20, seed=1)
    df.loc[0, "sex"] = "female"
    df.loc[1, "sex"] = "??"
    out, res = validate_employees(df)
    assert out.loc[0, "sex"] == "F" and out.loc[1, "sex"] == "X"
    assert res.ok


def test_quartiles_cover_everyone_once():
    df = _emp([{"employee_id": str(i), "sex": "F" if i % 2 else "M", "base_salary": 30000 + i * 1000} for i in range(40)])
    q = quartile_bands(df)
    assert [x["headcount"] for x in q] == [10, 10, 10, 10]
    for x in q:
        assert x["share_F"] + x["share_M"] == pytest.approx(1.0)


def test_category_threshold_and_justification():
    rows = [{"employee_id": f"m{i}", "sex": "M", "base_salary": 50000} for i in range(3)]
    rows += [{"employee_id": f"f{i}", "sex": "F", "base_salary": 45000} for i in range(3)]
    df = _emp(rows)
    s = Settings()
    [cat] = category_gaps(df, s)
    assert cat["mean_gap"] == pytest.approx(0.1)
    assert cat["status"] == "assessment_required"
    s.justifications[cat["key"]] = "Documented, gender-neutral reason"
    assert category_gaps(df, s)[0]["status"] == "justified"


def test_water_fill_raises_lowest_first_and_spends_budget():
    inc = _water_fill(np.array([10.0, 12.0, 20.0]), budget=4.0, cap=25.0)
    assert inc.sum() == pytest.approx(4.0)
    assert inc[2] == 0  # highest untouched
    assert 10 + inc[0] == pytest.approx(12 + inc[1])  # common floor


def test_remediation_brings_gaps_to_target():
    emp = synthetic.generate(n=600, seed=3)
    df, _ = validate_employees(emp)
    df = prepare_employees(df)
    df, _ = assign_categories(df, synthetic.job_evaluation(), Settings())
    res = simulate(df, Settings(), target_gap=0.04)
    assert res["categories"], "synthetic data should contain gaps to remediate"
    for c in res["categories"]:
        assert c["gap_after"] == pytest.approx(0.04, abs=1e-6)
    assert res["total_annual_cost"] > 0


def test_adjusted_gap_detects_planted_penalty():
    rng = np.random.default_rng(0)
    rows = []
    for i in range(400):
        sex = "F" if i % 2 else "M"
        lvl = int(rng.integers(1, 5))
        pay = 30000 * 1.3 ** (lvl - 1) * rng.lognormal(0, 0.03) * (0.9 if sex == "F" else 1.0)
        rows.append({"employee_id": str(i), "sex": sex, "job_level": lvl, "base_salary": pay})
    out = adjusted_gap(_emp(rows))
    assert out["available"]
    assert out["adjusted_gap"] == pytest.approx(0.10, abs=0.01)
    assert out["significant"]


def test_api_end_to_end():
    c = TestClient(app)
    c.post("/api/dataset/sample?n=300&seed=2")
    r = c.get("/api/report").json()
    assert r["indicators"]["headcount"]["total"] == 300
    assert len(r["quartiles"]) == 4
    rti = c.get("/api/employees/E00001/right-to-information").json()
    assert "Article 7" in rti["letter"]
    assert c.get("/api/employees/nope/right-to-information").status_code == 404
    csv = "employee_id,sex\n1,F\n"
    bad = c.post("/api/dataset/upload", files={"employees": ("e.csv", csv, "text/csv")})
    assert bad.status_code == 422
