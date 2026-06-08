#!/usr/bin/env python3
"""AgentCore Studio 后端 — 本地发布 + Playground 调用 + 可选云部署（零依赖，仅标准库）。
启动: python3 server.py  →  http://127.0.0.1:8799  (可用 PORT 环境变量覆盖)
仅绑定 127.0.0.1，会在本机执行生成的 agent 代码与 agentcore CLI，请勿暴露到公网。"""
import json, os, sys, types, importlib.util, subprocess, re, base64, threading, time, queue, shutil, uuid, tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AUTH = os.environ.get("STUDIO_PASSWORD")  # 设置则对所有 HTTP 请求启用 Basic Auth

ROOT = os.path.dirname(os.path.abspath(__file__))
WS = os.path.join(ROOT, "workspace")
PUBLISHED = {}  # name -> {dir, cfg}

def write_project(name, files):
    d = os.path.join(WS, name); os.makedirs(d, exist_ok=True)
    for fn, txt in files.items():
        fp = os.path.join(d, fn)
        os.makedirs(os.path.dirname(fp), exist_ok=True)  # 支持 skills/foo.py 等子目录
        with open(fp, "w") as f: f.write(txt)
    return d

def clean_stale_region(d, target_region):
    """若本地 .bedrock_agentcore.yaml 记录的 agent_arn 区域与目标区域不一致，
    清除过期的 toolkit 状态，使下次部署在新区域全新创建（而非跨区 Update 失败）。"""
    if not target_region: return None
    yaml_fp = os.path.join(d, ".bedrock_agentcore.yaml")
    if not os.path.isfile(yaml_fp): return None
    try:
        with open(yaml_fp) as f: content = f.read()
        m = re.search(r"agent_arn:\s*arn:aws:bedrock-agentcore:([a-z0-9-]+):", content)
        if m and m.group(1) != target_region:
            old = m.group(1)
            os.remove(yaml_fp)
            import shutil
            shutil.rmtree(os.path.join(d, ".bedrock_agentcore"), ignore_errors=True)
            return f"检测到旧部署区域 {old} 与目标 {target_region} 不一致，已清除本地状态，将在 {target_region} 全新创建"
    except Exception:
        pass
    return None

def _find_ready_runtime(region, name):
    """直接查 AWS：region 内是否有同名且 READY 的 agent runtime（不依赖本地工作区）。"""
    if not (region and name): return None
    try:
        r = subprocess.run(["aws", "bedrock-agentcore-control", "list-agent-runtimes",
                            "--region", region, "--output", "json"],
                           capture_output=True, text=True, timeout=20)
        if r.returncode != 0: return None
        rts = (json.loads(r.stdout or "{}")).get("agentRuntimes", [])
        # 先精确匹配名字，再前缀匹配（agentcore 偶尔给 ARN 加后缀，但 name 字段通常是裸名）
        for matcher in (lambda nm: nm == name, lambda nm: nm.startswith(name)):
            for rt in rts:
                if matcher(str(rt.get("agentRuntimeName", ""))) and rt.get("status") == "READY":
                    return {"agent_id": rt.get("agentRuntimeId"), "arn": rt.get("agentRuntimeArn"), "region": region}
    except Exception:
        pass
    return None

def delete_runtime(name, region):
    """按名字删除某 region 内的 agent runtime（用于改名后清理旧孤儿）；不删除关联 Memory。"""
    if not (name and region): return {"ok": False, "error": "缺少 name 或 region"}
    try:
        r = subprocess.run(["aws", "bedrock-agentcore-control", "list-agent-runtimes",
                            "--region", region, "--output", "json"], capture_output=True, text=True, timeout=20)
        if r.returncode != 0: return {"ok": False, "error": (r.stderr or "list 失败")[:200]}
        rid = None
        for rt in (json.loads(r.stdout or "{}")).get("agentRuntimes", []):
            nm = str(rt.get("agentRuntimeName", ""))
            if nm == name or nm.startswith(name):
                rid = rt.get("agentRuntimeId"); break
        if not rid: return {"ok": False, "error": "未找到 runtime " + name}
        dd = subprocess.run(["aws", "bedrock-agentcore-control", "delete-agent-runtime",
                            "--agent-runtime-id", rid, "--region", region], capture_output=True, text=True, timeout=30)
        if dd.returncode != 0: return {"ok": False, "error": (dd.stderr or "delete 失败")[:200]}
        return {"ok": True, "id": rid}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}

