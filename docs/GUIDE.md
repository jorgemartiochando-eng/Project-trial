# Building an EU pay transparency product: the guide

This guide goes with the code in this repo. It explains what the Directive asks
for, what the MVP already does, the data you need to gather, the methodology
decisions you have to own, and how to grow this into production software.

> **Not legal advice.** Directive (EU) 2023/970 had to be transposed by
> **7 June 2026**, and member states differ in the details (and some are late).
> Treat the national law as the source of truth and get sign-off from
> employment counsel and your works council for every methodology choice below.

---

## 1. The Directive in one page, mapped to features

| Article | Obligation | In the MVP | Still to build |
|---|---|---|---|
| 3 | "Pay" = basic salary **plus any other consideration in cash or in kind** | basic, variable, allowances and benefits in kind columns | overtime, pensions, stock plans |
| 4 | Pay structures must allow comparing **work of equal value** using objective, gender-neutral criteria: skills, effort, responsibility, working conditions | Factor-weighted job evaluation, configurable weights and band width | Job-evaluation workflow UI, versioning, evaluator sign-off |
| 5 | Candidates get the **initial pay or its range** before interview. No asking about **pay history**. Gender-neutral job titles | Suggested range per category | Push ranges to your ATS, check job-ad wording |
| 6 | Make the **criteria for pay, pay levels and progression** easily accessible | Not yet | Policy publishing page / employee portal |
| 7 | Workers can request **their pay and average pay by sex** for their category; answer **within 2 months**; no pay-secrecy clauses; remind staff of the right every year | Letter generator with small-group warning | Request intake, SLA tracking, audit trail, annual reminder |
| 9 | **Report** gap indicators (a)–(g) | All indicators, per legal entity | Official output format per member state, submission |
| 10 | **Joint pay assessment** when a category gap is **≥ 5%**, not justified by objective criteria and not remedied **within 6 months** | Flag, justification log, decomposition, remediation simulator | Assessment workflow with worker representatives, action plan tracking |
| 12 | Data protection: use personal data only for these purposes | In-memory only, pseudonymised IDs | See §6 |

**Reporting timeline (Art. 9)**, counted per employer (legal entity):

| Headcount | Frequency | First report due |
|---|---|---|
| 250+ | Annually | 7 June 2027 (covering 2026) |
| 150–249 | Every 3 years | 7 June 2027 |
| 100–149 | Every 3 years | 7 June 2031 |
| < 100 | Voluntary, unless national law requires it | |

---

## 2. How the engine computes things

**Hourly pay.** The Directive compares gross *hourly* pay, which makes full-time
and part-time staff comparable:

```
hourly_basic         = base_salary (at 100% FTE) / (full_time_weekly_hours × 52)
hourly_complementary = (variable + allowances + benefits_in_kind) / (fte × full_time_weekly_hours × 52)
hourly_total         = hourly_basic + hourly_complementary
gap                  = (mean_men − mean_women) / mean_men      # positive = men paid more
```

**Categories of workers.** Each role gets a 1–5 score on the four Art. 4 factors.
The weighted total is mapped to 0–100 points, and roles are grouped into bands
(default: 10 points wide). A Support Team Lead and a Shift Lead with similar
scores land in the same category and are compared with each other.

**Everything that has legal effect is scoped per legal entity.** That covers the
Art. 10 trigger, justifications, remediation, pay ranges and Art. 7 comparators.
The group view is only for management insight. Pooling Spain and Germany would
make country pay levels look like gender gaps.

**Adjusted gap.** OLS on `log(hourly_total)` with a female indicator plus
controls for category, job family, entity, tenure (and tenure²), part-time,
performance and age. `adjusted gap = 1 − exp(β_female)`. The
**Oaxaca-Blinder decomposition** splits the raw log gap into the part explained
by differences in those characteristics and the part left unexplained.

