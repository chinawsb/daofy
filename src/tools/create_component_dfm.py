"""
create_component_dfm — 通过编译+运行 Delphi 代码，将组件序列化为 DFM 文本

工作流程:
  1. AI 提供组件创建的 Pascal 代码（完整函数体 + uses 单元）
  2. 代码注入到模板 .dpr → 编译 → 运行
  3. 通过 WriteComponent + ObjectBinaryToText 序列化
  4. 返回 DFM 文本（含组件名称）

模板约定:
  - AI 的 code 必须定义 function CreateComponent(AOwner: TComponent): TComponent;
  - 函数内部可创建 TForm/TFrame 等容器作为 Parent 上下文
  - WriteComponent 在返回的组件上调用，无需关注容器清理
  - 事件通过赋值到容器 Form 的方法来序列化名称

典型 AI code 示例 (VCL TButton):
  ```pascal
  type
    TGenForm = class(TForm)
    public
      constructor Create(AOwner: TComponent); override;
    published
      procedure BtnClick(Sender: TObject);
    end;

  constructor TGenForm.Create(AOwner: TComponent);
  begin
    inherited CreateNew(AOwner);  // 不加载 DFM 资源
  end;

  procedure TGenForm.BtnClick(Sender: TObject);
  begin
  end;

  function CreateComponent(AOwner: TComponent): TComponent;
  var
    F: TGenForm;
    B: TButton;
  begin
    F := TGenForm.Create(nil);
    B := TButton.Create(nil);
    B.Name := 'Button1';
    B.Parent := F;
    B.Caption := 'Click Me';
    B.OnClick := F.BtnClick;
    Result := F;  // ← 返回 Form（工具自动解包提取子组件 DFM）
  end;
  ```

  对应的 uses: ["Vcl.Forms", "Vcl.StdCtrls"]
  对应的 init_code: "RegisterClass(TGenForm);"
"""

import os
import sys
import tempfile
import subprocess
import shutil
import re
import ctypes
from ctypes import wintypes
from typing import Optional, Dict, Any, List, Tuple, Set
from ..utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================
# 沙箱 — 危险操作阻断清单
# ============================================================
# Layer 1: 静态分析 — 禁止使用的单元（提供底层 OS 访问能力）
_DENY_UNITS: Set[str] = {
    # Win32 API 直接访问
    'Windows', 'Winapi.Windows',
    # Shell 操作
    'ShellAPI', 'Winapi.ShellAPI', 'Winapi.Shell', 'ShlObj', 'Winapi.ShlObj',
    # 注册表
    'Registry', 'System.Win.Registry',
    # 文件 I/O（低级）
    'SysUtils',  # 含 DeleteFile/RemoveDir — 但也是 VCL 基础单元，谨慎
    # 进程/线程操作
    'TlHelp32', 'Winapi.TlHelp32',
    # 网络
    'WinSock', 'Winapi.WinSock', 'WinHTTP', 'Winapi.WinHTTP',
    'WinINet', 'Winapi.WinINet',
    # 安全
    'AclAPI', 'Winapi.AclAPI',
}

# Layer 1: 静态分析 — 禁止出现的函数/关键字模式
_DENY_PATTERNS: List[str] = [
    # 文件系统破坏
    r'\bDeleteFile\b',
    r'\bRemoveDir\b',
    r'\bRenameFile\b',
    # 进程/代码执行
    r'\bCreateProcess\b',
    r'\bWinExec\b',
    r'\bShellExecute\b',
    r'\bShellExecuteEx\b',
    r'\bExecuteProcess\b',
    r'\bRunDLL\b',
    # 内存操作
    r'\bWriteProcessMemory\b',
    r'\bReadProcessMemory\b',
    r'\bVirtualProtect\b',
    r'\bVirtualAllocEx\b',
    # 进程控制
    r'\bTerminateProcess\b',
    r'\bCreateRemoteThread\b',
    r'\bOpenProcess\b',
    # DLL 注入
    r'\bLoadLibrary\b',
    r'\bGetProcAddress\b',
    r'\bSetWindowsHookEx\b',
    # 外部导入（绕过 uses 检查）
    r'\bexternal\b',
    r'\bdelayload\b',
]

