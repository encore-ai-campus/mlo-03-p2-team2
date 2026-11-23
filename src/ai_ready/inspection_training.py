"""Point-in-time feature and label construction for the two inspection tasks."""

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import date, timedelta
from itertools import groupby
from operator import attrgetter


EVALUATED_RESULTS = {"PASS", "PASS W/ CONDITIONS", "FAIL"}
HISTORY_COUNTS = (
    "prior_inspection_count_num",
    "prior_fail_count_num",
    "prior_code_observed_inspection_count_num",
    "prior_fully_parsed_inspection_count_num",
)


@dataclass(frozen=True, slots=True)
class Rules:
    history_days: int
    code_change: date
    validation_start: date
    test_start: date

    @classmethod
    def from_contract(cls, contract):
        return cls(
            contract["history_days"], date.fromisoformat(contract["code_system_change_dtm"]),
            date.fromisoformat(contract["split"]["validation_start_inclusive"]),
            date.fromisoformat(contract["split"]["test_start_inclusive"]),
        )

    def split(self, day):
        if day >= self.test_start:
            return "test"
        if day >= self.validation_start:
            return "validation"
        return "train"

    def code_version(self, day):
        return self.code_change.isoformat() if day >= self.code_change else "pre_" + self.code_change.isoformat()


@dataclass(frozen=True, slots=True)
class Inspection:
    key: str
    license_number: str | None
    day: date
    result: str | None
    source_row: int


@dataclass(frozen=True, slots=True)
class Recurrence:
    code_version: str
    code: str
    followup: Inspection
    repeated: bool


def load_recurrence_labels(records, inspections, codes, rejected, rules):
    """Reconcile Gold labels with the shared inspections and accepted 02 codes."""
    labels = defaultdict(list)
    counts = Counter()
    grain = set()
    for row in records:
        key, version, code = (row[name] for name in (
            "base_inspection_key", "code_system_version", "violation_cd",
        ))
        base = inspections.get(key)
        identity = (key, version, code)
        if identity in grain:
            raise ValueError(f"Duplicate 03 Gold grain: {identity!r}")
        grain.add(identity)
        if (base is None or code not in codes.get(key, ()) or base.day < rules.code_change
                or version != rules.code_version(base.day) or base.day != row["base_inspection_dtm"]
                or base.license_number != row["license_number_key"]
                or base.result != row["base_result_cd"] or base.result not in EVALUATED_RESULTS):
            raise ValueError(f"03 Gold base and shared inspection/02 Gold disagree: {identity!r}")

        status, flag = row["comparison_status_cd"], row["repeat_flag"]
        counts[status] += 1
        if status != "comparable":
            if flag is not None:
                raise ValueError(f"Non-comparable 03 Gold row has a target: {identity!r}")
            continue
        followup = inspections.get(row["followup_inspection_key"])
        if (followup is None or base.license_number is None or followup.license_number != base.license_number
                or followup.day != row["followup_inspection_dtm"] or followup.day <= base.day
                or followup.result != row["followup_result_cd"] or followup.result not in EVALUATED_RESULTS
                or (followup.day - base.day).days != row["days_to_followup_num"]
                or key in rejected or followup.key in rejected or not codes.get(followup.key)
                or row["base_violation_parse_status_cd"] != "parsed"
                or row["followup_violation_parse_status_cd"] != "parsed"
                or type(flag) is not bool or flag != (code in codes[followup.key])):
            raise ValueError(f"03 Gold target and observed follow-up disagree: {identity!r}")
        if rules.split(base.day) != rules.split(followup.day):
            counts["excluded_cross_split_label"] += 1
            continue
        labels[key].append(Recurrence(version, code, followup, flag))
    return labels, dict(sorted(counts.items()))


def histories(inspections, codes, rejected, rules):
    """Yield prior features before admitting any record from the current day."""
    records = sorted(inspections, key=lambda row: (row.license_number or "", row.day, row.key))
    lookback = timedelta(days=rules.history_days)
    for license_number, group in groupby(records, attrgetter("license_number")):
        if license_number is None:
            for row in group:
                yield row, {
                    "history_status_cd": "missing_license",
                    "latest_prior_inspection_dtm": None,
                    "days_since_prior_inspection_num": None,
                    **dict.fromkeys(HISTORY_COUNTS),
                }, {}
            continue

        window = deque()
        totals = Counter()
        code_counts = Counter()

        def update(row, change):
            observed_codes = codes.get(row.key, ())
            totals["prior_inspection_count_num"] += change
            totals["prior_fail_count_num"] += change * (row.result == "FAIL")
            totals["prior_code_observed_inspection_count_num"] += change * bool(observed_codes)
            totals["prior_fully_parsed_inspection_count_num"] += change * (
                bool(observed_codes) and row.key not in rejected
            )
            if observed_codes:
                version = rules.code_version(row.day)
                for code in observed_codes:
                    identity = (version, code)
                    code_counts[identity] += change
                    if code_counts[identity] == 0:
                        del code_counts[identity]

        for day, same_day in groupby(group, attrgetter("day")):
            while window and window[0].day < day - lookback:
                update(window.popleft(), -1)
            latest = window[-1].day if window else None
            features = {
                "history_status_cd": "observed_earlier_inspection" if window else "no_prior_inspection_in_window",
                "latest_prior_inspection_dtm": latest,
                "days_since_prior_inspection_num": (day - latest).days if latest else None,
                **{name: totals[name] for name in HISTORY_COUNTS},
            }
            daily_rows = list(same_day)
            for row in daily_rows:
                yield row, features, code_counts
            for row in daily_rows:
                window.append(row)
                update(row, 1)


def training_examples(inspections, codes, rejected, labels, rules):
    """Yield task keys and rows. Future observations enter only label/audit fields."""
    for base, history, code_counts in histories(inspections, codes, rejected, rules):
        shared = {
            "inspection_key": base.key,
            "license_number_key": base.license_number,
            "source_row_num": base.source_row,
            "prediction_dtm": base.day,
            "split_cd": rules.split(base.day),
            **history,
        }
        if base.result in EVALUATED_RESULTS:
            yield "preinspection_failure", {
                **shared, "label_observed_dtm": base.day, "label_fail_flag": base.result == "FAIL",
            }
        for label in sorted(labels.get(base.key, ()), key=attrgetter("code")):
            yield "next_inspection_violation_recurrence", {
                **shared,
                "base_result_cd": base.result,
                "base_accepted_code_count_num": len(codes[base.key]),
                "code_system_version": label.code_version,
                "violation_cd": label.code,
                "prior_same_code_inspection_count_num": code_counts.get((label.code_version, label.code), 0),
                "followup_inspection_key": label.followup.key,
                "label_observed_dtm": label.followup.day,
                "label_repeat_flag": label.repeated,
            }
