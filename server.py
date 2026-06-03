#!/usr/bin/env python3
"""AgentCore Studio 后端 — 本地发布 + Playground 调用 + 可选云部署（零依赖，仅标准库）。
启动: python3 server.py  →  http://127.0.0.1:8799  (可用 PORT 环境变量覆盖)
仅绑定 127.0.0.1，会在本机执行生成的 agent 代码与 agentcore CLI，请勿暴露到公网。"""
import json, os, sys, types, importlib.util, subprocess, re, base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AUTH = os.environ.get("STUDIO_PASSWORD")  # 设置则对所有 HTTP 请求启用 Basic Auth

ROOT = os.path.dirname(os.path.abspath(__file__))
WS = os.path.join(ROOT, "workspace")
PUBLISHED = {}  # name -> {dir, cfg}

def write_project(name, files):
    d = os.path.join(WS, name); os.makedirs(d, exist_ok=True)
    for fn, txt in files.items():
        with open(os.path.join(d, fn), "w") as f: f.write(txt)
    return d

def _stub_sdk():
    if "bedrock_agentcore" in sys.modules: return
    try: __import__("bedrock_agentcore")
    except Exception:
        m = types.ModuleType("bedrock_agentcore")
        class _App:
            def entrypoint(self, f): return f
            def run(self, *a, **k): pass
        m.BedrockAgentCoreApp = _App
        sys.modules["bedrock_agentcore"] = m

def run_agent(name, prompt):
    info = PUBLISHED.get(name)
    if not info: return "尚未发布，请先点击「发布」", "error"
    _stub_sdk()
    entry = os.path.join(info["dir"], info["cfg"].get("entry", "agentcore_entry.py"))
    try:
        spec = importlib.util.spec_from_file_location("ac_" + name, entry)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        res = mod.invoke({"prompt": prompt})
        return (res.get("result") or res.get("error") or json.dumps(res)), "real"
    except Exception:
        return fallback(prompt, info["cfg"]), "mock"

def fallback(prompt, cfg):
    sp = (cfg.get("system_prompt") or "").strip()
    persona = f"依据设定「{sp}」，" if sp else ""
    tools, skills = cfg.get("tools") or [], cfg.get("skills") or []
    extra = f"（已注册工具: {', '.join(tools) or '无'}; 技能: {', '.join(skills) or '无'}）" if (tools or skills) else ""
    return f"{persona}针对「{prompt}」给出演示回复。{extra}配置真实模型凭证后将返回真实 Agent 响应。"

def deploy_cloud(name):
    info = PUBLISHED.get(name)
    if not info: return "尚未发布", False
    try:
        r = subprocess.run(["bash", "deploy.sh"], cwd=info["dir"], capture_output=True, text=True, timeout=900)
        out = (r.stdout + r.stderr)[-6000:] or "（无输出）"
        ok = r.returncode == 0 or "Deployment completed successfully" in out or "Agent created/updated" in out
        if ok: info["deployed"] = True
        return out, ok
    except Exception as e:
        return f"部署失败: {e}", False

def _extract(out):
    """从 agentcore invoke 的噪声输出里提取 agent 实际响应。"""
    dec = json.JSONDecoder(); i = 0; cand = None; any_d = None
    while True:
        j = out.find("{", i)
        if j < 0: break
        try:
            obj, end = dec.raw_decode(out[j:]); i = j + end
            if isinstance(obj, dict):
                any_d = obj
                if any(k in obj for k in ("result", "response", "output")): cand = obj
        except Exception:
            i = j + 1
    d = cand or any_d
    if isinstance(d, dict):
        return d.get("result") or d.get("response") or d.get("output") or json.dumps(d, ensure_ascii=False)
    lines = [l for l in out.splitlines() if l.strip()]
    return lines[-1] if lines else "（无输出）"

def invoke_cloud(name, prompt):
    info = PUBLISHED.get(name)
    if not info: return "尚未发布", "error"
    payload = json.dumps({"prompt": prompt})
    try:
        r = subprocess.run(["agentcore", "invoke", payload], cwd=info["dir"],
                           capture_output=True, text=True, timeout=120,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        out = re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout + r.stderr))
        if r.returncode == 0:
            return _extract(out), "cloud"
        return out.strip()[-1500:] or "（无输出）", "cloud-error"
    except FileNotFoundError:
        return "未找到 uv / agentcore CLI，无法调用云端 runtime", "error"
    except Exception as e:
        return f"云端调用失败: {e}", "error"

class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*"); self.end_headers(); self.wfile.write(b)
    def do_OPTIONS(self): self._send(204, "")
    def _authed(self):
        if not AUTH: return True
        h = self.headers.get("Authorization", "")
        if h.startswith("Basic "):
            try:
                if base64.b64decode(h[6:]).decode().split(":", 1)[1] == AUTH: return True
            except Exception: pass
        self.send_response(401); self.send_header("WWW-Authenticate", 'Basic realm="AgentCore Studio"')
        self.send_header("Content-Length", "0"); self.end_headers(); return False
    def do_GET(self):
        if not self._authed(): return
        path = "/index.html" if self.path in ("/", "") else self.path.split("?")[0]
        fp = os.path.join(ROOT, path.lstrip("/"))
        if os.path.isfile(fp):
            ct = "text/html; charset=utf-8" if fp.endswith(".html") else "text/plain"
            with open(fp, "rb") as f: self._send(200, f.read(), ct)
        else: self._send(404, "not found", "text/plain")
    def do_POST(self):
        if not self._authed(): return
        n = int(self.headers.get("Content-Length", 0))
        data = json.loads(self.rfile.read(n) or "{}")
        if self.path == "/api/publish":
            d = write_project(data["name"], data["files"])
            PUBLISHED[data["name"]] = {"dir": d, "cfg": data.get("cfg", {})}
            self._send(200, json.dumps({"ok": True, "dir": d}))
        elif self.path == "/api/invoke":
            out, mode = run_agent(data["name"], data.get("prompt", ""))
            self._send(200, json.dumps({"result": out, "mode": mode}))
        elif self.path == "/api/deploy":
            log, ok = deploy_cloud(data["name"]); self._send(200, json.dumps({"log": log, "ok": ok}))
        elif self.path == "/api/invoke-cloud":
            out, mode = invoke_cloud(data["name"], data.get("prompt", "")); self._send(200, json.dumps({"result": out, "mode": mode}))
        else: self._send(404, "{}")
    def log_message(self, *a): pass

if __name__ == "__main__":
    os.makedirs(WS, exist_ok=True)
    port = int(os.environ.get("PORT", 8799))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"AgentCore Studio  →  http://{host}:{port}   (Ctrl+C 退出)")
    ThreadingHTTPServer((host, port), H).serve_forever()
