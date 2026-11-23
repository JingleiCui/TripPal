import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/workspace.json", import.meta.url), "utf8"),
);

// Controlled provider responses exercise the browser flow without spending model calls.
async function workspace(
  page: Page,
  opts: {
    single?: boolean;
    failDetails?: boolean;
    generating?: boolean;
    account?: string;
  } = {},
) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  let generating = !!opts.generating;
  let loggedOut = false;
  let sent = false;
  let confirmed = false;
  let modified = false;
  const content: string[] = [];
  const variants = opts.single ? { A: fixture.A } : { A: fixture.A, B: fixture.B };
  const conversation = () => ({
    id: "conversation-one",
    version: content.length,
    trip_id: "trip-one",
    slots: { destination: "北京", duration: "3 days" },
    state: { fixture: true, task_id: "task-one" },
    messages: [
      { id: 1, role: "assistant", content: "想去哪里、玩几天？", meta: {} },
      ...content.map((text, i) => ({
        id: i + 2,
        role: "user",
        content: text,
        meta: {},
      })),
    ],
    task: sent
      ? {
          id: "task-one",
          status: confirmed ? "completed" : generating ? "running" : "waiting_choice",
          result: {
            variants: generating ? undefined : variants,
            base_version: 0,
            draft_revision: 1,
            requested_count: 2,
            missing_variant_reason: opts.single
              ? "候选地点不足，方案 B 暂未生成，方案 A 已保留。"
              : undefined,
          },
        }
      : null,
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const method = route.request().method();
    let json: unknown = {};
    if (path === "/auth/me" && loggedOut)
      return route.fulfill({ status: 401, json: { detail: "请登录" } });
    if (path === "/auth/logout") {
      loggedOut = true;
      json = {};
    } else if (path === "/auth/me")
      json = {
        name: opts.account || "workspace-user",
        csrf: "test",
        preferences: {},
        consent: { decided: true },
      };
    else if (path === "/health") json = { vision_status: "synthetic_fixture" };
    else if (path === "/trips") json = [];
    else if (path === "/saved-places") json = [];
    else if (path === "/explore")
      json = {
        items: fixture.A.days[0].stops,
        notice: "合成测试资料",
        fixture: true,
        next_page: null,
        has_more: false,
        end_reason: "exhausted",
      };
    else if (path === "/conversations" && method === "GET")
      json = sent
        ? [
            {
              id: "conversation-one",
              slots: { destination: "北京" },
              status: confirmed ? "completed" : "waiting_choice",
            },
          ]
        : [];
    else if (path === "/conversations" && method === "POST") json = conversation();
    else if (path.endsWith("/events"))
      return route.fulfill({
        contentType: "text/event-stream",
        body: ": controlled fixture\n\n",
      });
    else if (path.endsWith("/turns")) {
      const body = route.request().postDataJSON();
      if (sent) expect(body.draft_task_id).toBe("task-one");
      content.push(body.content);
      sent = true;
      json = conversation();
    } else if (path === "/conversations/conversation-one") json = conversation();
    else if (path === "/trips/trip-one")
      json = {
        id: "trip-one",
        title: "北京旅行",
        version: confirmed ? 1 : 0,
        plan: confirmed ? fixture.A : {},
        role: "owner",
      };
    else if (path.endsWith("/daily-details")) {
      if (opts.failDetails && !modified) {
        modified = true;
        return route.fulfill({
          status: 503,
          json: { detail: "餐饮资料暂不可用，请重试" },
        });
      }
      json = fixture.details;
    } else if (path.endsWith("/budget")) json = fixture.budget;
    else if (/\/tasks\/task-one\/variants\/[AB]$/.test(path) && method === "POST") {
      confirmed = true;
      json = { trip_id: "trip-one", version: 1 };
    } else if (path.endsWith("/members")) json = { members: [] };
    else if (path.endsWith("/pending-changes")) json = [];
    return route.fulfill({ json });
  });
  await page.addInitScript(() => {
    localStorage.setItem("tripal-analytics-consent", "denied");
  });
  return {
    content,
    complete: () => {
      generating = false;
    },
  };
}

async function generate(page: Page) {
  await page.goto("/");
  await page.getByLabel(/使用合成资料体验/).check();
  await page
    .getByLabel("旅行对话输入")
    .fill("2027-05-01，北京三天，需要酒店，给我两个方案，直接规划");
  await page.getByLabel("给我两个不同方案供选择").check();
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  await expect(
    page.getByText("草稿已自动保存 · 待确认", { exact: true }),
  ).toBeVisible();
}

