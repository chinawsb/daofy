#!/usr/bin/env python3
"""
MCP 客户端测试脚本 — 使用 mcp 官方库
启动 MCP Server → 通过 stdio 协议调用工具 → 测量性能

用法:
    python test_mcp_client.py --test-only             # 只测试连接
    python test_mcp_client.py --project <path.dproj>   # 测试构建
    python test_mcp_client.py                          # 自动检测项目
"""

import sys
import os
import time
import asyncio
import json
from pathlib import Path

# ============================================================
# 使用 mcp 官方库
# ============================================================
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession
from datetime import timedelta


async def call_tool(session: ClientSession, name: str, arguments: dict = None, timeout_seconds: int = 600) -> dict:
    """调用 MCP 工具并返回结果"""
    td = timedelta(seconds=timeout_seconds)
    result = await session.call_tool(name, arguments or {}, read_timeout_seconds=td)
    return result


def _extract_text(result) -> str:
    """从 MCP CallToolResult 中提取文本"""
    if hasattr(result, 'content') and result.content:
        texts = []
        for c in result.content:
            if hasattr(c, 'text'):
                texts.append(c.text)
        return '\n'.join(texts)
    elif isinstance(result, dict):
        return str(result)
    return str(result)


async def run_build_test(session: ClientSession, project_path: str):
    """测试项目知识库构建性能"""
    print("\n" + "=" * 60)
    print("测试: 项目知识库构建 (force_rebuild=True)")
    print("项目: %s" % project_path)
    print("=" * 60)

    # 1. 构建项目知识库 (async_mode=True)
    print("\n[1/3] 发起构建请求...")
    t0 = time.time()
    args_dict = {
        "action": "build",
        "kb_type": "project",
        "project_path": project_path,
        "async_mode": True,
        "force_rebuild": True,
    }
    try:
        result = await call_tool(session, "delphi_kb", args_dict)
    except Exception as e:
        print("  [ERR] 构建请求失败: %s" % e)
        return None
    t1 = time.time()
    print("  → 请求耗时: %.1fs" % (t1 - t0))

    text = _extract_text(result)
    print("  → 响应: %s" % text[:300])

    # 解析 task_id
    import re
    task_id = None
    # 格式: "任务ID: task_1778740062_1" 或 "task_id='task_1778740062_1'"
    for p in [r'任务ID[=:]\s*(\w+)', r'task_id[=:]\s*(\w+)', r'task[=:]\s*(\w+)', r'task_(\d+_\d+)']:
        match = re.search(p, text)
        if match:
            task_id = match.group(1)
            if not task_id.startswith('task_'):
                task_id = 'task_' + task_id
            break

    if not task_id:
        print("  [?] 未获取到 task_id，尝试查看现有任务列表...")
        list_result = await call_tool(session, "async_task", {"action": "list"})
        list_text = _extract_text(list_result)
        print("  tasks: %s" % list_text[:300])
        for p in [r'task_id[=:]\s*(\w+)', r'task_(\d+_\d+)']:
            match = re.search(p, list_text)
            if match:
                g = match.group(1)
                task_id = g if g.startswith('task_') else ('task_' + g)
                break
        if not task_id:
            print("  [?] 仍无法获取 task_id")
            return None

    print("  -> task_id: %s" % task_id)

    # 2. 轮询构建状态
    print("\n[2/3] 轮询构建状态...")
    poll_count = 0
    t_start = time.time()

    while True:
        poll_count += 1
        t_poll = time.time()
        try:
            result = await call_tool(session, "async_task", {
                "action": "status",
                "task_id": task_id,
                "show_progress": True,
            }, timeout_seconds=120)
        except Exception as e:
            print("  [%d] %.0fs | 查询失败: %s" % (poll_count, t_poll - t_start, e))
            await asyncio.sleep(5)
            continue

        text = _extract_text(result)
        print("  [%d] %.0fs | %s" % (poll_count, t_poll - t_start, text[:200]))

        text_lower = text.lower()
        if "completed" in text_lower or "success" in text_lower:
            if "failed" not in text_lower:
                break
        if "failed" in text_lower and "task not found" not in text_lower:
            print("  [ERR] 构建失败")
            break
        if t_poll - t_start > 600:
            print("  超时 (600s)")
            break

        await asyncio.sleep(2)

    t_total = time.time() - t_start
    print("\n  [OK] 构建完成！总耗时: %.1fs" % t_total)
    print("  总轮询次数: %d" % poll_count)

    # 3. 获取统计
    print("\n[3/3] 获取知识库统计...")
    try:
        result = await call_tool(session, "delphi_kb", {"action": "stats"})
        print("  stats: %s" % _extract_text(result)[:500])
    except Exception as e:
        print("  stats 查询失败: %s" % e)

    return t_total


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="MCP 客户端测试脚本")
    parser.add_argument("--project", default=None, help="项目 .dproj 路径")
    parser.add_argument("--server", default=None, help="MCP Server 脚本路径 (默认: src/server.py)")
    parser.add_argument("--python", default=None, help="Python 解释器路径")
    parser.add_argument("--test-only", action="store_true", help="只测试连接和工具列表，不构建")
    parser.add_argument("--no-stderr", action="store_true", help="不显示 server stderr")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.resolve()
    server_script = args.server or str(base_dir / "src" / "server.py")

    if not Path(server_script).exists():
        print("[ERR] Server 脚本不存在: %s" % server_script)
        sys.exit(1)

    print("MCP 测试客户端 (mcp库版本: 1.26.0)")
    print("  Python: %s" % sys.executable)
    print("  Server: %s" % server_script)

    # 自动检测项目路径
    project_path = args.project
    if not project_path:
        dproj_files = list(base_dir.glob("*.dproj"))
        if not dproj_files:
            dproj_files = list(base_dir.parent.glob("*.dproj"))
        if dproj_files:
            project_path = str(dproj_files[0])
            print("  自动检测项目: %s" % project_path)
        else:
            for c in ["C:/User/diandaxia/diandaxia.dproj"]:
                if Path(c).exists():
                    project_path = c
                    print("  默认项目: %s" % project_path)
                    break

    if not project_path and not args.test_only:
        print("  [?] 未找到项目文件，请通过 --project 指定")
        sys.exit(1)

    # 创建 StdioServerParameters
    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_script)],
        env={
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        },
    )

    print("\n启动 MCP Server...")
    try:
        async with stdio_client(server_params, errlog=sys.stderr) as (read, write):
            async with ClientSession(read, write) as session:
                # 初始化
                print("  初始化中...")
                await session.initialize()
                print("  [OK] Server 已启动并初始化")

                # 列出工具
                tools_result = await session.list_tools()
                tools = tools_result.tools if hasattr(tools_result, 'tools') else []
                tool_names = [t.name for t in tools]
                print("  可用工具 (%d): %s%s" % (
                    len(tools),
                    ', '.join(tool_names[:15]),
                    '...' if len(tools) > 15 else ''
                ))

                if args.test_only:
                    print("\n[OK] 连接测试通过")
                    return

                if project_path:
                    project_path = project_path.replace("\\", "/")
                    if not Path(project_path).exists():
                        print("  项目文件不存在: %s" % project_path)
                        sys.exit(1)

                    # 测试构建
                    await run_build_test(session, project_path)

    except Exception as e:
        print("\n[ERR] 运行失败: %s" % e)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
