import { createServer } from 'node:http';
import { readFile, mkdir, writeFile, stat } from 'node:fs/promises';
import { createReadStream } from 'node:fs';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { dirname, extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url));
const localProjectRoot = dirname(root);
const syncRoot = join(root, 'sync-source');
const execFileAsync = promisify(execFile);
const phpRoot = join(syncRoot, 'shared_hosting_php');
const port = Number(process.env.PORT || 4173);
const mime = { '.css': 'text/css; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.png': 'image/png', '.webp': 'image/webp', '.svg': 'image/svg+xml', '.json': 'application/json; charset=utf-8' };
const subscribers = new Set();
const syncState = { branch: 'master', lastCheck: null, lastUpdate: null, commit: null, error: null, busy: false };

async function json(path) { return JSON.parse(await readFile(path, 'utf8')); }
async function catalog() {
  let dataRoot = join(phpRoot, 'data');
  try { await stat(dataRoot); } catch { dataRoot = join(localProjectRoot, 'shared_hosting_php', 'data'); }
  const [categories, demo] = await Promise.all([
    json(join(dataRoot, 'categories.json')),
    json(join(dataRoot, 'demo_catalog.json')),
  ]);
  return {
    categories,
    brands: demo.brands,
    products: demo.products.map((product) => ({
      ...product,
      image: `/assets/images/${product.image.split('/').pop()}`,
    })),
  };
}
function send(res, status, body, type = 'application/json; charset=utf-8') {
  res.writeHead(status, { 'Content-Type': type, 'Cache-Control': 'no-store' });
  res.end(typeof body === 'string' ? body : JSON.stringify(body));
}
function safeAsset(urlPath) {
  const relative = normalize(urlPath.replace(/^\/assets\//, '')).replace(/^([.][.][\\/])+/, '');
  return join(phpRoot, 'assets', relative);
}
function announceUpdate() {
  for (const client of subscribers) client.write('event: repository-update\ndata: {}\n\n');
}
async function syncRepository() {
  if (syncState.busy) return;
  syncState.busy = true;
  syncState.lastCheck = new Date().toISOString();
  try {
    await execFileAsync('git', ['fetch', '--quiet', 'origin'], { cwd: syncRoot, windowsHide: true });
    const { stdout: before } = await execFileAsync('git', ['rev-parse', 'HEAD'], { cwd: syncRoot, windowsHide: true });
    await execFileAsync('git', ['merge', '--ff-only', `origin/${syncState.branch}`], { cwd: syncRoot, windowsHide: true });
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
  try { await stat(synced); return synced; } catch { return join(localProjectRoot, relative); }
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://${req.headers.host || 'localhost'}`);
  try {
    if (url.pathname === '/api/catalog' && req.method === 'GET') return send(res, 200, await catalog());
    if (url.pathname === '/api/sync' && req.method === 'GET') return send(res, 200, syncState);
    if (url.pathname === '/events' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
      res.write(': connected\n\n');
      subscribers.add(res);
      req.on('close', () => subscribers.delete(res));
      return;
    }
    if (url.pathname === '/api/leads' && req.method === 'POST') {
      let body = '';
      for await (const part of req) { body += part; if (body.length > 100_000) return send(res, 413, { error: 'Слишком большой запрос' }); }
      const lead = JSON.parse(body || '{}');
      if (!String(lead.name || '').trim() || !String(lead.phone || '').trim()) return send(res, 400, { error: 'Укажите имя и телефон.' });
      const file = join(root, 'data', 'leads.json');
      await mkdir(dirname(file), { recursive: true });
      let leads = []; try { leads = await json(file); } catch { /* first local lead */ }
      leads.unshift({ name: String(lead.name).trim(), phone: String(lead.phone).trim(), email: String(lead.email || '').trim(), message: String(lead.message || '').trim(), createdAt: new Date().toISOString() });
      await writeFile(file, JSON.stringify(leads, null, 2), 'utf8');
      return send(res, 201, { ok: true });
    }
    if (url.pathname === '/app.js' || url.pathname === '/local.css') {
      const file = await projectFile(`local-site/public/${url.pathname.slice(1)}`);
      return send(res, 200, await readFile(file, 'utf8'), mime[extname(file)]);
    }
    if (url.pathname.startsWith('/assets/')) {
      let file = safeAsset(url.pathname);
      try { await stat(file); } catch { file = join(localProjectRoot, 'shared_hosting_php', 'assets', normalize(url.pathname.replace(/^\/assets\//, ''))); }
      const info = await stat(file);
      if (!info.isFile()) return send(res, 404, 'Не найдено', 'text/plain; charset=utf-8');
      res.writeHead(200, { 'Content-Type': mime[extname(file).toLowerCase()] || 'application/octet-stream' });
      return createReadStream(file).pipe(res);
    }
    return send(res, 200, await readFile(await projectFile('local-site/public/index.html'), 'utf8'), 'text/html; charset=utf-8');
  } catch (error) {
    console.error(error);
    return send(res, 500, { error: 'Локальный сервер не смог обработать запрос.' });
  }
});

try { syncState.branch = (await execFileAsync('git', ['branch', '--show-current'], { cwd: syncRoot, windowsHide: true })).stdout.trim() || 'master'; } catch { /* use default branch until first fetch */ }
server.listen(port, '127.0.0.1', () => {
  console.log(`KlimaEco local: http://localhost:${port}`);
  void syncRepository();
  setInterval(syncRepository, 10_000);
});
