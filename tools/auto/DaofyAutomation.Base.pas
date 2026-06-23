unit DaofyAutomation.Base;

{===============================================================================
  DaofyAutomation.Base - 自动化框架公共基类

  TAutomationProcessorBase（抽象类）：
    - 命名管道通信（纯 Win32 API，框架无关）
    - JSON 协议解析（同步/异步命令分发）
    - RTTI 辅助函数（IsSimpleKind / IsSkippedProp / PropToJSON）
    - Win32 层面命令（msgscan/msgclick/msgclose/wait/exit/snapdir）
    - BtnID 标准按钮 ID 映射
    - 框架相关操作通过抽象方法委托给子类

  子类必须实现 Vcl.DaofyAutomation 或 Fmx.DaofyAutomation。
  使用者 uses 具体子单元（如 Vcl.DaofyAutomation），不直接 uses 此基类。
===============================================================================}
interface

uses
  Winapi.Windows, Winapi.Messages,
  System.SysUtils, System.Classes, System.Rtti, System.TypInfo,
  System.Generics.Collections, System.JSON;

const
  WM_DAOFY_CMD = WM_USER + $200;
  MAX_PIPE     = 4096;
  BM_CLICK     = $00F5;
  JPG_Q        = 80;
  ASYNC_TTL    = 60000; // 异步结果 60 秒未取自动清理

type
  TAsyncResultRec = record
    Resp: string;
    Tick: UInt64;
  end;

type
  /// <summary>
  ///  自动化处理器抽象基类。派生于 TThread，在后台线程监听命名管道，
  ///  将接收到的 JSON 请求在主线程上下文中执行。
  ///  子类负责实现框架特定的截图/控件操作/RTTI。
  /// </summary>
  TAutomationProcessorBase = class(TThread)
  private
    class var FCurrent: TAutomationProcessorBase;
  strict private
    FMsgWnd: HWND;
    FPipeName: string;
    FLastResp: string;
    FAsyncResults: TDictionary<string, TAsyncResultRec>;
    FAsyncEvent: THandle;
    FAsyncQueue: TList<string>;
    FAsyncQueueCS: TRTLCriticalSection;
    FRegFilePath: string;  // 进程注册文件路径 (%TEMP%\daofy-rtti-{PID}.json)
  protected
    FSSDir: string;
    class function GetCurrent: TAutomationProcessorBase; static;
    class procedure SetCurrent(const Value: TAutomationProcessorBase); static;
  protected
    // ── 子类必须实现的抽象方法 ──

    /// <summary>截图：窗口内容 → JPEG 文件</summary>
    function TakeShot(const AFile: string): string; virtual; abstract;

    /// <summary>获取活动窗体状态快照（写入 _formstate.json）</summary>
    function DoDump: string; virtual; abstract;

    /// <summary>扫描弹出菜单（写入 _formstate.json）</summary>
    function DoDlgScan: string; virtual; abstract;

    /// <summary>点击弹出菜单项</summary>
    function DoDlgClick(const Param: string): string; virtual; abstract;

    /// <summary>激活指定类名/名称的窗体</summary>
    function HandleCmdGoto(const ReqId, Target: string): string; virtual; abstract;

    /// <summary>点击控件（可带 @x,y 坐标）</summary>
    function HandleCmdClick(const ReqId, Target: string): string; virtual; abstract;

    /// <summary>双击控件</summary>
    function HandleCmdDblClick(const ReqId, Target: string): string; virtual; abstract;

    /// <summary>右键弹出菜单</summary>
    function HandleCmdRightClick(const ReqId, Target: string): string; virtual; abstract;

    /// <summary>模拟鼠标悬停</summary>
    function HandleCmdHover(const ReqId, Target: string): string; virtual; abstract;

    /// <summary>移动鼠标到控件中心或指定坐标（x/y 可选）</summary>
    function HandleCmdMove(const ReqId, Target: string; const X, Y: Integer): string; virtual; abstract;

    /// <summary>拖拽：从 source 到 target 或到坐标 (x,y)</summary>
    function HandleCmdDrag(const ReqId, Source, Target: string; const X, Y: Integer): string; virtual; abstract;

    /// <summary>等待控件属性满足条件（prop 支持点号嵌套，timeout/interval 单位 ms）</summary>
    function HandleCmdWaitFor(const ReqId, Target, Prop, Value: string;
      TimeoutMs, IntervalMs: Integer): string; virtual;

    /// <summary>枚举所有窗口/窗体</summary>
    function HandleCmdListWnd(const ReqId: string): string; virtual; abstract;

    /// <summary>设置控件文本</summary>
    function HandleCmdType(const ReqId, Target, Value: string): string; virtual; abstract;

    /// <summary>发送按键（key 值如 Tab/Enter/Esc/F1 或单字符）</summary>
    function HandleCmdKey(const ReqId, Target, Key: string): string; virtual; abstract;

    /// <summary>RTTI 读取属性值</summary>
    function HandleRGet(const ReqId, Target, Prop: string): string; virtual; abstract;

    /// <summary>RTTI 写入属性值</summary>
    function HandleRSet(const ReqId, Target, Prop, Val: string): string; virtual; abstract;

    /// <summary>RTTI 调用控件的公开方法（method 支持点号路径如 Items.Add，params 为 JSON 数组）</summary>
    function HandleRCall(const ReqId, Target, Method, ParamsJSON: string): string; virtual; abstract;

    /// <summary>RTTI 检视控件（返回成员列表）</summary>
    function HandleRInsp(const ReqId, Target: string): string; virtual; abstract;

    /// <summary>终止应用程序</summary>
    procedure DoTerminateApp; virtual; abstract;

    /// <summary>查找命名控件</summary>
    function FindNamedControl(const AName: string): TObject; virtual; abstract;

    /// <summary>获取当前活动窗体</summary>
    function GetActiveForm: TObject; virtual; abstract;

    // ── RTTI 发现（可选重写，基类提供默认实现）──

    /// <summary>返回所有可选 RTTI 类（子类重写可返回 Screen.Forms 等）</summary>
    function GetRttiClasses: TArray<TClass>; virtual;

    /// <summary>RTTI 发现 — 扫描 published 方法/属性，返回 JSON Schema</summary>
    function HandleRttiDiscover(const ReqId, Target: string): string; virtual;

    // ── JSON 协议辅助 ──

    function GetReqId(const Req: string): string;
    function GetCmd(const Req: string): string;
    function IsAsyncCmd(const Cmd: string): Boolean;
    function GetJSONStr(const J: TJSONObject; const K, Def: string): string;
    function WriteResp(const ReqId, Status, Data: string): string;
    procedure WriteJSON(Obj: TJSONObject);

    // ── RTTI 辅助（纯 RTL，框架无关）──

    function IsSkippedProp(const N: string): Boolean;
    function IsSimpleKind(K: TTypeKind): Boolean;
    function PropToJSON(const Prop: TRttiProperty; Obj: TObject): TJSONValue;
    function BtnID(const S: string): Integer;

    /// <summary>解析 "PropName[Index]" → PropName, Index。无索引时返回 False。</summary>
    class function ParseIndexedProp(const Segment: string;
      out PropName: string; out Index: Integer): Boolean; static;

    // ── MessageBox / 文件对话框操作（纯 Win32）──

    function DoMsgScan: string;
    function DoMsgClick(const Param: string): string;
    function DoDlgFile(const APath, ATarget: string): string;

    // ── 进程注册（共享文件发现）──

    procedure WriteRegFile;
    procedure DeleteRegFile;

    // ── 命令分发 ──

    function ExecCmd(const AReq: string): string;
    procedure WndProc(var Msg: TMessage);

    // ── 截图入口 ──

    procedure DoCap(const AName: string);
  public
    constructor Create(const APipeName: string);
    destructor Destroy; override;
    procedure SetSSDir(const D: string);
    procedure DoCapPub(const AName: string);

    class property Current: TAutomationProcessorBase read GetCurrent write SetCurrent;

    procedure Execute; override;
  end;

