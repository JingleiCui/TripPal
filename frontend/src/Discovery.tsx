import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Bookmark,
  Check,
  Compass,
  ExternalLink,
  Heart,
  Loader2,
  MapPin,
  Search,
  SlidersHorizontal,
  Trash2,
  X,
} from "lucide-react";
import { api, post } from "./api";
import { safeHref } from "./lib/safeUrl";
import { Button } from "./components/ui/button";
import { PlacePhoto } from "./PlacePhoto";
import { MapPanel } from "./MapPanel";
import { openMapViewer } from "./lib/mapScene";
import { useWorkspaceState, readWorkspace, writeWorkspace } from "./lib/workspace";
import type { Stop, Source } from "./types";

export type DiscoveryPlace = Omit<
  Stop,
  "planned_start" | "planned_end" | "locked" | "source" | "lon" | "lat" | "photos"
> & {
  category?: string;
  coordinate_system?: string;
  source?: Source;
  lon?: number;
  lat?: number;
  photos?: string[];
  url?: string;
  source_label?: string;
};
export type SavedPlace = {
  id: string;
  place: DiscoveryPlace;
  collection: string;
  note: string;
  updated: string;
};
const categories = [
  ["all", "为你发现"],
  ["sights", "景点与体验"],
  ["food", "餐厅美食"],
  ["stays", "住宿地点"],
  ["nature", "公园与自然"],
  ["art", "文化艺术"],
];

// One real provider page at a time; edit here to tune browsing density.
const DISCOVERY_PAGE_SIZE = 20;
const PREFETCH_DISTANCE_PX = 280;
type DiscoveryPage = {
  items: DiscoveryPlace[];
  notice: string;
  fixture: boolean;
  next_page: number | null;
  has_more: boolean;
  end_reason: "provider_limit" | "exhausted" | null;
};

function ErrorNotice({ error }: { error: unknown }) {
  return error ? (
    <p className="notice error" role="alert">
      {error instanceof Error ? error.message : String(error)}
    </p>
  ) : null;
}

