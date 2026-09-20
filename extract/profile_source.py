from pathlib import Path
import os

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


# ============================================================
# 1. PROJECT PATHS
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"
OUTPUT_FILE = PROJECT_ROOT / "docs" / "source_profile_baseline.xlsx"


# ============================================================
# 2. LOAD ENVIRONMENT VARIABLES
# ============================================================

load_dotenv(ENV_FILE)

host = os.getenv("MYSQL_HOST")
port = os.getenv("MYSQL_PORT", "3306")
user = os.getenv("MYSQL_USER")
password = os.getenv("MYSQL_PASSWORD")
database = os.getenv("MYSQL_DATABASE")


# ============================================================
# 3. MIGRATION SCOPE
# ============================================================

MIGRATION_TABLES = [
    "actor",
    "address",
    "category",
    "city",
    "country",
    "customer",
    "film",
    "film_actor",
    "film_category",
    "film_text",
    "inventory",
    "language",
    "payment",
    "rental",
    "staff",
    "store",
]


# ============================================================
# 4. MYSQL CONNECTION
# ============================================================

connection_url = URL.create(
    drivername="mysql+pymysql",
    username=user,
    password=password,
    host=host,
    port=int(port),
    database=database,
)

engine = create_engine(connection_url)


# ============================================================
# 5. SAFE MYSQL IDENTIFIER
# ============================================================

def quote_identifier(identifier):
    return "`" + identifier.replace("`", "``") + "`"


# ============================================================
# 6. METADATA QUERIES
# ============================================================

columns_query = text("""
    SELECT
        TABLE_NAME,
        COLUMN_NAME,
        ORDINAL_POSITION,
        DATA_TYPE,
        COLUMN_TYPE,
        IS_NULLABLE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = :database
      AND TABLE_NAME = :table_name
    ORDER BY ORDINAL_POSITION
""")


pk_query = text("""
    SELECT
        COLUMN_NAME,
        ORDINAL_POSITION
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = :database
      AND TABLE_NAME = :table_name
      AND CONSTRAINT_NAME = 'PRIMARY'
    ORDER BY ORDINAL_POSITION
""")


# ============================================================
# 7. PROFILE ONE COLUMN
# ============================================================

def profile_column(
    connection,
    table_name,
    column_name,
    data_type,
    total_rows,
):

    table_sql = quote_identifier(table_name)
    column_sql = quote_identifier(column_name)

    # --------------------------------------------------------
    # Basic counts
    # --------------------------------------------------------

    count_sql = text(
        f"""
        SELECT
            COUNT(*) AS total_rows,
            SUM(
                CASE
                    WHEN {column_sql} IS NULL
                    THEN 1
                    ELSE 0
                END
            ) AS null_count,
            COUNT(DISTINCT {column_sql}) AS distinct_count
        FROM {table_sql}
        """
    )

    result = connection.execute(count_sql).mappings().one()

    null_count = int(result["null_count"] or 0)
    distinct_count = int(result["distinct_count"] or 0)

    null_percentage = (
        round((null_count / total_rows) * 100, 2)
        if total_rows > 0
        else 0
    )

    # --------------------------------------------------------
    # Blank strings
    # --------------------------------------------------------

    string_types = {
        "char",
        "varchar",
        "text",
        "tinytext",
        "mediumtext",
        "longtext",
        "enum",
        "set",
    }

    blank_count = None

    if data_type.lower() in string_types:

        blank_sql = text(
            f"""
            SELECT
                SUM(
                    CASE
                        WHEN {column_sql} IS NOT NULL
                         AND TRIM({column_sql}) = ''
                        THEN 1
                        ELSE 0
                    END
                ) AS blank_count
            FROM {table_sql}
            """
        )

        blank_result = connection.execute(blank_sql).scalar()

        blank_count = int(blank_result or 0)

    # --------------------------------------------------------
    # Min / Max
    # --------------------------------------------------------

    min_value = None
    max_value = None

    unsupported_min_max = {
        "blob",
        "tinyblob",
        "mediumblob",
        "longblob",
        "geometry",
        "point",
        "linestring",
        "polygon",
    }

    if data_type.lower() not in unsupported_min_max:

        min_max_sql = text(
            f"""
            SELECT
                MIN({column_sql}) AS min_value,
                MAX({column_sql}) AS max_value
            FROM {table_sql}
            """
        )

        min_max_result = connection.execute(
            min_max_sql
        ).mappings().one()

        min_value = min_max_result["min_value"]
        max_value = min_max_result["max_value"]

    return {
        "Table": table_name,
        "Column": column_name,
        "Source Type": data_type,
        "Total Rows": total_rows,
        "Null Count": null_count,
        "Null %": null_percentage,
        "Blank Count": blank_count,
        "Distinct Count": distinct_count,
        "Min Value": min_value,
        "Max Value": max_value,
    }


# ============================================================
# 8. MAIN PROFILING
# ============================================================

table_summary = []
column_profile = []
key_profile = []


print("Starting source profiling...")
print(f"Database: {database}")
print(f"Tables: {len(MIGRATION_TABLES)}")
print()