# Layer 2: Job Object 常量（Windows SDK）
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_LIMIT_JOB_TIME = 0x0004
_JOB_OBJECT_LIMIT_PROCESS_TIME = 0x0002
_JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x0008
_JOB_OBJECT_LIMIT_JOB_MEMORY = 0x0200
_PROCESS_CREATE_SUSPENDED = 0x00000004


def _validate_code_uses(uses: List[str]) -> Optional[str]:
    """Layer 1a: 检查 uses 中是否有禁止单元。"""
    for unit_name in uses:
        stripped = unit_name.strip()
        if stripped in _DENY_UNITS:
            return f"禁止使用危险单元 '{stripped}'：可能会被滥用来执行破坏性操作"
    return None


def _validate_code_patterns(code: str, uses: List[str]) -> Optional[str]:
    """Layer 1b: 检查代码中是否有危险函数调用。

    SysUtils 是例外 — VCL 基础单元必须可用，
    但如果代码中同时出现 SysUtils + 危险函数调用，需要特殊处理。
    """
    has_sysutils = any(u.strip() == 'SysUtils' for u in uses)

    for pattern in _DENY_PATTERNS:
        m = re.search(pattern, code, re.IGNORECASE)
        if m:
            func_name = m.group(0)
            # SysUtils 中的 DeleteFile/RemoveDir 是正常的 RTL 函数
            # 但如果 code 显式调用了它们，仍然危险
            return f"代码中检测到危险函数调用 '{func_name}'：已禁止执行"
    return None


def _validate_code_sandbox(code: str, uses: Optional[List[str]]) -> Optional[str]:
    """沙箱入口：静态分析代码，阻止危险操作。

    Returns:
        None = 通过检查
        str = 拒绝原因
    """
    safe_uses = uses or []
    err = _validate_code_uses(safe_uses)
    if err:
        return err
    err = _validate_code_patterns(code, safe_uses)
    if err:
        return err
    return None


# ============================================================
# Windows Job Object 沙箱（Layer 2）
# ============================================================

class _JobObjectSandbox:
    """Windows Job Object 进程沙箱。

    通过 ctypes 直接调用 kernel32 API，无需 pywin32 依赖。
    限制:
      - 进程/子进程总 CPU 时间 ≤ 15 秒
      - Job 句柄关闭时自动终止所有子进程
      - 最大活动进程数 5（防 fork 炸弹）
    """

    def __init__(self):
        self._handle = None
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    def create(self) -> bool:
        """创建 Job Object。"""
        # CreateJobObjectW(NULL, NULL)
        self._kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        self._kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        self._handle = self._kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            logger.warning("CreateJobObject 失败，跳过 Job Object 沙箱")
            return False
        return self._set_limits()

    def _set_limits(self) -> bool:
        """设置 Job Object 限制。"""
        # 构造 JOBOBJECT_EXTENDED_LIMIT_INFORMATION
        # 使用 bytearray 手动布局（避免定义完整 struct）
        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
                ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_ulonglong),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        # 15 秒 CPU 时间，以 100ns 为单位
        TIME_15S = 15 * 10_000_000

        basic = JOBOBJECT_BASIC_LIMIT_INFORMATION()
        basic.PerProcessUserTimeLimit = TIME_15S
        basic.PerJobUserTimeLimit = TIME_15S
        basic.LimitFlags = (
            _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
            _JOB_OBJECT_LIMIT_JOB_TIME |
            _JOB_OBJECT_LIMIT_PROCESS_TIME |
            _JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        )
        basic.ActiveProcessLimit = 5

        # JOBOBJECT_EXTENDED_LIMIT_INFORMATION contains basic + 3 more fields
        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", wintypes.DWORD * 3),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        ext = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        ext.BasicLimitInformation = basic
        ext.JobMemoryLimit = 256 * 1024 * 1024  # 256 MB 总内存上限

        self._kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, wintypes.DWORD,
            wintypes.LPVOID, wintypes.DWORD,
        ]
        self._kernel32.SetInformationJobObject.restype = wintypes.BOOL

        JobObjectExtendedLimitInformation = 9
        ok = self._kernel32.SetInformationJobObject(
            self._handle, JobObjectExtendedLimitInformation,
            ctypes.byref(ext), ctypes.sizeof(ext),
        )
        if not ok:
            logger.warning("SetInformationJobObject 失败，仅使用 kill-on-close")
        return True

    def assign(self, pid: int) -> bool:
        """将进程加入 Job Object。"""
        if not self._handle:
            return False
        self._kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self._kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        ph = self._kernel32.OpenProcess(0x1000 | 0x0010, False, pid)  # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        if not ph:
            logger.warning("OpenProcess(%d) 失败，无法加入 Job Object", pid)
            return False
        ok = self._kernel32.AssignProcessToJobObject(self._handle, ph)
        self._kernel32.CloseHandle(ph)
        if not ok:
            logger.warning("AssignProcessToJobObject(%d) 失败", pid)
        return ok

    def close(self):
        """关闭 Job Object 句柄（自动终止其中所有进程）。"""
        if self._handle:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

