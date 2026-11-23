import { BRAND } from "../brand";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";
import {
  ChevronDown,
  ChevronRight,
  Clock3,
  Compass,
  FolderOpen,
  Heart,
  History,
  LogOut,
  Map,
  Menu,
  MessageSquare,
  Plus,
  Search,
  Settings,
  SlidersHorizontal,
  X,
  type LucideIcon,
} from "lucide-react";
import type { Account, Health, Trip } from "../types";
import { TripalMark } from "./TripalLogo";

type RecentConversation = { id: string; slots: { destination?: string } };

type NavItem = {
  to: string;
  label: string;
  icon: LucideIcon;
  hint: string;
  secondary?: boolean;
  end?: boolean;
};

/** 单一数据源：桌面导航、更多菜单、移动抽屉与面包屑共用。 */
const NAV: NavItem[] = [
  {
    to: "/chat",
    label: "继续规划",
    secondary: true,
    icon: MessageSquare,
    hint: "用对话调整条件，候选方案确认后才会写入行程版本",
  },
  {
    to: "/",
    label: "开始规划",
    icon: Compass,
    hint: "填写出游条件，生成可修改、可追溯的行程版本",
    end: true,
  },
  {
    to: "/explore",
    label: "探索发现",
    icon: Search,
    hint: "查找有来源的地点与吃住行信息",
  },
  {
    to: "/saved",
    label: "旅行收藏",
    icon: Heart,
    hint: "把想去的地方收进清单，随时用于新行程",
  },
  {
    to: "/archive",
    label: "我的行程",
    icon: Map,
    hint: "查看全部行程、版本与导出记录",
  },
  {
    to: "/documents",
    label: "旅行资料",
    icon: FolderOpen,
    hint: "导入私人攻略，按来源检索原文依据",
    secondary: true,
  },
  {
    to: "/runs",
    label: "执行记录",
    icon: History,
    hint: "查看模型、工具与任务状态的真实调用记录",
    secondary: true,
  },
  {
    to: "/assistant",
    label: "旅行偏好",
    icon: SlidersHorizontal,
    hint: "设置默认目的地、天数与出行风格",
    secondary: true,
  },
  {
    to: "/settings",
    label: "平台与设置",
    icon: Settings,
    hint: "检查服务连通性、平台凭证与账号隐私",
    secondary: true,
  },
];

type Props = {
  account: Account;
  health?: Health;
  trips: Trip[];
  conversations: RecentConversation[];
  pathname: string;
  onLogout: () => Promise<void>;
};

