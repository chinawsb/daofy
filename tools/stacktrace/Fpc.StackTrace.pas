{*
 * Fpc.StackTrace.pas - FPC Cross-Platform Stack Trace Implementation
 *
 * 为 Free Pascal/Lazarus 提供跨平台异常堆栈跟踪能力。
 * 支持 Windows、Linux、macOS 三个平台。
 *
 * 编译选项：
 *   -gl  启用 lineinfo 单元（必需，提供符号解析）
 *   -gw  启用 DWARF 调试信息（推荐）
 *
 * 用法：
 *   uses Fpc.StackTrace;
 *   // 在程序初始化时调用
 *   TStackTraceManagerFPC.Initialize;
 *   // 或手动安装钩子
 *   TStackTraceManagerFPC.Install;
 *
 * 格式：exception.log
 *   [时间戳][线程ID]Exception class XXX with Message:YYY
 *   Call Stacks:
 *     地址 函数名 源文件(行号)
 *     ...
 *
 * MAPDATA 资源格式（由 fpc_stacktracer 嵌入）：
 *   MAPD v13 二进制格式（与 Delphi 共享）
 *}

unit Fpc.StackTrace;

{$mode delphi}{$H+}

interface

uses
  Classes,
  SysUtils,
  MapDataSerializer;

const
  MaxStackFrames = 64;

type
  { 栈帧信息 }
  TStackTraceFrame = record
    Address: Pointer;
    FuncName: string;
    SourceFile: string;
    Line: Integer;
  end;

  { 栈跟踪结果 }
  TStackTraceResult = record
    Frames: array[0..MaxStackFrames - 1] of TStackTraceFrame;
    FrameCount: Integer;
  end;

  { 异常上下文 }
  TExceptionContext = record
    ExceptionClass: string;
    ExceptionMessage: string;
    Timestamp: TDateTime;
    ThreadId: TThreadId;
    StackTrace: TStackTraceResult;
  end;

  { FPC 栈跟踪管理器 }
  TStackTraceManagerFPC = class
  private
    class var
      FInstalled: Boolean;
      FOldExceptProc: TExceptProc;
      FLock: TRTLCriticalSection;
      { MAPDATA 资源数据（MAPD v13 反序列化结果） }
      FMapDataLoaded: Boolean;
      FMapData: TMapData;          // MAPD v13 deserialized data
  private
    class procedure FPExceptProc(ExceptObject: TObject; ExceptAddr: Pointer; FrameCount: Longint; Frames: PPointer); static;
    class procedure WriteExceptionLog(const AContext: TExceptionContext); static;
    class function CaptureStackTrace(ASkipFrames: Integer = 0): TStackTraceResult; static;
    class function FormatStackTrace(const ATrace: TStackTraceResult): string; static;
    class procedure LoadMapData; static;
    class procedure FreeMapData; static;
    class function ResolveAddress(AAddr: Pointer; out AFuncName, ASourceFile: string; out ALine: Integer): Boolean; static;
  public
    { 安装异常钩子 }
    class procedure Install; static;
    { 卸载异常钩子 }
    class procedure Uninstall; static;
    { 初始化（加载 MAPDATA + 安装钩子 + 初始化临界区） }
    class procedure Initialize; static;
    { 清理（卸载钩子 + 销毁临界区） }
    class procedure Finalize; static;
    { 是否已安装 }
    class property Installed: Boolean read FInstalled;
  end;

implementation

uses
{$IFDEF WINDOWS}
  Windows,
{$ENDIF}
{$IFDEF LINUX}
  BaseUnix,
  linux,
{$ENDIF}
{$IFDEF DARWIN}
  MacOSAll,
{$ENDIF}
  RtlConsts;

{ ============================================================================
  MAPDATA 资源加载与解析（MAPD v13）
  ============================================================================ }

{$IFDEF WINDOWS}

