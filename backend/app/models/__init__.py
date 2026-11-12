
from sqlalchemy import (
    Column, Integer, String, Date, DateTime, Numeric, Boolean,
    Text, ForeignKey, UniqueConstraint, CheckConstraint, Index, func
)
from app.database import Base


# 1. EMPLOYEE


class Employee(Base):
    __tablename__ = "employees"

    employee_id = Column(String(20), primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    hire_date = Column(Date, nullable=False)
    employment_status = Column(String(20), nullable=False, default="ACTIVE")
    annual_salary = Column(Numeric(12, 2), nullable=False)
    bank_account_ref = Column(String(100), nullable=True)
    tax_id_ref = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())



# 2. PAY GROUP


class PayGroup(Base):
    __tablename__ = "pay_groups"

    pay_group_id = Column(String(20), primary_key=True)
    group_name = Column(String(100), unique=True, nullable=False)
    pay_frequency = Column(String(20), nullable=False)
    currency = Column(String(3), nullable=False, default="INR")
    is_active = Column(Boolean, default=True, nullable=False)



# 3. PAY PERIOD


class PayPeriod(Base):
    __tablename__ = "pay_periods"

    pay_period_id = Column(String(20), primary_key=True)
    pay_group_id = Column(
        String(20), ForeignKey("pay_groups.pay_group_id"), nullable=False
    )
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    pay_date = Column(Date, nullable=False)
    status = Column(String(20), nullable=False, default="OPEN")

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_period_dates"),
        UniqueConstraint(
            "pay_group_id", "start_date", "end_date",
            name="uq_pay_group_period"
        ),
    )



# 4. EMPLOYEE-PAY GROUP BRIDGE


class EmployeePayGroup(Base):
    __tablename__ = "employee_pay_groups"

    assignment_id = Column(Integer, primary_key=True, autoincrement=True)
    employee_id = Column(
        String(20), ForeignKey("employees.employee_id"), nullable=False
    )
    pay_group_id = Column(
        String(20), ForeignKey("pay_groups.pay_group_id"), nullable=False
    )
    effective_start = Column(Date, nullable=False)
    effective_end = Column(Date, nullable=True)

    __table_args__ = (
        CheckConstraint(
            "effective_end IS NULL OR effective_end >= effective_start",
            name="ck_assignment_dates"
        ),
        UniqueConstraint(
            "employee_id", "effective_start",
            name="uq_employee_assignment_start"
        ),
    )


# 5. TIME ENTRY


class TimeEntry(Base):
    __tablename__ = "time_entries"

    entry_id = Column(String(100), primary_key=True)
    employee_id = Column(
        String(20), ForeignKey("employees.employee_id"), nullable=False
    )
    pay_period_id = Column(
        String(20), ForeignKey("pay_periods.pay_period_id"), nullable=False
    )
    work_date = Column(Date, nullable=False)
    hours = Column(Numeric(5, 2), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    source_submission_id = Column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint("hours >= 0", name="ck_time_hours_nonnegative"),
        Index("ix_time_employee_date", "employee_id", "work_date"),
    )



# 6. LEAVE RECORD


