"""Design inputs for the SYNTHETIC enterprise scenario.

Everything in this module is fictional. It describes a fictional enterprise ("Meridian Enterprise Group") that runs
an AI programme on HPE portfolio categories. These are the *inputs* to the generator: plans, go-live dates, adoption,
unit values and cost mixes. The conclusions a CFO reaches (which initiatives are at risk, why ROI moved, how much
value is realised) are not written here; the analytics derive them from the generated transactions.

Fiscal year: September to August. FY2026 = Sep 2025 - Aug 2026 (the AI programme year). FY2025 is the pre-AI baseline.
Month index 0 = Sep 2025 ... 11 = Aug 2026.
"""
from __future__ import annotations

from dataclasses import dataclass, field

COMPANY = {
    "company_id": "MEG",
    "name": "Meridian Enterprise Group (fictional)",
    "industry": "Industrial technology and services",
    "fiscal_year_end": "31 August",
    "employees": 18_400,
    "customers": 42_000,
    "annual_revenue_fy2025": 6_380_000_000,
    "reporting_currency": "USD",
    "note": "Fictional enterprise used to demonstrate AI value management. Not HPE and not an HPE customer record.",
}

FY_MONTHS = [f"{y}-{m:02d}" for y, m in [(2025, 9), (2025, 10), (2025, 11), (2025, 12)] + [(2026, i) for i in range(1, 9)]]
FIN_MONTHS = [f"{y}-{m:02d}" for y, m in [(2024, 9), (2024, 10), (2024, 11), (2024, 12)] + [(2025, i) for i in range(1, 9)]] + FY_MONTHS
QUARTERS = {"FY26-Q1": [0, 1, 2], "FY26-Q2": [3, 4, 5], "FY26-Q3": [6, 7, 8], "FY26-Q4": [9, 10, 11]}

BUSINESS_UNITS = [
    # bu_id, name, leader (fictional role title), headcount
    ("BU-CUS", "Customer Operations", "Chief Customer Officer", 3_900),
    ("BU-SAL", "Sales & Commercial", "Chief Revenue Officer", 2_700),
    ("BU-SCM", "Supply Chain & Manufacturing", "Chief Operations Officer", 5_200),
    ("BU-FIN", "Finance", "Chief Financial Officer", 850),
    ("BU-TEC", "Technology & Security", "Chief Information Officer", 1_950),
    ("BU-COR", "Corporate Services", "Chief People Officer", 1_300),
    ("BU-ENG", "Engineering", "Chief Technology Officer", 2_500),
]

# Cost categories and how they roll into the value-bridge groups the CFO sees.
COST_CATEGORIES = {
    "compute": "Infrastructure", "gpu": "Infrastructure", "storage": "Infrastructure", "networking": "Infrastructure",
    "software": "Software", "saas": "Software",
    "employees": "People", "training": "People",
    "cloud": "Cloud",
    "consulting": "Services", "vendors": "Services",
    "data": "Other",
}
INFRA_CATEGORIES = ("compute", "gpu", "storage", "networking")

# Planned spend mix by deployment pattern (shares sum to 1).
COST_MIX = {
    "private_cloud_ai": {"gpu": .22, "compute": .08, "storage": .07, "networking": .04, "software": .10, "saas": .02,
                         "cloud": .02, "vendors": .05, "consulting": .10, "employees": .22, "training": .03, "data": .05},
    "greenlake": {"gpu": .06, "compute": .05, "storage": .04, "networking": .02, "software": .08, "saas": .06,
                  "cloud": .24, "vendors": .05, "consulting": .09, "employees": .23, "training": .03, "data": .05},
    "edge_network": {"gpu": .08, "compute": .07, "storage": .06, "networking": .14, "software": .10, "saas": .04,
                     "cloud": .06, "vendors": .07, "consulting": .10, "employees": .20, "training": .03, "data": .05},
    "hybrid_burst": {"gpu": .12, "compute": .05, "storage": .05, "networking": .03, "software": .08, "saas": .07,
                     "cloud": .16, "vendors": .04, "consulting": .08, "employees": .24, "training": .03, "data": .05},
}

