"""Oven scheduling with half-open ferment+bake intervals and next free window.

醒发架（ferment 段）与炉膛（bake 段）分开计容：同一座炉可同时登记
醒发架格数与炉膛盘数。发酵段只占架，烘烤段只占膛。区间一律半开
[start, end)，端点相接（前批 end == 后批 start）不算同时占用。
"""

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


PHASE_RESOURCE = {"ferment": "rack", "bake": "chamber"}
RESOURCE_LABEL = {"rack": "醒发架", "chamber": "炉膛"}
RESOURCE_UNIT = {"rack": "格", "chamber": "盘"}


@dataclass(frozen=True)
class Capacity:
    """某座炉的两项上限；任一项为 None 表示该资源不设限（不参与计容）。"""

    rack_slots: int | None = None
    chamber_trays: int | None = None

    @property
    def unconstrained(self) -> bool:
        return self.rack_slots is None and self.chamber_trays is None


@dataclass(frozen=True)
class CapacityViolation:
    resource: str  # rack | chamber
    limit: int
    peak: int
    time: int  # 超限时刻（分钟）
    opponent_ids: tuple[int, ...]  # 同时占用该资源的对手批次


@dataclass(frozen=True)
class UsageSegment:
    interval: Interval
    rack_count: int
    chamber_count: int


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
    """纯时间重叠检测（两项上限都留空时使用）：同炉且区间真重叠即冲突。"""
    hits: list[tuple[Occupancy, Occupancy]] = []
    for cand in candidates:
        for ex in existing:
            if ex.oven_id != cand.oven_id:
                continue
            if ex.interval.overlaps(cand.interval):
                hits.append((ex, cand))
    return hits


def count_segments(occupancies: list[Occupancy]) -> list[UsageSegment]:
    """事件扫描，产出 (架上发酵段数, 膛上烘烤段数) 恒定的最大时间片。

    同一时刻先收尾（-1）再开工（+1），因此半开区间端点相接不会被
    计为同时占用。零时长段不会产生任何时间片。
    """
    events: list[tuple[int, int, str]] = []
    for o in occupancies:
        if o.interval.start == o.interval.end:
            continue  # 零时长段（如发酵 0 分钟）不占资源
        resource = PHASE_RESOURCE[o.phase]
        events.append((o.interval.start, 1, resource))
        events.append((o.interval.end, -1, resource))
    # 同一分钟内 delta 升序：-1（结束）排在 +1（开始）之前
    events.sort(key=lambda e: (e[0], e[1]))

    counts = {"rack": 0, "chamber": 0}
    segments: list[UsageSegment] = []
    seg_start: int | None = None
    i = 0
    while i < len(events):
        t = events[i][0]
        if seg_start is not None and t > seg_start and (counts["rack"] or counts["chamber"]):
            segments.append(
                UsageSegment(Interval(seg_start, t), counts["rack"], counts["chamber"])
            )
        while i < len(events) and events[i][0] == t:
            _, delta, resource = events[i]
            counts[resource] += delta
            i += 1
        seg_start = t
    return segments


def evaluate_capacity(
    existing: list[Occupancy],
    candidates: list[Occupancy],
    capacity: Capacity,
) -> list[CapacityViolation]:
    """按醒发架/炉膛分别计容，返回候选批次触发的超限（每种资源取最早一片）。

    只统计与候选同炉的占用，且超限时间片必须有候选批次参与。
    """
    violations: list[CapacityViolation] = []
    cand_ids = {o.batch_id for o in candidates}
    oven_ids = {o.oven_id for o in candidates}
    pool = [o for o in existing if o.oven_id in oven_ids] + list(candidates)
    for resource, phase, limit in (
        ("rack", "ferment", capacity.rack_slots),
        ("chamber", "bake", capacity.chamber_trays),
    ):
        if limit is None:
            continue
        occs = [o for o in pool if o.phase == phase]
        cand_occs = [o for o in candidates if o.phase == phase]
        for seg in count_segments(occs):
            peak = seg.rack_count if resource == "rack" else seg.chamber_count
            if peak <= limit:
                continue
            if not any(
                o.interval.start < seg.interval.end and seg.interval.start < o.interval.end
                for o in cand_occs
            ):
                continue  # 既有占用自身的超限，与本次排入无关
            opponents = tuple(
                sorted(
                    {
                        o.batch_id
                        for o in occs
                        if o.batch_id not in cand_ids
                        and o.interval.start <= seg.interval.start < o.interval.end
                    }
                )
            )
            violations.append(
                CapacityViolation(resource, limit, peak, seg.interval.start, opponents)
            )
            break  # 该资源只报最早一次
    violations.sort(key=lambda v: (v.time, 0 if v.resource == "rack" else 1))
    return violations


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
