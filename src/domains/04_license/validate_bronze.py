from pipeline_io import cli
from validation import bronze_checks, write_validation


def run(config):
    return write_validation(config, "bronze", bronze_checks(config))


if __name__ == "__main__":
    raise SystemExit(cli(run, "Validate Domain 04 Bronze row counts and values"))
