"""공용 GeoJSON의 지역 속성을 변환하고 이전 WKT 경계와 대조한다."""

import csv
from hashlib import file_digest
import json

import pandas as pd
import pyarrow as pa
import shapely
from shapely.geometry import shape

from silver_spatial import assign_community_areas


BOUNDARY_FIELDS = ("the_geom", "AREA_NUMBE", "COMMUNITY", "AREA_NUM_1", "SHAPE_AREA", "SHAPE_LEN")
GEOGRAPHIC_CRS = {
    "OGC:CRS84", "CRS84", "EPSG:4326",
    "urn:ogc:def:crs:OGC:1.3:CRS84", "urn:ogc:def:crs:EPSG::4326",
}


def geojson_wkt(geometry):
    # 공간 배정에서 원천 좌표 정밀도를 유지하도록 반올림 없이 WKT로 변환한다.
    return shapely.to_wkt(shape(geometry), rounding_precision=-1)


def boundary_records(path):
    collection = json.loads(path.read_text(encoding="utf-8-sig"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError(f"{path.name}: expected a GeoJSON FeatureCollection")
    crs = collection.get("crs")
    if crs is not None and crs.get("properties", {}).get("name") not in GEOGRAPHIC_CRS:
        raise ValueError(f"{path.name}: unsupported GeoJSON coordinate reference system")
    for feature in collection["features"]:
        if feature.get("type") != "Feature":
            raise ValueError(f"{path.name}: unexpected GeoJSON member")
        properties = {name.casefold(): value for name, value in feature["properties"].items()}
        yield [geojson_wkt(feature["geometry"])] + [
            "" if properties[field.lower()] is None else str(properties[field.lower()])
            for field in BOUNDARY_FIELDS[1:]
        ]


def boundary_frame(records):
    selected = [(int(row[1]), row[0]) for row in records]
    return pd.DataFrame(selected, columns=["community_area_num", "geometry"])


def boundary_digest(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def compare_boundaries(geojson_path, wkt_path, inspections):
    common = boundary_frame(boundary_records(geojson_path))
    with wkt_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream, strict=True)
        if set(BOUNDARY_FIELDS) != set(rows.fieldnames or []):
            raise ValueError(f"{wkt_path.name}: WKT comparison columns differ from the contract")
        local = boundary_frame([row[field] for field in BOUNDARY_FIELDS] for row in rows)

    # 지역 번호로 도형을 맞춘 뒤 동일 좌표에서 배정 차이를 검사한다.
    common_hash, local_hash = boundary_digest(geojson_path), boundary_digest(wkt_path)
    invalid = inspections["coordinate_invalid_flag"]
    common_assignment, _ = assign_community_areas(inspections, common, common_hash, invalid)
    local_assignment, _ = assign_community_areas(inspections, local, local_hash, invalid)
    comparison = common.merge(local, on="community_area_num", suffixes=("_team", "_wkt"), validate="one_to_one")
    geometry_changed = ~shapely.equals(
        shapely.from_wkt(comparison["geometry_team"].to_numpy()), shapely.from_wkt(comparison["geometry_wkt"].to_numpy()),
    )
    number_changed = common_assignment["community_area_num"].fillna(0).ne(
        local_assignment["community_area_num"].fillna(0),
    )
    status_changed = common_assignment["community_area_match_status"].ne(
        local_assignment["community_area_match_status"],
    )
    candidate_columns = "community_area_candidate_nums"
    candidates_changed = sum(a != b for a, b in zip(
        pa.array(common_assignment[candidate_columns]).to_pylist(),
        pa.array(local_assignment[candidate_columns]).to_pylist(), strict=True,
    ))
    return {
        "team": {"file": geojson_path.name, "sha256": common_hash, "axis": "longitude/latitude"},
        "local": {"file": wkt_path.name, "sha256": local_hash, "crs": None, "axis": "assumed longitude/latitude"},
        "compared_area_count": len(comparison),
        "different_geometry_area_nums": comparison.loc[geometry_changed, "community_area_num"].tolist(),
        "compared_inspections": len(inspections),
        "changed_region_or_status_count": int((number_changed | status_changed).sum()),
        "changed_candidate_lists_count": candidates_changed,
    }
