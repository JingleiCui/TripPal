import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpen,
  Check,
  ChevronDown,
  ExternalLink,
  Loader2,
  MapPin,
  RefreshCw,
  Trash2,
} from "lucide-react";
import { api, post } from "./api";
import { Button } from "./components/ui/button";
import { MapPanel } from "./MapPanel";
import { safeHref } from "./lib/safeUrl";
import type { Day, Stop } from "./types";
import "./note-import.css";

type Evidence = { anchor: string; quote: string };
type Fact = {
  id: string;
  kind: string;
  text: string;
  city: string;
  sources: Evidence[];
  edited?: boolean;
  original_text?: string;
  candidates: Stop[];
  place: Stop | null;
  match_city?: string;
  match_error?: string;
};
type NoteImage = {
  id: string;
  status: string;
  skip_reason?: string;
  text?: string;
  error?: string;
  tiles: { box: number[]; truncated?: boolean; unclear?: boolean }[];
};
type Note = {
  id: string;
  name: string;
  parsed: {
    status: string;
    stage?: string;
    url?: string;
    manual_body?: string;
    link_body?: string;
    body_source?: string;
    share_text?: string;
    link_status?: string;
    link_error?: string;
    error?: string;
    limit_warning?: string;
    images: NoteImage[];
    facts: Fact[];
    selected_fact_ids: string[];
    confirmed_at?: string;
    auto_adopted_at?: string;
    fact_errors?: Record<string, string>;
  };
};
type Summary = { id: string; name: string; status: string };
const labels: Record<string, string> = {
  city: "城市",
  place: "地点",
  day: "天数",
  transport: "交通",
  cost: "费用",
  tip: "提醒",
};
const states: Record<string, string> = {
  queued: "等待处理",
  running: "正在解析",
  ready: "等待核对",
  partial: "部分内容需补充",
  needs_input: "请补充正文或图片",
  error: "解析中断，可重试",
};
export const isNoteShare = (text: string) =>
  /https?:\/\/(?:www\.)?(?:xhslink\.com|xiaohongshu\.com|rednote\.com)(?:\/|\b)/i.test(
    text,
  );