# ============================================================
# 模板 — 最小 dpr，无 VCL/FMX 耦合
# 所有框架代码（Form 声明、事件桩等）由 AI 在 code 参数中提供
# ============================================================

_TEMPLATE = r"""program dfmgen;

{$APPTYPE CONSOLE}

uses
  System.SysUtils,
  System.Classes{USER_UNITS};

{USER_TYPE_DECL}

{USER_CODE}

var
  comp: TComponent;
  ms: TMemoryStream;
  fs: TFileStream;
  outFile: string;
begin
  if ParamCount < 1 then
  begin
    WriteLn('ERROR:No output file specified');
    Halt(1);
  end;
  outFile := ParamStr(1);
  try
    {USER_INIT}
    comp := CreateComponent(nil);
    try
      ms := TMemoryStream.Create;
      try
        ms.WriteComponent(comp);
        ms.Position := 0;
        fs := TFileStream.Create(outFile, fmCreate);
        try
          ObjectBinaryToText(ms, fs);
        finally
          fs.Free;
        end;
      finally
        ms.Free;
      end;
    finally
      comp.Free;
    end;
  except
    on E: Exception do
    begin
      WriteLn('ERROR:' + E.Message);
      Halt(1);
    end;
  end;
end.
"""

# 编译器路径缓存（共享 dfm_utils 的查找逻辑）
_compiler_dcc32_path: Optional[str] = None


# ============================================================
# 编译器查找（与 dfm_utils 保持一致）
# ============================================================

def set_compiler_path(path: str):
    """设置 dcc32.exe 路径"""
    global _compiler_dcc32_path
    _compiler_dcc32_path = path


