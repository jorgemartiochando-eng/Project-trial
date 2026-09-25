"""REST API + static dashboard.

Run:  uvicorn app.main:app --reload   then open http://localhost:8000
"""
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import adjusted, art9, metrics, remediation
from .config import Settings
from .job_evaluation import roles_by_category
from .metrics import _clean, assessment_key
from .pay_ranges import pay_ranges, right_to_information
from .schema import EMPLOYEE_COLUMNS, JOB_EVALUATION_COLUMNS, template_csv
from .store import store

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title="EU Pay Transparency Engine",
    description="Analytics for Directive (EU) 2023/970: pay gap reporting, equal-value categories, "
                "joint pay assessment support, remediation and right-to-information.",
    version="0.1.0",
)

Entity = Query(None, description="Legal entity filter; omit or 'ALL' for the whole group.")


def _df(entity: str | None):
    df, meta = store.frame(entity)
    if df.empty:
        raise HTTPException(404, f"No employees for entity {entity!r}")
    return df, meta


# ---------------------------------------------------------------- dataset
@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/dataset")
def dataset_info():
    df, meta = store.frame()
    ds = store.dataset
    return {
        "source": ds.source,
        "employees": len(df),
        "legal_entities": sorted(df["legal_entity"].unique().tolist()),
        "job_families": sorted(df["job_family"].unique().tolist()),
        "categories": int(df["category_id"].nunique()),
        "category_method": meta,
        "validation": ds.validation.to_dict(),
    }


@app.post("/api/dataset/sample")
def load_sample(n: int = Query(900, ge=50, le=20000), seed: int = 7):
    res = store.load_sample(n=n, seed=seed)
    return {"validation": res.to_dict(), **dataset_info()}


async def _read_csv(f: UploadFile) -> pd.DataFrame:
    content = await f.read()
    try:
        return pd.read_csv(io.BytesIO(content), sep=None, engine="python")
    except Exception as exc:  # noqa: BLE001 - surface parser errors to the user
        raise HTTPException(400, f"Could not parse {f.filename}: {exc}") from exc


@app.post("/api/dataset/upload")
async def upload(employees: UploadFile = File(...), job_evaluation: UploadFile | None = File(None)):
    emp = await _read_csv(employees)
    je = await _read_csv(job_evaluation) if job_evaluation is not None and job_evaluation.filename else None
    res = store.load(emp, je, f"upload: {employees.filename}")
    if not res.ok:
        raise HTTPException(422, res.to_dict())
    return {"validation": res.to_dict(), **dataset_info()}


@app.get("/api/templates/{name}", response_class=PlainTextResponse)
def template(name: str):
    if name == "employees.csv":
        return template_csv(EMPLOYEE_COLUMNS)
    if name == "job_evaluation.csv":
        return template_csv(JOB_EVALUATION_COLUMNS)
    raise HTTPException(404)


@app.get("/api/schema")
def schema():
    fmt = lambda cols: [{"name": k, "required": r, "description": d} for k, (r, d) in cols.items()]  # noqa: E731
    return {"employees": fmt(EMPLOYEE_COLUMNS), "job_evaluation": fmt(JOB_EVALUATION_COLUMNS)}


# --------------------------------------------------------------- settings
@app.get("/api/settings")
def get_settings() -> Settings:
    return store.settings


@app.put("/api/settings")
def put_settings(settings: Settings) -> Settings:
    store.update_settings(settings)
    return store.settings


class Justification(BaseModel):
    text: str


@app.put("/api/justifications/{legal_entity}/{category_id}")
def put_justification(legal_entity: str, category_id: str, body: Justification):
    key = assessment_key(legal_entity, category_id)
    s = store.settings.model_copy(deep=True)
    if body.text.strip():
        s.justifications[key] = body.text.strip()
    else:
        s.justifications.pop(key, None)
    store.update_settings(s)
    return {"key": key, "justification": s.justifications.get(key, "")}


# -------------------------------------------------------------- analytics
@app.get("/api/report")
def report(entity: str | None = Entity):
    """Everything an Art. 9 report needs, for one legal entity or the group."""
    df, meta = _df(entity)
    cats = metrics.category_gaps(df, store.settings)
    return {
        "entity": entity or "ALL",
        "pay_basis": store.settings.pay_basis,
        "indicators": metrics.headline_indicators(df),
        "quartiles": metrics.quartile_bands(df),
        "categories": cats,
        "category_method": meta,
        "assessment_required": [c["key"] for c in cats if c["status"] == "assessment_required"],
        "by_entity": metrics.breakdown(df, "legal_entity"),
        "by_family": metrics.breakdown(df, "job_family"),
        "by_level": metrics.breakdown(df, "job_level"),
    }


