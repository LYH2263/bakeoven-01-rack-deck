import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
type Block = { batch_id: number; code: string; oven_id: number; oven_label: string; phase: string; start_min: number; end_min: number };
type Oven = { id: number; label: string; rack_slots: number | null; hearth_slots: number | null };
const DAY_START = 8 * 60, DAY_END = 18 * 60, SPAN = DAY_END - DAY_START;
function pct(m: number) { return ((m - DAY_START) / SPAN) * 100; }
function fmt(m: number) { const h = Math.floor(m / 60), mm = m % 60; return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`; }

type Seg = { start: number; end: number; count: number };
// 半开区间扫描线：同一时刻先收尾后开场，端点相接不重叠
function sweep(blocks: Block[]): Seg[] {
  const ev: [number, number][] = [];
  for (const b of blocks) if (b.end_min > b.start_min) { ev.push([b.start_min, 1]); ev.push([b.end_min, -1]); }
  ev.sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  const segs: Seg[] = [];
  let count = 0, prev: number | null = null;
  for (const [t, d] of ev) {
    if (prev !== null && t > prev && count > 0) segs.push({ start: prev, end: t, count });
    count += d; prev = t;
  }
  return segs;
}

export default function GanttPage() {
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [ovens, setOvens] = useState<Oven[]>([]);
  useEffect(() => {
    api<Block[]>("/gantt").then(setBlocks);
    api<Oven[]>("/ovens").then(setOvens).catch(() => setOvens([]));
  }, []);
  const capById = useMemo(() => new Map(ovens.map((o) => [o.id, o])), [ovens]);

  const rows = useMemo(() => {
    const map = new Map<number, { label: string; blocks: Block[] }>();
    for (const b of blocks) {
      if (!map.has(b.oven_id)) map.set(b.oven_id, { label: b.oven_label, blocks: [] });
      map.get(b.oven_id)!.blocks.push(b);
    }
    return [...map.entries()].map(([oid, row]) => {
      const rack = sweep(row.blocks.filter((b) => b.phase === "ferment")).filter((s) => s.count >= 2);
      const hearth = sweep(row.blocks.filter((b) => b.phase === "bake")).filter((s) => s.count >= 2);
      return { oid, ...row, rack, hearth };
    });
  }, [blocks]);

  function occMarkers(segs: Seg[], cls: string, limit: number | null | undefined) {
    return segs.map((s, i) => (
      <div
        key={i}
        className={`gantt-occ ${cls}${limit != null && s.count > limit ? " over" : ""}`}
        style={{ left: `${pct(s.start)}%`, width: `${((s.end - s.start) / SPAN) * 100}%` }}
        title={`${fmt(s.start)}–${fmt(s.end)} ${cls === "rack" ? "醒发架" : "炉膛"}占用 ${s.count}${limit != null ? ` / 上限 ${limit}` : ""}`}
      >
        {cls === "rack" ? "架" : "膛"}{s.count}
      </div>
    ));
  }

  return (<>
    <h2>甘特（生产占炉）</h2>
    <div className="axis"><div /><div className="axis-scale"><span>08:00</span><span>12:00</span><span>18:00</span></div></div>
    <div className="gantt">
      {rows.map((row) => {
        const cap = capById.get(row.oid);
        return (
          <div className="gantt-row" key={row.oid}>
            <div>
              {row.label}
              <div className="gantt-cap">醒发架 {cap?.rack_slots ?? "∞"} · 炉膛 {cap?.hearth_slots ?? "∞"}</div>
            </div>
            <div className="gantt-track">
              <div className="gantt-occ-layer top">{occMarkers(row.rack, "rack", cap?.rack_slots)}</div>
              <div className="gantt-occ-layer bottom">{occMarkers(row.hearth, "hearth", cap?.hearth_slots)}</div>
              {row.blocks.map((b, i) => (
                <div key={i} className={`gantt-block ${b.phase}`}
                  style={{ left: `${pct(b.start_min)}%`, width: `${((b.end_min - b.start_min) / SPAN) * 100}%` }}
                  title={`${b.code} ${b.phase}`}>
                  {b.code}/{b.phase === "ferment" ? "酵" : "烤"}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  </>);
}
