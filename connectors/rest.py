# ABOUTME: REST 连接器 —— 配置驱动地调用 HTTP/REST 业务系统（零依赖，仅标准库 urllib）。
# 支持：path/query/body 参数、auth(none/api_key/bearer/oauth2 client_credentials)、超时重试、响应裁剪。
import json
import time
import logging
import urllib.request
import urllib.parse
import urllib.error

from .base import Connector, register, resolve_secret, pick

log = logging.getLogger("studio.connectors.rest")

# 安全：只允许 http(s)，并用不含 File/FTP handler 的 opener，杜绝 base_url="file:///etc/passwd" 之类 LFI/SSRF
_ALLOWED_SCHEMES = ("http", "https")
_MAX_RESPONSE_BYTES = 1_000_000  # 响应体上限 1MB，防止塞爆上下文/内存
_OPENER = urllib.request.build_opener(urllib.request.HTTPHandler, urllib.request.HTTPSHandler,
                                      urllib.request.HTTPRedirectHandler)


def _require_http(url):
    """校验 URL scheme 只能是 http/https；否则抛错（连接器加载/调用时拦截）。"""
    scheme = urllib.parse.urlparse(url or "").scheme.lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(f"仅允许 http/https 地址，拒绝: {url!r}")


@register("rest")
class RestConnector(Connector):
    def __init__(self, cfg):
        super().__init__(cfg)
        conn = self.cfg.get("connection", {}) or {}
        self.base_url = (conn.get("base_url") or "").rstrip("/")
        if self.base_url:
            _require_http(self.base_url)          # B1：拒绝 file:// 等非 http(s)
        self.timeout = float(conn.get("timeout") or 10)   # m7：强转类型，防字符串
        self.retries = int(conn.get("retries") or 0)
        self.auth = conn.get("auth", {}) or {}
        self._oauth_token = None
        self._oauth_expiry = 0

    # ── 执行一个 operation ────────────────────────────────────────────────────
    def call(self, op_name, **kwargs):
        try:
            op = self._get_op(op_name)
            method = (op.get("method") or "GET").upper()
            path = op.get("path", "")
            params = op.get("params", {}) or {}

            path_vals, query_vals, body_vals = {}, {}, {}
            for pname, pdef in params.items():
                where = (pdef or {}).get("in", "query")
                if pname not in kwargs:
                    if (pdef or {}).get("required"):
                        return f"[{self.name}.{op_name}] 缺少必填参数: {pname}"
                    continue
                val = kwargs[pname]
                if where == "path":
                    path_vals[pname] = val
                elif where == "body":
                    body_vals[pname] = val
                else:
                    query_vals[pname] = val

            # 组装 URL（M2：path 参数做 URL 编码，防路径注入/越权，如 "../admin"）
            filled_path = path
            for pname, pval in path_vals.items():
                filled_path = filled_path.replace("{" + pname + "}",
                                                   urllib.parse.quote(str(pval), safe=""))
            if "{" in filled_path:
                return f"[{self.name}.{op_name}] 路径参数未全部提供: {filled_path}"
            url = self.base_url + filled_path
            if query_vals:
                url += ("&" if "?" in url else "?") + urllib.parse.urlencode(query_vals)

            headers = {"Accept": "application/json"}
            body_bytes = None
            if body_vals:
                headers["Content-Type"] = "application/json"
                body_bytes = json.dumps(body_vals).encode("utf-8")

            self._inject_auth(headers, query_vals, url)
            # 若 auth 改了 query（api_key in query），重建 url
            if self.auth.get("type") == "api_key" and self.auth.get("query"):
                url = self.base_url + filled_path
                merged = dict(query_vals)
                merged[self.auth["query"]] = resolve_secret(self.auth.get("secret_ref"))
                url += ("&" if "?" in url else "?") + urllib.parse.urlencode(merged)

            # M3：仅幂等方法（或 operation 显式声明 idempotent）才重试，避免重复退款/下单等副作用
            idempotent = method in ("GET", "HEAD", "OPTIONS") or bool(op.get("idempotent"))
            raw = self._request(method, url, headers, body_bytes, idempotent)
            return self._format_response(raw, op)
        except Exception as e:
            log.debug(f"REST 调用异常 {self.name}.{op_name}: {e}")
            return f"[{self.name}.{op_name}] 调用失败: {e}"

    # ── 鉴权注入 ──────────────────────────────────────────────────────────────
    def _inject_auth(self, headers, query_vals, url):
        atype = self.auth.get("type", "none")
        if atype in ("none", None):
            return
        if atype == "bearer":
            tok = resolve_secret(self.auth.get("secret_ref"))
            if tok:
                headers["Authorization"] = f"Bearer {tok}"
        elif atype == "api_key":
            key = resolve_secret(self.auth.get("secret_ref"))
            if key and self.auth.get("header"):
                headers[self.auth["header"]] = key
            elif key and not self.auth.get("query"):
                headers["X-API-Key"] = key  # 默认放 header
            # query 情形在 call() 里重建 url 时处理
        elif atype == "oauth2":
            tok = self._oauth2_token()
            if tok:
                headers["Authorization"] = f"Bearer {tok}"
        elif atype == "iam":
            # SigV4 需要额外签名，P0 暂不实现，明确报错而非静默
            raise NotImplementedError("iam(SigV4) 鉴权暂未实现，请用 bearer/api_key/oauth2")

    def _oauth2_token(self):
        """OAuth2 client_credentials：从 token_url 换取 access_token，带简单过期缓存。"""
        now = time.time()
        if self._oauth_token and now < self._oauth_expiry - 30:
            return self._oauth_token
        token_url = self.auth.get("token_url")
        client_id = self.auth.get("client_id")
        client_secret = resolve_secret(self.auth.get("secret_ref"))
        if not (token_url and client_id and client_secret):
            log.warning(f"{self.name}: oauth2 配置不全")
            return None
        _require_http(token_url)  # B1
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            **({"scope": self.auth["scope"]} if self.auth.get("scope") else {}),
        }).encode("utf-8")
        req = urllib.request.Request(token_url, data=data, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with _OPENER.open(req, timeout=self.timeout) as r:
            obj = json.loads(r.read(_MAX_RESPONSE_BYTES).decode("utf-8"))
        self._oauth_token = obj.get("access_token")
        self._oauth_expiry = now + int(obj.get("expires_in", 3600))
        return self._oauth_token

    # ── 带重试的 HTTP 请求 ─────────────────────────────────────────────────────
    def _request(self, method, url, headers, body_bytes, idempotent=False):
        _require_http(url)  # B1：再次校验（防 query 重建后被篡改）
        attempts = (self.retries + 1) if idempotent else 1  # M3：非幂等只发一次
        last_err = None
        for attempt in range(attempts):
            try:
                req = urllib.request.Request(url, data=body_bytes, method=method, headers=headers)
                with _OPENER.open(req, timeout=self.timeout) as r:  # 不含 File/FTP handler
                    return r.read(_MAX_RESPONSE_BYTES).decode("utf-8", "replace")  # m3：限大小
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read(_MAX_RESPONSE_BYTES).decode("utf-8", "replace")[:500]
                except Exception:
                    pass
                if 400 <= e.code < 500:
                    return f"HTTP {e.code}: {detail or e.reason}"  # 4xx 不重试
                last_err = f"HTTP {e.code}: {detail or e.reason}"
            except Exception as e:
                last_err = str(e)
            if attempt < attempts - 1:
                time.sleep(0.5 * (attempt + 1))  # 线性退避
        return f"请求失败（重试 {attempts - 1} 次后）: {last_err}"

    # ── 响应格式化 ─────────────────────────────────────────────────────────────
    def _format_response(self, raw, op):
        resp_cfg = op.get("response", {}) or {}
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return raw  # 非 JSON 直接返回文本
        if resp_cfg.get("pick"):
            data = pick(data, resp_cfg["pick"])
        return json.dumps(data, ensure_ascii=False) if not isinstance(data, str) else data
