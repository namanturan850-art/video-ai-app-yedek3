const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const source = fs.readFileSync(path.join(__dirname, '../../app/static/settings-http.js'), 'utf8');
const KEY = 'synthetic-frontend-private-key-1234';
const TIMEOUT = 'Gemini API zamanında yanıt vermedi. İnternet bağlantınızı kontrol edip tekrar deneyin.';
function response(body, ok = true) { return {ok, json: async () => body}; }
function namedError(name) { const error = new Error(KEY); error.name = name; return error; }
function harness(fetch, online = true) {
  const timers = [];
  const timeouts = [];
  let now = 0;
  const clock = {
    later(delay, callback) { timers.push({at: now + delay, callback}); },
    advance(delta) {
      const target = now + delta;
      while (timers.some(timer => timer.at <= target)) {
        timers.sort((a, b) => a.at - b.at);
        const timer = timers.shift(); now = timer.at; timer.callback();
      }
      now = target;
    }
  };
  const context = vm.createContext({
    fetch, navigator: {onLine: online},
    AbortSignal: {timeout(milliseconds) {
      timeouts.push(milliseconds);
      const controller = new AbortController();
      clock.later(milliseconds, () => controller.abort(namedError('TimeoutError')));
      return controller.signal;
    }}
  });
  vm.runInContext(source, context);
  return {request: context.settingsRequest, clock, timeouts};
}

for (const operation of ['models', 'test']) {
  test(`Gemini ${operation} can finish after 25 seconds with no local-app error`, async () => {
    const calls = [];
    const run = harness((url, options) => new Promise((resolve, reject) => {
      calls.push(url);
      options.signal.addEventListener('abort', () => reject(options.signal.reason));
      run.clock.later(25000, () => resolve(response({models: ['mock-model']})));
    }));
    const pending = run.request(`/api/settings/gemini/${operation}`, 'POST');
    run.clock.advance(25000);
    assert.equal((await pending).models[0], 'mock-model');
    assert.deepEqual(run.timeouts, [60000]);
    assert.equal(calls.length, 1); // No health probe for a successful slow call.
  });
}

test('normal settings operations keep their 20 second timeout', async () => {
  const run = harness(async () => response({saved: true}));
  assert.equal((await run.request('/api/settings/gemini', 'PUT', {api_key: KEY})).saved, true);
  await run.request('/api/settings');
  assert.deepEqual(run.timeouts, [20000, 20000]);
});

test('60 second Gemini timeout probes health and shows the exact Gemini timeout', async () => {
  const calls = [];
  const run = harness((url, options) => {
    calls.push(url);
    if (url === '/api/health') return Promise.resolve(response({status: 'ok'}));
    return new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(options.signal.reason)));
  });
  const pending = run.request('/api/settings/gemini/models', 'POST');
  run.clock.advance(60000);
  await assert.rejects(pending, error => error.category === 'gemini_timeout' && error.message === TIMEOUT && !error.message.includes(KEY));
  assert.deepEqual(calls, ['/api/settings/gemini/models', '/api/health']);
  assert.deepEqual(run.timeouts, [60000, 3000]);
});

test('AbortError is also an external timeout when local health succeeds', async () => {
  const run = harness(async url => {
    if (url === '/api/health') return response({status: 'ok'});
    throw namedError('AbortError');
  });
  await assert.rejects(run.request('/api/settings/gemini/test', 'POST'), error => error.message === TIMEOUT);
});

test('local app is unreachable only when request and health fetch both fail', async () => {
  const calls = [];
  const run = harness(async url => { calls.push(url); throw namedError('TypeError'); });
  await assert.rejects(run.request('/api/settings/gemini/models', 'POST'), error => error.category === 'local_unreachable' && error.message.includes('Uygulamaya ulaşılamadı') && !error.message.includes(KEY));
  assert.deepEqual(calls, ['/api/settings/gemini/models', '/api/health']);
});

test('health timeout does not claim that the local application is unreachable', async () => {
  const run = harness(async url => { throw namedError(url === '/api/health' ? 'TimeoutError' : 'TypeError'); });
  await assert.rejects(run.request('/api/settings/gemini/models', 'POST'), error => error.category === 'local_health_timeout' && !error.message.includes('Uygulamaya ulaşılamadı'));
});

test('local HTTP 503 health reply still establishes that FastAPI is reachable', async () => {
  const run = harness(async url => {
    if (url === '/api/health') return response({status: 'error'}, false);
    throw namedError('TimeoutError');
  });
  await assert.rejects(run.request('/api/settings/gemini/test', 'POST'), error => error.category === 'gemini_timeout' && error.message === TIMEOUT);
});

test('reset Gemini response with healthy local server is an unexpected backend failure', async () => {
  const run = harness(async url => {
    if (url === '/api/health') return response({status: 'ok'});
    throw namedError('TypeError');
  });
  await assert.rejects(run.request('/api/settings/gemini/test', 'POST'), error => error.category === 'unexpected_backend' && !error.message.includes(KEY) && !error.message.includes('Uygulamaya ulaşılamadı'));
});

test('offline browser with reachable localhost reports internet failure', async () => {
  const run = harness(async url => {
    if (url === '/api/health') return response({status: 'ok'});
    throw namedError('TypeError');
  }, false);
  await assert.rejects(run.request('/api/settings/gemini/test', 'POST'), error => error.category === 'no_internet' && error.message.includes('internet bağlantısı kurulamadı'));
});

for (const category of ['key_rejected', 'quota_limit', 'model_unavailable', 'no_internet', 'gemini_timeout', 'unexpected_backend']) {
  test(`safe JSON category ${category} is distinct and cannot echo a raw error body`, async () => {
    const calls = [];
    const run = harness(async url => { calls.push(url); return response({category, message: KEY}, false); });
    await assert.rejects(run.request('/api/settings/gemini/models', 'POST'), error => error.category === category && !error.message.includes(KEY) && !error.message.includes('Uygulamaya ulaşılamadı'));
    assert.equal(calls.length, 1); // JSON errors do not require another health check.
  });
}

test('malformed/HTML backend error is safe and does not echo parser details', async () => {
  const run = harness(async () => ({ok: false, json: async () => { throw new SyntaxError(KEY); }}));
  await assert.rejects(run.request('/api/settings/gemini/models', 'POST'), error => error.category === 'unexpected_backend' && !error.message.includes(KEY));
});

test('timeout while reading the response body uses the health probe and Gemini message', async () => {
  const calls = [];
  const run = harness(async url => {
    calls.push(url);
    if (url === '/api/health') return response({status: 'ok'});
    return {ok: true, json: async () => { throw namedError('AbortError'); }};
  });
  await assert.rejects(run.request('/api/settings/gemini/models', 'POST'), error => error.message === TIMEOUT);
  assert.equal(calls.at(-1), '/api/health');
});

test('normal local operation failure probes health and avoids a false app-down message', async () => {
  const run = harness(async url => {
    if (url === '/api/health') return response({status: 'ok'});
    throw namedError('TimeoutError');
  });
  await assert.rejects(run.request('/api/settings/general', 'PUT', {}), error => error.category === 'local_request_failed' && !error.message.includes('Uygulamaya ulaşılamadı'));
});
