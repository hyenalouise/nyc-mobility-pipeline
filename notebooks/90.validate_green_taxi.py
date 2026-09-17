# Databricks notebook source
# MAGIC %md
# MAGIC # Green Taxi Bronze Data Quality Validation
# MAGIC
# MAGIC This notebook validates the Green Taxi Bronze dataset before Silver processing.
# MAGIC
# MAGIC Bronze table:
# MAGIC
# MAGIC `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC DQ results table:
# MAGIC
# MAGIC `ftw-week-08`.`01-control`.green_taxi_data_quality_results
# MAGIC
# MAGIC Source period:
# MAGIC
# MAGIC March–May 2026
# MAGIC
# MAGIC Source files:
# MAGIC
# MAGIC - `green_tripdata_2026-03.parquet`
# MAGIC - `green_tripdata_2026-04.parquet`
# MAGIC - `green_tripdata_2026-05.parquet`
# MAGIC
# MAGIC Bronze preserves the source values. Source-level anomalies are measured and documented rather than silently modified.
# MAGIC
# MAGIC Validation results are written to the shared control-layer DQ results table so that validation runs remain traceable through run and batch metadata.

# COMMAND ----------

# MAGIC %md
# MAGIC # 1. Validation Approach
# MAGIC
# MAGIC The Bronze validation covers:
# MAGIC
# MAGIC - Volume
# MAGIC - Schema
# MAGIC - Required timestamps
# MAGIC - Timestamp consistency
# MAGIC - Reporting-period coverage
# MAGIC - Passenger-count conditions
# MAGIC - Trip-distance validity
# MAGIC - Fare and total-amount conditions
# MAGIC - Source categorical domains
# MAGIC - Location ID validity
# MAGIC - Full-row duplicates
# MAGIC - Provenance completeness
# MAGIC - Source-to-Bronze row-count reconciliation
# MAGIC
# MAGIC Status meanings:
# MAGIC
# MAGIC - `PASS` — expectation is satisfied
# MAGIC - `WARN` — non-blocking quality condition requiring attention
# MAGIC - `FAIL` — blocking Bronze issue
# MAGIC - `INFO` — informational/source-trait measurement
# MAGIC
# MAGIC Threshold-based checks use their configured thresholds to determine the resulting status.
# MAGIC
# MAGIC `FAIL` results block the Bronze exit gate.
# MAGIC
# MAGIC `WARN`, `INFO`, and `PASS` results do not block the Bronze exit gate.
# MAGIC
# MAGIC Source-level anomalies are preserved in Bronze. Cleaning and standardization are handled in Silver.

# COMMAND ----------

# MAGIC %md
# MAGIC # 2. Dataset and Source Context
# MAGIC
# MAGIC The Green Taxi source consists of monthly Parquet files covering March–May 2026.
# MAGIC
# MAGIC Expected source row counts are obtained from:
# MAGIC
# MAGIC `ftw-week-08`.`01-control`.ingestion_batches
# MAGIC
# MAGIC The reconciliation compares the recorded ingestion `row_count` for each Green Taxi source batch against the corresponding row count in the Bronze table.
# MAGIC
# MAGIC Expected row counts are therefore derived from ingestion metadata rather than hardcoded in this validation notebook.
# MAGIC
# MAGIC There is no natural trip identifier in the source. Duplicate validation therefore uses the complete set of source business fields rather than treating `VendorID` as a unique trip identifier.
# MAGIC
# MAGIC Bronze preserves source-level values and anomalies. Silver owns downstream standardization and quality handling.

# COMMAND ----------

# MAGIC %sql
# MAGIC
# MAGIC DESCRIBE `ftw-week-08`.`01-control`.ingestion_batches;

# COMMAND ----------

# MAGIC %md
# MAGIC # 3. Bronze Profile

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ============================================================
# MAGIC -- BRONZE PROFILE
# MAGIC -- ============================================================
# MAGIC
# MAGIC SELECT
# MAGIC     COUNT(*) AS total_rows,
# MAGIC     COUNT(DISTINCT source_file) AS source_file_count,
# MAGIC     MIN(lpep_pickup_datetime) AS earliest_pickup,
# MAGIC     MAX(lpep_pickup_datetime) AS latest_pickup
# MAGIC FROM `ftw-week-08`.`02-bronze`.green_taxi_raw;
# MAGIC
# MAGIC SELECT
# MAGIC     source_file,
# MAGIC     COUNT(*) AS row_count,
# MAGIC     MIN(lpep_pickup_datetime) AS earliest_pickup,
# MAGIC     MAX(lpep_pickup_datetime) AS latest_pickup
# MAGIC FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC GROUP BY source_file
# MAGIC ORDER BY source_file;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ============================================================
# MAGIC -- BRONZE SCHEMA PROFILE
# MAGIC -- ============================================================
# MAGIC
# MAGIC DESCRIBE `ftw-week-08`.`02-bronze`.green_taxi_raw;

