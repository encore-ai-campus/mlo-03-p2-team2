# 04 사업체 인허가 · 공유 보고서

2026-11-20에 다시 실행한 팀 공용본의 결과입니다. 위생점검 **318,627행**, 인허가 **1,212,132행**으로 검증 39개를 모두 통과했습니다. 공유 보고서는 `reports/runs/04_license/`에서 생성된 파일입니다. [원천과 Bronze 체크섬](../../metadata/lineage/04_license/bronze_manifest.json)

| 단계 | 공유 결과 |
| --- | --- |
| Bronze | [원천과 적재 검증 7/7](validation_bronze.csv) |
| Silver | [표준 스키마와 행 추적 검증 6/6](validation_silver.csv) |
| 품질 검사 | [품질 관리 MD](품질%20관리.md) · [규칙별 전후 비교 CSV](quality_comparison.csv) · [보고서 검증 3/3](validation_quality.csv) |
| Gold | [키·기간 매칭·Silver 대비 사실 검증 23/23](validation_gold.csv) |
| 체크섬 | [Git 원천 파일 SHA-256](../../data/00_origin/SHA256SUMS) · [04번 Parquet SHA-256](parquet_sha256sums.txt) |

[기존 318,552행 대비 매칭 건수 비교](match_comparison.md) · [04번 통합 문서와 실행 방법](../../docs/domains/04_license.md) · [컬럼 변환 목록](../../metadata/lineage/04_license/column_lineage.csv)
