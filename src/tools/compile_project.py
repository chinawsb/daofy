"""
工程编译工具

提供 Delphi 工程整体编译功能
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
from mcp.types import CallToolResult
from ..models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform, OutputType, RuntimeLibrary
from ..models.compile_result import CompileResult
from ..services.compiler_service import CompilerService
from ..utils.dproj_parser import DprojParser
from ..utils.logger import get_logger
from ..utils.dproj_parser import resolve_target_platform_from_dproj
import shlex
import subprocess as _subprocess

# 导入 install_package 中的函数（复用已有逻辑）
try:
    from .install_package import (
        _is_runtime_only_package,
        _get_delphi_version,
        _register_packages_to_ide,
        _compile_single_package
    )
    _has_install_package = True
except ImportError:
    _has_install_package = False

logger = get_logger(__name__)

# 全局编译服务实例
_compiler_service: Optional[CompilerService] = None


def set_compiler_service(service: CompilerService):
    """设置编译服务实例"""
    global _compiler_service
    _compiler_service = service


def _detect_compiler_from_project(project_path: str, target_platform: str) -> Optional[str]:
    """
    从项目中自动检测最适配的编译器

    Args:
        project_path: 项目文件路径
        target_platform: 目标平台

    Returns:
        编译器名称,如果检测失败则返回 None
    """
    project_path_obj = Path(project_path)
    if not project_path_obj.exists():
        logger.warning(f"项目文件不存在: {project_path}")
        return None

    dproj_path = project_path
    if project_path_obj.suffix.lower() == '.dpr':
        dproj_path = str(project_path_obj.with_suffix('.dproj'))

    if not Path(dproj_path).exists():
        logger.warning(f"未找到 .dproj 文件: {dproj_path}")
        return None

    parser = DprojParser(dproj_path)
    if not parser.parse():
        logger.error(f"解析 .dproj 文件失败: {dproj_path}")
        return None

    project_version = parser.get_project_version()
    if not project_version:
        logger.warning(f"未获取到项目版本号: {dproj_path}")
        return None

    logger.info(f"项目版本号: {project_version}")

    if _compiler_service and _compiler_service.config_manager:
        compiler = _compiler_service.config_manager.get_compiler_for_project(project_version, target_platform)
        if compiler:
            logger.info(f"自动匹配编译器: {compiler.name}")
            return compiler.name

    return None


def _cleanup_project_dcu(project_dir: Path):
    """递归清理项目目录下的所有 .dcu / .dcpp / .dpu 缓存文件"""
    patterns = ['**/*.dcu', '**/*.dcpp', '**/*.dpu']
    deleted = 0
    for pattern in patterns:
        for f in Path(project_dir).glob(pattern):
            try:
                f.unlink()
                deleted += 1
            except OSError as e:
                logger.debug(f"删除缓存文件失败: {f}: {e}")
    if deleted > 0:
        logger.info(f"已清理 {deleted} 个编译器缓存文件")


def _check_and_clean_stale_resources(project_path: str, build_configuration: Optional[str] = None, target_platform: str = "win32") -> bool:
    """
    检测 .dproj 中引用的资源文件是否比已生成的 exe 更新。
    如果资源文件更新，则删除对应的 .res 文件，强制 brcc32 重新编译。

    .dproj 中每个 <RcItem Include="..."> 对应一个资源源文件，
    编译器通过 brcc32 将其编译为 .res 后链接到 exe。
    但 MSBuild 增量编译对 <RcItem> 的变更检测不可靠，
    修改源文件后可能不会触发重新编译。

    Returns:
        True 表示有资源文件变更（已处理），False 表示无需处理
    """
    try:
        proj_path = Path(project_path)
        if not proj_path.exists():
            return False

        # 解析 .dproj 获取资源引用
        parser = DprojParser(str(proj_path))
        if not parser.parse():
            return False

        resources = parser.get_resource_items()
        if not resources:
            return False

        # 获取输出 exe 路径
        config = build_configuration or "Debug"
        platform = target_platform or "win32"
        # 统一平台名首字母大写: win32 → Win32, win64 → Win64
        platform_cap = platform.capitalize() if platform in ("win32", "win64") else platform

        exe_dir_str = parser.get_output_path(config=config, platform=platform_cap)
        if not exe_dir_str:
            # 尝试从 dproj 目录默认输出路径查找
            project_dir = proj_path.parent
            exe_dir = project_dir / platform_cap / config
        else:
            exe_dir = Path(exe_dir_str)

        # 查找 exe
        project_name = proj_path.stem
        exe_path = exe_dir / f"{project_name}.exe"
        if not exe_path.exists():
            return False

        exe_mtime = exe_path.stat().st_mtime

        stale_resources = []
        for res in resources:
            src_path = res["source_path"]
            src_file = Path(src_path)
            if not src_file.exists():
                continue
            # 资源源文件比 exe 新 → 需要重新编译
            if src_file.stat().st_mtime > exe_mtime:
                stale_resources.append(res)

        if not stale_resources:
            return False

        # 有资源变更: 删除可能生成的 .res 文件（brcc32 产物）和 .dcu 缓存
        res_files_cleaned = 0
        for res in stale_resources:
            # brcc32 输出: 项目目录下同名的 .res 文件
            src_file = Path(res["source_path"])
            possible_res = src_file.with_suffix(".res")
            if possible_res.exists():
                possible_res.unlink()
                res_files_cleaned += 1
                logger.info(f"资源变更 → 已删除旧 .res: {possible_res.name}")

        # 同时清理项目目录下可能存在的 .res 缓存
        # Delphi 有时会在 $(BDS)\lib\$(Platform)\release 下生成 .res
        for res in stale_resources:
            res_name = f"{res['resource_id']}.res"
            for cached in proj_path.parent.rglob(res_name):
                try:
                    cached.unlink()
                    logger.info(f"资源变更 → 已删除缓存: {cached}")
                except Exception as e:
                    logger.debug("忽略非致命异常: %s", str(e))

        # 也清理 .dcu 缓存（资源变动可能影响代码路径）
        _cleanup_project_dcu(proj_path.parent)

        logger.info(
            f"检测到 {len(stale_resources)} 个资源文件已变更: "
            + ", ".join(r["resource_id"] or r["include"] for r in stale_resources)
            + "，已清理缓存，将执行完整重新编译"
        )
        return True

    except Exception as e:
        logger.warning(f"资源变更检测异常(不影响编译): {e}")
        return False


async def compile_project(
    project_path: str,
    target_platform: Optional[str] = None,
    output_path: Optional[str] = None,
    compiler_version: Optional[str] = None,
    timeout: int = 600,
    conditional_defines: Optional[List[str]] = None,
    unit_search_paths: Optional[List[str]] = None,
    resource_search_paths: Optional[List[str]] = None,
    optimize: bool = True,
    debug: bool = False,
    warning_level: int = 2,
    disabled_warnings: Optional[List[str]] = None,
    output_type: str = "gui",
    runtime_library: str = "static",
    build_configuration: Optional[str] = None,
    auto_install: bool = True,
    run_after_compile: bool = False
) -> CallToolResult:
    """
    编译 Delphi 工程

    Args:
        project_path: 项目文件路径(.dproj/.dpr/.dpk)
        target_platform: 目标平台(win32/win64/osx64/osxarm64/iosdevice64/android/linux64等，不传时从 .dproj 读取)
        output_path: 输出路径
        compiler_version: 编译器版本名称
        timeout: 超时时间(秒)
        conditional_defines: 条件编译符号列表
        unit_search_paths: 单元搜索路径列表
        resource_search_paths: 资源搜索路径列表
        optimize: 是否启用优化
        debug: 是否生成调试信息
        warning_level: 警告级别(0-4)
        disabled_warnings: 禁用的警告列表
        output_type: 输出类型(console/gui/dll)
        runtime_library: 运行时库链接方式(static/dynamic)
        build_configuration: 编译配置名称
        auto_install: 如果是设计期包，是否自动安装（默认 True）
        run_after_compile: 编译成功后，以末次运行参数启动程序

    Returns:
        编译结果字典
    """
    logger.info(f"收到工程编译请求: {project_path}")

    if _compiler_service is None:
        logger.error("编译服务未初始化")
        return CallToolResult(
            content=[{"type": "text", "text": "编译服务未初始化"}],
            isError=True
        )

    try:
        # 如果未指定目标平台（或为默认值"win32"），尝试从 .dproj 读取
        if not target_platform or target_platform == "win32":
            target_platform = resolve_target_platform_from_dproj(project_path)
            logger.info(f"从 .dproj 读取到目标平台: {target_platform}")
        else:
            target_platform = target_platform.lower()
        
        # 检查是否为 .dpk 文件
        project_ext = Path(project_path).suffix.lower()
        
        if project_ext == '.dpk':
            # 处理 DPK 包文件
            return await _compile_dpk_package(
                project_path=project_path,
                target_platform=target_platform,
                build_configuration=build_configuration or "Debug",
                timeout=timeout,
                auto_install=auto_install
            )
        
        # 自动检测编译器版本(如果未指定)
        if not compiler_version:
            detected = _detect_compiler_from_project(project_path, target_platform)
            if detected:
                compiler_version = detected
                logger.info(f"自动检测到编译器: {compiler_version}")
            else:
                logger.info("未自动检测到编译器,将使用默认编译器")

        # 检查资源文件是否变更（自动清理缓存，强制重新编译）
        _check_and_clean_stale_resources(project_path, build_configuration, target_platform)

        # 构建编译选项
        options = CompileOptions(
            target_platform=TargetPlatform(target_platform),
            output_path=output_path,
            compiler_version=compiler_version,
            timeout=timeout,
            conditional_defines=conditional_defines or [],
            unit_search_paths=unit_search_paths or [],
            resource_search_paths=resource_search_paths or [],
            optimize=optimize,
            debug=debug,
            warning_level=warning_level,
            disabled_warnings=disabled_warnings or [],
            output_type=OutputType(output_type),
            runtime_library=RuntimeLibrary(runtime_library),
            build_configuration=build_configuration
        )

        # 构建编译请求
        request = ProjectCompileRequest(
            project_path=project_path,
            options=options
        )

        # 执行编译
        result = await _compiler_service.compile_project(request)

        # F2084 Internal Error: 编译器内部错误，通常由损坏的 .dcu 缓存引起
        # 自动清理 .dcu 后重新编译一次
        if (result.status.value == "failed" and result.log and
            ("F2084" in result.log or "Internal Error" in result.log)):
            logger.warning("检测到编译器内部错误(F2084)，清理 .dcu 缓存后重新编译...")
            _cleanup_project_dcu(Path(project_path).parent)
            result = await _compiler_service.compile_project(request)
            if result.status.value == "success":
                logger.info("清理 .dcu 后编译成功")
            else:
                logger.warning("清理 .dcu 后编译仍然失败")

        # 返回结果
        result_text = str(result.to_dict())

        # 编译成功后，如需启动程序
        if run_after_compile and result.status.value == "success":
            try:
                exe_path = result.output_file
                if exe_path and Path(exe_path).exists():
                    # 从 .dproj 读取末次运行参数
                    parser = DprojParser(project_path)
                    run_params = None
                    if parser.parse():
                        plat = (target_platform or "win32").capitalize()
                        cfg = build_configuration or "Debug"
                        run_params = parser.get_debugger_run_params(config=cfg, platform=plat)

                    # 拆分参数（空格分隔，支持引号分组）
                    cmd = [exe_path]
                    if run_params:
                        try:
                            cmd.extend(shlex.split(run_params))
                        except Exception:
                            cmd.extend(run_params.split())

                    proc = _subprocess.Popen(
                        cmd,
                        cwd=Path(exe_path).parent,
                        creationflags=getattr(_subprocess, 'CREATE_NEW_CONSOLE', 0),
                    )
                    launch_msg = f"\n\n🚀 已启动: {Path(exe_path).name} (PID: {proc.pid})"
                    if run_params:
                        launch_msg += f"\n参数: {run_params}"
                    result_text += launch_msg
                    logger.info(f"编译后启动程序: {exe_path} PID={proc.pid} args={run_params}")
                else:
                    logger.warning(f"编译后启动: 未找到输出文件 {exe_path}")
            except Exception as e:
                logger.warning(f"编译后启动失败: {e}")
                result_text += f"\n⚠️ 自动启动失败: {e}"

        return CallToolResult(
            content=[{"type": "text", "text": result_text}],
            isError=result.status.value != "success"
        )

    except Exception as e:
        error_msg = f"编译过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )


async def _compile_dpk_package(
    project_path: str,
    target_platform: str,
    build_configuration: str,
    timeout: int,
    auto_install: bool
) -> CallToolResult:
    """
    编译 DPK 包文件

    Args:
        project_path: DPK 文件路径
        target_platform: 目标平台
        build_configuration: 构建配置
        timeout: 超时时间
        auto_install: 是否安装设计期包

    Returns:
        编译结果
    """
    # 查找对应的 .dproj 文件
    dproj_path = Path(project_path).with_suffix('.dproj')
    
    if not dproj_path.exists():
        # 如果没有 .dproj，尝试直接编译 .dpk
        logger.warning(f"未找到对应的 .dproj 文件: {dproj_path}，尝试直接编译 .dpk")
        dproj_path = Path(project_path)
    
    # 使用 install_package 中的函数编译和检测
    if _has_install_package:
        # 复用 install_package 的完整编译逻辑
        compile_result = await _compile_single_package(
            str(dproj_path),
            target_platform,
            build_configuration,
            timeout
        )
        
        is_runtime = _is_runtime_only_package(str(dproj_path))
        is_design_package = not is_runtime
        success = compile_result.get("success", False)
        output_file = compile_result.get("output_file", "")
        errors = compile_result.get("errors", [])
        warnings = compile_result.get("warnings", [])
    else:
        # 降级方案
        is_design_package = _is_design_package_simple(project_path)
        
        options = CompileOptions(
            target_platform=TargetPlatform(target_platform),
            build_configuration=build_configuration,
            timeout=timeout,
            debug=True
        )
        
        request = ProjectCompileRequest(
            project_path=str(dproj_path),
            options=options
        )
        
        result = await _compiler_service.compile_project(request)
        
        success = result.status.value == "success"
        output_file = result.output_file
        errors = result.errors
        warnings = result.warnings
    
    logger.info(f"包类型: {'设计期包' if is_design_package else '运行期包'}")
    
    # 如果编译成功且是设计期包，自动安装
    if success and is_design_package and auto_install:
        logger.info("编译成功，开始安装设计期包...")
        
        # 使用 install_package 中的注册函数
        if _has_install_package:
            version = _get_delphi_version()
            install_success = _register_packages_to_ide([output_file], version)
            install_result = "✅ 已自动安装到 IDE" if install_success else "⚠️ 自动安装失败，请手动安装"
        else:
            install_result = f"请手动安装: {output_file}"
        
        output_text = f"编译成功: {output_file}\n"
        output_text += f"包类型: 设计期包\n"
        output_text += f"安装结果: {install_result}"
        
        return CallToolResult(
            content=[{"type": "text", "text": output_text}],
            isError=False
        )
    
    # 返回编译结果
    output_text = f"编译{'成功' if success else '失败'}\n"
    output_text += f"输出文件: {output_file}\n"
    output_text += f"包类型: {'设计期包' if is_design_package else '运行期包'}\n"
    
    if errors:
        output_text += f"\n错误:\n"
        for err in errors:
            output_text += f"  {err}\n"
    
    if warnings:
        output_text += f"\n警告:\n"
        for warn in warnings:
            output_text += f"  {warn}\n"
    
    return CallToolResult(
        content=[{"type": "text", "text": output_text}],
        isError=not success
    )


def _is_design_package_simple(package_path: str) -> bool:
    """
    简单检测是否为设计期包（降级方案，当 install_package 不可用时使用）

    Args:
        package_path: 包文件路径

    Returns:
        是否为设计期包
    """
    try:
        with open(package_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read().upper()
        
        # 检测设计期包标记
        design_markers = [
            '{$DESIGNONLY',
            'DSNIDE',
            'DESIGNINTF',
            'DESIGNEDITORS',
        ]
        
        for marker in design_markers:
            if marker in content:
                return True
        
        return False
    except Exception as e:
        logger.error(f"检测包类型失败: {e}")
        return False
