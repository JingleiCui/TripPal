import { useEffect, useMemo, useRef, useState } from "react";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { BedDouble, X, Search, Check, Loader2 } from "lucide-react";
import { api, post } from "./api";
import type { Trip, Plan, Hotel } from "./types";
import { Button } from "./components/ui/button";
import { PlacePhoto } from "./PlacePhoto";

const HOTEL_PAGE_SIZE = 20;
const PREFETCH_DISTANCE_PX = 200;
type HotelPage = { items: Hotel[]; next_page: number | null; notice: string };

export function HotelSelector({ trip }: { trip: Trip }) {
  const [open, setOpen] = useState(false);
  if (!trip.version) return null;
  return (
    <>
      <Button
        size="sm"
        variant="secondary"
        disabled={trip.role === "viewer"}
        onClick={() => setOpen(true)}
      >
        <BedDouble size={14} />
        住宿地点
      </Button>
      {open && <HotelDialog trip={trip} close={() => setOpen(false)} />}
    </>
  );
}

function HotelDialog({ trip, close }: { trip: Trip; close: () => void }) {
  const client = useQueryClient();
  const plan = trip.plan as Plan;
  const cities = Array.from(
    new Set(plan.days.map((day) => day.city || plan.requirements.city)),
  );
  const [city, setCity] = useState(cities[0] || plan.requirements.city);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<{ city: string; query: string } | null>(null);
  const [selecting, setSelecting] = useState("");
  const [error, setError] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  const results = useInfiniteQuery({
    queryKey: ["hotel-candidates", trip.id, search],
    enabled: search !== null,
    initialPageParam: 1,
    queryFn: ({ pageParam, signal }) =>
      api<HotelPage>(
        `/trips/${trip.id}/hotels?` +
          new URLSearchParams({
            city: search!.city,
            query: search!.query,
            page: String(pageParam),
            page_size: String(HOTEL_PAGE_SIZE),
          }),
        { signal },
      ),
    getNextPageParam: (lastPage) => lastPage.next_page ?? undefined,
    retry: false,
    staleTime: 0,
  });
  const items = useMemo(() => {
    if (!search) return [];
    const unique = new Map<string, Hotel>();
    for (const page of results.data?.pages ?? [])
      for (const item of page.items)
        if (!unique.has(item.id)) unique.set(item.id, item);
    return [...unique.values()];
  }, [results.data, search]);
  const { fetchNextPage, hasNextPage, isFetching, isFetchNextPageError } = results;
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialogRef.current?.showModal();
    return () => {
      dialogRef.current?.close();
      previous?.focus();
    };
  }, []);
  useEffect(() => {
    if (
      !moreRef.current ||
      !hasNextPage ||
      isFetching ||
      isFetchNextPageError ||
      typeof IntersectionObserver === "undefined"
    )
      return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting))
          void fetchNextPage({ cancelRefetch: false });
      },
      { root: dialogRef.current, rootMargin: `${PREFETCH_DISTANCE_PX}px 0px` },
    );
    observer.observe(moreRef.current);
    return () => observer.disconnect();
  }, [fetchNextPage, hasNextPage, isFetching, isFetchNextPageError]);
  async function choose(item: Hotel) {
    setSelecting(item.id);
    setError("");
    try {
      await post(`/trips/${trip.id}/hotel`, {
        place_id: item.id,
        city: search!.city,
        base_version: trip.version,
      });
      await client.invalidateQueries({ queryKey: ["trip", trip.id] });
      close();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setSelecting("");
    }
  }
  return (
    <dialog
      ref={dialogRef}
      className="hotel-dialog"
      aria-label="选择住宿地点"
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <header className="hotel-dialog-heading">
        <div>
          <h2>把住宿地点放到地图上</h2>
          <p>选择地点后更新行程；价格与库存请向预订平台核实。</p>
        </div>
        <button type="button" aria-label="关闭住宿选择" onClick={close}>
          <X size={20} />
        </button>
      </header>
      <form
        className="hotel-search"
        onSubmit={(event) => {
          event.preventDefault();
          setError("");
          setSearch({ city, query: query.trim() });
        }}
      >
        <label>
          城市
          <select
            aria-label="住宿城市"
            value={city}
            onChange={(event) => {
              setCity(event.target.value);
              setSearch(null);
            }}
          >
            {cities.map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          酒店或区域
          <input
            aria-label="酒店查询"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            maxLength={100}
            placeholder="比如：北京站附近"
            required
          />
        </label>
        <Button type="submit" disabled={!query.trim()}>
          <Search size={16} />
          查询地点
        </Button>
      </form>
      {(error || (results.isError && !results.data)) && (
        <p className="notice error" role="alert">
          {error || results.error?.message}
        </p>
      )}
      {search && (
        <p className="hotel-result-count" aria-live="polite">
          {search.city} · 已显示 {items.length} 处住宿
        </p>
      )}
      <div className="hotel-results">
        {items.map((item) => (
          <article className="hotel-choice" key={item.id}>
            <div className="hotel-choice-photo">
              <PlacePhoto photos={item.photos} alt={item.name} />
            </div>
            <div className="hotel-choice-copy">
              <h3>{item.name}</h3>
              <p>{item.address || "地址待核实"}</p>
              <small>
                {item.price_text ? `参考费用：${item.price_text}` : "价格待核实"} ·{" "}
                {item.source.provider}
              </small>
            </div>
            <Button
              size="sm"
              variant="secondary"
              disabled={!!selecting}
              onClick={() => void choose(item)}
            >
              {selecting === item.id ? (
                <Loader2 size={15} className="spin" />
              ) : (
                <Check size={15} />
              )}
              选择
            </Button>
          </article>
        ))}
      </div>
      <div ref={moreRef} className="discovery-pagination">
        {results.isFetching ? (
          <span role="status">
            <Loader2 size={18} className="spin" />
            正在查询住宿…
          </span>
        ) : results.isFetchNextPageError ? (
          <>
            <p>更多住宿加载失败，已有结果已保留。</p>
            <Button variant="secondary" onClick={() => void results.fetchNextPage()}>
              重试加载住宿
            </Button>
          </>
        ) : results.hasNextPage ? (
          <Button
            variant="secondary"
            onClick={() => void results.fetchNextPage({ cancelRefetch: false })}
          >
            加载更多住宿
          </Button>
        ) : search && !results.error ? (
          <p>
            {items.length
              ? "当前结果已展示，换个区域继续寻找。"
              : "没有匹配的住宿，请换个关键词。"}
          </p>
        ) : (
          <p>输入酒店名称或区域，寻找合适的住宿。</p>
        )}
      </div>
    </dialog>
  );
}
