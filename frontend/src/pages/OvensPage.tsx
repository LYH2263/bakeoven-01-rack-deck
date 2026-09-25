import { useEffect, useState } from "react";
import { api } from "../api/client";
type O = { id: number; label: string; capacity_note: string; rack_slots: number | null; chamber_trays: number | null };
type Field = number | "";
export default function OvensPage() {
  const [rows, setRows] = useState<O[]>([]);
  const [draft, setDraft] = useState<Record<number, { rack: Field; chamber: Field }>>({});
  const [saving, setSaving] = useState<number | null>(null);
  const [note, setNote] = useState<{ id: number; ok: boolean; text: string } | null>(null);
  const load = () => api<O[]>("/ovens").then(os => {
    setRows(os);
    setDraft(Object.fromEntries(os.map(o => [o.id, { rack: o.rack_slots ?? "", chamber: o.chamber_trays ?? "" }])));
  });
  useEffect(() => { load(); }, []);
  function edit(id: number, key: "rack" | "chamber", raw: string) {
    if (raw === "") { setDraft(d => ({ ...d, [id]: { ...d[id], [key]: "" } })); return; }
    const v = Math.max(1, Math.floor(Number(raw) || 1));
    setDraft(d => ({ ...d, [id]: { ...d[id], [key]: v } }));
  }
  async function save(o: O) {
    const d = draft[o.id];
    if (!d) return;
    setSaving(o.id); setNote(null);
    try {
      await api<O>(`/ovens/${o.id}`, {
        method: "PUT",
        body: JSON.stringify({
          rack_slots: d.rack === "" ? null : d.rack,
          chamber_trays: d.chamber === "" ? null : d.chamber,
        }),
      });
      setNote({ id: o.id, ok: true, text: "已保存" });
      await load();
    } catch (e) {
      setNote({ id: o.id, ok: false, text: e instanceof Error ? e.message : String(e) });
    } finally { setSaving(null); }
  }
  return (<>
    <h2>炉位</h2>
    <p style={{ color: "var(--bake-muted)", fontSize: ".82rem", marginTop: 0 }}>
      醒发架与炉膛分开计容：发酵段只占架、烘烤段只占膛。两项都留空时只按时间重叠排炉。
    </p>
    <table className="table">
      <thead><tr><th>标签</th><th>备注</th><th>醒发架格数</th><th>炉膛盘数</th><th></th></tr></thead>
      <tbody>{rows.map(o => {
        const d = draft[o.id] ?? { rack: "", chamber: "" };
        const changed = (o.rack_slots ?? "") !== d.rack || (o.chamber_trays ?? "") !== d.chamber;
        return (
          <tr key={o.id}>
            <td>{o.label}</td>
            <td>{o.capacity_note}</td>
            <td><input type="number" min={1} style={{ width: 100 }}
              placeholder="留空不限" value={d.rack}
              onChange={e => edit(o.id, "rack", e.target.value)} /></td>
            <td><input type="number" min={1} style={{ width: 100 }}
              placeholder="留空不限" value={d.chamber}
              onChange={e => edit(o.id, "chamber", e.target.value)} /></td>
            <td>
              <button disabled={!changed || saving === o.id} onClick={() => save(o)}>
                {saving === o.id ? "保存中…" : "保存"}
              </button>
              {note && note.id === o.id &&
                <span style={{ marginLeft: 8, fontSize: ".8rem" }} className={note.ok ? "ok" : "err"}>{note.text}</span>}
            </td>
          </tr>
        );
      })}</tbody>
    </table>
  </>);
}
