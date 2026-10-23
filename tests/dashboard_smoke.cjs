const fs=require('fs'),vm=require('vm'),path=require('path');
const html=fs.readFileSync(path.join(__dirname,'../reports/dashboard.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements={};
for(const id of ['cell','threshold','model','forecastHistory','window','sohModel','validation','cohort','sohChart','info','slider','cycleLabel','play','future','health','flag','rul','note','chart','detail','sensor','ml','metrics'])elements[id]={value:'',checked:false,style:{},textContent:'',innerHTML:'',addEventListener(){},add(option){if(!this.value)this.value=option.value;}};
elements.window.value='60s';elements.sohModel.value='ridge';elements.validation.value='temporal_70_30';elements.cohort.value='common';elements.model.value='recent_30';elements.threshold.value='70';elements.slider.value='60';
let replayTick=null;
const context=vm.createContext({document:{getElementById:id=>elements[id]},Option:function(text,value){return {text,value}},setInterval:fn=>{replayTick=fn;return 1},clearInterval:()=>{},console});
vm.runInContext(script,context);
let count=0;
for(const cell of ['B0005','B0006','B0007','B0018'])for(const model of ['recent_30','all_history','power_law'])for(const threshold of [70,80])for(const cycle of [30,40,60,80,120,132])for(const future of [false,true]){
 elements.model.value=model;elements.cell.value=cell;elements.threshold.value=String(threshold);elements.slider.value=String(cycle);elements.future.checked=future;
 vm.runInContext('render()',context);
 if(!elements.chart.innerHTML.includes('polyline')||/NaN|undefined/.test(elements.chart.innerHTML))throw Error('Invalid chart');
 if(!elements.health.textContent.endsWith('%'))throw Error('Invalid health');
 count++;
}
elements.play.onclick();replayTick();elements.play.onclick();
console.log(`Dashboard script checks passed: ${count} cell/threshold/cycle/reveal combinations; replay starts and pauses.`);


let upgraded=0;
for(const cell of ['B0005','B0006','B0007','B0018'])for(const window of ['60s','5min','15min','30min','full','reference'])for(const model of ['ridge','random_forest','mean','all'])for(const validation of ['temporal_70_30','unseen'])for(const history of [false,true]){
 elements.cell.value=cell;elements.window.value=window;elements.sohModel.value=model;elements.validation.value=validation;elements.forecastHistory.checked=history;elements.slider.value='120';
 vm.runInContext('render()',context);
 if(/NaN|undefined/.test(elements.sohChart.innerHTML)||!elements.info.textContent.includes(cell))throw Error('Invalid SOH plot/panel');
 if(!elements.info.textContent.includes('cycle 120'))throw Error('Missing cycle');
 upgraded++;
}
console.log('Upgraded SOH/RUL checks passed: '+upgraded+' combinations.');
// Retained prediction history must never show points after the slider cutoff.
elements.cell.value='B0005';elements.window.value='15min';elements.sohModel.value='all';elements.validation.value='unseen';elements.cohort.value='common';
let priorCount=0;
for(const cycle of [60,80,120]){
 elements.slider.value=String(cycle);vm.runInContext('render()',context);
 const points=[...elements.sohChart.innerHTML.matchAll(/<circle cx="([^"]+)"/g)].map(m=>Number(m[1]));
 if(points.some(x=>x>65+cycle/168*905+1e-6))throw Error('Future prediction displayed');
 if(points.length<priorCount)throw Error('Previous predictions lost');priorCount=points.length;
}
elements.forecastHistory.checked=true;vm.runInContext('render()',context);
if(!elements.chart.innerHTML.includes('opacity="0.18"'))throw Error('Forecast history missing');
elements.forecastHistory.checked=false;vm.runInContext('render()',context);
if(elements.chart.innerHTML.includes('opacity="0.18"'))throw Error('Forecast history not hidden');
console.log('Prediction prefix retention and forecast-history toggle checks passed.');
