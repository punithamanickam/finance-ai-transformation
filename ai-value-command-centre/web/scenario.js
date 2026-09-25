/* Browser port of src/scenario/engine.py `run()`. Same formulas, same inputs; tests/test_scenario.py checks parity via node. */
(function (root) {
  const LEVERS = ["additional_investment", "utilisation_target", "cloud_cost_change", "productivity_change", "revenue_uplift_change",
    "adoption_change", "benefit_realisation", "project_delay_months", "implementation_cost_change"];
  const DEFAULTS = { additional_investment: 0, cloud_cost_change: 0, productivity_change: 0, revenue_uplift_change: 0, adoption_change: 0,
    benefit_realisation: 1, project_delay_months: 0, implementation_cost_change: 0 };

  function roi(v, i) { return i === 0 ? null : (v - i) / i; }

  function run(base, levers, A) {
    const lv = Object.assign({}, DEFAULTS, { utilisation_target: base.utilisation });
    for (const k of LEVERS) if (levers && levers[k] !== undefined && levers[k] !== null) lv[k] = Number(levers[k]);
    const bridge = [];
    const add = (lever, label, dv, dc, note) => {
      dv = dv || 0; dc = dc || 0;
      if (Math.abs(dv) > 0.005 || Math.abs(dc) > 0.005) bridge.push({ lever, label, value_change: dv, cost_change: dc, note: note || "" });
    };
    add("additional_investment", "Additional investment in proven use cases",
      lv.additional_investment * base.top_performer_value_per_dollar * A["A-35"], lv.additional_investment);
    const dUtil = lv.utilisation_target - base.utilisation;
    const dHours = base.capacity_gpu_hours_annual * dUtil;
    if (Math.abs(dUtil) > 1e-9) {
      add("utilisation_target", "Infrastructure utilisation (new workloads on existing capacity)",
        dHours * base.value_per_used_gpu_hour * A["A-33"], dHours * (base.non_infra_investment_per_used_gpu_hour * A["A-36"] + A["A-34"]));
    }
    add("cloud_cost_change", "Cloud cost", 0, base.cloud_spend * lv.cloud_cost_change);
    add("productivity_change", "Employee productivity", base.expected_productivity * lv.productivity_change, 0);
    add("revenue_uplift_change", "Revenue uplift", base.expected_revenue * lv.revenue_uplift_change, 0);
    add("adoption_change", "AI adoption (productivity benefits)", base.expected_productivity * lv.adoption_change, 0);
    add("implementation_cost_change", "Implementation cost", 0, base.investment * lv.implementation_cost_change);
    add("project_delay_months", "Project delay (in-flight initiatives)", -base.in_flight_expected_value * lv.project_delay_months * A["A-37"], 0);
    const gross = base.expected_benefit + bridge.reduce((s, b) => s + b.value_change, 0);
    add("benefit_realisation", "Benefit realisation rate", gross * (lv.benefit_realisation - 1), 0);
    const dV = bridge.reduce((s, b) => s + b.value_change, 0);
    const dC = bridge.reduce((s, b) => s + b.cost_change, 0);
    const sInv = base.investment + dC, sVal = base.expected_value + dV, monthly = dV / 12;
    return {
      levers: lv,
      base: { investment: base.investment, expected_value: base.expected_value, net_value: base.expected_value - base.investment,
        roi: roi(base.expected_value, base.investment), utilisation: base.utilisation },
      scenario: { investment: sInv, expected_value: sVal, net_value: sVal - sInv, roi: roi(sVal, sInv), utilisation: lv.utilisation_target },
      incremental: { cost: dC, value: dV, net_value: dV - dC, roi: dC > 0 ? roi(dV, dC) : null, capacity_gpu_hours: dHours,
        infrastructure_avoided: Math.max(dHours, 0) * base.infra_cost_per_capacity_gpu_hour,
        payback_months: dC > 0 && monthly > 0 ? dC / monthly : null },
      bridge,
      label: "ILLUSTRATIVE scenario on SYNTHETIC data - not a forecast",
    };
  }

  function sensitivity(base, A, swing) {
    swing = swing === undefined ? 0.2 : swing;
    const ref = run(base, {}, A).scenario.net_value;
    const tests = [
      ["utilisation_target", "Infrastructure utilisation (+/-10pp)", base.utilisation - 0.1, base.utilisation + 0.1],
      ["adoption_change", "AI adoption", -swing, swing], ["revenue_uplift_change", "Revenue uplift", -swing, swing],
      ["productivity_change", "Productivity improvement", -swing, swing], ["cloud_cost_change", "Cloud cost", swing, -swing],
      ["implementation_cost_change", "Implementation cost", swing, -swing], ["benefit_realisation", "Benefit realisation", 1 - swing, 1 + swing]];
    return tests.map(([lever, label, lo, hi]) => {
      const low = run(base, { [lever]: lo }, A).scenario.net_value - ref, high = run(base, { [lever]: hi }, A).scenario.net_value - ref;
      return { lever, label, low, high, swing: Math.abs(high - low), low_input: lo, high_input: hi };
    }).sort((a, b) => b.swing - a.swing);
  }

  const api = { run, sensitivity, LEVERS };
  if (typeof module !== "undefined" && module.exports) module.exports = api; else root.AVCCScenario = api;
})(typeof window !== "undefined" ? window : globalThis);