# COMMAND ----------

# MAGIC %sql
# MAGIC
# MAGIC CREATE TABLE IF NOT EXISTS `ftw-week-08`.`01-control`.green_taxi_data_quality_results (
# MAGIC     run_id STRING,
# MAGIC     executed_at TIMESTAMP,
# MAGIC     layer STRING,
# MAGIC     dataset STRING,
# MAGIC     batch_id STRING,
# MAGIC     source_version_id STRING,
# MAGIC     code_revision STRING,
# MAGIC     check_name STRING,
# MAGIC     check_type STRING,
# MAGIC     status STRING,
# MAGIC     severity STRING,
# MAGIC     fail_count BIGINT,
# MAGIC     total_count BIGINT,
# MAGIC     fail_pct DOUBLE,
# MAGIC     threshold_pct DOUBLE,
# MAGIC     metric_value DOUBLE,
# MAGIC     owner STRING,
# MAGIC     details STRING,
# MAGIC     evidence_location STRING
# MAGIC )
# MAGIC USING DELTA;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ============================================================
# MAGIC -- RUN CONTEXT
# MAGIC -- Generate one unique run_id for this validation run.
# MAGIC -- ============================================================
# MAGIC
# MAGIC DECLARE OR REPLACE VARIABLE dq_run_id STRING;
# MAGIC
# MAGIC SET VAR dq_run_id = uuid();
# MAGIC
# MAGIC SELECT dq_run_id AS run_id;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ============================================================
# MAGIC -- GREEN TAXI BRONZE DQ EXECUTION
# MAGIC -- One execution creates exactly one result row per check.
# MAGIC -- ============================================================
# MAGIC
# MAGIC -- Generate one run ID for this DQ execution
# MAGIC DECLARE OR REPLACE VARIABLE dq_run_id STRING DEFAULT uuid();
# MAGIC
# MAGIC INSERT INTO `ftw-week-08`.`01-control`.green_taxi_data_quality_results
# MAGIC
# MAGIC WITH total AS (
# MAGIC     SELECT COUNT(*) AS total_count
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC ),
# MAGIC
# MAGIC schema_expected AS (
# MAGIC     SELECT *
# MAGIC     FROM VALUES
# MAGIC         ('VendorID', 'INT', 0),
# MAGIC         ('lpep_pickup_datetime', 'TIMESTAMP_NTZ', 1),
# MAGIC         ('lpep_dropoff_datetime', 'TIMESTAMP_NTZ', 2),
# MAGIC         ('store_and_fwd_flag', 'STRING', 3),
# MAGIC         ('RatecodeID', 'LONG', 4),
# MAGIC         ('PULocationID', 'INT', 5),
# MAGIC         ('DOLocationID', 'INT', 6),
# MAGIC         ('passenger_count', 'LONG', 7),
# MAGIC         ('trip_distance', 'DOUBLE', 8),
# MAGIC         ('fare_amount', 'DOUBLE', 9),
# MAGIC         ('extra', 'DOUBLE', 10),
# MAGIC         ('mta_tax', 'DOUBLE', 11),
# MAGIC         ('tip_amount', 'DOUBLE', 12),
# MAGIC         ('tolls_amount', 'DOUBLE', 13),
# MAGIC         ('ehail_fee', 'DOUBLE', 14),
# MAGIC         ('improvement_surcharge', 'DOUBLE', 15),
# MAGIC         ('total_amount', 'DOUBLE', 16),
# MAGIC         ('payment_type', 'LONG', 17),
# MAGIC         ('trip_type', 'LONG', 18),
# MAGIC         ('congestion_surcharge', 'DOUBLE', 19),
# MAGIC         ('cbd_congestion_fee', 'DOUBLE', 20),
# MAGIC         ('source_system', 'STRING', 21),
# MAGIC         ('source_file', 'STRING', 22),
# MAGIC         ('ingested_at', 'TIMESTAMP', 23),
# MAGIC         ('batch_id', 'STRING', 24)
# MAGIC     AS expected(column_name, data_type, ordinal_position)
# MAGIC ),
# MAGIC
# MAGIC schema_actual AS (
# MAGIC     SELECT
# MAGIC         column_name,
# MAGIC         data_type,
# MAGIC         ordinal_position
# MAGIC     FROM `system`.information_schema.columns
# MAGIC     WHERE table_catalog = 'ftw-week-08'
# MAGIC       AND table_schema = '02-bronze'
# MAGIC       AND table_name = 'green_taxi_raw'
# MAGIC ),
# MAGIC
# MAGIC schema_mismatches AS (
# MAGIC     SELECT
# MAGIC         COUNT(*) AS fail_count
# MAGIC     FROM (
# MAGIC         SELECT
# MAGIC             expected.column_name,
# MAGIC             expected.data_type,
# MAGIC             expected.ordinal_position
# MAGIC         FROM schema_expected expected
# MAGIC
# MAGIC         FULL OUTER JOIN schema_actual actual
# MAGIC             ON expected.column_name = actual.column_name
# MAGIC            AND expected.data_type = actual.data_type
# MAGIC            AND expected.ordinal_position = actual.ordinal_position
# MAGIC
# MAGIC         WHERE expected.column_name IS NULL
# MAGIC            OR actual.column_name IS NULL
# MAGIC     )
# MAGIC ),
# MAGIC
# MAGIC duplicate_rows AS (
# MAGIC     SELECT
# MAGIC         SUM(duplicate_count - 1) AS fail_count
# MAGIC     FROM (
# MAGIC         SELECT
# MAGIC             VendorID,
# MAGIC             lpep_pickup_datetime,
# MAGIC             lpep_dropoff_datetime,
# MAGIC             store_and_fwd_flag,
# MAGIC             RatecodeID,
# MAGIC             PULocationID,
# MAGIC             DOLocationID,
# MAGIC             passenger_count,
# MAGIC             trip_distance,
# MAGIC             fare_amount,
# MAGIC             extra,
# MAGIC             mta_tax,
# MAGIC             tip_amount,
# MAGIC             tolls_amount,
# MAGIC             ehail_fee,
# MAGIC             improvement_surcharge,
# MAGIC             total_amount,
# MAGIC             payment_type,
# MAGIC             trip_type,
# MAGIC             congestion_surcharge,
# MAGIC             cbd_congestion_fee,
# MAGIC             COUNT(*) AS duplicate_count
# MAGIC         FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC         GROUP BY
# MAGIC             VendorID,
# MAGIC             lpep_pickup_datetime,
# MAGIC             lpep_dropoff_datetime,
# MAGIC             store_and_fwd_flag,
# MAGIC             RatecodeID,
# MAGIC             PULocationID,
# MAGIC             DOLocationID,
# MAGIC             passenger_count,
# MAGIC             trip_distance,
# MAGIC             fare_amount,
# MAGIC             extra,
# MAGIC             mta_tax,
# MAGIC             tip_amount,
# MAGIC             tolls_amount,
# MAGIC             ehail_fee,
# MAGIC             improvement_surcharge,
# MAGIC             total_amount,
# MAGIC             payment_type,
# MAGIC             trip_type,
# MAGIC             congestion_surcharge,
# MAGIC             cbd_congestion_fee
# MAGIC         HAVING COUNT(*) > 1
# MAGIC     )
# MAGIC ),
# MAGIC
# MAGIC checks AS (
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 1. ROW COUNT
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'row_count_not_empty' AS check_name,
# MAGIC         'VOLUME' AS check_type,
# MAGIC         'FAIL' AS severity,
# MAGIC         0.0 AS threshold_pct,
# MAGIC         CASE
# MAGIC             WHEN COUNT(*) = 0 THEN 1
# MAGIC             ELSE 0
# MAGIC         END AS fail_count,
# MAGIC         CAST(NULL AS DOUBLE) AS metric_value,
# MAGIC         'Bronze table must contain rows.' AS details
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 2. SOURCE SCHEMA
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'source_schema',
# MAGIC         'SCHEMA',
# MAGIC         'FAIL',
# MAGIC         0.0,
# MAGIC         CAST(fail_count AS BIGINT),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Bronze schema must match the expected 25-column structure and Databricks data types.'
# MAGIC     FROM schema_mismatches
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 3. PICKUP TIMESTAMP NOT NULL
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'pickup_timestamp_not_null',
# MAGIC         'NOT_NULL',
# MAGIC         'FAIL',
# MAGIC         0.0,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN lpep_pickup_datetime IS NULL THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Pickup timestamp is required.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 4. DROPOFF TIMESTAMP NOT NULL
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'dropoff_timestamp_not_null',
# MAGIC         'NOT_NULL',
# MAGIC         'FAIL',
# MAGIC         0.0,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN lpep_dropoff_datetime IS NULL THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Dropoff timestamp is required.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 5. DROPOFF AFTER PICKUP
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'dropoff_after_pickup',
# MAGIC         'CONSISTENCY',
# MAGIC         'WARN',
# MAGIC         0.01,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN lpep_pickup_datetime IS NOT NULL
# MAGIC                  AND lpep_dropoff_datetime IS NOT NULL
# MAGIC                  AND lpep_dropoff_datetime <= lpep_pickup_datetime
# MAGIC                 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Dropoff should be strictly later than pickup. Anomalies are retained for Silver handling.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 6. REPORTING PERIOD COVERAGE
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'expected_month_coverage',
# MAGIC         'DATE_COVERAGE',
# MAGIC         'WARN',
# MAGIC         0.01,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN lpep_pickup_datetime < TIMESTAMP('2026-03-01 00:00:00')
# MAGIC                   OR lpep_pickup_datetime >= TIMESTAMP('2026-06-01 00:00:00')
# MAGIC                 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Pickup timestamps outside the March–May 2026 reporting period are retained and flagged.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 7. PASSENGER COUNT > 8
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'passenger_count_gt_8',
# MAGIC         'RANGE',
# MAGIC         'WARN',
# MAGIC         0.01,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN passenger_count > 8 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Passenger counts greater than 8 are separately flagged.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 8. PASSENGER COUNT = 0
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'passenger_count_zero',
# MAGIC         'MEASURE',
# MAGIC         'WARN',
# MAGIC         NULL,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN passenger_count = 0 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Zero passenger counts are retained and separately flagged for Silver handling.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 9. PASSENGER COUNT NULL
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'passenger_count_null',
# MAGIC         'MEASURE',
# MAGIC         'INFO',
# MAGIC         NULL,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN passenger_count IS NULL THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Null passenger counts are retained. No Bronze imputation is performed.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 10. TRIP DISTANCE NON-NEGATIVE
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'trip_distance_non_negative',
# MAGIC         'RANGE',
# MAGIC         'FAIL',
# MAGIC         0.0,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN trip_distance < 0 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Trip distance must be zero or greater.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 11. NEGATIVE FARE
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'negative_fare_amount',
# MAGIC         'MEASURE',
# MAGIC         'WARN',
# MAGIC         NULL,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN fare_amount < 0 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Negative fare values are retained and flagged for downstream handling.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 12. NEGATIVE TOTAL
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'negative_total_amount',
# MAGIC         'MEASURE',
# MAGIC         'WARN',
# MAGIC         NULL,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN total_amount < 0 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Negative total values are retained and flagged for downstream handling.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 13. ZERO DISTANCE / HIGH FARE
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'zero_distance_high_fare',
# MAGIC         'MEASURE',
# MAGIC         'INFO',
# MAGIC         NULL,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN trip_distance = 0
# MAGIC                  AND fare_amount > 20
# MAGIC                 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(
# MAGIC             SUM(
# MAGIC                 CASE
# MAGIC                     WHEN trip_distance = 0
# MAGIC                      AND fare_amount > 20
# MAGIC                     THEN 1
# MAGIC                     ELSE 0
# MAGIC                 END
# MAGIC             ) AS DOUBLE
# MAGIC         ),
# MAGIC         'Sensitivity-review condition. Rows remain in Bronze.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 14. VENDOR ID DOMAIN
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'vendor_id_domain',
# MAGIC         'DOMAIN',
# MAGIC         'WARN',
# MAGIC         0.01,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN VendorID IS NOT NULL
# MAGIC                  AND VendorID NOT IN (1, 2, 6)
# MAGIC                 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Valid profiled VendorID values are 1, 2, and 6.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 15. PAYMENT TYPE DOMAIN
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'payment_type_domain',
# MAGIC         'DOMAIN',
# MAGIC         'WARN',
# MAGIC         0.01,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN payment_type IS NOT NULL
# MAGIC                  AND payment_type NOT IN (0, 1, 2, 3, 4, 5, 6)
# MAGIC                 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Valid profiled payment_type values are 0–6.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 16. RATECODE DOMAIN
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'ratecode_id_domain',
# MAGIC         'DOMAIN',
# MAGIC         'WARN',
# MAGIC         0.01,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN RatecodeID IS NOT NULL
# MAGIC                  AND RatecodeID NOT IN (1, 2, 3, 4, 5, 6, 99)
# MAGIC                 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Valid profiled RatecodeID values are 1–6 and 99.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 17. PICKUP LOCATION ID RANGE
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'pickup_location_id_range',
# MAGIC         'RANGE',
# MAGIC         'WARN',
# MAGIC         0.01,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN PULocationID IS NULL
# MAGIC                   OR PULocationID < 1
# MAGIC                   OR PULocationID > 265
# MAGIC                 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Pickup LocationID must be within the Taxi Zone snapshot range 1–265.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 18. DROPOFF LOCATION ID RANGE
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'dropoff_location_id_range',
# MAGIC         'RANGE',
# MAGIC         'WARN',
# MAGIC         0.01,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN DOLocationID IS NULL
# MAGIC                   OR DOLocationID < 1
# MAGIC                   OR DOLocationID > 265
# MAGIC                 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Dropoff LocationID must be within the Taxi Zone snapshot range 1–265.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 19. FULL SOURCE ROW DUPLICATES
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'full_source_row_duplicate',
# MAGIC         'UNIQUE',
# MAGIC         'WARN',
# MAGIC         0.01,
# MAGIC         CAST(COALESCE(fail_count, 0) AS BIGINT),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Duplicate source rows are measured using all source business fields. There is no natural trip ID.'
# MAGIC     FROM duplicate_rows
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC     -- ========================================================
# MAGIC     -- 20. PROVENANCE COMPLETENESS
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'provenance_completeness',
# MAGIC         'PROVENANCE',
# MAGIC         'FAIL',
# MAGIC         0.0,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN source_system IS NULL
# MAGIC                   OR source_file IS NULL
# MAGIC                   OR ingested_at IS NULL
# MAGIC                   OR batch_id IS NULL
# MAGIC                 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'Required Bronze provenance fields must be populated.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC     UNION ALL
# MAGIC
# MAGIC        -- ========================================================
# MAGIC     -- 21. SOURCE SYSTEM DOMAIN
# MAGIC     -- ========================================================
# MAGIC     SELECT
# MAGIC         'source_system_domain',
# MAGIC         'DOMAIN',
# MAGIC         'FAIL',
# MAGIC         0.0,
# MAGIC         SUM(
# MAGIC             CASE
# MAGIC                 WHEN source_system IS NULL
# MAGIC                   OR source_system <> 'green_taxi'
# MAGIC                 THEN 1
# MAGIC                 ELSE 0
# MAGIC             END
# MAGIC         ),
# MAGIC         CAST(NULL AS DOUBLE),
# MAGIC         'source_system must identify the Green Taxi source as green_taxi.'
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC )
# MAGIC
# MAGIC SELECT
# MAGIC     dq_run_id AS run_id,
# MAGIC     current_timestamp() AS executed_at,
# MAGIC     'Bronze' AS layer,
# MAGIC     'green_taxi' AS dataset,
# MAGIC     CAST('39942fd4-14d8-41cf-81fe-7f28417aa688,7254498d-d4cc-466a-8777-bd8264160b31,ea5e3843-cc27-4fb6-8b6b-a005026e1d89' AS STRING) AS batch_id,
# MAGIC     CAST('green_taxi_2026-03_v1,green_taxi_2026-04_v1,green_taxi_2026-05_v1' AS STRING) AS source_version_id,
# MAGIC     CAST(NULL AS STRING) AS code_revision,
# MAGIC     c.check_name,
# MAGIC     c.check_type,
# MAGIC
# MAGIC     CASE
# MAGIC     WHEN c.severity = 'INFO' THEN 'INFO'
# MAGIC     WHEN c.fail_count = 0 THEN 'PASS'
# MAGIC     WHEN c.severity = 'FAIL' THEN 'FAIL'
# MAGIC     WHEN c.threshold_pct IS NOT NULL
# MAGIC          AND (
# MAGIC              (c.fail_count * 100.0) / NULLIF(t.total_count, 0)
# MAGIC          ) <= c.threshold_pct
# MAGIC         THEN 'WARN'
# MAGIC     WHEN c.threshold_pct IS NOT NULL
# MAGIC          AND (
# MAGIC              (c.fail_count * 100.0) / NULLIF(t.total_count, 0)
# MAGIC          ) > c.threshold_pct
# MAGIC         THEN 'FAIL'
# MAGIC     ELSE 'WARN'
# MAGIC END AS status,
# MAGIC
# MAGIC     c.severity,
# MAGIC     CAST(c.fail_count AS BIGINT) AS fail_count,
# MAGIC     t.total_count,
# MAGIC     100.0 * c.fail_count / NULLIF(t.total_count, 0) AS fail_pct,
# MAGIC     c.threshold_pct,
# MAGIC     c.metric_value,
# MAGIC     'Data Engineering' AS owner,
# MAGIC     c.details,
# MAGIC     CAST(NULL AS STRING) AS evidence_location
# MAGIC
# MAGIC FROM checks c
# MAGIC CROSS JOIN total t;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ============================================================
# MAGIC -- REVIEW CURRENT DQ RUN
# MAGIC -- ============================================================
# MAGIC
# MAGIC SELECT
# MAGIC     check_name,
# MAGIC     check_type,
# MAGIC     status,
# MAGIC     severity,
# MAGIC     fail_count,
# MAGIC     total_count,
# MAGIC     ROUND(fail_pct, 4) AS fail_pct,
# MAGIC     threshold_pct,
# MAGIC     metric_value,
# MAGIC     details
# MAGIC FROM `ftw-week-08`.`02-bronze`.90_validate_green_taxi
# MAGIC WHERE run_id = dq_run_id
# MAGIC ORDER BY
# MAGIC     CASE status
# MAGIC         WHEN 'FAIL' THEN 1
# MAGIC         WHEN 'WARN' THEN 2
# MAGIC         WHEN 'PASS' THEN 3
# MAGIC         WHEN 'INFO' THEN 4
# MAGIC         ELSE 5
# MAGIC     END,
# MAGIC     check_name;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ============================================================
# MAGIC -- DQ SUMMARY
# MAGIC -- ============================================================
# MAGIC
# MAGIC SELECT
# MAGIC     status,
# MAGIC     COUNT(*) AS check_count
# MAGIC FROM `ftw-week-08`.`02-bronze`.90_validate_green_taxi
# MAGIC WHERE run_id = dq_run_id
# MAGIC GROUP BY status
# MAGIC ORDER BY
# MAGIC     CASE status
# MAGIC         WHEN 'FAIL' THEN 1
# MAGIC         WHEN 'WARN' THEN 2
# MAGIC         WHEN 'PASS' THEN 3
# MAGIC         WHEN 'INFO' THEN 4
# MAGIC         ELSE 5
# MAGIC     END;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ============================================================
# MAGIC -- BRONZE DQ EXIT GATE
# MAGIC -- DQ failures OR source-to-Bronze reconciliation failures
# MAGIC -- block progression to Silver.
# MAGIC -- ============================================================
# MAGIC
# MAGIC WITH latest_run AS (
# MAGIC     SELECT MAX(executed_at) AS executed_at
# MAGIC     FROM `ftw-week-08`.`01-control`.green_taxi_data_quality_results
# MAGIC ),
# MAGIC
# MAGIC dq AS (
# MAGIC     SELECT
# MAGIC         SUM(CASE WHEN r.status = 'FAIL' THEN 1 ELSE 0 END) AS dq_fail_count,
# MAGIC         SUM(CASE WHEN r.status = 'WARN' THEN 1 ELSE 0 END) AS warn_count,
# MAGIC         SUM(CASE WHEN r.status = 'PASS' THEN 1 ELSE 0 END) AS pass_count,
# MAGIC         SUM(CASE WHEN r.status = 'INFO' THEN 1 ELSE 0 END) AS info_count
# MAGIC     FROM `ftw-week-08`.`01-control`.green_taxi_data_quality_results r
# MAGIC     INNER JOIN latest_run l
# MAGIC         ON r.executed_at = l.executed_at
# MAGIC ),
# MAGIC
# MAGIC reconciliation AS (
# MAGIC     SELECT
# MAGIC         CASE
# MAGIC             WHEN actual_rows = expected_total_rows THEN 0
# MAGIC             ELSE 1
# MAGIC         END AS reconciliation_fail_count
# MAGIC     FROM (
# MAGIC         SELECT
# MAGIC             (
# MAGIC                 SELECT SUM(row_count)
# MAGIC                 FROM `ftw-week-08`.`01-control`.ingestion_batches
# MAGIC                 WHERE source_system = 'green_taxi'
# MAGIC                   AND status = 'SUCCESS'
# MAGIC                   AND source_object IN (
# MAGIC                       'green_tripdata_2026-03.parquet',
# MAGIC                       'green_tripdata_2026-04.parquet',
# MAGIC                       'green_tripdata_2026-05.parquet'
# MAGIC                   )
# MAGIC             ) AS expected_total_rows,
# MAGIC
# MAGIC             (
# MAGIC                 SELECT COUNT(*)
# MAGIC                 FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC             ) AS actual_rows
# MAGIC     )
# MAGIC )
# MAGIC
# MAGIC SELECT
# MAGIC     CASE
# MAGIC         WHEN COALESCE(dq.dq_fail_count, 0) > 0
# MAGIC           OR reconciliation.reconciliation_fail_count > 0
# MAGIC         THEN 'BLOCKED'
# MAGIC         ELSE 'READY_FOR_SILVER'
# MAGIC     END AS bronze_dq_gate,
# MAGIC
# MAGIC     COALESCE(dq.dq_fail_count, 0)
# MAGIC         + reconciliation.reconciliation_fail_count AS fail_count,
# MAGIC
# MAGIC     COALESCE(dq.warn_count, 0) AS warn_count,
# MAGIC     COALESCE(dq.pass_count, 0) AS pass_count,
# MAGIC     COALESCE(dq.info_count, 0) AS info_count,
# MAGIC
# MAGIC     reconciliation.reconciliation_fail_count
# MAGIC
# MAGIC FROM dq
# MAGIC CROSS JOIN reconciliation;

