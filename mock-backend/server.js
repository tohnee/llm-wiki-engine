#!/usr/bin/env node
/**
 * LLM-Wiki Engine - Mock Backend
 * 纯 Node.js 内置 http 模块,零 npm 依赖。
 *
 * Usage:   PORT=8000 node server.js
 * Default: 0.0.0.0:8000
 *
 * 覆盖前端(llmwiki/frontend/src/api.js)的所有 API 路径。
 * 数据 & 路由分离: db.js + routes.js。
 */

import http from 'node:http';
import { ROUTES } from './routes.js';

const PORT = parseInt(process.env.PORT || '8000', 10);
const HOST = process.env.HOST || '0.0.0.0';

// ---------- helpers ----------
function send(res, status, body, extra = {}) {
  const data = typeof body === 'string' ? body : JSON.stringify(body);
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Content-Length': Buffer.byteLength(data),
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Admin-Key',
    ...extra,
  });
  res.end(data);
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let d = '';
    req.on('data', c => d += c);
    req.on('end', () => {
      if (!d) return resolve({});
      try { resolve(JSON.parse(d)); } catch { reject(new Error('invalid JSON')); }
    });
    req.on('error', reject);
  });
}

function matchPath(pattern, actual) {
  const pp = pattern.split('/'), ap = actual.split('/');
  if (pp.length !== ap.length) return null;
  const params = {};
  for (let i = 0; i < pp.length; i++) {
    if (pp[i].startsWith(':')) params[pp[i].slice(1)] = decodeURIComponent(ap[i]);
    else if (pp[i] !== ap[i]) return null;
  }
  return params;
}

function colorLog(method, path, status, ms) {
  const c = status >= 500 ? '\x1b[31m' : status >= 400 ? '\x1b[33m' : '\x1b[32m';
  console.log(`${c}[${new Date().toISOString()}] ${method.padEnd(6)} ${path.padEnd(48)} ${status} ${ms}ms\x1b[0m`);
}

// ---------- HTTP server ----------
const server = http.createServer(async (req, res) => {
  const t0 = Date.now();
  const path = (req.url || '/').split('?')[0];

  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Admin-Key',
      'Access-Control-Max-Age': '600',
    });
    res.end();
    colorLog(req.method, path, 204, Date.now() - t0);
    return;
  }

  // 路由匹配
  for (const route of ROUTES) {
    if (route.method !== req.method) continue;
    const params = matchPath(route.path, path);
    if (params === null) continue;
    try {
      const body = (req.method === 'POST' || req.method === 'PUT') ? await readBody(req) : {};
      await route.handler(req, res, params, body, send);
    } catch (e) {
      console.error(`[ERROR] ${route.method} ${path}:`, e);
      if (!res.headersSent) send(res, 500, { detail: e.message || 'internal error' });
    }
    colorLog(req.method, path, res.statusCode, Date.now() - t0);
    return;
  }

  // 404
  send(res, 404, { detail: `route not found: ${req.method} ${path}` });
  colorLog(req.method, path, 404, Date.now() - t0);
});

server.on('error', (err) => {
  console.error('\x1b[31m[FATAL]', err.message, '\x1b[0m');
  if (err.code === 'EADDRINUSE') {
    console.error(`端口 ${PORT} 已被占用。请关闭占用进程或换端口: PORT=8888 node server.js`);
  }
  process.exit(1);
});

server.listen(PORT, HOST, () => {
  console.log('');
  console.log('╔════════════════════════════════════════════════════════════════╗');
  console.log('║  🎬  LLM-Wiki Engine  -  Mock Backend                          ║');
  console.log('╠════════════════════════════════════════════════════════════════╣');
  console.log(`║  Listening on  http://${HOST}:${PORT}`.padEnd(65) + '║');
  console.log(`║  Routes        ${ROUTES.length} endpoints`.padEnd(65) + '║');
  console.log('║  Frontend      cd llmwiki/frontend && npm run dev              ║');
  console.log('║  Login         任何邮箱+密码组合均可,例: demo@llmwiki.test     ║');
  console.log('║  Stop          Ctrl+C                                          ║');
  console.log('╚════════════════════════════════════════════════════════════════╝');
  console.log('');
  console.log('已注册路由:');
  for (const r of ROUTES) {
    console.log(`  ${r.method.padEnd(6)} ${r.path}`);
  }
  console.log('');
});

// 优雅退出
process.on('SIGINT', () => {
  console.log('\n[Mock] Shutting down...');
  server.close(() => process.exit(0));
});
