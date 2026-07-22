unit DaofyAutomation.Windows;

{===============================================================================
  DaofyAutomation.Windows - Named Pipe 传输层实现（Windows 专用）

  实现 IAutomationTransport，通过 Win32 Named Pipe + Overlapped I/O
  与 Python 自动化客户端通信。

  本单元不依赖任何 GUI 框架（VCL/FMX），仅使用 Win32 API。
===============================================================================}

interface

uses
  Winapi.Windows,
  System.SysUtils,
  System.Classes,
  DaofyAutomation.Base;

type
  /// <summary>Named Pipe 传输层。Overlapped I/O 模式，支持同时等待管道请求和唤醒事件。</summary>
  TNamedPipeTransport = class(TInterfacedObject, IAutomationTransport)
  private
    FAddress: string;
    FActualPipeName: string;  // Accept 后派生的实际管道名（含 PID）
    FhPipe: THandle;
    FhOverlapEvent: THandle;
    FhWakeEvent: THandle;
    FOverlap: TOverlapped;
    FBuf: array[0..MAX_PIPE - 1] of AnsiChar;
    FBytesRead: DWORD;
    FReadPending: Boolean;
    procedure InitOverlapRead;
    procedure CancelOverlapRead;
  public
    constructor Create;
    destructor Destroy; override;

    { IAutomationTransport }
    procedure Open(const AAddress: string);
    function Accept(TimeoutMs: Cardinal): Boolean;
    function WaitForRequest(TimeoutMs: Cardinal): TTransportWaitResult;
    function ReadRequest(out ARequest: string): Boolean;
    function SendResponse(const AResp: string): Boolean;
    procedure Disconnect;
    procedure Wake;
    procedure Close;
    function GetTransportAddress: string;
  end;

implementation

{ TNamedPipeTransport }

constructor TNamedPipeTransport.Create;
begin
  inherited Create;
  FhPipe := INVALID_HANDLE_VALUE;
  FhOverlapEvent := 0;
  FhWakeEvent := CreateEvent(nil, False, False, nil);
  FReadPending := False;
end;

destructor TNamedPipeTransport.Destroy;
begin
  Close;
  if FhWakeEvent <> 0 then
    CloseHandle(FhWakeEvent);
  inherited;
end;

procedure TNamedPipeTransport.Open(const AAddress: string);
begin
  FAddress := AAddress;
  FActualPipeName := '';
end;

function TNamedPipeTransport.Accept(TimeoutMs: Cardinal): Boolean;
var
  PipeName: string;
  ErrorCode: DWORD;
  ConnectOverlap: TOverlapped;
  ConnectEvent: THandle;
  WaitHandles: array[0..1] of THandle;
  WaitResult: DWORD;
  BytesTransferred: DWORD;
