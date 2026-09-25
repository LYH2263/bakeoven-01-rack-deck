from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.models import Batch, ConflictLog, Oven, Product
from app.schemas.schemas import (
    BatchCreate,
    BatchOut,
    ConflictOut,
    GanttBlock,
    OvenOut,
    OvenUpdate,
    ProductOut,
    UsageSegmentOut,
    WindowOut,
)
from app.services.oven_engine import (
    RESOURCE_LABEL,
    RESOURCE_UNIT,
    Capacity,
    Occupancy,
    RecipeDurations,
    build_occupancies,
    count_segments,
    evaluate_capacity,
    find_conflicts,
    next_free_window,
)

api_router = APIRouter()


def _recipe(p: Product) -> RecipeDurations:
    return RecipeDurations(p.ferment_min, p.bake_min)


def _oven_capacity(o: Oven) -> Capacity:
    return Capacity(rack_slots=o.rack_slots, chamber_trays=o.chamber_trays)


def _fmt_time(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def _all_occupancies(db: Session) -> list[Occupancy]:
    batches = db.scalars(select(Batch)).all()
    out: list[Occupancy] = []
    for b in batches:
        p = db.get(Product, b.product_id)
        if not p:
            continue
        out.extend(build_occupancies(b.oven_id, b.id, b.start_min, _recipe(p)))
    return out


def _batch_out(db: Session, b: Batch) -> BatchOut:
    p = db.get(Product, b.product_id)
    o = db.get(Oven, b.oven_id)
    ferment_end = b.start_min + (p.ferment_min if p else 0)
    bake_end = ferment_end + (p.bake_min if p else 0)
    return BatchOut(
        id=b.id,
        product_id=b.product_id,
        oven_id=b.oven_id,
        code=b.code,
        start_min=b.start_min,
        status=b.status,
        product_name=p.name if p else None,
        oven_label=o.label if o else None,
        ferment_end=ferment_end,
        bake_end=bake_end,
    )


def _batch_label(db: Session, batch_id: int) -> str:
    b = db.get(Batch, batch_id)
    return b.code if b else f"#{batch_id}"


def _log_conflict(db: Session, batch_code: str, oven_id: int, detail: str) -> None:
    db.add(ConflictLog(batch_code=batch_code, oven_id=oven_id, detail=detail))
    db.commit()


@api_router.get("/health")
def health():
    return {"status": "ok"}


@api_router.get("/products", response_model=list[ProductOut])
def products(db: Session = Depends(get_db)):
    return db.scalars(select(Product).order_by(Product.id)).all()


@api_router.get("/ovens", response_model=list[OvenOut])
def ovens(db: Session = Depends(get_db)):
    return db.scalars(select(Oven).order_by(Oven.id)).all()


@api_router.put("/ovens/{oven_id}", response_model=OvenOut)
def update_oven(oven_id: int, body: OvenUpdate, db: Session = Depends(get_db)):
    oven = db.get(Oven, oven_id)
    if not oven:
        raise HTTPException(404, "炉位不存在")
    data = body.model_dump(exclude_unset=True)
    if "rack_slots" in data:
        oven.rack_slots = data["rack_slots"]
    if "chamber_trays" in data:
        oven.chamber_trays = data["chamber_trays"]
    db.commit()
    db.refresh(oven)
    return oven


@api_router.get("/batches", response_model=list[BatchOut])
def batches(db: Session = Depends(get_db)):
    rows = db.scalars(select(Batch).order_by(Batch.start_min)).all()
    return [_batch_out(db, b) for b in rows]


@api_router.post("/batches", response_model=BatchOut)
def create_batch(body: BatchCreate, db: Session = Depends(get_db)):
    product = db.get(Product, body.product_id)
    oven = db.get(Oven, body.oven_id)
    if not product or not oven:
        raise HTTPException(404, "产品或炉位不存在")
    recipe = _recipe(product)
    candidates = build_occupancies(oven.id, -1, body.start_min, recipe)
    existing = _all_occupancies(db)
    capacity = _oven_capacity(oven)
    code = body.code or f"BO-{body.start_min}"
    if capacity.unconstrained:
        # 两项上限都留空：只按时间重叠拒绝，与原排炉一致
        hits = find_conflicts(existing, candidates)
        if hits:
            ex, cand = hits[0]
            phase_label = "发酵" if ex.phase == "ferment" else "烘烤"
            detail = (
                f"与批次{_batch_label(db, ex.batch_id)} 的{phase_label}段时间重叠："
                f"[{_fmt_time(cand.interval.start)},{_fmt_time(cand.interval.end)})"
            )
            _log_conflict(db, code, oven.id, detail)
            raise HTTPException(409, detail)
    else:
        violations = evaluate_capacity(existing, candidates, capacity)
        if violations:
            v = violations[0]
            res_label = RESOURCE_LABEL[v.resource]
            unit = RESOURCE_UNIT[v.resource]
            phase_label = "发酵" if v.resource == "rack" else "烘烤"
            opponents = "、".join(_batch_label(db, bid) for bid in v.opponent_ids) or "其他批次"
            detail = (
                f"{res_label}已满（上限 {v.limit}{unit}，{_fmt_time(v.time)} 需 {v.peak}{unit}）："
                f"本批{phase_label}段与{opponents}同时占{res_label}"
            )
            _log_conflict(db, code, oven.id, detail)
            raise HTTPException(409, detail)
    batch = Batch(
        product_id=product.id,
        oven_id=oven.id,
        code=code,
        start_min=body.start_min,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)
    return _batch_out(db, batch)


@api_router.get("/gantt", response_model=list[GanttBlock])
def gantt(db: Session = Depends(get_db)):
    blocks: list[GanttBlock] = []
    for b in db.scalars(select(Batch).order_by(Batch.start_min)).all():
        p = db.get(Product, b.product_id)
        o = db.get(Oven, b.oven_id)
        if not p or not o:
            continue
        for occ in build_occupancies(b.oven_id, b.id, b.start_min, _recipe(p)):
            blocks.append(
                GanttBlock(
                    batch_id=b.id,
                    code=b.code,
                    oven_id=o.id,
                    oven_label=o.label,
                    phase=occ.phase,
                    start_min=occ.interval.start,
                    end_min=occ.interval.end,
                )
            )
    return blocks


@api_router.get("/usage", response_model=list[UsageSegmentOut])
def usage(db: Session = Depends(get_db)):
    """各炉醒发架/膛占用随时间的分段计数，供甘特在重叠处标注。"""
    by_oven: dict[int, list[Occupancy]] = {}
    for occ in _all_occupancies(db):
        by_oven.setdefault(occ.oven_id, []).append(occ)
    out: list[UsageSegmentOut] = []
    for oven in db.scalars(select(Oven).order_by(Oven.id)).all():
        for seg in count_segments(by_oven.get(oven.id, [])):
            out.append(
                UsageSegmentOut(
                    oven_id=oven.id,
                    start_min=seg.interval.start,
                    end_min=seg.interval.end,
                    rack_count=seg.rack_count,
                    chamber_count=seg.chamber_count,
                    rack_slots=oven.rack_slots,
                    chamber_trays=oven.chamber_trays,
                )
            )
    return out


@api_router.get("/conflicts", response_model=list[ConflictOut])
def conflicts(db: Session = Depends(get_db)):
    return db.scalars(select(ConflictLog).order_by(ConflictLog.id.desc())).all()


@api_router.get("/windows", response_model=list[WindowOut])
def windows(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "产品不存在")
    duration = product.ferment_min + product.bake_min
    existing = _all_occupancies(db)
    out: list[WindowOut] = []
    for oven in db.scalars(select(Oven).order_by(Oven.id)).all():
        w = next_free_window(existing, oven.id, duration, search_from=8 * 60, search_to=22 * 60)
        if w:
            out.append(
                WindowOut(
                    oven_id=oven.id,
                    oven_label=oven.label,
                    start_min=w.start,
                    end_min=w.end,
                    duration_min=duration,
                )
            )
    return out
