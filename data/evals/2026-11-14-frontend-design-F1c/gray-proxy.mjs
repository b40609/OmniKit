// 灰階版：轉送到原本的示範頁，在 HTML 裡插一段灰階樣式（用頁面自己的 CSP nonce，才不會被擋）。
// 原版 18790、X 18791、Y 18792、Z 18793 → 對應 18780 到 18783。
import http from 'node:http';

const MAP = { 18790: 18780, 18791: 18781, 18792: 18782, 18793: 18783 };
for (const [port, target] of Object.entries(MAP)) {
  http.createServer((req, res) => {
    const up = http.request({ host: '127.0.0.1', port: target, path: req.url, method: req.method,
      headers: { ...req.headers, host: `127.0.0.1:${target}`, 'accept-encoding': 'identity' } }, (r) => {
      const type = r.headers['content-type'] || '';
      if (!type.includes('text/html')) { res.writeHead(r.statusCode, r.headers); r.pipe(res); return; }
      let body = '';
      r.setEncoding('utf8');
      r.on('data', (c) => { body += c; });
      r.on('end', () => {
        const csp = String(r.headers['content-security-policy'] || '');
        const nonce = (csp.match(/style-src[^;]*'nonce-([^']+)'/) || body.match(/nonce="([^"]+)"/) || [])[1];
        const tag = `<style${nonce ? ` nonce="${nonce}"` : ''}>html{filter:grayscale(1)!important}</style>`;
        body = body.includes('</head>') ? body.replace('</head>', `${tag}</head>`) : tag + body;
        const headers = { ...r.headers };
        delete headers['content-length'];
        res.writeHead(r.statusCode, headers);
        res.end(body);
      });
    });
    up.on('error', (e) => { res.writeHead(502); res.end(String(e)); });
    req.pipe(up);
  }).listen(Number(port), '127.0.0.1');
}
console.log('灰階：原版 18790、X 18791、Y 18792、Z 18793');
