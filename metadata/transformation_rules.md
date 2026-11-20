# 계층별 역할과 변환 규칙 초안

측정 근거: [원천 프로파일](source_profiles.md)과 [기계 판독 결과](source_profiles.json). 아래 Silver·Gold 규칙은 **예정**이며 현재 구현되지 않았다. `검토 필요`는 데이터 의미나 처리 기준을 팀에서 결정해야 함을 뜻한다. 측정 기준과 업무 규칙을 혼동하지 않는다.

## 계층의 책임

| 계층 | 역할 | 현재 상태 |
| --- | --- | --- |
| Origin | 시카고시 다운로드 스냅샷과 메타데이터·체크섬을 원본 그대로 보관 | 보관 중 |
| Bronze | 원천 행·문자열·geometry를 보존하고 출처·적재 시각만 추가 | 구현됨 |
| Silver | 원본과 정제값을 추적하며 형식·키·범주를 표준화하고 예외를 기록 | 미구현 |
| Gold | 검증된 Silver에서 grain이 명확한 사실·차원·관점별 모델 구성 | 미구현 |

## 규칙 목록

| 규칙 ID | 적용 데이터셋 | 발견한 문제·근거 | 적용 예정 계층 | 예상 처리 방식 | 검증 방법 | 결정 상태 |
| --- | --- | --- | --- | --- | --- | --- |
| BR-001 | 3종 | 원천 파일 무결성 필요; 6개 sidecar 존재 | Bronze (구현됨) | 적재 전 SHA-256 대조, 원천 보존 | 해시 일치, 행·원본값 대조 | 확정 |
| BR-002 | CSV 2종 | ZIP·ID·날짜의 원래 표기 보존 필요 | Bronze (구현됨) | 모든 CSV 원본 컬럼을 Parquet string으로 저장 | 원천과 전체 행·값 비교 | 확정 |
| BR-003 | community_areas | 77개 MultiPolygon geometry | Bronze (구현됨) | geometry 객체를 JSON 문자열로 보존 | 77개 원본 geometry 객체와 대조 | 확정 |
| SI-001 | food_inspections | `City`에 CHICAGO/Chicago/chicago; 기타 표기 차이 | Silver (예정) | 원본값과 정규화 후보를 병행 보관; 매핑표 승인 후 적용 | 원본 복원·매핑 전후 분포 | 검토 필요 |
| SI-002 | business_licenses | 미국 ZIP 패턴 불일치 166건, 해외 코드 가능 | Silver (예정) | 국가·주소 맥락 확인 후 ZIP 형식과 예외 사유 분리 | 예외 166건 재검토 및 규칙별 건수 | 검토 필요 |
| SI-003 | business_licenses | 만료일 `08/17/0206`, `01/01/9999` 각 1건 | Silver (예정) | 원문 보존; 정상 날짜·특수 sentinel·판단 불가를 구분, 추측 보정 금지 | 연도 예외 건수와 처리 사유 대조 | 검토 필요 |
| SI-004 | food_inspections | `Violations` 복수 항목 197,271행, `Comments:` 없는 행 184건 | Silver (예정) | 점검 1행은 유지하고 순서가 있는 `inspection_violations` 파생 테이블 설계 | 분해 항목 재결합·원문 복원, 파싱 예외 수 | 검토 필요 |
| SI-005 | business_licenses | `ID` 중복 출현 252건, `LICENSE NUMBER` 복수 이력 | Silver (예정) | `LICENSE ID` 고유성을 유지; `ID` 생성 규칙·이력 의미 확인 후 키 설계 | 키 유일성, 이력 수, 임의 삭제 0건 | 검토 필요 |
| SI-006 | food_inspections + business_licenses | 점검 266,088행에 인허가 후보 복수 | Silver (예정) | 번호만 JOIN하지 않고 점검일·유효기간·복수 후보 규칙을 합의 | JOIN 전후 행 수, 무매칭·복수 후보 수 | 검토 필요 |
| SI-007 | community_areas + licenses | 지역 번호 공란 99,589건·`0` 38건 | Silver (예정) | 번호 매칭 상태를 분리하고 원본값 유지 | 77개 지역 번호 매칭, 예외 건수 | 검토 필요 |
| SI-008 | food_inspections + community_areas | 점검 좌표 결측 1,064건; 점검에 지역 번호 없음 | Silver (예정) | 좌표 유효성·경계 밖·경계 접촉 처리 기준을 합의 | 공간 매칭 전후 행 수 및 미매칭 사유 | 검토 필요 |
| SI-009 | CSV 2종 | 빈 문자열·공백 문자열·NULL형 문자는 의미가 다름; 인허가 사업체명에 NULL형 문자 398건 | Silver (예정) | 컬럼별 의미를 확인한 뒤 원문과 표준 결측 상태를 병행 보관 | 원본 복원, 결측 유형별 건수 | 검토 필요 |
| GO-001 | 3종 | 인허가 이력과 위반 반복으로 JOIN 시 행 폭증 위험 | Gold (예정) | 각 테이블의 grain과 조인 키를 문서화한 뒤 모델 선택 | grain 키 유일성, JOIN 전후 행 수 | 검토 필요 |

**우선순위 제안:** 원본 추적·키/날짜 의미 합의 → 위반 파싱과 예외 기록 → ZIP·도시명·결측 표준화 → 인허가 기간/지역 매칭 → Gold grain. 아직 Silver 또는 Gold 데이터를 생성하지 않았다.
