#!/usr/bin/env python3
"""Web control panel for the Paper server. Standard library only."""
import collections, hmac, json, os, re, secrets, shutil, signal, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(os.environ.get("MC_DIR", Path(__file__).resolve().parent))
PLUGINS = ROOT / "plugins"
PROPS = ROOT / "server.properties"
PORT = int(os.environ.get("PANEL_PORT", "8080"))
LAN = os.environ.get("PANEL_LAN") == "1"
JAVA = ["java", "-Xms1G", "-Xmx2G", "-XX:+UseG1GC", "-XX:+ParallelRefProcEnabled",
        "-XX:MaxGCPauseMillis=200", "-XX:+DisableExplicitGC",
        "-Djava.net.preferIPv4Stack=true", "-jar", "server.jar", "nogui"]
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+() -]{0,120}\.jar(\.disabled)?")
MAX_UPLOAD = 100 * 1024 * 1024

log = collections.deque(maxlen=300)
lock = threading.Lock()
proc = None


def load_token():
    f = ROOT / ".panel_token"
    if not f.exists():
        fd = os.open(f, os.O_WRONLY | os.O_CREAT, 0o600)
        with os.fdopen(fd, "w") as h:
            h.write(secrets.token_urlsafe(24))
    return f.read_text().strip()


TOKEN = load_token()


def running():
    return proc is not None and proc.poll() is None


def pump(p):
    for line in p.stdout:
        print(line, end="", flush=True)
        log.append(line.rstrip())


def start():
    global proc
    with lock:
        if running():
            return
        proc = subprocess.Popen(JAVA, cwd=ROOT, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, errors="replace",
                                bufsize=1, start_new_session=True)
        threading.Thread(target=pump, args=(proc,), daemon=True).start()


def command(text):
    text = text.replace("\r", " ").replace("\n", " ").strip()
    with lock:
        if not running():
            raise ValueError("Server is not running")
        if text:
            proc.stdin.write(text + "\n")
            proc.stdin.flush()


def plugin_path(name):
    if not NAME.fullmatch(name):
        raise ValueError("Use a simple .jar file name")
    return PLUGINS / name


PAGE = """<!doctype html><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Server panel</title>
<style>
body{background:#000;color:#eee;font:15px system-ui;margin:0 auto;max-width:700px;padding:16px}
h1,h2{color:#ff3b55;font-size:18px}
section{border:1px solid #7a0b1c;border-radius:12px;padding:12px;margin:12px 0}
button,input,textarea{background:#14040a;color:#fff;border:1px solid #ff1f3d;border-radius:8px;padding:10px;font:inherit}
textarea,#cmd{width:100%;box-sizing:border-box}
pre{height:280px;overflow:auto;white-space:pre-wrap;word-break:break-all;font-size:12px}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:6px 0}
</style>
<h1>Minecraft server panel</h1>
<section><div id="st">Connecting...</div><div class="row">
<button onclick="act('/api/start')">Start</button>
<button onclick="send('stop')">Stop</button>
<button id="cp">Copy panel link</button></div><div id="msg" role="status"></div></section>
<section><h2>Console</h2><pre id="log"></pre><input id="cmd" placeholder="Command, such as: list">
<button onclick="send(cmd.value);cmd.value=''">Send</button></section>
<section><h2>Plugins</h2><div id="pl"></div>
<div class="row"><input type="file" id="file" accept=".jar"><button onclick="upload()">Upload</button></div>
<small>Only add plugins you trust. Restart the server after changes.</small></section>
<section><h2>server.properties</h2><textarea id="props" rows="14"></textarea>
<div class="row"><button onclick="save()">Save</button><button onclick="loadProps()">Reload</button></div>
<small>Stop the server before saving, then start it again.</small></section>
<script>
const $=id=>document.getElementById(id);
const cmd=$('cmd');
if(location.hash.length>1){sessionStorage.setItem('t',location.hash.slice(1));history.replaceState(null,'','/')}
const T=sessionStorage.getItem('t')||'';
async function api(p,o={}){o.headers={'X-Token':T};const r=await fetch(p,o);const j=await r.json();if(!r.ok)throw new Error(j.error);return j}
const say=m=>$('msg').textContent=m;
async function act(p,body){try{await api(p,{method:'POST',body});say('Done');refresh();return true}catch(e){say(e.message);return false}}
const send=c=>act('/api/command',c);
const q=n=>encodeURIComponent(n);
let shown='';
async function refresh(){try{const s=await api('/api/status');
$('st').textContent=s.running?'Process running (check the console for "Done")':'Server stopped';
const l=$('log'),t=s.log.join('\\n');if(l.textContent!==t){l.textContent=t;l.scrollTop=l.scrollHeight}
const k=JSON.stringify(s.plugins);if(k!==shown){shown=k;$('pl').replaceChildren(...s.plugins.map(n=>{
const d=document.createElement('div');d.className='row';d.append(n);
const a=document.createElement('button');a.textContent=n.endsWith('.disabled')?'Enable':'Disable';a.onclick=()=>act('/api/toggle?name='+q(n));
const b=document.createElement('button');b.textContent='Delete';b.onclick=()=>{if(confirm('Delete '+n+'?'))act('/api/delete?name='+q(n))};
d.append(a,b);return d}))}}catch(e){$('st').textContent=e.message}}
async function upload(){const f=$('file').files[0];if(!f)return say('Choose a .jar file first');say('Uploading...');await act('/api/upload?name='+q(f.name),f)}
async function loadProps(){try{$('props').value=(await api('/api/props')).text}catch(e){say(e.message)}}
const save=()=>act('/api/props',$('props').value);
$('cp').onclick=async()=>{const u=location.origin+'/#'+T;try{await navigator.clipboard.writeText(u);say('Link copied. Keep it private.')}catch(e){prompt('Copy this private link:',u)}};
refresh();loadProps();setInterval(refresh,2000);
</script>"""


