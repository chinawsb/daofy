{
  DaofyAutomation.pas — 左右道飞MCP服务系统 自动化截图辅助单元

  原理：
    1. 创建隐藏消息窗口接收自动化消息
    2. IAT Hook 拦截 MessageBoxW / TaskDialogIndirect
    3. API 调用时 PostMessage 到隐藏窗口 → 主线程消息循环处理截图
    4. 后台命名管道接收 Python 命令
    5. 手动埋点 AutoCapture 在代码关键位置触发截图

  用法：
    uses DaofyAutomation;
    begin
      DaofyAutomation.AutoStart;
      Application.Initialize;
      Application.CreateForm(TForm1, Form1);
      Application.Run;
      DaofyAutomation.AutoStop;
    end.

    代码中调用截图: AutoCapture('order_confirm_003');

  编译：
    - Delphi 2009+: PNG 输出（需引用 Vcl.Imaging.pngimage）
    - 旧版: BMP 输出自动降级
}

unit DaofyAutomation;

interface

uses
  Winapi.Windows, Winapi.Messages, Winapi.CommCtrl,
  System.SysUtils, System.Classes;

// ── 公开接口 ──

/// 启动自动化：创建隐藏消息窗口 + IAT Hook + 命名管道监听
procedure AutoStart(const APipeName: string = '\\.\pipe\daofy_auto');

/// 停止自动化
procedure AutoStop;

/// 任意位置手动截图：{ScreenshotDir}\{AName}.png(.bmp)
procedure AutoCapture(const AName: string);

/// 设置截图保存目录（默认 Python 端 snapdir 命令设置）
procedure SetScreenshotDir(const ADir: string);

implementation

uses
  Vcl.Forms, Vcl.Controls, Vcl.Graphics;

// ============================================================
// 常量
// ============================================================
const
  WM_DAOFY_COMMAND  = WM_USER + $200;
  WM_DAOFY_CAPTURE  = WM_USER + $201;
  MAX_CMD_LEN       = 4096;
  MSG_WIN_CLASS     = 'DaofyAutoMsgWindow';

// ============================================================
// 函数指针类型（从 IAT 读出原始地址后直接调用）
// ============================================================
type
  TMessageBoxWFunc = function(hWnd: HWND; lpText, lpCaption: LPCWSTR;
    uType: UINT): Integer; stdcall;
  TTaskDialogIndirectFunc = function(const pConfig: TTaskDialogIndirectConfig;
    pnButton: PInteger; pnRadioButton: PInteger;
    pfVerificationFlagChecked: PBOOL): HRESULT; stdcall;

// ============================================================
// 全局状态
// ============================================================
var
  _PipeThread: TThread          = nil;
  _MsgWnd: HWND                 = 0;
  _ScreenshotDir: string        = '';
  _MsgBoxCounter: Integer       = 0;
  _TaskDlgCounter: Integer      = 0;
  _OrigMessageBoxW: TMessageBoxWFunc         = nil;
  _OrigTaskDialogIndirect: TTaskDialogIndirectFunc = nil;

// ============================================================
// IAT 查找 — 在 EXE 导入表中定位目标函数
// ============================================================

function FindIATEntry(const TargetModule, TargetFunc: AnsiString): PPointer;
var
  Base: PByte;
  DosHdr: PImageDosHeader;
  NtHdrs: PImageNtHeaders;
  ImpDesc: PImageImportDescriptor;
  OrigThunk, Thunk: PImageThunkData;
  FuncName: PAnsiChar;
  I: Integer;
begin
  Result := nil;
  Base := PByte(GetModuleHandle(nil));
  if Base = nil then Exit;

  DosHdr := PImageDosHeader(Base);
  if DosHdr.e_magic <> IMAGE_DOS_SIGNATURE then Exit;

  NtHdrs := PImageNtHeaders(Base + DosHdr._lfanew);
  if NtHdrs.Signature <> IMAGE_NT_SIGNATURE then Exit;

  ImpDesc := PImageImportDescriptor(Base +
    NtHdrs.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT].VirtualAddress);
  if ImpDesc = nil then Exit;

  for I := 0 to 1023 do
  begin
    if ImpDesc[I].OriginalFirstThunk = 0 then Break;

    if (AnsiCompareText(PAnsiChar(Base + ImpDesc[I].Name), TargetModule) = 0)
       or (AnsiCompareText(PAnsiChar(Base + ImpDesc[I].Name),
           PAnsiChar(TargetModule + '.dll')) = 0) then
    begin
      OrigThunk := PImageThunkData(Base + ImpDesc[I].OriginalFirstThunk);
      Thunk     := PImageThunkData(Base + ImpDesc[I].FirstThunk);

      while Thunk.u1.Function <> 0 do
      begin
        if OrigThunk.u1.Ordinal and IMAGE_ORDINAL_FLAG32 <> 0 then
        begin
          Inc(OrigThunk); Inc(Thunk);
          Continue;
        end;
        if OrigThunk.u1.AddressOfData <> 0 then
        begin
          FuncName := PAnsiChar(Base +
            PImageImportByName(Base + OrigThunk.u1.AddressOfData).Name);
          if AnsiCompareText(FuncName, TargetFunc) = 0 then
          begin
            Result := @Thunk.u1.Function;
            Exit;
          end;
        end;
        Inc(OrigThunk); Inc(Thunk);
      end;
    end;
  end;