class procedure TStackTraceManagerFPC.LoadMapData;
var
  LModule: HMODULE;
  LResInfo: HRSRC;
  LResData: HGLOBAL;
  LPtr: Pointer;
  LSize: DWORD;
  LMapBytes: TBytes;
begin
  FMapDataLoaded := False;
  FMapData := Default(TMapData);

  LModule := GetModuleHandle(nil);
  if LModule = 0 then
    Exit;

  LResInfo := FindResource(LModule, 'MAPDATA', MAKEINTRESOURCE(10));
  if LResInfo = 0 then
    Exit;

  LResData := LoadResource(LModule, LResInfo);
  if LResData = 0 then
    Exit;

  LPtr := LockResource(LResData);
  LSize := SizeofResource(LModule, LResInfo);
  if (LPtr = nil) or (LSize < 5) then  // 最小: 'MAPD' + version
    Exit;

  { 将资源数据复制到 TBytes 供 Deserialize 使用 }
  SetLength(LMapBytes, LSize);
  Move(LPtr^, LMapBytes[0], LSize);

  { 反序列化 MAPD v13 }
  try
    FMapData := TMapDataSerializer.Deserialize(LMapBytes);
    if FMapData.Version = MapResVersion then
      FMapDataLoaded := True
    else
      FMapData := Default(TMapData);
  except
    FMapData := Default(TMapData);
  end;
end;

class procedure TStackTraceManagerFPC.FreeMapData;
begin
  FMapDataLoaded := False;
  FMapData := Default(TMapData);
end;

class function TStackTraceManagerFPC.ResolveAddress(
  AAddr: Pointer;
  out AFuncName, ASourceFile: string;
  out ALine: Integer
): Boolean;
const
  { 最大函数体大小 4MB，超过则视为不在模块代码范围内 }
  MAX_FUNC_RVA = $400000;
var
  LAddr: UInt64;
  LLo, LHi, LMid: Integer;
  LFuncIdx: Integer;
  LFuncAddr: UInt64;
  LLineMid: Integer;
  LLineAddr: UInt64;
  LModuleBase: NativeUInt;
  LMaxFuncAddr: UInt64;
begin
  Result := False;
  AFuncName := '';
  ASourceFile := '';
  ALine := 0;

  if not FMapDataLoaded then
    Exit;
  if Length(FMapData.SymbolEntries) = 0 then
    Exit;

  { MAPDATA stores RVAs (relative to ImageBase).
    Runtime addresses from RtlCaptureStackBackTrace are absolute.
    Convert: RVA = AbsoluteAddr - ModuleBase }
  LModuleBase := NativeUInt(GetModuleHandle(nil));
  if LModuleBase = 0 then
    Exit;

  { 地址低于模块基址 → 不在本模块内 }
  if NativeUInt(AAddr) < LModuleBase then
    Exit;

  LAddr := UInt64(NativeUInt(AAddr)) - UInt64(LModuleBase);

  { 地址超过最后一个符号 + MAX_FUNC_RVA → 不在本模块内（可能是系统 DLL） }
  LMaxFuncAddr := FMapData.SymbolEntries[Length(FMapData.SymbolEntries) - 1].Addr;
  if LAddr > LMaxFuncAddr + MAX_FUNC_RVA then
    Exit;

  { 二分查找函数（SymbolEntries 已按 Addr 排序） }
  LFuncIdx := -1;
  LLo := 0;
  LHi := Length(FMapData.SymbolEntries) - 1;
  while LLo <= LHi do
  begin
    LMid := (LLo + LHi) div 2;
    LFuncAddr := FMapData.SymbolEntries[LMid].Addr;
    if (LAddr >= LFuncAddr) then
    begin
      LFuncIdx := LMid;
      LLo := LMid + 1;
    end
    else
      LHi := LMid - 1;
  end;

  if LFuncIdx < 0 then
    Exit;

  { 使用 ExpandTokenName 解析函数名 }
  AFuncName := TMapDataSerializer.ExpandTokenName(
    FMapData.TokenDict, FMapData.TokenData, LFuncIdx, FMapData.SymbolEntries);

  { 二分查找行号（找 <= LAddr 的最大项） }
  LLo := 0;
  LHi := Length(FMapData.LineInfo) - 1;
  while LLo <= LHi do
  begin
    LLineMid := (LLo + LHi) div 2;
    LLineAddr := FMapData.LineInfo[LLineMid].Addr;
    if LLineAddr <= LAddr then
    begin
      { 使用 FileIdx 索引 SourcePaths }
      if (FMapData.LineInfo[LLineMid].FileIdx >= 0) and
         (FMapData.LineInfo[LLineMid].FileIdx < Length(FMapData.SourcePaths)) then
        ASourceFile := FMapData.SourcePaths[FMapData.LineInfo[LLineMid].FileIdx]
      else
        ASourceFile := '';
      ALine := FMapData.LineInfo[LLineMid].Line;
      LLo := LLineMid + 1;
    end
    else
      LHi := LLineMid - 1;
  end;

  Result := True;
