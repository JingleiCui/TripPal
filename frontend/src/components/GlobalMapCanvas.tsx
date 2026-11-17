import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { ArrowUpRight, KeyRound, Layers, MapPinned, X } from "lucide-react";
import { api } from "../api";
import { loadAMap, type AMapConfig } from "../lib/amap";
import {
  closeMapViewer,
  getMapSceneSnapshot,
  getServerMapSceneSnapshot,
  openMapViewer,
  setMapShowAll,
  subscribeMapScene,
} from "../lib/mapScene";

type MapState = "loading" | "ready" | "no-key" | "error" | "fixture";

/** 大地色系：墨绿主色 + 赭橙餐饮，与纸质地图书配色一致。 */
const DAY_COLORS = [
  "#234b42",
  "#a6783f",
  "#5a6b75",
  "#8a6f5b",
  "#6b7a5a",
  "#a05c48",
  "#707c86",
];
const DINING_COLOR = "#c05f35";

/** 无 Key / fixture / 加载失败时的纸质地图书占位，避免白屏。 */
function PaperMapBackdrop() {
  return (
    <svg
      className="mf-paper-map"
      viewBox="0 0 1440 900"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
    >
      <defs>
        <pattern id="mf-contour" width="96" height="96" patternUnits="userSpaceOnUse">
          <path
            d="M0 48 Q24 20 48 48 T96 48 M0 78 Q30 54 60 78 T120 78"
            fill="none"
            stroke="rgba(107,122,90,.16)"
            strokeWidth="1"
          />
        </pattern>
      </defs>
      <rect width="1440" height="900" fill="#eee9dc" />
      <path
        d="M0 150 Q280 210 460 130 T900 170 T1440 90 L1440 0 L0 0Z"
        fill="#e3ebdd"
        opacity=".75"
      />
      <path
        d="M980 560 Q1100 500 1260 580 T1440 620 L1440 900 L900 900Z"
        fill="#e3ebdd"
        opacity=".6"
      />
      <path
        d="M-40 700 Q220 620 400 700 T820 660 T1200 760 T1500 700"
        fill="none"
        stroke="#dbe6e4"
        strokeWidth="86"
        opacity=".95"
      />
      <path
        d="M0 0 L1440 900 M0 900 L1440 0"
        stroke="rgba(185,179,163,.45)"
        strokeWidth="2"
      />
      <path
        d="M120 0 V900 M420 0 V900 M760 0 V900 M1080 0 V900 M1320 0 V900"
        stroke="rgba(185,179,163,.35)"
        strokeWidth="1.5"
      />
      <path
        d="M0 220 H1440 M0 470 H1440 M0 720 H1440"
        stroke="rgba(185,179,163,.35)"
        strokeWidth="1.5"
      />
      <rect width="1440" height="900" fill="url(#mf-contour)" />
      <path
        d="M280 620 Q420 520 560 560 T860 420 T1120 330"
        fill="none"
        stroke="rgba(192,95,53,.42)"
        strokeWidth="2.5"
        strokeDasharray="8 9"
      />
      <g
        fill="rgba(90,107,117,.62)"
        fontFamily="Georgia, 'Songti SC', serif"
        fontSize="15"
        letterSpacing="2"
      >
        <text x="318" y="300">
          旧城街区
        </text>
        <text x="900" y="250">
          河岸步道
        </text>
        <text x="1080" y="720">
          南岸
        </text>
        <text x="560" y="800">
          中轴线
        </text>
      </g>
    </svg>
  );
}

const PLACEHOLDER_COPY: Record<MapState, { title: string; body: string }> = {
  loading: { title: "正在打开地图", body: "地点、路线与每日安排会同步显示在这里。" },
  ready: { title: "", body: "" },
  "no-key": {
    title: "地图等待接入",
    body: "配置高德 Web JS Key 后，将显示真实地点、路网与交通线路。未配置时这里是一张纸质地图书，不影响其他功能使用。",
  },
  fixture: {
    title: "流程验证视图",
    body: "当前地点与线路是合成测试资料，不代表真实地图。为保持证据口径一致，此模式不叠加真实高德底图。",
  },
  error: {
    title: "地图暂时无法加载",
    body: "请检查网络、JS Key 权限与安全代理配置后重试。规划、资料与版本功能不受影响。",
  },
};

