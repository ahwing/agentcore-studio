# ABOUTME: 连接器框架基类 —— 把一份声明式 connector config 变成 agent 可调用的工具。
# 设计要点：
#   1) 连接器 = Gateway target 的"声明式形态"（并进现有 gateway_targets，只新增 type）。
#   2) 声明式配置，不生成代码：一份 config 描述"怎么调这个业务系统"，取代 LLM 现写 Lambda。
#   3) 复用而非重造：密钥走 Secrets Manager（只存引用），治理走已有 Policy。
#   4) 一个 operation = 一个 strands @tool，agent 直接按名字调用。
import os
import json
import logging

log = logging.getLogger("studio.connectors")

# 连接器类型注册表：type 名 -> Connector 子类
_REGISTRY = {}

# 已解析密钥缓存（secret_ref -> 明文），避免每次调用都打 Secrets Manager
_SECRET_CACHE = {}


def register(type_name):
    """类装饰器：把某 Connector 子类注册到某个 type 名下。"""
    def _wrap(cls):
        _REGISTRY[type_name] = cls
        return cls
    return _wrap


def _ensure_builtins_loaded():
    """惰性加载内置连接器（rest 等），避免循环导入；仅在注册表为空时触发。"""
    if _REGISTRY:
        return
    try:
        from . import rest  # noqa: F401  —— 导入即自注册
    except Exception as e:  # pragma: no cover
        log.debug(f"内置连接器加载失败: {e}")


def resolve_secret(secret_ref):
    """把 secret_ref 解析成明文密钥。支持三种形式（按安全性从高到低）：
      - "arn:aws:secretsmanager:...:name"  → 经 boto3 从 Secrets Manager 读取（生产推荐）
      - "env:VAR_NAME"                       → 从环境变量读取（本地开发）
      - 其他字面量                           → 原样返回（仅演示，生产勿用）
    绝不把明文密钥写进 config / 生成代码里。"""
    if not secret_ref:
        return None
    if secret_ref in _SECRET_CACHE:
        return _SECRET_CACHE[secret_ref]

    val = None
    if secret_ref.startswith("env:"):
        val = os.environ.get(secret_ref[4:])
    elif secret_ref.startswith("arn:aws:secretsmanager:") or secret_ref.startswith("secretsmanager:"):
        val = _read_secrets_manager(secret_ref)
    else:
        # 字面量：本地演示用；生产应走上面两种
        val = secret_ref

    if val is not None:
        _SECRET_CACHE[secret_ref] = val  # 仅缓存成功结果；失败不缓存，允许轮转/瞬时故障后重试
    return val


def _read_secrets_manager(secret_ref):
    """从 AWS Secrets Manager 读取。密钥可为纯字符串或 JSON（取常见字段）。"""
    try:
        import boto3
        # 从 ARN 里解析 region；secretsmanager:REGION:... 或标准 arn
        region = None
        parts = secret_ref.split(":")
        if secret_ref.startswith("arn:aws:secretsmanager:") and len(parts) > 3:
            region = parts[3]
        client = boto3.client("secretsmanager", region_name=region) if region else boto3.client("secretsmanager")
        resp = client.get_secret_value(SecretId=secret_ref)
        raw = resp.get("SecretString")
        if not raw:
            return None
        # 若为 JSON，取常见 token 字段；否则返回整串
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                for k in ("token", "api_key", "apiKey", "value", "secret", "password"):
                    if k in obj:
                        return str(obj[k])
                # 无已知字段则返回整个 JSON 字符串
                return raw
        except (json.JSONDecodeError, ValueError):
            pass
        return raw
    except Exception as e:
        log.warning(f"读取 Secrets Manager 失败 ({secret_ref}): {e}")
        return None


class Connector:
    """连接器基类。子类实现 call()；as_tools() 把每个 operation 包成 strands @tool。"""

    def __init__(self, cfg):
        self.cfg = cfg or {}
        self.name = self.cfg.get("name", "connector")
        self.description = self.cfg.get("description", "")
        self.operations = {op["name"]: op for op in self.cfg.get("operations", []) if op.get("name")}

    # ── 工厂 ────────────────────────────────────────────────────────────────
    @classmethod
    def from_config(cls, cfg):
        """按 config 的 type 分发到对应连接器子类。"""
        _ensure_builtins_loaded()
        ctype = (cfg or {}).get("type")
        impl = _REGISTRY.get(ctype)
        if impl is None:
            raise ValueError(f"未知连接器类型: {ctype!r}（已注册: {sorted(_REGISTRY)}）")
        return impl(cfg)

    # ── 子类必须实现 ──────────────────────────────────────────────────────────
    def call(self, op_name, **kwargs):
        """执行一个 operation，返回字符串结果（工具语义：永远返回 str，出错也返回可读错误）。"""
        raise NotImplementedError

    # ── operation → strands @tool ─────────────────────────────────────────────
    def as_tools(self):
        """把每个 operation 动态包成一个 strands @tool，供 Agent 直接调用。
        惰性导入 strands，使本模块在无 strands 环境（如单测）下也可被导入/测试 call()。"""
        from strands import tool
        return [tool(self._make_tool_fn(op)) for op in self.operations.values()]

    def _make_tool_fn(self, op):
        """为单个 operation 生成一个带正确签名/类型注解/文档的函数（strands 据此推断工具 schema）。"""
        import inspect
        params = op.get("params", {}) or {}
        pytype_map = {"string": str, "number": float, "integer": int, "boolean": bool, "object": dict, "array": list}

        def fn(**kwargs):
            return self.call(op["name"], **kwargs)

        fn.__name__ = op["name"]
        fn.__doc__ = op.get("description", "") or op["name"]
        sig_params, annotations = [], {}
        for pname, pdef in params.items():
            pytype = pytype_map.get((pdef or {}).get("type"), str)
            required = bool((pdef or {}).get("required"))
            default = inspect.Parameter.empty if required else None
            sig_params.append(inspect.Parameter(
                pname, inspect.Parameter.KEYWORD_ONLY, default=default, annotation=pytype))
            annotations[pname] = pytype
        annotations["return"] = str
        fn.__signature__ = inspect.Signature(sig_params, return_annotation=str)
        fn.__annotations__ = annotations
        return fn

    # ── 辅助 ──────────────────────────────────────────────────────────────────
    def _get_op(self, op_name):
        op = self.operations.get(op_name)
        if not op:
            raise ValueError(f"连接器 {self.name} 无 operation: {op_name}")
        return op


def pick(data, expr):
    """极简 JSONPath 裁剪：支持 "$.a.b" 点路径与数字下标 "$.a.0"。用于裁剪响应，避免塞爆上下文。"""
    if not expr or not expr.startswith("$"):
        return data
    cur = data
    for seg in expr.lstrip("$").lstrip(".").split("."):
        if seg == "":
            continue
        if isinstance(cur, dict):
            cur = cur.get(seg)
        elif isinstance(cur, list) and seg.isdigit():
            idx = int(seg)
            cur = cur[idx] if 0 <= idx < len(cur) else None
        else:
            return None
        if cur is None:
            return None
    return cur
