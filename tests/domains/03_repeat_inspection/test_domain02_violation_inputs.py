import json
from hashlib import file_digest
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

import pyarrow as pa
import pyarrow.parquet as pq


DOMAIN = Path(__file__).resolve().parents[3] / "src" / "domains" / "03_repeat_inspection"
sys.path.insert(0, str(DOMAIN))

from violation_inputs import ACCEPTED, QUARANTINE, RECONCILIATION, load_domain02_violations
from build_inspection_marts import inspection_metadata


class Domain02ViolationInputTests(unittest.TestCase):
    def test_domain01_manifest_verifies_the_actual_silver_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            silver = root / "food_inspections.parquet"
            manifest_path = root / "inspection_silver_manifest.json"
            pq.write_table(pa.table({"inspection_key": ["one"]}), silver)
            with silver.open("rb") as stream:
                checksum = file_digest(stream, "sha256").hexdigest()
            manifest = {
                "artifacts": {silver.name: checksum}, "source_sha256": "a" * 64, "silver_rows": 1,
            }
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            self.assertEqual(inspection_metadata(pq.ParquetFile(silver), silver, manifest_path), {
                b"source_sha256": b"a" * 64,
                b"inspection_silver_sha256": checksum.encode("ascii"),
            })
            manifest["artifacts"][silver.name] = "0" * 64
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Silver SHA-256 differs"):
                inspection_metadata(pq.ParquetFile(silver), silver, manifest_path)

    def test_statuses_use_both_outputs_and_keep_string_codes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in (ACCEPTED, QUARANTINE, RECONCILIATION):
                (root / relative).parent.mkdir(parents=True, exist_ok=True)
            for relative, ids, source_rows, codes, status in (
                (ACCEPTED, ["a", "a", "b"], [1, 1, 2], ["1A", "1A", "007"], "PARSED"),
                (QUARANTINE, ["b", "c"], [2, 3], ["5", "6"], "MISSING_COMMENTS_MARKER"),
            ):
                pq.write_table(pa.table({
                    "inspection_id": ids,
                    "bronze_row_number": source_rows,
                    "violation_code": codes,
                    "parsing_status": [status] * len(ids),
                }), root / relative)
            (root / RECONCILIATION).write_text(json.dumps({
                "status": "PASS", "issues": {}, "origin_sha256": "abc",
                "counts": {"accepted": 3, "quarantined": 2},
            }), encoding="utf-8")
            inspections = [
                SimpleNamespace(inspection_key=key, source_row_num=index)
                for index, key in enumerate("abcd", 1)
            ]
            baseline = {key: (set(), "parsed" if key != "d" else "missing") for key in "abcd"}

            result = load_domain02_violations(root, b"ABC", inspections, baseline)

            self.assertEqual(result, {
                "a": ({"1A"}, "parsed"),
                "b": ({"007"}, "partial"),
                "c": (set(), "unparsed"),
                "d": (set(), "missing"),
            })
            with self.assertRaisesRegex(ValueError, "same source SHA-256"):
                load_domain02_violations(root, b"different", inspections, baseline)