implementation

uses
  DaofyAutomation.RttiDiscovery;

{ ═════════════════════════════════════════════════════════════════════════════
  WndProc（stdcall 静态函数，可被 SendMessage 跨线程调用）
  ═════════════════════════════════════════════════════════════════════════════ }

function WP(hWnd: HWND; Msg: UINT; w: WPARAM; l: LPARAM): LRESULT; stdcall;
var P: PWideChar; Cmd: string;
begin
  Result := 0;
  if (Msg = WM_DAOFY_CMD) and (TAutomationProcessorBase.Current <> nil) then begin
    P := PWideChar(w);
    if P <> nil then begin
      Cmd := string(P);
      TAutomationProcessorBase.Current.ExecCmd(Cmd);
      GlobalFree(Winapi.Windows.HGLOBAL(w));
    end;
  end else
    Result := DefWindowProc(hWnd, Msg, w, l);
end;

{ ═════════════════════════════════════════════════════════════════════════════
  TAutomationProcessorBase
  ═════════════════════════════════════════════════════════════════════════════ }

class function TAutomationProcessorBase.GetCurrent: TAutomationProcessorBase;
begin
  Result := FCurrent;
end;

class procedure TAutomationProcessorBase.SetCurrent(
  const Value: TAutomationProcessorBase);
begin
  FCurrent := Value;
end;

constructor TAutomationProcessorBase.Create(const APipeName: string);
begin
  inherited Create(False);
  FPipeName := APipeName;
  FMsgWnd := AllocateHWnd(WndProc);
  FAsyncResults := TDictionary<string, TAsyncResultRec>.Create;
  FAsyncQueue := TList<string>.Create;
  FAsyncEvent := CreateEvent(nil, False, False, nil);
  InitializeCriticalSection(FAsyncQueueCS);
  FreeOnTerminate := False;
end;

destructor TAutomationProcessorBase.Destroy;
begin
  DeleteRegFile;
  Terminate;
  WaitFor;
  if FMsgWnd <> 0 then begin
    DeallocateHWnd(FMsgWnd);
    FMsgWnd := 0;
  end;
  FAsyncQueue.Free;
  FAsyncResults.Free;
  CloseHandle(FAsyncEvent);
  DeleteCriticalSection(FAsyncQueueCS);
  if FCurrent = Self then
    FCurrent := nil;
  inherited;
end;

procedure TAutomationProcessorBase.SetSSDir(const D: string);
begin
  FSSDir := D;
end;

procedure TAutomationProcessorBase.DoCapPub(const AName: string);
begin
  DoCap(AName);
end;

