# 데이터 폴더 구조 변경 기록

## A. 작업 개요

- **작업일:** 2026-11-20
- **Git 브랜치:** `chore/data-directory-structure`
- **기준 커밋:** `a33fadf15b409f385c007bb6fa869d2b6f8025c2`
- **목적:** 강사님 요구에 맞춰 Origin, Bronze, Silver, Gold의 데이터 경로를 단계별로 정리하고, 기존 파이프라인이 새 경로를 읽도록 설정을 갱신한다.
- **요구 구조:** `data/00_origin/`, `data/01_bronze/`, `data/02_silver/`, `data/03_gold/`를 사용하며 기존 `ai_ready/`, `quarantine/` 디렉터리도 보존한다. 파이프라인 코드는 `src/bronze/`, `src/profiling/`, `src/silver/`에 둔다.

변경 전 데이터 경로는 `origin/`, `data/bronze/`, `data/silver/`, `data/gold/`였다. 새 경로로 복사하고 검증한 뒤 기본 코드 경로를 변경했다. **기존 경로의 파일은 삭제하지 않아 두 위치가 함께 남아 있다.**

현재 목표 구조와 보존한 기존 경로는 다음과 같다.

```text
data/
├── 00_origin/       # 읽기 전용 원천 복사본
├── 01_bronze/       # 원천 형식·값을 보존한 Parquet
├── 02_silver/       # 표준화 단계용
├── 03_gold/         # 분석 모델 단계용
├── ai_ready/        # 향후 AI 데이터용, 유지
├── quarantine/      # 향후 격리 데이터용, 유지
├── bronze/          # 기존 데이터, 안전 확인 전까지 유지
├── silver/          # 기존 경로 및 표시 파일 유지
└── gold/            # 기존 경로 및 표시 파일 유지

src/
├── bronze/          # Bronze 적재 코드
├── profiling/       # 원천 프로파일링 코드
└── silver/          # Silver 구현 코드 위치
```

## B. 구조를 나눈 이유

- **Origin과 Bronze:** Origin은 받은 원본 스냅샷을 읽기 전용으로 보관한다. Bronze는 원본 값을 보존하면서 Parquet과 적재 기술 컬럼을 붙여 파이프라인에서 읽기 쉽게 만든 사본이다. 둘을 나누면 원본과 적재 산출물을 혼동하지 않고 비교할 수 있다.
- **Silver와 Gold:** Silver는 원천의 표준화와 품질 규칙을 적용하는 정제 데이터 단계다. Gold는 분석 목적에 맞춘 사실·차원·집계 모델 단계다. 목적과 행 단위가 다르므로 별도 경로에 둔다. 이번 작업은 Silver·Gold 데이터를 만들지 않았다.
- **단계 번호:** `00_`부터 `03_`까지 붙여 파일 탐색기에서 처리 순서대로 보이게 한다. 디렉터리 이름만으로 데이터 계층을 식별하기 쉽다.
- **코드와 데이터:** `src/`에는 재실행할 코드, `data/`에는 입력 및 생성 데이터를 둔다. 코드 변경과 데이터 산출물을 구별하고, 큰 데이터 파일을 Git에서 제외하기 쉽다.
- **경로 설정 변경:** 파이썬은 설정된 경로를 기준으로 입력과 출력을 찾는다. 폴더만 이동하면 코드가 예전 위치를 계속 조회해 파일을 찾지 못하므로 중앙 경로 설정과 경로를 문서로 만드는 코드도 함께 바꿔야 한다.

## C. 실제 변경 내역

아래는 이번 브랜치의 실제 Git diff를 확인해 요약한 것이다.

