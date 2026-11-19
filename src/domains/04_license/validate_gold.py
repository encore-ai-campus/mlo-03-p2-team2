from pipeline_io import cli
from validation import gold_checks, write_validation


def run(config):
    return write_validation(config, "gold", gold_checks(config))


if __name__ == "__main__":
    raise SystemExit(cli(run, "Validate Domain 04 Gold primary and foreign keys"))
