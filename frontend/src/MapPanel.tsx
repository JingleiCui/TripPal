import { useEffect, useId, useRef } from "react";
import { MapPinned } from "lucide-react";
import { publishMapScene } from "./lib/mapScene";
import type { Day, Hotel, Stop } from "./types";

/**
 * 地图场景适配器 + 紧凑的状态条。
 *
 * 真实高德地图由外壳层的 GlobalMapCanvas 单例持有，默认显示在页面右侧，
 * 并随当前页面的行程场景实时更新；这里只发布场景，保留原有 props 签名，
 * 各调用点无需改动。
 */
export function MapPanel({
  day,
  onSelect,
  fixture,
  allDays,
  hotels,
  highlightId,
  kind = "itinerary",
  viewKey,
}: {
  day?: Day;
  onSelect: (s: Stop) => void;
  fixture: boolean;
  allDays?: Day[];
  hotels?: (Hotel & { user_selected?: boolean })[];
  highlightId?: string;
  kind?: "explore" | "itinerary";
  viewKey?: string;
}) {
  const id = useId();
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;

  useEffect(() => {
    publishMapScene(id, {
      day,
      allDays,
      hotels,
      highlightId,
      fixture,
      kind,
      viewKey,
      onSelect: (stop) => onSelectRef.current(stop),
    });
  }, [id, day, allDays, hotels, highlightId, fixture, kind, viewKey]);
  useEffect(() => () => publishMapScene(id, null), [id]);

  const stopCount = allDays?.length
    ? allDays.reduce((total, item) => total + (item?.stops?.length ?? 0), 0)
    : (day?.stops?.length ?? 0);

  return (
    <div className="map-shell mf-map-entry" data-map-state="delegated">
      <span className="mf-map-entry-icon" aria-hidden="true">
        <MapPinned size={16} />
      </span>
      <div className="mf-map-entry-text">
        <b>{kind === "explore" ? "地点与地图同步" : "行程与地图同步"}</b>
        <small>
          {fixture
            ? "合成流程验证视图，不代表真实地点"
            : stopCount
              ? `${stopCount} 个地点 · 点选标记查看详情`
              : "点选标记查看地点详情"}
        </small>
      </div>
    </div>
  );
}
