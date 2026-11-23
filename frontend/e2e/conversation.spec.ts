import { test, expect } from "@playwright/test";

test("conversation: gate, live candidates, choice, hotel, portrait and recovery", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("conv-" + Date.now());
  await page.getByLabel("密码", { exact: true }).fill("conv-browser-1234");
  await page.getByRole("button", { name: "创建账户", exact: true }).click();
  await page.getByRole("button", { name: "不参与统计", exact: true }).click();
  await page.getByRole("link", { name: "新建旅行", exact: true }).click();
  await page.getByLabel(/使用合成资料体验/).check();
  await page.getByLabel("给我两个不同方案供选择").check();
  await page.getByLabel("旅行对话输入").fill("去北京");
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  await expect(page.getByText("这次打算玩几天？", { exact: true })).toBeVisible();
  await page.getByLabel("旅行对话输入").fill("三天，直接规划");
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  await expect(page.getByText(/准备哪天出发/)).toBeVisible();
  await page.getByLabel("旅行对话输入").fill("2027-05-01，直接规划");
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  await expect(page.getByRole("button", { name: "确认并保存方案 A" })).toBeEnabled({
    timeout: 45000,
  });
  await page.screenshot({
    path: "../reports/candidates-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: /^方案 B/ }).click();
  await page.getByRole("button", { name: "确认并保存方案 B" }).click();
  // 桌面端聊天抽屉和方案预览同时可见。
  await expect(page.getByText(/方案 B 已保存为行程版本/)).toBeVisible();
  await page.reload();
  await expect(page.getByText(/方案 B 已保存为行程版本/)).toBeVisible();
  // 住宿选择器位于「行程画布」视图，切回后再操作。

  await page.getByRole("button", { name: "住宿地点", exact: true }).click();
  await page.getByLabel("酒店查询").fill("北京站");
  await page.getByRole("button", { name: "查询地点", exact: true }).click();
  await expect(page.getByText("演示·北京旅居酒店 1", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "选择", exact: true }).first().click();
  await expect(
    page.getByRole("heading", { name: "把住宿地点放到地图上" }),
  ).not.toBeVisible();
  await page.getByRole("button", { name: "评分 4 星" }).click();
  await page.screenshot({
    path: "../reports/canvas-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  // 当前工作区是文档流双栏：移动端不再有旧的「方案 / 对话」切换按钮。
  await expect(page.locator(".app-mobile-panel")).toHaveCount(0);
  await expect(page.locator(".assistant-drawer")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../reports/canvas-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});

test("multi-city chat preserves per-city plan and privacy export", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("cities-" + Date.now());
  await page.getByLabel("密码", { exact: true }).fill("cities-browser-123");
  await page.getByRole("button", { name: "创建账户", exact: true }).click();
  await page.getByRole("button", { name: "不参与统计", exact: true }).click();
  await page.getByRole("link", { name: "新建旅行", exact: true }).click();
  await page.getByLabel(/使用合成资料体验/).check();
  await page.getByLabel("旅行对话输入").fill("北京两天，上海两天，直接规划");
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  await expect(page.getByText(/准备哪天出发/)).toBeVisible();
  await page.getByLabel("旅行对话输入").fill("2027-05-01，直接规划");
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  await expect(
    page.getByRole("button", { name: "第 3 天 · 上海", exact: true }),
  ).toBeVisible({ timeout: 45000 });
  await page.getByRole("button", { name: "第 3 天 · 上海", exact: true }).click();
  await expect(page.locator(".canvas-stops")).toContainText("上海");
  await page.getByRole("button", { name: "更多页面" }).click();
  await page.getByRole("link", { name: "平台与设置", exact: true }).click();
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "下载个人数据 ZIP" }).click(),
  ]);
  expect(download.suggestedFilename()).toContain(".zip");
});