| 파일 | 변경 전 | 변경 후 | 변경 이유 |
| --- | --- | --- | --- |
| `src/bronze/paths.py` | 기본 Origin `origin/`, Bronze `data/bronze/` | 기본 Origin `data/00_origin/`, Bronze `data/01_bronze/`; `CHICAGO_RAW_DIR` 상대경로는 프로젝트 루트 기준으로 해석 | 새 경로에서 Bronze 적재와 프로파일링이 입력을 찾도록 중앙 경로를 조정 |
| `src/bronze/load_bronze.py` | CSV 요약 로그만 기록 | 기존 CSV 열은 유지하고 실행별 상세 JSONL 기록 추가 | 원천 출처·해시와 출력 경로 등 재현에 필요한 이력을 남김 |
| `src/profiling/render_profiles.py` | 렌더링되는 Markdown에서 `origin/` 경로 표시 | `data/00_origin/` 경로 표시 | 새 경로와 생성 문서 경로를 일치시킴 |
| `.env.example` | `CHICAGO_RAW_DIR=origin` | `CHICAGO_RAW_DIR=data/00_origin` | 새 기본 입력 위치를 팀 설정 예시에 반영 |
| `.gitignore` | `/origin/`, `/data/**` 등 기존 제외 규칙 | `/origin/` 규칙을 유지하고 새 `data/00_origin`~`03_gold` 경로도 명시적으로 제외; `.gitkeep` 예외 유지 | 원천·Parquet 및 생성 데이터를 Git 추적에서 제외하고 디렉터리 표시는 공유 가능하게 함 |
| `tests/bronze/test_load_bronze.py` | Bronze 값·기본 로그 검증 | 상세 JSONL의 파일명, 원천 SHA-256, 행 수, 성공 상태도 검증 | 적재 이력 추가가 실행에서 작동하는지 확인 |
| `README.md` | Origin 및 Bronze 출력의 옛 경로 | 새 입력·출력 경로, 데이터 폴더 역할, 실행 로그와 이 변경 기록 링크 | 팀원이 시작점에서 현재 구조와 작업 기록을 찾도록 함 |
| `AGENTS.md`, `docs/00_project_plan.md` | `origin/` 경로 안내 | `data/00_origin/` 안내 | 공용 작업 규칙과 프로젝트 계획의 경로 일치 |
| `docs/bronze.md` | 옛 Origin·Bronze 경로와 CSV 로그 설명 | 새 경로 및 JSONL 상세 로그 설명 추가 | Bronze 실행·로그 계약을 문서화 |
| `docs/team_share/bronze_pipeline_changelog.md` | 과거 경로로 표시 | 현재 경로로 표시 | 공유용 Bronze 경로 표기를 현재 폴더와 맞춤 |
| `metadata/source_profiles.md` | 측정값은 유지하고 옛 Origin 경로 표시 | 경로만 `data/00_origin/`으로 갱신 | 실제 결측률·중복·이상값 수치를 유지하면서 파일 위치만 반영 |
| `docs/team_share/data_directory_structure_changelog.md` | 없음 | 이번 작업 기록 신규 작성 | 변경 배경과 검증 결과를 팀에 공유 |

기존 설정·코드 외의 별도 `src/` 이동은 하지 않았다. Bronze와 Profiling 코드는 이미 각각 해당 `src/` 하위 폴더에 있었다.

## D. 데이터 복사 및 검증

복사 전 외부 감사 파일 `C:\mlo-03-p2-team2-directory-migration-20261120\before_files.json`에 22개 기존 파일의 상대 경로, 바이트 크기, SHA-256을 기록했다. 각 파일을 새 위치에 복사하고 원래 위치와 새 위치의 해시를 대조했다.

| 구분 | 파일 수 | 복사 크기 |
| --- | ---: | ---: |
| Origin | 14 | 881,334,035 bytes |
| Bronze (기존 `.gitkeep` 포함) | 4 | 170,602,417 bytes |
| Silver | 1 | 0 bytes |
| Gold | 3 | 0 bytes |
| **합계** | **22** | **1,051,936,452 bytes** |

