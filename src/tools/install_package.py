"""
组件包安装工具

提供 Delphi 组件包编译和安装功能
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from mcp.types import CallToolResult
from ..constants import REG_KEY_EMBARCADERO_BDS
from ..services.compiler_service import CompilerService
from ..utils.delphi_env import (
    get_delphi_bpl_dir,
    get_delphi_version as detect_delphi_version,
)
from ..utils.logger import get_logger

logger = get_logger(__name__)

_compiler_service: Optional[CompilerService] = None


def set_compiler_service(service: CompilerService):
    """设置编译服务实例"""
    global _compiler_service
    _compiler_service = service


async def install_package(
    package_path: str,
    target_platform: str = "win32",
    build_configuration: str = "Debug",
    timeout: int = 300,
    install: bool = True
) -> CallToolResult:
    """
    编译并安装 Delphi 组件包

    Args:
        package_path: 包文件路径(.dproj/.dpk/.groupproj)
        target_platform: 目标平台(win32/win64)
        build_configuration: 构建配置(Debug/Release)
        timeout: 超时时间(秒)
        install: 是否自动安装到IDE

    Returns:
        编译安装结果
    """
    logger.info(f"收到组件包安装请求: {package_path}")

    if _compiler_service is None:
        logger.error("编译服务未初始化")
        return CallToolResult(
            content=[{"type": "text", "text": "编译服务未初始化"}],
            isError=True
        )

    try:
        path_obj = Path(package_path)
        if not path_obj.exists():
            return CallToolResult(
                content=[{"type": "text", "text": f"文件不存在: {package_path}"}],
                isError=True
            )

        ext = path_obj.suffix.lower()
        if ext == '.groupproj':
            result = await _install_group_project(package_path, target_platform, build_configuration, timeout, install)
        elif ext == '.dproj':
            result = await _install_dproj_package(package_path, target_platform, build_configuration, timeout, install)
        elif ext == '.dpk':
            result = await _install_dpk_package(package_path, target_platform, build_configuration, timeout, install)
        else:
            return CallToolResult(
                content=[{"type": "text", "text": f"不支持的文件类型: {ext}，支持: .dproj, .dpk, .groupproj"}],
                isError=True
            )

        return result

    except Exception as e:
        error_msg = f"组件包安装过程发生异常: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CallToolResult(
            content=[{"type": "text", "text": error_msg}],
            isError=True
        )


async def _install_group_project(
    group_path: str,
    target_platform: str,
    build_configuration: str,
    timeout: int,
    install: bool
) -> CallToolResult:
    """处理项目组"""
    import xml.etree.ElementTree as ET

    tree = ET.parse(group_path)
    root = tree.getroot()
    
    ns = 'http://schemas.microsoft.com/developer/msbuild/2003'
    
    results = []
    for project in root.findall(f'.//{{{ns}}}Projects'):
        proj_file = project.get('Include')
        if proj_file:
            proj_path = str(Path(group_path).parent / proj_file)
            if Path(proj_path).exists():
                is_runtime = _is_runtime_only_package(proj_path)
                result = await _compile_single_package(proj_path, target_platform, build_configuration, timeout)
                results.append((proj_path, is_runtime, result))
    
    if not results:
        for project in root.findall('.//Projects'):
            proj_file = project.get('Include')
            if proj_file:
                proj_path = str(Path(group_path).parent / proj_file)
                if Path(proj_path).exists():
                    is_runtime = _is_runtime_only_package(proj_path)
                    result = await _compile_single_package(proj_path, target_platform, build_configuration, timeout)
                    results.append((proj_path, is_runtime, result))
    
    return _format_group_results(results, install, target_platform)


async def _install_dproj_package(
    dproj_path: str,
    target_platform: str,
    build_configuration: str,
    timeout: int,
    install: bool
) -> CallToolResult:
    """处理单个项目"""
    is_runtime = _is_runtime_only_package(dproj_path)
    result = await _compile_single_package(dproj_path, target_platform, build_configuration, timeout)
    return _format_group_results([(dproj_path, is_runtime, result)], install, target_platform)


async def _install_dpk_package(
    dpk_path: str,
    target_platform: str,
    build_configuration: str,
    timeout: int,
    install: bool
) -> CallToolResult:
    """处理 dpk 包 - 转为 dproj"""
    dproj_path = dpk_path.replace('.dpk', '.dproj')
    
    if not Path(dproj_path).exists():
        return CallToolResult(
            content=[{"type": "text", "text": f"未找到对应的 .dproj 文件: {dproj_path}"}],
            isError=True
        )
    
    result = await _compile_single_package(dproj_path, target_platform, build_configuration, timeout)
    return _format_results([(dproj_path, result)], install, target_platform)


async def _compile_single_package(
    project_path: str,
    target_platform: str,
    build_configuration: str,
    timeout: int,
    extra_args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """编译单个包项目"""
    from ..models.compile_request import ProjectCompileRequest, CompileOptions, TargetPlatform
    
    existing_bpl = _find_bpl_file(project_path, target_platform, build_configuration)
    
    if not extra_args and existing_bpl and Path(existing_bpl).exists():
        return {
            "success": True,
            "output_file": existing_bpl,
            "errors": [],
            "warnings": [],
            "log": f"Using existing BPL: {existing_bpl}",
            "duration": 0
        }
    
    options = CompileOptions(
        target_platform=TargetPlatform(target_platform),
        build_configuration=build_configuration,
        timeout=timeout,
        debug=True,
        extra_args=extra_args or [],
    )
    
    request = ProjectCompileRequest(
        project_path=project_path,
        options=options
    )
    
    result = await _compiler_service.compile_project_with_msbuild(request)
    
    output_file = None
    if result.status.value == "success":
        output_file = _find_bpl_file(project_path, target_platform, build_configuration)
    
    return {
        "success": result.status.value == "success",
        "output_file": output_file if output_file else result.output_file,
        "errors": result.errors,
        "warnings": result.warnings,
        "log": result.log,
        "duration": result.duration
    }
    
    return {
        "success": result.status.value == "success",
        "output_file": output_file if output_file else result.output_file,
        "errors": result.errors,
        "warnings": result.warnings,
        "log": result.log,
        "duration": result.duration
    }


async def _compile_dpk(dpk_path: str, target_platform: str, output_dir: str, timeout: int) -> Dict[str, Any]:
    """直接编译 DPK 包文件"""
    import subprocess
    import tempfile
    
    if _compiler_service is None:
        return {
            "success": False,
            "output_file": None,
            "errors": [{"message": "编译服务未初始化"}],
            "warnings": [],
            "log": "",
            "duration": 0
        }
    
    rsvars_path = _compiler_service._get_rsvars_path()
    if not rsvars_path:
        return {
            "success": False,
            "output_file": None,
            "errors": [{"message": "未找到 rsvars.bat"}],
            "warnings": [],
            "log": "",
            "duration": 0
        }
    
    delphi_root = _compiler_service._get_delphi_root_from_registry()
    if not delphi_root:
        return {
            "success": False,
            "output_file": None,
            "errors": [{"message": "无法获取 Delphi 安装目录"}],
            "warnings": [],
            "log": "",
            "duration": 0
        }
    
    version_key = Path(delphi_root).name
    public_doc = Path.home() / "Documents" / "Embarcadero" / "Studio" / version_key
    bpl_dir = public_doc / "Bpl" / _platform_to_dir(target_platform)
    dcp_dir = public_doc / "Dcp"
    
    bpl_dir.mkdir(parents=True, exist_ok=True)
    dcp_dir.mkdir(parents=True, exist_ok=True)
    
    platform_dir = _platform_to_dir(target_platform)
    lib_path = Path(delphi_root) / "lib" / platform_dir
    
    project_name = Path(dpk_path).stem.replace('GR32_', 'GR32')
    bpl_output = str(bpl_dir / "%s.bpl" % project_name)
    
    for _p_name, _p_val in [('rsvars_path', rsvars_path), ('dpk_path', dpk_path),
                             ('lib_path', lib_path), ('bpl_dir', bpl_dir), ('dcp_dir', dcp_dir)]:
        if '"' in str(_p_val):
            return {"success": False, "errors": [{"message": "路径包含非法字符(\"): %s=%s" % (_p_name, _p_val)}],
                    "output_file": None, "warnings": [], "log": ""}
    
    batch_content = '@echo off\ncall "%s"\ndcc32 -b "%s" -U"%s" -LE"%s" -LN"%s"\n' % (
        rsvars_path, dpk_path, lib_path, bpl_dir, dcp_dir)
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='utf-8') as f:
        f.write(batch_content)
        batch_file = f.name
    
    try:
        proc = subprocess.Popen(
            ['cmd.exe', '/c', batch_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path(dpk_path).parent,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        )
        
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            return_code = proc.returncode
        except subprocess.TimeoutExpired:
            proc.kill()
            return {
                "success": False,
                "output_file": None,
                "errors": [{"message": f"编译超时 ({timeout}秒)"}],
                "warnings": [],
                "log": "",
                "duration": timeout * 1000
            }
        
        output = stdout.decode('utf-8', errors='replace') + stderr.decode('utf-8', errors='replace')
        
        bpl_path = Path(bpl_output)
        success = return_code == 0 and bpl_path.exists()
        
        return {
            "success": success,
            "output_file": str(bpl_path) if success else None,
            "errors": [],
            "warnings": [],
            "log": output,
            "duration": 0
        }
        
    finally:
        try:
            os.unlink(batch_file)
        except OSError:
            pass


def _get_delphi_version() -> Optional[str]:
    """从注册表获取 Delphi 版本号"""
    if _compiler_service:
        root_dir = _compiler_service._get_delphi_root_from_registry()
        if root_dir:
            return Path(root_dir).name
    return detect_delphi_version()


def _find_bpl_file(project_path: str, target_platform: str, build_configuration: str) -> Optional[str]:
    """查找编译生成的 BPL 文件"""
    version = _get_delphi_version()
    if not version:
        return None
    
    search_dirs = []
    public_bpl_dir = get_delphi_bpl_dir(version)
    if public_bpl_dir is not None:
        search_dirs.append(public_bpl_dir)
    search_dirs.append(Path.home() / "Documents" / "Embarcadero" / "Studio" / version / "Bpl")
    
    project_name = Path(project_path).stem
    is_runtime = '_R' in project_name
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        
        pattern = "GR32_R*" if is_runtime else "GR32_D*"
        bpl_files = list(search_dir.glob(pattern))
        if bpl_files:
            return str(bpl_files[0])
        
        bpl_files = list(search_dir.glob("GR32_*.bpl"))
        if bpl_files:
            return str(bpl_files[0])
    
    return None


def _platform_to_dir(platform: str) -> str:
    """将平台名称转换为目录名"""
    mapping = {"win32": "Win32", "win64": "Win64"}
    return mapping.get(platform.lower(), "Win32")


def _is_runtime_only_package(project_path: str) -> bool:
    """检查是否是运行时包（不需要安装到IDE）"""
    import xml.etree.ElementTree as ET
    
    try:
        tree = ET.parse(project_path)
        root = tree.getroot()
        ns = 'http://schemas.microsoft.com/developer/msbuild/2003'
        
        for pg in root.findall(f'.//{{{ns}}}PropertyGroup'):
            for child in pg:
                tag = child.tag.replace(f'{{{ns}}}', '')
                if tag == 'RuntimeOnlyPackage':
                    return child.text.strip().lower() == 'true'
        return False
    except Exception:
        return False


def _format_results(results: List[tuple], install: bool, target_platform: str) -> CallToolResult:
    """格式化单个项目编译结果"""
    return _format_group_results([(proj, is_runtime, result) for proj, (is_runtime, result) in [
        (r[0], (False, r[1])) for r in results
    ]], install, target_platform)


def _format_group_results(results: List[tuple], install: bool, target_platform: str) -> CallToolResult:
    """格式化项目组编译结果（包含运行时/设计时包区分）"""
    all_success = all(r[2].get("success", False) for r in results)
    
    output = "=" * 50 + "\n"
    output += "组件包编译结果\n"
    output += "=" * 50 + "\n\n"
    
    design_bpl_files = []
    
    for proj_path, is_runtime, result in results:
        pkg_type = "运行时包" if is_runtime else "设计时包"
        output += f"项目: {Path(proj_path).name} ({pkg_type})\n"
        output += f"状态: {'成功' if result.get('success') else '失败'}\n"
        
        output_file = result.get("output_file", "")
        if output_file and output_file.endswith('.bpl'):
            output += f"BPL文件: {output_file}\n"
            if not is_runtime:
                design_bpl_files.append(output_file)
        elif output_file:
            output += f"输出目录: {output_file}\n"
        
        if result.get("warnings"):
            output += f"警告: {len(result['warnings'])} 个\n"
        if result.get("errors"):
            output += f"错误: {len(result['errors'])} 个\n"
        output += "\n"
    
    if install and all_success:
        install_result = _format_install_guide(design_bpl_files, results)
        output += install_result
    
    return CallToolResult(
        content=[{"type": "text", "text": output}],
        isError=not all_success
    )


def _format_install_guide(bpl_files: List[str], results: List[tuple]) -> str:
    """生成安装指南"""
    output = "=" * 50 + "\n"
    output += "IDE 安装指南\n"
    output += "=" * 50 + "\n\n"
    
    version = _get_delphi_version()
    
    if bpl_files:
        output += "已找到以下 BPL 文件:\n"
        for bpl in bpl_files:
            output += f"  {bpl}\n"
        output += "\n"
        
        if _register_packages_to_ide(bpl_files, version):
            output += "✅ 组件包已自动安装到 IDE!\n\n"
        else:
            output += "⚠️ 自动安装失败，请手动安装:\n"
    else:
        output += "未找到预编译的 BPL 文件\n"
        output += "编译后请手动安装:\n"
        for proj_path, result in results:
            if result.get("success"):
                project_name = Path(proj_path).stem.replace('GR32_', 'GR32')
                output += f"  - {project_name}_R.bpl (运行时)\n"
                output += f"  - {project_name}_D.bpl (设计时)\n"
        output += "\n"
    
    output += "安装步骤:\n"
    output += "1. 打开 Delphi IDE\n"
    output += "2. 菜单: Component → Install Packages...\n"
    output += "3. 点击 Add 按钮\n"
    output += "4. 浏览并选择上面的 BPL 文件\n"
    output += "5. 点击 OK 完成安装\n"
    
    return output


def _register_packages_to_ide(bpl_files: List[str], version: str) -> bool:
    """将组件包注册到 IDE"""
    import winreg
    
    try:
        key_path = f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Known Packages"
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
        
        for bpl_path in bpl_files:
            try:
                winreg.SetValueEx(key, bpl_path, 0, winreg.REG_SZ, bpl_path)
                logger.info(f"已注册组件包: {bpl_path}")
            except Exception as e:
                logger.error(f"注册组件包失败 {bpl_path}: {e}")
        
        winreg.CloseKey(key)
        return True
    except Exception as e:
        logger.error(f"注册组件包失败: {e}")
        return False


async def list_installed_packages() -> CallToolResult:
    """
    列出已安装的组件包

    Returns:
        已安装包列表
    """
    import winreg
    
    output = "已安装的 Delphi 组件包:\n\n"
    
    try:
        version = _get_delphi_version()
        if not version:
            return CallToolResult(
                content=[
                    {
                        "type": "text",
                        "text": "未检测到 Delphi 版本，无法读取已安装组件包",
                    }
                ],
                isError=True,
            )

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            f"{REG_KEY_EMBARCADERO_BDS}\\{version}\\Known Packages",
            0,
            winreg.KEY_READ
        )
        
        index = 0
        while True:
            try:
                name, path, _ = winreg.EnumValue(key, index)
                output += f"  - {name}: {path}\n"
                index += 1
            except OSError:
                break
        
        winreg.CloseKey(key)
        
    except Exception as e:
        output += f"读取注册表失败: {e}\n"
    
    return CallToolResult(content=[{"type": "text", "text": output}])


async def handle_package(**kwargs) -> dict:
    """统一的 package 工具入口，通过 action 分发。

    Args:
        action: "install" 或 "list"
        其他参数见对应函数。

    Returns:
        dict: {"status": "ok"/"failed", "message": ...}
    """
    action = kwargs.get("action", "install")
    try:
        if action == "install":
            result = await install_package(
                package_path=kwargs.get("package_path", ""),
                target_platform=kwargs.get("target_platform", "win32"),
                build_configuration=kwargs.get("build_configuration", "Debug"),
                timeout=kwargs.get("timeout", 300),
                install=kwargs.get("install", True),
            )
            # CallToolResult → dict
            if isinstance(result, CallToolResult):
                text = result.content[0].text if result.content else ""
                return {"status": "failed" if result.isError else "ok", "message": text}
            return {"status": "ok", "message": str(result)}

        elif action == "list":
            result = await list_installed_packages()
            if isinstance(result, CallToolResult):
                text = result.content[0].text if result.content else ""
                return {"status": "ok", "message": text}
            return {"status": "ok", "message": str(result)}

        else:
            return {"status": "failed", "message": f"未知 action: {action}，可用: install/list"}
    except Exception as e:
        logger.exception("package 执行失败")
        return {"status": "failed", "message": str(e)}