class Handler(BaseHTTPRequestHandler):
    timeout = 60

    def log_message(self, *args):
        pass

    def reply(self, code, data, kind="application/json"):
        body = data.encode() if isinstance(data, str) else json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", kind + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def authed(self):
        got = self.headers.get("X-Token", "").encode()
        return hmac.compare_digest(got, TOKEN.encode())

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self.reply(200, PAGE, "text/html")
        if not self.authed():
            return self.reply(401, {"error": "Open the full private link from Termux"})
        if path == "/api/status":
            names = sorted(p.name for p in PLUGINS.glob("*.jar*") if p.is_file())
            return self.reply(200, {"running": running(), "log": list(log), "plugins": names})
        if path == "/api/props":
            return self.reply(200, {"text": PROPS.read_text() if PROPS.exists() else ""})
        self.reply(404, {"error": "Not found"})

    def do_POST(self):
        if not self.authed():
            return self.reply(401, {"error": "Not authorized"})
        url = urlparse(self.path)
        name = parse_qs(url.query).get("name", [""])[0]
        try:
            size = int(self.headers.get("Content-Length") or 0)
            limit = MAX_UPLOAD if url.path == "/api/upload" else 64 * 1024
            if not 0 <= size <= limit:
                raise ValueError("Request is too large")
            if url.path == "/api/upload":
                self.upload(name, size)
            else:
                body = self.rfile.read(size).decode()
                if url.path == "/api/start":
                    start()
                elif url.path == "/api/command":
                    command(body)
                elif url.path == "/api/props":
                    if running():
                        raise ValueError("Stop the server before saving settings")
                    if not body.strip():
                        raise ValueError("Settings cannot be empty")
                    if PROPS.exists():
                        shutil.copy(PROPS, ROOT / "server.properties.bak")
                    PROPS.write_text(body)
                elif url.path == "/api/delete":
                    plugin_path(name).unlink()
                elif url.path == "/api/toggle":
                    src = plugin_path(name)
                    new = name[:-9] if name.endswith(".disabled") else name + ".disabled"
                    if (PLUGINS / new).exists():
                        raise ValueError("A file with that name already exists")
                    src.rename(PLUGINS / new)
                else:
                    return self.reply(404, {"error": "Not found"})
            self.reply(200, {"ok": True})
        except (ValueError, OSError) as e:
            self.reply(400, {"error": str(e)})

    def upload(self, name, size):
        dest = plugin_path(name)
        if not name.endswith(".jar") or dest.exists():
            raise ValueError("Needs a new .jar name. Delete the old file first")
        tmp = PLUGINS / ".upload.part"
        with open(tmp, "xb") as h:
            try:
                left = size
                while left:
                    chunk = self.rfile.read(min(left, 65536))
                    if not chunk:
                        raise ValueError("Upload was interrupted")
                    h.write(chunk)
                    left -= len(chunk)
                h.flush()
                tmp.rename(dest)
            finally:
                tmp.unlink(missing_ok=True)


def main():
    PLUGINS.mkdir(parents=True, exist_ok=True)
    (PLUGINS / ".upload.part").unlink(missing_ok=True)
    web = ThreadingHTTPServer(("0.0.0.0" if LAN else "127.0.0.1", PORT), Handler)
    web.daemon_threads = True

    def quit_panel(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, quit_panel)
    signal.signal(signal.SIGHUP, quit_panel)
    link = f"http://127.0.0.1:{PORT}/#{TOKEN}"
    start()
    threading.Thread(target=web.serve_forever, daemon=True).start()
    banner = f"\n=== PANEL LINK (keep private) ===\n{link}\n"
    if LAN:
        banner += "LAN mode: replace 127.0.0.1 with your phone's Wi-Fi IP. HTTP is not encrypted.\n"
    print(banner, flush=True)
    if shutil.which("termux-clipboard-set"):
        try:
            subprocess.run(["termux-clipboard-set"], input=link, text=True, timeout=5, check=True)
            print("Link copied to clipboard.", flush=True)
        except (subprocess.SubprocessError, OSError):
            print("Could not auto-copy. Copy the link by hand.", flush=True)
    try:
        # The terminal still accepts commands; "link" reprints the address.
        for line in sys.stdin:
            if line.strip() == "link":
                print(banner)
                continue
            try:
                command(line)
            except (ValueError, OSError) as e:
                print(e)
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        if running():
            print("Saving and stopping the server...")
            try:
                command("stop")
                proc.wait(timeout=90)
            except (ValueError, OSError, subprocess.TimeoutExpired):
                proc.terminate()
        web.shutdown()


if __name__ == "__main__":
    main()
