import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Compass,
  MessageSquare,
  Send,
  Map,
  Plus,
  Loader2,
  Check,
  ArrowRight,
  RefreshCw,
  Users,
  X,
  Star,
  Paperclip,
} from "lucide-react";
import { api, post } from "./api";
import { Button } from "./components/ui/button";
import { TripalMark } from "./components/TripalLogo";
import { BookingManager } from "./Bookings";
import { TripExperience } from "./TripExperience";
import { HotelSelector } from "./HotelSelector";
import { VoiceControls } from "./VoiceControls";
import { NoteImportPanel, isNoteShare } from "./NoteImportPanel";
import type { Plan, Trip, Attachment, ScreenshotFacts, Health } from "./types";
import { capture } from "./AccountLifecycle";
import { type DiscoveryPlace } from "./Discovery";
import { useWorkspaceState, writeWorkspace, isWorkspaceActive } from "./lib/workspace";

function isScreenshot(parsed: unknown): parsed is ScreenshotFacts {
  if (!parsed || typeof parsed !== "object") return false;
  const status = (parsed as { status?: unknown }).status;
  return (
    status === "ok" ||
    status === "synthetic" ||
    status === "unavailable" ||
    status === "error"
  );
}

/** 未识别成功的截图不产生可交给助手的内容，按钮保持禁用。 */
function canAdopt(att: Attachment) {
  if (!isScreenshot(att.parsed)) return true;
  return att.parsed.status === "ok" || att.parsed.status === "synthetic";
}

function ScreenshotFactsView({ parsed }: { parsed: ScreenshotFacts }) {
  if (parsed.status === "unavailable" || parsed.status === "error") {
    return (
      <div className="screenshot-gap" role="status">
        {parsed.error || parsed.note || "截图内容未被识别，请手动录入关键信息。"}
      </div>
    );
  }
  const f = parsed.fields;
  const chips: { label: string; value: string }[] = [];
  if (f?.cities?.length) chips.push({ label: "目的地", value: f.cities.join("、") });
  if (f?.dates?.length) chips.push({ label: "日期", value: f.dates.join("、") });
  if (f?.places?.length)
    chips.push({ label: "想去的地方", value: f.places.join("、") });
  if (f?.days) chips.push({ label: "天数", value: f.days });
  if (f?.budget_text) chips.push({ label: "预算 / 价格", value: f.budget_text });
  if (f?.notes?.length) chips.push({ label: "备注", value: f.notes.join("、") });
  return (
    <div className="screenshot-facts">
      <div className="screenshot-head">
        <span
          className={
            parsed.synthetic ? "screenshot-badge synthetic" : "screenshot-badge"
          }
        >
          {parsed.synthetic ? "合成演示识别" : "截图识别 · 待核实"}
        </span>
        <small>识别内容不会自动写入行程</small>
      </div>
      {chips.length > 0 ? (
        <ul className="screenshot-chips">
          {chips.map((chip) => (
            <li key={chip.label}>
              <span>{chip.label}</span>
              {chip.value}
            </li>
          ))}
        </ul>
      ) : (
        <p className="screenshot-gap">图中未识别到可用的旅行信息，请手动补充。</p>
      )}
      {!!parsed.unknowns?.length && (
        <small className="screenshot-unknowns">
          未识别：{parsed.unknowns.join("、")}
        </small>
      )}
      {f?.raw_text && (
        <details className="screenshot-raw">
          <summary>查看图中文字摘录</summary>
          <p>{f.raw_text}</p>
        </details>
      )}
    </div>
  );
}

type ChatMessage = {
  id: number;
  role: string;
  content: string;
  meta: { task_id?: string; question_key?: string; status?: string };
};
type Conversation = {
  id: string;
  version: number;
  trip_id: string | null;
  slots: Record<string, unknown>;
  state: { task_id?: string; fixture: boolean };
  messages: ChatMessage[];
  task: {
    id: string;
    status: string;
    result: {
      variants?: Record<string, Plan>;
      base_version?: number;
      error?: string;
      draft_revision?: number;
      requested_count?: number;
      missing_variant_reason?: string;
    };
  } | null;
};