VENDORS = {
    # vendor_id, name, type. Non-HPE vendors are deliberately generic.
    "gpu": ("V-HPE-INF", "HPE (AI infrastructure)", "technology"),
    "compute": ("V-HPE-INF", "HPE (AI infrastructure)", "technology"),
    "storage": ("V-HPE-INF", "HPE (AI infrastructure)", "technology"),
    "networking": ("V-HPE-NET", "HPE (networking)", "technology"),
    "cloud": ("V-HPE-GL", "HPE GreenLake (consumption)", "technology"),
    "software": ("V-SW-A", "AI software vendor A", "software"),
    "saas": ("V-SAAS-B", "SaaS provider B", "software"),
    "consulting": ("V-SI-C", "Systems integrator C", "services"),
    "vendors": ("V-SVC-D", "Managed services provider D", "services"),
    "data": ("V-DATA-E", "Data provider E", "data"),
    "employees": (None, "Internal staff", "internal"),
    "training": ("V-TRN-F", "Training provider F", "services"),
}
PUBLIC_CLOUD_VENDOR = ("V-PC-G", "Public cloud provider G", "technology")

CLUSTERS = {
    # cluster_id: (name, platform, region, hpe_product_id, GPUs by month (planned capacity decisions))
    "PCAI-EMEA-01": ("Private AI cluster EMEA", "HPE Private Cloud AI", "EMEA", "HPE-PCAI", [8, 8, 16, 16, 24, 24, 24, 24, 24, 28, 28, 28]),
    "PCAI-US-01": ("Private AI cluster Americas", "HPE Private Cloud AI", "Americas", "HPE-PCAI", [8, 8, 16, 16, 16, 16, 16, 16, 16, 24, 24, 24]),
    "GL-US-01": ("GreenLake AI compute Americas", "HPE GreenLake cloud", "Americas", "HPE-GL", [4, 4, 8, 8, 8, 8, 12, 12, 12, 12, 12, 12]),
    "GL-APJ-01": ("GreenLake AI compute APJ", "HPE GreenLake cloud", "APJ", "HPE-GL", [4, 4, 4, 8, 8, 8, 12, 12, 12, 12, 12, 12]),
    "PUB-GPU-01": ("Public cloud GPU burst", "Public cloud (non-HPE)", "Global", None, [0, 0, 4, 4, 4, 8, 8, 8, 8, 10, 10, 10]),
}


@dataclass
class BenefitLine:
    type: str  # revenue | cost_savings | productivity | risk
    description: str
    driver: str
    unit: str
    unit_value: float  # $ per driver unit (synthetic assumption)
    business_case: float  # $ FY2026 business case
    measured: float  # $ measured = realised + validated (synthetic outcome input)
    validated: float  # $ confirmed by business owner, not yet in financial / operational actuals
    evidence_type: str  # financial (GL-backed) | operational (telemetry-backed)
    methodology: str  # controlled_test | before_after | attribution_model | management_estimate
    residual_reason: str  # why value per unit differs from plan (leakage code), if it does
    finance_validated: bool
    owner_confirmed: bool
    assumption_ids: tuple[str, ...] = ()
    owner_forecast_share: float = 0.5  # share of the unevidenced remainder the owner still forecasts
    revision: tuple[int, float] | None = None  # (from month, multiplier): measured value per unit revised from a month


@dataclass
class Initiative:
    initiative_id: str
    name: str
    bu_id: str
    geography: str
    hpe_category: str
    hpe_products: tuple[str, ...]
    use_case: str
    cluster_id: str
    cost_mix: str
    start: int
    planned_go_live: int
    actual_go_live: int
    target_completion: str
    status: str  # PMO-reported delivery status (an input; "at risk" is derived by the analytics)
    budget: float
    actual_spend: float
    users_target: int
    adoption_plan: float
    adoption_actual: float
    interactions_per_user: float
    transaction_label: str
    transactions_per_interaction: float
    gpu_hours_per_1k_interactions: float
    incremental_opex_plan: float
    incremental_opex_actual: float
    owner: str
    benefits: list[BenefitLine] = field(default_factory=list)
    cost_shocks: list[tuple[str, int, float]] = field(default_factory=list)  # (category, from month, multiplier)
    public_cloud_share: float = 0.0  # share of 'cloud' spend on non-HPE public cloud


