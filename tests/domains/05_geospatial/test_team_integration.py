"""Verify CSV record numbering and the 05 team integration interfaces."""

from collections import Counter
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import pandas as pd
import pyarrow as pa

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src/domains/05_geospatial"))
import geographic_medallion as medallion


class TeamIntegrationTests(unittest.TestCase):
    def test_license_blank_gets_quality_reason_and_proposed_code_does_not(self):
        from audit_geographic_silver import quality_reason

        batch = pa.record_batch({"License #": ["", "0", "0007"], "batch_id": ["test"] * 3,
                                 "source_row_num": [1, 2, 3]})
        spec = {"columns": [{"source_column": "License #", "standard_column": "license_number_key",
                             "transform": "inspection_license"}]}
        issues = []
        normalized = medallion.standardize_batch("food_inspections", spec, batch, {}, issues, Counter())
        self.assertEqual(normalized["license_number_key"].to_pylist(), [None, None, "0007"])
        reason = "MISSING_LICENSE_NUMBER"
        self.assertIn(reason, pa.concat_tables(issues)["reason_cd"].to_pylist())
        self.assertEqual(quality_reason("license_number_key", "inspection_license", "", None, None), reason)
        self.assertIsNone(quality_reason("result_cd", "code", "Fail", "FAIL", "proposed"))

    def test_csv_skips_empty_records_and_preserves_quoted_line_breaks(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "food_inspections.csv"
            path.write_text('ID,Text\n1,"first\nsecond"\n\n,\n2, \n', encoding="utf-8", newline="\n")
            stats = Counter()
            rows = list(medallion.source_records(path, ["ID", "Text"], stats))
        self.assertEqual(rows, [["1", "first\nsecond"], ["2", " "]])
        self.assertEqual(stats["empty_records"], 2)

    def test_team_boundary_reader_preserves_feature_number_and_coordinate_precision(self):
        from geographic_boundary import boundary_records

        point = [-87.1234567890123, 41.5]
        feature = {
            "type": "Feature",
            "geometry": {"type": "Polygon", "coordinates": [[point, [-87, 41.5], [-87, 42], point]]},
            "properties": {"area_numbe": "8", "community": "NEAR NORTH SIDE",
                           "area_num_1": "8", "shape_area": "123.5", "shape_len": "400"},
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "community_areas.geojson"
            path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
            row, = boundary_records(path)
        self.assertIn("-87.1234567890123", row[0])
        self.assertEqual(row[1:], ["8", "NEAR NORTH SIDE", "8", "123.5", "400"])

    def test_shared_observations_determine_code_ready_denominator(self):
        from geographic_integration import attach_shared_violations

        era = "from_2018_07_01"
        inspections = pd.DataFrame({
            "inspection_key": ["a", "b", "c"],
            "code_system_version": [era, era, era],
            "violation_observation_status": ["parsed", "parsed", "raw_missing"],
            "violation_code_occurrence_ready": [True, True, False],
        })
        codes = pd.DataFrame({"inspection_key": ["a"], "code_system_version": [era], "violation_cd": ["07"]})
        observations = pd.DataFrame({
            "inspection_key": ["c", "a", "b"],
            "violation_observation_status": ["raw_missing", "parsed", "unrecognized"],
        })
        updated = attach_shared_violations(inspections, codes, observations)
        self.assertEqual(updated["inspection_key"].tolist(), ["a", "b", "c"])
        self.assertEqual(updated["violation_code_occurrence_ready"].tolist(), [True, False, False])
        self.assertEqual(updated["violation_observation_status"].tolist(), ["parsed", "unrecognized", "raw_missing"])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            attach_shared_violations(inspections, pd.concat([codes, codes]), observations)
        with self.assertRaisesRegex(ValueError, "procedure"):
            attach_shared_violations(inspections, codes.assign(code_system_version="pre_2018_07_01"), observations)

    def test_team_source_rejects_wrong_fingerprint(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "food_inspections.csv").write_text("Inspection ID\n123\n", encoding="utf-8")
            contract = {"datasets": {"food_inspections": {
                "file": "food_inspections.csv", "team_sha256": "0" * 64,
                "source_id": "4ijn-s7e5", "url": "https://data.cityofchicago.org/d/4ijn-s7e5",
                "columns": [{"source_column": "Inspection ID"}],
            }}}
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                medallion.source_inventory(folder, contract)


if __name__ == "__main__":
    unittest.main()