22개 모두 원래 파일과 복사 파일의 바이트 크기 및 SHA-256이 일치했다. Bronze Parquet 원천 파일 3종도 새 위치에서 실제 읽기를 확인하고, 기존 Parquet과 행 수·열 수·Arrow 스키마가 일치하는 것을 확인했다.

| 데이터셋 | 원천 행 × 열 | Bronze 행 × 열 | 검증 |
| --- | ---: | ---: | --- |
| Food Inspections | 318,552 × 17 | 318,552 × 19 | 읽기 성공, 행 수와 스키마 일치 |
| Business Licenses | 1,212,132 × 37 | 1,212,132 × 39 | 읽기 성공, 행 수와 스키마 일치 |
| Community Areas | 77 × 11 | 77 × 13 | 읽기 성공, 행 수와 스키마 일치 |

Bronze의 추가 2개 컬럼은 `_SRC_FILE`(원천 파일명)과 `_LOAD_DTM`(UTC 적재 시각)이다. 복사 검증 동안 기존 `origin/`과 `data/bronze/`는 남겨 두었다. 학습용 미추적 파일 [`docs/learning/01_origin_bronze_profiling_guide.md`](../learning/01_origin_bronze_profiling_guide.md)과 [`reports/learning/data_pipeline_explorer.html`](../../reports/learning/data_pipeline_explorer.html)의 SHA-256도 각각 `D53026AABFAEBA324D8F9040A8ABCF46CD70C1DF63B8BE855A61E87990828FCC`, `329A1A647B1C0054EED359C5B1EA30565691CC370D7C9E2867E1C565FE61756A`로 기존 기록과 일치했다.

## E. Bronze 적재 로그

기존 [`logs/pipeline_runs.csv`](../../logs/pipeline_runs.csv)는 `PIPELINE_RUN_ID`, 계층, 대상, 원천 상대경로, 시작·종료 UTC 시각, 입력·출력 행 수, 상태를 기록한다. 확인 시 9개 실행 행이 있었고 마지막 실행은 2026-11-19T10:47:36Z에 끝난 Community Areas 77행 성공이었다. 기존 CSV는 이번 임시 실행에서 갱신되지 않았다.

새 코드는 상세 로그를 `RUN_LOG.parent / "bronze_run_details.jsonl"`에 덧붙인다. 기본 `RUN_LOG`가 프로젝트 `logs/pipeline_runs.csv`이므로 일반 실행의 경로는 `logs/bronze_run_details.jsonl`이다. 다만 이번 검증은 프로젝트 로그를 쓰지 않도록 `RUN_LOG`를 외부 임시 폴더로 지정했다. 실제로 생성한 파일은 `C:\mlo-03-p2-team2-directory-migration-20261120\verification_logs\bronze_run_details.jsonl`이며, 아래 세 건만 검증 실행 결과로 기록되어 있다.

| 항목 | 상세 JSONL 기록 여부 | 확인 내용 |
| --- | --- | --- |
| 실행 시각 | 있음 | `load_dtm`은 `2026-11-20T01:58:26Z` |
| 원천 파일명·경로·출처 | 있음 | 파일명, 절대 경로, manifest의 다운로드 URL |
| 출력 파일명·경로 | 있음 | 세부 데이터셋 Parquet 경로 |
| 처리 건수 | 있음 | 입력·출력 행 수 |
| 원천 SHA-256 | 있음 | 실행 때 원천 파일에서 계산 |
| 성공 여부 | 있음 | 각 레코드 `SUCCESS` |
| 오류 메시지 | 필드 있음 | 성공은 빈 문자열; 실패 시 예외 종류와 메시지를 기록하도록 구현 |

세 레코드는 같은 실행 ID `f8d69cb821d3482c9a79f9f6f6ce240f`를 사용하고, Bronze 출력은 감사 폴더 아래 임시 경로에 생성했다. 이 임시 실행은 원래 `logs/pipeline_runs.csv`나 새 경로의 기존 Parquet을 덮어쓰지 않았다. 프로젝트 내 `logs/bronze_run_details.jsonl`은 이번 작업 검증 실행으로 생성하지 않았다.

