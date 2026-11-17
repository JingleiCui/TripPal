/** Export the existing canonical React SVG; no new logo is drawn here. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const CONFIG = {
  source: path.join(ROOT, "frontend/src/components/TripalLogo.tsx"),
  outputDir: path.join(ROOT, "docs/assets/brand"),
  favicon: path.join(ROOT, "frontend/public/tripal-mark.svg"),
  pngSize: 480,
  browserChannel: "chrome",
};
const require = createRequire(path.join(ROOT, "frontend/package.json"));
const { chromium } = require("playwright");
const source = await fs.readFile(CONFIG.source, "utf8");
const match = source.match(/<svg[\s\S]*?<\/svg>/);
if (!match) throw new Error("Canonical logo SVG not found");
const svg = match[0]
  .replace(/\{\/\*[\s\S]*?\*\/\}/g, "")
  .replace("className={className}", "")
  .replace("width={size}", 'width="120"')
  .replace("height={size}", 'height="120"')
  .replace("aria-label={title}", 'aria-label="Tripal 旅伴"')
  .replaceAll("strokeWidth=", "stroke-width=")
  .replaceAll("strokeLinecap=", "stroke-linecap=")
  .replaceAll("strokeDasharray=", "stroke-dasharray=");
if (/[{}]/.test(svg)) throw new Error("Unsupported JSX in logo; update exporter before publishing");
await fs.mkdir(CONFIG.outputDir, { recursive: true });
await fs.writeFile(path.join(CONFIG.outputDir, "tripal-mark.svg"), svg + "\n");
await fs.writeFile(CONFIG.favicon, svg + "\n");
const browser = await chromium.launch({ channel: CONFIG.browserChannel, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: CONFIG.pngSize, height: CONFIG.pngSize } });
  await page.setContent(`<style>body{margin:0}svg{width:100vw;height:100vh}</style>${svg}`);
  await page.screenshot({ path: path.join(CONFIG.outputDir, "tripal-mark.png"), omitBackground: true });
} finally {
  await browser.close();
}
console.log("Exported canonical SVG, transparent PNG and favicon.");
