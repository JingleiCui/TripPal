/** Run from an IDE or `node scripts/capture_brand_demo.mjs` after starting the app.
 * Configuration lives here; the script creates an isolated local QA account and
 * explicitly selects synthetic planning data. It never modifies existing trips.
 */
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs/promises";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CONFIG = {
  baseURL: "http://127.0.0.1:8808",
  outputDir: path.join(ROOT, "docs/assets"),
  videoDir: path.join(ROOT, "reports/brand-video"),
  viewport: { width: 1440, height: 1000 },
  browserChannel: "chrome",
  timeoutMs: 90_000,
  accountName: `visual-demo-${Date.now()}`,
  accountPassword: "local-visual-demo-2026",
  tripPrompt: "去北京玩三天，两个人，总预算3000元，喜欢历史文化，少走路，直接规划。",
  documentPath: path.join(ROOT, "docs/assets/demo/sample-guide.md"),
};
const require = createRequire(path.join(ROOT, "frontend/package.json"));
const { chromium, expect: baseExpect } = require("@playwright/test");
const expect = baseExpect.configure({ timeout: CONFIG.timeoutMs });
await fs.mkdir(CONFIG.videoDir, { recursive: true });
await fs.mkdir(path.join(CONFIG.outputDir, "ui"), { recursive: true });
const browser = await chromium.launch({ channel: CONFIG.browserChannel, headless: true });
let context;
try {
  const registration = await browser.newContext({ viewport: CONFIG.viewport });
  const auth = await registration.newPage();
  await auth.goto(CONFIG.baseURL);
  await auth.getByLabel("用户名", { exact: true }).fill(CONFIG.accountName);
  await auth.getByLabel("密码", { exact: true }).fill(CONFIG.accountPassword);
  await auth.getByRole("button", { name: "创建账户", exact: true }).click();
  await auth.getByRole("button", { name: "不参与统计", exact: true }).click();
  // A fresh load also verifies that the consent decision persists server-side.
  await auth.reload();
  await auth.getByLabel("旅行想法", { exact: true }).waitFor();
  const state = await registration.storageState();
  await registration.close();
  context = await browser.newContext({
    viewport: CONFIG.viewport,
    storageState: state,
    recordVideo: { dir: CONFIG.videoDir, size: { width: 1152, height: 800 } },
  });
  const page = await context.newPage();
  page.setDefaultTimeout(CONFIG.timeoutMs);
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  const capture = async name => {
    await page.screenshot({ path: path.join(CONFIG.outputDir, `ui/${name}.png`) });
    console.log(`Captured ${name}`);
  };
  await page.goto(CONFIG.baseURL);
  await page.getByLabel("旅行想法", { exact: true }).waitFor();
  await capture("home");
  // Short holds make the recording readable; all action waits use real UI states.
  await page.waitForTimeout(1400);
  await page.getByLabel("旅行想法", { exact: true }).fill(CONFIG.tripPrompt);
  await page.getByRole("link", { name: "新建旅行", exact: true }).click();
  await page.getByLabel(/使用合成资料体验/).check();
  await page.getByLabel("给我两个不同方案供选择").check();
  await page.getByLabel("旅行对话输入").fill(CONFIG.tripPrompt);
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  await expect(page.getByRole("button", { name: "选择并保存方案 A" })).toBeEnabled();
  await capture("recommendations");
  await page.waitForTimeout(1800);
  await page.getByRole("button", { name: "选择并保存方案 A" }).click();
  await expect(page.locator(".canvas-save-status")).toBeVisible();
  await expect(page.locator(".timeline-entry").first()).toBeVisible();
  await capture("itinerary");
  await page.waitForTimeout(1800);
  const trips = await page.evaluate(async () => {
    const response = await fetch("/api/v1/trips");
    if (!response.ok) throw new Error(`Trip list returned ${response.status}`);
    return response.json();
  });
  const tripId = trips[0]?.id;
  if (!tripId) throw new Error("Saved trip not found");
  await page.goto(`${CONFIG.baseURL}/trips/${tripId}`);
  await page.getByRole("button", { name: "依据", exact: true }).click();
  await expect(page.locator(".sources-panel .source-row").first()).toBeVisible();
  await capture("sources");
  await page.waitForTimeout(1800);
  await page.goto(`${CONFIG.baseURL}/documents`);
  const uploadResponse = page.waitForResponse(response =>
    response.url().endsWith("/api/v1/documents") && response.request().method() === "POST",
  );
  await page.getByLabel("上传旅行资料").setInputFiles(CONFIG.documentPath);
  if (!(await uploadResponse).ok()) throw new Error("Sample document upload failed");
  // Reopen the list after upload, including when the initial empty-list fetch was in flight.
  await page.reload();
  await expect(page.getByText(/已索引/).first()).toBeVisible();
  await page.getByLabel("检索问题").fill("示例旅行节奏如何安排？");
  await page.getByRole("button", { name: "检索资料", exact: true }).click();
  await expect(page.locator(".retrieval-hit").first()).toBeVisible();
  await capture("retrieval");
  await page.waitForTimeout(1800);
  const responsive = [];
  await page.goto(CONFIG.baseURL);
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.getByLabel("旅行想法", { exact: true }).waitFor();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    responsive.push({ width, overflow });
    if (overflow) throw new Error(`Horizontal overflow at ${width}px`);
  }
  const radii = await page.evaluate(() => Object.fromEntries(
    [".app-header", ".category-chip", ".home-composer", ".travel-home-postcard", ".destination-card"].map(selector => {
      const element = document.querySelector(selector);
      return [selector, element ? getComputedStyle(element).borderTopLeftRadius : null];
    }),
  ));
  if (Object.values(radii).some(radius => radius !== "12px")) {
    throw new Error(`Inconsistent component radii: ${JSON.stringify(radii)}`);
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await capture("home-mobile");
  await page.emulateMedia({ reducedMotion: "reduce" });
  const reducedMotion = await page.evaluate(() => matchMedia("(prefers-reduced-motion: reduce)").matches);
  if (errors.length) throw new Error(errors.join("\n"));
  const video = page.video();
  await context.close();
  context = null;
  await video.saveAs(path.join(CONFIG.outputDir, "demo/tripal-demo.webm"));
  await fs.writeFile(path.join(CONFIG.outputDir, "demo/verification.json"), JSON.stringify({
    date: "2026-11-17", source: "Running local app; no API mocks", fixturePlanning: true,
    retrieval: "Real document upload, indexing and search using self-authored sample-guide.md",
    pageErrors: errors, responsive, reducedMotion, radii,
  }, null, 2) + "\n");
  console.log("Saved video and browser verification.");
} finally {
  if (context) await context.close();
  await browser.close();
}
