"""Central paths and source contracts for Bronze."""

from dataclasses import dataclass
from pathlib import Path
import os


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ORIGIN_ROOT = Path(os.environ.get("CHICAGO_RAW_DIR", PROJECT_ROOT / "origin"))
BRONZE_ROOT = PROJECT_ROOT / "data" / "bronze"
RUN_LOG = PROJECT_ROOT / "logs" / "pipeline_runs.csv"


@dataclass(frozen=True)
class Source:
    name: str
    relative_path: str
    expected_rows: int
    format: str

    @property
    def path(self) -> Path:
        return ORIGIN_ROOT / self.relative_path

    @property
    def output(self) -> Path:
        return BRONZE_ROOT / self.name / f"{self.name}.parquet"


SOURCES = (
    Source("food_inspections", "food_inspections/food_inspections.csv", 318_552, "csv"),
    Source("business_licenses", "business_licenses/business_licenses.csv", 1_212_132, "csv"),
    Source("community_areas", "community_areas/community_areas.geojson", 77, "geojson"),
)
