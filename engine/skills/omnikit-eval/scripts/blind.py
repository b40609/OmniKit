# /// script
# requires-python = ">=3.11"
# dependencies = []
#
# [tool.uv]
# exclude-newer = "2026-11-01T00:00:00Z"
# ///
"""盲選（品味題）：幾個版本各開一個網址，隨機標籤、封存對照，使用者選完才解封。

前端設計三輪（data/evals/2026-11-1[34]-frontend-design-F1*）手動做過的事，收成一支腳本；第三輪就是手動給錯網址，
所以開站後一定先自動檢查每個網址回應的真的是該有的版本，對不上就全部關掉，不給使用者看。

一次盲選一個資料夾，裡面的 spec.json：
  {"title": "…",
   "versions": {"<名稱>": {"dir": "<版本的資料夾>", "cmd": ["node", "ui-mock.mjs"],
                         "port_env": "LINEPORT_MOCK_PORT", "env": {…}}, …},
   "reference": "<名稱>"（可省略：這個版本不蒙，標成「原版」，當對照）,
   "path": "/",
   "fingerprint": [{"path": "/", "file": "index.html"}],   # 網址回應要最像這個版本自己的哪個檔（相對 dir）
   "phases": ["gray", "color"]}                              # 品味題先灰階評版面與操作，再彩色只評配色
cmd 裡的 {port} 換成分到的 port；port_env 有寫就把 port 放進那個環境變數。

步驟：
1. seal：隨機標籤（A、B、C…），對照表加一段亂數後封存（sealed.json 只存 base64，防的是不小心看到，不是加密），
   SHA-256 寫在 seal.sha256 並印出來；解封時比對雜湊，證明對照表選完之後沒有被改過。只印標籤。
2. serve：每個版本開在隨機的空 port（不沿用上一次，避免舊的服務還開著）；每個標籤另外開一個灰階轉送
   （插一段 grayscale 樣式，遇到 CSP 用頁面自己的 nonce）。開好先 verify，過了才印網址；過不了就關掉、照實說。
   這個指令會一直開著，用 stop 關掉（或 Ctrl+C）。
3. verify：每個標籤的網址要 200、彩色沒有灰階樣式、灰階有、灰階拿掉樣式之後跟彩色一樣；回應最像的必須是這個標籤
   自己的版本的檔（比對行的集合），而且明顯比其他版本像；兩個版本的檔一模一樣就不能盲選。訊息只寫標籤，不寫名稱。
4. shots（可省略）：Chrome headless 截圖（桌機 1440、手機 375，灰階與彩色），檔名只有標籤，給評審或使用者看。
5. choose：記下使用者每一段的選擇（--phase gray|color，--pick 標籤或 tie，可以加 --rank 與 --note）。
6. reveal：每一段都選了才解封（--force 會記下是強制解封的）；比對雜湊，印出對照並寫 result.json。

這支腳本只動它的資料夾與它自己開的程式；不連外網。

用法：
  uv run scripts/blind.py seal <資料夾>
  uv run scripts/blind.py serve <資料夾>
  uv run scripts/blind.py verify <資料夾>
  uv run scripts/blind.py shots <資料夾>
  uv run scripts/blind.py choose <資料夾> --phase gray --pick B [--rank B,A,C] [--note …]
  uv run scripts/blind.py reveal <資料夾> [--force]
  uv run scripts/blind.py stop <資料夾>
  uv run scripts/blind.py --selftest
"""
import argparse
import base64
import contextlib
import hashlib
import http.client
import io
import json
import os
import re
import secrets
import shutil
import signal
import socket
import string
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MARK = "data-omnikit-gray"
GRAY_CSS = "html{filter:grayscale(1)!important}"
PHASES = {"gray": "灰階（版面與操作）", "color": "彩色（只評配色）"}
SIZES = {"桌機": "1440,1800", "手機": "375,812"}
MIN_SCORE = 0.5    # 回應跟自己的檔至少這麼像
MIN_MARGIN = 0.02  # 而且要比第二像的版本高出這麼多
REF_LABEL = "原版"


# ---------- 檔案 ----------

