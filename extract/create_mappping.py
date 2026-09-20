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
OUTPUT_FILE = PROJECT_ROOT / "docs" / "source_to_target_mapping.xlsx"


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
# 5. SOURCE COLUMN METADATA
# ============================================================

columns_query = text("""
    SELECT
        TABLE_NAME,
        COLUMN_NAME,
        ORDINAL_POSITION,
        DATA_TYPE,
        COLUMN_TYPE,
        CHARACTER_MAXIMUM_LENGTH,
        NUMERIC_PRECISION,
        NUMERIC_SCALE,
        IS_NULLABLE,
        COLUMN_DEFAULT
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = :database
      AND TABLE_NAME IN :tables
    ORDER BY TABLE_NAME, ORDINAL_POSITION
""")


# ============================================================
# 6. KEY / FOREIGN KEY METADATA
# ============================================================

keys_query = text("""
    SELECT
        TABLE_NAME,
        COLUMN_NAME,
        CONSTRAINT_NAME,
        REFERENCED_TABLE_NAME,
        REFERENCED_COLUMN_NAME
    FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
    WHERE TABLE_SCHEMA = :database
      AND TABLE_NAME IN :tables
    ORDER BY TABLE_NAME, ORDINAL_POSITION
""")


# ============================================================
# 7. DATATYPE MAPPING FUNCTIONS
# ============================================================

def get_bronze_type(data_type: str) -> str:
    """
    Bronze keeps source data as close to raw as practical.
    """

    data_type = data_type.lower()

    if data_type == "blob":
        return "BINARY"

    return "STRING"


def get_silver_type(data_type: str, numeric_precision, numeric_scale) -> str:
    """
    Map MySQL source types to Databricks / Spark SQL types.
    """

    data_type = data_type.lower()

    integer_mapping = {
        "tinyint": "TINYINT",
        "smallint": "SMALLINT",
        "mediumint": "INT",
        "int": "INT",
        "integer": "INT",
        "bigint": "BIGINT",
    }

    if data_type in integer_mapping:
        return integer_mapping[data_type]

    if data_type in {"decimal", "numeric"}:
        if pd.notna(numeric_precision) and pd.notna(numeric_scale):
            return f"DECIMAL({int(numeric_precision)},{int(numeric_scale)})"
        return "DECIMAL"

    if data_type in {"float"}:
        return "FLOAT"

    if data_type in {"double", "real"}:
        return "DOUBLE"

    if data_type in {"char", "varchar", "text", "tinytext", "mediumtext", "longtext"}:
        return "STRING"

    if data_type == "date":
        return "DATE"

    if data_type in {"datetime", "timestamp"}:
        return "TIMESTAMP"

    if data_type == "year":
        return "INT"

    if data_type in {"enum", "set"}:
        return "STRING"

    if data_type == "blob":
        return "BINARY"

    if data_type in {"geometry", "point", "linestring", "polygon"}:
        return "STRING"

    return "STRING"


def get_transformation_rule(data_type: str) -> str:
    """
    Define the expected Bronze -> Silver transformation.
    """

    data_type = data_type.lower()

    if data_type in {
        "char",
        "varchar",
        "text",
        "tinytext",
        "mediumtext",
        "longtext",
    }:
        return "TRIM string values; convert empty strings to NULL where applicable"

    if data_type in {
        "tinyint",
        "smallint",
        "mediumint",
        "int",
        "integer",
        "bigint",
    }:
        return "CAST raw value to corresponding integer type"

    if data_type in {"decimal", "numeric"}:
        return "CAST raw value to source DECIMAL precision and scale"

    if data_type in {"datetime", "timestamp"}:
        return "CAST raw value to TIMESTAMP with documented timezone handling"

    if data_type == "date":
        return "CAST raw value to DATE"

    if data_type == "year":
        return "CAST to INT and validate four-digit year range"

    if data_type == "enum":
        return "CAST to STRING and validate against source domain"

    if data_type == "set":
        return "Preserve source representation as STRING"

    if data_type == "blob":
        return "Preserve binary value as BINARY; exclude sensitive contents from documentation"

    if data_type in {"geometry", "point", "linestring", "polygon"}:
        return "Preserve source representation as STRING; spatial transformation out of scope"

    return "Apply explicit source-to-target type conversion"


