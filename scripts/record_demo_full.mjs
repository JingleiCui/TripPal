/** 按正常使用顺序演示全部主要功能，跳过模型等待（用预置的真实行程），全程真实高德地图。 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs/promises";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CASE = JSON.parse(await fs.readFile(path.join(ROOT, "reports/live-daily-case.json"), "utf8"));
const CFG = {
  baseURL: "http://127.0.0.1:8808",
  tmpDir: path.join(ROOT, "reports/demo-full"),
  password: "Local-ui-preview-123",
  tripId: CASE.trip_id,
  timeout: 120_000,
  video: { width: 1440, height: 980 },
  docPath: path.join(ROOT, "docs/assets/demo/sample-guide.md"),
};
const require = createRequire(path.join(ROOT, "frontend/package.json"));
const { chromium, expect: baseExpect } = require("@playwright/test");
const expect = baseExpect.configure({ timeout: CFG.timeout });
await fs.mkdir(CFG.tmpDir, { recursive: true });

const browser = await chromium.launch({ channel: "chrome", headless: true });
let ctx;
async function login(context) {
  const p = await context.newPage();
  await p.goto(CFG.baseURL);
  await p.getByRole("button", { name: "已有账户？登录", exact: true }).click();
  await p.getByLabel("用户名", { exact: true }).fill(CASE.name);
  await p.getByLabel("密码", { exact: true }).fill(CFG.password);
  await p.getByRole("button", { name: "登录", exact: true }).click();
  await expect(p.getByRole("heading", { name: "一句话，安排好下一程。" })).toBeVisible();
  const consent = p.getByRole("button", { name: "不参与统计", exact: true });
  if (await consent.isVisible()) await consent.click();
  return p;
}
const tab = (p, name) => p.getByRole("tab", { name, exact: true });
try {
  // 预热：登录 + 加载真实地图瓦片/POI图片 + 上传示例资料，避免录制中出现加载空白
  const warm = await browser.newContext({ viewport: CFG.video });
  const wp = await login(warm);
  await wp.goto(`${CFG.baseURL}/trips/${CFG.tripId}`);
  await expect(wp.locator(".amap-container")).toBeVisible({ timeout: 60000 });
  await expect(wp.getByText(/AutoNavi/).first()).toBeVisible({ timeout: 60000 });
  await expect(wp.locator(".timeline-entry").first()).toBeVisible({ timeout: 90000 });
  await wp.goto(`${CFG.baseURL}/explore`);
  await expect(wp.locator(".place-photo img").first()).toBeVisible({ timeout: 45000 });
  await wp.waitForTimeout(1500);
  // 预热时收藏 3 个真实 POI，让收藏页有内容可展示（真实账号操作）
  const favBtns = wp.locator('button[aria-label^="收藏"]');
  const favCount = Math.min(3, await favBtns.count());
  for (let i = 0; i < favCount; i++) {
    await favBtns.nth(i).click();
    await wp.waitForTimeout(600);
  }
  console.log("warmed favorites:", favCount);
  await wp.goto(`${CFG.baseURL}/documents`);
  if (await wp.getByLabel("上传旅行资料").count()) {
    await wp.getByLabel("上传旅行资料").setInputFiles(CFG.docPath);
    await wp.waitForTimeout(2000);
  }
  const state = await warm.storageState();
  await warm.close();

  ctx = await browser.newContext({
    viewport: CFG.video,
    storageState: state,
    recordVideo: { dir: CFG.tmpDir, size: CFG.video },
  });
  const page = await ctx.newPage();
  page.setDefaultTimeout(CFG.timeout);
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  const hold = (ms) => page.waitForTimeout(ms);
  const step = (n) => console.log("STEP " + n);

  // 1. 首页：描述需求入口（填入旅行想法，展示需求描述）
  step("1 home / 描述需求");
  await page.goto(CFG.baseURL);
  await expect(page.getByRole("heading", { name: "一句话，安排好下一程。" })).toBeVisible();
  await hold(1200);
  const idea = page.getByLabel("旅行想法", { exact: true });
  if (await idea.count()) {
    await idea.fill("北京三日游，喜欢历史文化，想吃地道小吃，住在地铁站附近，节奏轻松一点。");
  }
  await hold(1800);

  // 2. 行程：每日安排 + 真实高德地图（跳过模型等待，直接用已规划好的真实行程）
  step("2 trip / 每日安排 + 真实地图");
  await page.goto(`${CFG.baseURL}/trips/${CFG.tripId}`);
  await expect(page.locator(".amap-container")).toBeVisible();
  await expect(page.getByText(/AutoNavi/).first()).toBeVisible();
  await expect(page.locator(".timeline-entry").first()).toBeVisible();
  await hold(2800);

  // 3. 吃什么
  step("3 吃什么");
  await tab(page, "吃什么").click();
  await expect(page.locator(".meal-detail-card").first()).toBeVisible();
  await hold(2300);

  // 4. 住哪里
  step("4 住哪里");
  await tab(page, "住哪里").click();
  await hold(2300);

  // 5. 怎么走
  step("5 怎么走");
  await tab(page, "怎么走").click();
  await hold(2300);

  // 6. 花费
  step("6 花费");
  await tab(page, "花费").click();
  await hold(2300);

  // 7. 依据/来源
  step("7 依据与来源");
  await tab(page, "每日安排").click();
  await page.getByRole("button", { name: "依据", exact: true }).click();
  await expect(page.locator(".sources-panel .source-row").first()).toBeVisible();
  await hold(2400);

  // 8. 路书
  step("8 路书");
  await page.goto(`${CFG.baseURL}/trips/${CFG.tripId}/routebook`);
  await expect(page.locator("h1,h2").first()).toBeVisible();
  await hold(2400);

  // 9. 探索发现：真实地图 + 真实 POI 照片
  step("9 探索发现 / 真实地图+POI");
  await page.goto(`${CFG.baseURL}/explore`);
  await expect(page.locator(".place-photo img").first()).toBeVisible();
  await hold(2600);
  await page.evaluate(() => window.scrollTo(0, 560));
  await hold(1800);

  // 10. 旅行收藏
  step("10 旅行收藏");
  await page.goto(`${CFG.baseURL}/saved`);
  await hold(2000);

  // 11. 资料检索：真实上传+索引+检索
  step("11 资料检索");
  await page.goto(`${CFG.baseURL}/documents`);
  const q = page.getByLabel("检索问题");
  if (await q.isVisible()) {
    await q.fill("示例旅行节奏如何安排？");
    await page.getByRole("button", { name: "检索资料", exact: true }).click();
    await expect(page.locator(".retrieval-hit").first()).toBeVisible();
    await hold(2600);
  }

  // 12. 我的行程（留存/版本）收尾
  step("12 我的行程");
  await page.goto(`${CFG.baseURL}/archive`);
  await hold(2000);

  if (errors.length) console.log("pageerrors:", errors);
  const video = page.video();
  await ctx.close();
  ctx = null;
  const out = path.join(CFG.tmpDir, "demo-full.webm");
  await video.saveAs(out);
  console.log("VIDEO_PATH=" + out);
  console.log("DONE, pageerrors=" + errors.length);
} finally {
  if (ctx) await ctx.close();
  await browser.close();
}
