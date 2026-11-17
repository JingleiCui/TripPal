import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Download,
  Footprints,
  MapPin,
  Printer,
  Sparkles,
  Sun,
  Wallet,
} from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { api, downloadRouteBook } from "./api";
import { TripalMark } from "./components/TripalLogo";
import type { Plan, Stop, Trip } from "./types";

type BudgetDay = {
  day: number;
  priced_subtotal_cny: number | null;
  rows: { label: string; category_name: string; subtotal_cny: number | null }[];
};
type BudgetLedger = { days: BudgetDay[]; notice?: string };

const money = (v: number | null | undefined) =>
  v == null ? "待核实" : "¥" + v.toLocaleString("zh-CN");

/** 从高德 casts 里按日期取当天的真实预报；没有就返回 null，绝不编造天气。 */
function weatherFor(plan: Plan, date?: string) {
  const casts = plan.weather?.forecasts?.flatMap((f) => f.casts ?? []) ?? [];
  if (!date) return null;
  const short = date.slice(5); // MM-DD
  const hit = casts.find((c) => c.date === date || c.date?.endsWith(short));
  if (!hit) return null;
  const temp = hit.daytemp ? `${hit.daytemp}°` : "";
  return `${hit.dayweather || "天气"}${temp ? " " + temp : ""}`;
}

/**
 * 真实路线地图：直接展示后端用高德静态图渲染的 PNG（真实坐标 + polyline）。
 * 不用 SVG 插画示意图冒充地图；服务不可用时如实说明，而不是画一张假图。
 */
function RealRouteMap({ tripId, version, days }: { tripId: string; version: number; days: Plan["days"] }) {
  const [failed, setFailed] = useState(false);
  const src = `/api/v1/trips/${tripId}/route-map.png?v=${version}`;
  const colors = ["#FF8A6B", "#5FC9AC", "#7B8BD8", "#E8A93C", "#B98CD8"];
  return (
    <div className="rb-map-card">
      <h4>全程路线 / REAL ROUTE MAP</h4>
      {failed ? (
        <div className="rb-map-unavailable" role="status">
          <b>地图暂不可用</b>
          <p>真实底图需要高德 Web 服务 Key 与网络；行程中的坐标与路线数据仍完整保留。</p>
        </div>
      ) : (
        <img
          className="rb-map-image"
          src={src}
          alt="高德地图：行程真实地点标记与路线"
          onError={() => setFailed(true)}
        />
      )}
      <div className="rb-map-legend">
        {days.map((d, i) => (
          <span key={d.day}>
            <i style={{ background: colors[i % colors.length] }} />
            DAY {String(d.day).padStart(2, "0")}
          </span>
        ))}
      </div>
      <p className="rb-map-caption">高德地图 · GCJ-02 坐标 · 真实地点与路线</p>
    </div>
  );
}

function stopPrice(stop: Stop) {
  const t = stop.price_text?.trim();
  if (!t) return "待核实";
  return t.length > 14 ? t.slice(0, 14) + "…" : t;
}

