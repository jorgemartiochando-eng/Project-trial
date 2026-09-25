/* Pay Transparency Engine — dashboard (vanilla JS + Chart.js). */
"use strict";

const state = { entity: "ALL", report: null, settings: null, remediation: null, charts: {}, selectedCat: null };

// ------------------------------------------------------------------ helpers
const $ = (sel) => document.querySelector(sel);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pct = (x, d = 1) => (x === null || x === undefined ? "–" : `${(x * 100).toFixed(d)}%`);
const num = (x, d = 0) => (x === null || x === undefined ? "–" : Number(x).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const gapCell = (g) => `<td class="num ${g > 0 ? "pos" : g < 0 ? "neg" : ""}">${pct(g)}</td>`;
const monthly = () => !state.settings || state.settings.pay_basis !== "hourly";
const money = (x) => num(x, monthly() ? 0 : 2);
const unitShort = () => (monthly() ? "/month" : "/h");
const unitLong = () => (monthly() ? "gross monthly pay (FTE)" : "gross hourly pay");
const entityParam = () => (state.entity && state.entity !== "ALL" ? `?entity=${encodeURIComponent(state.entity)}` : "");

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail; } catch (_) { /* not json */ }
    throw Object.assign(new Error(typeof detail === "string" ? detail : JSON.stringify(detail)), { detail });
  }
  return res.json();
}