test("explore drawer: place context, draft tabs, navigation recovery, editing and confirmation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const server = await workspace(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await generate(page);
  await expect(page.getByRole("button", { name: /方案 B/ }).first()).toBeVisible();
  await page.getByRole("tab", { name: "吃什么", exact: true }).click();
  await expect(page.locator(".meal-detail-card")).toHaveCount(3);
  await page.getByRole("tab", { name: "住哪里", exact: true }).click();
  await expect(page.locator(".stay-detail-card")).toBeVisible();
  await page.getByRole("tab", { name: "怎么走", exact: true }).click();
  await expect(page.locator(".transport-leg").first()).toBeVisible();
  await page.getByRole("tab", { name: "花费", exact: true }).click();
  await expect(page.locator(".budget-verdict")).toBeVisible();
  await page.getByRole("tab", { name: "吃什么", exact: true }).click();
  await page.getByLabel("旅行对话输入").fill("还没发送的调整要求");
  await page.getByRole("link", { name: "旅行收藏", exact: true }).click();
  await page.getByRole("link", { name: "探索发现", exact: true }).click();
  await expect(page.getByLabel("旅行对话输入")).toHaveValue("还没发送的调整要求");
  await expect(page.getByRole("tab", { name: "吃什么", exact: true })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await page.reload();
  await expect(page.locator(".meal-detail-card")).toHaveCount(3);
  await expect(page.getByLabel("旅行对话输入")).toHaveValue("还没发送的调整要求");
  await page.screenshot({ path: "../reports/workspace-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "返回探索", exact: true }).click();
  await page
    .getByRole("button", { name: /和 AI 聊这个地点：/ })
    .first()
    .click();
  await expect(page.locator(".assistant-place-context")).toBeVisible();
  await page.getByLabel("旅行对话输入").fill("想把这个地方安排进去，轻松一点");
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  await expect.poll(() => server.content.length).toBe(2);
  expect(server.content[1]).toContain("参考地点：");
  await page.getByRole("button", { name: "查看方案", exact: true }).click();
  await page.getByRole("button", { name: "确认并保存方案 A", exact: true }).click();
  await expect(page.getByText(/正式行程已保存/)).toBeVisible();
  expect(errors).toEqual([]);
});

test("mobile: full screen drawer, single actual variant, retry and return to discovery", async ({
  page,
}) => {
  await workspace(page, { single: true, failDetails: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await generate(page);
  await expect(
    page.getByText("候选地点不足，方案 B 暂未生成，方案 A 已保留。").last(),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: /^方案 B/ })).toHaveCount(0);
  await expect(page.getByText("当天详情暂时没有查到")).toBeVisible();
  await page.getByRole("button", { name: "重新查询", exact: true }).click();
  await page.getByRole("tab", { name: "吃什么", exact: true }).click();
  await expect(page.locator(".meal-detail-card")).toHaveCount(3);
  await page.screenshot({ path: "../reports/workspace-mobile.png", fullPage: true });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBe(true);
  await page.getByRole("button", { name: "关闭 AI 助手", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "把好奇，变成下一站。" }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /草稿待确认 · 继续规划/ }),
  ).toBeFocused();
});

test("generating tasks survive navigation without starting a new conversation", async ({
  page,
}) => {
  const server = await workspace(page, { generating: true });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/explore?new=1&assistant=open");
  await page.getByLabel("旅行对话输入").fill("2027-05-01，北京三天，直接规划");
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  await expect(page.getByText("正在生成 · 可继续浏览", { exact: true })).toBeVisible();
  await page.getByLabel("旅行对话输入").fill("完成后再调整的文字");
  await page.getByRole("link", { name: "旅行收藏", exact: true }).click();
  await page.getByRole("link", { name: "探索发现", exact: true }).click();
  await expect(page.getByText("正在生成 · 可继续浏览", { exact: true })).toBeVisible();
  await expect(page.getByLabel("旅行对话输入")).toHaveValue("完成后再调整的文字");
  server.complete();
  await page.reload();
  await expect(
    page.getByText("草稿已自动保存 · 待确认", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "确认并保存方案 A", exact: true }),
  ).toBeEnabled();
  expect(server.content).toEqual(["2027-05-01，北京三天，直接规划"]);
});

test("new conversations and another account have independent composers", async ({
  page,
}) => {
  await workspace(page);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await generate(page);
  await page.getByLabel("旅行对话输入").fill("属于第一段旅行的未发送文字");
  await page.getByRole("button", { name: "新对话", exact: true }).click();
  await expect(page.getByLabel("旅行对话输入")).toHaveValue("");
  await page.getByLabel("切换旅行对话").selectOption("conversation-one");
  await expect(page.getByLabel("旅行对话输入")).toHaveValue(
    "属于第一段旅行的未发送文字",
  );
  await page.unrouteAll({ behavior: "wait" });
  await workspace(page, { account: "another-user" });
  await page.goto("/explore");
  await page.getByRole("button", { name: "和 AI 一起规划", exact: true }).click();
  await expect(page.getByLabel("旅行对话输入")).toHaveValue("");
  await expect(page.locator(".chat-history")).not.toContainText("北京三天，需要酒店");
  await page.getByRole("button", { name: "关闭 AI 助手", exact: true }).click();
  await page.getByRole("button", { name: "账户菜单", exact: true }).click();
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(() =>
        Object.keys(localStorage).filter((key) =>
          key.startsWith("tripal-workspace:another-user:"),
        ),
      ),
    )
    .toEqual([]);
});