export function ConversationWorkspace({ accountId }: { accountId: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [activeId, setActiveId] = useWorkspaceState<string | null>(
    accountId + ":active",
    null,
  );
  const conversationId = searchParams.has("new")
    ? undefined
    : searchParams.get("conversation") || activeId || undefined;
  const sessionKey = accountId + ":" + (conversationId || "new");
  const preview = true;
  const [contextPlace, setContextPlace] = useWorkspaceState<DiscoveryPlace | null>(
    sessionKey + ":place",
    null,
  );
  const client = useQueryClient();
  const [noteAutoImport, setNoteAutoImport] = useState<{
    text: string;
    nonce: number;
  } | null>(null);
  const [input, setInput] = useWorkspaceState(sessionKey + ":input", "");
  const [compare, setCompare] = useWorkspaceState(sessionKey + ":compare", false);
  const [fixture, setFixture] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [streamed, setStreamed] = useState<Record<string, string>>({});
  const [variant, setVariant] = useWorkspaceState(sessionKey + ":variant", "A");
  const [dayIndex, setDayIndex] = useWorkspaceState(sessionKey + ":day", 0);
  const recent = useQuery({
    queryKey: ["conversations"],
    queryFn: () =>
      api<{ id: string; slots: { destination?: string }; status?: string }[]>(
        "/conversations",
      ),
  });
  useEffect(() => {
    if (searchParams.has("new")) {
      setActiveId("");
      setInput("");
      setContextPlace(null);
      setCompare(false);
      setFixture(false);
      setSearchParams(
        (old) => {
          const next = new URLSearchParams(old);
          next.delete("new");
          next.delete("conversation");
          next.delete("assistant");
          return next;
        },
        { replace: true },
      );
    } else {
      if (searchParams.get("conversation"))
        setActiveId(searchParams.get("conversation")!);
    }
  }, [searchParams.toString()]);
  useEffect(() => {
    if (
      activeId === null &&
      !searchParams.has("new") &&
      !searchParams.has("conversation") &&
      recent.data?.length
    ) {
      setActiveId(recent.data[0].id);
    }
  }, [recent.data, activeId]);
  const bottom = useRef<HTMLDivElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [attachments, setAttachments] = useWorkspaceState<Attachment[]>(
    sessionKey + ":attachments",
    [],
  );
  const [attaching, setAttaching] = useState(false),
    [attachError, setAttachError] = useState("");
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<Health>("/health"),
  });
  const visionHint =
    health.data?.vision_status === "synthetic_fixture"
      ? "截图识别：合成演示，结果不代表真实识别"
      : health.data?.vision_status === "configured_not_verified"
        ? "截图识别：已配置，待真实服务联调"
        : "截图识别：未启用，上传后会提示手动录入";
  const [stageVariants, setStageVariants] = useState<
      Record<string, Record<string, Plan>>
    >({}),
    [stages, setStages] = useState<Record<string, string>>({});
  const conversation = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => api<Conversation>("/conversations/" + conversationId),
    enabled: !!conversationId,
    // SSE 推送 token/stage，轮询仅作断线兜底；后台标签页不轮询。
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.task?.status || "") &&
      !document.hidden
        ? 3000
        : false,
  });
  const conv = conversation.data,
    tripId = conv?.trip_id;
  const trip = useQuery({
    queryKey: ["trip", tripId],
    queryFn: () => api<Trip>("/trips/" + tripId),
    enabled: !!tripId,
  });
  useEffect(() => {
    if (!tripId || !trip.data?.plan?.days) return;
    const key = "travel-open:" + tripId;
    if (!sessionStorage.getItem(key)) {
      sessionStorage.setItem(key, "1");
      void post(`/trips/${tripId}/feedback`, {
        event_type: "trip_opened",
        request_key: crypto.randomUUID(),
      });
    }
  }, [tripId, !!trip.data?.plan?.days]);
  const waiting = conv?.task?.status === "waiting_choice";
  const running = ["queued", "running"].includes(conv?.task?.status || "");
  const staged = waiting
    ? conv.task?.result?.variants
    : running
      ? stageVariants[conv?.task?.id || ""]
      : undefined;
  useEffect(() => {
    if (waiting && staged && !staged[variant])
      setVariant(Object.keys(staged)[0] || "A");
  }, [conv?.task?.id, waiting, !!staged?.[variant]]);
  const stage = stages[conv?.task?.id || ""];
  const plan = (staged?.[variant] ||
    (trip.data?.plan?.days ? trip.data.plan : null)) as Plan | null;
  const editable = !trip.data?.role || ["owner", "editor"].includes(trip.data.role);
  useEffect(() => {
    setStreamed({});
    setStageVariants({});
    setStages({});
    setError("");
  }, [conversationId]);
  useEffect(() => {
    if (conv?.state?.fixture !== undefined) setFixture(conv.state?.fixture);
  }, [conv?.state?.fixture]);
  useEffect(() => {
    if (!conversationId) return;
    const stream = new EventSource(`/api/v1/conversations/${conversationId}/events`);
    stream.addEventListener("message", () =>
      client.invalidateQueries({ queryKey: ["conversation", conversationId] }),
    );
    stream.addEventListener("token", (e) => {
      const value = JSON.parse((e as MessageEvent).data);
      setStreamed((old) => ({
        ...old,
        [value.task_id + ":" + (value.variant || "")]:
          (old[value.task_id + ":" + (value.variant || "")] || "") + value.delta,
      }));
    });
    stream.addEventListener("reset", (e) => {
      const value = JSON.parse((e as MessageEvent).data);
      setStreamed((old) => ({
        ...old,
        [value.task_id + ":" + (value.variant || "")]: "",
      }));
    });
    stream.addEventListener("variant", (e) => {
      const value = JSON.parse((e as MessageEvent).data);
      setStageVariants((old) => ({
        ...old,
        [value.task_id]: { ...old[value.task_id], [value.variant]: value.plan },
      }));
    });
    stream.addEventListener("stage", (e) => {
      const value = JSON.parse((e as MessageEvent).data);
      setStages((old) => ({ ...old, [value.task_id]: value.name }));
    });
    return () => stream.close();
  }, [conversationId]);
  useEffect(() => {
    if (conv?.task?.status === "completed") {
      client.invalidateQueries({ queryKey: ["trip", tripId] });
      client.invalidateQueries({ queryKey: ["trips"] });
    }
    client.invalidateQueries({ queryKey: ["conversations"] });
  }, [conv?.task?.status, tripId]);
  useEffect(() => {
    const history = bottom.current?.parentElement;
    history?.scrollTo({ top: history.scrollHeight, behavior: "smooth" });
  }, [conv?.messages?.length, streamed]);
  async function send(
    content = input,
    regenerate = false,
    attachmentIds: string[] = [],
  ) {
    if (!content.trim() || busy || running || (conversationId && !conv)) return;
    if (isNoteShare(content) && !attachmentIds.length) {
      setNoteAutoImport({ text: content, nonce: Date.now() });
      return;
    }
    setBusy(true);
    setError("");
    try {
      let current = conv;
      if (!current) {
        current = await post<Conversation>("/conversations", { fixture });
        void capture("conversation_started");
      }
      if (!isWorkspaceActive(accountId)) return;
      // Retain the newly created conversation even if the first turn fails.
      if (!conversationId) {
        client.setQueryData(["conversation", current.id], current);
        writeWorkspace(accountId + ":" + current.id + ":input", input);
        writeWorkspace(accountId + ":" + current.id + ":place", contextPlace);
        writeWorkspace(accountId + ":" + current.id + ":compare", compare);
        setActiveId(current.id);
        setSearchParams(
          (old) => {
            const next = new URLSearchParams(old);
            next.set("conversation", current!.id);
            return next;
          },
          { replace: true },
        );
      }
      const outgoing = contextPlace
        ? `${content}\n参考地点：${contextPlace.name}；城市：${contextPlace.city || "待确认"}；地点 ID：${contextPlace.id}；地址：${contextPlace.address || "待核实"}。`
        : content;
      const updated = await post<Conversation>(`/conversations/${current.id}/turns`, {
        content: outgoing,
        version: current.version,
        request_key: crypto.randomUUID(),
        plan_now: regenerate,
        compare,
        regenerate,
        attachment_ids: attachmentIds,
        ...(waiting
          ? {
              draft_task_id: conv?.task?.id,
              draft_variant: variant,
              draft_revision: conv?.task?.result.draft_revision || 1,
            }
          : {}),
      });
      if (!isWorkspaceActive(accountId)) return;
      client.setQueryData(["conversation", current.id], updated);
      writeWorkspace(accountId + ":" + current.id + ":input", "");
      writeWorkspace(accountId + ":" + current.id + ":place", null);
      setInput("");
      setContextPlace(null);
      if (updated.state.task_id) void capture("plan_requested");

      client.invalidateQueries({ queryKey: ["conversations"] });
    } catch (e) {
      setError((e as Error).message);
      if (attachmentIds.length) throw e;
    } finally {
      setBusy(false);
    }
  }
  async function choose(label: string) {
    if (!conv?.task) return;
    setBusy(true);
    try {
      await post(`/tasks/${conv.task.id}/variants/${label}`, {
        base_version: conv.task.result.base_version,
        draft_revision: conv.task.result.draft_revision || 1,
      });
      void capture("plan_selected");
      await client.invalidateQueries({
        queryKey: ["conversation", conversationId],
      });
      await client.invalidateQueries({ queryKey: ["trip", tripId] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function uploadAttachment(file: File) {
    setAttaching(true);
    setAttachError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const att = await api<Attachment>("/attachments", {
        method: "POST",
        body: form,
      });
      setAttachments((old) => [att, ...old]);
    } catch (e) {
      setAttachError((e as Error).message);
    } finally {
      setAttaching(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }
  function adoptAttachment(att: Attachment) {
    void send(att.suggestion);
    setAttachments((old) => old.filter((a) => a.id !== att.id));
  }
  const messages = conv?.messages || [
    {
      id: 0,
      role: "assistant",
      content:
        "想去哪里、玩几天？从一句话开始，我会记住已确认的条件，每次只问一个问题。",
      meta: {},
    },
  ];
  return (
    <div className="planning-workspace">
      <aside
        id="travel-assistant"
        aria-label="AI 旅行助手"
        className="assistant-drawer"
      >
        <div className="assistant-drawer-heading">
          <div>
            <b>{String(conv?.slots?.destination || "这次旅行")} · AI 助手</b>
            <small role="status">
              {running
                ? "正在生成 · 可继续浏览"
                : waiting
                  ? "草稿已自动保存 · 待确认"
                  : trip.data?.version
                    ? "正式行程已保存"
                    : "说说旅行想法，方案会出现在右侧"}
            </small>
          </div>
        </div>
        <div className="assistant-session-tools">
          <select
            aria-label="切换旅行对话"
            value={conversationId || ""}
            onChange={(e) => {
              const next = new URLSearchParams(searchParams);
              next.set("conversation", e.target.value);
              setSearchParams(next);
              document
                .querySelector<HTMLTextAreaElement>('[aria-label="旅行对话输入"]')
                ?.focus();
            }}
          >
            <option value="" disabled>
              当前新对话
            </option>
            {(recent.data || []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.slots.destination || "尚未确定目的地"} ·{" "}
                {(
                  {
                    waiting_choice: "待确认",
                    running: "生成中",
                    queued: "生成中",
                    completed: "已确认",
                  } as Record<string, string>
                )[item.status || ""] || "讨论中"}
              </option>
            ))}
          </select>
          <Button
            variant="secondary"
            size="sm"
            disabled={busy}
            onClick={() => {
              setActiveId("");
              writeWorkspace(accountId + ":new:input", "");
              writeWorkspace(accountId + ":new:place", null);
              setSearchParams({ new: "1", assistant: "open" });
            }}
          >
            <Plus size={14} />
            新对话
          </Button>
        </div>
        {error && (
          <div role="alert" className="notice error">
            {error}
          </div>
        )}
        {conversation.isError && (
          <div role="alert" className="notice error">
            {conversation.error.message}
            <button onClick={() => void conversation.refetch()}>重新加载对话</button>
          </div>
        )}
        <section className="card conversation-chat">
          <header>
            <MessageSquare size={17} />
            <b>旅行对话</b>
            {fixture && <span className="status-pill">合成资料体验</span>}
          </header>
          <div className="chat-history">
            {conversationId && conversation.isPending && (
              <p role="status">正在恢复旅行对话…</p>
            )}
            {messages.map((message) => (
              <div className={"chat-message " + message.role} key={message.id}>
                <span className="chat-avatar">
                  {message.role === "user" ? "你" : <TripalMark size={20} />}
                </span>
                <div>{message.content}</div>
              </div>
            ))}
            {Object.entries(streamed)
              .filter(
                ([id, text]) =>
                  text &&
                  !messages.some(
                    (m) => id.startsWith(m.meta.task_id + ":") && m.meta.status,
                  ),
              )
              .map(([id, text]) => (
                <div className="chat-message assistant" key={id}>
                  <span className="chat-avatar">
                    <TripalMark size={20} />
                  </span>
                  <div aria-live="polite" aria-label="正在生成的回复">
                    {text}
                    <span className="typing-cursor" aria-hidden="true" />
                  </div>
                </div>
              ))}
            {(busy || running) && (
              <div className="chat-activity">
                <Loader2 className="spin" size={14} />
                {busy
                  ? "正在理解你的条件…"
                  : stage
                    ? `执行阶段：${stage}`
                    : "正在调查、编排并检查行程…"}
              </div>
            )}
            {conv?.task?.result?.error && (
              <div className="notice error">{conv.task.result.error}</div>
            )}
            {conv?.task?.status === "waiting_input" && (
              <div className="notice">
                行程条件存在需要确认的取舍。
                <Link to={"/trips/" + tripId}>打开详情继续处理 →</Link>
              </div>
            )}
            {plan && (
              <div className="assistant-plan-summary" role="status">
                <b>
                  {waiting
                    ? `已准备 ${Object.keys(staged || {}).length} 个方案`
                    : running
                      ? "草稿正在更新"
                      : "查看已保存行程"}
                </b>
                {conv?.task?.result.missing_variant_reason && (
                  <p>{conv.task.result.missing_variant_reason}</p>
                )}
                {running && compare && (
                  <p>A、B 方案完成后会分别显示；你可以继续探索。</p>
                )}
                <small>方案已显示在预览区，可继续聊天调整。</small>
              </div>
            )}
            <div ref={bottom} />
          </div>
          <div className="known-slots">
            {Object.entries(conv?.slots || {})
              .filter(
                ([key, value]) =>
                  [
                    "destination",
                    "duration",
                    "start_location",
                    "needs_accommodation",
                  ].includes(key) &&
                  value !== null &&
                  value !== "",
              )
              .map(([key, value]) => (
                <span key={key}>
                  {
                    (
                      {
                        destination: "目的地",
                        duration: "时长",
                        start_location: "出发",
                        needs_accommodation: "住宿",
                      } as Record<string, string>
                    )[key]
                  }
                  ：
                  {key === "needs_accommodation"
                    ? value
                      ? "需要"
                      : "已安排／不需要"
                    : String(value) === "declined"
                      ? "已跳过"
                      : String(value).replace(/(\d+)\s*days?/gi, "$1 天")}
                </span>
              ))}
          </div>
          <div className="conversation-input">
            {contextPlace && (
              <div className="assistant-place-context">
                <span>参考地点：{contextPlace.name}</span>
                <button aria-label="移除参考地点" onClick={() => setContextPlace(null)}>
                  <X size={14} />
                </button>
              </div>
            )}
            {waiting && <small>可以继续说哪里需要调整，满意后再确认。</small>}
            <label className="check-label">
              <input
                type="checkbox"
                checked={compare}
                onChange={(e) => setCompare(e.target.checked)}
                disabled={running || busy}
              />
              给我两个不同方案供选择
            </label>
            {!conversationId && (
              <label className="check-label">
                <input
                  type="checkbox"
                  checked={fixture}
                  onChange={(e) => setFixture(e.target.checked)}
                />
                使用合成资料体验（不调用模型和真实平台）
              </label>
            )}
            <div className="attachment-row">
              <input
                ref={fileInput}
                type="file"
                accept=".txt,.md,.pdf,.docx,.gpx,.json,.png,.jpg,.jpeg,.webp"
                hidden
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) void uploadAttachment(f);
                }}
              />
              <button
                type="button"
                className="text-link attachment-add"
                disabled={running || busy || attaching}
                onClick={() => fileInput.current?.click()}
              >
                <Paperclip size={15} />
                {attaching ? "正在识别附件…" : "添加附件（订单 / 轨迹 / 旅行截图）"}
              </button>
              {attachError && <small className="error-text">{attachError}</small>}
              <small className="input-channel-hint">{visionHint}</small>
            </div>
            {attachments.length > 0 && (
              <div className="attachment-cards">
                {attachments.map((att) => (
                  <article className="attachment-card" key={att.id}>
                    <div className="attachment-card-head">
                      <b>{att.name}</b>
                      <small>{att.kind}</small>
                    </div>
                    {att.kind === "screenshot" && isScreenshot(att.parsed) && (
                      <ScreenshotFactsView parsed={att.parsed} />
                    )}
                    <p>{att.suggestion}</p>
                    <div className="attachment-actions">
                      <Button
                        size="sm"
                        disabled={busy || running || !canAdopt(att)}
                        onClick={() => adoptAttachment(att)}
                      >
                        {att.kind === "screenshot"
                          ? "把识别结果交给助手"
                          : "把建议交给助手"}
                      </Button>
                      <button
                        className="text-link"
                        onClick={() =>
                          setAttachments((old) => old.filter((a) => a.id !== att.id))
                        }
                      >
                        忽略
                      </button>
                    </div>
                  </article>
                ))}
              </div>
            )}
            <NoteImportPanel
              key={accountId + ":notes"}
              scope={accountId + ":notes"}
              disabled={busy || running || !editable || (!!conversationId && !conv)}
              autoImport={noteAutoImport}
              onAutoImportHandled={() => setNoteAutoImport(null)}
              onAdopt={async (id) => {
                await send(
                  "我已导入一篇小红书攻略，请直接阅读附件中的笔记正文、配图转写和候选要点，概括这份攻略并给出可执行的旅行建议；作者的日期、价格和营业时间只作参考，不要当成我的硬性条件。若缺少出游城市、天数或出行人数，再简要问我。",
                  false,
                  [id],
                );
              }}
            />
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send();
              }}
            >
              <textarea
                aria-label="旅行对话输入"
                maxLength={4000}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="比如：想去北京玩三天，喜欢博物馆，直接规划"
                rows={4}
              />
              <div className="planning-composer-actions">
                <VoiceControls
                  onTranscript={(text) =>
                    setInput((old) => (old.trim() ? `${old.trim()}\n${text}` : text))
                  }
                  disabled={busy || running || !editable || (!!conversationId && !conv)}
                />
                <Button
                  title="发送旅行对话"
                  aria-label="发送旅行对话"
                  disabled={
                    busy ||
                    running ||
                    !editable ||
                    (!!conversationId && !conv) ||
                    !input.trim()
                  }
                >
                  <Send size={17} /> 发送
                </Button>
              </div>
            </form>
            <small>可选条件可以跳过 · 不会把未知价格与开放信息当作事实</small>
          </div>
        </section>
      </aside>
      <section className="conversation-canvas workspace-plan-preview" hidden={!preview}>
        <div className="workspace-preview-heading">
          <h2>{plan?.title || "旅行灵感与方案"}</h2>
        </div>
        <div className="canvas-toolbar">
          {trip.data?.plan?.days?.length && !waiting && !running ? (
            <span className="canvas-save-status" role="status">
              <Check size={15} /> 行程已保存 · 版本 {trip.data.version}
            </span>
          ) : null}

          {tripId && !waiting && !running && (
            <div>
              {plan && !waiting && (
                <Button
                  size="sm"
                  variant="secondary"
                  disabled={running || busy || !editable}
                  onClick={() =>
                    send("重新生成一个不同的安排，保留锁定条件，直接规划。", true)
                  }
                >
                  <RefreshCw size={14} />
                  重新生成
                </Button>
              )}
              {tripId && <MemberManager tripId={tripId} />}{" "}
              {trip.data && (
                <>
                  {trip.data.role === "owner" && (
                    <BookingManager tripId={trip.data.id} />
                  )}
                  <HotelSelector trip={trip.data} />
                </>
              )}
              <Button variant="secondary" size="sm" asChild>
                <Link to={"/trips/" + tripId}>
                  行程详情
                  <ArrowRight size={14} />
                </Link>
              </Button>
            </div>
          )}
        </div>
        {staged && (
          <div className="card variant-selector">
            <div>
              <span className="eyebrow">比较后再出发</span>
              <h3>
                {Object.keys(staged).length > 1
                  ? "选择你更喜欢的安排"
                  : "查看并确认这份安排"}
              </h3>
              <p>
                {running
                  ? "方案正在生成，完成后可确认。"
                  : `${Object.keys(staged).length} 个方案已自动保存为草稿，确认后写入正式行程。`}
              </p>
              {conv?.task?.result.missing_variant_reason && (
                <p>{conv.task.result.missing_variant_reason}</p>
              )}
            </div>
            <div className="variant-options">
              {Object.entries(staged).map(([label, candidate]) => (
                <button
                  key={label}
                  className={variant === label ? "selected" : ""}
                  onClick={() => {
                    setVariant(label);
                    setDayIndex(0);
                  }}
                >
                  <b>方案 {label}</b>
                  <span>
                    {candidate.days
                      .flatMap((d) => d.stops.map((s) => s.name))
                      .slice(0, 3)
                      .join(" · ")}
                  </span>
                </button>
              ))}
            </div>
            <Button
              disabled={
                busy || !editable || !waiting || !staged[variant] || trip.isFetching
              }
              onClick={() => choose(variant)}
            >
              <Check size={15} />
              确认并保存方案 {variant}
            </Button>
          </div>
        )}
        {plan && preview ? (
          <>
            <div className="canvas-stops experience-wrapper">
              <TripExperience
                trip={trip.data}
                plan={plan}
                dayIndex={dayIndex}
                setDayIndex={setDayIndex}
                staged={!!staged}
                draft={
                  waiting && conv?.task
                    ? {
                        taskId: conv.task.id,
                        variant,
                        revision: conv.task.result.draft_revision || 1,
                        conversationId: conv.id,
                      }
                    : undefined
                }
                storageKey={sessionKey + ":" + variant}
              />
              {!staged && !running && tripId && <TripFeedback tripId={tripId} />}
            </div>
          </>
        ) : (
          <div className="card blank-canvas">
            <Compass size={40} />
            {conv?.slots?.destination ? (
              <>
                <h2>已识别你的期待</h2>
                <ul className="recognized-slots">
                  {conv.slots.destination ? (
                    <li>目的地：{String(conv.slots.destination)}</li>
                  ) : null}
                  {conv.slots.travel_dates ? (
                    <li>
                      出游日期：
                      {conv.slots.travel_dates === "declined"
                        ? "待定（需补充）"
                        : String(conv.slots.travel_dates)}
                    </li>
                  ) : null}
                  {conv.slots.duration ? (
                    <li>天数：{String(conv.slots.duration)}</li>
                  ) : null}
                  {conv.slots.budget_cny ? (
                    <li>总预算：¥{String(conv.slots.budget_cny)}</li>
                  ) : null}
                  {conv.slots.interests ? (
                    <li>兴趣：{String(conv.slots.interests)}</li>
                  ) : null}
                </ul>
                <p>补全剩余条件（或直接说「开始规划」）后，行程地图将在这里展开。</p>
              </>
            ) : (
              <>
                <img
                  className="planning-inspiration-photo"
                  src="/images/hangzhou.jpg"
                  alt="杭州的湖山与茶园"
                />
                <h2>从湖山与茶香，找一点灵感。</h2>
                <p>
                  告诉我想去哪里、玩几天，方案会在这里展开。下面也有更多目的地可以探索。
                </p>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
}

export function MemberManager({ tripId }: { tripId: string }) {
  const [open, setOpen] = useState(false),
    [name, setName] = useState(""),
    [role, setRole] = useState("viewer"),
    [error, setError] = useState("");
  const client = useQueryClient();
  const members = useQuery({
    queryKey: ["members", tripId],
    queryFn: () =>
      api<{
        role: string;
        members: { user_id: string; username: string; role: string }[];
      }>(`/trips/${tripId}/members`),
    enabled: open,
  });
  return (
    <>
      <Button variant="secondary" size="sm" onClick={() => setOpen(true)}>
        <Users size={14} />
        协作
      </Button>
      {open && (
        <div className="modal-scrim" onClick={() => setOpen(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <Button
              className="modal-close"
              variant="ghost"
              size="icon"
              onClick={() => setOpen(false)}
            >
              <X size={16} />
            </Button>
            <h2>邀请同行者一起规划</h2>
            <p className="muted">
              查看者只能阅读；编辑者可修改行程。公开链接仍保持只读。
            </p>
            {members.data?.members?.map((m) => (
              <div className="member-row" key={m.user_id}>
                <b>{m.username}</b>
                <span>{m.role === "editor" ? "编辑者" : "查看者"}</span>
                {members.data?.role === "owner" && (
                  <button
                    onClick={async () => {
                      await api(`/trips/${tripId}/members/${m.user_id}`, {
                        method: "DELETE",
                      });
                      client.invalidateQueries({
                        queryKey: ["members", tripId],
                      });
                    }}
                  >
                    移除
                  </button>
                )}
              </div>
            ))}
            {members.data?.role === "owner" && (
              <form
                onSubmit={async (e) => {
                  e.preventDefault();
                  try {
                    await api(`/trips/${tripId}/members`, {
                      method: "PUT",
                      body: JSON.stringify({ username: name, role }),
                    });
                    setName("");
                    client.invalidateQueries({ queryKey: ["members", tripId] });
                  } catch (e) {
                    setError((e as Error).message);
                  }
                }}
              >
                <label>
                  对方已注册的用户名
                  <input
                    aria-label="协作者用户名"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                  />
                </label>
                <label>
                  权限
                  <select value={role} onChange={(e) => setRole(e.target.value)}>
                    <option value="viewer">查看者</option>
                    <option value="editor">编辑者</option>
                  </select>
                </label>
                <Button>添加或更新成员</Button>
              </form>
            )}
            {error && (
              <p role="alert" className="error-text">
                {error}
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export function TripFeedback({ tripId }: { tripId: string }) {
  const [rating, setRating] = useState(0),
    [notice, setNotice] = useState("");
  return (
    <div className="trip-feedback">
      <span>这份安排合你心意吗？</span>
      <div>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            aria-label={`评分 ${n} 星`}
            onClick={async () => {
              await post(`/trips/${tripId}/feedback`, {
                event_type: "rating",
                rating: n,
                request_key: crypto.randomUUID(),
              });
              setRating(n);
              setNotice("已记录，仅用于启发式偏好建议。");
            }}
          >
            <Star size={17} fill={n <= rating ? "#ba9d56" : "none"} />
          </button>
        ))}
      </div>
      <button
        onClick={async () => {
          await post(`/trips/${tripId}/feedback`, {
            event_type: "itinerary_kept",
            request_key: crypto.randomUUID(),
          });
          setNotice("已记下你喜欢这份安排。");
        }}
      >
        喜欢这个安排
      </button>
      {notice && <small>{notice}</small>}
    </div>
  );
}
