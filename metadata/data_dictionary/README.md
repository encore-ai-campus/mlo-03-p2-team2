# 공용 Silver 데이터 사전

[공용 컬럼 사전](shared_silver_columns.csv)에서 원천 컬럼명, Silver 표준명, 타입, 변환 규칙을 관리한다. [공용 코드표](shared_code_map.csv)는 원천 범주값과 표준 코드의 대응을 관리한다.

| 공용 테이블 | 업무 컬럼 | 기본 키 | 주요 규칙 |
| --- | ---: | --- | --- |
| 식품위생 점검 | 17 | `inspection_key` | 점검일은 `date32`, 좌표는 `float64`. 결과·위험도는 코드표를 조회하고, 공란과 미등록값은 각각 품질 플래그로 기록한다. 위반 원문은 비어 있지 않으면 그대로 보존한다. |
| 사업 인허가 | 19 | `license_event_key` | 면허번호 등 식별자는 문자열, 이력 날짜는 `date32`. 신청·상태 코드는 기존 04 규칙에 따라 대문자로 표준화한다. |
| 커뮤니티 지역 경계 | 3 | `community_area_num` | 지역 번호는 `int64`, 지역명은 양끝 공백을 제거하고, 경계 JSON은 보존한다. |

세 테이블은 `source_row_num`을 `int64`로 추가해 Bronze 행과 일대일로 추적한다. 사전에서 `date`는 Arrow `date32`를 뜻한다. 논리 타입 `string`은 Arrow `string`과 `large_string`을 허용한다.

## 관점별 규칙과 참조 자료

- [04 독립 점검 컬럼](04_license/standalone_inspection_columns.csv)은 공용 입력을 받기 전 04 독립 실행에 쓰는 호환 규칙이다. 인허가 컬럼은 공용 사전을 공유하고, 사용자 지정 `--dictionary`는 기존 CSV 형식을 따른다.
- [05 공간 처리 계약](05_geospatial/column_contract.json)은 지역 분석의 독립 실행과 파생 산출물을 위한 계약이다. 02 위반 키 등록부는 [02 표준화 자료](../standards/02_violation/)에서 관리한다.
- [원천 프로파일 사전](../data_dictionary.md)과 [표준안 검토](../standards/team_standard_review.md)는 원천 조사와 설계 이력이다. 현재 공용 Silver의 컬럼 검증은 위 공용 사전을 기준으로 실행한다.

## 변경 후 검증

저장소 루트에서 공용 스냅샷을 복원하고, 컬럼·타입·코드표·키·행 순번의 일치를 검사한다.

```powershell
python -m src.domains.06_integration.publish --restore
python -m src.silver.validate_integration_silver
```

실제로 변환 규칙을 바꿨다면 새 실행 경로에서 빌드하고 배포 전후의 값을 대조한다. [공용 Bronze·Silver 실행 가이드](../../docs/domains/06_integration.md)
