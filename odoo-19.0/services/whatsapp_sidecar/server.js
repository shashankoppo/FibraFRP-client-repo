const express = require('express');
const http = require('http');
const { Server } = require('socket.io');
const cors = require('cors');
const axios = require('axios');
const dotenv = require('dotenv');
const { createClient } = require('redis');
const crypto = require('crypto');

dotenv.config();

const app = express();
app.use(cors());
app.use(express.json({
    limit: process.env.JSON_LIMIT || '10mb',
    verify: (req, res, buf) => {
        req.rawBody = Buffer.from(buf);
    },
}));

const server = http.createServer(app);
const io = new Server(server, {
    cors: {
        origin: process.env.CORS_ORIGIN || '*',
        methods: ['GET', 'POST'],
    },
});

const PORT = process.env.PORT || 3000;
const SIDECAR_SECRET = process.env.SIDECAR_SECRET || '';
const ODOO_URL = process.env.ODOO_URL || 'http://odoo:8069';
const VERIFY_TOKEN = process.env.VERIFY_TOKEN || '';
const META_APP_SECRET = process.env.META_APP_SECRET || process.env.APP_SECRET || '';
const REDIS_URL = process.env.REDIS_URL || '';
const QUEUE_KEY = process.env.REDIS_QUEUE_KEY || 'elsx:whatsapp:webhook:queue';
const DEAD_KEY = process.env.REDIS_DEAD_KEY || 'elsx:whatsapp:webhook:dead';
const RECENT_EVENTS_KEY = process.env.REDIS_RECENT_EVENTS_KEY || 'elsx:whatsapp:recent-events';
const MAX_ATTEMPTS = parseInt(process.env.MAX_FORWARD_ATTEMPTS || '12', 10);
const QUEUE_INTERVAL_MS = parseInt(process.env.QUEUE_INTERVAL_MS || '2000', 10);

let redis = null;
let redisReady = false;
const memoryQueue = [];
const memoryDead = [];
const recentEvents = [];

async function initRedis() {
    if (!REDIS_URL) {
        console.warn('[SIDECAR] REDIS_URL not configured, using memory queue');
        return;
    }

    redis = createClient({
        url: REDIS_URL,
        socket: {
            reconnectStrategy: (retries) => Math.min(retries * 200, 5000),
            connectTimeout: 3000,
        },
    });

    redis.on('ready', () => {
        redisReady = true;
        console.log('[SIDECAR] Redis queue connected');
    });
    redis.on('error', (err) => {
        redisReady = false;
        console.warn('[SIDECAR] Redis unavailable, using memory queue:', err.message);
    });
    redis.on('end', () => {
        redisReady = false;
    });

    try {
        await Promise.race([
            redis.connect(),
            new Promise((_, reject) => setTimeout(() => reject(new Error('Redis connection timed out')), 4000)),
        ]);
    } catch (err) {
        redisReady = false;
        console.warn('[SIDECAR] Redis connection failed, using memory queue:', err.message);
        try {
            await redis.disconnect();
        } catch (disconnectErr) {
            // The client may already be disconnected after a failed startup attempt.
        }
    }
}

function makeQueueItem(payload, source = 'meta', meta = {}) {
    return {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        payload,
        source,
        rawBodyBase64: meta.rawBody ? meta.rawBody.toString('base64') : null,
        metaSignature: meta.metaSignature || null,
        attempts: 0,
        createdAt: Date.now(),
        nextAttemptAt: Date.now(),
        lastError: null,
    };
}

async function enqueueWebhook(payload, source = 'meta', meta = {}) {
    const item = makeQueueItem(payload, source, meta);
    const serialized = JSON.stringify(item);
    if (redisReady) {
        try {
            await redis.lPush(QUEUE_KEY, serialized);
            return item;
        } catch (err) {
            redisReady = false;
            console.warn('[SIDECAR] Redis enqueue failed, falling back to memory:', err.message);
        }
    }
    memoryQueue.push(item);
    return item;
}

