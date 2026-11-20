"""Configuration shared by the Domain 04 scripts."""

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

import yaml


PROJECT = Path(__file__).resolve().parents[3]
DOMAIN = "04_license"
TABLES = ("business_licenses", "food_inspections")
STAGE_DIRS = {"bronze": "01_bronze", "silver": "02_silver", "gold": "03_gold"}


def parquet_name(name):
    return f"{DOMAIN.split('_', 1)[0]}_{name}.parquet"


@dataclass(frozen=True)
class Source:
    path: Path
    format: str
    columns: tuple[str, ...] | None
    sheet: str | None
    encoding: str


@dataclass(frozen=True)
class Config:
    sources: dict[str, Source]
    dictionary: Path
    data: Path
    reports: Path

    def stage_dir(self, stage):
        return self.data / STAGE_DIRS[stage]

    def table(self, stage, name):
        return self.stage_dir(stage) / DOMAIN / parquet_name(name)


def dotenv_value(name):
    env_file = PROJECT / ".env"
    if env_file.is_file():
        for line in env_file.read_text(encoding="utf-8-sig").splitlines():
            key, sep, value = line.strip().partition("=")
            if sep and key.strip() == name:
                return value.strip().strip("'\"")
    return None


def project_path(value):
    return (PROJECT / value).resolve()


def directories_overlap(first, second):
    return first.is_relative_to(second) or second.is_relative_to(first)


def settings(args):
    local_sources = PROJECT / "config" / "sources.local.yaml"
    default = local_sources if local_sources.is_file() else PROJECT / "config" / "sources.example.yaml"
    source_config = args.sources_config.resolve() if args.sources_config else default
    doc = yaml.safe_load(source_config.read_text(encoding="utf-8-sig"))
    env_key = doc["raw_root_env"]
    if args.raw_dir:
        raw = args.raw_dir.resolve()
    else:
        raw = project_path(os.environ.get(env_key) or dotenv_value(env_key) or "data/00_origin")
    data, reports = args.data_dir.resolve(), args.report_dir.resolve()
    stages = [(data / dirname).resolve() for dirname in STAGE_DIRS.values()]
    if (directories_overlap(data, reports)
            or any(directories_overlap(raw, output) for output in [*stages, reports])):
        raise ValueError("Raw, stage output and report directories must not overlap.")
    sources = {}
    for name in TABLES:
        spec = doc["sources"][name]
        path = (raw / spec["file"]).resolve()
        if not path.is_relative_to(raw):
            raise ValueError(f"{name}: source path must be inside the raw directory.")
        kind = spec.get("format", path.suffix.removeprefix(".")).lower()
        if kind not in {"csv", "xlsx"}:
            raise ValueError(f"{name}: unsupported input format {kind!r}.")
        columns = spec.get("columns")
        if columns is not None and (
            not isinstance(columns, list) or not columns
            or any(not isinstance(column, str) for column in columns)
            or len(set(columns)) != len(columns)
        ):
            raise ValueError(f"{name}: columns must be a nonempty list of distinct names.")
        sources[name] = Source(path, kind, tuple(columns) if columns else None,
                               spec.get("sheet"), spec.get("encoding", "utf-8"))
    return Config(sources, args.dictionary.resolve(), data, reports)


def add_config_arguments(parser):
    parser.add_argument("--raw-dir", type=Path, help="Directory containing the immutable input files")
    parser.add_argument("--sources-config", type=Path, help="YAML source mapping")
    parser.add_argument("--dictionary", type=Path, default=Path(__file__).with_name("데이터 사전.csv"))
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "data")
    parser.add_argument("--report-dir", type=Path, default=PROJECT / "reports" / "runs" / DOMAIN)


def load_config(description):
    parser = argparse.ArgumentParser(description=description)
    add_config_arguments(parser)
    return settings(parser.parse_args())
