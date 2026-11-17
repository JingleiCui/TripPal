import { test, expect, Page } from "@playwright/test";

async function register(page: Page) {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("discover-" + Date.now());
  await page.getByLabel("密码", { exact: true }).fill("travel-discovery-123");
  await page.getByRole("button", { name: "创建账户", exact: true }).click();
  await page.getByRole("button", { name: "不参与统计", exact: true }).click();
}

test("discovery: search, detail, save, collections, planning and assistant preferences persist", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 1000 });
  await register(page);
  await page.getByRole("button", { name: "寻找美食", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "餐厅美食", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("合成资料体验", { exact: true }).check();
  await expect(
    page.getByRole("heading", { name: "演示·北京餐厅 1", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "查看演示·北京餐厅 1", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "演示·北京餐厅 1详情" })).toBeVisible();
  await page.getByRole("button", { name: "加入旅行收藏", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "已加入收藏", exact: true }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "关闭地点详情" }).click();
  await page.screenshot({
    path: "../reports/explore-desktop.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "旅行收藏", exact: true }).click();
  await page.getByRole("button", { name: "编辑收藏", exact: true }).click();
  await page.getByLabel("收藏夹名称", { exact: true }).fill("北京美食之旅");
  await page.getByLabel("想去的理由", { exact: true }).fill("想和朋友一起吃当地菜");
  await page.getByRole("button", { name: "保存收藏", exact: true }).click();
  await page.reload();
  await expect(page.getByText("想和朋友一起吃当地菜", { exact: true })).toBeVisible();
  await page.screenshot({
    path: "../reports/saved-desktop.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "用此地点规划", exact: true }).click();
  await expect(page.getByLabel("目的地", { exact: true })).toHaveValue("北京");
  await expect(page.getByLabel("还有什么特别期待？", { exact: true })).toHaveValue(
    /演示·北京餐厅 1/,
  );
  await expect(page.getByRole("checkbox", { name: /合成流程体验/ })).toBeChecked();
  await page.getByRole("button", { name: "更多页面", exact: true }).click();
  await page.getByRole("link", { name: "旅行偏好", exact: true }).click();
  await page.getByLabel("默认目的地", { exact: true }).fill("上海");
  await page.getByLabel("默认旅行天数", { exact: true }).selectOption("4");
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page.getByRole("button", { name: "当地美食", exact: true }).click();
  await page.getByRole("button", { name: "下一步", exact: true }).click();
  await page
    .getByLabel("旅行节奏", { exact: true })
    .selectOption({ label: "轻松慢游，每天少安排一些" });
  await page.getByRole("button", { name: "保存旅行偏好", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "旅行助手，已经更了解你了。" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "开始我的旅行", exact: true }).click();
  await page.locator(".planning-details > summary").click();
  await expect(page.getByLabel("目的地", { exact: true })).toHaveValue("上海");
  await expect(page.getByLabel("天数", { exact: true })).toHaveValue("4");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/explore");
  await page.getByLabel("合成资料体验", { exact: true }).check();
  await expect(
    page.getByRole("heading", { name: "演示·城市博物馆", exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page.screenshot({
    path: "../reports/explore-mobile.png",
    fullPage: true,
  });
  await page.goto("/saved");
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  expect(errors).toEqual([]);
});

test("bookings: attach receipt, edit logistics, survive refresh and remove", async ({
  page,
}) => {
  await register(page);
  await page.locator(".planning-details > summary").click();
  await page.getByLabel("出发位置", { exact: true }).fill("北京站");
  await page.getByLabel("出游日期", { exact: true }).fill("2027-05-01");
  await page.getByRole("checkbox", { name: /合成流程体验/ }).check();
  await page.getByRole("button", { name: "开始规划", exact: true }).click();
  await page.getByRole("button", { name: "查看每日安排", exact: true }).click();
  await page.getByRole("button", { name: "订单与凭证", exact: true }).click();
  await page.getByRole("button", { name: "添加已安排事项", exact: true }).click();
  await page.getByLabel("安排名称", { exact: true }).fill("北京住宿确认单");
  await page.getByLabel("开始时间", { exact: true }).fill("2027-05-01T14:00");
  await page.getByLabel("结束时间（可选）", { exact: true }).fill("2027-05-04T12:00");
  await page.getByLabel("确认号（可选）", { exact: true }).fill("TRAVEL-2027");
  await page.getByLabel("上传订单凭证", { exact: true }).setInputFiles({
    name: "住宿确认.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("北京住宿，三晚，确认号 TRAVEL-2027"),
  });
  await expect(page.getByLabel("关联已有凭证", { exact: true })).not.toHaveValue("");
  await page.getByRole("button", { name: "保存安排", exact: true }).click();
  await expect(page.getByText("确认号：TRAVEL-2027", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "关闭订单与凭证" }).click();
  await page.reload();
  await page.getByRole("button", { name: "订单与凭证", exact: true }).click();
  await expect(
    page.getByRole("link", { name: "查看原始凭证", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page.getByLabel("安排名称", { exact: true }).fill("北京住宿已确认");
  await page.getByRole("button", { name: "保存安排", exact: true }).click();
  await page.screenshot({
    path: "../reports/bookings-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page
    .getByRole("button", { name: "移除安排北京住宿已确认", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "还没有记录已安排的事项", exact: true }),
  ).toBeVisible();
});

test("place cards recover from broken photos and normalize trusted HTTP images", async ({
  page,
}) => {
  const image = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j3vQAAAAASUVORK5CYII=",
    "base64",
  );
  await page.route("https://store.is.autonavi.com/qa-broken-photo.jpg", (route) =>
    route.abort(),
  );
  await page.route("https://store.is.autonavi.com/qa-good-photo.jpg", (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: image }),
  );
  await page.route("**/api/v1/explore?**", async (route) => {
    const response = await route.fetch();
    if (!response.ok()) return route.fulfill({ response });
    const body = await response.json();
    body.items = body.items.map((p: unknown) => ({
      ...(p as object),
      photos: [
        "https://store.is.autonavi.com/qa-broken-photo.jpg",
        "http://store.is.autonavi.com/qa-good-photo.jpg",
      ],
    }));
    await route.fulfill({ response, json: body });
  });
  await register(page);
  await page.goto("/explore");
  await page.getByLabel("合成资料体验", { exact: true }).check();
  const photo = page
    .getByRole("button", { name: "查看演示·城市博物馆", exact: true })
    .locator("img");
  await expect(photo).toHaveAttribute(
    "src",
    "https://store.is.autonavi.com/qa-good-photo.jpg",
  );
  await expect
    .poll(() =>
      photo.evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0),
    )
    .toBeTruthy();
});
