# ABOUTME: 连接器框架单测 —— 用标准库起一个 mock HTTP server 验证 REST 连接器。
# 运行: python3 -m unittest connectors.test_rest   （零第三方依赖，无需 AWS/strands）
import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from connectors.base import Connector, pick


# ── mock HTTP server ─────────────────────────────────────────────────────────
class _Handler(BaseHTTPRequestHandler):
    captured = {}  # 记录最近一次请求，供断言
    hits = {}      # path 命中计数，验证重试行为

    def _reply(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def _count(self):
        key = self.path.split("?")[0]
        _Handler.hits[key] = _Handler.hits.get(key, 0) + 1

    def do_GET(self):
        self._count()
        _Handler.captured = {"method": "GET", "path": self.path,
                             "auth": self.headers.get("Authorization"),
                             "apikey": self.headers.get("X-API-Key")}
        if self.path.startswith("/flaky"):
            self._reply(500, {"error": "boom"}); return
        # /orders/{id}
        if self.path.startswith("/orders/"):
            oid = self.path.split("/orders/")[1].split("?")[0]
            self._reply(200, {"data": {"order_id": oid, "status": "shipped"}, "meta": {"ts": 1}})
        else:
            self._reply(404, {"error": "not found"})

    def do_POST(self):
        self._count()
        n = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(n) or "{}")
        _Handler.captured = {"method": "POST", "path": self.path, "body": body,
                             "auth": self.headers.get("Authorization")}
        if self.path.startswith("/flaky"):
            self._reply(500, {"error": "boom"}); return
        self._reply(200, {"ok": True, "refunded": body.get("amount")})

    def log_message(self, *a):
        pass


class RestConnectorTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.port = cls.srv.server_address[1]
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def _cfg(self, auth=None):
        return {
            "name": "order_system", "type": "rest",
            "connection": {"base_url": self.base, "timeout": 5, "retries": 1,
                           **({"auth": auth} if auth else {})},
            "operations": [
                {"name": "query_order", "method": "GET", "path": "/orders/{order_id}",
                 "params": {"order_id": {"in": "path", "type": "string", "required": True}},
                 "response": {"pick": "$.data"}},
                {"name": "refund_order", "method": "POST", "path": "/orders/{order_id}/refund",
                 "params": {"order_id": {"in": "path", "type": "string", "required": True},
                            "amount": {"in": "body", "type": "number", "required": True}}},
            ],
        }

    def test_get_with_path_param_and_pick(self):
        c = Connector.from_config(self._cfg())
        out = c.call("query_order", order_id="A123")
        obj = json.loads(out)
        self.assertEqual(obj["order_id"], "A123")      # pick $.data 生效，剥掉了外层
        self.assertEqual(obj["status"], "shipped")
        self.assertNotIn("meta", obj)

    def test_bearer_auth_injected(self):
        os.environ["TEST_TOKEN"] = "secret-xyz"
        c = Connector.from_config(self._cfg(auth={"type": "bearer", "secret_ref": "env:TEST_TOKEN"}))
        c.call("query_order", order_id="B1")
        self.assertEqual(_Handler.captured["auth"], "Bearer secret-xyz")

    def test_api_key_header_default(self):
        os.environ["TEST_KEY"] = "k-123"
        c = Connector.from_config(self._cfg(auth={"type": "api_key", "secret_ref": "env:TEST_KEY"}))
        c.call("query_order", order_id="B2")
        self.assertEqual(_Handler.captured["apikey"], "k-123")

    def test_post_body_param(self):
        c = Connector.from_config(self._cfg())
        out = c.call("refund_order", order_id="C1", amount=50)
        obj = json.loads(out)
        self.assertTrue(obj["ok"])
        self.assertEqual(_Handler.captured["body"], {"amount": 50})
        self.assertEqual(_Handler.captured["path"], "/orders/C1/refund")

    def test_missing_required_param(self):
        c = Connector.from_config(self._cfg())
        out = c.call("query_order")  # 缺 order_id
        self.assertIn("缺少必填参数", out)

    def test_unknown_type_raises(self):
        with self.assertRaises(ValueError):
            Connector.from_config({"name": "x", "type": "nope"})

    def test_pick_helper(self):
        self.assertEqual(pick({"a": {"b": [10, 20]}}, "$.a.b.1"), 20)
        self.assertEqual(pick({"a": 1}, "$.a"), 1)
        self.assertIsNone(pick({"a": 1}, "$.x.y"))

    # ── 安全/健壮性回归（评审 B1/M2/M3）──────────────────────────────────────
    def test_rejects_non_http_scheme(self):
        # B1：file:// 等非 http(s) 应被拒绝，杜绝 LFI/SSRF
        bad = self._cfg()
        bad["connection"]["base_url"] = "file:///etc/passwd"
        with self.assertRaises(ValueError):
            Connector.from_config(bad)

    def test_path_param_url_encoded(self):
        # M2：path 参数注入 "../admin" 应被编码，不产生路径穿越
        c = Connector.from_config(self._cfg())
        c.call("query_order", order_id="../admin")
        self.assertIn("%2F", _Handler.captured["path"])
        self.assertNotIn("/orders/../admin", _Handler.captured["path"])

    def _flaky_cfg(self):
        return {
            "name": "flaky", "type": "rest",
            "connection": {"base_url": self.base, "timeout": 5, "retries": 2},
            "operations": [
                {"name": "read_flaky", "method": "GET", "path": "/flaky", "params": {}},
                {"name": "write_flaky", "method": "POST", "path": "/flaky", "params": {}},
            ],
        }

    def test_get_retried_on_5xx(self):
        _Handler.hits.pop("/flaky", None)
        c = Connector.from_config(self._flaky_cfg())
        c.call("read_flaky")
        self.assertEqual(_Handler.hits.get("/flaky"), 3)  # 1 + retries(2)

    def test_post_not_retried_on_5xx(self):
        # M3：非幂等方法(POST)不重试，避免重复副作用（退款/下单）
        _Handler.hits.pop("/flaky", None)
        c = Connector.from_config(self._flaky_cfg())
        c.call("write_flaky")
        self.assertEqual(_Handler.hits.get("/flaky"), 1)


if __name__ == "__main__":
    unittest.main()