def cloud_status(d, region, name=None):
    """检测是否已有就绪(READY)的云端 agent，用作演示托底环境。
    优先用本地 .bedrock_agentcore.yaml（本工作区部署过）；否则直接按名字查 AWS（托管/全新容器也能命中）。"""
    if not region: return None
    yaml_fp = os.path.join(d, ".bedrock_agentcore.yaml")
    if os.path.isfile(yaml_fp):
        try:
            content = open(yaml_fp).read()
            m = re.search(r"agent_id:\s*([A-Za-z0-9_\-]+)", content)
            if m:
                aid = m.group(1)
                r = subprocess.run(["aws", "bedrock-agentcore-control", "get-agent-runtime",
                                    "--agent-runtime-id", aid, "--region", region,
                                    "--query", "[status,agentRuntimeArn]", "--output", "text"],
                                   capture_output=True, text=True, timeout=15)
                if r.returncode == 0 and r.stdout.split():
                    parts = r.stdout.split()
                    if parts[0] == "READY":
                        return {"agent_id": aid, "region": region, "arn": parts[1] if len(parts) > 1 else None}
        except Exception:
            pass
    # 托底：直接按名字查 AWS
    return _find_ready_runtime(region, name)

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

def bedrock_reply(prompt, cfg):
    """直接调用 Bedrock converse 返回真实模型回复。无 boto3/凭证/模型权限则抛异常。"""
    import boto3
    model = cfg.get("model") or "anthropic.claude-3-5-sonnet-20241022-v2:0"
    region = cfg.get("region") or "us-west-2"
    # 跨区域推理配置：新模型按需调用需带地域前缀
    import re as _re
    if not _re.match(r"^(us|eu|apac|us-gov)\.", model):
        geo = "eu." if region.startswith("eu-") else "apac." if region.startswith("ap-") else "us-gov." if region.startswith("us-gov") else "us." if region.startswith("us-") else ""
        model = geo + model
    sp = (cfg.get("system_prompt") or "").strip()
    tools, skills = cfg.get("tools") or [], cfg.get("skills") or []
    if tools or skills:
        sp += f"\n（可用工具: {', '.join(tools) or '无'}; 技能: {', '.join(skills) or '无'}）"
    br = boto3.client("bedrock-runtime", region_name=region)
    kw = {"modelId": model, "messages": [{"role": "user", "content": [{"text": prompt}]}],
          "inferenceConfig": {"maxTokens": 1024, "temperature": 0.7}}
    if sp.strip(): kw["system"] = [{"text": sp.strip()}]
    r = br.converse(**kw)
    return r["output"]["message"]["content"][0]["text"]

def run_agent(name, prompt):
    info = PUBLISHED.get(name)
    if not info: return "尚未发布，请先点击「发布」", "error"
    _stub_sdk()
    entry = os.path.join(info["dir"], info["cfg"].get("entry", "agentcore_entry.py"))
    # 1) 优先真实运行已发布的 entry.py（需框架依赖，如 strands）
    try:
        spec = importlib.util.spec_from_file_location("ac_" + name, entry)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        res = mod.invoke({"prompt": prompt})
        out = res.get("result") or res.get("error") or json.dumps(res)
        if out and not res.get("error"): return out, "real"
    except Exception:
        pass
    # 2) 直连 Bedrock converse（有 boto3+凭证+模型权限即返回真实回复）
    try:
        return bedrock_reply(prompt, info["cfg"]), "real"
    except Exception:
        pass
    # 3) 文本兜底（无依赖/无凭证）
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
    # 防御：CLI 可能按终端宽度把 JSON 折行（插入真实换行），尝试在 Response 段去掉折行后重组解析
    m = re.search(r"Response:\s*(\{.*\})", out, re.DOTALL)
    if m:
        try:
            collapsed = re.sub(r"\n", "", m.group(1))
            obj = json.loads(collapsed)
            if isinstance(obj, dict):
                return obj.get("result") or obj.get("response") or obj.get("output") or json.dumps(obj, ensure_ascii=False)
        except Exception:
            pass
    noise = ("suppress_recommendation", "silence this warning", "recommendation", "set agentcore_", "💡", "⚠")
    lines = [l for l in out.splitlines() if l.strip() and not any(k in l.lower() for k in noise)]
    return lines[-1] if lines else "（无输出）"

