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


PAGE = r"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Server Control</title>
<style>
:root{--r:#ff2e55;--b:#2e8bff;--t:#eef2ff;--m:#97a3c4}
*{box-sizing:border-box}
body{margin:0;background:#03040a;color:var(--t);font:15px system-ui,sans-serif;min-height:100vh}
.bg{position:fixed;inset:0;z-index:-1;overflow:hidden}
.bg i{position:absolute;width:70vmax;height:70vmax;border-radius:50%;animation:drift 14s ease-in-out infinite alternate}
.bg i:first-child{background:radial-gradient(circle,#ff2e5540,transparent 65%);top:-25vmax;left:-30vmax}
.bg i:last-child{background:radial-gradient(circle,#2e8bff40,transparent 65%);bottom:-25vmax;right:-30vmax;animation-delay:-7s}
@keyframes drift{to{transform:translate(18vw,12vh) scale(1.15)}}
main{max-width:720px;margin:auto;padding:16px}
h1{margin:8px 0 2px;font-size:25px;letter-spacing:2px;background:linear-gradient(90deg,var(--r),var(--b),var(--r));background-size:200%;-webkit-background-clip:text;background-clip:text;color:transparent;animation:flow 4s linear infinite}
@keyframes flow{to{background-position:200%}}
.sub{color:var(--m);font-size:12px}
.card{position:relative;margin:14px 0;padding:14px;border-radius:16px;border:1.5px solid transparent;background:linear-gradient(#090b16,#090b16) padding-box,linear-gradient(120deg,var(--r),#1a1d33,var(--b),var(--r)) border-box;background-size:100%,300%;animation:in .6s both,edge 7s linear infinite}
.card:nth-of-type(2){animation-delay:.1s,0s}.card:nth-of-type(3){animation-delay:.2s,0s}.card:nth-of-type(4){animation-delay:.3s,0s}
@keyframes in{from{opacity:0;transform:translateY(24px)}}
@keyframes edge{to{background-position:0 0,300% 0}}
h2{margin:0 0 10px;font-size:16px;color:#cfe0ff}
.status{display:flex;align-items:center;gap:12px;font-size:17px;font-weight:600}
.dot{flex:none;width:14px;height:14px;border-radius:50%;background:var(--r);box-shadow:0 0 12px var(--r)}
.on .dot{background:var(--b);box-shadow:0 0 12px var(--b);animation:pulse 1.4s infinite}
@keyframes pulse{50%{transform:scale(1.35);opacity:.6}}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}
button{border:0;border-radius:10px;padding:11px 15px;min-height:42px;color:#fff;font:600 14px system-ui;cursor:pointer;background:linear-gradient(120deg,#c4123a,#1858c9);background-size:160%;transition:transform .15s,box-shadow .25s,background-position .4s}
button:hover{transform:translateY(-2px);box-shadow:0 0 18px #2e8bff88;background-position:100%}
button:active{transform:scale(.94)}
button.red{background:#c4123a}button.blue{background:#1858c9}
button.ghost{background:#141830;border:1px solid #303a66}
button:focus-visible,input:focus,textarea:focus{outline:2px solid var(--b);outline-offset:2px}
input,textarea{width:100%;background:#04050c;color:var(--t);border:1px solid #303a66;border-radius:10px;padding:11px;font:inherit}
textarea{font:13px ui-monospace,monospace}
.send{display:flex;gap:8px;margin-top:10px}
#log{height:300px;overflow:auto;margin:0;padding:10px;border-radius:10px;background:#010207;border:1px solid #222a50;font:12px/1.6 ui-monospace,monospace;white-space:pre-wrap;word-break:break-word}
#log div{animation:line .25s both}
@keyframes line{from{opacity:0;transform:translateX(-8px)}}
.err{color:#ff6b85}.warn{color:#ffc46b}.ok{color:#6fb2ff}
.plug{justify-content:space-between;padding:8px 10px;border:1px solid #222a50;border-radius:10px}
.plug span{word-break:break-all}
small{display:block;margin-top:8px;color:var(--m)}
#msg{position:sticky;bottom:12px;margin:auto;width:fit-content;max-width:100%;padding:10px 16px;border-radius:20px;background:#121735;border:1px solid var(--b);opacity:0;transform:translateY(20px);transition:.3s;pointer-events:none}
#msg.show{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>
<div class="bg" aria-hidden="true"><i></i><i></i></div>
<main>
<h1>SERVER CONTROL</h1><div class="sub">Minecraft server panel</div>
<section class="card"><div class="status" id="box"><span class="dot"></span><span id="st">Connecting...</span></div>
<div class="row"><button class="blue" onclick="act('/api/start',undefined,'Start requested')">&#9654; Start</button>
<button class="red" onclick="if(confirm('Stop the server?'))send('stop')">&#9632; Stop</button>
<button class="ghost" id="cp">Copy panel link</button></div></section>
<section class="card"><h2>Console</h2><div id="log" role="log"></div>
<form class="send" id="form"><input id="cmd" placeholder="Command, such as: list" aria-label="Command" autocomplete="off" autocapitalize="off"><button>Send</button></form>
<div class="row" id="quick"></div>
<div class="row"><button class="ghost" id="prev" type="button">&#8593; Last command</button></div></section>
<section class="card"><h2>Plugins</h2><div id="pl"></div>
<div class="row"><input type="file" id="file" accept=".jar" aria-label="Plugin file"><button onclick="upload()">Upload</button></div>
<small>Only add plugins you trust. Restart the server after changes.</small></section>
<section class="card"><h2>server.properties</h2><textarea id="props" rows="12" aria-label="Server settings" spellcheck="false"></textarea>
<div class="row"><button onclick="save()">Save</button><button class="ghost" onclick="loadProps()">Reload</button></div>
<small>Stop the server before saving, then start it again.</small></section>
<div id="msg" role="status"></div>
</main>
<script>
const $=id=>document.getElementById(id);
const cmd=$('cmd');
if(location.hash.length>1){sessionStorage.setItem('t',location.hash.slice(1));history.replaceState(null,'','/')}
const T=sessionStorage.getItem('t')||'';
async function api(p,o={}){o.headers={'X-Token':T};const r=await fetch(p,o);const j=await r.json();if(!r.ok)throw new Error(j.error);return j}
let timer;
function say(m){const e=$('msg');e.textContent=m;e.classList.add('show');clearTimeout(timer);timer=setTimeout(()=>e.classList.remove('show'),3500)}
async function act(p,body,done='Done'){try{await api(p,{method:'POST',body});say(done);refresh();return true}catch(e){say(e.message);return false}}
const send=c=>act('/api/command',c,'Sent: '+c);
const q=n=>encodeURIComponent(n);
const el=(tag,text,cls)=>{const e=document.createElement(tag);e.textContent=text;if(cls)e.className=cls;return e};
let last='';
$('form').onsubmit=async e=>{e.preventDefault();const c=cmd.value.trim();if(!c)return say('Type a command first');if(await send(c)){last=c;cmd.value=''}};
$('prev').onclick=()=>{if(!last)return say('No earlier command');cmd.value=last;cmd.focus()};
['list','save-all','tps','time set day','weather clear','help'].forEach(c=>{const b=el('button',c,'ghost');b.onclick=()=>send(c);$('quick').append(b)});
let shownLog=[],shown='';
const tone=l=>/ERROR|Exception|FATAL/.test(l)?'err':/WARN/.test(l)?'warn':/Done|joined the game/.test(l)?'ok':'';
function drawLog(lines){const box=$('log');if(lines.join('\n')===shownLog.join('\n'))return;
const bottom=box.scrollHeight-box.scrollTop-box.clientHeight<40;
let keep=0;for(let n=Math.min(shownLog.length,lines.length);n>0;n--){if(shownLog.slice(-n).join('\n')===lines.slice(0,n).join('\n')){keep=n;break}}
if(!keep)box.replaceChildren();else for(let i=shownLog.length-keep;i>0;i--)box.firstChild.remove();
lines.slice(keep).forEach(l=>box.append(el('div',l,tone(l))));shownLog=lines;if(bottom)box.scrollTop=box.scrollHeight}
async function refresh(){try{const s=await api('/api/status');
$('box').classList.toggle('on',s.running);
$('st').textContent=s.running?'Process running (check console for "Done")':'Server stopped';
drawLog(s.log);
const k=JSON.stringify(s.plugins);if(k!==shown){shown=k;$('pl').replaceChildren(...s.plugins.map(n=>{
const d=el('div','','row plug');
const a=el('button',n.endsWith('.disabled')?'Enable':'Disable','blue');a.onclick=()=>act('/api/toggle?name='+q(n));
const b=el('button','Delete','red');b.onclick=()=>{if(confirm('Delete '+n+'?'))act('/api/delete?name='+q(n))};
d.append(el('span',n),a,b);return d}));if(!s.plugins.length)$('pl').append(el('small','No plugins yet. Upload a .jar file.'))}
}catch(e){$('box').classList.remove('on');$('st').textContent=e.message}}
async function upload(){const f=$('file').files[0];if(!f)return say('Choose a .jar file first');say('Uploading...');await act('/api/upload?name='+q(f.name),f,'Uploaded')}
async function loadProps(){try{$('props').value=(await api('/api/props')).text}catch(e){say(e.message)}}
const save=()=>act('/api/props',$('props').value,'Settings saved');
$('cp').onclick=async()=>{const u=location.origin+'/#'+T;try{await navigator.clipboard.writeText(u);say('Link copied. Keep it private.')}catch(e){prompt('Copy this private link:',u)}};
async function loop(){if(!document.hidden)await refresh();setTimeout(loop,2000)}
loadProps();loop();
</script>
"""


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
