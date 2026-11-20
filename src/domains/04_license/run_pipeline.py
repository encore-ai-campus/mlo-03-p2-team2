"""Run or validate Domain 04 from a full snapshot or new CSV rows."""

import argparse
import csv
import subprocess
import sys
from pathlib import Path

from config import add_config_arguments, settings
from merge_sources import merge_sources


STEPS = {"bronze": "01_bronze", "silver": "02_normalize", "quality": "03_quality", "gold": "04_modeling"}


def run(args):
    config = settings(args)
    if args.delta_dir:
        if not args.raw_dir or not args.combined_raw_dir or args.start_at != "bronze" or args.validate_only:
            raise ValueError("Incoming rows require --raw-dir, --combined-raw-dir and a full Bronze-to-Gold run.")
        combined = args.combined_raw_dir.resolve()
        merge_sources(config, args.raw_dir.resolve(), args.delta_dir.resolve(), combined)
        args.raw_dir = combined
        settings(args)
    elif args.combined_raw_dir:
        raise ValueError("--combined-raw-dir requires --delta-dir.")

    switches = ("raw_dir", "data_dir", "report_dir", "sources_config", "dictionary")
    options = [value for name in switches if getattr(args, name) is not None
               for value in ("--" + name.replace("_", "-"), str(getattr(args, name)))]
    start = list(STEPS).index(args.start_at)
    for index, (stage, script) in enumerate(STEPS.items()):
        scripts = [f"validate_{stage}"]
        if not args.validate_only and index >= start:
            scripts.insert(0, script)
        for command in scripts:
            path = Path(__file__).with_name(f"{command}.py")
            subprocess.run([sys.executable, str(path), *options], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    add_config_arguments(parser)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--start-at", choices=STEPS, default="bronze", help="First stage to rebuild")
    mode.add_argument("--validate-only", action="store_true", help="Validate all existing stages")
    parser.add_argument("--delta-dir", type=Path, help="Directory containing incoming full CSV rows")
    parser.add_argument("--combined-raw-dir", type=Path, help="Separate output directory for merged CSVs")
    args = parser.parse_args()
    try:
        run(args)
    except (OSError, ValueError, KeyError, csv.Error, subprocess.CalledProcessError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
