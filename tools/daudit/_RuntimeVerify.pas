unit _RuntimeVerify;

{==============================================================================}
{  运行时验证单元 — 由 compile_project(run_verify=True) 自动注入            }
{                                                                              }
{  机制:                                                                        }
{    1. Vectored Exception Handler (VEH) — 在 OS 层面拦截所有 Delphi 异常     }
{       无论异常被 VCL/SEH 在何处吞掉, VEH 最先触发, 直接写出异常信息并终止   }
{    2. TApplicationEvents 挂 OnException — 捕获消息循环中的未处理异常       }
{    3. VerifyReportException — 供 .dpr 的 try/except 块直接从 ExceptObject  }
{       获取异常信息                                                           }
{                                                                              }
{  输出格式:                                                                    }
{    RUNTIME_VERIFY_READY                                                       }
{    EXCEPTION: EClassName: Message                                             }
{    STACKTRACE: ... (可选, 需 .map 文件)                                       }
{    END_EXCEPTION                                                              }
{==============================================================================}

interface

{ 导出给 .dpr 的 try/except 块调用的公开过程 }
procedure VerifyReportException;

implementation

uses
  Winapi.Windows,
  System.SysUtils,
  Vcl.Forms,
  Vcl.AppEvnts;

var
  AppEvents: TApplicationEvents = nil;
  StdOut: THandle = INVALID_HANDLE_VALUE;
  VEVHandle: Pointer = nil;  // Vectored Exception Handler 句柄

procedure WriteToPipe(const Msg: string);
var
  Written: DWORD;
  Bytes: TBytes;
begin
  if StdOut = INVALID_HANDLE_VALUE then Exit;
  Bytes := TEncoding.UTF8.GetBytes(Msg);
  WriteFile(StdOut, Bytes[0], Length(Bytes), Written, nil);
end;

procedure DoReportException(E: Exception);
begin
  WriteToPipe('EXCEPTION: ' + E.ClassName + ': ' + E.Message + #13#10);
  try
    if E.StackTrace <> '' then
    begin
      WriteToPipe('STACKTRACE:' + #13#10);
      WriteToPipe(E.StackTrace + #13#10);
    end;
  except
    // StackTrace 可能因 map 缺失不可用
  end;
  WriteToPipe('END_EXCEPTION' + #13#10);
end;

{ 给 .dpr 的 try/except 块调用的公开过程 }
procedure VerifyReportException;
begin
  if ExceptObject is Exception then
  begin
    DoReportException(Exception(ExceptObject));
    Halt(1);
  end;
end;

{ TApplicationEvents.OnException 的事件处理方法（必须是实例方法） }
type
  TEventHandler = class
    procedure OnException(Sender: TObject; E: Exception);
  end;

var
  EventHandler: TEventHandler;

procedure TEventHandler.OnException(Sender: TObject; E: Exception);
begin
  DoReportException(E);
  Halt(1);
end;

{ Delphi 异常在 Win32 下的异常码 }
const
  DELPHI_EXCEPTION_CODE = $0EEDFADE;

{==============================================================================}
{  Vectored Exception Handler — OS 层面最低层拦截                              }
{  在任何 SEH 处理之前被调用, 即使 VCL/异常框架吞掉异常也能捕获               }
{==============================================================================}
function VectoredExceptionHandler(ExceptionInfo: PEXCEPTION_POINTERS): LongInt; stdcall;
var
  E: Exception;
begin
  // 只处理 Delphi 异常（raise Exception(...)）
  if (ExceptionInfo <> nil) and
     (ExceptionInfo.ExceptionRecord <> nil) and
     (ExceptionInfo.ExceptionRecord.ExceptionCode = DELPHI_EXCEPTION_CODE) and
     (ExceptionInfo.ExceptionRecord.NumberParameters >= 1) then
  begin
    // ExceptionInformation[0] = Exception 对象地址
    Pointer(E) := ExceptionInfo.ExceptionRecord.ExceptionInformation[0];
    if (E <> nil) and (E is Exception) then
    begin
      DoReportException(E);
      // 终止进程，不交给后续 SEH 处理
      ExitProcess(1);
    end;
  end;
  // 非 Delphi 异常或其他异常，继续搜索
  Result := EXCEPTION_CONTINUE_SEARCH;
end;

initialization
  StdOut := GetStdHandle(STD_OUTPUT_HANDLE);
  if StdOut = 0 then
    StdOut := GetStdHandle(STD_ERROR_HANDLE);

  // 1. VEH — 最低层异常拦截（优先于所有 SEH 帧）
  VEVHandle := AddVectoredExceptionHandler(1, @VectoredExceptionHandler);

  // 2. TApplicationEvents 挂 OnException（消息循环内异常）
  AppEvents := TApplicationEvents.Create(nil);
  EventHandler := TEventHandler.Create;
  AppEvents.OnException := EventHandler.OnException;

  WriteToPipe('RUNTIME_VERIFY_READY' + #13#10);

finalization
  if VEVHandle <> nil then
    RemoveVectoredExceptionHandler(VEVHandle);
  EventHandler.Free;
  AppEvents.Free;
end.