function Dropdown({
  label,
  trigger,
  children,
  className = "",
}: {
  label: string;
  trigger: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!anchor.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div className={"app-popover-anchor " + className} ref={anchor}>
      <button
        type="button"
        className="app-dropdown-trigger"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        {trigger}
      </button>
      {open && (
        <div className="app-popover" role="menu" onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  );
}

function currentSection(pathname: string): NavItem | undefined {
  if (pathname.startsWith("/trips/")) return NAV.find((item) => item.to === "/archive");
  return (
    NAV.find((item) => item.to !== "/" && pathname.startsWith(item.to)) ??
    (pathname === "/" ? NAV.find((item) => item.to === "/") : undefined)
  );
}

export function AppHeader({
  account,
  health,
  trips,
  conversations,
  pathname,
  onLogout,
}: Props) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);

  useEffect(() => setMobileOpen(false), [pathname]);
  useEffect(() => {
    if (!mobileOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [mobileOpen]);

  const section = currentSection(pathname);
  const isManagePath = ["/documents", "/runs", "/assistant", "/settings"].some((p) =>
    pathname.startsWith(p),
  );
  const showPlanningSteps =
    pathname === "/" || pathname.startsWith("/chat") || pathname.startsWith("/trips/");
  // 用「我在第几步」替代并列入口，减少首次使用的选择成本。
  const stepIndex =
    pathname.startsWith("/trips/") || pathname === "/archive"
      ? 2
      : /^\/chat\/.+/.test(pathname)
        ? 1
        : 0;
  const services = Object.values(health?.services ?? {});
  const unavailable = services.filter((value) => value !== "ready").length;
  const healthLabel = !health
    ? "正在检查服务"
    : unavailable
      ? `${unavailable} 项服务异常`
      : "服务正常";
  const healthTone = !health ? "pending" : unavailable ? "warning" : "ready";

  // /chat 由右上方唯一的主 CTA 承担，不再与「开始规划」并列造成选择困难。
  const primary = NAV.filter((item) => !item.secondary && item.to !== "/chat");
  const secondary = NAV.filter((item) => item.secondary);

  async function logout() {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await onLogout();
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <header className="app-header">
      <div className="app-header-inner">
        <Link
          to="/"
          className="app-brand"
          aria-label={`${BRAND.fullName} · 返回工作台`}
        >
          <span className="app-brand-mark" aria-hidden="true">
            <TripalMark size={34} />
          </span>
          <b>
            {BRAND.name}
            <span className="app-brand-cn">{BRAND.nameCn}</span>
            <small className="app-brand-role">AI 旅行规划</small>
          </b>
        </Link>

        <nav className="app-header-nav" aria-label="主导航">
          {primary.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              title={item.hint}
              className={({ isActive }) => "app-nav-link" + (isActive ? " active" : "")}
            >
              <item.icon size={16} />
              {item.label}
            </NavLink>
          ))}
          <Dropdown
            label="更多页面"
            className="app-nav-more"
            trigger={
              <>
                更多 <ChevronDown size={14} />
              </>
            }
          >
            {primary.slice(3).map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className="app-popover-item app-nav-collapsible"
              >
                <item.icon size={16} />
                {item.label}
              </NavLink>
            ))}
            <p className="app-popover-title app-nav-collapsible-divider">更多功能</p>
            {secondary.map((item) => (
              <NavLink key={item.to} to={item.to} className="app-popover-item">
                <item.icon size={16} />
                {item.label}
              </NavLink>
            ))}
          </Dropdown>
        </nav>

        <div className="app-header-actions">
          <Link
            to="/settings"
            className={"app-service app-service-" + healthTone}
            title="查看服务状态与平台配置"
          >
            <span className="app-service-dot" aria-hidden="true" />
            <span className="app-desktop-only">{healthLabel}</span>
          </Link>

          <Dropdown
            label="最近访问"
            className="app-desktop-only"
            trigger={
              <>
                <Clock3 size={15} /> 最近 <ChevronDown size={14} />
              </>
            }
          >
            <p className="app-popover-title">已保存行程</p>
            {trips.length ? (
              trips.slice(0, 4).map((trip) => (
                <Link
                  key={trip.id}
                  to={"/trips/" + trip.id}
                  className="app-popover-item"
                >
                  <Map size={15} />
                  <span className="app-popover-ellipsis">{trip.title}</span>
                </Link>
              ))
            ) : (
              <p className="app-popover-empty">还没有保存的行程</p>
            )}
            <p className="app-popover-title">最近对话</p>
            {conversations.length ? (
              conversations.slice(0, 3).map((item) => (
                <Link
                  key={item.id}
                  to={"/chat/" + item.id}
                  className="app-popover-item"
                >
                  <MessageSquare size={15} />
                  <span className="app-popover-ellipsis">
                    {item.slots.destination || "尚未确定目的地"}
                  </span>
                </Link>
              ))
            ) : (
              <p className="app-popover-empty">还没有对话记录</p>
            )}
          </Dropdown>

          <Link
            to="/?new=1"
            className="app-cta"
            title="用对话说清期待，确认候选方案后才会写入行程版本"
          >
            <Plus size={16} /> <span className="app-cta-label">新建旅行</span>
          </Link>

          <Dropdown
            label="账户菜单"
            className="app-desktop-only"
            trigger={
              <span className="app-avatar">{account.name.charAt(0).toUpperCase()}</span>
            }
          >
            <div className="app-account-card">
              <b>{account.name}</b>
              <small>本机旅行档案</small>
            </div>
            <NavLink to="/assistant" className="app-popover-item">
              <SlidersHorizontal size={16} /> 旅行偏好
            </NavLink>
            <NavLink to="/settings" className="app-popover-item">
              <Settings size={16} /> 平台与设置
            </NavLink>
            <button type="button" className="app-popover-item" onClick={logout}>
              <LogOut size={16} /> {loggingOut ? "正在退出…" : "退出登录"}
            </button>
          </Dropdown>

          <button
            type="button"
            className="app-mobile-toggle"
            aria-label={mobileOpen ? "关闭导航" : "打开导航"}
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen((value) => !value)}
          >
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      <div className="app-context">
        <div className="app-context-inner">
          <div className="app-breadcrumb" aria-label="当前位置">
            <Link to="/">工作空间</Link>
            <ChevronRight size={13} aria-hidden="true" />
            <span aria-current="page">{section?.label ?? "我的旅行"}</span>
          </div>
          {section?.hint && <span className="app-context-hint">{section.hint}</span>}
          {!isManagePath && showPlanningSteps && (
            <div
              className="mf-steps"
              aria-label="当前规划阶段"
              title="规划分三步：说清期待 → 确认方案 → 写入行程版本"
            >
              {["说清期待", "确认方案", "定行程"].map((label, index) => (
                <span
                  key={label}
                  className={
                    "mf-step " +
                    (index < stepIndex ? "done" : index === stepIndex ? "active" : "")
                  }
                >
                  <b className="mf-num">{String(index + 1).padStart(2, "0")}</b>
                  {label}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {mobileOpen && (
        <>
          <button
            type="button"
            className="app-mobile-scrim"
            aria-label="关闭导航"
            onClick={() => setMobileOpen(false)}
          />
          <div className="app-mobile-panel" role="dialog" aria-label="导航菜单">
            <p className="app-popover-title">页面导航</p>
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  "app-popover-item" + (isActive ? " active" : "")
                }
              >
                <item.icon size={17} /> {item.label}
              </NavLink>
            ))}
            {(trips.length > 0 || conversations.length > 0) && (
              <>
                <p className="app-popover-title">最近访问</p>
                {trips.slice(0, 3).map((trip) => (
                  <Link
                    key={trip.id}
                    to={"/trips/" + trip.id}
                    className="app-popover-item"
                  >
                    <Map size={16} />
                    <span className="app-popover-ellipsis">{trip.title}</span>
                  </Link>
                ))}
                {conversations.slice(0, 2).map((item) => (
                  <Link
                    key={item.id}
                    to={"/chat/" + item.id}
                    className="app-popover-item"
                  >
                    <MessageSquare size={16} />
                    <span className="app-popover-ellipsis">
                      {item.slots.destination || "尚未确定目的地"}
                    </span>
                  </Link>
                ))}
              </>
            )}
            <div className="app-mobile-account">
              <span className="app-avatar">{account.name.charAt(0).toUpperCase()}</span>
              <div>
                <b>{account.name}</b>
                <small>本机旅行档案</small>
              </div>
              <button type="button" onClick={logout}>
                <LogOut size={15} /> {loggingOut ? "退出中" : "退出"}
              </button>
            </div>
          </div>
        </>
      )}
    </header>
  );
}
