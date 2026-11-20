from src.profiling.profile_sources import column_state, update_column, valid_multipolygon


def test_missing_categories_remain_distinct():
    stats = column_state(["value"])["value"]
    for index, value in enumerate(["", "   ", "NULL", "N/A", "0"], 1):
        update_column(stats, value, index)
    assert (stats["empty"], stats["whitespace"], stats["null_token"]) == (1, 1, 2)
    assert stats["numeric_integer"] == 1


def test_multipolygon_structure_rejects_unclosed_ring():
    geometry = {"type": "MultiPolygon", "coordinates": [[[[0, 0], [0, 1], [1, 1], [0, 0]]]]}
    assert valid_multipolygon(geometry)
    geometry["coordinates"][0][0][-1] = [1, 0]
    assert not valid_multipolygon(geometry)
