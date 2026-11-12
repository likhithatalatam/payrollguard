
from pathlib import Path
from sqlalchemy import inspect

from app.database import engine


def inspect_database():
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    output = []
    output.append("PAYROLLGUARD AI - DATABASE SCHEMA")
    output.append("=" * 60)

    for table_name in sorted(tables):
        output.append(f"\nTABLE: {table_name}")
        output.append("-" * 60)

        columns = inspector.get_columns(table_name)
        primary_keys = inspector.get_pk_constraint(table_name)
        foreign_keys = inspector.get_foreign_keys(table_name)

        pk_columns = primary_keys.get("constrained_columns", [])

        for column in columns:
            name = column["name"]
            data_type = column["type"]
            nullable = column["nullable"]
            primary_key = "PRIMARY KEY" if name in pk_columns else ""
            null_text = "NULL allowed" if nullable else "NOT NULL"

            output.append(
                f"  {name}: {data_type} | {null_text} | {primary_key}"
            )

        if foreign_keys:
            output.append("  FOREIGN KEYS:")

            for fk in foreign_keys:
                source = ", ".join(fk["constrained_columns"])
                target_table = fk["referred_table"]
                target = ", ".join(fk["referred_columns"])

                output.append(
                    f"    {source} -> {target_table}({target})"
                )

    report = "\n".join(output)

    print(report)

    project_root = Path(__file__).resolve().parents[2]
    docs_folder = project_root / "docs"
    docs_folder.mkdir(exist_ok=True)

    report_path = docs_folder / "schema_snapshot.txt"
    report_path.write_text(report, encoding="utf-8")

    print(f"\nSchema report saved to: {report_path}")


if __name__ == "__main__":
    inspect_database()
