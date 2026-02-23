# blackroad-budget-tracker

Government budget planning and expenditure tracking system.

## Features
- Create and manage multi-department budgets with fiscal year tracking
- Granular budget lines with category/subcategory allocation
- Record expenditures with vendor, approver, and receipt tracking
- Commit (encumber) funds before expenditure
- Variance analysis with over-budget detection
- Compliance checks with warning thresholds
- Executive summary reports

## Budget Lifecycle
`draft` → `approved` → `active` → `closed`

## Usage
```bash
python budget_tracker.py list
python budget_tracker.py stats
python budget_tracker.py variance <budget_id>
python budget_tracker.py compliance <budget_id>
python budget_tracker.py summary <budget_id>
```

## Run Tests
```bash
pip install pytest
pytest tests/ -v
```
