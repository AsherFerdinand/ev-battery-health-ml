const assert = require('node:assert/strict');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const {readFileSync,mkdirSync} = require('node:fs');
const {join} = require('node:path');
const {performance} = require('node:perf_hooks');
const {gunzipSync} = require('node:zlib');

(async () => {
 const url = new URL(process.argv[2] || 'http://127.0.0.1:8765/');
 assert.equal(url.hostname, '127.0.0.1', 'Use the workbench loopback server');
 const browser = await chromium.launch({
  executablePath:process.env.CHROMIUM_PATH,
  args:['--disable-background-networking'],
 });
 try {
  const context = await browser.newContext({viewport:{width:1440,height:930}});
  const externalRequests=[];
  await context.route('**/*', route=>{
   if(new URL(route.request().url()).origin===url.origin)return route.continue();
   externalRequests.push(route.request().url());return route.abort();
  });
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
  page.on('pageerror',error=>errors.push(error.stack||error.message));
  page.on('console',message=>{if(message.type()==='error')errors.push(message.text());});
  const startup=[];
  for(let i=0;i<5;i++){
   const start=performance.now();
   await page.goto(url.href);
   await page.locator('#explorer-scenario-title').waitFor();
   startup.push(Math.round(performance.now()-start));
  }
  await page.waitForFunction(()=>document.querySelector('#explorer-status').textContent.startsWith('Python-generated'));
  const first=await resources();
  await page.waitForTimeout(2500);
  const idle=await resources();
  console.log('Startup wall ms',startup,'Browser aggregate idle PSS MiB',idle[0].toFixed(1),'Blank PSS MiB',blank.toFixed(1),'CPU-s during 2.5s idle',(idle[1]-first[1]).toFixed(3));

  if(process.env.WORKBENCH_SCREENSHOT) await page.screenshot({path:process.env.WORKBENCH_SCREENSHOT});
  const check = (id,text) => page.locator(id).textContent().then(x=>assert.match(x,text));
  const checkPage = (target,id,text) => target.locator(id).textContent().then(x=>assert.match(x,text));
  for (const [name,id] of [['Battery Explorer','#fundamentals'],['Battery Physics','#physics'],['Dataset Explorer','#data'],['Machine Learning','#ml'],['SOC Estimation','#ekf'],['Investigation Lab','#hybrid'],['Reports','#reports']]) {
   await page.locator('[data-view=\"'+id.slice(1)+'\"]').click();
   assert.equal(await page.locator(id).isVisible(),true,name+' destination should open');
   assert.equal(await page.locator('.view[hidden] .plot').count(),0,'Inactive views should release rendered plots');
   if(process.env.WORKBENCH_SCREENSHOT_DIR&&['fundamentals','physics','data'].includes(id.slice(1))){
    mkdirSync(process.env.WORKBENCH_SCREENSHOT_DIR,{recursive:true});
    const name={fundamentals:'battery-explorer',physics:'physics-lab',data:'nasa-dataset'}[id.slice(1)];
    await page.screenshot({path:join(process.env.WORKBENCH_SCREENSHOT_DIR,name+'.png'),fullPage:true});
   }
  }
  await page.locator('[data-view="reports"]').click();
  await check('#report-results',/Final · thevenin/i);
  assert.equal(await page.locator('#reports a[href^="../docs/"]').count(),2);
  const reportResponse=await context.request.get(new URL('../docs/robust-hybrid-v2.md',url).href);
  assert.equal(reportResponse.status(),200);
  assert.match(reportResponse.headers()['content-type'],/text\/markdown/);
  await check('#report-capacity',/Final thevenin/);
  assert.equal(await page.locator('[data-view="hybrid"]').textContent(),'Investigation Lab');
  await page.locator('[data-view="hybrid"]').click();
  await check('#hybrid',/Evaluate estimator reliability/);
  await check('#hybrid',/It rejected every adaptation on both independent final cohorts/);
  await check('#hybrid',/not a validated selective reliability detector/);
  await page.locator('[data-view="ekf"]').click();
  await check('#ekf',/Coulomb Counting/);
  await check('#ekf',/Fixed EKF/);
  await check('#ekf',/Hybrid A \/ B/);
  await check('#ekf',/Safeguarded Hybrid B/);
  await page.locator('[data-view="fundamentals"]').click();
  await page.getByRole('button',{name:'Switch color theme'}).click();
  assert.equal(await page.locator('html').getAttribute('data-theme'),'dark');
  await page.getByRole('button',{name:'Switch color theme'}).click();
  await page.locator('[data-view="hybrid"]').click();
  const hasAdaptive = await page.locator('#adaptive-panel').isVisible();
  if (process.env.REQUIRE_HYBRID_B) assert.ok(hasAdaptive, 'Hybrid B payload required');
  const seek = (view, sample) => page.locator('#'+view+' input[aria-label="Playback position"]').fill(String(sample));
  const hasRobust=await page.locator('#robust-validation').isVisible();
  if (process.env.REQUIRE_ROBUST) assert.ok(hasRobust, 'Robust validation payload required');
  let payload, robustIndex;
  if(hasAdaptive||hasRobust){
   const exportedHtml=await (await context.request.get(url.href)).text();
   assert.equal((exportedHtml.match(/\bsetInterval\(/g)||[]).length,1,'All workbench playback sources share one interval timer');
   assert.doesNotMatch(exportedHtml,/explorerTimer|simState\.timer/,'No isolated Explorer or Simulation Lab playback timer remains');
   const encoded=exportedHtml.match(/id="workbench-data"[^>]*>([^<]+)/)[1];
   payload=JSON.parse(gunzipSync(Buffer.from(encoded,'base64')));
  }
  if(hasRobust){
   await check('#robust-capacity',/MAE.*Clipped/);
   const cohorts=page.locator('#robust-cohorts details');
   assert.equal(await cohorts.count(),payload.robust.cohorts.length);
   await cohorts.first().locator('summary').click();
   await check('#robust-cohorts',/Rejection rate/);
   let found=0;
   for(let i=0;i<payload.scenarios.length;i++){
    const scenario=payload.scenarios[i], run=Object.values(scenario.trials)[0];
    if(!run.robust?.decision)continue;
    found++;
    robustIndex ??= i;
    const decision=run.robust.decision;
    const window=decision.window_s??payload.robust.window_s??run.adaptive?.window_s??payload.hybrid_b.window_s;
    const index=scenario.time.indexOf(window);
    assert.ok(index>0);
    await page.locator('#hybrid').getByLabel('Scenario',{exact:true}).selectOption({index:i});
    await seek('hybrid',index-1);
    await check('#robust-status',/Collecting causal observations/);
    assert.equal(await page.locator('#robust-reasons').isVisible(),false);
    await seek('hybrid',index);
    await check('#robust-status',decision.accepted?/Accepted at/:/Rejected at/);
    await check('#hybrid-chart',/Safeguarded Hybrid B/);
    await check('#adaptive-voltage',/Safeguarded Hybrid B/);
    const capacity=(decision.applied_capacity_c/3600).toFixed(3)+' Ah';
    assert.equal(await page.locator('#robust-parameters tbody tr').first().locator('td').last().textContent(),capacity);
   }
   assert.ok(found>0,'At least one robustness playback is required');
   await page.locator('#hybrid').getByLabel('Scenario',{exact:true}).selectOption({index:0});
   const initialWindow=payload.hybrid_b.window_s;
   await seek('hybrid',payload.scenarios[0].time.indexOf(initialWindow));
  }
  if(hasAdaptive){
   const scenario=payload.scenarios[0], run=Object.values(scenario.trials)[0];
   const timing = await page.locator('#adaptive-timing').textContent();
   const cutoff = Number(timing.match(/Window closes at (\d+) s/)[1]);
   const index = scenario.time.indexOf(cutoff);
   assert.ok(cutoff >= 180 && index > 0);
   await check('#adaptive-parameters',/Fixed.*Hybrid B.*Reference/);
   await seek('hybrid',index-1);
   await check('#adaptive-timing',/Collecting measured features/);
   await page.locator('#hybrid').getByRole('button',{name:'Step',exact:true}).click();
   await check('#adaptive-timing',/first affect prediction on the following interval/);
   assert.equal(await page.locator('#adaptive-voltage svg polyline').count(),run.robust?4:3);
   const printed=payload.hybrid_b.parameters.map(({key,unit})=>
    run.adaptive.parameters[key].estimated.toFixed(unit==='Ω'?5:2)+' '+unit);
   const values=await page.locator('#adaptive-parameters tbody tr td:nth-child(3)').allTextContents();
   assert.deepEqual(values,printed,'Parameter display must match the exported update exactly');
   const times=payload.scenarios[0].time, researchSamples=[0,Math.floor((times.length-1)/2),times.length-1],researchCursor=[];
   for(const sample of researchSamples){
    await seek('hybrid',sample);
    await check('#hybrid-chart .chart-sample',new RegExp('^'+Number(times[sample]).toFixed(1)+' s'));
    researchCursor.push(Number(await page.locator('#hybrid-chart [data-time-cursor]').getAttribute('x1')));
   }
   assert.ok(researchCursor[0]<researchCursor[1]&&researchCursor[1]<researchCursor[2],'Research plot cursor follows start, middle, and end selections');
  }
  await seek('hybrid',180);
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
  await page.getByRole('button',{name:'SOC Estimation',exact:true}).click();
  await page.locator('#ekf').getByLabel('Initial SOC',{exact:true}).selectOption('2');
  await check('#ekf-readouts',/90.00%/);
  if(hasAdaptive){
   await page.getByLabel('Filter trace',{exact:true}).selectOption('1');
   await check('#ekf-equations',/Innovation.*SOC⁺.*σ/);
  }
  const equation=await page.locator('#ekf-equations').textContent();
  await page.locator('#ekf').getByRole('button',{name:'Step',exact:true}).click();
  assert.notEqual(await page.locator('#ekf-equations').textContent(),equation);
  await page.locator('#ekf').getByRole('button',{name:'Play',exact:true}).click();
  await page.getByRole('button',{name:'Battery Physics',exact:true}).click();
  await check('#ekf .primary',/^Play$/);
  await check('#sim-circuit-description',/one parallel R₁\/C₁ polarisation branch/);
  const r0point=await page.locator('#sim-circuit [data-focus="sim-r0"] .part').evaluate(path=>{
   const svg=path.ownerSVGElement,p=svg.createSVGPoint(),local=path.getPointAtLength(path.getTotalLength()*.1);
   p.x=local.x;p.y=local.y;const screen=p.matrixTransform(svg.getScreenCTM());return{x:screen.x,y:screen.y};
  });
  await page.mouse.click(r0point.x,r0point.y);
  assert.equal(await page.evaluate(()=>document.activeElement.id),'sim-r0');
  const c1=page.locator('#sim-circuit [data-focus="sim-c1"]');
  await c1.focus();await c1.press('Enter');
  assert.equal(await page.evaluate(()=>document.activeElement.id),'sim-c1');
  await page.locator('#sim-model').selectOption('rint');
  await check('#sim-circuit-description',/Rint has an OCV source/);
  assert.equal(await page.locator('#sim-circuit [data-focus="sim-r1"]').count(),0);
  await page.locator('#sim-model').selectOption('dual');
  await check('#sim-circuit-description',/fast and slow RC branches/);
  assert.ok(await page.locator('#sim-circuit [data-focus="sim-r2"]').count());
  await page.locator('#sim-model').selectOption('thevenin');
  await page.locator('#circuit-explorer > summary').click();
  await page.locator('#physics-model-explanation [data-model="0"]').click();
  await check('#physics-model-description',/simplest circuit.*immediate voltage change/);
  await page.locator('#physics-model-explanation [data-model="1"]').click();
  await check('#physics-model-description',/one resistor-capacitor branch/);
  await page.locator('#physics-model-explanation [data-model="2"]').click();
  await check('#physics-model-description',/second RC branch/);
  await page.locator('#physics-model-explanation [data-model="1"]').click();
  const physicsCursor=[];
  for(const sample of [0,60,120]){
   await page.locator('#physics-playback input[aria-label="Playback position"]').fill(String(sample));
   await check('#physics-chart .chart-sample',new RegExp('^'+sample+'\\.0 s'));
   physicsCursor.push(Number(await page.locator('#physics-chart [data-time-cursor]').getAttribute('x1')));
  }
  assert.ok(physicsCursor[0]<physicsCursor[1]&&physicsCursor[1]<physicsCursor[2],'ECM comparison uses a shared response playback clock');
  await page.locator('#physics-response-mode').selectOption('1');
  assert.equal(await page.locator('#physics-chart polyline').count(),3,'Voltage-deviation mode compares all three ECM outputs');
  await page.locator('#physics-response-mode').selectOption('0');
  await page.locator('#sim-duration').fill('60');
  await page.locator('#sim-profile').selectOption('constant_discharge');
  await page.locator('#sim-current').fill('1');
  await page.getByRole('button',{name:'Run simulation'}).click();
  await page.waitForFunction(()=>document.querySelector('#sim-status').textContent.startsWith('Simulation complete'));
  await check('#sim-status',/Simulation complete.*61 exact/);
  assert.ok(await page.locator('#sim-voltage-chart svg').count());
  assert.equal(await page.locator('#sim-voltage-chart polyline').count(),1,'Simulation chart retains the complete trajectory');
  await check('#sim-inspector',/Thevenin.*terminal energy out/i);
  const simulationCursor=[];
  for(const sample of [0,30,60]){
   await page.locator('#sim-seek').fill(String(sample));
   await check('#sim-clock',new RegExp('^'+sample+' s$'));
   await check('#sim-voltage-chart .chart-sample',new RegExp('^'+sample+'\\.0 s'));
   simulationCursor.push(Number(await page.locator('#sim-voltage-chart [data-time-cursor]').getAttribute('x1')));
  }
  assert.ok(simulationCursor[0]<simulationCursor[1]&&simulationCursor[1]<simulationCursor[2], 'Simulation chart cursor follows start, middle, and end selections');
  await page.locator('#sim-results details summary').click();
  await page.waitForFunction(()=>document.querySelector('#sim-polarisation-chart').textContent.includes('RC branch 1'));
  await check('#sim-polarisation-chart',/RC branch 1/);
  await page.getByRole('button',{name:'Save as baseline'}).click();
  await page.locator('#sim-r0').fill('65');
  await page.getByRole('button',{name:'Run simulation'}).click();
  await page.waitForFunction(()=>document.querySelector('#sim-status').textContent.startsWith('Simulation complete'));
  await check('#sim-status',/Simulation complete/);
  await page.getByRole('button',{name:'Compare',exact:true}).click();
  assert.equal(await page.locator('#sim-comparison').isVisible(),true);
  await check('#sim-difference-metrics',/Mean absolute voltage difference.*Ohmic heat difference/);
  assert.equal(await page.locator('#sim-compare-voltage svg polyline').count(),2);
  await page.locator('#sim-speed').selectOption('2');
  await page.locator('#sim-restart').click();
  await page.locator('#sim-play').click();
  await page.waitForTimeout(260);
  await page.locator('#sim-pause').click();
  assert.ok(Number(await page.locator('#sim-seek').inputValue())>0);
  await page.locator('#sim-restart').click();
  assert.equal(await page.locator('#sim-clock').textContent(),'0 s');
  const jsonDownload=page.waitForEvent('download');
  await page.locator('#sim-export-json').click();
  assert.match((await jsonDownload).suggestedFilename(),/\.json$/);
  const csvDownload=page.waitForEvent('download');
  await page.locator('#sim-export-csv').click();
  assert.match((await csvDownload).suggestedFilename(),/\.csv$/);
  await page.locator('#sim-model').selectOption('rint');
  assert.equal(await page.locator('#sim-r1-field').isVisible(),false);
  await page.getByRole('button',{name:'Run simulation'}).click();
  await page.waitForFunction(()=>document.querySelector('#sim-status').textContent.startsWith('Simulation complete'));
  await check('#sim-status',/Simulation complete/);
  await page.locator('#sim-model').selectOption('dual');
  assert.equal(await page.locator('#sim-r2-field').isVisible(),true);
  await page.locator('#sim-reset').click();
  await check('#sim-empty',/Choose a configuration/);
  await page.locator('#sim-duration').fill('20');
  await page.getByRole('button',{name:'Run simulation'}).click();
  assert.equal(await page.locator('#sim-duration').evaluate(input=>input.validity.valid),false);
  await page.locator('#sim-duration').fill('60');
  await page.getByRole('button',{name:'Battery Physics',exact:true}).click();
  if(!await page.locator('#circuit-explorer').evaluate(details=>details.open)) await page.locator('#circuit-explorer > summary').click();
  await page.getByLabel('Model',{exact:true}).selectOption('2');
  await page.getByLabel('Capacitance scale').selectOption('2');
  await check('#physics-readouts',/τ2/);
  await page.getByRole('button',{name:'Machine Learning',exact:true}).click();
  await check('#surface',/X axis.*Voltage change \(V\).*Y axis.*Mean temperature \(K\).*Z axis.*SOH/);
  await check('#ml',/SOH percentage points.*Lower values are generally better/);
  if(await page.locator('#trained-detail').isVisible()){
   await check('#trained-material',/standardised features/);
   await page.getByLabel('Estimator',{exact:true}).selectOption('1');
   await check('#trained-material',/Tree 1.*leaf/);
  }
  await page.getByLabel('Estimator',{exact:true}).selectOption('2');
  if(await page.locator('#trained-detail').isVisible()) await check('#trained-material',/fitted tree contribution/);
  assert.equal(await page.locator('#surface svg polyline').count(),20);
  await page.locator('#lesson-input').fill('30');
  await check('#worked-result',/Stage 3 of 3/);
  await page.getByRole('button',{name:'Dataset Explorer',exact:true}).click();
  await check('#nasa-intro',/NASA battery ageing/);
  await check('#nasa-data',/Phase annotations are inferred.*current sign/);
  await page.getByLabel('Dataset',{exact:true}).selectOption('0');
  await check('#synthetic-chart',/Simulated reference SOC/);
  await page.getByLabel('Dataset',{exact:true}).selectOption('1');
  if(await page.getByLabel('Cell',{exact:true}).count() > 0){
   await check('#nasa-chart',/B0005.*discharge 1/);
   await page.getByLabel('Cell',{exact:true}).selectOption('1');
   await page.getByLabel('Discharge cycle').selectOption({index:7});
   await check('#nasa-chart',/B0006.*discharge 8/);
   const nasaCursor=[];
   for(const sample of [0,20,39]){
    await page.locator('#nasa-playback input[aria-label="Playback position"]').fill(String(sample));
    const expectedTime=payload?.nasa?.B0006?.[7]?.trace?.[sample]?.[0];
    if(Number.isFinite(expectedTime)) await check('#nv .chart-sample',new RegExp('^'+Number(expectedTime).toFixed(1)+' s'));
    else await check('#nv .chart-sample',/ s · Measured voltage/);
    nasaCursor.push(Number(await page.locator('#nv [data-time-cursor]').getAttribute('x1')));
   }
   assert.ok(nasaCursor[0]<nasaCursor[1]&&nasaCursor[1]<nasaCursor[2], 'NASA plots follow the selected irregular timestamp');
   await page.locator('#nasa-playback input[aria-label="Playback position"]').fill('25');
   if(process.env.WORKBENCH_SCREENSHOT_DIR) await page.screenshot({path:join(process.env.WORKBENCH_SCREENSHOT_DIR,'nasa-dataset.png'),fullPage:true});
   await page.locator('#nasa-playback').getByRole('button',{name:'Step',exact:true}).click();
   assert.ok(parseInt(await page.locator('#nasa-playback output').textContent())>0);
  } else {
   await check('#nasa-chart',/No local recording/);
  }
  await page.getByRole('button',{name:'Battery Explorer',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('#explorer-status').textContent.startsWith('Python-generated'));
  await check('#explorer-readouts',/Modelled SOC.*Modelled terminal voltage/);
  await check('#explorer-readouts',/Initial SOC reference.*Change since start/);
  const initialFill=Number(await page.locator('#explorer-soc-fill').getAttribute('height'));
  await page.locator('#explorer-scenario-controls').getByRole('button',{name:'Heavy device usage'}).click();
  await page.waitForFunction(()=>document.querySelector('#explorer-status').textContent.startsWith('Python-generated'));
  await check('#explorer-readouts',/2\.80 A/);
  await page.locator('#explorer-seek').fill('20');
  await page.locator('#explorer-play').click();
  await page.waitForFunction(()=>document.querySelector('#explorer-current-flow').dataset.moving==='true');
  await page.locator('#explorer-pause').click();
  assert.equal(await page.locator('#explorer-current-flow').getAttribute('data-moving'),'false','Pause freezes the circuit animation');
  await page.locator('#explorer-seek').fill('20');
  await check('#explorer-voltage-chart .chart-sample',/^20\.0 s/);
  const explorerCursor=[];
  for(const sample of [0,20,40]){
   await page.locator('#explorer-seek').fill(String(sample));
   await check('#explorer-voltage-chart .chart-sample',new RegExp('^'+sample+'\\.0 s'));
   explorerCursor.push(Number(await page.locator('#explorer-voltage-chart [data-time-cursor]').getAttribute('x1')));
  }
  assert.ok(explorerCursor[0]<explorerCursor[1]&&explorerCursor[1]<explorerCursor[2], 'Explorer charts follow start, middle, and end selections');
  await page.locator('#explorer-seek').fill('20');
  await page.locator('#explorer-voltage-chart .chart-toggle').click();
  assert.equal(await page.locator('#explorer-voltage-chart').getAttribute('class'),'chart-expanded');
  await page.locator('#explorer-voltage-chart .chart-toggle').click();
  assert.ok(Number(await page.locator('#explorer-soc-fill').getAttribute('height'))<initialFill,'Discharge animation follows decreasing SOC');
  await check('#explorer-temperature-note',/warming/);
  await page.locator('#explorer-restart').click();
  await check('#explorer-time',/^0 s$/);
  await page.locator('#explorer-scenario-controls').getByRole('button',{name:'Cold outdoor use'}).click();
  await page.waitForFunction(()=>document.querySelector('#explorer-status').textContent.startsWith('Python-generated'));
  await check('#explorer-temperature-note',/ambient -5\.0 °C/);
  await page.locator('#explorer-scenario-controls').getByRole('button',{name:'Aged battery example'}).click();
  await page.waitForFunction(()=>document.querySelector('#explorer-status').textContent.startsWith('Python-generated'));
  await check('#explorer-readouts',/Modelled usable capacity.*1\.60 Ah.*Configured SOH.*80\.00%/);
  await page.getByRole('button',{name:'Separator',exact:true}).click();
  await check('#layer-title',/^Separator$/);
  await check('#layer-materials',/polyolefin/);
  const collector=page.locator('.cell-part[data-layer="4"]');
  await collector.focus();await collector.press('Enter');
  await check('#layer-title',/^Current collectors$/);
  await page.getByLabel('Charge direction',{exact:true}).selectOption('2');
  await check('#ion-note',/Charge:.*cathode toward anode/);
  await page.emulateMedia({reducedMotion:'reduce'});
  const ionDuration=await page.locator('.ion-flow').evaluate(el=>getComputedStyle(el).animationDuration);
  const ionSeconds=parseFloat(ionDuration)/(ionDuration.endsWith('ms')?1000:1);
  assert.ok(ionSeconds<=0.0001,'Reduced motion disables ion animation');
  await page.emulateMedia({reducedMotion:'no-preference'});
  await page.getByLabel('Charge direction',{exact:true}).selectOption('1');
  await check('#ion-note',/anode to cathode/);
  await page.getByLabel('Charge direction',{exact:true}).selectOption('2');
  await check('#ion-note',/cathode toward anode/);
  await page.locator('#age-soh').fill('60');
  await page.locator('#age-soc').fill('50');
  await page.locator('#age-resistance').fill('75');
  await check('#age-readouts',/1.20 Ah.*0.60 Ah.*150 mV.*300 mW/);
  const casing=page.locator('#age-cell rect[stroke]').nth(0),casingBefore=await casing.getAttribute('height');
  await page.locator('#age-soh').fill('80');await page.locator('#age-soc').fill('50');
  assert.equal(await page.locator('#age-usable-fill').getAttribute('height'),'120');
  assert.equal(await page.locator('#age-charge-fill').getAttribute('height'),'60');
  assert.equal(await casing.getAttribute('height'),casingBefore,'Illustrative casing dimensions remain fixed');
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth),'No mobile overflow');
  await page.setViewportSize({width:1440,height:930});
  await page.locator('[data-view="hybrid"]').click();
  if(robustIndex!==undefined)
   await page.locator('#hybrid').getByLabel('Scenario',{exact:true}).selectOption({index:robustIndex});
  const renders=await page.evaluate(()=>{
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
  assert.deepEqual(externalRequests,[],'Studio operation should make no external network requests');
  const fallback=await browser.newContext();
  await fallback.route('**/*',route=>{
   const requestUrl=new URL(route.request().url());
   requestUrl.origin===url.origin&&requestUrl.pathname!=='/api/simulate'?route.continue():route.abort();
  });
  const filePage=await fallback.newPage();
  const fileErrors=[];filePage.on('pageerror',error=>fileErrors.push(error.message));
  await filePage.goto(url.href);
  await filePage.locator('#explorer-scenario-title').waitFor();
  await filePage.waitForFunction(()=>document.querySelector('#explorer-status').textContent.startsWith('No scenario measurements shown'));
  await filePage.locator('[data-view="physics"]').click();
  await filePage.locator('#sim-duration').fill('60');
  await filePage.getByRole('button',{name:'Run simulation'}).click();
  await filePage.waitForFunction(()=>document.querySelector('#sim-status').textContent.startsWith('Start the studio'));
  await checkPage(filePage,'#sim-status',/Start the studio with python build_workbench\.py/);
  await filePage.locator('[data-view="data"]').click();
  await filePage.getByLabel('Dataset',{exact:true}).selectOption('0');
  await checkPage(filePage,'#synthetic-chart',/Simulated reference SOC/);
  assert.deepEqual(fileErrors,[]);
  await fallback.close();
  console.log('Browser smoke passed offline through all seven studio destinations.');
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
