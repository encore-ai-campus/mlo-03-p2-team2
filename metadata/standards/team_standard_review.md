# 팀 공통 표준안 대조 (Silver 사전 설계)

상태: **검토안, 미구현** · 검토일: 2026-11-20 · 기준: `feature/silver-standardization`. 팀원 공유 문서 네 개는 로컬 `C:\Users\Playdata\Downloads`에서 읽었다. 현재 저장소에 원본 문서를 복제하지 않고 필요한 제안과 차이만 이 문서와 CSV에 기록한다. 실제 측정 수치는 [기존 원천 프로파일](../source_profiles.md)과 [기계 판독 결과](../source_profiles.json)를 기준으로 유지한다.

| 팀원 문서 | SHA-256(읽은 버전) | 이 프로젝트에서 사용한 부분 |
| --- | --- | --- |
| `source_data_inventory.md` | `220AA2CB36C2072BEB167511684F84DE668BFF3AF05C446DE44ADF16BD10EDAF` | 원천→표준명·타입, 컬럼 개수 기준 |
| `data_integration_conventions.md` | `1237F9A1BCB89DDE17F794DE786FC6D22411654299B6F78E49DC643C10778D24` | STD-01~06, 공통 용어·코드·날짜·취합 원칙 |
| `domain_proposal_template.md` | `1A2ED354422A86FE7429B75D2C4F1266ACB1024CD50C384ADA23F69ADFE977EB` | 향후 관점별 Gold 설계 검토 항목 |
| `04_license_proposal.md` | `C294ECBD3BB4DBE0E21515CD7358E596A650D9114868A206F60229589446A602` | 인허가 grain, 기간 JOIN 후보, 팀원 집계 |

## 컬럼 범위와 원천 사전

팀 인벤토리의 CSV는 점검 17개+인허가 37개로 이 프로젝트의 [데이터 사전](../data_dictionary.md)과 일치한다. GeoJSON은 **업무·시스템 `properties` 9개**로 세므로 총 63개(17+37+9)다. 이 프로젝트의 65개는 Feature 수준의 `type`과 `geometry`를 별도 원천 컬럼으로 더한 수(17+37+9+2)다. 포털 지역 컬럼 메타데이터 6개는 `the_geom`과 업무 속성 5개를 설명한다. GeoJSON 추출본에는 별도의 시스템 속성 4개가 더 있다. 따라서 63·65·6은 서로 다른 집계 단위이며 측정 오류로 간주하지 않는다.

[65개 컬럼 매핑 검토표](column_mapping_review.csv)는 원천 이름, 팀 표준명·타입, 기존 Silver 타입 권장안을 행별로 비교한다. 팀 표준명은 현재 파이프라인에 적용하지 않았다. 점검 `License #`와 인허가 `LICENSE NUMBER`는 `license_number_key`로, 두 DBA·주소·좌표는 공통 개념으로 매핑하되 결합 결과에서는 `inspection_`/`license_` 출처를 구분한다. `Inspection ID`는 `inspection_key`, 인허가 `LICENSE ID`는 `license_event_key`; 인허가 `ID`는 계산 원천 ID로 구분한다. `account_key + site_key`는 사업장 키 **후보**이며 유일성과 기간 안정성이 아직 검증되지 않았다.

| 항목 | 기존 문서·구현 | 팀 기준안 | 추천·보류 사유 |
| --- | --- | --- | --- |
| 컬럼명 | 원천명 보존, Silver명 미확정 | 65개 대응 `snake_case` 이름 제안 | 매핑 표를 구현 계약 후보로 사용; 테이블 내 이름 충돌과 출처 접두사 합의 후 확정 |
| ID·ZIP·코드 | Bronze와 기존 Silver 권장안은 문자열 | 식별자·ZIP·코드 `string` | 방향 일치; 원문·선행 0 유지 |
| 점검/인허가 날짜 | 기존 Silver 권장 `date` | Arrow `date32`, 표시는 `YYYY-MM-DD`, 이름은 `*_dtm` | 방향 일치. `*_dtm`은 시각처럼 보이지만 실제는 달력 날짜이므로 명명 합의 필요 |
| 지역 번호 | 기존 Silver 권장 `string (검토 필요)` | `int64` | 파싱 실패, `0`, 결측, 경계 매칭 의미 확인 후 변환값 병행 |
| 위경도·경계 수치 | 기존 Silver 권장 `decimal` | `float64` | 계산 편의와 원본 정밀도 간 선택. 원문 병행·오차 허용치 합의 필요 |
| GeoJSON 시각 | 기존 문자열·업무 의미 미확정 | `timestamp[ms, UTC]` | 포털 시스템 시각인지 경계 유효 시각인지 구분한 뒤 변환 |
| geometry | Bronze의 JSON 문자열, 77개 객체 보존 | 표준명 `geometry`, 저장형 미명시 | Silver의 GeoParquet/WKB/GeoJSON 중 선택 전까지 원문 보존 |
| `source_row_num` | 현재 Bronze는 `_SRC_FILE`, `_LOAD_DTM`만 추가 | 공용 Bronze 행 순번 제안 | 기존 Bronze 변경 금지. 원천 순번의 생성·재실행 안정성과 추가 계층을 합의해야 함 |
| 점검 면허번호 `0`·`9999999` | 원문·키 후보 유지 | 해당 필드에서 `null` 제안 | 실제 `0` 840건, `9999999` 1건 확인. 업무상 무효 근거·JOIN 영향 합의 전 자동 변경 금지 |

