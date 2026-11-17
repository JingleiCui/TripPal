import { test, expect } from "@playwright/test";
test("desktop: register, plan, version, export, share, archive and documents", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 1050 });
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("browser-" + Date.now());
  await page.getByLabel("密码", { exact: true }).fill("travel-browser-test-123");
  await page.getByRole("button", { name: "创建账户", exact: true }).click();
  await page.getByRole("button", { name: "不参与统计", exact: true }).click();
  await expect(page.getByRole("heading", { name: "下一程，想去哪里？" })).toBeVisible();
  await page.screenshot({
    path: "../reports/home-desktop.png",
    fullPage: true,
  });
  if (await page.locator(".planning-details").count())
    await page.locator(".planning-details > summary").click();
  await page.getByLabel("出发位置", { exact: true }).fill("北京站");
  await page.getByLabel("出游日期", { exact: true }).fill("2027-05-01");
  await page.getByRole("checkbox", { name: /合成流程体验/ }).check();
  await page.getByRole("button", { name: "开始规划", exact: true }).click();
  await expect(page.getByRole("button", { name: "查看每日安排" })).toBeVisible({
    timeout: 45000,
  });
  await page.getByRole("button", { name: "查看每日安排" }).click();
  await expect(
    page.getByRole("heading", { name: "北京 · 3 日城市行程" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "保留安排" }).first().click();
  await expect(page.getByRole("button", { name: "版本 2" })).toBeVisible();
  await page.screenshot({
    path: "../reports/workspace-desktop.png",
    fullPage: true,
  });
  const [download] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "路书", exact: true }).click(),
  ]);
  expect(download.suggestedFilename()).toBe("travel-roadbook.pdf");
  await page.getByRole("button", { name: "分享", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "分享旅行路书" })).toBeVisible();
  await page.getByRole("button", { name: "撤销此链接" }).click();
  await page.getByRole("link", { name: "我的行程", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "留住每一次出发的想法" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "旅行资料", exact: true }).click();
  await page.getByLabel("上传旅行资料").setInputFiles({
    name: "我的攻略.txt",
    mimeType: "text/plain",
    buffer: Buffer.from("这是一份合成旅行资料。测试景区需要提前三天预约。"),
  });
  await expect(page.getByText("我的攻略.txt", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "执行记录", exact: true }).click();
  await expect(page.getByRole("heading", { name: "每一步，都有来处" })).toBeVisible();
  await page.getByRole("link", { name: "平台与设置", exact: true }).click();
  await expect(page.getByRole("heading", { name: "平台与运行设置" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("mobile: navigation, form and overflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("mobile-" + Date.now());
  await page.getByLabel("密码", { exact: true }).fill("travel-mobile-test-123");
  await page.getByRole("button", { name: "创建账户", exact: true }).click();
  await page.getByRole("button", { name: "不参与统计", exact: true }).click();
  await expect(page.getByRole("heading", { name: "下一程，想去哪里？" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({ path: "../reports/home-mobile.png", fullPage: true });
  await page.getByRole("button", { name: "打开导航" }).click();
  await page.getByRole("link", { name: "平台与设置", exact: true }).click();
  await expect(page.getByRole("heading", { name: "平台与运行设置" })).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: "../reports/settings-mobile.png",
    fullPage: true,
  });
});

test("interrupted task survives page refresh and resumes", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("resume-" + Date.now());
  await page.getByLabel("密码", { exact: true }).fill("travel-resume-test-123");
  await page.getByRole("button", { name: "创建账户", exact: true }).click();
  await page.getByRole("button", { name: "不参与统计", exact: true }).click();
  await page.locator(".planning-details > summary").click();
  await page.getByRole("checkbox", { name: /合成流程体验/ }).check();
  await page.getByRole("button", { name: "开始规划", exact: true }).click();
  await expect(page.getByRole("heading", { name: "补充日期与出发位置" })).toBeVisible({
    timeout: 40000,
  });
  await page.reload();
  await expect(page.getByRole("heading", { name: "补充日期与出发位置" })).toBeVisible();
  await page.getByLabel("出发位置", { exact: true }).fill("北京站");
  await page.getByLabel("出游日期", { exact: true }).fill("2027-05-01");
  await page.getByRole("button", { name: "继续调查", exact: true }).click();
  await expect(page.getByRole("button", { name: "查看每日安排" })).toBeVisible({
    timeout: 40000,
  });
});
