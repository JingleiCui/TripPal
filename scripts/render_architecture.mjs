/** Edit CONFIG and .mmd files, then run directly. Rendering never changes app code. */
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const CONFIG = {
  sourceDir: path.join(ROOT, 'docs/architecture/diagrams'),
  outputDir: path.join(ROOT, 'docs/assets/architecture'),
  mermaidBundle: path.join(ROOT, 'reports/architecture-tools/node_modules/mermaid/dist/mermaid.min.js'),
  browserChannel: 'chrome',
  exportScale: 2,
};
const require = createRequire(path.join(ROOT, 'frontend/package.json'));
const { chromium } = require('playwright');
await fs.mkdir(CONFIG.outputDir, { recursive: true });
const browser = await chromium.launch({ channel: CONFIG.browserChannel, headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 }, deviceScaleFactor: CONFIG.exportScale });
  await page.setContent('<style>body{margin:0;background:white;font-family:"PingFang SC",Arial,sans-serif}#output{display:inline-block;padding:24px}svg{display:block;max-width:none!important}</style><div id="output"></div>');
  await page.addScriptTag({ path: CONFIG.mermaidBundle });
  await page.evaluate(() => mermaid.initialize({ startOnLoad: false, htmlLabels: false, securityLevel: 'loose', theme: 'base', fontFamily: 'PingFang SC, Microsoft YaHei, Arial, sans-serif', themeVariables: { fontSize: '16px', primaryColor: '#ffffff', primaryTextColor: '#263743', primaryBorderColor: '#9aa9b4', lineColor: '#778e9d', clusterBkg: '#f7f9fb', clusterBorder: '#c8d3db', edgeLabelBackground: '#ffffff', borderRadius: '4' }, flowchart: { htmlLabels: false, curve: 'linear', wrappingWidth: 360, nodeSpacing: 30, rankSpacing: 44, padding: 16, useMaxWidth: false } }));
  for (const file of (await fs.readdir(CONFIG.sourceDir)).filter(name => name.endsWith('.mmd')).sort()) {
    const name = path.basename(file, '.mmd');
    const source = await fs.readFile(path.join(CONFIG.sourceDir, file), 'utf8');
    const result = await page.evaluate(async ({ source, name }) => {
      const { svg } = await mermaid.render('diagram_' + name.replaceAll('-', '_'), source);
      document.querySelector('#output').innerHTML = svg;
      const element = document.querySelector('#output svg');
      const view = element.viewBox.baseVal;
      element.setAttribute('width', Math.ceil(view.width)); element.setAttribute('height', Math.ceil(view.height));
      return { svg: new XMLSerializer().serializeToString(element), width: view.width, height: view.height };
    }, { source, name });
    await fs.writeFile(path.join(CONFIG.outputDir, name + '.svg'), result.svg);
    await page.locator('#output').screenshot({ path: path.join(CONFIG.outputDir, name + '.png') });
    console.log(`${name}: ${Math.ceil(result.width)} × ${Math.ceil(result.height)}`);
  }
} finally { await browser.close(); }
