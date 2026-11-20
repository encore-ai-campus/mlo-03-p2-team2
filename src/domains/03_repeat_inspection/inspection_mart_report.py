from collections import Counter
from html import escape
import re
from statistics import median

import pyarrow.parquet as pq


STATUS_LABELS = {
    "matched": "1–30일 이내 연결",
    "not_observed": "30일 이내 연결 미관측",
    "ambiguous_same_day": "같은 날 후보가 있어 미확정",
    "missing_license": "면허번호 없음",
    "missing_date": "점검일 없음",
    "insufficient_observation": "관측 기간 30일 미만·미관측",
}
COMPARISON_STATUS_DETAILS = {
    "no_followup": (
        "다음 비교 대상 점검 기록 없음",
        "같은 면허번호에서 기준 점검보다 늦은 비교 대상 점검이 기록되지 않은 경우",
    ),
    "followup_violations_unconfirmed": (
        "다음 점검의 위반 원문 공란 또는 파싱 미확정",
        "다음 점검은 연결됐으나 위반 내용이 비어 있거나 코드를 모두 읽을 수 없어 재관측 여부를 확인하지 못한 경우",
    ),
    "ambiguous_same_day": (
        "같은 날짜에 복수 점검이 있어 비교 대상 미확정",
        "기준일 또는 다음 비교 대상 날짜에 같은 면허번호의 점검이 여러 건 있어 날짜만으로 비교할 쌍을 정할 수 없는 경우",
    ),
    "base_violations_unconfirmed": (
        "기준 점검의 위반 원문 파싱 미확정",
        "기준 점검의 위반 코드 일부는 읽었으나 원문 전체를 해석하지 못해 비교에서 제외한 경우",
    ),
}


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


def violation_code_order(code):
    text = str(code)
    prefix = re.match(r"[0-9]+", text)
    return (int(prefix[0]), text) if prefix else (float("inf"), text)


def comparison_table(baseline, eligible, repeated):
    baseline_eligible, baseline_repeated = baseline
    rows = (
        ("비교 가능 코드 행", f"{baseline_eligible:,}", f"{eligible:,}"),
        ("재관측 코드 행", f"{baseline_repeated:,}", f"{repeated:,}"),
        (
            "재관측률",
            f"{baseline_repeated / baseline_eligible:.1%}" if baseline_eligible else "—",
            f"{repeated / eligible:.1%}" if eligible else "—",
        ),
    )
    cells = "".join(
        f'<tr><th scope="row">{label}</th><td>{previous}</td><td>{current}</td></tr>'
        for label, previous, current in rows
    )
    return f"""<h3 id="rule-comparison">위반 처리 기준 적용 전후</h3>
<table aria-labelledby="rule-comparison">
  <thead><tr><th scope="col">지표</th><th scope="col">기존 03번 파서</th><th scope="col">02번 산출물 적용</th></tr></thead>
  <tbody>{cells}</tbody>
</table>
<p>같은 점검 Silver에 두 위반 처리 방식을 적용했습니다. 02번에서 격리된 위반 조각이 있는 점검은 재관측 여부를 확정할 수 없는 점검으로 처리했습니다.</p>"""


