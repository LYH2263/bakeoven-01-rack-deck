"""Oven scheduling with half-open ferment+bake intervals and next free window."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    start: int  # minutes from day origin
    end: int  # exclusive

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end


@dataclass(frozen=True)
class RecipeDurations:
    ferment_min: int
    bake_min: int

    @property
    def total(self) -> int:
        return self.ferment_min + self.bake_min


@dataclass(frozen=True)
class Occupancy:
    oven_id: int
    interval: Interval
    phase: str  # ferment | bake
    batch_id: int


def build_occupancies(
    oven_id: int,
    batch_id: int,
    start_min: int,
    recipe: RecipeDurations,
) -> list[Occupancy]:
    ferment = Interval(start_min, start_min + recipe.ferment_min)
    bake = Interval(ferment.end, ferment.end + recipe.bake_min)
    return [
        Occupancy(oven_id, ferment, "ferment", batch_id),
        Occupancy(oven_id, bake, "bake", batch_id),
    ]


def find_conflicts(existing: list[Occupancy], candidates: list[Occupancy]) -> list[tuple[Occupancy, Occupancy]]:
    hits: list[tuple[Occupancy, Occupancy]] = []
    for cand in candidates:
        for ex in existing:
            if ex.oven_id != cand.oven_id:
                continue
            if ex.interval.overlaps(cand.interval):
                hits.append((ex, cand))
    return hits


# 发酵段只占醒发架，烘烤段只占炉膛
@dataclass(frozen=True)
class OvenCapacity:
    rack_slots: int | None  # 醒发架格数；None=不按架计容
    hearth_slots: int | None  # 炉膛盘数；None=不按膛计容


@dataclass(frozen=True)
class CapacityViolation:
    resource: str  # rack(架满) | hearth(膛满)
    limit: int
    peak: int
    start: int
    end: int
    rivals: tuple[int, ...]  # 同时占用该资源的对手批次 id


def _sweep_violation(
    existing: list[tuple[int, int, int]],
    candidates: list[tuple[int, int, int]],
    limit: int,
    resource: str,
) -> CapacityViolation | None:
    """半开区间扫描：仅在候选段在场的区段统计占用，返回最严重的一次超限。"""
    events: list[tuple[int, int, int, int]] = []  # 时刻, 增量(-1先/+1后), 批次id, 是否候选
    for s, e, b in existing:
        if e > s:
            events.append((s, 1, b, 0))
            events.append((e, -1, b, 0))
    for s, e, b in candidates:
        if e > s:
            events.append((s, 1, b, 1))
            events.append((e, -1, b, 1))
    events.sort(key=lambda x: (x[0], x[1]))  # 同一时刻先收尾后开场，端点相接不重叠

    active_existing: set[int] = set()
    cand_count = 0
    prev: int | None = None
    worst: CapacityViolation | None = None
    for t, delta, bid, is_cand in events:
        if prev is not None and t > prev and cand_count > 0:
            total = len(active_existing) + cand_count
            if total > limit and (worst is None or total > worst.peak):
                worst = CapacityViolation(
                    resource=resource,
                    limit=limit,
                    peak=total,
                    start=prev,
                    end=t,
                    rivals=tuple(sorted(active_existing)),
                )
        if is_cand:
            cand_count += delta
        elif delta == 1:
            active_existing.add(bid)
        else:
            active_existing.discard(bid)
        prev = t
    return worst


def check_capacity(
    existing: list[Occupancy],
    candidates: list[Occupancy],
    capacity: OvenCapacity,
) -> CapacityViolation | None:
    """发酵只核架格、烘烤只核膛盘；两项留空的资源不限制（退回纯时间重叠）。"""
    if not candidates:
        return None
    oven_id = candidates[0].oven_id
    on_oven = [o for o in existing if o.oven_id == oven_id]
    for phase, resource, limit in (
        ("ferment", "rack", capacity.rack_slots),
        ("bake", "hearth", capacity.hearth_slots),
    ):
        if limit is None:
            continue
        ex = [(o.interval.start, o.interval.end, o.batch_id) for o in on_oven if o.phase == phase]
        cand = [(o.interval.start, o.interval.end, o.batch_id) for o in candidates if o.phase == phase]
        violation = _sweep_violation(ex, cand, limit, resource)
        if violation is not None:
            return violation
    return None


def next_free_window(
    existing: list[Occupancy],
    oven_id: int,
    duration: int,
    search_from: int = 0,
    search_to: int = 24 * 60,
) -> Interval | None:
    """Find earliest half-open [start, start+duration) free on oven."""
    if duration <= 0:
        return None
    busy = sorted(
        [o.interval for o in existing if o.oven_id == oven_id],
        key=lambda i: i.start,
    )
    cursor = search_from
    for iv in busy:
        if iv.end <= cursor:
            continue
        if iv.start >= cursor + duration:
            end = cursor + duration
            if end <= search_to:
                return Interval(cursor, end)
            return None
        cursor = max(cursor, iv.end)
    if cursor + duration <= search_to:
        return Interval(cursor, cursor + duration)
    return None