def get_validation_rule(
    data_type: str,
    key_type: str,
    nullable: str,
) -> str:
    """
    Define column-level validation expectations.
    """

    data_type = data_type.lower()

    rules = []

    if "PK" in key_type:
        rules.append("PK values must be unique and non-null")

    if "FK" in key_type:
        rules.append("FK values must satisfy referential integrity")

    if nullable == "NO":
        rules.append("NULL values not permitted")

    if data_type in {"decimal", "numeric"}:
        rules.append("Validate precision and scale")

    if data_type in {"datetime", "timestamp"}:
        rules.append("Validate timestamp conversion")

    if data_type == "year":
        rules.append("Validate valid year range")

    if data_type == "enum":
        rules.append("Validate source enum domain")

    if not rules:
        rules.append("Validate source-to-target values")

    return "; ".join(rules)


# ============================================================
# 8. READ METADATA FROM MYSQL
# ============================================================

print("Reading column metadata from MySQL...")

with engine.connect() as connection:

    columns_df = pd.read_sql(
        columns_query,
        connection,
        params={
            "database": database,
            "tables": tuple(MIGRATION_TABLES),
        },
    )

    print(f"Columns retrieved: {len(columns_df)}")

    keys_df = pd.read_sql(
        keys_query,
        connection,
        params={
            "database": database,
            "tables": tuple(MIGRATION_TABLES),
        },
    )

    print(f"Key metadata rows retrieved: {len(keys_df)}")


# ============================================================
# 9. BUILD KEY INFORMATION
# ============================================================

key_records = []

for _, row in keys_df.iterrows():

    key_type = []

    if row["CONSTRAINT_NAME"] == "PRIMARY":
        key_type.append("PK")

    if pd.notna(row["REFERENCED_TABLE_NAME"]):
        key_type.append("FK")

    if not key_type:
        continue

    key_records.append(
        {
            "TABLE_NAME": row["TABLE_NAME"],
            "COLUMN_NAME": row["COLUMN_NAME"],
            "KEY_TYPE": ", ".join(key_type),
            "REFERENCED_TABLE": row["REFERENCED_TABLE_NAME"],
            "REFERENCED_COLUMN": row["REFERENCED_COLUMN_NAME"],
        }
    )


keys_processed_df = pd.DataFrame(key_records)


# ============================================================
# 10. JOIN COLUMN + KEY METADATA
# ============================================================

mapping_df = columns_df.merge(
    keys_processed_df,
    how="left",
    on=["TABLE_NAME", "COLUMN_NAME"],
)


mapping_df["KEY_TYPE"] = mapping_df["KEY_TYPE"].fillna("")

mapping_df["REFERENCED_TABLE"] = mapping_df["REFERENCED_TABLE"].fillna("")

mapping_df["REFERENCED_COLUMN"] = mapping_df["REFERENCED_COLUMN"].fillna("")


# ============================================================
# 11. APPLY SOURCE -> TARGET MAPPING
# ============================================================

mapping_df["Bronze Type"] = mapping_df["DATA_TYPE"].apply(
    get_bronze_type
)

mapping_df["Silver Type"] = mapping_df.apply(
    lambda row: get_silver_type(
        row["DATA_TYPE"],
        row["NUMERIC_PRECISION"],
        row["NUMERIC_SCALE"],
    ),
    axis=1,
)

mapping_df["Transformation Rule"] = mapping_df["DATA_TYPE"].apply(
    get_transformation_rule
)

mapping_df["Validation Rule"] = mapping_df.apply(
    lambda row: get_validation_rule(
        row["DATA_TYPE"],
        row["KEY_TYPE"],
        row["IS_NULLABLE"],
    ),
    axis=1,
)


# ============================================================
# 12. CREATE FINAL MAPPING DATAFRAME
# ============================================================

final_mapping = mapping_df[
    [
        "TABLE_NAME",
        "COLUMN_NAME",
        "ORDINAL_POSITION",
        "DATA_TYPE",
        "CHARACTER_MAXIMUM_LENGTH",
        "NUMERIC_PRECISION",
        "NUMERIC_SCALE",
        "IS_NULLABLE",
        "COLUMN_DEFAULT",
        "KEY_TYPE",
        "REFERENCED_TABLE",
        "REFERENCED_COLUMN",
        "Bronze Type",
        "Silver Type",
        "Transformation Rule",
        "Validation Rule",
    ]
].copy()


