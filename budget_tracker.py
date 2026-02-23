#!/usr/bin/env python3
"""
BlackRoad Budget Tracker — Government budget planning and expenditure tracking
"""

import sqlite3
import json
import uuid
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List
from enum import Enum
from pathlib import Path


DB_PATH = Path("budget_tracker.db")


class BudgetStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"
    ACTIVE = "active"
    CLOSED = "closed"


@dataclass
class Budget:
    title: str
    fiscal_year: int
    total_amount: float
    department: str
    status: BudgetStatus = BudgetStatus.DRAFT
    budget_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    notes: str = ""


@dataclass
class BudgetLine:
    budget_id: str
    category: str
    subcategory: str
    allocated: float
    spent: float = 0.0
    committed: float = 0.0
    line_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    @property
    def available(self) -> float:
        return self.allocated - self.spent - self.committed

    @property
    def utilization_pct(self) -> float:
        if self.allocated == 0:
            return 0.0
        return round((self.spent / self.allocated) * 100, 2)


@dataclass
class Expenditure:
    budget_line_id: str
    vendor: str
    amount: float
    description: str
    approved_by: str
    date: str
    expenditure_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    receipt_ref: Optional[str] = None
    category: str = ""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Initialize database schema."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS budgets (
            budget_id       TEXT PRIMARY KEY,
            title           TEXT NOT NULL,
            fiscal_year     INTEGER NOT NULL,
            total_amount    REAL NOT NULL,
            department      TEXT NOT NULL,
            status          TEXT DEFAULT 'draft',
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL,
            approved_by     TEXT,
            approved_at     TEXT,
            notes           TEXT DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS budget_lines (
            line_id         TEXT PRIMARY KEY,
            budget_id       TEXT NOT NULL,
            category        TEXT NOT NULL,
            subcategory     TEXT NOT NULL,
            allocated       REAL NOT NULL,
            spent           REAL DEFAULT 0.0,
            committed       REAL DEFAULT 0.0,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (budget_id) REFERENCES budgets(budget_id)
        );

        CREATE TABLE IF NOT EXISTS expenditures (
            expenditure_id  TEXT PRIMARY KEY,
            budget_line_id  TEXT NOT NULL,
            vendor          TEXT NOT NULL,
            amount          REAL NOT NULL,
            description     TEXT NOT NULL,
            approved_by     TEXT NOT NULL,
            date            TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            receipt_ref     TEXT,
            category        TEXT DEFAULT '',
            FOREIGN KEY (budget_line_id) REFERENCES budget_lines(line_id)
        );

        CREATE TABLE IF NOT EXISTS audit_log (
            log_id      TEXT PRIMARY KEY,
            budget_id   TEXT,
            action      TEXT NOT NULL,
            details     TEXT,
            timestamp   TEXT NOT NULL,
            user_id     TEXT DEFAULT 'system'
        );
    """)
    conn.commit()
    conn.close()


def _log(budget_id: str, action: str, details: str = "", user_id: str = "system"):
    conn = get_connection()
    conn.execute(
        "INSERT INTO audit_log VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), budget_id, action, details, datetime.utcnow().isoformat(), user_id)
    )
    conn.commit()
    conn.close()


def create_budget(title: str, fiscal_year: int, total_amount: float, department: str,
                  notes: str = "") -> Budget:
    """Create a new budget."""
    init_db()
    budget = Budget(title=title, fiscal_year=fiscal_year, total_amount=total_amount,
                    department=department, notes=notes)
    conn = get_connection()
    conn.execute(
        "INSERT INTO budgets VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (budget.budget_id, title, fiscal_year, total_amount, department,
         budget.status.value, budget.created_at, budget.updated_at,
         None, None, notes)
    )
    conn.commit()
    conn.close()
    _log(budget.budget_id, "CREATE_BUDGET", f"Budget for {department} FY{fiscal_year}")
    return budget


def add_budget_line(budget_id: str, category: str, subcategory: str, allocated: float) -> BudgetLine:
    """Add a line item to a budget."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM budgets WHERE budget_id=?", (budget_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Budget {budget_id} not found")
    if row["status"] not in (BudgetStatus.DRAFT.value, BudgetStatus.APPROVED.value):
        conn.close()
        raise ValueError(f"Cannot add lines to budget in status: {row['status']}")
    line = BudgetLine(budget_id=budget_id, category=category, subcategory=subcategory, allocated=allocated)
    conn.execute(
        "INSERT INTO budget_lines VALUES (?,?,?,?,?,?,?,?)",
        (line.line_id, budget_id, category, subcategory, allocated, 0.0, 0.0, line.created_at)
    )
    conn.execute(
        "UPDATE budgets SET updated_at=? WHERE budget_id=?",
        (datetime.utcnow().isoformat(), budget_id)
    )
    conn.commit()
    conn.close()
    _log(budget_id, "ADD_LINE", f"{category}/{subcategory}: ${allocated:,.2f}")
    return line


def approve_budget(budget_id: str, approved_by: str) -> bool:
    """Approve a draft budget."""
    conn = get_connection()
    row = conn.execute("SELECT * FROM budgets WHERE budget_id=?", (budget_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Budget {budget_id} not found")
    if row["status"] != BudgetStatus.DRAFT.value:
        conn.close()
        raise ValueError(f"Only draft budgets can be approved")
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE budgets SET status=?, approved_by=?, approved_at=?, updated_at=? WHERE budget_id=?",
        (BudgetStatus.APPROVED.value, approved_by, now, now, budget_id)
    )
    conn.commit()
    conn.close()
    _log(budget_id, "APPROVE_BUDGET", f"Approved by {approved_by}")
    return True


def activate_budget(budget_id: str) -> bool:
    """Activate an approved budget."""
    conn = get_connection()
    row = conn.execute("SELECT status FROM budgets WHERE budget_id=?", (budget_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Budget {budget_id} not found")
    if row["status"] != BudgetStatus.APPROVED.value:
        conn.close()
        raise ValueError(f"Only approved budgets can be activated")
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE budgets SET status=?, updated_at=? WHERE budget_id=?",
        (BudgetStatus.ACTIVE.value, now, budget_id)
    )
    conn.commit()
    conn.close()
    _log(budget_id, "ACTIVATE_BUDGET")
    return True


def record_expenditure(line_id: str, vendor: str, amount: float, description: str,
                       approved_by: str, date: Optional[str] = None,
                       receipt_ref: Optional[str] = None) -> Expenditure:
    """Record an expenditure against a budget line."""
    conn = get_connection()
    line = conn.execute("SELECT * FROM budget_lines WHERE line_id=?", (line_id,)).fetchone()
    if not line:
        conn.close()
        raise ValueError(f"Budget line {line_id} not found")
    available = line["allocated"] - line["spent"] - line["committed"]
    if amount > available:
        conn.close()
        raise ValueError(f"Expenditure ${amount:,.2f} exceeds available ${available:,.2f}")
    exp_date = date or datetime.utcnow().isoformat()[:10]
    exp = Expenditure(
        budget_line_id=line_id, vendor=vendor, amount=amount,
        description=description, approved_by=approved_by, date=exp_date,
        receipt_ref=receipt_ref, category=line["category"]
    )
    conn.execute(
        "INSERT INTO expenditures VALUES (?,?,?,?,?,?,?,?,?,?)",
        (exp.expenditure_id, line_id, vendor, amount, description,
         approved_by, exp_date, exp.created_at, receipt_ref, line["category"])
    )
    conn.execute(
        "UPDATE budget_lines SET spent=spent+? WHERE line_id=?",
        (amount, line_id)
    )
    conn.commit()
    conn.close()
    _log(line["budget_id"], "RECORD_EXPENDITURE", f"{vendor}: ${amount:,.2f} — {description}")
    return exp


def commit_funds(line_id: str, amount: float, description: str) -> bool:
    """Commit (encumber) funds against a budget line."""
    conn = get_connection()
    line = conn.execute("SELECT * FROM budget_lines WHERE line_id=?", (line_id,)).fetchone()
    if not line:
        conn.close()
        raise ValueError(f"Budget line {line_id} not found")
    available = line["allocated"] - line["spent"] - line["committed"]
    if amount > available:
        conn.close()
        raise ValueError(f"Cannot commit ${amount:,.2f}, only ${available:,.2f} available")
    conn.execute(
        "UPDATE budget_lines SET committed=committed+? WHERE line_id=?",
        (amount, line_id)
    )
    conn.commit()
    conn.close()
    _log(line["budget_id"], "COMMIT_FUNDS", f"${amount:,.2f} — {description}")
    return True


def get_variance(budget_id: str) -> dict:
    """Calculate budget variance analysis."""
    conn = get_connection()
    budget = conn.execute("SELECT * FROM budgets WHERE budget_id=?", (budget_id,)).fetchone()
    if not budget:
        conn.close()
        raise ValueError(f"Budget {budget_id} not found")
    lines = conn.execute(
        "SELECT * FROM budget_lines WHERE budget_id=? ORDER BY category, subcategory",
        (budget_id,)
    ).fetchall()
    conn.close()

    total_allocated = sum(l["allocated"] for l in lines)
    total_spent = sum(l["spent"] for l in lines)
    total_committed = sum(l["committed"] for l in lines)
    total_available = total_allocated - total_spent - total_committed

    line_variances = []
    for l in lines:
        avail = l["allocated"] - l["spent"] - l["committed"]
        pct = round((l["spent"] / l["allocated"] * 100), 2) if l["allocated"] > 0 else 0.0
        line_variances.append({
            "line_id": l["line_id"],
            "category": l["category"],
            "subcategory": l["subcategory"],
            "allocated": l["allocated"],
            "spent": l["spent"],
            "committed": l["committed"],
            "available": avail,
            "utilization_pct": pct,
            "status": "over_budget" if avail < 0 else ("warning" if pct > 80 else "ok")
        })

    return {
        "budget_id": budget_id,
        "title": budget["title"],
        "fiscal_year": budget["fiscal_year"],
        "department": budget["department"],
        "status": budget["status"],
        "total_budget": budget["total_amount"],
        "total_allocated": total_allocated,
        "total_spent": total_spent,
        "total_committed": total_committed,
        "total_available": total_available,
        "overall_utilization_pct": round((total_spent / total_allocated * 100), 2) if total_allocated > 0 else 0.0,
        "unallocated": budget["total_amount"] - total_allocated,
        "lines": line_variances
    }


def compliance_check(budget_id: str) -> dict:
    """Run compliance checks on a budget."""
    variance = get_variance(budget_id)
    issues = []
    warnings = []

    if variance["unallocated"] < 0:
        issues.append(f"OVER-ALLOCATED: Lines exceed total budget by ${abs(variance['unallocated']):,.2f}")

    for line in variance["lines"]:
        if line["available"] < 0:
            issues.append(f"OVER-SPENT: {line['category']}/{line['subcategory']} by ${abs(line['available']):,.2f}")
        elif line["utilization_pct"] > 90:
            warnings.append(f"HIGH UTILIZATION ({line['utilization_pct']}%): {line['category']}/{line['subcategory']}")

    conn = get_connection()
    exps_without_receipt = conn.execute(
        """SELECT COUNT(*) FROM expenditures e
           JOIN budget_lines bl ON e.budget_line_id = bl.line_id
           WHERE bl.budget_id=? AND e.receipt_ref IS NULL""",
        (budget_id,)
    ).fetchone()[0]
    conn.close()

    if exps_without_receipt > 0:
        warnings.append(f"{exps_without_receipt} expenditure(s) missing receipt references")

    return {
        "budget_id": budget_id,
        "compliant": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "checked_at": datetime.utcnow().isoformat(),
    }


def executive_summary(budget_id: str) -> str:
    """Generate an executive summary report."""
    variance = get_variance(budget_id)
    compliance = compliance_check(budget_id)

    lines = [
        "=" * 65,
        "BUDGET EXECUTIVE SUMMARY",
        "=" * 65,
        f"Budget Title    : {variance['title']}",
        f"Department      : {variance['department']}",
        f"Fiscal Year     : {variance['fiscal_year']}",
        f"Status          : {variance['status'].upper()}",
        "",
        "FINANCIAL OVERVIEW",
        "-" * 40,
        f"  Total Budget   : ${variance['total_budget']:>15,.2f}",
        f"  Total Allocated: ${variance['total_allocated']:>15,.2f}",
        f"  Total Spent    : ${variance['total_spent']:>15,.2f}",
        f"  Total Committed: ${variance['total_committed']:>15,.2f}",
        f"  Available      : ${variance['total_available']:>15,.2f}",
        f"  Utilization    : {variance['overall_utilization_pct']:>14.1f}%",
        "",
        "LINE ITEMS",
        "-" * 40,
    ]
    for l in variance["lines"]:
        flag = "⚠" if l["status"] == "warning" else ("🔴" if l["status"] == "over_budget" else "✓")
        lines.append(f"  {flag} {l['category']}/{l['subcategory']}")
        lines.append(f"      Allocated: ${l['allocated']:,.2f} | Spent: ${l['spent']:,.2f} | {l['utilization_pct']}%")

    lines += [
        "",
        "COMPLIANCE STATUS",
        "-" * 40,
        f"  Status  : {'COMPLIANT ✓' if compliance['compliant'] else 'NON-COMPLIANT ✗'}",
    ]
    if compliance["issues"]:
        lines.append("  Issues:")
        for issue in compliance["issues"]:
            lines.append(f"    🔴 {issue}")
    if compliance["warnings"]:
        lines.append("  Warnings:")
        for warning in compliance["warnings"]:
            lines.append(f"    ⚠ {warning}")

    lines.append("=" * 65)
    return "\n".join(lines)


def get_expenditures(budget_id: str) -> List[dict]:
    """Get all expenditures for a budget."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT e.*, bl.category, bl.subcategory FROM expenditures e
           JOIN budget_lines bl ON e.budget_line_id = bl.line_id
           WHERE bl.budget_id=? ORDER BY e.date DESC""",
        (budget_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def close_budget(budget_id: str) -> bool:
    """Close an active budget at end of fiscal year."""
    conn = get_connection()
    row = conn.execute("SELECT status FROM budgets WHERE budget_id=?", (budget_id,)).fetchone()
    if not row:
        conn.close()
        raise ValueError(f"Budget {budget_id} not found")
    if row["status"] != BudgetStatus.ACTIVE.value:
        conn.close()
        raise ValueError(f"Only active budgets can be closed")
    now = datetime.utcnow().isoformat()
    conn.execute(
        "UPDATE budgets SET status=?, updated_at=? WHERE budget_id=?",
        (BudgetStatus.CLOSED.value, now, budget_id)
    )
    conn.commit()
    conn.close()
    _log(budget_id, "CLOSE_BUDGET")
    return True


def list_budgets(department: Optional[str] = None, fiscal_year: Optional[int] = None) -> List[dict]:
    """List budgets with optional filters."""
    conn = get_connection()
    query = "SELECT * FROM budgets WHERE 1=1"
    params = []
    if department:
        query += " AND department=?"
        params.append(department)
    if fiscal_year:
        query += " AND fiscal_year=?"
        params.append(fiscal_year)
    rows = conn.execute(query + " ORDER BY created_at DESC", params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def budget_stats() -> dict:
    """Get aggregate budget statistics."""
    conn = get_connection()
    total = conn.execute("SELECT COUNT(*) FROM budgets").fetchone()[0]
    total_allocated = conn.execute("SELECT COALESCE(SUM(total_amount),0) FROM budgets").fetchone()[0]
    total_spent = conn.execute("SELECT COALESCE(SUM(spent),0) FROM budget_lines").fetchone()[0]
    by_status = {}
    for s in BudgetStatus:
        cnt = conn.execute("SELECT COUNT(*) FROM budgets WHERE status=?", (s.value,)).fetchone()[0]
        by_status[s.value] = cnt
    conn.close()
    return {
        "total_budgets": total,
        "total_budget_amount": total_allocated,
        "total_spent": total_spent,
        "overall_utilization_pct": round(total_spent / total_allocated * 100, 2) if total_allocated > 0 else 0.0,
        "by_status": by_status,
    }


def cli():
    import sys
    if len(sys.argv) < 2:
        print("Usage: python budget_tracker.py <command>")
        print("Commands: create, add-line, approve, activate, spend, variance, compliance, summary, stats, list")
        return
    init_db()
    cmd = sys.argv[1]
    if cmd == "stats":
        print(json.dumps(budget_stats(), indent=2))
    elif cmd == "list":
        budgets = list_budgets()
        for b in budgets:
            print(f"[{b['status'].upper()}] {b['title']} — {b['department']} FY{b['fiscal_year']} ${b['total_amount']:,.2f}")
    elif cmd == "summary" and len(sys.argv) >= 3:
        print(executive_summary(sys.argv[2]))
    elif cmd == "variance" and len(sys.argv) >= 3:
        print(json.dumps(get_variance(sys.argv[2]), indent=2))
    elif cmd == "compliance" and len(sys.argv) >= 3:
        result = compliance_check(sys.argv[2])
        print(json.dumps(result, indent=2))
    else:
        print(f"Unknown command: {cmd}")


if __name__ == "__main__":
    cli()
