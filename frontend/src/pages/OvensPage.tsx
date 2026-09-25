import { useEffect, useState } from "react";
import { api } from "../api/client";
type O = { id: number; label: string; capacity_note: string; rack_slots: number | null; hearth_slots: number | null };

export default function OvensPage() {
  const [rows, setRows] = useState<O[]>([]);
  const [draft, setDraft] = useState<Record<number, { rack: string; hearth: string }>>({});
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [saving, setSaving] = useState<number | null>(null);

  function load() {
    api<O[]>("/ovens").then((os) => {
      setRows(os);
      setDraft(Object.fromEntries(
        os.map((o) => [o.id, {
          rack: o.rack_slots == null ? "" : String(o.rack_slots),
          hearth: o.hearth_slots == null ? "" : String(o.hearth_slots),
        }]),
      ));
    });
  }
  useEffect(load, []);

  async function save(o: O) {
    const d = draft[o.id] ?? { rack: "", hearth: "" };
    const rack = d.rack.trim() === "" ? null : Number(d.rack);
    const hearth = d.hearth.trim() === "" ? null : Number(d.hearth);
    if (rack != null && (!Number.isInteger(rack) || rack < 1)) { setErr("醒发架格数需为 ≥1 的整数（或留空）"); return; }
    if (hearth != null && (!Number.isInteger(hearth) || hearth < 1)) { setErr("炉膛盘数需为 ≥1 的整数（或留空）"); return; }
    setMsg(""); setErr(""); setSaving(o.id);
    try {
      const updated = await api<O>(`/ovens/${o.id}`, {
        method: "PATCH",
        body: JSON.stringify({ rack_slots: rack, hearth_slots: hearth }),
      });
      setRows((rs) => rs.map((r) => (r.id === o.id ? updated : r)));
      setMsg(`已保存：${o.label}（醒发架 ${updated.rack_slots ?? "—"} / 炉膛 ${updated.hearth_slots ?? "—"}）`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(null);
    }
  }

  return (<>
    <h2>炉位</h2>
    <p style={{ color: "var(--bake-muted)", fontSize: ".82rem", marginTop: "-.3rem" }}>
      醒发架格数管发酵段，炉膛盘数管烘烤段；两项都留空时只按时间重叠排炉。
    </p>
    {msg && <div className="ok">{msg}</div>}
    {err && <div className="err">{err}</div>}
    <table className="table">
      <thead><tr><th>标签</th><th>备注</th><th>醒发架格数</th><th>炉膛盘数</th><th></th></tr></thead>
      <tbody>
        {rows.map((o) => {
          const d = draft[o.id] ?? { rack: "", hearth: "" };
          return (
            <tr key={o.id}>
              <td>{o.label}</td>
              <td>{o.capacity_note}</td>
              <td>
                <input
                  type="number" min={1} placeholder="留空" style={{ width: 100 }}
                  value={d.rack}
                  onChange={(e) => setDraft((m) => ({ ...m, [o.id]: { ...d, rack: e.target.value } }))}
                />
              </td>
              <td>
                <input
                  type="number" min={1} placeholder="留空" style={{ width: 100 }}
                  value={d.hearth}
                  onChange={(e) => setDraft((m) => ({ ...m, [o.id]: { ...d, hearth: e.target.value } }))}
                />
              </td>
              <td><button onClick={() => save(o)} disabled={saving === o.id}>{saving === o.id ? "保存中…" : "保存"}</button></td>
            </tr>
          );
        })}
      </tbody>
    </table>
  </>);
}
