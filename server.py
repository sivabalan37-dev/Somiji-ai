#!/usr/bin/env python3
"""SOMIJI AI backend (Python 3.9+, standard library only).

Serves the web UI and relays chat requests to model providers. API keys are read
from the environment or a local .env file and are never sent to the browser."""
import json, mimetypes, os, time, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
MAX_BODY = 20_000_000
IMG = {"image/png", "image/jpeg", "image/gif", "image/webp"}
BASE = ("You are SOMIJI AI, a capable, friendly personal assistant. Be accurate and concise; "
        "put code in Markdown code blocks.")
CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
       "script-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")


def load_env():
    f = ROOT / ".env"
    if f.is_file():
        for line in f.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip("\"'"))


def names(var, default=""):
    return [x.strip() for x in os.environ.get(var, default).split(",") if x.strip()]


def catalog():
    c = {}
    if os.environ.get("ANTHROPIC_API_KEY"):
        c["anthropic"] = names("ANTHROPIC_MODELS", "claude-sonnet-5-5,claude-haiku-5-5")
    if os.environ.get("OPENAI_API_KEY"):
        c["openai"] = names("OPENAI_MODELS", "gpt-4o-mini")
    if os.environ.get("OLLAMA_MODELS"):
        c["ollama"] = names("OLLAMA_MODELS")
    c["demo"] = ["demo-echo"]  # no key needed; echoes your text (not a real AI)
    return c


def sse_data(resp):
    for raw in resp:
        line = raw.decode("utf-8", "replace").strip()
        if line.startswith("data:") and line[5:].strip() != "[DONE]":
            yield json.loads(line[5:])


def post(url, body, headers):
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json", **headers})
    return urllib.request.urlopen(req, timeout=120)


def demo(system, msgs):
    for w in f"[Demo mode, no AI connected] You said: {msgs[-1]['text']}".split(" "):
        yield w + " "
        time.sleep(0.03)


def anthropic(system, msgs, model):
    out = []
    for m in msgs:
        parts = [{"type": "image", "source": {"type": "base64", "media_type": i["mime"], "data": i["data"]}}
                 for i in m["images"]] + [{"type": "text", "text": m["text"] or " "}]
        out.append({"role": m["role"], "content": parts})
    url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com").rstrip("/") + "/v1/messages"
    hdr = {"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"}
    with post(url, {"model": model, "max_tokens": 4096, "system": system, "messages": out, "stream": True}, hdr) as r:
        for d in sse_data(r):
            if d.get("type") == "content_block_delta" and d["delta"].get("type") == "text_delta":
                yield d["delta"]["text"]


def openai_compat(system, msgs, model, base, key):
    out = [{"role": "system", "content": system}]
    for m in msgs:
        parts = [{"type": "text", "text": m["text"]}] + [
            {"type": "image_url", "image_url": {"url": f"data:{i['mime']};base64,{i['data']}"}} for i in m["images"]]
        out.append({"role": m["role"], "content": parts if m["images"] else m["text"]})
    hdr = {"Authorization": "Bearer " + key} if key else {}
    with post(base.rstrip("/") + "/chat/completions", {"model": model, "messages": out, "stream": True}, hdr) as r:
        for d in sse_data(r):
            t = ((d.get("choices") or [{}])[0].get("delta") or {}).get("content")
            if t:
                yield t


def stream(prov, model, system, msgs):
    if prov == "demo":
        return demo(system, msgs)
    if prov == "anthropic":
        return anthropic(system, msgs, model)
    if prov == "openai":
        return openai_compat(system, msgs, model, os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
                             os.environ["OPENAI_API_KEY"])
    return openai_compat(system, msgs, model, os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434/v1"), None)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, body, ctype="application/json"):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        if ctype.startswith("text/html"):
            self.send_header("Content-Security-Policy", CSP)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/models":
            c = catalog()
            return self.reply(200, {"demoOnly": list(c) == ["demo"],
                                    "models": [{"id": f"{p}:{m}", "label": f"{m} ({p})"} for p, ms in c.items() for m in ms]})
        f = (STATIC / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
        if STATIC not in f.parents or not f.is_file():
            return self.reply(404, {"error": "Not found"})
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        self.reply(200, f.read_bytes(), ctype + ("; charset=utf-8" if ctype.startswith("text/") else ""))

    def do_POST(self):
        if self.path != "/api/chat":
            return self.reply(404, {"error": "Not found"})
        n = int(self.headers.get("Content-Length") or 0)
        if not 0 < n <= MAX_BODY:
            return self.reply(413, {"error": "Request too large (limit 20 MB)."})
        try:
            d = json.loads(self.rfile.read(n))
            prov, _, model = str(d["model"]).partition(":")
            msgs = [{"role": m["role"], "text": str(m.get("text", "")),
                     "images": [{"mime": i["mime"], "data": i["data"]} for i in m.get("images", []) if i.get("mime") in IMG]}
                    for m in d["messages"]]
            ok = bool(msgs) and model in catalog().get(prov, []) and all(m["role"] in ("user", "assistant") for m in msgs)
        except Exception:
            ok = False
        if not ok:
            return self.reply(400, {"error": "Invalid request or unknown model."})
        system = BASE + "\n" + str(d.get("system", ""))[:4000]
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        def ev(o):
            try:
                self.wfile.write(b"data: " + json.dumps(o).encode() + b"\n\n")
                self.wfile.flush()
            except OSError:
                raise ConnectionAbortedError

        try:
            for t in stream(prov, model, system, msgs):
                ev({"t": t})
            ev({"done": True})
        except ConnectionAbortedError:
            pass
        except urllib.error.HTTPError as e:
            ev({"error": f"{prov} returned HTTP {e.code}: " + e.read(300).decode("utf-8", "replace")})
        except Exception as e:
            ev({"error": f"Could not get a reply from {prov}: {e}"})


if __name__ == "__main__":
    load_env()
    host, port = os.environ.get("HOST", "127.0.0.1"), int(os.environ.get("PORT", "8000"))
    print(f"SOMIJI AI running at http://{host}:{port}  (providers: {', '.join(catalog())})")
    ThreadingHTTPServer((host, port), Handler).serve_forever()
