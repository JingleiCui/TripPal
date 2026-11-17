import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

// Live QA uses a dedicated local account and real provider calls. Keep opt-in to avoid routine API usage.
const LIVE_CASE_PATH = "../reports/live-daily-case.json";
const LIVE_CASE_PASSWORD = "Local-ui-preview-123";
test("opt-in real daily dining, lodging and map", async ({ page }) => {
  test.skip(
    process.env.TRAVEL_LIVE_DAILY !== "1",
    "Requires the prepared real-provider QA case",
  );
  test.setTimeout(180000);
  const data = JSON.parse(readFileSync(LIVE_CASE_PATH, "utf8"));
  await page.setViewportSize({ width: 1500, height: 1000 });
  await page.goto("/");
  await page.getByRole("button", { name: "已有账户？登录", exact: true }).click();
  await page.getByLabel("用户名", { exact: true }).fill(data.name);
  await page.getByLabel("密码", { exact: true }).fill(LIVE_CASE_PASSWORD);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "一句话，安排好下一程。" })).toBeVisible();
  const consent = page.getByRole("button", { name: "不参与统计", exact: true });
  if (await consent.isVisible()) await consent.click();
  await page.goto("/explore");
  await expect(page.locator(".place-photo img")).toHaveCount(8, {
    timeout: 30000,
  });
  for (const photo of await page.locator(".place-photo img").all()) {
    await photo.scrollIntoViewIfNeeded();
    await expect
      .poll(
        () =>
          photo.evaluate(
            (img: HTMLImageElement) => img.complete && img.naturalWidth > 0,
          ),
        { timeout: 15000 },
      )
      .toBeTruthy();
  }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({
    path: "../reports/explore-photos-fixed.png",
    fullPage: true,
  });
  await page.goto("/trips/" + data.trip_id);
  await page.getByRole("tab", { name: "吃什么", exact: true }).click();
  await expect(page.locator(".meal-detail-card")).toHaveCount(3, {
    timeout: 120000,
  });
  await expect(page.locator(".meal-detail-card").first()).not.toContainText("演示·");
  await expect(page.locator(".map-shell")).toHaveAttribute("data-map-state", "ready", {
    timeout: 40000,
  });
  await page.screenshot({
    path: "../reports/real-daily-food-desktop.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "住哪里", exact: true }).click();
  await expect(page.locator(".stay-detail-card")).toBeVisible();
  await page.screenshot({
    path: "../reports/real-daily-hotel-desktop.png",
    fullPage: true,
  });
  if (process.env.TRAVEL_LIVE_MARKET === "1") {
    await page.getByRole("button", { name: "查询房型与价格", exact: true }).click();
    await expect
      .poll(() => page.locator(".market-product").count(), { timeout: 160000 })
      .toBeGreaterThan(0);
    await page.screenshot({
      path: "../reports/real-hotel-room-cards.png",
      fullPage: true,
    });
    await page.getByRole("button", { name: "关闭吃住行详情", exact: true }).click();
  }
  await page.getByRole("tab", { name: "花费", exact: true }).click();
  await expect(page.locator(".budget-verdict")).toBeVisible();
  await expect(page.locator(".budget-verdict")).not.toContainText("在预算内");
  await page.screenshot({
    path: "../reports/real-budget-desktop.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "怎么走", exact: true }).click();
  await expect(page.locator(".transport-leg").first()).toContainText("分钟");
  await page.screenshot({
    path: "../reports/real-daily-transport-desktop.png",
    fullPage: true,
  });
});
