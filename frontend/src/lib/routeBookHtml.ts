/**
 * 路书下载的 HTML 兜底。
 *
 * 服务端 PDF 在历史行程数据异常、缺少中文字体等情况下可能失败；此时前端仍要
 * 交付一份「看得懂、能打印成 PDF」的设计版路书，而不是让下载按钮毫无反应。
 * 生成的 HTML 自包含（内联 CSS + 内联 Logo），不依赖任何外链资源。
 */
import type { Day, Plan, Stop } from "../types";

type BudgetLike = {
  days?: {
    day: number;
    priced_subtotal_cny: number | null;
    rows?: {
      label: string;
      category_name: string;
      subtotal_cny: number | null;
    }[];
  }[];
  notice?: string;
};

const escapeHtml = (value: unknown) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (ch) =>
      ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
      })[ch] as string,
  );

const money = (value: number | null | undefined) =>
  value == null ? "待核实" : "¥" + value.toLocaleString("zh-CN");

/** 与 components/TripalLogo.tsx 的 TripalMark 完全一致：方箱微圆角 + 黄色星光。 */
const TRIPAL_MARK = `<svg width="40" height="40" viewBox="0 0 120 120" role="img" aria-label="Tripal 旅伴" xmlns="http://www.w3.org/2000/svg">
<ellipse cx="60" cy="108" rx="39" ry="5.5" fill="#F2E3DA"/>
<path d="M45 34V20a15 15 0 0 1 30 0v14" fill="none" stroke="#EA6E4E" stroke-width="9" stroke-linecap="round"/>
<path d="M47.5 33V20a12.5 12.5 0 0 1 25 0v13" fill="none" stroke="#FFB49A" stroke-width="3" stroke-linecap="round"/>
<rect x="19" y="31" width="82" height="70" rx="25" fill="#FF8A6B"/>
<rect x="19" y="31" width="82" height="70" rx="25" fill="none" stroke="#F27A5A" stroke-width="1.5" stroke-dasharray="3 4" opacity="0.55"/>
<rect x="36" y="96" width="17" height="13" rx="6.5" fill="#E9704F"/>
<rect x="67" y="96" width="17" height="13" rx="6.5" fill="#E9704F"/>
<ellipse cx="33" cy="75" rx="7.5" ry="4.2" fill="#FFC2AD"/>
<ellipse cx="87" cy="75" rx="7.5" ry="4.2" fill="#FFC2AD"/>
<ellipse cx="47" cy="65" rx="4.3" ry="5.6" fill="#3B3432"/>
<ellipse cx="73" cy="65" rx="4.3" ry="5.6" fill="#3B3432"/>
<circle cx="45.5" cy="63" r="1.4" fill="#FFFFFF"/>
<circle cx="71.5" cy="63" r="1.4" fill="#FFFFFF"/>
<path d="M55 76q5 6 10 0" fill="none" stroke="#3B3432" stroke-width="2.6" stroke-linecap="round"/>
<path d="M101 8l3.4 8.6L113 20l-8.6 3.4L101 32l-3.4-8.6L89 20l8.6-3.4z" fill="#FFCE73"/>
</svg>`;

function weatherFor(plan: Plan, date?: string) {
  const casts = plan.weather?.forecasts?.flatMap((f) => f.casts ?? []) ?? [];
  if (!date) return null;
  const short = date.slice(5);
  const hit = casts.find((c) => c.date === date || c.date?.endsWith(short));
  if (!hit) return null;
  return `${hit.dayweather || "天气"}${hit.daytemp ? ` ${hit.daytemp}°` : ""}`;
}

function stopPrice(stop: Stop) {
  const text = stop.price_text?.trim();
  if (!text) return "待核实";
  return text.length > 18 ? text.slice(0, 18) + "…" : text;
}

