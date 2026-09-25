from app.services.oven_engine import (
    Capacity,
    Interval,
    Occupancy,
    RecipeDurations,
    build_occupancies,
    count_segments,
    evaluate_capacity,
    find_conflicts,
    next_free_window,
)


def test_half_open_no_touch_conflict():
    a = Occupancy(1, Interval(0, 30), "bake", 1)
    b = Occupancy(1, Interval(30, 60), "bake", 2)
    assert find_conflicts([a], [b]) == []


def test_overlap_detected():
    recipe = RecipeDurations(20, 30)
    cand = build_occupancies(1, 9, 10, recipe)
    existing = [Occupancy(1, Interval(25, 40), "bake", 1)]
    assert find_conflicts(existing, cand)


def test_next_free_window_after_busy():
    existing = [
        Occupancy(1, Interval(0, 40), "ferment", 1),
        Occupancy(1, Interval(40, 70), "bake", 1),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(70, 100)


def test_next_free_in_gap():
    existing = [
        Occupancy(1, Interval(0, 20), "bake", 1),
        Occupancy(1, Interval(80, 100), "bake", 2),
    ]
    w = next_free_window(existing, 1, duration=30, search_from=0)
    assert w == Interval(20, 50)


# —— 醒发架 / 炉膛分开计容 ——

RACK2_CHAMBER1 = Capacity(rack_slots=2, chamber_trays=1)


def _ferment(oven: int, start: int, end: int, bid: int) -> Occupancy:
    return Occupancy(oven, Interval(start, end), "ferment", bid)


def _bake(oven: int, start: int, end: int, bid: int) -> Occupancy:
    return Occupancy(oven, Interval(start, end), "bake", bid)


def test_two_ferment_overlaps_fit_rack2():
    # 两批只有发酵重叠（炉膛各 1 盘、端点相接不重叠）：都能留下
    existing = [
        _ferment(1, 0, 40, 1),
        _bake(1, 40, 70, 1),
    ]
    cand = [
        _ferment(1, 30, 70, 2),
        _bake(1, 70, 100, 2),
    ]
    assert evaluate_capacity(existing, cand, RACK2_CHAMBER1) == []


def test_two_bake_overlaps_rejected_chamber1():
    # 两批烘烤重叠，膛只有 1 盘：后一批被拒绝，并带上对手批次
    existing = [
        _ferment(1, 0, 40, 1),
        _bake(1, 40, 70, 1),
    ]
    cand = [
        _ferment(1, 0, 20, 2),
        _bake(1, 20, 60, 2),
    ]
    violations = evaluate_capacity(existing, cand, RACK2_CHAMBER1)
    assert len(violations) == 1
    v = violations[0]
    assert v.resource == "chamber"
    assert v.limit == 1
    assert v.peak == 2
    assert v.opponent_ids == (1,)


def test_rack_full_reports_rack_and_opponents():
    existing = [
        _ferment(1, 0, 60, 1),
        _ferment(1, 10, 70, 2),
    ]
    cand = [_ferment(1, 20, 80, 3), _bake(1, 80, 100, 3)]
    violations = evaluate_capacity(existing, cand, RACK2_CHAMBER1)
    assert len(violations) == 1
    v = violations[0]
    assert v.resource == "rack"
    assert v.limit == 2
    assert v.peak == 3
    assert v.opponent_ids == (1, 2)


def test_endpoint_touch_is_not_concurrent():
    # 前批烘烤 [40,70)，后批烘烤 [70,90)：端点相接不算同时
    existing = [_bake(1, 40, 70, 1)]
    cand = [_ferment(1, 30, 70, 2), _bake(1, 70, 90, 2)]
    assert evaluate_capacity(existing, cand, RACK2_CHAMBER1) == []


def test_ferment_and_bake_do_not_block_each_other():
    # 发酵只占架、烘烤只占膛：同一时刻一批发酵一批烘烤互不挤占
    existing = [_ferment(1, 0, 50, 1)]
    cand = [_ferment(1, 60, 80, 2), _bake(1, 20, 45, 2)]
    assert evaluate_capacity(existing, cand, RACK2_CHAMBER1) == []


def test_only_rack_capacity_ignores_bake_time_overlap():
    # 只登记架格、膛留空：烘烤时间重叠也不拒绝
    cap = Capacity(rack_slots=2)
    existing = [_bake(1, 0, 60, 1)]
    cand = [_bake(1, 10, 70, 2)]
    assert evaluate_capacity(existing, cand, cap) == []


def test_unconstrained_falls_back_to_time_overlap():
    existing = [_bake(1, 0, 30, 1)]
    cand = [_bake(1, 20, 50, 2)]
    assert find_conflicts(existing, cand)


def test_other_oven_occupancies_do_not_count():
    # 别的炉的占用不计入本炉计容
    existing = [_bake(2, 0, 60, 1), _bake(2, 10, 70, 2)]
    cand = [_ferment(1, 0, 30, 3), _bake(1, 30, 60, 3)]
    assert evaluate_capacity(existing, cand, RACK2_CHAMBER1) == []


def test_preexisting_overlimit_not_involving_candidate_ignored():
    # 既有批次自身超限的时段与本次排入无关，不应误拒
    existing = [
        _bake(1, 0, 30, 1),
        _bake(1, 10, 40, 2),  # 膛1 下 0-40 已有两批烘烤重叠（历史遗留）
    ]
    cand = [_ferment(1, 100, 130, 3), _bake(1, 130, 160, 3)]
    assert evaluate_capacity(existing, cand, RACK2_CHAMBER1) == []


def test_count_segments_endpoint_touch_peak():
    segs = count_segments(
        [_ferment(1, 0, 30, 1), _ferment(1, 30, 60, 2)]
    )
    # 相接两段各自计数 1，不出现 2
    assert [(s.interval.start, s.interval.end, s.rack_count) for s in segs] == [
        (0, 30, 1),
        (30, 60, 1),
    ]