[타입별 검토표](type_mapping_review.csv)는 65개 각각의 포털 선언/원천 형식, 현재 Bronze `string`, 기존 권장 타입과 팀 후보 타입을 분리한다. 원천 컬럼의 **Bronze 저장 타입을 바꾸자는 문서가 아니다.** 기존 결측률·중복·이상값 결과도 변경하지 않았다.

## STD-01~06 반영 범위

각 STD의 상세한 현재 SI 규칙 연결과 검증 기준은 [변환 규칙 문서](../transformation_rules.md)에 추가했다. `STD-01` 이름 매핑, `STD-02` 공백·결측, `STD-03` 식별자 문자열 보존, `STD-04` 수치, `STD-05` 날짜·시각, `STD-06` 코드 조회는 모두 **Silver 예정·검토 필요**다. Bronze의 문자열 보존과 충돌하지 않는다. 팀 문서의 일괄 trim/null 변환은 기존 프로파일의 빈 문자열·공백 문자열·NULL형 문자를 구분한 뒤 컬럼별로 적용한다. `Violations` 내부 줄바꿈과 설명을 정리 대상으로 취급하지 않는다.

## 코드 상태 계약

[원천 범주값 검토표](code_mapping_review.csv)는 원천에서 직접 센 비공란 범주값 24종과 `Risk` 공란 1종을 기록한다. 팀 문서가 언급한 `shared_code_map.csv`는 **제공된 네 파일 및 현 저장소에서 확인되지 않았다**. 따라서 팀 초안의 예시 코드만 `mapped_code` 후보로 채웠고, 현재 비공란 24종은 모두 `mapping_status=review`다. 0종을 `confirmed` 또는 `unregistered`로 단정하지 않는다. 원천 공란은 `missing_raw`로 분리했다. CSV의 건수는 이번 읽기 전용 원천 집계이며 기존 프로파일 수치를 대체하지 않는다.

| 상태 | 의미 | Silver 적용 제안 |
| --- | --- | --- |
| `confirmed` | 코드표에 등록되고 뜻·소유자·버전이 팀 합의로 확정 | 승인된 표준 코드 사용; 원문도 보존 |
| `review` | 코드 후보는 있으나 뜻·분모·사용 여부가 미확정 | `raw_value`, `mapped_code` 후보, `mapping_status`를 분리; 분석 포함 여부는 팀 합의 전 보류 |
| `unregistered` | 승인된 코드표에 원천 값이 없음 | `mapped_code=null`, 원문과 출현 건수·예외 사유 기록; 조용히 다른 코드로 묶지 않음 |
| `missing_raw` | 원천 공란 | 미등록 값과 구분하고 컬럼별 결측 규칙 적용 |

## 날짜와 다음 단계

CSV 9개 날짜 컬럼은 원천 `MM/DD/YYYY`, 표준 표시 후보 `YYYY-MM-DD`다. 현 프로파일에서 **달력 파싱 실패는 0건**이지만 인허가 만료일 `08/17/0206`, `01/01/9999` 각 1건은 조사 범위 밖 연도다. 읽기 전용 확인에서 두 값은 Python 날짜와 Arrow `date32`로 표현 가능했다. **업무상 유효함을 뜻하지 않는다.** 현재 환경에 Pandas가 없어 Pandas 날짜 타입 변환은 미검증이다. `raw_date_text`, `parse_status`, `business_validity_status`, 표준 date 후보를 분리하고 의미가 확정되지 않으면 기간 JOIN 후보에서 제외하는 안을 검토한다. 값을 `2026` 등으로 추측 보정하거나 삭제하지 않는다.

팀의 기간 JOIN 집계와 현재 번호 전용 집계의 차이, 미매칭·복수 후보·기간 경계는 [통합 검토](integration_review.md)에 기록했다. Silver 구현은 이름·타입·코드표·예외 상태·JOIN 경계 합의 후 진행하는 것이 안전하다.

## 향후 Gold 관점 제시안 계약

팀의 템플릿은 실제 Gold 테이블을 생성하는 지시가 아닌 **설계 검토 양식**으로 사용한다. 각 관점은 분석 목적과 공유 결과, 입력 원천·스냅샷, 각 입력 및 결과의 한 행 단위(grain), 연결 키·적용 시점, 공통 제공 컬럼·타입, 미매칭·중복·다중 후보 처리, 품질 검증의 기준과 실제 측정값, 타 관점 의존성, 팀 합의 항목을 작성한다. `04_license_proposal.md`의 점검 1건당 1행 매칭 결과는 **후보 설계**이며 현재 프로젝트에 구현된 Gold 모델은 없다. 공통 Fact/Dimension은 5개 관점의 제시안을 대조한 뒤 중복 없이 결정한다.
