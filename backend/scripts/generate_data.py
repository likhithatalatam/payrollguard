
import json
import random
import hashlib
import calendar
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pandas as pd
from faker import Faker
from sqlalchemy import text

from app.database import engine


# --------------------------------------------------
# 1. CONFIGURATION
# --------------------------------------------------

SEED = 20261022
EMPLOYEE_COUNT = 3000

TIME_COUNT = 70000
ALLOWANCE_COUNT = 15000
DEDUCTION_COUNT = 15000

LEAVE_COUNT = 4500

fake = Faker("en_IN")
fake.seed_instance(SEED)
rng = random.Random(SEED)

PERIODS = [
    ("PP-2026-01", date(2026, 1, 1), date(2026, 1, 31),
     date(2026, 2, 5)),
    ("PP-2026-02", date(2026, 2, 1), date(2026, 2, 28),
     date(2026, 3, 5)),
    ("PP-2026-03", date(2026, 3, 1), date(2026, 3, 31),
     date(2026, 4, 5)),
]

PAY_GROUP_ID = "PG-001"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GENERATED_DIR = PROJECT_ROOT / "data" / "generated"
GROUND_TRUTH_DIR = PROJECT_ROOT / "data" / "ground_truth"
DOCS_DIR = PROJECT_ROOT / "docs"

GENERATED_DIR.mkdir(parents=True, exist_ok=True)
GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------
# 2. HELPER FUNCTIONS
# --------------------------------------------------

def money(value):
    return Decimal(str(value)).quantize(Decimal("0.01"))


def make_id(prefix, number):
    return f"{prefix}-{number:06d}"


def random_date(start_date, end_date):
    days = (end_date - start_date).days
    return start_date + timedelta(days=rng.randint(0, days))


def write_csv(name, records):
    path = GENERATED_DIR / name
    pd.DataFrame(records).to_csv(path, index=False)
    return path


def checksum(path):
    digest = hashlib.sha256()

    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def ensure_empty_database():
    tables = [
        "employees",
        "pay_groups",
        "pay_periods",
        "employee_pay_groups",
        "time_entries",
        "leave_records",
        "allowances",
        "deductions",
        "payroll_inputs",
        "exceptions",
        "approvals",
        "payroll_exports",
        "event_history",
    ]

    with engine.connect() as connection:
        populated = []

        for table in tables:
            count = connection.execute(
                text(f"SELECT COUNT(*) FROM `{table}`")
            ).scalar_one()

            if count > 0:
                populated.append(f"{table}: {count} records")

    if populated:
        raise RuntimeError(
            "Database is not empty. No records were changed.\n"
            + "\n".join(populated)
            + "\nDo not rerun this generator without a planned reset."
        )


# --------------------------------------------------
# 3. GENERATE PAY GROUPS AND PAY PERIODS
# --------------------------------------------------

def generate_pay_groups():
    return [{
        "pay_group_id": PAY_GROUP_ID,
        "group_name": "India Monthly Salaried",
        "pay_frequency": "MONTHLY",
        "currency": "INR",
        "is_active": 1,
    }]


def generate_pay_periods():
    records = []

    for period_id, start, end, pay_date in PERIODS:
        records.append({
            "pay_period_id": period_id,
            "pay_group_id": PAY_GROUP_ID,
            "start_date": start,
            "end_date": end,
            "pay_date": pay_date,
            "status": "CLOSED",
        })

    return records


# --------------------------------------------------
# 4. GENERATE EMPLOYEES
# --------------------------------------------------

def generate_employees():
    employees = []
    assignments = []

    for number in range(1, EMPLOYEE_COUNT + 1):
        employee_id = make_id("EMP", number)

        # Synthetic references only.
        # These are NOT real bank accounts or tax IDs.
        bank_ref = f"SYN-BANK-{employee_id}"
        tax_ref = f"SYN-TAX-{employee_id}"

        # Controlled missing-detail cases.
        if number <= 30:
            bank_ref = None

        if 31 <= number <= 60:
            tax_ref = None

        salary = rng.randint(300000, 1800000)

        employees.append({
            "employee_id": employee_id,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "email": f"{employee_id.lower()}@payrollguard.test",
            "hire_date": date(
                rng.randint(2019, 2025),
                rng.randint(1, 12),
                rng.randint(1, 28),
            ),
            "employment_status": "ACTIVE",
            "annual_salary": money(salary),
            "bank_account_ref": bank_ref,
            "tax_id_ref": tax_ref,
            "created_at": datetime(2025, 12, 1, 9, 0, 0),
        })

        assignments.append({
            "employee_id": employee_id,
            "pay_group_id": PAY_GROUP_ID,
            "effective_start": date(2025, 1, 1),
            "effective_end": None,
        })

    return employees, assignments