end;

{$ELSE}

class procedure TStackTraceManagerFPC.LoadMapData;
begin
  { Linux/macOS: 暂不支持 MAPDATA 资源加载 }
  FMapDataLoaded := False;
end;

class procedure TStackTraceManagerFPC.FreeMapData;
begin
  FMapDataLoaded := False;
end;

class function TStackTraceManagerFPC.ResolveAddress(
  AAddr: Pointer;
  out AFuncName, ASourceFile: string;
  out ALine: Integer
): Boolean;
begin
  Result := False;
  AFuncName := '';
  ASourceFile := '';
  ALine := 0;
end;

{$ENDIF}

{ ============================================================================
  跨平台堆栈捕获
  ============================================================================ }

{$IFDEF WINDOWS}

{ Windows: 使用 RtlCaptureStackBackTrace }
function RtlCaptureStackBackTrace(
    FramesToSkip: DWORD;
    FramesToCapture: DWORD;
    BackTrace: Pointer;
    BackTraceHash: PDWORD
): DWORD; stdcall; external 'ntdll.dll';

class function TStackTraceManagerFPC.CaptureStackTrace(ASkipFrames: Integer): TStackTraceResult;
var
  LFrames: array[0..MaxStackFrames - 1] of Pointer;
  LCount: DWORD;
  I: Integer;
begin
  Result.FrameCount := 0;
  LCount := RtlCaptureStackBackTrace(
      ASkipFrames + 1,  // 跳过当前帧和 RtlCaptureStackBackTrace 本身
      MaxStackFrames,
      @LFrames[0],
      nil
  );
  if LCount > 0 then
  begin
    Result.FrameCount := LCount;
    for I := 0 to LCount - 1 do
    begin
      Result.Frames[I].Address := LFrames[I];
      // 优先使用 MAPDATA 资源解析
      if not ResolveAddress(LFrames[I], Result.Frames[I].FuncName,
                            Result.Frames[I].SourceFile, Result.Frames[I].Line) then
      begin
        // 降级到 BackTraceStrFunc
        Result.Frames[I].FuncName := BackTraceStrFunc(LFrames[I]);
        Result.Frames[I].SourceFile := '';
        Result.Frames[I].Line := 0;
      end;
    end;
  end;
end;

{$ENDIF}

{$IFDEF LINUX}

{ Linux: 使用 backtrace }
type
  PBacktraceInfo = ^TBacktraceInfo;
  TBacktraceInfo = record
    Size: cint;
    Trace: array[0..MaxStackFrames - 1] of Pointer;
  end;

function backtrace(buffer: PPVoid; size: cint): cint; cdecl; external 'libc' name 'backtrace';
function backtrace_symbols(buffer: PPVoid; size: cint): PPChar; cdecl; external 'libc' name 'backtrace_symbols';
procedure free(ptr: Pointer); cdecl; external 'libc' name 'free';