def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def write_json(path, doc):
    Path(path).write_bytes((json.dumps(doc, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))


def load_spec(folder):
    spec = read_json(Path(folder) / "spec.json")
    if not isinstance(spec, dict) or not isinstance(spec.get("versions"), dict) or len(spec["versions"]) < 2:
        raise SystemExit(f"{folder}\\spec.json 要有 versions，至少兩個版本")
    for name, v in spec["versions"].items():
        if not isinstance(v, dict) or not v.get("dir") or not v.get("cmd"):
            raise SystemExit(f"版本 {name} 要有 dir 與 cmd")
        if not Path(v["dir"]).is_dir():
            raise SystemExit(f"版本 {name} 的資料夾不存在：{v['dir']}")
    ref = spec.get("reference")
    if ref is not None and ref not in spec["versions"]:
        raise SystemExit(f"reference「{ref}」不在 versions 裡")
    if len([n for n in spec["versions"] if n != ref]) < 2:
        raise SystemExit("要蒙的版本至少兩個（reference 不算）")
    spec.setdefault("path", "/")
    spec.setdefault("fingerprint", [{"path": spec["path"], "file": "index.html"}])
    spec.setdefault("phases", ["gray", "color"])
    if not set(spec["phases"]) <= set(PHASES):
        raise SystemExit(f"phases 只能是 {', '.join(PHASES)}")
    return spec


# ---------- 封存 ----------

def seal(folder, rng=None):
    folder = Path(folder)
    spec = load_spec(folder)
    if (folder / "sealed.json").exists():
        raise SystemExit("已經封存過了；要重來先刪掉 sealed.json、seal.sha256、choices.json")
    rng = rng or secrets.SystemRandom()
    names = [n for n in spec["versions"] if n != spec.get("reference")]
    rng.shuffle(names)
    labels = list(string.ascii_uppercase[:len(names)])
    mapping = dict(zip(labels, names))
    if spec.get("reference"):
        mapping[REF_LABEL] = spec["reference"]
    raw = json.dumps({"nonce": secrets.token_hex(16), "mapping": mapping}, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    write_json(folder / "sealed.json", {"labels": [*labels, *([REF_LABEL] if spec.get("reference") else [])],
                                        "sealed": base64.b64encode(raw).decode("ascii")})
    (folder / "seal.sha256").write_text(digest + "\n", encoding="utf-8")
    print(f"封存好了：標籤 {'、'.join(labels)}" + (f"，另有{REF_LABEL}（不蒙）" if spec.get("reference") else "") + f"。SHA-256 {digest}")
    return labels, digest


def unseal(folder):
    """回傳（對照表, 雜湊）；雜湊對不上就停。"""
    folder = Path(folder)
    doc = read_json(folder / "sealed.json")
    if not doc:
        raise SystemExit("還沒封存：先跑 seal")
    raw = base64.b64decode(doc["sealed"])
    digest = hashlib.sha256(raw).hexdigest()
    want = (folder / "seal.sha256").read_text(encoding="utf-8").strip() if (folder / "seal.sha256").exists() else ""
    if digest != want:
        raise SystemExit("對照表的雜湊跟封存時不一樣：sealed.json 被改過，這次盲選不算")
    return json.loads(raw)["mapping"], digest


# ---------- 灰階 ----------

def nonce_of(csp, body):
    m = re.search(r"style-src[^;]*'nonce-([^']+)'", csp or "") or re.search(r"default-src[^;]*'nonce-([^']+)'", csp or "")
    if m:
        return m.group(1)
    m = re.search(r"<style[^>]*\snonce=\"([^\"]+)\"", body) or re.search(r"\snonce=\"([^\"]+)\"", body)
    return m.group(1) if m else None


def inject(body, csp=""):
    nonce = nonce_of(csp, body)
    attr = ' nonce="' + nonce + '"' if nonce else ""
    tag = f"<style {MARK}{attr}>{GRAY_CSS}</style>"
    if re.search(r"</head>", body, re.I):
        return re.sub(r"</head>", lambda _m: tag + "</head>", body, count=1, flags=re.I)
    return tag + body


def strip_gray(body):
    return re.sub(rf"<style {MARK}[^>]*>[^<]*</style>", "", body)


HOP = {"connection", "keep-alive", "transfer-encoding", "te", "trailer", "upgrade", "proxy-authorization", "proxy-authenticate"}


def gray_handler(target):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_a):
            pass

        def _go(self):
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = {k: v for k, v in self.headers.items() if k.lower() not in HOP | {"host", "accept-encoding"}}
            headers["Host"] = f"127.0.0.1:{target}"
            headers["Accept-Encoding"] = "identity"
            try:
                conn = http.client.HTTPConnection("127.0.0.1", target, timeout=60)
                conn.request(self.command, self.path, body=body, headers=headers)
                r = conn.getresponse()
            except OSError as e:
                self.send_response(502)
                data = f"灰階轉送連不到原本的服務：{e}".encode("utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            out = [(k, v) for k, v in r.getheaders() if k.lower() not in HOP | {"content-length"}]
            if "text/html" in (r.getheader("Content-Type") or "") and self.command != "HEAD":
                data = inject(r.read().decode("utf-8", "replace"), r.getheader("Content-Security-Policy") or "").encode("utf-8")
                self.send_response(r.status)
                for k, v in out:
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:  # 其他照原樣轉，分段送（事件串流也能過）
                self.send_response(r.status)
                for k, v in out:
                    self.send_header(k, v)
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                if self.command != "HEAD":
                    while chunk := r.read1(65536):
                        self.wfile.write(chunk)
                        self.wfile.flush()
            conn.close()

        do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _go

    return Handler


# ---------- 開站 ----------

def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_port(port, seconds):
    end = time.time() + seconds
    while time.time() < end:
        with contextlib.suppress(OSError), socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
        time.sleep(0.3)
    return False


def kill_tree(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
    else:
        with contextlib.suppress(OSError):
            os.killpg(pid, signal.SIGTERM)


class Session:
    """開好的服務：每個標籤一個版本的服務加一個灰階轉送。"""

    def __init__(self, folder, spec, mapping):
        self.folder, self.spec, self.mapping = Path(folder), spec, mapping
        self.procs, self.proxies, self.urls, self.ports = [], [], {}, {}

    def start(self, timeout=90):
        logs = self.folder / "logs"
        logs.mkdir(exist_ok=True)
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        for label in sorted(self.mapping):
            v = self.spec["versions"][self.mapping[label]]
            port = free_port()
            env = {**os.environ, **{k: str(x) for k, x in (v.get("env") or {}).items()}}
            if v.get("port_env"):
                env[v["port_env"]] = str(port)
            cmd = [str(c).replace("{port}", str(port)) for c in v["cmd"]]
            exe = shutil.which(cmd[0]) or cmd[0]
            log = (logs / f"{label}.log").open("wb")
            p = subprocess.Popen([exe, *cmd[1:]], cwd=v["dir"], env=env, stdin=subprocess.PIPE, stdout=log, stderr=log,
                                 creationflags=flags, start_new_session=os.name != "nt")
            self.procs.append(p)
            self.ports[label] = port
        for label, port in self.ports.items():
            if not wait_port(port, timeout):
                self.close()
                raise SystemExit(f"標籤 {label} 的服務 {timeout} 秒內沒有開起來（看 logs\\{label}.log）")
            gport = free_port()
            srv = ThreadingHTTPServer(("127.0.0.1", gport), gray_handler(port))
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            self.proxies.append(srv)
            path = self.spec["path"]
            self.urls[label] = {"color": f"http://127.0.0.1:{port}{path}", "gray": f"http://127.0.0.1:{gport}{path}"}
        return self.urls

    def alive(self):
        return all(p.poll() is None for p in self.procs)

    def close(self):
        for srv in self.proxies:
            srv.shutdown()
            srv.server_close()
        for p in self.procs:
            if p.poll() is None:
                kill_tree(p.pid)
        for p in self.procs:
            with contextlib.suppress(Exception):
                p.wait(timeout=10)
        self.procs, self.proxies = [], []


# ---------- 檢查 ----------

def fetch(url, timeout=30):
    m = re.match(r"http://([^:/]+):(\d+)(/.*)?$", url)
    conn = http.client.HTTPConnection(m.group(1), int(m.group(2)), timeout=timeout)
    try:
        conn.request("GET", m.group(3) or "/", headers={"Accept-Encoding": "identity"})
        r = conn.getresponse()
        return r.status, r.read().decode("utf-8", "replace")
    except OSError as e:
        return None, str(e)
    finally:
        conn.close()


def lines_of(text):
    return {x.strip() for x in text.splitlines() if x.strip()}


def similarity(a, b):
    a, b = lines_of(a), lines_of(b)
    return len(a & b) / len(a | b) if a | b else 1.0


def with_path(url, path):
    return re.sub(r"^(http://[^/]+).*$", r"\1", url) + path


def verify(spec, mapping, urls):
    """回傳問題清單（空的就是通過）。訊息只寫標籤。"""
    problems = []
    files = {}
    for fp in spec["fingerprint"]:
        for name, v in spec["versions"].items():
            try:
                files[(fp["path"], name)] = (Path(v["dir"]) / fp["file"]).read_text(encoding="utf-8", errors="replace")
            except OSError:
                problems.append(f"有一個版本找不到用來比對的檔 {fp['file']}")
                return problems
        names = list(spec["versions"])
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if files[(fp["path"], a)] == files[(fp["path"], b)]:
                    problems.append(f"有兩個版本的 {fp['file']} 一模一樣，盲選沒有意義（可能是執行沒有改到東西）")
    if problems:
        return problems
    bodies = {}
    for label in sorted(urls):
        for fp in spec["fingerprint"]:
            color_url, gray_url = with_path(urls[label]["color"], fp["path"]), with_path(urls[label]["gray"], fp["path"])
            cs, color = fetch(color_url)
            gs, gray = fetch(gray_url)
            if cs != 200 or gs != 200:
                problems.append(f"標籤 {label}：{fp['path']} 回應 {cs}／灰階 {gs}，不是 200")
                continue
            if MARK in color:
                problems.append(f"標籤 {label}：彩色網址帶了灰階樣式（網址對調了）")
            if MARK not in gray:
                problems.append(f"標籤 {label}：灰階網址沒有插進灰階樣式")
            elif similarity(strip_gray(gray), color) < 0.9:
                problems.append(f"標籤 {label}：灰階與彩色的內容不一樣（灰階轉送接到別的服務了）")
            scores = {name: similarity(color, files[(fp["path"], name)]) for name in spec["versions"]}
            own = scores[mapping[label]]
            rest = max(s for n, s in scores.items() if n != mapping[label])
            if own < MIN_SCORE or own - rest < MIN_MARGIN:
                problems.append(f"標籤 {label}：{fp['path']} 的回應不像它該有的版本（相似度 {own:.2f}，"
                                f"另一個版本 {rest:.2f}）：網址可能接到別的版本或舊的服務")
            bodies.setdefault(fp["path"], {})[label] = color
    for path, by in bodies.items():
        seen = {}
        for label, body in by.items():
            if body in seen:
                problems.append(f"標籤 {seen[body]} 與 {label}：{path} 的回應一模一樣")
            seen.setdefault(body, label)
    return problems


# ---------- 指令 ----------

def serve(folder, timeout=90, once=False):
    folder = Path(folder)
    spec = load_spec(folder)
    mapping, digest = unseal(folder)
    run = read_json(folder / "run.json", {})
    if run.get("pid") and run.get("pid") != os.getpid() and pid_alive(run["pid"]):
        raise SystemExit(f"這個資料夾的服務已經開著（pid {run['pid']}）：先 stop")
    with contextlib.suppress(OSError):
        (folder / "stop").unlink()
    s = Session(folder, spec, mapping)
    urls = s.start(timeout)
    problems = verify(spec, mapping, urls)
    if problems:
        s.close()
        print("網址檢查沒過，已經全部關掉，不要給使用者看：\n" + "\n".join(f"- {p}" for p in problems))
        return 1
    write_json(folder / "run.json", {"pid": os.getpid(), "started": datetime.now().isoformat(timespec="seconds"),
                                     "seal": digest, "urls": urls})
    print(f"網址檢查通過（每個標籤都回應它該有的版本）。封存 SHA-256 {digest[:16]}…")
    for label in sorted(urls, key=lambda x: (x == REF_LABEL, x)):
        print(f"- {label}：灰階 {urls[label]['gray']}　彩色 {urls[label]['color']}")
    order = "先只看灰階，評版面與操作；選完再看彩色，只評配色。" if spec["phases"] == ["gray", "color"] else ""
    print(f"{order}選完用 choose 記下，每一段都記了才 reveal。關掉：blind.py stop {folder}", flush=True)
    if once:
        s.close()
        return 0
    try:
        while s.alive() and not (folder / "stop").exists():
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        s.close()
        with contextlib.suppress(OSError):
            (folder / "stop").unlink()
    return 0


def verify_cmd(folder):
    folder = Path(folder)
    spec = load_spec(folder)
    mapping, _ = unseal(folder)
    run = read_json(folder / "run.json", {})
    if not run.get("urls") or not pid_alive(run.get("pid")):
        print("服務沒有開著：先 serve")
        return 1
    problems = verify(spec, mapping, run["urls"])
    print("通過：每個標籤都回應它該有的版本。" if not problems else "沒過：\n" + "\n".join(f"- {p}" for p in problems))
    return 1 if problems else 0


def pid_alive(pid):
    if not pid:
        return False
    if os.name == "nt":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, errors="replace")
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def stop(folder):
    folder = Path(folder)
    run = read_json(folder / "run.json", {})
    if not pid_alive(run.get("pid")):
        print("沒有開著的服務。")
        return 0
    (folder / "stop").write_text("stop\n", encoding="utf-8")
    for _ in range(20):
        if not pid_alive(run["pid"]):
            break
        time.sleep(0.5)
    else:
        kill_tree(run["pid"])
    print("已經關掉。")
    return 0


def chrome():
    for c in (os.environ.get("CHROME"), r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", shutil.which("google-chrome"),
              shutil.which("chromium"), shutil.which("chrome")):
        if c and Path(c).exists():
            return c
    return None


def shots(folder):
    folder = Path(folder)
    run = read_json(folder / "run.json", {})
    if not run.get("urls") or not pid_alive(run.get("pid")):
        print("服務沒有開著：先 serve")
        return 1
    exe = chrome()
    if not exe:
        print("找不到 Chrome 或 Edge（可以設 CHROME 環境變數）")
        return 1
    out = folder / "shots"
    out.mkdir(exist_ok=True)
    for label, u in run["urls"].items():
        for tone in ("gray", "color"):
            for kind, size in SIZES.items():
                f = out / f"{label}-{tone}-{kind}.png"
                subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", f"--screenshot={f}",
                                f"--window-size={size}", "--virtual-time-budget=5000", u[tone]], capture_output=True, timeout=120)
    print(f"截圖在 {out}（檔名只有標籤）。")
    return 0


