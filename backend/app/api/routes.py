
from io import StringIO
import csv
import hashlib
import uuid
from decimal import Decimal

from app.models import PayrollExport
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models import (
    Employee,
    PayPeriod,
    PayrollInput,
    ExceptionRecord,
    ValidationRule,
)
from app.services.payroll_engine import run_payroll_for_period


router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    """High-level payroll dashboard metrics."""

    return {
        "total_employees": db.query(Employee).filter(
            Employee.employment_status == "ACTIVE"
        ).count(),
        "total_pay_periods": db.query(PayPeriod).count(),
        "total_payroll_records": db.query(PayrollInput).count(),
        "open_exceptions": db.query(ExceptionRecord).filter(
            ExceptionRecord.status == "OPEN"
        ).count(),
        "payroll_status": [
            {"status": status, "count": count}
            for status, count in db.query(
                PayrollInput.status,
                func.count(PayrollInput.payroll_input_id),
            ).group_by(PayrollInput.status).all()
        ],
    }


@router.get("/periods")
def get_periods(db: Session = Depends(get_db)):
    periods = (
        db.query(PayPeriod)
        .order_by(PayPeriod.start_date)
        .all()
    )

    return [
        {
            "pay_period_id": p.pay_period_id,
            "pay_group_id": p.pay_group_id,
            "start_date": str(p.start_date),
            "end_date": str(p.end_date),
            "pay_date": str(p.pay_date),
            "status": p.status,
        }
        for p in periods
    ]


@router.get("/employees")
def get_employees(
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    employees = (
        db.query(Employee)
        .order_by(Employee.employee_id)
        .limit(limit)
        .all()
    )

    return [
        {
            "employee_id": e.employee_id,
            "first_name": e.first_name,
            "last_name": e.last_name,
            "email": e.email,
            "employment_status": e.employment_status,
            "annual_salary": str(e.annual_salary),
            "has_bank_details": bool(e.bank_account_ref),
            "has_tax_details": bool(e.tax_id_ref),
        }
        for e in employees
    ]


@router.post("/payroll/run/{pay_period_id}")
def run_payroll(
    pay_period_id: str,
    db: Session = Depends(get_db),
):
    try:
        return run_payroll_for_period(db, pay_period_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Payroll processing failed: {str(error)}",
        )


@router.get("/payroll/{pay_period_id}")
def get_payroll(
    pay_period_id: str,
    db: Session = Depends(get_db),
):
    records = (
        db.query(PayrollInput)
        .filter(PayrollInput.pay_period_id == pay_period_id)
        .order_by(PayrollInput.employee_id)
        .all()
    )

    return [
        {
            "payroll_input_id": p.payroll_input_id,
            "employee_id": p.employee_id,
            "pay_period_id": p.pay_period_id,
            "base_pay": str(p.base_pay),
            "overtime_pay": str(p.overtime_pay),
            "allowances_total": str(p.allowances_total),
            "deductions_total": str(p.deductions_total),
            "gross_pay": str(p.gross_pay),
            "net_pay": str(p.net_pay),
            "status": p.status,
        }
        for p in records
    ]


@router.get("/exceptions/{pay_period_id}")
def get_exceptions(
    pay_period_id: str,
    db: Session = Depends(get_db),
):
    exceptions = (
        db.query(ExceptionRecord)
        .filter(ExceptionRecord.pay_period_id == pay_period_id)
        .order_by(ExceptionRecord.severity, ExceptionRecord.employee_id)
        .all()
    )

    return [
        {
            "exception_id": e.exception_id,
            "employee_id": e.employee_id,
            "pay_period_id": e.pay_period_id,
            "rule_id": e.rule_id,
            "severity": e.severity,
            "status": e.status,
            "description": e.description,
            "source_record_id": e.source_record_id,
        }
        for e in exceptions
    ]


@router.get("/reconciliation/{pay_period_id}")
def reconciliation(
    pay_period_id: str,
    db: Session = Depends(get_db),
):
    records = (
        db.query(PayrollInput)
        .filter(PayrollInput.pay_period_id == pay_period_id)
        .all()
    )

    if not records:
        raise HTTPException(
            status_code=404,
            detail="No payroll records found for this period. Run payroll first.",
        )

    gross_total = sum((p.gross_pay for p in records), 0)
    deductions_total = sum((p.deductions_total for p in records), 0)
    net_total = sum((p.net_pay for p in records), 0)

    errors = [
        p.employee_id
        for p in records
        if round(float(p.gross_pay - p.deductions_total - p.net_pay), 2) != 0
    ]

    return {
        "pay_period_id": pay_period_id,
        "records_processed": len(records),
        "gross_total": str(gross_total),
        "deductions_total": str(deductions_total),
        "net_total": str(net_total),
        "reconciliation_errors": len(errors),
        "reconciliation_status": "PASS" if not errors else "FAIL",
        "employees_with_errors": errors,
    }



@router.get("/payroll/export/{pay_period_id}")
def export_payroll(
    pay_period_id: str,
    db: Session = Depends(get_db),
):
    records = (
        db.query(PayrollInput)
        .filter(PayrollInput.pay_period_id == pay_period_id)
        .order_by(PayrollInput.employee_id)
        .all()
    )

    if not records:
        raise HTTPException(
            status_code=404,
            detail="No payroll records found. Run payroll first.",
        )

    # 1. Prevent unsafe payroll exports
    blocked_count = sum(
        1 for p in records if p.status == "BLOCKED"
    )
    review_count = sum(
        1 for p in records if p.status == "REVIEW"
    )

    if blocked_count > 0 or review_count > 0:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Payroll export blocked. Resolve validation issues first.",
                "blocked_records": blocked_count,
                "review_records": review_count,
                "total_records": len(records),
            },
        )

    # 2. Verify payroll reconciliation
    gross_total = sum(
        (Decimal(str(p.gross_pay or 0)) for p in records),
        Decimal("0.00"),
    )

    deductions_total = sum(
        (Decimal(str(p.deductions_total or 0)) for p in records),
        Decimal("0.00"),
    )

    net_total = sum(
        (Decimal(str(p.net_pay or 0)) for p in records),
        Decimal("0.00"),
    )

    expected_net = (gross_total - deductions_total).quantize(
        Decimal("0.01")
    )

    if expected_net != net_total:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Payroll reconciliation failed. Export rejected.",
                "expected_net": str(expected_net),
                "actual_net": str(net_total),
            },
        )

    # 3. Generate CSV
    output = StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "Employee ID",
        "Pay Period",
        "Base Pay",
        "Overtime Pay",
        "Allowances",
        "Deductions",
        "Gross Pay",
        "Net Pay",
        "Status",
    ])

    for p in records:
        writer.writerow([
            p.employee_id,
            p.pay_period_id,
            p.base_pay,
            p.overtime_pay,
            p.allowances_total,
            p.deductions_total,
            p.gross_pay,
            p.net_pay,
            p.status,
        ])

    csv_content = output.getvalue()

    # 4. Generate checksum
    checksum = hashlib.sha256(
        csv_content.encode("utf-8")
    ).hexdigest()

    filename = f"payroll_{pay_period_id}.csv"

    # 5. Record successful export in audit table
    export_record = PayrollExport(
        export_id=f"EXP-{uuid.uuid4().hex[:12].upper()}",
        pay_period_id=pay_period_id,
        export_format="CSV",
        status="COMPLETED",
        file_name=filename,
        record_count=len(records),
        checksum=checksum,
        exported_by="SYSTEM/API",
    )

    db.add(export_record)
    db.commit()

    # 6. Return CSV
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Export-Checksum": checksum,
        },
    )

