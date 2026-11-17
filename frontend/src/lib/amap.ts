/** 高德 Web JS 2.0 加载器：整个应用只注入一次 script。 */
export type AMapConfig = { key: string; serviceHost: string };

declare global {
  interface Window {
    AMap: any;
    _AMapSecurityConfig: { serviceHost?: string } | undefined;
  }
}

let loading: Promise<void> | undefined;
const SDK_LOAD_TIMEOUT_MS = 15_000;

export function loadAMap(key: string, serviceHost: string): Promise<void> {
  if (window.AMap?.Map) return Promise.resolve();
  if (loading) return loading;
  loading = new Promise<void>((resolve, reject) => {
    window._AMapSecurityConfig = {
      serviceHost: /^https?:/.test(serviceHost)
        ? serviceHost
        : location.origin + serviceHost,
    };
    const script = document.createElement("script");
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
    script.async = true;
    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      script.onload = null;
      script.onerror = null;
      if (error) {
        script.remove();
        loading = undefined;
        reject(error);
      } else resolve();
    };
    const timer = setTimeout(
      () => finish(new Error("地图脚本加载超时，请检查网络后重新加载。")),
      SDK_LOAD_TIMEOUT_MS,
    );
    script.onload = () =>
      finish(
        window.AMap?.Map
          ? undefined
          : new Error("地图脚本未能初始化，请检查 JS Key 与网络。"),
      );
    script.onerror = () =>
      finish(new Error("高德地图脚本加载失败，请检查网络及 JS Key 权限"));
    document.head.appendChild(script);
  });
  return loading;
}
