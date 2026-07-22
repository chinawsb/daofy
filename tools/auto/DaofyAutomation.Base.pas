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
  System.Classes,
  System.Generics.Collections,
  System.JSON,
  System.Rtti,
  System.SysUtils,
  System.TypInfo,
  Winapi.Messages,
  Winapi.Windows;

const
  WM_DAOFY_CMD = WM_USER + $200;
  MAX_PIPE     = 4096;
  BM_CLICK     = $00F5;
  JPG_Q        = 80;
  ASYNC_TTL    = 60000; // 异步结果 60 秒未取自动清理
type
  /// <summary>传输层等待结果。由平台相关传输单元返回。</summary>
  TTransportWaitResult = (twRequest, twWake, twTimeout, twError);

  /// <summary>传输层抽象接口。
  /// 由平台相关单元实现：Windows → TNamedPipeTransport（NamedPipe），
  /// POSIX → TUnixSocketTransport（Unix Domain Socket）。</summary>
  IAutomationTransport = interface
    ['{F2A1B3C0-D4E5-6789-ABCD-EF0123456789}']
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

  TFixtureSetup = reference to function: TValue;
  TFixtureTeardown = reference to procedure(const AValue: TValue);

  TTestFixture = record
    Setup: TFixtureSetup;
    TearDown: TFixtureTeardown;
    class function Create(ASetup: TFixtureSetup; ATearDown: TFixtureTeardown): TTestFixture; static;
  end;

  TAsyncResultRec = record
    Resp: string;
    Tick: UInt64;
  end;


  TAutomationCommandHandler = function(const ReqId, Target: string;
    const J: TJSONObject): string;
  /// <summary>
  ///  自动化处理器抽象基类。派生于 TThread，在后台线程监听命名管道，
  ///  将接收到的 JSON 请求在主线程上下文中执行。
  ///  子类负责实现框架特定的截图/控件操作/RTTI。
  /// </summary>
  TAutomationProcessorBase = class(TThread)
  private
    class var
      FCurrent: TAutomationProcessorBase;
      FExtraCommandHandlers: TDictionary<string, TAutomationCommandHandler>;
      FFixtures: TDictionary<string, TTestFixture>;
      FTestClasses: TDictionary<string, TClass>;
  strict private
    FMsgWnd: HWND;
    FPipeName: string;
    FLastResp: string;
    FAsyncResults: TDictionary<string, TAsyncResultRec>;
    FTransport: IAutomationTransport;
    FAsyncQueue: TList<string>;
    FAsyncQueueCS: TRTLCriticalSection;
    FAsyncResultsCS: TRTLCriticalSection; // 保护 FAsyncResults 跨线程访问
    FRegFilePath: string;  // 进程注册文件路径 (%TEMP%\daofy-rtti-{PID}.json)
    class function TryHandleExtraCommand(const Cmd, ReqId, Target: string;
      const J: TJSONObject; out AResponse: string): Boolean; static;
  protected
    FSSDir: string;
    class function GetCurrent: TAutomationProcessorBase; static;
    class procedure SetCurrent(const Value: TAutomationProcessorBase); static;
  protected
    /// <summary>工厂方法：按平台创建传输层实例。
    /// Windows → TNamedPipeTransport；POSIX → TUnixSocketTransport。
    /// 子类可重写以提供自定义传输层。</summary>
    function CreateTransport: IAutomationTransport; virtual;

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

    /// <summary>点击控件（支持 @x,y 坐标偏移）</summary>
    function HandleCmdClick(const ReqId, Target: string): string; virtual; abstract;

    /// <summary>双击控件</summary>
    function HandleCmdDblClick(const ReqId, Target: string): string; virtual; abstract;

    /// <summary>右键控件</summary>
    function HandleCmdRightClick(const ReqId, Target: string): string; virtual; abstract;

    /// <summary>悬停控件</summary>
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

    /// <summary>查找控件中指定文本的边界矩形（返回客户端 left,top,width,height），替代 OCR</summary>
    /// <param name="Mode">捕获模式：auto=先尝试 paint-hook 再回退 type-bound；paint=仅 paint-hook；type=仅 type-bound</param>
    /// <param name="IncludeInvisible">是否包含完全不可见的记录（默认 false，用于诊断）</param>
    function HandleCmdTextBounds(const ReqId, Target, Text: string;
      const Mode: string; IncludeInvisible: Boolean): string; virtual; abstract;

    /// <summary>RTTI 读取属性值</summary>
    function HandleRGet(const ReqId, Target, Prop: string): string; virtual; abstract;
    /// <summary>RTTI 写入属性值</summary>
    function HandleRSet(const ReqId, Target, Prop, Val: string): string; virtual; abstract;
    /// <summary>RTTI 调用控件的方法（method 支持点号路径如 Items.Add，params 为 JSON 数组，visibility 过滤可见度）</summary>
    function HandleRCall(const ReqId, Target, Method, ParamsJSON, Visibility: string): string; virtual; abstract;

    /// <summary>RTTI 检视控件（返回成员列表）
    /// <param name="Visibility">可见度过滤，逗号分隔：private,protected,public,published（默认 public,published）</param>
    /// </summary>
    function HandleRInsp(const ReqId, Target, Visibility: string): string; virtual; abstract;

    /// <summary>批量执行测试 — 解析 tests 数组，逐个 rcall，返回结构化报告</summary>
    function HandleRunTests(const ReqId: string; Tests: TJSONArray): string; virtual;

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

    class function FindProcessDialog(AStartAfter: HWND = 0): HWND; static;
    function DoMsgScan: string;
    function DoMsgClick(const Param: string): string;
    function DoDlgFile(const APath, ATarget: string): string;

    // ── 进程注册（共享文件发现）──

    procedure WriteRegFile(const AStatus: string = 'ready'; AErrorCode: DWORD = ERROR_SUCCESS);
    procedure DeleteRegFile;

    // ── 命令分发 ──

    function ExecCmd(const AReq: string): string;
    procedure WndProc(var Msg: TMessage);

    // ── 截图入口 ──

    procedure DoCap(const AName: string);
  public
    class procedure RegisterCommandHandler(const Cmd: string;
      Handler: TAutomationCommandHandler); static;
    class procedure UnregisterCommandHandler(const Cmd: string); static;

    class procedure RegisterFixture(const AName: string; ASetup: TFixtureSetup;
      ATearDown: TFixtureTeardown); static;
    class procedure UnregisterFixture(const AName: string); static;
    class function GetFixture(const AName: string): TTestFixture; static;

    class procedure RegisterTestClass(AClass: TClass;
      const AName: string = ''); static;
    class procedure UnregisterTestClass(const AName: string); static;
    class function GetTestClass(const AName: string): TClass; static;
    constructor Create(const APipeName: string);
    destructor Destroy; override;
    procedure Stop;
    procedure SetSSDir(const D: string);
    procedure DoCapPub(const AName: string);

    class property Current: TAutomationProcessorBase read GetCurrent write SetCurrent;

    procedure Execute; override;
  end;

