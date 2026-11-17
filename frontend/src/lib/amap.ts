/** 高德 Web JS 2.0 加载器：整个应用只注入一次 script。 */
export type AMapConfig = { key: string; serviceHost: string };

declare global {
  interface Window {
    AMap: any;
    _AMapSecurityConfig: { serviceHost?: string } | undefined;
  }
}

let loading: Promise<void> | undefined;

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
    script.onload = () => resolve();
    script.onerror = () => {
      loading = undefined;
      reject(new Error("高德地图脚本加载失败，请检查网络及 JS Key 权限"));
    };
    document.head.appendChild(script);
  });
  return loading;
}
