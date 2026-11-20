from argparse import ArgumentParser
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from profile_datasets import DATA_DIR, DATASETS, DATE_COLUMNS, THOUSANDS_COLUMNS, select_dataset


@dataclass(frozen=True)
class QualityRules:
    identifiers: tuple[str, ...]
    categories: tuple[str, ...]
    nonnegative_integers: tuple[str, ...] = ()
    nonnegative_numbers: tuple[str, ...] = ()
    coordinates: tuple[str, str] | None = None
    term: tuple[str, str] | None = None


RULES = {
    "food_inspections": QualityRules(
        identifiers=("Inspection ID",),
        categories=("Facility Type", "Risk", "City", "State", "Inspection Type", "Results"),
        nonnegative_integers=("Inspection ID", "License #"),
        coordinates=("Latitude", "Longitude"),
    ),
    "business_licenses": QualityRules(
        identifiers=("ID", "LICENSE ID"),
        categories=(
            "STATE", "WARD", "COMMUNITY AREA", "LICENSE CODE", "LICENSE DESCRIPTION",
            "APPLICATION TYPE", "CONDITIONAL APPROVAL", "LICENSE STATUS",
        ),
        nonnegative_integers=(
            "LICENSE ID", "LICENSE NUMBER", "ACCOUNT NUMBER", "SITE NUMBER",
            "WARD", "PRECINCT", "POLICE DISTRICT", "COMMUNITY AREA", "LICENSE CODE", "SSA",
        ),
        coordinates=("LATITUDE", "LONGITUDE"),
        term=("LICENSE TERM START DATE", "LICENSE TERM EXPIRATION DATE"),
    ),
    "community_areas": QualityRules(
        identifiers=("AREA_NUMBE", "AREA_NUM_1"),
        categories=("COMMUNITY",),
        nonnegative_integers=("AREA_NUMBE", "AREA_NUM_1"),
        nonnegative_numbers=("SHAPE_AREA", "SHAPE_LEN"),
    ),
}


def null_tokens(values: pd.Series) -> pd.Series:
    return values.isna() | values.str.fullmatch(r"(?i:NULL)", na=False)


def present_values(raw: pd.Series) -> pd.Series:
    values = raw.str.strip()
    return values[~null_tokens(values) & values.ne("")]


def examples(values: pd.Series) -> str:
    return ", ".join(repr(value[:60]) for value in values.drop_duplicates().head(3)) or "–"


def report_missing(df: pd.DataFrame) -> None:
    print("\n[결측값] NULL 표기와 빈 문자열·공백을 별도로 집계")
    rows = []
    for column, raw in df.items():
        values = raw.str.strip()
        null_count = int(null_tokens(values).sum())
        blank_count = int(values.eq("").sum())
        total = len(values)
        rows.append({
            "column": column,
            "null_count": null_count,
            "null_pct": round(100 * null_count / total, 2) if total else 0,
            "blank_count": blank_count,
            "blank_pct": round(100 * blank_count / total, 2) if total else 0,
        })
    print(pd.DataFrame(rows).to_string(index=False))


def report_duplicates(df: pd.DataFrame, identifiers: tuple[str, ...]) -> None:
    print("\n[중복값] 첫 행을 제외한 초과 중복 건수")
    print(f"전체 행 중복: {df.duplicated().sum():,}건")
    for column in identifiers:
        ids = present_values(df[column])
        repeated = ids[ids.duplicated()]
        print(f"{column}: 초과 {len(repeated):,}건, 중복 ID {repeated.nunique():,}개, 예시 {examples(repeated)}")


def report_categories(df: pd.DataFrame, columns: tuple[str, ...], top: int) -> None:
    print("\n[범주형 고유값과 빈도] 비율은 결측·빈값을 제외한 건수 기준")
    for column in columns:
        values = present_values(df[column])
        counts = values.value_counts()
        shown = counts.head(top) if top else counts
        table = shown.rename_axis("value").reset_index(name="count")
        table["pct"] = (100 * table["count"] / len(values)).round(2)
        print(f"\n{column}: {len(counts):,}종, 유효 값 {len(values):,}건")
        if not table.empty:
            print(table.to_string(index=False, max_colwidth=64))
        if len(shown) < len(counts):
            print(f"나머지 {len(counts) - len(shown):,}종, {len(values) - shown.sum():,}건")