(*═════════════════════════════════════════════════════════════════════════════
  进程注册（共享文件发现）
  写入 %TEMP%\daofy-rtti-{PID}.json，MCP 端通过扫描这些文件发现运行中的进程。
  ════════════════════════════════════════════════════════════════════════════*)

procedure TAutomationProcessorBase.WriteRegFile;
var
  TempDir: array[0..MAX_PATH] of Char;
  AppPath: array[0..MAX_PATH] of Char;
  PID: DWORD;
  RegObj: TJSONObject;
  UTF8NoBom: TEncoding;
begin
  if FRegFilePath <> '' then Exit;

  GetTempPath(MAX_PATH, TempDir);
  PID := GetCurrentProcessId;
  GetModuleFileName(0, AppPath, MAX_PATH);

  FRegFilePath := Format('%sdaofy-rtti-%d.json', [TempDir, PID]);

  UTF8NoBom := TEncoding.GetEncoding(CP_UTF8);
  RegObj := TJSONObject.Create;
  try
    RegObj.AddPair('pipe', TJSONString.Create(FPipeName));
    RegObj.AddPair('pid', TJSONNumber.Create(PID));
    RegObj.AddPair('name', TJSONString.Create(ExtractFileName(AppPath)));
    RegObj.AddPair('timestamp', TJSONNumber.Create(Now * 86400));

    var Bytes: TBytes := UTF8NoBom.GetBytes(RegObj.ToJSON);
    var FS: TFileStream := TFileStream.Create(FRegFilePath, fmCreate);
    try
      FS.Write(Bytes[0], Length(Bytes));
    finally
      FS.Free;
    end;
  finally
    RegObj.Free;
    UTF8NoBom.Free;
  end;
end;

procedure TAutomationProcessorBase.DeleteRegFile;
begin
  if FRegFilePath <> '' then
  begin
    if FileExists(FRegFilePath) then
      DeleteFile(FRegFilePath);
    FRegFilePath := '';
  end;
end;

{ ── 管道线程 ── }

