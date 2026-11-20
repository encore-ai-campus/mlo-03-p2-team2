from pipeline_io import cli
from validation import quality_checks, write_validation


def run(config):
    return write_validation(config, "quality", quality_checks(config))


if __name__ == "__main__":
    raise SystemExit(cli(run, "Validate reproducibility of Domain 04 quality reports"))