/// <summary>按可见度过滤查找 RTTI 方法。支持逗号分隔列表：private,protected,public,published,all。</summary>
function FindMethodByVisibility(const AType: TRttiType; const AName, Visibility: string): TRttiMethod;

implementation

uses
  DaofyAutomation.RttiDiscovery
{$IFDEF MSWINDOWS}
  , DaofyAutomation.Windows
{$ELSE}
  , DaofyAutomation.Posix
{$ENDIF}
  ;

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

class procedure TAutomationProcessorBase.RegisterCommandHandler(const Cmd: string;
  Handler: TAutomationCommandHandler);
begin
  if (Cmd = '') or not Assigned(Handler) then
    Exit;
  if FExtraCommandHandlers = nil then
    FExtraCommandHandlers := TDictionary<string, TAutomationCommandHandler>.Create;
  FExtraCommandHandlers.AddOrSetValue(LowerCase(Cmd), Handler);
end;

class procedure TAutomationProcessorBase.UnregisterCommandHandler(const Cmd: string);
begin
  if (Cmd <> '') and (FExtraCommandHandlers <> nil) then
    FExtraCommandHandlers.Remove(LowerCase(Cmd));
end;

class function TAutomationProcessorBase.TryHandleExtraCommand(
  const Cmd, ReqId, Target: string; const J: TJSONObject;
  out AResponse: string): Boolean;
var
  Handler: TAutomationCommandHandler;
begin
  Result := False;
  if (FExtraCommandHandlers <> nil) and
     FExtraCommandHandlers.TryGetValue(LowerCase(Cmd), Handler) then
  begin
    AResponse := Handler(ReqId, Target, J);
    Result := True;
  end;
end;

{ ── Fixture 注册 ── }

class function TTestFixture.Create(ASetup: TFixtureSetup; ATearDown: TFixtureTeardown): TTestFixture;
begin
  Result.Setup := ASetup;
  Result.TearDown := ATearDown;
end;

class procedure TAutomationProcessorBase.RegisterFixture(const AName: string;
  ASetup: TFixtureSetup; ATearDown: TFixtureTeardown);
begin
  if FFixtures = nil then
    FFixtures := TDictionary<string, TTestFixture>.Create;
  FFixtures.AddOrSetValue(AName, TTestFixture.Create(ASetup, ATearDown));
end;

class procedure TAutomationProcessorBase.UnregisterFixture(const AName: string);
begin
  if (AName <> '') and (FFixtures <> nil) then
    FFixtures.Remove(AName);
end;

class function TAutomationProcessorBase.GetFixture(
  const AName: string): TTestFixture;
begin
  if (FFixtures <> nil) and FFixtures.TryGetValue(AName, Result) then
    Exit;
  Result.Setup := nil;
  Result.TearDown := nil;
end;

class procedure TAutomationProcessorBase.RegisterTestClass(AClass: TClass;
  const AName: string);
var
  Key: string;
begin
  if AClass = nil then
    Exit;
  Key := AName;
  if Key = '' then
    Key := AClass.ClassName;
  if FTestClasses = nil then
    FTestClasses := TDictionary<string, TClass>.Create;
  FTestClasses.AddOrSetValue(Key, AClass);
end;

class procedure TAutomationProcessorBase.UnregisterTestClass(
  const AName: string);
begin
  if (AName <> '') and (FTestClasses <> nil) then
    FTestClasses.Remove(AName);
end;

class function TAutomationProcessorBase.GetTestClass(
  const AName: string): TClass;
begin
  Result := nil;
  if FTestClasses <> nil then
    FTestClasses.TryGetValue(AName, Result);
end;
constructor TAutomationProcessorBase.Create(const APipeName: string);
begin
  inherited Create(True);
  FPipeName := APipeName;
  FMsgWnd := AllocateHWnd(WndProc);
  FAsyncResults := TDictionary<string, TAsyncResultRec>.Create;
  FAsyncQueue := TList<string>.Create;
  FTransport := CreateTransport;
  if FTransport <> nil then
    FTransport.Open(FPipeName);
  InitializeCriticalSection(FAsyncQueueCS);
  InitializeCriticalSection(FAsyncResultsCS);
  FreeOnTerminate := False;
end;

procedure TAutomationProcessorBase.Stop;
begin
  Terminate;
  if FTransport <> nil then
    FTransport.Wake;
end;

destructor TAutomationProcessorBase.Destroy;
begin
  Stop;
  WaitFor;
  DeleteRegFile;
  if FMsgWnd <> 0 then begin
    DeallocateHWnd(FMsgWnd);
    FMsgWnd := 0;
  end;
  FAsyncQueue.Free;
  FAsyncResults.Free;
  FTransport := nil;
  DeleteCriticalSection(FAsyncQueueCS);
  DeleteCriticalSection(FAsyncResultsCS);
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

procedure TAutomationProcessorBase.WriteRegFile(const AStatus: string; AErrorCode: DWORD);
var
  TempDir: array[0..MAX_PATH] of Char;
  AppPath: array[0..MAX_PATH] of Char;
  PID: DWORD;
  RegObj: TJSONObject;
  UTF8NoBom: TEncoding;
begin
  GetTempPath(MAX_PATH, TempDir);
  PID := GetCurrentProcessId;
  GetModuleFileName(0, AppPath, MAX_PATH);

  if FRegFilePath = '' then
    FRegFilePath := Format('%sdaofy-rtti-%d.json', [TempDir, PID]);

  UTF8NoBom := TEncoding.GetEncoding(CP_UTF8);
  RegObj := TJSONObject.Create;
  try
    // 优先用传输层实际地址（Accept 后可能派生为含 PID 的管道名/套接字路径）
    if (FTransport <> nil) and (FTransport.GetTransportAddress <> '') then
      RegObj.AddPair('pipe', TJSONString.Create(FTransport.GetTransportAddress))
    else
      RegObj.AddPair('pipe', TJSONString.Create(FPipeName));
    RegObj.AddPair('pid', TJSONNumber.Create(PID));
    RegObj.AddPair('name', TJSONString.Create(ExtractFileName(AppPath)));
    RegObj.AddPair('timestamp', TJSONNumber.Create(Now * 86400));
    RegObj.AddPair('status', TJSONString.Create(AStatus));
    RegObj.AddPair('error', TJSONNumber.Create(AErrorCode));

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
      System.SysUtils.DeleteFile(FRegFilePath);
    FRegFilePath := '';
  end;