function toast(msg) {
  const t = $("#tooltip-toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.add("hidden"), 2500);
}

function table(el, headers, rows) {
  const th = headers.map((h) => `<th class="${h.num ? "num" : ""}">${esc(h.label ?? h)}</th>`).join("");
  el.innerHTML = `<thead><tr>${th}</tr></thead><tbody>${rows.join("")}</tbody>`;
}

function tile(label, value, sub = "") {
  return `<div class="tile"><div class="label">${esc(label)}</div><div class="value">${value}</div><div class="sub">${sub}</div></div>`;
}

function statusBadge(s) {
  const labels = { ok: "Below threshold", justified: "Justified", assessment_required: "Joint assessment required", not_comparable: "No comparator" };
  const icons = { ok: "✓", justified: "!", assessment_required: "✕", not_comparable: "–" };
  return `<span class="status ${s}"><span class="dot"></span>${icons[s]} ${labels[s]}</span>`;
}

function downloadCsv(filename, rows) {
  if (!rows.length) return;
  const cols = Object.keys(rows[0]);
  const csv = [cols.join(",")].concat(rows.map((r) => cols.map((c) => JSON.stringify(r[c] ?? "")).join(","))).join("\n");
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
  a.download = filename;
  a.click();
}

// -------------------------------------------------------------- chart setup
function chartDefaults() {
  Chart.defaults.font.family = 'Calibri, Carlito, "Segoe UI", Arial, sans-serif';
  Chart.defaults.font.size = 13;
  Chart.defaults.color = cssVar("--ink-2");
  Chart.defaults.borderColor = cssVar("--grid");
  Chart.defaults.plugins.legend.labels.boxWidth = 10;
  Chart.defaults.plugins.legend.labels.boxHeight = 10;
  Chart.defaults.plugins.tooltip.backgroundColor = cssVar("--ink");
  Chart.defaults.plugins.tooltip.titleColor = cssVar("--page");
  Chart.defaults.plugins.tooltip.bodyColor = cssVar("--page");
  Chart.defaults.maintainAspectRatio = false;
}

function makeChart(key, canvasId, config) {
  if (state.charts[key]) state.charts[key].destroy();
  state.charts[key] = new Chart(document.getElementById(canvasId), config);
}

const thresholdLine = (value) => ({
  id: "threshold",
  afterDatasetsDraw(chart) {
    const { ctx, chartArea, scales } = chart;
    const y = scales.y.getPixelForValue(value);
    ctx.save();
    ctx.strokeStyle = cssVar("--critical");
    ctx.setLineDash([4, 4]);
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(chartArea.left, y); ctx.lineTo(chartArea.right, y); ctx.stroke();
    ctx.restore();
  },
});

// ------------------------------------------------------------------ loading
async function loadDataset() {
  const ds = await api("/api/dataset");
  $("#source").textContent = `${ds.employees} employees · ${ds.source}`;
  $("#private-dir").textContent = ds.private_dir;
  const sel = $("#entity");
  const current = state.entity;
  sel.innerHTML = `<option value="ALL">All entities (group)</option>` +
    ds.legal_entities.map((e) => `<option value="${esc(e)}">${esc(e)}</option>`).join("");
  sel.value = ds.legal_entities.includes(current) ? current : "ALL";
  state.entity = sel.value;
  const note = $("#method-note");
  const m = ds.category_method;
  let text = m.method === "job_level_proxy" ? m.note : "";
  if (m.unmatched_titles && m.unmatched_titles.length) {
    text += ` ${m.unmatched_titles.length} job titles have no job evaluation and were grouped by level: ${m.unmatched_titles.slice(0, 8).join(", ")}…`;
  }
  note.textContent = text;
  note.classList.toggle("hidden", !text);
  renderValidation(ds.validation);
  return ds;
}

async function refresh() {
  const [report, settings] = await Promise.all([api(`/api/report${entityParam()}`), api("/api/settings")]);
  state.report = report;
  state.settings = settings;
  renderOverview();
  renderCategories();
  renderSettings();
  const active = document.querySelector(".tabs button.active").dataset.tab;
  await loadTab(active);
}

async function loadTab(tab) {
  if (tab === "art9") await renderArt9();
  if (tab === "explain") await renderExplain();
  if (tab === "remediation") await runRemediation();
  if (tab === "ranges") await renderRanges();
  if (tab === "data") await renderDataTab();
  if (tab === "categories") await renderOutliers();
  if (tab === "rti") await fillRtiIds();
}

// ----------------------------------------------------------------- overview
function renderOverview() {
  const r = state.report;
  const ind = r.indicators;
  const nAssess = r.assessment_required.length;
  $("#tiles").innerHTML = [
    tile("Mean gender pay gap", pct(ind.mean_gap), monthly() ? "Monthly FTE pay, Art. 9(1)(a)" : "Hourly pay, Art. 9(1)(a)"),
    tile("Median gender pay gap", pct(ind.median_gap), "Art. 9(1)(c)"),
    tile("Mean gap, basic pay only", pct(ind.mean_gap_basic), `Median ${pct(ind.median_gap_basic)}`),
    tile("Categories needing joint assessment", `${nAssess} / ${r.categories.length}`,
      nAssess ? "✕ Gap ≥ threshold, no justification" : "✓ None"),
    tile("Headcount", num(ind.headcount.total), `${num(ind.headcount.F)} women · ${num(ind.headcount.M)} men · ${num(ind.headcount.X)} other`),
  ].join("");

  const women = cssVar("--women"), men = cssVar("--men");
  const q = r.quartiles;
  makeChart("quartiles", "chart-quartiles", {
    type: "bar",
    data: {
      labels: q.map((x) => x.label),
      datasets: [
        { label: "Women", data: q.map((x) => x.share_F * 100), backgroundColor: women, borderRadius: 4, borderColor: cssVar("--surface"), borderWidth: 1 },
        { label: "Men", data: q.map((x) => x.share_M * 100), backgroundColor: men, borderRadius: 4, borderColor: cssVar("--surface"), borderWidth: 1 },
      ],
    },
    options: {
      indexAxis: "y",
      scales: { x: { stacked: true, max: 100, ticks: { callback: (v) => `${v}%` } }, y: { stacked: true, grid: { display: false } } },
      plugins: {
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.parsed.x.toFixed(1)}% (${money(q[c.dataIndex].min_pay)}–${money(q[c.dataIndex].max_pay)}${unitShort()})` } },
      },
    },
  });

  const ent = r.by_entity.filter((e) => e.mean_gap !== null);
  makeChart("entities", "chart-entities", {
    type: "bar",
    data: {
      labels: ent.map((e) => e.legal_entity),
      datasets: [{ label: "Mean gap", data: ent.map((e) => e.mean_gap * 100), backgroundColor: cssVar("--accent"), borderRadius: 4, maxBarThickness: 48 }],
    },
    options: {
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (c) => `Mean ${c.parsed.y.toFixed(1)}% · median ${pct(ent[c.dataIndex].median_gap)} · ${ent[c.dataIndex].headcount_F + ent[c.dataIndex].headcount_M} staff` } },
      },
      scales: { y: { ticks: { callback: (v) => `${v}%` }, suggestedMin: 0 }, x: { grid: { display: false } } },
    },
    plugins: [thresholdLine(state.settings.gap_threshold * 100)],
  });

  table($("#comp-table"), ["Indicator", { label: "Women", num: true }, { label: "Men", num: true }], [
    `<tr><td>Receiving complementary/variable pay</td><td class="num">${pct(ind.share_receiving_complementary.F)}</td><td class="num">${pct(ind.share_receiving_complementary.M)}</td></tr>`,
    `<tr><td>Receiving variable pay (bonus/commission)</td><td class="num">${pct(ind.share_receiving_variable.F)}</td><td class="num">${pct(ind.share_receiving_variable.M)}</td></tr>`,
    `<tr><td>Mean ${unitLong()}</td><td class="num">${money(ind.mean_pay.F)}</td><td class="num">${money(ind.mean_pay.M)}</td></tr>`,
    `<tr><td>Mean gap in all complementary pay (variable + allowances + benefits)</td><td class="num" colspan="2">${pct(ind.mean_gap_complementary)}</td></tr>`,
    `<tr><td>Median gap in all complementary pay</td><td class="num" colspan="2">${pct(ind.median_gap_complementary)}</td></tr>`,
  ]);

  table($("#obligations"), ["Legal entity", { label: "Headcount", num: true }, "Obligation"], r.by_entity.map((e) => {
    const n = e.headcount_F + e.headcount_M;
    let ob = "Voluntary (member state may require)";
    if (n >= 250) ob = "Annual report · first due 7 June 2027 (2026 data)";
    else if (n >= 150) ob = "Every 3 years · first due 7 June 2027";
    else if (n >= 100) ob = "Every 3 years · first due 7 June 2031";
    return `<tr><td>${esc(e.legal_entity)}</td><td class="num">${num(n)}</td><td>${ob}</td></tr>`;
  }));

  const bd = (rows, key, label) => table(rows.el, [label, { label: "Women", num: true }, { label: "Men", num: true }, { label: "% women", num: true }, { label: "Mean gap", num: true }, { label: "Part-time W/M", num: true }],
    rows.data.map((x) => `<tr><td>${esc(x[key])}</td><td class="num">${x.headcount_F}</td><td class="num">${x.headcount_M}</td><td class="num">${pct(x.share_F, 0)}</td>${gapCell(x.mean_gap)}<td class="num">${pct(x.part_time_share_F, 0)} / ${pct(x.part_time_share_M, 0)}</td></tr>`));
  bd({ el: $("#by-family"), data: r.by_family }, "job_family", "Job family");
  bd({ el: $("#by-level"), data: r.by_level }, "job_level", "Level");
}

// ------------------------------------------------------------------- art. 9
async function renderArt9() {
  const groupBy = $("#art9-group").value;
  const sep = entityParam() ? "&" : "?";
  const r = await api(`/api/art9${entityParam()}${sep}group_by=${groupBy}`);
  const scope = state.entity === "ALL" ? "all legal entities combined (for official reporting, select one legal entity)" : state.entity;
  $("#art9-intro").textContent = `Scope: ${scope}. Pay amounts are ${unitLong()} in the reporting currency. ` +
    "Remuneration = basic pay + variable pay + allowances + benefits in kind. Variable pay (b, d) is compared among the workers who received it. " +
    "A positive gap means men are paid more.";
  $("#export-art9").href = `/api/export/art9.csv${entityParam()}${sep}group_by=${groupBy}`;

  const g = (v) => (v === null || v === undefined ? "–" : `${v.toFixed(1)}%`);
  const calc = (x, word) => x.men === null || x.women === null ? "Not enough data"
    : `(${money(x.men)} − ${money(x.women)}) / ${money(x.men)} × 100 = <strong>${g(x.gap_pct)}</strong><br>` +
      `${word} of men ${money(x.men)} (${num(x.n_men)} men) · women ${money(x.women)} (${num(x.n_women)} women)`;
  const card = (k, body) => `<div class="card"><div class="ind-head"><span class="ind-letter">${k}</span><h3>${esc(r.titles[k])}</h3></div>
    <p class="formula">${esc(r.formulas[k])}</p>${body}</div>`;
  const gapCard = (k, word) => card(k, `<div class="ind-value ${r[k].gap_pct > 0 ? "pos" : r[k].gap_pct < 0 ? "neg" : ""}">${g(r[k].gap_pct)}</div>
    <div class="calc">${calc(r[k], word)}</div>`);
  const e = r.e;
  $("#art9-cards").innerHTML = [
    gapCard("a", "Mean"), gapCard("b", "Mean"), gapCard("c", "Median"), gapCard("d", "Median"),
    card("e", `<div class="ind-value split"><div>${g(e.men_pct)}<small>of men</small></div><div>${g(e.women_pct)}<small>of women</small></div></div>
      <div class="calc">Men: ${num(e.men_receiving)} / ${num(e.men_total)} × 100 = <strong>${g(e.men_pct)}</strong><br>
      Women: ${num(e.women_receiving)} / ${num(e.women_total)} × 100 = <strong>${g(e.women_pct)}</strong></div>`),
  ].join("");

  $("#art9-f-title").textContent = r.titles.f;
  $("#art9-f-formula").textContent = r.formulas.f;
  const w = cssVar("--women"), m = cssVar("--men");
  table($("#art9-f"), ["Quartile", { label: "Pay range", num: true }, { label: "Workers", num: true }, { label: "% women", num: true }, { label: "% men", num: true }, "Women / men"],
    r.f.map((q) => `<tr><td>Q${q.quartile} · ${esc(q.label)}</td><td class="num">${money(q.min_pay)} – ${money(q.max_pay)}</td><td class="num">${num(q.headcount)}</td>
      <td class="num">${g(q.women_pct)}</td><td class="num">${g(q.men_pct)}</td>
      <td><div class="minibar" title="Women ${g(q.women_pct)} · Men ${g(q.men_pct)}"><span style="width:${q.women_pct}%;background:${w}"></span><span style="width:${q.men_pct}%;background:${m}"></span></div></td></tr>`));

  $("#art9-g-title").textContent = r.titles.g;
  $("#art9-g-formula").textContent = r.formulas.g;
  const gc = (v) => `<td class="num ${v > 0 ? "pos" : v < 0 ? "neg" : ""}">${g(v)}</td>`;
  table($("#art9-g"), ["Entity", groupBy === "job_level" ? "Job level" : "Category", { label: "Women", num: true }, { label: "Men", num: true },
    { label: "a) Mean gap", num: true }, { label: "b) Mean variable gap", num: true }, { label: "c) Median gap", num: true }, { label: "d) Median variable gap", num: true }],
    r.g.map((x) => `<tr><td>${esc(x.legal_entity)}</td><td>${esc(x.group)}${x.small_group ? ' <span class="tag" title="Fewer than the minimum group size of one sex">small</span>' : ""}</td>
      <td class="num">${x.women}</td><td class="num">${x.men}</td>${gc(x.a_gap_pct)}${gc(x.b_gap_pct)}${gc(x.c_gap_pct)}${gc(x.d_gap_pct)}</tr>`));
}

// --------------------------------------------------------------- categories
function renderCategories() {
  const r = state.report;
  $("#thr-label").textContent = pct(state.settings.gap_threshold, 0);
  $("#export-cats").href = `/api/export/categories.csv${entityParam()}`;
  table($("#cat-table"), [
    "Entity", "Category", "Job families", { label: "W", num: true }, { label: "M", num: true },
    { label: `Mean ${unitShort()} W`, num: true }, { label: `Mean ${unitShort()} M`, num: true },
    { label: "Mean gap", num: true }, { label: "Median gap", num: true }, { label: "Basic", num: true }, { label: "Complem.", num: true }, "Status",
  ], r.categories.map((c) => `<tr data-cat="${esc(c.key)}" class="${c.key === state.selectedCat ? "selected" : ""}">
      <td>${esc(c.legal_entity)}</td><td>${esc(c.category_label)}${c.small_group ? ' <span class="tag" title="Fewer than the minimum group size of one sex">small</span>' : ""}</td>
      <td class="small">${esc(c.job_families.join(", "))}</td>
      <td class="num">${c.headcount_F}</td><td class="num">${c.headcount_M}</td>
      <td class="num">${money(c.mean_pay_F)}</td><td class="num">${money(c.mean_pay_M)}</td>
      ${gapCell(c.mean_gap)}${gapCell(c.median_gap)}${gapCell(c.mean_gap_basic)}${gapCell(c.mean_gap_complementary)}
      <td>${statusBadge(c.status)}</td></tr>`));
  document.querySelectorAll("#cat-table tbody tr").forEach((tr) => tr.addEventListener("click", () => selectCategory(tr.dataset.cat)));
  if (state.selectedCat && r.categories.some((c) => c.key === state.selectedCat)) selectCategory(state.selectedCat);
  else $("#cat-detail").classList.add("hidden");
}

async function selectCategory(key) {
  state.selectedCat = key;
  document.querySelectorAll("#cat-table tbody tr").forEach((tr) => tr.classList.toggle("selected", tr.dataset.cat === key));
  const cat = state.report.categories.find((c) => c.key === key);
  const cid = cat.category_id;
  const ent = encodeURIComponent(cat.legal_entity);
  const [emps, roles] = await Promise.all([
    api(`/api/employees?entity=${ent}&category_id=${encodeURIComponent(cid)}`),
    api(`/api/categories/roles?entity=${ent}`),
  ]);
  $("#cat-detail").classList.remove("hidden");
  $("#cat-detail-title").textContent = `${cat.legal_entity} · ${cat.category_label} — mean gap ${pct(cat.mean_gap)}`;
  $("#justification").value = cat.justification || "";
  $("#just-saved").textContent = "";

  const roleInfo = roles.find((x) => x.category_id === cid);
  table($("#cat-roles"), ["Role", "Family", { label: "Headcount", num: true }], (roleInfo ? roleInfo.roles : []).map((r) =>
    `<tr><td>${esc(r.job_title)}</td><td>${esc(r.job_family)}</td><td class="num">${r.headcount}</td></tr>`));

  // deterministic jitter so dots don't move on re-render
  const jitter = (id) => { let h = 0; for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) >>> 0; return ((h % 1000) / 1000 - 0.5) * 0.5; };
  const pts = (sex, x) => emps.filter((e) => e.sex === sex).map((e) => ({ x: x + jitter(e.employee_id), y: e.pay_total, e }));
  const ring = cssVar("--surface");
  makeChart("strip", "chart-cat-strip", {
    type: "scatter",
    data: {
      datasets: [
        { label: "Women", data: pts("F", 0), backgroundColor: cssVar("--women"), borderColor: ring, borderWidth: 1, pointRadius: 4, pointHoverRadius: 6 },
        { label: "Men", data: pts("M", 1), backgroundColor: cssVar("--men"), borderColor: ring, borderWidth: 1, pointRadius: 4, pointHoverRadius: 6 },
      ],
    },
    options: {
      scales: {
        x: { min: -0.5, max: 1.5, ticks: { stepSize: 1, callback: (v) => ({ 0: "Women", 1: "Men" }[v] ?? "") }, grid: { display: false } },
        y: { title: { display: true, text: unitLong()[0].toUpperCase() + unitLong().slice(1) } },
      },
      plugins: {
        tooltip: { callbacks: { label: (c) => { const e = c.raw.e; return `${e.employee_id} · ${e.job_title} · ${e.legal_entity} · ${money(e.pay_total)}${unitShort()} · FTE ${e.fte}`; } } },
      },
    },
  });
}

async function saveJustification() {
  const cat = state.report.categories.find((c) => c.key === state.selectedCat);
  await api(`/api/justifications/${encodeURIComponent(cat.legal_entity)}/${encodeURIComponent(cat.category_id)}`, {
    method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: $("#justification").value }),
  });
  toast("Justification saved");
  await refresh();
}

async function renderOutliers() {
  const rows = await api(`/api/outliers${entityParam()}`);
  table($("#outliers"), ["Employee", "Sex", "Role", "Entity", "Category", { label: `Pay ${unitShort()}`, num: true }, { label: "Other-sex median", num: true }, { label: "Ratio", num: true }],
    rows.slice(0, 200).map((o) => `<tr><td>${esc(o.employee_id)}</td><td>${esc(o.sex)}</td><td>${esc(o.job_title)}</td><td>${esc(o.legal_entity)}</td><td>${esc(o.category_id)}</td>
      <td class="num">${money(o.pay_total)}</td><td class="num">${money(o.other_sex_median)}</td><td class="num">${pct(o.compa_ratio, 0)}</td></tr>`));
  if (rows.length > 200) $("#outliers").insertAdjacentHTML("beforeend", `<tfoot><tr><td colspan="8" class="muted small">Showing 200 of ${rows.length}</td></tr></tfoot>`);
}

// ------------------------------------------------------------------ explain
async function renderExplain() {
  const a = await api(`/api/adjusted${entityParam()}`);
  if (!a.available) {
    $("#adj-tiles").innerHTML = tile("Adjusted gap", "–", esc(a.reason));
    return;
  }
  const d = a.decomposition;
  $("#adj-tiles").innerHTML = [
    tile("Raw gap (geometric)", pct(d.raw_gap_pct), "Difference in mean log pay"),
    tile("Explained by factors", pct(d.explained_share, 0), "Share of the raw gap"),
    tile("Adjusted (unexplained) gap", pct(a.adjusted_gap), `95% CI ${pct(a.ci95[0])} to ${pct(a.ci95[1])}`),
    tile("Statistically significant?", a.significant ? "Yes" : "No", a.significant ? "✕ Investigate: like-for-like pay differs" : "✓ Not distinguishable from zero"),
  ].join("");

  const items = d.contributions.map((c) => ({ label: c.factor, v: c.log_points * 100 }))
    .concat([{ label: "Unexplained", v: d.unexplained_log * 100 }]);
  makeChart("decomp", "chart-decomp", {
    type: "bar",
    data: {
      labels: items.map((i) => i.label),
      datasets: [{
        label: "Contribution", data: items.map((i) => i.v), borderRadius: 4,
        backgroundColor: items.map((i) => (i.label === "Unexplained" ? cssVar("--men") : cssVar("--accent"))),
      }],
    },
    options: {
      indexAxis: "y",
      plugins: { legend: { display: false }, tooltip: { callbacks: { label: (c) => `${c.parsed.x.toFixed(2)} log points` } } },
      scales: { x: { title: { display: true, text: "log points × 100" } }, y: { grid: { display: false } } },
    },
  });
  table($("#adj-meta"), ["Model", ""], [
    `<tr><td>Observations</td><td class="num">${num(a.n)} (${num(a.n_F)} W / ${num(a.n_M)} M)</td></tr>`,
    `<tr><td>R²</td><td class="num">${num(a.r_squared, 3)}</td></tr>`,
    `<tr><td>Controls</td><td>${esc(a.controls.join(", "))}</td></tr>`,
  ]);
}

// -------------------------------------------------------------- remediation
async function runRemediation() {
  const target = Number($("#target").value) / 100;
  const r = await api(`/api/remediation${entityParam()}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ target_gap: target, include_justified: $("#incl-justified").checked }),
  });
  state.remediation = r;
  $("#rem-tiles").innerHTML = [
    tile("Annual cost", num(r.total_annual_cost), "Reporting currency, incl. part-time pro-rating"),
    tile("Share of payroll", pct(r.cost_share_of_payroll, 2), `Payroll ${num(r.total_payroll)}`),
    tile("Employees adjusted", num(r.adjustments.length), `${r.categories.length} categories`),
  ].join("");
  table($("#rem-cats"), ["Entity", "Category", { label: "Gap before", num: true }, { label: "Gap after", num: true }, { label: "Women adjusted", num: true }, { label: "Annual cost", num: true }],
    r.categories.map((c) => `<tr><td>${esc(c.legal_entity)}</td><td>${esc(c.category_label)}${c.justified ? ' <span class="tag">justified</span>' : ""}</td>${gapCell(c.gap_before)}${gapCell(c.gap_after)}
      <td class="num">${c.women_adjusted}</td><td class="num">${num(c.annual_cost)}</td></tr>`));
  if (!r.categories.length) $("#rem-cats tbody").innerHTML = `<tr><td colspan="6" class="muted">No category exceeds the target gap.</td></tr>`;
  table($("#rem-adj"), ["Employee", "Role", "Entity", "Category", { label: "Base now", num: true }, { label: "Proposed", num: true }, { label: "Increase", num: true }, { label: "Annual cost", num: true }],
    r.adjustments.map((a) => `<tr><td>${esc(a.employee_id)}</td><td>${esc(a.job_title)}</td><td>${esc(a.legal_entity)}</td><td>${esc(a.category_id)}</td>
      <td class="num">${num(a.current_base_salary)}</td><td class="num">${num(a.proposed_base_salary)}</td><td class="num">${pct(a.increase_pct)}</td><td class="num">${num(a.annual_cost)}</td></tr>`));
}

