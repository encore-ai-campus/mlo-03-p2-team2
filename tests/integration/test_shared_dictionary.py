from pathlib import Path
import shutil

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from src.silver.shared_dictionary import CODE_MAP, SHARED_COLUMNS, load_shared_codes, load_shared_columns
from src.silver.validate_integration_silver import verify_schema


ROOT = Path(__file__).resolve().parents[2]


def test_shared_dictionary_rejects_duplicate_column(tmp_path):
    path = tmp_path / SHARED_COLUMNS
    path.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / SHARED_COLUMNS, path)
    with path.open("a", encoding="utf-8") as stream:
        stream.write("food_inspections,Test ID,inspection_key,string,trim,\n")
    with pytest.raises(ValueError, match="duplicate source/target"):
        load_shared_columns(tmp_path)


def test_shared_codes_validate_required_value_lists(tmp_path):
    path = tmp_path / CODE_MAP
    path.parent.mkdir(parents=True)
    original = (ROOT / CODE_MAP).read_text(encoding="utf-8")
    path.write_text("".join(line for line in original.splitlines(keepends=True)
                            if not line.startswith("food_inspections,Risk,")), encoding="utf-8")
    with pytest.raises(ValueError, match="Missing shared code mappings"):
        load_shared_codes(tmp_path, load_shared_columns(ROOT))

    first_entry = original.splitlines()[1]
    path.write_text(original + first_entry + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate shared code"):
        load_shared_codes(tmp_path, load_shared_columns(ROOT))


def test_schema_validates_types_in_addition_to_column_names(tmp_path):
    path = tmp_path / "inspection.parquet"
    fields = [{"target_column": "inspection_key", "type": "string"}]
    pq.write_table(pa.table({"inspection_key": pa.array(["001"], type=pa.large_string()),
                             "source_row_num": [1]}), path)
    verify_schema(path, fields)

    pq.write_table(pa.table({"inspection_key": [1], "source_row_num": [1]}), path)
    with pytest.raises(ValueError, match="inspection_key must be string"):
        verify_schema(path, fields)
