import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const fixture = JSON.parse(
  readFileSync(new URL("./fixtures/workspace.json", import.meta.url), "utf8"),
);
test.use({
  actionTimeout: 5000,
  permissions: ["microphone"],
  launchOptions: {
    args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
  },
});

test("home keeps chat, preview and recommendations; discovery keeps its large map", async ({
  page,
}) => {
  const messages: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.setViewportSize({ width: 1440, height: 1000 });
  const conversation = () => ({
    id: "home-conv",
    version: messages.length,
    trip_id: "home-trip",
    slots: { destination: "北京" },
    state: { fixture: true },
    messages: messages.map((content, i) => ({
      id: i + 1,
      role: "user",
      content,
      meta: {},
    })),
    task: messages.length
      ? {
          id: "home-task",
          status: "waiting_choice",
          result: { variants: { A: fixture.A }, base_version: 0, draft_revision: 1 },
        }
      : null,
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    let json: unknown = {};
    if (path === "/auth/me")
      json = {
        name: "home-user",
        csrf: "test",
        preferences: {},
        consent: { decided: true },
      };
    else if (path === "/health") json = { voice_enabled: true, voice_ready: true };
    else if (path === "/voice/asr") json = { text: "语音输入的旅行要求" };
    else if (path === "/explore")
      json = {
        items: fixture.A.days[0].stops,
        fixture: true,
        notice: "合成资料",
        next_page: null,
        has_more: false,
        end_reason: "exhausted",
      };
    else if (path.endsWith("/events"))
      return route.fulfill({ contentType: "text/event-stream", body: ": fixture\n\n" });
    else if (path === "/conversations" && route.request().method() === "GET")
      json = messages.length
        ? [{ id: "home-conv", slots: { destination: "北京" } }]
        : [];
    else if (path === "/conversations" || path === "/conversations/home-conv")
      json = conversation();
    else if (path.endsWith("/turns")) {
      messages.push(route.request().postDataJSON().content);
      json = conversation();
    } else if (path === "/trips/home-trip")
      json = { id: "home-trip", version: 0, role: "owner", plan: {} };
    else if (path.endsWith("/daily-details")) json = fixture.details;
    else if (["/trips", "/saved-places"].includes(path)) json = [];
    await route.fulfill({ json });
  });
  await page.goto("/");
  const chat = page.getByLabel("旅行对话输入");
  await expect(chat).toBeVisible();
  await expect(
    page.getByRole("button", { name: "开始语音输入", exact: true }),
  ).toBeVisible();
  await chat.fill("2027-05-01，北京三天，直接规划");
  await page.getByRole("button", { name: "发送旅行对话", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "确认并保存方案 A", exact: true }),
  ).toBeVisible();
  expect(new URL(page.url()).pathname).toBe("/");
  await expect(page.locator(".travel-home-discover")).toBeVisible();
  await page.getByRole("tab", { name: "吃什么", exact: true }).click();
  await expect(page.locator(".meal-detail-card")).toHaveCount(3);
  await page.getByRole("button", { name: "开始语音输入", exact: true }).click();
  await expect(page.getByText(/录音中，最多/)).toBeVisible();
  await page.waitForTimeout(250); // Give the fake microphone a nonempty recording chunk.
  await page.getByRole("button", { name: "停止录音并识别", exact: true }).click();
  await expect(chat).toHaveValue("语音输入的旅行要求");
  expect(messages).toHaveLength(1); // Speech transcribes; it never sends automatically.
  await page.screenshot({
    path: "../reports/planning-home-desktop.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "探索发现", exact: true }).click();
  await expect(page.locator(".mf-map-viewer.is-open")).toBeVisible();
  await expect(page.locator(".assistant-drawer")).toHaveCount(0);
  const cards = await page.locator(".explore-page").boundingBox();
  const map = await page.locator(".mf-map-viewer.is-open").boundingBox();
  expect(map!.x).toBeGreaterThanOrEqual(cards!.x + cards!.width - 2);
  expect(map!.width).toBeGreaterThan(600);
  await page.screenshot({
    path: "../reports/explore-map-restored.png",
    fullPage: true,
  });
  await page.getByRole("link", { name: "开始规划", exact: true }).click();
  await expect(chat).toHaveValue("语音输入的旅行要求");
  await expect(page.getByRole("tab", { name: "吃什么", exact: true })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await page.reload();
  await expect(chat).toHaveValue("语音输入的旅行要求");
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".travel-home-discover")).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBe(true);
  await page.screenshot({
    path: "../reports/planning-home-mobile.png",
    fullPage: true,
  });
  expect(errors).toEqual([]);
});
