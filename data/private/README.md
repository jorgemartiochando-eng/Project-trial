# Your private data folder

Put your real HR files here. **Git ignores everything in this folder except
this README**, so the files never get committed, pushed to GitHub, or shared.

| File name | Required | What it is |
|---|---|---|
| `employees.xlsx` (or `employees.csv`) | Yes | One row per employee, with the columns in `data/sample_employees.csv` |
| `job_evaluation.xlsx` (or `.csv`) | Recommended | One row per job title with the four factor scores |

Your company export works as it is. These headers are recognised:

| Your column | Used as |
|---|---|
| User ID | employee_id |
| Gender (M / F) | sex |
| Position title | job_title |
| Job classification | job_family |
| Job level | job_level (numbers or codes like "L3") |
| Code(company) | legal_entity (the country follows from it) |
| FTE | fte (0.5 or 50 both work) |
| Base salary | base_salary (**annual**, at 100% FTE) |
| Recruit date | hire_date |

No hours column is needed: FTE 1 = 160.33 hours a month. Optional extra columns,
such as variable pay, allowances, location and cost center, make more indicators
available. See the data dictionary on the *Data & settings* tab.

When the app starts, it loads these files automatically instead of the demo
data. After editing a file, click **Reload my local files** on the
*Data & settings* tab, or restart the app.

To keep the files somewhere else (for example an encrypted drive), set the
`PAY_DATA_DIR` environment variable before starting the app:

```
set PAY_DATA_DIR=D:\HR\pay-transparency
uvicorn app.main:app
```