// ------------------------------------------------------------------- ranges
async function renderRanges() {
  const rows = await api(`/api/pay-ranges${entityParam()}`);
  const lo = Math.min(...rows.map((r) => r.p10)), hi = Math.max(...rows.map((r) => r.p90));
  const pos = (v) => ((v - lo) / (hi - lo || 1)) * 100;
  table($("#ranges"), ["Entity", "Category", "Roles", { label: "Headcount", num: true }, { label: "Advertise", num: true }, "P10 – P90 (suggested range dark)", { label: "Below range W / M", num: true }],
    rows.map((r) => `<tr><td>${esc(r.legal_entity)}</td><td>${esc(r.category_label)}</td><td class="small">${esc(r.roles.slice(0, 4).join(", "))}${r.roles.length > 4 ? ` +${r.roles.length - 4}` : ""}</td>
      <td class="num">${r.headcount}</td><td class="num">${num(r.suggested_min)} – ${num(r.suggested_max)}</td>
      <td><div class="rangebar" title="P10 ${num(r.p10)} · P25 ${num(r.p25)} · median ${num(r.median)} · P75 ${num(r.p75)} · P90 ${num(r.p90)}">
        <div class="p" style="left:${pos(r.p10)}%;width:${pos(r.p90) - pos(r.p10)}%"></div>
        <div class="s" style="left:${pos(r.suggested_min)}%;width:${pos(r.suggested_max) - pos(r.suggested_min)}%"></div>
        <div class="m" style="left:${pos(r.median)}%"></div></div></td>
      <td class="num">${r.below_range.F} / ${r.below_range.M}</td></tr>`));
}