def report_dates(
    df: pd.DataFrame, snapshot_date: pd.Timestamp | None, term: tuple[str, str] | None
) -> None:
    print("\n[날짜 범위와 변환 유효성] MM/DD/YYYY 기준")
    date_columns = [column for column in df if column.upper() in DATE_COLUMNS]
    if not date_columns:
        print("점검 대상 날짜 컬럼 없음")
        return

    rows = []
    term_dates = {}
    for column in date_columns:
        values = present_values(df[column])
        dates = pd.to_datetime(values, format="%m/%d/%Y", errors="coerce")
        invalid = dates.isna()
        future = "–"
        if term and column in term:
            term_dates[column] = dates
        elif snapshot_date is not None:
            future = int(dates.gt(snapshot_date).sum())
        rows.append({
            "column": column,
            "first": str(dates.min().date()) if dates.notna().any() else "–",
            "last": str(dates.max().date()) if dates.notna().any() else "–",
            "invalid_date": int(invalid.sum()),
            "after_snapshot": future,
            "invalid_examples": examples(values[invalid]),
        })
    print(pd.DataFrame(rows).to_string(index=False))
    if snapshot_date is not None:
        print(f"기준일: {snapshot_date.date()} (원본 파일명 날짜)")
    if term:
        period = pd.DataFrame(term_dates).dropna()
        start, end = term
        reversed_terms = period[start].gt(period[end]).sum()
        print(f"시작일이 만료일보다 늦음: {reversed_terms:,}건 (두 날짜가 유효한 {len(period):,}건 중)")


def report_numbers(df: pd.DataFrame, rules: QualityRules) -> None:
    print("\n[숫자 변환 유효성 및 이상값]")
    labels = {column: "정수" for column in rules.nonnegative_integers}
    labels.update({column: "숫자" for column in rules.nonnegative_numbers})
    coordinate_bounds = dict(zip(rules.coordinates or (), (90, 180)))
    labels.update({column: "좌표" for column in coordinate_bounds})

    rows = []
    for column, label in labels.items():
        values = present_values(df[column])
        numeric_text = values
        if column in THOUSANDS_COLUMNS:
            grouped = values.str.fullmatch(r"[+-]?[0-9]{1,3}(?:,[0-9]{3})+(?:\.[0-9]+)?")
            numeric_text = values.mask(grouped, values.str.replace(",", "", regex=False))

        numbers = pd.to_numeric(numeric_text, errors="coerce")
        valid = numbers.notna() & numbers.abs().ne(float("inf"))
        if label == "정수":
            valid &= numbers.mod(1).eq(0)
        usable = numbers[valid]
        bound = coordinate_bounds.get(column)
        rows.append({
            "column": column,
            "expected": label,
            "invalid_number": int((~valid).sum()),
            "negative": int(usable.lt(0).sum()) if bound is None else "–",
            "outside_range": int(usable.abs().gt(bound).sum()) if bound is not None else "–",
            "invalid_examples": examples(values[~valid]),
        })
    print(pd.DataFrame(rows).to_string(index=False))
    if coordinate_bounds:
        print("허용 범위: 위도 -90~90, 경도 -180~180")


def main() -> None:
    parser = ArgumentParser(description="시카고 CSV 데이터셋 품질 조사")
    parser.add_argument("--top", type=int, default=15, help="범주형 빈도 표시 개수 (0은 전체)")
    args = select_dataset(parser)
    if args.top < 0:
        parser.error("--top은 0 이상이어야 합니다.")

    name, filename = DATASETS[args.dataset]
    rules = RULES[args.dataset]
    print(f"\n데이터셋: {name} ({filename})", flush=True)
    # CSV의 빈 필드와 NULL 문자를 읽을 때 구분할 수 있도록 유지
    df = pd.read_csv(
        DATA_DIR / filename,
        dtype="string",
        na_filter=False,
        low_memory=False,
        encoding="utf-8-sig",
    )
    print(f"행 수: {len(df):,} / 열 수: {len(df.columns)}")

    file_date = Path(filename).stem.rsplit("_", 1)[-1]
    snapshot_date = pd.to_datetime(file_date, format="%Y%m%d") if file_date.isdigit() else None
    report_missing(df)
    report_duplicates(df, rules.identifiers)
    report_categories(df, rules.categories, args.top)
    report_dates(df, snapshot_date, rules.term)
    report_numbers(df, rules)
    print("\n[다음 단계] 허가번호와 지역 코드의 데이터셋 간 매칭")


if __name__ == "__main__":
    main()
