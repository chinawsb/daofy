"""
参数生成器

版权所有 (C) 吉林省左右软件开发有限公司
Copyright (C) Equilibrium Software Development Co., Ltd, Jilin
Update & Mod By Crystalxp (黑夜杀手 QQ:281309196)

根据编译选项生成 Delphi 编译器命令行参数
"""

import os
from pathlib import Path
from typing import List, Optional
from ..models.compile_request import CompileOptions, OutputType, RuntimeLibrary, TargetPlatform
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ArgsGenerator:
    """Delphi 编译器参数生成器"""

    # 平台→库目录映射
    _PLATFORM_LIB_DIR = {
        TargetPlatform.WIN32: 'Win32', TargetPlatform.WIN64: 'Win64',
        TargetPlatform.OSX64: 'OSX64', TargetPlatform.OSXARM64: 'OSXARM64',
        TargetPlatform.IOSDEVICE64: 'iOSDevice64', TargetPlatform.IOSDEVICE: 'iOSDevice',
        TargetPlatform.IOSSIMULATOR: 'iOSSimulator',
        TargetPlatform.ANDROID: 'Android', TargetPlatform.ANDROID64: 'Android64',
        TargetPlatform.LINUX64: 'Linux64',
    }

    def _get_platform_lib_path(self, delphi_version: str, platform: TargetPlatform) -> str:
        """获取目标平台的库路径（优先从注册表获取，回退到默认路径）"""
        lib_dir = self._PLATFORM_LIB_DIR.get(platform, 'Win32')
        # 优先通过 delphi_env 从注册表获取库路径（支持非标准安装位置）
        try:
            from ..utils.delphi_env import get_delphi_library_paths, expand_delphi_path_macros
            paths = get_delphi_library_paths(version=delphi_version, platform=lib_dir)
            # 寻找 Delphi 标准库路径：含 \lib\ 目录组件 + release
            for p in paths:
                expanded = expand_delphi_path_macros(p, version=delphi_version, platform=lib_dir)
                if ('\\lib\\' in expanded or '/lib/' in expanded) and 'release' in expanded.lower():
                    return expanded
        except Exception as e:
            logger.debug("忽略非致命异常: %s", str(e))
        try:
            from ..utils.delphi_env import get_delphi_root_dir
            root_dir = get_delphi_root_dir(delphi_version)
            if root_dir:
                return str(Path(root_dir) / "lib" / lib_dir / "release")
        except Exception as e:
            logger.debug("忽略非致命异常: %s", str(e))

        program_files_x86 = os.environ.get("ProgramFiles(x86)")
        if not program_files_x86:
            return ""
        return str(
            Path(program_files_x86)
            / "Embarcadero"
            / "Studio"
            / delphi_version
            / "lib"
            / lib_dir
            / "release"
        )

    def generate(self, project_path: str, options: CompileOptions) -> List[str]:
        """生成编译器参数列表"""
        args = []

        # 基础参数: 项目文件(不添加引号,asyncio.create_subprocess_exec 会自动处理)
        args.append(project_path)

        # 输出路径
        if options.output_path:
            args.append('-E' + options.output_path)

        # 条件编译符号
        if options.conditional_defines:
            defines = ";".join(options.conditional_defines)
            args.append('-$D+' + defines)

        # 单元搜索路径
        if options.unit_search_paths:
            paths = ";".join(options.unit_search_paths)
            args.append('-U' + paths)

        # 资源搜索路径
        if options.resource_search_paths:
            paths = ";".join(options.resource_search_paths)
            args.append('-R' + paths)

        # 优化选项
        if options.optimize:
            args.append('-$O+')
        else:
            args.append('-$O-')

        # 调试信息
        if options.debug:
            args.append('-$D+')
        else:
            args.append('-$D-')

        # 警告级别
        args.append('-$W' + str(options.warning_level))

        # 禁用警告
        for warning in options.disabled_warnings:
            args.append('-$W-' + warning)

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

        # 生成 Detailed 级别 .map 文件（供 StackTrace callgraph 解析）
        args.append('-GD')

        logger.debug("生成的参数: " + " ".join(args))
        return args

    def validate_args(self, args: List[str]) -> bool:
        """验证参数合法性"""
        path_params = {'-U', '-I', '-R', '-NS', '-LE', '-LN', '-NU', '-NH', '-NO', '-NB', '-NX'}
        
        for arg in args:
            param_prefix = None
            for pf in path_params:
                if arg.startswith(pf):
                    param_prefix = pf
                    break
            
            if '"' in arg and arg.count('"') >= 2:
                parts = arg.split('"')
                for i in range(0, len(parts), 2):
                    if any(char in parts[i] for char in ['|', '&', '`', '<', '>']):
                        logger.error("参数包含非法字符: " + arg)
                        return False
            else:
                if param_prefix:
                    if any(char in arg for char in ['|', '&', '`', '<', '>']):
                        logger.error("参数包含非法字符: " + arg)
                        return False
                else:
                    if any(char in arg for char in ['|', '&', '`', '(', ')', '<', '>']):
                        logger.error("参数包含非法字符: " + arg)
                        return False
            
            if '$' in arg and not arg.startswith('-$'):
                logger.error("参数包含非法 $ 字符: " + arg)
                return False
            
            if ';' in arg and param_prefix is None:
                logger.error("参数包含非法 ; 字符: " + arg)
                return False

        return True

    def format_command(self, executable: str, args: List[str]) -> str:
        """生成完整命令字符串"""
        if ' ' in executable:
            executable = '"' + executable + '"'

        command = executable + " " + " ".join(args)
        logger.debug("完整命令: " + command)
        return command

    def generate_for_file(self, file_path: str, unit_search_paths: List[str] = None,
                         warning_level: int = 2, disabled_warnings: List[str] = None,
                         namespaces: List[str] = None, include_paths: List[str] = None,
                         output_dir: str = None, delphi_version: Optional[str] = None,
                         conditional_defines: List[str] = None) -> List[str]:
        """生成单文件编译参数

        Args:
            file_path: 要编译的文件路径
            unit_search_paths: 单元搜索路径列表
            warning_level: 警告级别 (0-4)
            disabled_warnings: 要禁用的警告列表
            namespaces: 命名空间列表 (用于解析单元名称)
            include_paths: include文件搜索路径列表
            output_dir: 输出目录 (用于存放.dcu文件)
            delphi_version: Delphi版本号，默认自动检测
            conditional_defines: 条件编译符号列表
        """
        args = []

        # 文件路径(不添加引号,asyncio.create_subprocess_exec 会自动处理)
        args.append(file_path)

        # 条件编译符号
        if conditional_defines:
            defines = ";".join(conditional_defines)
            args.append('-D' + defines)

        # 命名空间 - 这是关键！用于解析 System.Classes 等单元
        if namespaces:
            ns_string = ";".join(namespaces)
            args.append('-NS' + ns_string)
        else:
            # 默认命名空间
            default_namespaces = [
                "System", "Winapi", "System.Win", "Vcl", "Vcl.Imaging",
                "Vcl.Touch", "Vcl.Samples", "Vcl.Shell", "Data", "Datasnap",
                "Web", "Soap", "Xml"
            ]
            args.append('-NS' + ";".join(default_namespaces))

        # 添加Delphi标准库路径（按目标平台）
        if unit_search_paths is None:
            unit_search_paths = []
        if not delphi_version:
            try:
                from ..utils.delphi_env import get_delphi_version
                delphi_version = get_delphi_version()
            except Exception as e:
                logger.debug("自动检测 Delphi 版本失败: %s", str(e))

        if delphi_version:
            delphi_lib_path = Path(self._get_platform_lib_path(delphi_version, TargetPlatform.WIN32))
            if delphi_lib_path.exists():
                # 将标准库路径添加到搜索路径的开头
                unit_search_paths.insert(0, str(delphi_lib_path))

        # 单元搜索路径
        if unit_search_paths:
            paths = ";".join(unit_search_paths)
            args.append('-U' + paths)

        # Include文件搜索路径
        if include_paths:
            paths = ";".join(include_paths)
            args.append('-I' + paths)

        # 输出目录 (用于存放.dcu文件) - 不加引号，asyncio会自动处理
        if output_dir:
            args.append('-N' + output_dir)

        # 警告级别
        args.append('-$W' + str(warning_level))

        # 禁用警告
        if disabled_warnings:
            for warning in disabled_warnings:
                args.append('-$W-' + warning)

        # 仅语法检查
        args.append('-$M-')

        logger.debug("生成的单文件编译参数: " + " ".join(args))
        return args
