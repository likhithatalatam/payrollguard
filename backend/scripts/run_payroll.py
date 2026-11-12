
from app.database import SessionLocal
from app.models import PayPeriod
from app.services.payroll_engine import run_payroll_for_period


def main():
    db = SessionLocal()

    try:
        periods = (
            db.query(PayPeriod)
            .order_by(PayPeriod.start_date)
            .all()
        )

        if not periods:
            print("No pay periods found.")
            return

        for period in periods:
            print(f"\nProcessing {period.pay_period_id}...")

            result = run_payroll_for_period(
                db,
                period.pay_period_id,
            )

            for key, value in result.items():
                print(f"{key}: {value}")

        print("\nAll payroll periods processed successfully.")

    except Exception as error:
        db.rollback()
        print(f"\nPayroll processing failed: {error}")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
