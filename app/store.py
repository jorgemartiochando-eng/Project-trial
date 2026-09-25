"""In-memory dataset store (single tenant, MVP).

Production replacement: PostgreSQL with one schema/tenant, encryption at rest,
row-level access control and an immutable audit log (see docs/GUIDE.md).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field

import pandas as pd

from . import synthetic
from .config import Settings
from .job_evaluation import assign_categories
from .schema import ValidationResult, prepare_employees, validate_employees, validate_job_evaluation


@dataclass
class Dataset:
    employees: pd.DataFrame
    job_evaluation: pd.DataFrame | None
    source: str
    validation: ValidationResult = field(default_factory=ValidationResult)


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.settings = Settings()
        self.dataset: Dataset | None = None
        self._cache: tuple[pd.DataFrame, dict] | None = None

    # ---- loading -------------------------------------------------------
    def load(self, employees_raw: pd.DataFrame, job_eval_raw: pd.DataFrame | None, source: str) -> ValidationResult:
        emp, res = validate_employees(employees_raw)
        je = None
        if job_eval_raw is not None:
            je, res_je = validate_job_evaluation(job_eval_raw)
            res.errors += res_je.errors
            res.warnings += res_je.warnings
        if not res.ok:
            return res
        if len(emp) == 0:
            res.errors.append("No valid employee rows after validation.")
            return res
        with self._lock:
            self.dataset = Dataset(emp, je, source, res)
            self._cache = None
        return res

    def load_sample(self, n: int = 900, seed: int = 7) -> ValidationResult:
        return self.load(synthetic.generate(n=n, seed=seed), synthetic.job_evaluation(), f"synthetic (n={n}, seed={seed})")

    def update_settings(self, settings: Settings) -> None:
        with self._lock:
            self.settings = settings
            self._cache = None

    # ---- derived frame -------------------------------------------------
    def frame(self, entity: str | None = None) -> tuple[pd.DataFrame, dict]:
        if self.dataset is None:
            self.load_sample()
        with self._lock:
            if self._cache is None:
                ref = pd.Timestamp(self.settings.reference_date) if self.settings.reference_date else None
                prepared = prepare_employees(self.dataset.employees, ref, self.settings.pay_basis)
                self._cache = assign_categories(prepared, self.dataset.job_evaluation, self.settings)
            df, meta = self._cache
        if entity and entity != "ALL":
            df = df[df["legal_entity"] == entity]
        return df, meta


store = Store()
