import { test, expect } from "@playwright/test";

test("human trip flow: chat, concrete meals, replace restaurant, hotel, route mode and mobile canvas", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto("/");
  await page.getByLabel("用户名", { exact: true }).fill("daily-" + Date.now());
  await page.getByLabel("密码", { exact: true }).fill("travel-daily-test-123");
  await page.getByRole("button", { name: "创建账户", exact: true }).click();
  await page.getByRole("button", { name: "不参与统计", exact: true }).click();
  await expect(page.getByLabel("旅行想法", { exact: true })).toBeVisible();
  await expect(page.getByLabel("出发位置", { exact: true })).not.toBeVisible();
  await page.getByRole("link", { name: "对话规划", exact: true }).click();
  await page.getByLabel(/使用合成资料体验/).check();
  await page
    .getByLabel("旅行对话输入")
    .fill("北京三天，需要酒店，喜欢本地美食，直接规划");
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  await page.getByRole("tab", { name: "吃什么", exact: true }).click();
  await expect(page.locator(".meal-detail-card")).toHaveCount(3, {
    timeout: 45000,
  });
  await expect(page.locator(".meal-detail-card").nth(1)).toContainText(
    "演示·本地家常菜馆",
  );
  await page
    .locator(".meal-detail-card")
    .nth(1)
    .getByRole("button", { name: "换一家", exact: true })
    .click();
  await page
    .locator(".service-candidate")
    .nth(1)
    .getByRole("button", { name: "选这家餐厅", exact: true })
    .click();
  await expect(page.locator(".meal-detail-card").nth(1)).toContainText("演示·街角面馆");
  await page.reload();
  await page.getByRole("tab", { name: "吃什么", exact: true }).click();
  await expect(page.locator(".meal-detail-card").nth(1)).toContainText("演示·街角面馆");
  await page.screenshot({
    path: "../reports/daily-food-desktop.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "住哪里", exact: true }).click();
  await expect(page.locator(".stay-dates")).toContainText("2 晚");
  await page.getByRole("button", { name: "换一家住宿", exact: true }).click();
  await page
    .locator(".service-candidate")
    .nth(1)
    .getByRole("button", { name: "选这家住宿", exact: true })
    .click();
  await expect(page.locator(".stay-detail-card")).toContainText("演示·街区精品酒店");
  await expect(page.locator(".stay-detail-card")).toContainText("你选择的住宿地点");
  await page.getByRole("tab", { name: "怎么走", exact: true }).click();
  await expect(page.locator(".transport-leg").first()).toContainText("分钟");
  await page.getByLabel("当天交通方式", { exact: true }).selectOption("walk");
  await expect(page.getByLabel("当天交通方式", { exact: true })).toHaveValue("walk");
  await expect(page.locator(".transport-leg").first()).toContainText("步行");
  await page.screenshot({
    path: "../reports/daily-transport-desktop.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "花费", exact: true }).click();
  await expect(page.locator(".budget-verdict")).toContainText("尚未设置预算");
  await page.getByLabel("全程总预算", { exact: true }).fill("100");
  await page.getByLabel("当天单独预算", { exact: true }).fill("50");
  await page.getByLabel("预算房间数", { exact: true }).fill("2");
  await page.getByRole("button", { name: "保存预算设置", exact: true }).click();
  await page
    .locator(".expense-row")
    .filter({ hasText: "早餐" })
    .first()
    .getByRole("button")
    .click();
  await page.getByLabel("费用单价", { exact: true }).fill("80");
  await page.getByRole("button", { name: "保存这项费用", exact: true }).click();
  await expect(page.locator(".budget-verdict")).toContainText("30.00");
  await page
    .locator(".expense-row")
    .filter({ hasText: "当晚" })
    .first()
    .getByRole("button")
    .click();
  await page.getByLabel("费用单价", { exact: true }).fill("120");
  await expect(page.locator(".expense-preview")).toContainText("240.00");
  await page.getByLabel("费用金额状态", { exact: true }).selectOption("confirmed");
  await page.getByRole("button", { name: "保存这项费用", exact: true }).click();
  await expect(page.locator(".budget-verdict")).toContainText("320.00");
  await expect(page.locator(".budget-verdict")).toContainText("270.00");
  await page.reload();
  await page.getByRole("tab", { name: "花费", exact: true }).click();
  await expect(page.locator(".budget-verdict")).toContainText("320.00");
  await page.screenshot({
    path: "../reports/budget-desktop.png",
    fullPage: true,
  });
  await page.getByRole("tab", { name: "每日安排", exact: true }).click();
  await expect(page.locator(".experience-timeline")).toContainText("演示·街角面馆");
  await expect(page.locator(".experience-timeline")).toContainText("演示·街区精品酒店");
  await page.screenshot({
    path: "../reports/daily-workspace-desktop.png",
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "行程画布", exact: true }).click();
  await expect(page.locator(".experience-timeline")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page.getByRole("button", { name: "展开地图", exact: true }).click();
  await expect(page.locator(".experience-map")).toBeVisible();
  await page.getByRole("button", { name: "返回安排", exact: true }).click();
  await page.screenshot({
    path: "../reports/daily-workspace-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