// ---------------------------------------------------------------------- RTI
async function fillRtiIds() {
  if ($("#rti-ids").children.length) return;
  const emps = await api("/api/employees?limit=300");
  $("#rti-ids").innerHTML = emps.map((e) => `<option value="${esc(e.employee_id)}">${esc(e.job_title)}</option>`).join("");
}

async function runRti() {
  const id = $("#rti-id").value.trim();
  if (!id) return;
  try {
    const r = await api(`/api/employees/${encodeURIComponent(id)}/right-to-information`);
    $("#rti-out").classList.remove("hidden");
    $("#rti-warn").innerHTML = r.warnings.map((w) => `<div class="msg warn">${esc(w)}</div>`).join("");
    const cf = r.category_averages;
    $("#rti-tiles").innerHTML = [
      tile(monthly() ? "Your monthly pay (FTE)" : "Your hourly pay", money(r.employee.pay_total), `${esc(r.employee.job_title)} · ${esc(r.employee.legal_entity)} · ${esc(r.employee.category_label)}`),
      tile("Women in category (average)", money(cf.F.mean_pay_total), `${cf.F.headcount} people`),
      tile("Men in category (average)", money(cf.M.mean_pay_total), `${cf.M.headcount} people`),
      tile("Reply deadline", `${r.response_deadline_days} days`, "From the date of request"),
    ].join("");
    $("#rti-letter").textContent = r.letter;
  } catch (e) {
    toast(e.message);
  }
}

