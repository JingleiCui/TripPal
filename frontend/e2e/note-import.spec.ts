import { test, expect } from "@playwright/test";

test.use({ actionTimeout: 15000 });

// Controlled provider content verifies the interaction without spending model calls.
test("note import: fallback, source review, ignored watermark, map preview and recovery", async ({
  page,
}) => {
  const note = {
    id: "note-one",
    name: "北京攻略",
    kind: "travel_note",
    parsed: {
      status: "needs_input",
      stage: "请补充正文或图片",
      url: "https://www.xiaohongshu.com/explore/example",
      link_status: "error",
      link_error: "笔记链接需要登录，请补充正文和图片",
      link_body: "",
      manual_body: "",
      selected_fact_ids: [] as string[],
      confirmed_at: "",
      auto_adopted_at: "",
      facts: [] as any[],
      images: [] as any[],
    },
  };
  let confirmed = false;
  const turns: any[] = [];
  await page.addInitScript(() =>
    localStorage.setItem("tripal-analytics-consent", "denied"),
  );
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    const method = route.request().method();
    let result: unknown = {};
    if (path === "/auth/me")
      result = { id: "note-user", name: "note-user", csrf: "test", consent: { decided: true, analytics: false }, preferences: {} };
    else if (path === "/health") result = { voice_enabled: false, voice_ready: false };
    else if (
      ["/trips", "/saved-places", "/conversations"].includes(path) &&
      method === "GET"
    )
      result = [];
    else if (path === "/explore")
      result = { items: [], notice: "受控测试资料", fixture: true, has_more: false };
    else if (path.endsWith("/events"))
      return route.fulfill({ contentType: "text/event-stream", body: ": test\n\n" });
    else if (path === "/note-imports" && method === "POST") result = note;
    else if (path === "/note-imports" && method === "GET")
      result = [{ id: note.id, name: note.name, status: note.parsed.status }];
    else if (path === "/note-imports/note-one/sources") {
      note.parsed.status = "ready";
      note.parsed.stage = "解析完成，等待核对";
      note.parsed.manual_body = "北京颐和园一日游，票价仅供参考。";
      const place = {
        id: "amap:test",
        name: "颐和园",
        city: "北京",
        lon: 116.27,
        lat: 39.99,
        photos: [],
        description: "候选地点",
        address: "北京市海淀区",
        source: { provider: "amap", retrieved_at: "2026-11-22T00:00:00Z" },
      };
      note.parsed.facts = [
        {
          id: "city",
          kind: "city",
          text: "北京",
          city: "北京",
          sources: [{ anchor: "manual_body:1", quote: "北京颐和园一日游" }],
          candidates: [],
          place: null,
        },
        {
          id: "place",
          kind: "place",
          text: "颐和园",
          city: "北京",
          sources: [{ anchor: "image:guide:1", quote: "颐和园" }],
          candidates: [place],
          place,
        },
      ];
      note.parsed.images = [
        {
          id: "guide",
          status: "ok",
          text: "颐和园游览路线",
          tiles: [{ box: [0, 0, 100, 100] }],
        },
        {
          id: "photo",
          status: "skipped",
          classification: "watermark",
          skip_reason: "仅相机水印，无攻略文字",
          text: "",
          tiles: [],
        },
      ];
      result = note;
    } else if (path === "/note-imports/note-one/confirm") {
      const body = route.request().postDataJSON();
      expect(body.selected_fact_ids).toEqual(["city", "place"]);
      expect(body.auto).toBeTruthy();
      confirmed = true;
      note.parsed.selected_fact_ids = body.selected_fact_ids;
      note.parsed.confirmed_at = "2026-11-23T10:00:00Z";
      note.parsed.auto_adopted_at = "2026-11-23T10:00:00Z";
      result = note;
    } else if (path === "/note-imports/note-one") result = note;
    else if (path === "/conversations" && method === "POST")
      result = {
        id: "conv-note",
        version: 0,
        slots: {},
        state: { fixture: true },
        messages: [],
        task: null,
      };
    else if (path.endsWith("/turns")) {
      expect(confirmed).toBeTruthy();
      const body = route.request().postDataJSON();
      turns.push(body);
      expect(body.attachment_ids).toEqual(["note-one"]);
      result = {
        id: "conv-note",
        version: 1,
        slots: { destination: "北京" },
        state: { fixture: true },
        messages: [],
        task: null,
      };
    } else if (path === "/conversations/conv-note")
      result = {
        id: "conv-note",
        version: 1,
        slots: { destination: "北京" },
        state: { fixture: true },
        messages: [],
        task: null,
      };
    else if (path.includes("/images/"))
      return route.fulfill({ status: 404, body: "fixture image" });
    return route.fulfill({ json: result });
  });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/");
  const consent = page.getByRole("button", { name: "不参与统计", exact: true });
  if (await consent.isVisible()) await consent.click();
  await page
    .getByLabel("旅行对话输入")
    .fill("收藏的攻略 https://xhslink.com/a/example");
  await page.getByRole("button", { name: "发送旅行对话" }).click();
  const panel = page.getByRole("region", { name: "小红书攻略导入" });
  await expect(panel.getByText("笔记链接需要登录，请补充正文和图片")).toBeVisible();
  await panel
    .getByLabel("笔记正文", { exact: true })
    .fill("北京颐和园一日游，票价仅供参考。");
  await panel.getByRole("button", { name: "补充到这篇攻略", exact: true }).click();
  // 正文解析完成后应自动确认并发起一轮对话，无需人工勾选确认。
  await expect.poll(() => turns.length).toBe(1);
  await page.getByRole("button", { name: /小红书攻略导入/ }).click();
  await expect(panel.getByText(/已匹配 1 个攻略候选地点/)).toBeVisible();
  await panel.getByText("图片 2 · 已跳过 · 0 个分块", { exact: true }).click();
  await expect(panel.getByText("仅相机水印，无攻略文字，未做文字提取。")).toBeVisible();
  await expect(panel.getByRole("button", { name: "仍然识别这张图片" })).toBeVisible();
  await panel
    .locator(".note-fact")
    .last()
    .getByText("查看来源", { exact: true })
    .click();
  await expect(panel.getByText("图片 1 · 第 1 段", { exact: true })).toBeVisible();
  await page.screenshot({ path: "../reports/note-import-desktop.png", fullPage: true });
  await page.reload();
  if (await consent.isVisible()) await consent.click();
  await expect(page.getByText("已自动交给助手", { exact: true })).toBeVisible();
  await expect.poll(() => turns.length).toBe(1);
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBeTruthy();
  await page.screenshot({ path: "../reports/note-import-mobile.png", fullPage: true });
  await page.unrouteAll({ behavior: "ignoreErrors" });
});