class LeaveRecord(Base):
    __tablename__ = "leave_records"

    leave_id = Column(String(100), primary_key=True)
    employee_id = Column(
        String(20), ForeignKey("employees.employee_id"), nullable=False
    )
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    leave_type = Column(String(30), nullable=False)
    leave_days = Column(Numeric(5, 2), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")

    __table_args__ = (
        CheckConstraint("end_date >= start_date", name="ck_leave_dates"),
        CheckConstraint("leave_days > 0", name="ck_leave_days"),
    )



# 7. ALLOWANCE


class Allowance(Base):
    __tablename__ = "allowances"

    allowance_id = Column(String(100), primary_key=True)
    employee_id = Column(
        String(20), ForeignKey("employees.employee_id"), nullable=False
    )
    pay_period_id = Column(
        String(20), ForeignKey("pay_periods.pay_period_id"), nullable=False
    )
    allowance_type = Column(String(50), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    effective_start = Column(Date, nullable=False)
    effective_end = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")
    source_reference = Column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_allowance_amount"),
    )



# 8. DEDUCTION


class Deduction(Base):
    __tablename__ = "deductions"

    deduction_id = Column(String(100), primary_key=True)
    employee_id = Column(
        String(20), ForeignKey("employees.employee_id"), nullable=False
    )
    pay_period_id = Column(
        String(20), ForeignKey("pay_periods.pay_period_id"), nullable=False
    )
    deduction_type = Column(String(50), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    effective_start = Column(Date, nullable=False)
    effective_end = Column(Date, nullable=True)
    status = Column(String(20), nullable=False, default="PENDING")
    source_reference = Column(String(100), nullable=True)

    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_deduction_amount"),
    )


# 9. PAYROLL INPUT


class PayrollInput(Base):
    __tablename__ = "payroll_inputs"

    payroll_input_id = Column(String(100), primary_key=True)
    employee_id = Column(
        String(20), ForeignKey("employees.employee_id"), nullable=False
    )
    pay_period_id = Column(
        String(20), ForeignKey("pay_periods.pay_period_id"), nullable=False
    )

    base_pay = Column(Numeric(12, 2), nullable=False, default=0)
    overtime_pay = Column(Numeric(12, 2), nullable=False, default=0)
    allowances_total = Column(Numeric(12, 2), nullable=False, default=0)
    deductions_total = Column(Numeric(12, 2), nullable=False, default=0)
    gross_pay = Column(Numeric(12, 2), nullable=False, default=0)
    net_pay = Column(Numeric(12, 2), nullable=False, default=0)

    status = Column(String(30), nullable=False, default="DRAFT")
    calculated_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "employee_id", "pay_period_id",
            name="uq_employee_payroll_period"
        ),
        CheckConstraint("gross_pay >= 0", name="ck_gross_pay"),
        CheckConstraint("net_pay >= 0", name="ck_net_pay"),
    )


# 10. VALIDATION RULE


class ValidationRule(Base):
    __tablename__ = "validation_rules"

    rule_id = Column(String(30), primary_key=True)
    rule_code = Column(String(50), unique=True, nullable=False)
    rule_name = Column(String(150), nullable=False)
    description = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)


# 11. EXCEPTION RECORD


class ExceptionRecord(Base):
    __tablename__ = "exceptions"

    exception_id = Column(String(100), primary_key=True)
    payroll_input_id = Column(
        String(100),
        ForeignKey("payroll_inputs.payroll_input_id"),
        nullable=True
    )
    employee_id = Column(
        String(20), ForeignKey("employees.employee_id"), nullable=False
    )
    pay_period_id = Column(
        String(20), ForeignKey("pay_periods.pay_period_id"), nullable=False
    )
    rule_id = Column(
        String(30), ForeignKey("validation_rules.rule_id"), nullable=True
    )
    severity = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="OPEN")
    description = Column(Text, nullable=False)
    source_record_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    resolved_at = Column(DateTime, nullable=True)



# 12. APPROVAL


class Approval(Base):
    __tablename__ = "approvals"

    approval_id = Column(String(100), primary_key=True)
    payroll_input_id = Column(
        String(100),
        ForeignKey("payroll_inputs.payroll_input_id"),
        nullable=False
    )
    approver_role = Column(String(30), nullable=False)
    approver_employee_id = Column(
        String(20), ForeignKey("employees.employee_id"), nullable=True
    )
    decision = Column(String(20), nullable=False, default="PENDING")
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    decided_at = Column(DateTime, nullable=True)


# 13. PAYROLL EXPORT


class PayrollExport(Base):
    __tablename__ = "payroll_exports"

    export_id = Column(String(100), primary_key=True)
    pay_period_id = Column(
        String(20), ForeignKey("pay_periods.pay_period_id"), nullable=False
    )
    export_format = Column(String(10), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING")
    file_name = Column(String(255), nullable=True)
    record_count = Column(Integer, default=0)
    checksum = Column(String(128), nullable=True)
    exported_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, server_default=func.now())


# 14. EVENT HISTORY / AUDIT TRAIL


class EventHistory(Base):
    __tablename__ = "event_history"

    event_id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(String(100), nullable=False)
    action = Column(String(50), nullable=False)
    actor_role = Column(String(30), nullable=False)
    actor_id = Column(String(100), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
