"""Configuration shared by the Domain 04 scripts."""

import argparse
import os
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import yaml


PROJECT = Path(__file__).resolve().parents[3]
DOMAIN = "04_license"
TABLES = ("business_licenses", "food_inspections")


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

    def table(self, stage, name):
        return self.data / stage / DOMAIN / f"{name}.parquet"

    def gold(self, group, name):
        return self.data / "gold" / group / DOMAIN / f"{name}.parquet"


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


def settings(args):
    local_sources = PROJECT / "config" / "sources.local.yaml"
    default = local_sources if local_sources.is_file() else PROJECT / "config" / "sources.example.yaml"
    source_config = args.sources_config.resolve() if args.sources_config else default
    doc = yaml.safe_load(source_config.read_text(encoding="utf-8-sig"))
    env_key = doc["raw_root_env"]
    if args.raw_dir:
        raw = args.raw_dir.resolve()
    else:
        raw = project_path(os.environ.get(env_key) or dotenv_value(env_key) or "origin")
    data, reports = args.data_dir.resolve(), args.report_dir.resolve()
    folders = raw, data, reports
    if any(a.is_relative_to(b) or b.is_relative_to(a) for a, b in combinations(folders, 2)):
        raise ValueError("Raw, data and report directories must be separate.")
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


def load_config(description):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--raw-dir", type=Path, help="Directory containing the immutable input files")
    parser.add_argument("--sources-config", type=Path, help="YAML source mapping")
    parser.add_argument("--dictionary", type=Path, default=Path(__file__).with_name("데이터 사전.csv"))
    parser.add_argument("--data-dir", type=Path, default=PROJECT / "data")
    parser.add_argument("--report-dir", type=Path, default=PROJECT / "reports" / "runs" / DOMAIN)
    return settings(parser.parse_args())
