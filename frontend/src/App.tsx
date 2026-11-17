import { useEffect, useState, useRef } from "react";
import {
  Link,
  NavLink,
  Route,
  Routes,
  useNavigate,
  useParams,
  useSearchParams,
  useLocation,
} from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  SlidersHorizontal,
  Heart,
  BedDouble,
  Utensils,
  Mountain,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Check,
  ChevronLeft,
  ChevronRight,
  Compass,
  Download,
  ExternalLink,
  FileText,
  FolderOpen,
  History,
  Leaf,
  Loader2,
  LockKeyhole,
  LogOut,
  Map,
  MapPin,
  Menu,
  MessageSquare,
  Plus,
  Route as RouteIcon,
  Search,
  Send,
  Settings,
  Share2,
  ShieldCheck,
  Sparkles,
  Square,
  Sun,
  Trash2,
  Unlock,
  Upload,
  Wallet,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { QRCodeSVG } from "qrcode.react";
import { Button } from "./components/ui/button";
import { AppHeader } from "./components/AppHeader";
import { TripalBrand, TripalMark } from "./components/TripalLogo";
import { GlobalMapCanvas } from "./components/GlobalMapCanvas";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { EmptyState, ErrorState, Skeleton } from "./components/ui/states";
import { safeHref, safeImageSrc } from "./lib/safeUrl";
import {
  AUTH_EXPIRED_EVENT,
  ApiError,
  api,
  downloadRouteBook,
  post,
  setCsrf,
} from "./api";
import {
  ExplorePage,
  SavedPlacesPage,
  AssistantSetup,
  type SavedPlace,
} from "./Discovery";
import { BookingManager } from "./Bookings";
import { TripExperience } from "./TripExperience";
import { RouteBook } from "./RouteBook";
import { HomeDiscovery } from "./HomeDiscovery";
import { MapPanel } from "./MapPanel";
import { HotelSelector } from "./HotelSelector";
import { VoiceControls } from "./VoiceControls";
import { ConversationWorkspace, MemberManager } from "./ConversationWorkspace";
import {
  ForgotPassword,
  PublicAccountAction,
  PrivacyPanel,
  ConsentBanner,
} from "./AccountLifecycle";
import type {
  Account,
  Day,
  Health,
  Plan,
  Requirements,
  Stop,
  Task,
  Trace,
  Trip,
} from "./types";

const statusNames: Record<string, string> = {
  queued: "等待执行",
  running: "正在调查",
  waiting_input: "需要补充信息",
  awaiting_credentials: "需要配置平台",
  completed: "已完成",
  failed: "执行失败",
  conflict: "行程版本冲突",
  cancelled: "已取消",
};
const defaultReq = (): Requirements => ({
  city: "北京",
  origin: "",
  start_date: null,
  days: 3,
  people: 1,
  budget: null,
  transport: "public_transit",
  style: "city",
  max_walk_meters: 8000,
  interests: "历史文化、公园与街区",
  locked_ids: [],
  excluded_ids: [],
  indoor_only: false,
});
function Markdown({ text }: { text: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: (props) => <a {...props} target="_blank" rel="noopener noreferrer" />,
          img: (props) => (
            <img {...props} loading="lazy" referrerPolicy="no-referrer" />
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
function ErrorBox({ message }: { message: string }) {
  return message ? (
    <div role="alert" className="notice error ui-notice">
      <AlertCircle size={16} aria-hidden="true" />
      <span>{message}</span>
    </div>
  ) : null;
}

function Login({ onDone }: { onDone: (a: Account) => void }) {
  const [email, setEmail] = useState(""),
    [forgot, setForgot] = useState(false);
  const [register, setRegister] = useState(true),
    [name, setName] = useState(""),
    [password, setPassword] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      onDone(
        await post<Account>(register ? "/auth/register" : "/auth/login", {
          name,
          password,
          ...(register ? { email: email || null } : {}),
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (forgot)
    return (
      <div className="account-action-page">
        <section className="card">
          <ForgotPassword onBack={() => setForgot(false)} />
        </section>
      </div>
    );
  return (
    <div className="login-page">
      <div className="login-story">
        <div className="brand">
          <TripalBrand size={46} light />
        </div>
        <span className="eyebrow light">AI 旅行规划助手</span>
        <h1>
          一句话，
          <br />
          安排好下一程。
        </h1>
        <p>说出你的期待，让路线、时间与花费都有界可循。</p>
        <div className="story-route">
          <span>01 · 灵感</span>
          <i />
          <span>02 · 规划</span>
          <i />
          <span>03 · 出发</span>
        </div>
        <div className="story-orbit one" />
        <div className="story-orbit two" />
        <small>中国旅行规划与行程协同助手 · 个人学习项目</small>
      </div>
      <div className="login-panel">
        <form onSubmit={submit}>
          <span className="eyebrow">开启下一段旅程</span>
          <h2>{register ? "从这里，开始下一程" : "欢迎回来"}</h2>
          <p>创建本机账户，保存你的行程与旅行资料。</p>
          <label>
            用户名
            <input
              required
              minLength={2}
              maxLength={60}
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="username"
              placeholder="为自己取一个名字"
            />
          </label>
          <label>
            密码
            <input
              required
              minLength={10}
              maxLength={100}
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete={register ? "new-password" : "current-password"}
              placeholder="至少 10 个字符"
            />
          </label>
          {register && (
            <label>
              邮箱（本机可选，用于找回密码）
              <input
                aria-label="注册邮箱"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </label>
          )}
          <ErrorBox message={error} />
          <Button type="submit" disabled={busy}>
            {busy ? <Loader2 className="spin" size={17} /> : null}
            {register ? "创建账户" : "登录"}
            <ArrowRight size={17} />
          </Button>
          <button
            type="button"
            className="text-button"
            onClick={() => setRegister(!register)}
          >
            {register ? "已有账户？登录" : "还没有账户？创建一个"}
          </button>
          {!register && (
            <button
              type="button"
              className="text-button"
              onClick={() => setForgot(true)}
            >
              忘记密码？
            </button>
          )}
          <div className="privacy-line">
            <ShieldCheck size={15} />
            资料按账户隔离，仅保存到本机服务。
          </div>
        </form>
      </div>
    </div>
  );
}

export default function App() {
  const routeLocation = useLocation();
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [routeLocation.pathname]);
  const client = useQueryClient();
  const [account, setAccount] = useState<Account | null>(null);
  // 会话过期后 /auth/me 的缓存或重新探测不应把用户"自动登录"回去。
  const [sessionExpired, setSessionExpired] = useState(false);
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<Account>("/auth/me"),
    retry: false,
  });
  const currentAccount = sessionExpired ? null : (account ?? me.data ?? null);
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api<Health>("/health"),
    // 后台标签页不轮询；前台也降到 60s，健康检查不是高频数据。
    refetchInterval: () => (document.hidden ? false : 60000),
  });
  const recentTrips = useQuery({
    queryKey: ["trips"],
    queryFn: () => api<Trip[]>("/trips"),
    enabled: !!currentAccount,
  });
  const recentConversations = useQuery({
    queryKey: ["conversations"],
    queryFn: () =>
      api<{ id: string; slots: { destination?: string } }[]>("/conversations"),
    enabled: !!currentAccount,
  });
  useEffect(() => {
    if (me.data) {
      setAccount(me.data);
      setCsrf(me.data.csrf);
    }
  }, [me.data]);
  useEffect(() => {
    // 任何接口的 401 都统一收回到登录页，避免各页面各自处理过期会话。
    const onExpired = () => {
      setSessionExpired(true);
      setAccount(null);
      setCsrf("");
      client.clear();
    };
    window.addEventListener(AUTH_EXPIRED_EVENT, onExpired);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, onExpired);
  }, [client]);
  function authenticated(a: Account) {
    setSessionExpired(false);
    setCsrf(a.csrf);
    setAccount(a);
    client.invalidateQueries();
  }
  const unauthenticated = me.isError && me.error instanceof ApiError && me.error.isAuth;
  if (routeLocation.pathname === "/verify-email")
    return <PublicAccountAction kind="verify" />;
  if (routeLocation.pathname === "/reset-password")
    return <PublicAccountAction kind="reset" />;
  if (!currentAccount && (sessionExpired || unauthenticated))
    return <Login onDone={authenticated} />;
  if (!currentAccount && (me.isPending || !me.isError))
    return (
      <div className="initial-loading ui-initial-loading">
        <TripalMark size={44} />
        <b>Tripal 旅伴</b>
        <span className="ui-initial-hint">一句话，安排好下一程。</span>
        <Skeleton lines={2} compact />
      </div>
    );
  if (!currentAccount)
    return (
      <div className="ui-initial-loading">
        <ErrorState
          title="无法连接服务"
          message={
            me.error instanceof ApiError
              ? me.error.message
              : "请检查本地服务是否已启动，然后重试。"
          }
          requestId={me.error instanceof ApiError ? me.error.requestId : undefined}
          onRetry={() => void me.refetch()}
        />
      </div>
    );
  // 旅行域共享常驻地图画布；资料 / 执行记录 / 偏好 / 设置这类表单列表页不铺地图。
  const managePaths = ["/documents", "/runs", "/assistant", "/settings"];
  const isManage = managePaths.some((p) => routeLocation.pathname.startsWith(p));
  return (
    <div
      className={
        "app-shell mf-shell " + (isManage ? "mf-manage-view" : "mf-travel-view")
      }
    >
      <GlobalMapCanvas mode={isManage ? "manage" : "travel"} />
      <AppHeader
        account={currentAccount}
        health={health.data}
        trips={recentTrips.data ?? []}
        conversations={recentConversations.data ?? []}
        pathname={routeLocation.pathname}
        onLogout={async () => {
          try {
            await post("/auth/logout");
          } finally {
            setAccount(null);
            setCsrf("");
            client.clear();
          }
        }}
      />
      <main className="app-main">
        <ErrorBoundary resetKey={routeLocation.pathname}>
          <Routes>
            <Route path="/chat/:conversationId?" element={<ConversationWorkspace />} />
            <Route path="/" element={<Planner />} />
            <Route path="/trips/:id" element={<Planner />} />
            <Route path="/trips/:id/routebook" element={<RouteBook />} />
            <Route path="/explore" element={<ExplorePage />} />
            <Route path="/saved" element={<SavedPlacesPage />} />
            <Route path="/assistant" element={<AssistantSetup />} />
            <Route path="/archive" element={<Archive />} />
            <Route path="/documents" element={<Documents />} />
            <Route path="/runs" element={<Runs />} />
            <Route
              path="/settings"
              element={<SettingsPage health={health.data} account={currentAccount} />}
            />
          </Routes>
        </ErrorBoundary>
      </main>
      <ConsentBanner />
    </div>
  );
}

