// Offline rendering only: every request is intercepted; no stand commands.
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const output = path.join(root, 'output/playwright/fault_diagnostics_20261007');
  fs.mkdirSync(output, { recursive: true });
  const base = JSON.parse(fs.readFileSync(path.join(root,
    'artifacts/fault_diagnostics_20261007/live/report.json'), 'utf8')).last;
  const browser = await chromium.launch({ channel:'chrome', headless: true });
  const results = [];
  try {
    for (const viewport of [{width:1440,height:900},{width:390,height:844}]) {
      for (const fault of ['undervoltage','uart_ore']) {
        const context = await browser.newContext({ viewport });
        const data = {...base, mc_diag_valid:1, mc_last_bad_valid:1};
        if (fault === 'uart_ore') Object.assign(data, {mc_bad_cnt:1,bp_bad_cnt:1,
          mc_last_bad_reason:12,mc_last_uart_error_flags:8});
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror', e => errors.push(e.message));
        await page.route('**/*', async route => {
          const request = route.request();
          const url = new URL(request.url());
          if (request.method() !== 'GET') {
            await route.fulfill({status:403,body:'offline preview: commands disabled'}); return;
          }
          if (url.pathname === '/api/status') {
            await route.fulfill({contentType:'application/json',body:JSON.stringify({ok:true,data})}); return;
          }
          const files = {'/':'index.html','/app.js':'app.js','/style.css':'style.css'};
          const file = files[url.pathname];
          if (file) {
            const types = {'.html':'text/html','.js':'application/javascript','.css':'text/css'};
            await route.fulfill({contentType:types[path.extname(file)],
              body:fs.readFileSync(path.join(root,'web_hmi/static',file))}); return;
          }
          await route.fulfill({status:404,body:'offline preview'});
        });
        await page.goto('http://mic-ui.test/');
        const expected = fault === 'uart_ore' ? 'UART RX: ORE' : 'Низкое Vbus';
        await page.waitForFunction(expected => document.body.innerText.includes(expected), expected);
        const overflow = await page.evaluate(() => {
          const e=document.getElementById('sysText');
          return {horizontal:document.documentElement.scrollWidth > innerWidth,
            chip:e ? e.scrollWidth > e.clientWidth+1 : false};
        });
        await page.screenshot({path:path.join(output,`${fault}_${viewport.width}.png`),fullPage:true});
        if (errors.length || overflow.horizontal || overflow.chip) {
          throw new Error(JSON.stringify({fault,viewport,errors,overflow}));
        }
        results.push({fault,viewport,errors,overflow,pass:true});
        await context.close();
      }
    }
  } finally { await browser.close(); }
  fs.writeFileSync(path.join(output,'report.json'),JSON.stringify({pass:true,scope:'offline UI; no network/stand commands',results},null,2));
  process.stdout.write(JSON.stringify({pass:true,screenshots:results.length,output})+'\n');
}
main().catch(e=>{console.error(e);process.exitCode=1;});
