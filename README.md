# Pay Transparency Engine

An open, explainable analytics engine and dashboard for the **EU Pay Transparency
Directive (EU) 2023/970**. It turns an HR/payroll extract into:

| Directive requirement | What the tool does |
|---|---|
| **Art. 4**: same work / work of equal value | Scores each role on skills, effort, responsibility and working conditions and groups roles into **categories of workers**, even across job families |
| **Art. 9**: pay gap reporting | Mean and median gaps, basic vs. complementary/variable pay, share receiving bonuses, **pay quartile bands**, gaps per category |
| **Art. 10**: joint pay assessment | Flags each category (per legal entity) with a gap of 5% or more, records objective justifications, and shows which categories still need an assessment |
| Root-cause analysis | **Adjusted gap** (regression) and **Oaxaca-Blinder decomposition**: how much of the gap is explained by category, family, tenure, and so on, and how much is unexplained |
| Remediation | Simulator: cheapest raises that bring every flagged category under the target, with per-employee proposals and total cost |
| **Art. 5 / 6**: pay ranges | Suggested advertised range per category, plus the incumbents who sit below it |
| **Art. 7**: right to information | Generates the individual response letter, with a small-group privacy warning |

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
# open http://localhost:8000  (loads 900 synthetic employees automatically)
# API docs: http://localhost:8000/docs
pytest
```

To use your own data, go to **Data & settings**, download the CSV templates, fill
them in, and upload them. `python scripts/generate_sample_data.py` writes example
files to `data/`.

## Project layout

```
app/
  schema.py          input contract, validation, hourly-pay derivation
  job_evaluation.py  Art. 4 factor scoring -> categories of workers
  metrics.py         Art. 9 indicators, per-category Art. 10 test, outliers
  adjusted.py        regression-adjusted gap + Oaxaca-Blinder decomposition
  remediation.py     water-filling raise simulator
  pay_ranges.py      Art. 5 ranges, Art. 7 response generator
  synthetic.py       realistic demo workforce with planted biases
  store.py           in-memory dataset (swap for a database, see guide)
  main.py            REST API + serves the dashboard
web/                 dashboard (vanilla JS + vendored Chart.js, no build step)
tests/               unit + API tests
docs/GUIDE.md        how to take this from MVP to a product
```

**Read [`docs/GUIDE.md`](docs/GUIDE.md)** next. It covers the data you need to
collect, the methodology decisions you have to make, and a phased roadmap to production.

> This is not legal advice. Each member state transposes the Directive into
> national law with its own details. Validate the methodology with employment
> counsel and your works council.