class function TStackTraceManagerFPC.CaptureStackTrace(ASkipFrames: Integer): TStackTraceResult;
var
  LFrames: array[0..MaxStackFrames - 1] of Pointer;
  LCount: cint;
  LSymbols: PPChar;
  I: Integer;
begin
  Result.FrameCount := 0;
  LCount := backtrace(@LFrames[0], MaxStackFrames);
  if LCount > ASkipFrames + 1 then
  begin
    Result.FrameCount := LCount - ASkipFrames - 1;
    LSymbols := backtrace_symbols(@LFrames[0], LCount);
    try
      for I := ASkipFrames + 1 to LCount - 1 do
      begin
        Result.Frames[I - ASkipFrames - 1].Address := LFrames[I];
        if LSymbols <> nil then
          Result.Frames[I - ASkipFrames - 1].FuncName := StrPas(LSymbols[I])
        else
          Result.Frames[I - ASkipFrames - 1].FuncName := Format('$%p', [LFrames[I]]);
        Result.Frames[I - ASkipFrames - 1].SourceFile := '';
        Result.Frames[I - ASkipFrames - 1].Line := 0;
      end;
    finally
      if LSymbols <> nil then
        free(LSymbols);
    end;
  end;
end;

{$ENDIF}

{$IFDEF DARWIN}

{ macOS: 使用 execinfo }
function backtrace(buffer: PPVoid; size: cint): cint; cdecl; external 'libc' name 'backtrace';
function backtrace_symbols(buffer: PPVoid; size: cint): PPChar; cdecl; external 'libc' name 'backtrace_symbols';
procedure free(ptr: Pointer); cdecl; external 'libc' name 'free';

class function TStackTraceManagerFPC.CaptureStackTrace(ASkipFrames: Integer): TStackTraceResult;
var
  LFrames: array[0..MaxStackFrames - 1] of Pointer;
  LCount: cint;
  LSymbols: PPChar;
  I: Integer;
begin
  Result.FrameCount := 0;
  LCount := backtrace(@LFrames[0], MaxStackFrames);
  if LCount > ASkipFrames + 1 then
  begin
    Result.FrameCount := LCount - ASkipFrames - 1;
    LSymbols := backtrace_symbols(@LFrames[0], LCount);
    try
      for I := ASkipFrames + 1 to LCount - 1 do
      begin
        Result.Frames[I - ASkipFrames - 1].Address := LFrames[I];
        if LSymbols <> nil then
          Result.Frames[I - ASkipFrames - 1].FuncName := StrPas(LSymbols[I])
        else
          Result.Frames[I - ASkipFrames - 1].FuncName := Format('$%p', [LFrames[I]]);
        Result.Frames[I - ASkipFrames - 1].SourceFile := '';
        Result.Frames[I - ASkipFrames - 1].Line := 0;
      end;
    finally
      if LSymbols <> nil then
        free(LSymbols);
    end;
  end;
end;

{$ENDIF}

{ ============================================================================
  格式化输出
  ============================================================================ }

class function TStackTraceManagerFPC.FormatStackTrace(const ATrace: TStackTraceResult): string;
var
  I: Integer;
  LLine: string;
begin
  Result := '';
  for I := 0 to ATrace.FrameCount - 1 do
  begin
    LLine := Format('  %p %s', [ATrace.Frames[I].Address, ATrace.Frames[I].FuncName]);
    if ATrace.Frames[I].SourceFile <> '' then
    begin
      LLine := LLine + ' ' + ATrace.Frames[I].SourceFile;
      if ATrace.Frames[I].Line > 0 then
        LLine := LLine + '(' + IntToStr(ATrace.Frames[I].Line) + ')';
    end;
    if Result <> '' then
      Result := Result + LineEnding;
    Result := Result + LLine;
  end;