end;

{ ── 传输层线程 ── }

procedure TAutomationProcessorBase.Execute;

  procedure FlushAsyncResults;
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
      if FTransport <> nil then
        FTransport.SendResponse(S);
  end;

var
  Req, Resp, ReqId, Cmd: string;
begin
  try
    while not Terminated do begin
      // 已由构造函数 Open(address)，此处直接监听连接
      if FTransport = nil then begin
        Sleep(500);
        Continue;
      end;

      // ── 等待客户端连接 ──
      if not FTransport.Accept(INFINITE) then begin
        WriteRegFile('accept_failed', 0);
        Sleep(500);
        Continue;
      end;
      WriteRegFile('connected', 0);

      // ── 请求处理循环 ──
      while not Terminated do begin
        case FTransport.WaitForRequest(ASYNC_TTL) of
          twRequest: begin
            if not FTransport.ReadRequest(Req) then
              Break; // 连接断开

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
                  Resp := WriteResp(ReqId, 'ack', '');
                end else
                  Resp := WriteResp(ReqId, 'err', 'alloc_failed');
              end else begin
                var P := PWideChar(GlobalAlloc(GMEM_FIXED,
                  (Length(Req) + 1) * SizeOf(WideChar)));
                if P <> nil then begin
                  Move(PWideChar(Req)^, P^, (Length(Req) + 1) * SizeOf(WideChar));
                  SendMessage(FMsgWnd, WM_DAOFY_CMD, WPARAM(P), 0);
                  Resp := FLastResp;
                end else
                  Resp := WriteResp(ReqId, 'err', 'alloc_failed');
              end;
              FTransport.SendResponse(Resp);
            end;
          end;

          twWake: begin
            // ── 异步结果就绪（等待 peekresult 取回）──
          end;

          twTimeout: begin
            // ── 超时，清理过期异步结果 ──
            var NowTick := GetTickCount;
            var ExpiredList: TList<string>;
            ExpiredList := TList<string>.Create;
            try
              EnterCriticalSection(FAsyncResultsCS);
              try
                for var K in FAsyncResults.Keys do
                  if NowTick - FAsyncResults[K].Tick > ASYNC_TTL then
                    ExpiredList.Add(K);
                for var K in ExpiredList do
                  FAsyncResults.Remove(K);
              finally
                LeaveCriticalSection(FAsyncResultsCS);
              end;
            finally
              ExpiredList.Free;
            end;
          end;

          twError: begin
            Break;
          end;
        end;
      end;

      // 断开连接，等待下次连接
      FTransport.Disconnect;
    end;
  finally
    DeleteRegFile;
  end;
end;

{$IFDEF MSWINDOWS}
function TAutomationProcessorBase.CreateTransport: IAutomationTransport;
begin
  Result := TNamedPipeTransport.Create;
end;
{$ELSE}
function TAutomationProcessorBase.CreateTransport: IAutomationTransport;
begin
  Result := TUnixSocketTransport.Create;
end;
{$ENDIF}

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
      try
        CmdStr := string(P);
        Cmd := GetCmd(CmdStr);
        try
          FLastResp := ExecCmd(CmdStr);
        except
          on E: Exception do
            FLastResp := WriteResp(GetReqId(CmdStr), 'err', E.Message);
        end;
        // 异步命令完成后存结果，供 getresult 取回
        if IsAsyncCmd(Cmd) then begin
          RId := GetReqId(CmdStr);
          if RId <> '' then begin
            var AR: TAsyncResultRec;
            AR.Resp := FLastResp;
            AR.Tick := GetTickCount;
            EnterCriticalSection(FAsyncResultsCS);
            try
              FAsyncResults.AddOrSetValue(RId, AR);
            finally
              LeaveCriticalSection(FAsyncResultsCS);
            end;
            EnterCriticalSection(FAsyncQueueCS);
            try
              FAsyncQueue.Add(FLastResp);
            finally
              LeaveCriticalSection(FAsyncQueueCS);
            end;
            if FTransport <> nil then
              FTransport.Wake;
          end;
        end;
      finally
        GlobalFree(Winapi.Windows.HGLOBAL(Msg.WParam));
      end;
    end;
    Msg.Result := 0;
  end else
    Msg.Result := DefWindowProc(FMsgWnd, Msg.Msg, Msg.WParam, Msg.LParam);
end;

{ ── ExecCmd：所有命令的统一入口（运行在主线程）── }

