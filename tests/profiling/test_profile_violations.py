"""Checks for the observed Violations text patterns."""

from src.profiling.profile_violations import FRAGMENT_SEPARATOR, parse_fragment


def test_canonical_violation_fragment_captures_code_description_and_comments():
    fragment = "16. FOOD-CONTACT SURFACES CLEANED - Comments: CLEAN ICE MACHINE"
    parsed = parse_fragment(fragment)

    assert parsed["code"] == "16"
    assert parsed["has_code_header"]
    assert parsed["has_canonical_comments_marker"]
    assert parsed["has_standard_description_comments_pattern"]
    assert parsed["description_nonempty"]
    assert parsed["comments_nonempty"]


def test_fragment_without_comments_marker_keeps_description_but_is_partial():
    parsed = parse_fragment("1. PERSON IN CHARGE PRESENT, DEMONSTRATES KNOWLEDGE")

    assert parsed["code"] == "1"
    assert parsed["description_nonempty"]
    assert not parsed["has_comments_marker"]
    assert not parsed["has_standard_description_comments_pattern"]


def test_unrecognized_header_is_detected_without_guessing_a_code():
    parsed = parse_fragment("NO VIOLATION CODE OR DESCRIPTION")

    assert parsed["code"] is None
    assert not parsed["has_code_header"]
    assert not parsed["has_comments_marker"]


def test_only_whitespace_padded_pipe_is_recognized_as_fragment_separator():
    assert FRAGMENT_SEPARATOR.split("1. A - Comments: x | 2. B - Comments: y") == [
        "1. A - Comments: x", "2. B - Comments: y"
    ]
    assert FRAGMENT_SEPARATOR.split("1. A - Comments: x|2. B - Comments: y") == [
        "1. A - Comments: x|2. B - Comments: y"
    ]