def choose(folder, phase, pick, rank=None, note=None):
    folder = Path(folder)
    spec = load_spec(folder)
    labels = read_json(folder / "sealed.json", {}).get("labels") or []
    if not labels:
        raise SystemExit("還沒封存：先跑 seal")
    if phase not in spec["phases"]:
        raise SystemExit(f"這次的階段是 {'、'.join(spec['phases'])}")
    if pick != "tie" and pick not in labels:
        raise SystemExit(f"「{pick}」不是這次的標籤（{'、'.join(labels)}，或 tie）")
    rank = [x.strip() for x in rank.split(",")] if rank else []
    if any(x not in labels for x in rank):
        raise SystemExit(f"排序裡有不是這次的標籤：{'、'.join(x for x in rank if x not in labels)}")
    doc = read_json(folder / "choices.json", {"choices": []})
    if (folder / "result.json").exists():
        raise SystemExit("已經解封了，不能再改選擇")
    seal_hash = (folder / "seal.sha256").read_text(encoding="utf-8").strip()
    doc["choices"] = [c for c in doc["choices"] if c["phase"] != phase]
    doc["choices"].append({"phase": phase, "pick": pick, "rank": rank, "note": note or "", "seal": seal_hash,
                           "at": datetime.now().isoformat(timespec="seconds")})
    write_json(folder / "choices.json", doc)
    left = [p for p in spec["phases"] if p not in {c["phase"] for c in doc["choices"]}]
    print(f"記下了：{PHASES[phase]}選 {pick}。" + (f"還沒選：{'、'.join(PHASES[p] for p in left)}。" if left else "每一段都選了，可以 reveal。"))
    return 0


