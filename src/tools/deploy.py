"""
Delphi 部署工具

提供 Delphi 项目部署功能，支持：
- 枚举连接的设备列表（iOS/Android/Windows）
- 部署编译后的应用到设备
- 支持 PAServer (iOS/macOS) 和 ADB (Android) 等部署方式
"""

import asyncio
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logger import get_logger

logger = get_logger(__name__)


class DeployService:
    """Delphi 部署服务"""

    def __init__(self):
        self._paserver_path: Optional[str] = None
        self._adb_path: Optional[str] = None

    # ─── 设备枚举 ───────────────────────────────────────────────

    async def list_devices(self, platform: Optional[str] = None,
                           project_path: Optional[str] = None) -> Dict[str, Any]:
        """枚举连接的设备列表

        Args:
            platform: 目标平台 (iosdevice64/iossimulator/android64/androidarm64/win32/win64)。
                      不传则根据项目推断，仍无法推断则枚举所有可用平台。
            project_path: 项目文件路径（可选，用于推断目标平台）

        Returns:
            设备列表字典
        """
        platform = self._resolve_platform(platform, project_path)
        devices: List[Dict[str, Any]] = []

        if platform.startswith("ios"):
            devices = await self._list_ios_devices(platform)
        elif platform.startswith("android"):
            devices = await self._list_android_devices()
        elif platform in ("win32", "win64"):
            devices = self._list_windows_devices(platform)
        else:
            # 枚举所有可用平台
            all_devices: Dict[str, List[Dict[str, Any]]] = {}
            for plat in ("iosdevice64", "android64", "win32"):
                try:
                    result = await self.list_devices(platform=plat)
                    if result.get("devices"):
                        all_devices[plat] = result["devices"]
                except Exception as e:
                    logger.debug("枚举 %s 设备失败: %s", plat, e)
            return {
                "status": "ok",
                "platform": "all",
                "devices": all_devices,
            }

        return {
            "status": "ok",
            "platform": platform,
            "devices": devices,
        }

    async def _list_ios_devices(self, platform: str) -> List[Dict[str, Any]]:
        """枚举 iOS 设备（通过 PAServer 或 iosdeploy）

        iOS 部署需要：
        1. PAServer (Platform Assistant Server) 运行在 Mac 上
        2. 或者使用 iosdeploy / libimobiledevice 工具
        """
        devices: List[Dict[str, Any]] = []

        # 方法 1: 尝试使用 iosdeploy (libimobiledevice)
        iosdeploy_path = self._find_iosdeploy()
        if iosdeploy_path:
            try:
                proc = await asyncio.create_subprocess_exec(
                    iosdeploy_path, "--detect",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)
                output = stdout.decode("utf-8", errors="replace")
                for line in output.splitlines():
                    # 解析 iosdeploy 输出格式: "Found Apple Device: <UDID> (<Name>)"
                    match = re.search(
                        r"Found\s+(?:Apple\s+)?Device:\s+(\S+)\s+\(([^)]+)\)", line
                    )
                    if match:
                        devices.append({
                            "udid": match.group(1),
                            "name": match.group(2),
                            "platform": platform,
                            "source": "iosdeploy",
                        })
                if devices:
                    return devices
            except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
                logger.debug("iosdeploy 检测失败: %s", e)

        # 方法 2: 尝试使用 idevice_id (libimobiledevice)
        idevice_id_path = shutil.which("idevice_id")
        if idevice_id_path:
            try:
                proc = await asyncio.create_subprocess_exec(
                    idevice_id_path, "-l",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
                output = stdout.decode("utf-8", errors="replace")
                for line in output.splitlines():
                    udid = line.strip()
                    if udid:
                        # 获取设备名称
                        name = await self._get_ios_device_name(idevice_id_path, udid)
                        devices.append({
                            "udid": udid,
                            "name": name or udid,
                            "platform": platform,
                            "source": "libimobiledevice",
                        })
                if devices:
                    return devices
            except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
                logger.debug("idevice_id 检测失败: %s", e)

        # 方法 3: 尝试使用 MSBuild 部署目标探测
        # MSBuild 在编译时会自动检测连接的 iOS 设备
        logger.info("未检测到 iOS 设备枚举工具 (iosdeploy/libimobiledevice)")
        logger.info("提示: 请确保设备已通过 USB 连接并信任此电脑")
        logger.info("提示: 可安装 libimobiledevice: https://libimobiledevice.org/")
        return devices

    async def _get_ios_device_name(self, idevice_id_path: str, udid: str) -> Optional[str]:
        """获取 iOS 设备名称"""
        idevice_name = shutil.which("ideviceinfo")
        if not idevice_name:
            return None
        try:
            proc = await asyncio.create_subprocess_exec(
                idevice_name, "-u", udid, "-k", "DeviceName",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            output = stdout.decode("utf-8", errors="replace").strip()
            # 输出格式: "DeviceName: <name>"
            if ": " in output:
                return output.split(": ", 1)[1].strip()
        except Exception:
            pass
        return None

    async def _list_android_devices(self) -> List[Dict[str, Any]]:
        """枚举 Android 设备（通过 ADB）"""
        devices: List[Dict[str, Any]] = []

        adb_path = self._find_adb()
        if not adb_path:
            logger.info("未找到 ADB 工具")
            logger.info("提示: 请安装 Android SDK Platform Tools")
            logger.info("提示: 或设置 ANDROID_HOME 环境变量")
            return devices

        try:
            proc = await asyncio.create_subprocess_exec(
                adb_path, "devices", "-l",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            output = stdout.decode("utf-8", errors="replace")

            for line in output.splitlines():
                # 跳过标题行和空行
                if line.startswith("List of") or not line.strip():
                    continue
                # 解析 ADB 设备输出格式: "<serial>   device [usb:<path>] [model:<name>]"
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    serial = parts[0]
                    # 提取 model
                    model = ""
                    for part in parts[2:]:
                        if part.startswith("model:"):
                            model = part.split(":", 1)[1]
                            break
                    devices.append({
                        "serial": serial,
                        "name": model or serial,
                        "platform": "android",
                        "status": "device",
                        "source": "adb",
                    })
        except asyncio.TimeoutError:
            logger.warning("ADB 设备列表获取超时")
        except FileNotFoundError:
            logger.warning("ADB 工具执行失败")

        return devices

    def _list_windows_devices(self, platform: str) -> List[Dict[str, Any]]:
        """列出 Windows 本地设备（始终返回本机）"""
        import socket
        hostname = socket.gethostname()
        return [{
            "serial": "local",
            "name": hostname,
            "platform": platform,
            "status": "local",
            "source": "local",
        }]

    # ─── 部署 ───────────────────────────────────────────────────

    async def deploy(self, project_path: str, target_platform: str,
                     device_id: Optional[str] = None,
                     build_configuration: str = "Debug",
                     extra_args: Optional[List[str]] = None,
                     timeout: int = 600) -> Dict[str, Any]:
        """部署编译后的应用到设备

        Args:
            project_path: 项目文件路径 (.dproj/.dpr)
            target_platform: 目标平台 (iosdevice64/android64/win32 等)
            device_id: 目标设备 ID（如 iOS UDID 或 Android serial），
                       不传则部署到默认设备
            build_configuration: 编译配置 (Debug/Release)
            extra_args: 附加到 MSBuild 的参数
            timeout: 超时秒数

        Returns:
            部署结果字典
        """
        project_path_obj = Path(project_path)
        if not project_path_obj.exists():
            return {"status": "failed", "message": f"项目文件不存在: {project_path}"}

        # 确定 .dproj 路径
        dproj_path = project_path
        if project_path_obj.suffix.lower() == ".dpr":
            dproj_path = str(project_path_obj.with_suffix(".dproj"))

        if not Path(dproj_path).exists():
            return {"status": "failed", "message": f"未找到 .dproj 文件: {dproj_path}"}

        target_platform = target_platform.lower()

        # 根据平台选择部署方式
        if target_platform.startswith("ios"):
            return await self._deploy_ios(
                dproj_path, target_platform, device_id,
                build_configuration, extra_args, timeout,
            )
        elif target_platform.startswith("android"):
            return await self._deploy_android(
                dproj_path, target_platform, device_id,
                build_configuration, extra_args, timeout,
            )
        elif target_platform in ("win32", "win64"):
            return await self._deploy_windows(
                dproj_path, target_platform,
                build_configuration, extra_args, timeout,
            )
        else:
            return {
                "status": "failed",
                "message": f"不支持的部署平台: {target_platform}。"
                           f"支持的平台: iosdevice64, android64, win32, win64",
            }

    async def _deploy_ios(self, dproj_path: str, platform: str,
                          device_id: Optional[str], build_configuration: str,
                          extra_args: Optional[List[str]], timeout: int) -> Dict[str, Any]:
        """部署到 iOS 设备

        使用 MSBuild 的 Deploy 目标进行部署。
        需要 PAServer (Platform Assistant Server) 运行在 Mac 上。
        """
        # 查找 MSBuild
        msbuild_path = self._find_msbuild()
        if not msbuild_path:
            return {
                "status": "failed",
                "message": "未找到 MSBuild。iOS 部署需要 MSBuild。",
            }

        # 构建 MSBuild 参数
        msbuild_args = [
            msbuild_path,
            dproj_path,
            "/t:Deploy",
            f"/p:Platform={self._msbuild_platform(platform)}",
            f"/p:Config={build_configuration}",
        ]

        # 添加设备 ID
        if device_id:
            msbuild_args.append(f"/p:DevId={device_id}")

        # 添加 PAServer 密码（如果有）
        paserver_password = os.environ.get("PASERVER_PASSWORD", "")
        if paserver_password:
            msbuild_args.append(f"/p:DevicePassword={paserver_password}")

        # 添加额外参数
        if extra_args:
            msbuild_args.extend(extra_args)

        logger.info("iOS 部署命令: %s", " ".join(msbuild_args))

        try:
            proc = await asyncio.create_subprocess_exec(
                *msbuild_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            return_code = proc.returncode

            if return_code == 0:
                return {
                    "status": "ok",
                    "message": "iOS 部署成功",
                    "platform": platform,
                    "device_id": device_id,
                    "log": stdout_text[-2000:] if len(stdout_text) > 2000 else stdout_text,
                }
            else:
                return {
                    "status": "failed",
                    "message": f"iOS 部署失败 (exit code: {return_code})",
                    "platform": platform,
                    "device_id": device_id,
                    "log": stdout_text[-2000:] if len(stdout_text) > 2000 else stdout_text,
                    "error": stderr_text[-1000:] if stderr_text else "",
                }
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "message": f"iOS 部署超时 ({timeout}秒)",
                "platform": platform,
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"iOS 部署异常: {str(e)}",
                "platform": platform,
            }

    async def _deploy_android(self, dproj_path: str, platform: str,
                              device_id: Optional[str], build_configuration: str,
                              extra_args: Optional[List[str]], timeout: int) -> Dict[str, Any]:
        """部署到 Android 设备

        使用 MSBuild 的 Deploy 目标进行部署。
        需要 Android SDK 和 ADB。
        """
        msbuild_path = self._find_msbuild()
        if not msbuild_path:
            return {
                "status": "failed",
                "message": "未找到 MSBuild。Android 部署需要 MSBuild。",
            }

        # 构建 MSBuild 参数
        msbuild_args = [
            msbuild_path,
            dproj_path,
            "/t:Deploy",
            f"/p:Platform={self._msbuild_platform(platform)}",
            f"/p:Config={build_configuration}",
        ]

        # 添加设备 ID
        if device_id:
            msbuild_args.append(f"/p:DeviceId={device_id}")

        # 添加额外参数
        if extra_args:
            msbuild_args.extend(extra_args)

        logger.info("Android 部署命令: %s", " ".join(msbuild_args))

        try:
            proc = await asyncio.create_subprocess_exec(
                *msbuild_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )

            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")
            return_code = proc.returncode

            if return_code == 0:
                return {
                    "status": "ok",
                    "message": "Android 部署成功",
                    "platform": platform,
                    "device_id": device_id,
                    "log": stdout_text[-2000:] if len(stdout_text) > 2000 else stdout_text,
                }
            else:
                return {
                    "status": "failed",
                    "message": f"Android 部署失败 (exit code: {return_code})",
                    "platform": platform,
                    "device_id": device_id,
                    "log": stdout_text[-2000:] if len(stdout_text) > 2000 else stdout_text,
                    "error": stderr_text[-1000:] if stderr_text else "",
                }
        except asyncio.TimeoutError:
            return {
                "status": "failed",
                "message": f"Android 部署超时 ({timeout}秒)",
                "platform": platform,
            }
        except Exception as e:
            return {
                "status": "failed",
                "message": f"Android 部署异常: {str(e)}",
                "platform": platform,
            }

    async def _deploy_windows(self, dproj_path: str, platform: str,
                              build_configuration: str,
                              extra_args: Optional[List[str]], timeout: int) -> Dict[str, Any]:
        """Windows 本地部署

        Windows 部署本质上是编译后的文件复制到目标目录。
        """
        # 对于 Windows，"部署"主要是确保编译产物在正确位置
        # 可以调用 compile 然后返回产物路径
        return {
            "status": "ok",
            "message": "Windows 本地部署：编译产物已在本地",
            "platform": platform,
            "hint": "Windows 无需远程部署，编译后可直接运行",
            "action_required": "请使用 action='compile' 编译项目",
        }

    # ─── 工具查找 ───────────────────────────────────────────────

    def _find_adb(self) -> Optional[str]:
        """查找 ADB 工具"""
        # 1. 检查 ANDROID_HOME
        android_home = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT")
        if android_home:
            adb_path = Path(android_home) / "platform-tools" / "adb.exe"
            if adb_path.exists():
                return str(adb_path)

        # 2. 检查 PATH
        adb_in_path = shutil.which("adb")
        if adb_in_path:
            return adb_in_path

        # 3. 常见安装路径
        common_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk" / "platform-tools" / "adb.exe",
            Path(os.environ.get("PROGRAMFILES", "")) / "Android" / "sdk" / "platform-tools" / "adb.exe",
        ]
        for p in common_paths:
            if p.exists():
                return str(p)

        return None

    def _find_iosdeploy(self) -> Optional[str]:
        """查找 iosdeploy 工具"""
        return shutil.which("iosdeploy")

    def _find_msbuild(self) -> Optional[str]:
        """查找 MSBuild 工具"""
        # 复用 compiler_service 的逻辑
        try:
            from .compile_project import _compiler_service
            if _compiler_service and _compiler_service.msbuild_path:
                return _compiler_service.msbuild_path
        except ImportError:
            pass

        # 回退: 查找 vswhere
        program_files_x86 = os.environ.get("ProgramFiles(x86)", "")
        vswhere = Path(program_files_x86) / "Microsoft Visual Studio" / "Installer" / "vswhere.exe"
        if vswhere.exists():
            try:
                result = subprocess.run(
                    [
                        str(vswhere),
                        "-latest", "-products", "*",
                        "-requires", "Microsoft.Component.MSBuild",
                        "-find", r"MSBuild\**\Bin\MSBuild.exe",
                    ],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    paths = result.stdout.strip().splitlines()
                    if paths:
                        return paths[0]
            except Exception:
                pass

        return None

    def _resolve_platform(self, platform: Optional[str],
                          project_path: Optional[str]) -> str:
        """解析目标平台"""
        if platform:
            return platform.lower()

        # 尝试从项目推断
        if project_path:
            try:
                from ..utils.dproj_parser import DprojParser
                dproj_path = project_path
                if project_path.lower().endswith(".dpr"):
                    dproj_path = str(Path(project_path).with_suffix(".dproj"))
                parser = DprojParser(dproj_path)
                if parser.parse():
                    target = parser.get_target_platform()
                    if target:
                        return target.lower()
            except Exception:
                pass

        return "win32"

    def _msbuild_platform(self, platform: str) -> str:
        """转换平台名为 MSBuild 格式"""
        platform_map = {
            "win32": "Win32",
            "win64": "Win64",
            "iosdevice64": "iOSDevice64",
            "iossimulator": "iOSSimulator",
            "android64": "Android64",
            "androidarm64": "Android64",
            "osx64": "OSX64",
            "osxarm64": "OSXARM64",
            "linux64": "Linux64",
        }
        return platform_map.get(platform, platform.capitalize())


# 全局实例
_deploy_service: Optional[DeployService] = None


def get_deploy_service() -> DeployService:
    """获取部署服务单例"""
    global _deploy_service
    if _deploy_service is None:
        _deploy_service = DeployService()
    return _deploy_service


# ─── MCP 工具入口 ──────────────────────────────────────────────


async def deploy_project(**kwargs) -> Dict[str, Any]:
    """部署 Delphi 项目到设备

    Args:
        action: 操作类型 (devices/deploy)
        project_path: 项目文件路径 (.dproj/.dpr)
        target_platform: 目标平台
        device_id: 目标设备 ID
        build_configuration: 编译配置
        extra_args: 附加参数
        timeout: 超时秒数

    Returns:
        操作结果
    """
    action = kwargs.get("action", "devices")
    service = get_deploy_service()

    try:
        if action == "devices":
            return await service.list_devices(
                platform=kwargs.get("target_platform"),
                project_path=kwargs.get("project_path"),
            )
        elif action == "deploy":
            project_path = kwargs.get("project_path", "")
            if not project_path:
                return {"status": "failed", "message": "缺少必需参数: project_path"}

            target_platform = kwargs.get("target_platform", "")
            if not target_platform:
                return {"status": "failed", "message": "缺少必需参数: target_platform"}

            return await service.deploy(
                project_path=project_path,
                target_platform=target_platform,
                device_id=kwargs.get("device_id"),
                build_configuration=kwargs.get("build_configuration", "Debug"),
                extra_args=kwargs.get("extra_args"),
                timeout=kwargs.get("timeout", 600),
            )
        else:
            return {
                "status": "failed",
                "message": f"未知 action: {action}。可用 actions: devices, deploy",
            }
    except Exception as e:
        logger.exception("部署操作失败")
        return {"status": "failed", "message": str(e)}
