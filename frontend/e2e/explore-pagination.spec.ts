import { test, expect, type Page } from "@playwright/test";

async function openExplore(page: Page) {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill(`browse-${Date.now()}`);
  await page.getByLabel("密码", { exact: true }).fill("browse-local-test-2026");
  await page.getByRole("button", { name: "创建账户", exact: true }).click();
  await page.getByLabel("旅行想法", { exact: true }).waitFor();
  const consent = page.getByRole("button", { name: "不参与统计", exact: true });
  if (await consent.isVisible()) await consent.click();
  await page.goto("/explore");
  await page.getByLabel("合成资料体验", { exact: true }).check();
  await expect(page.locator(".discovery-place")).toHaveCount(20);
}

test("scroll appends real fixture pages, resets categories and retains a large sticky map", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await openExplore(page);
  const map = page.locator(".mf-map-viewer.is-open");
  const initial = await map.boundingBox();
  expect(initial!.width / 1440).toBeGreaterThan(0.55);
  await page.locator(".discovery-pagination").scrollIntoViewIfNeeded();
  await expect(page.locator(".discovery-place")).toHaveCount(36);
  const ids = await page.locator(".discovery-place h3").allTextContents();
  expect(new Set(ids).size).toBe(36);
  await expect(page.getByText(/已经到底了/)).toBeVisible();
  const scrolled = await map.boundingBox();
  expect(scrolled!.y).toBeGreaterThanOrEqual(110);
  expect(scrolled!.y).toBeLessThan(140);
  await page.getByRole("button", { name: "住宿地点", exact: true }).click();
  await expect(page.locator(".discovery-place")).toHaveCount(20);
  await expect(page.locator(".discovery-place h3").first()).toHaveText(
    "演示·北京酒店 1",
  );
  await page.locator(".discovery-pagination").scrollIntoViewIfNeeded();
  await expect(page.locator(".discovery-place")).toHaveCount(36);
  await page.getByRole("button", { name: "收藏演示·北京酒店 36", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "已收藏演示·北京酒店 36", exact: true }),
  ).toBeDisabled();
  await page.screenshot({ path: "../reports/discovery-paged-desktop.png" });
  expect(errors).toEqual([]);
});

test("failed next page preserves cards, retry succeeds, duplicate IDs are not appended", async ({
  page,
}) => {
  let failNext = true;
  await page.route("**/api/v1/explore?**", async (route) => {
    const url = new URL(route.request().url());
    if (
      url.searchParams.get("fixture") !== "true" ||
      url.searchParams.get("page") !== "2"
    )
      return route.continue();
    if (failNext) {
      failNext = false;
      return route.fulfill({ status: 503, json: { detail: "测试下一页短暂不可用" } });
    }
    const response = await route.fetch();
    const body = await response.json();
    body.items.push(body.items[0]);
    return route.fulfill({ response, json: body });
  });
  await openExplore(page);
  await page.locator(".discovery-pagination").scrollIntoViewIfNeeded();
  await expect(
    page.getByRole("button", { name: "重试加载", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".discovery-place")).toHaveCount(20);
  await page.getByRole("button", { name: "重试加载", exact: true }).click();
  await expect(page.locator(".discovery-place")).toHaveCount(36);
});

test("mobile browsing has no horizontal overflow, and a collapsed map stays collapsed while loading", async ({
  page,
}) => {
  await page.setViewportSize({ width: 375, height: 844 });
  await openExplore(page);
  await page.getByRole("button", { name: "收起地图", exact: true }).click();
  await page.locator(".discovery-pagination").scrollIntoViewIfNeeded();
  await expect(page.locator(".discovery-place")).toHaveCount(36);
  await expect(page.locator(".mf-map-viewer.is-open")).toHaveCount(0);
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page.getByRole("button", { name: "展开行程地图", exact: true }).click();
  await expect(
    page.getByRole("region", { name: "地点地图", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看演示·城市博物馆", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "演示·城市博物馆详情" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toBeHidden();
  await expect(page.locator(".mf-map-viewer.is-open")).toBeVisible();
  await page.screenshot({ path: "../reports/discovery-paged-mobile.png" });
});

test("the accommodation picker also scrolls past its first page and saves a later candidate", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await openExplore(page);
  const me = await (await page.request.get("/api/v1/auth/me")).json();
  const response = await page.request.post("/api/v1/tasks", {
    headers: { "X-CSRF-Token": me.csrf },
    data: {
      request_key: `hotel-browse-${Date.now()}`,
      fixture: true,
      message: "住宿分页验证",
      requirements: {
        city: "北京",
        days: 2,
        origin: "北京站",
        start_date: "2027-05-01",
      },
    },
  });
  expect(response.ok()).toBeTruthy();
  const task = await response.json();
  await page.goto(`/trips/${task.trip_id}`);
  await page.getByRole("button", { name: "住宿地点", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "选择住宿地点", exact: true });
  await dialog.getByLabel("酒店查询", { exact: true }).fill("北京站");
  await dialog.getByRole("button", { name: "查询地点", exact: true }).click();
  await expect(dialog.locator(".hotel-choice")).toHaveCount(20);
  await dialog.locator(".discovery-pagination").scrollIntoViewIfNeeded();
  await expect(dialog.locator(".hotel-choice")).toHaveCount(36);
  await page.setViewportSize({ width: 375, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await dialog
    .locator(".hotel-choice")
    .last()
    .getByRole("button", { name: "选择", exact: true })
    .click();
  await expect(dialog).toBeHidden();
  const trip = await (await page.request.get(`/api/v1/trips/${task.trip_id}`)).json();
  expect(trip.plan.hotels[0].name).toBe("演示·北京旅居酒店 36");
});