# COMMAND ----------

# MAGIC %md
# MAGIC # 4. Source → Bronze Reconciliation

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ============================================================
# MAGIC -- OVERALL SOURCE → BRONZE ROW COUNT
# MAGIC -- Expected row counts come from ingestion_batches
# MAGIC -- ============================================================
# MAGIC
# MAGIC WITH expected AS (
# MAGIC     SELECT
# MAGIC         SUM(row_count) AS expected_total_rows
# MAGIC     FROM `ftw-week-08`.`01-control`.ingestion_batches
# MAGIC     WHERE source_system = 'green_taxi'
# MAGIC       AND status = 'SUCCESS'
# MAGIC       AND source_object IN (
# MAGIC           'green_tripdata_2026-03.parquet',
# MAGIC           'green_tripdata_2026-04.parquet',
# MAGIC           'green_tripdata_2026-05.parquet'
# MAGIC       )
# MAGIC ),
# MAGIC
# MAGIC actual AS (
# MAGIC     SELECT COUNT(*) AS actual_rows
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC )
# MAGIC
# MAGIC SELECT
# MAGIC     expected.expected_total_rows,
# MAGIC     actual.actual_rows,
# MAGIC     actual.actual_rows - expected.expected_total_rows AS row_difference,
# MAGIC
# MAGIC     CASE
# MAGIC         WHEN actual.actual_rows = expected.expected_total_rows
# MAGIC         THEN 'PASS'
# MAGIC         ELSE 'FAIL'
# MAGIC     END AS reconciliation_status
# MAGIC
# MAGIC FROM expected
# MAGIC CROSS JOIN actual;

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ============================================================
# MAGIC -- OVERALL SOURCE → BRONZE ROW COUNT
# MAGIC -- ============================================================
# MAGIC
# MAGIC WITH expected AS (
# MAGIC     SELECT 44208 AS expected_rows
# MAGIC     UNION ALL
# MAGIC     SELECT 44238
# MAGIC     UNION ALL
# MAGIC     SELECT 44921
# MAGIC ),
# MAGIC
# MAGIC actual AS (
# MAGIC     SELECT COUNT(*) AS actual_rows
# MAGIC     FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC )
# MAGIC
# MAGIC SELECT
# MAGIC     SUM(expected_rows) AS expected_total_rows,
# MAGIC     actual_rows,
# MAGIC     actual_rows - SUM(expected_rows) AS row_difference,
# MAGIC
# MAGIC     CASE
# MAGIC         WHEN actual_rows = SUM(expected_rows)
# MAGIC         THEN 'PASS'
# MAGIC         ELSE 'FAIL'
# MAGIC     END AS reconciliation_status
# MAGIC
# MAGIC FROM expected
# MAGIC CROSS JOIN actual
# MAGIC GROUP BY actual_rows;

