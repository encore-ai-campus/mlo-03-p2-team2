from argparse import ArgumentParser, Namespace
from pathlib import Path

import pandas as pd

# 프로젝트 최상위 폴더
PROJECT = Path(__file__).resolve().parents[3]
DATA_DIR = PROJECT / "origin" / "03_repeat_inspection"

DATASETS = {
    "food_inspections": ("Food Inspections", "Food_Inspections_20261119.csv"),
    "business_licenses": ("Business Licenses", "Business_Licenses_20261120.csv"),
    "community_areas": ("Community Areas", "Community_Areas.csv"),
}

IDENTIFIER_COLUMNS = {
    "INSPECTION ID", "LICENSE #", "ZIP", "ID", "LICENSE ID", "ACCOUNT NUMBER",
    "SITE NUMBER", "ZIP CODE", "LICENSE CODE", "BUSINESS ACTIVITY ID",
    "LICENSE NUMBER", "AREA_NUMBE", "AREA_NUM_1",
}
DATE_COLUMNS = {
    "INSPECTION DATE", "APPLICATION CREATED DATE", "APPLICATION REQUIREMENTS COMPLETE",
    "PAYMENT DATE", "LICENSE TERM START DATE", "LICENSE TERM EXPIRATION DATE",
    "LICENSE APPROVED FOR ISSUANCE", "DATE ISSUED", "LICENSE STATUS CHANGE DATE",
}
THOUSANDS_COLUMNS = {"SHAPE_AREA", "SHAPE_LEN"}


def infer_column_type(column: pd.Series) -> str:
    values = column.dropna()
    if values.empty:
        return "unknown (all missing)"

    name = column.name.upper()
    if name in IDENTIFIER_COLUMNS:
        return "string (identifier)"

    if name in DATE_COLUMNS:
        valid_dates = pd.to_datetime(values, format="%m/%d/%Y", errors="coerce").notna()
        if valid_dates.all():
            return "date"
        return "mixed (date/string)" if valid_dates.any() else "string"

    if name == "CONDITIONAL APPROVAL" and values.isin(["Y", "N"]).all():
        return "boolean (Y/N)"

    if name in THOUSANDS_COLUMNS:
        values = values.str.replace(",", "", regex=False)

    # 일부 값이 이미 숫자가 아니면 전체 컬럼의 숫자 변환을 생략
    if pd.to_numeric(values.head(8), errors="coerce").isna().any():
        return "string"

    numbers = pd.to_numeric(values, errors="coerce")
    if numbers.isna().any():
        return "string"
    return "integer" if pd.api.types.is_integer_dtype(numbers.dtype) else "float"


def profile_dataset(name: str, filename: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"데이터셋: {name}")
    print(f"{'=' * 60}")

    path = DATA_DIR / filename

    # 샘플과 집계를 위해 원본 표기를 유지하고 타입은 별도로 추정
    df = pd.read_csv(
        path,
        dtype="string",
        low_memory=False,
        encoding="utf-8-sig"
    )

    # 1. 행 / 열 수
    print(f"\n행 수: {len(df):,}")
    print(f"열 수: {len(df.columns)}")

    # 2. 전체 컬럼명
    print("\n[전체 컬럼명]")
    for i, col in enumerate(df.columns, 1):
        print(f"{i}. {col}")

    # 3. 컬럼별 추정 타입, 결측값 및 고유값 수
    print("\n[컬럼별 정보]")

    summary = pd.DataFrame({
        "column": df.columns,
        "inferred_type": [infer_column_type(df[col]) for col in df.columns],
        "null_count": df.isna().sum().values,
        "null_pct": (
            df.isna().mean().values * 100
        ).round(2),
        "unique_count": df.nunique().values
    })

    print(summary.to_string(index=False))

    # 원본 컬럼을 세로로 배치해 콘솔에서 샘플을 비교하기 쉽게 표시
    sample = df.head(3).transpose()
    sample.columns = [f"샘플 {i}" for i in range(1, len(sample.columns) + 1)]
    print("\n[상위 3행]")
    print(sample.to_string(max_colwidth=32))


def select_dataset(parser: ArgumentParser, *, allow_all: bool = False) -> Namespace:
    choices = (*DATASETS, "all") if allow_all else tuple(DATASETS)
    parser.add_argument("dataset", nargs="?", choices=choices, help="조회할 데이터셋")
    args = parser.parse_args()

    if args.dataset is None:
        choices = {str(number): key for number, key in enumerate(DATASETS, 1)}
        for number, key in choices.items():
            print(f"{number}. {DATASETS[key][0]}")
        while args.dataset is None:
            selected = input("조회할 데이터셋 번호를 입력하세요: ").strip()
            args.dataset = choices.get(selected)
            if args.dataset is None:
                print("1, 2, 3 중 하나를 입력하세요.")

    return args


def main() -> None:
    parser = ArgumentParser(description="시카고 CSV 데이터셋 구조 조사")
    args = select_dataset(parser)
    profile_dataset(*DATASETS[args.dataset])


if __name__ == "__main__":
    main()
