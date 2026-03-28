"""
编码规则工具

提供 Delphi 源码编码规则查询功能
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from mcp.types import CallToolResult, TextContent
from ..utils.logger import get_logger

logger = get_logger(__name__)


async def get_coding_rules(project_path: Optional[str] = None) -> CallToolResult:
    """
    获取 Delphi 源码编码规则

    默认读取 config/CODING_RULES.mdc 文件，
    如果用户项目目录下存在 CODING_RULES.mdc，则合并用户规则（用户规则覆盖默认规则）

    Args:
        project_path: 项目路径（可选），用于查找用户自定义的编码规则文件

    Returns:
        编码规则内容字典
    """
    logger.info(f"收到获取编码规则请求，项目路径: {project_path}")

    try:
        # 获取默认编码规则文件路径
        current_dir = Path(__file__).parent.parent.parent
        default_rules_path = current_dir / "config" / "CODING_RULES.mdc"

        # 读取默认编码规则
        default_rules = ""
        if default_rules_path.exists():
            try:
                with open(default_rules_path, 'r', encoding='utf-8') as f:
                    default_rules = f.read()
                logger.info(f"成功读取默认编码规则文件: {default_rules_path}")
            except Exception as e:
                logger.error(f"读取默认编码规则文件失败: {str(e)}")
                default_rules = ""
        else:
            logger.warning(f"默认编码规则文件不存在: {default_rules_path}")

        # 如果提供了项目路径，尝试读取用户自定义的编码规则
        user_rules = ""
        if project_path:
            project_dir = Path(project_path)
            user_rules_path = project_dir / "CODING_RULES.mdc"

            if user_rules_path.exists():
                try:
                    with open(user_rules_path, 'r', encoding='utf-8') as f:
                        user_rules = f.read()
                    logger.info(f"成功读取用户自定义编码规则文件: {user_rules_path}")
                except Exception as e:
                    logger.error(f"读取用户自定义编码规则文件失败: {str(e)}")
                    user_rules = ""
            else:
                logger.info(f"用户项目目录下未找到自定义编码规则文件: {user_rules_path}")

        # 合并规则（用户规则覆盖默认规则）
        # 这里采用简单的策略：如果有用户规则，则使用用户规则；否则使用默认规则
        # 更复杂的合并策略可以根据实际需求实现
        final_rules = user_rules if user_rules else default_rules

        # 如果两者都不存在，返回空字符串
        if not final_rules:
            logger.warning("未找到任何编码规则文件")
            return CallToolResult(
                content=[TextContent(type="text", text="未找到任何编码规则文件")],
                isError=True
            )

        logger.info("成功获取编码规则")
        output = f"编码规则 (来源: {'用户' if user_rules else '默认'}):\n\n"
        output += final_rules[:2000]  # 限制输出长度
        return CallToolResult(content=[TextContent(type="text", text=output)])

    except Exception as e:
        error_msg = f"获取编码规则过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[TextContent(type="text", text=error_msg)],
            isError=True
        )
