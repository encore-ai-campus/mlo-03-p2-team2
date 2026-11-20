# Source Profiling 공유 기록

- **기존 작업 커밋:** `f88e6859df896f69d340f3f3a6f33d636cd4cf49` (`feature/source-profiling`, 부모 Bronze 커밋 `243ad0d`). 이 문서는 2026-11-20 현재 브랜치에서 기존 결과를 읽고 작성했다. 프로파일링 코드와 측정 결과는 이번 작업에서 변경하지 않았다.
- **조사 범위:** 점검 CSV 318,552행·17컬럼, 인허가 CSV 1,212,132행·37컬럼, 지역 GeoJSON 77 Feature·11개 Feature 필드. 모두 원천과 Bronze를 읽기 전용으로 참조한다.

## 조사 방법과 산출물

[프로파일링 코드](../../src/profiling/profile_sources.py)는 원천의 인코딩·헤더·SHA-256·행 수를 확인하고, 컬럼별 빈 문자열·공백 문자열·NULL형 문자, 결측률, 숫자 모양/문자 모양, 날짜 파싱·연도 범위, ZIP 형식, 키 중복, 위반 텍스트, 지역 geometry를 측정한다. 컬럼 고유값은 원천값 대조를 통과한 Bronze에서 한 컬럼씩 계산한다. `license_number_key` 후보의 번호 전용 연결 가능성도 집계한다.

| 기존 파일 | 내용 |
| --- | --- |
| [`metadata/source_profiles.json`](../../metadata/source_profiles.json) | 실행 ID와 전체 측정값 |
| [`metadata/source_profiles.md`](../../metadata/source_profiles.md) | 사람이 읽는 품질·구조 요약 |
| [`metadata/data_dictionary.md`](../../metadata/data_dictionary.md) | 원천 컬럼 65개 사전 |
| [`metadata/transformation_rules.md`](../../metadata/transformation_rules.md) | 계층별 규칙 초안. 2026-11-20 팀 표준 대조 절이 별도로 추가됨 |
| [`docs/decision_log.md`](../decision_log.md) | 기존 Bronze·Profiling 결정의 근거 |

```powershell
cd C:\mlo-03-p2-team2
python -m src.profiling.profile_sources
python -m src.profiling.render_dictionary
python -m src.profiling.render_profiles
```

프로파일 실행 로그는 Git 제외 대상 `logs/profiling_runs.csv`로, 측정 문서와 별도로 관리한다.

## 주요 기존 측정 결과

- 인허가 `ID` 중복 출현 252건, `LICENSE ID` 중복 0건. `LICENSE NUMBER`는 이력에 반복된다.
- 점검 `Violations` 빈 문자열 90,000행, 복수 후보 항목 197,271행. `Comments:` 없는 행 184건.
- 인허가 ZIP의 미국 5자리/ZIP+4 패턴 불일치 166건. 만료일의 조사 범위 밖 연도는 `08/17/0206`, `01/01/9999` 각 1건.
- 번호만 연결하면 점검 266,088건에 인허가 후보가 여러 개다. 기간을 적용한 매칭 결과가 아니다.
- 지역 77개 모두 `MultiPolygon`; 원천 geometry와 Bronze JSON 문자열의 객체 비교에서 오류 0건.

## 검증 출처와 Silver 인계

- **과거 Profiling 실행:** 기존 JSON에 기록된 실행 ID `79e8b4280ab443eb9d73f6774dfff5f5`와 기존 프로파일링 로그에 근거한다. 이번 작업에서 프로파일링 파이프라인을 다시 실행하지 않았다.
- **2026-11-20 이번 작업에서 직접 실행:** 전체 `python -m pytest -q` → **5개 통과**. 기존 측정 JSON·Markdown을 변경하지 않았다.

Silver에는 빈/공백/NULL형 문자 구분, 이력 키, 날짜의 파싱과 업무 유효성 분리, ZIP·도시명, 위반 항목 분해, 번호·기간 JOIN의 예외 처리를 전달한다. 팀의 표준명과 타입은 [표준안 대조](../../metadata/standards/team_standard_review.md)에 **미확정 후보**로 정리했다.
