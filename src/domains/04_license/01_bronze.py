from config import DOMAIN
from pipeline_io import bronze_batches, cli, staging, write_parquet


def run(config):
    with staging(config.data / "bronze" / DOMAIN) as target:
        for table, source in config.sources.items():
            batches = bronze_batches(source)
            write_parquet(target / f"{table}.parquet", next(batches), batches)
    print("Bronze: 2 source tables written or verified unchanged.")


if __name__ == "__main__":
    raise SystemExit(cli(run, "Build immutable Domain 04 Bronze Parquet"))