function TAutomationProcessorBase.ExecCmd(const AReq: string): string;
var
  J: TJSONObject;
  Cmd, ReqId, Target, ExtraResp: string;
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
        Result := WriteResp(ReqId, 'ok', DoMsgScan);
      end

      else if Cmd = 'msgclick' then begin
        Result := WriteResp(ReqId, 'ok', DoMsgClick(Target));
      end

      else if Cmd = 'msgclose' then begin
        var hMsgWnd: Winapi.Windows.HWND;
        hMsgWnd := FindProcessDialog(0);
        while hMsgWnd <> 0 do begin
          GetWindowTextW(hMsgWnd, Buf, 256);
          if (Target = '') or (Pos(Target, string(Buf)) > 0) then begin
            SendMessage(hMsgWnd, WM_CLOSE, 0, 0);
            Break;
          end;
          hMsgWnd := FindProcessDialog(hMsgWnd);
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
        Result := HandleRInsp(ReqId, Target,
          GetJSONStr(J, 'visibility', 'public,published'))

      else if Cmd = 'rcall' then
        Result := HandleRCall(ReqId, Target, GetJSONStr(J, 'method', ''),
          GetJSONStr(J, 'params', ''),
          GetJSONStr(J, 'visibility', 'public,published'))

      else if Cmd = 'run_tests' then begin
        var TestsArr := J.Values['tests'] as TJSONArray;
        if TestsArr = nil then
          Result := WriteResp(ReqId, 'err', 'no tests array')
        else
          Result := HandleRunTests(ReqId, TestsArr);
      end

      else if Cmd = 'rtti_discover' then
        Result := HandleRttiDiscover(ReqId, Target)

      else if Cmd = 'waitfor' then
        Result := HandleCmdWaitFor(ReqId, Target, GetJSONStr(J, 'prop', ''),
          GetJSONStr(J, 'value', ''),
          StrToIntDef(GetJSONStr(J, 'timeout', '5000'), 5000),
          StrToIntDef(GetJSONStr(J, 'interval', '100'), 100))

      else if Cmd = 'key' then
        Result := HandleCmdKey(ReqId, Target, GetJSONStr(J, 'key', ''))

      else if Cmd = 'textbounds' then
        Result := HandleCmdTextBounds(ReqId, Target, GetJSONStr(J, 'text', ''),
          GetJSONStr(J, 'mode', 'auto'),
          GetJSONStr(J, 'include_invisible', 'false') = 'true')

      else if Cmd = 'peekresult' then begin
        var AR: TAsyncResultRec;
        EnterCriticalSection(FAsyncResultsCS);
        try
          if FAsyncResults.TryGetValue(Target, AR) then begin
            FAsyncResults.Remove(Target);
            Result := AR.Resp;
          end else
            Result := WriteResp(ReqId, 'err', 'NR:' + Target);
        finally
          LeaveCriticalSection(FAsyncResultsCS);
        end;
      end

      else if Cmd = 'listwnd' then
        Result := HandleCmdListWnd(ReqId)

      else if TryHandleExtraCommand(Cmd, ReqId, Target, J, ExtraResp) then
        Result := ExtraResp

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

class function TAutomationProcessorBase.FindProcessDialog(AStartAfter: HWND): HWND;
var
  WindowPID: DWORD;
begin
  Result := FindWindowExW(0, AStartAfter, '#32770', nil);
  while Result <> 0 do begin
    WindowPID := 0;
    GetWindowThreadProcessId(Result, @WindowPID);
    if WindowPID = GetCurrentProcessId then
      Exit;
    Result := FindWindowExW(0, Result, '#32770', nil);
  end;
end;

{ ── MessageBox 扫描/点击（纯 Win32 API，框架无关）── }

function TAutomationProcessorBase.DoMsgScan: string;
var
  Root: TJSONObject;
  Buttons: TJSONArray;
  hDlg: HWND;
  Buf: array[0..511] of Char;
  TextValue: string;


  procedure ScanChildren(AParent: HWND);
  var
    hChild: HWND;
    ClassBuf: array[0..255] of Char;
    Txt: string;
  begin
    hChild := FindWindowExW(AParent, 0, nil, nil);
    while hChild <> 0 do begin
      FillChar(ClassBuf, SizeOf(ClassBuf), 0);
      GetClassNameW(hChild, ClassBuf, 255);
      FillChar(Buf, SizeOf(Buf), 0);
      GetWindowTextW(hChild, Buf, 511);
      Txt := Trim(string(Buf));
      if SameText(string(ClassBuf), 'Static') and (Txt <> '') then begin
        if TextValue <> '' then
          TextValue := TextValue + sLineBreak;
        TextValue := TextValue + Txt;
      end else if SameText(string(ClassBuf), 'Button') and (Txt <> '') then
        Buttons.AddElement(TJSONString.Create(Txt));
      ScanChildren(hChild);
      hChild := FindWindowExW(AParent, hChild, nil, nil);
    end;
  end;
begin
  if FSSDir = '' then Exit('NODIR');
  hDlg := FindProcessDialog(0);
  if hDlg = 0 then Exit('NOD');

  Root := TJSONObject.Create;
  try
    FillChar(Buf, SizeOf(Buf), 0);
    GetWindowTextW(hDlg, Buf, 511);
    Root.AddPair('title', string(Buf));
    Root.AddPair('type', 'msgbox');
    Root.AddPair('hWnd', IntToStr(hDlg));

    Buttons := TJSONArray.Create;
    TextValue := '';
    ScanChildren(hDlg);
    Root.AddPair('text', TextValue);
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
  ID: Integer;
  TargetText: string;


  function FindButton(AParent: HWND): HWND;
  var
    hChild, hFound: HWND;
    ClassBuf: array[0..255] of Char;
    Buf: array[0..255] of Char;
    Txt: string;
  begin
    Result := 0;
    hChild := FindWindowExW(AParent, 0, nil, nil);
    while hChild <> 0 do begin
      FillChar(ClassBuf, SizeOf(ClassBuf), 0);
      GetClassNameW(hChild, ClassBuf, 255);
      if SameText(string(ClassBuf), 'Button') then begin
        FillChar(Buf, SizeOf(Buf), 0);
        GetWindowTextW(hChild, Buf, 255);
        Txt := StringReplace(LowerCase(Trim(string(Buf))), '&', '', [rfReplaceAll]);
        if (TargetText <> '') and (Txt <> '') and
           ((Txt = TargetText) or (Pos(TargetText, Txt) > 0) or (Pos(Txt, TargetText) > 0)) then
          Exit(hChild);
      end;
      hFound := FindButton(hChild);
      if hFound <> 0 then
        Exit(hFound);
      hChild := FindWindowExW(AParent, hChild, nil, nil);
    end;
  end;
begin
  hDlg := FindProcessDialog(0);
  if hDlg = 0 then Exit('NOD');

  ID := BtnID(Param);
  if ID > 0 then begin
    SendMessage(hDlg, WM_COMMAND, ID, 0);
    Exit('OK');
  end;

  TargetText := StringReplace(LowerCase(Trim(Param)), '&', '', [rfReplaceAll]);
  hBtn := FindButton(hDlg);
  if hBtn <> 0 then begin
    SendMessage(hBtn, BM_CLICK, 0, 0);
    Exit('OK');
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
  WaitResult: DWORD;
  Msg: TMsg;
  EmptyHandles: THandle;
