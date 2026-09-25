"""Relational data model (SQLAlchemy Core). Portable across SQLite (default) and PostgreSQL.

Two clearly separated data domains:
* SYNTHETIC enterprise data (every synthetic table carries `data_label`), and
* PUBLIC HPE information (`hpe_products`, `hpe_sources`, `hpe_financials`, `documents`), each row cited to a URL.
"""
from __future__ import annotations

from sqlalchemy import Boolean, Column, Float, Integer, MetaData, String, Table, Text

metadata = MetaData()


def _t(name: str, *cols: Column, synthetic: bool = True) -> Table:
    extra = [Column("data_label", String(16), nullable=False, default="SYNTHETIC")] if synthetic else []
    return Table(name, metadata, *cols, *extra)


S, F, I, B, T = String(200), Float, Integer, Boolean, Text

companies = _t("companies", Column("company_id", String(10), primary_key=True), Column("name", S), Column("industry", S),
               Column("fiscal_year_end", S), Column("employees", I), Column("customers", I),
               Column("annual_revenue_fy2025", F), Column("reporting_currency", String(3)), Column("note", T))
business_units = _t("business_units", Column("bu_id", String(10), primary_key=True), Column("company_id", String(10)),
                    Column("name", S), Column("leader_role", S), Column("headcount", I))
cost_centres = _t("cost_centres", Column("cost_centre_id", String(20), primary_key=True), Column("bu_id", String(10)), Column("name", S))
ai_initiatives = _t("ai_initiatives", Column("initiative_id", String(10), primary_key=True), Column("name", S), Column("bu_id", String(10)),
                    Column("geography", S), Column("hpe_category", S), Column("hpe_product_ids", S), Column("use_case", T),
                    Column("cluster_id", S), Column("start_date", String(10)), Column("planned_go_live", String(10)),
                    Column("actual_go_live", String(10)), Column("target_completion", String(10)), Column("status", S),
                    Column("budget", F), Column("users_target", I), Column("adoption_target", F),
                    Column("incremental_opex_plan", F), Column("owner", S))
milestones = _t("milestones", Column("id", I, primary_key=True, autoincrement=True), Column("initiative_id", String(10)),
                Column("milestone", S), Column("planned_date", String(10)), Column("actual_date", String(10)),
                Column("forecast_date", String(10)), Column("status", S))
investment_transactions = _t("investment_transactions", Column("funding_id", String(30), primary_key=True),
                             Column("initiative_id", String(10)), Column("approval_date", String(10)), Column("gate", S),
                             Column("approved_amount", F), Column("approver", S))
cost_transactions = _t("cost_transactions", Column("transaction_id", String(12), primary_key=True), Column("initiative_id", String(10)),
                       Column("month", String(7)), Column("cost_category", S), Column("cost_group", S), Column("cost_type", S),
                       Column("vendor_id", S), Column("cost_centre_id", S), Column("amount", F), Column("description", T))
budgets = _t("budgets", Column("id", I, primary_key=True, autoincrement=True), Column("initiative_id", String(10)),
             Column("month", String(7)), Column("cost_category", S), Column("cost_group", S), Column("budget_amount", F))
forecasts = _t("forecasts", Column("id", I, primary_key=True, autoincrement=True), Column("initiative_id", String(10)),
               Column("forecast_version", S), Column("horizon", S), Column("measure", S), Column("amount", F))
benefits = _t("benefits", Column("benefit_id", String(12), primary_key=True), Column("initiative_id", String(10)),
              Column("benefit_type", S), Column("description", T), Column("driver", S), Column("driver_unit", S),
              Column("unit_value", F), Column("business_case_value", F), Column("owner_forecast_value", F),
              Column("evidence_type", S), Column("methodology", S), Column("residual_reason", S),
              Column("finance_validated", B), Column("owner_confirmed", B), Column("assumption_ids", S), Column("benefit_owner", S))