begin
  Result := False;

  // ── 派生管道名（默认名追加 PID 防冲突）──
  if SameText(FAddress, '\\.\pipe\daofy_auto') then
    PipeName := Format('%s_%d', [FAddress, GetCurrentProcessId])
  else
    PipeName := FAddress;
  FActualPipeName := PipeName;

  // ── 创建命名管道实例 ──
  FhPipe := CreateNamedPipe(
    PChar(PipeName),
    PIPE_ACCESS_DUPLEX or FILE_FLAG_OVERLAPPED,
    PIPE_TYPE_MESSAGE or PIPE_READMODE_MESSAGE or PIPE_WAIT,
    PIPE_UNLIMITED_INSTANCES,
    MAX_PIPE, MAX_PIPE,
    5000, nil);

  if FhPipe = INVALID_HANDLE_VALUE then begin
    Sleep(500);
    Exit;
  end;

  // ── 等待客户端连接；异步句柄的 ConnectNamedPipe 也必须传 OVERLAPPED ──
  FillChar(ConnectOverlap, SizeOf(ConnectOverlap), 0);
  ConnectEvent := CreateEvent(nil, True, False, nil);
  if ConnectEvent = 0 then begin
    CloseHandle(FhPipe);
    FhPipe := INVALID_HANDLE_VALUE;
    Exit;
  end;
  try
    ConnectOverlap.hEvent := ConnectEvent;
    if ConnectNamedPipe(FhPipe, @ConnectOverlap) then
      Result := True
    else begin
      ErrorCode := GetLastError;
      case ErrorCode of
        ERROR_PIPE_CONNECTED:
          Result := True;
        ERROR_IO_PENDING:
          begin
            WaitHandles[0] := ConnectEvent;
            WaitHandles[1] := FhWakeEvent;
            WaitResult := WaitForMultipleObjects(2, @WaitHandles, False,
              TimeoutMs);
            if WaitResult = WAIT_OBJECT_0 then
              Result := GetOverlappedResult(FhPipe, ConnectOverlap,
                BytesTransferred, False)
            else begin
              CancelIoEx(FhPipe, @ConnectOverlap);
              WaitForSingleObject(ConnectEvent, 1000);
            end;
          end;
      end;
    end;
  finally
    CloseHandle(ConnectEvent);
  end;

  if not Result then begin
    CloseHandle(FhPipe);
    FhPipe := INVALID_HANDLE_VALUE;
    Exit;
  end;

  // ── 初始化 Overlapped I/O ──
  FillChar(FOverlap, SizeOf(FOverlap), 0);
  FhOverlapEvent := CreateEvent(nil, True, False, nil);
  if FhOverlapEvent = 0 then begin
    Disconnect;
    Exit(False);
  end;
  FOverlap.hEvent := FhOverlapEvent;

  FReadPending := False;
  InitOverlapRead;
end;

procedure TNamedPipeTransport.InitOverlapRead;
begin
  if FReadPending or (FhPipe = INVALID_HANDLE_VALUE) or
     (FhOverlapEvent = 0) then
    Exit;
  FillChar(FBuf, SizeOf(FBuf), 0);
  FBytesRead := 0;
  ResetEvent(FhOverlapEvent);

  if ReadFile(FhPipe, FBuf, SizeOf(FBuf) - 1, FBytesRead, @FOverlap) then begin
    FReadPending := True;
    SetEvent(FhOverlapEvent);
  end else if GetLastError = ERROR_IO_PENDING then
    FReadPending := True
  else
    FReadPending := False;
end;

procedure TNamedPipeTransport.CancelOverlapRead;
begin
  if FReadPending and (FhPipe <> INVALID_HANDLE_VALUE) then begin
    CancelIoEx(FhPipe, @FOverlap);
    if FhOverlapEvent <> 0 then
      WaitForSingleObject(FhOverlapEvent, 1000);
    FReadPending := False;
  end;
end;

function TNamedPipeTransport.WaitForRequest(TimeoutMs: Cardinal): TTransportWaitResult;
var
  WaitHandles: array[0..1] of THandle;
  WR: DWORD;
begin
  if FhPipe = INVALID_HANDLE_VALUE then
    Exit(twError);

  WaitHandles[0] := FhOverlapEvent;
  WaitHandles[1] := FhWakeEvent;

  WR := WaitForMultipleObjects(2, @WaitHandles, False, TimeoutMs);

  case WR of
    WAIT_OBJECT_0:     Result := twRequest;
    WAIT_OBJECT_0 + 1: Result := twWake;
    WAIT_TIMEOUT:      Result := twTimeout;
  else
    Result := twError;
  end;
end;

function TNamedPipeTransport.ReadRequest(out ARequest: string): Boolean;
var
  ReqBuf: TBytes;
  TotalLen, ChunkLen: Integer;
  ReadOk: BOOL;