export function NoteImportPanel({
  scope,
  disabled,
  autoImport,
  onAdopt,
  onAutoImportHandled,
}: {
  scope: string;
  disabled: boolean;
  autoImport: { text: string; nonce: number } | null;
  onAdopt: (id: string) => Promise<void>;
  onAutoImportHandled: () => void;
}) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false),
    [id, setId] = useState(() => sessionStorage.getItem("note-import:" + scope) || "");
  const [share, setShare] = useState(""),
    [body, setBody] = useState(""),
    [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [selected, setSelected] = useState<string[]>([]),
    [edits, setEdits] = useState<Record<string, string>>({});
  const [cities, setCities] = useState<Record<string, string>>({}),
    [highlight, setHighlight] = useState("");
  const noteQuery = useQuery({
    queryKey: ["note-import", id],
    queryFn: () => api<Note>("/note-imports/" + id),
    enabled: !!id,
    retry: false,
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.parsed.status || "") ? 2000 : false,
  });
  const library = useQuery({
    queryKey: ["note-imports"],
    queryFn: () => api<Summary[]>("/note-imports"),
    enabled: open,
  });
  const note = noteQuery.data,
    data = note?.parsed;
  const processing = ["queued", "running"].includes(data?.status || "");
  const autoAdoptKey = (noteId: string) => `note-auto-adopted:${scope}:${noteId}`;
  const autoAdopted = Boolean(
    id && (data?.auto_adopted_at || sessionStorage.getItem(autoAdoptKey(id))),
  );
  useEffect(() => {
    if (id) sessionStorage.setItem("note-import:" + scope, id);
    else sessionStorage.removeItem("note-import:" + scope);
  }, [id, scope]);
  useEffect(() => {
    setSelected(data?.selected_fact_ids || []);
    setEdits({});
    setCities({});
  }, [id, !!data]);
  useEffect(() => {
    if (noteQuery.isError) setError(noteQuery.error.message);
  }, [noteQuery.isError]);
  useEffect(() => {
    if (autoImport) {
      setOpen(true);
      setShare(autoImport.text);
      onAutoImportHandled();
      void create(autoImport.text);
    }
  }, [autoImport?.nonce]);

  // 正文已经解析完成时，不再要求人工勾选，直接把整篇笔记交给大模型继续回答。
  useEffect(() => {
    if (!id || !data || processing || busy || autoAdopted) return;
    const bodyText = (data.manual_body || data.link_body || "").trim();
    if (!bodyText || ["error", "needs_input"].includes(data.status)) return;
    sessionStorage.setItem(autoAdoptKey(id), "1");
    void adopt(true);
  }, [
    id,
    data?.status,
    data?.link_body,
    data?.manual_body,
    data?.auto_adopted_at,
    data?.facts.length,
    processing,
    busy,
    autoAdopted,
  ]);

  async function action(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function update(value: Note) {
    client.setQueryData(["note-import", value.id], value);
    setId(value.id);
    void client.invalidateQueries({ queryKey: ["note-imports"] });
  }
  async function create(text = share) {
    await action(async () => {
      const form = new FormData();
      form.append("share_text", text);
      form.append("body_text", body);
      files.forEach((f) => form.append("files", f));
      const value = await api<Note>("/note-imports", { method: "POST", body: form });
      sessionStorage.removeItem(autoAdoptKey(value.id));
      update(value);
      setBody("");
      setFiles([]);
      setSelected([]);
      setEdits({});
    });
  }
  async function supplement() {
    await action(async () => {
      const form = new FormData();
      form.append("body_text", body);
      files.forEach((f) => form.append("files", f));
      const value = await api<Note>(`/note-imports/${id}/sources`, {
        method: "POST",
        body: form,
      });
      sessionStorage.removeItem(autoAdoptKey(value.id));
      update(value);
      setBody("");
      setFiles([]);
      setSelected([]);
      setEdits({});
    });
  }
  async function retry(image_id?: string, retry_link = false, force_ocr = false) {
    await action(async () => {
      update(
        await post<Note>(`/note-imports/${id}/retry`, {
          image_id,
          retry_link,
          force_ocr,
        }),
      );
    });
  }
  const defaultCity =
    data?.facts.filter((f) => f.kind === "city").map((f) => f.text) || [];
  async function match(fact: Fact, candidate_id?: string) {
    await action(async () => {
      update(
        await post<Note>(`/note-imports/${id}/facts/${fact.id}/place`, {
          city:
            cities[fact.id] ||
            fact.match_city ||
            fact.city ||
            (defaultCity.length === 1 ? defaultCity[0] : ""),
          candidate_id,
        }),
      );
    });
  }
  const mapped = useMemo(
    () =>
      (data?.facts || [])
        .filter((f) => f.place)
        .map((f) => ({
          ...f.place!,
          photos: f.place!.photos || [],
          description: "攻略候选地点，尚未加入行程",
          planned_start: "",
          planned_end: "",
          locked: false,
        })),
    [data?.facts],
  );
  const day: Day = useMemo(
    () => ({
      day: 1,
      city: "攻略地点",
      date: "",
      stops: mapped,
      routes: [],
      known_route_walking_meters: 0,
      walking_note: "",
    }),
    [mapped],
  );
  function anchorLabel(anchor: string) {
    const parts = anchor.split(":");
    if (parts[0] === "image")
      return `图片 ${(data?.images.findIndex((i) => i.id === parts[1]) ?? -1) + 1} · 第 ${parts[2]} 段`;
    return `${parts[0] === "manual_body" ? "补充正文" : "网页正文"} · 第 ${parts[1]} 段`;
  }
  async function adopt(auto = false) {
    const chosen = auto ? (data?.facts || []).map((f) => f.id) : selected;
    await action(async () => {
      update(
        await post<Note>(`/note-imports/${id}/confirm`, {
          selected_fact_ids: chosen,
          edits: auto ? {} : edits,
          auto,
        }),
      );
      await onAdopt(id);
      setOpen(false);
    });
  }
  return (
    <section className="note-import" aria-label="小红书攻略导入">
      <button
        type="button"
        className="text-link note-import-toggle"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        <BookOpen size={16} /> 小红书攻略导入{" "}
        {processing && <Loader2 size={14} className="spin" />}
        {autoAdopted && !processing && <span className="note-auto-badge">已自动交给助手</span>}
        <ChevronDown size={14} />
      </button>
      {open && (
        <div className="note-import-content">
          <p>
            粘贴分享文案或链接，读取正文与配图；也可以直接粘贴正文、批量上传图片。解析完成后自动交给助手，无需逐项确认。
          </p>
          <label>
            小红书分享文案或链接
            <textarea
              aria-label="小红书分享文案或链接"
              value={share}
              onChange={(e) => setShare(e.target.value)}
              rows={2}
              maxLength={10000}
            />
          </label>
          <label>
            笔记正文 / 补充正文
            <textarea
              aria-label="笔记正文"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
              maxLength={200000}
              placeholder="链接不可读时，把笔记正文粘贴到这里。分享标题不等于完整正文。"
            />
          </label>
          <label>
            笔记配图（最多 20 张，单张 5 MB，总计 50 MB）
            <input
              type="file"
              aria-label="笔记配图"
              accept="image/png,image/jpeg,image/webp"
              multiple
              onChange={(e) => {
                const chosen = Array.from(e.target.files || []);
                if (
                  chosen.length > 20 ||
                  chosen.some((f) => f.size > 5 * 1024 * 1024) ||
                  chosen.reduce((n, f) => n + f.size, 0) > 50 * 1024 * 1024
                ) {
                  setError("图片超限：最多 20 张，单张 5 MB，总计 50 MB");
                  setFiles([]);
                  e.target.value = "";
                } else {
                  setFiles(chosen);
                  setError("");
                }
              }}
            />
          </label>
          {!!files.length && (
            <small>
              已选 {files.length} 张：{files.map((f) => f.name).join("、")}
            </small>
          )}
          <div className="note-actions">
            <Button
              disabled={
                busy || disabled || (!share.trim() && !body.trim() && !files.length)
              }
              onClick={() => create()}
            >
              导入为新攻略
            </Button>
            {id && (
              <Button
                variant="secondary"
                disabled={busy || processing || (!body.trim() && !files.length)}
                onClick={supplement}
              >
                补充到这篇攻略
              </Button>
            )}
          </div>
          {error && (
            <p role="alert" className="error-text">
              {error}
            </p>
          )}
          {!!library.data?.length && (
            <label>
              恢复已导入攻略
              <select
                aria-label="恢复已导入攻略"
                value={id}
                onChange={(e) => {
                  setId(e.target.value);
                  setSelected([]);
                  setEdits({});
                }}
              >
                <option value="">选择一篇攻略</option>
                {library.data.map((n) => (
                  <option key={n.id} value={n.id}>
                    {n.name} · {states[n.status] || n.status}
                  </option>
                ))}
              </select>
            </label>
          )}
          {note && data && (
            <article className="note-result">
              <header>
                <div>
                  <h3>{note.name}</h3>
                  <p role="status" aria-live="polite">
                    {states[data.status]}
                    {data.stage ? ` · ${data.stage}` : ""}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label="删除导入攻略"
                  disabled={busy}
                  onClick={() =>
                    action(async () => {
                      await api(`/note-imports/${id}`, { method: "DELETE" });
                      client.removeQueries({ queryKey: ["note-import", id] });
                      setId("");
                      void client.invalidateQueries({ queryKey: ["note-imports"] });
                    })
                  }
                >
                  <Trash2 size={16} />
                </Button>
              </header>
              {data.url && safeHref(data.url) && (
                <a href={safeHref(data.url)!} target="_blank" rel="noopener noreferrer">
                  查看原笔记 <ExternalLink size={12} />
                </a>
              )}
              {(data.link_error || data.error || data.limit_warning) && (
                <p className="note-warning" role="status">
                  {data.link_error || data.error} {data.limit_warning}
                </p>
              )}
              {!processing &&
                data.link_status &&
                ["error", "partial"].includes(data.link_status) && (
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    onClick={() => retry(undefined, true)}
                  >
                    重试读取链接
                  </Button>
                )}
              {(data.link_body || data.manual_body) && (
                <details>
                  <summary>
                    查看笔记正文
                    {data.body_source === "metadata_preview"
                      ? "（网页预览，非完整正文）"
                      : ""}
                  </summary>
                  {data.link_body && (
                    <div>
                      <h4>网页读取</h4>
                      <pre>{data.link_body}</pre>
                    </div>
                  )}
                  {data.manual_body && (
                    <div>
                      <h4>手动补充</h4>
                      <pre>{data.manual_body}</pre>
                    </div>
                  )}
                </details>
              )}
              <p>
                正文：
                {data.manual_body
                  ? "已补充"
                  : data.link_body
                    ? data.body_source === "metadata_preview"
                      ? "仅网页预览"
                      : "已读取"
                    : "尚未读取"}{" "}
                · 配图 {data.images.length} 张，其中{" "}
                {data.images.filter((i) => i.status === "skipped").length} 张已跳过
              </p>
              <div className="note-images">
                {data.images.map((image, index) => (
                  <details key={image.id}>
                    <summary>
                      图片 {index + 1} ·{" "}
                      {
                        (
                          {
                            pending: "等待识别",
                            ok: "已转写",
                            partial: "需要核对",
                            error: "识别失败",
                            skipped: "已跳过",
                          } as Record<string, string>
                        )[image.status]
                      }{" "}
                      · {image.tiles.length} 个分块
                    </summary>
                    <img
                      src={`/api/v1/note-imports/${id}/images/${image.id}`}
                      alt={`笔记原图 ${index + 1}`}
                      loading="lazy"
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                      }}
                    />
                    {image.skip_reason && <p>{image.skip_reason}，未做文字提取。</p>}
                    {image.error && <p className="note-warning">{image.error}</p>}
                    <pre>
                      {image.text || "尚无转写文字；未读取的图片不视为解析成功。"}
                    </pre>
                    {!processing && image.status !== "ok" && (
                      <Button
                        variant="secondary"
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          retry(image.id, false, image.status === "skipped")
                        }
                      >
                        <RefreshCw size={14} />{" "}
                        {image.status === "skipped"
                          ? "仍然识别这张图片"
                          : `重试图片 ${index + 1}`}
                      </Button>
                    )}
                  </details>
                ))}
              </div>
              {!!Object.keys(data.fact_errors || {}).length && (
                <p className="note-warning">
                  有 {Object.keys(data.fact_errors || {}).length}{" "}
                  段要点未提取，原文仍可查看。
                </p>
              )}
              {!processing && (
                <div className="note-actions">
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={busy}
                    onClick={() => retry()}
                  >
                    重试未完成内容
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setSelected(data.facts.map((f) => f.id))}
                  >
                    选择全部候选信息
                  </Button>
                </div>
              )}
              <p className="note-warning">
                这些是笔记作者的经验，日期、价格和营业时间尚未核实。正文已自动交给助手参考，导入不会自动改动你的行程。
              </p>
              <div className="note-facts">
                {data.facts.map((fact) => (
                  <div
                    className={`note-fact ${highlight === fact.place?.id ? "is-highlighted" : ""}`}
                    id={`note-fact-${fact.id}`}
                    key={fact.id}
                  >
                    <label>
                      <input
                        type="checkbox"
                        aria-label={`采用${fact.text}`}
                        disabled={processing || disabled}
                        checked={selected.includes(fact.id)}
                        onChange={(e) =>
                          setSelected((s) =>
                            e.target.checked
                              ? [...s, fact.id]
                              : s.filter((v) => v !== fact.id),
                          )
                        }
                      />
                      <span>{labels[fact.kind] || fact.kind} · 待核实</span>
                    </label>
                    <textarea
                      aria-label={`编辑攻略信息${fact.id}`}
                      rows={2}
                      value={edits[fact.id] ?? fact.text}
                      maxLength={1200}
                      disabled={processing || busy}
                      onChange={(e) =>
                        setEdits((v) => ({ ...v, [fact.id]: e.target.value }))
                      }
                    />
                    <details>
                      <summary>
                        查看来源
                        {fact.edited || edits[fact.id] ? "（包含人工修改）" : ""}
                      </summary>
                      {fact.sources.map((e, i) => (
                        <blockquote key={i}>
                          <small>{anchorLabel(e.anchor)}</small>
                          <p>{e.quote}</p>
                        </blockquote>
                      ))}
                    </details>
                    {fact.kind === "place" && !processing && (
                      <div className="note-place-match">
                        <label>
                          匹配城市
                          <input
                            aria-label={`匹配城市${fact.id}`}
                            value={
                              cities[fact.id] ?? fact.match_city ?? fact.city ?? ""
                            }
                            placeholder={defaultCity[0] || "请输入城市"}
                            onChange={(e) =>
                              setCities((c) => ({ ...c, [fact.id]: e.target.value }))
                            }
                          />
                        </label>
                        <Button
                          variant="secondary"
                          size="sm"
                          disabled={busy || !!edits[fact.id]}
                          onClick={() => match(fact)}
                        >
                          <MapPin size={14} /> 查询地图地点
                        </Button>
                        {fact.match_error && <small>{fact.match_error}</small>}
                        {fact.candidates.map((place) => (
                          <button
                            className="note-place-choice"
                            type="button"
                            key={place.id}
                            disabled={busy}
                            onClick={() => match(fact, place.id)}
                          >
                            {fact.place?.id === place.id && <Check size={14} />}{" "}
                            {place.name} · {place.address || fact.match_city}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
              {!!mapped.length && (
                <>
                  <p>
                    已匹配 {mapped.length}{" "}
                    个攻略候选地点，右侧地图可预览；尚未写入行程。
                  </p>
                  <MapPanel
                    kind="explore"
                    viewKey={`note:${id}`}
                    day={day}
                    fixture={false}
                    highlightId={highlight}
                    onSelect={(stop) => {
                      setHighlight(stop.id);
                      const fact = data.facts.find((f) => f.place?.id === stop.id);
                      if (fact)
                        document
                          .getElementById(`note-fact-${fact.id}`)
                          ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
                    }}
                  />
                </>
              )}
              <Button
                variant="secondary"
                disabled={busy || processing || disabled}
                onClick={() => void adopt(false)}
              >
                {busy ? <Loader2 size={15} className="spin" /> : <Check size={15} />}{" "}
                重新交给助手
              </Button>
            </article>
          )}
        </div>
      )}
    </section>
  );
}
