unit DaofyAutomation.Posix;

{===============================================================================
  DaofyAutomation.Posix - Unix Domain Socket 传输层实现（Linux / macOS）

  实现 IAutomationTransport，通过 AF_UNIX SOCK_STREAM + select()
  与 Python 自动化客户端通信。

  本单元使用 FPC RTL 的 socket/pipe API 实现跨平台（Lazarus / FPC）。
===============================================================================}

interface

uses
  BaseUnix,
  Unix,
  Sockets,
  System.SysUtils,
  System.Classes,
  DaofyAutomation.Base;

type
  /// <summary>Unix Domain Socket 传输层。使用自唤醒管道（self-pipe trick）实现超时唤醒。</summary>
  TUnixSocketTransport = class(TInterfacedObject, IAutomationTransport)
  private
    FAddress: string;
    FActualSocketPath: string;  // Accept 后派生的实际套接字路径（含 PID）
    FListenSocket: Integer;
    FClientSocket: Integer;
    FWakePipe: array[0..1] of Integer;
    FConnected: Boolean;
    procedure CloseSocket(var ASocket: Integer);
    function DrainWakePipe: Boolean;
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

const
  INVALID_SOCKET = -1;
  UNIX_PATH_MAX = 107;

type
  { sockaddr_un for Free Pascal - struct sockaddr_un in system header }
  TSockAddrUn = packed record
    sun_family: sa_family_t;
    sun_path: array[0..UNIX_PATH_MAX] of AnsiChar;
  end;

{ TUnixSocketTransport }

constructor TUnixSocketTransport.Create;
begin
  inherited Create;
  FListenSocket := INVALID_SOCKET;
  FClientSocket := INVALID_SOCKET;
  FWakePipe[0] := -1;
  FWakePipe[1] := -1;
  FConnected := False;
end;

destructor TUnixSocketTransport.Destroy;
begin
  Close;
  inherited;
end;

procedure TUnixSocketTransport.CloseSocket(var ASocket: Integer);
begin
  if ASocket <> INVALID_SOCKET then begin
    fpShutdown(ASocket, 2); // SHUT_RDWR
    fpClose(ASocket);
    ASocket := INVALID_SOCKET;
  end;
end;

procedure TUnixSocketTransport.Open(const AAddress: string);
begin
  FAddress := AAddress;
  FActualSocketPath := '';
end;

function TUnixSocketTransport.Accept(TimeoutMs: Cardinal): Boolean;
var
  SockAddr: TSockAddrUn;
  AddrLen: Integer;
  SockPath: AnsiString;
begin
  Result := False;

  // ── 清理旧连接 ──
  if FConnected then
    Disconnect;
  CloseSocket(FClientSocket);

  // ── 创建监听套接字（仅首次 ──
  if FListenSocket = INVALID_SOCKET then begin
    // 生成套接字路径：若为 "daofy_auto" 默认名，则追加 PID
    if SameText(FAddress, 'daofy_auto') then
      SockPath := AnsiString('/tmp/daofy_auto_' + IntToStr(fpGetPID))
    else
      SockPath := AnsiString(FAddress);
    FActualSocketPath := string(SockPath);

    // 移除旧套接字文件（如果存在）
    FpUnlink(PAnsiChar(SockPath));

    FListenSocket := fpSocket(AF_UNIX, SOCK_STREAM, 0);
    if FListenSocket = INVALID_SOCKET then begin
      Sleep(500);
      Exit;
    end;

    FillChar(SockAddr, SizeOf(SockAddr), 0);
    SockAddr.sun_family := AF_UNIX;
    StrPLCopy(SockAddr.sun_path, string(SockPath), UNIX_PATH_MAX);

    AddrLen := SizeOf(SockAddr.sun_family) + Length(SockPath);
    if AddrLen > SizeOf(SockAddr) then
      AddrLen := SizeOf(SockAddr);

    if fpBind(FListenSocket, @SockAddr, AddrLen) <> 0 then begin
      CloseSocket(FListenSocket);
      Sleep(500);
      Exit;
    end;

    if fpListen(FListenSocket, 1) <> 0 then begin
      CloseSocket(FListenSocket);
      Sleep(500);
      Exit;
    end;

    // 创建自唤醒管道
    if fpPipe(FWakePipe) <> 0 then begin
      CloseSocket(FListenSocket);
      Sleep(500);
      Exit;
    end;
  end;

  // ── 接受连接（非阻塞轮询 + 可唤醒）──
  while True do begin
    // 用 select 监听 listen socket + wake pipe
    if not FConnected then begin
      // 首次连接：等待客户端加入
      AddrLen := SizeOf(SockAddr);
      FillChar(SockAddr, SizeOf(SockAddr), 0);
      FClientSocket := fpAccept(FListenSocket, @SockAddr, @AddrLen);
      if FClientSocket <> INVALID_SOCKET then begin
        FConnected := True;
        Result := True;
        Exit;
      end else begin
        Sleep(500);
        Exit;
      end;
    end;
  end;