begin
  Result := False;
  ARequest := '';
  SetLength(ReqBuf, 0);
  TotalLen := 0;

  repeat
    ReadOk := GetOverlappedResult(FhPipe, FOverlap, FBytesRead, False);
    if not ReadOk then begin
      if GetLastError = ERROR_MORE_DATA then begin
        ChunkLen := Integer(FBytesRead);
        SetLength(ReqBuf, TotalLen + ChunkLen);
        Move(FBuf[0], ReqBuf[TotalLen], ChunkLen);
        Inc(TotalLen, ChunkLen);

        FillChar(FBuf, SizeOf(FBuf), 0);
        ResetEvent(FhOverlapEvent);
        if not ReadFile(FhPipe, FBuf, SizeOf(FBuf) - 1, FBytesRead, @FOverlap) then
          if GetLastError <> ERROR_IO_PENDING then begin
            FReadPending := False;
            Exit;
          end;
        if WaitForSingleObject(FhOverlapEvent, 5000) <> WAIT_OBJECT_0 then begin
          FReadPending := False;
          Exit;
        end;
        Continue;
      end else begin
        FReadPending := False;
        Exit;
      end;
    end;

    if FBytesRead = 0 then begin
      FReadPending := False;
      Exit;
    end;

    ChunkLen := Integer(FBytesRead);
    SetLength(ReqBuf, TotalLen + ChunkLen);
    Move(FBuf[0], ReqBuf[TotalLen], ChunkLen);
    Break;
  until False;

  FReadPending := False;
  ARequest := Trim(TEncoding.UTF8.GetString(ReqBuf));
  Result := True;

  // 发起下一次异步读取
  InitOverlapRead;
end;

function TNamedPipeTransport.SendResponse(const AResp: string): Boolean;
var
  R: TBytes;
  BytesWritten: DWORD;
  ErrorCode: DWORD;
  WriteOverlap: TOverlapped;
  WriteEvent: THandle;
begin
  Result := False;
  if FhPipe = INVALID_HANDLE_VALUE then
    Exit;

  R := TEncoding.UTF8.GetBytes(AResp + #10);
  FillChar(WriteOverlap, SizeOf(WriteOverlap), 0);
  WriteEvent := CreateEvent(nil, True, False, nil);
  if WriteEvent = 0 then
    Exit;
  try
    WriteOverlap.hEvent := WriteEvent;
    BytesWritten := 0;
    if WriteFile(FhPipe, R[0], Length(R), BytesWritten,
      @WriteOverlap) then
      Result := BytesWritten = DWORD(Length(R))
    else begin
      ErrorCode := GetLastError;
      if ErrorCode <> ERROR_IO_PENDING then
        Exit;
      if WaitForSingleObject(WriteEvent, 5000) <> WAIT_OBJECT_0 then begin
        CancelIoEx(FhPipe, @WriteOverlap);
        WaitForSingleObject(WriteEvent, 1000);
        Exit;
      end;
      Result := GetOverlappedResult(FhPipe, WriteOverlap, BytesWritten,
        False) and (BytesWritten = DWORD(Length(R)));
    end;
  finally
    CloseHandle(WriteEvent);
  end;
end;

procedure TNamedPipeTransport.Disconnect;
begin
  CancelOverlapRead;
  if FhOverlapEvent <> 0 then begin
    CloseHandle(FhOverlapEvent);
    FhOverlapEvent := 0;
  end;
  if FhPipe <> INVALID_HANDLE_VALUE then begin
    FlushFileBuffers(FhPipe);
    DisconnectNamedPipe(FhPipe);
    CloseHandle(FhPipe);
    FhPipe := INVALID_HANDLE_VALUE;
  end;
  FReadPending := False;
end;

procedure TNamedPipeTransport.Wake;
begin
  if FhWakeEvent <> 0 then
    SetEvent(FhWakeEvent);
end;

procedure TNamedPipeTransport.Close;
begin
  Disconnect;
end;

function TNamedPipeTransport.GetTransportAddress: string;
begin
  if FActualPipeName <> '' then
    Result := FActualPipeName
  else
    Result := FAddress;
end;

end.
