import pyarrow.parquet as pq

from bronze_manifest import MANIFEST, artifact_identity, check_entry, manifest_bytes, now_utc, read_manifest
from config import DOMAIN
from pipeline_io import bronze_batches, cli, sha256, staging, write_parquet


def run(config):
    bronze = config.stage_dir("bronze") / DOMAIN
    manifest = bronze / MANIFEST
    payload, existing = read_manifest(manifest, config.sources) if manifest.exists() else (None, {})
    entries = []

    with staging(bronze) as target:
        for table, source in config.sources.items():
            destination = config.table("bronze", table)
            existed = destination.exists()
            started = now_utc()
            source_digest = sha256(source.path)
            batches = bronze_batches(source)
            output = target / destination.name
            write_parquet(output, next(batches), batches)
            written = now_utc()
            if sha256(source.path) != source_digest:
                raise ValueError(f"Source changed while reading: {source.path.name}")
            with pq.ParquetFile(output) as parquet:
                identity = artifact_identity(table, source, source_digest, output, parquet.metadata.num_rows)
            if table in existing:
                check_entry(existing[table], identity)
            else:
                entries.append(identity | {
                    "status": "verified_existing" if existed else "created",
                    "source_read_started_at_utc": started,
                    "bronze_created_at_utc": None if existed else written,
                    "recorded_at_utc": now_utc(),
                })
        (target / MANIFEST).write_bytes(payload if payload is not None else manifest_bytes(entries))
    print(f"Bronze: {len(config.sources)} source tables and the ingestion manifest verified.")


if __name__ == "__main__":
    raise SystemExit(cli(run, "Build immutable Domain 04 Bronze Parquet"))
