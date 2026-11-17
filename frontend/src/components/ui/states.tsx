import type { ReactNode } from "react";
import { AlertCircle, Inbox, Loader2, RotateCcw } from "lucide-react";
import { Button } from "./button";

/** 骨架屏：用于首屏与列表加载，避免页面跳动或一片空白。 */
export function Skeleton({
  lines = 3,
  compact = false,
}: {
  lines?: number;
  compact?: boolean;
}) {
  return (
    <div
      className={"ui-skeleton" + (compact ? " ui-skeleton-compact" : "")}
      role="status"
      aria-label="内容加载中"
      aria-busy="true"
    >
      {Array.from({ length: lines }, (_, i) => (
        <span
          className="ui-skeleton-line"
          key={i}
          style={{ width: i === 0 ? "58%" : i === lines - 1 ? "76%" : "100%" }}
        />
      ))}
    </div>
  );
}

/** 页面级骨架：标题 + 内容卡片，和真实页面布局接近。 */
export function PageSkeleton() {
  return (
    <div className="page ui-page-skeleton" role="status" aria-label="页面加载中">
      <div className="ui-skeleton-line ui-skeleton-eyebrow" />
      <div className="ui-skeleton-line ui-skeleton-title" />
      <div className="ui-skeleton-line ui-skeleton-subtitle" />
      <div className="ui-skeleton-grid">
        <div className="card">
          <Skeleton lines={5} />
        </div>
        <div className="card">
          <Skeleton lines={5} />
        </div>
      </div>
    </div>
  );
}

/** 空态：说明「为什么空」以及「下一步能做什么」。 */
export function EmptyState({
  title,
  description,
  icon,
  action,
}: {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="ui-state ui-state-empty">
      <span className="ui-state-icon" aria-hidden="true">
        {icon ?? <Inbox size={22} />}
      </span>
      <b>{title}</b>
      {description && <p>{description}</p>}
      {action && <div className="ui-state-action">{action}</div>}
    </div>
  );
}

/** 错误态：给出可操作的原因、request-id 与重试入口。 */
export function ErrorState({
  title = "暂时无法加载",
  message,
  requestId,
  onRetry,
}: {
  title?: string;
  message?: string;
  requestId?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="ui-state ui-state-error" role="alert">
      <span className="ui-state-icon" aria-hidden="true">
        <AlertCircle size={22} />
      </span>
      <b>{title}</b>
      <p>
        {message ||
          "请检查网络连接后重试。如果持续出现，请到「平台与设置」查看服务状态。"}
      </p>
      {requestId && <small className="ui-request-id">请求编号 {requestId}</small>}
      {onRetry && (
        <div className="ui-state-action">
          <Button variant="secondary" size="sm" onClick={onRetry}>
            <RotateCcw size={14} /> 重新加载
          </Button>
        </div>
      )}
    </div>
  );
}

/** 轻量行内加载提示，用于按钮旁或局部区域。 */
export function InlineLoading({ label = "处理中" }: { label?: string }) {
  return (
    <span className="ui-inline-loading" role="status">
      <Loader2 size={14} className="spin" /> {label}
    </span>
  );
}
