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

assert.ok(data.robust.cohorts.length >= 2);
let traces = 0;
let robustTraces = 0;
for (const scenario of data.scenarios) {
  const index = scenario.time.indexOf(data.window_s);
  for (const trial of Object.values(scenario.trials)) {
    const d = trial.diagnostics;
    const hybrid = d.corrected_state.map(pair => pair[0]);
    const b = trial.adaptive.diagnostics;
    const kB = scenario.time.indexOf(trial.adaptive.window_s ?? data.hybrid_b.window_s);
    assert.ok(kB > 0);
    if (trial.robust) {
      robustTraces++;
      const guard = trial.robust;
      const guarded = guard.soc ?? trial.soc['Fixed EKF'];
      const pred = guard.predicted_voltage_v ?? trial.adaptive.fixed_voltage_v;
      assert.ok(guard.decision.reasons.length);
      assert.deepEqual(guarded.slice(0, kB+1), trial.soc['Fixed EKF'].slice(0, kB+1));
      assert.deepEqual(pred.slice(0, kB+1), trial.adaptive.fixed_voltage_v.slice(0, kB+1));
      if (!guard.decision.accepted) {
        assert.deepEqual(guarded, trial.soc['Fixed EKF']);
        assert.deepEqual(pred, trial.adaptive.fixed_voltage_v);
      }
      const post = guarded.slice(kB+1).reduce((sum, value, i) =>
        sum + 100*Math.abs(value-scenario.truth[i+kB+1]), 0)/(guarded.length-kB-1);
      assert.ok(Math.abs(post-trial.metrics['Safeguarded Hybrid B'].adaptive_post_mae_pp) < 1e-12);
    } else {
      assert.ok(trial.adaptive.update_applied);
    }
    assert.deepEqual(b.corrected_state.slice(0, kB+1).map(pair => pair[0]),
                     trial.soc['Fixed EKF'].slice(0, kB+1));
    assert.deepEqual(b.predicted_voltage_v.slice(0, kB+1),
                     trial.adaptive.fixed_voltage_v.slice(0, kB+1));
    const parameters = trial.adaptive.parameters;
    assert.equal(b.capacity_c[kB-1], data.nominal_c);
    assert.equal(b.capacity_c[kB], parameters.capacity_c.estimated);
    assert.ok(parameters.r0_ref_ohm.estimated >= .020 && parameters.r0_ref_ohm.estimated <= .080);
    let bPost = 0;
    for (let i=kB+1; i<scenario.time.length; i++){
      assert.ok(Math.abs(scenario.voltage[i] - b.predicted_voltage_v[i] - b.innovation_v[i]) < 1e-12);
      bPost += 100*Math.abs(b.corrected_state[i][0]-scenario.truth[i]);
    }
    assert.ok(Math.abs(bPost/(scenario.time.length-kB-1)-trial.metrics['Hybrid B'].adaptive_post_mae_pp) < 1e-12);
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
assert.equal(traces-robustTraces, 18);
assert.ok(robustTraces >= 2);
assert.equal(Object.keys(data.physics).length, 63);
console.log('Workbench export checks passed for '+traces+' paired trace sets and 63 circuit examples.');
