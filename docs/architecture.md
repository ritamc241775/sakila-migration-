                         SOURCE
                           |
                           v
                  +----------------+
                  | MySQL Sakila   |
                  | 16 Base Tables |
                  +----------------+
                           |
                           | Python Extraction
                           v
                  +----------------+
                  | CSV / Parquet  |
                  | + Manifest      |
                  +----------------+
                           |
                           | File Upload
                           v
                  +----------------+
                  | Unity Catalog   |
                  | Volume          |
                  +----------------+
                           |
                           v
                  +----------------+
                  |     BRONZE     |
                  | Raw Delta Data |
                  +----------------+
                           |
                           v
                  +----------------+
                  |     SILVER     |
                  | Cleaned /      |
                  | Validated Data |
                  +----------------+
                           |
                           v
                  +----------------+
                  |      GOLD      |
                  | Business /     |
                  | Analytical Data|
                  +----------------+

       MySQL Source ----------------------+
                                           |
                                           v
                              +----------------------+
                              | Validation Framework |
                              +----------------------+
                                           |
                                           v
                              validation_results