def reveal(folder, force=False):
    folder = Path(folder)
    spec = load_spec(folder)
    mapping, digest = unseal(folder)
    choices = read_json(folder / "choices.json", {"choices": []})["choices"]
    left = [p for p in spec["phases"] if p not in {c["phase"] for c in choices}]
    if left and not force:
        print(f"還沒選：{'、'.join(PHASES[p] for p in left)}。選完才解封（真的要先看就加 --force，會記下來）。")
        return 1
    stale = [c["phase"] for c in choices if c.get("seal") != digest]
    if stale:
        print(f"這幾段的選擇是在另一次封存下做的：{'、'.join(stale)}，不算。")
        return 1
    name = lambda x: mapping.get(x, x)  # noqa: E731
    result = {"title": spec.get("title"), "seal": digest, "mapping": mapping, "forced": bool(left),
              "revealed": datetime.now().isoformat(timespec="seconds"),
              "choices": [{**c, "pick_name": "tie" if c["pick"] == "tie" else name(c["pick"]),
                           "rank_names": [name(x) for x in c["rank"]]} for c in choices]}
    write_json(folder / "result.json", result)
    print(f"解封（SHA-256 {digest} 比對相符）" + ("，強制解封：有階段還沒選" if left else "") + "：")
    for label in sorted(mapping, key=lambda x: (x == REF_LABEL, x)):
        print(f"- {label} = {mapping[label]}")
    for c in result["choices"]:
        print(f"- {PHASES[c['phase']]}：選 {c['pick']}（{c['pick_name']}）"
              + (f"，排序 {' > '.join(c['rank_names'])}" if c["rank_names"] else "") + (f"。{c['note']}" if c["note"] else ""))
    return 0