function dayBlock(
  plan: Plan,
  day: Day,
  index: number,
  ledger?: BudgetLike,
): string {
  const weather =
    weatherFor(plan, day.date) ||
    (plan.weather?.note ? "天气待核实" : "出行前请查询预报");
  const budget = ledger?.days?.find((d) => d.day === day.day);
  const cost = budget?.priced_subtotal_cny ?? null;
  const stops = day.stops
    .map(
      (stop) => `<div class="stop">
        <span class="time">${escapeHtml(stop.planned_start)}</span>
        <span class="place"><b>${escapeHtml(stop.name)}</b><small>${escapeHtml(stop.address?.slice(0, 40) || "地点")}</small></span>
        <span class="price">${escapeHtml(stopPrice(stop))}</span>
      </div>`,
    )
    .join("");
  return `<section class="day d${index % 3}">
    <header><b>DAY ${String(day.day).padStart(2, "0")}</b><span>${escapeHtml(day.date?.slice(5) || "日期待定")} · ${escapeHtml(day.city || "")}</span><small>${day.stops.length} 站</small></header>
    <div class="context"><span>☀ ${escapeHtml(weather)}</span><i></i><span>当日已知花费 <b>${money(cost)}</b></span><i></i><span>已知步行 ${((day.known_route_walking_meters || 0) / 1000).toFixed(1)} km</span></div>
    ${stops || '<p class="empty">当日暂无已确认地点</p>'}
    <p class="walk">${escapeHtml(day.walking_note || "路段信息待核实")}</p>
  </section>`;
}

/**
 * 生成可独立打开、可直接打印为 PDF 的设计版路书。
 * @param plan 行程计划
 * @param ledger 可选费用账本（有则展示逐日已知花费）
 * @param tripId 仅用于页脚标识，不发起任何请求
 */
export function routeBookFallbackHtml(
  plan: Plan,
  ledger?: BudgetLike,
  tripId?: string,
): string {
  const days = plan.days ?? [];
  const stopCount = days.reduce((sum, day) => sum + (day.stops?.length ?? 0), 0);
  const walkKm = (
    days.reduce((sum, day) => sum + (day.known_route_walking_meters || 0), 0) / 1000
  ).toFixed(1);
  const budgetRows = (ledger?.days ?? [])
    .flatMap((day) => day.rows ?? [])
    .slice(0, 14)
    .map(
      (row) =>
        `<div class="budget-row"><span>${escapeHtml(row.category_name)}</span><b>${money(row.subtotal_cny)}</b></div>`,
    )
    .join("");
  const dayHtml = days
    .map((day, index) => dayBlock(plan, day, index, ledger))
    .join("");
  const routeHtml = days
    .map(
      (day, index) =>
        `<span class="legend"><i style="background:${["#ff8a6b", "#5fc9ac", "#7b8bd8", "#e8a93c"][index % 4]}"></i>DAY ${String(day.day).padStart(2, "0")} · ${escapeHtml(day.city || "")}</span>`,
    )
    .join("");

  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(plan.title)} · Tripal 路书</title><style>