# --------------------------------------------------
# 5. GENERATE LEAVE RECORDS
# --------------------------------------------------

def generate_leave_records():
    records = []

    employee_periods = [
        (employee_number, period)
        for employee_number in range(1, EMPLOYEE_COUNT + 1)
        for period in PERIODS
    ]

    selected = rng.sample(employee_periods, LEAVE_COUNT)

    for number, (employee_number, period) in enumerate(
        selected, start=1
    ):
        employee_id = make_id("EMP", employee_number)
        period_id, period_start, period_end, _ = period

        start = random_date(period_start, period_end)
        max_days = min(3, (period_end - start).days + 1)
        days = rng.randint(1, max_days)
        end = start + timedelta(days=days - 1)

        leave_type = rng.choice([
            "ANNUAL",
            "SICK",
            "UNPAID",
        ])

        status = rng.choices(
            ["APPROVED", "PENDING", "REJECTED"],
            weights=[85, 10, 5],
        )[0]

        records.append({
            "leave_id": f"LEAVE-{employee_id}-{period_id}",
            "employee_id": employee_id,
            "start_date": start,
            "end_date": end,
            "leave_type": leave_type,
            "leave_days": money(days),
            "status": status,
        })

    return records


# --------------------------------------------------
# 6. GENERATE TIME ENTRIES
# --------------------------------------------------


def generate_time_entries():
    records = []
    used_employee_dates = set()

    # Reserve one employee/date for a duplicate submission.
    duplicate_employee = "EMP-000001"
    duplicate_period = PERIODS[0]
    duplicate_date = date(2026, 1, 12)

    used_employee_dates.add(
        (duplicate_employee, duplicate_date)
    )

    # Reserve one entry for an excess-hours case.
    excess_employee = "EMP-000002"
    excess_date = date(2026, 1, 13)

    used_employee_dates.add((excess_employee, excess_date))

    # Reserve one entry for unapproved-time case.
    pending_employee = "EMP-000003"
    pending_date = date(2026, 1, 14)

    used_employee_dates.add((pending_employee, pending_date))

    # Four reserved records will be added below:
    # 1. Excess hours
    # 2. Unapproved time
    # 3. Original time entry
    # 4. Duplicate time entry
    target_normal = TIME_COUNT - 4

    for number in range(target_normal):
        while True:
            employee_number = rng.randint(1, EMPLOYEE_COUNT)
            period = rng.choice(PERIODS)

            employee_id = make_id("EMP", employee_number)
            period_id, period_start, period_end, _ = period

            work_date = random_date(period_start, period_end)

            key = (employee_id, work_date)

            if key not in used_employee_dates:
                used_employee_dates.add(key)
                break

        hours = money(rng.choice([
            7.5, 8.0, 8.0, 8.0, 8.5
        ]))

        # Normal synthetic time entries are approved.
        # The dedicated GT-005 record below represents unapproved time.
        status = "APPROVED"

        records.append({
            "entry_id": f"TIME-{employee_id}-{work_date.isoformat()}",
            "employee_id": employee_id,
            "pay_period_id": period_id,
            "work_date": work_date,
            "hours": hours,
            "status": status,
            "source_submission_id": f"SUB-{number + 1:08d}",
        })

    # Edge case 1: Excess hours.
    records.append({
        "entry_id": f"TIME-{excess_employee}-2026-01-13",
        "employee_id": excess_employee,
        "pay_period_id": "PP-2026-01",
        "work_date": excess_date,
        "hours": money(16),
        "status": "APPROVED",
        "source_submission_id": "SUB-EDGE-EXCESS",
    })

    # Edge case 2: Unapproved time.
    records.append({
        "entry_id": f"TIME-{pending_employee}-2026-01-14",
        "employee_id": pending_employee,
        "pay_period_id": "PP-2026-01",
        "work_date": pending_date,
        "hours": money(8),
        "status": "PENDING",
        "source_submission_id": "SUB-EDGE-PENDING",
    })

    # Edge case 3: Original time submission.
    records.append({
        "entry_id": f"TIME-{duplicate_employee}-2026-01-12",
        "employee_id": duplicate_employee,
        "pay_period_id": duplicate_period[0],
        "work_date": duplicate_date,
        "hours": money(8),
        "status": "APPROVED",
        "source_submission_id": "SUB-EDGE-ORIGINAL",
    })

    # Edge case 4: Duplicate time submission.
    records.append({
        "entry_id": f"TIME-{duplicate_employee}-2026-01-12-DUP01",
        "employee_id": duplicate_employee,
        "pay_period_id": duplicate_period[0],
        "work_date": duplicate_date,
        "hours": money(8),
        "status": "APPROVED",
        "source_submission_id": "SUB-EDGE-DUPLICATE",
    })

    return records

