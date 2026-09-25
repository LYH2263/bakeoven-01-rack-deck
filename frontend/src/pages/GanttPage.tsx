import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
type Block = { batch_id: number; code: string; oven_id: number; oven_label: string; phase: string; start_min: number; end_min: number };
type Usage = { oven_id: number; start_min: number; end_min: number; rack_count: number; chamber_count: number; rack_slots: number | null; chamber_trays: number | null };
type Oven = { id: number; label: string; rack_slots: number | null; chamber_trays: number | null };
const DAY_START = 8 * 60, DAY_END = 18 * 60, SPAN = DAY_END - DAY_START;
function pct(m: number) { return ((m - DAY_START) / SPAN) * 100; }
export default function GanttPage() {
  const [blocks, setBlocks] = useState<Block[]>([]);
  const [usage, setUsage] = useState<Usage[]>([]);
  const [ovens, setOvens] = useState<Oven[]>([]);
  useEffect(() => {
    api<Block[]>("/gantt").then(setBlocks);
    api<Usage[]>("/usage").then(setUsage);
    api<Oven[]>("/ovens").then(setOvens);
  }, []);
  const rows = useMemo(() => {
    const map = new Map<number, { label: string; blocks: Block[]; usage: Usage[] }>();
    for (const o of ovens) map.set(o.id, { label: o.label, blocks: [], usage: [] });
    for (const b of blocks) {
      if (!map.has(b.oven_id)) map.set(b.oven_id, { label: b.oven_label, blocks: [], usage: [] });
      map.get(b.oven_id)!.blocks.push(b);
    }
    for (const u of usage) {
      if (!map.has(u.oven_id)) map.set(u.oven_id, { label: `炉位 ${u.oven_id}`, blocks: [], usage: [] });
      map.get(u.oven_id)!.usage.push(u);
    }
    return [...map.entries()];
  }, [blocks, usage, ovens]);
  return (<>
    <h2>甘特（生产占炉）</h2>
    <div className="axis"><div /><div className="axis-scale"><span>08:00</span><span>12:00</span><span>18:00</span></div></div>
    <div className="gantt">
      {rows.map(([oid, row]) => {
        const oven = ovens.find(o => o.id === oid);
        const rackSlots = oven?.rack_slots ?? row.usage[0]?.rack_slots ?? null;
        const chamberTrays = oven?.chamber_trays ?? row.usage[0]?.chamber_trays ?? null;
        return (
          <div className="gantt-row" key={oid}>
            <div>
              {row.label}
              {(rackSlots != null || chamberTrays != null) &&
                <div className="gantt-cap">架 {rackSlots ?? "∞"} · 膛 {chamberTrays ?? "∞"}</div>}
            </div>
            <div className="gantt-lane">
              <div className="gantt-track">
                {row.blocks.map((b, i) => (
                  <div key={i} className={`gantt-block ${b.phase}`}
                    style={{ left: `${pct(b.start_min)}%`, width: `${((b.end_min - b.start_min) / SPAN) * 100}%` }}
                    title={`${b.code} ${b.phase}`}>
                    {b.code}/{b.phase === "ferment" ? "酵" : "烤"}
                  </div>
                ))}
              </div>
              <div className="usage-strip">
                {row.usage.map((u, i) => {
                  if (u.end_min <= DAY_START || u.start_min >= DAY_END) return null;
                  const left = pct(Math.max(u.start_min, DAY_START));
                  const width = pct(Math.min(u.end_min, DAY_END)) - left;
                  const rackOver = u.rack_slots != null && u.rack_count > u.rack_slots;
                  const chamberOver = u.chamber_trays != null && u.chamber_count > u.chamber_trays;
                  const overlap = u.rack_count >= 2 || u.chamber_count >= 2;
                  const cls = rackOver || chamberOver ? "usage-chip over" : overlap ? "usage-chip hot" : "usage-chip";
                  return (
                    <div key={i} className={cls}
                      style={{ left: `${left}%`, width: `${Math.max(width, 4)}%` }}
                      title={`${Math.floor(u.start_min / 60)}:${String(u.start_min % 60).padStart(2, "0")} 架 ${u.rack_count}${u.rack_slots != null ? "/" + u.rack_slots : ""}，膛 ${u.chamber_count}${u.chamber_trays != null ? "/" + u.chamber_trays : ""}`}>
                      <span className={u.rack_count > 0 ? "on" : ""}>架{u.rack_count}{u.rack_slots != null ? `/${u.rack_slots}` : ""}</span>
                      <span className={u.chamber_count > 0 ? "on" : ""}>膛{u.chamber_count}{u.chamber_trays != null ? `/${u.chamber_trays}` : ""}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  </>);
}
