// Render the single SVG source at application and Windows icon sizes.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

(async () => {
  const root = path.resolve(__dirname, '..');
  const svg = fs.readFileSync(path.join(root, 'public/icon.svg'), 'utf8');
  const browser = await chromium.launch({ executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe', headless: true });
  try {
    const page = await browser.newPage({ viewport: { width: 1024, height: 1024 }, deviceScaleFactor: 1 });
    await page.setContent(`<style>html,body{margin:0;background:transparent}svg{width:1024px;height:1024px;display:block}</style>${svg}`);
    await page.screenshot({ path: path.join(__dirname, 'workstudio-icon.png'), omitBackground: true });
    await page.setViewportSize({ width: 1200, height: 760 });
    await page.setContent(`<style>
      *{box-sizing:border-box}body{margin:0;background:#eeede6;color:#214D51;font-family:Arial,"Microsoft YaHei",sans-serif}
      main{display:grid;grid-template-columns:1fr 1fr;min-height:760px}
      .hero{display:flex;flex-direction:column;justify-content:center;padding:80px}.hero svg{width:250px;height:250px}
      h1{font-size:44px;letter-spacing:-1.6px;margin:34px 0 10px;font-weight:650}p{font-size:16px;color:#6b7975;margin:0;letter-spacing:2px}
      .samples{background:#183337;display:flex;flex-direction:column;justify-content:center;padding:72px;color:#ecebdd}
      .caption{font-size:13px;letter-spacing:2px;opacity:.55;margin-bottom:36px}
      .row{display:flex;align-items:center;gap:32px;height:130px;border-bottom:1px solid #ffffff12}
      .sample{display:flex;align-items:center;justify-content:center;width:100px;min-height:100px}.row span{color:#9eafaa;font-size:14px}
      .wordmark{display:flex;align-items:center;gap:16px;font-size:25px;font-weight:650;margin-top:50px}.wordmark svg{height:48px;width:48px}
    </style><main><section class="hero">${svg}<h1>workstudio</h1><p>影音素材 · 一处整理</p></section><section class="samples"><div class="caption">DESIGNED FOR YOUR WORKSPACE</div>${[64,32,16].map(size=>`<div class="row"><div class="sample">${svg.replace('<svg ',`<svg width="${size}" height="${size}" `)}</div><span>${size} × ${size}</span></div>`).join('')}<div class="wordmark">${svg}workstudio</div></section></main>`);
    await page.screenshot({ path: path.join(__dirname, 'workstudio-icon-preview.png') });
  } finally { await browser.close(); }
})();
