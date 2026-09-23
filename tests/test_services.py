from datetime import datetime

import pytest

from app.services import exposure_by_year, find_overlap, split_by_year


class Rec:
    def __init__(self, rid, start, end):
        self.id = rid
        self.start_time = start
        self.end_time = end


def test_split_same_year():
    segs = list(split_by_year(datetime(2026, 3, 1, 8), datetime(2026, 3, 1, 18)))
    assert segs == [(2026, 10.0)]


def test_split_cross_year_boundary():
    segs = dict(split_by_year(datetime(2025, 12, 31, 12), datetime(2026, 1, 1, 12)))
    assert segs == {2025: 12.0, 2026: 12.0}


def test_split_multi_year_total_preserved():
    start, end = datetime(2024, 6, 1, 0), datetime(2026, 6, 1, 0)
    segs = dict(split_by_year(start, end))
    assert set(segs) == {2024, 2025, 2026}
    assert segs[2025] == 365 * 24  # 2025 非闰年，全年计入
    total = (end - start).total_seconds() / 3600
    assert sum(segs.values()) == pytest.approx(total)


def test_split_leap_year():
    segs = dict(split_by_year(datetime(2024, 1, 1), datetime(2025, 1, 1)))
    assert segs[2024] == 366 * 24


def test_split_invalid_range():
    with pytest.raises(ValueError):
        list(split_by_year(datetime(2026, 1, 2), datetime(2026, 1, 1)))


def test_exposure_by_year_cross_year():
    e = exposure_by_year(datetime(2025, 12, 31, 20), datetime(2026, 1, 1, 4), 50.0)
    assert e == {2025: 200.0, 2026: 200.0}


def test_overlap_detected():
    existing = [Rec(1, datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))]
    # 包含、被包含、两端相交都算重叠
    assert find_overlap(existing, datetime(2026, 1, 10, 12), datetime(2026, 1, 10, 13))
    assert find_overlap(existing, datetime(2026, 1, 10, 8), datetime(2026, 1, 10, 10))
    assert find_overlap(existing, datetime(2026, 1, 10, 16), datetime(2026, 1, 10, 20))
    assert find_overlap(existing, datetime(2026, 1, 10, 8), datetime(2026, 1, 10, 20))


def test_touching_boundaries_not_overlap():
    existing = [Rec(1, datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))]
    # 左闭右开：首尾相接不算重叠
    assert find_overlap(existing, datetime(2026, 1, 10, 17), datetime(2026, 1, 10, 19)) is None
    assert find_overlap(existing, datetime(2026, 1, 10, 7), datetime(2026, 1, 10, 9)) is None


def test_overlap_exclude_self():
    existing = [Rec(1, datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 17))]
    assert find_overlap(
        existing, datetime(2026, 1, 10, 9), datetime(2026, 1, 10, 12), exclude_id=1
    ) is None