end;

function InstallIATHook(const TargetModule, TargetFunc: AnsiString;
  HookProc: Pointer; out OriginalProc: Pointer): Boolean;
var
  IATPtr: PPointer;
  Old: DWORD;
begin
  Result := False;
  OriginalProc := nil;
  IATPtr := FindIATEntry(TargetModule, TargetFunc);
  if IATPtr = nil then Exit;
  OriginalProc := IATPtr^;
  if VirtualProtect(IATPtr, SizeOf(Pointer), PAGE_READWRITE, Old) then
  begin
    IATPtr^ := HookProc;
    VirtualProtect(IATPtr, SizeOf(Pointer), Old, Old);
    Result := True;
  end;
end;

// ============================================================
// IAT Hook 回调
// ============================================================

function HookedMessageBoxW(hWnd: HWND; lpText, lpCaption: LPCWSTR;
  uType: UINT): Integer; stdcall;
var
  CapName: AnsiString;
begin
  Inc(_MsgBoxCounter);
  CapName := AnsiString(Format('auto_msgbox_%.3d', [_MsgBoxCounter]));

  // 异步投递截图 — 原 MessageBoxW 模态循环中会处理此消息
  if _MsgWnd <> 0 then
    PostMessage(_MsgWnd, WM_DAOFY_CAPTURE, WPARAM(@CapName[1]), 0);

  // 通过原始函数指针直接调用（不走 IAT，防止递归）
  if Assigned(_OrigMessageBoxW) then
    Result := _OrigMessageBoxW(hWnd, lpText, lpCaption, uType)
  else
    Result := MessageBoxW(hWnd, lpText, lpCaption, uType);
end;

function HookedTaskDialogIndirect(const pConfig: TTaskDialogIndirectConfig;
  pnButton: PInteger; pnRadioButton: PInteger;
  pfVerificationFlagChecked: PBOOL): HRESULT; stdcall;
var
  CapName: AnsiString;
begin
  Inc(_TaskDlgCounter);
  CapName := AnsiString(Format('auto_taskdlg_%.3d', [_TaskDlgCounter]));

  if _MsgWnd <> 0 then
    PostMessage(_MsgWnd, WM_DAOFY_CAPTURE, WPARAM(@CapName[1]), 0);

  if Assigned(_OrigTaskDialogIndirect) then
    Result := _OrigTaskDialogIndirect(pConfig, pnButton, pnRadioButton,
      pfVerificationFlagChecked)
  else
    Result := TaskDialogIndirect(pConfig, pnButton, pnRadioButton,
      pfVerificationFlagChecked);
end;

// ============================================================
// 截图
// ============================================================

function TakeScreenshotToFile(const AFileName: string): Boolean;
var
  hWin: HWND;
  DC, MemDC: HDC;
  Bmp: TBitmap;
  Old: HGDIOBJ;
  R: TRect;
begin
  Result := False;
  hWin := GetActiveWindow;
  if hWin = 0 then hWin := GetForegroundWindow;
  if hWin = 0 then Exit;

  GetWindowRect(hWin, R);
  if (R.Width <= 0) or (R.Height <= 0) then Exit;

  DC := GetWindowDC(hWin);
  if DC = 0 then Exit;
  try
    MemDC := CreateCompatibleDC(DC);
    if MemDC = 0 then Exit;
    try
      Bmp := TBitmap.Create;
      try
        Bmp.PixelFormat := pf24bit;
        Bmp.Width  := R.Width;
        Bmp.Height := R.Height;
        Old := SelectObject(MemDC, Bmp.Handle);
        BitBlt(MemDC, 0, 0, R.Width, R.Height, DC, 0, 0, SRCCOPY);
        SelectObject(MemDC, Old);

        ForceDirectories(ExtractFilePath(AFileName));
        {$IF declared(TPNGImage)}
        Bmp.SaveToFile(ChangeFileExt(AFileName, '.png'));
        {$ELSE}
        Bmp.SaveToFile(ChangeFileExt(AFileName, '.bmp'));
        {$ENDIF}
        Result := True;
      finally
        Bmp.Free;
      end;
    finally
      DeleteDC(MemDC);
    end;
  finally
    ReleaseDC(hWin, DC);
  end;
