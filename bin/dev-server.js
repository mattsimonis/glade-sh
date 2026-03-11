#!/usr/bin/env node
// Roost local dev server — zero npm deps
//
// Usage:  node bin/dev-server.js [port]   (default: 3000)
//         make dev
//
// Opens an SSH tunnel (casper.local:80 → localhost:8080) then serves
// web/index.html fresh from disk at / and proxies all other requests.
// Edit web/index.html and refresh — no deploy step needed.

const http   = require('http');
const net    = require('net');
const fs     = require('fs');
const path   = require('path');
const { execSync } = require('child_process');

const HTML        = path.join(__dirname, '..', 'web', 'index.html');
const DEV_PORT    = parseInt(process.argv[2]) || 3000;
const TUNNEL_PORT = 8080;   // casper:80 → localhost:8080
const UPSTREAM    = { host: '127.0.0.1', port: TUNNEL_PORT };
const CASPER_HOST = 'casper.local';

// Forward all per-project ttyd ports too (7681 main + 7690-7699 project shells).
const TTYD_PORTS  = [7681, ...Array.from({ length: 10 }, (_, i) => 7690 + i)];

function ensureTunnel() {
    const local80  = `-L ${TUNNEL_PORT}:localhost:80`;
    const ttydArgs = TTYD_PORTS.map(p => `-L ${p}:localhost:${p}`).join(' ');
    try {
        execSync(`ssh -f -N ${local80} ${ttydArgs} ${CASPER_HOST}`, { stdio: 'pipe' });
        console.log('SSH tunnel established (ports 80 + ttyd).');
    } catch {
        console.log('SSH tunnel already open or casper unreachable — proceeding.');
    }
}

function proxyHTTP(req, res) {
    const opts = {
        ...UPSTREAM,
        path:    req.url,
        method:  req.method,
        headers: { ...req.headers, host: CASPER_HOST },
    };
    const proxy = http.request(opts, (pr) => {
        res.writeHead(pr.statusCode, pr.headers);
        pr.pipe(res);
    });
    proxy.on('error', (e) => { if (!res.headersSent) res.writeHead(502); res.end(e.message); });
    req.pipe(proxy);
}

function proxyWS(req, socket, head) {
    // ttyd WebSocket connections go direct to their port (not through port 80).
    // The browser connects to ws://localhost:PORT/ws — no proxy needed here since
    // those ports are tunneled directly.  Any other WS upgrade still needs routing.
    const upstream = net.createConnection(UPSTREAM.port, UPSTREAM.host, () => {
        let hdrs = `${req.method} ${req.url} HTTP/1.1\r\nHost: ${CASPER_HOST}\r\n`;
        for (const [k, v] of Object.entries(req.headers)) {
            if (k.toLowerCase() !== 'host') hdrs += `${k}: ${v}\r\n`;
        }
        hdrs += '\r\n';
        upstream.write(hdrs);
        if (head && head.length) upstream.write(head);
    });
    socket.pipe(upstream);
    upstream.pipe(socket);
    socket.on('error', () => upstream.destroy());
    upstream.on('error', () => socket.destroy());
}

ensureTunnel();

const server = http.createServer((req, res) => {
    if (req.url === '/' || req.url === '/index.html') {
        let html;
        try { html = fs.readFileSync(HTML); } catch {
            res.writeHead(500); res.end('Cannot read ' + HTML); return;
        }
        res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
        res.end(html);
        return;
    }
    proxyHTTP(req, res);
});

server.on('upgrade', proxyWS);

server.listen(DEV_PORT, '127.0.0.1', () => {
    console.log(`\nRoost dev server → http://localhost:${DEV_PORT}`);
    console.log(`Serving  : ${HTML}`);
    console.log(`Proxying : everything else → http://${CASPER_HOST} (via SSH tunnel)`);
    console.log('\nEdit web/index.html and refresh to see changes.\n');
});
