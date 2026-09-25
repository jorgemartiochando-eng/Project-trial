# How the code works, and how to change it yourself

This guide is for someone who is not a professional developer. It explains
what happens when you open the dashboard, which file does what, and how to
make common changes on your own, including using your real data without it
ever leaving your laptop.

---

## 1. The big picture

The app has two halves that talk to each other, both running on your laptop:

```
 ┌─────────────────────────────┐        ┌──────────────────────────────────────────┐
 │  YOUR BROWSER               │        │  PYTHON PROGRAM (the black window)       │
 │  http://localhost:8000      │        │                                          │
 │                             │  asks  │  main.py      receives the question      │
 │  web/index.html  the page   │ ─────► │     │                                    │
 │  web/styles.css  the looks  │        │  store.py     holds the employee data    │
 │  web/app.js      the logic  │ ◄───── │     │                                    │
 │  (draws tables and charts)  │ answers│  schema.py    cleans it, computes pay    │
 └─────────────────────────────┘ (JSON) │  job_evaluation.py  groups roles         │
                                        │  metrics.py / art9.py / ...  calculates  │
                                        └──────────────────────────────────────────┘
```

- **The browser half (`web/`)** only displays things. It has no salary
  logic. When you click a tab, it asks the Python half for numbers.
- **The Python half (`app/`)** does all the work: it reads the data,
  checks it, converts pay to monthly FTE, groups roles into categories, and
  calculates every indicator.
- `localhost` means "this computer". Nothing goes over the internet.

## 2. What happens, step by step

1. You run `uvicorn app.main:app`. Python starts `app/main.py`.
2. You open `http://localhost:8000`. The browser downloads `web/index.html`,
   `styles.css` and `app.js` from the Python program.
3. `app.js` asks `/api/dataset`: "what data do we have?"
4. The first time, `store.py` looks for **your files** in `data/private/`
   (`employees.xlsx` or `.csv`). If there are none, it uses made-up demo data
   from `synthetic.py`.
5. `schema.py` **validates** the data: it renames known column names,
   rejects impossible values and lists warnings. Then it **derives pay
   fields**, such as monthly FTE pay and variable pay.
6. `job_evaluation.py` gives each role a score and puts it in a **category of
   workers** (work of equal value).
7. When you open a tab, `app.js` asks a matching question, for example
   `/api/art9?entity=DE GmbH`. `main.py` passes it to the right calculation
   file, which returns numbers as JSON (plain text data).
8. `app.js` turns those numbers into tables and charts.

You can see every question the page can ask, and try them, at
**http://localhost:8000/docs**.

## 3. File map: what to open for what

| File | What it does | Open it when you want to... |
|---|---|---|
| `web/index.html` | Page structure: tabs, titles, explanatory text | Change a heading, a sentence, or a tab name |
| `web/styles.css` | Colours, fonts, spacing (colours are at the top, under `:root`) | Change colours or sizes |
| `web/app.js` | Fetches numbers and draws tables and charts | Change a table column or a chart |
| `app/main.py` | The list of questions the page can ask (`@app.get(...)`) | Add a new page or export |
| `app/config.py` | Default settings: 5% threshold, factor weights, monthly/hourly | Change a default |
| `app/schema.py` | Expected columns, column-name translations, pay formulas | Match your HR export, or add a pay component |
| `app/data_io.py` | Reads Excel/CSV and finds your private folder | Change where data is read from |
| `app/store.py` | Keeps the loaded data in memory | Rarely |
| `app/job_evaluation.py` | Scores roles and forms categories | Change how categories are built |
| `app/art9.py` | Art. 9 indicators a) to g), with formulas; `explore()` powers the indicator picker, filters and "Dive in" tables | Change an Art. 9 definition, or add a filter (edit `FILTERS`) |
| `app/metrics.py` | Overview numbers, per-category gaps, Art. 10 status | Change the Art. 10 logic |
| `app/adjusted.py` | Regression and "explain the gap" | Add or remove an explanatory factor |
| `app/remediation.py` | Raise simulator | Change how raises are distributed |
| `app/pay_ranges.py` | Pay ranges and the Art. 7 letter | Change the letter's wording |
| `tests/test_engine.py` | Automatic checks of the formulas | Run after every change |

## 4. Starting the app the easy way

Double-click **`start.bat`** in the project folder. It downloads the latest
changes (`git pull`), sets up or repairs Python if needed (so moving the
folder is fine), installs new libraries only when something changed, starts
the app and opens the browser. Close the black window to stop the app.

## 5. How to make a change yourself

**Tools.** Install **Visual Studio Code** (free, from code.visualstudio.com).
Choose File → Open Folder and select your `pay-transparency` folder. You get
all the files on the left and a built-in terminal (Terminal → New Terminal).

**Workflow.**
1. Start the app with auto-reload, so it restarts by itself whenever you
   save a Python file:
   ```
   .venv\Scripts\activate
   uvicorn app.main:app --reload
   ```
2. Edit a file and save it with **Ctrl+S**.
3. Refresh the browser with **Ctrl+F5**.
4. If something breaks, the black window shows the error in red and names
   the file and line number. To undo all your changes to a file:
   `git checkout -- path\to\file`.
5. Check you didn't break a formula by running the tests:
   `pip install -r requirements-dev.txt` (once), then `pytest`.

### Worked examples

**a) Change a text on the page.** Open `web/index.html`, press Ctrl+F, search
for the sentence, edit it, save, and refresh the browser.

**b) Change the default threshold from 5% to 4%.** In `app/config.py`:
```python
gap_threshold: float = Field(0.05, gt=0, lt=1)   # change 0.05 to 0.04
```

**c) Your HR export uses different column names.** In `app/schema.py`, find
`COLUMN_ALIASES` and add a line: *your name → app name*. Write your name in
lower case, with underscores instead of spaces:
```python
    "salary_2026": "base_salary",
    "business_unit": "legal_entity",
```

**d) Change a colour.** In `web/styles.css`, at the top: `--brand-navy`,
`--brand-blue`, `--women`, `--men`...

**e) Change the Art. 7 letter.** In `app/pay_ranges.py`, edit the text inside
`letter = (...)`. Keep the `{...}` parts: they insert the numbers.

**f) Include employees without variable pay in indicators b) and d).** In
`app/art9.py`, inside `core()`, replace `vm` and `vf` in the `("b", ...)`
and `("d", ...)` lines with `m` and `f`.

## 6. Using your real data safely

**Where to put it:** `data/private/employees.xlsx`, plus optionally
`data/private/job_evaluation.xlsx`. The app loads them automatically at
startup. After editing them, click **Reload my local files** on the
*Data & settings* tab.

**The format:** the same columns as `data/sample_employees.csv`. Open that
file in Excel to see an example. Your column names can differ (see 4c), and
FTE can be written as 0.8 or as 80.

**Why it is safe:**

| Where could data go? | What happens |
|---|---|
| Internet | Nothing is sent. The app only talks to `localhost` (your own laptop) |
| GitHub | `data/private/` and all `.xlsx`/`.xls` files are listed in `.gitignore`, so `git` never uploads them, even by accident |
| Claude | Claude only sees what you type or attach in the chat |

**Good habits:**
- Use pseudonymous IDs (E0001…) instead of names in the employee file.
- When asking Claude for help, share **column names and error messages**, not
  rows of real data. Error messages only contain employee IDs.
- Before any `git commit`, run `git status` and check that no data file is listed.
- Keep your laptop's disk encrypted (BitLocker on Windows). To keep the data
  on another drive, see `data/private/README.md`.