procedure TAutomationProcessorBase.Execute;

  procedure SendResp(h: THandle; const Resp: string);
  var R: TBytes; Bw: DWORD;
  begin
    R := TEncoding.UTF8.GetBytes(Resp + #10);
    WriteFile(h, R[0], Length(R), Bw, nil);
  end;

  procedure FlushAsyncResults(h: THandle);
  var
    List: TArray<string>;
    S: string;
  begin
    EnterCriticalSection(FAsyncQueueCS);
    try
      List := FAsyncQueue.ToArray;
      FAsyncQueue.Clear;
    finally
      LeaveCriticalSection(FAsyncQueueCS);
    end;
    for S in List do
      SendResp(h, S);
  end;

type
  PByteBuffer = ^TByteBuffer;
  TByteBuffer = array[0..MAX_PIPE - 1] of AnsiChar;

var
  h: THandle;
  pBuf: PByteBuffer;
  Buf: array[0..MAX_PIPE - 1] of AnsiChar;
  Br, Bw, Bw2: DWORD;
  Req, Resp, ReqId, Cmd: string;
  Overlap: TOverlapped;
  WaitEvents: array[0..1] of THandle;
  WR: DWORD;
  BytesAvail: DWORD;
begin
  while not Terminated do begin
    h := CreateNamedPipe(PChar(FPipeName), PIPE_ACCESS_DUPLEX,
      PIPE_TYPE_MESSAGE or PIPE_READMODE_MESSAGE or PIPE_WAIT,
      PIPE_UNLIMITED_INSTANCES, MAX_PIPE, MAX_PIPE, 100, nil);
    if h = INVALID_HANDLE_VALUE then begin Sleep(500); Continue; end;
    if not ConnectNamedPipe(h, nil) and (GetLastError <> ERROR_PIPE_CONNECTED) then begin
      CloseHandle(h); Sleep(500); Continue;
    end;

    // 首次连接成功后写入进程注册文件
    WriteRegFile;

    // 初始化 OVERLAPPED 结构
    FillChar(Overlap, SizeOf(Overlap), 0);
    Overlap.hEvent := CreateEvent(nil, True, False, nil);
    WaitEvents[0] := Overlap.hEvent;
    WaitEvents[1] := FAsyncEvent;

    // 发起异步 ReadFile
    if not ReadFile(h, Buf, SizeOf(Buf) - 1, Br, @Overlap) then begin
      if GetLastError <> ERROR_IO_PENDING then begin
        CloseHandle(Overlap.hEvent); CloseHandle(h); Continue;
      end;
    end;

    while not Terminated do begin
      WR := WaitForMultipleObjects(2, @WaitEvents, False, ASYNC_TTL);

      if WR = WAIT_OBJECT_0 then begin
        // ── 管道请求到达 ──
        if not GetOverlappedResult(h, Overlap, Br, False) or (Br = 0) then
          Break;
        Req := Trim(string(UTF8ToString(Copy(Buf, 0, Br))));
        if Req <> '' then begin
          ReqId := GetReqId(Req);
          Cmd := GetCmd(Req);
          if Cmd = '' then
            Resp := WriteResp(ReqId, 'err', 'no cmd')
          else if IsAsyncCmd(Cmd) then begin
            var P := PWideChar(GlobalAlloc(GMEM_FIXED,
              (Length(Req) + 1) * SizeOf(WideChar)));
            if P <> nil then begin
              Move(PWideChar(Req)^, P^, (Length(Req) + 1) * SizeOf(WideChar));
              PostMessage(FMsgWnd, WM_DAOFY_CMD, WPARAM(P), 0);
            end;
            Resp := WriteResp(ReqId, 'ack', '');
          end else begin
            var P := PWideChar(GlobalAlloc(GMEM_FIXED,
              (Length(Req) + 1) * SizeOf(WideChar)));
            if P <> nil then begin
              Move(PWideChar(Req)^, P^, (Length(Req) + 1) * SizeOf(WideChar));
              SendMessage(FMsgWnd, WM_DAOFY_CMD, WPARAM(P), 0);
            end;
            Resp := FLastResp;
          end;
          SendResp(h, Resp);
        end;
        // 发起下一次异步 ReadFile
        FillChar(Buf, SizeOf(Buf), 0);
        ResetEvent(Overlap.hEvent);
        if not ReadFile(h, Buf, SizeOf(Buf) - 1, Br, @Overlap) then
          if GetLastError <> ERROR_IO_PENDING then Break;

      end else if WR = WAIT_OBJECT_0 + 1 then begin
        // ── 异步结果就绪（等待 peekresult 取回）──
      end else if WR = WAIT_TIMEOUT then begin
        // ── 60 秒超时，清理过期异步结果 ──
        var NowTick := GetTickCount;
        var ExpiredList: TList<string>;
        ExpiredList := TList<string>.Create;
        try
          for var K in FAsyncResults.Keys do
            if NowTick - FAsyncResults[K].Tick > ASYNC_TTL then
              ExpiredList.Add(K);
          for var K in ExpiredList do
            FAsyncResults.Remove(K);
        finally
          ExpiredList.Free;
        end;
      end else
        Break;
    end;

    CloseHandle(Overlap.hEvent);
    CloseHandle(h);
  end;
end;

{ ── WndProc（AllocateHWnd 回调，运行在主线程）── }

procedure TAutomationProcessorBase.WndProc(var Msg: TMessage);
var
  CmdStr: string;
  Cmd: string;
  RId: string;
begin
  if Msg.Msg = WM_DAOFY_CMD then begin
    var P := PWideChar(Msg.WParam);
    if P <> nil then begin
      CmdStr := string(P);
      FLastResp := ExecCmd(CmdStr);
      // 异步命令完成后存结果，供 getresult 取回
      Cmd := GetCmd(CmdStr);
      if IsAsyncCmd(Cmd) then begin
        RId := GetReqId(CmdStr);
        if RId <> '' then begin
          var AR: TAsyncResultRec;
          AR.Resp := FLastResp;
          AR.Tick := GetTickCount;
          FAsyncResults.AddOrSetValue(RId, AR);
          EnterCriticalSection(FAsyncQueueCS);
          FAsyncQueue.Add(FLastResp);
          LeaveCriticalSection(FAsyncQueueCS);
          SetEvent(FAsyncEvent);
        end;
      end;
      GlobalFree(Winapi.Windows.HGLOBAL(Msg.WParam));
    end;
    Msg.Result := 0;
  end else
    Msg.Result := DefWindowProc(FMsgWnd, Msg.Msg, Msg.WParam, Msg.LParam);
end;

{ ── ExecCmd：所有命令的统一入口（运行在主线程）── }

function TAutomationProcessorBase.ExecCmd(const AReq: string): string;
var
  J: TJSONObject;
  Cmd, ReqId, Target: string;
  WaitMs: Integer;
  Buf: array[0..255] of Char;
  V: TJSONValue;
begin
  try
    V := TJSONObject.ParseJSONValue(AReq);
    if V = nil then Exit(WriteResp('', 'err', 'invalid JSON'));
    if not (V is TJSONObject) then begin
      V.Free;
      Exit(WriteResp('', 'err', 'not a JSON object'));
    end;
    J := V as TJSONObject;
    try
      ReqId := GetJSONStr(J, 'reqId', '');
      Cmd   := LowerCase(GetJSONStr(J, 'cmd', ''));
      Target := GetJSONStr(J, 'target', '');

      if Cmd = '' then
        Result := WriteResp(ReqId, 'err', 'no cmd')

      // ── 框架无关命令（纯 Win32 / RTL）──

      else if Cmd = 'wait' then begin
        WaitMs := StrToIntDef(GetJSONStr(J, 'ms', '500'), 500);
        if WaitMs > 10000 then WaitMs := 10000;
        Sleep(WaitMs);
        Result := WriteResp(ReqId, 'ok', 'OK');
      end

      else if Cmd = 'capture' then begin
        DoCap(Target);
        Result := WriteResp(ReqId, 'ok', 'captured');
      end

      else if Cmd = 'snapdir' then begin
        FSSDir := Target;
        ForceDirectories(FSSDir);
        Result := WriteResp(ReqId, 'ok', 'OK');
      end

      else if Cmd = 'exit' then begin
        DoTerminateApp;
        Result := WriteResp(ReqId, 'ok', 'bye');
      end

      // ── MessageBox/对话框扫描（纯 Win32 API）──

      else if Cmd = 'msgscan' then begin
        DoMsgScan;
        Result := WriteResp(ReqId, 'ok', 'scanned');
      end

      else if Cmd = 'msgclick' then begin
        Result := WriteResp(ReqId, 'ok', DoMsgClick(Target));
      end

      else if Cmd = 'msgclose' then begin
        var hMsgWnd: Winapi.Windows.HWND;
        hMsgWnd := FindWindowW('#32770', nil);
        while hMsgWnd <> 0 do begin
          GetWindowTextW(hMsgWnd, Buf, 256);
          if (Target = '') or (Pos(Target, string(Buf)) > 0) then begin
            SendMessage(hMsgWnd, WM_CLOSE, 0, 0);
            Break;
          end;
          hMsgWnd := GetNextWindow(hMsgWnd, GW_HWNDNEXT);
        end;
        Result := WriteResp(ReqId, 'ok', 'OK');
      end

      // ── 文件对话框操作 ──

      else if Cmd = 'dlgfile' then begin
        Result := WriteResp(ReqId, 'ok', DoDlgFile(
          GetJSONStr(J, 'path', ''),
          LowerCase(Target)));
      end

      // ── 框架相关命令（委托给子类）──

      else if Cmd = 'goto' then
        Result := HandleCmdGoto(ReqId, Target)

      else if Cmd = 'click' then
        Result := HandleCmdClick(ReqId, Target)

      else if Cmd = 'dblclick' then
        Result := HandleCmdDblClick(ReqId, Target)

      else if Cmd = 'rclick' then
        Result := HandleCmdRightClick(ReqId, Target)

      else if Cmd = 'hover' then
        Result := HandleCmdHover(ReqId, Target)

      else if Cmd = 'drag' then begin
        var Src := GetJSONStr(J, 'source', '');
        if Src = '' then Src := Target;
        var DX := StrToIntDef(GetJSONStr(J, 'x', '-1'), -1);
        var DY := StrToIntDef(GetJSONStr(J, 'y', '-1'), -1);
        Result := HandleCmdDrag(ReqId, Src, GetJSONStr(J, 'target', ''), DX, DY);
      end

      else if Cmd = 'move' then begin
        var MX := StrToIntDef(GetJSONStr(J, 'x', '-1'), -1);
        var MY := StrToIntDef(GetJSONStr(J, 'y', '-1'), -1);
        Result := HandleCmdMove(ReqId, Target, MX, MY);
      end

      else if Cmd = 'type' then
        Result := HandleCmdType(ReqId, Target, GetJSONStr(J, 'value', ''))

      else if Cmd = 'dlgscan' then begin
        var DlgJSON := DoDlgScan;
        Result := WriteResp(ReqId, 'ok', DlgJSON);
      end

      else if Cmd = 'dlgclick' then
        Result := WriteResp(ReqId, 'ok', DoDlgClick(Target))

      else if Cmd = 'dumpstate' then begin
        var DumpJSON := DoDump;
        Result := WriteResp(ReqId, 'ok', DumpJSON);
      end

      // ── RTTI 命令 ──

      else if Cmd = 'rget' then
        Result := HandleRGet(ReqId, Target, GetJSONStr(J, 'prop', ''))

      else if Cmd = 'rset' then
        Result := HandleRSet(ReqId, Target, GetJSONStr(J, 'prop', ''),
          GetJSONStr(J, 'value', ''))

      else if Cmd = 'rinspect' then
        Result := HandleRInsp(ReqId, Target)

      else if Cmd = 'rcall' then
        Result := HandleRCall(ReqId, Target, GetJSONStr(J, 'method', ''),
          GetJSONStr(J, 'params', ''))

      else if Cmd = 'rtti_discover' then
        Result := HandleRttiDiscover(ReqId, Target)

      else if Cmd = 'waitfor' then
        Result := HandleCmdWaitFor(ReqId, Target, GetJSONStr(J, 'prop', ''),
          GetJSONStr(J, 'value', ''),
          StrToIntDef(GetJSONStr(J, 'timeout', '5000'), 5000),
          StrToIntDef(GetJSONStr(J, 'interval', '100'), 100))

      else if Cmd = 'key' then
        Result := HandleCmdKey(ReqId, Target, GetJSONStr(J, 'key', ''))

      else if Cmd = 'peekresult' then begin
        var AR: TAsyncResultRec;
        if FAsyncResults.TryGetValue(Target, AR) then
          Result := AR.Resp
        else
          Result := WriteResp(ReqId, 'err', 'NR:' + Target);
      end

      else if Cmd = 'listwnd' then
        Result := HandleCmdListWnd(ReqId)

      else
        Result := WriteResp(ReqId, 'err', 'unknown cmd: ' + Cmd);

    finally
      J.Free;
    end;
  except
    on E: Exception do
      Result := WriteResp('', 'err', E.Message);
  end;
end;

{ ── 截图入口 ── }

procedure TAutomationProcessorBase.DoCap(const AName: string);
begin
  if FSSDir = '' then Exit;
  TakeShot(FSSDir + '\' + AName + '.jpg');
end;

{ ── JSON 协议辅助 ── }

function TAutomationProcessorBase.GetJSONStr(const J: TJSONObject;
  const K, Def: string): string;
var V: TJSONValue;
begin
  V := J.Values[K];
  if V <> nil then Result := V.Value else Result := Def;
end;

function TAutomationProcessorBase.WriteResp(const ReqId, Status,
  Data: string): string;
var J: TJSONObject;
begin
  J := TJSONObject.Create;
  try
    J.AddPair('reqId', ReqId);
    J.AddPair('status', Status);
    J.AddPair('data', Data);
    Result := J.ToJSON;
  finally
    J.Free;
  end;
end;

procedure TAutomationProcessorBase.WriteJSON(Obj: TJSONObject);
var F: string; Raw: TBytes; SS: TFileStream;
begin
  if (FSSDir = '') or (Obj = nil) then Exit;
  F := FSSDir + '\_formstate.json';
  Raw := TEncoding.UTF8.GetBytes(Obj.ToJSON);
  SS := TFileStream.Create(F, fmCreate);
  try
    SS.Write(Raw[0], Length(Raw));
  finally
    SS.Free;
  end;
end;

function TAutomationProcessorBase.GetReqId(const Req: string): string;
var V: TJSONValue;
begin
  V := TJSONObject.ParseJSONValue(Req);
  if V is TJSONObject then
    Result := GetJSONStr(V as TJSONObject, 'reqId', '')
  else
    Result := '';
  V.Free;
end;

function TAutomationProcessorBase.GetCmd(const Req: string): string;
var V: TJSONValue;
begin
  V := TJSONObject.ParseJSONValue(Req);
  if V is TJSONObject then
    Result := LowerCase(GetJSONStr(V as TJSONObject, 'cmd', ''))
  else
    Result := '';
  V.Free;
end;

function TAutomationProcessorBase.IsAsyncCmd(const Cmd: string): Boolean;
begin
  Result := (Cmd = 'click') or (Cmd = 'dblclick') or (Cmd = 'rclick') or
            (Cmd = 'msgclick') or (Cmd = 'dlgclick') or (Cmd = 'hover') or
            (Cmd = 'move') or (Cmd = 'drag') or (Cmd = 'rcall') or
            (Cmd = 'key') or (Cmd = 'rset') or (Cmd = 'type');
end;

{ ── RTTI 辅助 ── }

function TAutomationProcessorBase.IsSkippedProp(const N: string): Boolean;
const
  X: array of string = [
    'Action', 'Align', 'AlignWithMargins', 'Anchors',
    'BiDiMode', 'BorderSpacing', 'Brush', 'Canvas',
    'ClientHeight', 'ClientWidth', 'Color', 'Constraints',
    'Cursor', 'CustomHint', 'Font', 'Handle',
    'HelpContext', 'HelpKeyword', 'HelpType', 'Hint',
    'ImeMode', 'ImeName',
    'Margins', 'Name', 'Owner', 'Padding', 'Parent',
    'ParentBackground', 'ParentBiDiMode', 'ParentColor',
    'ParentCtl3D', 'ParentCustomHint', 'ParentDoubleBuffered',
    'ParentFont', 'ParentShowHint', 'PopupMenu', 'ScrollBar',
    'Showing', 'StyleElements', 'Tag', 'Touch',
    'WindowHandle', 'WindowProc',
    'OnActivate', 'OnClick', 'OnChange', 'OnClose', 'OnCreate',
    'OnDblClick', 'OnDeactivate', 'OnDestroy', 'OnEnter',
    'OnExit', 'OnKeyDown', 'OnKeyPress', 'OnKeyUp',
    'OnMouseActivate', 'OnMouseDown', 'OnMouseEnter',
    'OnMouseLeave', 'OnMouseMove', 'OnMouseUp', 'OnResize',
    'OnShow'];
var S: string;
begin
  for S in X do
    if SameText(S, N) then Exit(True);
  Result := False;
end;

function TAutomationProcessorBase.IsSimpleKind(K: TTypeKind): Boolean;
begin
  Result := K in [tkString, tkUString, tkWString, tkLString,
    tkChar, tkWChar, tkInteger, tkInt64, tkEnumeration, tkFloat];
end;

function TAutomationProcessorBase.PropToJSON(const Prop: TRttiProperty;
  Obj: TObject): TJSONValue;
var V: TValue;
begin
  if not Prop.IsReadable then Exit(TJSONNull.Create);
  V := Prop.GetValue(Obj);
  case V.Kind of
    tkString, tkUString, tkWString, tkLString:
      Result := TJSONString.Create(V.AsString);
    tkChar, tkWChar:
      Result := TJSONString.Create(string(V.AsString));
    tkInteger, tkInt64:
      Result := TJSONNumber.Create(V.AsInteger);
    tkEnumeration:
      if SameText(Prop.PropertyType.Name, 'Boolean') then
        Result := TJSONBool.Create(V.AsBoolean)
      else
        Result := TJSONString.Create(GetEnumName(
          Prop.PropertyType.Handle, V.AsOrdinal));
    tkFloat:
      Result := TJSONNumber.Create(V.AsExtended);
  else
    Result := TJSONNull.Create;
  end;
end;

function TAutomationProcessorBase.BtnID(const S: string): Integer;
begin
  if LowerCase(S) = 'ok'     then Exit(1);
  if LowerCase(S) = 'cancel' then Exit(2);
  if LowerCase(S) = 'abort'  then Exit(3);
  if LowerCase(S) = 'retry'  then Exit(4);
  if LowerCase(S) = 'ignore' then Exit(5);
  if LowerCase(S) = 'yes'    then Exit(6);
  if LowerCase(S) = 'no'     then Exit(7);
  Result := -1;
end;

class function TAutomationProcessorBase.ParseIndexedProp(
  const Segment: string; out PropName: string; out Index: Integer): Boolean;
var
  LB, RB: Integer;
begin
  LB := Pos('[', Segment);
  RB := Pos(']', Segment);
  if (LB > 0) and (RB > LB) then
  begin
    PropName := Copy(Segment, 1, LB - 1);
    Index := StrToIntDef(Copy(Segment, LB + 1, RB - LB - 1), -1);
    Result := Index >= 0;
  end else
  begin
    PropName := Segment;
    Index := -1;
    Result := False;
  end;
end;

{ ── MessageBox 扫描/点击（纯 Win32 API，框架无关）── }

function TAutomationProcessorBase.DoMsgScan: string;
var
  Root: TJSONObject;
  Buttons: TJSONArray;
  hDlg, hSt, hBtn: HWND;
  Buf: array[0..511] of Char;
begin
  if FSSDir = '' then Exit('NODIR');
  hDlg := FindWindowW('#32770', nil);
  if hDlg = 0 then Exit('NOD');

  Root := TJSONObject.Create;
  try
    FillChar(Buf, SizeOf(Buf), 0);
    GetWindowTextW(hDlg, Buf, 512);
    Root.AddPair('title', string(Buf));
    Root.AddPair('type', 'msgbox');
    Root.AddPair('hWnd', IntToStr(hDlg));

    hSt := FindWindowExW(hDlg, 0, 'Static', nil);
    if hSt <> 0 then begin
      FillChar(Buf, SizeOf(Buf), 0);
      GetWindowTextW(hSt, Buf, 512);
      Root.AddPair('text', string(Buf));
    end else
      Root.AddPair('text', '');

    Buttons := TJSONArray.Create;
    hBtn := FindWindowExW(hDlg, 0, 'Button', nil);
    while hBtn <> 0 do begin
      FillChar(Buf, SizeOf(Buf), 0);
      GetWindowTextW(hBtn, Buf, 512);
      if string(Buf) <> '' then
        Buttons.AddElement(TJSONString.Create(string(Buf)));
      hBtn := FindWindowExW(hDlg, hBtn, 'Button', nil);
    end;
    Root.AddPair('buttons', Buttons);

    WriteJSON(Root);
    Result := 'OK';
  finally
    Root.Free;
  end;
end;

function TAutomationProcessorBase.DoMsgClick(const Param: string): string;
var
  hDlg, hBtn: HWND;
  Buf: array[0..255] of Char;
  ID: Integer;
begin
  hDlg := FindWindowW('#32770', nil);
  if hDlg = 0 then Exit('NOD');

  ID := BtnID(Param);
  if ID > 0 then begin
    SendMessage(hDlg, WM_COMMAND, ID, 0);
    Exit('OK');
  end;

  hBtn := FindWindowExW(hDlg, 0, 'Button', nil);
  while hBtn <> 0 do begin
    FillChar(Buf, SizeOf(Buf), 0);
    GetWindowTextW(hBtn, Buf, 255);
    if LowerCase(string(Buf)) = LowerCase(Param) then begin
      SendMessage(hBtn, BM_CLICK, 0, 0);
      Exit('OK');
    end;
    hBtn := FindWindowExW(hDlg, hBtn, 'Button', nil);
  end;
  Result := 'NF';
end;

{ ── waitfor ── }

function TAutomationProcessorBase.HandleCmdWaitFor(const ReqId, Target,
  Prop, Value: string; TimeoutMs, IntervalMs: Integer): string;
var
  Ctrl: TObject;
  Ctx: TRttiContext;
  Pr: TRttiProperty;
  IP: TRttiIndexedProperty;
  V: TValue;
  StartTime: UInt64;
  Parts: TArray<string>;
  i: Integer;
  Obj: TObject;
  CurrentValue: string;
  PropName: string;
  Idx: Integer;
begin
  Result := WriteResp(ReqId, 'err', 'NF:' + Target);

  // 用 Sleep 简单轮询（ExecCmd 在主线程运行，Sleep 不阻塞消息泵）
  StartTime := GetTickCount;
  while GetTickCount - StartTime < UInt64(TimeoutMs) do begin
    Ctrl := FindNamedControl(Target);
    if Ctrl = nil then begin
      Sleep(IntervalMs);
      Continue;
    end;

    Parts := Prop.Split(['.']);
    if Length(Parts) = 0 then
      Exit(WriteResp(ReqId, 'err', 'no property'));

    Ctx := TRttiContext.Create;
    try
      ParseIndexedProp(Parts[0], PropName, Idx);
      if Idx >= 0 then begin
        IP := Ctx.GetType(Ctrl.ClassType).GetIndexedProperty(PropName);
        if IP = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + PropName));
        V := IP.GetValue(Ctrl, [TValue.From<Integer>(Idx)]);
      end else begin
        Pr := Ctx.GetType(Ctrl.ClassType).GetProperty(PropName);
        if Pr = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + PropName));
        V := Pr.GetValue(Ctrl);
      end;
      Obj := Ctrl;

      for i := 1 to High(Parts) do begin
        if V.Kind <> tkClass then Break;
        Obj := V.AsObject;
        if Obj = nil then Break;

        ParseIndexedProp(Parts[i], PropName, Idx);
        if Idx >= 0 then begin
          IP := Ctx.GetType(Obj.ClassType).GetIndexedProperty(PropName);
          if IP = nil then Break;
          V := IP.GetValue(Obj, [TValue.From<Integer>(Idx)]);
        end else begin
          Pr := Ctx.GetType(Obj.ClassType).GetProperty(PropName);
          if Pr = nil then Break;
          V := Pr.GetValue(Obj);
        end;
      end;

      CurrentValue := V.ToString;
      if CurrentValue = Value then begin
        Result := WriteResp(ReqId, 'ok', CurrentValue);
        Exit;
      end;
    finally
      Ctx.Free;
    end;

    Sleep(IntervalMs);
  end;

  Result := WriteResp(ReqId, 'err', 'TIMEOUT:' + CurrentValue);