begin
  Result := WriteResp(ReqId, 'err', 'NF:' + Target);

  // MsgWaitForMultipleObjects 轮询，同时处理消息避免阻塞消息泵。
  // TRttiContext 提到循环外，避免每轮重复创建。
  EmptyHandles := 0;
  StartTime := GetTickCount;
  Ctx := TRttiContext.Create;
  try
    while GetTickCount - StartTime < UInt64(TimeoutMs) do begin
      Ctrl := FindNamedControl(Target);
      if Ctrl = nil then begin
        WaitResult := MsgWaitForMultipleObjects(0, EmptyHandles, False, IntervalMs, QS_ALLINPUT);
        if WaitResult = WAIT_OBJECT_0 then begin
          while PeekMessage(Msg, 0, 0, 0, PM_REMOVE) do begin
            TranslateMessage(Msg);
            DispatchMessage(Msg);
          end;
        end;
        Continue;
      end;

      Parts := Prop.Split(['.']);
      if Length(Parts) = 0 then
        Exit(WriteResp(ReqId, 'err', 'no property'));

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

      // 两轮 RTTI 检查之间同样用 MsgWaitForMultipleObjects 等待
      WaitResult := MsgWaitForMultipleObjects(0, EmptyHandles, False, IntervalMs, QS_ALLINPUT);
      if WaitResult = WAIT_OBJECT_0 then begin
        while PeekMessage(Msg, 0, 0, 0, PM_REMOVE) do begin
          TranslateMessage(Msg);
          DispatchMessage(Msg);
        end;
      end;
    end;
  finally
    Ctx.Free;
  end;

  Result := WriteResp(ReqId, 'err', 'TIMEOUT:' + CurrentValue);
end;

{ ── RTTI 发现 ── }

function TAutomationProcessorBase.GetRttiClasses: TArray<TClass>;
begin
  if FTestClasses <> nil then
    Result := FTestClasses.Values.ToArray
  else
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

{ ── run_tests 批量测试 ── }

