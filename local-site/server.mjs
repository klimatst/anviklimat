import { createServer } from 'node:http';
import { readFile, mkdir, writeFile, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { dirname, extname, join, normalize, resolve, sep } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const localProjectRoot = dirname(root);
const syncRoot = join(root, 'sync-source');
const execFileAsync = promisify(execFile);
const repoUrl = 'https://github.com/klimatst/anviklimat.git';
const branch = 'master';
const port = Number(process.env.PORT || 4173);
const mime = {
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.svg': 'image/svg+xml',
  '.json': 'application/json; charset=utf-8',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
};
const subscribers = new Set();
const syncState = { branch, lastCheck: null, lastUpdate: null, commit: null, error: null, busy: false };

async function json(path) {
  return JSON.parse(await readFile(path, 'utf8'));
}
async function exists(path) {
  try { await stat(path); return true; } catch { return false; }
}
async function catalog() {
  const syncedDataRoot = join(syncRoot, 'shared_hosting_php', 'data');
  const localDataRoot = join(localProjectRoot, 'shared_hosting_php', 'data');
  const dataRoot = await exists(syncedDataRoot) ? syncedDataRoot : localDataRoot;
  const [categories, demo] = await Promise.all([
    json(join(dataRoot, 'categories.json')),
    json(join(dataRoot, 'demo_catalog.json')),
  ]);
  return {
    categories,
    brands: demo.brands || [],
    products: (demo.products || []).map((product) => {
      const source = String(product.image || '');
      const match = source.match(/(?:\/static\/images\/|\/assets\/images\/)(.+)$/);
      return { ...product, image: match ? `/assets/images/${match[1]}` : '' };
    }),
  };
}
function send(res, status, body, type = 'application/json; charset=utf-8') {
  res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end(typeof body === 'string' ? body : JSON.stringify(body));
}
function safeAsset(urlPath, assetRoot) {
  let decoded;
  try { decoded = decodeURIComponent(urlPath.slice('/assets/'.length)); }
  catch { return null; }
  const rootPath = resolve(assetRoot);
  const target = resolve(rootPath, normalize(decoded));
  if (target !== rootPath && !target.startsWith(rootPath + sep)) return null;
  return target;
}
function announceUpdate() {
  for (const client of subscribers) client.write('event: repository-update\ndata: {}\n\n');
}
async function ensureClone() {
  if (await exists(join(syncRoot, '.git'))) return;
  if (await exists(syncRoot)) {
    throw new Error('Папка local-site/sync-source уже существует, но не является Git-копией. Переименуйте её и перезапустите сервер.');
  }
  await mkdir(dirname(syncRoot), { recursive: true });
  console.log('Первый запуск: загружаю копию репозитория для синхронизации GitHub…');
  await execFileAsync('git', ['clone', '--depth', '1', '--branch', branch, repoUrl, syncRoot], {
    cwd: root, windowsHide: true, timeout: 120_000, maxBuffer: 2 * 1024 * 1024,
  });
}
async function syncRepository() {
  if (syncState.busy) return;
  syncState.busy = true;
  syncState.lastCheck = new Date().toISOString();
  try {
    await ensureClone();
    const { stdout: before } = await execFileAsync('git', ['rev-parse', 'HEAD'], { cwd: syncRoot, windowsHide: true });
    await execFileAsync('git', ['fetch', '--quiet', 'origin', branch], {
      cwd: syncRoot, windowsHide: true, timeout: 60_000, maxBuffer: 2 * 1024 * 1024,
    });
    await execFileAsync('git', ['merge', '--ff-only', `origin/${branch}`], { cwd: syncRoot, windowsHide: true });
    const { stdout: after } = await execFileAsync('git', ['rev-parse', 'HEAD'], { cwd: syncRoot, windowsHide: true });
    syncState.commit = after.trim().slice(0, 12);
    syncState.error = null;
    if (before.trim() !== after.trim()) {
      syncState.lastUpdate = new Date().toISOString();
      announceUpdate();
      console.log(`GitHub обновлён: ${syncState.commit}`);
    }
  } catch (error) {
    syncState.error = error.message;
    console.error(`GitHub sync: ${error.message}`);
  } finally {
    syncState.busy = false;
  }
}
async function projectFile(relative) {
  const synced = join(syncRoot, relative);
  if (await exists(synced)) return synced;
  return join(localProjectRoot, relative);
}
async function readLeadBody(req) {
  let body = '';
  for await (const part of req) {
    body += part;
    if (Buffer.byteLength(body, 'utf8') > 16_384) throw Object.assign(new Error('Слишком большой запрос'), { statusCode: 413 });
  }
  try { return JSON.parse(body || '{}'); }
  catch { throw Object.assign(new Error('Некорректный JSON'), { statusCode: 400 }); }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
  try {
    if (url.pathname === '/api/catalog' && req.method === 'GET') {
      return send(res, 200, await catalog());
    }
    if (url.pathname === '/api/sync' && req.method === 'GET') {
      return send(res, 200, syncState);
    }
    if (url.pathname === '/events' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream; charset=utf-8', 'Cache-Control': 'no-cache', Connection: 'keep-alive', 'X-Accel-Buffering': 'no' });
      res.write(': connected\n\n');
      subscribers.add(res);
      req.on('close', () => subscribers.delete(res));
      return;
    }
    if (url.pathname === '/api/leads' && req.method === 'POST') {
      const lead = await readLeadBody(req);
      const name = String(lead.name || '').trim().slice(0, 160);
      const phone = String(lead.phone || '').trim().slice(0, 80);
      if (!name || !phone) return send(res, 400, { error: 'Укажите имя и телефон.' });
      const file = join(root, 'data', 'leads.json');
      await mkdir(dirname(file), { recursive: true });
      let leads = [];
      try { leads = await json(file); if (!Array.isArray(leads)) leads = []; } catch { /* first local lead */ }
      leads.unshift({
        name, phone,
        email: String(lead.email || '').trim().slice(0, 200),
        message: String(lead.message || '').trim().slice(0, 4000),
        createdAt: new Date().toISOString(),
      });
      await writeFile(file, JSON.stringify(leads, null, 2), 'utf8');
      return send(res, 201, { ok: true });
    }
    if (url.pathname === '/app.js' || url.pathname === '/local.css') {
      const file = await projectFile(`local-site/public/${url.pathname.slice(1)}`);
      return send(res, 200, await readFile(file, 'utf8'), mime[extname(file).toLowerCase()] || 'text/plain; charset=utf-8');
    }
    if (url.pathname.startsWith('/assets/')) {
      const syncedRoot = join(syncRoot, 'shared_hosting_php', 'assets');
      const localRoot = join(localProjectRoot, 'shared_hosting_php', 'assets');
      let file = safeAsset(url.pathname, await exists(syncedRoot) ? syncedRoot : localRoot);
      if (!file) return send(res, 400, 'Некорректный путь', 'text/plain; charset=utf-8');
      if (!await exists(file) && await exists(localRoot)) file = safeAsset(url.pathname, localRoot);
      if (!file || !await exists(file) || !(await stat(file)).isFile()) {
        return send(res, 404, 'Файл не найден', 'text/plain; charset=utf-8');
      }
      res.writeHead(200, { 'Content-Type': mime[extname(file).toLowerCase()] || 'application/octet-stream', 'X-Content-Type-Options': 'nosniff' });
      return createReadStream(file).pipe(res);
    }
    if (req.method !== 'GET' && req.method !== 'HEAD') {
      return send(res, 405, { error: 'Метод не поддерживается' }, 'application/json; charset=utf-8');
    }
    return send(res, 200, await readFile(await projectFile('local-site/public/index.html'), 'utf8'), 'text/html; charset=utf-8');
  } catch (error) {
    console.error(error);
    return send(res, error.statusCode || 500, { error: error.statusCode ? error.message : 'Локальный сервер не смог обработать запрос.' });
  }
});

server.listen(port, '127.0.0.1', () => {
  console.log(`KlimaEco local: http://localhost:${port}`);
  console.log('Проверка синхронизации: http://localhost:' + port + '/api/sync');
  void syncRepository();
  setInterval(syncRepository, 10_000);
});
