import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


DOMAIN = Path(__file__).resolve().parents[3] / "src" / "domains" / "03_repeat_inspection"
sys.path.insert(0, str(DOMAIN))

from build_food_inspections_bronze import build_bronze, sha256
from build_food_inspections_silver import read_bronze


class BronzeParquetTests(unittest.TestCase):
    def test_preserves_empty_strings_leading_zeroes_and_multiline_values(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "raw.csv"
            source.write_bytes(b'Inspection ID,Violations\r\n001,"first\r\nsecond"\r\n\r\n002,\r\n')
            manifest = {
                "header": ["Inspection ID", "Violations"], "sha256": sha256(source),
                "logical_row_count": 2,
            }
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            output = root / "03_food_inspections.parquet"

            build_bronze(source, output, manifest_path)

            expected = [
                {"Inspection ID": "001", "Violations": "first\r\nsecond", "source_row_num": 1},
                {"Inspection ID": "002", "Violations": "", "source_row_num": 2},
            ]
            self.assertEqual(list(read_bronze(output, manifest)), expected)
            self.assertEqual(list(read_bronze(source, manifest)), expected)