# --------------------------------------------------
# 7. GENERATE ALLOWANCES
# --------------------------------------------------

def generate_allowances():
    records = []
    used_combinations = set()

    duplicate_employee = "EMP-000004"
    duplicate_period = "PP-2026-01"
    duplicate_type = "TRAVEL"

    used_combinations.add(
        (duplicate_employee, duplicate_period, duplicate_type)
    )

    allowance_types = [
        "TRAVEL",
        "MEAL",
        "HOUSING",
        "INTERNET",
    ]

    # Leave one slot for the duplicate allowance.
    for number in range(ALLOWANCE_COUNT - 2):
        while True:
            employee_number = rng.randint(1, EMPLOYEE_COUNT)
            period = rng.choice(PERIODS)

            employee_id = make_id("EMP", employee_number)
            period_id, start, end, _ = period
            allowance_type = rng.choice(allowance_types)

            key = (employee_id, period_id, allowance_type)

            if key not in used_combinations:
                used_combinations.add(key)
                break

        amount = rng.randint(500, 8000)

        records.append({
            "allowance_id": f"ALW-{number + 1:08d}",
            "employee_id": employee_id,
            "pay_period_id": period_id,
            "allowance_type": allowance_type,
            "amount": money(amount),
            "effective_start": start,
            "effective_end": end,
            "status": "APPROVED",
            "source_reference": f"ALLOWANCE-SOURCE-{number + 1:08d}",
        })

    # Edge case 4: Original allowance.
    records.append({
        "allowance_id": "ALW-EDGE-ORIGINAL",
        "employee_id": duplicate_employee,
        "pay_period_id": duplicate_period,
        "allowance_type": duplicate_type,
        "amount": money(2500),
        "effective_start": date(2026, 1, 1),
        "effective_end": date(2026, 1, 31),
        "status": "APPROVED",
        "source_reference": "ALLOWANCE-SOURCE-EDGE-DUPLICATE",
    })

    # Edge case 5: Duplicate allowance.
    records.append({
        "allowance_id": "ALW-EDGE-DUPLICATE",
        "employee_id": duplicate_employee,
        "pay_period_id": duplicate_period,
        "allowance_type": duplicate_type,
        "amount": money(2500),
        "effective_start": date(2026, 1, 1),
        "effective_end": date(2026, 1, 31),
        "status": "APPROVED",
        "source_reference": "ALLOWANCE-SOURCE-EDGE-DUPLICATE",
    })

    return records


# --------------------------------------------------
# 8. GENERATE DEDUCTIONS
# --------------------------------------------------

def generate_deductions(leave_records):
    records = []

    # Use an approved unpaid leave record for the
    # duplicate leave-deduction example.
    unpaid_leave = next(
        (
            leave for leave in leave_records
            if leave["leave_type"] == "UNPAID"
            and leave["status"] == "APPROVED"
        ),
        None,
    )

    if unpaid_leave is None:
        raise RuntimeError("No approved unpaid leave record found.")

    target_employee = unpaid_leave["employee_id"]
    target_period = next(
        period_id
        for period_id, start, end, _ in PERIODS
        if start <= unpaid_leave["start_date"] <= end
    )

    reserved_key = (
        target_employee,
        target_period,
        "UNPAID_LEAVE",
    )

    used_combinations = {reserved_key}

    deduction_types = [
        "TAX",
        "INSURANCE",
        "RETIREMENT",
        "LOAN",
        "UNPAID_LEAVE",
    ]

    # Two records are reserved for the duplicate deduction case.
    for number in range(DEDUCTION_COUNT - 2):
        while True:
            employee_number = rng.randint(1, EMPLOYEE_COUNT)
            period = rng.choice(PERIODS)

            employee_id = make_id("EMP", employee_number)
            period_id, start, end, _ = period
            deduction_type = rng.choice(deduction_types)

            key = (employee_id, period_id, deduction_type)

            if key not in used_combinations:
                used_combinations.add(key)
                break

        amount = rng.randint(300, 5000)

        records.append({
            "deduction_id": f"DED-{number + 1:08d}",
            "employee_id": employee_id,
            "pay_period_id": period_id,
            "deduction_type": deduction_type,
            "amount": money(amount),
            "effective_start": start,
            "effective_end": end,
            "status": "APPROVED",
            "source_reference": f"DEDUCTION-SOURCE-{number + 1:08d}",
        })

    # Edge case 5: The same leave is deducted twice.
    for suffix in ["01", "02"]:
        records.append({
            "deduction_id": f"DED-EDGE-LEAVE-{suffix}",
            "employee_id": target_employee,
            "pay_period_id": target_period,
            "deduction_type": "UNPAID_LEAVE",
            "amount": money(1500),
            "effective_start": unpaid_leave["start_date"],
            "effective_end": unpaid_leave["end_date"],
            "status": "APPROVED",
            "source_reference": unpaid_leave["leave_id"],
        })

    return records, unpaid_leave


