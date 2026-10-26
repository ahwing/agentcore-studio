# ABOUTME: 连接器框架包 —— 声明式接入业务系统，生成 agent 可调用的工具。
from .base import Connector, register, resolve_secret, pick
from . import rest  # noqa: F401  —— 导入内置连接器以完成自注册

__all__ = ["Connector", "register", "resolve_secret", "pick"]
