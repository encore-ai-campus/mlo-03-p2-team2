"""점검 좌표와 WKT 경계의 교차를 계산해 Community Area를 배정한다.

입력 점검 순서를 유지하고 좌표 공란·비정상·경계 밖·다중 후보를 구분한다.
"""

import numpy as np
import pandas as pd
import pyarrow as pa
import shapely


def _read_boundaries(areas: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    # 시카고 지역 번호 1~77과 2차원 폴리곤의 유효성을 검사한다.
    area_numbers = areas["community_area_num"]
    if sorted(area_numbers.dropna().tolist()) != list(range(1, 78)) or len(areas) != 77:
        raise ValueError("Community-area boundary keys must contain exactly one row per area 1–77")

    geometries = shapely.from_wkt(
        areas["geometry"].to_numpy(dtype=object, na_value=None), on_invalid="ignore"
    )
    valid = (
        shapely.is_valid(geometries)
        & ~shapely.is_empty(geometries)
        & np.isin(shapely.get_type_id(geometries), [3, 6])
        & (shapely.get_coordinate_dimension(geometries) == 2)
    )
    if not valid.all():
        raise ValueError(f"Invalid polygon geometries for community areas {area_numbers[~valid].tolist()}")
    return area_numbers.to_numpy(dtype=np.int64), geometries


def assign_community_areas(
    inspections: pd.DataFrame,
    areas: pd.DataFrame,
    boundary_sha256: str,
    invalid_coordinates: pd.Series | None = None,
) -> tuple[pd.DataFrame, dict]:
    """Return one spatial result per input row in the same order and a QA summary.

    The optional Boolean mask preserves coordinate parse failures from Silver
    that would otherwise be indistinguishable from missing coordinates.
    """
    area_numbers, geometries = _read_boundaries(areas)
    bounds = shapely.total_bounds(geometries).tolist()
    if not (-180 <= bounds[0] <= bounds[2] <= 180 and -90 <= bounds[1] <= bounds[3] <= 90):
        raise ValueError("Community-area geometry bounds are outside longitude/latitude limits")

    longitude = inspections["longitude"]
    latitude = inspections["latitude"]
    x = pd.to_numeric(longitude, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    y = pd.to_numeric(latitude, errors="coerce").to_numpy(dtype=float, na_value=np.nan)
    invalid_x = longitude.notna().to_numpy() & ~(np.isfinite(x) & (np.abs(x) <= 180))
    invalid_y = latitude.notna().to_numpy() & ~(np.isfinite(y) & (np.abs(y) <= 90))
    invalid = invalid_x | invalid_y
    if invalid_coordinates is not None:
        if not invalid_coordinates.index.equals(inspections.index):
            raise ValueError("The invalid-coordinate mask must align with the inspection rows")
        invalid |= invalid_coordinates.to_numpy(dtype=bool, na_value=False)
    missing = (longitude.isna() | latitude.isna()).to_numpy() & ~invalid
    positions = np.flatnonzero(~(missing | invalid))

    # 반복되는 좌표는 한 번만 교차를 계산하고 점검 순서에 맞춰 복원한다.
    coordinates = np.column_stack([x[positions], y[positions]])
    unique_coordinates, lookup = np.unique(coordinates, axis=0, return_inverse=True)
    lookup = lookup.reshape(-1)
    points = shapely.points(unique_coordinates)
    point_ids, geometry_ids = shapely.STRtree(geometries).query(points, predicate="intersects")
    hit_counts = np.bincount(point_ids, minlength=len(points))

    unique_hits = hit_counts[point_ids] == 1
    unique_point_ids = point_ids[unique_hits]
    unique_geometry_ids = geometry_ids[unique_hits]
    assigned_numbers = np.zeros(len(points), dtype=np.int64)
    assigned_numbers[unique_point_ids] = area_numbers[unique_geometry_ids]
    on_boundary = np.zeros(len(points), dtype=bool)
    on_boundary[unique_point_ids] = ~shapely.within(
        points[unique_point_ids], geometries[unique_geometry_ids]
    )

    # 복수 경계와 교차한 좌표의 후보 지역 번호를 모두 보존한다.
    candidate_numbers = [[] for _ in points]
    for point_id, geometry_id in zip(point_ids.tolist(), geometry_ids.tolist(), strict=True):
        candidate_numbers[point_id].append(int(area_numbers[geometry_id]))
    for candidates in candidate_numbers:
        candidates.sort()

    statuses = np.full(len(inspections), "outside_boundary", dtype=object)
    statuses[missing] = "missing_coordinates"
    statuses[invalid] = "invalid_coordinates"
    statuses[positions[hit_counts[lookup] == 1]] = "unique_area"
    statuses[positions[hit_counts[lookup] > 1]] = "multiple_boundaries"
    counts = np.zeros(len(inspections), dtype=np.int64)
    counts[positions] = hit_counts[lookup]
    numbers = np.zeros(len(inspections), dtype=np.int64)
    numbers[positions] = assigned_numbers[lookup]
    edge = np.zeros(len(inspections), dtype=bool)
    edge[positions] = on_boundary[lookup]
    candidates_by_row = [None] * len(inspections)
    for position, point_id in zip(positions, lookup, strict=True):
        candidates_by_row[position] = candidate_numbers[point_id]

    result = inspections[["inspection_key"]].copy()
    result["community_area_num"] = pd.arrays.IntegerArray(numbers, counts != 1)
    result["community_area_match_status"] = pd.array(statuses, dtype="string")
    result["community_area_candidate_count"] = pd.arrays.IntegerArray(counts, missing | invalid)
    result["community_area_candidate_nums"] = pd.array(
        candidates_by_row, dtype=pd.ArrowDtype(pa.list_(pa.int64()))
    )
    result["community_area_on_boundary"] = pd.arrays.BooleanArray(edge, counts != 1)
    result["boundary_version"] = pd.Series(boundary_sha256, index=result.index, dtype="string")

    summary = {
        "rows": len(result),
        "missing_coordinates": int(missing.sum()),
        "invalid_coordinates": int(invalid.sum()),
        "invalid_or_missing_coordinates": int((missing | invalid).sum()),
        "outside_boundary": int((statuses == "outside_boundary").sum()),
        "multiple_boundaries": int((counts > 1).sum()),
        "unique_area": int((counts == 1).sum()),
        "unique_area_on_boundary": int(edge.sum()),
        "unique_valid_coordinate_pairs": len(points),
        "boundary": {
            "rows": len(areas),
            "valid_polygon_rows": len(geometries),
            "sha256": boundary_sha256,
            "source_file": "export.csv",
            "official_dataset_id": "igwz-8jzy",
            "map_id": "cauq-8yn6",
            "official_dataset_url": "https://data.cityofchicago.org/d/igwz-8jzy",
            "local_extract_url": None,
            "local_crs": None,
            "axis_assumption": "WKT x/y treated as longitude/latitude in decimal degrees",
            "bounds_xy": bounds,
            "area_length_units": None,
            "business_effective_period": None,
        },
        "predicate": "intersects includes the polygon boundary; within identifies interior points",
    }
    return result, summary