function TAutomationProcessorBase.HandleRunTests(const ReqId: string;
  Tests: TJSONArray): string;

  function IsVisibilityAllowed(const AVisibility: TMemberVisibility;
    const AFilter: string): Boolean;
  var
    VisSet: set of TMemberVisibility;
    VisItem: string;
  begin
    VisSet := [mvPublic, mvPublished];
    if AFilter <> '' then
    begin
      VisSet := [];
      for VisItem in AFilter.Split([',']) do
      begin
        if SameText(VisItem.Trim, 'private') then
          Include(VisSet, mvPrivate)
        else if SameText(VisItem.Trim, 'protected') then
          Include(VisSet, mvProtected)
        else if SameText(VisItem.Trim, 'public') then
          Include(VisSet, mvPublic)
        else if SameText(VisItem.Trim, 'published') then
          Include(VisSet, mvPublished)
        else if SameText(VisItem.Trim, 'all') then
          VisSet := [mvPrivate, mvProtected, mvPublic, mvPublished];
      end;
    end;
    Result := AVisibility in VisSet;
  end;

  function TryJSONToValue(const AJSON: TJSONValue; const AType: TRttiType;
    out AValue: TValue; out AError: string): Boolean;
  var
    OrdinalValue: Int64;
    FloatValue: Double;
    EnumValue: Integer;
    TextValue: string;
    FormatSettings: TFormatSettings;
  begin
    Result := False;
    AValue := TValue.Empty;
    AError := '';
    if (AJSON = nil) or (AType = nil) then
    begin
      AError := 'missing parameter value or RTTI type';
      Exit;
    end;

    if AJSON is TJSONNull then
    begin
      if AType.TypeKind = tkClass then
      begin
        try
          AValue := TValue.From<TObject>(nil).Cast(AType.Handle);
          Exit(True);
        except
          on E: Exception do
            AError := E.Message;
        end;
      end else
        AError := 'null is only supported for object parameters';
      Exit;
    end;

    TextValue := AJSON.Value;
    try
      case AType.TypeKind of
        tkInteger, tkInt64:
          begin
            if not TryStrToInt64(TextValue, OrdinalValue) then
            begin
              AError := 'expected integer for ' + AType.Name;
              Exit;
            end;
            AValue := TValue.FromOrdinal(AType.Handle, OrdinalValue);
          end;
        tkEnumeration:
          begin
            if SameText(AType.Name, 'Boolean') or
               SameText(AType.Name, 'ByteBool') or
               SameText(AType.Name, 'WordBool') or
               SameText(AType.Name, 'LongBool') then
            begin
              if SameText(TextValue, 'true') then
                OrdinalValue := 1
              else if SameText(TextValue, 'false') then
                OrdinalValue := 0
              else
              begin
                AError := 'expected boolean for ' + AType.Name;
                Exit;
              end;
            end else
            begin
              EnumValue := GetEnumValue(AType.Handle, TextValue);
              if EnumValue < 0 then
              begin
                AError := 'invalid ' + AType.Name + ' value: ' + TextValue;
                Exit;
              end;
              OrdinalValue := EnumValue;
            end;
            AValue := TValue.FromOrdinal(AType.Handle, OrdinalValue);
          end;
        tkFloat:
          begin
            FormatSettings := TFormatSettings.Create;
            FormatSettings.DecimalSeparator := '.';
            if not TryStrToFloat(TextValue, FloatValue, FormatSettings) then
            begin
              AError := 'expected number for ' + AType.Name;
              Exit;
            end;
            AValue := TValue.From<Double>(FloatValue);
            if AType.Handle <> TypeInfo(Double) then
              AValue := AValue.Cast(AType.Handle);
          end;
        tkString, tkLString, tkWString, tkUString:
          begin
            if not (AJSON is TJSONString) then
            begin
              AError := 'expected string for ' + AType.Name;
              Exit;
            end;
            AValue := TValue.From<string>(TextValue);
            if AType.Handle <> TypeInfo(string) then
              AValue := AValue.Cast(AType.Handle);
          end;
        tkChar, tkWChar:
          begin
            if Length(TextValue) <> 1 then
            begin
              AError := 'expected one character for ' + AType.Name;
              Exit;
            end;
            AValue := TValue.FromOrdinal(AType.Handle, Ord(TextValue[1]));
          end;
      else
        AError := 'unsupported parameter type: ' + AType.Name;
        Exit;
      end;
      Result := True;
    except
      on E: Exception do
        AError := E.Message;
    end;
  end;

  function TryBindMethod(const AType: TRttiType; const AName,
    AVisibility: string; const AParams: TJSONArray; out AMethod: TRttiMethod;
    out AValues: TArray<TValue>; out AError: string): Boolean;

    function HaveSameSignature(const ALeft, ARight: TRttiMethod): Boolean;
    var
      LeftParameters, RightParameters: TArray<TRttiParameter>;
      Index: Integer;
    begin
      Result := ALeft.MethodKind = ARight.MethodKind;
      if not Result then
        Exit;
      LeftParameters := ALeft.GetParameters;
      RightParameters := ARight.GetParameters;
      Result := Length(LeftParameters) = Length(RightParameters);
      if not Result then
        Exit;
      for Index := 0 to Length(LeftParameters) - 1 do
        if LeftParameters[Index].ParamType.Handle <>
           RightParameters[Index].ParamType.Handle then
          Exit(False);
    end;

    function IsDeclaredInMoreDerivedType(const ALeft,
      ARight: TRttiMethod): Boolean;
    var
      LeftClass, RightClass: TClass;
    begin
      Result := False;
      if not (ALeft.Parent is TRttiInstanceType) or
         not (ARight.Parent is TRttiInstanceType) then
        Exit;
      LeftClass := TRttiInstanceType(ALeft.Parent).MetaclassType;
      RightClass := TRttiInstanceType(ARight.Parent).MetaclassType;
      Result := (LeftClass <> RightClass) and LeftClass.InheritsFrom(RightClass);
    end;

  var
    Candidate: TRttiMethod;
    CandidateValues: TArray<TValue>;
    MatchedMethods: TArray<TRttiMethod>;
    MatchedValues: array of TArray<TValue>;
    Parameters: TArray<TRttiParameter>;
    ParamCount, ParamIndex, MatchCount, MatchIndex: Integer;
    ParamError: string;
    CanUse: Boolean;
  begin
    Result := False;
    AMethod := nil;
    SetLength(AValues, 0);
    AError := '';
    ParamCount := 0;
    if AParams <> nil then
      ParamCount := AParams.Count;
    MatchCount := 0;

    for Candidate in AType.GetMethods do
    begin
      if not SameText(Candidate.Name, AName) or
         not IsVisibilityAllowed(Candidate.Visibility, AVisibility) or
         (Candidate.MethodKind = mkDestructor) then
        Continue;

      Parameters := Candidate.GetParameters;
      if Length(Parameters) <> ParamCount then
        Continue;

      SetLength(CandidateValues, ParamCount);
      ParamError := '';
      CanUse := True;
      for ParamIndex := 0 to ParamCount - 1 do
      begin
        if (Parameters[ParamIndex].Flags * [pfVar, pfOut]) <> [] then
        begin
          ParamError := 'var/out parameters are not supported: ' +
            Parameters[ParamIndex].Name;
          CanUse := False;
          Break;
        end;
        if not TryJSONToValue(AParams.Items[ParamIndex],
          Parameters[ParamIndex].ParamType, CandidateValues[ParamIndex],
          ParamError) then
        begin
          CanUse := False;
          Break;
        end;
      end;

      if CanUse then
      begin
        MatchIndex := -1;
        for ParamIndex := 0 to MatchCount - 1 do
          if HaveSameSignature(MatchedMethods[ParamIndex], Candidate) then
          begin
            MatchIndex := ParamIndex;
            Break;
          end;

        if MatchIndex >= 0 then
        begin
          // RTTI includes inherited declarations; keep the nearest declaration.
          if IsDeclaredInMoreDerivedType(Candidate,
            MatchedMethods[MatchIndex]) then
          begin
            MatchedMethods[MatchIndex] := Candidate;
            MatchedValues[MatchIndex] :=
              System.Copy(CandidateValues, 0, Length(CandidateValues));
          end;
        end else
        begin
          SetLength(MatchedMethods, MatchCount + 1);
          SetLength(MatchedValues, MatchCount + 1);
          MatchedMethods[MatchCount] := Candidate;
          MatchedValues[MatchCount] :=
            System.Copy(CandidateValues, 0, Length(CandidateValues));
          Inc(MatchCount);
        end;
      end else if AError = '' then
        AError := ParamError;
    end;

    if MatchCount = 1 then
    begin
      AMethod := MatchedMethods[0];
      AValues := MatchedValues[0];
      Exit(True);
    end;
    if MatchCount > 1 then
      AError := 'ambiguous overload: ' + AName
    else if AError = '' then
      AError := 'no compatible method: ' + AName;
  end;

  function GetArrayField(const AObject: TJSONObject; const AName: string;
    out AArray: TJSONArray; out AOwnsArray: Boolean;
    out AError: string): Boolean;
  var
    JSONValue: TJSONValue;
    ParsedValue: TJSONValue;
  begin
    Result := False;
    AArray := nil;
    AOwnsArray := False;
    AError := '';
    JSONValue := AObject.Values[AName];
    if JSONValue = nil then
      Exit(True);
    if JSONValue is TJSONArray then
    begin
      AArray := TJSONArray(JSONValue);
      Exit(True);
    end;
    if JSONValue is TJSONString then
    begin
      ParsedValue := TJSONObject.ParseJSONValue(JSONValue.Value);
      if ParsedValue is TJSONArray then
      begin
        AArray := TJSONArray(ParsedValue);
        AOwnsArray := True;
        Exit(True);
      end;
      ParsedValue.Free;
    end;
    AError := AName + ' must be a JSON array';
  end;

  procedure SetStatus(const AObject: TJSONObject; const AStatus: string);
  var
    Pair: TJSONPair;
  begin
    Pair := AObject.RemovePair('status');
    Pair.Free;
    AObject.AddPair('status', TJSONString.Create(AStatus));
  end;

var
  Root, TestObj, ResultObj: TJSONObject;
  Results: TJSONArray;
  i: Integer;
  Target, MethodName, ClassName, VisibilityPerTest: string;
  Expected, ExpectedException, ExpectedMessage, Phase, BindError,
    ArrayError: string;
  Obj: TObject;
  RegisteredClass: TClass;
  Ctx: TRttiContext;
  RType: TRttiType;
  MethodRtti: TRttiMethod;
  ParamArray, CtorParamArray: TJSONArray;
  ParamValues, CtorParamValues: TArray<TValue>;
  OwnsParamArray, OwnsCtorParamArray: Boolean;
  StartTick, ElapsedMs: UInt64;
  RttiResult: TValue;
  OwnsObj, FixtureReady: Boolean;
  Fixture: TTestFixture;
  FixtureValue: TValue;
  ExpectedValue, StatusValue: TJSONValue;
  PassedCount, FailedCount, ErrorCount: Integer;
