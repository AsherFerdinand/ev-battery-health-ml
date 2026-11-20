const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const root = path.resolve(__dirname, '..');
const file = process.argv[2] ?? path.join(root, 'reports', 'workbench.html');
const html = fs.readFileSync(file, 'utf8');
const payload = html.match(/<script id="workbench-data"[^>]*>([^<]+)<\/script>/);
assert.ok(payload, 'Missing precomputed data');
const data = JSON.parse(zlib.gunzipSync(Buffer.from(payload[1], 'base64')));
const inlineScript = html.match(/<script>([\s\S]+)<\/script>/);
assert.ok(inlineScript);
new (require('node:vm').Script)(inlineScript[1]);
assert.ok(!/https?:\/\/.+\.js/.test(html), 'Offline application requires no remote scripts');

let traces = 0;
for (const scenario of data.scenarios) {
  const index = scenario.time.indexOf(data.window_s);
  for (const trial of Object.values(scenario.trials)) {
    const d = trial.diagnostics;
    const hybrid = trial.soc['Hybrid A'];
    assert.deepEqual(hybrid.slice(0, index+1), trial.soc['Fixed EKF'].slice(0, index+1));
    assert.equal(d.capacity_c[index-1], 7200);
    assert.ok(d.capacity_c[index] >= 3960 && d.capacity_c[index] <= 7200);
    assert.ok(d.capacity_c.slice(index).every(capacity => capacity === d.capacity_c[index]));
    assert.equal('Oracle EKF' in trial.soc, scenario.plant === 'thevenin');
    const mae = hybrid.reduce((sum, value, k) => {
      assert.equal(value, d.corrected_state[k][0]);
      assert.ok(Math.abs(scenario.voltage[k] - d.predicted_voltage_v[k] - d.innovation_v[k]) < 1e-12);
      return sum + 100*Math.abs(value - scenario.truth[k]);
    }, 0) / hybrid.length;
    assert.ok(Math.abs(mae - trial.metrics['Hybrid A'].mae_pp) < 1e-12);
    traces++;
  }
}
assert.equal(traces, 15);
assert.equal(Object.keys(data.physics).length, 63);
console.log('Workbench export checks passed for 15 trace sets and 63 circuit examples.');
