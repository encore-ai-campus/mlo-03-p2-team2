# Chicago Food Safety Data Quality & AI-Ready Platform

시카고시의 식품위생 점검, 사업체 인허가, 지역 경계 데이터를 연결해 위생 점검 패턴을 분석하는 팀 프로젝트입니다. 원천 검증부터 Bronze, Silver, Gold, AI-Ready까지 단계별로 구성합니다.

[초기 프로젝트 기획서](docs/00_project_plan.md)에서 목표와 작업 범위를 확인할 수 있습니다. 팀 논의와 이후 결정은 [프로젝트 Wiki](https://github.com/encore-ai-campus/mlo-03-p2-team2/wiki)에 기록합니다.

## 관점별 작업 폴더

| 폴더명 | 분석 관점 |
| --- | --- |
| `01_inspection` | 식품위생 점검 성과 |
| `02_violation` | 위반 유형 |
| `03_repeat_inspection` | 반복 위반·후속 검사 |
| `04_license` | 사업체 인허가 이력 |
| `05_geospatial` | 지역별 점검 패턴 |

관점별 코드와 테스트는 각각 `src/domains/<폴더명>/`과 `tests/domains/<폴더명>/`에 둡니다. 파일명은 영문 `snake_case`를 사용합니다. 04번의 예시는 `match_license_periods.sql`과 `test_match_license_periods.py`입니다.

## 로컬 설정

팀이 공유한 원천 데이터와 컬럼 JSON을 `origin/`에 두고, `.env.example`을 `.env`로 복사합니다. 원천과 공유용 압축본은 Git에서 제외됩니다. [원천 설정 예시](config/sources.example.yaml) · [공용 작업 규칙](AGENTS.md)

원천 파일의 데이터셋별 배치, Bronze 적재·검증·재실행 방법은 [Bronze 작업 안내](docs/bronze.md)에 기록했습니다.
Bronze 출력은 `data/bronze/<데이터셋>/<데이터셋>.parquet`에 저장합니다.

Silver 설계 전 원천 구조와 품질을 확인하려면 [원천 프로파일](metadata/source_profiles.md), [컬럼 데이터 사전](metadata/data_dictionary.md), [변환 규칙 초안](metadata/transformation_rules.md), [결정 로그](docs/decision_log.md)를 참조합니다. 재실행 명령은 `python -m src.profiling.profile_sources`이며, 이후 `python -m src.profiling.render_dictionary`와 `python -m src.profiling.render_profiles`로 문서를 갱신합니다.
