import csv
import hashlib
import json

import pyarrow.parquet as pq

from src.bronze import load_bronze, paths


def test_output_names_follow_dataset_names():
    assert {source.name: source.output.name for source in paths.SOURCES} == {
        "food_inspections": "food_inspections.parquet",
        "business_licenses": "business_licenses.parquet",
        "community_areas": "community_areas.parquet",
    }


def test_team_snapshot_contracts_are_current():
    contracts = {source.name: source for source in paths.SOURCES}
    assert contracts["food_inspections"].expected_rows == 318_627
    assert contracts["business_licenses"].expected_rows == 1_212_282
    assert contracts["community_areas"].relative_path == "community_areas/community_areas.csv"
    assert contracts["community_areas"].format == "csv"


def test_csv_full_refresh_preserves_values(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ORIGIN_ROOT", tmp_path / "origin")
    monkeypatch.setattr(paths, "BRONZE_ROOT", tmp_path / "bronze")
    monkeypatch.setattr(load_bronze, "RUN_LOG", tmp_path / "logs" / "runs.csv")
    source = paths.Source("food_inspections", "food_inspections/food_inspections.csv", 2, "csv")
    assert source.output.name == "food_inspections.parquet"
    source.path.parent.mkdir(parents=True)
    content = 'Inspection ID,City,Zip,Inspection Date\n1,CHICAGO,06001,08/17/0206\n2,Chicago,,01/01/9999\n'
    source.path.write_text(content, encoding="utf-8")
    source.path.with_name(source.path.name + ".sha256").write_text(hashlib.sha256(source.path.read_bytes()).hexdigest(), encoding="ascii")

    assert load_bronze.load_source(source, "run1", "2026-11-19T00:00:00Z") == 2
    assert load_bronze.load_source(source, "run2", "2026-11-19T00:00:01Z") == 2
    rows = pq.read_table(source.output).to_pylist()
    assert len(rows) == 2
    assert rows[0]["Zip"] == "06001"
    assert rows[0]["Inspection Date"] == "08/17/0206"
    assert rows[1]["Zip"] == ""
    assert rows[0]["City"] == "CHICAGO" and rows[1]["City"] == "Chicago"
    assert {row["_LOAD_DTM"] for row in rows} == {"2026-11-19T00:00:01Z"}
    assert source.path.read_text(encoding="utf-8") == content
    with load_bronze.RUN_LOG.open(encoding="utf-8", newline="") as stream:
        assert [row["STATUS"] for row in csv.DictReader(stream)] == ["SUCCESS", "SUCCESS"]
    details = [json.loads(line) for line in (tmp_path / "logs" / "bronze_run_details.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(details) == 2
    assert details[-1]["source_file"] == "food_inspections.csv"
    assert details[-1]["bronze_file"] == "food_inspections.parquet"
    assert details[-1]["source_sha256"] == hashlib.sha256(source.path.read_bytes()).hexdigest().upper()
    assert details[-1]["output_rows"] == 2 and details[-1]["status"] == "SUCCESS"


def test_geojson_geometry_and_properties_survive(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "ORIGIN_ROOT", tmp_path / "origin")
    monkeypatch.setattr(paths, "BRONZE_ROOT", tmp_path / "bronze")
    monkeypatch.setattr(load_bronze, "RUN_LOG", tmp_path / "logs" / "runs.csv")
    source = paths.Source("community_areas", "community_areas/community_areas.geojson", 77, "geojson")
    assert source.output.name == "community_areas.parquet"
    source.path.parent.mkdir(parents=True)
    features = [{"type": "Feature", "geometry": {"type": "MultiPolygon", "coordinates": [[[[i, 0], [i, 1], [i + 1, 0], [i, 0]]]]}, "properties": {"area_numbe": str(i), "community": f"Area {i}"}} for i in range(1, 78)]
    content = json.dumps({"type": "FeatureCollection", "features": features})
    source.path.write_text(content, encoding="utf-8")
    source.path.with_name(source.path.name + ".sha256").write_text(hashlib.sha256(source.path.read_bytes()).hexdigest(), encoding="ascii")

    assert load_bronze.load_source(source, "run", "2026-11-19T00:00:00Z") == 77
    rows = pq.read_table(source.output).to_pylist()
    assert [json.loads(row["geometry"]) for row in rows] == [feature["geometry"] for feature in features]
    assert [row["area_numbe"] for row in rows] == [str(i) for i in range(1, 78)]
