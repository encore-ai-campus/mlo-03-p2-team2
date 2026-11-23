# 02 위반유형 05 공유 샘플 검증

작업 워크트리 `C:\mlo-03-p2-team2`, 브랜치 `codex/domain-02-sharing-ai-ready`. 기준 커밋 `be744f2`.

팀 원천 한 스냅샷의 전체 행으로 만든 로컬 검토용 샘플이다. 02 실행 `lineage-pl6vwsd7`의 정상·격리 Silver를 사용했고, 같은 원천으로 별도 생성한 01 Silver의 매니페스트와 SHA-256을 대조했다. 02 상세의 모든 정상·격리 조각에서 점검 키와 원천 행 번호가 01 Silver에 일치했다. 원천 점검 CSV의 SHA-256은 `b43beb7fae834a8698ca162004caf2929cb2eca7ff75c27b4db6bf07aa103c98`이다.

샘플 경로는 `reports/runs/02_violation/sharing-ai-ready/sample-05/`다. 05가 이 폴더를 `--shared-violations-dir`로 바로 읽을 수 있도록 현재 소비 코드의 파일명을 사용했다. 최종 배포 경로와 `02_` 접두사 적용 방식은 [공유 스키마 초안](team_integration_schema_draft.md)에 따라 합의한다.

| 파일 | 한 행의 의미 | 행 수 |
| --- | --- | ---: |
| `inspection_violation_codes.parquet` | 점검·코드 체계 버전·승인 코드 조합 1건 | 963,709 |
| `inspection_violation_observations.parquet` | 원천 점검의 위반 관측 상태 1건 | 318,627 |

- 두 파일의 키 중복과 코드의 고아 참조가 각각 0건이다. 날짜로 코드 체계 버전을 정할 수 없어 제외한 승인 코드는 0건이다. 2018-07-01 전 515,018행, 당일부터 448,691행이다.
- 관측 상태는 `parsed` 227,423건, `partial` 998건, `raw_missing` 90,022건, `unrecognized` 184건이다. 합계는 01 Silver 및 02 Bronze의 318,627건과 같다.
- 02 Silver 조각 1,031,073건은 정상 1,029,281건과 격리 1,792건으로 대사됐다. 샘플은 정상 조각만 사용하고 같은 점검·버전·코드를 한 건으로 센다.
- 05 자체 파서에서 나온 코드 조합과 대조한 결과, 샘플의 모든 조합이 05 후보에 있었다. 05 후보에만 있는 조합은 1,697개다. 코멘트 경계 등 승인 기준을 합의할 때 이 차이를 확인한다.
- 같은 입력으로 다시 생성한 두 Parquet와 검증 기록의 SHA-256이 첫 실행과 모두 일치했다. 파일별 행 수와 체크섬, 입력 지문은 샘플 폴더의 `verification.json`에 있다.

05 Gold에 01 Silver와 02 샘플을 연결해 실제 집계 생성과 `verify`를 통과했다. Windows에서 05의 임시 폴더를 이동하기 전에 Parquet 읽기 핸들을 닫도록 검증 프로세스에서만 보완했다. 05 소스와 집계 규칙은 변경하지 않았다.

## 03 기존 입력 확인

03의 기존 실행 명령과 기존 03 점검 Silver를 그대로 사용해, 02의 정상·격리 상세 Parquet와 대사 JSON을 다시 읽었다. 점검 이력 Parquet, 재점검·반복 위반 mart 두 파일, HTML 보고서까지 네 파일의 SHA-256이 이전 검증 산출물과 모두 일치했다. 기존 02·03 테스트 27개가 통과했다.

## 샘플 재실행

저장소 루트에서 실행한다. 01 입력은 기존 01 파이프라인으로 동일 원천에서 만든 Silver와 매니페스트가 함께 있는 실행 루트를 지정한다. 출력 폴더는 새 경로를 지정한다.

```powershell
$run = 'reports/runs/02_violation/sharing-ai-ready'
python -m src.domains.02_violation.export_shared_sample `
  --domain02-root reports/runs/02_violation/lineage-pl6vwsd7 `
  --domain01-root "$run/check-01" `
  --output-dir "$run/sample-05-new"
```