end;

procedure DoCapture(const AName: string);
var
  FName: string;
begin
  if _ScreenshotDir = '' then Exit;
  FName := _ScreenshotDir + '\' + AName;
  TakeScreenshotToFile(FName);
end;

// ============================================================
// 命令执行（主线程调用）
// ============================================================

procedure ExecCommand(const ACmd: string);
var
  Cmd, Param: string;
  P: Integer;
  I: Integer;
  WaitMs: Integer;
  Ctrl: TControl;
  Btn: TButton;
  hWnd: HWND;
  Buf: array[0..255] of Char;
begin
  P := Pos(':', ACmd);
  if P > 0 then
  begin
    Cmd   := LowerCase(Copy(ACmd, 1, P - 1));
    Param := Copy(ACmd, P + 1, MaxInt);
  end
  else
  begin
    Cmd   := LowerCase(ACmd);
    Param := '';
  end;

  if Cmd = 'goto' then
  begin
    for I := 0 to Screen.FormCount - 1 do
      if SameText(Screen.Forms[I].ClassName, Param) or
         SameText(Screen.Forms[I].Name, Param) then
      begin
        Screen.Forms[I].Show;
        Screen.Forms[I].BringToFront;
        Screen.Forms[I].SetFocus;
        Break;
      end;
  end
  else if Cmd = 'click' then
  begin
    if (Screen.ActiveForm <> nil) and (Param <> '') then
    begin
      Ctrl := Screen.ActiveForm.FindChildControl(Param);
      if (Ctrl is TButton) and Assigned(TButton(Ctrl).OnClick) then
        TButton(Ctrl).OnClick(TButton(Ctrl));
    end;
  end
  else if Cmd = 'type' then
  begin
    // 格式: type:ControlName=Text
    P := Pos('=', Param);
    if (P > 0) and (Screen.ActiveForm <> nil) then
    begin
      Ctrl := Screen.ActiveForm.FindChildControl(Copy(Param, 1, P - 1));
      if Ctrl is TEdit then
        TEdit(Ctrl).Text := Copy(Param, P + 1, MaxInt);
    end;
  end
  else if Cmd = 'wait' then
  begin
    WaitMs := StrToIntDef(Param, 500);
    if WaitMs > 10000 then WaitMs := 10000;
    Sleep(WaitMs);
  end
  else if Cmd = 'capture' then
    DoCapture(Param)
  else if Cmd = 'msgclose' then
  begin
    // 按标题找 #32770 弹窗并关闭
    hWnd := FindWindowW('#32770', nil);
    while hWnd <> 0 do
    begin
      GetWindowTextW(hWnd, Buf, 256);
      if (Param = '') or (Pos(Param, string(Buf)) > 0) then
      begin
        SendMessage(hWnd, WM_CLOSE, 0, 0);
        Break;
      end;
      hWnd := GetNextWindow(hWnd, GW_HWNDNEXT);
    end;
  end
  else if Cmd = 'snapdir' then
  begin
    _ScreenshotDir := Param;
    ForceDirectories(_ScreenshotDir);
  end
  else if Cmd = 'exit' then
    Application.Terminate;
end;

// ============================================================
// 隐藏消息窗口（处理来自 Hook 和管道线程的消息）
// ============================================================

function MsgWndProc(hWnd: HWND; Msg: UINT; wParam: WPARAM;
  lParam: LPARAM): LRESULT; stdcall;
begin
  if Msg = WM_DAOFY_COMMAND then
  begin
    ExecCommand(string(PWideChar(wParam)));
    Result := 0;
  end
  else if Msg = WM_DAOFY_CAPTURE then
  begin
    DoCapture(string(PWideChar(wParam)));
    Result := 0;
  end
  else
    Result := DefWindowProc(hWnd, Msg, wParam, lParam);
end;

function CreateMsgWindow: HWND;
var
  WndClass: TWndClassEx;
