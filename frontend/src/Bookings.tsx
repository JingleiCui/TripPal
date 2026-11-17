import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, FileText, Loader2, Plus, Trash2, Upload, X } from "lucide-react";
import { api, post } from "./api";
import { Button } from "./components/ui/button";

type Booking = {
  id: string;
  kind: string;
  title: string;
  start: string;
  end: string | null;
  location: string;
  reference: string;
  note: string;
  document_id: string | null;
};
const kinds: Record<string, string> = {
  hotel: "住宿",
  flight: "航班",
  train: "火车",
  activity: "活动与门票",
  other: "其他安排",
};
const newBooking = (): Omit<Booking, "id"> => ({
  kind: "hotel",
  title: "",
  start: "",
  end: null,
  location: "",
  reference: "",
  note: "",
  document_id: null,
});

export function BookingManager({ tripId }: { tripId: string }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false),
    [editing, setEditing] = useState<Partial<Booking> | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const items = useQuery({
    queryKey: ["bookings", tripId],
    queryFn: () => api<Booking[]>(`/trips/${tripId}/bookings`),
    enabled: open,
  });
  const docs = useQuery({
    queryKey: ["documents"],
    queryFn: () => api<{ id: string; name: string; status: string }[]>("/documents"),
    enabled: open,
  });
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError("");
    try {
      const body = {
        ...editing,
        end: editing.end || null,
        document_id: editing.document_id || null,
      };
      if (editing.id)
        await api("/bookings/" + editing.id, {
          method: "PUT",
          body: JSON.stringify(body),
        });
      else await post(`/trips/${tripId}/bookings`, body);
      await client.invalidateQueries({ queryKey: ["bookings", tripId] });
      setEditing(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: string) {
    setBusy(true);
    setError("");
    try {
      await api("/bookings/" + id, { method: "DELETE" });
      await client.invalidateQueries({ queryKey: ["bookings", tripId] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function upload(file: File | undefined) {
    if (!file || !editing) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await api<{ id: string }>("/documents", {
        method: "POST",
        body: form,
      });
      setEditing((old) => ({ ...old, document_id: result.id }));
      await client.invalidateQueries({ queryKey: ["documents"] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => {
          setOpen(true);
          setError("");
        }}
      >
        <CalendarDays size={15} />
        订单与凭证
      </Button>
      {open && (
        <div className="modal-scrim" onClick={() => !busy && setOpen(false)}>
          <section
            className="modal bookings-modal"
            role="dialog"
            aria-modal="true"
            aria-label="旅行订单与凭证"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="modal-close"
              aria-label="关闭订单与凭证"
              onClick={() => setOpen(false)}
            >
              <X size={20} />
            </button>
            <span className="eyebrow">旅行信息，放在一起</span>
            <h2>订单与旅行凭证</h2>
            <p className="booking-intro">
              记录已安排的住宿、交通和活动，关联你的确认单。内容仅自己可见，不会出现在分享路书中；此处不会代你预订或付款。时间按目的地当地时间填写。
            </p>
            {(error || items.error || docs.error) && (
              <p role="alert" className="notice error">
                {error || items.error?.message || docs.error?.message}
              </p>
            )}
            {editing ? (
              <form onSubmit={submit} className="booking-form">
                <div className="form-row">
                  <label>
                    安排类型
                    <select
                      value={editing.kind}
                      onChange={(e) => setEditing({ ...editing, kind: e.target.value })}
                    >
                      {Object.entries(kinds).map(([k, v]) => (
                        <option value={k} key={k}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    安排名称
                    <input
                      required
                      maxLength={150}
                      value={editing.title || ""}
                      onChange={(e) =>
                        setEditing({ ...editing, title: e.target.value })
                      }
                      placeholder="例如：北京三晚住宿"
                    />
                  </label>
                </div>
                <div className="form-row">
                  <label>
                    开始时间
                    <input
                      type="datetime-local"
                      required
                      value={editing.start?.slice(0, 16) || ""}
                      onChange={(e) =>
                        setEditing({ ...editing, start: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    结束时间（可选）
                    <input
                      type="datetime-local"
                      min={editing.start?.slice(0, 16)}
                      value={editing.end?.slice(0, 16) || ""}
                      onChange={(e) => setEditing({ ...editing, end: e.target.value })}
                    />
                  </label>
                </div>
                <label>
                  地址或路线
                  <input
                    maxLength={300}
                    value={editing.location || ""}
                    onChange={(e) =>
                      setEditing({ ...editing, location: e.target.value })
                    }
                    placeholder="例如：北京南站 → 上海虹桥站"
                  />
                </label>
                <label>
                  确认号（可选）
                  <input
                    maxLength={100}
                    value={editing.reference || ""}
                    onChange={(e) =>
                      setEditing({ ...editing, reference: e.target.value })
                    }
                  />
                </label>
                <label>
                  备注
                  <textarea
                    rows={2}
                    maxLength={2000}
                    value={editing.note || ""}
                    onChange={(e) => setEditing({ ...editing, note: e.target.value })}
                  />
                </label>
                <div className="booking-attachment">
                  <label>
                    关联已有凭证
                    <select
                      aria-label="关联已有凭证"
                      value={editing.document_id || ""}
                      onChange={(e) =>
                        setEditing({ ...editing, document_id: e.target.value })
                      }
                    >
                      <option value="">暂不关联</option>
                      {docs.data
                        ?.filter((d) => d.status !== "deleted")
                        .map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label className="booking-upload">
                    <Upload size={15} />
                    上传确认单
                    <input
                      aria-label="上传订单凭证"
                      type="file"
                      accept=".txt,.md,.pdf,.docx"
                      disabled={busy}
                      onChange={(e) => {
                        upload(e.target.files?.[0]);
                        e.target.value = "";
                      }}
                    />
                  </label>
                </div>
                <small>
                  支持文本、PDF、Word（不超过 5
                  MB）。图片和扫描件暂不能识别，请手动填写关键信息。
                </small>
                <div className="booking-form-actions">
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={busy}
                    onClick={() => setEditing(null)}
                  >
                    返回安排列表
                  </Button>
                  <Button disabled={busy}>
                    {busy && <Loader2 className="spin" size={15} />}保存安排
                  </Button>
                </div>
              </form>
            ) : (
              <>
                <div className="booking-list">
                  {items.isPending ? (
                    <p role="status">正在打开旅行安排…</p>
                  ) : !items.data?.length ? (
                    <div className="booking-empty">
                      <CalendarDays size={32} />
                      <h3>还没有记录已安排的事项</h3>
                      <p>把酒店确认单、车次或活动时间整理在这里。</p>
                    </div>
                  ) : (
                    items.data.map((b) => (
                      <article className="booking-row" key={b.id}>
                        <span className="booking-kind">{kinds[b.kind]}</span>
                        <div>
                          <h3>{b.title}</h3>
                          <p>
                            {b.start.replace("T", " ").slice(0, 16)}
                            {b.end ? " — " + b.end.replace("T", " ").slice(0, 16) : ""}
                          </p>
                          {b.location && <p>{b.location}</p>}
                          {b.reference && <p>确认号：{b.reference}</p>}
                          {b.note && <p className="booking-note">{b.note}</p>}
                          {b.document_id && (
                            <a
                              className="text-link"
                              href={`/api/v1/documents/${b.document_id}/original`}
                            >
                              <FileText size={13} />
                              查看原始凭证
                            </a>
                          )}
                        </div>
                        <div className="booking-row-actions">
                          <button
                            className="text-link"
                            onClick={() => {
                              setEditing(b);
                              setError("");
                            }}
                          >
                            编辑
                          </button>
                          <button
                            aria-label={"移除安排" + b.title}
                            disabled={busy}
                            onClick={() => remove(b.id)}
                          >
                            <Trash2 size={15} />
                          </button>
                        </div>
                      </article>
                    ))
                  )}
                </div>
                <Button
                  onClick={() => {
                    setEditing(newBooking());
                    setError("");
                  }}
                >
                  <Plus size={16} />
                  添加已安排事项
                </Button>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}