function RequirementsForm({
  req,
  setReq,
}: {
  req: Requirements;
  setReq: (r: Requirements) => void;
}) {
  function patch(values: Partial<Requirements>) {
    setReq({ ...req, ...values });
  }
  return (
    <div className="requirements">
      <div className="form-row">
        <label>
          目的地
          <input
            aria-label="目的地"
            value={req.city}
            onChange={(e) => patch({ city: e.target.value })}
          />
        </label>
        <label>
          出发位置
          <input
            aria-label="出发位置"
            value={req.origin}
            onChange={(e) => patch({ origin: e.target.value })}
            placeholder="城市、车站或酒店"
          />
        </label>
      </div>
      <div className="form-row three">
        <label>
          出游日期
          <input
            aria-label="出游日期"
            type="date"
            value={req.start_date || ""}
            onChange={(e) => patch({ start_date: e.target.value || null })}
          />
        </label>
        <label>
          天数
          <select
            aria-label="天数"
            value={req.days}
            onChange={(e) => patch({ days: Number(e.target.value) })}
          >
            {Array.from({ length: 14 }, (_, i) => i + 1).map((n) => (
              <option key={n} value={n}>
                {n} 天
              </option>
            ))}
          </select>
        </label>
        <label>
          人数
          <input
            aria-label="人数"
            type="number"
            min="1"
            max="12"
            value={req.people}
            onChange={(e) => patch({ people: Number(e.target.value) })}
          />
        </label>
      </div>
      <div className="form-row">
        <label>
          总预算 · 元
          <input
            aria-label="总预算"
            type="number"
            min="1"
            value={req.budget ?? ""}
            onChange={(e) =>
              patch({ budget: e.target.value ? Number(e.target.value) : null })
            }
            placeholder="可不填写"
          />
        </label>
        <label>
          出行方式
          <select
            value={req.transport}
            onChange={(e) =>
              patch({ transport: e.target.value as Requirements["transport"] })
            }
          >
            <option value="public_transit">公共交通</option>
            <option value="drive">自驾</option>
            <option value="walk">步行</option>
          </select>
        </label>
      </div>
      <div className="form-row">
        <label>
          旅行类型
          <select
            value={req.style}
            onChange={(e) => patch({ style: e.target.value as Requirements["style"] })}
          >
            <option value="city">城市漫游</option>
            <option value="outdoor">景区 / 轻户外</option>
          </select>
        </label>
        <label>
          路段步行上限
          <select
            value={req.max_walk_meters}
            onChange={(e) => patch({ max_walk_meters: Number(e.target.value) })}
          >
            <option value={3000}>3 公里</option>
            <option value={5000}>5 公里</option>
            <option value={8000}>8 公里</option>
            <option value={12000}>12 公里</option>
          </select>
        </label>
      </div>
      <label>
        偏好与必去地点
        <input
          value={req.interests}
          onChange={(e) => patch({ interests: e.target.value })}
          placeholder="博物馆、自然、当地美食…"
        />
      </label>
      <label className="check-label">
        <input
          type="checkbox"
          checked={req.indoor_only}
          onChange={(e) => patch({ indoor_only: e.target.checked })}
        />
        仅安排已确认的室内地点
      </label>
    </div>
  );
}

