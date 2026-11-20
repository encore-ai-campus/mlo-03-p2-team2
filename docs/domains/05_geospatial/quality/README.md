# 품질 검사 · 원천과 변환 결과 대조

공용 점검 318,627건과 경계 77개를 기준으로 원천 값, 순번, 표준화 결과와 공간 배정을 확인합니다. Gold와 AI-ready는 입력 지문, 집계 단위와 지표 분모를 각각 대조합니다.

| 검증 범위 | 확인 내용 |
| --- | --- |
| Origin → Bronze | 파일 SHA-256, 논리 행 수, 셀 값, 원천 순번과 매니페스트 |
| Bronze → Silver | 점검 ID·지역 번호 유일성, 컬럼 타입과 변환 값, 품질 사유 |
| 지역 배정 | 좌표 유효성, 단일 지역·공란·경계 밖·다중 후보, 경계 버전 |
| 위반 파싱 | 원문과 토큰 대조, 파싱 상태, 점검·절차 구간·코드의 고유성 |
| Gold·AI-ready | 월·연도별 전체 점검과 평가 완료 건수, 위반 코드 건수 및 분모, 산출물 키와 스키마 |

공용 원천을 사용한 독립 검증에서 단일 지역 배정 317,238건, 좌표 공란 1,065건, 경계 밖 324건을 확인했습니다. 비정상 좌표 및 복수 경계는 0건입니다. GeoJSON과 로컬 WKT를 지역 번호로 대조한 결과 도형이 다른 지역과 배정·후보 변경은 각각 0건이었습니다. 로컬 WKT의 원래 좌표계는 별도 증빙이 필요합니다. [원천별 체크섬과 검증 수치](../../../../reports/05_geospatial/README.md)

| Silver 품질 사유 | 건수 |
| --- | ---: |
| 점검 CSV 면허번호 특수값 `0` 또는 `9999999` | 841 |
| 점검 CSV 면허번호 공란 | 19 |
| 위험 등급 `ALL` 검토 | 90 |
| 위험 등급 공란 | 88 |

한 점검에 여러 사유가 기록될 수 있습니다. 사유 1,038건이 점검 997행에 해당합니다. [독립 검증 코드](../../../../src/domains/05_geospatial/audit_geographic_silver.py)

## 검증 실행

[통합 실행](../../05_geospatial.md#실행)에 사용한 셸에서 아래 명령을 실행합니다. 팀 Gold와 AI-ready를 생성한 경우에는 구축과 같은 01·02 입력 경로와 Gold 릴리스를 사용합니다.

```bash
python "$domain/geographic_medallion.py" verify
python "$domain/geographic_gold.py" verify --silver-dir "$silver_dir" \
  --inspection-silver "$inspection_silver" --shared-violations-dir "$violations_dir"
python "$domain/geographic_ai_ready.py" verify --gold-dir "$gold_dir"
```

원천·Bronze·Silver를 독립 대조합니다. 로컬 WKT를 같이 비교하는 경우에는 `--compare-wkt origin/05_geospatial/export.csv`를 추가합니다.

```bash
mkdir -p reports/runs/05_geospatial
python "$domain/audit_geographic_silver.py" --bronze-dir "$bronze_dir" --silver-dir "$silver_dir" \
  > reports/runs/05_geospatial/team_audit.json

python -m unittest discover -s tests/domains/05_geospatial -v
```

로컬 비교 배치의 독립 검증에는 해당 Bronze·Silver 출력 경로와 `--source-dir origin/05_geospatial`을 함께 전달합니다.
