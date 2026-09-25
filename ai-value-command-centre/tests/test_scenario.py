import json
import shutil
import subprocess

import pytest

from src import settings
from src.scenario.engine import run


@pytest.fixture(scope="module")
def eng(ctx):
    return ctx.scenario


def test_baseline_has_no_change(eng):
    r = eng.run({})
    assert r["incremental"]["value"] == pytest.approx(0) and r["incremental"]["cost"] == pytest.approx(0)
    assert r["scenario"]["expected_value"] == pytest.approx(r["base"]["expected_value"])


def test_utilisation_scenario_follows_documented_formula(eng):
    b, A = eng.base, eng.assumptions
    r = eng.run({"utilisation_target": 0.80})
    hours = b["capacity_gpu_hours_annual"] * (0.80 - b["utilisation"])
    assert r["incremental"]["capacity_gpu_hours"] == pytest.approx(hours)
    assert r["incremental"]["value"] == pytest.approx(hours * b["value_per_used_gpu_hour"] * A["A-33"])
    assert r["incremental"]["cost"] == pytest.approx(hours * (b["non_infra_investment_per_used_gpu_hour"] * A["A-36"] + A["A-34"]))
    inc = r["incremental"]
    assert inc["roi"] == pytest.approx((inc["value"] - inc["cost"]) / inc["cost"])
    assert inc["payback_months"] == pytest.approx(inc["cost"] / (inc["value"] / 12))


def test_levers_move_value_in_the_expected_direction(eng):
    base = eng.run({})["scenario"]["net_value"]
    assert eng.run({"benefit_realisation": 0.8})["scenario"]["net_value"] < base
    assert eng.run({"cloud_cost_change": 0.2})["scenario"]["net_value"] < base
    assert eng.run({"adoption_change": 0.1})["scenario"]["net_value"] > base
    assert eng.run({"project_delay_months": 3})["scenario"]["net_value"] < base


def test_sensitivity_is_sorted_by_swing(eng):
    s = eng.sensitivity()
    assert [x["swing"] for x in s] == sorted([x["swing"] for x in s], reverse=True)


def test_scenario_is_reproducible(eng):
    assert run(eng.base, {"utilisation_target": 0.8}, eng.assumptions) == run(eng.base, {"utilisation_target": 0.8}, eng.assumptions)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_browser_engine_matches_python(eng):
    cases = [{}, {"utilisation_target": 0.8}, {"additional_investment": 1e7}, {"benefit_realisation": 0.8, "cloud_cost_change": 0.2},
             {"adoption_change": 0.2, "project_delay_months": 3, "implementation_cost_change": 0.1}]
    js = settings.WEB_DIR / "scenario.js"
    prog = f"const s=require({json.dumps(str(js))});const b={json.dumps(eng.base)};const A={json.dumps(eng.assumptions)};" \
           f"console.log(JSON.stringify({json.dumps(cases)}.map(c=>s.run(b,c,A))));"
    out = json.loads(subprocess.run(["node", "-e", prog], capture_output=True, text=True, check=True).stdout)
    for case, js_res in zip(cases, out):
        py = run(eng.base, case, eng.assumptions)
        for part in ("base", "scenario", "incremental"):
            for k, v in py[part].items():
                if isinstance(v, float):
                    assert js_res[part][k] == pytest.approx(v, rel=1e-9, abs=1e-6), (case, part, k)