async function requeueWebhook(item) {
    const delayMs = Math.min(60000, 1000 * (2 ** Math.max(item.attempts - 1, 0)));
    item.nextAttemptAt = Date.now() + delayMs;
    const serialized = JSON.stringify(item);
    if (redisReady) {
        try {
            await redis.lPush(QUEUE_KEY, serialized);
            return;
        } catch (err) {
            redisReady = false;
            console.warn('[SIDECAR] Redis requeue failed, falling back to memory:', err.message);
        }
    }
    memoryQueue.push(item);
}

async function deadLetter(item) {
    const serialized = JSON.stringify(item);
    if (redisReady) {
        try {
            await redis.lPush(DEAD_KEY, serialized);
            await redis.lTrim(DEAD_KEY, 0, 999);
            return;
        } catch (err) {
            console.warn('[SIDECAR] Redis dead-letter write failed:', err.message);
        }
    }
    memoryDead.push(item);
    if (memoryDead.length > 1000) memoryDead.shift();
}

async function dequeueWebhook() {
    let item = null;
    if (redisReady) {
        try {
            const raw = await redis.rPop(QUEUE_KEY);
            item = raw ? JSON.parse(raw) : null;
        } catch (err) {
            redisReady = false;
            console.warn('[SIDECAR] Redis dequeue failed, falling back to memory:', err.message);
        }
    }
    if (!item) item = memoryQueue.shift() || null;
    return item;
}

async function forwardToOdoo(item) {
    const body = item.rawBodyBase64
        ? Buffer.from(item.rawBodyBase64, 'base64')
        : Buffer.from(JSON.stringify(item.payload || {}));
    const headers = {
        'x-sidecar-key': SIDECAR_SECRET,
        'Content-Type': 'application/json',
    };
    if (item.metaSignature) {
        headers['X-Hub-Signature-256'] = item.metaSignature;
    }
    await axios.post(`${ODOO_URL}/whatsapp/sidecar/receive`, body, {
        headers: {
            ...headers,
        },
        timeout: 10000,
    });
}

function verifyMetaSignature(req) {
    if (!META_APP_SECRET) {
        console.warn('[SIDECAR] META_APP_SECRET not configured; Meta HMAC verification skipped');
        return true;
    }

    const signature = req.headers['x-hub-signature-256'] || '';
    if (!signature) return false;

    const rawBody = req.rawBody || Buffer.from(JSON.stringify(req.body || {}));
    const expected = `sha256=${crypto
        .createHmac('sha256', META_APP_SECRET)
        .update(rawBody)
        .digest('hex')}`;

    const actualBuffer = Buffer.from(signature);
    const expectedBuffer = Buffer.from(expected);
    return actualBuffer.length === expectedBuffer.length
        && crypto.timingSafeEqual(actualBuffer, expectedBuffer);
}

async function processQueue() {
    const item = await dequeueWebhook();
    if (!item) return;

    if (item.nextAttemptAt && item.nextAttemptAt > Date.now()) {
        await requeueWebhook(item);
        return;
    }

    try {
        await forwardToOdoo(item);
        console.log(`[SIDECAR] Webhook forwarded to Odoo item=${item.id} attempts=${item.attempts + 1}`);
    } catch (err) {
        item.attempts += 1;
        item.lastError = err.message;
        if (item.attempts >= MAX_ATTEMPTS) {
            console.error(`[SIDECAR] Dead-lettering webhook item=${item.id}:`, err.message);
            await deadLetter(item);
        } else {
            console.warn(`[SIDECAR] Forward failed item=${item.id}, retry=${item.attempts}/${MAX_ATTEMPTS}:`, err.message);
            await requeueWebhook(item);
        }
    }
}

