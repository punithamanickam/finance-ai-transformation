/* AI Value Command Centre - single-page front end.
   Two data modes: API (FastAPI, login, live engines) and SNAPSHOT (window.AVCC_SNAPSHOT embedded by scripts/export_static.py). */
(function () {
  "use strict";
  const SNAP = window.AVCC_SNAPSHOT || null;
  const S = { token: null, user: null, page: "command", thread: [], levers: { utilisation_target: 0.8 }, pf: { bu: "", cat: "", rag: "", q: "" }, meta: null };
  const store = {
    get(k) { try { return sessionStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { v === null ? sessionStorage.removeItem(k) : sessionStorage.setItem(k, v); } catch (e) { /* storage blocked */ } },
  };
  const cache = {};

  /* ------------------------------------------------------------ data layer */
  async function get(path) {
    if (cache[path]) return cache[path];
    let data;
    if (SNAP) {
      const [, a, b] = path.split("/");
      if (a === "initiatives" && b) data = SNAP.initiatives[b];
      else if (a === "evidence") data = SNAP.evidence[decodeURIComponent(b)] || null;
      else if (a === "scenario") data = SNAP.scenario;
      else data = SNAP[a];
      if (data === undefined || data === null) throw new Error("Not available in the static snapshot");
    } else {
      const r = await fetch(path, { headers: { Authorization: "Bearer " + S.token } });
      if (r.status === 401) { logout(); throw new Error("Session expired"); }
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
      data = await r.json();
    }
    cache[path] = data;
    return data;
  }
  async function post(path, body) {
    if (SNAP) {
      if (path === "/copilot/query") return snapAnswer(body.question);
      if (path === "/scenario/run") return window.AVCCScenario.run(SNAP.scenario.base, body.levers, SNAP.scenario.assumptions);
      if (path === "/reports/cfo") return SNAP.report;
      throw new Error("Not available in the static snapshot");
    }
    const r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json", Authorization: "Bearer " + S.token }, body: JSON.stringify(body) });
    if (r.status === 401) { logout(); throw new Error("Session expired"); }
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail || r.statusText));
    return j;
  }
  function words(s) { return new Set((s.toLowerCase().match(/[a-z0-9$%]+/g) || []).filter(w => w.length > 2)); }
  function snapAnswer(q) {
    const w = words(q);
    let best = null, score = 0;
    for (const item of SNAP.copilot) {
      const iw = words(item.question);
      const inter = [...w].filter(x => iw.has(x)).length;
      const s = inter / Math.max(1, Math.min(w.size, iw.size) + 0.5 * Math.abs(w.size - iw.size));
      if (s > score) { score = s; best = item; }
    }
    if (best && score >= 0.34) return Object.assign({}, best.response, { question: q, snapshot_match: best.question });
    return { question: q, intent: "snapshot", agent: "Static snapshot", answer: "This static snapshot contains pre-computed answers to the suggested questions. Run the app locally (see README) to ask free-form questions of the live copilot.",
      key_drivers: [], numbers: [], evidence: [], assumptions: [], confidence: { level: "High", basis: "Nothing was guessed." }, drilldown: [], follow_ups: SNAP.copilot.slice(0, 5).map(c => c.question) };
  }

  /* ------------------------------------------------------------ formatting */
  const esc = s => String(s === null || s === undefined ? "" : s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  function money(x, d) {
    if (x === null || x === undefined || isNaN(x)) return "n/a";
    d = d === undefined ? 1 : d;
    const s = x < 0 ? "-" : "", a = Math.abs(x);
    if (a >= 1e9) return `${s}$${(a / 1e9).toFixed(d)}B`;
    if (a >= 1e6) return `${s}$${(a / 1e6).toFixed(d)}M`;
    if (a >= 1e3) return `${s}$${Math.round(a / 1e3).toLocaleString()}K`;
    return `${s}$${Math.round(a).toLocaleString()}`;
  }
  const pct = (x, d) => (x === null || x === undefined || isNaN(x)) ? "n/a" : `${(x * 100).toFixed(d || 0)}%`;
  const spct = (x, d) => (x === null || x === undefined || isNaN(x)) ? "n/a" : `${x >= 0 ? "+" : ""}${(x * 100).toFixed(d || 0)}%`;
  const num = (x, d) => (x === null || x === undefined || isNaN(x)) ? "n/a" : Number(x).toLocaleString(undefined, { maximumFractionDigits: d || 0 });
  const cls = x => x < 0 ? "neg" : "";
  const pill = (t, c) => `<span class="pill ${esc(c || t)}">${esc(t)}</span>`;
  const explain = (id, label) => `<button class="explain" data-ev="${esc(id)}" title="Show calculation, sources and assumptions">${esc(label || "Explain")}</button>`;
  const iniBtn = (id, name) => `<a href="#" data-ini="${esc(id)}">${esc(name || id)}</a>`;
  const $ = (sel, root) => (root || document).querySelector(sel);

  /* ------------------------------------------------------------ charts */
  function tok(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function series() { return ["--s1", "--s2", "--s3", "--s4", "--s5", "--s6", "--s7", "--s8"].map(tok); }
  function statusColor(rag) { return { Red: tok("--crit"), Amber: tok("--warn"), Green: tok("--good") }[rag] || tok("--muted"); }
  function plot(el, traces, layout, onClick) {
    if (!el || !window.Plotly) { if (el) el.innerHTML = '<p class="muted small">Charts need the Plotly library (loaded from cdnjs).</p>'; return; }
    const ink = tok("--ink-2"), line = tok("--line"), muted = tok("--muted");
    const base = {
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", margin: { l: 56, r: 16, t: 8, b: 40 },
      font: { family: tok("--font") || "IBM Plex Sans, sans-serif", size: 12, color: ink },
      xaxis: { gridcolor: line, linecolor: line, zerolinecolor: tok("--line-strong"), tickfont: { color: muted }, automargin: true },
      yaxis: { gridcolor: line, linecolor: line, zerolinecolor: tok("--line-strong"), tickfont: { color: muted }, automargin: true },
      legend: { orientation: "h", y: -0.18, font: { color: ink } }, hoverlabel: { bgcolor: tok("--surface"), bordercolor: tok("--line-strong"), font: { color: tok("--ink") } },
      bargap: 0.35,
    };
    const L = deepMerge(base, layout || {});
    Plotly.react(el, traces, L, { displayModeBar: false, responsive: true });
    if (onClick) { el.removeAllListeners && el.removeAllListeners("plotly_click"); el.on("plotly_click", onClick); }
  }
  function deepMerge(a, b) {
    const o = Object.assign({}, a);
    for (const k in b) o[k] = (b[k] && typeof b[k] === "object" && !Array.isArray(b[k]) && a[k] && typeof a[k] === "object") ? deepMerge(a[k], b[k]) : b[k];
    return o;
  }
  const M = v => v / 1e6;

  /* ------------------------------------------------------------ shell */
  const PAGES = [
    ["command", "A", "Executive Command Center", "Are we actually getting value from AI?"],
    ["portfolio", "B", "AI Investment Portfolio", "What have we invested in, and how is each initiative doing?"],
    ["value", "C", "Value & ROI", "What return are we getting, and why did it move?"],
    ["costs", "D", "Cost Intelligence", "Where is the money going and what is driving cost growth?"],
    ["benefits", "E", "Benefit Realisation", "Which benefits are real, which are pending and which are assumptions?"],
    ["risks", "E2", "Risk Intelligence", "Which risks could erode AI value?"],
    ["copilot", "F", "AI CFO Copilot", "Ask the portfolio a question"],
    ["scenario", "G", "Scenario Simulator", "What happens if we change the assumptions?"],
    ["evidence", "H", "Evidence & Trust", "Can we prove it?"],
    ["report", "I", "Executive Report", "CFO-ready summary"],
  ];

  function shell() {
    const u = S.user || {};
    $("#app").innerHTML = `
      <div class="shell">
        <aside class="rail" id="rail">
          <div class="brand"><b>AI Value Command Centre</b><span>Enterprise AI value management</span></div>
          <nav class="nav" aria-label="Sections">${PAGES.map(p => `<button data-page="${p[0]}" class="${S.page === p[0] ? "on" : ""}"><span class="k">${p[1]}</span>${p[2]}</button>`).join("")}</nav>
          <div class="foot">
            <span class="chip syn">SYNTHETIC enterprise data</span>
            <span class="chip pub">PUBLIC HPE sources, cited</span>
            <span>Fictional enterprise “Meridian Enterprise Group”. Synthetic figures are not HPE or any company's actual data.</span>
            ${SNAP ? `<span>Static snapshot · generated ${esc(SNAP.generated)}</span>` : `<button class="btn sm" id="logout">Sign out</button>`}
          </div>
        </aside>
        <div class="main">
          <div class="topbar">
            <button class="btn sm menu-btn" id="menu" aria-label="Open navigation">Menu</button>
            <div><h1 id="ptitle"></h1><div class="q" id="pq"></div></div>
            <div class="spacer"></div>
            <span class="chip role">${esc(u.display_name || "")} · ${esc(u.role || "")}${u.bu_id ? " · " + esc(u.bu_id) : ""}</span>
            <span class="chip syn">FY2026 · as of 31 Aug 2026</span>
          </div>
          <main class="page" id="page"></main>
        </div>
      </div>`;
    document.querySelectorAll(".nav button").forEach(b => b.onclick = () => go(b.dataset.page));
    $("#menu").onclick = () => $("#rail").classList.toggle("open");
    const lo = $("#logout"); if (lo) lo.onclick = logout;
  }

  function go(page, arg) {
    S.page = page;
    try { history.replaceState(null, "", "#" + page); } catch (e) { /* sandboxed */ }
    document.querySelectorAll(".nav button").forEach(b => b.classList.toggle("on", b.dataset.page === page));
    $("#rail").classList.remove("open");
    const p = PAGES.find(x => x[0] === page);
    $("#ptitle").textContent = p[2]; $("#pq").textContent = p[3];
    const el = $("#page");
    el.innerHTML = '<div class="loading">Loading…</div>';
    RENDER[page](el, arg).catch(err => { el.innerHTML = `<div class="panel"><p class="err">${esc(err.message)}</p></div>`; });
    window.scrollTo(0, 0);
  }

  document.addEventListener("click", e => {
    const ev = e.target.closest("[data-ev]");
    if (ev) { e.preventDefault(); openEvidence(ev.dataset.ev); return; }
    const ini = e.target.closest("[data-ini]");
    if (ini) { e.preventDefault(); openInitiative(ini.dataset.ini); return; }
    const ask = e.target.closest("[data-ask]");
    if (ask) { e.preventDefault(); go("copilot", ask.dataset.ask); return; }
    const dd = e.target.closest("[data-drill]");
    if (dd) { e.preventDefault(); drill(dd.dataset.kind, dd.dataset.drill); }
  });

  function drill(kind, ref) {
    if (kind === "initiative") openInitiative(ref);
    else if (kind === "evidence") openEvidence(ref);
    else if (kind === "benefit") ref === "all" ? go("benefits") : openEvidence("benefit." + ref);
    else if (kind === "cost") openEvidence(ref);
    else if (kind === "scenario") go("scenario", ref);
    else if (kind === "report") go("report", "generate");
  }

  /* ------------------------------------------------------------ drawer */
  function drawer(title, html, chip) {
    closeDrawer();
    const d = document.createElement("div");
    d.innerHTML = `<div class="scrim" id="scrim"></div><aside class="drawer" role="dialog" aria-modal="true" aria-label="${esc(title)}">
      <header><h3>${esc(title)}</h3>${chip || ""}<button class="btn sm x" id="dx">Close</button></header><div class="body" id="dbody">${html}</div></aside>`;
    d.id = "drawer";
    document.body.appendChild(d);
    $("#scrim").onclick = closeDrawer; $("#dx").onclick = closeDrawer;
    $("#dx").focus();
    return $("#dbody");
  }
  function closeDrawer() { const d = $("#drawer"); if (d) d.remove(); }
  document.addEventListener("keydown", e => { if (e.key === "Escape") closeDrawer(); });

  async function openEvidence(id) {
    const b = drawer("Evidence", '<div class="loading">Loading…</div>');
    try {
      const e = await get("/evidence/" + encodeURIComponent(id));
      const val = e.unit === "USD" ? money(e.value) : e.unit === "ratio" ? pct(e.value, 1) : e.unit === "pp" ? `${Number(e.value).toFixed(1)} pp` : num(e.value, 1);
      b.innerHTML = `
        <div class="lineage"><span>Source data</span><b>→</b><span>Calculation</span><b>→</b><span>Assumptions</span><b>→</b><span>Confidence</span></div>
        <div><p class="section-title">${esc(e.evidence_id)}</p><h3 style="font-size:18px;margin-top:4px">${esc(e.label)}: ${esc(val)}</h3>
          <p class="muted small">${esc(e.data_label)} data · engine ${esc(e.engine_version)} · as of ${esc(e.as_of)}</p></div>
        <div><p class="section-title">Calculation</p><pre class="sql">${esc(e.formula)}</pre></div>
        ${e.components && e.components.length ? `<div><p class="section-title">Components</p><div class="tbl-wrap"><table><tbody>
          ${e.components.map(c => `<tr><td>${esc(c.label)}${c.detail ? `<div class="muted small">${esc(c.detail)}</div>` : ""}</td>
          <td class="n">${c.value === null || c.value === undefined ? "" : (e.unit === "pp" ? Number(c.value).toFixed(2) + " pp" : e.unit === "score" ? Number(c.value).toFixed(2) : Math.abs(c.value) < 5 && e.unit !== "USD" ? num(c.value, 2) : money(c.value))}</td>
          <td>${c.evidence_id ? explain(c.evidence_id, "Drill") : ""}</td></tr>`).join("")}</tbody></table></div></div>` : ""}
        ${e.datasets && e.datasets.length ? `<div><p class="section-title">Data sources</p><ul class="list">${e.datasets.map(d => `<li><span class="chip syn">${esc(d.table)}</span><span>${num(d.rows)} rows${d.filter ? ` · <span class="mono">${esc(d.filter)}</span>` : ""}</span></li>`).join("")}</ul></div>` : ""}
        ${e.query ? `<div><p class="section-title">Reproducible query</p><pre class="sql">${esc(e.query)}</pre></div>` : ""}
        ${e.assumption_details && e.assumption_details.length ? `<div><p class="section-title">Assumptions (kept separate from actuals)</p><div class="tbl-wrap"><table><thead><tr><th>ID</th><th>Assumption</th><th class="n">Value</th><th>Source</th><th>Reviewed</th></tr></thead><tbody>
          ${e.assumption_details.map(a => `<tr><td class="mono">${esc(a.assumption_id)}</td><td>${esc(a.description)}</td><td class="n">${num(a.value, 3)} <span class="muted small">${esc(a.unit)}</span></td><td>${esc(a.source)}</td><td class="mono">${esc(a.last_reviewed)}</td></tr>`).join("")}</tbody></table></div></div>` : ""}
        ${e.notes && e.notes.length ? `<div><p class="section-title">Notes and confidence basis</p><ul>${e.notes.map(n => `<li>${esc(n)}</li>`).join("")}</ul></div>` : ""}`;
    } catch (err) { b.innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  }

  async function openInitiative(id) {
    const b = drawer("Initiative " + id, '<div class="loading">Loading…</div>');
    try {
      const d = await get("/initiatives/" + id);
      const i = d.initiative;
      $("#drawer header h3").textContent = i.name;
      $("#drawer header").insertAdjacentHTML("beforeend", "");
      b.innerHTML = `
        <div class="filters">${pill(i.rag)} <span class="chip role">${esc(i.business_unit)}</span><span class="chip role">${esc(i.geography)}</span><span class="chip pub">${esc(i.hpe_category)}</span>${explain("initiative." + id, "Show evidence")}</div>
        <p style="margin:0">${esc(i.use_case)}</p>
        <dl class="kv">
          <dt>Investment (actual)</dt><dd>${money(i.investment)} vs budget ${money(i.budget)} (<span class="${i.budget_variance_pct > 0.05 ? "neg" : ""}">${spct(i.budget_variance_pct)}</span>)</dd>
          <dt>Expected value</dt><dd>${money(i.expected_value)} <span class="muted small">business case</span></dd>
          <dt>Realised value</dt><dd>${money(i.realised_value)} (${pct(i.benefit_realisation)} realised)</dd>
          <dt>Validated / hypothetical</dt><dd>${money(i.validated_value)} / ${money(i.hypothetical_value)}</dd>
          <dt>Realised ROI</dt><dd class="${cls(i.realised_roi)}">${pct(i.realised_roi)}</dd>
          <dt>3-yr NPV · IRR · payback</dt><dd>${money(i.npv_3yr)} · ${i.irr_3yr === null ? "n/a" : pct(i.irr_3yr)} · ${i.payback_months === null ? "not within 3 yrs" : num(i.payback_months, 1) + " months"} <span class="muted small">forecast</span></dd>
          <dt>Adoption</dt><dd>${pct(i.adoption_rate)} active of ${num(i.users_target)} target users (plan ${pct(i.adoption_target)})</dd>
          <dt>Go-live</dt><dd>planned ${esc(i.planned_go_live)} · actual ${esc(i.actual_go_live)}${i.schedule_slip_months ? ` <span class="neg">(${i.schedule_slip_months} mo late)</span>` : ""}</dd>
          <dt>Confidence</dt><dd>${num(i.confidence)}/100 ${pill(i.confidence_band)}</dd>
          <dt>HPE products</dt><dd>${esc((i.hpe_product_ids || "").split(",").join(", "))}</dd>
          <dt>Owner</dt><dd>${esc(i.owner)}</dd>
        </dl>
        ${i.risk_flags && i.risk_flags.length ? `<div><p class="section-title">Flags (derived by rule)</p>${i.risk_flags.map(f => `<div class="flag ${f.level}">${esc(f.label)}: ${esc(f.detail)}</div>`).join("")}</div>` : ""}
        <div><p class="section-title">Monthly spend vs budget ($M)</p><div class="chart short" id="c_ms"></div></div>
        <div><p class="section-title">Monthly benefit: business case vs realised ($M)</p><div class="chart short" id="c_mb"></div></div>
        <div><p class="section-title">Benefit lines</p><div class="tbl-wrap"><table><thead><tr><th>Benefit</th><th class="n">Business case</th><th class="n">Realised</th><th class="n">Validated</th><th>Method</th><th></th></tr></thead><tbody>
          ${d.benefit_lines.map(l => `<tr><td>${esc(l.description)}<div class="muted small">${esc(l.benefit_type)} · ${esc(l.evidence_type)} evidence</div></td><td class="n">${money(l.business_case_value)}</td><td class="n">${money(l.realised_value)}</td><td class="n">${money(l.validated_value)}</td><td class="small">${esc((l.methodology || "").replace(/_/g, " "))}</td><td>${explain("benefit." + l.benefit_id)}</td></tr>`).join("")}
        </tbody></table></div></div>
        <div><p class="section-title">Cost by category</p><div class="tbl-wrap"><table><thead><tr><th>Category</th><th class="n">Actual</th><th class="n">Budget</th><th class="n">Variance</th></tr></thead><tbody>
          ${d.cost_by_category.map(c => `<tr><td>${esc(c.category)}</td><td class="n">${money(c.actual)}</td><td class="n">${money(c.budget)}</td><td class="n ${c.variance > 0 ? "neg" : ""}">${money(c.variance)}</td></tr>`).join("")}</tbody></table></div></div>
        <div><p class="section-title">Milestones</p><div class="tbl-wrap"><table><thead><tr><th>Milestone</th><th>Planned</th><th>Actual / forecast</th><th>Status</th></tr></thead><tbody>
          ${d.milestones.map(m => `<tr><td>${esc(m.milestone)}</td><td class="mono">${esc(m.planned_date)}</td><td class="mono">${esc(m.actual_date || m.forecast_date)}</td><td>${esc(m.status)}</td></tr>`).join("")}</tbody></table></div></div>
        <div><p class="section-title">Risks</p><ul class="list">${d.risks.map(r => `<li><span class="mono ix">${esc(r.risk_id)}</span><div><b>${esc(r.category)}</b>: ${esc(r.title)}<div class="muted small">impact ${money(r.financial_impact)} · owner-assessed probability ${pct(r.probability)} · ${esc(r.status)} · mitigation: ${esc(r.mitigation)}</div></div></li>`).join("") || "<li class='muted'>No risks recorded</li>"}</ul></div>`;
      const mo = d.monthly.map(x => x.month);
      const c = series();
      plot($("#c_ms"), [{ type: "bar", name: "Actual spend", x: mo, y: d.monthly.map(x => M(x.spend)), marker: { color: c[0] }, hovertemplate: "%{x}<br>Actual $%{y:.2f}M<extra></extra>" },
        { type: "scatter", mode: "lines", name: "Budget", x: mo, y: d.monthly.map(x => M(x.budget)), line: { color: c[1], width: 2, dash: "dot" }, hovertemplate: "%{x}<br>Budget $%{y:.2f}M<extra></extra>" }], { margin: { l: 44, b: 50 } });
      plot($("#c_mb"), [{ type: "scatter", mode: "lines", name: "Business case", x: mo, y: d.monthly.map(x => M(x.business_case)), line: { color: c[1], width: 2, dash: "dot" }, hovertemplate: "%{x}<br>Plan $%{y:.2f}M<extra></extra>" },
        { type: "bar", name: "Realised", x: mo, y: d.monthly.map(x => M(x.realised)), marker: { color: c[2] }, hovertemplate: "%{x}<br>Realised $%{y:.2f}M<extra></extra>" }], { margin: { l: 44, b: 50 } });
    } catch (err) { b.innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  }

  /* ------------------------------------------------------------ pages */
  const RENDER = {};

  RENDER.command = async el => {
    const d = await get("/dashboard");
    const k = d.kpis;
    const tiles = [
      ["Total AI investment", money(k.total_investment), `${spct(k.budget_variance_pct, 1)} vs ${money(k.budget)} budget`, "kpi.total_investment"],
      ["Realised AI value", money(k.realised_value), "evidenced in actuals", "kpi.realised_value", true],
      ["Expected AI value", money(k.expected_value), "approved business case", "kpi.expected_value"],
      ["Net AI value", money(k.net_value), `expected ${money(k.expected_net_value)}`, "kpi.net_value"],
      ["Benefit realisation", pct(k.benefit_realisation), "realised ÷ expected", "kpi.benefit_realisation", true],
      ["Realised ROI", pct(k.realised_roi), `$${k.value_per_dollar.toFixed(2)} value per $1`, "kpi.realised_roi"],
      ["Expected ROI", pct(k.expected_roi), "if business case is met", "kpi.expected_roi"],
      ["AI cost growth", spct(k.ai_cost_growth_qoq, 1), "FY26-Q4 vs Q3", "kpi.ai_cost_growth_qoq"],
      ["AI initiatives", String(k.initiatives), `GPU utilisation ${pct(k.utilisation_q4, 1)} (Q4)`, "kpi.at_risk"],
      ["At-risk initiatives", String(k.at_risk), `${k.watch} more on watch`, "kpi.at_risk", true],
    ];
    const cl = d.classification;
    const tot = cl.realised + cl.validated + Math.max(cl.hypothetical, 0);
    const mv = d.roi_movement;
    el.innerHTML = `
      ${d.scope ? `<div class="banner">Business-unit view: figures are limited to ${esc(d.scope)} initiatives.</div>` : ""}
      <section class="kpis" aria-label="Headline KPIs">${tiles.map(t => `<div class="kpi ${t[4] ? "hl" : ""}"><div class="l">${esc(t[0])}${explain(t[3])}</div><div class="v">${esc(t[1])}</div><div class="d">${esc(t[2])}</div></div>`).join("")}</section>
      <div class="grid g-7-5">
        <section class="panel"><header><h3>Value bridge</h3><span class="sub">FY2026 investment to net realised value · click a bar to drill in</span></header>
          <div class="chart" id="c_wf" style="min-height:440px"></div><div id="wf_drill" class="small muted">Select a component to see which initiatives make it up.</div></section>
        <section class="panel"><header><h3>Realised vs validated vs hypothetical</h3><span class="sub">of ${money(cl.expected)} expected value</span><span class="act">${explain("kpi.value_classification")}</span></header>
          <div class="stack" role="img" aria-label="Value classification">
            <div class="r" style="flex:${cl.realised / tot}" title="Realised">${pct(cl.realised / tot)}</div>
            <div class="va" style="flex:${cl.validated / tot}" title="Validated">${pct(cl.validated / tot)}</div>
            <div class="h" style="flex:${Math.max(cl.hypothetical, 0) / tot}" title="Hypothetical">${pct(Math.max(cl.hypothetical, 0) / tot)}</div></div>
          <div class="legend"><span><i style="background:var(--s1)"></i>Realised ${money(cl.realised)}: financial or operational evidence</span>
            <span><i style="background:var(--s3)"></i>Validated ${money(cl.validated)}: owner-confirmed, not yet in actuals</span>
            <span><i style="background:var(--line-strong)"></i>Hypothetical ${money(cl.hypothetical)}: business-case assumptions</span></div>
          <p class="section-title" style="margin-top:6px">Confidence by benefit type</p>
          <div class="tbl-wrap"><table><thead><tr><th>Benefit type</th><th class="n">Expected</th><th class="n">Realised</th><th>Confidence</th></tr></thead><tbody>
            ${cl.confidence_by_type.map(c => `<tr><td>${esc(c.label)}<div class="muted small">${c.evidence.finance_validated_lines} finance-validated · ${c.evidence.management_estimated_lines} management-estimated lines</div></td><td class="n">${money(c.expected)}</td><td class="n">${money(c.realised)}</td><td>${num(c.score)}/100 ${pill(c.band)}</td></tr>`).join("")}
          </tbody></table></div>
          <p class="muted small" style="margin:0">Confidence summarises evidence quality from eight documented factors. It is not a probability.</p></section>
      </div>
      <div class="grid g2">
        <section class="panel"><header><h3>Quarterly investment and realised value</h3><span class="sub">$M, FY2026</span></header><div class="chart" id="c_q"></div></section>
        <section class="panel"><header><h3>ROI movement ${esc(mv.from)} → ${esc(mv.to)}</h3><span class="sub">${pct(mv.roi_from, 1)} → ${pct(mv.roi_to, 1)} (${Number(mv.change_pp).toFixed(1)} pp)</span>
          <span class="act">${explain("analysis.roi_movement")}<button class="btn sm" data-ask="Why did AI ROI decline this quarter?">Ask why</button></span></header>
          <div class="chart" id="c_mv"></div></section>
      </div>
      <div class="grid g-7-5">
        <section class="panel"><header><h3>Portfolio matrix</h3><span class="sub">investment vs benefit realisation · bubble = expected value · hover for names, click to open · dotted line = 70% realisation</span></header><div class="chart tall" id="c_mx"></div></section>
        <section class="panel"><header><h3>Needs attention</h3><span class="sub">derived from the data by documented rules</span></header><div id="att"></div></section>
      </div>`;
    const c = series();
    // waterfall
    const st = d.waterfall.steps;
    plot($("#c_wf"), [{
      type: "waterfall", orientation: "v", x: st.map(s => s.label), y: st.map(s => M(s.value)),
      measure: st.map((s, i) => s.kind === "total" ? "total" : "relative"), text: st.map(s => money(s.value)), textposition: "outside",
      decreasing: { marker: { color: c[1] } }, increasing: { marker: { color: c[0] } }, totals: { marker: { color: d.waterfall.net_value < 0 ? tok("--crit") : tok("--good") } },
      connector: { line: { color: tok("--line-strong"), width: 1 } }, hovertemplate: "%{x}: %{text}<extra></extra>", cliponaxis: false,
    }], { yaxis: { title: { text: "$M" } }, margin: { t: 24, b: 90 }, xaxis: { tickangle: -35 } }, ev => {
      const s = st[ev.points[0].pointIndex];
      const names = Object.fromEntries(d.matrix.map(m => [m.initiative_id, m.name]));
      $("#wf_drill").innerHTML = s.drilldown ? `<b>${esc(s.label)}</b> ${money(Math.abs(s.value))}${s.expected ? ` (business case ${money(s.expected)})` : ""} · ${explain(s.id)}<br>` +
        s.drilldown.map(x => `${iniBtn(x.initiative_id, names[x.initiative_id])} ${money(x.value)}`).join(" · ") : `<b>Net AI value</b> ${money(s.value)} · ${explain("kpi.net_value")}`;
    });
    // quarterly
    const q = d.quarterly;
    plot($("#c_q"), [
      { type: "bar", name: "Investment", x: q.map(r => r.quarter), y: q.map(r => M(r.investment)), marker: { color: c[1] }, hovertemplate: "%{x}<br>Investment $%{y:.1f}M<extra></extra>" },
      { type: "bar", name: "Realised value", x: q.map(r => r.quarter), y: q.map(r => M(r.realised_value)), marker: { color: c[0] }, hovertemplate: "%{x}<br>Realised $%{y:.1f}M<extra></extra>" },
      { type: "scatter", mode: "lines+markers", name: "Business-case benefit", x: q.map(r => r.quarter), y: q.map(r => M(r.business_case_value)), line: { color: c[2], width: 2, dash: "dot" }, marker: { size: 8 }, hovertemplate: "%{x}<br>Business case $%{y:.1f}M<extra></extra>" },
    ], { barmode: "group", yaxis: { title: { text: "$M" } }, annotations: q.map(r => ({ x: r.quarter, y: Math.max(M(r.investment), M(r.realised_value), M(r.business_case_value)), yshift: 14, text: "ROI " + pct(r.roi), showarrow: false, font: { size: 11, color: tok("--muted") } })) });
    // movement
    const ini = [...mv.initiatives].reverse();
    plot($("#c_mv"), [{ type: "bar", orientation: "h", y: ini.map(x => x.name), x: ini.map(x => x.contribution_pp), marker: { color: ini.map(x => x.contribution_pp < 0 ? c[1] : c[0]) },
      hovertemplate: "%{y}<br>%{x:.2f} pp<extra></extra>", text: ini.map(x => x.contribution_pp.toFixed(1) + " pp"), textposition: "inside", insidetextanchor: "middle", textfont: { color: "#fff" } }],
      { xaxis: { title: { text: "contribution to ROI change (pp)" } }, margin: { l: 10, r: 16 }, showlegend: false });
    // matrix
    const groups = ["Green", "Amber", "Red"];
    plot($("#c_mx"), groups.map(g => {
      const rows = d.matrix.filter(m => m.rag === g);
      return { type: "scatter", mode: "markers", name: g === "Red" ? "At risk" : g === "Amber" ? "Watch" : "On track", x: rows.map(r => M(r.investment)), y: rows.map(r => r.benefit_realisation * 100),
        text: rows.map(r => r.name.replace(/^AI /, "")), textposition: "top center", textfont: { size: 10.5, color: tok("--ink-2") }, customdata: rows.map(r => r.initiative_id),
        marker: { size: rows.map(r => 10 + Math.sqrt(M(r.expected_value)) * 9), color: statusColor(g), opacity: 0.85, line: { color: tok("--surface"), width: 2 }, symbol: g === "Red" ? "diamond" : g === "Amber" ? "square" : "circle" },
        hovertemplate: "%{text}<br>Investment $%{x:.1f}M<br>Realisation %{y:.0f}%<extra></extra>" };
    }), { xaxis: { title: { text: "investment ($M)" } }, yaxis: { title: { text: "benefit realisation (%)" }, range: [0, 125] },
      shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 70, y1: 70, line: { color: tok("--line-strong"), dash: "dot", width: 1 } }] }, ev => openInitiative(ev.points[0].customdata));
    // attention list
    const port = await get("/portfolio");
    const flagged = port.initiatives.filter(i => i.rag !== "Green").sort((a, b) => (a.rag === "Red" ? 0 : 1) - (b.rag === "Red" ? 0 : 1) || b.investment - a.investment);
    $("#att").innerHTML = `<ul class="list">${flagged.map(i => `<li>${pill(i.rag)}<div>${iniBtn(i.initiative_id, i.name)} <span class="muted small">${money(i.investment)} · ${pct(i.benefit_realisation)} realised</span>
      <div>${i.risk_flags.map(f => `<div class="flag ${f.level}">${esc(f.detail)}</div>`).join("")}</div></div></li>`).join("")}</ul>`;
  };

  RENDER.portfolio = async el => {
    const p = await get("/portfolio");
    const bus = [...new Set(p.initiatives.map(i => i.business_unit))].sort(), cats = [...new Set(p.initiatives.map(i => i.hpe_category))].sort();
    el.innerHTML = `
      <div class="page-head"><p>${p.initiatives.length} initiatives. Status (red / amber / green) is derived from realisation, budget, schedule and adoption rules, not entered by hand. Click a row for the full drill-down.</p></div>
      <div class="filters">
        <select id="f_bu" aria-label="Business unit"><option value="">All business units</option>${bus.map(b => `<option ${S.pf.bu === b ? "selected" : ""}>${esc(b)}</option>`).join("")}</select>
        <select id="f_cat" aria-label="HPE category"><option value="">All HPE categories</option>${cats.map(b => `<option ${S.pf.cat === b ? "selected" : ""}>${esc(b)}</option>`).join("")}</select>
        <select id="f_rag" aria-label="Status"><option value="">All statuses</option>${["Red", "Amber", "Green"].map(b => `<option ${S.pf.rag === b ? "selected" : ""}>${b}</option>`).join("")}</select>
        <input id="f_q" placeholder="Search initiatives" value="${esc(S.pf.q)}" aria-label="Search">
        <span class="muted small" id="f_n"></span>
      </div>
      <div class="tbl-wrap"><table id="ptbl"><thead><tr><th>ID</th><th>Initiative</th><th>Business unit</th><th>Geo</th><th>HPE category</th><th>Status</th><th class="n">Budget</th><th class="n">Actual</th><th class="n">Forecast</th><th class="n">Var.</th>
        <th class="n">Users</th><th class="n">Cloud</th><th class="n">Exp. revenue</th><th class="n">Exp. savings</th><th class="n">Exp. productivity</th><th class="n">Realised</th><th class="n">Realisation</th><th class="n">ROI</th><th class="n">Payback</th><th class="n">Risk exp.</th><th class="n">Confidence</th><th>Start</th><th>Target</th></tr></thead><tbody></tbody></table></div>
      <div class="grid g2">
        <section class="panel"><header><h3>Investment by HPE portfolio category</h3><span class="sub">synthetic initiatives mapped to public HPE categories</span></header><div class="chart short" id="c_cat"></div></section>
        <section class="panel"><header><h3>HPE portfolio reference</h3><span class="chip pub">PUBLIC</span><span class="sub">descriptions paraphrase the cited source</span></header>
          <ul class="list">${p.products.map(x => `<li><span class="mono ix">${esc(x.product_id.replace("HPE-", ""))}</span><div><b>${esc(x.name)}</b> <span class="muted small">${esc(x.category)}</span><div class="small">${esc(x.public_description)}</div>
            ${x.url ? `<a class="small" href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.source_title)} (${esc(x.date)})</a>` : ""}</div></li>`).join("")}</ul></section>
      </div>`;
    const draw = () => {
      const f = S.pf, q = f.q.toLowerCase();
      const rows = p.initiatives.filter(i => (!f.bu || i.business_unit === f.bu) && (!f.cat || i.hpe_category === f.cat) && (!f.rag || i.rag === f.rag) && (!q || (i.name + i.use_case + i.initiative_id).toLowerCase().includes(q)));
      $("#f_n").textContent = `${rows.length} shown · ${money(rows.reduce((s, i) => s + i.investment, 0))} investment`;
      $("#ptbl tbody").innerHTML = rows.map(i => `<tr class="click" data-ini="${i.initiative_id}"><td class="mono">${i.initiative_id}</td><td><b>${esc(i.name)}</b><div class="muted small">${esc(i.use_case)}</div></td>
        <td>${esc(i.business_unit)}</td><td>${esc(i.geography)}</td><td>${esc(i.hpe_category)}</td><td>${pill(i.rag)}<div class="muted small">${esc(i.status)}</div></td>
        <td class="n">${money(i.budget)}</td><td class="n">${money(i.actual_spend)}</td><td class="n">${money(i.forecast_spend)}</td><td class="n ${i.budget_variance_pct > 0.05 ? "neg" : ""}">${spct(i.budget_variance_pct)}</td>
        <td class="n">${num(i.active_users)}</td><td class="n">${money(i.cloud_consumption)}</td><td class="n">${money(i.expected_revenue)}</td><td class="n">${money(i.expected_cost_savings)}</td><td class="n">${money(i.expected_productivity)}</td>
        <td class="n">${money(i.realised_value)}</td><td class="n">${pct(i.benefit_realisation)}<div class="bar"><i style="width:${Math.min(100, i.benefit_realisation * 100)}%"></i></div></td>
        <td class="n ${cls(i.realised_roi)}">${pct(i.realised_roi)}</td><td class="n">${i.payback_months === null ? "&gt;36 mo" : num(i.payback_months, 1) + " mo"}</td><td class="n">${money(i.risk_exposure)}</td><td class="n">${num(i.confidence)} ${pill(i.confidence_band)}</td>
        <td class="mono">${esc(i.start_date)}</td><td class="mono">${esc(i.target_completion)}</td></tr>`).join("");
    };
    ["bu", "cat", "rag"].forEach(k => $("#f_" + k).onchange = e => { S.pf[k] = e.target.value; draw(); });
    $("#f_q").oninput = e => { S.pf.q = e.target.value; draw(); };
    draw();
    const c = series();
    const bc = p.by_hpe_category.sort((a, b) => a.investment - b.investment);
    plot($("#c_cat"), [
      { type: "bar", orientation: "h", name: "Investment", y: bc.map(r => r.hpe_category), x: bc.map(r => M(r.investment)), marker: { color: c[1] }, hovertemplate: "%{y}<br>Investment $%{x:.1f}M<extra></extra>" },
      { type: "bar", orientation: "h", name: "Realised value", y: bc.map(r => r.hpe_category), x: bc.map(r => M(r.realised_value)), marker: { color: c[0] }, hovertemplate: "%{y}<br>Realised $%{x:.1f}M<extra></extra>" }],
      { barmode: "group", xaxis: { title: { text: "$M" } }, margin: { l: 10 } });
  };

  RENDER.value = async el => {
    const r = await get("/roi");
    const k = r.kpis, mv = r.movement;
    el.innerHTML = `
      <section class="kpis">
        ${[["Realised ROI (in-year)", pct(k.realised_roi), "kpi.realised_roi"], ["Expected ROI", pct(k.expected_roi), "kpi.expected_roi"], ["Value per $1 invested", "$" + k.value_per_dollar.toFixed(2), "unit.value_per_dollar_invested"],
          ["Net realised value", money(k.net_value), "kpi.net_value"], ["3-year NPV (forecast)", money(k.npv_3yr), null]].map(t => `<div class="kpi"><div class="l">${t[0]}${t[2] ? explain(t[2]) : '<span class="muted small">A-30..A-32</span>'}</div><div class="v">${t[1]}</div></div>`).join("")}
      </section>
      <div class="grid g2">
        <section class="panel"><header><h3>Quarterly ROI</h3><span class="sub">realised value vs spend in the quarter</span></header><div class="chart" id="c_roi"></div></section>
        <section class="panel"><header><h3>Why ROI moved: ${esc(mv.from)} → ${esc(mv.to)}</h3><span class="act">${explain("analysis.roi_movement")}</span></header>
          <dl class="kv"><dt>ROI change</dt><dd>${Number(mv.change_pp).toFixed(1)} pp (${pct(mv.roi_from, 1)} → ${pct(mv.roi_to, 1)})</dd>
            <dt>Cost effect</dt><dd>${Number(mv.cost_effect_pp).toFixed(1)} pp (spend ${money(mv.cost_from)} → ${money(mv.cost_to)})</dd>
            <dt>Value effect</dt><dd>${Number(mv.value_effect_pp).toFixed(1)} pp (value ${money(mv.value_from)} → ${money(mv.value_to)})</dd>
            <dt>Infrastructure cost</dt><dd>${spct(mv.cost_groups.Infrastructure.change_pct)} quarter on quarter</dd>
            <dt>GPU utilisation</dt><dd>${pct(mv.utilisation_from, 1)} → ${pct(mv.utilisation_to, 1)} (capacity ${spct(mv.capacity_change_pct)})</dd>
            <dt>Assumption revisions</dt><dd>${mv.value_per_unit_revisions.map(x => `${esc(x.name)}: value per user ${spct(x.value_per_user_change)}`).join("; ") || "none detected"}</dd>
            <dt>Delayed go-lives</dt><dd>${mv.delayed_initiatives.map(x => `${esc(x.name)} (${x.schedule_slip_months} mo)`).join("; ") || "none"}</dd></dl>
          <p class="muted small" style="margin:0">Decomposition: ΔROI = (V₂−V₁)/C₂ + V₁(1/C₂−1/C₁). Initiative contributions sum exactly to the change.</p></section>
      </div>
      <section class="panel"><header><h3>Lifecycle view (forecast)</h3><span class="sub">FY2026 actuals + two outlook years at FY26-Q4 run-rates · discount rate A-30 · assumptions A-31, A-32</span></header>
        <div class="tbl-wrap"><table><thead><tr><th>Initiative</th><th class="n">3-yr NPV</th><th class="n">IRR</th><th class="n">Payback</th><th class="n">Outlook annual net</th></tr></thead><tbody>
          ${r.lifecycle.sort((a, b) => b.npv_3yr - a.npv_3yr).map(x => `<tr class="click" data-ini="${x.initiative_id}"><td>${esc(x.name)}</td><td class="n ${cls(x.npv_3yr)}">${money(x.npv_3yr)}</td><td class="n">${x.irr_3yr === null ? "n/a" : pct(x.irr_3yr)}</td><td class="n">${x.payback_months === null ? "not within 36 mo" : num(x.payback_months, 1) + " mo"}</td><td class="n ${cls(x.outlook_annual_net)}">${money(x.outlook_annual_net)}</td></tr>`).join("")}
        </tbody></table></div></section>
      <section class="panel"><header><h3>Documented formulas</h3><span class="sub">deterministic functions in src/finance/formulas.py; the language model never calculates</span></header>
        <ul class="list">${Object.entries(r.formulas).map(([k2, v]) => `<li><span class="mono ix">${esc(k2)}</span><span class="mono">${esc(v)}</span></li>`).join("")}</ul></section>`;
    const q = r.quarterly, c = series();
    plot($("#c_roi"), [{ type: "bar", x: q.map(x => x.quarter), y: q.map(x => x.roi * 100), marker: { color: q.map(x => x.roi < 0 ? c[1] : c[0]) }, text: q.map(x => pct(x.roi, 1)), textposition: "outside", cliponaxis: false, hovertemplate: "%{x}<br>ROI %{y:.1f}%<extra></extra>" }],
      { yaxis: { title: { text: "ROI (%)" } }, showlegend: false, margin: { t: 20 } });
  };

  RENDER.costs = async el => {
    const d = await get("/costs");
    const u = d.unit_economics.metrics, g = d.growth;
    const spark = arr => { const mx = Math.max(...arr, 1), w = 90, h = 22; const pts = arr.map((v, i) => `${(i / (arr.length - 1)) * w},${h - (v / mx) * (h - 3) - 1}`).join(" ");
      return `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="monthly trend"><polyline points="${pts}" fill="none" stroke="var(--s1)" stroke-width="1.6"/><circle cx="${w}" cy="${h - (arr[arr.length - 1] / mx) * (h - 3) - 1}" r="2.4" fill="var(--s1)"/></svg>`; };
    const ue = [["AI cost per employee", u.ai_cost_per_employee, "unit.ai_cost_per_employee"], ["AI cost per customer", u.ai_cost_per_customer, "unit.ai_cost_per_customer"],
      ["AI cost per transaction", u.ai_cost_per_transaction, "unit.ai_cost_per_transaction"], ["AI cost per AI interaction", u.ai_cost_per_interaction, "unit.ai_cost_per_interaction"],
      ["Cost per used GPU-hour", u.ai_cost_per_gpu_hour_used, "unit.ai_cost_per_gpu_hour_used"], ["AI cost per $1 incremental revenue margin", u.ai_cost_per_dollar_revenue, "unit.ai_cost_per_dollar_revenue"],
      ["AI cost per $1 of savings", u.ai_cost_per_dollar_savings, "unit.ai_cost_per_dollar_savings"], ["AI value per $1 invested", u.value_per_dollar_invested, "unit.value_per_dollar_invested"]];
    el.innerHTML = `
      <section class="kpis">${ue.slice(0, 5).map(t => `<div class="kpi"><div class="l">${t[0]}${explain(t[2])}</div><div class="v">${t[1] === null ? "n/a" : "$" + num(t[1], t[1] < 100 ? 2 : 0)}</div></div>`).join("")}</section>
      <section class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">${ue.slice(5).map(t => `<div class="kpi"><div class="l">${t[0]}${explain(t[2])}</div><div class="v">${t[1] === null ? "n/a" : "$" + num(t[1], 2)}</div></div>`).join("")}</section>
      <div class="grid g2">
        <section class="panel"><header><h3>Monthly AI spend vs budget</h3><span class="sub">$M · all initiatives</span></header><div class="chart" id="c_mo"></div></section>
        <section class="panel"><header><h3>What drove Q4 cost growth</h3><span class="sub">${money(g.q3)} → ${money(g.q4)} (${spct(g.growth, 1)})</span><span class="act"><button class="btn sm" data-ask="What is driving AI cost growth?">Ask the copilot</button></span></header><div class="chart" id="c_gr"></div></section>
      </div>
      <section class="panel"><header><h3>Cost by category</h3><span class="sub">actual, budget, forecast (Q3 re-forecast rule), variance and trend</span></header>
        <div class="tbl-wrap"><table><thead><tr><th>Category</th><th class="n">Actual</th><th class="n">Budget</th><th class="n">Forecast</th><th class="n">Variance</th><th class="n">Var. %</th><th class="n">Q4 vs Q3</th><th>12-month trend</th><th></th></tr></thead><tbody>
          ${d.by_category.map(c => `<tr><td>${esc(c.label)}</td><td class="n">${money(c.actual)}</td><td class="n">${money(c.budget)}</td><td class="n">${money(c.forecast)}</td><td class="n ${c.variance > 0 ? "neg" : ""}">${money(c.variance)}</td><td class="n ${c.variance_pct > 0.05 ? "neg" : ""}">${spct(c.variance_pct)}</td><td class="n">${spct(c.qoq_trend)}</td><td>${spark(c.monthly)}</td><td>${explain("cost." + c.category)}</td></tr>`).join("")}
        </tbody></table></div></section>
      <div class="grid g2">
        <section class="panel"><header><h3>GPU utilisation by cluster</h3><span class="sub">GPU-hours used ÷ installed capacity</span></header><div class="chart" id="c_ut"></div></section>
        <section class="panel"><header><h3>Infrastructure clusters</h3><span class="sub">capacity added ahead of demand shows as idle GPU-hours</span></header>
          <div class="tbl-wrap"><table><thead><tr><th>Cluster</th><th>Platform</th><th class="n">GPUs</th><th class="n">Util. Q3</th><th class="n">Util. Q4</th><th class="n">Idle GPU-h Q4</th><th class="n">FY cost</th></tr></thead><tbody>
            ${d.infrastructure.clusters.map(c => `<tr><td>${esc(c.name)}</td><td>${esc(c.platform)}</td><td class="n">${c.gpus_now}</td><td class="n">${pct(c.utilisation_q3)}</td><td class="n">${pct(c.utilisation_q4)}</td><td class="n">${num(c.idle_gpu_hours_q4)}</td><td class="n">${money(c.cost_fy)}</td></tr>`).join("")}
          </tbody></table></div></section>
      </div>
      <div class="grid g2">
        <section class="panel"><header><h3>Unit economics by initiative</h3></header>
          <div class="tbl-wrap"><table><thead><tr><th>Initiative</th><th>Outcome unit</th><th class="n">Cost per outcome</th><th class="n">Cost per active user</th><th class="n">Value per $1</th></tr></thead><tbody>
            ${d.unit_economics.by_initiative.map(x => `<tr class="click" data-ini="${x.initiative_id}"><td>${esc(x.name)}</td><td class="small">${esc(x.transaction_type)}</td><td class="n">${x.cost_per_transaction === null ? "n/a" : "$" + num(x.cost_per_transaction, 2)}</td><td class="n">${x.cost_per_active_user === null ? "n/a" : "$" + num(x.cost_per_active_user, 0)}</td><td class="n">${x.value_per_dollar === null ? "n/a" : "$" + x.value_per_dollar.toFixed(2)}</td></tr>`).join("")}
          </tbody></table></div></section>
        <section class="panel"><header><h3>Spend by vendor</h3><span class="sub">non-HPE vendors are generic placeholders; amounts are synthetic, not HPE pricing</span></header><div class="chart" id="c_vd"></div></section>
      </div>`;
    const c = series(), mo = d.monthly;
    plot($("#c_mo"), [{ type: "bar", name: "Actual", x: mo.map(x => x.month), y: mo.map(x => M(x.actual)), marker: { color: c[0] }, hovertemplate: "%{x}<br>Actual $%{y:.2f}M<extra></extra>" },
      { type: "scatter", mode: "lines+markers", name: "Budget", x: mo.map(x => x.month), y: mo.map(x => M(x.budget)), line: { color: c[1], width: 2 }, marker: { size: 8 }, hovertemplate: "%{x}<br>Budget $%{y:.2f}M<extra></extra>" }], { yaxis: { title: { text: "$M" } } });
    const gc = g.by_category.filter(x => Math.abs(x.change) > 1000).reverse();
    plot($("#c_gr"), [{ type: "bar", orientation: "h", y: gc.map(x => x.label), x: gc.map(x => x.change / 1e3), marker: { color: gc.map(x => x.change > 0 ? c[1] : c[0]) }, hovertemplate: "%{y}<br>%{x:,.0f}K<extra></extra>" }],
      { xaxis: { title: { text: "change in quarterly spend ($K)" } }, showlegend: false, margin: { l: 10 } });
    const cl = d.infrastructure.clusters;
    plot($("#c_ut"), cl.map((k2, i) => ({ type: "scatter", mode: "lines+markers", name: k2.name, x: k2.monthly.map(m => m.month), y: k2.monthly.map(m => m.utilisation * 100), line: { color: c[i], width: 2 }, marker: { size: 8 }, hovertemplate: k2.name + "<br>%{x}: %{y:.0f}%<extra></extra>" })),
      { yaxis: { title: { text: "utilisation (%)" }, range: [0, 100] }, legend: { y: -0.3 }, margin: { b: 60 } });
    const vd = [...d.vendors].reverse();
    plot($("#c_vd"), [{ type: "bar", orientation: "h", y: vd.map(v => v.vendor), x: vd.map(v => M(v.amount)), marker: { color: c[0] }, hovertemplate: "%{y}<br>$%{x:.2f}M<extra></extra>" }], { xaxis: { title: { text: "$M" } }, showlegend: false, margin: { l: 10 } });
  };

  RENDER.benefits = async el => {
    const d = await get("/benefits");
    const lk = d.leakage, pnl = d.pnl;
    el.innerHTML = `
      <div class="grid g-7-5">
        <section class="panel"><header><h3>Benefits leakage</h3><span class="sub">why ${money(lk.unrealised)} of the ${money(lk.business_case)} business case is not realised</span><span class="act"><button class="btn sm" data-ask="Why is realised value below expected value?">Ask the copilot</button></span></header>
          <div class="chart" id="c_lk"></div><p class="muted small" style="margin:0">${esc(lk.method)}. Business run-cost overruns of ${money(lk.cost_overruns)} reduce net value separately.</p></section>
        <section class="panel"><header><h3>How much is in the P&amp;L?</h3><span class="sub">realised benefit by evidence type</span></header>
          <div class="stack"><div class="r" style="flex:${pnl.financial_realised}">${pct(pnl.share_of_realised_in_pnl)} in P&amp;L</div><div class="va" style="flex:${pnl.operational_realised}">operational</div></div>
          <dl class="kv"><dt>GL-evidenced (P&amp;L)</dt><dd>${money(pnl.financial_realised)}</dd><dt>Operational (hours released)</dt><dd>${money(pnl.operational_realised)}</dd>
            <dt>Validated, not yet in actuals</dt><dd>${money(pnl.validated)}</dd><dt>Hypothetical</dt><dd>${money(pnl.hypothetical)}</dd>
            <dt>Share of business case in P&amp;L</dt><dd>${pct(pnl.share_of_expected_in_pnl)}</dd><dt>P&amp;L tags reconcile</dt><dd>${pnl.reconciles ? "Yes" : "No"} (${money(pnl.pnl_tagged_benefit)} tagged)</dd></dl>
          <p class="muted small" style="margin:0">Operational benefit becomes financial value only when released capacity is redeployed or cost is removed.</p></section>
      </div>
      <section class="panel"><header><h3>Benefit realisation by line</h3><span class="sub">business case, owner forecast, validated, realised, gap, realisation, confidence, primary evidence</span></header>
        <div class="tbl-wrap"><table><thead><tr><th>Initiative / benefit</th><th class="n">Business case</th><th class="n">Forecast</th><th class="n">Validated</th><th class="n">Realised</th><th class="n">Gap</th><th class="n">Realisation</th><th class="n">Confidence</th><th>Primary evidence</th><th>Main leakage</th><th></th></tr></thead><tbody>
          ${d.lines.sort((a, b) => b.gap - a.gap).map(l => { const parts = [["delay", l.delayed_implementation], ["adoption", l.low_adoption], [l.value_per_unit_reason.replace(/_/g, " "), l.value_per_unit], ["pending validation", l.pending_validation]].sort((a, b) => b[1] - a[1]);
            return `<tr><td>${iniBtn(l.initiative_id, l.initiative_name)}<div class="small">${esc(l.description)}</div></td><td class="n">${money(l.business_case)}</td><td class="n">${money(l.owner_forecast)}</td><td class="n">${money(l.validated)}</td><td class="n">${money(l.realised)}</td><td class="n">${money(l.gap)}</td>
            <td class="n">${pct(l.realisation)}<div class="bar"><i style="width:${Math.min(100, l.realisation * 100)}%"></i></div></td><td class="n">${num(l.confidence)} ${pill(l.confidence_band)}</td><td class="small">${esc(l.primary_evidence)}</td><td class="small">${parts[0][1] > 1000 ? esc(parts[0][0]) + " " + money(parts[0][1]) : "none"}</td><td>${explain("benefit." + l.benefit_id)}${explain("confidence." + l.benefit_id, "Confidence")}</td></tr>`; }).join("")}
        </tbody></table></div></section>
      <div class="grid g2">
        <section class="panel"><header><h3>Benefits that rely on assumptions</h3><span class="sub">assumption share = (hypothetical + ½ validated) ÷ expected</span></header>
          <div class="tbl-wrap"><table><thead><tr><th>Benefit</th><th class="n">Expected</th><th class="n">Assumption share</th><th>Method</th><th>Key assumptions</th></tr></thead><tbody>
            ${d.assumption_dependency.slice(0, 10).map(a => `<tr><td>${esc(a.description)}<div class="muted small mono">${esc(a.benefit_id)}</div></td><td class="n">${money(a.expected)}</td><td class="n ${a.assumption_share >= 0.4 ? "neg" : ""}">${pct(a.assumption_share)}</td><td class="small">${esc(a.methodology.replace(/_/g, " "))}</td>
              <td class="small">${a.assumptions.map(x => `<span class="mono">${esc(x.assumption_id)}</span> ${esc(x.description)} <span class="muted">(${esc(x.source)})</span>`).join("<br>")}</td></tr>`).join("")}
          </tbody></table></div></section>
        <section class="panel"><header><h3>AI Value Confidence Engine</h3><span class="sub">eight weighted evidence factors</span></header>
          <div class="tbl-wrap"><table><thead><tr><th>Factor</th><th class="n">Weight</th></tr></thead><tbody>${Object.entries(d.confidence_weights).map(([f, w]) => `<tr><td>${esc(f.replace(/_/g, " "))}</td><td class="n">${pct(w)}</td></tr>`).join("")}</tbody></table></div>
          <p class="small muted" style="margin:0">${esc(d.confidence_disclaimer)}</p>
          ${d.confidence_by_type.map(c => `<div><b>${esc(c.label)}</b>: ${money(c.expected)} expected, confidence ${num(c.score)}/100 ${pill(c.band)}<div class="small muted">${c.evidence.finance_validated_lines} finance-validated, ${c.evidence.management_estimated_lines} management-estimated, ${c.evidence.gl_backed_lines} GL-backed, ${c.evidence.telemetry_backed_lines} telemetry-backed lines across ${c.evidence.initiatives} initiatives</div></div>`).join("")}</section>
      </div>`;
    const r = lk.reasons.filter(x => Math.abs(x.value) > 1000).reverse(), c = series();
    plot($("#c_lk"), [{ type: "bar", orientation: "h", y: r.map(x => x.label), x: r.map(x => M(x.value)), marker: { color: r.map(x => x.value < 0 ? c[2] : x.reason === "pending_validation" ? c[2] : c[1]) }, text: r.map(x => money(x.value)), textposition: "outside", cliponaxis: false, hovertemplate: "%{y}<br>%{text}<extra></extra>" }],
      { xaxis: { title: { text: "$M of business case not realised (negative = over-delivery)" } }, showlegend: false, margin: { l: 10, r: 50 } });
  };

  RENDER.risks = async el => {
    const d = await get("/risks");
    el.innerHTML = `
      <div class="banner">${esc(d.note)}</div>
      <div class="grid g-7-5">
        <section class="panel"><header><h3>Risk register</h3><span class="sub">exposure = financial impact × owner-assessed probability</span></header>
          <div class="tbl-wrap"><table><thead><tr><th>ID</th><th>Initiative</th><th>Category</th><th>Risk</th><th class="n">Impact</th><th class="n">Prob.</th><th class="n">Exposure</th><th>Mitigation</th><th>Owner</th><th>Status</th></tr></thead><tbody>
            ${d.risks.map(r => `<tr><td class="mono">${esc(r.risk_id)}</td><td>${iniBtn(r.initiative_id, r.initiative_name)}</td><td>${esc(r.category)}</td><td>${esc(r.title)}</td><td class="n">${money(r.financial_impact)}</td><td class="n">${pct(r.probability)}</td><td class="n">${money(r.exposure)}</td><td class="small">${esc(r.mitigation)}</td><td class="small">${esc(r.owner)}</td><td>${pill(r.status, r.status === "Open" ? "Amber" : r.status === "Closed" ? "Green" : "plain")}</td></tr>`).join("")}
          </tbody></table></div></section>
        <section class="panel"><header><h3>Open exposure by category</h3><span class="sub">$M</span></header><div class="chart tall" id="c_rk"></div></section>
      </div>`;
    const b = [...d.by_category].reverse();
    plot($("#c_rk"), [{ type: "bar", orientation: "h", y: b.map(x => x.category), x: b.map(x => M(x.exposure)), marker: { color: series()[1] }, text: b.map(x => `${x.risks} risk${x.risks > 1 ? "s" : ""}`), textposition: "outside", cliponaxis: false, hovertemplate: "%{y}<br>$%{x:.2f}M exposure<extra></extra>" }],
      { xaxis: { title: { text: "exposure ($M)" } }, showlegend: false, margin: { l: 10, r: 50 } });
  };

  const DEMO_QUESTIONS = ["How much have we invested in AI?", "How much value has actually been realised?", "Why is realised value below expected value?", "What is driving AI cost growth?",
    "Show initiatives with significant budget variance.", "Which benefits rely heavily on assumptions?", "Explain the biggest ROI movement.", "What happens if utilisation increases to 80%?",
    "Which business units have the highest AI spend?", "Prepare a board-level AI investment briefing."];
  const MORE_QUESTIONS = ["Where is the AI money going?", "Show me all AI initiatives with more than $5M investment.", "What percentage of AI value is actually reflected in the P&L?",
    "Explain the $49.5M expected benefit.", "Which projects have benefits below plan?", "Are we actually getting value from AI?", "What is HPE Private Cloud AI?", "What is HPE's AI backlog?"];

  RENDER.copilot = async (el, initial) => {
    el.innerHTML = `
      <div class="copilot">
        <div class="thread"><div id="thread" class="thread"></div>
          <form class="askbar" id="askf"><input id="askq" maxlength="500" placeholder="Ask about AI investment, value, ROI, costs, benefits, scenarios or HPE's public portfolio" aria-label="Question"><button class="btn primary" type="submit">Ask</button></form></div>
        <aside class="panel"><header><h3>Try asking the CFO Copilot</h3></header><div class="suggest">${DEMO_QUESTIONS.map(q => `<button data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
          <p class="section-title" style="margin-top:8px">More</p><div class="suggest">${MORE_QUESTIONS.map(q => `<button data-q="${esc(q)}">${esc(q)}</button>`).join("")}</div>
          <p class="small muted" style="margin:0">Numbers come from deterministic engines. ${SNAP ? "This static snapshot answers the listed questions." : "An LLM, if configured, only rewrites the narrative and is checked against the evidence."}</p></aside>
      </div>`;
    el.querySelectorAll("[data-q]").forEach(b => b.onclick = () => askQ(b.dataset.q));
    $("#askf").onsubmit = e => { e.preventDefault(); const q = $("#askq").value.trim(); if (q) { $("#askq").value = ""; askQ(q); } };
    S.thread.forEach(t => renderTurn(t.q, t.r));
    if (initial) askQ(initial);
    else if (!S.thread.length) renderIntro();
  };
  function renderIntro() {
    $("#thread").innerHTML = `<div class="answer"><div class="lead">Ask a question in plain English. Each answer shows the <b>answer</b>, <b>key drivers</b>, the <b>numbers</b> and how they were calculated, the <b>evidence</b>, <b>assumptions</b> kept apart from actuals, a <b>confidence</b> level with its basis, and <b>drill-downs</b> into the data.</div></div>`;
  }
  async function askQ(q) {
    const th = $("#thread");
    if (!S.thread.length) th.innerHTML = "";
    const holder = document.createElement("div"); holder.className = "thread";
    holder.innerHTML = `<div class="qbubble">${esc(q)}</div><div class="answer"><div class="muted">Analysing…</div></div>`;
    th.appendChild(holder); holder.scrollIntoView({ block: "start", behavior: "smooth" });
    try { const r = await post("/copilot/query", { question: q }); S.thread.push({ q, r }); holder.remove(); renderTurn(q, r); }
    catch (err) { holder.querySelector(".answer").innerHTML = `<p class="err">${esc(err.message)}</p>`; }
  }
  function renderTurn(q, r) {
    const th = $("#thread");
    const div = document.createElement("div"); div.className = "thread";
    const tbl = r.table && r.table.rows && r.table.rows.length && r.intent !== "briefing" ? renderTable(r.table) : "";
    div.innerHTML = `<div class="qbubble">${esc(q)}</div>
      <article class="answer">
        <div class="meta">${pill(r.confidence.level)} <span>${esc(r.agent)}</span><span>·</span><span class="mono">${esc(r.intent)}</span>${r.audit_id ? `<span>· audit #${r.audit_id}</span>` : ""}${r.narrative_source && r.narrative_source !== "deterministic" ? `<span>· ${esc(r.narrative_source)}</span>` : ""}${r.snapshot_match && r.snapshot_match !== q ? `<span>· matched “${esc(r.snapshot_match)}”</span>` : ""}</div>
        <div class="blk"><p class="section-title">Answer</p><div class="lead">${esc(r.answer)}</div></div>
        ${r.key_drivers.length ? `<div class="blk"><p class="section-title">Key drivers</p><ul>${r.key_drivers.map(x => `<li>${esc(x)}</li>`).join("")}</ul></div>` : ""}
        ${r.numbers.length ? `<div class="blk"><p class="section-title">Numbers</p><div class="numgrid">${r.numbers.map(n => `<div class="n ${esc(n.basis)}"><span class="lb">${esc(n.label)}</span><span class="vl">${esc(n.display)}</span><span class="bs">${esc(n.basis)}${n.evidence_id ? " · " + explain(n.evidence_id, "explain") : ""}</span>${n.formula ? `<span class="muted small mono">${esc(n.formula)}</span>` : ""}</div>`).join("")}</div></div>` : ""}
        ${r.query ? `<div class="blk"><p class="section-title">Generated query (read-only semantic layer)</p><pre class="sql">${esc(r.query.sql)}\n-- params: ${esc(JSON.stringify(r.query.params))}</pre></div>` : ""}
        ${tbl ? `<div class="blk"><p class="section-title">Data</p>${tbl}</div>` : ""}
        ${r.evidence.length ? `<div class="blk"><p class="section-title">Evidence</p>${r.evidence.map(e => `<div class="ev ${esc(e.kind)}"><span><b>${esc(e.label)}</b> <span class="muted mono small">${esc(e.ref)}</span>${e.kind === "calculation" ? " " + explain(e.ref, "open") : ""}</span>${e.detail ? `<span class="muted small">${esc(e.detail)}</span>` : ""}${e.quote ? `<q>${esc(e.quote)}</q>` : ""}${e.url ? `<a class="small" href="${esc(e.url)}" target="_blank" rel="noopener">${esc(e.url)}</a>${e.date ? ` <span class="muted small">(${esc(e.date)})</span>` : ""}` : ""}</div>`).join("")}</div>` : ""}
        ${r.assumptions.length ? `<div class="blk"><p class="section-title">Assumptions (not actuals)</p><ul>${r.assumptions.map(a => `<li><span class="mono">${esc(a.assumption_id)}</span> ${esc(a.description)}${a.value !== null && a.value !== undefined ? `: <b>${num(a.value, 3)}</b> ${esc(a.unit || "")}` : ""}${a.source ? ` <span class="muted">(${esc(a.source)})</span>` : ""}</li>`).join("")}</ul></div>` : ""}
        <div class="blk"><p class="section-title">Confidence: ${esc(r.confidence.level)}</p><div class="small">${esc(r.confidence.basis)}</div></div>
        ${r.drilldown.length ? `<div class="blk"><p class="section-title">Drill-down</p><div class="drill">${r.drilldown.map(x => `<button class="btn sm" data-kind="${esc(x.kind)}" data-drill="${esc(x.ref)}">${esc(x.label)}</button>`).join("")}</div></div>` : ""}
        ${r.follow_ups && r.follow_ups.length ? `<div class="drill">${r.follow_ups.map(f => `<button class="btn sm" data-q="${esc(f)}">${esc(f)}</button>`).join("")}</div>` : ""}
        <div class="muted small">${esc(r.data_label)}</div>
      </article>`;
    div.querySelectorAll("[data-q]").forEach(b => b.onclick = () => askQ(b.dataset.q));
    th.appendChild(div);
    if (S.thread.length && S.thread[S.thread.length - 1].q === q) div.scrollIntoView({ block: "start", behavior: "smooth" });
  }
  function renderTable(t) {
    const cols = t.columns.slice(0, 9);
    const fmt = (c, v) => {
      if (v === null || v === undefined) return "";
      if (typeof v === "number") {
        if (/pct|realisation|share|roi|rate|probability/.test(c)) return pct(v);
        if (/confidence|payback|users|count|risks/.test(c)) return num(v, 1);
        if (Math.abs(v) >= 1000 || /investment|budget|value|cost|actual|variance|gap|realised|validated|expected|impact|exposure|spend|case|hypothetical|amount|low|high|swing/.test(c)) return money(v);
        return num(v, 2);
      }
      if (typeof v === "object") return esc(JSON.stringify(v)).slice(0, 80);
      return esc(v);
    };
    return `<div class="tbl-wrap"><table><thead><tr>${cols.map(c => `<th>${esc(c.replace(/_/g, " "))}</th>`).join("")}</tr></thead><tbody>${t.rows.slice(0, 25).map(r => `<tr${r.initiative_id ? ` class="click" data-ini="${esc(r.initiative_id)}"` : ""}>${cols.map(c => `<td class="${typeof r[c] === "number" ? "n" : ""}">${fmt(c, r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
  }

  RENDER.scenario = async (el, arg) => {
    const meta = S.meta || (S.meta = await get("/scenario/meta"));
    if (arg && arg !== "sensitivity") arg.split("&").forEach(kv => { const [k, v] = kv.split("="); if (meta.levers[k]) S.levers[k] = Number(v); });
    const L = meta.levers;
    const val = k => S.levers[k] !== undefined ? S.levers[k] : L[k].default;
    const show = (k, v) => L[k].unit === "USD" ? money(v) : L[k].unit === "months" ? `${v} mo` : k === "utilisation_target" || k === "benefit_realisation" ? pct(v) : spct(v);
    el.innerHTML = `
      <div class="banner">Illustrative what-if on synthetic data, using documented scenario assumptions (listed below). Not a forecast.</div>
      <div class="filters"><span class="muted small">Presets:</span>
        <button class="btn sm" data-preset="utilisation_target=0.8">Utilisation 63% → 80%</button>
        <button class="btn sm" data-preset="additional_investment=10000000">Invest additional $10M</button>
        <button class="btn sm" data-preset="benefit_realisation=0.8&cloud_cost_change=0.2">Downside: 80% realisation, cloud +20%</button>
        <button class="btn sm" data-preset="adoption_change=0.2&productivity_change=0.1">Adoption +20%, productivity +10%</button>
        <button class="btn sm" data-preset="">Reset</button></div>
      <div class="grid g-7-5" style="grid-template-columns:minmax(0,4fr) minmax(0,8fr)">
        <section class="panel"><header><h3>Inputs</h3></header><div class="levers">${Object.entries(L).map(([k, l]) => `<div class="lever"><label for="lv_${k}">${esc(l.label)}</label><output id="o_${k}">${show(k, val(k))}</output>
          <input type="range" id="lv_${k}" data-k="${k}" min="${l.min}" max="${l.max}" step="${l.step}" value="${val(k)}"></div>`).join("")}</div></section>
        <div class="grid" style="align-content:start">
          <div class="compare" id="cmp"></div>
          <section class="panel"><header><h3>Scenario bridge</h3><span class="sub">change in expected value and cost by lever ($M)</span></header><div class="chart short" id="c_br"></div><div id="br_notes" class="small muted"></div></section>
        </div>
      </div>
      <div class="grid g2">
        <section class="panel"><header><h3>Sensitivity</h3><span class="sub">change in net value for ±20% on each driver (utilisation ±10pp)</span></header><div class="chart" id="c_tor"></div></section>
        <section class="panel"><header><h3>Scenario assumptions</h3></header><div class="tbl-wrap"><table><thead><tr><th>ID</th><th>Assumption</th><th class="n">Value</th><th>Source</th></tr></thead><tbody>
          ${meta.baseline.assumptions.map(a => `<tr><td class="mono">${esc(a.assumption_id)}</td><td>${esc(a.description)}</td><td class="n">${num(a.value, 3)}</td><td class="small">${esc(a.source)}</td></tr>`).join("")}
          <tr><td class="mono">base</td><td>Value per used GPU-hour (Q4 run-rate)</td><td class="n">$${num(meta.base.value_per_used_gpu_hour, 2)}</td><td class="small">derived from benefit and GPU telemetry</td></tr>
          <tr><td class="mono">base</td><td>Non-infrastructure investment per used GPU-hour</td><td class="n">$${num(meta.base.non_infra_investment_per_used_gpu_hour, 2)}</td><td class="small">derived from programme spend</td></tr>
          <tr><td class="mono">base</td><td>Current GPU utilisation (FY26-Q4)</td><td class="n">${pct(meta.base.utilisation, 1)}</td><td class="small">infrastructure_usage</td></tr>
        </tbody></table></div></section>
      </div>`;
    let timer = null;
    const update = async () => {
      Object.keys(L).forEach(k => { $("#o_" + k).textContent = show(k, val(k)); });
      let r;
      const levers = Object.fromEntries(Object.keys(L).filter(k => S.levers[k] !== undefined).map(k => [k, S.levers[k]]));
      try { r = SNAP ? window.AVCCScenario.run(meta.base, levers, meta.assumptions) : await post("/scenario/run", { levers }); }
      catch (err) { $("#cmp").innerHTML = `<p class="err">${esc(err.message)}</p>`; return; }
      const b = r.base, s = r.scenario, inc = r.incremental;
      $("#cmp").innerHTML = `
        <div class="col"><p class="section-title">Base case (FY2026)</p><dl class="kv"><dt>Investment</dt><dd>${money(b.investment)}</dd><dt>Expected value</dt><dd>${money(b.expected_value)}</dd><dt>Net value</dt><dd>${money(b.net_value)}</dd><dt>ROI</dt><dd>${pct(b.roi, 1)}</dd><dt>Utilisation</dt><dd>${pct(b.utilisation, 1)}</dd></dl></div>
        <div class="col sc"><p class="section-title">Scenario</p><dl class="kv"><dt>Investment</dt><dd>${money(s.investment)}</dd><dt>Expected value</dt><dd>${money(s.expected_value)}</dd><dt>Net value</dt><dd class="${cls(s.net_value)}">${money(s.net_value)}</dd><dt>ROI</dt><dd>${pct(s.roi, 1)}</dd><dt>Utilisation</dt><dd>${pct(s.utilisation, 1)}</dd></dl></div>
        <div class="col" style="grid-column:1/-1"><p class="section-title">Incremental</p><dl class="kv" style="grid-template-columns:repeat(4,max-content 1fr)">
          <dt>Cost</dt><dd>${money(inc.cost)}</dd><dt>Expected benefit</dt><dd>${money(inc.value)}</dd><dt>Net value</dt><dd class="${cls(inc.net_value)}">${money(inc.net_value)}</dd><dt>Incremental ROI</dt><dd>${inc.roi === null ? "n/a" : pct(inc.roi)}</dd>
          <dt>Capacity</dt><dd>${num(inc.capacity_gpu_hours)} GPU-h</dd><dt>Infra avoided</dt><dd>${money(inc.infrastructure_avoided)}</dd><dt>Payback</dt><dd>${inc.payback_months ? num(inc.payback_months, 1) + " mo" : "n/a"}</dd><dt></dt><dd></dd></dl></div>`;
      const c = series(), br = r.bridge;
      if (!br.length) { $("#c_br").innerHTML = '<p class="muted small">Move a lever or pick a preset to see the bridge.</p>'; $("#br_notes").innerHTML = ""; return; }
      $("#c_br").innerHTML = "";
      plot($("#c_br"), [{ type: "bar", name: "Value change", x: br.map(x => x.label), y: br.map(x => M(x.value_change)), marker: { color: c[0] }, hovertemplate: "%{x}<br>Value %{y:.2f}M<extra></extra>" },
        { type: "bar", name: "Cost change", x: br.map(x => x.label), y: br.map(x => M(x.cost_change)), marker: { color: c[1] }, hovertemplate: "%{x}<br>Cost %{y:.2f}M<extra></extra>" }],
        { barmode: "group", yaxis: { title: { text: "$M" } }, margin: { b: 70 } });
      $("#br_notes").innerHTML = br.filter(x => x.note).map(x => `${esc(x.label)}: ${esc(x.note)}`).join("<br>");
    };
    el.querySelectorAll("input[type=range]").forEach(inp => inp.oninput = () => { S.levers[inp.dataset.k] = Number(inp.value); clearTimeout(timer); timer = setTimeout(update, SNAP ? 0 : 150); Object.keys(L).forEach(k => { $("#o_" + k).textContent = show(k, val(k)); }); });
    el.querySelectorAll("[data-preset]").forEach(b => b.onclick = () => { S.levers = {}; if (b.dataset.preset) b.dataset.preset.split("&").forEach(kv => { const [k, v] = kv.split("="); S.levers[k] = Number(v); }); go("scenario"); });
    update();
    const t = [...meta.sensitivity].reverse(), c = series();
    plot($("#c_tor"), [{ type: "bar", orientation: "h", name: "Downside", y: t.map(x => x.label), x: t.map(x => M(Math.min(x.low, x.high))), marker: { color: c[1] }, hovertemplate: "%{y}<br>%{x:.2f}M<extra></extra>" },
      { type: "bar", orientation: "h", name: "Upside", y: t.map(x => x.label), x: t.map(x => M(Math.max(x.low, x.high))), marker: { color: c[0] }, hovertemplate: "%{y}<br>+%{x:.2f}M<extra></extra>" }],
      { barmode: "overlay", xaxis: { title: { text: "change in net value ($M)" } }, margin: { l: 10, b: 80 }, legend: { y: -0.32 } });
  };

  RENDER.evidence = async el => {
    const [src, d] = await Promise.all([get("/sources"), get("/dashboard")]);
    const kpiIds = [["kpi.total_investment", "Total AI investment"], ["kpi.realised_value", "Realised AI value"], ["kpi.expected_value", "Expected AI value"], ["kpi.value_classification", "Realised / validated / hypothetical"],
      ["kpi.realised_roi", "Realised ROI"], ["kpi.expected_roi", "Expected ROI"], ["kpi.benefit_realisation", "Benefit realisation"], ["kpi.net_value", "Net AI value"], ["kpi.ai_cost_growth_qoq", "AI cost growth"], ["kpi.at_risk", "At-risk initiatives"], ["analysis.roi_movement", "ROI movement"]];
    const h = src.headline || {}, a = h.annual || {};
    const fy = ["FY2023", "FY2024", "FY2025"];
    const rowsFin = [["Total net revenue", "total_net_revenue"], ["Gross profit", "gross_profit"], ["Earnings from operations", "earnings_from_operations"], ["Net earnings", "net_earnings_attributable_to_HPE"], ["R&D", "research_and_development"], ["Operating cash flow", "net_cash_from_operating_activities"], ["Free cash flow (non-GAAP)", "free_cash_flow_non_GAAP"]];
    el.innerHTML = `
      <section class="panel"><header><h3>How every number is produced</h3><span class="sub">data lineage</span></header>
        <div class="lineage"><span>Public HPE sources (SEC filings, IR, partner releases)</span><b>+</b><span>Synthetic enterprise transactions</span><b>→</b><span>Relational data model (24 tables)</span><b>→</b><span>Deterministic finance engines</span><b>→</b><span>Evidence record (formula, components, datasets, SQL)</span><b>→</b><span>Copilot answer</span><b>→</b><span>Audit log + SHA-256</span></div>
        <p class="small muted" style="margin:0">Every headline figure below has an evidence record. Each copilot answer is logged with its question, intent, agent, evidence ids, SQL and a hash of the response, so it can be reproduced from the same data.</p></section>
      <div class="grid g2">
        <section class="panel"><header><h3>Explain a headline number</h3></header><ul class="list">${kpiIds.map(([id, l]) => `<li><span class="mono ix">›</span><div>${esc(l)} ${explain(id)}</div></li>`).join("")}</ul></section>
        <section class="panel"><header><h3>HPE public financial context</h3><span class="chip pub">PUBLIC</span><span class="sub">$M, fiscal years to 31 Oct, from HPE's FY2025 Form 10-K</span></header>
          <div class="tbl-wrap"><table><thead><tr><th>Metric</th>${fy.map(y => `<th class="n">${y}</th>`).join("")}</tr></thead><tbody>
            ${rowsFin.map(([l, m]) => `<tr><td>${l}</td>${fy.map(y => `<td class="n ${cls((a[m] || {})[y])}">${(a[m] || {})[y] === undefined || (a[m] || {})[y] === null ? "n/a" : num((a[m] || {})[y] / 1e6)}</td>`).join("")}</tr>`).join("")}
          </tbody></table></div>
          <p class="section-title">Latest quarter: Q3 FY2026 segments</p>
          <div class="tbl-wrap"><table><thead><tr><th>Segment</th><th class="n">Revenue $M</th><th class="n">Operating profit $M</th><th class="n">Margin</th></tr></thead><tbody>
            ${Object.entries(h.segments_q3_fy2026 || {}).map(([s, v]) => `<tr><td>${esc(s)}</td><td class="n">${num(v.revenue / 1e6)}</td><td class="n ${cls(v.operating_profit)}">${num(v.operating_profit / 1e6)}</td><td class="n">${v.revenue ? pct(v.operating_profit / v.revenue, 1) : ""}</td></tr>`).join("")}
          </tbody></table></div></section>
      </div>
      <section class="panel"><header><h3>HPE AI facts</h3><span class="chip pub">PUBLIC</span><span class="sub">verbatim quotes from cited sources; order and backlog figures are company-reported KPIs</span></header>
        <div class="tbl-wrap"><table><thead><tr><th>ID</th><th>Topic</th><th>Fact</th><th>Quote</th><th>Source</th></tr></thead><tbody>
          ${(h.ai_facts || []).map(f => `<tr><td class="mono">${esc(f.id)}</td><td class="small">${esc(f.topic)}</td><td>${esc(f.claim)}</td><td class="small"><q>${esc(f.quote)}</q></td><td class="small"><a href="${esc(f.url)}" target="_blank" rel="noopener">${esc(f.source_title)}</a><div class="muted">${esc(f.date)}</div></td></tr>`).join("")}
        </tbody></table></div></section>
      <section class="panel"><header><h3>Source registry</h3><span class="sub">${src.sources.length} public sources used by the RAG corpus, product mapping and financial context</span></header>
        <div class="tbl-wrap"><table><thead><tr><th>ID</th><th>Title</th><th>Publisher</th><th>Type</th><th>Date</th></tr></thead><tbody>
          ${src.sources.map(s => `<tr><td class="mono">${esc(s.source_id)}</td><td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a></td><td class="small">${esc(s.publisher)}</td><td class="small">${esc(s.source_type)}</td><td class="mono">${esc(s.date)}</td></tr>`).join("")}
        </tbody></table></div></section>
      <section class="panel" id="auditp"><header><h3>Audit log</h3><span class="sub">CFO role only</span></header><div id="audit" class="small muted">Loading…</div></section>`;
    try {
      const log = await get("/audit");
      $("#audit").innerHTML = `<div class="tbl-wrap"><table><thead><tr><th>#</th><th>Time (UTC)</th><th>User</th><th>Role</th><th>Action</th><th>Detail</th><th>Response SHA-256</th></tr></thead><tbody>
        ${log.slice(0, 40).map(x => `<tr><td class="mono">${x.id}</td><td class="mono">${esc(x.timestamp)}</td><td class="small">${esc(x.user_id)}</td><td>${esc(x.role)}</td><td class="mono">${esc(x.action)}</td><td class="small">${esc(x.detail && x.detail.question ? x.detail.question + " → " + x.detail.intent : JSON.stringify(x.detail).slice(0, 120))}</td><td class="mono small">${esc((x.result_sha256 || "").slice(0, 16))}</td></tr>`).join("")}</tbody></table></div>`;
    } catch (err) { $("#audit").textContent = err.message.includes("lacks") ? "Your role cannot view the audit log." : err.message; }
  };

  RENDER.report = async (el, arg) => {
    el.innerHTML = `<div class="filters"><button class="btn primary" id="gen">Generate CFO Briefing</button><span class="muted small">Assembled from engine outputs. Neutral language; decisions rest with management.</span></div><div id="rep"></div>`;
    const gen = async () => {
      $("#rep").innerHTML = '<div class="loading">Generating…</div>';
      try {
        const b = await post("/reports/cfo", { format: "json" });
        const k = b.kpis;
        $("#rep").innerHTML = `<article class="report"><div><p class="section-title">Board / CFO briefing · ${esc(b.scope)}</p><h2>${esc(b.title)}</h2><p class="muted small">${esc(b.subtitle)} · generated ${esc(b.generated)}</p></div>
          <div class="banner">${esc(b.disclaimer)}</div>
          <div class="kpis">${[["Investment", money(k.total_investment)], ["Realised value", money(k.realised_value)], ["Expected value", money(k.expected_value)], ["Realised ROI", pct(k.realised_roi)], ["At-risk initiatives", k.at_risk]].map(t => `<div class="kpi"><div class="l">${t[0]}</div><div class="v">${t[1]}</div></div>`).join("")}</div>
          ${b.sections.map(s => `<section><h4>${esc(s.heading)}</h4><ul>${s.points.map(p => `<li>${esc(p)}</li>`).join("")}</ul></section>`).join("")}
          <div class="filters"><button class="btn sm" id="copymd">Copy as Markdown</button><span id="copied" class="muted small"></span></div></article>`;
        $("#copymd").onclick = async () => {
          const md = `# ${b.title}\n*${b.subtitle}*\n\n> ${b.disclaimer}\n\n` + b.sections.map(s => `## ${s.heading}\n` + s.points.map(p => `- ${p}`).join("\n")).join("\n\n");
          try { await navigator.clipboard.writeText(md); $("#copied").textContent = "Copied"; } catch (e) { $("#copied").textContent = "Copy is blocked here; select the text instead."; }
        };
      } catch (err) { $("#rep").innerHTML = `<p class="err">${esc(err.message)}</p>`; }
    };
    $("#gen").onclick = gen;
    if (arg === "generate" || SNAP) gen();
  };

  /* ------------------------------------------------------------ auth + boot */
  function logout() { store.set("avcc_token", null); store.set("avcc_user", null); S.token = null; location.hash = ""; loginView(); }
  async function loginView(msg) {
    let users = [];
    try { users = await (await fetch("/auth/demo-users")).json(); } catch (e) { /* offline */ }
    $("#app").innerHTML = `<div class="login"><form class="card" id="lf">
      <div><b style="font-size:18px">AI Value Command Centre</b><div class="muted small">Are we actually getting value from AI?</div></div>
      <div class="banner">Portfolio prototype. Public HPE information plus clearly labelled SYNTHETIC data for a fictional enterprise. Nothing here is HPE internal data.</div>
      <label for="lu">Demo user<select id="lu">${users.map(u => `<option value="${esc(u.user_id)}">${esc(u.display_name)} (${esc(u.role)}${u.bu_id ? ", " + esc(u.bu_id) : ""})</option>`).join("")}</select></label>
      <label for="lp">Password<input id="lp" type="password" value="" autocomplete="current-password" placeholder="demo password (AVCC_DEMO_PASSWORD)"></label>
      ${msg ? `<div class="err">${esc(msg)}</div>` : ""}
      <button class="btn primary" type="submit">Sign in</button>
      <div class="muted small">Roles: CFO sees everything including the audit log; Finance sees the whole portfolio; a business-unit leader sees only their unit.</div></form></div>`;
    $("#lf").onsubmit = async e => {
      e.preventDefault();
      const r = await fetch("/auth/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ user_id: $("#lu").value, password: $("#lp").value }) });
      if (!r.ok) return loginView("Sign-in failed: check the password.");
      const j = await r.json(); S.token = j.token; S.user = j.user; store.set("avcc_token", j.token); store.set("avcc_user", JSON.stringify(j.user));
      for (const k in cache) delete cache[k];
      S.meta = null; S.thread = []; boot();
    };
  }
  function boot() {
    shell();
    const h = (location.hash || "").replace("#", "");
    go(PAGES.some(p => p[0] === h) ? h : "command");
  }
  // re-theme charts when the viewer's theme changes
  const rerender = () => { if (S.user && $("#page")) go(S.page); };
  try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", rerender); } catch (e) { /* old browsers */ }
  new MutationObserver(rerender).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });

  if (SNAP) { S.user = SNAP.user; boot(); }
  else {
    S.token = store.get("avcc_token");
    try { S.user = JSON.parse(store.get("avcc_user") || "null"); } catch (e) { S.user = null; }
    if (S.token && S.user) boot(); else loginView();
  }
})();
