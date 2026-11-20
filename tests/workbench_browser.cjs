const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {readFileSync} = require('node:fs');
const {performance} = require('node:perf_hooks');

(async () => {
 const url = new URL(process.argv[2] || 'http://127.0.0.1:8765/');
 assert.equal(url.hostname, '127.0.0.1', 'Use the workbench loopback server');
 const browser = await chromium.launch({
  executablePath:process.env.CHROMIUM_PATH,
  args:['--disable-background-networking'],
 });
 try {
  const context = await browser.newContext({viewport:{width:1440,height:930}});
  await context.route('**/*', route => new URL(route.request().url()).origin === url.origin
   ? route.continue() : route.abort());
  const page = await context.newPage();
  const cdp = await browser.newBrowserCDPSession();
  async function resources() {
    const {processInfo} = await cdp.send('SystemInfo.getProcessInfo');
    const pss=processInfo.reduce((sum,p)=>{
      try {return sum+Number(readFileSync('/proc/'+p.id+'/smaps_rollup','utf8').match(/^Pss:\s+(\d+)/m)[1]);}
      catch {return sum;}
    },0);
    return [pss/1024,processInfo.reduce((sum,p)=>sum+p.cpuTime,0)];
  }
  const blank=(await resources())[0];
  const errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  const startup=[];
  for(let i=0;i<5;i++){
   const start=performance.now();
   await page.goto(url.href);
   await page.locator('#hybrid-chart svg').waitFor();
   startup.push(Math.round(performance.now()-start));
  }
  const first=await resources();
  await page.waitForTimeout(2500);
  const idle=await resources();
  console.log('Startup wall ms',startup,'Browser aggregate idle PSS MiB',idle[0].toFixed(1),'Blank PSS MiB',blank.toFixed(1),'CPU-s during 2.5s idle',(idle[1]-first[1]).toFixed(3));

  if(process.env.WORKBENCH_SCREENSHOT) await page.screenshot({path:process.env.WORKBENCH_SCREENSHOT});
  const check = (id,text) => page.locator(id).textContent().then(x=>assert.match(x,text));
  await check('#update-note',/Capacity changes at 180 s/);
  await page.locator('#hybrid').getByRole('button',{name:'Step',exact:true}).click();
  await check('#hybrid output',/181 s/);
  await page.locator('#hybrid').getByRole('button',{name:'Play',exact:true}).click();
  await page.waitForTimeout(260);
  await page.locator('#hybrid').getByRole('button',{name:'Pause'}).click();
  assert.ok(parseInt(await page.locator('#hybrid output').textContent())>181);
  await page.locator('#hybrid').getByRole('button',{name:'Reset'}).click();
  await check('#hybrid output',/0 s/);
  await check('#update-note',/Assuming nominal/);
  await page.locator('#hybrid').getByLabel('Scenario',{exact:true}).selectOption('4');
  await check('#oracle-note',/unavailable/);
  await page.getByRole('button',{name:'Kalman filter',exact:true}).click();
  await page.locator('#ekf').getByLabel('Initial SOC',{exact:true}).selectOption('2');
  await check('#ekf-readouts',/90.00%/);
  await page.locator('#ekf').getByRole('button',{name:'Play',exact:true}).click();
  await page.getByRole('button',{name:'Battery physics',exact:true}).click();
  await check('#ekf .primary',/^Play$/);
  await page.getByLabel('Model',{exact:true}).selectOption('2');
  await page.getByLabel('Capacitance scale').selectOption('2');
  await check('#physics-readouts',/τ2/);
  await page.getByRole('button',{name:'Machine learning',exact:true}).click();
  await page.getByLabel('Estimator',{exact:true}).selectOption('2');
  assert.equal(await page.locator('#surface svg polyline').count(),20);
  await page.locator('#lesson-input').fill('30');
  await check('#worked-result',/Stage 3 of 3/);
  await page.getByRole('button',{name:'Dataset explorer',exact:true}).click();
  await check('#synthetic-chart',/Simulated reference SOC/);
  await page.getByLabel('Dataset',{exact:true}).selectOption('1');
  if(await page.getByLabel('Cell',{exact:true}).count() > 0){
   await check('#nasa-chart',/B0005.*discharge 1/);
   await page.getByLabel('Cell',{exact:true}).selectOption('1');
   await page.getByLabel('Discharge cycle').selectOption({index:7});
   await check('#nasa-chart',/B0006.*discharge 8/);
   await page.locator('#nasa-playback').getByRole('button',{name:'Step',exact:true}).click();
   assert.ok(parseInt(await page.locator('#nasa-playback output').textContent())>0);
  } else {
   await check('#nasa-chart',/No local recording/);
  }
  await page.getByRole('button',{name:'Battery fundamentals',exact:true}).click();
  await page.getByRole('button',{name:'Separator',exact:true}).click();
  await check('#layer-title',/^Separator$/);
  const renders=await page.evaluate(()=>{
    const nav=document.querySelector('[data-view="hybrid"]');
    nav.click();
    const slider=document.querySelector('#hybrid input');
    return Array.from({length:50},(_,i)=>{
      slider.value=String(i*14);
      const started=performance.now();
      slider.dispatchEvent(new Event('input'));
      return performance.now()-started;
    }).sort((a,b)=>a-b);
  });
  console.log('50 synchronous playback renders median/p95/max ms',renders[25],renders[47],renders[49]);
  assert.deepEqual(errors,[]);
  console.log('Browser smoke passed offline through all six sections.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
