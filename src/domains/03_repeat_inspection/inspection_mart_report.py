from collections import Counter
from html import escape
from statistics import median

import pyarrow.parquet as pq


STATUS_LABELS = {
    "matched": "관측 종료일까지 연결",
    "not_observed": "관측 종료일까지 미관측",
    "ambiguous_same_day": "같은 날 후보가 있어 미확정",
    "missing_license": "면허번호 없음",
    "missing_date": "점검일 없음",
    "insufficient_observation": "관측 기간 30일 미만·미관측",
}
WINDOW_LABELS = {"within_30_days": "1–30일", "after_30_days": "31일 이후"}


def bar_chart(rows):
    entries = []
    for label, value, scale, display in rows:
        width = 100 * value / scale if scale else 0
        entries.append(
            f'<li><span>{escape(label)}</span><span class="track" aria-hidden="true">'
            f'<span class="bar" style="width:{width:.3f}%"></span>'
            f'</span><strong>{escape(display)}</strong></li>'
        )
    return '<ul class="chart">' + "".join(entries) + "</ul>"


def build_report(repeat_path, reinspection_path, parse_counts, observation_end):
    repeat_counts = Counter()
    comparison_counts = Counter()
    repeat = pq.ParquetFile(repeat_path)
    for batch in repeat.iter_batches(columns=["violation_cd", "repeat_flag", "comparison_status_cd"]):
        for row in batch.to_pylist():
            comparison_counts[row["comparison_status_cd"]] += 1
            if row["repeat_flag"] is not None:
                repeat_counts[row["violation_cd"], row["repeat_flag"]] += 1
    code_totals = {
        code: repeat_counts[code, True] + repeat_counts[code, False]
        for code, _ in repeat_counts
    }
    top_codes = sorted(code_totals, key=lambda code: (-code_totals[code], code))[:10]
    repeat_chart = bar_chart(
        (f"위반 {code}번", repeat_counts[code, True], code_totals[code],
         f"{repeat_counts[code, True] / code_totals[code]:.1%} ({repeat_counts[code, True]:,}/{code_totals[code]:,})")
        for code in top_codes
    )
    eligible = comparison_counts["comparable"]
    repeated = sum(count for (_, flag), count in repeat_counts.items() if flag)
    repeat_rate = f"{repeated / eligible:.1%}" if eligible else "—"

    reinspections = pq.read_table(reinspection_path, columns=[
        "reinspection_match_status_cd", "reinspection_window_cd", "followup_result_cd", "days_to_followup_num",
    ]).to_pylist()
    statuses = Counter(row["reinspection_match_status_cd"] for row in reinspections)
    matched = [row for row in reinspections if row["reinspection_match_status_cd"] == "matched"]
    outcomes = Counter(row["followup_result_cd"] or "결과 미상" for row in matched)
    delays = [row["days_to_followup_num"] for row in matched]
    passed = outcomes["PASS"]
    pass_rate = f"{passed / len(matched):.1%}" if matched else "—"
    delay_median = f"{median(delays):g}일" if delays else "—"
    outcome_chart = bar_chart(
        (f"FAIL → {label}", count, len(matched), f"{count / len(matched):.1%} ({count:,}건)")
        for label, count in outcomes.most_common()
    )
    window_rows = []
    for window, label in WINDOW_LABELS.items():
        window_results = Counter(
            row["followup_result_cd"] for row in matched if row["reinspection_window_cd"] == window
        )
        total = window_results.total()
        pass_cells = []
        for result in ("PASS", "PASS W/ CONDITIONS"):
            count = window_results[result]
            pass_cells.append(f"<td>{count:,}건 ({count / total:.1%})</td>" if total else "<td>—</td>")
        window_rows.append(f"<tr><th scope='row'>{label}</th><td>{total:,}</td>{''.join(pass_cells)}</tr>")
    window_table = "".join(window_rows)
    delay_buckets = (
        ("1–7일", 1, 7), ("8–14일", 8, 14), ("15–21일", 15, 21),
        ("22–30일", 22, 30), ("31–60일", 31, 60), ("61–90일", 61, 90),
        ("91일 이상", 91, None),
    )
    delay_chart = bar_chart(
        (label, count, len(matched), f"{count:,}건")
        for label, start, end in delay_buckets
        for count in [sum(days >= start and (end is None or days <= end) for days in delays)]
    )
    status_rows = "".join(
        f"<tr><th scope='row'>{escape(STATUS_LABELS[status])}</th><td>{count:,}</td></tr>"
        for status, count in statuses.most_common()
    )
    return f"""<!doctype html>
<html lang="ko">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>시카고 식품 위생 점검 분석</title>
<style>
  :root {{ color-scheme: light dark; --accent: light-dark(#146b67, #63d3c4); }}
  * {{ box-sizing: border-box; }}
  body {{ margin: auto; max-width: 900px; padding: 2rem 1.25rem; font: 16px/1.55 system-ui,sans-serif; }}
  h1 {{ font-size: clamp(1.6rem, 5vw, 2.5rem); line-height: 1.2; margin-bottom: .5rem; }}
  h2 {{ margin: 0 0 .5rem; }}
  h3 {{ margin: 1.6rem 0 .5rem; }}
  section {{ border-top: 1px solid color-mix(in srgb, currentColor 23%, transparent); margin-top: 2rem; padding-top: 1.5rem; }}
  .chart {{ list-style: none; padding: 0; display: grid; gap: .5rem; }}
  .chart li {{ display: grid; grid-template-columns: minmax(9rem, 1fr) minmax(4rem, 2fr) minmax(9rem, auto); gap: .75rem; align-items: center; }}
  .track {{ display: block; height: .6rem; background: color-mix(in srgb, currentColor 14%, transparent); }}
  .bar {{ display: block; height: 100%; background: var(--accent); }}
  strong, td {{ font-variant-numeric: tabular-nums; }}
  table {{ border-collapse: collapse; width: 100%; max-width: 45rem; }}
  th, td {{ padding: .3rem .6rem; border-bottom: 1px solid color-mix(in srgb, currentColor 20%, transparent); text-align: start; }}
  td {{ text-align: end; }}
  @media (max-width: 520px) {{
    .chart li {{ grid-template-columns: 1fr auto; gap: .2rem .5rem; }}
    .chart strong {{ grid-column: 2; grid-row: 1; }}
    .track {{ grid-column: 1 / -1; }}
  }}
</style>
<main>
<h1>시카고 식품 위생 점검 분석</h1>
<p>로컬 점검 데이터 · 관측 종료일 {observation_end.isoformat()}</p>
<section aria-labelledby="reinspection">
<h2 id="reinspection">불합격 후 첫 재검사</h2>
<p>FAIL {len(reinspections):,}건 중 {len(matched):,}건을 연결했어요. 연결된 점검 중 <strong>FAIL → PASS {pass_rate}</strong> ({passed:,}건), 첫 재검사까지 중앙값은 <strong>{delay_median}</strong>이에요.</p>
<p>같은 면허번호의 직전 FAIL에 점검 유형상 재검사인 건을 연결했어요. 관측 종료일까지 첫 재검사를 찾고, 같은 날 순서가 모호한 경우는 미확정으로 집계했어요.</p>
<h3>첫 재검사 시점별 통과 결과</h3>
<table><thead><tr><th scope="col">시점</th><th scope="col">연결 건수</th><th scope="col">일반 통과</th><th scope="col">조건부 통과</th></tr></thead><tbody>{window_table}</tbody></table>
<p>비율의 분모는 각 시점 구간에 연결된 첫 재검사 건수예요.</p>
<h3>첫 재검사 결과</h3>
{outcome_chart}
<h3>재검사까지 걸린 일수</h3>
{delay_chart}
<h3>불합격 점검의 연결 상태</h3>
<table><thead><tr><th scope="col">상태</th><th scope="col">건수</th></tr></thead><tbody>{status_rows}</tbody></table>
<p>연결 상태는 최초 불합격 점검마다 같은 면허번호의 첫 재검사 방문을 찾았는지, 찾지 못했다면 이유가 무엇인지 보여줘요. 전체 불합격 {len(reinspections):,}건 중 {len(matched):,}건을 연결했고, {len(reinspections) - len(matched):,}건은 연결되지 않았어요.</p>
<ul>
  <li><strong>미관측</strong>은 데이터의 관측 종료일까지 해당 불합격 건에 연결할 재검사가 없었던 경우예요.</li>
  <li><strong>같은 날 후보가 있어 미확정</strong>은 기록에 날짜만 있어서 여러 후보 중 순서를 정할 수 없었던 경우예요.</li>
  <li><strong>면허번호 또는 점검일 없음</strong>은 같은 영업면허의 후속 방문을 찾거나 날짜 순서를 확인할 정보가 부족했던 경우예요.</li>
  <li><strong>관측 기간 30일 미만·미관측</strong>은 불합격부터 관측 종료일까지 30일도 지나지 않았고, 그 사이 재검사가 기록되지 않은 경우예요.</li>
</ul>
<p>예를 들어 같은 면허번호에서 1월 10일과 20일에 각각 불합격하고 25일에 재검사를 받았다면, 25일 재검사는 가장 최근 불합격인 20일 건에 연결해요. 10일 건은 미관측으로 남을 수 있어요.</p>
</section>
<section aria-labelledby="repeat">
<h2 id="repeat">같은 위반 코드의 재관측</h2>
<p>비교 가능한 기준 점검·위반 코드 <strong>{eligible:,}건</strong> 중 <strong>{repeated:,}건 ({repeat_rate})</strong>이 다음 점검에서도 관측됐어요.</p>
<p>2018-07-01 이후 같은 면허번호의 연속 점검을 비교했어요. 양쪽 위반 원문이 모두 파싱된 경우만 재관측률 분모에 넣었어요.</p>
<h3>비교 건수가 많은 위반 코드 10개</h3>
{repeat_chart}
<p>반복 위반 Mart에서 후속 점검·파싱 조건 등으로 비교할 수 없었던 위반 코드 행은 {repeat.metadata.num_rows - eligible:,}건이에요. 분석 대상 점검 중 위반 원문 공란은 {parse_counts['missing']:,}건, 일부 또는 전체 파싱 실패는 {parse_counts['partial'] + parse_counts['unparsed']:,}건이에요.</p>
</section>
</main>
</html>
"""