@app.get("/api/art9")
def art9_indicators(entity: str | None = Entity,
                    group_by: str = Query("category", pattern="^(category|job_level)$")):
    """Art. 9(1)(a)-(g) with the formulas and the numbers that went into them."""
    df, _ = _df(entity)
    return art9.indicators(df, store.settings, group_by)


@app.get("/api/export/art9.csv")
def export_art9(entity: str | None = Entity,
                group_by: str = Query("category", pattern="^(category|job_level)$")):
    df, _ = _df(entity)
    r = art9.indicators(df, store.settings, group_by)
    unit = r["pay_basis"]
    rows = []
    for x in "abcd":
        rows.append({"indicator": x, "title": r["titles"][x], "scope": entity or "ALL", "group": "",
                     "value_pct": r[x]["gap_pct"], "men": r[x]["men"], "women": r[x]["women"],
                     "n_men": r[x]["n_men"], "n_women": r[x]["n_women"], "unit": unit, "formula": r["formulas"][x]})
    e = r["e"]
    rows.append({"indicator": "e", "title": r["titles"]["e"], "scope": entity or "ALL", "group": "men",
                 "value_pct": e["men_pct"], "n_men": e["men_total"], "formula": r["formulas"]["e"]})
    rows.append({"indicator": "e", "title": r["titles"]["e"], "scope": entity or "ALL", "group": "women",
                 "value_pct": e["women_pct"], "n_women": e["women_total"], "formula": r["formulas"]["e"]})
    for q in r["f"]:
        rows.append({"indicator": "f", "title": r["titles"]["f"], "scope": entity or "ALL",
                     "group": f"Q{q['quartile']} {q['label']}: women", "value_pct": q["women_pct"], "formula": r["formulas"]["f"]})
        rows.append({"indicator": "f", "title": r["titles"]["f"], "scope": entity or "ALL",
                     "group": f"Q{q['quartile']} {q['label']}: men", "value_pct": q["men_pct"], "formula": r["formulas"]["f"]})
    for g in r["g"]:
        for x in "abcd":
            rows.append({"indicator": f"g-{x}", "title": f"{r['titles']['g']}: {r['titles'][x]}", "scope": g["legal_entity"],
                         "group": g["group"], "value_pct": g[f"{x}_gap_pct"], "men": g[f"{x}_men"], "women": g[f"{x}_women"],
                         "n_men": g["men"], "n_women": g["women"], "unit": unit})
    buf = io.StringIO()
    pd.DataFrame(rows).convert_dtypes().to_csv(buf, index=False)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=art9_indicators_{entity or 'ALL'}.csv"},
    )


@app.get("/api/categories/roles")
def category_roles(entity: str | None = Entity):
    df, _ = _df(entity)
    return roles_by_category(df)


@app.get("/api/adjusted")
def adjusted_gap(entity: str | None = Entity):
    df, _ = _df(entity)
    return adjusted.adjusted_gap(df)


@app.get("/api/outliers")
def outliers(entity: str | None = Entity, max_ratio: float = Query(0.9, gt=0, le=1)):
    df, _ = _df(entity)
    return metrics.outliers(df, max_ratio)


class RemediationRequest(BaseModel):
    target_gap: float | None = None
    include_justified: bool = False


@app.post("/api/remediation")
def remediation_sim(body: RemediationRequest, entity: str | None = Entity):
    df, _ = _df(entity)
    return remediation.simulate(df, store.settings, body.target_gap, body.include_justified)


@app.get("/api/pay-ranges")
def ranges(entity: str | None = Entity):
    df, _ = _df(entity)
    return pay_ranges(df)


@app.get("/api/employees")
def employees(entity: str | None = Entity, category_id: str | None = None, limit: int = 5000):
    df, _ = _df(entity)
    if category_id:
        df = df[df["category_id"] == category_id]
    cols = ["employee_id", "sex", "job_title", "job_family", "job_level", "legal_entity", "category_id",
            "fte", "base_salary", "pay_basic", "pay_complementary", "pay_variable", "pay_total", "tenure_years"]
    recs = df[cols].head(limit).to_dict(orient="records")
    return [{k: _clean(v) for k, v in r.items()} for r in recs]


@app.get("/api/employees/{employee_id}/right-to-information")
def rti(employee_id: str):
    df, _ = store.frame()
    out = right_to_information(df, employee_id, store.settings)
    if out is None:
        raise HTTPException(404, "Employee not found")
    return out


@app.get("/api/export/categories.csv")
def export_categories(entity: str | None = Entity):
    df, _ = _df(entity)
    out = pd.DataFrame(metrics.category_gaps(df, store.settings))
    out["job_families"] = out["job_families"].str.join("; ")
    buf = io.StringIO()
    out.to_csv(buf, index=False)
    return StreamingResponse(
        iter([buf.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=pay_gap_categories_{entity or 'ALL'}.csv"},
    )


# ------------------------------------------------------------------ web UI
if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")
