"""
进程管理器

负责编译器进程的创建、监控、超时处理和输出捕获
"""

import asyncio
import os
from typing import Callable, Tuple, Optional
from ..utils import get_console_encoding
from ..utils.logger import get_logger

logger = get_logger(__name__)


class ProcessManager:
    """编译器进程管理器"""

    def __init__(self):
        """初始化进程管理器，检测控制台编码"""
        self._encoding = get_console_encoding()
        logger.debug(f"进程管理器初始化，控制台编码: {self._encoding}")

    def _get_delphi_env(self, compiler_path: str) -> dict:
        """
        获取 Delphi 编译器所需的环境变量

        Args:
            compiler_path: 编译器路径

        Returns:
            环境变量字典
        """
        # 从编译器路径推断 Delphi 安装路径
        if 'Studio' in compiler_path:
            import re
            match = re.search(r'(.+Studio\\\d+\.\d+)', compiler_path)
            if match:
                bds_path = match.group(1)
                bds_version = bds_path.split('\\')[-1]
                env = {
                    'BDS': bds_path,
                    'BDSINCLUDE': f"{bds_path}\\include",
                    'BDSCOMMONDIR': f"C:\\Users\\Public\\Documents\\Embarcadero\\Studio\\{bds_version}",
                    'LANGDIR': 'EN',
                }
                logger.debug(f"设置 Delphi 环境变量: {env}")
                return env
        return {}

    async def execute(
        self,
        executable: str,
        args: list,
        timeout: int
    ) -> Tuple[int, str, str]:
        """
        执行编译器进程

        Args:
            executable: 可执行文件路径
            args: 参数列表
            timeout: 超时时间(秒)

        Returns:
            (return_code, stdout, stderr) 元组

        Raises:
            TimeoutError: 编译超时
            RuntimeError: 进程执行失败
        """
        logger.info(f"启动编译器进程: {executable}")
        logger.debug(f"参数: {' '.join(args)}")

        try:
            # 获取 Delphi 环境变量
            delphi_env = self._get_delphi_env(executable)
            
            # 合并环境变量
            env = os.environ.copy()
            env.update(delphi_env)

            # 创建进程
            process = await asyncio.create_subprocess_exec(
                executable,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env
            )

            logger.debug(f"进程已启动,PID: {process.pid}")

            # 等待完成或超时
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                return_code = process.returncode
                stdout_str = stdout.decode(self._encoding, errors='ignore')
                stderr_str = stderr.decode(self._encoding, errors='ignore')

                logger.info(f"进程执行完成,返回码: {return_code}")
                logger.debug(f"stdout 长度: {len(stdout_str)}, stderr 长度: {len(stderr_str)}")

                return (return_code, stdout_str, stderr_str)

            except asyncio.TimeoutError:
                logger.error(f"编译超时({timeout}秒),终止进程")
                await self.kill_process(process)
                raise TimeoutError(f"编译超时({timeout}秒)")

        except FileNotFoundError:
            error_msg = f"编译器可执行文件不存在: {executable}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        except Exception as e:
            error_msg = f"进程执行失败: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    async def kill_process(self, process: asyncio.subprocess.Process):
        """
        强制终止进程

        Args:
            process: 进程对象
        """
        try:
            logger.warning(f"终止进程 PID: {process.pid}")
            # kill() 在 AsyncMock 中可能返回协程，兼容两种场景
            _r = process.kill()
            if asyncio.iscoroutine(_r):
                await _r
            # 带短超时的 wait，防止 communicate() 被 cancel 后 pipe 残留阻塞 wait()
            await asyncio.wait_for(process.wait(), timeout=5)
            logger.info(f"进程已终止")
        except asyncio.TimeoutError:
            logger.warning(f"终止进程 wait() 超时(5秒),但进程已 kill,PID: {process.pid}")
        except ProcessLookupError:
            logger.warning(f"进程不存在,可能已终止")
        except Exception as e:
            logger.error(f"终止进程失败: {str(e)}")

    async def execute_with_callback(
        self,
        executable: str,
        args: list,
        timeout: int,
        stdout_callback: Optional[Callable] = None,
        stderr_callback: Optional[Callable] = None
    ) -> Tuple[int, str, str]:
        """
        执行编译器进程,支持实时输出回调

        Args:
            executable: 可执行文件路径
            args: 参数列表
            timeout: 超时时间(秒)
            stdout_callback: stdout 输出回调函数
            stderr_callback: stderr 输出回调函数

        Returns:
            (return_code, stdout, stderr) 元组
        """
        logger.info(f"启动编译器进程(带回调): {executable}")

        try:
            process = await asyncio.create_subprocess_exec(
                executable,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout_lines = []
            stderr_lines = []

            async def read_stream(stream, callback, lines_list):
                """读取流并调用回调"""
                while True:
                    line = await stream.readline()
                    if not line:
                        break
                    line_str = line.decode(self._encoding, errors='ignore').rstrip()
                    lines_list.append(line_str)
                    if callback:
                        callback(line_str)

            # 并发读取 stdout 和 stderr
            try:
                await asyncio.wait_for(
                    asyncio.gather(
                        read_stream(process.stdout, stdout_callback, stdout_lines),
                        read_stream(process.stderr, stderr_callback, stderr_lines)
                    ),
                    timeout=timeout
                )

                await process.wait()

                return_code = process.returncode
                stdout_str = '\n'.join(stdout_lines)
                stderr_str = '\n'.join(stderr_lines)

                logger.info(f"进程执行完成,返回码: {return_code}")
                return (return_code, stdout_str, stderr_str)

            except asyncio.TimeoutError:
                logger.error(f"编译超时({timeout}秒),终止进程")
                await self.kill_process(process)
                raise TimeoutError(f"编译超时({timeout}秒)")

        except Exception as e:
            error_msg = f"进程执行失败: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)
