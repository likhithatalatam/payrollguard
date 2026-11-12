from io import StringIO
from datetime import datetime
import csv
import hashlib
import uuid
import json
from decimal import Decimal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Body,
)
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
    TimeEntry,
    EventHistory,
    PayrollExport,
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
        .order_by(PayrollInput.employee_id)
        .all()
    )

    if not records:
        raise HTTPException(
            status_code=404,
            detail="No payroll records found for this period. Run payroll first.",
        )

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

    errors = []

    for p in records:
        expected_net = (
            Decimal(str(p.gross_pay or 0))
            - Decimal(str(p.deductions_total or 0))
        ).quantize(Decimal("0.01"))

        actual_net = Decimal(str(p.net_pay or 0)).quantize(
            Decimal("0.01")
        )

        if expected_net != actual_net:
            errors.append(p.employee_id)

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

    # Verify reconciliation for every employee.
    employee_errors = []

    for p in records:
        expected_employee_net = (
            Decimal(str(p.gross_pay or 0))
            - Decimal(str(p.deductions_total or 0))
        ).quantize(Decimal("0.01"))

        actual_employee_net = Decimal(
            str(p.net_pay or 0)
        ).quantize(Decimal("0.01"))

        if expected_employee_net != actual_employee_net:
            employee_errors.append(p.employee_id)

    if expected_net != net_total or employee_errors:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Payroll reconciliation failed. Export rejected.",
                "expected_net": str(expected_net),
                "actual_net": str(net_total),
                "employees_with_errors": employee_errors,
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
@router.get("/time-entries/pending/{pay_period_id}")
def get_pending_time_entries(
    pay_period_id: str,
    db: Session = Depends(get_db)
):
    entries = (
        db.query(TimeEntry)
        .filter(
            TimeEntry.pay_period_id == pay_period_id,
            TimeEntry.status == "PENDING"
        )
        .order_by(TimeEntry.work_date.asc())
        .limit(100)
        .all()
    )

    return [
        {
            "entry_id": entry.entry_id,
            "employee_id": entry.employee_id,
            "pay_period_id": entry.pay_period_id,
            "work_date": entry.work_date.isoformat(),
            "hours": float(entry.hours),
            "status": entry.status
        }
        for entry in entries
    ]
@router.post("/time-entries/{entry_id}/decision")
def decide_time_entry(
    entry_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """
    Approve or reject a time entry.
    Recalculates payroll and records the action in the audit trail.
    """

    entry = (
        db.query(TimeEntry)
        .filter(TimeEntry.entry_id == entry_id)
        .first()
    )

    if not entry:
        raise HTTPException(
            status_code=404,
            detail="Time entry not found.",
        )

    if entry.status != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=f"Cannot decide this entry because its current status is {entry.status}.",
        )

    decision = str(payload.get("decision", "")).upper()

    if decision not in ["APPROVED", "REJECTED"]:
        raise HTTPException(
            status_code=400,
            detail="Decision must be APPROVED or REJECTED.",
        )

    actor_role = str(payload.get("actor_role", "MANAGER")).upper()
    actor_id = str(payload.get("actor_id", "MANAGER-USER"))

    old_status = entry.status

    entry.status = decision

    db.add(EventHistory(
        entity_type="TIME_ENTRY",
        entity_id=entry.entry_id,
        action=f"TIME_ENTRY_{decision}",
        actor_role=actor_role,
        actor_id=actor_id,
        old_value=old_status,
        new_value=decision,
    ))

    try:
        # The payroll engine commits the decision, audit event,
        # payroll updates, and exception changes together.
        result = run_payroll_for_period(
            db,
            entry.pay_period_id,
        )

        return {
            "message": f"Time entry {decision.lower()} successfully.",
            "entry_id": entry.entry_id,
            "old_status": old_status,
            "new_status": decision,
            "payroll_recalculation": result,
        }

    except Exception as error:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Time-entry decision failed: {str(error)}",
        )

@router.post("/exceptions/{exception_id}/resolve")
def resolve_exception(
    exception_id: str,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """
    Manually resolve an exception after the underlying issue is corrected.
    """

    exception = (
        db.query(ExceptionRecord)
        .filter(ExceptionRecord.exception_id == exception_id)
        .first()
    )

    if not exception:
        raise HTTPException(
            status_code=404,
            detail="Exception not found.",
        )

    if exception.status == "RESOLVED":
        raise HTTPException(
            status_code=409,
            detail="This exception is already resolved.",
        )

    resolution_note = str(
        payload.get("resolution_note", "")
    ).strip()

    if not resolution_note:
        raise HTTPException(
            status_code=400,
            detail="Please provide a resolution_note.",
        )

    actor_role = str(payload.get("actor_role", "HR")).upper()
    actor_id = str(payload.get("actor_id", "HR-USER"))

    old_status = exception.status

    exception.status = "RESOLVED"
    exception.resolved_at = datetime.utcnow()

    db.add(EventHistory(
        entity_type="EXCEPTION",
        entity_id=exception.exception_id,
        action="EXCEPTION_MANUALLY_RESOLVED",
        actor_role=actor_role,
        actor_id=actor_id,
        old_value=old_status,
        new_value=json.dumps({
            "status": "RESOLVED",
            "resolution_note": resolution_note,
        }),
    ))

    db.commit()

    return {
        "message": "Exception resolved successfully.",
        "exception_id": exception.exception_id,
        "old_status": old_status,
        "new_status": exception.status,
        "resolution_note": resolution_note,
    }
@router.get("/audit/{entity_type}/{entity_id}")
def get_audit_history(
    entity_type: str,
    entity_id: str,
    db: Session = Depends(get_db),
):
    events = (
        db.query(EventHistory)
        .filter(
            EventHistory.entity_type == entity_type.upper(),
            EventHistory.entity_id == entity_id,
        )
        .order_by(EventHistory.created_at.desc())
        .all()
    )

    return [
        {
            "event_id": event.event_id,
            "entity_type": event.entity_type,
            "entity_id": event.entity_id,
            "action": event.action,
            "actor_role": event.actor_role,
            "actor_id": event.actor_id,
            "old_value": event.old_value,
            "new_value": event.new_value,
            "created_at": (
                event.created_at.isoformat()
                if event.created_at else None
            ),
        }
        for event in events
    ]