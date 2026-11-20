"""Render measured source-profile summary without changing source data."""

import csv
import json

from src.bronze.paths import ORIGIN_ROOT, PROJECT_ROOT


PROFILE = PROJECT_ROOT / "metadata" / "source_profiles.json"
OUTPUT = PROJECT_ROOT / "metadata" / "source_profiles.md"


def main():
    data = json.loads(PROFILE.read_text(encoding="utf-8"))
    sources = data["sources"]
    with (ORIGIN_ROOT / "download_manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
        manifest = {row["File"]: row for row in csv.DictReader(stream)}
    lines = ["# Origin 구조·품질 프로파일", "", f"실행 ID `{data['run_id']}` · UTC `{data['executed_at_utc']}` · 재실행: `python -m src.profiling.profile_sources` 및 `python -m src.profiling.render_profiles`", "", "## 측정 기준", "", "- CSV는 UTF-8(선택적 BOM), 쉼표 구분자로 파싱했다. GeoJSON은 UTF-8 `FeatureCollection`으로 파싱했다. 원천 파일과 대응 `.sha256`을 대조했다.", "- **빈 값**은 CSV 필드가 정확히 빈 문자열이거나 JSON `null`인 경우다. **공백값**은 비어 있지 않으나 `strip()` 결과가 빈 문자열인 경우다. `NULL`·`N/A`·`NA`·`NONE`은 **NULL형 문자값**으로 별도 기록했고 자동 결측 처리하지 않았다.", "- 결측률 = (빈 값 + 공백값) / 전체 행 수. 고유값 수는 원천값 전체 대조를 통과한 Bronze 원본 컬럼에서 컬럼별로 정확히 계산했다. 빈 문자열도 고유값에 포함된다.", "- 숫자형·문자형 혼합은 **문자 모양**의 분류다. 업무 데이터 타입 오류 판정이 아니다. 날짜의 비정상 연도는 1900년 미만 또는 2100년 초과라는 **조사 기준**이며 자동 정제 기준이 아니다.", "- 완전 동일 행 수는 각 행의 128비트 digest로 비교한 결과다. 해시 충돌 가능성이 있으므로 엄밀한 원문 바이트 단위 중복 증명은 아니다.", "", "## 데이터 출처", "", "세 파일은 `origin/download_manifest.csv`에 시카고시 오픈데이터 다운로드 URL과 SHA-256이 기록된 동일 스냅샷이다. 원천 파일 경로와 제공 컬럼 메타데이터는 아래 데이터셋별로 제시한다.", ""]
    for name, source in sources.items():
        filename = source["source_file"].split("/")[-1]
        metadata_file = {"food_inspections": "food_columns.json", "business_licenses": "license_columns.json", "community_areas": "area_columns.json"}[name]
        metadata = json.loads((ORIGIN_ROOT / name / metadata_file).read_text(encoding="utf-8-sig"))
        metadata_names = {item["name"] for item in metadata} if name != "community_areas" else {item.get("fieldName") for item in metadata}
        actual_names = set(source["columns"])
        if name == "community_areas":
            actual_names.remove("type")
            actual_names.remove("geometry")
            metadata_names.discard("the_geom")
        metadata_extra = sorted(metadata_names - actual_names)
        actual_extra = sorted(actual_names - metadata_names)
        lines.extend([f"## {name}", "", f"- 파일: `origin/{source['source_file']}` · 형식: {source['format']} · 인코딩: {source['encoding']} · {source['rows']:,}행 × {len(source['columns'])}컬럼", f"- 출처 URL(원본 manifest): {manifest[filename]['Source']}", f"- 제공 컬럼 메타데이터: `origin/{name}/{metadata_file}`. 메타데이터에만 있는 항목: {metadata_extra or '없음'}. 실제 속성에만 있는 항목: {actual_extra or '없음'}.", f"- 원본 컬럼 목록·의미·타입·샘플: [data_dictionary.md](data_dictionary.md). 재현 가능한 전체 측정값: [source_profiles.json](source_profiles.json).", f"- 완전 동일 행 후보: {source['full_row_duplicates_hash16']:,}건.", "", "### 컬럼별 결측과 고유값", "", "| 원본 컬럼 | 빈 값 | 공백값 | NULL형 문자 | 결측률 | 고유값 수 |", "| --- | ---: | ---: | ---: | ---: | ---: |"])
        for col in source["columns"]:
            s = source["column_stats"][col]
            lines.append(f"| {col.replace('|', '&#124;')} | {s['empty']:,} | {s['whitespace']:,} | {s['null_token']:,} | {s['missing_rate_percent']:.4f}% | {s['unique_values']:,} |")
        lines.extend(["", "### 키·형식·날짜", "", "| 키 후보 | 중복 출현 행 수 | 중복률 |", "| --- | ---: | ---: |"])
        for key, count in source["key_duplicate_rows"].items():
            lines.append(f"| {key} | {count:,} | {source['key_duplicate_rate_percent'][key]:.4f}% |")
        if name != "community_areas":
            lines.extend(["", f"도시명 표기 사례(전체 행 기준): `{source.get('city_spelling_examples', {})}`."])
        if name == "food_inspections":
            lines.append(f"사업체명 대소문자 표기 차이 사례: `{source.get('business_name_case_variants', [])[:5]}`. 동일 사업체임을 확정한 것은 아니다.")
        if "dates" in source:
            lines.extend(["", "날짜는 비어 있지 않은 값을 `%m/%d/%Y`로 달력 파싱했다. 파싱 실패와 범위 밖 연도는 별도 측정했다.", "", "| 날짜 컬럼 | 최소 | 최대 | 파싱 실패 | 조사 범위 밖 연도 | 예시 |", "| --- | --- | --- | ---: | ---: | --- |"])
            for col, values in source["dates"].items():
                lines.append(f"| {col} | {values['min']} | {values['max']} | {values['invalid_calendar']:,} | {values['outside_1900_2100']:,} | {', '.join(values['examples']) or '—'} |")
            mixed = [(col, s) for col, s in source["column_stats"].items() if s["numeric_integer"] and s["other_text"]]
            lines.extend(["", "숫자 모양과 일반 문자가 함께 나온 컬럼(업무상 혼합 타입으로 확정한 것은 아님):", "", "| 컬럼 | 정수 모양 | 소수 모양 | 그 외 문자 |", "| --- | ---: | ---: | ---: |"])
            for col, s in mixed:
                lines.append(f"| {col} | {s['numeric_integer']:,} | {s['numeric_decimal']:,} | {s['other_text']:,} |")
            lines.extend(["", f"ZIP의 미국 5자리 또는 ZIP+4 정규식 불일치: **{source['zip_non_us_pattern_count']:,}건**. 예시: {', '.join(f'{value} ({count})' for value, count in source['zip_non_us_pattern_examples'][:5]) or '없음'}. 해외 주소·원천 오류 여부는 별도 판단이 필요하다.", ""])
        else:
            lines.extend(["", f"GeoJSON 최상위 키: `{source['top_level_keys']}`. Feature 키: `{source['feature_keys']}`. `properties` 키: `{source['property_keys']}`.", f"Geometry 유형: `{source['geometry_types']}`. 속성·geometry 구조 및 Bronze 값 대조 오류: `{source['structural_errors']}`. `area_numbe` 중복은 0건이다.", "", "`pd.json_normalize()` 같은 평탄화는 `properties`의 속성에만 적용할 수 있다. `geometry.coordinates`는 중첩 배열을 유지해야 하므로 평탄화 대상이 아니다. 현재 Bronze의 JSON 문자열을 파싱해 원본 geometry 객체와 77건 모두 비교했다.", ""])
    food = sources["food_inspections"]
    v = food["violations"]
    lines.extend(["## 반복 위반 텍스트", "", f"`Violations` 빈 문자열 {v['empty']:,}건, 비어 있지 않은 행 {v['nonempty']:,}건. 공백만 있는 행 {v.get('whitespace', 0):,}건. 공백을 양쪽에 둔 `|`로 나눈 **후보 항목**은 {v['candidate_items']:,}개이고, 복수 항목 행은 {v['multi_item_rows']:,}건이다. 이 수는 아직 확정된 위반 건수가 아니다.", f"후보 조각의 번호 머리글 정규식 `^\\d+[A-Z]?\\.\\s+`에 맞지 않는 행은 {v.get('rows_with_nonstandard_header', 0):,}건이었다. `Comments:` 표지가 없는 행은 {v['rows_without_comments_marker']:,}건이다. 예를 들어 `56. ADEQUATE VENTILATION & LIGHTING; DESIGNATED AREAS USED`처럼 머리글만 있고 설명이 없는 형태가 있다. 구분자 없는 `|` 관측 행은 {v['rows_with_unspaced_pipe']:,}건이다.", "", "**설계 제안:** Silver에서 `inspection_violations` 파생 테이블을 만들면 점검 1건의 여러 위반을 표현할 수 있다. `Inspection ID`와 원래 항목 순서, 원문 전체, 파싱 상태를 유지하고, 조각 분해 실패는 별도 예외로 기록한다. `Comments:`가 없는 행을 무조건 실패로 버리지 않는다. 위반 코드의 시대별 의미와 분모는 팀 결정이 필요하다. Bronze는 1점검 1행을 유지한다.", ""])
    license = sources["business_licenses"]
    join = data["joins"]["inspection_license_number"]
    area = data["joins"]["license_area_number"]
    lines.extend(["## 인허가 이력과 연결성", "", f"인허가 `ID`는 중복 출현 행 {license['key_duplicate_rows'].get('ID', 0):,}건, `LICENSE ID`는 0건, `LICENSE NUMBER`는 {license['key_duplicate_rows'].get('LICENSE NUMBER', 0):,}건이다. `ID=2835961-20260416`의 두 행은 `LICENSE ID`가 `3072380`·`3072378`로 다르고 상태도 `AAI`·`AAC`로 다르다. 즉 단순 동일 행은 아니다. `LICENSE NUMBER=1697585`에는 `ISSUE` 후 여러 `RENEW` 기간이 관찰된다. 중복을 삭제하지 않는다.", "", "발급·갱신·상태 관련 컬럼: `APPLICATION TYPE`, `APPLICATION CREATED DATE`, `APPLICATION REQUIREMENTS COMPLETE`, `PAYMENT DATE`, `CONDITIONAL APPROVAL`, `LICENSE TERM START DATE`, `LICENSE TERM EXPIRATION DATE`, `LICENSE APPROVED FOR ISSUANCE`, `DATE ISSUED`, `LICENSE STATUS`, `LICENSE STATUS CHANGE DATE`. 시점별 의미와 유효기간 경계는 아직 결정되지 않았다.", "", f"점검 `License #` ↔ 인허가 `LICENSE NUMBER`: 비공란 번호가 양쪽에 존재하는 고유 번호 {join['distinct_shared_nonblank']:,}개. 점검 행 기준 번호 공란 {join['inspection_rows_blank']:,}, 비공란 무매칭 {join['inspection_rows_no_match_nonblank']:,}, 후보 1건 {join['inspection_rows_one_candidate']:,}, 후보 복수 {join['inspection_rows_multiple_candidates']:,}; 번호당 최대 후보 {join['max_license_history_candidates']}건. 따라서 번호만으로 JOIN하면 행이 늘어난다.", f"인허가 `COMMUNITY AREA` ↔ 지역 `area_numbe`: 77개 지역 번호가 모두 나타난다. 인허가 지역번호 공란 {area['blank_rows']:,}건, 비공란 미매칭 {area['nonblank_unmatched_rows']:,}건(`{area['unmatched_values']}`). 점검에는 지역번호가 없어 좌표 기반 연결이 필요하지만 아직 공간 JOIN을 수행하지 않았다.", "", "## Silver 작업 후보", "", "1. 키·원본 행 식별과 날짜 의미를 합의하고 인허가 이력의 기간·다중 후보 규칙을 설계한다.", "2. 위반 텍스트를 원문 보존형 파생 테이블로 구조화하고 예외 형식을 기록한다.", "3. 만료일 이상 연도, ZIP 형식, 표기 차이, 결측·NULL형 문자값을 규칙별로 판정한다.", "4. 지역 경계 연결과 좌표 결측·경계 밖 처리 기준을 정한다.", "", "이 문서는 측정 결과와 설계 제안을 구분한다. 위 항목은 Silver 구현 결과가 아니다.", ""])
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