# One dedicated SQLAlchemy connection for profiling queries
with engine.connect() as connection:

    for table_name in MIGRATION_TABLES:

        print(f"Profiling table: {table_name}")

        table_sql = quote_identifier(table_name)

        # ----------------------------------------------------
        # Table row count
        # ----------------------------------------------------

        row_count_sql = text(
            f"""
            SELECT COUNT(*) AS total_rows
            FROM {table_sql}
            """
        )

        total_rows = int(
            connection.execute(row_count_sql).scalar()
        )

        # ----------------------------------------------------
        # Column metadata
        #
        # IMPORTANT:
        # Use engine here rather than the long-lived
        # profiling connection.
        # ----------------------------------------------------

        columns_df = pd.read_sql(
            columns_query,
            engine,
            params={
                "database": database,
                "table_name": table_name,
            },
        )

        table_summary.append(
            {
                "Table": table_name,
                "Row Count": total_rows,
                "Column Count": len(columns_df),
            }
        )

        # ----------------------------------------------------
        # Column profiling
        # ----------------------------------------------------

        for _, column in columns_df.iterrows():

            profile = profile_column(
                connection=connection,
                table_name=table_name,
                column_name=column["COLUMN_NAME"],
                data_type=column["DATA_TYPE"],
                total_rows=total_rows,
            )

            column_profile.append(profile)

        # ----------------------------------------------------
        # Primary-key metadata
        #
        # IMPORTANT:
        # Use engine rather than the profiling connection.
        # ----------------------------------------------------

        pk_df = pd.read_sql(
            pk_query,
            engine,
            params={
                "database": database,
                "table_name": table_name,
            },
        )

        # ----------------------------------------------------
        # Composite-aware PK profiling
        # ----------------------------------------------------

        if not pk_df.empty:

            pk_columns = pk_df["COLUMN_NAME"].tolist()

            pk_column_sql = [
                quote_identifier(column)
                for column in pk_columns
            ]

            # ------------------------------------------------
            # PK NULL validation
            #
            # For a composite PK, ANY NULL component makes
            # the complete PK invalid.
            # ------------------------------------------------

            null_conditions = " OR ".join(
                f"{column} IS NULL"
                for column in pk_column_sql
            )

            pk_null_sql = text(
                f"""
                SELECT
                    SUM(
                        CASE
                            WHEN {null_conditions}
                            THEN 1
                            ELSE 0
                        END
                    ) AS null_count
                FROM {table_sql}
                """
            )

            pk_null_count = int(
                connection.execute(
                    pk_null_sql
                ).scalar()
                or 0
            )

            # ------------------------------------------------
            # PK duplicate validation
            #
            # GROUP BY uses ALL PK columns together.
            # ------------------------------------------------

            pk_columns_for_group = ", ".join(
                pk_column_sql
            )

            pk_duplicate_sql = text(
                f"""
                SELECT COUNT(*) AS duplicate_groups
                FROM (
                    SELECT {pk_columns_for_group}
                    FROM {table_sql}
                    GROUP BY {pk_columns_for_group}
                    HAVING COUNT(*) > 1
                ) duplicates
                """
            )

            duplicate_groups = int(
                connection.execute(
                    pk_duplicate_sql
                ).scalar()
                or 0
            )

            key_profile.append(
                {
                    "Table": table_name,
                    "PK Columns": " + ".join(pk_columns),
                    "PK Column Count": len(pk_columns),
                    "PK Null Rows": pk_null_count,
                    "Duplicate PK Groups": duplicate_groups,
                }
            )


# ============================================================
# 9. CREATE DATAFRAMES
# ============================================================

table_summary_df = pd.DataFrame(table_summary)

column_profile_df = pd.DataFrame(column_profile)

key_profile_df = pd.DataFrame(key_profile)


# ============================================================
# 10. WRITE EXCEL
# ============================================================

OUTPUT_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)


print()
print("Creating source profiling workbook...")


with pd.ExcelWriter(
    OUTPUT_FILE,
    engine="openpyxl",
) as writer:

    table_summary_df.to_excel(
        writer,
        sheet_name="Table Summary",
        index=False,
    )

    column_profile_df.to_excel(
        writer,
        sheet_name="Column Profile",
        index=False,
    )

    key_profile_df.to_excel(
        writer,
        sheet_name="Key Profile",
        index=False,
    )

    for sheet_name in writer.sheets:

        sheet = writer.sheets[sheet_name]

        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions

        for column_cells in sheet.columns:

            max_length = 0
            column_letter = column_cells[0].column_letter

            for cell in column_cells:

                value = (
                    str(cell.value)
                    if cell.value is not None
                    else ""
                )

                max_length = max(
                    max_length,
                    len(value),
                )

            sheet.column_dimensions[
                column_letter
            ].width = min(
                max_length + 2,
                50,
            )


# ============================================================
# 11. FINAL SUMMARY
# ============================================================

print()
print("Source profiling completed successfully.")
print(f"Output: {OUTPUT_FILE}")
print(f"Tables profiled: {len(table_summary_df)}")
print(f"Columns profiled: {len(column_profile_df)}")
print(f"PK tables profiled: {len(key_profile_df)}")
print()

print("Table row counts:")

for _, row in table_summary_df.iterrows():

    print(
        f"  {row['Table']:<15} "
        f"{row['Row Count']:>6} rows"
    )