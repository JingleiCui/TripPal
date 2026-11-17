import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

test("opt-in real Amap SDK, markers and hotel location", async ({ page }) => {
  test.skip(
    process.env.TRAVEL_LIVE_MAP !== "1",
    "Requires own configured Amap keys and explicitly prepared live case",
  );
  const data = JSON.parse(readFileSync("../reports/amap-browser-case.json", "utf8"));
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill(data.name);
  await page.getByLabel("密码", { exact: true }).fill("Map-browser-check-123");
  await page.getByRole("button", { name: "已有账户？登录", exact: true }).click();
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "一句话，安排好下一程。" })).toBeVisible();
  const consent = page.getByRole("button", { name: "不参与统计", exact: true });
  if (await consent.isVisible()) await consent.click();
  await page.goto("/trips/" + data.trip_id);
  await expect(page.locator(".amap-container")).toBeVisible({ timeout: 45000 });
  await expect
    .poll(() => page.locator(".colored-map-pin").count(), { timeout: 30000 })
    .toBeGreaterThanOrEqual(2);
  await expect(page.locator(".map-shell")).toHaveAttribute("data-map-state", "ready", {
    timeout: 25000,
  });
  await expect(page.locator(".colored-map-pin").first()).toBeInViewport();
  await page.screenshot({
    path: "../reports/amap-real-desktop.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "住宿地点", exact: true }).click();
  await page.getByLabel("酒店查询").fill("北京站");
  await page.getByRole("button", { name: "查询地点", exact: true }).click();
  await expect(page.locator(".hotel-choice").first()).toBeVisible({
    timeout: 35000,
  });
  await page.getByRole("button", { name: "选择", exact: true }).first().click();
  await expect(
    page.getByRole("heading", { name: "把住宿地点放到地图上" }),
  ).not.toBeVisible();
  await expect(
    page.locator(".amap-marker-label").filter({ hasText: "住宿" }),
  ).toBeVisible({ timeout: 15000 });
  await expect(page.locator(".map-shell")).toHaveAttribute("data-map-state", "ready", {
    timeout: 25000,
  });
  await expect(page.locator(".colored-map-pin").first()).toBeInViewport();
  await page.screenshot({
    path: "../reports/amap-real-hotel.png",
    fullPage: true,
  });
});
