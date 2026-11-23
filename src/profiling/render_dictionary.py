"""Render a source-backed column dictionary from profiling JSON."""

import json
from pathlib import Path

from src.bronze.paths import ORIGIN_ROOT, PROJECT_ROOT


PROFILE = PROJECT_ROOT / "metadata" / "source_profiles.json"
OUTPUT = PROJECT_ROOT / "metadata" / "data_dictionary.md"
META_FILES = {
    "food_inspections": ORIGIN_ROOT / "food_inspections" / "food_columns.json",
    "business_licenses": ORIGIN_ROOT / "business_licenses" / "license_columns.json",
    "community_areas": ORIGIN_ROOT / "community_areas" / "area_columns.json",
}


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def recommended(name, dataset):
    upper = name.upper()
    if upper == "GEOMETRY":
        return "geometry/GeoJSON (검토 필요)"
    if "DATE" in upper or upper in {"PAYMENT DATE", "DATE ISSUED"}:
        return "date (예외 검증 후)"
    if upper in {"LATITUDE", "LONGITUDE", "SHAPE_AREA", "SHAPE_LEN"}:
        return "decimal (원본값 병행 보존)"
    if upper in {"ZIP", "ZIP CODE"}:
        return "string"
    if upper in {"INSPECTION ID", "LICENSE ID", "LICENSE #", "LICENSE NUMBER", "ACCOUNT NUMBER", "SITE NUMBER", "ID", "AREA_NUMBE", "AREA_NUM_1"}:
        return "string (키)"
    return "string (검토 필요)"


def main():
    profile = json.loads(PROFILE.read_text(encoding="utf-8"))
    lines = ["# 원천 데이터 사전", "", "생성 명령: `python -m src.profiling.render_dictionary`. 수치는 `metadata/source_profiles.json`의 실제 측정값이다. 의미는 제공된 컬럼 메타데이터의 설명을 사용하며 설명이 없거나 불명확하면 `확인 필요`로 표시했다. 이 문서의 Silver 타입은 원천 조사 당시 권장안이다. 현재 구현은 [공용 Silver 데이터 사전](data_dictionary/README.md)을 참고한다.", "", "결측은 원천의 빈 문자열과 공백만 있는 문자열의 합이다. `NULL` 같은 문자 토큰은 별도 집계하고 결측률에 넣지 않는다. 고유값 수는 검증된 Bronze의 원본 컬럼을 한 컬럼씩 정확히 계산했다.", ""]
    for dataset, source in profile["sources"].items():
        meta = json.loads(META_FILES[dataset].read_text(encoding="utf-8-sig"))
        lookup = {item["name"]: item for item in meta}
        if dataset == "community_areas":
            lookup.update({item.get("fieldName"): item for item in meta})
            lookup["geometry"] = lookup.get("the_geom", {})
        lines.extend([f"## {dataset}", "", f"원천: `{source['source_file']}` · {source['rows']:,}행 · {len(source['columns'])}개 원천 컬럼", "", "| 원본 컬럼명 | 의미 | 원본 형식 | Bronze 타입 | Silver 권장 타입 | 결측 건수·비율 | 고유값 수 | 샘플 값 | 주의사항 |", "| --- | --- | --- | --- | --- | ---: | ---: | --- | --- |"])
        for name in source["columns"]:
            stat = source["column_stats"][name]
            item = lookup.get(name, {})
            description = (item.get("description") or "").strip() or "확인 필요"
            if name == "type" and dataset == "community_areas":
                description = "GeoJSON Feature 유형"
            if name == "geometry":
                description = "GeoJSON 공간 geometry 객체"
            source_type = f"{source['format']} 문자열"
            if dataset == "community_areas" and name == "geometry":
                source_type = "GeoJSON 객체"
            elif item.get("dataTypeName"):
                source_type += f" / 메타데이터: {item['dataTypeName']}"
            caution = []
            if stat["whitespace"]:
                caution.append(f"공백값 {stat['whitespace']:,}")
            if stat["null_token"]:
                caution.append(f"NULL형 문자 {stat['null_token']:,}")
            if stat["numeric_integer"] and stat["other_text"]:
                caution.append("숫자형·문자형 혼합")
            if name in {"ID", "LICENSE NUMBER", "License #"}:
                caution.append("이력/매칭 기준 검토")
            if name in {"Violations", "geometry"}:
                caution.append("복합 구조, 분해 전 원본 보존")
            if name in {"ZIP CODE", "Zip"}:
                caution.append("형식 예외 별도 검증")
            if not caution:
                caution.append("없음 (측정 범위)")
            missing = stat["empty"] + stat["whitespace"]
            sample = stat["sample"] or "(비어 있음)"
            lines.append("| " + " | ".join(map(cell, [name, description, source_type, "string", recommended(name, dataset), f"{missing:,} / {stat['missing_rate_percent']:.4f}%", f"{stat['unique_values']:,}", sample, "; ".join(caution)])) + " |")
        lines.append("")
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
