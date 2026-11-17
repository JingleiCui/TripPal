import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Check,
  Loader2,
  Pencil,
  RefreshCw,
  Wallet,
  X,
} from "lucide-react";
import { api } from "./api";
import { Button } from "./components/ui/button";
import type { Trip, Plan } from "./types";

type Expense = {
  key: string;
  day: number;
  category: string;
  category_name: string;
  label: string;
  unit_price_cny: number | null;
  unit: string;
  quantity: number;
  subtotal_cny: number | null;
  confidence: string;
  fingerprint: string;
  source: string;
  note: string;
};
type Summary = {
  priced_subtotal_cny: number;
  limit_cny: number | null;
  unpriced_count: number;
  is_complete: boolean;
  status: string;
  overrun_cny: number | null;
  remaining_cny: number | null;
  confirmed_subtotal_cny: number;
};
type DayBudget = Summary & {
  day: number;
  date: string | null;
  city: string;
  rows: Expense[];
  limit_basis: string;
};
type Ledger = {
  version: number;
  days: DayBudget[];
  trip: Summary;
  people: number;
  rooms: number;
  rooms_estimated?: boolean;
  notice: string;
  daily_limits: Record<string, string>;
};
const money = (value: number | null | undefined) =>
  value == null
    ? "待核实"
    : "¥" +
      value.toLocaleString("zh-CN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
const units: Record<string, string> = {
  per_person: "每人",
  per_room_night: "每间每晚",
  group: "该项合计",
};
function verdict(summary: Summary, basis = "") {
  return summary.status === "no_budget"
    ? "尚未设置预算"
    : summary.status === "over_budget"
      ? basis.includes("日均")
        ? `高于日均预算参考 ${money(summary.overrun_cny)}，需结合全程核对`
        : `已计参考费用超出 ${money(summary.overrun_cny)}`
      : summary.status === "incomplete"
        ? `还有 ${summary.unpriced_count} 项费用未计，暂不能判断未超预算`
        : summary.status === "within_estimate"
          ? "按当前参考价预计在预算内"
          : "已记录金额在预算内";
}

export function BudgetPanel({ trip, dayNumber }: { trip: Trip; dayNumber: number }) {
  const client = useQueryClient(),
    plan = trip.plan as Plan;
  const ledger = useQuery({
    queryKey: ["budget", trip.id, trip.version],
    queryFn: () => api<Ledger>(`/trips/${trip.id}/budget`),
    retry: false,
  });
  const [total, setTotal] = useState(""),
    [rooms, setRooms] = useState(1),
    [daily, setDaily] = useState(""),
    [editing, setEditing] = useState<Expense | null>(null),
    [price, setPrice] = useState(""),
    [unit, setUnit] = useState("group"),
    [confidence, setConfidence] = useState("estimated"),
    [note, setNote] = useState(""),
    [busy, setBusy] = useState(false),
    [progress, setProgress] = useState(""),
    [error, setError] = useState("");
  const data = ledger.data,
    current = data?.days?.find((d) => d.day === dayNumber);
  useEffect(() => {
    if (data) {
      setTotal(data.trip.limit_cny == null ? "" : String(data.trip.limit_cny));
      setRooms(data.rooms);
      setDaily(data.daily_limits[String(dayNumber)] || "");
    }
  }, [data?.version, dayNumber]);
  const editable = trip.role !== "viewer";
  async function save(extra: Record<string, unknown> = {}) {
    if (!data) return;
    setBusy(true);
    setError("");
    try {
      const dailyLimits = { ...data.daily_limits };
      if (daily.trim()) dailyLimits[String(dayNumber)] = daily;
      else delete dailyLimits[String(dayNumber)];
      await api(`/trips/${trip.id}/budget`, {
        method: "PUT",
        body: JSON.stringify({
          base_version: trip.version,
          total_limit_cny: total.trim() ? Number(total) : null,
          rooms,
          daily_limits: dailyLimits,
          ...extra,
        }),
      });
      setEditing(null);
      await client.invalidateQueries({ queryKey: ["trip", trip.id] });
      await client.invalidateQueries({ queryKey: ["trips"] });
      await client.invalidateQueries({ queryKey: ["budget", trip.id] });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function calculateAll() {
    setBusy(true);
    setError("");
    try {
      for (const day of plan.days) {
        setProgress(`正在核算第 ${day.day} 天的餐厅、住宿与接驳…`);
        await api(`/trips/${trip.id}/daily-details?day=${day.day}`);
      }
      await ledger.refetch();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setProgress("");
    }
  }
  function edit(row: Expense) {
    setEditing(row);
    setPrice(row.unit_price_cny == null ? "" : String(row.unit_price_cny));
    setUnit(row.unit);
    setConfidence(row.confidence === "confirmed" ? "confirmed" : "estimated");
    setNote(row.note || "");
    setError("");
  }
  if (ledger.isPending)
    return (
      <div className="service-loading">
        <Loader2 className="spin" size={20} />
        正在核对费用明细…
      </div>
    );
  if (!data || !current)
    return (
      <div className="notice error" role="alert">
        {ledger.error?.message || "费用明细暂不可用"}
      </div>
    );
  return (
    <div className="budget-panel">
      <div className="service-section-title">
        <h2>今天的花费，逐项算清。</h2>
        <p>
          按 {data.people} 人、{data.rooms}{" "}
          间房核算。房费只计实际过夜的日期，不在退房日重复收一晚。
        </p>
      </div>
      <div className={"budget-verdict " + current.status}>
        <div>
          <small>第 {dayNumber} 天 · 已计参考小计</small>
          <b>{money(current.priced_subtotal_cny)}</b>
          <span>
            {current.limit_cny == null
              ? "请先填写预算"
              : `对照预算 ${money(current.limit_cny)}`}
          </span>
        </div>
        <p>
          <AlertCircle size={15} />
          {verdict(current, current.limit_basis)}
        </p>
        {current.unpriced_count > 0 && (
          <small>
            未定价项目没有按 0 元处理。下方“待核实”的金额补齐后，才能完成核算。
          </small>
        )}
        <div className="budget-meter">
          <i
            style={{
              width: current.limit_cny
                ? Math.min(
                    100,
                    (current.priced_subtotal_cny / current.limit_cny) * 100,
                  ) + "%"
                : "0%",
            }}
          />
        </div>
        <small>{current.limit_basis}</small>
      </div>
      {data.rooms_estimated && (
        <p className="service-source-note">
          房间数暂按每间 2
          人估算，请按实际房型容量和预订间数调整；这不代表已确认入住容量。
        </p>
      )}
      <form
        className="budget-settings"
        onSubmit={(e) => {
          e.preventDefault();
          save();
        }}
      >
        <label>
          全程总预算（元）
          <input
            aria-label="全程总预算"
            type="number"
            min={1}
            max={1000000}
            step={1}
            value={total}
            onChange={(e) => setTotal(e.target.value)}
            disabled={!editable || busy}
            placeholder="未设置"
          />
        </label>
        <div className="form-row">
          <label>
            当天单独预算（元）
            <input
              aria-label="当天单独预算"
              type="number"
              min={0}
              max={1000000}
              step="0.01"
              value={daily}
              onChange={(e) => setDaily(e.target.value)}
              disabled={!editable || busy}
              placeholder="留空按总预算日均参考"
            />
          </label>
          <label>
            房间数
            <input
              aria-label="预算房间数"
              type="number"
              min={1}
              max={12}
              value={rooms}
              onChange={(e) => setRooms(Number(e.target.value))}
              disabled={!editable || busy}
            />
          </label>
        </div>
        <Button size="sm" variant="secondary" disabled={!editable || busy}>
          <Check size={13} />
          保存预算设置
        </Button>
      </form>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <div className="expense-list">
        {current.rows.map((row) => (
          <article
            className={"expense-row " + (row.subtotal_cny == null ? "unpriced" : "")}
            key={row.key}
          >
            <div>
              <span>{row.category_name}</span>
              <h3>{row.label}</h3>
              <p>
                {row.unit_price_cny == null
                  ? "未查到可靠金额"
                  : `${money(row.unit_price_cny)} / ${units[row.unit]} × ${row.quantity}${row.unit === "per_person" ? " 人" : row.unit === "per_room_night" ? " 间" : " 项"}`}{" "}
                ·{" "}
                {row.confidence === "confirmed"
                  ? "已确认金额"
                  : row.confidence === "unknown"
                    ? "待核实"
                    : "参考 / 预估"}
              </p>
              {row.note && <small>{row.note}</small>}
            </div>
            <div>
              <b>{money(row.subtotal_cny)}</b>
              <button
                aria-label={"核对费用" + row.label}
                disabled={!editable || busy}
                onClick={() => edit(row)}
              >
                <Pencil size={13} />
                {row.subtotal_cny == null ? "填写" : "核对"}
              </button>
            </div>
          </article>
        ))}
      </div>
      <div className="trip-budget-summary">
        <h3>全程一起看</h3>
        <p>
          已计 {money(data.trip.priced_subtotal_cny)}
          {data.trip.limit_cny != null
            ? ` / 总预算 ${money(data.trip.limit_cny)}`
            : " · 未设置总预算"}
        </p>
        <b>{verdict(data.trip)}</b>
        <p>
          缺少 {data.trip.unpriced_count} 项金额；已确认金额{" "}
          {money(data.trip.confirmed_subtotal_cny)}。
        </p>
        <Button size="sm" variant="secondary" disabled={busy} onClick={calculateAll}>
          {busy && progress ? (
            <Loader2 size={14} className="spin" />
          ) : (
            <RefreshCw size={14} />
          )}
          查询并核算全程
        </Button>
        {progress && <p role="status">{progress}</p>}
      </div>
      <p className="service-source-note">{data.notice}</p>
      {editing && (
        <div className="service-drawer-scrim" onClick={() => !busy && setEditing(null)}>
          <form
            className="service-drawer expense-editor"
            role="dialog"
            aria-modal="true"
            aria-label="核对单项费用"
            onClick={(e) => e.stopPropagation()}
            onSubmit={(e) => {
              e.preventDefault();
              save({
                expense: {
                  key: editing.key,
                  unit_price_cny: price,
                  unit,
                  confidence,
                  note,
                  fingerprint: editing.fingerprint,
                },
              });
            }}
          >
            <button
              type="button"
              className="drawer-close"
              aria-label="关闭费用编辑"
              onClick={() => setEditing(null)}
            >
              <X size={20} />
            </button>
            <span className="eyebrow">金额与人数，分开核对</span>
            <h2>{editing.label}</h2>
            <label>
              单价或该项合计（元）
              <input
                aria-label="费用单价"
                type="number"
                min={0}
                max={1000000}
                step="0.01"
                required
                value={price}
                onChange={(e) => setPrice(e.target.value)}
              />
            </label>
            <label>
              计价方式
              <select
                aria-label="费用计价方式"
                value={unit}
                onChange={(e) => setUnit(e.target.value)}
              >
                {Object.entries(units)
                  .filter(
                    ([key]) => editing.category === "hotel" || key !== "per_room_night",
                  )
                  .map(([key, label]) => (
                    <option value={key} key={key}>
                      {label}
                    </option>
                  ))}
              </select>
            </label>
            <p className="expense-preview">
              本项合计：
              {price
                ? money(
                    Number(price) *
                      (unit === "per_person"
                        ? data.people
                        : unit === "per_room_night"
                          ? rooms
                          : 1),
                  )
                : "待填写"}
            </p>
            <label>
              金额状态
              <select
                aria-label="费用金额状态"
                value={confidence}
                onChange={(e) => setConfidence(e.target.value)}
              >
                <option value="estimated">预估金额</option>
                <option value="confirmed">已确认金额</option>
              </select>
            </label>
            <label>
              依据或备注
              <textarea
                aria-label="费用依据或备注"
                maxLength={500}
                rows={3}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="例如：官网票价、已拿到的酒店报价，或不需要此项的原因"
              />
            </label>
            {error && (
              <p className="notice error" role="alert">
                {error}
              </p>
            )}
            <div className="expense-editor-actions">
              <Button disabled={busy}>
                <Check size={15} />
                保存这项费用
              </Button>
              <Button
                type="button"
                variant="secondary"
                disabled={busy}
                onClick={() => save({ clear_expense: editing.key })}
              >
                恢复平台参考
              </Button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}

export function BudgetNotice({
  trip,
  dayNumber,
  onOpen,
}: {
  trip: Trip;
  dayNumber: number;
  onOpen: () => void;
}) {
  const ledger = useQuery({
    queryKey: ["budget", trip.id, trip.version],
    queryFn: () => api<Ledger>(`/trips/${trip.id}/budget`),
    retry: false,
  });
  const day = ledger.data?.days?.find((d) => d.day === dayNumber);
  if (!day) return null;
  return (
    <button
      className={"budget-inline " + (day.status === "over_budget" ? "over-budget" : "")}
      onClick={onOpen}
    >
      <Wallet size={15} />
      <span>
        当天已计 {money(day.priced_subtotal_cny)}
        <small>
          {day.status === "no_budget"
            ? "尚未设置预算"
            : day.status === "over_budget"
              ? verdict(day, day.limit_basis)
              : day.unpriced_count
                ? `${day.unpriced_count} 项待计价，暂不能判断未超预算`
                : "按当前参考价核算"}
        </small>
      </span>
      <b>核对花费</b>
    </button>
  );
}
