from pipeline_io import cli, staging
from quality import compare, render_reports


def run(config):
    results = compare(config)
    reports = render_reports(results)
    with staging(config.reports, replace=True) as target:
        for name, content in reports.items():
            (target / name).write_bytes(content)
    print(f"Quality: {len(results)} comparable rules, with decision IDs.")


if __name__ == "__main__":
    raise SystemExit(cli(run, "Compare Domain 04 Bronze and Silver quality"))
