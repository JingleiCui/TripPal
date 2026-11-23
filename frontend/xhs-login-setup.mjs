import { chromium } from "@playwright/test";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

const userDataDir =
  process.env.TRIPAL_XHS_USER_DATA_DIR ||
  path.join(os.homedir(), ".config", "tripal", "xhs-browser-profile");
fs.mkdirSync(userDataDir, { recursive: true });

const context = await chromium.launchPersistentContext(userDataDir, {
  channel: "chrome",
  headless: false,
  locale: "zh-CN",
  viewport: { width: 1280, height: 900 },
});
const page = context.pages()[0] || (await context.newPage());
await page.goto("https://www.xiaohongshu.com/explore/", {
  waitUntil: "domcontentloaded",
  timeout: 30000,
});
console.error(
  "请在打开的 Chrome 窗口中登录小红书；完成后关闭该窗口。最多等待 180 秒，登录态会保存到：" +
    userDataDir,
);
try {
  await page.waitForEvent("close", { timeout: 180000 });
} catch {
  // 超时也保存当前 profile，用户可稍后继续登录。
}
try {
  await context.close();
} catch {
  // 用户已关闭窗口时忽略。
}
console.log(JSON.stringify({ status: "ready", user_data_dir: userDataDir }));
