"""Daofy MCP Server 入口

允许通过 python -m src 启动，绕过 pip 生成的 .exe 包装器
在路径含空格的 Windows 环境下，.exe 包装器可能被 MCP 客户端错误拆分。
"""
from src.server import main

main()