final_mapping.rename(
    columns={
        "TABLE_NAME": "Table",
        "COLUMN_NAME": "Column",
        "ORDINAL_POSITION": "Ordinal",
        "DATA_TYPE": "Source Type",
        "CHARACTER_MAXIMUM_LENGTH": "Length",
        "NUMERIC_PRECISION": "Precision",
        "NUMERIC_SCALE": "Scale",
        "IS_NULLABLE": "Nullable",
        "COLUMN_DEFAULT": "Default",
        "KEY_TYPE": "Key Type",
        "REFERENCED_TABLE": "Referenced Table",
        "REFERENCED_COLUMN": "Referenced Column",
    },
    inplace=True,
)


# ============================================================
# 13. MAPPING GUIDE
# ============================================================

mapping_guide = pd.DataFrame(
    [
        [
            "Bronze",
            "Raw ingestion layer",
            "Preserve source values with minimal transformation. Add ingestion metadata.",
        ],
        [
            "Silver",
            "Cleansed and typed layer",
            "Apply Databricks-compatible data types, trimming, null handling and data-quality rules.",
        ],
        [
            "Gold",
            "Business-ready layer",
            "Create business-level tables and analytical aggregates.",
        ],
        [
            "Primary Key",
            "PK",
            "Validate uniqueness and non-null values.",
        ],
        [
            "Foreign Key",
            "FK",
            "Validate referential integrity against the referenced table.",
        ],
        [
            "Decimal",
            "DECIMAL(p,s)",
            "Preserve source precision and scale wherever possible.",
        ],
        [
            "MySQL MEDIUMINT",
            "INT",
            "Databricks does not have a MEDIUMINT equivalent.",
        ],
        [
            "MySQL YEAR",
            "INT",
            "Store as integer and validate the source year.",
        ],
        [
            "MySQL ENUM",
            "STRING",
            "Preserve value and validate against the source domain.",
        ],
        [
            "MySQL SET",
            "STRING",
            "Preserve the source representation.",
        ],
        [
            "MySQL BLOB",
            "BINARY",
            "Preserve binary data without exposing sensitive contents in documentation.",
        ],
        [
            "MySQL GEOMETRY",
            "STRING",
            "Preserve representation initially; spatial transformation is out of scope.",
        ],
    ],
    columns=[
        "Concept",
        "Mapping",
        "Description",
    ],
)


# ============================================================
# 14. WRITE EXCEL WORKBOOK
# ============================================================

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

print(f"Creating mapping workbook: {OUTPUT_FILE}")

with pd.ExcelWriter(
    OUTPUT_FILE,
    engine="openpyxl",
) as writer:

    final_mapping.to_excel(
        writer,
        sheet_name="Column Mapping",
        index=False,
    )

    mapping_guide.to_excel(
        writer,
        sheet_name="Mapping Guide",
        index=False,
    )

    workbook = writer.book

    # Format Column Mapping sheet
    mapping_sheet = writer.sheets["Column Mapping"]
    mapping_sheet.freeze_panes = "A2"
    mapping_sheet.auto_filter.ref = mapping_sheet.dimensions

    # Format Mapping Guide sheet
    guide_sheet = writer.sheets["Mapping Guide"]
    guide_sheet.freeze_panes = "A2"
    guide_sheet.auto_filter.ref = guide_sheet.dimensions

    # Basic readable column widths
    for sheet in [mapping_sheet, guide_sheet]:

        for column_cells in sheet.columns:

            max_length = 0
            column_letter = column_cells[0].column_letter

            for cell in column_cells:
                value = str(cell.value) if cell.value is not None else ""
                max_length = max(max_length, len(value))

            sheet.column_dimensions[column_letter].width = min(
                max_length + 2,
                60,
            )


# ============================================================
# 15. FINAL SUMMARY
# ============================================================

print()
print("Mapping workbook created successfully.")
print(f"Output: {OUTPUT_FILE}")
print(f"Tables: {final_mapping['Table'].nunique()}")
print(f"Columns: {len(final_mapping)}")
print()
print("Tables included:")

for table_name in final_mapping["Table"].drop_duplicates():
    print(f"  - {table_name}")