// --------------------------------------------------------------------- data
function renderValidation(v) {
  $("#validation").innerHTML =
    (v.errors || []).map((e) => `<div class="msg error">✕ ${esc(e)}</div>`).join("") +
    (v.warnings || []).map((w) => `<div class="msg warn">! ${esc(w)}</div>`).join("") +
    (v.ok && !(v.warnings || []).length ? `<div class="msg ok">✓ Data passed validation.</div>` : "");
}

function renderSettings() {
  const s = state.settings, f = $("#settings-form");
  for (const k of ["skills", "effort", "responsibility", "working_conditions"]) f.elements[k].value = s.weights[k];
  f.elements.band_width.value = s.band_width;
  f.elements.gap_threshold.value = +(s.gap_threshold * 100).toFixed(2);
  f.elements.min_group_size.value = s.min_group_size;
  f.elements.reference_date.value = s.reference_date || "";
  f.elements.pay_basis.value = s.pay_basis || "monthly";
}

async function renderDataTab() {
  const [roles, schema] = await Promise.all([api(`/api/categories/roles${entityParam()}`), api("/api/schema")]);
  table($("#roles-map"), ["Category", "Job families", "Roles (headcount)"], roles.map((c) =>
    `<tr><td>${esc(c.category_label)}</td><td class="small">${esc(c.job_families.join(", "))}</td>
     <td class="small">${c.roles.map((r) => `${esc(r.job_title)} (${r.headcount})`).join(", ")}</td></tr>`));
  table($("#schema"), ["Column", "Required", "Meaning"], schema.employees.map((c) =>
    `<tr><td><code>${esc(c.name)}</code></td><td>${c.required ? "Yes" : "No"}</td><td>${esc(c.description)}</td></tr>`));
}