end;

function TUnixSocketTransport.WaitForRequest(TimeoutMs: Cardinal): TTransportWaitResult;
var
  rfds: TFDSet;
  MaxFd, N: Integer;
  tv: TTimeVal;
  tvp: PTimeVal;
begin
  if FClientSocket = INVALID_SOCKET then
    Exit(twError);

  FD_ZERO(rfds);
  FD_SET(FClientSocket, rfds);
  FD_SET(FWakePipe[0], rfds);

  if FClientSocket > FWakePipe[0] then
    MaxFd := FClientSocket + 1
  else
    MaxFd := FWakePipe[0] + 1;

  // 超时参数
  if TimeoutMs = INFINITE then
    tvp := nil
  else begin
    tv.tv_sec := TimeoutMs div 1000;
    tv.tv_usec := (TimeoutMs mod 1000) * 1000;
    tvp := @tv;
  end;

  N := fpSelect(MaxFd, @rfds, nil, nil, tvp);
  if N < 0 then begin
    if fpGetErrno = ESysEINTR then
      Exit(twTimeout);
    Exit(twError);
  end;
  if N = 0 then
    Exit(twTimeout);

  // 唤醒管道可读 → 清空并返回 twWake
  if FD_ISSET(FWakePipe[0], rfds) then begin
    DrainWakePipe;
    Exit(twWake);
  end;

  // 客户端套接字可读
  if FD_ISSET(FClientSocket, rfds) then
    Exit(twRequest);

  Result := twTimeout;
end;

function TUnixSocketTransport.DrainWakePipe: Boolean;
var
  Buf: array[0..63] of Byte;
begin
  repeat
    // 非阻塞清空唤醒管道
  until fpRead(FWakePipe[0], @Buf, SizeOf(Buf)) <= 0;
  // 忽略 EAGAIN / EWOULDBLOCK
  Result := True;
end;

function TUnixSocketTransport.ReadRequest(out ARequest: string): Boolean;
const
  BUF_SIZE = 4096;
var
  Buf: array[0..BUF_SIZE - 1] of Byte;
  Total: TBytes;
  N: Integer;
  Framed: Boolean;
begin
  Result := False;
  ARequest := '';
  SetLength(Total, 0);
  Framed := False;

  repeat
    N := fpRead(FClientSocket, @Buf, SizeOf(Buf));
    if N <= 0 then begin
      // 连接断开
      Disconnect;
      Exit;
    end;

    // 检查帧边界：JSON 以 #0 终止（client 端发送约定）
    if Buf[N - 1] = 0 then begin
      SetLength(Total, Length(Total) + N - 1);
      Move(Buf[0], Total[Length(Total) - (N - 1)], N - 1);
      Framed := True;
      Break;
    end else begin
      SetLength(Total, Length(Total) + N);
      Move(Buf[0], Total[Length(Total) - N], N);
    end;
  until Framed;

  ARequest := Trim(TEncoding.UTF8.GetString(Total));
  Result := ARequest <> '';
end;

function TUnixSocketTransport.SendResponse(const AResp: string): Boolean;
var
  RespBytes: TBytes;
  N: Integer;
begin
  if FClientSocket = INVALID_SOCKET then
    Exit(False);
  RespBytes := TEncoding.UTF8.GetBytes(AResp + #10);
  N := fpWrite(FClientSocket, @RespBytes[0], Length(RespBytes));
  Result := N > 0;
end;

procedure TUnixSocketTransport.Disconnect;
begin
  FConnected := False;
  CloseSocket(FClientSocket);
end;

procedure TUnixSocketTransport.Wake;
var
  C: Byte;
begin
  C := 1;
  if FWakePipe[1] <> -1 then
    fpWrite(FWakePipe[1], @C, 1);
end;

procedure TUnixSocketTransport.Close;
begin
  Disconnect;
  CloseSocket(FListenSocket);

  // 清理唤醒管道
  if FWakePipe[0] <> -1 then begin
    fpClose(FWakePipe[0]);
    FWakePipe[0] := -1;
  end;
  if FWakePipe[1] <> -1 then begin
    fpClose(FWakePipe[1]);
    FWakePipe[1] := -1;
  end;

  // 移除套接字文件
  if FAddress <> '' then begin
    if SameText(FAddress, 'daofy_auto') then
      FpUnlink(PAnsiChar('/tmp/daofy_auto_' + IntToStr(fpGetPID)))
    else
      FpUnlink(PAnsiChar(AnsiString(FAddress)));
  end;
end;

function TUnixSocketTransport.GetTransportAddress: string;
begin
  if FActualSocketPath <> '' then
    Result := FActualSocketPath
  else
    Result := FAddress;
end;

end.