async function rememberEvent(event) {
    const item = JSON.stringify({ ...event, ts: Date.now() });
    recentEvents.push(item);
    if (recentEvents.length > 200) recentEvents.shift();
    if (redisReady) {
        try {
            await redis.lPush(RECENT_EVENTS_KEY, item);
            await redis.lTrim(RECENT_EVENTS_KEY, 0, 199);
        } catch (err) {
            console.warn('[SIDECAR] Failed to store recent event:', err.message);
        }
    }
}

async function getQueueStats() {
    if (redisReady) {
        try {
            return {
                driver: 'redis',
                queued: await redis.lLen(QUEUE_KEY),
                dead: await redis.lLen(DEAD_KEY),
            };
        } catch (err) {
            redisReady = false;
        }
    }
    return { driver: 'memory', queued: memoryQueue.length, dead: memoryDead.length };
}

app.get('/health', async (req, res) => {
    res.status(200).json({
        status: 'healthy',
        version: '1.2.0',
        odoo_url: ODOO_URL,
        redis: redisReady ? 'connected' : 'fallback',
        queue: await getQueueStats(),
    });
});

app.get('/events/recent', async (req, res) => {
    const limit = Math.min(parseInt(req.query.limit || '50', 10), 200);
    if (redisReady) {
        try {
            const rows = await redis.lRange(RECENT_EVENTS_KEY, 0, limit - 1);
            return res.status(200).json(rows.map((row) => JSON.parse(row)));
        } catch (err) {
            console.warn('[SIDECAR] Recent events read failed:', err.message);
        }
    }
    res.status(200).json(recentEvents.slice(-limit).reverse().map((row) => JSON.parse(row)));
});

app.get('/webhook', (req, res) => {
    const mode = req.query['hub.mode'];
    const token = req.query['hub.verify_token'];
    const challenge = req.query['hub.challenge'];

    if (mode === 'subscribe' && token === VERIFY_TOKEN) {
        console.log('[SIDECAR] Webhook verified');
        res.status(200).send(challenge);
    } else {
        res.sendStatus(403);
    }
});

app.post('/webhook', async (req, res) => {
    const body = req.body;
    console.log('[SIDECAR] Incoming webhook from Meta');

    if (!verifyMetaSignature(req)) {
        console.warn('[SIDECAR] Rejected webhook with invalid Meta signature');
        return res.status(403).send('Invalid signature');
    }

    res.status(200).send('EVENT_RECEIVED');

    io.emit('sync_required', { reason: 'webhook_received' });
    await enqueueWebhook(body, 'meta', {
        rawBody: req.rawBody,
        metaSignature: req.headers['x-hub-signature-256'] || null,
    });
});

app.post('/relay/new-message', async (req, res) => {
    const authHeader = req.headers['x-sidecar-key'];
    if (authHeader !== SIDECAR_SECRET) {
        return res.status(403).json({ error: 'Unauthorized' });
    }

    const { chat_id, message, type } = req.body;
    const event = { chat_id, message, type };
    console.log(`[SIDECAR] Relaying ${type} for chat ${chat_id}`);

    await rememberEvent(event);
    io.emit('whatsapp_event', event);
    res.status(200).json({ status: 'sent' });
});

io.on('connection', (socket) => {
    console.log(`[SOCKET] User connected: ${socket.id}`);
    socket.emit('sync_required', { reason: 'connected' });

    socket.on('join_chat', (chatId) => {
        socket.join(`chat_${chatId}`);
    });

    socket.on('presence', (data) => {
        io.emit('agent_presence', { socket_id: socket.id, ...data, ts: Date.now() });
    });

    socket.on('disconnect', () => {
        console.log(`[SOCKET] User disconnected: ${socket.id}`);
    });
});

initRedis().finally(() => {
    setInterval(processQueue, QUEUE_INTERVAL_MS);
    server.listen(PORT, '0.0.0.0', () => {
        console.log(`[SIDECAR] Industrial Sidecar running on port ${PORT}`);
    });
});