*{box-sizing:border-box}body{margin:0;background:#fff7f1;color:#3b3432;font:14px/1.65 "PingFang SC","Microsoft YaHei",sans-serif}
.page{max-width:1040px;margin:0 auto;background:#fff7f1}
.header{background:linear-gradient(135deg,#ff8a6b,#fa7a58);color:#fff;padding:26px 40px 30px}
.header-top{display:flex;align-items:center;justify-content:space-between;gap:16px}
.mark{display:grid;place-items:center;width:56px;height:56px;background:#fffdf9;border-radius:16px;box-shadow:0 6px 16px rgba(120,48,30,.18)}
.doc{font-size:11px;letter-spacing:.22em;color:#ffe4da;font-weight:700}
h1{margin:18px 0 6px;font-size:34px;line-height:1.25}
.header p{margin:0;font-size:12px;color:#ffe4da}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 40px 0;padding:18px;background:#fff;border-radius:16px;text-align:center}
.stats b{display:block;font-size:22px}.stats span{font-size:11px;color:#988d87}
.grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(0,1fr);gap:20px;padding:24px 40px 0;align-items:start}
.left,.right{display:flex;flex-direction:column;gap:14px;min-width:0}
h2{font-size:14px;margin:0}.card,.day{background:#fff;border-radius:16px;padding:16px}
.day header{display:flex;align-items:baseline;gap:10px;margin-bottom:10px}
.day header b{color:#ea6e4e;font-size:13px}.day header span{font-size:12px}.day header small{margin-left:auto;color:#988d87;font-size:11px}
.d1 header b{color:#2e9e82}.d2 header b{color:#7b8bd8}
.context{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:10px;margin-bottom:10px;font-size:12px;background:#fff3ec;color:#8a6e2e}
.d1 .context{background:#ecf8f4;color:#5e7a72}.d2 .context{background:#f0f2fc;color:#5d6796}
.context i{width:1px;height:12px;background:#d8cec8}.context b{margin-left:2px}
.stop{display:grid;grid-template-columns:52px minmax(0,1fr) auto;gap:10px;align-items:baseline;padding:6px 0;border-top:1px dashed #f0e6de;font-size:12px}
.time{color:#ea6e4e;font-weight:700}.d1 .time{color:#2e9e82}.d2 .time{color:#7b8bd8}
.place b{display:block}.place small{color:#988d87}.price{color:#2e9e82;font-weight:700;white-space:nowrap}
.walk,.empty{margin:10px 0 0;font-size:11px;color:#988d87}
h3{margin:0 0 8px;font-size:13px}.card p{margin:4px 0;font-size:12px;color:#6b625e}
.budget-row{display:flex;justify-content:space-between;gap:10px;margin:7px 0;font-size:12px;color:#6b625e}
.routes{display:flex;flex-wrap:wrap;gap:9px}.legend{display:inline-flex;align-items:center;gap:5px;font-size:11px;color:#6b625e}.legend i{width:9px;height:9px;border-radius:50%}
.foot{display:flex;justify-content:space-between;gap:16px;margin:26px 40px 0;padding-top:16px;border-top:1px solid #f0e3d9;font-size:11px;color:#988d87}
@media(max-width:820px){.grid{grid-template-columns:1fr;padding:18px}.header,.stats{margin:0 18px}.stats{grid-template-columns:repeat(2,1fr)}h1{font-size:26px}.foot{margin:24px 18px 0;flex-direction:column}}
@media print{body{background:#fff}.page{box-shadow:none}.header{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
</style></head><body><main class="page">
<header class="header"><div class="header-top"><span class="mark">${TRIPAL_MARK}</span><span class="doc">ROUTE BOOK / 路书</span></div>
<h1>${escapeHtml(plan.title)}</h1><p>${escapeHtml(plan.requirements?.start_date || "日期待定")} · 由 Tripal AI 生成 · ${days.length} 天 ${stopCount} 站</p></header>
<div class="stats"><div><b>${days.length} 天</b><span>行程天数</span></div><div><b>${stopCount} 站</b><span>地点数量</span></div><div><b>${walkKm} km</b><span>已知路段步行</span></div><div><b>${money(plan.budget?.known_subtotal_cny)}</b><span>已计参考费用</span></div></div>
<div class="grid"><div class="left"><h2>每日行程 / DAY BY DAY</h2>${dayHtml}
<div class="card"><h3>AI 备注</h3><p>${escapeHtml(plan.rationale || "行程由 AI 依据条件生成。")} 营业、预约与最终价格以官方或商家确认为准；尚未查到的项目不计为零。</p></div></div>
<div class="right"><div class="card"><h3>全程路线 / ROUTE MAP</h3><div class="routes">${routeHtml}</div></div>
<div class="card"><h3>费用明细 / BUDGET</h3>${budgetRows || '<p>费用明细暂不可用。</p>'}${ledger?.notice ? `<p>${escapeHtml(ledger.notice)}</p>` : ""}</div>
<div class="card"><h3>打包清单 / PACKING</h3><p>身份证件 · 充电宝 · 舒适步行鞋</p><p>雨具 · 常用药 · 纸巾</p></div>
<div class="card"><h3>关于这份路书</h3><p>天气仅在预报期内展示，未查到即标注待核实。</p><p>花费为已记录的参考价，未查到的项目不计为零。</p></div></div></div>
<footer class="foot"><span>Tripal 旅伴 · 一句话，安排好下一程。</span><span>由 Tripal AI 生成${tripId ? " · " + escapeHtml(tripId.slice(0, 8)) : ""} · 出行前请核实营业、预约与价格</span></footer>
</main></body></html>`;
}
