import { useState, useMemo, useRef, useEffect } from "react";
import { safeHref, safeImageSrc } from "./lib/safeUrl";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BedDouble,
  Bus,
  Car,
  ChevronRight,
  Clock,
  Coffee,
  ExternalLink,
  Footprints,
  Loader2,
  MapPin,
  Navigation,
  Phone,
  RefreshCw,
  Search,
  Star,
  Sun,
  Utensils,
  Wallet,
  X,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, post } from "./api";
import { Button } from "./components/ui/button";
import { BudgetPanel, BudgetNotice } from "./BudgetPanel";
import { MapPanel } from "./MapPanel";
import { useWorkspaceState } from "./lib/workspace";
import { openMapViewer } from "./lib/mapScene";
import type { Plan, Trip, Stop, Route, PendingChange } from "./types";

type Place = Omit<Stop, "planned_start" | "planned_end" | "locked"> & {
  category?: string;
  rating?: number;
  phone?: string;
  distance_meters?: number;
  district?: string;
  business_area?: string;
};
type Leg = Route & {
  from_name: string;
  to_name: string;
  mode: string;
  before_index: number;
  arrival?: string;
  instructions?: string[];
  cost_cny?: number;
  distance_meters?: number;
};
type Meal = {
  slot: string;
  label: string;
  place: Place | null;
  alternatives: Place[];
  anchor_name: string;
  planned_start?: string;
  user_selected: boolean;
};
type Details = {
  version: number;
  day: number;
  city: string;
  date?: string;
  mode: string;
  fixture: boolean;
  meals: Meal[];
  hotel?: Place;
  hotels: Place[];
  stay?: {
    checkin?: string;
    checkout?: string;
    nights: number;
    people: number;
    selected: boolean;
  };
  timeline: {
    kind: string;
    slot?: string;
    label: string;
    place: Place;
    start: string;
    end: string;
    duration: number;
    timing_verified?: boolean;
  }[];
  legs: Leg[];
  walking_meters: number;
  known_transport_cny_per_person: number;
  warnings: string[];
  notice: string;
  retrieved_at: string;
};
type MarketItem = {
  title: string;
  subtitle: string;
  url: string;
  photo?: string;
  price_text: string;
  specification: string;
  details: string;
};
const modes: Record<string, string> = {
  public_transit: "公共交通",
  walk: "步行",
  drive: "驾车",
};
const slotNames: Record<string, string> = {
  breakfast: "早餐",
  lunch: "午餐",
  dinner: "晚餐",
  hotel: "住宿",
};

/** 当天真实预报（高德 casts 按日期匹配），未查到返回 null，绝不编造。 */
function dayWeather(plan: Plan, date?: string) {
  const casts = plan.weather?.forecasts?.flatMap((f) => f.casts ?? []) ?? [];
  if (!date) return null;
  const short = date.slice(5);
  const hit = casts.find((c) => c.date === date || c.date?.endsWith(short));
  if (!hit) return null;
  return `${hit.dayweather || "天气"}${hit.daytemp ? ` ${hit.daytemp}°` : ""}`;
}

function PlaceFacts({ place, kind }: { place: Place; kind?: string }) {
  return (
    <>
      <div className="service-facts">
        <span>{place.category?.split(";").slice(-1)[0] || "地点"}</span>
        {place.rating != null && place.rating > 0 && (
          <span>
            <Star size={12} />
            {place.rating} 分
          </span>
        )}
        {place.price_text && !/酒店|宾馆|旅馆|住宿/.test(place.category || "") && (
          <span>
            {place.price_text.includes("元") || place.source.synthetic
              ? place.price_text
              : `参考消费 ¥${place.price_text}`}
            {kind === "food" && !place.source.synthetic ? " / 人" : ""}
          </span>
        )}
      </div>
      <p className="service-address">
        <MapPin size={13} />
        {place.address || "地址待核实"}
      </p>
      {place.opening_text && (
        <p className="service-hours">
          <Clock size={13} />
          {place.opening_text}
        </p>
      )}
    </>
  );
}