M = 1_000_000

INITIATIVES: list[Initiative] = [
    Initiative(
        "AI-001", "AI Customer Support Copilot", "BU-CUS", "EMEA", "HPE Private Cloud AI", ("HPE-PCAI", "HPE-NVIDIA", "HPE-ALLETRA"),
        "Agent-assist and self-service resolution for customer support", "PCAI-EMEA-01", "private_cloud_ai",
        0, 2, 2, "2026-03-31", "Live", 5.2 * M, 5.0 * M, 2_400, 0.85, 0.88, 310, "support cases handled", 0.18, 0.9,
        0.30 * M, 0.30 * M, "Director, Customer Service Operations",
        [BenefitLine("cost_savings", "Contact-handling cost reduction", "cases deflected or shortened", "case", 14.0,
                     5.4 * M, 5.4 * M, 0.3 * M, "financial", "controlled_test", "", True, True, ("A-01", "A-02"), 0.4),
         BenefitLine("productivity", "Agent time released for complex cases", "agent hours saved", "hour", 46.0,
                     1.6 * M, 1.5 * M, 0.3 * M, "operational", "before_after", "incorrect_assumptions", False, True, ("A-03",), 0.5)],
    ),
    Initiative(
        "AI-002", "AI Sales Forecasting", "BU-SAL", "Americas", "HPE GreenLake cloud", ("HPE-GL", "HPE-PCAI"),
        "Machine-learning pipeline forecast and deal-risk scoring", "GL-US-01", "greenlake",
        0, 3, 4, "2026-05-31", "Live", 2.8 * M, 3.1 * M, 900, 0.80, 0.72, 120, "forecast runs", 0.02, 3.5,
        0.10 * M, 0.14 * M, "VP Sales Operations",
        [BenefitLine("revenue", "Margin on revenue from improved win-rate", "attributed incremental gross margin", "$ margin", 1.0,
                     2.4 * M, 1.9 * M, 1.1 * M, "financial", "attribution_model", "benefit_measurement_problem", False, True, ("A-04", "A-05"), 0.6),
         BenefitLine("productivity", "Forecast preparation time saved", "sales-ops hours saved", "hour", 58.0,
                     0.8 * M, 0.7 * M, 0.1 * M, "operational", "before_after", "", False, True, ("A-06",), 0.5)],
    ),
    Initiative(
        "AI-003", "Supply Chain AI Optimisation", "BU-SCM", "Global", "HPE Private Cloud AI", ("HPE-PCAI", "HPE-NVIDIA", "HPE-ALLETRA", "HPE-SERVICES"),
        "Demand sensing, inventory and logistics optimisation", "PCAI-US-01", "private_cloud_ai",
        0, 3, 5, "2026-12-31", "Delayed", 7.25 * M, 8.4 * M, 1_100, 0.80, 0.45, 140, "planning scenarios", 0.05, 0.3,
        0.00 * M, 0.00 * M, "VP Supply Chain Planning",
        [BenefitLine("cost_savings", "Inventory carrying and expedite cost reduction", "carrying cost avoided", "$ cost", 1.0,
                     5.0 * M, 1.6 * M, 0.2 * M, "financial", "before_after", "technical_constraints", True, True, ("A-07", "A-08"), 0.6),
         BenefitLine("revenue", "Margin on sales recovered from higher fill-rate", "recovered gross margin", "$ margin", 1.0,
                     2.5 * M, 0.9 * M, 0.2 * M, "financial", "attribution_model", "incorrect_assumptions", False, True, ("A-09",), 0.6)],
        cost_shocks=[("gpu", 9, 2.0), ("compute", 9, 1.8), ("storage", 9, 1.5), ("consulting", 5, 1.35)],
    ),
    Initiative(
        "AI-004", "Finance Close Copilot", "BU-FIN", "Global", "HPE Private Cloud AI", ("HPE-PCAI", "HPE-NVIDIA"),
        "Reconciliation matching, variance commentary drafting and close checklist automation", "PCAI-US-01", "private_cloud_ai",
        1, 3, 3, "2026-04-30", "Live", 1.9 * M, 1.8 * M, 420, 0.90, 0.93, 260, "reconciliations processed", 0.35, 0.8,
        0.10 * M, 0.09 * M, "Group Financial Controller",
        [BenefitLine("productivity", "Close and reconciliation effort released", "finance hours saved", "hour", 62.0,
                     1.8 * M, 1.9 * M, 0.0 * M, "operational", "before_after", "", True, True, ("A-10",), 0.5),
         BenefitLine("cost_savings", "Reduced external audit support and contractor spend", "contractor spend avoided", "$ cost", 1.0,
                     0.6 * M, 0.6 * M, 0.0 * M, "financial", "before_after", "", True, True, ("A-11",), 0.5)],
    ),
    Initiative(
        "AI-005", "IT Service Desk AI", "BU-TEC", "Global", "HPE GreenLake cloud", ("HPE-GL", "HPE-OPSRAMP"),
        "Ticket triage, auto-resolution and knowledge suggestions for IT support", "GL-US-01", "greenlake",
        0, 2, 2, "2026-02-28", "Live", 2.1 * M, 2.0 * M, 18_000, 0.60, 0.62, 2.1, "tickets resolved", 1.0, 1.1,
        0.20 * M, 0.21 * M, "Head of IT Service Management",
        [BenefitLine("cost_savings", "Tier-1 service desk cost reduction", "tickets auto-resolved", "ticket", 22.0,
                     3.0 * M, 3.0 * M, 0.1 * M, "financial", "controlled_test", "", True, True, ("A-12",), 0.4),
         BenefitLine("productivity", "Employee downtime avoided", "employee hours restored", "hour", 38.0,
                     0.6 * M, 0.5 * M, 0.1 * M, "operational", "management_estimate", "incorrect_assumptions", False, True, ("A-13",), 0.5)],
    ),
    Initiative(
        "AI-006", "Enterprise Knowledge Copilot", "BU-COR", "Global", "HPE Private Cloud AI", ("HPE-PCAI", "HPE-NVIDIA", "HPE-ALLETRA"),
        "Retrieval-augmented assistant over policies, procedures and technical documentation", "PCAI-EMEA-01", "hybrid_burst",
        1, 4, 4, "2026-06-30", "Live", 3.6 * M, 3.9 * M, 12_000, 0.70, 0.31, 36, "questions answered", 1.0, 0.25,
        0.30 * M, 0.36 * M, "Chief People Officer (sponsor)",
        [BenefitLine("productivity", "Search and re-work time saved", "employee hours saved", "hour", 41.0,
                     4.4 * M, 2.6 * M, 0.9 * M, "operational", "management_estimate", "incorrect_assumptions", False, True, ("A-14", "A-15"), 0.6)],
        cost_shocks=[("cloud", 7, 1.45), ("saas", 8, 1.25), ("gpu", 9, 1.4)], public_cloud_share=0.7,
    ),
    Initiative(
        "AI-007", "Cybersecurity AI", "BU-TEC", "Global", "Networking", ("HPE-ARUBA", "HPE-JUNIPER", "HPE-GL"),
        "Anomaly detection and alert triage across network and endpoint telemetry", "GL-US-01", "edge_network",
        0, 3, 3, "2026-06-30", "Live", 3.0 * M, 3.2 * M, 160, 0.95, 0.94, 900, "alerts triaged", 0.9, 0.35,
        0.20 * M, 0.23 * M, "Chief Information Security Officer",
        [BenefitLine("risk", "Expected loss reduction from faster containment", "risk-weighted loss avoided", "$ loss", 1.0,
                     2.0 * M, 1.2 * M, 0.7 * M, "operational", "management_estimate", "incorrect_assumptions", False, True, ("A-16", "A-17"), 0.7),
         BenefitLine("cost_savings", "Security operations analyst overtime and MSSP fees avoided", "SOC cost avoided", "$ cost", 1.0,
                     0.9 * M, 0.8 * M, 0.1 * M, "financial", "before_after", "", True, True, ("A-18",), 0.4)],
    ),
    Initiative(
        "AI-008", "AI Infrastructure Optimisation", "BU-TEC", "Global", "AI Infrastructure", ("HPE-PROLIANT", "HPE-GL", "HPE-OPSRAMP"),
        "Workload placement, rightsizing and energy optimisation across data-centre estate", "GL-APJ-01", "greenlake",
        0, 2, 2, "2026-03-31", "Live", 4.5 * M, 4.6 * M, 1_200, 0.90, 0.92, 45, "workloads optimised", 0.1, 2.0,
        0.20 * M, 0.20 * M, "VP Infrastructure & Operations",
        [BenefitLine("cost_savings", "Data-centre, hosting and energy cost reduction", "infrastructure cost avoided", "$ cost", 1.0,
                     6.4 * M, 6.3 * M, 0.2 * M, "financial", "before_after", "", True, True, ("A-19", "A-20"), 0.4)],
    ),
    Initiative(
        "AI-009", "Predictive Maintenance", "BU-SCM", "APJ", "Networking", ("HPE-ARUBA", "HPE-ALLETRA", "HPE-GL"),
        "Sensor-based failure prediction for production lines", "GL-APJ-01", "edge_network",
        0, 4, 5, "2026-09-30", "Live", 3.4 * M, 3.3 * M, 650, 0.85, 0.80, 160, "asset predictions", 3.0, 3.0,
        0.20 * M, 0.19 * M, "Director, Manufacturing Engineering",
        [BenefitLine("cost_savings", "Unplanned downtime and maintenance cost reduction", "maintenance cost avoided", "$ cost", 1.0,
                     3.9 * M, 3.6 * M, 1.0 * M, "financial", "before_after", "", True, True, ("A-21", "A-22"), 0.5),
         BenefitLine("revenue", "Margin on output recovered from higher line availability", "recovered gross margin", "$ margin", 1.0,
                     0.6 * M, 0.4 * M, 0.2 * M, "financial", "attribution_model", "benefit_measurement_problem", False, True, ("A-23",), 0.5)],
    ),
    Initiative(
        "AI-010", "AI Revenue Intelligence", "BU-SAL", "Americas", "HPE GreenLake cloud", ("HPE-GL", "HPE-PCAI"),
        "Next-best-action, pricing guidance and churn signals for account teams", "GL-US-01", "greenlake",
        0, 3, 3, "2026-06-30", "Live", 3.3 * M, 3.6 * M, 1_500, 0.80, 0.74, 95, "account recommendations", 0.4, 1.6,
        0.30 * M, 0.34 * M, "Chief Revenue Officer (sponsor)",
        [BenefitLine("revenue", "Margin on incremental cross-sell and retained revenue", "attributed incremental gross margin", "$ margin", 1.0,
                     4.6 * M, 3.0 * M, 1.5 * M, "financial", "attribution_model", "incorrect_assumptions", False, True, ("A-24", "A-25"), 0.5,
                     revision=(9, 0.45))],
        cost_shocks=[("cloud", 9, 1.5)],
    ),
    Initiative(
        "AI-011", "Document Intelligence", "BU-COR", "EMEA", "HPE Private Cloud AI", ("HPE-PCAI", "HPE-ALLETRA"),
        "Contract, invoice and supplier-document extraction and review", "PCAI-EMEA-01", "private_cloud_ai",
        1, 3, 3, "2026-03-31", "Live", 1.5 * M, 1.4 * M, 380, 0.90, 0.90, 210, "documents processed", 1.0, 1.2,
        0.10 * M, 0.10 * M, "General Counsel (sponsor)",
        [BenefitLine("productivity", "Legal and procurement review time saved", "reviewer hours saved", "hour", 71.0,
                     1.2 * M, 1.2 * M, 0.1 * M, "operational", "before_after", "", False, True, ("A-26",), 0.5),
         BenefitLine("cost_savings", "Outsourced document processing avoided", "outsourcing cost avoided", "$ cost", 1.0,
                     0.9 * M, 0.8 * M, 0.0 * M, "financial", "before_after", "", True, True, ("A-27",), 0.4)],
    ),
    Initiative(
        "AI-012", "AI Developer Productivity", "BU-ENG", "APJ", "AI Infrastructure", ("HPE-PROLIANT", "HPE-GL", "HPE-NVIDIA"),
        "Code assistance, test generation and code review support", "GL-APJ-01", "hybrid_burst",
        0, 2, 2, "2026-04-30", "Live", 2.4 * M, 2.0 * M, 2_300, 0.75, 0.66, 140, "code suggestions accepted", 0.3, 0.45,
        0.30 * M, 0.23 * M, "VP Engineering Productivity",
        [BenefitLine("productivity", "Engineering capacity released", "engineer hours saved", "hour", 78.0,
                     3.5 * M, 3.3 * M, 1.4 * M, "operational", "management_estimate", "incorrect_assumptions", False, True, ("A-28", "A-29"), 0.6)],
        cost_shocks=[("cloud", 8, 1.55)], public_cloud_share=0.6,
    ),
]