def _find_dcc32() -> Optional[str]:
    """查找可用的 dcc32.exe（与 dfm_utils._find_dcc32 逻辑一致）"""
    if _compiler_dcc32_path and os.path.isfile(_compiler_dcc32_path):
        return _compiler_dcc32_path

    which_cmd = "where" if sys.platform == "win32" else "which"
    try:
        result = subprocess.run(
            [which_cmd, "dcc32.exe" if sys.platform == "win32" else "dcc32"],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        if result.returncode == 0:
            path = result.stdout.strip().split('\n')[0].strip()
            if path and os.path.isfile(path):
                return path
    except Exception:
        logger.debug("通过 where/which 查找 dcc32 失败", exc_info=True)
    return None


def _find_library_path(dcc32: str) -> Optional[str]:
    """
    根据 dcc32 路径推导 RTL 库路径。

    Args:
        dcc32: dcc32.exe 完整路径

    Returns:
        库路径，未找到返回 None
    """
    dcc_dir = os.path.dirname(os.path.abspath(dcc32))
    root = os.path.dirname(dcc_dir)
    candidates = [
        os.path.join(root, "lib", "win32", "release"),
        os.path.join(root, "lib", "Win32", "Release"),
        os.path.join(root, "lib"),
    ]
    for p in candidates:
        if os.path.isdir(p):
            return p
    return None


# ============================================================
# 模板代码生成
# ============================================================

def _generate_dpr(
    uses: List[str],
    code: str,
    type_decl: str = "",
    init_code: str = "",
) -> str:
    """
    生成 dfmgen 项目 .dpr 源码。

    Args:
        uses: AI 额外指定的 uses 单元列表（不含 System.SysUtils 等基础单元）
        code: 实现代码段（必须包含 CreateComponent 函数定义）
        type_decl: 类型声明段（Form 类、事件桩等）
        init_code: 初始化代码段（在 CreateComponent 之前执行），
                   用于 RegisterClass 等全局初始化

    Returns:
        完整 .dpr 内容
    """
    # 格式化 uses 子句
    # 模板格式: "System.Classes{USER_UNITS};"
    # {USER_UNITS} 需以 ",\n  <unit>" 开头（非空时）
    cleaned = [u.strip() for u in uses if u.strip()]
    if cleaned:
        items = ",\n  ".join(cleaned)
        uses_block = ",\n  " + items
    else:
        uses_block = ""

    dpr = _TEMPLATE.replace("{USER_UNITS}", uses_block)
    dpr = dpr.replace("{USER_TYPE_DECL}", type_decl.strip())
    dpr = dpr.replace("{USER_INIT}", init_code.strip())
    dpr = dpr.replace("{USER_CODE}", code.strip())

    return dpr


def _extract_component_name(dfm_text: str) -> Optional[str]:
    """
    从 DFM 文本中提取组件名称。

    Args:
        dfm_text: 文本格式 DFM 内容

    Returns:
        组件 Name 值，未找到返回 None
    """
    m = re.search(r'^\s*(?:object|inherited)\s+(\w+)\s*:\s*\w+', dfm_text, re.MULTILINE)
    if m:
        return m.group(1)
    return None


def _unwrap_form_dfm(dfm_text: str) -> Optional[str]:
    """
    如果 DFM 根节点是一个 Form（视觉容器），提取其内部的第一个子组件 DFM。
    如果根节点不是 Form，返回 None（表示直接使用原始文本）。

    Form 检测：根节点类名包含 "Form" 且有嵌套 object/inherited。

    Args:
        dfm_text: 文本格式 DFM 内容

    Returns:
        子组件 DFM 文本，或 None（不需要解包）
    """
    text = dfm_text.strip()
    if not text:
        return None

    # 提取根对象声明和类名
    m = re.search(r'^(object|inherited)\s+(\w+)\s*:\s*(\w+)', text, re.MULTILINE)
    if not m:
        return None

    root_class = m.group(3)  # 如 TForm1, TForm, TGenForm
    has_form = 'Form' in root_class

    if not has_form:
        return None  # 不是 Form 容器，不解包

    # 找第一个嵌套的 object/inherited（子组件）
    # 从根对象声明之后开始搜索
    start_pos = m.end()
    remaining = text[start_pos:]

    child_m = re.search(r'^[ \t]+(object|inherited)\s+(\w+)\s*:\s*(\w+)', remaining, re.MULTILINE)
    if not child_m:
        return None  # Form 但没有子组件

    # 找到子组件的缩进级别（支持空格或 tab）
    raw_indent = child_m.group().rstrip()
    indent_text = raw_indent[:len(raw_indent) - len(raw_indent.lstrip())]
    child_start = start_pos + child_m.start()

    # 提取子组件文本：从子组件声明开始，到对应的 end 结束
    # 子组件的 end 在同样缩进级别（空格/tab 均可）
    escaped_indent = re.escape(indent_text)
    end_pattern = re.compile(r'^' + escaped_indent + r'end\b', re.MULTILINE)
    end_m = end_pattern.search(text, child_start)
    if not end_m:
        return None

    child_dfm = text[child_start:end_m.end()]
    return child_dfm


def _read_dfm_output(out_file: str) -> Dict[str, Any]:
    """
    读取并处理 DFM 输出文件。
    如果 DFM 被 Form 包裹，自动解包提取子组件。

    Args:
        out_file: DFM 文件路径

    Returns:
        {"success": True, "dfm_text": "...", "component_name": "..."}
        or {"success": False, "error": "...", "stage": "output"}
    """
    if not os.path.isfile(out_file):
        return {"success": False, "error": "执行成功但未生成输出文件", "stage": "output"}

    with open(out_file, "r", encoding="utf-8", errors="replace") as f:
        raw_text = f.read().strip()

    if not raw_text:
        return {"success": False, "error": "输出 DFM 文件为空", "stage": "output"}

    # 尝试解包 Form 容器
    unwrapped = _unwrap_form_dfm(raw_text)
    if unwrapped:
        dfm_text = unwrapped
    else:
        dfm_text = raw_text

    component_name = _extract_component_name(dfm_text)
    return {
        "success": True,
        "dfm_text": dfm_text,
        "component_name": component_name or "",
    }


# ============================================================
# 编译 & 执行
# ============================================================

def _compile_project(tmp_dir: str) -> Tuple[bool, str]:
    """
    编译 dfmgen 项目。

    Args:
        tmp_dir: 临时目录（含 dfmgen.dpr）

    Returns:
        (success: bool, message: str)
    """
    dpr_path = os.path.join(tmp_dir, "dfmgen.dpr")
    exe_path = os.path.join(tmp_dir, "dfmgen.exe")

    dcc32 = _find_dcc32()
    if not dcc32:
        return False, "未找到 dcc32.exe，请检查 Delphi 编译器安装"

    try:
        lib_path = _find_library_path(dcc32)

        # 尝试无 -U 参数编译
        cmd = [dcc32, dpr_path, f"-E{tmp_dir}", "-Q", "-B"]
        logger.info(f"编译 DFM 生成器: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )

        # 如果失败且有库路径，重试带 -U
        if result.returncode != 0 and lib_path:
            cmd2 = [dcc32, dpr_path, f"-E{tmp_dir}", "-Q", "-B", f"-U{lib_path}"]
            logger.info(f"重试编译(带-U): {' '.join(cmd2)}")
            result = subprocess.run(
                cmd2, capture_output=True, text=True, timeout=60,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            detail = stderr or stdout or f"退出码 {result.returncode}"
            return False, f"编译失败:\n{detail}"

        if not os.path.isfile(exe_path):
            return False, f"编译后未找到 exe: {exe_path}"

        return True, exe_path

    except subprocess.TimeoutExpired:
        return False, "编译超时(60s)"
    except Exception as e:
        logger.error(f"编译异常: {e}", exc_info=True)
        return False, f"编译异常: {e}"


def _execute_gen(exe_path: str, out_file: str, timeout: int = 15) -> Tuple[bool, str]:
    """
    执行编译好的 dfmgen.exe（沙箱环境）。

    Args:
        exe_path: dfmgen.exe 路径
        out_file: 输出 DFM 文件路径
        timeout: 执行超时秒数

    Returns:
        (success: bool, message: str)
        成功时 message 为空；失败时 message 为错误信息
    """
    # [沙箱] Layer 2: Windows Job Object — 超时自动杀进程 + kill-on-close
    job = _JobObjectSandbox()
    job_created = job.create()

    try:
        # 启动进程，然后立即加入 Job Object
        proc = subprocess.Popen(
            [exe_path, out_file],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )

        # 加入 Job Object（即使失败也继续执行，降级但不阻断）
        if job_created:
            job.assign(proc.pid)

        # 等待完成
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
            raise

        # 检查运行时错误（模板输出 ERROR: 前缀到 stdout）
        out_text = (stdout or "").strip()
        if out_text.startswith("ERROR:"):
            return False, out_text[len("ERROR:"):].strip()

        if proc.returncode != 0:
            err_text = (stderr or "").strip()
            return False, err_text or f"进程退出码 {proc.returncode}"

        # 验证输出文件存在
        if not os.path.isfile(out_file):
            return False, "未生成输出文件"

        return True, ""

    except subprocess.TimeoutExpired:
        return False, f"执行超时({timeout}s) — 组件创建代码可能陷入死循环"
    except Exception as e:
        logger.error(f"执行异常: {e}", exc_info=True)
        return False, f"执行异常: {e}"
    finally:
        job.close()


# ============================================================
# 主入口
# ============================================================

async def generate_component_dfm(
    code: str,
    uses: Optional[List[str]] = None,
    type_decl: str = "",
    init_code: str = "",
    compile_timeout: int = 60,
    exec_timeout: int = 15,
) -> Dict[str, Any]:
    """
    编译+运行 Delphi 代码，通过 WriteComponent 序列化生成 DFM 文本。

    Args:
        code: AI 写的 Pascal 实现代码。
              必须包含 function CreateComponent(AOwner: TComponent): TComponent; 定义。
              可包含辅助类型/过程/函数。
        uses: AI 指定需要引用的单元列表，如 ["Vcl.Forms", "Vcl.StdCtrls"]
        type_decl: 类型声明段（可选），用于声明 Form 类、事件桩等
        init_code: 初始化代码段（可选），在 CreateComponent 之前执行。
                   用于 RegisterClass 等全局注册，如 "RegisterClass(TGenForm);"
        compile_timeout: 编译超时秒数（默认 60）
        exec_timeout: 执行超时秒数（默认 15）

    Returns:
        success=True 时:
          {
            "success": True,
            "dfm_text": "...DFM text...",
            "component_name": "Button1"
          }
        success=False 时:
          {
            "success": False,
            "error": "...error description...",
            "stage": "compile|execute|output"
          }

    Usage (AI Agent):
      # 1. 查 KB 确认组件类名、单元、VCL/FMX 归属
      # 2. 写 CreateComponent 函数（含容器 Form + 事件桩）
      #    自定义 Form 类需 RegisterClass: init_code="RegisterClass(TGenForm);"
      # 3. 调此工具 → 获得 DFM 文本
      # 4. dfm_merge 合并到目标 / 事件桩写入 .pas
    """
    code = (code or "").strip()
    if not code:
        return {"success": False, "error": "code 参数不能为空", "stage": "input"}

    uses = uses or []
    type_decl = (type_decl or "").strip()
    init_code = (init_code or "").strip()

    # 验证 code 中包含 CreateComponent 函数
    if "CreateComponent" not in code:
        return {
            "success": False,
            "error": "code 中必须定义 CreateComponent(AOwner: TComponent): TComponent 函数",
            "stage": "input",
        }

    # [沙箱] 静态分析：阻断危险单元和函数调用
    sandbox_err = _validate_code_sandbox(code, uses)
    if sandbox_err:
        logger.warning("沙箱阻断: %s", sandbox_err)
        return {"success": False, "error": f"代码被沙箱拒绝: {sandbox_err}", "stage": "sandbox"}

    # 创建临时工作目录
    tmp_dir = tempfile.mkdtemp(prefix="dfmgen_")
    out_file = os.path.join(tmp_dir, "output.dfm")

    try:
        # 1. 生成 .dpr
        dpr_content = _generate_dpr(
            uses=uses,
            code=code,
            type_decl=type_decl,
            init_code=init_code,
        )
        dpr_path = os.path.join(tmp_dir, "dfmgen.dpr")
        with open(dpr_path, "w", encoding="utf-8") as f:
            f.write(dpr_content)

        # 2. 编译
        ok, msg = _compile_project(tmp_dir)
        if not ok:
            return {"success": False, "error": msg, "stage": "compile"}

        exe_path = msg  # _compile_project 成功时 msg 返回 exe_path

        # 3. 执行
        ok, err_msg = _execute_gen(exe_path, out_file, timeout=exec_timeout)
        if not ok:
            return {"success": False, "error": err_msg, "stage": "execute"}

        # 4. 读取输出 DFM（自动解包 Form 容器）
        result = _read_dfm_output(out_file)
        if not result["success"]:
            return result

        # 5. 写一份解析后的 DFM 返回
        return result

    finally:
        # 清理临时文件
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            logger.debug("清理临时目录失败: %s", tmp_dir, exc_info=True)
