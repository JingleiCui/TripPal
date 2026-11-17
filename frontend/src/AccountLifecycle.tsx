import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Mail, ShieldCheck, Download, Trash2, Check } from "lucide-react";
import { api, post } from "./api";
import { Button } from "./components/ui/button";

export function ForgotPassword({ onBack }: { onBack: () => void }) {
  const [email, setEmail] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
          const r = await post<{ message: string }>("/auth/forgot-password", {
            email,
          });
          setMessage(r.message);
        } catch (e) {
          setMessage((e as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <span className="eyebrow">找回你的账户</span>
      <h2>找回你的旅行档案</h2>
      <p>填写注册邮箱。开发环境的重置邮件会进入本地收件箱。</p>
      <label>
        注册邮箱
        <input
          aria-label="找回密码邮箱"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
      </label>
      <Button disabled={busy}>发送重置链接</Button>
      {message && <p role="status">{message}</p>}
      <button type="button" className="text-button" onClick={onBack}>
        返回登录
      </button>
    </form>
  );
}

export function PublicAccountAction({ kind }: { kind: "verify" | "reset" }) {
  const token =
    new URLSearchParams(location.hash.slice(1)).get("token") ||
    new URLSearchParams(location.search).get("token") ||
    "";
  const [password, setPassword] = useState(""),
    [message, setMessage] = useState(""),
    [busy, setBusy] = useState(false),
    [done, setDone] = useState(false);
  return (
    <div className="account-action-page">
      <section className="card">
        <span className="icon-orbit">
          <Mail size={26} />
        </span>
        <h1>{kind === "verify" ? "确认你的邮箱" : "设置新的密码"}</h1>
        <p>链接仅能使用一次，有效期 30 分钟。</p>
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setBusy(true);
            try {
              const r = await post<{ message: string }>(
                kind === "verify" ? "/auth/verify-email" : "/auth/reset-password",
                { token, ...(kind === "reset" ? { password } : {}) },
              );
              setMessage(r.message);
              setDone(true);
            } catch (e) {
              setMessage((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          {kind === "reset" && !done && (
            <label>
              新密码
              <input
                aria-label="新密码"
                type="password"
                required
                minLength={10}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
          )}
          {!done && (
            <Button disabled={busy || !token}>
              {kind === "verify" ? "验证邮箱" : "更新密码"}
            </Button>
          )}
        </form>
        {message && (
          <div role="status" className="notice">
            {message}
          </div>
        )}
        {!token && (
          <div className="notice error">链接缺少验证凭证，请重新发送邮件。</div>
        )}
        <a className="text-button" href="/">
          返回登录／工作台
        </a>
      </section>
    </div>
  );
}

export function PrivacyPanel({ username }: { username: string }) {
  const client = useQueryClient();
  const account = useQuery({
    queryKey: ["me"],
    queryFn: () =>
      api<{
        email?: string;
        email_verified?: boolean;
        consent?: { analytics?: boolean; decided?: boolean };
      }>("/auth/me"),
  });
  const portrait = useQuery({
    queryKey: ["portrait"],
    queryFn: () =>
      api<{
        portrait: { leanings: Record<string, unknown>; signal_count: number };
        notice: string;
      }>("/preferences/portrait"),
  });
  const [message, setMessage] = useState(""),
    [confirm, setConfirm] = useState(false),
    [name, setName] = useState(""),
    [password, setPassword] = useState("");
  return (
    <>
      <section className="card settings-card">
        <h2>邮箱与账户</h2>
        <p>{account.data?.email || "此本机账户没有邮箱；无法通过邮件找回密码。"}</p>
        {account.data?.email && (
          <>
            <p>{account.data.email_verified ? "邮箱已验证" : "邮箱尚未验证"}</p>
            {!account.data.email_verified && (
              <Button
                variant="secondary"
                size="sm"
                onClick={async () => {
                  try {
                    const r = await post<{ message: string }>(
                      "/auth/resend-verification",
                    );
                    setMessage(r.message);
                  } catch (e) {
                    setMessage((e as Error).message);
                  }
                }}
              >
                重新发送验证邮件
              </Button>
            )}
          </>
        )}
        {["localhost", "127.0.0.1", "::1"].includes(window.location.hostname) && (
          <p>
            <a
              href={`${window.location.protocol}//${window.location.hostname}:18026`}
              target="_blank"
              rel="noopener noreferrer"
            >
              打开本地开发收件箱 ↗
            </a>
          </p>
        )}
        <p className="muted">
          本地收件箱不代表邮件已发到你的真实邮箱；正式部署需配置 SMTP。
        </p>
        {message && <p role="status">{message}</p>}
      </section>
      <section className="card settings-card">
        <h2>偏好画像与统计选择</h2>
        <p>本机行为信号形成启发式建议，不是机器学习模型，也不覆盖你的明确条件。</p>
        <div className="portrait-summary">
          {Object.entries(portrait.data?.portrait?.leanings || {}).map(
            ([key, value]) => (
              <p key={key}>
                {(
                  {
                    interests: "常见兴趣",
                    trip_type: "旅行类型",
                    budget: "费用倾向",
                  } as Record<string, string>
                )[key] || key}
                ：{Array.isArray(value) ? value.join("、") : String(value)}
              </p>
            ),
          )}
          <p>已记录 {portrait.data?.portrait?.signal_count || 0} 条有效信号</p>
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={async () => {
            await api("/preferences/portrait", { method: "DELETE" });
            client.invalidateQueries({ queryKey: ["portrait"] });
          }}
        >
          清除本机行为画像
        </Button>
        <label className="check-label">
          <input
            type="checkbox"
            checked={!!account.data?.consent?.analytics}
            onChange={async (e) => {
              await api("/privacy/consent", {
                method: "PUT",
                body: JSON.stringify({ analytics: e.target.checked }),
              });
              client.invalidateQueries({ queryKey: ["me"] });
            }}
          />
          允许可选匿名产品统计
        </label>
        <p className="muted">
          只有同意且服务配置了 PostHog write key
          才会发送；不上传对话、地点、邮箱或文档。
        </p>
      </section>
      <section className="card settings-card">
        <h2>我的数据</h2>
        <p>下载账户、行程版本、对话、偏好、任务及原始资料的个人数据副本。</p>
        <Button variant="secondary" size="sm" asChild>
          <a href="/api/v1/privacy/export">
            <Download size={15} />
            下载个人数据 ZIP
          </a>
        </Button>
        <div className="danger-zone">
          <h3>注销账户</h3>
          <p>
            删除账户及关联行程、对话、资料、分享、偏好和登录凭证。此操作不可撤销；已有离线备份按独立保留策略处理。
          </p>
          {!confirm ? (
            <Button size="sm" variant="danger" onClick={() => setConfirm(true)}>
              <Trash2 size={14} />
              我要注销账户
            </Button>
          ) : (
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await api("/privacy/account", {
                    method: "DELETE",
                    body: JSON.stringify({ password, confirmation: name }),
                  });
                  window.location.assign("/");
                } catch (e) {
                  setMessage((e as Error).message);
                }
              }}
            >
              <label>
                输入用户名确认：{username}
                <input
                  aria-label="注销确认用户名"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </label>
              <label>
                当前密码
                <input
                  aria-label="注销确认密码"
                  required
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </label>
              <Button variant="danger">确认永久注销</Button>
              <button type="button" onClick={() => setConfirm(false)}>
                取消
              </button>
            </form>
          )}
          {message && <p role="status">{message}</p>}
        </div>
      </section>
    </>
  );
}

export function ConsentBanner() {
  const client = useQueryClient();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: () => api<{ consent?: { decided?: boolean } }>("/auth/me"),
  });
  if (!me.data || me.data.consent?.decided) return null;
  async function choose(analytics: boolean) {
    await api("/privacy/consent", {
      method: "PUT",
      body: JSON.stringify({ analytics }),
    });
    client.invalidateQueries({ queryKey: ["me"] });
  }
  return (
    <aside className="consent-banner" aria-label="可选产品统计">
      <ShieldCheck size={20} />
      <p>
        <b>你的旅行资料由你决定。</b>
        <span>
          可选产品统计默认关闭。只有你同意且配置服务密钥后才发送，不包含对话、地点与资料内容。
        </span>
      </p>
      <Button variant="secondary" size="sm" onClick={() => choose(false)}>
        不参与统计
      </Button>
      <Button size="sm" onClick={() => choose(true)}>
        同意匿名统计
      </Button>
    </aside>
  );
}

export function capture(event: string) {
  return post("/privacy/analytics", { event }).catch(() => undefined);
}