end;

{ ── RTTI 发现 ── }

function TAutomationProcessorBase.GetRttiClasses: TArray<TClass>;
begin
  // 基类默认返回空数组，子类（VCL/FMX）可重写返回所有可用窗体类
  Result := [];
end;

function TAutomationProcessorBase.HandleRttiDiscover(const ReqId,
  Target: string): string;
var
  Obj: TObject;
  Classes: TArray<TClass>;
  i: Integer;
  Root: TJSONObject;
  ClassesArr: TJSONArray;
  DiscoveredObj: TJSONObject;
  Found: Boolean;
begin
  Found := False;
  Root := TJSONObject.Create;
  try
    if Target <> '' then
    begin
      // ── 指定 target：按名称查找控件或类 ──
      Obj := FindNamedControl(Target);
      if Obj <> nil then
      begin
        // 找到了控件实例 → 扫描它的类
        ClassesArr := TJSONArray.Create;
        ClassesArr.AddElement(TRttiDiscoverer.DiscoverClass(Obj.ClassType, Target));
        Root.AddPair('classes', ClassesArr);
        Found := True;
      end
      else
      begin
        // 未找到控件 → 尝试在 GetRttiClasses 中匹配类名
        Classes := GetRttiClasses;
        for i := 0 to Length(Classes) - 1 do
          if SameText(Classes[i].ClassName, Target) then
          begin
            ClassesArr := TJSONArray.Create;
            ClassesArr.AddElement(TRttiDiscoverer.DiscoverClass(Classes[i], Target));
            Root.AddPair('classes', ClassesArr);
            Found := True;
            Break;
          end;
      end;

      if not Found then
        Exit(WriteResp(ReqId, 'err', 'NF:' + Target));
    end
    else
    begin
      // ── 未指定 target：扫描所有已知类 ──
      Classes := GetRttiClasses;
      ClassesArr := TJSONArray.Create;
      for i := 0 to Length(Classes) - 1 do
      begin
        DiscoveredObj := TRttiDiscoverer.DiscoverClass(Classes[i]);
        ClassesArr.AddElement(DiscoveredObj);
      end;
      Root.AddPair('classes', ClassesArr);
    end;

    Result := WriteResp(ReqId, 'ok', Root.ToJSON);
  finally
    Root.Free;
  end;
