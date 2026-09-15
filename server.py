#!/usr/bin/env python3
"""AI 群聊室：多人同一房间 + AI 模型作为群成员，SSE 实时广播。
用法: python3 server.py [host] [port]   默认 127.0.0.1 666
环境变量: API_BASE, API_KEY 可覆盖上游地址与密钥。
"""
import json, os, sys, time, queue, threading, urllib.request, urllib.error
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

API_BASE = os.environ.get("API_BASE", "http://100.105.192.115:8080/v1").rstrip("/")
API_KEY = os.environ.get("API_KEY", "llama")
HERE = os.path.dirname(os.path.abspath(__file__))
INDEX = os.path.join(HERE, "index.html")
HISTORY = os.path.join(HERE, "history.json")
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))  # 直连，不走系统代理

lock = threading.Lock()
messages = []          # {id, role: user|assistant, name, content, ts, done}
subscribers = set()    # queue.Queue per SSE client
models = []            # 上游模型列表缓存
next_id = 1
try:
    messages = json.load(open(HISTORY))
    next_id = max([m["id"] for m in messages] + [0]) + 1
except Exception:
    pass


def api(method, path, body=None):
    req = urllib.request.Request(API_BASE + path, data=body, method=method,
        headers={"Authorization": "Bearer " + API_KEY, "Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=600)


def load_models():
    global models
    try:
        with api("GET", "/models") as r:
            models = [{"id": m["id"], "name": m.get("name") or m["id"]} for m in json.load(r)["data"]]
    except Exception as e:
        print("获取模型失败:", e, file=sys.stderr)


def broadcast(ev, data):
    payload = "event: %s\ndata: %s\n\n" % (ev, json.dumps(data, ensure_ascii=False))
    for q in list(subscribers):
        q.put(payload)


def save():
    with lock:
        json.dump(messages[-500:], open(HISTORY, "w"), ensure_ascii=False)


def add_message(role, name, content, done=True, model=None):
    global next_id
    with lock:
        m = {"id": next_id, "role": role, "name": name, "content": content, "ts": time.time(), "done": done}
        if model: m["model"] = model
        next_id += 1
        messages.append(m)
    broadcast("message", m)
    return m


def find_models(text):
    """返回文中 @ 到的模型；@AI / @所有人 表示第一个模型"""
    hit = []
    for m in models:
        if ("@" + m["id"]) in text or ("@" + m["name"]) in text:
            hit.append(m)
    if not hit and ("@AI" in text or "@ai" in text or "@所有" in text):
        hit = models[:1]
    return hit


def ai_reply(model, thinking, system):
    """让模型基于群聊记录回复，流式广播"""
    with lock:
        hist = messages[-40:]
    convo = []
    for m in hist:
        if m["role"] == "assistant" and m.get("model") == model["id"]:
            convo.append({"role": "assistant", "content": m["content"]})
        else:
            convo.append({"role": "user", "content": "[%s]: %s" % (m["name"], m["content"])})
    sysmsg = ("你是群聊里的一员，叫「%s」，群里还有其他人和 AI，消息格式为“[昵称]: 内容”。\n"
              "像普通群友一样聊天：口语化，一两句话说完，别长篇大论，别列条目，别客套，别总结、别反问“还有什么可以帮你”。"
              "只回应刚才 @ 你或和你相关的话，不用面面俱到。不要在开头写自己的名字或方括号。" % model["name"])
    if system: sysmsg += "\n" + system
    convo.insert(0, {"role": "system", "content": sysmsg})
    body = {"model": model["id"], "messages": convo, "stream": True}
    if not thinking:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    msg = add_message("assistant", model["name"], "", done=False, model=model["id"])
    content, think, in_think = "", "", False
    try:
        with api("POST", "/chat/completions", json.dumps(body).encode()) as r:
            for line in r:
                line = line.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"): continue
                d = line[5:].strip()
                if d == "[DONE]": break
                try: delta = json.loads(d)["choices"][0]["delta"]
                except Exception: continue
                if delta.get("reasoning_content"):
                    think += delta["reasoning_content"]
                if delta.get("content"):
                    content += delta["content"]
                broadcast("delta", {"id": msg["id"], "content": content, "think": think})
    except urllib.error.HTTPError as e:
        content += "\n\n**错误 %d**: %s" % (e.code, e.read().decode("utf-8", "ignore")[:500])
    except Exception as e:
        content += "\n\n**请求失败**: %s" % e
    with lock:
        msg["content"] = content or "（无回复）"
        if think: msg["think"] = think
        msg["done"] = True
    broadcast("message", msg)
    save()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)): body = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, open(INDEX, "rb").read(), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            if not models: load_models()
            with lock:
                self._send(200, {"models": models, "messages": messages[-200:]})
        elif self.path == "/api/events":
            self._sse()
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try: data = json.loads(self.rfile.read(n) or b"{}")
        except Exception: return self._send(400, {"error": "bad json"})
        if self.path == "/api/send":
            name = (data.get("name") or "匿名").strip()[:20]
            text = (data.get("content") or "").strip()
            if not text: return self._send(400, {"error": "empty"})
            add_message("user", name, text)
            save()
            targets = find_models(text)
            if not targets and data.get("auto") and models:
                targets = [next((m for m in models if m["id"] == data.get("auto")), models[0])]
            for m in targets:
                threading.Thread(target=ai_reply, args=(m, data.get("thinking", True), data.get("system", "")), daemon=True).start()
            self._send(200, {"ok": True, "ai": [m["id"] for m in targets]})
        elif self.path == "/api/clear":
            with lock: messages.clear()
            save(); broadcast("clear", {})
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "not found"})

    def _sse(self):
        q = queue.Queue()
        subscribers.add(q)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            while True:
                try: chunk = q.get(timeout=15)
                except queue.Empty: chunk = ": ping\n\n"
                b = chunk.encode()
                self.wfile.write(b"%x\r\n%s\r\n" % (len(b), b)); self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            subscribers.discard(q)


if __name__ == "__main__":
    host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 666
    load_models()
    print("AI 群聊室 -> http://%s:%d   上游 %s   模型 %s" % (host, port, API_BASE, [m["id"] for m in models]))
    ThreadingHTTPServer((host, port), Handler).serve_forever()