export function ExplorePage({
  storageKey = "explore",
  onDiscuss,
  mapActive = true,
}: {
  storageKey?: string;
  mapActive?: boolean;
  onDiscuss?: (place: DiscoveryPlace) => void;
}) {
  const client = useQueryClient();
  const [searchParams] = useSearchParams();
  const initialCity = searchParams.get("city") || "北京";
  const initialCategory = categories.some(
    ([key]) => key === searchParams.get("category"),
  )
    ? searchParams.get("category")!
    : "all";
  const [city, setCity] = useWorkspaceState(storageKey + ":city", initialCity),
    [query, setQuery] = useWorkspaceState(storageKey + ":query", "");
  const [params, setParams] = useWorkspaceState(storageKey + ":params", {
    city: initialCity,
    query: "",
    category: initialCategory,
    fixture: false,
  });
  useEffect(() => {
    const urlCity = searchParams.get("city");
    const urlCategory = searchParams.get("category");
    if (urlCity || urlCategory) {
      if (urlCity) setCity(urlCity);
      setParams((old) => ({
        ...old,
        ...(urlCity ? { city: urlCity } : {}),
        ...(categories.some(([key]) => key === urlCategory)
          ? { category: urlCategory! }
          : {}),
      }));
    }
  }, [searchParams.get("city"), searchParams.get("category")]);
  const [selected, setSelected] = useState<DiscoveryPlace | null>(null),
    [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  const loadMoreRef = useRef<HTMLDivElement>(null);
  const results = useInfiniteQuery({
    queryKey: ["explore", params],
    initialPageParam: 1,
    initialData: () =>
      readWorkspace<{ pages: DiscoveryPage[]; pageParams: number[] } | undefined>(
        storageKey + ":results:" + JSON.stringify(params),
        undefined,
      ),
    queryFn: ({ pageParam, signal }) =>
      api<DiscoveryPage>(
        "/explore?" +
          new URLSearchParams({
            ...params,
            fixture: String(params.fixture),
            page: String(pageParam),
            page_size: String(DISCOVERY_PAGE_SIZE),
          }),
        { signal },
      ),
    getNextPageParam: (lastPage) => lastPage.next_page ?? undefined,
    retry: false,
  });
  useEffect(() => {
    if (results.data)
      writeWorkspace(storageKey + ":results:" + JSON.stringify(params), results.data);
  }, [results.data, JSON.stringify(params)]);
  const { fetchNextPage, hasNextPage, isFetching, isFetchNextPageError } = results;
  useEffect(() => {
    const target = loadMoreRef.current;
    if (
      !target ||
      !hasNextPage ||
      isFetching ||
      isFetchNextPageError ||
      typeof IntersectionObserver === "undefined"
    )
      return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          void fetchNextPage({ cancelRefetch: false });
        }
      },
      { rootMargin: `${PREFETCH_DISTANCE_PX}px 0px` },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetching, isFetchNextPageError]);
  const saved = useQuery({
    queryKey: ["saved-places"],
    queryFn: () => api<SavedPlace[]>("/saved-places"),
  });
  async function save(place: DiscoveryPlace) {
    setBusy(place.id);
    setError("");
    try {
      await post("/saved-places", { place_id: place.id });
      await client.invalidateQueries({ queryKey: ["saved-places"] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  const places = useMemo(() => {
    const unique = new Map<string, DiscoveryPlace>();
    for (const page of results.data?.pages ?? []) {
      for (const place of page.items) {
        if (!unique.has(place.id)) unique.set(place.id, place);
      }
    }
    return [...unique.values()];
  }, [results.data]);
  const lastPage = results.data?.pages.at(-1);
  const mapDay = useMemo(
    () => ({
      day: 1,
      date: "",
      city: params.city,
      stops: places
        .filter(
          (p) =>
            typeof p.lon === "number" &&
            typeof p.lat === "number" &&
            (p.lon !== 0 || p.lat !== 0),
        )
        .map((p) => ({
          ...p,
          planned_start: "",
          planned_end: "",
          locked: false,
        })) as Stop[],
      routes: [],
      known_route_walking_meters: 0,
      walking_note: "",
    }),
    [places, params.city],
  );
  return (
    <div className="page explore-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">发现值得出发的地方</span>
          <h1>把好奇，变成下一站。</h1>
          <p>找景点、餐厅和住宿，把想去的地方放进收藏夹。</p>
        </div>
        <Button asChild variant="secondary">
          <Link to="/saved">
            <Bookmark size={16} />
            我的收藏
          </Link>
        </Button>
      </div>
      <Button
        className="explore-map-open"
        variant="secondary"
        size="sm"
        onClick={openMapViewer}
      >
        <MapPin size={16} />
        查看地点地图
      </Button>
      <form
        className="explore-search"
        onSubmit={(e) => {
          e.preventDefault();
          setSelected(null);
          setParams({ ...params, city: city.trim(), query: query.trim() });
        }}
      >
        <label>
          <MapPin size={17} />
          <input
            aria-label="探索城市"
            value={city}
            onChange={(e) => setCity(e.target.value)}
            maxLength={40}
            required
            placeholder="目的地城市"
          />
        </label>
        <label>
          <Search size={17} />
          <input
            aria-label="搜索地点"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            maxLength={100}
            placeholder="搜索景点、餐厅、酒店或街区"
          />
        </label>
        <Button type="submit" disabled={!city.trim()}>
          <Search size={17} />
          搜索地点
        </Button>
      </form>
      <div className="explore-filter-row">
        <div className="explore-filters" aria-label="地点类型">
          {categories.map(([key, label]) => (
            <button
              key={key}
              className={params.category === key ? "selected" : ""}
              aria-pressed={params.category === key}
              onClick={() => {
                setSelected(null);
                setParams({
                  ...params,
                  category: key,
                  city: city.trim() || "北京",
                  query: query.trim(),
                });
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="check-label">
          <input
            type="checkbox"
            checked={params.fixture}
            onChange={(e) => {
              setSelected(null);
              setParams({ ...params, fixture: e.target.checked });
            }}
          />
          合成资料体验
        </label>
      </div>
      <ErrorNotice error={error || (!results.data && results.error) || saved.error} />
      {results.isPending ? (
        <div className="discovery-loading" role="status">
          <Loader2 className="spin" size={22} />
          正在寻找{params.city}的好去处…
        </div>
      ) : (
        results.data && (
          <p className="discovery-notice">{results.data.pages[0].notice}</p>
        )
      )}
      <div className="explore-layout">
        <div className="explore-results">
          <div className="explore-results-title">
            <h2>
              {params.city} · {categories.find((c) => c[0] === params.category)?.[1]}
            </h2>
            <span aria-live="polite">已显示 {places.length} 个地点</span>
          </div>
          {!results.isPending &&
            !results.error &&
            !results.hasNextPage &&
            !results.isFetching &&
            !places.length && (
              <div className="discovery-empty">
                <Search size={32} />
                <h2>还没找到匹配的地点</h2>
                <p>换一个关键词或地点类型，再试一次。</p>
              </div>
            )}
          <div className="place-grid">
            {places.map((p) => {
              const isSaved = saved.data?.some((s) => s.place.id === p.id);
              return (
                <article
                  key={p.id}
                  className={
                    "card discovery-place" + (selected?.id === p.id ? " selected" : "")
                  }
                >
                  <button
                    className="place-photo"
                    onClick={() => setSelected(p)}
                    aria-label={"查看" + p.name}
                  >
                    <PlacePhoto photos={p.photos} alt={p.name} />
                    {p.source?.synthetic && <em>合成体验</em>}
                  </button>
                  {p.source_label === "美团" ? (
                    <span className="source-badge meituan" aria-hidden="true">
                      美团
                    </span>
                  ) : (
                    <button
                      className="place-save"
                      aria-label={(isSaved ? "已收藏" : "收藏") + p.name}
                      aria-pressed={isSaved}
                      disabled={!!busy || isSaved}
                      onClick={() => save(p)}
                    >
                      {busy === p.id ? (
                        <Loader2 size={17} className="spin" />
                      ) : (
                        <Heart size={17} fill={isSaved ? "currentColor" : "none"} />
                      )}
                    </button>
                  )}
                  <div className="place-card-copy">
                    <button onClick={() => setSelected(p)}>
                      <h3>{p.name}</h3>
                    </button>
                    <p>{(p.category || "地点").split(";").at(-1)}</p>
                    <small>{p.address || "地址信息待核实"}</small>
                    {p.price_text && (
                      <span className="place-reference-price">
                        参考费用：{p.price_text}
                      </span>
                    )}
                    <div>
                      <button className="text-link" onClick={() => setSelected(p)}>
                        地点详情 <ArrowRight size={13} />
                      </button>
                      <span>{p.source?.provider || p.source_label || "未知来源"}</span>
                    </div>
                    {onDiscuss && (
                      <button
                        className="text-link discuss-place"
                        onClick={() => onDiscuss(p)}
                        aria-label={"带到开始规划：" + p.name}
                      >
                        带到开始规划
                      </button>
                    )}
                    {p.source_label === "美团" && safeHref(p.url) && (
                      <a
                        className="text-link meituan-link"
                        href={safeHref(p.url)}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        在美团查看
                        <ExternalLink size={12} />
                      </a>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
          <div className="discovery-pagination" ref={loadMoreRef} aria-live="polite">
            {results.isFetchingNextPage ? (
              <span role="status">
                <Loader2 size={18} className="spin" /> 正在加载更多地点…
              </span>
            ) : results.isFetchNextPageError ? (
              <>
                <p>更多地点加载失败，已有结果已保留。</p>
                <Button
                  variant="secondary"
                  onClick={() => void results.fetchNextPage()}
                >
                  重试加载
                </Button>
              </>
            ) : results.hasNextPage ? (
              <Button
                variant="secondary"
                onClick={() => void results.fetchNextPage({ cancelRefetch: false })}
              >
                加载更多地点
              </Button>
            ) : places.length > 0 ? (
              <p>
                {lastPage?.end_reason === "provider_limit"
                  ? "可浏览的结果已展示，换个关键词或地点类型继续发现。"
                  : "已经到底了，换个关键词，发现更多好去处。"}
              </p>
            ) : null}
          </div>
        </div>
        <aside className="explore-map">
          <MapPanel
            day={mapDay}
            kind="explore"
            defaultOpen={true}
            active={mapActive}
            viewKey={JSON.stringify(params)}
            highlightId={selected?.id}
            fixture={params.fixture}
            onSelect={(s) => setSelected(s)}
          />
        </aside>
      </div>
      {selected && (
        <PlaceDialog
          place={selected}
          close={() => setSelected(null)}
          saved={!!saved.data?.some((s) => s.place.id === selected.id)}
          saving={!!busy}
          save={() => save(selected)}
          discuss={
            onDiscuss
              ? () => {
                  onDiscuss(selected);
                  setSelected(null);
                }
              : undefined
          }
        />
      )}
    </div>
  );
}

function PlaceDialog({
  place,
  close,
  saved,
  saving,
  save,
  discuss,
}: {
  discuss?: () => void;
  place: DiscoveryPlace;
  close: () => void;
  saved: boolean;
  saving: boolean;
  save: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const dialog = dialogRef.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      previouslyFocused?.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialogRef}
      className="discovery-dialog"
      aria-label={place.name + "详情"}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <section className="modal discovery-detail">
        <button className="modal-close" aria-label="关闭地点详情" onClick={close}>
          <X size={20} />
        </button>
        <span className="eyebrow">{place.city} · 地点详情</span>
        <h2>{place.name}</h2>
        <p>{place.description || "暂无地点介绍"}</p>
        {place.source_label === "美团" && place.price_text && (
          <p className="meituan-price">参考：{place.price_text}</p>
        )}
        <dl>
          <dt>地址</dt>
          <dd>{place.address || "待核实"}</dd>
          <dt>开放时间</dt>
          <dd>{place.opening_text || "未提供，请向场所核实"}</dd>
          <dt>参考费用</dt>
          <dd>{place.price_text || "未提供，请以场所或预订平台为准"}</dd>
          <dt>资料来源</dt>
          <dd>
            {place.source?.provider || place.source_label || "未知来源"}
            {place.source?.retrieved_at
              ? " · " + place.source.retrieved_at.slice(0, 10)
              : ""}
          </dd>
        </dl>
        <div className="discovery-detail-actions">
          {discuss && (
            <Button variant="secondary" onClick={discuss}>
              带到开始规划
            </Button>
          )}
          {place.source_label === "美团" ? (
            safeHref(place.url) && (
              <Button asChild variant="secondary">
                <a href={safeHref(place.url)} target="_blank" rel="noopener noreferrer">
                  在美团查看优惠
                  <ExternalLink size={14} />
                </a>
              </Button>
            )
          ) : (
            <Button onClick={save} disabled={saved || saving}>
              <Heart size={16} />
              {saved ? "已加入收藏" : "加入旅行收藏"}
            </Button>
          )}
          {safeHref(place.source?.url) && (
            <Button asChild variant="secondary">
              <a
                href={safeHref(place.source?.url)}
                target="_blank"
                rel="noopener noreferrer"
              >
                查看地图来源
                <ExternalLink size={14} />
              </a>
            </Button>
          )}
        </div>
        {place.source?.synthetic && (
          <p className="notice">这是合成资料，不可用于实际出游。</p>
        )}
      </section>
    </dialog>
  );
}

export function SavedPlacesPage() {
  const client = useQueryClient();
  const saved = useQuery({
    queryKey: ["saved-places"],
    queryFn: () => api<SavedPlace[]>("/saved-places"),
  });
  const [filter, setFilter] = useState("全部收藏"),
    [search, setSearch] = useState(""),
    [editing, setEditing] = useState<SavedPlace | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const folders = Array.from(new Set(saved.data?.map((s) => s.collection) || []));
  const items = (saved.data || []).filter(
    (s) =>
      (filter === "全部收藏" || s.collection === filter) &&
      [s.place.name, s.place.city, s.note].join(" ").includes(search),
  );
  async function remove(row: SavedPlace) {
    setBusy(true);
    setError("");
    try {
      await api("/saved-places/" + row.id, { method: "DELETE" });
      await client.invalidateQueries({ queryKey: ["saved-places"] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function update(e: React.FormEvent) {
    e.preventDefault();
    if (!editing) return;
    setBusy(true);
    setError("");
    try {
      await api("/saved-places/" + editing.id, {
        method: "PATCH",
        body: JSON.stringify({
          collection: editing.collection,
          note: editing.note,
        }),
      });
      await client.invalidateQueries({ queryKey: ["saved-places"] });
      setEditing(null);
      setFilter("全部收藏");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page saved-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">收藏一份出发的期待</span>
          <h1>好地方，先收藏。</h1>
          <p>按旅行心愿分类，记下想去的理由，随时带进下一次规划。</p>
        </div>
        <Button asChild>
          <Link to="/explore">
            <Compass size={16} />
            发现更多地点
          </Link>
        </Button>
      </div>
      <div className="saved-tools">
        <div className="explore-filters">
          {["全部收藏", ...folders].map((f) => (
            <button
              key={f}
              className={f === filter ? "selected" : ""}
              onClick={() => setFilter(f)}
            >
              {f}
            </button>
          ))}
        </div>
        <label className="saved-search">
          <Search size={16} />
          <input
            aria-label="搜索收藏"
            placeholder="地点、城市或备注"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      <ErrorNotice error={error || saved.error} />
      {saved.isPending ? (
        <p role="status">正在打开收藏夹…</p>
      ) : !items.length ? (
        <div className="discovery-empty">
          <Bookmark size={36} />
          <h2>{saved.data?.length ? "没有匹配的收藏" : "把想去的地方，留在这里。"}</h2>
          <p>在探索页面收藏一个地点，就能开始整理你的旅行心愿单。</p>
          <Button asChild variant="secondary">
            <Link to="/explore">
              去发现好地方
              <ArrowRight size={15} />
            </Link>
          </Button>
        </div>
      ) : (
        <div className="saved-grid">
          {items.map((row) => (
            <article className="card saved-card" key={row.id}>
              <div className="saved-card-heading">
                <MapPin size={20} />
                <span>
                  {row.place.city} · {row.collection}
                </span>
                <button
                  onClick={() => remove(row)}
                  disabled={busy}
                  aria-label={"移除收藏" + row.place.name}
                >
                  <Trash2 size={16} />
                </button>
              </div>
              <h2>{row.place.name}</h2>
              <p>{row.place.address || "地址待核实"}</p>
              {row.place.source?.synthetic && (
                <span className="status-pill">合成资料 · 不可出游</span>
              )}
              <div className="saved-note">{row.note || "还没写下想去的理由。"}</div>
              <div className="saved-card-actions">
                <button
                  className="text-link"
                  onClick={() => {
                    setError("");
                    setEditing(row);
                  }}
                >
                  <SlidersHorizontal size={14} />
                  编辑收藏
                </button>
                <Button asChild size="sm" variant="secondary">
                  <Link to={"/?saved=" + row.id}>
                    用此地点规划
                    <ArrowRight size={14} />
                  </Link>
                </Button>
              </div>
            </article>
          ))}
        </div>
      )}
      {editing && (
        <div className="modal-scrim" onClick={() => !busy && setEditing(null)}>
          <form
            className="modal saved-edit"
            role="dialog"
            aria-modal="true"
            aria-label="编辑旅行收藏"
            onClick={(e) => e.stopPropagation()}
            onSubmit={update}
          >
            <button
              type="button"
              className="modal-close"
              aria-label="关闭收藏编辑"
              onClick={() => setEditing(null)}
            >
              <X size={20} />
            </button>
            <h2>整理这份旅行心愿</h2>
            <p>{editing.place.name}</p>
            <label>
              收藏夹名称
              <input
                value={editing.collection}
                required
                maxLength={60}
                list="saved-folders"
                onChange={(e) => setEditing({ ...editing, collection: e.target.value })}
              />
              <datalist id="saved-folders">
                {folders.map((f) => (
                  <option key={f} value={f} />
                ))}
              </datalist>
            </label>
            <label>
              想去的理由
              <textarea
                rows={4}
                maxLength={1000}
                value={editing.note}
                onChange={(e) => setEditing({ ...editing, note: e.target.value })}
              />
            </label>
            <ErrorNotice error={error} />
            <Button disabled={busy}>保存收藏</Button>
          </form>
        </div>
      )}
    </div>
  );
}

export function AssistantSetup() {
  const client = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<{ preferences: Record<string, string> }>("/auth/me"),
  });
  const [prefs, setPrefs] = useState<Record<string, string>>({}),
    [step, setStep] = useState(0),
    [busy, setBusy] = useState(false),
    [done, setDone] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    if (me.data) setPrefs(me.data.preferences);
  }, [me.data]);
  async function save() {
    setBusy(true);
    setError("");
    try {
      await api("/preferences", { method: "PUT", body: JSON.stringify(prefs) });
      await client.invalidateQueries({ queryKey: ["me"] });
      setDone(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="page assistant-page">
      <div className="page-heading">
        <div>
          <span className="eyebrow">让每次出发，都更合你心意</span>
          <h1>认识一下，你的旅行方式。</h1>
          <p>只保存你主动填写的偏好，每次规划时都可以更改。</p>
        </div>
      </div>
      <section className="card assistant-setup">
        <div className="setup-progress">
          {["常去哪里", "喜欢什么", "怎样旅行"].map((s, i) => (
            <button
              key={s}
              className={i === step ? "active" : ""}
              onClick={() => {
                setStep(i);
                setDone(false);
              }}
            >
              <span>{i + 1}</span>
              {s}
            </button>
          ))}
        </div>
        {done ? (
          <div className="setup-done">
            <Check size={38} />
            <h2>旅行助手，已经更了解你了。</h2>
            <p>新对话与规划表单会读取这些偏好。你随时可以回来修改。</p>
            <Button asChild>
              <Link to="/">
                开始我的旅行
                <ArrowRight size={16} />
              </Link>
            </Button>
          </div>
        ) : (
          <>
            <div className="setup-body">
              {step === 0 ? (
                <>
                  <h2>下一程，通常从哪里开始？</h2>
                  <p>留空也没关系，旅行时再决定。</p>
                  <label>
                    默认目的地
                    <input
                      value={prefs.default_city || ""}
                      maxLength={40}
                      onChange={(e) =>
                        setPrefs({ ...prefs, default_city: e.target.value })
                      }
                      placeholder="例如：北京"
                    />
                  </label>
                  <label>
                    默认旅行天数
                    <select
                      aria-label="默认旅行天数"
                      value={prefs.default_days || ""}
                      onChange={(e) =>
                        setPrefs({ ...prefs, default_days: e.target.value })
                      }
                    >
                      <option value="">每次单独决定</option>
                      {Array.from({ length: 14 }, (_, i) => (
                        <option key={i} value={i + 1}>
                          {i + 1} 天
                        </option>
                      ))}
                    </select>
                  </label>
                </>
              ) : step === 1 ? (
                <>
                  <h2>让你心动的旅行体验</h2>
                  <p>选择喜欢的内容，也可以自己补充。</p>
                  <div className="setup-interests">
                    {[
                      "历史文化",
                      "当地美食",
                      "博物馆",
                      "公园与自然",
                      "艺术展览",
                      "亲子活动",
                      "轻徒步",
                      "城市漫游",
                    ].map((item) => (
                      <button
                        key={item}
                        aria-pressed={(prefs.travel_style || "")
                          .split("、")
                          .includes(item)}
                        onClick={() => {
                          const values = (prefs.travel_style || "")
                            .split("、")
                            .filter(Boolean);
                          setPrefs({
                            ...prefs,
                            travel_style: values.includes(item)
                              ? values.filter((v) => v !== item).join("、")
                              : [...values, item].join("、"),
                          });
                        }}
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                  <label>
                    旅行风格与兴趣
                    <input
                      value={prefs.travel_style || ""}
                      maxLength={300}
                      onChange={(e) =>
                        setPrefs({ ...prefs, travel_style: e.target.value })
                      }
                    />
                  </label>
                  <label>
                    饮食偏好
                    <input
                      value={prefs.food || ""}
                      maxLength={300}
                      onChange={(e) => setPrefs({ ...prefs, food: e.target.value })}
                      placeholder="例如：喜欢本地小吃，少辣"
                    />
                  </label>
                </>
              ) : (
                <>
                  <h2>把节奏，交给自己。</h2>
                  <p>说说你的步调和需要照顾的安排。</p>
                  <label>
                    旅行节奏
                    <select
                      aria-label="旅行节奏"
                      value={prefs.pace || ""}
                      onChange={(e) => setPrefs({ ...prefs, pace: e.target.value })}
                    >
                      <option value="">每次单独决定</option>
                      <option>轻松慢游，每天少安排一些</option>
                      <option>适中，兼顾景点与休息</option>
                      <option>充实，希望多看看不同地方</option>
                      {prefs.pace &&
                        ![
                          "轻松慢游，每天少安排一些",
                          "适中，兼顾景点与休息",
                          "充实，希望多看看不同地方",
                        ].includes(prefs.pace) && <option>{prefs.pace}</option>}
                    </select>
                  </label>
                  <label>
                    出行需求
                    <textarea
                      rows={3}
                      value={prefs.accessibility || ""}
                      maxLength={300}
                      onChange={(e) =>
                        setPrefs({ ...prefs, accessibility: e.target.value })
                      }
                      placeholder="例如：希望少走路，尽量选择无障碍路线"
                    />
                  </label>
                </>
              )}
            </div>
            <ErrorNotice error={error || me.error} />
            <div className="setup-footer">
              <button disabled={step === 0 || busy} onClick={() => setStep(step - 1)}>
                上一步
              </button>
              {step < 2 ? (
                <Button onClick={() => setStep(step + 1)}>
                  下一步
                  <ArrowRight size={16} />
                </Button>
              ) : (
                <Button disabled={busy || me.isPending || !!me.error} onClick={save}>
                  {busy ? <Loader2 className="spin" size={16} /> : <Check size={16} />}
                  保存旅行偏好
                </Button>
              )}
            </div>
          </>
        )}
      </section>
    </div>
  );
}