end;

{ ── dlgfile ── }

function TAutomationProcessorBase.DoDlgFile(const APath,
  ATarget: string): string;
var
  hDlg: HWND;
  hEdit, hBtn: HWND;
  Buf: array[0..511] of Char;
begin
  hDlg := FindWindowW('#32770', nil);
  if hDlg = 0 then Exit('NOD');

  if APath <> '' then begin
    // 找文件名输入框（Edit 或 ComboBox）
    hEdit := FindWindowExW(hDlg, 0, 'Edit', nil);
    if hEdit = 0 then begin
      hEdit := FindWindowExW(hDlg, 0, 'ComboBoxEx32', nil);
      if hEdit = 0 then
        hEdit := FindWindowExW(hDlg, 0, 'ComboBox', nil);
    end;
    if hEdit <> 0 then begin
      SetWindowTextW(hEdit, PWideChar(APath));
      // 设完文本后发 EN_CHANGE 通知，让对话框感知
      SendMessageW(hDlg, WM_COMMAND, $4000 or $300, LPARAM(hEdit));
    end;
  end;

  // 点按钮
  if ATarget = 'cancel' then begin
    SendMessageW(hDlg, WM_CLOSE, 0, 0);
    Result := 'OK';
  end else begin
    hBtn := FindWindowExW(hDlg, 0, 'Button', nil);
    while hBtn <> 0 do begin
      FillChar(Buf, SizeOf(Buf), 0);
      GetWindowTextW(hBtn, Buf, 511);
      var Txt := LowerCase(string(Buf));
      if (ATarget = '') and ((Txt = 'open') or (Txt = 'save') or
         (Txt = #25153#24320) or (Txt = #20445#23384)) then begin
        SendMessageW(hBtn, BM_CLICK, 0, 0);
        Exit('OK');
      end;
      if Txt = ATarget then begin
        SendMessageW(hBtn, BM_CLICK, 0, 0);
        Exit('OK');
      end;
      hBtn := FindWindowExW(hDlg, hBtn, 'Button', nil);
    end;
    // 没找到匹配按钮，用默认 IDOK
    if ATarget <> 'cancel' then begin
      SendMessageW(hDlg, WM_COMMAND, 1, 0);
      Result := 'OK';
    end else
      Result := 'NF';
  end;
end;

end.