export function GlobalMapCanvas({ mode }: { mode: "travel" | "manage" }) {
  const { scene, showAll, viewerOpen } = useSyncExternalStore(
    subscribeMapScene,
    getMapSceneSnapshot,
    getServerMapSceneSnapshot,
  );
  const rootRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<any>(null);
  const overlaysRef = useRef<any[]>([]);
  const markersRef = useRef<Map<string, { marker: any; element: HTMLDivElement }>>(
    new Map(),
  );
  const readyRef = useRef(false);
  const [state, setState] = useState<MapState>("loading");
  const [message, setMessage] = useState("");
  // 地图默认显示；首次进入「有场景的旅行页」才加载高德 SDK，此后 DOM 与实例常驻。
  const [everOpened, setEverOpened] = useState(false);
  const hasScene = !!(
    scene?.day?.stops?.length ||
    (scene?.allDays?.length ?? 0) > 0 ||
    scene?.hotels?.length
  );
  const viewerVisible = viewerOpen && mode === "travel" && hasScene;

  useEffect(() => {
    if (viewerVisible) setEverOpened(true);
  }, [viewerVisible]);

  // 只创建一次 AMap 实例：跨路由、跨天常驻，不随页面组件卸载而 destroy。
  useEffect(() => {
    if (!everOpened) return;
    let dead = false;
    let map: any;
    let timer: ReturnType<typeof setTimeout> | undefined;
    api<AMapConfig>("/map-config")
      .then(async (config) => {
        if (dead) return;
        if (!config.key) {
          setState("no-key");
          return;
        }
        await loadAMap(config.key, config.serviceHost);
        if (dead || !rootRef.current) return;
        map = new window.AMap.Map(rootRef.current, {
          zoom: 12,
          center: [116.4074, 39.9042],
          mapStyle: "amap://styles/normal",
          resizeEnable: true,
          viewMode: "2D",
          // 滚轮交给页面滚动：上下滑动时地图不会自己缩放，页面不会卡住。
          // 缩放改用官方 +/- 控件与双击，兼顾地图交互与阅读体验。
          scrollWheel: false,
        });
        mapRef.current = map;
        map.on("complete", () => {
          if (dead) return;
          readyRef.current = true;
          setState("ready");
          clearTimeout(timer);
          try {
            window.AMap.plugin?.("AMap.ToolBar", () => {
              if (dead || !mapRef.current) return;
              mapRef.current.addControl(
                new window.AMap.ToolBar({
                  position: { right: "14px", bottom: "72px" },
                }),
              );
            });
          } catch {
            // 控件插件不可用时不影响底图、标记与路线。
          }
        });
        timer = setTimeout(() => {
          if (!dead && !readyRef.current) {
            setState("error");
            setMessage("地图底图未完成加载，请检查网络、JS Key 和安全配置后重试。");
          }
        }, 15000);
      })
      .catch((error: Error) => {
        if (!dead) {
          setState("error");
          setMessage(error.message);
        }
      });
    return () => {
      dead = true;
      clearTimeout(timer);
      map?.destroy?.();
      mapRef.current = null;
      overlaysRef.current = [];
      markersRef.current.clear();
    };
  }, [everOpened]);

  const effectiveState: MapState = scene?.fixture ? "fixture" : state;

  // 场景变化只增删 overlay，不重建地图实例（修复原先 day 变化即 map.destroy 的问题）。
  useEffect(() => {
    const map = mapRef.current;
    if (!map || effectiveState !== "ready") return;
    overlaysRef.current.forEach((overlay) => map.remove(overlay));
    overlaysRef.current = [];
    markersRef.current.clear();

    const days =
      showAll && scene?.allDays?.length ? scene.allDays : scene?.day ? [scene.day] : [];

    days.forEach((activeDay) => {
      const color = DAY_COLORS[(activeDay.day - 1) % DAY_COLORS.length];
      activeDay.stops.forEach((stop, index) => {
        const dining = /餐厅|餐饮|茶艺馆|咖啡/.test(
          (stop as typeof stop & { category?: string }).category || "",
        );
        const element = document.createElement("div");
        element.className = "mf-amap-pin";
        element.style.background = dining ? DINING_COLOR : color;
        element.textContent = dining ? "食" : String(index + 1);
        element.classList.toggle("is-active", stop.id === scene?.highlightId);
        const marker = new window.AMap.Marker({
          position: [stop.lon, stop.lat],
          content: element,
          offset: new window.AMap.Pixel(-15, -15),
        });
        marker.on("click", () => {
          scene?.onSelect?.(stop);
          const detail = document.createElement("div");
          detail.className = "mf-amap-info";
          detail.textContent = `第 ${activeDay.day} 天 · ${stop.name}`;
          new window.AMap.InfoWindow({
            content: detail,
            offset: new window.AMap.Pixel(0, -26),
          }).open(map, [stop.lon, stop.lat]);
        });
        map.add(marker);
        overlaysRef.current.push(marker);
        markersRef.current.set(stop.id, { marker, element });
      });

      [
        ...(activeDay.arrival_route ? [activeDay.arrival_route] : []),
        ...activeDay.routes,
      ].forEach((route) => {
        if (route.polyline?.length > 1) {
          const line = new window.AMap.Polyline({
            path: route.polyline,
            strokeColor: color,
            strokeWeight: 5,
            strokeOpacity: 0.78,
            lineJoin: "round",
          });
          map.add(line);
          overlaysRef.current.push(line);
        }
      });
    });

    scene?.hotels
      ?.filter((hotel) => showAll || !scene?.day?.city || hotel.city === scene.day.city)
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
          detail.className = "mf-amap-info";
          detail.textContent =
            (hotel.user_selected ? "已选住宿（未预订）· " : "推荐住宿（未预订）· ") +
            hotel.name;
          new window.AMap.InfoWindow({ content: detail }).open(map, [
            hotel.lon,
            hotel.lat,
          ]);
        });
        map.add(marker);
        overlaysRef.current.push(marker);
      });

    if (scene?.day?.stops?.length) map.setFitView();
  }, [scene, showAll, effectiveState]);

  // 高亮只改 class 与视角，不重建任何 overlay。
  useEffect(() => {
    markersRef.current.forEach(({ marker, element }, id) => {
      const active = id === scene?.highlightId;
      element.classList.toggle("is-active", active);
      if (active) {
        marker.setzIndex?.(999);
        mapRef.current?.panTo(marker.getPosition());
      }
    });
  }, [scene?.highlightId]);

  // 面板展开 / 收起或场景变化时，容器尺寸改变后通知 AMap 重算并收回视野。
  useEffect(() => {
    if (!viewerVisible || state !== "ready") return;
    const timer = setTimeout(() => {
      const map = mapRef.current;
      if (!map) return;
      map.resize?.();
      if (scene?.day?.stops?.length) map.setFitView?.();
    }, 120);
    return () => clearTimeout(timer);
  }, [viewerVisible, state, scene]);

  // 地图是常驻面板而非模态框：不锁页面滚动，Esc 只做「收起」。
  useEffect(() => {
    if (!viewerVisible) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") closeMapViewer();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [viewerVisible]);

  const days =
    showAll && scene?.allDays?.length ? scene.allDays : scene?.day ? [scene.day] : [];
  const copy = PLACEHOLDER_COPY[effectiveState];
  const stopCount = days.reduce((total, day) => total + (day?.stops?.length ?? 0), 0);

  return (
    <>
      {/* 仅在主动收起地图后出现，作为唯一的「重新展开」入口。 */}
      {mode === "travel" && hasScene && !viewerOpen && (
        <button
          type="button"
          className="mf-map-fab"
          onClick={openMapViewer}
          aria-label="展开行程地图"
        >
          <span className="mf-map-fab-icon" aria-hidden="true">
            <MapPinned size={19} />
          </span>
          <span className="mf-map-fab-copy">
            <b>查看地图</b>
            <small>
              {scene?.fixture
                ? "合成流程验证视图"
                : stopCount
                  ? `${stopCount} 个地点 · 真实高德地图`
                  : "真实高德地图"}
            </small>
          </span>
          <ArrowUpRight size={15} aria-hidden="true" />
        </button>
      )}

      {/* 右侧常驻地图面板：DOM 常驻，AMap 实例不随展开/收起重建。 */}
      <div
        className={"mf-map-viewer" + (viewerVisible ? " is-open" : "")}
        aria-hidden={!viewerVisible}
      >
        <section className="mf-map-dialog" role="region" aria-label="行程地图">
          <header className="mf-map-dialog-bar">
            <div className="mf-map-dialog-heading">
              <span className="mf-map-dialog-icon" aria-hidden="true">
                <MapPinned size={18} />
              </span>
              <div>
                <b>行程地图</b>
                <small>
                  {scene?.fixture
                    ? "合成流程验证视图 · 不代表真实地点"
                    : "高德地图 · 点选标记查看地点详情"}
                </small>
              </div>
            </div>
            <div className="mf-map-dialog-tools">
              {(scene?.allDays?.length ?? 0) > 1 && (
                <label className="mf-map-switch">
                  <input
                    type="checkbox"
                    checked={showAll}
                    onChange={(event) => setMapShowAll(event.target.checked)}
                  />
                  <Layers size={14} aria-hidden="true" />
                  显示全部天数
                </label>
              )}
              <button
                type="button"
                className="mf-map-dialog-close"
                onClick={closeMapViewer}
                aria-label="收起地图"
              >
                <X size={18} />
                <span>收起</span>
              </button>
            </div>
          </header>

          <div className="mf-map-layer">
            <div ref={rootRef} className="mf-map-root" aria-hidden="true" />

            {effectiveState !== "ready" && (
              <div className="mf-map-placeholder">
                <PaperMapBackdrop />
                <div className="mf-map-notice mf-glass" role="status">
                  <span className="mf-map-notice-icon" aria-hidden="true">
                    {effectiveState === "no-key" ? (
                      <KeyRound size={19} />
                    ) : (
                      <MapPinned size={19} />
                    )}
                  </span>
                  <b>{copy.title}</b>
                  <p>{effectiveState === "error" && message ? message : copy.body}</p>
                  {effectiveState === "no-key" && (
                    <Link to="/settings" className="mf-btn mf-btn-outline">
                      查看配置指南 →
                    </Link>
                  )}
                </div>
              </div>
            )}

            <div className="mf-map-controls">
              {days.length > 0 && effectiveState === "ready" && (
                <div className="mf-map-legend">
                  {days.map((day) => (
                    <span key={day.day}>
                      <i
                        style={{
                          background: DAY_COLORS[(day.day - 1) % DAY_COLORS.length],
                        }}
                      />
                      第 {day.day} 天{day.city ? " · " + day.city : ""}
                    </span>
                  ))}
                  {scene?.hotels?.length ? <span>住宿地点 · 尚未预订</span> : null}
                </div>
              )}
            </div>

            {scene?.day && effectiveState === "ready" && (
              <div className="mf-map-day mf-glass">
                <span className="mf-eyebrow">当前查看</span>
                <b>
                  第 {scene.day.day} 天 · {scene.day.date}
                </b>
                <small>{scene.day.stops.length} 处安排</small>
              </div>
            )}
            <span className="mf-map-caption">
              {scene?.fixture ? "合成流程 · 禁止据此出游" : "高德地图 · GCJ-02 坐标"}
            </span>
          </div>

          <footer className="mf-map-dialog-foot">
            <span>拖拽平移 · 用 +/- 或双击缩放 · 点击标记查看地点</span>
            <span>按 Esc 或点「收起」隐藏地图</span>
          </footer>
        </section>
      </div>
    </>
  );
}