**Remediation.** For each flagged category, the engine computes the minimum
total raise that brings women's mean to `(1 − target) × men's mean`. It then
"water-fills": the lowest-paid women are raised first, up to a shared floor,
and nobody is raised above the men's mean. The raise is costed on actual hours paid.

---

## 3. The data you need to collect

Start with **one legal entity and one reference year**. Collecting data is the
hard part of this project; the calculations are easy.

### Employee extract (one row per worker employed in the reference period)

| Field | Typical source | Pitfalls |
|---|---|---|
| `employee_id` | HRIS | Use a stable pseudonymous key, not a name |
| `sex` | HRIS | Missing or non-binary values: the Directive counts women and men only; keep others visible in headcounts |
| `job_title`, `job_family`, `job_level` | HRIS / job architecture | Titles are often inconsistent. Clean them before running job evaluation |
| `legal_entity`, `country` | HRIS / payroll | The reporting unit is the employer, not the group |
| `fte`, `full_time_weekly_hours` | HRIS / time system | Full-time hours differ by country and collective agreement (35h in FR, 40h in DE...) |
| `base_salary` (annualised at 100% FTE) | Payroll | Use the reporting currency. Convert FX at a documented rate |
| `variable_pay` (actually paid in the year) | Payroll | Decide between "paid in year" and "earned for year" and stay consistent |
| `allowances`, `benefits_in_kind` | Payroll / benefits | Car, housing, shift premia, on-call. The Art. 3 definition of pay is broad |
| `hire_date` | HRIS | Needed for tenure. Handle re-hires |
| `performance_rating`, `birth_year` (optional) | Performance system | Controls only. Ratings can themselves be biased, so review them |

### Job evaluation (one row per role)

Run a structured, documented exercise: HR, line managers and ideally worker
representatives score each role on the four factors (1–5). Keep **the reasons
behind each score**, because you will need to defend them in a joint pay
assessment. Established methods (point-factor schemes, or commercial ones like
Hay/Korn Ferry or Mercer IPE) can be mapped onto the four factors.

### Data-quality checklist before trusting the numbers

- [ ] Headcounts match the payroll register for each entity
- [ ] Total pay reconciles with the payroll ledger (within ±1%)
- [ ] Every job title has a job evaluation (see the "unevaluated" warning in the UI)
- [ ] Part-time staff have the right FTE, and hours are not double-counted
- [ ] Leavers and joiners are handled consistently (annualise or pro-rate)
- [ ] A single currency, with the conversion documented

---

## 4. Methodology decisions you must own (and document)

| Decision | MVP default | Alternatives |
|---|---|---|
| Reference period | Annual amounts, as supplied | Pay snapshot on a date + variable pay for 12 months |
| Who is included | Everyone in the file | Exclude apprentices/interns? Only staff employed on the snapshot date? |
| Factor weights | Skills 35%, Responsibility 30%, Effort 20%, Conditions 15% | Negotiate with worker representatives |
| Category band width | 10 points | Narrower = more precise comparisons but smaller groups |
| Gap test | Mean total hourly pay, |gap| ≥ 5% | Also test basic pay and complementary pay separately |
| Small groups | Warn below 3 of either sex | Check national guidance on disclosure |
| Justification standard | Free text per entity × category | Structured reasons + evidence attachments + approver |

A decision log with dates and approvers is a feature in its own right. Auditors
and courts will ask for it, and Art. 18 places the burden of proof on the employer.

---

## 5. Roadmap: from MVP to product

### Phase 0: prove it on your data (2–4 weeks)
1. Extract one entity for one year, filling in the `employees.csv` template.
2. Build a first job evaluation for its roles.
3. Run the tool and reconcile the numbers with payroll. Fix data issues.
4. Show the results to HR leadership and legal. Agree on the methodology (§4).

### Phase 1: make it safe to use with real data (1–2 months)
- **Persistence**: PostgreSQL (one schema or row-level security per tenant),
  datasets versioned by reference year, immutable snapshots for each report.
- **Auth**: SSO (SAML/OIDC via Entra ID or Okta). Role-based access with roles
  such as HR admin, comp analyst, legal, worker representative (aggregates
  only), and auditor (read-only).
- **Audit log**: who uploaded what, who changed weights or justifications, and when.
- **Security**: encryption at rest and in transit, hosting in the EU, backups,
  secrets management, dependency scanning.
- **GDPR**: a DPIA, data minimisation (no names), retention rules, records of
  processing. Aggregate views must not let anyone infer an individual's pay.

### Phase 2: workflows (2–3 months)
- **Joint pay assessment workspace** (Art. 10): per flagged category, the gap
  analysis, the decomposition, justification evidence, the remediation plan,
  comments from worker representatives, sign-off, and a 6-month remediation
  deadline tracker.
- **Art. 7 request desk**: an intake form, a 2-month SLA timer, generated
  responses, delivery log, and the annual reminder to staff.
- **Report builder**: PDF/Excel output in each member state's format. Keep
  national rules (thresholds, deadlines, extra indicators) in a rules table
  keyed by country, not in code.
- **Pay ranges → ATS**: publish category ranges to job requisitions
  (Greenhouse, Workday Recruiting, SmartRecruiters…) and block pay-history questions.

### Phase 3: integrations and scale
- **HRIS/payroll connectors** replacing CSV: Workday, SAP SuccessFactors,
  Personio, HiBob, BambooHR, ADP, or a unified API such as Merge or Finch.
- **Frontend**: move `web/` to React/TypeScript once the workflows grow.
  The API contract (`/docs`) stays the same.
- **Continuous monitoring**: re-run on every payroll cycle and alert on new
  hires or promotions that widen a category gap ("pay equity check at offer time").
- **Scenario planning**: model the gap effect of the merit budget before the
  annual review.
- **Multi-language employee portal** for Art. 6 criteria and Art. 7 responses.

---

## 6. Extending the code

| You want to... | Change |
|---|---|
| Add a pay component (e.g. overtime) | `EMPLOYEE_COLUMNS` and `prepare_employees` in `app/schema.py` |
| Change how categories are formed | `app/job_evaluation.py` (e.g. use your existing grades) |
| Add a control to the adjusted-gap model | `_design()` in `app/adjusted.py` |
| Cap individual raises or phase them over years | `simulate()` in `app/remediation.py` |
| Add a country-specific rule | Add a rules table and read it in `metrics.category_gaps` |
| Replace in-memory storage | `app/store.py`. Keep the `frame()` interface so analytics stay unchanged |

Run `pytest` after every change. The tests pin the Directive's formulas, so
keep them passing and add a test for each new rule.

---

## 7. Known limitations of the MVP

- Single tenant, in memory: data is lost on restart and there is no login. **Do
  not deploy it on the open internet with real salary data.**
- A single reporting currency is assumed.
- Partial-year employees are not pro-rated automatically.
- The adjusted-gap model is a transparent OLS model, not a causal analysis.
  Controls such as category can hide discrimination in promotions.
- Remediation can propose large individual raises where a category is
  heterogeneous. Treat that as a signal to revisit the job evaluation, not only
  as a pay action.
