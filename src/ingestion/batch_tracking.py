import hashlib
from datetime import datetime, timezone

DEFAULT_TABLE = "`ftw-week-08`.`01-control`.ingestion_batches"


def hash_file(path):
    """Hash a file's raw bytes in chunks, to avoid loading the whole file into memory."""
    sha256 = hashlib.sha256()
    with open(path.replace("dbfs:", "/dbfs"), "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_schema_fingerprint(spark, file_path):
    """Hash the column name+type signature of a Parquet file, to detect schema drift."""
    df = spark.read.parquet(file_path)
    schema_str = "|".join(
        f"{field.name}:{field.dataType.simpleString()}" for field in df.schema.fields
    )
    return hashlib.sha256(schema_str.encode("utf-8")).hexdigest()


def _successful_versions(spark, table, source_system, source_period):
    """Return (content_sha256, source_version_id) for every SUCCESS batch of this period.

    An empty list means either nothing has succeeded yet or the control table does
    not exist yet. Any other failure is re-raised rather than swallowed.
    """
    query = f"""
        SELECT DISTINCT content_sha256, source_version_id
        FROM {table}
        WHERE source_system = :source_system
          AND source_period = :source_period
          AND status = 'SUCCESS'
    """
    try:
        rows = spark.sql(
            query,
            args={"source_system": source_system, "source_period": source_period},
        ).collect()
    except Exception as exc:  # noqa: BLE001 - narrowed by the check below
        if "TABLE_OR_VIEW_NOT_FOUND" in str(exc).upper():
            return []
        raise
    return [(row["content_sha256"], row["source_version_id"]) for row in rows]


def resolve_source_version_id(
    spark, table, source_system, source_period, content_hash, source_version_label=None
):
    """Decide the source_version_id for a batch, refusing to reuse one silently.

    D14 states that the version suffix is incremented by a person who has confirmed a
    genuine content change. Defaulting to `_v1` unconditionally would let a revised
    file for an already-processed period land under the same source_version_id as the
    original, which makes D04's "replace the prior contribution for that logical
    source batch" ambiguous: two different contents, one version identity.

    Re-registering identical content is allowed and keeps its existing label.
    """
    recorded = _successful_versions(spark, table, source_system, source_period)
    conflicting = sorted({version for digest, version in recorded if digest != content_hash})

    if conflicting and source_version_label is None:
        raise ValueError(
            f"Content change detected for {source_system} {source_period}. "
            f"Already recorded SUCCESS under {conflicting} with a different "
            f"content_sha256; this file hashes to {content_hash}. "
            "Confirm the revision, then pass an explicit source_version_label "
            "(for example "
            f"'{source_system}_{source_period}_v2') and follow D04 for replacing "
            "the prior contribution."
        )

    if source_version_label is not None:
        clashing = [
            digest
            for digest, version in recorded
            if version == source_version_label and digest != content_hash
        ]
        if clashing:
            raise ValueError(
                f"source_version_label '{source_version_label}' is already recorded "
                f"SUCCESS against a different content_sha256 ({clashing[0]}). "
                "Choose a new label rather than reusing an existing version identity."
            )
        return source_version_label

    return f"{source_system}_{source_period}_v1"


def register_batch_discovered(
    spark,
    dbutils,
    file_path,
    source_system,
    source_period,
    table=DEFAULT_TABLE,
    source_version_label=None,
):
    """Register a new batch as DISCOVERED. Returns the generated batch_id.

    Raises ValueError if this period already succeeded under a different
    content_sha256 and no explicit source_version_label is supplied.
    """
    import uuid
    from pyspark.sql import Row
    from pyspark.sql.types import (
        StructType, StructField, StringType, TimestampType, LongType,
    )

    file_info = dbutils.fs.ls(file_path)[0]

    batch_id = str(uuid.uuid4())
    content_hash = hash_file(file_path)
    schema_fingerprint = get_schema_fingerprint(spark, file_path)
    source_version_id = resolve_source_version_id(
        spark, table, source_system, source_period, content_hash, source_version_label
    )

    schema = StructType([
        StructField("batch_id", StringType(), True),
        StructField("source_system", StringType(), True),
        StructField("source_object", StringType(), True),
        StructField("source_period", StringType(), True),
        StructField("request_parameters", StringType(), True),
        StructField("content_sha256", StringType(), True),
        StructField("source_version_id", StringType(), True),
        StructField("schema_fingerprint", StringType(), True),
        StructField("raw_uri", StringType(), True),
        StructField("status", StringType(), True),
        StructField("discovered_at", TimestampType(), True),
        StructField("started_at", TimestampType(), True),
        StructField("completed_at", TimestampType(), True),
        StructField("row_count", LongType(), True),
        StructField("file_size", LongType(), True),
        StructField("file_modified_time", TimestampType(), True),
    ])

    row = spark.createDataFrame([Row(
        batch_id=batch_id,
        source_system=source_system,
        source_object=file_path.split("/")[-1],
        source_period=source_period,
        request_parameters=None,
        content_sha256=content_hash,
        source_version_id=source_version_id,
        schema_fingerprint=schema_fingerprint,
        raw_uri=file_path,
        status="DISCOVERED",
        discovered_at=datetime.now(timezone.utc),
        started_at=None,
        completed_at=None,
        row_count=None,
        file_size=file_info.size,
        file_modified_time=datetime.fromtimestamp(
            file_info.modificationTime / 1000, tz=timezone.utc
        ),
    )], schema=schema)

    row.write.mode("append").saveAsTable(table)
    return batch_id


def mark_batch_started(spark, batch_id, table=DEFAULT_TABLE):
    """Mark a batch STARTED, immediately before the actual load begins."""
    started_at = datetime.now(timezone.utc)
    spark.sql(f"""
        UPDATE {table}
        SET status = 'STARTED',
            started_at = '{started_at.isoformat()}'
        WHERE batch_id = '{batch_id}'
    """)


def mark_batch_success(spark, batch_id, row_count, table=DEFAULT_TABLE):
    """Mark a batch SUCCESS. Call only after the load has been validated."""
    completed_at = datetime.now(timezone.utc)
    spark.sql(f"""
        UPDATE {table}
        SET status = 'SUCCESS',
            row_count = {row_count},
            completed_at = '{completed_at.isoformat()}'
        WHERE batch_id = '{batch_id}'
    """)


def mark_batch_failed(spark, batch_id, table=DEFAULT_TABLE):
    """Mark a batch FAILED. The batch stays re-processable — a retry uses a new batch_id."""
    completed_at = datetime.now(timezone.utc)
    spark.sql(f"""
        UPDATE {table}
        SET status = 'FAILED',
            completed_at = '{completed_at.isoformat()}'
        WHERE batch_id = '{batch_id}'
    """)