end;

{ ============================================================================
  异常日志写入
  ============================================================================ }

class procedure TStackTraceManagerFPC.WriteExceptionLog(const AContext: TExceptionContext);
var
  LFileName: string;
  LStream: TFileStream;
  LBytes: TBytes;
  LStackText: string;
begin
  LStackText := FormatStackTrace(AContext.StackTrace);
  LFileName := ExtractFilePath(ParamStr(0)) + 'exception.log';

  EnterCriticalSection(FLock);
  try
    if FileExists(LFileName) then
    begin
      LStream := TFileStream.Create(LFileName, fmOpenWrite or fmShareDenyNone);
      LStream.Seek(0, soEnd);
    end
    else
    begin
      LStream := TFileStream.Create(LFileName, fmCreate);
      // 写入 UTF-8 BOM
      LBytes := TEncoding.UTF8.GetPreamble;
      if Length(LBytes) > 0 then
        LStream.Write(LBytes[0], Length(LBytes));
    end;
    try
      LBytes := TEncoding.UTF8.GetBytes(
          Format(
              '[%s][%d]Exception class %s with Message:%s' + LineEnding +
              'Call Stacks:' + LineEnding +
              '%s' + LineEnding,
              [
                  FormatDateTime('yyyy-mm-dd hh:nn:ss.zzz', AContext.Timestamp),
                  AContext.ThreadId,
                  AContext.ExceptionClass,
                  AContext.ExceptionMessage,
                  LStackText
              ]
          )
      );
      LStream.Write(LBytes[0], Length(LBytes));
    finally
      FreeAndNil(LStream);
    end;
  finally
    LeaveCriticalSection(FLock);
  end;
end;

{ ============================================================================
  异常钩子
  ============================================================================ }

class procedure TStackTraceManagerFPC.FPExceptProc(
    ExceptObject: TObject;
    ExceptAddr: Pointer;
    FrameCount: Longint;
    Frames: PPointer
);
var
  LContext: TExceptionContext;
  LTrace: TStackTraceResult;
begin
  if not FInstalled then
    Exit;

  // FPC ExceptProc 通常 FrameCount=0，需要自己捕获堆栈
  LTrace := CaptureStackTrace(1); // 跳过 FPExceptProc 本身

  // 构建异常上下文
  LContext.Timestamp := Now;
  LContext.ThreadId := {$IFDEF WINDOWS}GetCurrentThreadId{$ELSE}0{$ENDIF};
  if ExceptObject is Exception then
  begin
    LContext.ExceptionClass := ExceptObject.ClassName;
    LContext.ExceptionMessage := Exception(ExceptObject).Message;
  end
  else
  begin
    LContext.ExceptionClass := 'Unknown';
    LContext.ExceptionMessage := 'Non-exception object';
  end;
  LContext.StackTrace := LTrace;

  // 写入日志
  WriteExceptionLog(LContext);

  // 调用原始处理器
  if Assigned(FOldExceptProc) then
    FOldExceptProc(ExceptObject, ExceptAddr, FrameCount, Frames);
end;
{ ============================================================================
  Install / Uninstall
  ============================================================================ }

class procedure TStackTraceManagerFPC.Install;
begin
  if FInstalled then
    Exit;
  InitializeCriticalSection(FLock);
  FOldExceptProc := ExceptProc;
  ExceptProc := @FPExceptProc;
  FInstalled := True;
end;

class procedure TStackTraceManagerFPC.Uninstall;
begin
  if not FInstalled then
    Exit;
  if Assigned(FOldExceptProc) then
    ExceptProc := FOldExceptProc;
  FInstalled := False;
  DoneCriticalSection(FLock);
end;

class procedure TStackTraceManagerFPC.Initialize;
begin
  LoadMapData;
  Install;
end;

class procedure TStackTraceManagerFPC.Finalize;
begin
  Uninstall;
  FreeMapData;
end;

end.