## F. 테스트 및 검증

| 검증 | 결과 | 실행·확인 방법 |
| --- | --- | --- |
| 전체 테스트 | **5 passed** | `python -m pytest -q --basetemp C:\mlo-03-p2-team2-directory-migration-20261120\pytest_final` |
| 테스트 첫 시도 | 준비 단계 오류 2건 | 기본 Windows pytest 임시 디렉터리 `C:\Users\Playdata\AppData\Local\Temp\pytest-of-Playdata` 접근이 거부됨. 외부 감사 폴더를 `--basetemp`로 지정해 재실행하여 해결 |
| Bronze 재적재 확인 | 성공, 3개 데이터셋 | 새 Origin을 입력으로 사용하고 출력·실행 로그를 외부 감사 폴더로 지정; 각 원천 행 수와 출력 행 수 일치 |
| Profiling 확인 | 성공 | 새 경로에서 실행; 출력 JSON은 외부 임시 경로에 기록. 기존 `sources` 및 `joins` 측정값과 동일함을 확인 |
| 프로파일 Markdown 생성 확인 | 성공 | 렌더 결과를 외부 임시 폴더에 기록하고 새 `data/00_origin/` 경로 포함 확인 |
| 데이터 SHA-256 | **22개 모두 일치** | 복사 전 감사 manifest와 기존·신규 파일의 크기 및 SHA-256 비교 |
| Git 검사 | 통과 | `git diff --check`; 원천·Parquet 파일은 Git 추적 목록에 없음. `.gitignore` 규칙으로 새 데이터 경로 제외 확인 |

## G. 미완료 사항 및 다음 작업

- **기존 경로 정리 보류:** 새 위치에서 실행 검증을 마쳤지만, 기존 경로 삭제는 이번 작업 범위가 아니다. 팀원 환경과 설정도 새 경로로 전환됐는지 확인한 후, 별도 백업과 해시를 대조하고 정리해야 한다.
- **팀원 경로 설정 확인:** 로컬 `.env`의 `CHICAGO_RAW_DIR`가 설정된 팀원은 새 위치 `data/00_origin`을 가리키는지 확인한다. `config/sources.example.yaml`의 상대 파일 경로는 데이터셋 폴더 내부 기준이므로 이번 구조 변경에서는 바꾸지 않았다.
- **Silver 구현 준비:** 팀 공통 표준 정의와 품질 규칙을 합의하고, `src/silver/` 및 `data/02_silver/`를 사용할 때 원천 행 추적, rejected 처리, 입출력 행 수 검증을 함께 설계한다. 이번 작업에서 Silver 데이터·파이프라인은 생성하지 않았다.
- **Gold 연계:** Gold의 grain과 연결 키를 합의한 뒤 `data/03_gold/`을 사용한다. `ai_ready/`와 `quarantine/`은 후속 단계용으로 유지한다.
- **README:** 데이터 구조·폴더 역할, 로그 위치, 이 공유 변경 기록 링크를 추가했다. 일반 실행의 세부 JSONL 기본 위치는 `logs/bronze_run_details.jsonl`이며, 상세 항목은 [Bronze 안내](../bronze.md)에도 있다.
- **작업 기록 원칙:** 이후 코드·데이터·설정 변경도 작업 전 상태, 목적, 파일별 diff, 실행 명령과 결과, 데이터 검증, 오류·해결, 미해결 및 팀 합의 사항을 팀 공유 Markdown에 누적한다. 기존 기록과 실행 로그는 덮어쓰거나 소급 생성하지 않는다.

이번 변경은 아직 커밋하지 않았다. 현재 브랜치와 작업 트리를 유지하고 있다.