# --------------------------------------------------
# 9. DATABASE INSERTION
# --------------------------------------------------

def insert_records(connection, table, records):
    if not records:
        return

    columns = list(records[0].keys())

    column_sql = ", ".join(f"`{column}`" for column in columns)
    value_sql = ", ".join(f":{column}" for column in columns)

    statement = text(
        f"INSERT INTO `{table}` ({column_sql}) "
        f"VALUES ({value_sql})"
    )

    # Insert in batches to keep memory and query size manageable.
    batch_size = 2000

    for start in range(0, len(records), batch_size):
        batch = records[start:start + batch_size]
        connection.execute(statement, batch)


def insert_all_data(
    pay_groups,
    pay_periods,
    employees,
    assignments,
    time_entries,
    leave_records,
    allowances,
    deductions,
):
    ensure_empty_database()

    print("\nInserting records into MySQL...")

    with engine.begin() as connection:
        insert_records(connection, "pay_groups", pay_groups)
        insert_records(connection, "pay_periods", pay_periods)
        insert_records(connection, "employees", employees)
        insert_records(connection, "employee_pay_groups", assignments)
        insert_records(connection, "time_entries", time_entries)
        insert_records(connection, "leave_records", leave_records)
        insert_records(connection, "allowances", allowances)
        insert_records(connection, "deductions", deductions)

    print("Database insertion completed successfully!")


# --------------------------------------------------
# 10. EXPORT CSV FILES AND GROUND TRUTH
# --------------------------------------------------

def export_files(
    pay_groups,
    pay_periods,
    employees,
    assignments,
    time_entries,
    leave_records,
    allowances,
    deductions,
    unpaid_leave,
):
    datasets = {
        "pay_groups.csv": pay_groups,
        "pay_periods.csv": pay_periods,
        "employees.csv": employees,
        "employee_pay_groups.csv": assignments,
        "time_entries.csv": time_entries,
        "leave_records.csv": leave_records,
        "allowances.csv": allowances,
        "deductions.csv": deductions,
    }

    exported_files = {}

    for filename, records in datasets.items():
        path = write_csv(filename, records)
        exported_files[filename] = {
            "row_count": len(records),
            "sha256": checksum(path),
        }

    edge_cases = [
        {
            "case_id": "GT-001",
            "rule_code": "MISSING_BANK_DETAILS",
            "entity_type": "employee",
            "entity_id": "EMP-000001",
            "expected_detection": True,
        },
        {
            "case_id": "GT-002",
            "rule_code": "MISSING_TAX_DETAILS",
            "entity_type": "employee",
            "entity_id": "EMP-000031",
            "expected_detection": True,
        },
        {
            "case_id": "GT-003",
            "rule_code": "EXCESS_HOURS",
            "entity_type": "time_entry",
            "entity_id": "TIME-EMP-000002-2026-01-13",
            "expected_detection": True,
        },
        {
            "case_id": "GT-004",
            "rule_code": "DUPLICATE_TIME_ENTRY",
            "entity_type": "time_entry",
            "entity_id": "TIME-EMP-000001-2026-01-12-DUP01",
            "expected_detection": True,
        },
        {
            "case_id": "GT-005",
            "rule_code": "UNAPPROVED_TIME",
            "entity_type": "time_entry",
            "entity_id": "TIME-EMP-000003-2026-01-14",
            "expected_detection": True,
        },
        {
            "case_id": "GT-006",
            "rule_code": "DUPLICATE_ALLOWANCE",
            "entity_type": "allowance",
            "entity_id": "ALW-EDGE-DUPLICATE",
            "expected_detection": True,
        },
        {
            "case_id": "GT-007",
            "rule_code": "DUPLICATE_LEAVE_DEDUCTION",
            "entity_type": "leave",
            "entity_id": unpaid_leave["leave_id"],
            "expected_detection": True,
        },
        {
            "case_id": "GT-008",
            "rule_code": "PAYROLL_RECONCILIATION",
            "entity_type": "payroll_input",
            "entity_id": None,
            "stage": "payroll_calculation",
            "expected_detection": True,
        },
    ]

    ground_truth = {
        "seed": SEED,
        "description": (
            "Expected edge-case labels. "
            "This file is separate from payroll input data."
        ),
        "cases": edge_cases,
    }

    ground_truth_path = GROUND_TRUTH_DIR / "ground_truth.json"

    ground_truth_path.write_text(
        json.dumps(ground_truth, indent=4, default=str),
        encoding="utf-8",
    )

    manifest = {
        "project": "PayrollGuard AI",
        "seed": SEED,
        "employee_count": len(employees),
        "pay_period_count": len(pay_periods),
        "combined_transaction_count": (
            len(time_entries)
            + len(allowances)
            + len(deductions)
        ),
        "files": exported_files,
    }

    manifest_path = DOCS_DIR / "source_manifest.json"

    manifest_path.write_text(
        json.dumps(manifest, indent=4),
        encoding="utf-8",
    )

    return edge_cases, exported_files


