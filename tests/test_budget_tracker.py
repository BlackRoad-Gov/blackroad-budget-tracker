"""Tests for budget_tracker.py"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import budget_tracker as bt
bt.DB_PATH = Path("/tmp/test_budget_tracker.db")


@pytest.fixture(autouse=True)
def clean_db():
    if bt.DB_PATH.exists():
        bt.DB_PATH.unlink()
    bt.init_db()
    yield
    if bt.DB_PATH.exists():
        bt.DB_PATH.unlink()


def make_budget(**kwargs):
    defaults = dict(title="FY2025 Budget", fiscal_year=2025, total_amount=1_000_000.0, department="Finance")
    defaults.update(kwargs)
    return bt.create_budget(**defaults)


def test_create_budget():
    budget = make_budget()
    assert budget.title == "FY2025 Budget"
    assert budget.status == bt.BudgetStatus.DRAFT
    assert budget.total_amount == 1_000_000.0


def test_add_budget_line():
    budget = make_budget()
    line = bt.add_budget_line(budget.budget_id, "Personnel", "Salaries", 500_000.0)
    assert line.category == "Personnel"
    assert line.allocated == 500_000.0
    assert line.spent == 0.0


def test_approve_budget():
    budget = make_budget()
    bt.add_budget_line(budget.budget_id, "IT", "Software", 100_000.0)
    result = bt.approve_budget(budget.budget_id, "Director Smith")
    assert result is True
    budgets = bt.list_budgets()
    b = next(x for x in budgets if x["budget_id"] == budget.budget_id)
    assert b["status"] == bt.BudgetStatus.APPROVED.value


def test_activate_budget():
    budget = make_budget()
    bt.approve_budget(budget.budget_id, "Director")
    bt.activate_budget(budget.budget_id)
    budgets = bt.list_budgets()
    b = next(x for x in budgets if x["budget_id"] == budget.budget_id)
    assert b["status"] == bt.BudgetStatus.ACTIVE.value


def test_record_expenditure():
    budget = make_budget()
    line = bt.add_budget_line(budget.budget_id, "Operations", "Travel", 50_000.0)
    exp = bt.record_expenditure(line.line_id, "Delta Airlines", 1_200.0, "Conference travel", "Manager Jones")
    assert exp.vendor == "Delta Airlines"
    assert exp.amount == 1_200.0
    variance = bt.get_variance(budget.budget_id)
    spent_line = next(l for l in variance["lines"] if l["line_id"] == line.line_id)
    assert spent_line["spent"] == 1_200.0


def test_over_budget_error():
    budget = make_budget()
    line = bt.add_budget_line(budget.budget_id, "Legal", "Contracts", 10_000.0)
    with pytest.raises(ValueError, match="exceeds available"):
        bt.record_expenditure(line.line_id, "Law Firm", 15_000.0, "Legal fees", "CFO")


def test_compliance_check_clean():
    budget = make_budget()
    bt.add_budget_line(budget.budget_id, "HR", "Benefits", 200_000.0)
    result = bt.compliance_check(budget.budget_id)
    assert isinstance(result["compliant"], bool)
    assert "issues" in result


def test_variance_report():
    budget = make_budget()
    line = bt.add_budget_line(budget.budget_id, "Tech", "Cloud", 300_000.0)
    bt.record_expenditure(line.line_id, "AWS", 50_000.0, "Cloud hosting", "CTO")
    variance = bt.get_variance(budget.budget_id)
    assert variance["total_spent"] == 50_000.0
    assert variance["total_allocated"] == 300_000.0


def test_executive_summary():
    budget = make_budget()
    bt.add_budget_line(budget.budget_id, "Marketing", "Advertising", 100_000.0)
    summary = bt.executive_summary(budget.budget_id)
    assert "BUDGET EXECUTIVE SUMMARY" in summary
    assert "FY2025 Budget" in summary


def test_close_budget():
    budget = make_budget()
    bt.approve_budget(budget.budget_id, "Director")
    bt.activate_budget(budget.budget_id)
    bt.close_budget(budget.budget_id)
    budgets = bt.list_budgets()
    b = next(x for x in budgets if x["budget_id"] == budget.budget_id)
    assert b["status"] == bt.BudgetStatus.CLOSED.value


def test_stats():
    make_budget(title="B1", fiscal_year=2024)
    make_budget(title="B2", fiscal_year=2025)
    stats = bt.budget_stats()
    assert stats["total_budgets"] >= 2
