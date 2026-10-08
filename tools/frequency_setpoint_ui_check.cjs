// Offline browser regression: intercept every request, never contact the stand.
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

async function main() {
  const root = path.resolve(__dirname, '..');
  const out = path.join(root, 'output/playwright/frequency_setpoint_20261007');
  fs.mkdirSync(out, {recursive:true});
  const base = JSON.parse(fs.readFileSync(path.join(root,
    'artifacts/current_pwm_20261007/full_debug_r1/matrix_live/report.json'), 'utf8')).before;
  const script = fs.readFileSync(path.join(root, 'web_hmi/static/app.js'), 'utf8');
  const browser = await chromium.launch({channel:'chrome', headless:true});
  const results = [];
  try {
    for (const viewport of [{width:1440,height:900},{width:390,height:844}]) {
      for (const test of [{cmd:5,ref:0,expect:'5.0'}, {cmd:20,ref:0,expect:'20.0'},
                         {cmd:0,ref:20,expect:'0.0'}, {cmd:undefined,ref:7,expect:'7.0'}]) {
        const context = await browser.newContext({viewport});
        const page = await context.newPage();
        const errors = [];
        page.on('pageerror',e=>errors.push(e.message));
        const data = {...base, freq:test.ref, freq_cmd:test.cmd};
        await page.route('**/*',async route=>{
          const req=route.request(), url=new URL(req.url());
          if(req.method()!=='GET') return route.fulfill({status:403,body:'offline commands disabled'});
          if(url.pathname==='/api/status') return route.fulfill({contentType:'application/json',body:JSON.stringify({ok:true,data})});
          const files={'/':'index.html','/app.js':'app.js','/style.css':'style.css'};
          const file=files[url.pathname];
          if(!file) return route.fulfill({status:404,body:'offline'});
          const types={'.html':'text/html','.js':'application/javascript','.css':'text/css'};
          return route.fulfill({contentType:types[path.extname(file)],body:file==='app.js'?script:fs.readFileSync(path.join(root,'web_hmi/static',file))});
        });
        await page.goto('http://frequency-ui.test/');
        try {
          await page.waitForFunction(v=>Number(document.querySelector('#freqSlider').value)===Number(v),test.expect,{timeout:5000});
        } catch(error) {
          throw new Error(JSON.stringify({test,errors,dom:await page.evaluate(()=>({value:document.querySelector('#freqSlider')?.value,
            label:document.querySelector('.freq-block .label')?.textContent,body:document.body.innerText.slice(-400)}))}));
        }
        await page.locator('#freqSlider').hover();
        const tooltip=await page.locator('#freqReadout').textContent();
        if(tooltip!==`${test.expect} Гц`) throw new Error(`stale tooltip: ${tooltip}`);
        const label=await page.locator('.freq-block .label').textContent();
        if(label!==`Задание частоты: ${test.expect} Гц`) throw new Error(`wrong label: ${label}`);
        await page.evaluate(()=>{document.querySelector('#freqSlider').dispatchEvent(new Event('pointerdown'));setFrequencyFromStatus({freq_cmd:30,freq:0});});
        if(Number(await page.locator('#freqSlider').inputValue())!==Number(test.expect)) throw new Error('status overwrote drag');
        await page.evaluate(()=>document.querySelector('#freqSlider').dispatchEvent(new Event('pointerup')));
        await page.evaluate(()=>setFrequencyFromStatus({freq_cmd:NaN,freq:0}));
        if(Number(await page.locator('#freqSlider').inputValue())!==Number(test.expect)) throw new Error('NaN overwrote value');
        const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth);
        if(errors.length || overflow) throw new Error(JSON.stringify({errors,overflow}));
        if(test.cmd===20) await page.screenshot({path:path.join(out,`setpoint_20_${viewport.width}.png`),fullPage:true});
        results.push({viewport,...test,tooltip,pass:true});
        await context.close();
      }
    }
  } finally {await browser.close();}
  fs.writeFileSync(path.join(out,'report.json'),JSON.stringify({pass:true,scope:'offline browser; no stand commands',results},null,2));
  console.log(JSON.stringify({pass:true,scenarios:results.length,out}));
}
main().catch(error=>{console.error(error);process.exitCode=1;});
