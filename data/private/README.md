# Your private data folder

Put your real HR files here. **Git ignores everything in this folder except
this README**, so the files never get committed, pushed to GitHub, or shared.

| File name | Required | What it is |
|---|---|---|
| `employees.xlsx` (or `employees.csv`) | Yes | One row per employee, with the columns in `data/sample_employees.csv` |
| `job_evaluation.xlsx` (or `.csv`) | Recommended | One row per job title with the four factor scores |

When the app starts, it loads these files automatically instead of the demo
data. After editing a file, click **Reload my local files** on the
*Data & settings* tab, or restart the app.

To keep the files somewhere else (for example an encrypted drive), set the
`PAY_DATA_DIR` environment variable before starting the app:

```
set PAY_DATA_DIR=D:\HR\pay-transparency
uvicorn app.main:app
```
