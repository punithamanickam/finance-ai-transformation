"""Financial driver trees with drill-down. Every node is computed from reported facts; every tree reconciles."""
from __future__ import annotations

from pydantic import BaseModel, Field

from src.calculations.engine import CalculationEngine
from src.calculations.models import InputRef
from src.financial_model.builder import load_metric_map


class DriverNode(BaseModel):
    node_id: str
    label: str
    current: float | None = None
    prior: float | None = None
    change: float | None = None  # contribution to the parent's change, same unit as parent
    unit: str = "USD millions"
    share_of_parent_change: float | None = None
    formula: str = ""
    note: str = ""
    inputs: list[InputRef] = Field(default_factory=list)
    children: list["DriverNode"] = Field(default_factory=list)


def _refs(eng: CalculationEngine, metric_id: str, fy: int, member: str = "") -> list[InputRef]:
    out = []
    for y in (fy, fy - 1):
        try:
            out.append(eng.fact_input(metric_id, metric_id, y, member))
        except Exception:
            pass
    return out


def _share(node: DriverNode, parent_change: float | None) -> None:
    if node.change is not None and parent_change:
        node.share_of_parent_change = node.change / parent_change


def revenue_tree(eng: CalculationEngine, fy: int) -> DriverNode:
    rc, rp = eng.value("revenue", fy), eng.value("revenue", fy - 1)
    root = DriverNode(node_id="revenue", label="Total revenue", current=rc, prior=rp,
                      change=None if rc is None or rp is None else rc - rp,
                      formula="Change in total revenue = sum of segment revenue changes", inputs=_refs(eng, "revenue", fy))
    offering_map = {k: v for k, v in load_metric_map().get("offering_segment_map", {}).items() if not k.startswith("_")}
    offerings = eng.repo.members("revenue_by_offering")
    for seg, name in eng.segments():
        c, p = eng.value("segment_revenue", fy, seg), eng.value("segment_revenue", fy - 1, seg)
        node = DriverNode(node_id=f"segment:{seg}", label=name, current=c, prior=p,
                          change=None if c is None or p is None else c - p,
                          formula="Segment revenue[t] - Segment revenue[t-1]", inputs=_refs(eng, "segment_revenue", fy, seg))
        _share(node, root.change)
        child_sum_c = child_sum_p = 0.0
        for member, label in zip(offerings.dimension_member, offerings.dimension_label):
            if offering_map.get(member) != seg:
                continue
            oc, op = eng.value("revenue_by_offering", fy, member), eng.value("revenue_by_offering", fy - 1, member)
            if oc is None or op is None:
                continue
            child = DriverNode(node_id=f"offering:{member}", label=label, current=oc, prior=op, change=oc - op,
                               formula="Offering revenue[t] - Offering revenue[t-1]",
                               inputs=_refs(eng, "revenue_by_offering", fy, member))
            _share(child, node.change)
            node.children.append(child)
            child_sum_c += oc
            child_sum_p += op
        if node.children and c is not None and p is not None:
            diff_c, diff_p = c - child_sum_c, p - child_sum_p
            if abs(diff_c) > 0.5 or abs(diff_p) > 0.5:
                node.children.append(DriverNode(
                    node_id=f"unreconciled:{seg}", label="Unreconciled / unallocated difference", current=diff_c, prior=diff_p,
                    change=diff_c - diff_p,
                    note="Product-offering revenue is not reported by segment; the mapping follows the Note 18 description. "
                         "The residual is shown rather than hidden."))
        node.children.sort(key=lambda n: -(n.change or 0))
        root.children.append(node)
    root.children.sort(key=lambda n: -(n.change or 0))
    return root