def _invoke_runtime_arn(arn, region, prompt):
    """托底：不依赖本地工作区，直接用 AWS 数据面 API 按 ARN 调用云端 runtime。"""
    sid = uuid.uuid4().hex + uuid.uuid4().hex  # 64 chars，满足 runtimeSessionId 长度要求
    payload_b64 = base64.b64encode(json.dumps({"prompt": prompt}).encode()).decode()  # 默认 cli_binary_format=base64
    outpath = None
    try:
        fd, outpath = tempfile.mkstemp(suffix=".out"); os.close(fd)
        r = subprocess.run(["aws", "bedrock-agentcore", "invoke-agent-runtime",
                            "--agent-runtime-arn", arn, "--region", region,
                            "--runtime-session-id", sid,
                            "--content-type", "application/json", "--accept", "application/json",
                            "--payload", payload_b64, outpath],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            return (r.stderr or r.stdout).strip()[-1500:] or "云端调用失败", "cloud-error"
        body = open(outpath, encoding="utf-8", errors="replace").read()
        return _extract(body), "cloud"
    except Exception as e:
        return f"云端调用失败: {e}", "error"
    finally:
        if outpath and os.path.isfile(outpath):
            try: os.remove(outpath)
            except Exception: pass

def invoke_cloud(name, prompt, region=None):
    info = PUBLISHED.get(name)
    if not info:
        # PUBLISHED 无记录（如容器重启清空内存）→ 仍按名字查 AWS 托底，避免误报"尚未发布"
        reg = region or "us-west-2"
        cs = _find_ready_runtime(reg, name)
        if cs: return _invoke_runtime_arn(cs["arn"], reg, prompt)
        return "尚未发布（云端也未找到同名就绪 Agent）", "error"
    # 托底：本地工作区无部署状态（如托管/全新容器），但云端已有就绪 runtime → 直接按 ARN 调 AWS API
    if not os.path.isfile(os.path.join(info["dir"], ".bedrock_agentcore.yaml")) and info["cfg"].get("deploy_mode") != "harness":
        arn = info.get("cloud_arn"); reg = info.get("cloud_region") or info["cfg"].get("region") or region
        if not arn and reg:
            cs = _find_ready_runtime(reg, name)
            if cs: arn = cs["arn"]; info["cloud_arn"] = arn; info["cloud_region"] = reg
        if arn and reg: return _invoke_runtime_arn(arn, reg, prompt)
        return "尚未发布（云端也未找到同名就绪 Agent）", "error"
    # Harness 模式: 用 agentcore invoke --harness CLI（项目在 <pn>/ 子目录）
    if info["cfg"].get("deploy_mode") == "harness":
        pn = info["cfg"].get("harness_name") or "".join(ch for ch in name if ch.isalnum()) or "agent"
        proj_dir = os.path.join(info["dir"], pn)
        if not os.path.isdir(proj_dir):
            proj_dir = info["dir"]  # 回退：项目可能直接在 dir
        try:
            r = subprocess.run(
                ["npx", "@aws/agentcore", "invoke", "--harness", pn, "--prompt", prompt],
                cwd=proj_dir, capture_output=True, text=True, timeout=120,
                env={**os.environ, "PYTHONIOENCODING": "utf-8", "AGENTCORE_SUPPRESS_RECOMMENDATION": "1", "COLUMNS": "100000"})
            out = re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout + r.stderr))
            if r.returncode == 0:
                return _extract(out), "cloud"
            return out.strip()[-1500:] or "（无输出）", "cloud-error"
        except FileNotFoundError:
            return "未找到 @aws/agentcore CLI，请运行: npm install -g @aws/agentcore@preview", "error"
        except Exception as e:
            return f"Harness 调用失败: {e}", "error"
    # Runtime 模式: 用 agentcore invoke CLI
    payload = json.dumps({"prompt": prompt})
    try:
        r = subprocess.run(["agentcore", "invoke", payload], cwd=info["dir"],
                           capture_output=True, text=True, timeout=120,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8", "AGENTCORE_SUPPRESS_RECOMMENDATION": "1", "COLUMNS": "100000"})
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
            # 写入上传的 zip 技能包（base64），并校验含 SKILL.md
            zip_warn = []
            for fn, b64 in (data.get("zips") or {}).items():
                try:
                    import zipfile, io
                    raw = base64.b64decode(b64)
                    zf = zipfile.ZipFile(io.BytesIO(raw))
                    if not any(n.lower().endswith("skill.md") for n in zf.namelist()):
                        zip_warn.append(f"{fn}: 未含 SKILL.md，已跳过"); continue
                    fp = os.path.join(d, fn)
                    os.makedirs(os.path.dirname(fp), exist_ok=True)
                    with open(fp, "wb") as f: f.write(raw)
                except Exception as e:
                    zip_warn.append(f"{fn}: {e}")
            PUBLISHED[data["name"]] = {"dir": d, "cfg": data.get("cfg", {})}
            region_notice = clean_stale_region(d, (data.get("cfg") or {}).get("region"))
            resp = {"ok": True, "dir": d, "zip_warn": zip_warn}
            if region_notice: resp["region_notice"] = region_notice
            cs = cloud_status(d, (data.get("cfg") or {}).get("region"), data.get("name"))
            if cs:
                PUBLISHED[data["name"]]["cloud_arn"] = cs.get("arn")
                PUBLISHED[data["name"]]["cloud_region"] = cs.get("region")
                resp["cloud_ready"] = True; resp["cloud_agent"] = cs["agent_id"]; resp["cloud_region"] = cs["region"]
            self._send(200, json.dumps(resp))
        elif self.path == "/api/invoke":
            out, mode = run_agent(data["name"], data.get("prompt", ""))
            self._send(200, json.dumps({"result": out, "mode": mode}))
        elif self.path == "/api/deploy":
            self._stream_deploy(data["name"])
        elif self.path == "/api/invoke-cloud":
            out, mode = invoke_cloud(data["name"], data.get("prompt", ""), (data.get("cfg") or {}).get("region") or data.get("region")); self._send(200, json.dumps({"result": out, "mode": mode}))
        elif self.path == "/api/delete-runtime":
            self._send(200, json.dumps(delete_runtime(data.get("name"), data.get("region"))))
        else: self._send(404, "{}")
    def _stream_deploy(self, name):
        # SSE: 逐行流式输出部署日志；无输出时 5s 心跳保活；结束写 data:{done,ok,log}
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        # 立刻写首个字节：App Runner 入口若头 1-2s 收不到 body 会掐断连接
        try:
            self.wfile.write(("data: " + json.dumps({"tick": 0}) + "\n\n").encode()); self.wfile.flush()
        except Exception:
            return
        info = PUBLISHED.get(name)
        if not info:
            try:
                self.wfile.write(("data: " + json.dumps({"done": True, "ok": False, "log": "尚未发布"}) + "\n\n").encode()); self.wfile.flush()
            except Exception: pass
            return
        q = queue.Queue(); result = {}
        def keep(s):
            s = s.strip()
            if not s: return False
            if s.startswith((">>>", "#", "✅", "⚠", "❌", "☁️", "===")): return True
            low = s.lower()
            kw = ("error", "exception", "traceback", "failed", "fail:", "denied",
                  "completed", "created", "created/updated", "deploying", "building",
                  "pushing", "uploading", "success", "arn:aws", "endpoint", "ready")
            return any(k in low for k in kw)
        def worker():
            lines = []
            try:
                env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
                # stdbuf 强制行缓冲：让 agentcore 输出实时流出，而非被块缓冲憋住（憋住会让 App Runner 误判空闲掐断）
                cmd = ["stdbuf", "-oL", "-eL", "bash", "deploy.sh"] if shutil.which("stdbuf") else ["bash", "deploy.sh"]
                p = subprocess.Popen(cmd, cwd=info["dir"],
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, bufsize=1, env=env)
                for line in iter(p.stdout.readline, ""):
                    line = line.rstrip("\n"); lines.append(line)
                    if keep(line): q.put(("line", line))   # 仅推送关键行，压缩日志量
                p.stdout.close(); rc = p.wait(timeout=900)
                out = "\n".join(lines)
                ok = rc == 0 or "Deployment completed successfully" in out or "Agent created/updated" in out
                if ok: info["deployed"] = True
                result["ok"] = ok; result["log"] = out[-4000:]
            except Exception as e:
                result["ok"] = False; result["log"] = ("\n".join(lines) + f"\ndeploy error: {e}")[-4000:]
            q.put(("done", None))
        threading.Thread(target=worker, daemon=True).start()
        try:
            tick = 0
            while True:
                try:
                    kind, val = q.get(timeout=2)
                except queue.Empty:
                    # 用真实 data 事件做心跳（App Runner 入口会掐断静默的流式响应，注释行不算数据）
                    tick += 1
                    self.wfile.write(("data: " + json.dumps({"tick": tick}) + "\n\n").encode()); self.wfile.flush(); continue
                if kind == "line":
                    self.wfile.write(("data: " + json.dumps({"line": val}) + "\n\n").encode()); self.wfile.flush()
                else:
                    self.wfile.write(("data: " + json.dumps({"done": True, "ok": result.get("ok", False), "log": result.get("log", "")}) + "\n\n").encode()); self.wfile.flush()
                    break
        except (BrokenPipeError, ConnectionResetError):
            return  # 客户端断了；后台 deploy 仍会跑完
    def log_message(self, *a): pass

if __name__ == "__main__":
    os.makedirs(WS, exist_ok=True)
    port = int(os.environ.get("PORT", 8799))
    host = os.environ.get("HOST", "127.0.0.1")
    print(f"AgentCore Studio  →  http://{host}:{port}   (Ctrl+C 退出)")
    ThreadingHTTPServer((host, port), H).serve_forever()
