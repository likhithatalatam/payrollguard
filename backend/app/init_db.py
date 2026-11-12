
from app.database import Base, engine, SessionLocal
from app.models import (
    Employee,
    PayGroup,
    PayPeriod,
    EmployeePayGroup,
    TimeEntry,
    LeaveRecord,
    Allowance,
    Deduction,
    PayrollInput,
    ValidationRule,
    ExceptionRecord,
    Approval,
    PayrollExport,
    EventHistory,
)


def create_tables():
    print("Creating PayrollGuard database tables...")

    Base.metadata.create_all(bind=engine)

    print("Database tables created successfully!")


def seed_validation_rules():
    rules = [
        {
            "rule_id": "RULE-001",
            "rule_code": "MISSING_BANK_DETAILS",
            "rule_name": "Missing bank details",
            "description": "Employee must have valid bank details before export.",
            "severity": "HIGH",
        },
        {
            "rule_id": "RULE-002",
            "rule_code": "MISSING_TAX_DETAILS",
            "rule_name": "Missing tax details",
            "description": "Employee must have valid tax details before export.",
            "severity": "HIGH",
        },
        {
            "rule_id": "RULE-003",
            "rule_code": "DUPLICATE_TIME_ENTRY",
            "rule_name": "Duplicate time entry",
            "description": "Detect duplicate submissions for the same employee and work date.",
            "severity": "HIGH",
        },
        {
            "rule_id": "RULE-004",
            "rule_code": "EXCESS_HOURS",
            "rule_name": "Excess working hours",
            "description": "Flag working hours above the configured daily limit.",
            "severity": "MEDIUM",
        },
        {
            "rule_id": "RULE-005",
            "rule_code": "DUPLICATE_ALLOWANCE",
            "rule_name": "Duplicate allowance",
            "description": "Detect repeated allowances for the same employee and period.",
            "severity": "HIGH",
        },
        {
            "rule_id": "RULE-006",
            "rule_code": "UNAPPROVED_TIME",
            "rule_name": "Unapproved time entry",
            "description": "Prevent unapproved time entries from being included in payroll.",
            "severity": "HIGH",
        },
        {
            "rule_id": "RULE-007",
            "rule_code": "DUPLICATE_LEAVE_DEDUCTION",
            "rule_name": "Duplicate leave deduction",
            "description": "Detect when the same unpaid leave is deducted more than once.",
            "severity": "HIGH",
        },
        {
            "rule_id": "RULE-008",
            "rule_code": "PAYROLL_RECONCILIATION",
            "rule_name": "Payroll reconciliation mismatch",
            "description": "Flag differences between calculated payroll and expected totals.",
            "severity": "HIGH",
        },
    ]

    session = SessionLocal()

    try:
        for rule_data in rules:
            existing_rule = session.query(ValidationRule).filter_by(
                rule_id=rule_data["rule_id"]
            ).first()

            if not existing_rule:
                session.add(ValidationRule(**rule_data))

        session.commit()
        print("Validation rules inserted successfully!")

    except Exception:
        session.rollback()
        raise

    finally:
        session.close()


if __name__ == "__main__":
    create_tables()
    seed_validation_rules()
