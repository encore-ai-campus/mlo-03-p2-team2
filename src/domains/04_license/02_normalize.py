from config import DOMAIN, TABLES, parquet_name
from normalization import load_dictionary, normalize_batch, silver_schema
from pipeline_io import cli, parquet_batches, staging, write_parquet


def run(config):
    mapping = load_dictionary(config.dictionary)
    with staging(config.stage_dir("silver") / DOMAIN) as target:
        for table in TABLES:
            source = config.table("bronze", table)
            fields = mapping[table]
            schema = silver_schema(fields)
            batches = (normalize_batch(batch, fields, schema) for batch in parquet_batches(source))
            write_parquet(target / parquet_name(table), schema, batches)
    print("Silver: 2 tables standardized with row lineage preserved.")


if __name__ == "__main__":
    raise SystemExit(cli(run, "Standardize Domain 04 Bronze with the data dictionary"))