benefit_monthly = _t("benefit_monthly", Column("id", I, primary_key=True, autoincrement=True), Column("benefit_id", String(12)),
                     Column("initiative_id", String(10)), Column("month", String(7)), Column("benefit_type", S),
                     Column("business_case_value", F), Column("measured_value", F), Column("realised_value", F),
                     Column("validated_value", F), Column("driver_volume", F))
benefit_evidence = _t("benefit_evidence", Column("evidence_id", String(20), primary_key=True), Column("benefit_id", String(12)),
                      Column("evidence_kind", S), Column("dataset", S), Column("period_from", String(7)), Column("period_to", String(7)),
                      Column("amount_covered", F), Column("validated_by", S), Column("quality", S), Column("evidence_date", String(10)))
ai_usage = _t("ai_usage", Column("id", I, primary_key=True, autoincrement=True), Column("initiative_id", String(10)),
              Column("month", String(7)), Column("licensed_users", I), Column("planned_active_users", I), Column("active_users", I),
              Column("adoption_rate", F), Column("interactions", I), Column("transactions", I), Column("transaction_type", S),
              Column("gpu_hours", F))
infrastructure_usage = _t("infrastructure_usage", Column("id", I, primary_key=True, autoincrement=True), Column("cluster_id", S),
                          Column("month", String(7)), Column("cluster_name", S), Column("platform", S), Column("region", S),
                          Column("hpe_product_id", S), Column("gpus", I), Column("gpu_hours_capacity", F), Column("gpu_hours_used", F),
                          Column("utilisation", F), Column("infrastructure_cost", F), Column("energy_kwh", F))
risks = _t("risks", Column("risk_id", String(8), primary_key=True), Column("initiative_id", String(10)), Column("category", S),
           Column("title", T), Column("financial_impact", F), Column("probability", F), Column("probability_basis", S),
           Column("mitigation", T), Column("owner", S), Column("status", S))
assumptions = _t("assumptions", Column("assumption_id", String(8), primary_key=True), Column("description", T), Column("value", F),
                 Column("unit", S), Column("category", S), Column("source", S), Column("owner", S), Column("last_reviewed", String(10)),
                 Column("initiative_id", String(10)))
vendors = _t("vendors", Column("vendor_id", String(12), primary_key=True), Column("name", S), Column("vendor_type", S))
financials = _t("financials", Column("id", I, primary_key=True, autoincrement=True), Column("month", String(7)), Column("bu_id", String(10)),
                Column("account", S), Column("amount", F), Column("ai_programme_spend", F), Column("ai_attributed_benefit", F))

# ---- public HPE information (cited) ----
hpe_sources = _t("hpe_sources", Column("source_id", String(20), primary_key=True), Column("title", T), Column("publisher", S),
                 Column("url", T), Column("date", String(10)), Column("source_type", S), Column("topic", S), synthetic=False)
hpe_products = _t("hpe_products", Column("product_id", String(20), primary_key=True), Column("name", S), Column("category", S),
                  Column("public_description", T), Column("source_id", String(20)), synthetic=False)
hpe_financials = _t("hpe_financials", Column("id", I, primary_key=True, autoincrement=True), Column("metric", S), Column("segment", S),
                    Column("period", S), Column("value", F), Column("unit", S), Column("source_id", String(20)), Column("note", T), synthetic=False)
documents = _t("documents", Column("chunk_id", String(40), primary_key=True), Column("doc_id", S), Column("title", T), Column("url", T),
               Column("date", String(10)), Column("topic", S), Column("source_type", S), Column("text", T), synthetic=False)

# ---- platform ----
users = Table("users", metadata, Column("user_id", String(40), primary_key=True), Column("display_name", S), Column("role", S),
              Column("bu_id", String(10)), Column("password_hash", S))
audit_log = Table("audit_log", metadata, Column("id", I, primary_key=True, autoincrement=True), Column("timestamp", String(32)),
                  Column("user_id", String(40)), Column("role", S), Column("action", S), Column("detail", T), Column("result_sha256", String(64)))

SYNTHETIC_TABLES = [t.name for t in metadata.sorted_tables if "data_label" in t.c]
PUBLIC_TABLES = ["hpe_sources", "hpe_products", "hpe_financials", "documents"]
