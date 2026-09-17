const { test } = require('node:test');
const assert = require('node:assert/strict');
const { spawn } = require('node:child_process');
const http = require('node:http');
const crypto = require('node:crypto');
const path = require('node:path');

test('legacy relay rejects unauthorized access and acknowledges only durable Odoo acceptance', { timeout: 60000 }, async () => {
    const received = [];
    let available = true;
    const mock = http.createServer((req, res) => {
        const chunks = [];
        req.on('data', chunk => chunks.push(chunk));
        req.on('end', () => {
            received.push({ headers: req.headers, body: Buffer.concat(chunks).toString() });
            res.writeHead(available ? 200 : 503);
            res.end(available ? 'EVENT_RECEIVED' : 'Unavailable');
        });
    });
    await new Promise(resolve => mock.listen(0, '127.0.0.1', resolve));
    const portProbe = http.createServer();
    await new Promise(resolve => portProbe.listen(0, '127.0.0.1', resolve));
    const port = portProbe.address().port;
    await new Promise(resolve => portProbe.close(resolve));
    const child = spawn(process.execPath, [path.join(__dirname, 'server.js')], {
        cwd: __dirname, windowsHide: true,
        env: { ...process.env, NODE_ENV: 'production', PORT: String(port),
            ODOO_URL: 'http://127.0.0.1:' + mock.address().port,
            SIDECAR_SECRET: 'relay-test', META_APP_SECRET: 'meta-test',
            VERIFY_TOKEN: 'verify-test', REDIS_URL: '', CORS_ORIGIN: 'https://example.test' },
        stdio: ['ignore', 'pipe', 'pipe'],
    });
    const base = 'http://127.0.0.1:' + port;
    let output = '';
    child.stdout.on('data', data => { output += data.toString(); });
    child.stderr.on('data', data => { output += data.toString(); });
    child.on('error', error => { output += error.message; });
    try {
        let ready = false;
        for (let i = 0; i < 300; i += 1) {
            if (child.exitCode !== null) break;
            try { ready = (await fetch(base + '/health', { signal: AbortSignal.timeout(1000) })).ok; } catch {}
            if (ready) break;
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        assert.ok(ready, 'relay must start: ' + output);
        for (const endpoint of ['/events/recent', '/migration/status']) {
            assert.equal((await fetch(base + endpoint)).status, 403);
            assert.equal((await fetch(base + endpoint, { headers: { 'x-sidecar-key': 'wrong' } })).status, 403);
            assert.equal((await fetch(base + endpoint, { headers: { 'x-sidecar-key': 'relay-test' } })).status, 200);
        }
        const body = JSON.stringify({ object: 'whatsapp_business_account', entry: [] });
        const signature = 'sha256=' + crypto.createHmac('sha256', 'meta-test').update(body).digest('hex');
        const post = headers => fetch(base + '/webhook', { method: 'POST', headers: { 'Content-Type': 'application/json', ...headers }, body });
        assert.equal((await post({})).status, 403);
        assert.equal((await post({ 'x-hub-signature-256': signature + 'x' })).status, 403);
        assert.equal((await post({ 'x-hub-signature-256': signature })).status, 200);
        assert.equal(received[0].body, body);
        assert.equal(received[0].headers['x-hub-signature-256'], signature);
        assert.equal(received[0].headers['x-sidecar-key'], 'relay-test');
        available = false;
        assert.equal((await post({ 'x-hub-signature-256': signature })).status, 503);
        const handshake = await fetch(base + '/socket.io/?EIO=4&transport=polling');
        const session = JSON.parse((await handshake.text()).slice(1));
        await fetch(base + '/socket.io/?EIO=4&transport=polling&sid=' + session.sid,
            { method: 'POST', headers: { 'Content-Type': 'text/plain' }, body: '40' });
        const rejection = await fetch(base + '/socket.io/?EIO=4&transport=polling&sid=' + session.sid);
        assert.match(await rejection.text(), /Socket mode retired/);
    } finally {
        if (child.exitCode === null) {
            const exited = new Promise(resolve => child.once('exit', resolve));
            child.kill();
            await exited;
        }
        await new Promise(resolve => mock.close(resolve));
    }
});