def build_report(repeat_path, reinspection_path, observation_end, *, baseline=None):
    repeat_counts = Counter()
    comparison_counts = Counter()
    repeat = pq.ParquetFile(repeat_path)
    metadata = repeat.schema_arrow.metadata or {}
    inspection_source = "01번 점검 Silver" if b"inspection_silver_sha256" in metadata else "03번 로컬 점검 Silver"
    for batch in repeat.iter_batches(columns=["violation_cd", "repeat_flag", "comparison_status_cd"]):
        for row in batch.to_pylist():
            comparison_counts[row["comparison_status_cd"]] += 1
            if row["repeat_flag"] is not None:
                repeat_counts[row["violation_cd"], row["repeat_flag"]] += 1
    code_totals = {
        code: repeat_counts[code, True] + repeat_counts[code, False]
        for code, _ in repeat_counts
    }
    top_codes = sorted(code_totals, key=lambda code: (-code_totals[code], violation_code_order(code)))[:10]
    repeat_chart = bar_chart(
        (f"위반 {code}번", repeat_counts[code, True], code_totals[code],
         f"{repeat_counts[code, True] / code_totals[code]:.1%} ({repeat_counts[code, True]:,}/{code_totals[code]:,})")
        for code in top_codes
    )
    eligible = comparison_counts["comparable"]
    repeated = sum(count for (_, flag), count in repeat_counts.items() if flag)
    repeat_rate = f"{repeated / eligible:.1%}" if eligible else "—"
    rule_comparison = comparison_table(baseline, eligible, repeated) if baseline is not None else ""
    excluded_rows = []
    excluded_details = []
    for status, count in comparison_counts.most_common():
        if status == "comparable":
            continue
        label, detail = COMPARISON_STATUS_DETAILS[status]
        excluded_rows.append(f"<tr><th scope='row'>{escape(label)}</th><td>{count:,}</td></tr>")
        excluded_details.append(f"  <li><strong>{escape(label)}</strong> · {escape(detail)}</li>")
    excluded_explanations = (
        "<ul>\n" + "\n".join(excluded_details) + "\n</ul>" if excluded_details else ""
    )
    excluded_total = repeat.metadata.num_rows - eligible

    reinspections = pq.read_table(reinspection_path, columns=[
        "reinspection_match_status_cd", "followup_result_cd", "days_to_followup_num",
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
    delay_buckets = (
        ("1–7일", 1, 7), ("8–14일", 8, 14), ("15–21일", 15, 21), ("22–30일", 22, 30),
    )
    delay_chart = bar_chart(
        (label, count, len(matched), f"{count:,}건")
        for label, start, end in delay_buckets
        for count in [sum(start <= days <= end for days in delays)]
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
<p>{inspection_source} · 관측 종료일 {observation_end.isoformat()}</p>
<section aria-labelledby="reinspection">
<h2 id="reinspection">불합격 후 30일 이내 첫 재검사</h2>
<p>불합격 {len(reinspections):,}건 중 {len(matched):,}건을 연결했습니다. 연결 건 중 <strong>FAIL → PASS {pass_rate}</strong> ({passed:,}건)이며, 첫 재검사까지 걸린 기간의 중앙값은 <strong>{delay_median}</strong>입니다.</p>
<p>같은 면허번호의 가장 최근 불합격일로부터 1–30일 사이에 관측된 첫 재검사를 연결했습니다. 같은 날 순서가 모호한 건은 미확정으로 집계했습니다.</p>
<h3>첫 재검사 결과</h3>
{outcome_chart}
<h3>재검사까지 걸린 일수</h3>
{delay_chart}
<h3>불합격 점검의 연결 상태</h3>
<table><thead><tr><th scope="col">상태</th><th scope="col">건수</th></tr></thead><tbody>{status_rows}</tbody></table>
<p>30일 이내 재검사 미연결 {len(reinspections) - len(matched):,}건</p>
<ul>
  <li><strong>30일 이내 연결 미관측</strong> · 30일을 모두 관측했으나 연결할 재검사 기록 없음</li>
  <li><strong>같은 날 후보가 있어 미확정</strong> · 날짜만으로 여러 후보의 순서를 판단하기 어려운 경우</li>
  <li><strong>면허번호 또는 점검일 없음</strong> · 후속 방문이나 날짜 순서를 확인할 정보 부족</li>
  <li><strong>관측 기간 30일 미만·미관측</strong> · 관측 종료일까지 30일 미만이며 그 사이 연결할 재검사 기록 없음</li>
</ul>
<p>같은 면허번호에서 1월 10일과 20일에 각각 불합격하고 25일에 재검사를 받았다면, 25일 재검사는 가장 최근 불합격인 20일 건에 연결합니다. 10일 건은 미관측으로 남을 수 있습니다.</p>
</section>
<section aria-labelledby="repeat">
<h2 id="repeat">같은 위반 코드의 재관측</h2>
<p>기준 점검의 위반 코드 <strong>{eligible:,}건</strong>은 모두 다음 점검 기록과 비교할 수 있었습니다. 그중 <strong>{repeated:,}건 ({repeat_rate})</strong>에서 같은 위반 코드가 다시 나왔고, 나머지 <strong>{eligible - repeated:,}건</strong>에서는 같은 코드가 나오지 않았습니다.</p>
<p>2018-07-01 이후 같은 면허번호의 비교 대상 점검을 날짜순으로 비교했습니다. 기준 점검과 다음 점검의 위반 원문이 모두 파싱된 경우를 재관측률의 분모에 포함했습니다.</p>
{rule_comparison}
<h3>비교 건수가 많은 위반 코드 10개</h3>
<p>정렬 기준은 비교 가능 건수 내림차순이며, 동률이면 위반 코드 번호 오름차순입니다. 막대는 비교 가능 건수 중 같은 위반 코드가 다음 점검에서도 관측된 비율입니다.</p>
{repeat_chart}
<h3 id="comparison-exclusions">위반 코드 비교 불가 사유</h3>
<table aria-labelledby="comparison-exclusions">
  <thead><tr><th scope="col">사유</th><th scope="col">위반 코드 행 수</th></tr></thead>
  <tbody>{"".join(excluded_rows)}</tbody>
  <tfoot><tr><th scope="row">합계</th><td>{excluded_total:,}</td></tr></tfoot>
</table>
{excluded_explanations}
<p>기준 점검에 위반 코드가 3개 있고 다음 점검의 위반 원문이 공란이면, 비교 불가는 위반 코드 3행으로 집계합니다.</p>
</section>
</main>
</html>
"""
