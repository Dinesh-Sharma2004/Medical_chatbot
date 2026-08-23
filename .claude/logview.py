"""Dev-only live log viewer for the MediBot backend.

Serves an auto-refreshing page that tails the backend log file, so backend
logs can be watched in the Browser pane without running any command.
Stdlib only. Not imported by the app; nothing here affects backend behavior.
"""

import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG_PATH = os.environ.get("MEDIBOT_LOG", "backend.log")
PORT = int(os.environ.get("MEDIBOT_LOGVIEW_PORT", "8765"))
MAX_LINES = 600

PAGE = """<!doctype html>
<meta charset="utf-8">
<title>MediBot backend logs</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; background: #0d1117; color: #c9d1d9;
         font: 12.5px/1.55 "Cascadia Code", Consolas, monospace; }
  header { position: sticky; top: 0; display: flex; gap: 12px; align-items: center;
           padding: 9px 14px; background: #161b22; border-bottom: 1px solid #30363d; }
  h1 { margin: 0; font-size: 13px; font-weight: 600; letter-spacing: .02em; }
  #dot { width: 8px; height: 8px; border-radius: 50%; background: #3fb950; }
  #dot.stale { background: #d29922; }
  #meta { margin-left: auto; color: #8b949e; font-size: 11.5px; }
  label { color: #8b949e; font-size: 11.5px; display: flex; gap: 5px; align-items: center; }
  pre { margin: 0; padding: 12px 14px; white-space: pre-wrap; word-break: break-word; }
  .err  { color: #ff7b72; font-weight: 600; }
  .warn { color: #d29922; }
  .tag  { color: #79c0ff; }
  .req  { color: #56d364; }
  .groq { color: #d2a8ff; }
</style>
<header>
  <span id="dot"></span>
  <h1>MediBot backend logs</h1>
  <label><input type="checkbox" id="follow" checked> follow</label>
  <label><input type="checkbox" id="only"> errors only</label>
  <span id="meta">connecting…</span>
</header>
<pre id="out">waiting for output…</pre>
<script>
const out = document.getElementById('out'), meta = document.getElementById('meta');
const dot = document.getElementById('dot'), follow = document.getElementById('follow');
const only = document.getElementById('only');
const esc = s => s.replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
function paint(line) {
  const h = esc(line);
  if (/ERROR|Traceback|Exception|CRITICAL/.test(line)) return `<span class="err">${h}</span>`;
  if (/WARNING|WARN/.test(line))                       return `<span class="warn">${h}</span>`;
  if (/\\[(VS|EMB|WARMUP|INGEST|RERANK)\\]/.test(line)) return `<span class="tag">${h}</span>`;
  if (/api\\.groq\\.com|\\[GROQ\\]|KEY_ROTATE/.test(line)) return `<span class="groq">${h}</span>`;
  if (/HTTP\\/1\\.1" \\d{3}/.test(line))                return `<span class="req">${h}</span>`;
  return h;
}
let last = '';
async function tick() {
  try {
    const r = await fetch('raw', { cache: 'no-store' });
    let text = await r.text();
    meta.textContent = r.headers.get('X-Log-Size') + ' bytes · ' + new Date().toLocaleTimeString();
    dot.className = text === last ? 'stale' : '';
    last = text;
    let lines = text.split('\\n');
    if (only.checked) lines = lines.filter(l => /ERROR|Traceback|Exception|WARNING|CRITICAL/.test(l));
    out.innerHTML = lines.length ? lines.map(paint).join('\\n') : '(no matching lines)';
    if (follow.checked) window.scrollTo(0, document.body.scrollHeight);
  } catch (e) {
    dot.className = 'stale';
    meta.textContent = 'log viewer unreachable';
  }
}
tick(); setInterval(tick, 1500);
</script>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, ctype: str, extra=None):
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0].rstrip("/")
        if path in ("", "/index.html"):
            self._send(PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/raw":
            try:
                with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()[-MAX_LINES:]
                body = "".join(lines).encode("utf-8")
                size = str(os.path.getsize(LOG_PATH))
            except FileNotFoundError:
                body = f"log file not created yet: {LOG_PATH}".encode("utf-8")
                size = "0"
            self._send(body, "text/plain; charset=utf-8", {"X-Log-Size": size})
            return
        self.send_error(404)

    def log_message(self, *args):
        pass  # keep the viewer's own access logs out of the terminal


if __name__ == "__main__":
    print(f"[logview] tailing {LOG_PATH}", flush=True)
    print(f"[logview] serving on http://127.0.0.1:{PORT}", flush=True)
    try:
        HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
