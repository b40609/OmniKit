// F1 盲選實驗包：從 CatOS 的 commit 9fef976 建出原版、X、Y 三個版本，用同一份假資料同時開起來。
// 用法：node run.mjs --catos <CatOS repo 路徑> [--work <工作資料夾>] [--port 8890] [--rebuild]
// 需要 git、Node 與 npm。第一次會在工作資料夾跑 npm ci 並建置三個版本，之後直接啟動，不用再給 --catos。
// 埠：原版 8890、X 8891、Y 8892（--port 改起始埠）。只讀取 CatOS repo 的 git 物件，不動它的工作目錄。
import { spawnSync } from 'node:child_process';
import { createReadStream, existsSync, mkdirSync, rmSync, statSync } from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { handleApi } from './mock-server.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const COMMIT = '9fef976ed8910a94dcc6907b4e84cb4a47a43b90';
const FRONTEND = 'frontend/cat-os-vite';
const VERSIONS = [
  { label: '原版', dir: 'base', patch: null },
  { label: 'X', dir: 'x', patch: 'x.patch' },
  { label: 'Y', dir: 'y', patch: 'y.patch' },
];
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.svg': 'image/svg+xml', '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp',
  '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf', '.txt': 'text/plain; charset=utf-8',
};

function option(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  return i > 1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}

function run(cmd, args, cwd, env = {}) {
  const options = { cwd, stdio: 'inherit', env: { ...process.env, ...env } };
  // Windows 的 npm 是 .cmd，要經過 shell 才能啟動；這裡的參數都是固定字串，直接組成一行指令
  const r = process.platform === 'win32' && cmd === 'npm'
    ? spawnSync([cmd, ...args].join(' '), { ...options, shell: true })
    : spawnSync(cmd, args, options);
  if (r.status !== 0) throw new Error(`${cmd} ${args.join(' ')} 失敗（結束碼 ${r.status}）`);
}

function build(catos, work) {
  const src = path.join(work, 'src');
  const app = path.join(src, ...FRONTEND.split('/'));
  rmSync(src, { recursive: true, force: true });
  mkdirSync(src, { recursive: true });
  run('git', ['-C', catos, 'archive', '--format=tar', '-o', path.join(work, 'src.tar'), COMMIT, FRONTEND], work);
  // 用相對路徑：Git 附的 GNU tar 會把「C:」當成遠端主機
  run('tar', ['-xf', path.join('..', 'src.tar')], src);
  run('npm', ['ci', '--no-audit', '--no-fund'], app);
  // 不讓 git apply 往上找到別的 repo，否則 patch 的路徑會被當成那個 repo 根目錄底下的路徑
  const env = { GIT_CEILING_DIRECTORIES: path.dirname(app).replaceAll('\\', '/') };
  for (const v of VERSIONS) {
    if (v.patch) run('git', ['apply', '--whitespace=nowarn', path.join(HERE, v.patch)], app, env);
    run('node', [path.join('node_modules', 'vite', 'bin', 'vite.js'), 'build', '--outDir', path.join(work, 'dist', v.dir), '--emptyOutDir', '--logLevel', 'warn'], app);
    if (v.patch) run('git', ['apply', '-R', '--whitespace=nowarn', path.join(HERE, v.patch)], app, env);
  }
}

function serve(dir, port, label) {
  const root = path.resolve(dir);
  http.createServer((req, res) => {
    if (handleApi(req, res)) return;
    let file;
    try {
      file = path.join(root, decodeURIComponent(new URL(req.url, 'http://local').pathname));
    } catch {
      res.writeHead(400); res.end(); return;
    }
    if (file !== root && !file.startsWith(root + path.sep)) { res.writeHead(403); res.end(); return; }
    if (!existsSync(file) || statSync(file).isDirectory()) file = path.join(root, 'index.html');
    res.writeHead(200, { 'content-type': TYPES[path.extname(file)] ?? 'application/octet-stream', 'cache-control': 'no-store' });
    createReadStream(file).pipe(res);
  }).listen(port, '127.0.0.1', () => console.log(`${label}：http://127.0.0.1:${port}/`));
}

const catos = option('catos', null);
const work = path.resolve(option('work', path.join(os.tmpdir(), 'omnikit-f1')));
const port = Number(option('port', '8890'));
const built = VERSIONS.every((v) => existsSync(path.join(work, 'dist', v.dir, 'index.html')));
if (!built || process.argv.includes('--rebuild')) {
  if (!catos) {
    console.error('第一次執行要指定 CatOS 的路徑：node run.mjs --catos <CatOS repo 路徑>');
    process.exit(2);
  }
  mkdirSync(work, { recursive: true });
  build(path.resolve(catos), work);
}
VERSIONS.forEach((v, i) => serve(path.join(work, 'dist', v.dir), port + i, v.label));
console.log('請用無痕視窗開，避免沿用瀏覽器先前存下的版面比例。');
console.log('X、Y 是哪個工具封存在 mapping.sealed，選完再解開。按 Ctrl+C 結束。');
