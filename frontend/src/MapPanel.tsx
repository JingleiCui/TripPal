import { useEffect, useRef, useState } from "react";
import { MapPinned, KeyRound, ExternalLink } from "lucide-react";
import { api } from "./api";
import type { Day, Stop, Hotel } from "./types";
declare global {
  interface Window {
    AMap: any;
    _AMapSecurityConfig: any;
    __amapReady?: () => void;
  }
}
let loading: Promise<void> | undefined;
function loadMap(key: string, serviceHost: string) {
  if (window.AMap) return Promise.resolve();
  if (loading) return loading;
  loading = new Promise((resolve, reject) => {
    window._AMapSecurityConfig = { serviceHost: location.origin + serviceHost };
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
    script.onload = () => resolve();
    script.onerror = () => {
      loading = undefined;
      reject(new Error("地图脚本加载失败，请检查网络及 Key 权限"));
    };
    document.head.appendChild(script);
  });
  return loading;
}
export function MapPanel({
  day,
  onSelect,
  fixture,
  allDays,
  hotels,
  highlightId,
}: {
  day?: Day;
  onSelect: (s: Stop) => void;
  fixture: boolean;
  allDays?: Day[];
  hotels?: (Hotel & { user_selected?: boolean })[];
  highlightId?: string;
}) {
  const [showAll, setShowAll] = useState(false);
  const colors = [
    "#2f6957",
    "#b78d45",
    "#698ab0",
    "#9a698a",
    "#6e9153",
    "#b76e58",
    "#7883a1",
  ];
  const mapRef = useRef<any>(null);
  const markerRefs = useRef<
    Map<string, { marker: any; element: HTMLDivElement }>
  >(new Map());
  useEffect(() => {
    markerRefs.current.forEach(({ marker, element }, id) => {
      element.classList.toggle("active-map-pin", id === highlightId);
      if (id === highlightId) {
        marker.setzIndex?.(999);
        mapRef.current?.panTo(marker.getPosition());
      }
    });
  }, [highlightId]);
  const el = useRef<HTMLDivElement>(null),
    [state, setState] = useState("loading"),
    [message, setMessage] = useState("");
  useEffect(() => {
    let dead = false;
    let map: any;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    if (fixture) {
      setState("fixture");
      return;
    }
    setState("loading");
    api<{ key: string; serviceHost: string }>("/map-config")
      .then(async (config) => {
        if (!config.key) {
          setState("no-key");
          return;
        }
        await loadMap(config.key, config.serviceHost);
        if (dead || !el.current) return;
        map = new window.AMap.Map(el.current, {
          zoom: 12,
          center: [116.4074, 39.9042],
          mapStyle: "amap://styles/normal",
          resizeEnable: true,
        });
        mapRef.current = map;
        markerRefs.current.clear();
        map.on("complete", () => {
          if (!dead) setState("ready");
          clearTimeout(timeout);
        });
        timeout = setTimeout(() => {
          if (!dead) {
            setState("error");
            setMessage(
              "地图底图未完成加载，请检查网络、JS Key 和安全配置后重试。",
            );
          }
        }, 20000);
        const days = showAll && allDays?.length ? allDays : day ? [day] : [];
        days.forEach((activeDay) => {
          const color = colors[(activeDay.day - 1) % colors.length];
          activeDay.stops.forEach((stop, i) => {
            const content = document.createElement("div");
            content.className = "colored-map-pin";
            const dining = /餐厅|餐饮|茶艺馆|咖啡/.test(
              (stop as Stop & { category?: string }).category || "",
            );
            content.style.background = dining ? "#b88438" : color;
            content.textContent = dining ? "食" : String(i + 1);
            content.classList.toggle("active-map-pin", stop.id === highlightId);
            const marker = new window.AMap.Marker({
              position: [stop.lon, stop.lat],
              content,
            });
            markerRefs.current.set(stop.id, { marker, element: content });
            marker.on("click", () => {
              onSelect(stop);
              const detail = document.createElement("div");
              detail.textContent = `第 ${activeDay.day} 天 · ${stop.name}`;
              new window.AMap.InfoWindow({ content: detail }).open(map, [
                stop.lon,
                stop.lat,
              ]);
            });
            map.add(marker);
          });
          [
            ...(activeDay.arrival_route ? [activeDay.arrival_route] : []),
            ...activeDay.routes,
          ].forEach((route) => {
            if (route.polyline?.length > 1)
              map.add(
                new window.AMap.Polyline({
                  path: route.polyline,
                  strokeColor: color,
                  strokeWeight: 5,
                  strokeOpacity: 0.8,
                }),
              );
          });
        });
        hotels
          ?.filter((h) => showAll || !day?.city || h.city === day.city)
          .forEach((hotel) => {
            const marker = new window.AMap.Marker({
              position: [hotel.lon, hotel.lat],
              label: {
                content: hotel.user_selected ? "住宿" : "推荐住宿",
                direction: "top",
              },
            });
            marker.on("click", () => {
              const detail = document.createElement("div");
              detail.textContent =
                (hotel.user_selected
                  ? "已选住宿（未预订）· "
                  : "推荐住宿（未预订）· ") + hotel.name;
              new window.AMap.InfoWindow({ content: detail }).open(map, [
                hotel.lon,
                hotel.lat,
              ]);
            });
            map.add(marker);
          });
        if (day?.stops.length) map.setFitView();
      })
      .catch((e) => {
        if (!dead) {
          setState("error");
          setMessage(e.message);
        }
      });
    return () => {
      dead = true;
      clearTimeout(timeout);
      map?.destroy();
      if (mapRef.current === map) {
        mapRef.current = null;
        markerRefs.current.clear();
      }
    };
  }, [day, fixture, showAll, allDays, hotels]);
  return (
    <div className="map-shell" data-map-state={state}>
      {allDays && allDays.length > 1 && (
        <label className="all-days-map">
          <input
            type="checkbox"
            checked={showAll}
            onChange={(e) => setShowAll(e.target.checked)}
          />
          显示全部天数
        </label>
      )}
      <div ref={el} className="map-container" />
      {state !== "ready" && (
        <div className="map-empty">
          <div className="map-grid" />
          <div className="map-empty-card">
            <span className="icon-orbit">
              <MapPinned size={30} />
            </span>
            <h3>
              {state === "fixture"
                ? "流程验证视图"
                : state === "loading"
                  ? "正在加载地图"
                  : "地图等待接入"}
            </h3>
            <p>
              {state === "fixture"
                ? "当前地点与线路是合成测试资料，不代表真实地图。"
                : state === "error"
                  ? message
                  : state === "loading"
                    ? "地点、路线和每日安排将在这里同步展示。"
                    : "配置高德 Web JS Key 后，将显示真实地点与交通线路。"}
            </p>
            {state === "no-key" && (
              <small>
                <KeyRound size={13} /> 查看「平台与设置」中的配置指南
              </small>
            )}
          </div>
        </div>
      )}
      <div className="map-color-legend">
        {(showAll ? allDays : day ? [day] : [])?.map((d) => (
          <span key={d.day}>
            <i style={{ background: colors[(d.day - 1) % colors.length] }} />第{" "}
            {d.day} 天{d.city ? " · " + d.city : ""}
          </span>
        ))}
        {hotels?.length ? <span>🏨 住宿地点 · 尚未预订</span> : null}
      </div>
      <span className="map-caption">
        {fixture ? "合成流程 · 禁止据此出游" : "高德地图 · GCJ-02 坐标"}
      </span>
      {day && (
        <div className="map-day">
          <span>第 {day.day} 天</span>
          <b>{day.date}</b>
          <small>{day.stops.length} 处安排</small>
        </div>
      )}
    </div>
  );
}
