# Silver 표준안 통합 작업 변경 로그

## 1. 작업 개요

- **작업일:** 2026-11-20
- **작업자:** 확인되지 않음
- **브랜치:** `feature/silver-standardization` (`feature/source-profiling`의 `f88e685`에서 시작)
- **목적:** 팀 공통 표준안과 기존 원천 프로파일·데이터 사전·변환 규칙을 대조해 Silver 구현 전 계약 후보와 미확정 사항을 기록한다. **Silver·Gold 데이터나 코드는 만들지 않았다.**
- **읽은 팀 문서:** `source_data_inventory.md`, `data_integration_conventions.md`, `domain_proposal_template.md`, `04_license_proposal.md` (로컬 Downloads). 읽은 버전의 SHA-256은 [표준안 대조](../../metadata/standards/team_standard_review.md)에 있다.

## 2. 변경 파일 목록

| 파일 경로 | 신규/수정 | 변경 내용 | 변경 이유 |
| --- | --- | --- | --- |
| `metadata/transformation_rules.md` | 수정 | STD-01~06 대조 절과 후속 문서 링크 추가 | 기존 SI 측정·규칙을 보존하며 팀 초안과 연결 |
| `metadata/standards/team_standard_review.md` | 신규 | 65컬럼 범위, 표준명·타입 충돌, 코드·날짜·Gold 준비 | 팀 제안과 현재 구현의 차이를 한곳에서 검토 |
| `metadata/standards/column_mapping_review.csv` | 신규 | 원천 65컬럼과 팀 표준명·타입 행별 대조 | 이름 매핑의 누락·충돌 확인 |
| `metadata/standards/type_mapping_review.csv` | 신규 | 원천·Bronze·기존 권장·팀 후보 타입 비교 | 변환·정밀도 예외 확인 |
| `metadata/standards/code_mapping_review.csv` | 신규 | 실제 범주값 24종+Risk 공란과 팀 코드 예시 검토 | 코드 의미를 확정·검토·미등록으로 구분하기 위한 초안 |
| `metadata/standards/integration_review.md` | 신규 | 번호/기간 JOIN과 날짜 예외·후보 상태 | 조건이 다른 두 집계를 혼동하지 않기 위함 |
| `docs/silver_standardization_changelog.md` | 신규 | 이 변경 로그 | 팀원에게 변경·미확정을 공유 |
| `docs/bronze_pipeline_changelog.md` | 신규 | 기존 Bronze 작업의 사실·검증 요약 | 팀 통합 시 입력·적재 계약 공유 |
| `docs/source_profiling_changelog.md` | 신규 | 기존 Profiling 작업의 사실·검증 요약 | 팀 통합 시 품질 근거 공유 |

기존 `metadata/source_profiles.json`, `metadata/source_profiles.md`, `metadata/data_dictionary.md`, Origin, Bronze, Python 코드는 변경하지 않았다. 수정한 변환 규칙 원본은 저장소 밖 `C:\mlo-03-p2-team2-standards-backup-20261120\transformation_rules.md`에 SHA-256 확인 후 백업했다. 이전 브랜치 분리 백업도 유지한다.

## 3. 표준화 규칙 변경 내역

| 규칙 ID | 기존 기준 | 변경·보완 기준 | 변경 이유 | 상태 |
| --- | --- | --- | --- | --- |
| STD-01 | Silver명 미확정; SI-005~008의 키·매칭 검토 | 데이터셋+원천 컬럼으로 65개 표준명 후보 조회 | 팀 간 같은 개념의 이름을 맞추기 위함 | 예정·미확정 |
| STD-02 | SI-001·SI-009: 빈/공백/NULL형 문자 구분 | 일반 텍스트 trim과 null 후보를 원문 병행으로 검토; 위반 원문 내부 보존 | 원천 결측 유형을 잃지 않기 위함 | 예정·미확정 |
| STD-03 | Bronze 식별자·ZIP 문자열 보존 | Silver도 문자열 유지; `0`·`9999999` 면허번호 sentinel 제안 별도 판정 | 선행 0과 원문 유지, 무효 판단은 별도 | 예정·미확정 |
| STD-04 | 좌표·지역 코드 범위 검토 | 지역 번호 `int64`, 좌표·경계 수치 `float64` 후보 | 형식 변환과 업무 범위 검사를 분리 | 예정·미확정 |
| STD-05 | SI-003: 날짜 특이값 원문 보존 | `date32`·UTC timestamp 후보, 파싱/업무 유효성 분리 | 파싱 성공이 업무상 정상이라는 뜻은 아님 | 예정·미확정 |
| STD-06 | 범주 매핑 승인 전 원문 유지 | `raw_value`, `mapped_code`, `mapping_status` 분리 | 검토 중과 미등록을 섞지 않기 위함 | 예정·미확정 |

