"""
编译服务

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

核心业务逻辑,协调参数生成、进程执行、结果解析等组件
"""

import time
import os
from typing import Optional, List
from datetime import datetime
from pathlib import Path
from ..models.compile_request import ProjectCompileRequest, FileCompileRequest, TargetPlatform, CompileOptions, OutputType, RuntimeLibrary
from ..models.compile_result import CompileResult, CompileStatus
from ..models.command_args import CommandArgs
from ..models.compile_history import CompileHistoryEntry
from .args_generator import ArgsGenerator
from .process_manager import ProcessManager
from .config_manager import ConfigManager
from ..utils.parser import OutputParser
from ..utils.validator import Validator
from ..utils.dproj_parser import DprojParser
from ..utils.unit_dependency_analyzer import SmartLibraryPathResolver
from ..utils.logger import get_logger

logger = get_logger(__name__)


class CompilerService:
    """编译服务"""

    def __init__(self, config_manager: ConfigManager):
        """初始化编译服务
        
        Args:
            config_manager: 配置管理器
        """
        self.config_manager = config_manager
        self.args_generator = ArgsGenerator()
        self.process_manager = ProcessManager()
        self.output_parser = OutputParser()
        self.validator = Validator()
        self.history: list = []
        
        # MSBuild 路径
        self.msbuild_path = self._find_msbuild()
        
        logger.info("编译服务初始化完成")

    def _find_msbuild(self) -> Optional[str]:
        """
        查找 MSBuild 可执行文件
        
        Returns:
            MSBuild 路径,如果未找到则返回 None
        """
        # 常见的 MSBuild 路径
        possible_paths = [
            r"C:\Program Files (x86)\Microsoft Visual Studio\2019\BuildTools\MSBuild\Current\Bin\MSBuild.exe",
            r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Community\MSBuild\Current\Bin\MSBuild.exe",
            r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Professional\MSBuild\Current\Bin\MSBuild.exe",
            r"C:\Program Files (x86)\Microsoft Visual Studio\2019\Enterprise\MSBuild\Current\Bin\MSBuild.exe",
            r"C:\Program Files\Microsoft Visual Studio\2022\BuildTools\MSBuild\Current\Bin\MSBuild.exe",
            r"C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe",
            r"C:\Program Files\Microsoft Visual Studio\2022\Professional\MSBuild\Current\Bin\MSBuild.exe",
            r"C:\Program Files\Microsoft Visual Studio\2022\Enterprise\MSBuild\Current\Bin\MSBuild.exe",
        ]
        
        for path in possible_paths:
            if Path(path).exists():
                logger.info(f"找到 MSBuild: {path}")
                return path
        
        logger.warning("未找到 MSBuild")
        return None

    def _get_delphi_root_from_registry(self, version: Optional[str] = None) -> Optional[str]:
        """
        从注册表获取 Delphi 安装根目录
        
        Args:
            version: Delphi 版本号(如 "22.0")，如果为 None 则使用最新版本
            
        Returns:
            Delphi 安装根目录，如果未找到则返回 None
        """
        import winreg
        
        try:
            # 打开 Delphi 注册表项
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Embarcadero\BDS",
                0,
                winreg.KEY_READ | winreg.KEY_WOW64_32KEY
            )
            
            versions = []
            index = 0
            while True:
                try:
                    version_key = winreg.EnumKey(key, index)
                    index += 1
                    
                    # 打开版本子项
                    version_path_key = winreg.OpenKey(key, version_key)
                    try:
                        root_dir, _ = winreg.QueryValueEx(version_path_key, "RootDir")
                        if root_dir and Path(root_dir).exists():
                            versions.append((version_key, root_dir))
                    except:
                        pass
                    finally:
                        winreg.CloseKey(version_path_key)
                        
                except OSError:
                    break
            
            winreg.CloseKey(key)
            
            if not versions:
                return None
            
            # 如果指定了版本，查找对应版本
            if version:
                for v, root in versions:
                    if v == version:
                        return root
            
            # 返回最新版本（版本号最大的）
            versions.sort(key=lambda x: x[0], reverse=True)
            return versions[0][1]
            
        except Exception as e:
            logger.warning(f"从注册表获取 Delphi 路径失败: {e}")
            return None

    def _get_rsvars_path(self, version: Optional[str] = None) -> Optional[str]:
        """
        获取 rsvars.bat 路径
        
        Args:
            version: Delphi 版本号，如果为 None 则使用最新版本
            
        Returns:
            rsvars.bat 完整路径，如果未找到则返回 None
        """
        root_dir = self._get_delphi_root_from_registry(version)
        if not root_dir:
            logger.error("无法从注册表获取 Delphi 安装路径")
            return None
        
        rsvars_path = Path(root_dir) / "bin" / "rsvars.bat"
        if rsvars_path.exists():
            logger.info(f"找到 rsvars.bat: {rsvars_path}")
            return str(rsvars_path)
        else:
            logger.error(f"rsvars.bat 不存在: {rsvars_path}")
            return None

    def _check_process_running(self, process_name: str) -> Optional[dict]:
        """
        检查指定进程是否正在运行
        
        Args:
            process_name: 进程名称（不含.exe扩展名）
            
        Returns:
            如果进程正在运行，返回包含进程信息的字典；否则返回 None
        """
        import subprocess
        import json
        
        try:
            # 使用 PowerShell 检查进程
            result = subprocess.run(
                ['powershell', '-Command', 
                 f"Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue | Select-Object Id, ProcessName, Path | ConvertTo-Json"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0 and result.stdout.strip():
                output = result.stdout.strip()
                
                # 如果返回的是数组（多个进程），取第一个
                if output.startswith('['):
                    processes = json.loads(output)
                    if processes:
                        proc = processes[0]
                    else:
                        return None
                elif output.startswith('{'):
                    proc = json.loads(output)
                else:
                    return None
                
                logger.info(f"检测到进程正在运行: {proc.get('ProcessName')} (PID: {proc.get('Id')})")
                return {
                    'pid': proc.get('Id'),
                    'name': proc.get('ProcessName'),
                    'path': proc.get('Path')
                }
            
            return None
            
        except Exception as e:
            logger.warning(f"检查进程时发生错误: {str(e)}")
            return None

    def _cleanup_dcu_files(self, search_paths: list):
        """
        清理单元搜索路径中的 .dcu 文件
        
        Args:
            search_paths: 单元搜索路径列表
        """
        import glob
        
        total_deleted = 0
        for path in search_paths:
            if not Path(path).exists():
                continue
            
            # 查找所有 .dcu 文件
            dcu_pattern = str(Path(path) / "*.dcu")
            dcu_files = glob.glob(dcu_pattern)
            
            if dcu_files:
                logger.info(f"在 {path} 中找到 {len(dcu_files)} 个 .dcu 文件")
                
                # 删除 .dcu 文件
                for dcu_file in dcu_files:
                    try:
                        os.unlink(dcu_file)
                        logger.debug(f"已删除: {dcu_file}")
                        total_deleted += 1
                    except Exception as e:
                        logger.warning(f"删除失败 {dcu_file}: {str(e)}")
        
        if total_deleted > 0:
            logger.info(f"共删除 {total_deleted} 个 .dcu 文件")

    def _execute_build_event(self, event_name: str, event_cmd: str, project_dir: str, 
                            ignore_exit_code: bool = False, timeout: int = 60,
                            context: dict = None) -> tuple:
        """
        执行编译事件

        Args:
            event_name: 事件名称(用于日志)
            event_cmd: 事件命令
            project_dir: 项目目录
            ignore_exit_code: 是否忽略退出码
            timeout: 超时时间(秒)
            context: 上下文变量字典,包含项目信息等

        Returns:
            (success, error_message, output) 元组
        """
        import subprocess
        
        logger.info(f"执行 {event_name}: {event_cmd}")
        
        # 替换 Delphi 支持的变量
        if context:
            # 项目相关变量
            event_cmd = event_cmd.replace('$(PROJECTDIR)', context.get('project_dir', project_dir))
            event_cmd = event_cmd.replace('$(PROJECTPATH)', context.get('project_path', ''))
            event_cmd = event_cmd.replace('$(PROJECTFILENAME)', context.get('project_filename', ''))
            event_cmd = event_cmd.replace('$(PROJECTNAME)', context.get('project_name', ''))
            
            # 输入文件相关变量
            event_cmd = event_cmd.replace('$(INPUTPATH)', context.get('input_path', ''))
            event_cmd = event_cmd.replace('$(INPUTFILENAME)', context.get('input_filename', ''))
            event_cmd = event_cmd.replace('$(INPUTEXT)', context.get('input_ext', ''))
            
            # 输出文件相关变量
            event_cmd = event_cmd.replace('$(OUTPUTDIR)', context.get('output_dir', ''))
            event_cmd = event_cmd.replace('$(OUTPUTPATH)', context.get('output_path', ''))
            event_cmd = event_cmd.replace('$(OUTPUTFILENAME)', context.get('output_filename', ''))
            event_cmd = event_cmd.replace('$(OUTPUTEXT)', context.get('output_ext', ''))
            
            # 配置相关变量
            event_cmd = event_cmd.replace('$(Config)', context.get('config', 'Debug'))
            event_cmd = event_cmd.replace('$(Platform)', context.get('platform', 'Win32'))
            event_cmd = event_cmd.replace('$(DEFINES)', context.get('defines', ''))
            
            # 路径相关变量
            event_cmd = event_cmd.replace('$(DIR)', context.get('dir', project_dir))
            event_cmd = event_cmd.replace('$(INCLUDEPATH)', context.get('include_path', ''))
            event_cmd = event_cmd.replace('$(PATH)', context.get('path', ''))
            
            # Delphi 环境变量
            event_cmd = event_cmd.replace('$(BDS)', context.get('bds', ''))
            event_cmd = event_cmd.replace('$(LOCALCOMMAND)', context.get('local_command', ''))
            
            # 系统变量
            event_cmd = event_cmd.replace('$(SystemRoot)', context.get('system_root', ''))
            event_cmd = event_cmd.replace('$(WINDIR)', context.get('windir', ''))
        
        # 兼容旧版本的变量替换
        event_cmd = event_cmd.replace('$(PROJECTDIR)', project_dir)
        
        try:
            result = subprocess.run(
                event_cmd,
                shell=True,
                cwd=project_dir,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode != 0 and not ignore_exit_code:
                error_msg = f"{event_name} 失败(退出码 {result.returncode}): {result.stderr}"
                logger.error(error_msg)
                return (False, error_msg, result.stdout + result.stderr)
            
            logger.info(f"{event_name} 执行成功")
            if result.stdout:
                logger.debug(f"{event_name} 输出: {result.stdout}")
            
            return (True, None, result.stdout + result.stderr)
            
        except subprocess.TimeoutExpired:
            error_msg = f"{event_name} 执行超时({timeout}秒)"
            logger.error(error_msg)
            return (False, error_msg, None)
        except Exception as e:
            error_msg = f"{event_name} 执行失败: {str(e)}"
            logger.error(error_msg)
            return (False, error_msg, None)

    def _extract_config_from_dproj(self, project_path: str, options: 'CompileOptions') -> 'CompileOptions':
        """
        从 .dproj 文件中提取配置

        Args:
            project_path: 项目文件路径(.dproj 或 .dpr)
            options: 原始编译选项

        Returns:
            合并后的编译选项
        """
        # 如果传入的是 .dpr 文件,查找对应的 .dproj 文件
        if project_path.endswith('.dpr'):
            dproj_path = project_path.replace('.dpr', '.dproj')
            if not Path(dproj_path).exists():
                logger.info(f"未找到对应的 .dproj 文件: {dproj_path}")
                return options
        elif project_path.endswith('.dproj'):
            dproj_path = project_path
        else:
            return options

        # 解析 .dproj 文件
        parser = DprojParser(dproj_path)
        if not parser.parse():
            logger.warning(f"解析 .dproj 文件失败: {dproj_path}")
            return options

        # 获取配置和平台
        config = options.build_configuration
        platform = "Win64" if options.target_platform == TargetPlatform.WIN64 else "Win32"

        # 提取单元搜索路径
        # 1. 先获取基础路径(不限制配置和平台)
        base_unit_paths = parser.get_unit_search_paths()
        # 2. 再获取平台特定路径
        platform_unit_paths = parser.get_unit_search_paths(config, platform)
        # 3. 合并所有路径
        dproj_unit_paths = base_unit_paths + platform_unit_paths
        
        if dproj_unit_paths:
            # 合并用户指定的路径和 .dproj 中的路径
            all_paths = list(options.unit_search_paths) + dproj_unit_paths
            # 去重
            options.unit_search_paths = list(dict.fromkeys(all_paths))
            logger.info(f"从 .dproj 文件中提取了 {len(dproj_unit_paths)} 个单元搜索路径")

        # 提取条件编译符号
        dproj_defines = parser.get_conditional_defines(config, platform)
        if dproj_defines:
            all_defines = list(options.conditional_defines) + dproj_defines
            options.conditional_defines = list(dict.fromkeys(all_defines))
            logger.info(f"从 .dproj 文件中提取了 {len(dproj_defines)} 个条件编译符号")

        # 提取输出路径
        if not options.output_path:
            dproj_output = parser.get_output_path(config, platform)
            if dproj_output:
                options.output_path = dproj_output
                logger.info(f"从 .dproj 文件中提取了输出路径: {dproj_output}")

        # 智能解析第三方库路径
        # 注意：如果用户显式传入了 unit_search_paths，resolver 会直接返回，不会进行智能分析
        try:
            logger.info("开始解析第三方库路径...")
            resolver = SmartLibraryPathResolver()
            
            # 传入用户显式指定的路径，resolver 会判断是否跳过智能分析
            user_provided_paths = list(options.unit_search_paths) if options.unit_search_paths else None
            resolved_paths, info = resolver.resolve_library_paths(
                project_path, 
                platform,
                user_search_paths=user_provided_paths
            )
            
            if info.get("mode") == "user_provided":
                logger.info(f"使用用户显式传入的 {len(resolved_paths)} 个路径")
            elif resolved_paths:
                options.unit_search_paths = resolved_paths
                logger.info(f"智能解析选择了 {len(resolved_paths)} 个第三方库路径"
                           f"（从 {info.get('total_paths_count', 0)} 个全局路径中筛选，"
                           f"解决了 {info.get('resolved_units', 0)} 个单元依赖）")
                logger.debug(f"解析详情: {info}")
            
            # 记录未找到的单元
            if info.get('still_missing_units'):
                logger.warning(f"仍有 {len(info['still_missing_units'])} 个单元未找到: "
                             f"{info['still_missing_units'][:5]}")
                
        except Exception as e:
            logger.warning(f"智能解析第三方库路径失败: {e}，将使用默认方式")

        return options

    async def compile_dpr_direct(self, request: ProjectCompileRequest) -> CompileResult:
        """
        直接使用 dcc32/dcc64 编译 .dpr 文件（不依赖 .dproj）

        Args:
            request: 工程编译请求

        Returns:
            编译结果
        """
        logger.info(f"直接编译 .dpr 文件: {request.project_path}")
        start_time = time.time()

        try:
            # 1. 验证项目路径
            is_valid, error_msg = self.validator.validate_project_path(request.project_path)
            if not is_valid:
                logger.error(f"项目路径验证失败: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_PROJECT_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 2. 确定输出路径 - 默认输出到 Win32 子目录
            project_dir = str(Path(request.project_path).parent)
            project_name = Path(request.project_path).stem

            if request.options.output_path:
                output_base = request.options.output_path
            else:
                output_base = str(Path(project_dir) / "Win32")

            # 确保输出目录存在
            Path(output_base).mkdir(parents=True, exist_ok=True)

            # 3. 获取编译器配置
            compiler_config = self.config_manager.get_compiler(request.options.compiler_version)
            if not compiler_config:
                # 尝试自动查找 dcc32
                dcc32_path = self._find_dcc32_from_registry()
                if dcc32_path:
                    logger.info(f"自动找到 dcc32: {dcc32_path}")
                    compiler_path = dcc32_path
                else:
                    error_msg = "未配置默认编译器且无法自动查找"
                    logger.error(error_msg)
                    return CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="COMPILER_NOT_FOUND",
                        error_message=error_msg,
                        duration=int((time.time() - start_time) * 1000)
                    )
            else:
                compiler_path = compiler_config.path

            # 4. 根据目标平台选择编译器
            if request.options.target_platform == TargetPlatform.WIN64:
                if 'dcc32.exe' in compiler_path.lower():
                    compiler_path = compiler_path.replace('dcc32.exe', 'dcc64.exe')
                    logger.info(f"切换到 64 位编译器: {compiler_path}")

            # 5. 验证编译器路径
            is_valid, error_msg = self.validator.validate_compiler_path(compiler_path)
            if not is_valid:
                logger.error(f"编译器路径验证失败: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_COMPILER_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 6. 检查目标程序是否正在运行
            running_process = self._check_process_running(project_name)
            if running_process:
                error_msg = f"目标程序 '{project_name}.exe' 正在运行 (PID: {running_process['pid']})，无法编译。请先关闭程序后再试。"
                logger.warning(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROCESS_RUNNING",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                    log=f"进程信息: PID={running_process['pid']}, 路径={running_process.get('path', '未知')}"
                )

            # 7. 生成命令行参数
            args = self._generate_dpr_args(request.project_path, request.options, output_base)

            # 8. 验证参数
            if not self.args_generator.validate_args(args):
                logger.error("参数验证失败")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_ARGS",
                    error_message="编译参数包含非法字符",
                    duration=int((time.time() - start_time) * 1000)
                )

            logger.info(f"编译命令: {compiler_path} {' '.join(args)}")

            # 9. 执行编译
            try:
                return_code, stdout, stderr = await self.process_manager.execute(
                    compiler_path,
                    args,
                    request.options.timeout
                )

                # 10. 解析输出
                errors = self.output_parser.parse_errors(stdout + stderr)
                warnings = self.output_parser.parse_warnings(stdout + stderr)

                # 11. 构建结果
                duration = int((time.time() - start_time) * 1000)
                output_file = str(Path(output_base) / f"{project_name}.exe")

                if return_code == 0:
                    result = CompileResult(
                        status=CompileStatus.SUCCESS,
                        output_file=output_file,
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.info(f"编译成功,输出文件: {output_file},耗时 {duration}ms")
                else:
                    result = CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="COMPILATION_FAILED",
                        error_message=self.output_parser.extract_error_summary(stdout + stderr),
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.error(f"编译失败,耗时 {duration}ms")

                # 12. 保存编译历史
                self._save_history(request.project_path, result.status.value, duration, result.error_message)

                return result

            except TimeoutError as e:
                duration = int((time.time() - start_time) * 1000)
                logger.error(f"编译超时: {str(e)}")
                result = CompileResult(
                    status=CompileStatus.TIMEOUT,
                    error_code="COMPILATION_TIMEOUT",
                    error_message=str(e),
                    duration=duration
                )
                self._save_history(request.project_path, result.status.value, duration, str(e))
                return result

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"直接编译过程发生异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result = CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration
            )
            self._save_history(request.project_path, result.status.value, duration, error_msg)
            return result

    def _generate_dpr_args(self, project_path: str, options: 'CompileOptions', output_base: str) -> List[str]:
        """生成 .dpr 文件的直接编译参数"""
        from ..utils.delphi_env import get_delphi_library_paths, expand_delphi_path_macros
        
        args = []

        # 项目文件
        args.append(project_path)

        # 输出目录（存放 .exe 文件）
        args.append(f'-E{output_base}')

        # 中间文件目录（存放 .dcu 文件）
        dcu_dir = str(Path(output_base) / "dcu")
        args.append(f'-N{dcu_dir}')

        # 条件编译符号
        if options.conditional_defines:
            defines = ";".join(options.conditional_defines)
            args.append(f'-$D+{defines}')

        # 命名空间搜索路径 - 默认添加 System 命名空间
        default_namespaces = ["System", "Winapi", "System.Win", "Vcl", "Vcl.Imaging",
                              "Vcl.Touch", "Vcl.Samples", "Vcl.Shell", "Data", "Datasnap",
                              "Web", "Soap", "Xml"]
        args.append('-NS' + ";".join(default_namespaces))

        # 单元搜索路径 - 如果未提供，则自动获取 Delphi 默认库搜索路径
        unit_paths = options.unit_search_paths if options.unit_search_paths else []
        if not unit_paths:
            # 自动获取 Delphi 库搜索路径
            platform = "Win32" if options.target_platform.value == "win32" else "Win64"
            delphi_lib_paths = get_delphi_library_paths(platform=platform)
            # 展开路径中的宏变量
            for p in delphi_lib_paths:
                expanded = expand_delphi_path_macros(p, version=None, platform=platform)
                if expanded and expanded not in unit_paths:
                    unit_paths.append(expanded)
        
        if unit_paths:
            paths = ";".join(unit_paths)
            args.append(f'-U{paths}')

        # 资源搜索路径
        if options.resource_search_paths:
            paths = ";".join(options.resource_search_paths)
            args.append(f'-R{paths}')

        # 优化选项
        if options.optimization_enabled:
            args.append('-$O+')
        else:
            args.append('-$O-')

        # 调试信息
        if options.debug_info_enabled:
            args.append('-$D+')
        else:
            args.append('-$D-')

        # 警告级别
        args.append(f'-$W{options.warning_level}')

        # 禁用警告
        for warning in options.disabled_warnings:
            args.append(f'-$W-{warning}')

        # 输出类型
        output_type_map = {
            OutputType.CONSOLE: "-CC",
            OutputType.GUI: "-CG",
            OutputType.DLL: "-LD"
        }
        args.append(output_type_map[options.output_type])

        # 运行时库
        if options.runtime_library == RuntimeLibrary.DYNAMIC:
            args.append('-$Y+')
        else:
            args.append('-$Y-')

        logger.debug(f"生成的 .dpr 编译参数: {' '.join(args)}")
        return args

    def _find_dcc32_from_registry(self) -> Optional[str]:
        """从注册表查找 dcc32.exe 路径"""
        root_dir = self._get_delphi_root_from_registry()
        if not root_dir:
            return None

        dcc32_path = Path(root_dir) / "bin" / "dcc32.exe"
        if dcc32_path.exists():
            return str(dcc32_path)

        return None

    async def compile_project_with_msbuild(self, request: ProjectCompileRequest) -> CompileResult:
        """
        使用 MSBuild 编译 Delphi 工程
        
        Args:
            request: 工程编译请求
            
        Returns:
            编译结果
        """
        logger.info(f"使用 MSBuild 编译工程: {request.project_path}")
        start_time = time.time()
        
        try:
            # 1. 检查 MSBuild 是否可用
            if not self.msbuild_path:
                error_msg = "未找到 MSBuild,无法使用 MSBuild 编译"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="MSBUILD_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )
            
            # 2. 验证项目路径
            is_valid, error_msg = self.validator.validate_project_path(request.project_path)
            if not is_valid:
                logger.error(f"项目路径验证失败: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_PROJECT_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )
            
            # 3. 确定项目文件(.dproj)
            if request.project_path.endswith('.dpr'):
                dproj_path = request.project_path.replace('.dpr', '.dproj')
                if not Path(dproj_path).exists():
                    error_msg = f"未找到对应的 .dproj 文件: {dproj_path}"
                    logger.error(error_msg)
                    return CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="DPROJ_NOT_FOUND",
                        error_message=error_msg,
                        duration=int((time.time() - start_time) * 1000)
                    )
            elif request.project_path.endswith('.dproj'):
                dproj_path = request.project_path
            else:
                error_msg = "项目文件必须是 .dpr 或 .dproj 文件"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_PROJECT_FILE",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )
            
            # 4. 提取并执行编译事件
            platform = "Win64" if request.options.target_platform == TargetPlatform.WIN64 else "Win32"
            config = request.options.build_configuration or "Debug"
            project_dir = str(Path(dproj_path).parent)
            project_path = str(Path(dproj_path).parent)
            project_filename = Path(dproj_path).name
            project_name = Path(dproj_path).stem
            
            # 4.5 检查目标程序是否正在运行
            running_process = self._check_process_running(project_name)
            if running_process:
                error_msg = f"目标程序 '{project_name}.exe' 正在运行 (PID: {running_process['pid']})，无法编译。请先关闭程序后再试。"
                logger.warning(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="PROCESS_RUNNING",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000),
                    log=f"进程信息: PID={running_process['pid']}, 路径={running_process.get('path', '未知')}"
                )
            
            # 构建上下文变量
            import os
            context = {
                # 项目相关
                'project_dir': project_dir,
                'project_path': project_path,
                'project_filename': project_filename,
                'project_name': project_name,
                
                # 输入文件相关(对于项目编译,输入文件就是项目文件)
                'input_path': project_path,
                'input_filename': project_filename,
                'input_ext': Path(dproj_path).suffix,
                
                # 输出文件相关
                'output_dir': request.options.output_path or project_dir,
                'output_path': request.options.output_path or project_dir,
                'output_filename': f"{project_name}.exe",
                'output_ext': '.exe',
                
                # 配置相关
                'config': config,
                'platform': platform,
                'defines': ';'.join(request.options.conditional_defines) if request.options.conditional_defines else '',
                
                # 路径相关
                'dir': project_dir,
                'include_path': ';'.join(request.options.unit_search_paths) if request.options.unit_search_paths else '',
                'path': os.environ.get('PATH', ''),
                
                # Delphi 环境变量
                'bds': os.environ.get('BDS', r'C:\Program Files (x86)\Embarcadero\Studio\22.0'),
                'local_command': '',
                
                # 系统变量
                'system_root': os.environ.get('SystemRoot', r'C:\Windows'),
                'windir': os.environ.get('WINDIR', r'C:\Windows'),
            }
            
            # 解析 .dproj 文件获取编译事件
            parser = DprojParser(dproj_path)
            build_events = {}
            if parser.parse():
                build_events = parser.get_build_events(config, platform)
                
                # 执行 PreBuildEvent
                if build_events.get('pre_build'):
                    success, error_msg, output = self._execute_build_event(
                        "PreBuildEvent",
                        build_events['pre_build'],
                        project_dir,
                        build_events.get('pre_build_ignore_exit_code', False),
                        60,
                        context
                    )
                    
                    if not success:
                        return CompileResult(
                            status=CompileStatus.FAILED,
                            error_code="PRE_BUILD_EVENT_FAILED",
                            error_message=error_msg,
                            duration=int((time.time() - start_time) * 1000),
                            log=output or ""
                        )
            
            # 5. 构建 MSBuild 参数
            args = []
            
            # 项目文件
            args.append(dproj_path)
            
            # 目标平台
            args.append(f"/p:Platform={platform}")
            
            # 配置(Debug/Release)
            args.append(f"/p:Config={config}")
            
            # 输出路径
            if request.options.output_path:
                args.append(f"/p:DCC_ExeOutput={request.options.output_path}")
            
            # 条件编译符号
            if request.options.conditional_defines:
                defines = ";".join(request.options.conditional_defines)
                args.append(f"/p:DCC_Define={defines}")
            
            # 单元搜索路径
            if request.options.unit_search_paths:
                paths = ";".join(request.options.unit_search_paths)
                args.append(f"/p:DCC_UnitSearchPath={paths}")
            
            # 其他参数
            args.append("/v:minimal")  # 最小输出级别
            
            logger.info(f"MSBuild 参数: {' '.join(args)}")
            
            # 5. 获取 rsvars.bat 路径
            rsvars_path = self._get_rsvars_path()
            if not rsvars_path:
                error_msg = "无法找到 rsvars.bat，请检查 Delphi 安装"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="RSVARS_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )
            
            # 6. 创建临时批处理文件来设置环境并执行 MSBuild
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='utf-8') as f:
                # 设置 Delphi 环境变量
                f.write('@echo off\n')
                f.write(f'call "{rsvars_path}"\n')
                # 调用 MSBuild
                f.write(f'msbuild {" ".join(args)}\n')
                batch_file = f.name
            
            logger.info(f"创建批处理文件: {batch_file}")
            
            # 6. 执行批处理文件
            try:
                return_code, stdout, stderr = await self.process_manager.execute(
                    'cmd.exe',
                    ['/c', batch_file],
                    request.options.timeout
                )
                
                # 删除临时文件
                try:
                    os.unlink(batch_file)
                except:
                    pass
                
                # 6. 解析输出
                errors = self.output_parser.parse_errors(stdout + stderr)
                warnings = self.output_parser.parse_warnings(stdout + stderr)
                
                # 7. 构建结果
                duration = int((time.time() - start_time) * 1000)
                
                if return_code == 0:
                    # 编译成功
                    # 执行 PostBuildEvent
                    if build_events.get('post_build'):
                        # 检查执行条件
                        execute_when = build_events.get('post_build_execute_when', 'Always')
                        should_execute = False
                        
                        if execute_when == 'Always':
                            should_execute = True
                        elif execute_when == 'TargetOutOfDate':
                            # 目标过期时执行(编译成功意味着目标已更新)
                            should_execute = True
                        
                        if should_execute:
                            success, error_msg, output = self._execute_build_event(
                                "PostBuildEvent",
                                build_events['post_build'],
                                project_dir,
                                build_events.get('post_build_ignore_exit_code', False),
                                60,
                                context
                            )
                            
                            if not success:
                                logger.warning(f"PostBuildEvent 失败,但编译已成功: {error_msg}")
                    
                    result = CompileResult(
                        status=CompileStatus.SUCCESS,
                        output_file=self._extract_output_file(stdout, request.options.output_path),
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.info(f"MSBuild 编译成功,耗时 {duration}ms")
                else:
                    # 编译失败
                    result = CompileResult(
                        status=CompileStatus.FAILED,
                        error_code="COMPILATION_FAILED",
                        error_message=self.output_parser.extract_error_summary(stdout + stderr),
                        warnings=warnings,
                        errors=errors,
                        duration=duration,
                        log=stdout + stderr
                    )
                    logger.error(f"MSBuild 编译失败,耗时 {duration}ms")
                
                # 8. 保存编译历史
                self._save_history(request.project_path, result.status.value, duration, result.error_message)
                
                return result
                
            except TimeoutError as e:
                duration = int((time.time() - start_time) * 1000)
                logger.error(f"MSBuild 编译超时: {str(e)}")
                result = CompileResult(
                    status=CompileStatus.TIMEOUT,
                    error_code="COMPILATION_TIMEOUT",
                    error_message=str(e),
                    duration=duration
                )
                self._save_history(request.project_path, result.status.value, duration, str(e))
                return result
                
        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"MSBuild 编译过程发生异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result = CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration
            )
            self._save_history(request.project_path, result.status.value, duration, error_msg)
            return result

    async def compile_project(self, request: ProjectCompileRequest) -> CompileResult:
        """
        编译 Delphi 工程
        
        优先使用 MSBuild 编译,如果 MSBuild 不可用或没有 .dproj 文件则回退到直接调用编译器

        Args:
            request: 工程编译请求

        Returns:
            编译结果
        """
        logger.info(f"开始编译工程: {request.project_path}")

        # 检查项目类型
        is_dpr_only = request.project_path.lower().endswith('.dpr')
        
        # 检查是否存在 .dproj 文件
        dproj_exists = False
        if is_dpr_only:
            dproj_path = request.project_path.replace('.dpr', '.dproj')
            dproj_exists = Path(dproj_path).exists()
            if not dproj_exists:
                logger.info(f"未找到 .dproj 文件，将使用 dcc32 直接编译 .dpr 文件")
        
        # 如果是 .dpr 文件且没有 .dproj 文件，或者 MSBuild 不可用，使用直接编译
        if (is_dpr_only and not dproj_exists) or not self.msbuild_path:
            if is_dpr_only and not dproj_exists:
                logger.info("使用 dcc32 直接编译 .dpr 文件")
            else:
                logger.info("MSBuild 不可用，使用直接编译器调用")
            return await self.compile_dpr_direct(request)
        
        # 优先使用 MSBuild 编译
        logger.info("使用 MSBuild 编译")
        return await self.compile_project_with_msbuild(request)

    async def compile_file(self, request: FileCompileRequest) -> CompileResult:
        """
        编译单个 Delphi 单元文件(仅语法检查)

        Args:
            request: 单文件编译请求

        Returns:
            编译结果
        """
        logger.info(f"开始编译文件: {request.file_path}")
        start_time = time.time()

        try:
            # 1. 验证文件路径
            is_valid, error_msg = self.validator.validate_file_path(request.file_path)
            if not is_valid:
                logger.error(f"文件路径验证失败: {error_msg}")
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="INVALID_FILE_PATH",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 2. 获取默认编译器配置
            compiler_config = self.config_manager.get_compiler()
            if not compiler_config:
                error_msg = "未配置默认编译器"
                logger.error(error_msg)
                return CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="COMPILER_NOT_FOUND",
                    error_message=error_msg,
                    duration=int((time.time() - start_time) * 1000)
                )

            # 3. 查找项目文件并提取配置
            file_dir = str(Path(request.file_path).parent)
            file_name = Path(request.file_path).stem

            # 尝试查找项目文件
            dproj_path = None
            project_unit_paths = []
            project_include_paths = []
            project_namespaces = []

            # 方法1: 查找同目录下的.dproj文件
            dproj_files = list(Path(file_dir).glob('*.dproj'))
            if dproj_files:
                # 优先选择与文件名匹配的项目，否则选择第一个
                for dproj in dproj_files:
                    if dproj.stem == file_name:
                        dproj_path = str(dproj)
                        break
                if not dproj_path:
                    dproj_path = str(dproj_files[0])

            # 方法2: 检查文件是否在项目的DCCReference中
            if dproj_path:
                try:
                    parser = DprojParser(dproj_path)
                    if parser.parse():
                        # 检查文件是否属于项目
                        if parser.is_file_in_project(Path(request.file_path).name):
                            logger.info(f"文件 {Path(request.file_path).name} 属于项目 {Path(dproj_path).name}")

                            # 提取单元搜索路径
                            project_unit_paths = parser.get_unit_search_paths()
                            logger.info(f"从项目文件中提取了 {len(project_unit_paths)} 个单元搜索路径")

                            # 提取include路径（从单元搜索路径中推断）
                            for path in project_unit_paths:
                                if 'include' in path.lower():
                                    project_include_paths.append(path)

                            # 提取命名空间
                            project_namespaces = parser.get_namespace()
                            if project_namespaces:
                                logger.info(f"从项目文件中提取了 {len(project_namespaces)} 个命名空间")
                        else:
                            logger.info(f"文件 {Path(request.file_path).name} 不属于项目 {Path(dproj_path).name}")
                            dproj_path = None
                except Exception as e:
                    logger.warning(f"解析项目文件失败: {e}")
                    dproj_path = None

            # 4. 删除单元搜索路径中的旧版 .dcu 文件
            if request.unit_search_paths:
                self._cleanup_dcu_files(request.unit_search_paths)

            # 5. 准备命名空间和include路径
            # 合并项目命名空间和默认命名空间
            default_namespaces = [
                "System", "Winapi", "System.Win", "Vcl", "Vcl.Imaging",
                "Vcl.Touch", "Vcl.Samples", "Vcl.Shell", "Data", "Datasnap",
                "Web", "Soap", "Xml"
            ]
            if project_namespaces:
                # 合并并去重
                namespaces = list(dict.fromkeys(project_namespaces + default_namespaces))
            else:
                namespaces = default_namespaces

            # 合并include路径
            default_include_paths = [
                str(Path(file_dir) / "Thirdpart" / "Jedi" / "Jcl" / "source" / "include"),
                str(Path(file_dir) / "Thirdpart" / "Jedi" / "Jcl" / "source" / "include" / "jedi")
            ]
            if project_include_paths:
                include_paths = list(dict.fromkeys(project_include_paths + default_include_paths))
            else:
                include_paths = default_include_paths

            # 合并单元搜索路径
            if project_unit_paths and request.unit_search_paths:
                # 用户提供的路径优先
                all_unit_paths = list(dict.fromkeys(request.unit_search_paths + project_unit_paths))
                logger.info(f"合并单元搜索路径: 用户 {len(request.unit_search_paths)} 个 + 项目 {len(project_unit_paths)} 个")
            elif project_unit_paths:
                all_unit_paths = project_unit_paths
            else:
                all_unit_paths = request.unit_search_paths or []

            # 输出目录 - 使用固定的绝对路径
            output_dir = str(Path(file_dir) / "Win32" / "Debug")

            # 确保输出目录存在
            Path(output_dir).mkdir(parents=True, exist_ok=True)

            # 5. 生成参数
            args = self.args_generator.generate_for_file(
                request.file_path,
                all_unit_paths,
                request.warning_level,
                request.disabled_warnings,
                namespaces=namespaces,
                include_paths=include_paths if include_paths else None,
                output_dir=output_dir
            )

            # 5. 执行编译
            return_code, stdout, stderr = await self.process_manager.execute(
                compiler_config.path,
                args,
                timeout=60  # 单文件编译超时时间较短
            )

            # 5. 解析输出
            errors = self.output_parser.parse_errors(stdout + stderr)
            warnings = self.output_parser.parse_warnings(stdout + stderr)

            # 6. 构建结果
            duration = int((time.time() - start_time) * 1000)

            if return_code == 0:
                result = CompileResult(
                    status=CompileStatus.SUCCESS,
                    warnings=warnings,
                    errors=errors,
                    duration=duration,
                    log=stdout + stderr
                )
                logger.info(f"文件编译成功,耗时 {duration}ms")
            else:
                result = CompileResult(
                    status=CompileStatus.FAILED,
                    error_code="SYNTAX_ERROR",
                    error_message=self.output_parser.extract_error_summary(stdout + stderr),
                    warnings=warnings,
                    errors=errors,
                    duration=duration,
                    log=stdout + stderr
                )
                logger.error(f"文件编译失败,耗时 {duration}ms")

            return result

        except Exception as e:
            duration = int((time.time() - start_time) * 1000)
            error_msg = f"文件编译过程发生异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return CompileResult(
                status=CompileStatus.FAILED,
                error_code="INTERNAL_ERROR",
                error_message=error_msg,
                duration=duration
            )

    def get_args(self, request: ProjectCompileRequest) -> CommandArgs:
        """
        获取命令行参数(不执行编译)

        Args:
            request: 工程编译请求

        Returns:
            命令行参数对象
        """
        logger.info(f"生成命令行参数: {request.project_path}")

        # 获取编译器配置
        compiler_config = self.config_manager.get_compiler(request.options.compiler_version)
        if not compiler_config:
            raise ValueError(f"编译器配置不存在: {request.options.compiler_version or '默认编译器'}")

        # 根据目标平台选择编译器
        compiler_path = compiler_config.path
        if request.options.target_platform == TargetPlatform.WIN64:
            if 'dcc32.exe' in compiler_path:
                compiler_path = compiler_path.replace('dcc32.exe', 'dcc64.exe')

        # 生成参数
        args = self.args_generator.generate(request.project_path, request.options)

        # 生成完整命令
        full_command = self.args_generator.format_command(compiler_path, args)

        # 收集警告
        warnings = []
        if request.options.output_path:
            is_valid, error_msg = self.validator.validate_output_path(request.options.output_path)
            if not is_valid:
                warnings.append(f"输出路径警告: {error_msg}")

        return CommandArgs(
            compiler_executable=compiler_path,
            project_file=request.project_path,
            arguments=args,
            full_command=full_command,
            warnings=warnings
        )

    def _extract_output_file(self, output: str, output_path: Optional[str]) -> Optional[str]:
        """从输出中提取输出文件路径"""
        # 简单实现: 如果指定了输出路径,返回该路径
        # 实际应该从编译器输出中解析
        return output_path

    def _save_history(self, project_path: str, status: str, duration: int, error_message: Optional[str]):
        """保存编译历史"""
        entry = CompileHistoryEntry(
            timestamp=datetime.now(),
            project_path=project_path,
            status=status,
            duration=duration,
            error_message=error_message
        )
        self.config_manager.add_history_entry(entry)
