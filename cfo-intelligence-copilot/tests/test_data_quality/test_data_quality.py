"""Data-quality controls: accounting identities, reconciliations, units, currency, duplicates, missing values."""
import pandas as pd
import pytest

from src import settings
from src.governance.data_quality import coverage, run_checks


@pytest.fixture(scope="module")
def checks():
    return run_checks()


def _by(checks, category):
    return [c for c in checks if c.category == category]


@pytest.mark.parametrize("category", ["Balance sheet", "Cash flow", "Revenue", "Segments", "Income statement", "Calculations", "Integrity"])
def test_all_checks_pass(checks, category):
    cs = _by(checks, category)
    assert cs, f"no {category} checks ran"
    failed = [f"{c.name} FY{c.fiscal_year}: expected {c.expected} got {c.actual}" for c in cs if not c.passed]
    assert not failed, failed


def test_balance_sheet_balances_every_year(checks):
    years = {c.fiscal_year for c in _by(checks, "Balance sheet") if c.name.startswith("Total assets =")}
    assert {2025, 2026} <= years


def test_cash_flow_reconciliation_covers_three_years(checks):
    years = {c.fiscal_year for c in _by(checks, "Cash flow") if c.name.startswith("Operating + investing")}
    assert {2024, 2025, 2026} <= years


def test_no_duplicate_records():
    df = pd.read_csv(settings.FINANCIAL_FACTS_CSV)
    assert not df.fact_key.duplicated().any()


def test_every_fact_has_provenance():
    df = pd.read_csv(settings.FINANCIAL_FACTS_CSV)
    for col in ["source_document", "source_page", "source_section", "source_url", "unit", "fiscal_year"]:
        assert df[col].notna().all(), col
    assert (df[df.extraction_method == "ixbrl"].xbrl_concept.notna()).all()


def test_missing_values_are_flagged_not_filled():
    cov = coverage()
    # the loaded filings present balance sheets for FY2024-FY2026 only: FY2023 debt is flagged missing, not estimated
    assert not cov.loc[("Balance Sheet", "long_term_debt"), 2023]
    assert cov.loc[("Income Statement", "revenue"), [2023, 2024, 2025, 2026]].all()


def test_restatements_are_logged():
    c = pd.read_csv(settings.CONFLICTS_CSV)
    assert (c.conflict_type == "cross_filing_difference").any()
    assert not (c.conflict_type == "intra_filing_conflict").any()