async function submitSettings(ev) {
  ev.preventDefault();
  const f = ev.target, s = structuredClone(state.settings);
  for (const k of ["skills", "effort", "responsibility", "working_conditions"]) s.weights[k] = Number(f.elements[k].value);
  s.band_width = Number(f.elements.band_width.value);
  s.gap_threshold = Number(f.elements.gap_threshold.value) / 100;
  s.min_group_size = Number(f.elements.min_group_size.value);
  s.reference_date = f.elements.reference_date.value || null;
  s.pay_basis = f.elements.pay_basis.value;
  try {
    await api("/api/settings", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(s) });
    toast("Settings applied");
    await loadDataset();
    await refresh();
  } catch (e) { toast(e.message); }
}

async function upload(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  if (!fd.get("job_evaluation") || !fd.get("job_evaluation").name) fd.delete("job_evaluation");
  try {
    const r = await api("/api/dataset/upload", { method: "POST", body: fd });
    toast(`Loaded ${r.employees} employees`);
    state.selectedCat = null;
    $("#rti-ids").innerHTML = "";
    await loadDataset();
    await refresh();
  } catch (e) {
    renderValidation(e.detail && e.detail.errors ? e.detail : { errors: [e.message], warnings: [] });
  }
}

async function reloadLocal() {
  try {
    const r = await api("/api/dataset/reload-local", { method: "POST" });
    toast(`Loaded ${r.employees} employees from your local files`);
    state.selectedCat = null;
    $("#rti-ids").innerHTML = "";
    await loadDataset();
    await refresh();
  } catch (e) {
    renderValidation(e.detail && e.detail.errors ? e.detail : { errors: [e.message], warnings: [] });
  }
}