기존 SI-001~009, GO-001과 과거 측정 수치는 변경하지 않았다. 상세 검증 기준은 [변환 규칙](../../metadata/transformation_rules.md)에 있다.

## 4. 컬럼명 및 데이터 타입 변경 내역

아래는 **검토한 대표 컬럼**이다. 전체 65개는 [컬럼 매핑](../../metadata/standards/column_mapping_review.csv)과 [타입 대조](../../metadata/standards/type_mapping_review.csv)에 있다. 기존 사전은 원천명과 Bronze `string`을 기록했고 Silver명은 미확정이었다.

| 원천 데이터 | 원천 컬럼 | 기존 표준안 | 팀 공통 표준안 | 적용 여부 |
| --- | --- | --- | --- | --- |
| 점검 | `Inspection ID` | Silver `string (키)` 권장 | `inspection_key` · `string` | 매핑 후보만 기록 |
| 점검·인허가 | `License #` / `LICENSE NUMBER` | 문자열 키 후보 | `license_number_key` · `string` | 매핑 후보만 기록 |
| 인허가 | `LICENSE ID` | Silver 문자열 키 후보 | `license_event_key` · `string` | 매핑 후보만 기록 |
| 점검 | `Inspection Date` | `date` 권장 | `inspection_dtm` · `date32` | 타입·이름 검토 중 |
| 인허가 | `LICENSE TERM EXPIRATION DATE` | 특이 연도 별도 판정 | `term_end_dtm` · `date32` | 업무 유효성 미확정 |
| 인허가·지역 | `COMMUNITY AREA` / `area_numbe` | 문자열 검토 | `community_area_num` · `int64` | 예외·범위 확인 전 미적용 |
| 두 CSV | 위도·경도 | `decimal` 권장 | `latitude` / `longitude` · `float64` | 정밀도 합의 전 미적용 |
| 지역 | `geometry` | Bronze JSON 문자열 | `geometry` · 저장형 미명시 | 보존·형식 검토 중 |

팀 인벤토리는 CSV 54개+GeoJSON `properties` 9개=63개를 센다. 기존 사전 65개는 Feature `type`, `geometry`를 더한 값이다. 원천 컬럼을 새로 만들거나 삭제한 차이가 아니다.

## 5. 코드 매핑 및 날짜 예외 처리

- 제공된 네 문서와 현 저장소에 전체 `shared_code_map.csv`가 없어 **확정 코드 0건**으로 둔다. 실제 비공란 범주값 24종은 모두 `review`, `Risk` 공란은 `missing_raw`로 기록했다. 승인 코드표에 없는 값은 향후 `unregistered`, `mapped_code=null`과 원문·사유로 기록한다. 검토 중 코드의 분석 사용은 팀 합의 전 보류한다.
- 팀 문서의 명시적 예시만 `mapped_code` 후보로 기록했다. 등록 여부가 확인된 코드표라고 주장하지 않는다.
- 만료일 `08/17/0206`, `01/01/9999`는 각 1건이다. Python/Arrow `date32`로 읽을 수 있지만 업무 유효성은 미확정이다. 원본 문자열을 보존하고 파싱 상태와 업무 판정을 분리한다. Pandas 날짜 변환은 현 환경에 Pandas가 없어 **미검증**이다.
- 점검 면허번호 `0` 840건·`9999999` 1건을 원천에서 확인했지만 null로 변경하지 않았다.

## 6. 데이터 통합 및 JOIN 기준