export function TripExperience({
  trip,
  plan,
  dayIndex,
  setDayIndex,
  staged = false,
  onPlaceSelect,
  draft,
  storageKey,
}: {
  draft?: { taskId: string; variant: string; revision: number; conversationId: string };
  storageKey?: string;
  trip?: Trip;
  plan: Plan;
  dayIndex: number;
  setDayIndex: (n: number) => void;
  staged?: boolean;
  onPlaceSelect?: (p: Stop) => void;
}) {
  const client = useQueryClient();
  const marketAbort = useRef<AbortController | null>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  useEffect(() => () => marketAbort.current?.abort(), []);
  const [marketFacts, setMarketFacts] = useState<{ label: string; value: string }[]>(
    [],
  );
  const [marketWarning, setMarketWarning] = useState("");
  const [marketItems, setMarketItems] = useState<MarketItem[]>([]);
  const [refreshId, setRefreshId] = useState(0);
  const [view, setView] = useWorkspaceState(
    (storageKey || "trip:" + trip?.id) + ":view",
    "itinerary",
  );
  const [detail, setDetail] = useState<Place | null>(null),
    [alternatives, setAlternatives] = useState(""),
    [search, setSearch] = useState(""),
    [searchQuery, setSearchQuery] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [market, setMarket] = useState(""),
    [activeLeg, setActiveLeg] = useState<Leg | null>(null);
  const current = plan.days[dayIndex] || plan.days[0];
  useEffect(() => {
    contentRef.current?.scrollTo({ top: 0, behavior: "auto" });
  }, [view, current?.day]);
  const mode =
    (current as typeof current & { transport_mode?: string })?.transport_mode ||
    plan.requirements.transport;
  const facts = useQuery({
    queryKey: [
      "daily-details",
      draft?.taskId,
      draft?.variant,
      draft?.revision,
      trip?.id,
      trip?.version,
      current?.day,
      mode,
      searchQuery,
      alternatives,
      refreshId,
    ],
    queryFn: () =>
      api<Details>(
        (draft
          ? `/tasks/${draft.taskId}/variants/${draft.variant}/daily-details?`
          : `/trips/${trip!.id}/daily-details?`) +
          new URLSearchParams({
            day: String(current.day),
            mode,
            query: searchQuery,
            replacing: alternatives,
            refresh: String(refreshId > 0),
          }),
      ),
    enabled: !!current && (!!draft || (!!trip?.version && !staged)),
    placeholderData: (previous) =>
      !draft && previous?.day === current?.day ? previous : undefined,
    staleTime: 10 * 60 * 1000,
    retry: false,
  });
  const data = facts.data;
  // 逐变更卡片确认 + 撤销窗口：Agent 提交改动后在此给出「撤销 / 忽略」，
  // 不阻塞自身，比 interrupt 更顺滑。trip.version 变化即触发刷新。
  const pending = useQuery({
    queryKey: ["pending-changes", trip?.id, trip?.version],
    queryFn: () => api<PendingChange[]>(`/trips/${trip!.id}/pending-changes`),
    enabled: !!trip?.id && !staged,
    refetchInterval: 20_000,
    retry: false,
  });
  const [tick, setTick] = useState(() => Date.now());
  useEffect(() => {
    if (!pending.data?.length) return;
    const timer = window.setInterval(() => setTick(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [pending.data?.length]);
  async function undoChange(id: string) {
    if (!trip) return;
    setBusy(true);
    setError("");
    try {
      await post(`/trips/${trip.id}/pending-changes/${id}/undo`);
      await client.invalidateQueries({ queryKey: ["trip", trip.id] });
      await client.invalidateQueries({ queryKey: ["trips"] });
      await client.invalidateQueries({ queryKey: ["pending-changes", trip.id] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function dismissChange(id: string) {
    if (!trip) return;
    setBusy(true);
    setError("");
    try {
      await post(`/trips/${trip.id}/pending-changes/${id}/dismiss`);
      await client.invalidateQueries({ queryKey: ["pending-changes", trip.id] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  const editable = trip?.role !== "viewer" && (!staged || !!draft);
  async function toggleLock(place: Place) {
    if (!trip) return;
    setBusy(true);
    setError("");
    try {
      const locked = plan.requirements.locked_ids || [];
      await api(`/trips/${trip.id}/locks`, {
        method: "PUT",
        body: JSON.stringify({
          version: trip.version,
          locked_ids: locked.includes(place.id)
            ? locked.filter((id) => id !== place.id)
            : [...locked, place.id],
        }),
      });
      await client.invalidateQueries({ queryKey: ["trip", trip.id] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function choose(slot: string, p?: Place, nextMode = mode) {
    if (!trip) return;
    setBusy(true);
    setError("");
    try {
      await post(
        draft
          ? `/tasks/${draft.taskId}/variants/${draft.variant}/service-choice`
          : `/trips/${trip.id}/service-choice`,
        {
          day: current.day,
          base_version: draft?.revision || trip.version,
          slot,
          place_id: p?.id || "",
          mode: nextMode,
          query: searchQuery,
          replacing: alternatives,
        },
      );
      setAlternatives("");
      setSearch("");
      setSearchQuery("");
      setDetail(null);
      setMarket("");
      if (draft) {
        await client.invalidateQueries({
          queryKey: ["conversation", draft.conversationId],
        });
      } else {
        await client.invalidateQueries({ queryKey: ["trip", trip.id] });
        await client.invalidateQueries({ queryKey: ["trips"] });
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function closeDrawer() {
    marketAbort.current?.abort();
    setBusy(false);
    setDetail(null);
    setAlternatives("");
    setSearchQuery("");
    setMarket("");
    setMarketItems([]);
    setError("");
  }
  function openAlternatives(slot: string) {
    setAlternatives(slot);
    setSearch("");
    setSearchQuery("");
    setError("");
    setDetail(null);
    setMarket("");
  }
  function showPlace(p: Place) {
    marketAbort.current?.abort();
    setBusy(false);
    setDetail(p);
    setMarket("");
    setActiveLeg(null);
    onPlaceSelect?.({
      ...p,
      planned_start: "",
      planned_end: "",
      locked: false,
    });
  }
  async function queryMarket(p: Place, kind: string) {
    if (!trip) return;
    marketAbort.current?.abort();
    const controller = new AbortController();
    marketAbort.current = controller;
    setBusy(true);
    setError("");
    setMarket("");
    setMarketItems([]);
    setMarketWarning("");
    try {
      const r = await api<{
        raw_text: string;
        items?: MarketItem[];
        venue_warning?: string;
        facts?: { label: string; value: string }[];
      }>(
        draft
          ? `/tasks/${draft.taskId}/variants/${draft.variant}/market-details`
          : `/trips/${trip.id}/market-details`,
        {
          method: "POST",
          signal: controller.signal,
          body: JSON.stringify({ day: current.day, place_id: p.id, kind }),
        },
      );
      if (controller.signal.aborted) return;
      setMarket(r.raw_text.split("</answer>")[0]);
      setMarketItems(r.items || []);
      setMarketWarning(r.venue_warning || "");
      setMarketFacts(r.facts || []);
    } catch (e) {
      if (!controller.signal.aborted) setError((e as Error).message);
    } finally {
      if (marketAbort.current === controller) setBusy(false);
    }
  }
  const mapDay = useMemo(() => {
    const mapStops = data?.timeline?.length
      ? Array.from(
          new Map(
            data.timeline.map((t) => [
              t.place.id,
              {
                ...t.place,
                planned_start: t.start,
                planned_end: t.end,
                locked: false,
              },
            ]),
          ).values(),
        ).filter((p) => p.id !== data.hotel?.id)
      : current?.stops;
    return current
      ? {
          ...current,
          stops: mapStops || [],
          routes: data?.legs || current.routes,
          arrival_route: data ? undefined : current.arrival_route,
        }
      : undefined;
  }, [data, current]);
  const mapHotels = useMemo(
    () => (data?.hotel ? [data.hotel] : plan.hotels),
    [data, plan.hotels],
  );
  const candidates =
    alternatives === "hotel"
      ? data?.hotels
      : data?.meals?.find((m) => m.slot === alternatives)?.alternatives;
  return (
    <section className="trip-experience">
      <div className="experience-days">
        {plan.days.map((d, i) => (
          <button
            key={d.day}
            className={i === dayIndex ? "selected" : ""}
            onClick={() => {
              setDayIndex(i);
              setDetail(null);
              setAlternatives("");
              setSearchQuery("");
              setActiveLeg(null);
            }}
            aria-label={`第 ${d.day} 天${d.city ? ` · ${d.city}` : ""}`}
          >
            <span>第 {d.day} 天</span>
            <small>{d.date?.slice(5) || d.city || "日期待定"}</small>
          </button>
        ))}
      </div>
      <div className="experience-nav">
        <div role="tablist" aria-label="当天行程视图">
          {[
            ["itinerary", "每日安排"],
            ["food", "吃什么"],
            ["hotel", "住哪里"],
            ["transport", "怎么走"],
            ["budget", "花费"],
          ].map(([key, label]) => (
            <button
              role="tab"
              aria-selected={view === key}
              className={view === key ? "active" : ""}
              key={key}
              onClick={() => setView(key)}
            >
              {label}
            </button>
          ))}
        </div>
        <button
          className="experience-refresh"
          aria-label="刷新当天吃住行资料"
          disabled={facts.isFetching}
          onClick={() => setRefreshId((n) => n + 1)}
        >
          <RefreshCw size={14} />
        </button>
        <button
          onClick={() => {
            openMapViewer();
            requestAnimationFrame(() =>
              document
                .querySelector(".mf-map-viewer")
                ?.scrollIntoView({ behavior: "smooth", block: "nearest" }),
            );
          }}
          aria-label="查看地图"
          className="experience-map-toggle"
        >
          <MapPin size={15} />
          查看地图
        </button>
      </div>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {pending.data && pending.data.length > 0 && (
        <div className="pending-changes" role="region" aria-label="待确认的行程改动">
          <div className="pending-changes-head">
            <span className="eyebrow">行程刚被调整</span>
            <small>窗口内可一键撤销；超时后改动保留，历史仍可恢复。</small>
          </div>
          {pending.data.map((pc) => {
            const ms = new Date(pc.expires_at).getTime() - tick;
            const secs = Math.max(0, Math.floor(ms / 1000));
            const expired = pc.expired || secs <= 0;
            const mm = String(Math.floor(secs / 60)).padStart(2, "0");
            const ss = String(secs % 60).padStart(2, "0");
            return (
              <article className="pending-change-card" key={pc.id}>
                <div className="pending-change-info">
                  <b>{pc.summary}</b>
                  <small className={expired ? "muted" : ""}>
                    {expired
                      ? "已超出撤销窗口 · 改动已保留"
                      : `撤销窗口剩余 ${mm}:${ss}`}
                  </small>
                </div>
                <div className="pending-change-actions">
                  <Button
                    size="sm"
                    variant="secondary"
                    disabled={busy || expired}
                    onClick={() => undoChange(pc.id)}
                  >
                    <RefreshCw size={14} />
                    撤销改动
                  </Button>
                  <button
                    className="text-link"
                    disabled={busy || expired}
                    onClick={() => dismissChange(pc.id)}
                  >
                    忽略
                  </button>
                </div>
              </article>
            );
          })}
        </div>
      )}
      <div className="experience-body">
        <div className="experience-content" ref={contentRef}>
          {view === "budget" && trip && (!staged || !!draft) ? (
            <BudgetPanel
              trip={draft ? { ...trip, plan } : trip}
              dayNumber={current.day}
              draft={draft}
            />
          ) : staged && !draft ? (
            <div className="service-pending">
              <h3>方案正在生成</h3>
              <p>完成后即可预览当天的餐厅、住宿与接驳，无需先确认。</p>
              {current?.stops?.map((s) => (
                <button className="draft-place" key={s.id} onClick={() => showPlace(s)}>
                  <span>{s.planned_start}</span>
                  <b>{s.name}</b>
                  <ChevronRight size={14} />
                </button>
              ))}
            </div>
          ) : facts.isPending || (facts.isFetching && data?.mode !== mode) ? (
            <div className="service-loading" role="status">
              <Loader2 className="spin" size={24} />
              <h3>正在安排今天的吃、住、行</h3>
              <p>寻找景点附近的餐厅和住宿，查询每段路怎么走。</p>
              <div />
              <div />
              <div />
            </div>
          ) : facts.error ? (
            <div className="service-pending">
              <h3>当天详情暂时没有查到</h3>
              <p>{facts.error.message}</p>
              <Button size="sm" onClick={() => setRefreshId((n) => n + 1)}>
                <RefreshCw size={14} />
                重新查询
              </Button>
              {current?.stops?.map((s) => (
                <button className="draft-place" key={s.id} onClick={() => showPlace(s)}>
                  <span>{s.planned_start}</span>
                  <b>{s.name}</b>
                </button>
              ))}
            </div>
          ) : (
            data && (
              <>
                <div className="day-essentials">
                  <span>
                    <MapPin size={13} />
                    {data.city}
                  </span>
                  <span>
                    <Footprints size={13} />
                    已知步行 {(data.walking_meters / 1000).toFixed(1)} 公里
                  </span>
                  {data.fixture && <em>合成体验</em>}
                </div>
                {/* 当日天气 · 花费 · 步行：与当天路线同屏（对应设计稿） */}
                <div className="day-context">
                  <span className="dc-item">
                    <Sun size={13} />
                    {dayWeather(plan, current.date) ||
                      (plan.weather?.note ? "天气待核实" : "出行前查询预报")}
                  </span>
                  <span className="dc-sep">｜</span>
                  <span className="dc-item dc-cost">
                    <Wallet size={13} />
                    当日已知交通{" "}
                    {data.known_transport_cny_per_person > 0
                      ? `¥${data.known_transport_cny_per_person}`
                      : "待核实"}
                  </span>
                  <span className="dc-sep">｜</span>
                  <span className="dc-item">
                    <Footprints size={13} />
                    步行 {(data.walking_meters / 1000).toFixed(1)} km
                  </span>
                </div>
                {trip && !staged && view !== "budget" && (
                  <BudgetNotice
                    trip={trip}
                    dayNumber={current.day}
                    onOpen={() => setView("budget")}
                  />
                )}
                {view === "itinerary" && (
                  <div className="experience-timeline">
                    {data.timeline.map((entry, i) => {
                      const leg = data.legs.find((l) => l.before_index === i);
                      return (
                        <div key={entry.kind + entry.place.id + i}>
                          {leg && (
                            <button
                              className="timeline-transit"
                              onClick={() => {
                                setActiveLeg(leg);
                                setView("transport");
                              }}
                            >
                              {leg.mode === "walk" ? (
                                <Footprints size={13} />
                              ) : leg.mode === "drive" ? (
                                <Car size={13} />
                              ) : (
                                <Bus size={13} />
                              )}
                              <span>
                                {leg.minutes != null
                                  ? `约 ${leg.minutes} 分钟`
                                  : "路线待核实"}
                                {leg.walking_meters != null
                                  ? ` · 步行 ${Math.round(leg.walking_meters)} 米`
                                  : ""}
                              </span>
                              <ChevronRight size={12} />
                            </button>
                          )}
                          <article className={"timeline-entry entry-" + entry.kind}>
                            <span className="timeline-node">
                              {entry.kind === "meal" ? (
                                <Utensils size={14} />
                              ) : entry.kind.includes("hotel") ? (
                                <BedDouble size={14} />
                              ) : (
                                <MapPin size={14} />
                              )}
                            </span>
                            <div className="timeline-entry-body">
                              <div className="timeline-meta">
                                <span>
                                  {entry.timing_verified === false ? "待核实 · " : ""}
                                  {entry.start}
                                  {entry.duration > 0 ? `—${entry.end}` : ""}
                                </span>
                                <em>{entry.label}</em>
                              </div>
                              <button
                                onClick={() => showPlace(entry.place)}
                                className="timeline-place"
                              >
                                <h3>{entry.place.name}</h3>
                                {safeImageSrc(entry.place.photos?.[0]) && (
                                  <img
                                    src={safeImageSrc(entry.place.photos[0])}
                                    alt={entry.place.name}
                                    loading="lazy"
                                    referrerPolicy="no-referrer"
                                  />
                                )}
                              </button>
                              <PlaceFacts
                                place={entry.place}
                                kind={entry.kind === "meal" ? "food" : ""}
                              />
                              {entry.place.price_text && (
                                <span className="stop-cost">
                                  费用参考：{entry.place.price_text}
                                </span>
                              )}
                              {entry.kind === "place" && (
                                <div className="timeline-actions">
                                  <span>建议停留 {entry.duration} 分钟</span>
                                  <button
                                    disabled={!editable || busy || staged}
                                    onClick={() => toggleLock(entry.place)}
                                  >
                                    {plan.requirements.locked_ids?.includes(
                                      entry.place.id,
                                    )
                                      ? "解除保留"
                                      : "保留安排"}
                                  </button>
                                </div>
                              )}
                              {entry.kind === "meal" ? (
                                <div className="timeline-actions">
                                  <span>
                                    {
                                      data.meals.find((m) => m.slot === entry.slot)
                                        ?.anchor_name
                                    }
                                    附近
                                  </span>
                                  <button
                                    disabled={!editable || busy}
                                    onClick={() => openAlternatives(entry.slot!)}
                                  >
                                    换一家
                                  </button>
                                </div>
                              ) : entry.kind === "hotel" ? (
                                <div className="timeline-actions">
                                  <span>
                                    {data.stay?.selected
                                      ? "已选地点 · 未预订"
                                      : "推荐住宿 · 未预订"}
                                  </span>
                                  <button
                                    disabled={!editable || busy}
                                    onClick={() => openAlternatives("hotel")}
                                  >
                                    更换住宿
                                  </button>
                                </div>
                              ) : null}
                            </div>
                          </article>
                        </div>
                      );
                    })}
                  </div>
                )}
                {view === "food" && (
                  <div className="meal-view">
                    <div className="service-section-title">
                      <h2>今天，吃点当地的。</h2>
                      <p>围绕当天行程选餐厅，用餐时间留出余地。</p>
                    </div>
                    {data.meals.map((m) => (
                      <article className="meal-detail-card" key={m.slot}>
                        <div className="meal-heading">
                          <span>
                            {m.slot === "breakfast" ? (
                              <Coffee size={18} />
                            ) : (
                              <Utensils size={18} />
                            )}{" "}
                            {m.label}
                          </span>
                          <b>{m.planned_start || "时间待安排"}</b>
                          <button
                            disabled={!editable || busy}
                            onClick={() => openAlternatives(m.slot)}
                          >
                            换一家
                          </button>
                        </div>
                        {m.place ? (
                          <>
                            <button
                              className="service-place-title"
                              onClick={() => showPlace(m.place!)}
                            >
                              <h3>{m.place.name}</h3>
                              <ChevronRight size={16} />
                            </button>
                            <PlaceFacts place={m.place} kind="food" />
                            <p className="service-reason">
                              围绕「{m.anchor_name}」查找的餐饮地点。
                              {m.user_selected
                                ? "你已选择这家餐厅。"
                                : "可展开候选，按口味选择。"}
                            </p>
                            <div className="service-card-links">
                              <button
                                className="text-link"
                                disabled={busy}
                                onClick={() => {
                                  showPlace(m.place!);
                                  queryMarket(m.place!, "food");
                                }}
                              >
                                查看菜单与消费
                              </button>
                              {m.place.phone && (
                                <a href={"tel:" + m.place.phone.split(/[;,]/)[0]}>
                                  <Phone size={13} />
                                  联系商家
                                </a>
                              )}
                              {safeHref(m.place.source.url) && (
                                <a
                                  href={safeHref(m.place.source.url)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                >
                                  地图与导航
                                  <ExternalLink size={12} />
                                </a>
                              )}
                            </div>
                          </>
                        ) : (
                          <p>暂未查到餐厅，试试更换关键词。</p>
                        )}
                      </article>
                    ))}
                  </div>
                )}
                {view === "hotel" && (
                  <div className="hotel-view">
                    <div className="service-section-title">
                      <h2>住得顺路，玩得从容。</h2>
                      <p>优先查看首个景点周边的住宿，早晚接驳也放进路线。</p>
                    </div>
                    {data.hotel ? (
                      <article className="stay-detail-card">
                        {safeImageSrc(data.hotel.photos?.[0]) && (
                          <img
                            className="stay-photo"
                            src={safeImageSrc(data.hotel.photos[0])}
                            alt={data.hotel.name}
                            referrerPolicy="no-referrer"
                          />
                        )}
                        <div className="stay-status">
                          {data.stay?.selected ? "你选择的住宿地点" : "推荐住宿地点"} ·
                          尚未预订
                        </div>
                        <button
                          className="service-place-title"
                          onClick={() => showPlace(data.hotel!)}
                        >
                          <h3>{data.hotel.name}</h3>
                          <ChevronRight size={16} />
                        </button>
                        <PlaceFacts place={data.hotel} />
                        <div className="stay-dates">
                          <div>
                            <small>入住</small>
                            <b>{data.stay?.checkin || "日期待定"}</b>
                          </div>
                          <span>{data.stay?.nights} 晚</span>
                          <div>
                            <small>退房</small>
                            <b>{data.stay?.checkout || "日期待定"}</b>
                          </div>
                        </div>
                        <p className="service-reason">
                          {data.stay?.people}{" "}
                          位出行者。房型、房间数量、早餐和取消政策以对应日期的商家报价为准。
                        </p>
                        <div className="service-card-links">
                          <Button
                            size="sm"
                            disabled={busy}
                            onClick={() => {
                              showPlace(data.hotel!);
                              queryMarket(data.hotel!, "hotel");
                            }}
                          >
                            查询房型与价格
                          </Button>
                          <button
                            className="text-link"
                            disabled={!editable || busy}
                            onClick={() => openAlternatives("hotel")}
                          >
                            换一家住宿
                          </button>
                        </div>
                        {!data.stay?.selected && (
                          <Button
                            className="stay-select"
                            variant="secondary"
                            size="sm"
                            disabled={!editable || busy}
                            onClick={() => choose("hotel", data.hotel)}
                          >
                            选这家，重算接驳路线
                          </Button>
                        )}
                      </article>
                    ) : (
                      <div className="service-pending">
                        <BedDouble size={30} />
                        <p>
                          {plan.requirements.needs_accommodation === false
                            ? "你已说明不需要安排住宿。"
                            : "暂未查到住宿，可以换个区域再找。"}
                        </p>
                        {plan.requirements.needs_accommodation !== false && (
                          <Button size="sm" onClick={() => openAlternatives("hotel")}>
                            寻找住宿
                          </Button>
                        )}
                      </div>
                    )}
                  </div>
                )}
                {view === "transport" && (
                  <div className="transport-view">
                    <div className="service-section-title">
                      <h2>每一段路，心里有数。</h2>
                      <p>餐厅、景点与住宿接驳都在这里。每段另留 10 分钟缓冲。</p>
                    </div>
                    {trip && !staged && (
                      <IntercitySearch
                        trip={trip}
                        day={current.day}
                        city={current.city || plan.requirements.city}
                        date={current.date || ""}
                      />
                    )}
                    <label className="transport-mode">
                      今天怎么出行
                      <select
                        aria-label="当天交通方式"
                        value={mode}
                        disabled={!editable || busy}
                        onChange={(e) => choose("transport", undefined, e.target.value)}
                      >
                        {Object.entries(modes).map(([key, label]) => (
                          <option key={key} value={key}>
                            {label}
                          </option>
                        ))}
                      </select>
                    </label>
                    {data.legs.map((l, i) => (
                      <article
                        className={
                          "transport-leg " +
                          (activeLeg?.from_id === l.from_id &&
                          activeLeg?.to_id === l.to_id
                            ? "active"
                            : "")
                        }
                        key={i}
                      >
                        <div className="leg-destination">
                          <span>{i + 1}</span>
                          <div>
                            <b>{l.from_name}</b>
                            <small>到</small>
                            <b>{l.to_name}</b>
                          </div>
                        </div>
                        <div className="leg-numbers">
                          <span>{modes[l.mode]}</span>
                          <b>
                            {l.minutes != null ? `约 ${l.minutes} 分钟` : "耗时待核实"}
                          </b>
                          {l.cost_cny != null && (
                            <span>
                              参考 ¥{l.cost_cny}
                              {l.mode === "drive" ? " / 车" : " / 人"}
                            </span>
                          )}
                        </div>
                        {l.walking_meters != null && (
                          <p>
                            路段步行 {Math.round(l.walking_meters)} 米
                            {l.distance_meters
                              ? ` · 全程约 ${(l.distance_meters / 1000).toFixed(1)} 公里`
                              : ""}
                          </p>
                        )}
                        {l.instructions?.length ? (
                          <ol>
                            {l.instructions.map((step, j) => (
                              <li key={j}>{step}</li>
                            ))}
                          </ol>
                        ) : l.error ? (
                          <p className="error-text">{l.error}</p>
                        ) : (
                          <p>详细换乘请查看地图来源。</p>
                        )}
                        {safeHref(l.source?.url) && (
                          <a
                            className="text-link"
                            href={safeHref(l.source?.url)}
                            target="_blank"
                            rel="noopener noreferrer"
                          >
                            <Navigation size={13} />
                            打开这段导航
                            <ExternalLink size={12} />
                          </a>
                        )}
                      </article>
                    ))}
                  </div>
                )}
                {data.warnings?.length > 0 && (
                  <details className="service-warnings">
                    <summary>还有 {data.warnings.length} 项需要留意</summary>
                    {data.warnings.map((w, i) => (
                      <p key={i}>{w}</p>
                    ))}
                  </details>
                )}
                <p className="service-source-note">{data.notice}</p>
              </>
            )
          )}
        </div>
        <aside className="experience-map">
          <MapPanel
            defaultOpen={!storageKey}
            day={mapDay}
            hotels={mapHotels}
            highlightId={detail?.id}
            onSelect={(s) => showPlace(s)}
            fixture={plan.fixture}
          />
          <div className="map-context">
            <MapPin size={15} />
            <span>
              {data?.city || current?.city} · 第 {current?.day} 天
            </span>
            <small>点选地图标记，查看地点详情</small>
          </div>
        </aside>
      </div>
      {(detail || alternatives) && (
        <div className="service-drawer-scrim" onClick={closeDrawer}>
          <section
            role="dialog"
            aria-modal="true"
            aria-label={
              alternatives ? "更换" + slotNames[alternatives] : detail!.name + "详情"
            }
            className="service-drawer"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              className="drawer-close"
              aria-label="关闭吃住行详情"
              onClick={closeDrawer}
            >
              <X size={20} />
            </button>
            {alternatives ? (
              <>
                <span className="eyebrow">找到更合心意的安排</span>
                <h2>换一家{slotNames[alternatives] === "住宿" ? "住宿" : "餐厅"}</h2>
                <form
                  className="service-replace-search"
                  onSubmit={(e) => {
                    e.preventDefault();
                    setSearchQuery(search);
                  }}
                >
                  <input
                    aria-label="餐厅或住宿关键词"
                    value={search}
                    maxLength={80}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={
                      alternatives === "hotel" ? "酒店名或区域" : "餐厅名、菜系或口味"
                    }
                  />
                  <Button size="icon">
                    <Search size={17} />
                  </Button>
                </form>
                {facts.isFetching ? (
                  <p className="service-loading">
                    <Loader2 className="spin" size={20} />
                    正在查询附近候选…
                  </p>
                ) : (
                  candidates?.map((p) => (
                    <article className="service-candidate" key={p.id}>
                      <h3>{p.name}</h3>
                      <PlaceFacts
                        place={p}
                        kind={alternatives === "hotel" ? "hotel" : "food"}
                      />
                      <Button
                        size="sm"
                        disabled={busy || !editable}
                        onClick={() => choose(alternatives, p)}
                      >
                        选这家{alternatives === "hotel" ? "住宿" : "餐厅"}
                      </Button>
                    </article>
                  ))
                )}
                {!facts.isFetching && !candidates?.length && (
                  <p>没有查到匹配地点，请换一个关键词。</p>
                )}
              </>
            ) : (
              detail && (
                <>
                  {safeImageSrc(detail.photos?.[0]) && (
                    <img
                      className="drawer-photo"
                      src={safeImageSrc(detail.photos[0])}
                      alt={detail.name}
                      referrerPolicy="no-referrer"
                    />
                  )}
                  <span className="eyebrow">{detail.city} · 地点详情</span>
                  <h2>{detail.name}</h2>
                  <PlaceFacts place={detail} />
                  <p className="service-description">{detail.description}</p>
                  {detail.phone && (
                    <a
                      className="service-phone"
                      href={"tel:" + detail.phone.split(/[;,]/)[0]}
                    >
                      <Phone size={15} />
                      {detail.phone}
                    </a>
                  )}
                  {safeHref(detail.source.url) && (
                    <Button asChild variant="secondary">
                      <a
                        href={safeHref(detail.source.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        查看商家与导航
                        <ExternalLink size={14} />
                      </a>
                    </Button>
                  )}
                  <div className="service-market">
                    {busy ? (
                      <p>
                        <Loader2 className="spin" size={18} />
                        正在查询商家详情…
                      </p>
                    ) : market ? (
                      <>
                        {marketWarning && (
                          <p className="notice" role="status">
                            {marketWarning}
                          </p>
                        )}
                        <MarketCards items={marketItems} />
                        {!marketItems.length &&
                          (marketFacts.length ? (
                            <dl className="market-facts">
                              {marketFacts.map((fact, i) => (
                                <div key={i}>
                                  <dt>{fact.label}</dt>
                                  <dd>{fact.value}</dd>
                                </div>
                              ))}
                            </dl>
                          ) : (
                            <p>
                              平台暂未返回可比较的房型或菜单信息。请通过商家入口或电话核对。
                            </p>
                          ))}
                        {market && (
                          <details className="market-original">
                            <summary>查看平台查询原文</summary>
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {market}
                            </ReactMarkdown>
                          </details>
                        )}
                      </>
                    ) : null}
                  </div>
                  <p className="service-source-note">
                    来源：{detail.source.provider} ·{" "}
                    {detail.source.retrieved_at?.slice(0, 10)}
                    。营业与价格以商家确认为准。
                  </p>
                </>
              )
            )}
            {(error || facts.error) && (
              <p className="notice error" role="alert">
                {error || facts.error?.message}
              </p>
            )}
          </section>
        </div>
      )}
    </section>
  );
}

function IntercitySearch({
  trip,
  city,
  date,
}: {
  trip: Trip;
  day: number;
  city: string;
  date: string;
}) {
  const [origin, setOrigin] = useState((trip.plan as Plan).requirements.origin || ""),
    [destination, setDestination] = useState(city),
    [when, setWhen] = useState(date),
    [kind, setKind] = useState("train"),
    [busy, setBusy] = useState(false),
    [result, setResult] = useState(""),
    [error, setError] = useState("");
  async function search(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setResult("");
    try {
      const data = await post<{ raw_text: string }>(
        `/trips/${trip.id}/intercity-options`,
        {
          origin,
          destination,
          departure_date: when,
          kind,
          people: (trip.plan as Plan).requirements.people,
        },
      );
      setResult(data.raw_text);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details className="intercity-search">
      <summary>
        进出城市：查询车次与航班 <ChevronRight size={14} />
      </summary>
      <form onSubmit={search}>
        <div className="form-row">
          <label>
            出发城市或车站
            <input
              aria-label="城际出发地"
              value={origin}
              onChange={(e) => setOrigin(e.target.value)}
              required
              maxLength={80}
            />
          </label>
          <label>
            到达城市或车站
            <input
              aria-label="城际目的地"
              value={destination}
              onChange={(e) => setDestination(e.target.value)}
              required
              maxLength={80}
            />
          </label>
        </div>
        <div className="form-row">
          <label>
            出发日期
            <input
              aria-label="城际出发日期"
              type="date"
              required
              value={when}
              onChange={(e) => setWhen(e.target.value)}
            />
          </label>
          <label>
            交通方式
            <select
              aria-label="城际交通类型"
              value={kind}
              onChange={(e) => setKind(e.target.value)}
            >
              <option value="train">高铁 / 火车</option>
              <option value="flight">飞机</option>
            </select>
          </label>
        </div>
        <Button size="sm" disabled={busy}>
          {busy ? <Loader2 size={14} className="spin" /> : <Search size={14} />}
          查询班次与价格
        </Button>
      </form>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="intercity-result">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{result}</ReactMarkdown>
        </div>
      )}
      <small>余票和最终价格以售票平台确认结果为准。</small>
    </details>
  );
}

function MarketCards({ items }: { items: MarketItem[] }) {
  if (!items.length) return null;
  return (
    <div className="market-cards">
      <p className="market-policy">
        平台参考报价 · 脱敏价格按原样展示，最终金额以预订页为准。
      </p>
      {items.map((item, i) => (
        <article className="market-product" key={item.url + i}>
          {safeImageSrc(item.photo) && (
            <img
              src={safeImageSrc(item.photo)}
              alt={item.title}
              loading="lazy"
              referrerPolicy="no-referrer"
            />
          )}
          <div>
            <h3>{item.title}</h3>
            <p>{item.specification}</p>
            <small>{item.details}</small>
            <div className="market-product-bottom">
              <b>{item.price_text}</b>
              {safeHref(item.url) && (
                <a href={safeHref(item.url)} target="_blank" rel="noopener noreferrer">
                  到平台查看
                  <ExternalLink size={12} />
                </a>
              )}
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}