function Planner() {
  const { id } = useParams(),
    navigate = useNavigate(),
    client = useQueryClient();
  const [searchParams] = useSearchParams();
  const savedId = searchParams.get("saved");
  const savedPlaces = useQuery({
    queryKey: ["saved-places"],
    queryFn: () => api<SavedPlace[]>("/saved-places"),
    enabled: !!savedId,
  });
  const profile = useQuery({
    queryKey: ["me"],
    queryFn: () => api<Account>("/auth/me"),
  });
  const seeded = useRef("");
  const [idea, setIdea] = useState("");
  const [starting, setStarting] = useState(false);
  function openBrief() {
    const brief = document.getElementById("trip-brief") as HTMLDetailsElement | null;
    if (brief) {
      brief.open = true;
      brief.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }
  async function startChat(e: React.FormEvent) {
    e.preventDefault();
    if (!idea.trim()) return;
    setStarting(true);
    setError("");
    try {
      const conversation = await post<{ id: string; version: number }>(
        "/conversations",
        { fixture },
      );
      const updated = await post(`/conversations/${conversation.id}/turns`, {
        content: idea,
        version: conversation.version,
        request_key: crypto.randomUUID(),
        plan_now: false,
        compare: false,
        regenerate: false,
      });
      client.setQueryData(["conversation", conversation.id], updated);
      navigate("/chat/" + conversation.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }
  const previousTrip = useRef(id);
  const [req, setReq] = useState<Requirements>(defaultReq),
    [message, setMessage] = useState(""),
    [fixture, setFixture] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [taskId, setTaskId] = useState<string | null>(null),
    // 恢复/重试时只需重连 SSE，不必把 taskId 置空再 setTimeout 塞回去。
    [streamNonce, setStreamNonce] = useState(0),
    [trace, setTrace] = useState<Trace[]>([]),
    [dayIndex, setDayIndex] = useState(0),
    [selected, setSelected] = useState<Stop | null>(null),
    [tab, setTab] = useState("itinerary"),
    [showForm, setShowForm] = useState(false),
    [showShare, setShowShare] = useState<{ path: string; id: string } | null>(null),
    [showHistory, setShowHistory] = useState(false),
    [routeDownloading, setRouteDownloading] = useState(false),
    [routeDownloadNote, setRouteDownloadNote] = useState("");
  const trip = useQuery({
    queryKey: ["trip", id],
    queryFn: () => api<Trip>("/trips/" + id),
    enabled: !!id,
  });
  const task = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => api<Task>("/tasks/" + taskId),
    enabled: !!taskId,
    // SSE 负责实时状态，这里只做断线兜底；后台标签页不轮询。
    refetchInterval: (q) =>
      ["queued", "running"].includes(q.state.data?.status ?? "queued") &&
      !document.hidden
        ? 4000
        : false,
  });
  const recentTasks = useQuery({
    queryKey: ["trip-tasks", id],
    queryFn: () => api<Task[]>("/tasks"),
    enabled: !!id && !taskId,
  });
  useEffect(() => {
    if (!taskId && id && recentTasks.data) {
      const latest = recentTasks.data.find((t) => t.trip_id === id);
      if (latest) setTaskId(latest.id);
    }
  }, [id, taskId, recentTasks.data]);
  useEffect(() => {
    if (task.data?.status === "waiting_input") {
      setReq(task.data.requirements);
      setFixture(task.data.fixture);
      setTab("process");
    }
  }, [task.data?.id, task.data?.status]);
  const revisions = useQuery({
    queryKey: ["revisions", id],
    queryFn: () =>
      api<{ version: number; message: string }[]>(`/trips/${id}/revisions`),
    enabled: !!id && showHistory,
  });
  const plan = trip.data?.plan?.days ? (trip.data.plan as Plan) : null;
  const active = ["queued", "running"].includes(task.data?.status ?? "");
  useEffect(() => {
    if (previousTrip.current && previousTrip.current !== id) {
      setTaskId(null);
      setTrace([]);
      setSelected(null);
    }
    previousTrip.current = id;
    if (!id) {
      seeded.current = "";
      setReq(defaultReq());
      setFixture(false);
      setSelected(null);
      setTaskId(null);
      setTrace([]);
    }
  }, [id]);
  useEffect(() => {
    if (id || !profile.data) return;
    const seedKey = savedId || "defaults";
    if (seeded.current === seedKey) return;
    if (savedId && !savedPlaces.data) return;
    const prefs = profile.data.preferences;
    const saved = savedPlaces.data?.find((s) => s.id === savedId);
    setReq((old) => ({
      ...old,
      city: saved?.place?.city || prefs.default_city || old.city,
      days: Number(prefs.default_days) || old.days,
      interests: saved
        ? `希望安排：${saved.place.name}；${prefs.travel_style || ""}`
        : prefs.travel_style || old.interests,
    }));
    if (saved) {
      setMessage(`想去${saved.place.city}的${saved.place.name}。${saved.note}`);
      setFixture(!!saved.place.source?.synthetic);
      requestAnimationFrame(() =>
        document.getElementById("trip-brief")?.scrollIntoView({ block: "start" }),
      );
    }
    seeded.current = seedKey;
  }, [id, savedId, savedPlaces.data, profile.data]);
  useEffect(() => {
    if (plan) {
      setReq(plan.requirements);
      setFixture(plan.fixture);
      setDayIndex((old) => Math.max(0, Math.min(old, plan.days.length - 1)));
      setSelected(null);
    }
  }, [trip.data?.version]);
  useEffect(() => {
    if (task.data?.status === "completed") {
      client.invalidateQueries({ queryKey: ["trip", id] });
      client.invalidateQueries({ queryKey: ["trips"] });
    }
  }, [task.data?.status, id]);
  useEffect(() => {
    if (!taskId) return;
    setTrace([]);
    const sse = new EventSource(`/api/v1/tasks/${taskId}/events`);
    sse.addEventListener("trace", (e) => {
      try {
        const row = JSON.parse((e as MessageEvent).data) as Trace;
        setTrace((old) => [...old, row].slice(-300));
      } catch {
        // 单条坏事件不应让整条时间线崩掉。
      }
    });
    sse.addEventListener("status", () => {
      client.invalidateQueries({ queryKey: ["task", taskId] });
      sse.close();
    });
    sse.onerror = () => {
      // 浏览器会自动重连；任务侧轮询仍作为兜底，不在此清空已有记录。
      client.invalidateQueries({ queryKey: ["task", taskId] });
    };
    return () => sse.close();
  }, [taskId, streamNonce]);
  async function submit(text?: string, overrides?: Partial<Requirements>) {
    setError("");
    setBusy(true);
    try {
      const result = await post<Task>("/tasks", {
        trip_id: id || null,
        base_version: trip.data?.version || 0,
        request_key: crypto.randomUUID(),
        message:
          text ||
          message ||
          `请为我安排${req.city}${req.days}日行程，结合我的偏好，核查路线与约束。`,
        requirements: { ...req, ...overrides },
        fixture,
        strategy: "multi",
      });
      setTaskId(result.id);
      setTab("process");
      setMessage("");
      if (!id) navigate("/trips/" + result.trip_id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function toggleLock(stop: Stop) {
    if (!trip.data) return;
    try {
      const locks = req.locked_ids.includes(stop.id)
        ? req.locked_ids.filter((x) => x !== stop.id)
        : [...req.locked_ids, stop.id];
      await api(`/trips/${id}/locks`, {
        method: "PUT",
        body: JSON.stringify({ version: trip.data.version, locked_ids: locks }),
      });
      await client.invalidateQueries({ queryKey: ["trip", id] });
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function makeShare() {
    try {
      setShowShare(await post(`/trips/${id}/shares`));
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function downloadTripRouteBook() {
    if (!id || !plan || routeDownloading) return;
    setRouteDownloading(true);
    setRouteDownloadNote("");
    try {
      await downloadRouteBook(`/trips/${id}/export/pdf`);
    } catch (e) {
      setRouteDownloadNote("下载失败：" + (e as Error).message);
    } finally {
      setRouteDownloading(false);
    }
  }
  const current = plan?.days[Math.min(dayIndex, plan.days.length - 1)];
  const canEdit = !!plan && !active && !busy && trip.data?.role !== "viewer";
  return (
    <div className={"planner " + (!id ? "new-planner" : "")}>
      {id && (
        <div className="page-heading">
          <div>
            <span className="eyebrow">{id ? "你的旅程，你的节奏" : "从这里出发"}</span>
            <h1>
              {plan?.title || (id ? "正在准备你的行程" : "一句话，安排好下一程。")}
            </h1>
            <p>
              {id
                ? "把地点连成路线，把想法变成可调整的安排。"
                : "AI 旅行规划智能体助手 · 说出目的地、时间和偏好，生成可调整的每日行程。"}
            </p>
          </div>
          {id && (
            <div className="heading-actions">
              {trip.data && (
                <>
                  {trip.data.role === "owner" && (
                    <BookingManager tripId={trip.data.id} />
                  )}
                  <MemberManager tripId={trip.data.id} />
                  <HotelSelector trip={trip.data} />
                </>
              )}
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowForm(!showForm)}
              >
                <Settings size={15} />
                行程条件
              </Button>
              {plan && (
                <>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => setShowHistory(!showHistory)}
                  >
                    <History size={15} />
                    版本 {trip.data?.version}
                  </Button>
                  <Button variant="secondary" size="sm" asChild>
                    <Link to={`/trips/${id}/routebook`}>
                      <BookOpen size={15} />
                      路书预览
                    </Link>
                  </Button>
                  <Button variant="secondary" size="sm" asChild>
                    <a
                      href={`/api/v1/trips/${id}/export/pdf`}
                      aria-disabled={routeDownloading}
                      onClick={(event) => {
                        event.preventDefault();
                        void downloadTripRouteBook();
                      }}
                    >
                      <Download size={15} />
                      {routeDownloading ? "下载中…" : "路书"}
                    </a>
                  </Button>
                  <Button
                    size="sm"
                    disabled={trip.data?.role !== "owner"}
                    onClick={makeShare}
                  >
                    <Share2 size={15} />
                    分享
                  </Button>
                </>
              )}
            </div>
          )}
        </div>
      )}
      {!id && (
        <HomeDiscovery
          idea={idea}
          setIdea={setIdea}
          onPlan={startChat}
          starting={starting}
          error={error}
          city={req.city}
          onOpenBrief={openBrief}
        />
      )}
      {!id && (
        <details className="planning-details" id="trip-brief" open={!!savedId}>
          <summary>
            <SlidersHorizontal size={17} />
            按条件创建行程<span>已经有明确安排？展开填写</span>
            <ChevronRight size={16} />
          </summary>
          <div className="start-grid">
            <section className="card start-card">
              <div className="section-heading">
                <span className="section-icon">
                  <RouteIcon size={20} />
                </span>
                <div>
                  <h2>设计你的旅程</h2>
                  <p>先确定条件，细节可以慢慢调整。</p>
                </div>
              </div>
              <RequirementsForm req={req} setReq={setReq} />
              <label>
                还有什么特别期待？
                <textarea
                  aria-label="还有什么特别期待？"
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="比如：第一次到北京，想逛博物馆、看看老街，不想每天太赶。"
                  rows={3}
                />
              </label>
              <label className="check-label fixture-checkbox">
                <input
                  type="checkbox"
                  checked={fixture}
                  onChange={(e) => setFixture(e.target.checked)}
                />
                合成流程体验 <span>不调用模型或平台，不可用于出游</span>
              </label>
              <ErrorBox message={error} />
              <Button className="full" disabled={busy} onClick={() => submit()}>
                {busy ? <Loader2 size={18} className="spin" /> : <Compass size={18} />}
                开始规划
                <ArrowRight size={18} />
              </Button>
            </section>
          </div>
        </details>
      )}
      {id && (
        <>
          <ErrorBox message={error || trip.error?.message || ""} />
          {routeDownloadNote && <p className="notice">{routeDownloadNote}</p>}
          {showForm && (
            <section className="card edit-form">
              <div className="section-heading">
                <h2>更新行程条件</h2>
                <Button size="sm" variant="ghost" onClick={() => setShowForm(false)}>
                  <X size={16} />
                </Button>
              </div>
              <RequirementsForm req={req} setReq={setReq} />
              <Button
                size="sm"
                disabled={active || busy}
                onClick={() => submit("请按更新后的条件重新安排，保留锁定地点。")}
              >
                按新条件重新规划
              </Button>
            </section>
          )}
          {plan?.fixture && (
            <div className="notice fixture-notice">
              <ShieldCheck size={16} />
              当前为合成流程体验：地点、路线与费用均为测试资料；未调用真实旅行平台，模型调用以执行过程为准。
            </div>
          )}
          {showHistory && (
            <section className="card versions">
              <h3>行程版本</h3>
              {revisions.data?.map((r) => (
                <div key={r.version}>
                  <b>v{r.version}</b>
                  <span>{r.message}</span>
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={r.version === trip.data?.version}
                    onClick={async () => {
                      try {
                        await post(`/trips/${id}/restore/${r.version}`, {
                          base_version: trip.data?.version,
                        });
                        client.invalidateQueries({ queryKey: ["trip", id] });
                        setShowHistory(false);
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    恢复为新版本
                  </Button>
                </div>
              ))}
            </section>
          )}
          <div className="workspace">
            <section className="card itinerary-panel">
              <div className="panel-tabs">
                <button
                  className={tab === "itinerary" ? "active" : ""}
                  onClick={() => setTab("itinerary")}
                >
                  <RouteIcon size={16} />
                  每日安排
                </button>
                <button
                  className={tab === "process" ? "active" : ""}
                  onClick={() => setTab("process")}
                >
                  <History size={16} />
                  执行过程{active && <span className="live-dot" />}
                </button>
                <button
                  className={tab === "sources" ? "active" : ""}
                  onClick={() => setTab("sources")}
                >
                  <BookOpen size={16} />
                  依据
                </button>
              </div>
              {tab === "itinerary" &&
                (plan ? (
                  <TripExperience
                    trip={trip.data}
                    plan={plan}
                    dayIndex={dayIndex}
                    setDayIndex={setDayIndex}
                  />
                ) : (
                  <EmptyPlan active={active} />
                ))}
              {tab === "process" && (
                <div className="process">
                  <div className="process-status">
                    {active ? (
                      <Loader2 size={18} className="spin" />
                    ) : (
                      <History size={18} />
                    )}
                    <b>{statusNames[task.data?.status || ""] || "暂无执行任务"}</b>
                    {active && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={async () => {
                          await post(`/tasks/${taskId}/cancel`);
                          client.invalidateQueries({
                            queryKey: ["task", taskId],
                          });
                        }}
                      >
                        取消
                      </Button>
                    )}
                  </div>
                  {task.data?.result?.error && (
                    <ErrorBox message={task.data.result.error} />
                  )}
                  <div className="trace-list">
                    <TraceBatches traces={trace} />
                    {!trace.length && (
                      <p className="muted">
                        任务开始后，会在这里显示真实的模型和工具调用记录。
                      </p>
                    )}
                  </div>
                  {task.data?.status === "waiting_input" && (
                    <div className="resume-form">
                      <h3>补充日期与出发位置</h3>
                      <RequirementsForm req={req} setReq={setReq} />
                      <Button
                        onClick={async () => {
                          try {
                            await post(`/tasks/${taskId}/resume`, {
                              requirements: req,
                            });
                            client.invalidateQueries({
                              queryKey: ["task", taskId],
                            });
                            setStreamNonce((n) => n + 1);
                          } catch (e) {
                            setError((e as Error).message);
                          }
                        }}
                      >
                        继续调查
                      </Button>
                    </div>
                  )}
                  {["failed", "awaiting_credentials"].includes(
                    task.data?.status || "",
                  ) && (
                    <Button
                      variant="secondary"
                      onClick={async () => {
                        try {
                          await post(`/tasks/${taskId}/retry`);
                          client.invalidateQueries({
                            queryKey: ["task", taskId],
                          });
                          setStreamNonce((n) => n + 1);
                        } catch (e) {
                          setError((e as Error).message);
                        }
                      }}
                    >
                      配置或修复后重试
                    </Button>
                  )}
                  {task.data?.status === "completed" && (
                    <Button variant="secondary" onClick={() => setTab("itinerary")}>
                      查看每日安排
                      <ArrowRight size={15} />
                    </Button>
                  )}
                </div>
              )}
              {tab === "sources" && (
                <div className="sources-panel">
                  <h3>来源与未确认事项</h3>
                  <p>
                    检索到的资料不自动等同于已确认事实。开放、预约和最终价格仍需核实。
                  </p>
                  {plan?.rationale && (
                    <div className="source-rationale">{plan.rationale}</div>
                  )}
                  {plan?.days
                    .flatMap((d) => d.stops)
                    .map((s) => (
                      <div className="source-row" key={s.id}>
                        <b>{s.name}</b>
                        <small>
                          {s.source.provider} · {s.source.retrieved_at?.slice(0, 16)}
                        </small>
                        {safeHref(s.source.url) && (
                          <a
                            href={safeHref(s.source.url)}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            查看原始来源
                            <ArrowUpRight size={13} />
                          </a>
                        )}
                      </div>
                    ))}
                  {plan?.lodging?.raw_text && (
                    <>
                      <h3>美团酒旅查询原文</h3>
                      <Markdown text={plan.lodging.raw_text} />
                    </>
                  )}
                </div>
              )}
              <div className="chat-box">
                <div className="quick-actions">
                  <button
                    disabled={!canEdit}
                    onClick={() =>
                      submit("请减少路段步行量，保留锁定安排。", {
                        max_walk_meters: 3000,
                      })
                    }
                  >
                    少走一点
                  </button>
                  <button
                    disabled={!canEdit}
                    onClick={() =>
                      submit("请改为已确认的室内景点；资料不足时明确说明。", {
                        indoor_only: true,
                      })
                    }
                  >
                    雨天方案
                  </button>
                </div>
                <VoiceControls onTranscript={setMessage} />
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    submit();
                  }}
                >
                  <textarea
                    aria-label="修改行程"
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="想调整哪里？告诉我…"
                    rows={2}
                  />
                  <Button
                    size="icon"
                    title="发送行程修改"
                    disabled={active || busy || !message.trim()}
                  >
                    <Send size={17} />
                  </Button>
                </form>
                <small>修改会生成新版本 · 已锁定的安排优先保留</small>
              </div>
            </section>
            {tab !== "itinerary" && (
              <section className="map-panel">
                <MapPanel
                  day={current}
                  onSelect={setSelected}
                  fixture={fixture}
                  allDays={plan?.days}
                  hotels={plan?.hotels}
                />
                {selected ? (
                  <PlaceDetail stop={selected} close={() => setSelected(null)} />
                ) : plan ? (
                  <div className="card trip-overview">
                    <div>
                      <span className="eyebrow">留一点时间，给意外的发现</span>
                      <h2>安排清楚，也留有余地。</h2>
                      <p>{plan.budget.status}。景点内部步行与接驳尚需确认。</p>
                    </div>
                    <p className="notice">
                      完整费用请在「每日安排 → 花费」中核对；尚未查到的项目不会计为零。
                    </p>
                    {plan.warnings.length > 0 && (
                      <div className="warning-list">
                        {plan.warnings.map((w, i) => (
                          <p key={i}>· {w}</p>
                        ))}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="card waiting-card">
                    <Compass size={22} />
                    <div>
                      <b>行程与地图会在这里汇合</b>
                      <p>
                        你可以切到执行过程，查看查询到了什么，以及哪些信息仍然缺失。
                      </p>
                    </div>
                  </div>
                )}
              </section>
            )}
          </div>
        </>
      )}
      {showShare && (
        <div className="modal-scrim" onClick={() => setShowShare(null)}>
          <div
            role="dialog"
            aria-label="分享旅行路书"
            className="modal share-modal"
            onClick={(e) => e.stopPropagation()}
          >
            <Button
              variant="ghost"
              size="icon"
              className="modal-close"
              onClick={() => setShowShare(null)}
            >
              <X size={18} />
            </Button>
            <span className="eyebrow">分享旅途的期待</span>
            <h2>把这份路书，分享给同行者。</h2>
            <QRCodeSVG value={location.origin + showShare.path} size={150} />
            <p>只读快照，有效期 7 天。不包含私人资料和对话。</p>
            <input readOnly value={location.origin + showShare.path} />
            <small>
              127.0.0.1 地址只能在本机打开；跨设备使用需要局域网配置或 HTTPS 部署。
            </small>
            <div className="modal-actions">
              <Button
                onClick={() =>
                  navigator.clipboard.writeText(location.origin + showShare.path)
                }
              >
                复制链接
              </Button>
              <Button
                variant="secondary"
                onClick={async () => {
                  await api("/shares/" + showShare.id, { method: "DELETE" });
                  setShowShare(null);
                }}
              >
                撤销此链接
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function EmptyPlan({ active }: { active: boolean }) {
  return (
    <div className="empty-plan">
      <RouteIcon size={35} />
      <h3>{active ? "正在寻找适合你的安排" : "尚未生成行程"}</h3>
      <p>
        {active
          ? "我们会先查资料，再核对路线和条件。执行过程可实时查看。"
          : "缺少条件或平台配置时，会保留问题与已执行记录。"}
      </p>
    </div>
  );
}
function TraceBatches({ traces }: { traces: Trace[] }) {
  const groups = new globalThis.Map<number, Trace[]>();
  traces.forEach((t) => {
    const n = Number(t.data.attempt || 0);
    groups.set(n, [...(groups.get(n) || []), t]);
  });
  const latest = Math.max(...groups.keys());
  return (
    <>
      {Array.from(groups).map(([n, items]) => (
        <details className="trace-batch" key={n} open={n === latest}>
          <summary>
            {n === latest ? "本次执行" : "历史记录"} ·{" "}
            {n ? `第 ${n} 次执行` : "旧版执行记录"}
          </summary>
          {items.map((t, i) => (
            <TraceRow key={i} trace={t} />
          ))}
        </details>
      ))}
    </>
  );
}
function TraceRow({ trace }: { trace: Trace }) {
  const data = trace.data;
  return (
    <details className={"trace-row " + (data.success === false ? "trace-error" : "")}>
      <summary>
        <span className="trace-dot" />
        <div>
          <b>{String(data.label || data.name || data.error || trace.kind)}</b>
          <small>
            {trace.kind}{" "}
            {data.elapsed_ms !== undefined ? `· ${data.elapsed_ms} ms` : ""}
          </small>
        </div>
        <ChevronRight size={13} />
      </summary>
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </details>
  );
}
function PlaceDetail({ stop, close }: { stop: Stop; close: () => void }) {
  const photos = Array.from(
    new Set(stop.photos.map(safeImageSrc).filter(Boolean)),
  ) as string[];
  const sourceUrl = safeHref(stop.source.url);
  const guideUrl = safeHref(stop.guide_url);
  const bookingUrl = safeHref(stop.booking_url);
  return (
    <div className="card place-detail">
      <Button
        className="detail-close"
        variant="secondary"
        size="icon"
        aria-label="关闭地点详情"
        onClick={close}
      >
        <X size={16} />
      </Button>
      {photos.length ? (
        <div className="photo-strip">
          {photos.map((src, i) => (
            <img
              key={src}
              src={src}
              alt={`${stop.name} 来源图片 ${i + 1}`}
              loading="lazy"
              referrerPolicy="no-referrer"
            />
          ))}
        </div>
      ) : (
        <div className="no-photo">
          <MapPin size={28} />
          <span>来源未提供图片</span>
        </div>
      )}
      <div className="detail-body">
        <span className="eyebrow">地点详情</span>
        <h2>{stop.name}</h2>
        <p>{stop.address}</p>
        <p>{stop.description}</p>
        <dl>
          <dt>计划停留</dt>
          <dd>
            {stop.planned_start}—{stop.planned_end} · 计划值
          </dd>
          <dt>开放与预约</dt>
          <dd>{stop.opening_text || "待核实，请查看官方来源"}</dd>
          <dt>费用信息</dt>
          <dd>{stop.price_text || "尚无可信价格"}</dd>
        </dl>
        {sourceUrl && (
          <Button variant="secondary" asChild>
            <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
              地图与来源
              <ExternalLink size={14} />
            </a>
          </Button>
        )}
        {guideUrl && (
          <p>
            <a href={guideUrl} target="_blank" rel="noopener noreferrer">
              官方介绍与依据 ↗
            </a>{" "}
            · 静态来源核对于 {stop.guide_checked_at}
          </p>
        )}
        {bookingUrl && (
          <p>
            <a href={bookingUrl} target="_blank" rel="noopener noreferrer">
              查看官方游览／购票入口 ↗
            </a>
          </p>
        )}
        <small className="detail-source">
          {stop.source.provider} · {stop.source.retrieved_at}
        </small>
      </div>
    </div>
  );
}

function Archive() {
  const { data, error, isPending, refetch } = useQuery({
    queryKey: ["trips"],
    queryFn: () => api<Trip[]>("/trips"),
  });
  return (
    <div className="page">
      <PageHeading
        eyebrow="我的旅行收藏"
        title="留住每一次出发的想法"
        subtitle="行程会保存在本机。计划还可以改，想去的地方可以慢慢走。"
      />
      {error && (
        <ErrorState
          title="行程列表加载失败"
          message={error.message}
          requestId={error instanceof ApiError ? error.requestId : undefined}
          onRetry={() => void refetch()}
        />
      )}
      {isPending && (
        <div className="card ui-archive-loading">
          <Skeleton lines={4} />
        </div>
      )}
      <div className="archive-grid">
        <Link to="/" className="new-trip-card">
          <Plus size={28} />
          <h3>计划新旅程</h3>
          <p>下一站，由你决定。</p>
        </Link>
        {data?.map((t, i) => (
          <Link to={"/trips/" + t.id} className="card archive-card" key={t.id}>
            <div
              className={
                "archive-cover " +
                (t.plan.requirements?.city === "北京"
                  ? "color-0"
                  : t.plan.requirements?.city === "杭州"
                    ? "color-1"
                    : t.plan.requirements?.city === "上海"
                      ? "color-2"
                      : "")
              }
            >
              <Compass size={58} />
              <span>旅程 {String(i + 1).padStart(2, "0")}</span>
            </div>
            <div>
              <small>
                {t.plan.fixture ? "合成流程体验" : "旅行计划"} · v{t.version}
              </small>
              <h3>{t.title}</h3>
              <p>
                {new Date(t.updated + "Z").toLocaleDateString()} 更新{" "}
                <ArrowUpRight size={16} />
              </p>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
function PageHeading({
  eyebrow,
  title,
  subtitle,
}: {
  eyebrow: string;
  title: string;
  subtitle: string;
}) {
  return (
    <div className="page-heading">
      <div>
        <span className="eyebrow">{eyebrow}</span>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
    </div>
  );
}

type Doc = {
  id: string;
  name: string;
  status: string;
  version: number;
  info: { error?: string; warning?: string; chunks?: number };
};
function Documents() {
  const client = useQueryClient(),
    {
      data,
      error: loadError,
      isPending,
      refetch,
    } = useQuery({
      queryKey: ["documents"],
      queryFn: () => api<Doc[]>("/documents"),
      // 只有后台仍在解析/索引时才轮询，且后台标签页不发请求。
      refetchInterval: (q) => {
        const pending = q.state.data?.some((d) =>
          ["queued", "indexing"].includes(d.status),
        );
        return pending && !document.hidden ? 4000 : false;
      },
    });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [progress, setProgress] = useState(""),
    [query, setQuery] = useState(""),
    [hits, setHits] = useState<
      {
        id: string;
        text: string;
        name: string;
        anchor: string;
        rrf_score: number;
      }[]
    >([]),
    [support, setSupport] = useState("");
  async function upload(files: FileList | null) {
    if (!files) return;
    setBusy(true);
    setError("");
    try {
      const queue = Array.from(files);
      // 有限并发：既避免逐个串行等待，也不一次性压满上传连接。
      for (let i = 0; i < queue.length; i += 2) {
        const batch = queue.slice(i, i + 2);
        await Promise.all(
          batch.map(async (file) => {
            const form = new FormData();
            form.append("file", file);
            await api("/documents", { method: "POST", body: form });
          }),
        );
        setProgress(
          `正在提交 ${Math.min(i + batch.length, queue.length)}/${queue.length}`,
        );
      }
      setProgress("提交完成，后台将解析和建立索引。");
      client.invalidateQueries({ queryKey: ["documents"] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page">
      <PageHeading
        eyebrow="把灵感带上旅途"
        title="让你的旅行资料，也参与规划"
        subtitle="导入攻略与官方说明，检索原文依据。实时路线与价格仍由平台查询。"
      />
      <div className="documents-grid">
        <section>
          <label className="upload-zone">
            <span className="icon-orbit">
              <Upload size={24} />
            </span>
            <h3>{busy ? "正在上传…" : "把旅行灵感放进来"}</h3>
            <p>选择或拖入 TXT、MD、PDF、DOCX 文件</p>
            <small>单文件不超过 5 MB · 图片和扫描内容暂不进入索引</small>
            <input
              aria-label="上传旅行资料"
              type="file"
              multiple
              accept=".txt,.md,.pdf,.docx"
              disabled={busy}
              onChange={(e) => upload(e.target.files)}
            />
          </label>
          {progress && (
            <p className="muted" role="status">
              {progress}
            </p>
          )}
          <ErrorBox message={error} />
          {loadError && (
            <ErrorState
              title="资料列表加载失败"
              message={loadError.message}
              requestId={
                loadError instanceof ApiError ? loadError.requestId : undefined
              }
              onRetry={() => void refetch()}
            />
          )}
          <div className="card document-list">
            <h3>
              我的资料 <span>{data?.length || 0}</span>
            </h3>
            {isPending && <Skeleton lines={3} compact />}
            {!isPending && !loadError && !data?.length && (
              <EmptyState
                title="还没有旅行资料"
                description="导入一份自己的攻略或官方说明，检索结果会保留原文出处。"
              />
            )}
            {data?.map((d) => (
              <div className="document-row" key={d.id}>
                <FileText size={20} />
                <div>
                  <b>{d.name}</b>
                  <small>
                    {
                      (
                        {
                          ready: "已索引",
                          queued: "等待处理",
                          indexing: "正在索引",
                          failed: "处理失败",
                        } as Record<string, string>
                      )[d.status]
                    }{" "}
                    · v{d.version} {d.info.chunks ? `· ${d.info.chunks} 片段` : ""}
                  </small>
                  {d.info.error && <small className="error-text">{d.info.error}</small>}
                </div>
                <a href={`/api/v1/documents/${d.id}/original`} title="下载原文">
                  <Download size={15} />
                </a>
                <button
                  title="重新索引"
                  onClick={async () => {
                    try {
                      await post(`/documents/${d.id}/reindex`);
                      client.invalidateQueries({ queryKey: ["documents"] });
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  <History size={15} />
                </button>
                <button
                  title="移除文档"
                  onClick={async () => {
                    await api("/documents/" + d.id, { method: "DELETE" });
                    client.invalidateQueries({ queryKey: ["documents"] });
                  }}
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))}
          </div>
        </section>
        <section className="card retrieval">
          <span className="eyebrow">从资料中寻找答案</span>
          <h2>试着找一条依据</h2>
          <p>返回相关片段与位置，不把“相关”直接当作“正确”。</p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                const result = await post<{
                  hits: typeof hits;
                  message: string;
                }>("/knowledge/search", { query });
                setHits(result.hits);
                setSupport(result.message);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <input
              aria-label="检索问题"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="比如：预约需要提前多久？"
              required
            />
            <Button disabled={busy} size="icon" title="检索资料">
              <Search size={17} />
            </Button>
          </form>
          {support && <p className="notice">{support}</p>}
          {hits.map((h) => (
            <div className="retrieval-hit" key={h.id}>
              <b>{h.name}</b>
              <small>
                {h.anchor} · RRF {h.rrf_score.toFixed(4)}
              </small>
              <p>{h.text}</p>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}

function Runs() {
  const {
    data,
    error: loadError,
    isPending,
    refetch,
  } = useQuery({
    queryKey: ["tasks"],
    queryFn: () => api<Task[]>("/tasks"),
    refetchInterval: (q) => {
      const active = q.state.data?.some((t) =>
        ["queued", "running"].includes(t.status),
      );
      return active && !document.hidden ? 4000 : false;
    },
  });
  const [selected, setSelected] = useState<string | null>(null),
    [trace, setTrace] = useState<Trace[]>([]);
  useEffect(() => {
    if (!selected) return;
    setTrace([]);
    const stream = new EventSource(`/api/v1/tasks/${selected}/events`);
    stream.addEventListener("trace", (e) =>
      setTrace((old) => [...old, JSON.parse((e as MessageEvent).data)]),
    );
    stream.addEventListener("status", () => stream.close());
    return () => stream.close();
  }, [selected]);
  return (
    <div className="page">
      <PageHeading
        eyebrow="规划进度与记录"
        title="每一步，都有来处"
        subtitle="查看模型、工具与任务状态，区分真实执行和合成流程。"
      />
      {loadError && (
        <ErrorState
          title="执行记录加载失败"
          message={loadError.message}
          requestId={loadError instanceof ApiError ? loadError.requestId : undefined}
          onRetry={() => void refetch()}
        />
      )}
      <div className="runs-layout">
        <div className="card runs-list">
          {isPending && <Skeleton lines={4} compact />}
          {!isPending && !loadError && !data?.length && (
            <EmptyState
              title="还没有执行记录"
              description="提交一次规划后，模型、工具与任务状态会记录在这里。"
            />
          )}
          {data?.map((t) => (
            <button
              key={t.id}
              onClick={() => setSelected(t.id)}
              className={selected === t.id ? "selected" : ""}
            >
              <span className={"status-pill " + t.status}>{statusNames[t.status]}</span>
              <b>{t.message}</b>
              <small>
                {t.fixture ? "合成夹具" : "真实平台模式"} ·{" "}
                {new Date(t.created + "Z").toLocaleString()}
              </small>
              <Link to={"/trips/" + t.trip_id}>
                打开行程
                <ArrowUpRight size={13} />
              </Link>
            </button>
          ))}
        </div>
        <div className="card run-detail">
          <h3>执行时间线</h3>
          <TraceBatches traces={trace} />
          {!selected && <p className="muted">选择左侧任务，查看详细执行记录。</p>}
        </div>
      </div>
    </div>
  );
}

function SettingsPage({ health, account }: { health?: Health; account: Account }) {
  const client = useQueryClient();
  const [prefs, setPrefs] = useState(account.preferences),
    [message, setMessage] = useState("");
  return (
    <div className="page">
      <PageHeading
        eyebrow="偏好与服务管理"
        title="平台与运行设置"
        subtitle="常用参数在代码中修改；服务密钥只保存在本机，不需要发送到聊天。"
      />
      <div className="settings-grid">
        <PrivacyPanel username={account.name} />
        <section className="card settings-card">
          <h2>服务连接</h2>
          {Object.entries(health?.services || {}).map(([k, v]) => (
            <div className="setting-status" key={k}>
              <span>{k}</span>
              <b className={v === "ready" ? "good" : "error-text"}>
                {v === "ready" ? "已连接" : "不可用"}
              </b>
            </div>
          ))}
          <h3>外部平台</h3>
          {Object.entries(health?.providers || {}).map(([k, v]) => (
            <div className="setting-status" key={k}>
              <span>{k}</span>
              <b>
                {v === "needs_key"
                  ? "待配置密钥"
                  : v === "disabled"
                    ? "尚未启用"
                    : "已配置 · 待真实验证"}
              </b>
            </div>
          ))}
          <p className="muted">
            配置文件：项目根目录 config.local.json
            <br />
            修改后重启后端与 worker。首次可复制 config.example.json。
          </p>
        </section>
        <section className="card settings-card">
          <h2>个人开发申请</h2>
          <div className="platform-entry">
            <b>01 / 高德地图</b>
            <p>
              个人实名认证后创建应用，分别申请 Web 服务 Key、Web JS Key 和安全配置。
            </p>
            <a href="https://lbs.amap.com/" target="_blank" rel="noopener noreferrer">
              打开高德开放平台
              <ArrowUpRight size={14} />
            </a>
          </div>
          <div className="platform-entry">
            <b>02 / Gemini 模型</b>
            <p>
              Google AI Studio 的官方 Key 使用 Gemini 原生接入。按
              config.gemini.example.json 填写本机配置，检查模型权限与额度。
            </p>
            <a
              href="https://ai.google.dev/gemini-api/docs/api-key"
              target="_blank"
              rel="noopener noreferrer"
            >
              申请指南
              <ArrowUpRight size={14} />
            </a>
          </div>
          <div className="platform-entry">
            <b>03 / 美团酒旅</b>
            <p>
              入驻个人开发者并配置官方 CLI
              Token。查询、价格展示与预订跳转以授权能力为准。
            </p>
            <a
              href="https://developer.meituan.com/ai-hub/skill-list/detail/12"
              target="_blank"
              rel="noopener noreferrer"
            >
              官方酒旅 Skill
              <ArrowUpRight size={14} />
            </a>
          </div>
        </section>
        <section className="card settings-card">
          <h2>确认保存的旅行偏好</h2>
          <p>仅保存你主动填写的偏好，不自动从对话推断个人信息。</p>
          {[
            ["default_city", "默认目的地（可留空）"],
            ["default_days", "默认天数（1—14，可留空）"],
            ["pace", "旅行节奏"],
            ["travel_style", "旅行风格"],
            ["accessibility", "出行需求"],
            ["food", "饮食偏好"],
          ].map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                value={prefs[key] || ""}
                onChange={(e) => setPrefs({ ...prefs, [key]: e.target.value })}
              />
            </label>
          ))}
          <Button
            onClick={async () => {
              try {
                await api("/preferences", {
                  method: "PUT",
                  body: JSON.stringify(prefs),
                });
                await client.invalidateQueries({ queryKey: ["me"] });
                setMessage("偏好已保存，新行程将读取这些信息。");
              } catch (e) {
                setMessage((e as Error).message);
              }
            }}
          >
            保存偏好
          </Button>
          {message && <p>{message}</p>}
        </section>
        <section className="card settings-card">
          <h2>项目边界</h2>
          <ul>
            <li>参考价格与最终成交价不同；没有自动下单。</li>
            <li>部分开放、预约和景点内部步行数据仍需人工核对。</li>
            <li>合成流程用于测试，不能证明真实平台或模型效果。</li>
            <li>小红书首版以用户导入资料为主，不读取私有笔记。</li>
            <li>语音功能在核心流程验收后启用，状态以实际测试为准。</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