begin
  Root := TJSONObject.Create;
  Results := TJSONArray.Create;
  Ctx := TRttiContext.Create;
  PassedCount := 0;
  FailedCount := 0;
  ErrorCount := 0;
  try
    for i := 0 to Tests.Count - 1 do
    begin
      ResultObj := TJSONObject.Create;
      ResultObj.AddPair('index', TJSONNumber.Create(i));
      Obj := nil;
      OwnsObj := False;
      FixtureReady := False;
      Fixture.Setup := nil;
      Fixture.TearDown := nil;
      FixtureValue := TValue.Empty;
      StartTick := 0;
      Phase := 'prepare';

      if not (Tests.Items[i] is TJSONObject) then
      begin
        ResultObj.AddPair('status', 'error');
        ResultObj.AddPair('phase', Phase);
        ResultObj.AddPair('error', 'test item must be an object');
        Results.AddElement(ResultObj);
        Inc(ErrorCount);
        Continue;
      end;

      TestObj := TJSONObject(Tests.Items[i]);
      Target := GetJSONStr(TestObj, 'target', '');
      ClassName := GetJSONStr(TestObj, 'className', '');
      MethodName := GetJSONStr(TestObj, 'method', '');
      VisibilityPerTest := GetJSONStr(TestObj, 'visibility',
        'public,published');
      ExpectedException := GetJSONStr(TestObj, 'expected_exception', '');
      ExpectedMessage := GetJSONStr(TestObj, 'expected_message', '');
      ExpectedValue := TestObj.Values['expected'];
      if ExpectedValue <> nil then
        Expected := ExpectedValue.Value
      else
        Expected := '';

      ResultObj.AddPair('method', MethodName);
      if TestObj.Values['id'] <> nil then
        ResultObj.AddPair('id', GetJSONStr(TestObj, 'id', ''));
      if TestObj.Values['name'] <> nil then
        ResultObj.AddPair('name', GetJSONStr(TestObj, 'name', ''));

      try
        if (Target = '') = (ClassName = '') then
          raise Exception.Create(
            'exactly one of target or className must be specified');
        if MethodName = '' then
          raise Exception.Create('method is required');

        if ClassName <> '' then
        begin
          ResultObj.AddPair('className', ClassName);
          Fixture := GetFixture(ClassName);
          if Fixture.Setup <> nil then
          begin
            Phase := 'setup';
            FixtureValue := Fixture.Setup();
            FixtureReady := True;
            if FixtureValue.IsObject then
            begin
              Obj := FixtureValue.AsObject;
              if Obj = nil then
                raise Exception.Create('fixture setup returned nil object');
              RType := Ctx.GetType(Obj.ClassType);
            end else
            begin
              if FixtureValue.TypeInfo = nil then
                raise Exception.Create('fixture setup returned an empty value');
              RType := Ctx.GetType(FixtureValue.TypeInfo);
            end;
          end else
          begin
            RegisteredClass := GetTestClass(ClassName);
            if RegisteredClass <> nil then
              RType := Ctx.GetType(RegisteredClass)
            else
            begin
              RType := Ctx.FindType(ClassName);
              if (RType = nil) or not RType.IsInstance then
              begin
                try
                  RType := Ctx.GetType(FindClass(ClassName));
                except
                  on E: Exception do
                    raise Exception.Create('class not found: ' + ClassName);
                end;
              end;
            end;
            if not GetArrayField(TestObj, 'constructor_params',
              CtorParamArray, OwnsCtorParamArray, ArrayError) then
              raise Exception.Create(ArrayError);
            try
              if not TryBindMethod(RType, 'Create',
                'public,published', CtorParamArray, MethodRtti,
                CtorParamValues, BindError) then
                raise Exception.Create(BindError);
              Obj := MethodRtti.Invoke(RType.AsInstance.MetaclassType,
                CtorParamValues).AsObject;
            finally
              if OwnsCtorParamArray then
                CtorParamArray.Free;
            end;
            if Obj = nil then
              raise Exception.Create('constructor returned nil');
            OwnsObj := True;
            RType := Ctx.GetType(Obj.ClassType);
          end;
        end else
        begin
          ResultObj.AddPair('target', Target);
          Obj := FindNamedControl(Target);
          if Obj = nil then
            raise Exception.Create('target not found: ' + Target);
          RType := Ctx.GetType(Obj.ClassType);
        end;

        if not GetArrayField(TestObj, 'params', ParamArray,
          OwnsParamArray, ArrayError) then
          raise Exception.Create(ArrayError);
        try
          if not TryBindMethod(RType, MethodName, VisibilityPerTest,
            ParamArray, MethodRtti, ParamValues, BindError) then
            raise Exception.Create(BindError);
        finally
          if OwnsParamArray then
            ParamArray.Free;
        end;

        Phase := 'test';
        StartTick := GetTickCount64;
        if FixtureReady and not FixtureValue.IsObject then
          RttiResult := MethodRtti.Invoke(FixtureValue, ParamValues)
        else
          RttiResult := MethodRtti.Invoke(Obj, ParamValues);
        ElapsedMs := GetTickCount64 - StartTick;

        ResultObj.AddPair('status', 'ok');
        ResultObj.AddPair('ms', TJSONNumber.Create(Int64(ElapsedMs)));
        if MethodRtti.ReturnType <> nil then
        begin
          if RttiResult.IsObject then
          begin
            if RttiResult.AsObject = nil then
              ResultObj.AddPair('result', '')
            else
              ResultObj.AddPair('result', RttiResult.AsObject.ClassName);
          end else
            ResultObj.AddPair('result', RttiResult.ToString);
        end;

        if ExpectedException <> '' then
        begin
          ResultObj.AddPair('assert', 'fail');
          ResultObj.AddPair('expected_exception', ExpectedException);
          ResultObj.AddPair('actual_exception', '');
          if ExpectedMessage <> '' then
            ResultObj.AddPair('expected_message', ExpectedMessage);
        end else if ExpectedValue <> nil then
        begin
          if RttiResult.ToString = Expected then
            ResultObj.AddPair('assert', 'pass')
          else
          begin
            ResultObj.AddPair('assert', 'fail');
            ResultObj.AddPair('expected', Expected);
            ResultObj.AddPair('actual', RttiResult.ToString);
          end;
        end;
      except
        on E: Exception do
        begin
          if (StartTick <> 0) and (ResultObj.Values['ms'] = nil) then
          begin
            ElapsedMs := GetTickCount64 - StartTick;
            ResultObj.AddPair('ms', TJSONNumber.Create(Int64(ElapsedMs)));
          end;
          if SameText(Phase, 'test') and (ExpectedException <> '') then
          begin
            SetStatus(ResultObj, 'ok');
            ResultObj.AddPair('exception_phase', Phase);
            ResultObj.AddPair('exception_class', E.ClassName);
            ResultObj.AddPair('exception_message', E.Message);
            ResultObj.AddPair('expected_exception', ExpectedException);
            if ExpectedMessage <> '' then
              ResultObj.AddPair('expected_message', ExpectedMessage);
            if SameText(E.ClassName, ExpectedException) and
               ((ExpectedMessage = '') or
                (Pos(LowerCase(ExpectedMessage), LowerCase(E.Message)) > 0)) then
              ResultObj.AddPair('assert', 'pass')
            else
            begin
              ResultObj.AddPair('assert', 'fail');
              ResultObj.AddPair('actual_exception', E.ClassName);
              ResultObj.AddPair('actual_message', E.Message);
            end;
          end else
          begin
            SetStatus(ResultObj, 'error');
            ResultObj.AddPair('phase', Phase);
            ResultObj.AddPair('exception_class', E.ClassName);
            ResultObj.AddPair('error', E.Message);
          end;
        end;
      end;

      try
        Phase := 'teardown';
        if FixtureReady and (Fixture.TearDown <> nil) then
          Fixture.TearDown(FixtureValue)
        else if OwnsObj then
          Obj.Free;
      except
        on E: Exception do
        begin
          SetStatus(ResultObj, 'error');
          ResultObj.AddPair('teardown_exception_class', E.ClassName);
          ResultObj.AddPair('teardown_error', E.Message);
          if ResultObj.Values['error'] = nil then
          begin
            ResultObj.AddPair('phase', Phase);
            ResultObj.AddPair('error', E.Message);
          end;
        end;
      end;

      StatusValue := ResultObj.Values['status'];
      if (StatusValue <> nil) and SameText(StatusValue.Value, 'ok') then
      begin
        if (ResultObj.Values['assert'] <> nil) and
           SameText(ResultObj.Values['assert'].Value, 'fail') then
          Inc(FailedCount)
        else
          Inc(PassedCount);
      end else
        Inc(ErrorCount);
      Results.AddElement(ResultObj);
    end;

    Root.AddPair('results', Results);
    Root.AddPair('total', TJSONNumber.Create(Tests.Count));
    Root.AddPair('passed', TJSONNumber.Create(PassedCount));
    Root.AddPair('failed', TJSONNumber.Create(FailedCount));
    Root.AddPair('errors', TJSONNumber.Create(ErrorCount));
    if (FailedCount = 0) and (ErrorCount = 0) then
      Root.AddPair('suite_status', 'ok')
    else
      Root.AddPair('suite_status', 'failed');
    Result := WriteResp(ReqId, 'ok', Root.ToJSON);
  finally
    Ctx.Free;
    Root.Free;
  end;