begin
  FillChar(WndClass, SizeOf(WndClass), 0);
  WndClass.cbSize        := SizeOf(WndClass);
  WndClass.lpfnWndProc   := @MsgWndProc;
  WndClass.hInstance     := HInstance;
  WndClass.lpszClassName := MSG_WIN_CLASS;
  WndClass.cbWndExtra    := 0;
  RegisterClassEx(WndClass);

  Result := CreateWindowEx(0, MSG_WIN_CLASS, '', 0,
    0, 0, 0, 0, HWND_MESSAGE, 0, HInstance, nil);
end;

// ============================================================
// 命名管道监听线程
// ============================================================

type
  TPipeThread = class(TThread)
  private
    FPipeName: string;
  protected
    procedure Execute; override;
  public
    constructor Create(const APipeName: string);
  end;

constructor TPipeThread.Create(const APipeName: string);
begin
  inherited Create(False);
  FPipeName := APipeName;
  FreeOnTerminate := True;
end;

procedure TPipeThread.Execute;
var
  hPipe: THandle;
  CmdBuf: array[0..MAX_CMD_LEN - 1] of AnsiChar;
  BytesRead, BytesWritten: DWORD;
  Cmd: string;
  RespBuf: AnsiString;
begin
  while not Terminated do
  begin
    hPipe := CreateNamedPipe(
      PChar(FPipeName),
      PIPE_ACCESS_DUPLEX,
      PIPE_TYPE_MESSAGE or PIPE_READMODE_MESSAGE or PIPE_WAIT,
      PIPE_UNLIMITED_INSTANCES,
      MAX_CMD_LEN,
      MAX_CMD_LEN,
      100,
      nil
    );
    if hPipe = INVALID_HANDLE_VALUE then
    begin
      Sleep(500);
      Continue;
    end;

    if not ConnectNamedPipe(hPipe, nil)
       and (GetLastError <> ERROR_PIPE_CONNECTED) then
    begin
      CloseHandle(hPipe);
      Sleep(500);
      Continue;
    end;

    while not Terminated do
    begin
      FillChar(CmdBuf, SizeOf(CmdBuf), 0);
      if not ReadFile(hPipe, CmdBuf, SizeOf(CmdBuf) - 1, BytesRead, nil) then
        Break;

      if BytesRead > 0 then
      begin
        Cmd := Trim(string(UTF8ToString(CmdBuf)));
        if Cmd <> '' then
        begin
          // 投递到隐藏窗口（主线程消息循环处理）
          if _MsgWnd <> 0 then
            SendMessage(_MsgWnd, WM_DAOFY_COMMAND, WPARAM(PWideChar(WideString(Cmd))), 0);

          // 写响应
          RespBuf := 'OK'#10;
          WriteFile(hPipe, RespBuf[1], Length(RespBuf), BytesWritten, nil);
        end;
      end;
    end;

    CloseHandle(hPipe);
  end;
end;

// ============================================================
// 公开接口
// ============================================================

procedure AutoStart(const APipeName: string = '\\.\pipe\daofy_auto');
var
  Orig: Pointer;
begin
  if _MsgWnd <> 0 then Exit;

  // 1. 创建隐藏消息窗口
  _MsgWnd := CreateMsgWindow;

  // 2. 安装 IAT Hook: MessageBoxW
  if InstallIATHook('user32', 'MessageBoxW', @HookedMessageBoxW, Orig) then
    _OrigMessageBoxW := TMessageBoxWFunc(Orig);

  // 3. 安装 IAT Hook: TaskDialogIndirect
  if InstallIATHook('comctl32', 'TaskDialogIndirect',
     @HookedTaskDialogIndirect, Orig) then
    _OrigTaskDialogIndirect := TTaskDialogIndirectFunc(Orig);

  // 4. 启动管道监听线程
  _PipeThread := TPipeThread.Create(APipeName);
end;

procedure AutoStop;
begin
  if Assigned(_PipeThread) then
  begin
    _PipeThread.Terminate;
    _PipeThread := nil;
  end;

  if _MsgWnd <> 0 then
  begin
    DestroyWindow(_MsgWnd);
    _MsgWnd := 0;
  end;

  _OrigMessageBoxW := nil;
  _OrigTaskDialogIndirect := nil;
end;

procedure AutoCapture(const AName: string);
begin
  DoCapture(AName);
end;

procedure SetScreenshotDir(const ADir: string);
begin
  _ScreenshotDir := ADir;
  ForceDirectories(_ScreenshotDir);
end;

end.