# Business-case and planning assumptions. Referenced by benefit lines, scenarios and the evidence layer.
ASSUMPTIONS = [
    # id, description, value, unit, category, source, owner, last_reviewed, initiative_id
    ("A-01", "Share of support cases deflected or shortened by the copilot", 0.32, "share", "benefit", "Controlled pilot (Nov 2025)", "Customer Ops finance partner", "2026-07-15", "AI-001"),
    ("A-02", "Fully loaded cost per support case", 14.0, "USD per case", "benefit", "Cost-centre actuals FY2025", "FP&A", "2026-06-30", "AI-001"),
    ("A-03", "Agent minutes released per assisted case", 3.1, "minutes", "benefit", "Business case", "Customer Ops", "2025-08-20", "AI-001"),
    ("A-04", "Win-rate uplift attributable to improved forecasting", 0.012, "share points", "benefit", "Business case", "Sales Ops", "2025-08-20", "AI-002"),
    ("A-05", "Gross margin on incremental revenue", 0.34, "share", "benefit", "Group margin FY2025", "FP&A", "2026-06-30", None),
    ("A-06", "Sales-ops hours per forecast cycle before AI", 1_900, "hours per month", "benefit", "Time study", "Sales Ops", "2025-10-05", "AI-002"),
    ("A-07", "Inventory reduction from demand sensing", 0.06, "share of inventory", "benefit", "Business case (vendor benchmark)", "Supply Chain", "2025-07-30", "AI-003"),
    ("A-08", "Annual inventory carrying-cost rate", 0.18, "share", "benefit", "Treasury policy", "Treasury", "2026-05-31", "AI-003"),
    ("A-09", "Fill-rate improvement", 0.015, "share points", "benefit", "Business case", "Supply Chain", "2025-07-30", "AI-003"),
    ("A-10", "Close effort reduction", 0.22, "share of close hours", "benefit", "Close time-tracking", "Financial Controller", "2026-07-31", "AI-004"),
    ("A-11", "Contractor spend avoided during close", 50_000, "USD per month", "benefit", "AP actuals", "Financial Controller", "2026-07-31", "AI-004"),
    ("A-12", "Tier-1 tickets auto-resolved", 0.28, "share", "benefit", "Controlled rollout by region", "IT Service Management", "2026-06-15", "AI-005"),
    ("A-13", "Employee minutes restored per auto-resolved ticket", 25, "minutes", "benefit", "Management estimate", "IT Service Management", "2025-09-10", "AI-005"),
    ("A-14", "Minutes saved per employee per week from knowledge search", 45, "minutes", "benefit", "Business case (survey based)", "Corporate Services", "2025-08-01", "AI-006"),
    ("A-15", "Target active adoption of knowledge copilot", 0.70, "share of licensed users", "adoption", "Business case", "Corporate Services", "2025-08-01", "AI-006"),
    ("A-16", "Annualised expected loss from security incidents (baseline)", 9_600_000, "USD", "benefit", "Risk quantification workshop", "CISO", "2025-11-12", "AI-007"),
    ("A-17", "Reduction in expected loss from faster containment", 0.25, "share", "benefit", "Management estimate", "CISO", "2025-11-12", "AI-007"),
    ("A-18", "MSSP fee and overtime reduction", 0.15, "share", "benefit", "Vendor invoices", "Security Operations", "2026-06-30", "AI-007"),
    ("A-19", "Hosting cost reduction from rightsizing", 0.11, "share of hosting cost", "benefit", "Before/after hosting invoices", "Infrastructure", "2026-07-31", "AI-008"),
    ("A-20", "Energy cost per kWh", 0.14, "USD per kWh", "cost", "Utility contracts", "Facilities", "2026-03-31", None),
    ("A-21", "Unplanned downtime reduction", 0.18, "share of downtime hours", "benefit", "Plant maintenance logs", "Manufacturing Engineering", "2026-07-20", "AI-009"),
    ("A-22", "Cost per hour of unplanned downtime", 21_000, "USD per hour", "benefit", "Plant finance", "Plant Controller", "2026-02-28", "AI-009"),
    ("A-23", "Output recovered per avoided downtime hour", 0.6, "share of line output", "benefit", "Engineering estimate", "Manufacturing Engineering", "2025-10-01", "AI-009"),
    ("A-24", "Cross-sell conversion uplift", 0.035, "share points", "benefit", "Business case (revised Q4 from 0.06)", "Sales & Commercial", "2026-06-20", "AI-010"),
    ("A-25", "Churn reduction on flagged accounts", 0.02, "share points", "benefit", "Business case", "Sales & Commercial", "2025-08-15", "AI-010"),
    ("A-26", "Review minutes saved per document", 11, "minutes", "benefit", "Time study", "Legal Operations", "2026-04-15", "AI-011"),
    ("A-27", "Outsourced processing cost per document", 3.8, "USD", "benefit", "Supplier invoices", "Procurement", "2026-04-15", "AI-011"),
    ("A-28", "Engineer hours saved per active developer per month", 5.5, "hours", "benefit", "Developer survey plus telemetry", "Engineering Productivity", "2026-05-31", "AI-012"),
    ("A-29", "Share of released engineering capacity redeployed to roadmap work", 0.6, "share", "benefit", "Management estimate", "Engineering", "2025-09-15", "AI-012"),
    ("A-30", "Discount rate for AI investment appraisal", 0.09, "share", "finance", "Group treasury hurdle rate", "Treasury", "2026-01-15", None),
    ("A-31", "Benefit run-rate persistence in FY2027-FY2028", 0.9, "share of FY2026 exit run-rate", "finance", "FP&A planning convention", "FP&A", "2026-08-31", None),
    ("A-32", "Run-cost share of FY2026 spend continuing in FY2027-FY2028", 0.45, "share", "finance", "FP&A planning convention", "FP&A", "2026-08-31", None),
    ("A-33", "Value of incremental GPU capacity used (share of current value per used GPU-hour)", 0.55, "share", "scenario", "Scenario convention (diminishing returns)", "AI Programme Office", "2026-08-31", None),
    ("A-34", "Variable run cost per incremental used GPU-hour", 1.9, "USD per GPU-hour", "scenario", "Energy and operations estimate", "Infrastructure", "2026-08-31", None),
    ("A-35", "Diminishing-return factor on additional investment (share of top-performer value per $)", 0.85, "share", "scenario", "Scenario convention", "AI Programme Office", "2026-08-31", None),
    ("A-36", "Onboarding cost of new workloads per GPU-hour, as a share of current non-infrastructure investment per used GPU-hour", 1.0, "share", "scenario", "Scenario convention (software, people and services scale with workloads; infrastructure does not)", "AI Programme Office", "2026-08-31", None),
    ("A-37", "Share of annual value lost per month of project delay (in-flight initiatives)", 1 / 12, "share per month", "scenario", "Scenario convention", "AI Programme Office", "2026-08-31", None),
]

