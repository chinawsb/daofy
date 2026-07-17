"""
Daofy 插件系统

提供语言无关的编译器插件架构，支持 Delphi、Lazarus/FPC 等编译器。
"""

from .base import CompilerPlugin, PluginInfo
from .registry import PluginRegistry

__all__ = ["CompilerPlugin", "PluginInfo", "PluginRegistry"]
