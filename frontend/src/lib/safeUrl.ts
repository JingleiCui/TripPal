/**
 * 统一的外部 URL 消毒入口。
 *
 * 平台返回的图片、来源链接、购票入口都属于不可信输入，直接写进 src/href
 * 会让 javascript: / data: 之类的协议进入 DOM。这里集中做协议白名单、
 * 高德图片域的 http→https 升级，以及畸形 URL 的静默拒绝。
 */

const AMAP_IMAGE_HOSTS = new Set([
  "store.is.autonavi.com",
  "aos-comment.amap.com",
  "aos-cdn-image.amap.com",
]);

export type SafeUrlOptions = {
  /** 只允许 https（含同源 https）；用于 <img>，避免混合内容。 */
  httpsOnly?: boolean;
};

export function safeUrl(value?: string | null, options: SafeUrlOptions = {}): string {
  if (!value) return "";
  const raw = String(value).trim();
  // eslint-disable-next-line no-control-regex
  if (!raw || /[\u0000-\u001f\u007f]/.test(raw)) return "";
  try {
    const normalized = raw.startsWith("//") ? `https:${raw}` : raw;
    const url = new URL(normalized, window.location.origin);
    if (url.protocol === "http:" && AMAP_IMAGE_HOSTS.has(url.hostname)) {
      url.protocol = "https:";
    }
    if (url.protocol !== "https:" && url.protocol !== "http:") return "";
    if (url.protocol === "http:" && url.origin !== window.location.origin) return "";
    if (options.httpsOnly && url.protocol !== "https:") return "";
    return url.href;
  } catch {
    return "";
  }
}

/** 只用于 <a>；返回空串时调用方应改为渲染不可点击的文本。 */
export function safeHref(value?: string | null): string {
  return safeUrl(value);
}

/** 只用于 <img>；拒绝非 https 与畸形地址。 */
export function safeImageSrc(value?: string | null): string {
  return safeUrl(value, { httpsOnly: true });
}
