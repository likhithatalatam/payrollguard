
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha1
import json

from sqlalchemy.orm import Session

from app.models import (
    Employee,
    EmployeePayGroup,
    PayPeriod,
    TimeEntry,
    Allowance,
    Deduction,
    PayrollInput,
    ValidationRule,
    ExceptionRecord,
    EventHistory,
)


ZERO = Decimal("0.00")
MONEY = Decimal("0.01")
STANDARD_HOURS_PER_DAY = Decimal("8")
STANDARD_WORKING_DAYS_PER_MONTH = Decimal("26")
OVERTIME_MULTIPLIER = Decimal("1.5")
EXCESS_HOURS_ALERT = Decimal("12")


def money(value):
    """Round a value safely to two decimal places."""
    return Decimal(str(value or 0)).quantize(
        MONEY, rounding=ROUND_HALF_UP
    )


def stable_id(prefix, *parts):
    """Create a repeatable, database-safe ID."""
    raw = "|".join(str(part) for part in parts)
    digest = sha1(raw.encode("utf-8")).hexdigest()[:12].upper()
    return f"{prefix}-{digest}"


def run_payroll_for_period(db: Session, pay_period_id: str):
    """
    Calculate payroll and create validation exceptions for one pay period.

    Policy:
    - Base pay = annual salary / 12.
    - Overtime = approved daily hours above 8, paid at 1.5x hourly rate.
    - Hourly rate = monthly base pay / (26 * 8).
    - Only approved allowances and deductions are included.
    - Duplicate financial records are counted once.
    - Duplicate time-entry days are excluded from overtime pending review.
    """

    period = (
        db.query(PayPeriod)
        .filter(PayPeriod.pay_period_id == pay_period_id)
        .first()
    )

    if not period:
        raise ValueError(f"Pay period not found: {pay_period_id}")

    rules = {
        rule.rule_code: rule
        for rule in db.query(ValidationRule)
        .filter(ValidationRule.is_active.is_(True))
        .all()
    }

    required_rules = [
        "MISSING_BANK_DETAILS",
        "MISSING_TAX_DETAILS",
        "DUPLICATE_TIME_ENTRY",
        "EXCESS_HOURS",
        "DUPLICATE_ALLOWANCE",
        "UNAPPROVED_TIME",
        "DUPLICATE_LEAVE_DEDUCTION",
        "PAYROLL_RECONCILIATION",
    ]

    missing_rules = [code for code in required_rules if code not in rules]
    if missing_rules:
        raise ValueError(
            "Missing active validation rules: " + ", ".join(missing_rules)
        )

    assignments = (
        db.query(EmployeePayGroup)
        .filter(
            EmployeePayGroup.pay_group_id == period.pay_group_id,
            EmployeePayGroup.effective_start <= period.end_date,
        )
        .all()
    )

    eligible_ids = {
        assignment.employee_id
        for assignment in assignments
        if assignment.effective_end is None
        or assignment.effective_end >= period.start_date
    }

    employees = (
        db.query(Employee)
        .filter(
            Employee.employee_id.in_(eligible_ids),
            Employee.employment_status == "ACTIVE",
        )
        .order_by(Employee.employee_id)
        .all()
    )

    employee_ids = {employee.employee_id for employee in employees}

    if not employees:
        raise ValueError(
            f"No active employees assigned to {pay_period_id}"
        )

    # Load period transactions once rather than querying per employee.
    time_entries = (
        db.query(TimeEntry)
        .filter(TimeEntry.pay_period_id == pay_period_id)
        .order_by(TimeEntry.entry_id)
        .all()
    )

    allowances = (
        db.query(Allowance)
        .filter(Allowance.pay_period_id == pay_period_id)
        .order_by(Allowance.allowance_id)
        .all()
    )

    deductions = (
        db.query(Deduction)
        .filter(Deduction.pay_period_id == pay_period_id)
        .order_by(Deduction.deduction_id)
        .all()
    )

    time_by_employee = defaultdict(list)
    allowance_by_employee = defaultdict(list)
    deduction_by_employee = defaultdict(list)

    for entry in time_entries:
        if entry.employee_id in employee_ids:
            time_by_employee[entry.employee_id].append(entry)

    for item in allowances:
        if item.employee_id in employee_ids:
            allowance_by_employee[item.employee_id].append(item)

    for item in deductions:
        if item.employee_id in employee_ids:
            deduction_by_employee[item.employee_id].append(item)

    # Rebuild exceptions for this period on every run.
    # Existing payroll inputs are updated rather than duplicated.
    db.query(ExceptionRecord).filter(
        ExceptionRecord.pay_period_id == pay_period_id
    ).delete(synchronize_session=False)

    db.flush()

    exception_count = 0
    blocked_count = 0
    review_count = 0
    calculated_count = 0
    total_gross = ZERO
    total_net = ZERO

    for employee in employees:
        employee_id = employee.employee_id
        employee_exceptions = []

        def add_exception(rule_code, description, source_record_id=None):
            rule = rules[rule_code]
            employee_exceptions.append({
                "exception_id": stable_id(
                    "PEX",
                    employee_id,
                    pay_period_id,
                    rule_code,
                    source_record_id or "EMPLOYEE",
                ),
                "employee_id": employee_id,
                "rule_id": rule.rule_id,
                "severity": rule.severity,
                "description": description,
                "source_record_id": source_record_id,
            })

        # 1. Employee profile checks.
        if not employee.bank_account_ref:
            add_exception(
                "MISSING_BANK_DETAILS",
                "Employee is missing bank account reference.",
            )

        if not employee.tax_id_ref:
            add_exception(
                "MISSING_TAX_DETAILS",
                "Employee is missing tax ID reference.",
            )

        # 2. Time-entry validation and overtime.
        daily_entries = defaultdict(list)

        for entry in time_by_employee[employee_id]:
            daily_entries[entry.work_date].append(entry)

            if entry.status.upper() != "APPROVED":
                add_exception(
                    "UNAPPROVED_TIME",
                    f"Time entry {entry.entry_id} has status "
                    f"{entry.status}; it is excluded from payroll.",
                    entry.entry_id,
                )

        overtime_hours = ZERO

        for work_date, day_entries in daily_entries.items():
            if len(day_entries) > 1:
                add_exception(
                    "DUPLICATE_TIME_ENTRY",
                    f"{len(day_entries)} time entries exist for "
                    f"{work_date}. This date is excluded from "
                    "overtime calculation pending review.",
                    str(work_date),
                )
                continue

            entry = day_entries[0]

            if entry.status.upper() != "APPROVED":
                continue

            hours = money(entry.hours)

            if hours > EXCESS_HOURS_ALERT:
                add_exception(
                    "EXCESS_HOURS",
                    f"{hours} hours recorded on {work_date}; "
                    f"this exceeds the {EXCESS_HOURS_ALERT}-hour "
                    "review threshold.",
                    entry.entry_id,
                )

            if hours > STANDARD_HOURS_PER_DAY:
                overtime_hours += hours - STANDARD_HOURS_PER_DAY

        base_pay = money(
            Decimal(str(employee.annual_salary))
            / Decimal("12")
        )

        hourly_rate = (
            base_pay
            / (
                STANDARD_WORKING_DAYS_PER_MONTH
                * STANDARD_HOURS_PER_DAY
            )
        )

        overtime_pay = money(
            overtime_hours * hourly_rate * OVERTIME_MULTIPLIER
        )

        # 3. Allowances: detect duplicates and count each source once.
        allowance_rows = allowance_by_employee[employee_id]
        allowance_groups = defaultdict(list)

        for item in allowance_rows:
            if item.source_reference:
                key = (
                    item.allowance_type,
                    item.source_reference,
                )
            else:
                key = ("UNIQUE", item.allowance_id)

            allowance_groups[key].append(item)

        allowances_total = ZERO

        for key, group in allowance_groups.items():
            if len(group) > 1:
                add_exception(
                    "DUPLICATE_ALLOWANCE",
                    f"Duplicate allowance records found for "
                    f"{key[0]} with source reference {key[1]}. "
                    "Only one record is counted.",
                    str(key[1]),
                )

            approved = [
                item for item in group
                if item.status.upper() == "APPROVED"
            ]

            if approved:
                # Deterministically count only the first record.
                allowances_total += money(approved[0].amount)

        allowances_total = money(allowances_total)

        # 4. Deductions: detect duplicate source references.
        deduction_rows = deduction_by_employee[employee_id]
        deduction_groups = defaultdict(list)

        for item in deduction_rows:
            if item.source_reference:
                key = (
                    item.deduction_type,
                    item.source_reference,
                )
            else:
                key = ("UNIQUE", item.deduction_id)

            deduction_groups[key].append(item)

        deductions_total = ZERO

        for key, group in deduction_groups.items():
            if len(group) > 1:
                is_leave_duplicate = (
                    "LEAVE" in str(key[0]).upper()
                    or "LEAVE" in str(key[1]).upper()
                )

                if is_leave_duplicate:
                    add_exception(
                        "DUPLICATE_LEAVE_DEDUCTION",
                        f"Duplicate leave deduction records found "
                        f"for source reference {key[1]}. "
                        "Only one record is counted.",
                        str(key[1]),
                    )

            approved = [
                item for item in group
                if item.status.upper() == "APPROVED"
            ]

            if approved:
                deductions_total += money(approved[0].amount)

        deductions_total = money(deductions_total)

        # 5. Final payroll calculation.
        gross_pay = money(
            base_pay + overtime_pay + allowances_total
        )

        net_pay = money(gross_pay - deductions_total)

        # A negative net amount is a reconciliation exception.
        if net_pay < ZERO:
            add_exception(
                "PAYROLL_RECONCILIATION",
                "Total deductions exceed gross pay. "
                "Payroll calculation requires review.",
            )
            net_pay = ZERO

        # Reconciliation check.
        if money(gross_pay - deductions_total) != net_pay:
            add_exception(
                "PAYROLL_RECONCILIATION",
                "Gross pay minus deductions does not match net pay.",
            )

        # 6. Determine payroll status.
        has_high = any(
            item["severity"].upper() == "HIGH"
            for item in employee_exceptions
        )
        has_medium = any(
            item["severity"].upper() == "MEDIUM"
            for item in employee_exceptions
        )

        if has_high:
            payroll_status = "BLOCKED"
            blocked_count += 1
        elif has_medium:
            payroll_status = "REVIEW"
            review_count += 1
        else:
            payroll_status = "CALCULATED"
            calculated_count += 1

        # 7. Save or update payroll input.
        payroll_id = f"PIN-{employee_id}-{pay_period_id}"

        payroll_input = (
            db.query(PayrollInput)
            .filter(
                PayrollInput.employee_id == employee_id,
                PayrollInput.pay_period_id == pay_period_id,
            )
            .first()
        )

        if payroll_input is None:
            payroll_input = PayrollInput(
                payroll_input_id=payroll_id,
                employee_id=employee_id,
                pay_period_id=pay_period_id,
            )
            db.add(payroll_input)

        payroll_input.base_pay = base_pay
        payroll_input.overtime_pay = overtime_pay
        payroll_input.allowances_total = allowances_total
        payroll_input.deductions_total = deductions_total
        payroll_input.gross_pay = gross_pay
        payroll_input.net_pay = net_pay
        payroll_input.status = payroll_status

        db.flush()

        # 8. Save exceptions linked to the payroll input.
        for item in employee_exceptions:
            db.add(ExceptionRecord(
                exception_id=item["exception_id"],
                payroll_input_id=payroll_input.payroll_input_id,
                employee_id=employee_id,
                pay_period_id=pay_period_id,
                rule_id=item["rule_id"],
                severity=item["severity"],
                status="OPEN",
                description=item["description"],
                source_record_id=item["source_record_id"],
            ))
            exception_count += 1

        total_gross += gross_pay
        total_net += net_pay

    # 9. Audit event.
    db.add(EventHistory(
        entity_type="PAY_PERIOD",
        entity_id=pay_period_id,
        action="PAYROLL_CALCULATED",
        actor_role="SYSTEM",
        actor_id="PAYROLL_ENGINE",
        old_value=None,
        new_value=json.dumps({
            "employees_processed": len(employees),
            "exceptions_created": exception_count,
            "blocked": blocked_count,
            "review": review_count,
            "calculated": calculated_count,
            "gross_total": str(money(total_gross)),
            "net_total": str(money(total_net)),
        }),
    ))

    db.commit()

    return {
        "pay_period_id": pay_period_id,
        "employees_processed": len(employees),
        "exceptions_created": exception_count,
        "blocked": blocked_count,
        "review": review_count,
        "calculated": calculated_count,
        "gross_total": str(money(total_gross)),
        "net_total": str(money(total_net)),
        "status": "SUCCESS",
    }
