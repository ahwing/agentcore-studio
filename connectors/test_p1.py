# ABOUTME: P1 集成测试 —— 验证 deep_generate 的连接器接线 + 生成 entry 的运行时装配模式。
# 运行: python3 -m unittest connectors.test_p1   （零第三方 HTTP 依赖；用到 strands 时才需其已安装）
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import deep_generate
from connectors.base import Connector


CONNECTOR_SPEC = {
    "summary": "订单助手",
    "deploy_mode": "runtime",
    "builtin_tools": [],
    "connectors": [{
        "name": "order_system", "type": "rest", "description": "订单系统",
        "connection": {"base_url": "http://PLACEHOLDER", "auth": {"type": "none"}},
        "operations": [
            {"name": "query_order", "description": "查订单", "method": "GET",
             "path": "/orders/{order_id}",
             "params": {"order_id": {"in": "path", "type": "string", "required": True}},
             "response": {"pick": "$.data"}},
            {"name": "refund_order", "description": "退款", "method": "POST",
             "path": "/orders/{order_id}/refund",
             "params": {"order_id": {"in": "path", "type": "string", "required": True},
                        "amount": {"in": "body", "type": "number", "required": True}}},
        ],
    }],
}


class DeepGenerateConnectorTest(unittest.TestCase):
    def test_canvas_nodes_emit_connector(self):
        nodes = deep_generate._build_canvas_nodes(CONNECTOR_SPEC, {}, "us-west-2")
        conn_nodes = [n for n in nodes if n["type"] == "mcp" and n["cfg"].get("type") == "rest"]
        self.assertEqual(len(conn_nodes), 1)
        cfg = conn_nodes[0]["cfg"]
        self.assertEqual(cfg["name"], "order_system")
        self.assertIn("connector", cfg)                       # 完整 config 随节点带出
        self.assertEqual(len(cfg["connector"]["operations"]), 2)

    def test_tools_description_lists_operations(self):
        desc = deep_generate._build_tools_description(CONNECTOR_SPEC, {})
        self.assertIn("query_order", desc)
        self.assertIn("refund_order", desc)


# ── mock 订单系统 ─────────────────────────────────────────────────────────────
class _OrderHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        oid = self.path.split("/orders/")[1].split("?")[0]
        body = json.dumps({"data": {"order_id": oid, "status": "shipped"}}).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass


class EntryRuntimePatternTest(unittest.TestCase):
    """复刻 genEntry 生成的连接器装配片段，验证运行时端到端可用（config → 工具 → 真实 HTTP）。"""
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), _OrderHandler)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def test_entry_assembly_pattern(self):
        # 与 index.html genEntry 的 connSetup 完全一致的装配方式
        import json as _j3
        cfg = json.loads(json.dumps(CONNECTOR_SPEC["connectors"][0]))  # 深拷贝
        cfg["connection"]["base_url"] = f"http://127.0.0.1:{self.port}"
        _CONNECTORS = _j3.loads(json.dumps([cfg]))                     # 模拟 _j3.loads(r'''...''')
        try:
            from strands import tool  # noqa: F401
        except Exception:
            self.skipTest("strands 未安装（as_tools 在 agent 运行时生效）")
        _CONN_TOOLS = []
        for _cc in _CONNECTORS:
            _CONN_TOOLS += Connector.from_config(_cc).as_tools()
        # 两个 operation → 两个工具
        self.assertEqual(len(_CONN_TOOLS), 2)
        # 真实 HTTP 调用（绕过 strands agent 循环，直接验证 connector 运行时）
        conn = Connector.from_config(cfg)
        out = json.loads(conn.call("query_order", order_id="Z9"))
        self.assertEqual(out["order_id"], "Z9")
        self.assertEqual(out["status"], "shipped")


if __name__ == "__main__":
    unittest.main()
