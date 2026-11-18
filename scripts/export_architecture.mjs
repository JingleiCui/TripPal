/** Fixed-grid SVG → PNG. Edit CONFIG, then run directly; no Mermaid dependency. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CONFIG = {
  directory: path.join(ROOT, 'docs/assets/architecture/structured'),
  browserChannel: 'chrome',
  exportScale: 2,
  textPadding: 8,
};
const require = createRequire(path.join(ROOT, 'frontend/package.json'));
const { chromium } = require('playwright');
const browser = await chromium.launch({ channel: CONFIG.browserChannel, headless: true });
let issues = 0;
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1600 }, deviceScaleFactor: CONFIG.exportScale });
  for (const file of (await fs.readdir(CONFIG.directory)).filter(name => name.endsWith('.svg')).sort()) {
    const source = await fs.readFile(path.join(CONFIG.directory, file), 'utf8');
    await page.setContent('<style>body{margin:0}svg{display:block}</style>' + source);
    await page.evaluate(() => document.fonts.ready);
    const errors = await page.evaluate(padding => {
      const svg = document.querySelector('svg');
      const canvas = svg.viewBox.baseVal;
      return [...document.querySelectorAll('text')].flatMap(text => {
        const b = text.getBBox();
        const box = text.closest('[data-box]');
        const [x,y,w,h] = box ? box.dataset.box.split(',').map(Number) : [0,0,canvas.width,canvas.height];
        const p = box ? padding : 0;
        return b.x < x+p || b.y < y+p || b.x+b.width > x+w-p || b.y+b.height > y+h-p
          ? [{ text:text.textContent, bounds:[b.x,b.y,b.width,b.height], container:[x,y,w,h] }] : [];
      });
    }, CONFIG.textPadding);
    if (errors.length) { issues += errors.length; console.error(file, JSON.stringify(errors)); }
    await page.locator('svg').screenshot({ path: path.join(CONFIG.directory, file.replace('.svg','.png')) });
    console.log(`${file}: exported PNG; ${errors.length} text overflow issues`);
  }
} finally { await browser.close(); }
if (issues) process.exitCode = 1;
