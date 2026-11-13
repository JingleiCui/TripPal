import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
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
} from "lucide-react";
import { api, post } from "./api";
import { Button } from "./components/ui/button";
import { BookingManager } from "./Bookings";
import { TripExperience } from "./TripExperience";
import { MapPanel } from "./MapPanel";
import { HotelSelector } from "./HotelSelector";
import type { Plan, Trip, Stop } from "./types";
import { capture } from "./AccountLifecycle";

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
    };
  } | null;
};

export function ConversationWorkspace() {
  const { conversationId } = useParams(),
    navigate = useNavigate(),
    client = useQueryClient();
  const [input, setInput] = useState(""),
    [fixture, setFixture] = useState(false),
    [compare, setCompare] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [mobile, setMobile] = useState("chat"),
    [variant, setVariant] = useState("A"),
    [dayIndex, setDayIndex] = useState(0),
    [streamed, setStreamed] = useState<Record<string, string>>({});
  const bottom = useRef<HTMLDivElement>(null);
  const [stageVariants, setStageVariants] = useState<
      Record<string, Record<string, Plan>>
    >({}),
    [stages, setStages] = useState<Record<string, string>>({});
  const conversation = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => api<Conversation>("/conversations/" + conversationId),
    enabled: !!conversationId,
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.task?.status || "")
        ? 1500
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
    ? conv.task?.result.variants
    : running
      ? stageVariants[conv?.task?.id || ""]
      : undefined;
  const stage = stages[conv?.task?.id || ""];
  const plan = (staged?.[variant] ||
    (trip.data?.plan?.days ? trip.data.plan : null)) as Plan | null;
  const editable =
    !trip.data?.role || ["owner", "editor"].includes(trip.data.role);
  useEffect(() => {
    setStreamed({});
    setStageVariants({});
    setStages({});
    setError("");
    setDayIndex(0);
  }, [conversationId]);
  useEffect(() => {
    if (conv?.state.fixture !== undefined) setFixture(conv.state.fixture);
  }, [conv?.state.fixture]);
  useEffect(() => {
    if (!conversationId) return;
    const stream = new EventSource(
      `/api/v1/conversations/${conversationId}/events`,
    );
    stream.addEventListener("message", () =>
      client.invalidateQueries({ queryKey: ["conversation", conversationId] }),
    );
    stream.addEventListener("token", (e) => {
      const value = JSON.parse((e as MessageEvent).data);
      setStreamed((old) => ({
        ...old,
        [value.task_id + ":" + (value.variant || "")]:
          (old[value.task_id + ":" + (value.variant || "")] || "") +
          value.delta,
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
    bottom.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [conv?.messages.length, streamed]);
  async function send(content = input, regenerate = false) {
    if (!content.trim()) return;
    setBusy(true);
    setError("");
    try {
      let current = conv;
      if (!current) {
        current = await post<Conversation>("/conversations", { fixture });
        void capture("conversation_started");
      }
      const updated = await post<Conversation>(
        `/conversations/${current.id}/turns`,
        {
          content,
          version: current.version,
          request_key: crypto.randomUUID(),
          plan_now: regenerate,
          compare,
          regenerate,
        },
      );
      client.setQueryData(["conversation", current.id], updated);
      setInput("");
      if (updated.state.task_id) void capture("plan_requested");
      if (!conversationId) navigate("/chat/" + current.id);
      client.invalidateQueries({ queryKey: ["conversations"] });
    } catch (e) {
      setError((e as Error).message);
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
    <div className="page chat-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">从对话到旅程</span>
          <h1>{plan?.title || "这次旅行，我们一起安排。"}</h1>
          <p>
            {plan
              ? "每天吃什么、住哪里、怎么走，都放进同一份计划。"
              : "告诉我去哪里、什么时候出发，其他细节边聊边定。"}
          </p>
        </div>
        <Button variant="secondary" size="sm" asChild>
          <Link to="/chat">
            <Plus size={15} />
            新对话
          </Link>
        </Button>
      </div>
      <div className="mobile-canvas-toggle">
        <button
          className={mobile === "chat" ? "active" : ""}
          onClick={() => setMobile("chat")}
        >
          <MessageSquare size={16} />
          对话
        </button>
        <button
          className={mobile === "canvas" ? "active" : ""}
          onClick={() => setMobile("canvas")}
        >
          <Map size={16} />
          行程画布
        </button>
      </div>
      {error && (
        <div role="alert" className="notice error">
          {error}
        </div>
      )}
      <div className={"conversation-layout mobile-show-" + mobile}>
        <section className="card conversation-chat">
          <header>
            <MessageSquare size={17} />
            <b>旅行对话</b>
            {fixture && <span className="status-pill">合成资料体验</span>}
          </header>
          <div className="chat-history">
            {messages.map((message) => (
              <div className={"chat-message " + message.role} key={message.id}>
                <span className="chat-avatar">
                  {message.role === "user" ? "你" : <Compass size={15} />}
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
                    <Compass size={15} />
                  </span>
                  <div>
                    {text}
                    <span className="typing-cursor" />
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
            {conv?.task?.result.error && (
              <div className="notice error">{conv.task.result.error}</div>
            )}
            {conv?.task?.status === "waiting_input" && (
              <div className="notice">
                行程条件存在需要确认的取舍。
                <Link to={"/trips/" + tripId}>打开详情继续处理 →</Link>
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
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send();
              }}
            >
              <textarea
                aria-label="旅行对话输入"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="比如：想去北京玩三天，喜欢博物馆，直接规划"
                rows={3}
              />
              <Button
                size="icon"
                title="发送旅行对话"
                disabled={
                  busy || running || waiting || !editable || !input.trim()
                }
              >
                <Send size={17} />
              </Button>
            </form>
            <small>可选条件可以跳过 · 不会把未知价格与开放信息当作事实</small>
          </div>
        </section>
        <section className="conversation-canvas">
          <div className="canvas-toolbar">
            <h2>
              <Map size={18} />
              行程画布
            </h2>
            {tripId && (
              <div>
                {plan && !waiting && (
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={running || busy || !editable}
                    onClick={() =>
                      send(
                        "重新生成一个不同的安排，保留锁定条件，直接规划。",
                        true,
                      )
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
                <h3>选择你更喜欢的安排</h3>
                <p>两种方案复用同一份研究资料，目前均未保存为行程。</p>
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
                disabled={busy || !editable || !waiting || !staged[variant]}
                onClick={() => choose(variant)}
              >
                <Check size={15} />
                选择并保存方案 {variant}
              </Button>
            </div>
          )}
          {plan ? (
            <>
              <div className="canvas-stops experience-wrapper">
                <TripExperience
                  trip={trip.data}
                  plan={plan}
                  dayIndex={dayIndex}
                  setDayIndex={setDayIndex}
                  staged={!!staged}
                />
                {!staged && !running && tripId && (
                  <TripFeedback tripId={tripId} />
                )}
              </div>
            </>
          ) : (
            <div className="card blank-canvas">
              <Compass size={40} />
              <h2>先聊清期待，再展开地图。</h2>
              <p>
                目的地和天数明确后，行程将在这里逐步形成。日期尚未确定时，只生成带缺口说明的草案。
              </p>
            </div>
          )}
        </section>
      </div>
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
            {members.data?.members.map((m) => (
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
                  <select
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                  >
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
