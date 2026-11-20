import csv
import gzip
import hashlib
import subprocess
import sys
from pathlib import Path


def test_origin_restores_verified_csvs_and_rejects_changed_parts(tmp_path):
    script = Path(__file__).resolve().parents[1] / "src/ingestion/restore_origin.py"
    root = tmp_path / "origin"
    root.mkdir()
    contents = {name: b"{\"value\":1}\n" for name in (
        "community_areas.geojson", "food_columns.json", "license_columns.json", "area_columns.json",
    )}
    raw = {name: b"id,name\r\n1,Chicago\r\n" for name in ("food_inspections.csv", "business_licenses.csv")}
    for name, payload in raw.items():
        encoded = gzip.compress(payload, mtime=0)
        cut = (len(encoded) + 1) // 2
        contents[f"{name}.gz.part-001"] = encoded[:cut]
        contents[f"{name}.gz.part-002"] = encoded[cut:]
    for name, payload in contents.items():
        (root / name).write_bytes(payload)
    (root / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(payload).hexdigest()}  {name}\n" for name, payload in contents.items()
    ), encoding="ascii")
    catalog = tmp_path / "download_manifest.csv"
    originals = raw | {name: value for name, value in contents.items() if ".part-" not in name}
    with catalog.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["File", "Bytes", "SHA256"])
        for name, payload in originals.items():
            writer.writerow([name, len(payload), hashlib.sha256(payload).hexdigest()])

    command = [sys.executable, str(script), "--origin-dir", str(root), "--catalog", str(catalog), "--restore"]
    outcome = subprocess.run(command, capture_output=True, text=True)
    assert outcome.returncode == 0, outcome.stderr
    assert {name: (root / name).read_bytes() for name in raw} == raw

    corrupt = root / "food_inspections.csv.gz.part-002"
    corrupt.write_bytes(b"bad part")
    outcome = subprocess.run(command, capture_output=True, text=True)
    assert outcome.returncode == 1
    assert "SHA-256 differs" in outcome.stderr
    assert {name: (root / name).read_bytes() for name in raw} == raw
