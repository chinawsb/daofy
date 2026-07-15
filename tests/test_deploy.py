#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
部署工具测试

测试 src/tools/deploy.py 的设备枚举和部署功能
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ============================================================
# DeployService 测试
# ============================================================

def test_deploy_service_singleton():
    """测试 DeployService 单例模式"""
    from src.tools.deploy import get_deploy_service
    
    service1 = get_deploy_service()
    service2 = get_deploy_service()
    
    assert service1 is service2, "应该返回同一个实例"
    print("  DeployService 单例模式正确")


def test_deploy_service_resolve_platform():
    """测试平台解析逻辑"""
    from src.tools.deploy import DeployService
    
    service = DeployService()
    
    # 直接指定平台
    assert service._resolve_platform("iosdevice64", None) == "iosdevice64"
    assert service._resolve_platform("Android64", None) == "android64"
    assert service._resolve_platform("win32", None) == "win32"
    
    # 默认平台
    assert service._resolve_platform(None, None) == "win32"
    
    print("  平台解析逻辑正确")


def test_deploy_service_msbuild_platform():
    """测试 MSBuild 平台名转换"""
    from src.tools.deploy import DeployService
    
    service = DeployService()
    
    assert service._msbuild_platform("win32") == "Win32"
    assert service._msbuild_platform("win64") == "Win64"
    assert service._msbuild_platform("iosdevice64") == "iOSDevice64"
    assert service._msbuild_platform("android64") == "Android64"
    
    print("  MSBuild 平台名转换正确")


def test_list_windows_devices():
    """测试 Windows 本地设备列表"""
    from src.tools.deploy import DeployService
    
    service = DeployService()
    devices = service._list_windows_devices("win32")
    
    assert len(devices) == 1, "Windows 应返回一个本地设备"
    assert devices[0]["serial"] == "local", "设备 serial 应为 local"
    assert devices[0]["platform"] == "win32", "平台应为 win32"
    assert devices[0]["source"] == "local", "来源应为 local"
    
    print("  Windows 本地设备列表正确")


@pytest.mark.asyncio
async def test_list_devices_windows():
    """测试枚举 Windows 设备"""
    from src.tools.deploy import DeployService
    
    service = DeployService()
    result = await service.list_devices(platform="win32")
    
    assert result["status"] == "ok", f"状态应为 ok，实际: {result}"
    assert result["platform"] == "win32", "平台应为 win32"
    assert len(result["devices"]) == 1, "应返回一个本地设备"
    
    print("  枚举 Windows 设备正确")


@pytest.mark.asyncio
async def test_list_devices_all():
    """测试枚举所有平台设备"""
    from src.tools.deploy import DeployService
    
    service = DeployService()
    # 传入 "all" 枚举所有平台
    result = await service.list_devices(platform="all")
    
    assert result["status"] == "ok", f"状态应为 ok，实际: {result}"
    assert result["platform"] == "all", "平台应为 all"
    assert "devices" in result, "应包含 devices 字段"
    
    print("  枚举所有平台设备正确")


@pytest.mark.asyncio
async def test_deploy_project_missing_path():
    """测试部署时缺少项目路径"""
    from src.tools.deploy import deploy_project
    
    result = await deploy_project(action="deploy")
    
    assert result["status"] == "failed", f"状态应为 failed，实际: {result}"
    assert "project_path" in result["message"], "错误信息应包含 project_path"
    
    print("  部署缺少项目路径检查正确")


@pytest.mark.asyncio
async def test_deploy_project_missing_platform():
    """测试部署时缺少目标平台"""
    from src.tools.deploy import deploy_project
    
    result = await deploy_project(action="deploy", project_path="App.dproj")
    
    assert result["status"] == "failed", f"状态应为 failed，实际: {result}"
    assert "target_platform" in result["message"], "错误信息应包含 target_platform"
    
    print("  部署缺少目标平台检查正确")


@pytest.mark.asyncio
async def test_deploy_project_invalid_action():
    """测试无效的部署 action"""
    from src.tools.deploy import deploy_project
    
    result = await deploy_project(action="invalid")
    
    assert result["status"] == "failed", f"状态应为 failed，实际: {result}"
    assert "未知 action" in result["message"], "错误信息应包含 未知 action"
    
    print("  无效部署 action 检查正确")


@pytest.mark.asyncio
async def test_deploy_windows_local():
    """测试 Windows 本地部署"""
    from src.tools.deploy import DeployService
    
    service = DeployService()
    result = await service._deploy_windows(
        dproj_path="App.dproj",
        platform="win32",
        build_configuration="Debug",
        extra_args=None,
        timeout=600,
    )
    
    assert result["status"] == "ok", f"状态应为 ok，实际: {result}"
    assert "hint" in result, "应包含提示信息"
    
    print("  Windows 本地部署正确")


def test_find_adb_not_found():
    """测试 ADB 查找（未找到时）"""
    from src.tools.deploy import DeployService
    
    service = DeployService()
    
    # 清除环境变量
    with patch.dict(os.environ, {}, clear=True):
        adb_path = service._find_adb()
        # 可能找到也可能找不到，取决于系统环境
        # 这里只测试不报错
        print(f"  ADB 查找结果: {adb_path}")


def test_find_msbuild():
    """测试 MSBuild 查找"""
    from src.tools.deploy import DeployService
    
    service = DeployService()
    msbuild_path = service._find_msbuild()
    
    # 可能找到也可能找不到，取决于系统环境
    print(f"  MSBuild 查找结果: {msbuild_path}")


# ============================================================
# 集成测试
# ============================================================

@pytest.mark.asyncio
async def test_project_handler_deploy():
    """测试 project handler 的 deploy action"""
    from src.tools.project import handle_project
    
    # 测试 devices action
    result = await handle_project(action="devices", target_platform="win32")
    assert result["status"] == "ok", f"状态应为 ok，实际: {result}"
    
    print("  project handler deploy action 正确")


if __name__ == "__main__":
    print("=== 部署工具测试 ===\n")
    
    test_deploy_service_singleton()
    test_deploy_service_resolve_platform()
    test_deploy_service_msbuild_platform()
    test_list_windows_devices()
    
    asyncio.run(test_list_devices_windows())
    asyncio.run(test_list_devices_all())
    asyncio.run(test_deploy_project_missing_path())
    asyncio.run(test_deploy_project_missing_platform())
    asyncio.run(test_deploy_project_invalid_action())
    asyncio.run(test_deploy_windows_local())
    
    test_find_adb_not_found()
    test_find_msbuild()
    
    asyncio.run(test_project_handler_deploy())
    
    print("\n=== 所有测试通过 ===")
