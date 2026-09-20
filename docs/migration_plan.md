# MySQL Sakila to Databricks Delta Lake Migration Plan

## 1. Document Purpose

This document defines the approach for migrating the MySQL Sakila sample
database into Databricks using Unity Catalog and Delta Lake.

The project demonstrates an end-to-end data migration process including:

- Source profiling
- File-based extraction
- Bronze ingestion
- Silver transformation and data quality handling
- Gold business-layer creation
- Source-to-target validation
- Defect injection and validation testing
- Pipeline automation

---

## 2. Project Objective

The objective is to migrate the Sakila relational database from a local
MySQL environment into Databricks Delta tables while preserving data
accuracy, integrity, and traceability.

The migration will also demonstrate a reusable validation framework capable
of identifying differences between the source and target at multiple stages
of the migration.

---

## 3. Source System

| Attribute             | Value                               |
| --------------------- | ----------------------------------- |
| Source platform       | MySQL                               |
| Source database       | Sakila                              |
| Source location       | Local development environment       |
| Source object type    | Relational tables                   |
| Migration scope       | 16 base tables                      |
| Source views          | Excluded from initial migration     |
| Extraction technology | Python, pandas, SQLAlchemy, PyMySQL |

### In-scope source tables

1. actor
2. address
3. category
4. city
5. country
6. customer
7. film
8. film_actor
9. film_category
10. film_text
11. inventory
12. language
13. payment
14. rental
15. staff
16. store

### Out-of-scope objects

The following Sakila views are excluded from the initial physical-table
migration:

- actor_info
- customer_list
- film_list
- nicer_but_slower_film_list
- sales_by_film_category
- sales_by_store
- staff_list

These views may be recreated later as analytical views if required.

---

## 4. Target Platform

| Attribute         | Value                   |
| ----------------- | ----------------------- |
| Target platform   | Databricks Free Edition |
| Catalog           | workspace               |
| Schema            | sakila_migration        |
| File landing area | Unity Catalog Volume    |
| Volume            | sakila_files            |
| Storage format    | Delta Lake              |
| Processing        | PySpark / Spark SQL     |
| Orchestration     | Databricks Jobs         |

### Target Volume

```text
/Volumes/workspace/sakila_migration/sakila_files/
```