# ---------- 自我測試 ----------

def selftest():
    failures = []

    def ok(cond, msg):
        if not cond:
            failures.append(msg)

    def quiet(fn, *a, **kw):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                rc = fn(*a, **kw)
            except SystemExit as e:
                return f"exit:{e}", buf.getvalue()
        return rc, buf.getvalue()

    # 灰階：nonce 從 CSP 標頭、從頁面、沒有；沒有 </head> 也要插
    page = '<html><head><style nonce="pg">a{}</style></head><body>x</body></html>'
    ok('nonce="hd"' in inject(page, "default-src 'self'; style-src 'self' 'nonce-hd'"), "CSP 標頭的 nonce 沒用上")
    ok('nonce="pg"' in inject(page), "頁面自己的 nonce 沒用上")
    ok("nonce" not in inject("<html><head></head></html>").split(MARK)[1].split(">")[0], "沒有 nonce 時不該帶 nonce")
    ok(inject("<p>x</p>").startswith(f"<style {MARK}"), "沒有 </head> 也要插在最前面")
    ok(strip_gray(inject(page)) == page, "拿掉灰階樣式之後要跟原本一樣")
    ok(inject(page).index(MARK) < inject(page).index("</head>"), "灰階樣式要插在 </head> 前面")

    # 兩個版本很像（只差幾行）：接錯的那個相似度也很高，要靠差距抓
    shared = "\n".join(f"<li>{i}</li>" for i in range(60))
    near = {"p": shared + "\n<b>甲</b>\n<b>甲2</b>", "q": shared + "\n<b>乙</b>\n<b>乙2</b>"}
    with tempfile.TemporaryDirectory() as td:
        for n, body in near.items():
            (Path(td) / n).mkdir()
            (Path(td) / n / "index.html").write_text(body, encoding="utf-8")
        nspec = {"versions": {n: {"dir": str(Path(td) / n), "cmd": ["x"]} for n in near}, "fingerprint": [{"path": "/", "file": "index.html"}]}
        served = {"http://h:1/": near["p"], "http://h:2/": near["q"],
                  "http://h:3/": inject(near["p"]), "http://h:4/": inject(near["q"])}
        real = globals()["fetch"]
        globals()["fetch"] = lambda url, timeout=30: (200, served[url])
        try:
            right = {"A": {"color": "http://h:1/", "gray": "http://h:3/"}, "B": {"color": "http://h:2/", "gray": "http://h:4/"}}
            wrong = {"A": {"color": "http://h:2/", "gray": "http://h:4/"}, "B": {"color": "http://h:1/", "gray": "http://h:3/"}}
            ok(verify(nspec, {"A": "p", "B": "q"}, right) == [], "很像的兩個版本：網址對的要通過")
            ok(len(verify(nspec, {"A": "p", "B": "q"}, wrong)) == 2, "很像的兩個版本：網址對調要靠差距抓到")
        finally:
            globals()["fetch"] = real
    ok(similarity("a\nb\nc", "a\nb\nc") == 1.0 and similarity("a\nb", "c\nd") == 0.0, "相似度算錯")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        common = "\n".join(f"<div>共同的第 {i} 行</div>" for i in range(30))
        for name, extra in (("old", "舊工具"), ("new", "新工具"), ("base", "原本")):
            d = root / "v" / name
            d.mkdir(parents=True)
            body = "\n".join(f"<p>{extra} 第 {i} 段</p>" for i in range(20))
            (d / "index.html").write_text(f"<html><head><title>t</title></head><body>\n{common}\n{body}\n</body></html>",
                                          encoding="utf-8")
            (d / "app.css").write_text(f"/* {name} */ body{{margin:0}}", encoding="utf-8")
        cmd = [sys.executable, "-m", "http.server", "{port}", "--bind", "127.0.0.1"]
        f = root / "blind"
        f.mkdir()
        write_json(f / "spec.json", {"title": "測試", "reference": "base",
                                     "versions": {n: {"dir": str(root / "v" / n), "cmd": cmd} for n in ("old", "new", "base")}})
        rc, out = quiet(seal, f)
        labels = read_json(f / "sealed.json")["labels"]
        ok(labels == ["A", "B", REF_LABEL], f"標籤不對：{labels}")
        raw = (f / "sealed.json").read_text(encoding="utf-8")
        ok("old" not in raw and "new" not in out and "old" not in out, "封存檔或輸出看得到版本名稱")
        ok(len((f / "seal.sha256").read_text().strip()) == 64, "沒有寫 SHA-256")
        ok(str(quiet(seal, f)[0]).startswith("exit:"), "重複封存要擋下來")
        mapping, digest = unseal(f)
        ok(set(mapping.values()) == {"old", "new", "base"} and mapping[REF_LABEL] == "base", "對照表不對")
        # 隨機：多封幾次，兩種排法都會出現
        seen = set()
        for i in range(30):
            g = root / f"r{i}"
            g.mkdir()
            shutil.copy(f / "spec.json", g / "spec.json")
            quiet(seal, g)
            seen.add(unseal(g)[0]["A"])
        ok(seen == {"old", "new"}, f"標籤沒有隨機：{seen}")

        spec = load_spec(f)
        s = Session(f, spec, mapping)
        try:
            urls = s.start(timeout=30)
            ok(set(urls) == {"A", "B", REF_LABEL}, "每個標籤都要有網址")
            ports = {u["color"] for u in urls.values()} | {u["gray"] for u in urls.values()}
            ok(len(ports) == 6, "每個網址都要是不同的 port")
            problems = verify(spec, mapping, urls)
            ok(problems == [], f"正確的網址被判沒過：{problems}")
            st, css = fetch(with_path(urls["A"]["gray"], "/app.css"))
            ok(st == 200 and MARK not in css and css.startswith("/*"), "非 HTML 的檔要照原樣轉送")
            # 第三輪的疏失：網址對調
            swapped = {**urls, "A": urls["B"], "B": urls["A"]}
            bad = verify(spec, mapping, swapped)
            ok(any("標籤 A" in p for p in bad) and any("標籤 B" in p for p in bad), f"網址對調沒抓到：{bad}")
            ok(not any(n in p for p in bad for n in ("old", "new")), "檢查訊息不能洩漏版本名稱")
            # 灰階與彩色對調、灰階接到別的服務
            flip = {**urls, "A": {"color": urls["A"]["gray"], "gray": urls["A"]["color"]}}
            ok(any("彩色網址帶了灰階" in p for p in verify(spec, mapping, flip)), "灰階彩色對調沒抓到")
            cross = {**urls, "A": {"color": urls["A"]["color"], "gray": urls["B"]["gray"]}}
            ok(any("灰階與彩色的內容不一樣" in p for p in verify(spec, mapping, cross)), "灰階接錯服務沒抓到")
            # 版本內容一樣
            same = json.loads(json.dumps(spec))
            same["versions"]["new"] = dict(same["versions"]["old"])
            ok(any("一模一樣" in p for p in verify(same, mapping, urls)), "兩個版本一樣沒擋下來")
        finally:
            s.close()
        ok(all(p.poll() is not None for p in s.procs) or not s.procs, "關掉後服務還在")
        dead = verify(spec, mapping, urls)
        ok(dead and all("不是 200" in p for p in dead), f"服務關掉之後要判沒過：{dead}")

        # 選擇與解封
        rc, out = quiet(reveal, f)
        ok(rc == 1 and not (f / "result.json").exists(), "還沒選就解封了")
        ok(str(quiet(choose, f, "gray", "Z")[0]).startswith("exit:"), "不存在的標籤要擋下來")
        ok(str(quiet(choose, f, "gray", "A", rank="A,Q")[0]).startswith("exit:"), "排序裡不存在的標籤要擋下來")
        quiet(choose, f, "gray", "A", rank=f"A,{REF_LABEL},B")
        rc, out = quiet(reveal, f)
        ok(rc == 1 and "彩色" in out, "只選了灰階就解封了")
        quiet(choose, f, "color", "tie")
        rc, out = quiet(reveal, f)
        res = read_json(f / "result.json")
        ok(rc == 0 and res and res["choices"][0]["pick_name"] == mapping["A"] and not res["forced"], f"解封結果不對：{out}")
        ok(res["choices"][0]["rank_names"] == [mapping["A"], "base", mapping["B"]], "排序沒換成名稱")
        ok(str(quiet(choose, f, "color", "B")[0]).startswith("exit:"), "解封後還能改選擇")
        # 強制解封會記下來
        g = root / "r0"
        quiet(choose, g, "gray", "B")
        rc, _ = quiet(reveal, g, force=True)
        ok(rc == 0 and read_json(g / "result.json")["forced"] is True, "強制解封沒有記下來")
        # 封存被改過
        h = root / "r1"
        doc = read_json(h / "sealed.json")
        raw = json.loads(base64.b64decode(doc["sealed"]))
        raw["mapping"]["A"], raw["mapping"]["B"] = raw["mapping"]["B"], raw["mapping"]["A"]
        doc["sealed"] = base64.b64encode(json.dumps(raw).encode()).decode()
        write_json(h / "sealed.json", doc)
        ok(str(quiet(unseal, h)[0]).startswith("exit:"), "對照表被改過沒抓到")
        # 選擇是在另一次封存下做的
        k = root / "r2"
        quiet(choose, k, "gray", "A")
        quiet(choose, k, "color", "A")
        c = read_json(k / "choices.json")
        c["choices"][0]["seal"] = "0" * 64
        write_json(k / "choices.json", c)
        ok(quiet(reveal, k)[0] == 1, "另一次封存的選擇被算進去了")
        # spec 的檢查
        bad_spec = root / "bad"
        bad_spec.mkdir()
        write_json(bad_spec / "spec.json", {"versions": {"x": {"dir": str(root), "cmd": ["x"]}, "y": {"dir": str(root), "cmd": ["y"]}},
                                            "reference": "x"})
        ok(str(quiet(seal, bad_spec)[0]).startswith("exit:"), "reference 之外只有一個版本要擋下來")

    if failures:
        print("自我測試失敗：\n" + "\n".join(f"- {x}" for x in failures))
        return 1
    print("blind.py 自我測試通過")
    return 0


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--selftest"]:
        return selftest()
    ap = argparse.ArgumentParser(description="盲選：隨機標籤、封存、灰階轉送、網址檢查、選完才解封")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("seal", "serve", "verify", "shots", "reveal", "stop"):
        p = sub.add_parser(name)
        p.add_argument("folder")
        if name == "serve":
            p.add_argument("--timeout", type=int, default=90)
            p.add_argument("--once", action="store_true", help="檢查完就關掉（只確認開得起來）")
        if name == "reveal":
            p.add_argument("--force", action="store_true")
    p = sub.add_parser("choose")
    p.add_argument("folder")
    p.add_argument("--phase", required=True, choices=list(PHASES))
    p.add_argument("--pick", required=True)
    p.add_argument("--rank")
    p.add_argument("--note")
    a = ap.parse_args(argv)
    if a.cmd == "seal":
        seal(a.folder)
        return 0
    if a.cmd == "serve":
        return serve(a.folder, a.timeout, a.once)
    if a.cmd == "verify":
        return verify_cmd(a.folder)
    if a.cmd == "shots":
        return shots(a.folder)
    if a.cmd == "choose":
        return choose(a.folder, a.phase, a.pick, a.rank, a.note)
    if a.cmd == "reveal":
        return reveal(a.folder, a.force)
    return stop(a.folder)


if __name__ == "__main__":
    sys.exit(main())