RISKS = [
    # id, initiative, category, title, impact $, probability (owner-assessed), mitigation, owner, status
    ("R-01", "AI-003", "Delivery", "Integration with planning system delayed go-live by six months", 2.6 * M, 0.7, "Dedicated integration squad; phased cut-over by region", "VP Supply Chain Planning", "Open"),
    ("R-02", "AI-003", "Financial", "GPU capacity added ahead of workload demand", 1.1 * M, 0.8, "Re-phase capacity; host other workloads on idle GPUs", "VP Infrastructure & Operations", "Open"),
    ("R-03", "AI-003", "Benefit-realisation", "Inventory reduction assumption based on vendor benchmark, not internal pilot", 1.5 * M, 0.5, "Run controlled test in two distribution centres", "Supply Chain finance partner", "Open"),
    ("R-04", "AI-006", "Adoption", "Active usage far below plan outside two business units", 2.0 * M, 0.7, "Embed in intranet and service portal; manager-led enablement", "Chief People Officer", "Open"),
    ("R-05", "AI-006", "Financial", "Public cloud inference cost growing faster than usage", 0.6 * M, 0.6, "Move steady-state inference to private cluster; token budgets", "Head of AI Platform", "Open"),
    ("R-06", "AI-006", "Data", "Knowledge sources out of date or duplicated", 0.4 * M, 0.5, "Content ownership model; freshness SLAs", "Knowledge Management Lead", "Mitigating"),
    ("R-07", "AI-010", "Benefit-realisation", "Cross-sell uplift revised down from business case", 1.8 * M, 0.6, "Re-baseline business case; holdout test in two regions", "Sales & Commercial finance partner", "Open"),
    ("R-08", "AI-010", "Regulatory", "Pricing-guidance model requires fairness and competition-law review", 0.3 * M, 0.3, "Legal review of guidance rules; human approval of price changes", "General Counsel", "Mitigating"),
    ("R-09", "AI-002", "Benefit-realisation", "Revenue attribution method not agreed with Finance", 0.9 * M, 0.5, "Agree attribution method; finance sign-off before recognition", "FP&A", "Open"),
    ("R-10", "AI-007", "Benefit-realisation", "Risk-reduction value based on management estimate of expected loss", 1.0 * M, 0.5, "Independent risk quantification; track incident metrics", "CISO", "Open"),
    ("R-11", "AI-007", "Security", "Model and prompt-injection exposure in alert triage", 0.5 * M, 0.2, "Red-team testing; human approval of containment actions", "CISO", "Mitigating"),
    ("R-12", "AI-012", "Benefit-realisation", "Productivity hours not converted into roadmap delivery or cost", 1.2 * M, 0.5, "Track throughput and cycle time; capacity redeployment plan", "VP Engineering Productivity", "Open"),
    ("R-13", "AI-012", "Vendor", "Public cloud pricing changes for code-assistant inference", 0.3 * M, 0.4, "Committed-use agreement; private hosting option", "Head of AI Platform", "Open"),
    ("R-14", "AI-001", "Regulatory", "EU AI Act transparency obligations for customer-facing assistant", 0.2 * M, 0.3, "Disclosure notices; conformity documentation", "Data Protection Officer", "Mitigating"),
    ("R-15", "AI-001", "Technology", "Model drift reduces deflection rate", 0.4 * M, 0.3, "Monthly evaluation set; retraining cadence", "Head of AI Platform", "Mitigating"),
    ("R-16", "AI-009", "Data", "Sensor coverage incomplete on older production lines", 0.5 * M, 0.4, "Retrofit sensors on priority lines", "Director, Manufacturing Engineering", "Open"),
    ("R-17", "AI-008", "Technology", "Workload moves create performance incidents", 0.2 * M, 0.2, "Change windows; automated rollback", "VP Infrastructure & Operations", "Closed"),
    ("R-18", "AI-004", "Regulatory", "Audit acceptance of AI-assisted reconciliations", 0.2 * M, 0.3, "Control documentation; reviewer sign-off retained", "Group Financial Controller", "Mitigating"),
    ("R-19", "AI-005", "Adoption", "Regional service desks bypass AI triage", 0.2 * M, 0.3, "Routing rules; weekly adoption review", "Head of IT Service Management", "Closed"),
    ("R-20", "AI-011", "Vendor", "Document-model licence renewal price uplift", 0.1 * M, 0.4, "Multi-year pricing; open-model fallback", "Procurement", "Open"),
]
