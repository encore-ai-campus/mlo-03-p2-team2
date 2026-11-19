from modeling import build_gold
from pipeline_io import cli, staging
from validation import gold_checks


def run(config):
    with staging(config.data / "gold") as target:
        build_gold(config, target)
        checks = gold_checks(config, target)
        failed = [check for check in checks if check.violations]
        if failed:
            raise ValueError(f"Gold validation failed: {failed}")
    print(f"Gold: 2 facts and 3 dimensions passed {len(checks)} checks.")


if __name__ == "__main__":
    raise SystemExit(cli(run, "Build and validate the Domain 04 Gold star"))
