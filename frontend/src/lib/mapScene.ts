/**
 * 地图场景的轻量外部 store。
 *
 * 为什么不用 Context：页面内的 MapPanel 与外壳的 GlobalMapCanvas 是兄弟节点，
 * 用模块级 store + useSyncExternalStore 可以让场景更新只重渲染地图画布，
 * 不会回灌到页面组件，避免 effect → setState → 重渲染 → effect 的循环。
 * 多个 MapPanel 同时挂载时，以「最近发布的」为准（切 tab 时的常见情况）。
 */
import type { Day, Hotel, Stop } from "../types";

export type MapScene = {
  kind?: "explore" | "itinerary";
  defaultOpen?: boolean;
  viewKey?: string;
  day?: Day;
  allDays?: Day[];
  hotels?: (Hotel & { user_selected?: boolean })[];
  highlightId?: string;
  fixture?: boolean;
  onSelect?: (stop: Stop) => void;
};

export type MapSnapshot = {
  scene: MapScene | null;
  showAll: boolean;
  viewerOpen: boolean;
};

const scenes = new Map<string, MapScene>();
const listeners = new Set<() => void>();
let showAll = false;
// 地图默认显示：有地图场景的页面（行程 / 对话 / 探索）右侧始终展示真实地图。
// 用户仍可主动「收起」；收起后由悬浮按钮恢复。
let viewerOpen = true;
let snapshot: MapSnapshot = { scene: null, showAll: false, viewerOpen: true };

function recompute() {
  const values = [...scenes.values()];
  const scene = values.length ? values[values.length - 1] : null;
  if (
    snapshot.scene === scene &&
    snapshot.showAll === showAll &&
    snapshot.viewerOpen === viewerOpen
  )
    return;
  snapshot = { scene, showAll, viewerOpen };
  listeners.forEach((listener) => listener());
}

export function publishMapScene(id: string, scene: MapScene | null) {
  const wasEmpty = scenes.size === 0;
  // delete + set 保证「最近发布的场景」排在最后。
  scenes.delete(id);
  if (scene) scenes.set(id, scene);
  // 进入新的有地图页面时恢复默认展开：不能让上一次手动收起的状态
  // 延续到下一页，否则用户会觉得「地图要点开才能看到」。
  if (wasEmpty && scene) viewerOpen = scene.defaultOpen ?? true;
  recompute();
}

export function setMapShowAll(value: boolean) {
  showAll = value;
  recompute();
}

/** 展开 / 收起右侧地图面板。默认展开，地图实时随场景变化。 */
export function setMapViewerOpen(value: boolean) {
  viewerOpen = value;
  recompute();
}
export function openMapViewer() {
  setMapViewerOpen(true);
}
export function closeMapViewer() {
  setMapViewerOpen(false);
}

export function subscribeMapScene(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getMapSceneSnapshot(): MapSnapshot {
  return snapshot;
}

export function getServerMapSceneSnapshot(): MapSnapshot {
  return { scene: null, showAll: false, viewerOpen: true };
}