# COMMAND ----------

# MAGIC %md
# MAGIC # 5. WARN / FAIL Investigation

# COMMAND ----------

# MAGIC %sql
# MAGIC -- ============================================================
# MAGIC -- WARN / FAIL INVESTIGATION
# MAGIC -- ============================================================
# MAGIC
# MAGIC SELECT
# MAGIC     source_file,
# MAGIC     COUNT(*) AS total_rows,
# MAGIC
# MAGIC     SUM(
# MAGIC         CASE
# MAGIC             WHEN fare_amount < 0 THEN 1
# MAGIC             ELSE 0
# MAGIC         END
# MAGIC     ) AS negative_fare_rows,
# MAGIC
# MAGIC     SUM(
# MAGIC         CASE
# MAGIC             WHEN total_amount < 0 THEN 1
# MAGIC             ELSE 0
# MAGIC         END
# MAGIC     ) AS negative_total_rows,
# MAGIC
# MAGIC     SUM(
# MAGIC         CASE
# MAGIC             WHEN trip_distance = 0
# MAGIC              AND fare_amount > 20
# MAGIC             THEN 1
# MAGIC             ELSE 0
# MAGIC         END
# MAGIC     ) AS zero_distance_high_fare_rows,
# MAGIC
# MAGIC     SUM(
# MAGIC         CASE
# MAGIC             WHEN passenger_count = 0 THEN 1
# MAGIC             ELSE 0
# MAGIC         END
# MAGIC     ) AS passenger_count_zero_rows,
# MAGIC
# MAGIC     SUM(
# MAGIC         CASE
# MAGIC             WHEN passenger_count > 8 THEN 1
# MAGIC             ELSE 0
# MAGIC         END
# MAGIC     ) AS passenger_count_gt_8_rows,
# MAGIC
# MAGIC     SUM(
# MAGIC         CASE
# MAGIC             WHEN passenger_count IS NULL THEN 1
# MAGIC             ELSE 0
# MAGIC         END
# MAGIC     ) AS passenger_count_null_rows,
# MAGIC
# MAGIC     SUM(
# MAGIC         CASE
# MAGIC             WHEN lpep_dropoff_datetime <= lpep_pickup_datetime
# MAGIC             THEN 1
# MAGIC             ELSE 0
# MAGIC         END
# MAGIC     ) AS invalid_duration_rows,
# MAGIC
# MAGIC     SUM(
# MAGIC         CASE
# MAGIC             WHEN lpep_pickup_datetime < TIMESTAMP('2026-03-01 00:00:00')
# MAGIC               OR lpep_pickup_datetime >= TIMESTAMP('2026-06-01 00:00:00')
# MAGIC             THEN 1
# MAGIC             ELSE 0
# MAGIC         END
# MAGIC     ) AS out_of_period_rows
# MAGIC
# MAGIC FROM `ftw-week-08`.`02-bronze`.green_taxi_raw
# MAGIC
# MAGIC GROUP BY source_file
# MAGIC
# MAGIC ORDER BY source_file;

# COMMAND ----------

# MAGIC %md
# MAGIC # 6. Final Review
# MAGIC
# MAGIC Known source-level conditions include:
# MAGIC
# MAGIC - Negative `fare_amount`
# MAGIC - Negative `total_amount`
# MAGIC - Zero-distance trips with higher fares
# MAGIC - `passenger_count = 0`
# MAGIC - `passenger_count > 8`
# MAGIC - Null `passenger_count`
# MAGIC - A small number of pickup timestamps outside the March–May 2026 reporting window
# MAGIC
# MAGIC These conditions are preserved in Bronze.
# MAGIC
# MAGIC Silver should apply the approved quality flags and measure-specific eligibility rules rather than silently modifying the Bronze source data.
# MAGIC
# MAGIC The Bronze DQ gate is:
# MAGIC
# MAGIC - `READY_FOR_SILVER` when there are zero FAIL results
# MAGIC - `BLOCKED` when one or more FAIL results remain
# MAGIC
# MAGIC INFO results are measurements only and do not block the Bronze gate.