export function RouteBook() {
  const { id } = useParams();
  const [downloading, setDownloading] = useState(false);
  const [downloadNote, setDownloadNote] = useState("");
  const trip = useQuery({
    queryKey: ["trip", id],
    queryFn: () => api<Trip>("/trips/" + id),
    enabled: !!id,
  });
  const ledger = useQuery({
    queryKey: ["budget", id, trip.data?.version],
    queryFn: () => api<BudgetLedger>(`/trips/${id}/budget`),
    enabled: !!id && !!trip.data,
    retry: false,
  });
  const plan = trip.data?.plan?.days ? (trip.data.plan as Plan) : null;
  if (trip.isPending) return <div className="rb-page"><div className="rb-card" style={{ margin: 24 }}>正在准备路书…</div></div>;
  if (trip.isError || !plan)
    return (
      <div className="rb-page">
        <div className="rb-card" style={{ margin: 24, color: "#a33b2a" }}>
          路书暂不可用：{trip.error?.message || "该行程尚无完整计划。"}
          <div style={{ marginTop: 12 }}><Link to="/archive">返回我的行程</Link></div>
        </div>
      </div>
    );

  const days = plan.days;
  const knownStops = days.reduce((s, d) => s + d.stops.length, 0);
  const budgetByDay = new Map(ledger.data?.days?.map((d) => [d.day, d]) ?? []);
  const stats = [
    { n: `${days.length} 天`, l: "行程天数", c: "#ea6e4e" },
    { n: `${knownStops} 站`, l: "地点数量", c: "#5fc9ac" },
    {
      n: `${(days.reduce((s, d) => s + d.known_route_walking_meters, 0) / 1000).toFixed(1)} km`,
      l: "已知路段步行",
      c: "#e8a93c",
    },
    { n: money(plan.budget.known_subtotal_cny), l: "已计参考费用", c: "#7b8bd8" },
  ];

  async function handleDownload() {
    if (!id || downloading) return;
    setDownloading(true);
    setDownloadNote("");
    try {
      await downloadRouteBook(`/trips/${id}/export/pdf`);
    } catch (error) {
      setDownloadNote("下载失败：" + (error as Error).message);
    } finally {
      setDownloading(false);
    }
  }

  return (
    <div className="rb-page">
      <header className="rb-header">
        {/* 高密度页眉：Logo 与右侧标题/元信息同一行，不额外占一整行 */}
        <div className="rb-header-top">
          <span className="rb-mark-badge"><TripalMark size={40} title="Tripal 旅伴" /></span>
          <div className="rb-header-copy">
            <h1>{plan.title}</h1>
            <p>
              <span className="rb-header-doc">ROUTE BOOK / 路书</span>
              <span className="rb-header-dot">·</span>
              {plan.requirements.start_date || "日期待定"}
              <span className="rb-header-dot">·</span>
              由 Tripal AI 生成
              <span className="rb-header-dot">·</span>
              {days.length} 天 {knownStops} 站
            </p>
          </div>
          <div className="rb-actions">
            <Link to={"/trips/" + id} className="rb-btn"><ArrowLeft size={14} /> 返回行程</Link>
            <button className="rb-btn" onClick={() => window.print()}><Printer size={14} /> 打印</button>
            <button className="rb-btn" disabled={downloading} onClick={() => void handleDownload()}>
              <Download size={14} /> {downloading ? "正在下载…" : "下载 PDF"}
            </button>
          </div>
        </div>
        {downloadNote && <p className="rb-download-note" role="status">{downloadNote}</p>}
      </header>

      <div className="rb-stats">
        {stats.map((s) => (
          <div className="rb-stat" key={s.l}>
            <b style={{ color: s.c }}>{s.n}</b>
            <span>{s.l}</span>
          </div>
        ))}
      </div>

      <div className="rb-grid">
        <div className="rb-left">
          <h2 className="rb-section-title">每日行程 / DAY BY DAY</h2>
          {days.map((day, i) => {
            const w = weatherFor(plan, day.date);
            const b = budgetByDay.get(day.day);
            const cost = b?.priced_subtotal_cny;
            return (
              <section className={`rb-day d${i % 3}`} key={day.day}>
                <div className="rb-day-head">
                  <b>DAY {String(day.day).padStart(2, "0")}　{day.date?.slice(5) || "日期待定"}　{day.city || ""}</b>
                  <small>{day.stops.length} 站</small>
                </div>
                <div className="rb-day-context">
                  <Sun size={13} />
                  <span>{w || (plan.weather?.note ? "天气待核实" : "出行前请查询预报")}</span>
                  <span className="rb-sep">｜</span>
                  <span className="rb-cost">当日已知花费 {money(cost)}</span>
                </div>
                {day.stops.map((stop) => (
                  <div className={`rb-stop d${i % 3}`} key={stop.id}>
                    <span className="rb-time">{stop.planned_start}</span>
                    <span className="rb-place">
                      <b>{stop.name}</b>
                      <small>{stop.address?.slice(0, 26) || "地点"}</small>
                    </span>
                    <span className="rb-price">{stopPrice(stop)}</span>
                  </div>
                ))}
              </section>
            );
          })}

          <div className="rb-notes">
            <b><Sparkles size={13} /> AI 备注</b>
            <p>
              {plan.rationale || "行程由 AI 依据条件生成。"
              } 营业、预约与最终价格以官方或商家确认为准；尚未查到的项目不计为零。
            </p>
          </div>

          <div className="rb-card rb-info-card">
            <h4>交通提示 / GET AROUND</h4>
            {days.map((d) => (
              <p key={d.day}>DAY {d.day}：{d.walking_note || `已知路段步行 ${(d.known_route_walking_meters / 1000).toFixed(1)} km`}</p>
            ))}
          </div>
          <div className="rb-card rb-info-card">
            <h4>费用明细 / BUDGET</h4>
            {ledger.data?.days?.flatMap((d) => d.rows).slice(0, 12).map((r, i) => (
              <div className="rb-budget-row" key={i}>
                <span className="rb-muted">{r.category_name}</span>
                <span className="rb-bar"><i style={{ width: "60%", background: "#ff8a6b" }} /></span>
                <span>{money(r.subtotal_cny)}</span>
              </div>
            ))}
            {!ledger.data && <p className="rb-muted">费用明细加载中或暂不可用。</p>}
            {ledger.data?.notice && <p className="rb-muted">{ledger.data.notice}</p>}
          </div>
        </div>

        <div className="rb-right">
          <RealRouteMap tripId={id!} version={trip.data?.version ?? 0} days={days} />
          <div className="rb-card rb-info-card">
            <h4>打包清单 / PACKING</h4>
            <p>身份证件 · 充电宝 · 舒适步行鞋</p>
            <p>雨具 · 常用药 · 纸巾</p>
          </div>
          <div className="rb-card rb-info-card">
            <h4><MapPin size={13} /> 关于这份路书</h4>
            <p><Footprints size={12} /> 天气仅在预报期内展示，未查到即标注待核实。</p>
            <p><Wallet size={12} /> 花费为已记录的参考价，未查到的项目不计为零。</p>
          </div>
        </div>
      </div>

      <footer className="rb-footer">
        <span>Tripal 旅伴 · 一句话，安排好下一程。</span>
        <span>由 Tripal AI 生成 · 出行前请核实营业、预约与价格</span>
      </footer>
    </div>
  );
}