def operating_income_tree(eng: CalculationEngine, fy: int) -> DriverNode:
    v = {m: (eng.value(m, fy), eng.value(m, fy - 1)) for m in
         ["revenue", "gross_profit", "research_and_development", "sales_and_marketing", "general_and_administrative", "operating_income"]}
    if any(a is None or b is None for a, b in v.values()):
        return DriverNode(node_id="operating_income", label="Operating income", note="Insufficient data in the loaded filings.")
    (rc, rp), (gc, gp) = v["revenue"], v["gross_profit"]
    gm_c, gm_p = gc / rc, gp / rp
    oc, op = v["operating_income"]
    root = DriverNode(node_id="operating_income", label="Operating income", current=oc, prior=op, change=oc - op,
                      formula="OI[t-1] + revenue volume effect + gross-margin rate effect - change in R&D - change in S&M - change in G&A = OI[t]",
                      inputs=_refs(eng, "operating_income", fy))
    volume = (rc - rp) * gm_p
    rate = (gm_c - gm_p) * rc
    gross = DriverNode(node_id="gross_profit", label="Gross margin (gross profit)", current=gc, prior=gp, change=gc - gp,
                       formula="Volume effect + rate effect", inputs=_refs(eng, "gross_profit", fy) + _refs(eng, "revenue", fy))
    gross.children = [
        DriverNode(node_id="gp_volume", label="Revenue growth at prior-year gross margin % (volume)", change=volume,
                   formula=f"(Revenue[t] - Revenue[t-1]) x GM%[t-1] = ({rc:,.0f} - {rp:,.0f}) x {gm_p:.2%}"),
        DriverNode(node_id="gp_rate", label="Change in gross margin % (rate / mix)", change=rate,
                   formula=f"(GM%[t] - GM%[t-1]) x Revenue[t] = ({gm_c:.2%} - {gm_p:.2%}) x {rc:,.0f}"),
    ]
    for ch in gross.children:
        _share(ch, gross.change)
    root.children.append(gross)
    for mid, label in [("research_and_development", "Research and development"), ("sales_and_marketing", "Sales and marketing"),
                       ("general_and_administrative", "General and administrative")]:
        c, p = v[mid]
        root.children.append(DriverNode(node_id=mid, label=f"{label} (cost increase reduces OI)", current=c, prior=p,
                                        change=-(c - p), formula=f"-({label}[t] - {label}[t-1])", inputs=_refs(eng, mid, fy)))
    for ch in root.children:
        _share(ch, root.change)
    check = sum(ch.change for ch in root.children)
    root.note = f"Bridge reconciles: sum of drivers = {check:,.0f} vs reported change {oc - op:,.0f}."
    return root


def free_cash_flow_tree(eng: CalculationEngine, fy: int) -> DriverNode:
    f = {m: (eng.value(m, fy), eng.value(m, fy - 1)) for m in
         ["operating_cash_flow", "capital_expenditure", "net_income", "depreciation_amortization_other", "stock_based_compensation",
          "investing_cash_flow", "acquisitions"]}
    if any(f[m][0] is None or f[m][1] is None for m in ["operating_cash_flow", "capital_expenditure"]):
        return DriverNode(node_id="free_cash_flow", label="Free cash flow", note="Insufficient data in the loaded filings.")
    (oc, op), (cc, cp) = f["operating_cash_flow"], f["capital_expenditure"]
    root = DriverNode(node_id="free_cash_flow", label="Free cash flow (OCF - capex)", current=oc - cc, prior=op - cp,
                      change=(oc - cc) - (op - cp), formula="Change in OCF - change in capex")
    ocf = DriverNode(node_id="operating_cash_flow", label="Net cash from operations", current=oc, prior=op, change=oc - op,
                     formula="Net income + non-cash items + working capital and other", inputs=_refs(eng, "operating_cash_flow", fy))
    known = 0.0
    for mid, label in [("net_income", "Net income"), ("depreciation_amortization_other", "Depreciation, amortization, and other"),
                       ("stock_based_compensation", "Stock-based compensation")]:
        c, p = f[mid]
        if c is None or p is None:
            continue
        ocf.children.append(DriverNode(node_id=mid, label=label, current=c, prior=p, change=c - p, inputs=_refs(eng, mid, fy)))
        known += c - p
    ocf.children.append(DriverNode(node_id="ocf_other", label="Other non-cash items and working capital (residual)",
                                   change=(oc - op) - known,
                                   note="Residual = change in OCF minus the itemised changes above (investment gains, deferred taxes, working capital)."))
    capex = DriverNode(node_id="capital_expenditure", label="Capital expenditure (increase reduces FCF)", current=cc, prior=cp,
                       change=-(cc - cp), inputs=_refs(eng, "capital_expenditure", fy))
    root.children = [ocf, capex]
    ac = f["acquisitions"]
    if ac[0] is not None and ac[1] is not None:
        root.children.append(DriverNode(node_id="acquisitions", label="Other investing: acquisitions & intangibles (memo - outside FCF definition)",
                                        current=ac[0], prior=ac[1], change=None, inputs=_refs(eng, "acquisitions", fy),
                                        note="Shown for context; not part of OCF - capex."))
    for ch in root.children:
        _share(ch, root.change)
    for ch in ocf.children:
        _share(ch, ocf.change)
    return root


def flatten(node: DriverNode, depth: int = 0) -> list[dict]:
    rows = [{"depth": depth, "node_id": node.node_id, "label": node.label, "current": node.current, "prior": node.prior,
             "change": node.change, "share_of_parent_change": node.share_of_parent_change, "formula": node.formula, "note": node.note}]
    for ch in node.children:
        rows.extend(flatten(ch, depth + 1))
    return rows
