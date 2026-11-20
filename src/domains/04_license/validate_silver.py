from pipeline_io import cli
from validation import silver_checks, write_validation


def run(config):
    return write_validation(config, "silver", silver_checks(config))


if __name__ == "__main__":
    raise SystemExit(cli(run, "Validate Domain 04 Silver against the data dictionary"))