- 공통 연결 후보: `Inspection ID`→`inspection_key`, `LICENSE ID`→`license_event_key`, `License #`/`LICENSE NUMBER`→`license_number_key`. 사업장 `account_key + site_key`는 검증 전 후보.
- **번호만:** 기존 프로젝트에서 직접 집계한 점검 0/1/복수 후보는 **16,577 / 35,887 / 266,088**건(0은 번호 공란 19건 포함).
- **번호+기간:** 팀 `04_license_proposal.md`의 0/1/복수 후보 **84,828 / 232,323 / 1,401**건을 인용했다. 이 프로젝트에서 같은 조건으로 재검증하지 않았으며 기간 경계·sentinel 처리와 실행 코드 확인이 필요하다.
- 미매칭은 원인별 상태, 복수 후보는 후보 수와 원본 후보 목록을 보존하는 안이다. 단일 후보만 확정 연결할지, 취소·철회일과 종료일 포함 여부는 미합의다. [통합 검토](../../metadata/standards/integration_review.md)에 상세히 기록했다.

## 7. 검증 및 테스트 결과

| 검증 항목 | 결과 | 확인 방법 |
| --- | --- | --- |
| 현재 브랜치·기준 | `feature/silver-standardization`, 시작 커밋 `f88e685` | `git branch --show-current`, `git log` |
| 원천 무결성 | 데이터 3종의 sidecar SHA-256 일치 | 이번 작업에서 읽기 전용 `verify_source` 실행 |
| Bronze 보존 | 점검 318,552×19, 인허가 1,212,132×39, 지역 77×13 | 기존 Parquet 메타데이터 확인; 재적재 안 함 |
| 매핑 범위 | 원천 컬럼 65개와 팀 인벤토리 대응 65개 일치 | CSV 생성 시 컬럼 집합 검증 |
| 코드 값 범위 | 비공란 24종+Risk 공란 | 원천 두 CSV를 읽기 전용 집계 |
| Bronze 테스트 | **3개 통과** | 이번 작업에서 `python -m pytest tests/bronze -q` 실행 |
| 전체 테스트 | **5개 통과** | 이번 작업에서 `python -m pytest -q` 실행 |
| 팀의 기간 JOIN 집계 | **미검증** | 제공된 04번 문서에서 인용만 함 |

## 8. 팀원 합의 필요 사항

| 항목 | 현재 제안 | 합의가 필요한 이유 | 상태 |
| --- | --- | --- | --- |
| 코드표와 검토 코드 | 전체 코드표·뜻·버전·소유자 수령 후 확정 | 24개 관측값의 승인 상태를 현재 알 수 없음 | 미확정 |
| 특이 날짜 | 원문 보존, 업무 미확정 값은 기간 후보 보류 | 0206·9999의 원천 의미 미확인 | 미확정 |
| 면허번호 sentinel | `0`, `9999999`를 원문과 별도 판정 | 무효·미매칭 지표 영향 | 미확정 |
| 기간 JOIN | 양쪽 포함 후보, 0/복수 상태 보존 | 종료일, 취소·철회, 다중 후보 우선순위 영향 | 미확정 |
| 공통 키와 표준명 | 팀 표준명 후보 활용 | `*_dtm`이 date32인 명명, `matched_license_event_id` 차이 | 미확정 |
| 수치·공간 타입 | float64·int64 후보와 원문 병행 | 정밀도, 범위, geometry 저장형 결정 | 미확정 |
| 원천 행 순번 | 안정적인 lineage 설계 후 추가 | 현 Bronze에는 `source_row_num`이 없음 | 미확정 |

## 9. 다음 작업

1. 팀에서 전체 코드표, 04번 기간 JOIN 실행 코드·스냅샷, 예외·다중 후보 기준을 확인한다.
2. Silver 구현 전 원천→표준 컬럼명, 날짜/수치 저장형, 결측·코드 상태를 승인한다.
3. 승인 뒤에만 원문 추적을 유지하는 Silver Parquet 3종과 규칙별 Data Quality 검증을 설계·생성한다. 원천 대비 행 수, 변환 실패, 키·코드·날짜 예외를 자동 확인한다.
4. 관점별 Gold 제시안을 같은 grain·키·품질 양식으로 대조한 뒤 공통 모델을 결정한다. 현재 Gold 스키마나 테이블은 생성하지 않았다.
