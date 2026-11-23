import { chromium } from "@playwright/test";
import fs from "node:fs";

const url = process.argv[2];
if (!url) {
  console.error("usage: node xhs-note-reader.mjs <note-url>");
  process.exit(2);
}

const IMAGE_HOST = /(^|\.)(xhscdn\.com|xiaohongshu\.com)$/i;
const LOGIN_WORDS = /登录后|扫码登录|安全验证|访问受限|log\s*in|sign\s*in/i;

function parseJson(text) {
  let out = "";
  let quoted = false;
  let escaped = false;
  for (let i = 0; i < text.length; ) {
    const c = text[i];
    if (quoted) {
      out += c;
      if (escaped) escaped = false;
      else if (c === "\\") escaped = true;
      else if (c === '"') quoted = false;
      i += 1;
    } else if (c === '"') {
      quoted = true;
      out += c;
      i += 1;
    } else if (text.startsWith("undefined", i)) {
      out += "null";
      i += 9;
    } else {
      out += c;
      i += 1;
    }
  }
  return JSON.parse(out);
}

function imageUrl(item) {
  const options = [
    item?.urlDefault,
    item?.urlPre,
    item?.url,
    ...(item?.infoList || []).map((v) => v?.url),
  ];
  for (const candidate of options) {
    if (typeof candidate !== "string" || !candidate) continue;
    const value = candidate.replace(/^http:\/\//, "https://");
    try {
      if (IMAGE_HOST.test(new URL(value).hostname)) return value;
    } catch {
      // ignore invalid image urls
    }
  }
  return "";
}

const headless = process.env.TRIPAL_XHS_HEADED !== "1";
const userDataDir = process.env.TRIPAL_XHS_USER_DATA_DIR;
let browser = null;
let context;
if (userDataDir) {
  fs.mkdirSync(userDataDir, { recursive: true });
  context = await chromium.launchPersistentContext(userDataDir, {
    channel: "chrome",
    headless,
    locale: "zh-CN",
    viewport: { width: 1440, height: 1000 },
  });
} else {
  browser = await chromium.launch({ channel: "chrome", headless });
  context = await browser.newContext({ locale: "zh-CN", viewport: { width: 1440, height: 1000 } });
}
try {
  const page = context.pages()[0] || (await context.newPage());
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(1200);

  await page.keyboard.press("Escape").catch(() => {});
  const closeSelectors = [
    'button[aria-label*="关闭"]',
    '[role="button"][aria-label*="关闭"]',
    '[class*="close-btn"]',
    '[class*="close-icon"]',
    '[class*="login"] [class*="close"]',
    '[class*="modal"] [class*="close"]',
    ".close",
  ];
  for (const selector of closeSelectors) {
    const target = page.locator(selector).first();
    try {
      if (await target.isVisible({ timeout: 500 })) {
        await target.click({ timeout: 1000 });
        await page.waitForTimeout(600);
        break;
      }
    } catch {
      // next selector
    }
  }
  await page.waitForTimeout(400);

  const finalUrl = page.url();
  const host = new URL(finalUrl).hostname.toLowerCase();
  if (!["xiaohongshu.com", "www.xiaohongshu.com", "xhslink.com", "www.xhslink.com", "rednote.com", "www.rednote.com"].includes(host)) {
    throw new Error("unsupported_redirect:" + host);
  }
  const noteId = new URL(url).pathname.split("/").filter(Boolean).pop() || "";

  const result = await page.evaluate(
    ({ noteId }) => {
      const parse = (text) => {
        let out = "";
        let quoted = false;
        let escaped = false;
        for (let i = 0; i < text.length; ) {
          const c = text[i];
          if (quoted) {
            out += c;
            if (escaped) escaped = false;
            else if (c === "\\") escaped = true;
            else if (c === '"') quoted = false;
            i += 1;
          } else if (c === '"') {
            quoted = true;
            out += c;
            i += 1;
          } else if (text.startsWith("undefined", i)) {
            out += "null";
            i += 9;
          } else {
            out += c;
            i += 1;
          }
        }
        return JSON.parse(out);
      };

      let state = window.__INITIAL_STATE__;
      if (typeof state === "string") state = parse(state);
      if (!state) {
        const script = [...document.scripts]
          .map((s) => s.textContent || "")
          .find((text) => text.includes("__INITIAL_STATE__"));
        if (script) {
          const match = script.match(/__INITIAL_STATE__\s*=\s*([\s\S]*)/);
          if (match) {
            try {
              state = parse(match[1].trim().replace(/;\s*$/, ""));
            } catch {
              state = null;
            }
          }
        }
      }

      const notes = state?.note?.noteDetailMap || {};
      let entry = noteId ? notes[noteId] : null;
      if (!entry && Object.keys(notes).length === 1) entry = Object.values(notes)[0];
      const note = entry?.note || {};
      const validNote = note.noteId && (!noteId || note.noteId === noteId);

      const imageHost = /(^|\.)(xhscdn\.com|xiaohongshu\.com)$/i;
      const images = [];
      if (validNote) {
        for (const item of note.imageList || []) {
          const options = [
            item?.urlDefault,
            item?.urlPre,
            item?.url,
            ...(item?.infoList || []).map((v) => v?.url),
          ];
          for (const candidate of options) {
            if (typeof candidate !== "string" || !candidate) continue;
            const value = candidate.replace(/^http:\/\//, "https://");
            try {
              if (imageHost.test(new URL(value).hostname)) {
                images.push(value);
                break;
              }
            } catch {
              // ignore
            }
          }
        }
      }

      const meta = (key) =>
        document.querySelector(`meta[property="${key}"]`)?.content ||
        document.querySelector(`meta[name="${key}"]`)?.content ||
        "";
      const title = String(note.title || meta("og:title") || document.title || "小红书攻略").slice(0, 200);
      const loginWords = /登录后|扫码登录|安全验证|访问受限|log\s*in|sign\s*in/i;
      let body = validNote && typeof note.desc === "string" ? note.desc : "";
      let bodySource = validNote ? "note_body" : "";
      if (!body) {
        body = document.querySelector("#detail-desc")?.innerText || meta("og:description") || "";
        bodySource = "dom_after_login_dismiss";
      }
      if (!body || loginWords.test(body) || loginWords.test(title)) {
        body = "";
      }

      return {
        title: loginWords.test(title) ? "小红书攻略" : title,
        body,
        images: [...new Set(images)],
        complete: Boolean(body || images.length),
        body_source: bodySource,
        url: location.href,
      };
    },
    { noteId },
  );

  console.log(JSON.stringify(result));
} finally {
  if (context) await context.close();
  if (browser) await browser.close();
}