# --------------------------------------------------
# 11. VALIDATE GENERATED DATA
# --------------------------------------------------

def validate_generated_data(
    employees,
    assignments,
    time_entries,
    leave_records,
    allowances,
    deductions,
):
    employee_ids = {
        employee["employee_id"] for employee in employees
    }

    assert len(employee_ids) == EMPLOYEE_COUNT
    assert len(employee_ids) == len(employees)

    assert len(assignments) == EMPLOYEE_COUNT

    assert len(time_entries) == TIME_COUNT
    assert len(allowances) == ALLOWANCE_COUNT
    assert len(deductions) == DEDUCTION_COUNT

    assert len({
        row["entry_id"] for row in time_entries
    }) == len(time_entries)

    assert len({
        row["allowance_id"] for row in allowances
    }) == len(allowances)

    assert len({
        row["deduction_id"] for row in deductions
    }) == len(deductions)

    for record in time_entries:
        assert record["employee_id"] in employee_ids
        assert record["hours"] >= 0

    for record in allowances:
        assert record["employee_id"] in employee_ids
        assert record["amount"] >= 0

    for record in deductions:
        assert record["employee_id"] in employee_ids
        assert record["amount"] >= 0

    for record in leave_records:
        assert record["employee_id"] in employee_ids
        assert record["end_date"] >= record["start_date"]
        assert record["leave_days"] > 0

    print("\nAll in-memory validation checks passed!")


# --------------------------------------------------
# 12. MAIN PROGRAM
# --------------------------------------------------

def main():
    print("=" * 60)
    print("PAYROLLGUARD AI - SYNTHETIC DATA GENERATOR")
    print("=" * 60)

    print(f"Random seed: {SEED}")

    ensure_empty_database()

    pay_groups = generate_pay_groups()
    pay_periods = generate_pay_periods()

    employees, assignments = generate_employees()

    leave_records = generate_leave_records()

    time_entries = generate_time_entries()
    allowances = generate_allowances()

    deductions, unpaid_leave = generate_deductions(
        leave_records
    )

    validate_generated_data(
        employees,
        assignments,
        time_entries,
        leave_records,
        allowances,
        deductions,
    )

    insert_all_data(
        pay_groups,
        pay_periods,
        employees,
        assignments,
        time_entries,
        leave_records,
        allowances,
        deductions,
    )

    edge_cases, exported_files = export_files(
        pay_groups,
        pay_periods,
        employees,
        assignments,
        time_entries,
        leave_records,
        allowances,
        deductions,
        unpaid_leave,
    )

    summary = {
        "seed": SEED,
        "employees": len(employees),
        "pay_groups": len(pay_groups),
        "pay_periods": len(pay_periods),
        "employee_pay_groups": len(assignments),
        "time_entries": len(time_entries),
        "allowances": len(allowances),
        "deductions": len(deductions),
        "combined_transactions": (
            len(time_entries)
            + len(allowances)
            + len(deductions)
        ),
        "leave_records": len(leave_records),
        "ground_truth_cases": len(edge_cases),
        "status": "SUCCESS",
    }

    summary_path = DOCS_DIR / "generation_summary.json"

    summary_path.write_text(
        json.dumps(summary, indent=4),
        encoding="utf-8",
    )

    print("\n" + "=" * 60)
    print("DATA GENERATION COMPLETED")
    print("=" * 60)

    for key, value in summary.items():
        print(f"{key}: {value}")

    print("\nGenerated CSV files:", GENERATED_DIR)
    print("Ground truth:", GROUND_TRUTH_DIR)
    print("Manifest:", DOCS_DIR / "source_manifest.json")
    print("Summary:", summary_path)


if __name__ == "__main__":
    main()