end;
function TAutomationProcessorBase.DoDlgFile(const APath,
  ATarget: string): string;
var
  hDlg: HWND;
  hEdit, hBtn: HWND;
  Buf: array[0..511] of Char;
  TargetText: string;
begin
  hDlg := FindProcessDialog(0);
  if hDlg = 0 then Exit('NOD');

  TargetText := StringReplace(LowerCase(ATarget), '&', '', [rfReplaceAll]);

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

  // 用异步 PostMessage 点击按钮，避免路径不存在时 Windows 错误框阻塞自动化管道。
  if SameText(ATarget, 'cancel') then begin
    SendMessageW(hDlg, WM_CLOSE, 0, 0);
    Result := 'OK';
  end else begin
    hBtn := FindWindowExW(hDlg, 0, 'Button', nil);
    while hBtn <> 0 do begin
      FillChar(Buf, SizeOf(Buf), 0);
      GetWindowTextW(hBtn, Buf, 511);
      var Txt := StringReplace(LowerCase(string(Buf)), '&', '', [rfReplaceAll]);
      if (ATarget = '') and ((Pos('open', Txt) > 0) or (Pos('save', Txt) > 0) or
         (Pos(#25153#24320, Txt) > 0) or (Pos(#20445#23384, Txt) > 0)) then begin
        PostMessageW(hBtn, BM_CLICK, 0, 0);
        Exit('OK');
      end;
      if (TargetText <> '') and ((Txt = TargetText) or (Pos(TargetText, Txt) > 0) or
         (Pos(Txt, TargetText) > 0)) then begin
        PostMessageW(hBtn, BM_CLICK, 0, 0);
        Exit('OK');
      end;
      hBtn := FindWindowExW(hDlg, hBtn, 'Button', nil);
    end;
    // 没找到匹配按钮，用默认 IDOK。
    if not SameText(ATarget, 'cancel') then begin
      PostMessageW(hDlg, WM_COMMAND, 1, 0);
      Result := 'OK';
    end else
      Result := 'NF';
  end;
end;

{ ═════════════════════════════════════════════════════════════════════════════
  全局辅助函数
  ═════════════════════════════════════════════════════════════════════════════ }

/// <summary>按可见度过滤查找 RTTI 方法。支持逗号分隔列表：private,protected,public,published,all。</summary>
function FindMethodByVisibility(const AType: TRttiType; const AName, Visibility: string): TRttiMethod;
var
  VisSet: set of TMemberVisibility;
  VisItem: string;
  Candidate: TRttiMethod;
begin
  Result := nil;
  VisSet := [mvPublic, mvPublished];
  if Visibility <> '' then begin
    VisSet := [];
    for VisItem in Visibility.Split([',']) do begin
      var VisLower := VisItem.Trim.ToLower;
      if VisLower = 'private' then Include(VisSet, mvPrivate)
      else if VisLower = 'protected' then Include(VisSet, mvProtected)
      else if VisLower = 'public' then Include(VisSet, mvPublic)
      else if VisLower = 'published' then Include(VisSet, mvPublished)
      else if VisLower = 'all' then VisSet := [mvPrivate, mvProtected, mvPublic, mvPublished];
    end;
  end;
  for Candidate in AType.GetMethods do
    if (Candidate.Name = AName) and (Candidate.Visibility in VisSet) then begin
      Result := Candidate;
      Break;
    end;
end;

initialization

finalization
  TAutomationProcessorBase.FExtraCommandHandlers.Free;
  TAutomationProcessorBase.FFixtures.Free;
  TAutomationProcessorBase.FTestClasses.Free;

end.