async function loadSample() {
  const n = $("#sample-n").value, seed = $("#sample-seed").value;
  await api(`/api/dataset/sample?n=${n}&seed=${seed}`, { method: "POST" });
  toast("Synthetic data loaded");
  state.selectedCat = null;
  $("#rti-ids").innerHTML = "";
  await loadDataset();
  await refresh();
}

// -------------------------------------------------------------------- wiring
function wire() {
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", async () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("active", x === b));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${b.dataset.tab}`));
    await loadTab(b.dataset.tab);
  }));
  $("#entity").addEventListener("change", async (e) => { state.entity = e.target.value; state.selectedCat = null; await refresh(); });
  $("#save-justification").addEventListener("click", saveJustification);
  $("#target").addEventListener("input", (e) => { $("#target-out").textContent = `${e.target.value}%`; });
  $("#target").addEventListener("change", runRemediation);
  $("#incl-justified").addEventListener("change", runRemediation);
  $("#run-rem").addEventListener("click", runRemediation);
  $("#dl-adjustments").addEventListener("click", () => state.remediation && downloadCsv("pay_adjustments.csv", state.remediation.adjustments));
  $("#rti-go").addEventListener("click", runRti);
  $("#art9-group").addEventListener("change", renderArt9);
  $("#rti-id").addEventListener("keydown", (e) => e.key === "Enter" && runRti());
  $("#rti-copy").addEventListener("click", async () => { await navigator.clipboard.writeText($("#rti-letter").textContent); toast("Copied"); });
  $("#settings-form").addEventListener("submit", submitSettings);
  $("#upload-form").addEventListener("submit", upload);
  $("#load-sample").addEventListener("click", loadSample);
  $("#reload-local").addEventListener("click", reloadLocal);
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { chartDefaults(); refresh(); });
}

(async function init() {
  // Charts are drawn on canvas, so wait for the web font before the first render.
  try { await document.fonts.ready; } catch (_) { /* older browsers */ }
  chartDefaults();
  wire();
  await loadDataset();
  await refresh();
})();
