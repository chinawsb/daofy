unit StackTrace;

interface

uses
{$IFDEF FPC}
  Classes,
  SysUtils,
  Generics.Collections,
  ZLib,
  Windows,
  SyncObjs,
  TypInfo,
  Rtti,
  Math,
  MapDataSerializer
{$ELSE}
  System.Classes,
  System.SysUtils,
  System.Generics.Collections,
  System.Generics.Defaults,
  System.JSON,
  System.ZLib,
  Winapi.Windows,
  Winapi.TlHelp32,
  System.TypInfo,
  System.Math,
  System.Rtti,
  MapDataSerializer
{$ENDIF}
      ;

const
{$IFDEF FPC}
  LineBrk = LineEnding;
{$ELSE}
  LineBrk = sLineBreak;
{$ENDIF}
  AddrModeFlat = 3;
  MaxStackFrames = 64;
  SYMOPT_LOAD_LINES = $0010;
  SYMOPT_UNDNAME = $0002;
  SYMOPT_DEFERRED_LOADS = $0004;
  PreferredImageBase = $00400000;
  MapAddrSegShift = $00401000 - PreferredImageBase;

type
  TModuleSymbolTable = record
    ModuleName: string;
    ModuleBase: NativeUInt;
    PreferredBase: NativeUInt;
    NameCache: TDictionary<string, UInt64>;
  end;

  TVarSnapshot = record
    Name: string;
    Value: string;
    TypeInfo: PTypeInfo;
    TypeKind: Byte; // 类型 Kind
    Addr: Pointer; // 变量在栈/寄存器中的地址
    Size: Integer; // 类型长度 (字节数)
    IsRegister: Boolean; // 是否为寄存器优化变量
    function TypeName: string;
  end;

  TFrameSnapshot = record
    Address: NativeUInt;
    FuncName: string;
    SourceInfo: string;
    Params: TArray<TVarSnapshot>;
    Locals: TArray<TVarSnapshot>;
  end;

  TExceptionContext = record
    ExceptionObj: Exception;
    CaptureVariables: Boolean;
    Frames: TArray<TFrameSnapshot>;
  end;

  IExceptionLogger = interface
    ['{5FA6454F-F37C-44E3-9042-EE91EB449DF1}']
    procedure HandleException(const AContext: TExceptionContext);
  end;

  TGlobalVarInfo = record
    Name: string;
    TypeHandle: PTypeInfo;
    Address: Pointer;
  end;

  TReturnAddrEntry = record
    ReturnAddr: Pointer;
    StackSlot: Pointer;
    FrameIndex: Integer;
  end;

  TFunctionExtent = record
    StartAddr: Pointer;
    Size: Integer;
    Found: Boolean;
  end;

  /// <summary>Symbol entry for profile detour integration (Name + runtime Address)</summary>
  TQProfileMapEntry = record
    Name: string;
    Address: Pointer;
  end;

  /// <summary>
  ///  IOverlaySymbolProvider — 叠加符号查询接口。
  ///  由热补丁系统 (PatchManager) 实现, StackTrace 通过它优先查询热补丁
  ///  新增函数的符号名/源文件/行号/函数范围。
  ///  定义在此处而非 PatchManager 中是为了避免循环单元引用。
  /// </summary>
  IOverlaySymbolProvider = interface
    ['{E4D1B3A7-5F2C-4A8B-9D6E-3C1F0A7B8D93}']
    /// <summary>解析地址对应的叠加符号名/源文件/行号。</summary>
    function ResolveOverlaySymbol(VA: NativeUInt; out AName, ASourceFile: string; out ALine: Integer): Boolean;
    /// <summary>获取地址所在的叠加函数范围。</summary>
    function GetOverlayFunctionExtent(Addr: Pointer; out AStartAddr: Pointer; out ASize: Integer): Boolean;
  end;

  TLocalVarExtractor =
      reference to procedure(
          const ASourcePaths: TArray<string>;
          const ASymbols: TArray<TMapSymbol>;
          const ADefines: TArray<string>;
          var ALocalVarData: TArray<TLocalVarEntry>
      );

  TStackTraceManager = class
  private
    type
      PStackInfoData = ^TStackInfoData;

      TStackInfoData = record
        FrameCount: Integer;
        Frames: array[0..MaxStackFrames - 1] of Pointer;
        FrameEBP: array[0..MaxStackFrames - 1] of Pointer;
      end;
  private
    FTokenDict: TArray<string>;
    FTokenData: TArray<Integer>;
    FSymEntries: TArray<TSymbolEntry>;
    FLineEntries: TArray<TLineEntry>;
    FSourcePaths: TArray<string>;
    FMapLoaded: Integer;
    FModuleBase: NativeUInt;
    FPreferredBase: NativeUInt;
    FLocalVarData: TArray<TLocalVarEntry>;
    FDefines: TArray<string>;
    FSymbolCache: TDictionary<NativeUInt, string>;
    FSymNameCache: TDictionary<string, UInt64>; // 符号名 -> 模块 RVA 反向缓存, 延迟构建
    FModuleTables: TArray<TModuleSymbolTable>; // 多模块符号表 (EXE + DLLs)
    FModulesLoaded: Integer; // 0=未加载, 1=已加载
    FOverlayProvider: IOverlaySymbolProvider;
    class function StackInfoStringProc(Info: Pointer): string; static;
    function ParseMapFile(
        const AMapPath: string;
        out ASymbols: TArray<TMapSymbol>;
        out ALines: TArray<TLineInfo>
    ): Boolean;
    procedure TokenizeName(
        const AName: string;
        ATokens: TList<Integer>;
        ADict: TDictionary<string, Integer>;
        AOrdered: TList<string>
    );
    function ExpandSymbolName(ASymIdx: Integer): string;
    procedure TokenizeAndStore(const ASymbols: TArray<TMapSymbol>; const ALines: TArray<TLineInfo>);
    function SerializeSymbols(
        const ASymbols: TArray<TMapSymbol>;
        const ALines: TArray<TLineInfo>;
        const ADefines: TArray<string>
    ): TBytes;
    function DeserializeSymbols(const AData: TBytes): Boolean;
    function TryLoadMapFromResource: Boolean;
    function TryLoadMapFromOverlay: Boolean;
    function TryLoadMapFile: Boolean;
    function WriteMapDataOverlay(
        const AExePath: string;
        const ACompressed: TBytes;
        AProgress: TResourceSerializeProgress
    ): Boolean;
    function ValidatePEImage(const AExePath: string): Boolean;
    procedure StripSourcePaths(var ALines: TArray<TLineInfo>);
    function ResolveFromMap(VA: NativeUInt): string;
    procedure ClearSymbolCache;
    procedure BuildSymbolNameCache;
    function GetModulePreferredBase(hModule: HMODULE): NativeUInt;
    function GetPEFilePreferredBase(const AExePath: string): UInt64;
    procedure EnsureMainModuleBases;
    function MapAddrToRuntimeAddr(AMapAddr: UInt64): NativeUInt;
    function RuntimeAddrToMapAddr(ARuntimeAddr: NativeUInt): UInt64;
    procedure LoadAllModuleSymbols;
    function FindLocalVars(SymIdx: Integer): TArray<TLocalVarInfo>;
    function ReadFunctionPrologue(
        AFuncAddr: Pointer;
        out FrameSize: Integer;
        out RegisterSpill: TArray<SmallInt>
    ): Boolean;
    function ComputeVarOffsets(
        const AVars: TArray<TLocalVarInfo>;
        FrameSize, AParamCount, ACallConv: Integer;
        AIsMethod: Boolean;
        const RegisterSpill: TArray<SmallInt>;
        out Offsets: TArray<SmallInt>
    ): Boolean;
    function ReadStackVarValue(Addr: Pointer; TypeKind: Byte): string;
    function TryGetObjectClassName(Obj: Pointer): string;
    function TryGetStringValue(P: Pointer): string;
    class function GetEnabled: Boolean; static;
    class procedure SetEnabled(const AEnabled: Boolean); static;
  private
    class var
      FCurrent: TStackTraceManager;
      FLogger: IExceptionLogger;
      FCaptureVariables: Boolean;
      FLocalVarExtractor: TLocalVarExtractor;
  protected
    constructor Create; reintroduce;
    procedure InstallHooks; virtual; abstract;
    procedure UninstallHooks; virtual; abstract;
  public
    destructor Destroy; override;
    function WalkStackFromContext(const AContext: TContext): TArray<Pointer>;
    function CompressBytes(const AData: TBytes): TBytes;
    function DecompressBytes(const AData: TBytes): TBytes;
    function EmbedMapData(const AExePath: string; AProgress: TResourceSerializeProgress = nil): Boolean;
    procedure EmbedFinalize(AProgress: TResourceSerializeProgress = nil);
    procedure EnableDefaultLogger;
    function GetGlobalVariables: TArray<TGlobalVarInfo>;
    procedure SetLocalVarData(const AData: TArray<TLocalVarEntry>);
    function GetMapLoadStatus: Integer;
    function GetModuleBaseAddr: NativeUInt;
    function TryResolveSourceLine(VA: NativeUInt; out AFile: string; out ALine: Integer): Boolean;
    class function BuildExceptionContext(AException: Exception; AData: Pointer): TExceptionContext; static;
    class function FormatExceptionContext(const AContext: TExceptionContext): string; static;
    class function GetStackString(Info: Pointer): string; static;
    function GetFrameSnapshot(VA: NativeUInt; AEBP: Pointer): TFrameSnapshot;
    function GetFunctionExtent(Addr: Pointer): TFunctionExtent;
    function ScanReturnAddresses(
        const AContext: TContext;
        const AGuardStart, AGuardEnd: Pointer
    ): TArray<TReturnAddrEntry>;
    function CachedResolveFromMap(VA: NativeUInt): string;
    function ReadFrameFromContext(const AContext: TContext; AFrameIndex: Integer; out AFrame: TFrameSnapshot): Boolean;
    function EnumerateFunctions(AFilter: TFunc<string, Boolean> = nil): TArray<TQProfileMapEntry>;
    /// <summary>按符号名查找运行时地址 (反向解析)。ASLR 已包含。</summary>
    function FindSymbolAddress(const AName: string): Pointer;
    class property Enabled: Boolean read GetEnabled write SetEnabled;
    class property Current: TStackTraceManager read FCurrent;
    class property Logger: IExceptionLogger read FLogger write FLogger;
    class property CaptureVariables: Boolean read FCaptureVariables write FCaptureVariables;
    class property LocalVarExtractor: TLocalVarExtractor read FLocalVarExtractor write FLocalVarExtractor;
    property Defines: TArray<string> read FDefines;
    property OverlayProvider: IOverlaySymbolProvider read FOverlayProvider write FOverlayProvider;
  end;

{$IFNDEF FPC}

  TCallEdge = record
    CallerAddr: NativeUInt;
    CalleeAddr: NativeUInt;
    CallAddr: NativeUInt;
    CallerName: string;
    CalleeName: string;
    CalleeFile: string;
    CalleeLine: Integer;
    CallFile: string;
    CallLine: Integer;
  end;

  TStackSnapshot = record
    Addrs: TArray<NativeUInt>;
    Resolved: TArray<string>;
    ThreadId: Cardinal;
    CapturedAt: TDateTime;
  end;

  TStackTracer = class
  private
    type
      TCallSymbol = record
        Name: string;
        Address: NativeUInt;
      end;
      TEdgeIndex = TDictionary<NativeUInt, TList<Integer>>;
  private
    class var
      FSymbols: TArray<TCallSymbol>;
      FCallEdges: TArray<TCallEdge>;
      FCallerIndex: TEdgeIndex;
      FCalleeIndex: TEdgeIndex;
      FScanned: Boolean;
      FImageBase: NativeUInt;
      FTextStart: NativeUInt;
      FTextSize: NativeUInt;
      FMapLoadError: string;
      FLastError: string;
    class function EnsureSymbols: Boolean; static;
    class function LoadTextRange: Boolean; static;
    class function ResolveSymbolStart(AAddr: NativeUInt): NativeUInt; static;
    class function ResolveSymbolName(AAddr: NativeUInt): string; static;
    class function FindFuncAddr(const AName: string): NativeUInt; static;
    class function FormatCallGraphAddr(AAddr: NativeUInt): string; static;
    class function ResolveRelativeCallTarget(ACallSite: NativeUInt; ARel32: Integer): NativeUInt; static;
    class procedure ClearEdgeIndexes; static;
    class procedure AddEdgeIndex(AIndex: TEdgeIndex; AAddr: NativeUInt; AEdgeIndex: Integer); static;
    class procedure BuildEdgeIndexes; static;
    class procedure ScanCallGraph; static;
  public
    class function ResolveAddr(AAddr: NativeUInt): string; static;
    class function GetCallChain(const AEntryFunc: string; AMaxDepth: Integer = 5): TArray<TCallEdge>; static;
    class function GetCallerChain(const AEntryFunc: string; AMaxDepth: Integer = 5): TArray<TCallEdge>; static;
    class function CallChainToJSON(
        const AChain: TArray<TCallEdge>;
        const ARoot: string = '';
        const ADirection: string = 'callees'
    ): string; static;
    class property MapLoadError: string read FMapLoadError;
    class property LastError: string read FLastError;
  end;

{$ENDIF}

{$IFDEF FPC}

  TStackTraceManagerFPC = class(TStackTraceManager)
  private
    FOldExceptProc: TExceptProc;
    class procedure FPExceptProc(ExceptObject: TObject; ExceptAddr: Pointer; OSException: Boolean); static;
  protected
    procedure InstallHooks; override;
    procedure UninstallHooks; override;
  end;
{$ELSE}

  TStackTraceManagerDelphi = class(TStackTraceManager)
  private
    type
      TGetExceptionStackInfoProc = function(P: System.PExceptionRecord): Pointer;
      TGetStackInfoStringProc = function(Info: Pointer): string;
      TCleanUpStackInfoProc = procedure(Info: Pointer);
      PExceptionPointers = ^TExceptionPointers;
      TExceptionPointers = record
        ExceptionRecord: PExceptionRecord;
        ContextRecord: PContext;
      end;
  private
    FOrigGetExceptionStackInfoProc: TGetExceptionStackInfoProc;
    FOrigGetStackInfoStringProc: TGetStackInfoStringProc;
    FOrigCleanUpStackInfoProc: TCleanUpStackInfoProc;
    FVEHHandle: Pointer;
    class function ExceptionStackInfoProc(P: System.PExceptionRecord): Pointer; static;
    class procedure CleanupStackInfoProc(Info: Pointer); static;
    class function VEHHandler(ExceptionInfo: PExceptionPointers): LongInt; stdcall; static;
    class procedure WriteVEHExceptionLog(ExceptionInfo: PExceptionPointers); static;
  protected
    procedure InstallHooks; override;
    procedure UninstallHooks; override;
  end;
{$ENDIF}

  // ═══════════════════════════════════════════════════════════════════════
  //  运行时类型 (局部变量值快照 + MAPDATA 序列化工具类)
  // ═══════════════════════════════════════════════════════════════════════

  /// <summary>运行时局部变量值 (包含元数据 + 实际值)</summary>
  TLocalVariable = record
    Name: string;
    TypeName: string;
    Size: Integer;
    TypeKind: Byte;
    RawValue: TBytes; // 原始字节
    DisplayValue: string; // 格式化后的可读值
  end;

implementation

{$IFNDEF FPC}

uses
  System.IOUtils,
  System.Win.Registry;

// ─── VEH (Vectored Exception Handler) API ────────
function AddVectoredExceptionHandler(
    FirstFlag: DWORD;
    Handler: Pointer
): Pointer; stdcall; external 'kernel32.dll' name 'AddVectoredExceptionHandler';

function RemoveVectoredExceptionHandler(
    Handle: Pointer
): DWORD; stdcall; external 'kernel32.dll' name 'RemoveVectoredExceptionHandler';

// 线程局部存储：VEH 在展开前捕获的完整栈帧
threadvar
  VEHFrameCount: Integer;
  VEHFrameList: array[0..MaxStackFrames - 1] of Pointer;
  VEHEBPList: array[0..MaxStackFrames - 1] of Pointer;
  VEHDataValid: Boolean;
  VEHLogBusy: Boolean;
  VEHReentrancyGuard: Integer;

procedure AppendLogText(var ABuffer: array of AnsiChar; var AOffset: Integer; const AText: AnsiString);
var
  I: Integer;
begin
  for I := 1 to Length(AText) do begin
    if AOffset >= High(ABuffer) then
      Exit;
    ABuffer[AOffset] := AnsiChar(AText[I]);
    Inc(AOffset);
  end;
end;

procedure AppendLogHex(var ABuffer: array of AnsiChar; var AOffset: Integer; AValue: NativeUInt);
const
  HexChars: array[0..15] of AnsiChar = '0123456789ABCDEF';
var
  I: Integer;
begin
  AppendLogText(ABuffer, AOffset, '0x');
  for I := SizeOf(NativeUInt) * 2 - 1 downto 0 do begin
    if AOffset >= High(ABuffer) then
      Exit;
    ABuffer[AOffset] := HexChars[(AValue shr (I * 4)) and $F];
    Inc(AOffset);
  end;
end;

procedure AppendLogLineBreak(var ABuffer: array of AnsiChar; var AOffset: Integer);
begin
  AppendLogText(ABuffer, AOffset, #13#10);
end;

function BuildVEHLogPath(var APath: array of WideChar): Boolean;
var
  LLen: DWORD;
  LName: PWideChar;
  I: Integer;
  LPos: Integer;
begin
  Result := False;
  if Length(APath) = 0 then
    Exit;
  LLen := GetModuleFileNameW(0, @APath[0], Length(APath));
  if (LLen = 0) or (LLen >= DWORD(Length(APath))) then
    Exit;
  LPos := Integer(LLen);
  for I := Integer(LLen) - 1 downto 0 do begin
    if APath[I] = '\' then begin
      LPos := I + 1;
      Break;
    end;
  end;
  LName := 'veh-exception.log';
  I := 0;
  while LName[I] <> #0 do begin
    if LPos >= Length(APath) - 1 then
      Exit;
    APath[LPos] := LName[I];
    Inc(LPos);
    Inc(I);
  end;
  APath[LPos] := #0;
  Result := True;
end;

{$ENDIF}

{ TVarSnapshot }

function TVarSnapshot.TypeName: string;
begin
  if TypeInfo <> nil then
    Result := string(TypeInfo^.Name)
  else
    Result := '';
end;

type
  TAddress = record
    Offset: ULONG64;
    Segment: Word;
    AddrMode: DWORD;
  end;

  TDefaultExceptionLogger = class(TInterfacedObject, IExceptionLogger)
  private
    procedure HandleException(const AContext: TExceptionContext);
  end;

{$IFDEF FPC}

type
  TZCompressionStream = TCompressionStream;
  TZDecompressionStream = TDecompressionStream;
{$ENDIF}
function RtlCaptureStackBackTrace(
    FramesToSkip: DWORD;
    FramesToCapture: DWORD;
    BackTrace: Pointer;
    BackTraceHash: PDWORD
): DWORD; stdcall; external 'ntdll.dll';

// Resource update API (kernel32)
function BeginUpdateResourceW(
    pFileName: LPCWSTR;
    bDeleteExistingResources: BOOL
): THandle; stdcall; external 'kernel32.dll';
function UpdateResourceW(
    hUpdate: THandle;
    lpType: LPCWSTR;
    lpName: LPCWSTR;
    wLanguage: Word;
    lpData: Pointer;
    cbData: DWORD
): BOOL; stdcall; external 'kernel32.dll';
function EndUpdateResourceW(hUpdate: THandle; fDiscard: BOOL): BOOL; stdcall; external 'kernel32.dll';

function RT_RCDATA_W: PWideChar; inline;
begin
  Result := MakeIntResource(10);
end;

{$IFDEF FPC}

// FPC 模拟 TMonitor — 使用单一全局 TCriticalSection 而非 per-object 锁，
// 所有 TMonitor.Enter/Exit 调用竞争同一把锁。当前代码仅在 TDefaultExceptionLogger
// 的 HandleException 中使用 TMonitor(Self)，单实例场景下不影响正确性。
// 若未来在多对象上使用 TMonitor，需改为 TDictionary<Pointer, TCriticalSection>
// 实现 per-object 细粒度加锁。
type
  TMonitor = record
  private
    class var
      FLock: TCriticalSection;
    class function GetLock: TCriticalSection; static;
  public
    class procedure Enter(AObj: TObject); static;
    class procedure Exit(AObj: TObject); static;
  end;

class function TMonitor.GetLock: TCriticalSection;
begin
  if FLock = nil then
    FLock := TCriticalSection.Create;
  Result := FLock;
end;

class procedure TMonitor.Enter(AObj: TObject);
begin
  GetLock.Enter;
end;

class procedure TMonitor.Exit(AObj: TObject);
begin
  GetLock.Leave;
end;
{$ENDIF}

class function TStackTraceManager.FormatExceptionContext(const AContext: TExceptionContext): string;
var
  I, J: Integer;
begin
  Result := '';
  for I := 0 to High(AContext.Frames) do begin
    if Result <> '' then
      Result := Result + LineBrk;
    Result := Result + Format('  %p %s', [Pointer(AContext.Frames[I].Address), AContext.Frames[I].FuncName]);
    if AContext.Frames[I].SourceInfo <> '' then
      Result := Result + ' ' + AContext.Frames[I].SourceInfo;
    if AContext.CaptureVariables then begin
      for J := 0 to High(AContext.Frames[I].Params) do
        Result := Result + LineBrk + Format('    %s: %s', [AContext.Frames[I].Params[J].Name, AContext.Frames[I].Params[J].Value]);
      for J := 0 to High(AContext.Frames[I].Locals) do
        Result := Result + LineBrk + Format('    %s: %s', [AContext.Frames[I].Locals[J].Name, AContext.Frames[I].Locals[J].Value]);
    end;
  end;
end;

procedure TDefaultExceptionLogger.HandleException(const AContext: TExceptionContext);
var
  AFileName: string;
  AStream: TFileStream;
  ABytes: TBytes;
  LStackText: string;
begin
  if Assigned(AContext.ExceptionObj) then begin
    TMonitor.Enter(Self);
    try
      LStackText := TStackTraceManager.FormatExceptionContext(AContext);
      AFileName := ExtractFilePath(ParamStr(0)) + 'exception.log';
      if FileExists(AFileName) then begin
        AStream := TFileStream.Create(AFileName, fmOpenWrite or fmShareDenyNone);
        AStream.Seek(0, TSeekOrigin.soEnd);
      end
      else begin
        AStream := TFileStream.Create(AFileName, fmCreate);
        AStream.Write(TEncoding.UTF8.GetPreamble[0], 3);
      end;
      try
        ABytes :=
            TEncoding.UTF8.GetBytes(
                Format(
                    '[%s][%d]Exception class %s with Message:%s' + LineBrk + 'Call Stacks:' + LineBrk + '%s' + LineBrk,
                    [
                        FormatDateTime('yyyy-mm-dd hh:nn:ss.zzz', Now),
                        GetCurrentThreadId,
                        AContext.ExceptionObj.ClassName,
                        AContext.ExceptionObj.Message,
                        LStackText
                    ]
                )
            );
        AStream.Write(ABytes[0], Length(ABytes));
      finally
        FreeAndNil(AStream);
      end;
    finally
      TMonitor.Exit(Self);
    end;
  end;
end;

function TStackTraceManager.ParseMapFile(
    const AMapPath: string;
    out ASymbols: TArray<TMapSymbol>;
    out ALines: TArray<TLineInfo>
): Boolean;
const
  MAX_SEGMENTS = 8;
var
  LLines: TStringList;
  I: Integer;
  LLine: string;
  LInPublicsByValue: Boolean;
  LInLineNumbers: Boolean;
  LCurrentSourceFile: string;
  LSyms: TList<TMapSymbol>;
  LLinesInfo: TList<TLineInfo>;
  LSegRvas: array[1..MAX_SEGMENTS] of UInt64;
  LSegCount: Integer;
  LPreferredBase: UInt64;
  LLn: Integer;

  function TryParseHexUInt64(const AText: string; out AValue: UInt64): Boolean;
  var
    I: Integer;
    LDigit: UInt64;
    C: Char;
  begin
    Result := False;
    AValue := 0;
    if AText = '' then
      Exit;

    for I := 1 to Length(AText) do begin
      C := AText[I];
      case C of
        '0'..'9': LDigit := Ord(C) - Ord('0');
        'A'..'F': LDigit := Ord(C) - Ord('A') + 10;
        'a'..'f': LDigit := Ord(C) - Ord('a') + 10;
      else
        Exit;
      end;
      if AValue > (High(UInt64) shr 4) then
        Exit;
      AValue := (AValue shl 4) or LDigit;
    end;

    Result := True;
  end;

  function TrySegmentMapRva(ASegNum: Integer; AOffset: UInt64; out AAddr: UInt64): Boolean;
  begin
    Result := False;
    AAddr := 0;
    if (ASegNum < 1) or (ASegNum > MAX_SEGMENTS) then
      Exit;
    if AOffset > High(UInt64) - LSegRvas[ASegNum] then
      Exit;

    AAddr := LSegRvas[ASegNum] + AOffset;
    Result := True;
  end;
begin
  Result := False;
  ASymbols := nil;
  ALines := nil;

  if not FileExists(AMapPath) then
    Exit;

  LLines := TStringList.Create;
  try
    LLines.LoadFromFile(AMapPath);

    LPreferredBase := GetPEFilePreferredBase(ChangeFileExt(AMapPath, '.exe'));
    FillChar(LSegRvas, SizeOf(LSegRvas), 0);
    LSegCount := 0;
    for I := 0 to 15 do begin
      if I >= LLines.Count then
        Break;
      LLine := Trim(LLines[I]);
      if (Length(LLine) > 20) and (LLine[5] = ':') and (CharInSet(LLine[1], ['0'..'9'])) then begin
        var LSegNum := StrToIntDef('$' + Copy(LLine, 1, 4), 0);
        if (LSegNum < 1) or (LSegNum > MAX_SEGMENTS) then
          Continue;
        var LSpace1 := Pos(' ', LLine);
        if LSpace1 = 0 then
          Continue;
        var LAddrStr := Copy(LLine, 6, LSpace1 - 6);
        var LRem := Trim(Copy(LLine, LSpace1 + 1, MaxInt));
        var LSpace2 := Pos(' ', LRem);
        var LLenToken := LRem;
        if LSpace2 > 0 then
          LLenToken := Copy(LRem, 1, LSpace2 - 1);
        if (Length(LLenToken) > 1) and (LLenToken[Length(LLenToken)] = 'H') then begin
          var LBaseAddr: UInt64;
          if TryParseHexUInt64(LAddrStr, LBaseAddr) then begin
            if (LPreferredBase <> 0) and (LBaseAddr >= LPreferredBase) then
              LSegRvas[LSegNum] := LBaseAddr - LPreferredBase
            else
              LSegRvas[LSegNum] := LBaseAddr;
            if LSegNum > LSegCount then
              LSegCount := LSegNum;
          end;
        end;
      end;
    end;

    LSyms := TList<TMapSymbol>.Create;
    LLinesInfo := TList<TLineInfo>.Create;
    try
      LInPublicsByValue := False;
      LInLineNumbers := False;
      LCurrentSourceFile := '';

      for I := 0 to LLines.Count - 1 do begin
        LLine := Trim(LLines[I]);
        if LLine = '' then
          Continue;

        if LLine.Contains('Publics by Value') then begin
          LInPublicsByValue := True;
          LInLineNumbers := False;
          Continue;
        end;

        if LLine.StartsWith('Line numbers for ') then begin
          LInPublicsByValue := False;
          LInLineNumbers := True;
          var LStart := Pos('(', LLine);
          var LEnd := Pos(')', LLine);
          if (LStart > 0) and (LEnd > LStart) then
            LCurrentSourceFile := Copy(LLine, LStart + 1, LEnd - LStart - 1);
          Continue;
        end;

        if LInPublicsByValue then begin
          if (LLine.StartsWith('0001:')) or (LLine.StartsWith('0002:')) then begin
            var LSpacePos := Pos(' ', LLine);
            if LSpacePos > 0 then begin
              var LOffsetStr := Copy(LLine, 6, LSpacePos - 6);
              var LSymName := Trim(Copy(LLine, LSpacePos + 1, MaxInt));
              if (LOffsetStr <> '') and (LSymName <> '') and not LSymName.StartsWith('_') then begin
                var LOffset: UInt64;
                if TryParseHexUInt64(LOffsetStr, LOffset) then begin
                  var LSegNum := 1;
                  if LLine.StartsWith('0002:') then
                    LSegNum := 2;
                  var LFullAddr: UInt64;
                  if TrySegmentMapRva(LSegNum, LOffset, LFullAddr) then begin
                    var LSym: TMapSymbol;
                    LSym.Addr := LFullAddr;
                    LSym.Name := LSymName;
                    LSyms.Add(LSym);
                  end;
                end;
              end;
            end;
          end;
        end;

        if LInLineNumbers and (LCurrentSourceFile <> '') then begin
          if (LLine <> '') and (LLine[1] >= '0') and (LLine[1] <= '9') then begin
            var LTokens := LLine.Split([' '], TStringSplitOptions.ExcludeEmpty);
            var LTokenIdx := 0;
            while LTokenIdx + 1 < Length(LTokens) do begin
              var LLineNumStr := LTokens[LTokenIdx];
              var LAddrStr := LTokens[LTokenIdx + 1];
              if (LAddrStr.StartsWith('0001:')) or (LAddrStr.StartsWith('0002:')) then begin
                var LHexAddr := Copy(LAddrStr, 6, MaxInt);
                var LOffset: UInt64;
                if TryParseHexUInt64(LHexAddr, LOffset) and TryStrToInt(LLineNumStr, LLn) then begin
                  var LSegNum := 1;
                  if LAddrStr.StartsWith('0002:') then
                    LSegNum := 2;
                  var LFullAddr: UInt64;
                  if TrySegmentMapRva(LSegNum, LOffset, LFullAddr) then begin
                    var LInfo: TLineInfo;
                    LInfo.Addr := LFullAddr;
                    LInfo.SourceFile := LCurrentSourceFile;
                    LInfo.Line := LLn;
                    LLinesInfo.Add(LInfo);
                  end;
                end;
              end;
              Inc(LTokenIdx, 2);
            end;
          end;
        end;
      end;
      if LSyms.Count = 0 then
        Exit(False);

      var LSymArr := LSyms.ToArray;
      // Quick sort symbols by address using TList.Sort
      var LSymList := TList<TMapSymbol>.Create;
      try
        LSymList.AddRange(LSymArr);
        LSymList.Sort(
            TComparer<TMapSymbol>.Construct(
                function(const A, B: TMapSymbol): Integer
                begin
                  if A.Addr < B.Addr then
                    Exit(-1);
                  if A.Addr > B.Addr then
                    Exit(1);
                  Exit(0);
                end
            )
        );
        ASymbols := LSymList.ToArray;
      finally
        LSymList.Free;
      end;

      if LLinesInfo.Count > 0 then begin
        var LLinesArr := LLinesInfo.ToArray;
        var LLinesList := TList<TLineInfo>.Create;
        try
          LLinesList.AddRange(LLinesArr);
          LLinesList.Sort(
              TComparer<TLineInfo>.Construct(
                  function(const A, B: TLineInfo): Integer
                  begin
                    if A.Addr < B.Addr then
                      Exit(-1);
                    if A.Addr > B.Addr then
                      Exit(1);
                    Exit(0);
                  end
              )
          );
          ALines := LLinesList.ToArray;
        finally
          LLinesList.Free;
        end;
      end;

      Result := True;
    finally
      LSyms.Free;
      LLinesInfo.Free;
    end;
  finally
    LLines.Free;
  end;
end;


// Split a symbol name into tokens at delimiters: . < > { } $
// Returns token IDs via ATokens, adding new tokens to ADict/AOrdered.
procedure TStackTraceManager.TokenizeName(
    const AName: string;
    ATokens: TList<Integer>;
    ADict: TDictionary<string, Integer>;
    AOrdered: TList<string>
);
begin
  TMapDataSerializer.TokenizeName(AName, ATokens, ADict, AOrdered);
end;

// Reconstruct a symbol name from its token sequence.
function TStackTraceManager.ExpandSymbolName(ASymIdx: Integer): string;
var
  I: Integer;
  LEntry: TSymbolEntry;
  LEndToken: Integer;
begin
  if (ASymIdx < 0) or (ASymIdx >= Length(FSymEntries)) then
    Exit('');
  LEntry := FSymEntries[ASymIdx];
  if LEntry.TokenCount = 0 then
    Exit('');
  if (LEntry.FirstToken < 0) or (LEntry.TokenCount < 0) then
    Exit('');
  LEndToken := LEntry.FirstToken + LEntry.TokenCount;
  if (LEndToken > Length(FTokenData)) or (LEndToken <= LEntry.FirstToken) then
    Exit('');
  // Bounds-check: ensure all token indices within FTokenDict range
  for I := LEntry.FirstToken to LEndToken - 1 do
    if (FTokenData[I] < 0) or (FTokenData[I] >= Length(FTokenDict)) then
      Exit('');
  Result := FTokenDict[FTokenData[LEntry.FirstToken]];
  for I := LEntry.FirstToken + 1 to LEndToken - 1 do
    Result := Result + FTokenDict[FTokenData[I]];
end;

// Populate global tokenized structures from parsed map data.
procedure TStackTraceManager.TokenizeAndStore(const ASymbols: TArray<TMapSymbol>; const ALines: TArray<TLineInfo>);
var
  I: Integer;
  LTokenIds: TList<Integer>;
  LDict: TDictionary<string, Integer>;
  LOrdered: TList<string>;
  LPathDict: TDictionary<string, Integer>;
  LPaths: TList<string>;
  LId: Integer;
begin
  // Phase 1: tokenize all symbol names
  LTokenIds := TList<Integer>.Create;
  LDict := TDictionary<string, Integer>.Create;
  LOrdered := TList<string>.Create;
  try
    SetLength(FSymEntries, Length(ASymbols));
    for I := 0 to High(ASymbols) do begin
      FSymEntries[I].Addr := ASymbols[I].Addr;
      LTokenIds.Clear;
      TokenizeName(ASymbols[I].Name, LTokenIds, LDict, LOrdered);
      FSymEntries[I].TokenCount := LTokenIds.Count;
      // Append to flat token data; FirstToken is current FTokenData length
      var LOldLen := Length(FTokenData);
      FSymEntries[I].FirstToken := LOldLen;
      SetLength(FTokenData, LOldLen + LTokenIds.Count);
      for var J := 0 to LTokenIds.Count - 1 do
        FTokenData[LOldLen + J] := LTokenIds[J];
    end;
    FTokenDict := LOrdered.ToArray;
  finally
    LTokenIds.Free;
    LDict.Free;
    LOrdered.Free;
  end;

  // Phase 2: build source path string table for line info
  LPathDict := TDictionary<string, Integer>.Create;
  LPaths := TList<string>.Create;
  try
    SetLength(FLineEntries, Length(ALines));
    for I := 0 to High(ALines) do begin
      FLineEntries[I].Addr := ALines[I].Addr;
      FLineEntries[I].Line := ALines[I].Line;
      if not LPathDict.TryGetValue(ALines[I].SourceFile, LId) then begin
        LId := LPaths.Count;
        LPathDict.Add(ALines[I].SourceFile, LId);
        LPaths.Add(ALines[I].SourceFile);
      end;
      FLineEntries[I].FileIdx := LId;
    end;
    FSourcePaths := LPaths.ToArray;
  finally
    LPathDict.Free;
    LPaths.Free;
  end;
end;

function TStackTraceManager.SerializeSymbols(
    const ASymbols: TArray<TMapSymbol>;
    const ALines: TArray<TLineInfo>;
    const ADefines: TArray<string>
): TBytes;
var
  LMapData: TMapData;
begin
  TokenizeAndStore(ASymbols, ALines);

  LMapData.Version := MapResVersion;
  LMapData.Symbols := Copy(ASymbols);
  LMapData.SymbolEntries := Copy(FSymEntries);
  LMapData.LineInfo := Copy(FLineEntries);
  LMapData.SourcePaths := Copy(FSourcePaths);
  LMapData.LocalVars := Copy(FLocalVarData);
  LMapData.TokenDict := Copy(FTokenDict);
  LMapData.TokenData := Copy(FTokenData);
  LMapData.Defines := Copy(ADefines);

  Result := TMapDataSerializer.Serialize(LMapData);
end;

function TStackTraceManager.DeserializeSymbols(const AData: TBytes): Boolean;
var
  LMapData: TMapData;
begin
  Result := False;

  // 清空之前的数据
  FTokenDict := nil;
  FTokenData := nil;
  FSymEntries := nil;
  FLineEntries := nil;
  FSourcePaths := nil;
  FLocalVarData := nil;
  FDefines := nil;

  // 委托给 TMapDataSerializer 执行反序列化
  LMapData := TMapDataSerializer.Deserialize(AData);
  if LMapData.Version = 0 then
    Exit;

  // 从 TMapData 拷贝到内部状态
  FTokenDict := LMapData.TokenDict;
  FTokenData := LMapData.TokenData;
  FSymEntries := LMapData.SymbolEntries;
  FLineEntries := LMapData.LineInfo;
  FSourcePaths := LMapData.SourcePaths;
  FLocalVarData := LMapData.LocalVars;
  FDefines := LMapData.Defines;

  Result := True;
end;

function TStackTraceManager.TryLoadMapFromResource: Boolean;
var
  hRes: HRSRC;
  hGlobal: THandle;
  pData: Pointer;
  dwSize: DWORD;
  LBytes: TBytes;
begin
  Result := False;
  hRes := FindResourceW(HInstance, 'MAPDATA', RT_RCDATA_W);
  if hRes = 0 then
    Exit;
  dwSize := SizeofResource(HInstance, hRes);
  if dwSize = 0 then
    Exit;
  hGlobal := LoadResource(HInstance, hRes);
  if hGlobal = 0 then
    Exit;
  pData := LockResource(hGlobal);
  if pData = nil then
    Exit;

  SetLength(LBytes, dwSize);
  Move(pData^, LBytes[0], dwSize);
  UnlockResource(hGlobal);
  FreeResource(hGlobal);

  LBytes := DecompressBytes(LBytes);
  Result := DeserializeSymbols(LBytes);
end;

function TryLocateMapDataOverlay(AStream: TStream; out ADataOffset, ADataSize: Int64): Boolean;
var
  LMagic: array[0..SizeOf(MapOverlayMagic) - 1] of AnsiChar;
  LRawSize: UInt64;
  LFooterSize: Int64;
  I: Integer;
begin
  Result := False;
  ADataOffset := 0;
  ADataSize := 0;
  LFooterSize := SizeOf(MapOverlayMagic) + SizeOf(UInt64);
  if AStream.Size < LFooterSize then
    Exit;

  AStream.Position := AStream.Size - SizeOf(MapOverlayMagic);
  AStream.ReadBuffer(LMagic[0], SizeOf(LMagic));
  for I := 0 to High(LMagic) do
    if LMagic[I] <> MapOverlayMagic[I] then
      Exit;

  AStream.Position := AStream.Size - LFooterSize;
  AStream.ReadBuffer(LRawSize, SizeOf(LRawSize));
  if (LRawSize = 0) or (LRawSize > UInt64(AStream.Size - LFooterSize)) or (LRawSize > UInt64(High(Integer))) then
    Exit;

  ADataSize := Int64(LRawSize);
  ADataOffset := AStream.Size - LFooterSize - ADataSize;
  Result := ADataOffset >= 0;
end;

function TStackTraceManager.TryLoadMapFromOverlay: Boolean;
var
  LStream: TFileStream;
  LDataOffset: Int64;
  LDataSize: Int64;
  LCompressed: TBytes;
  LBytes: TBytes;
begin
  Result := False;
  try
    LStream := TFileStream.Create(ParamStr(0), fmOpenRead or fmShareDenyNone);
    try
      if not TryLocateMapDataOverlay(LStream, LDataOffset, LDataSize) then
        Exit;
      SetLength(LCompressed, Integer(LDataSize));
      LStream.Position := LDataOffset;
      LStream.ReadBuffer(LCompressed[0], Integer(LDataSize));
    finally
      LStream.Free;
    end;

    LBytes := DecompressBytes(LCompressed);
    Result := DeserializeSymbols(LBytes);
  except
    Result := False;
  end;
end;

function TStackTraceManager.WriteMapDataOverlay(
    const AExePath: string;
    const ACompressed: TBytes;
    AProgress: TResourceSerializeProgress
): Boolean;
var
  LStream: TFileStream;
  LDataOffset: Int64;
  LDataSize: Int64;
  LRawSize: UInt64;
begin
  Result := False;
  if Length(ACompressed) = 0 then
    Exit;

  try
    LStream := TFileStream.Create(AExePath, fmOpenReadWrite or fmShareDenyWrite);
    try
      if TryLocateMapDataOverlay(LStream, LDataOffset, LDataSize) then
        LStream.Size := LDataOffset;
      LStream.Position := LStream.Size;
      LStream.WriteBuffer(ACompressed[0], Length(ACompressed));
      LRawSize := UInt64(Length(ACompressed));
      LStream.WriteBuffer(LRawSize, SizeOf(LRawSize));
      LStream.WriteBuffer(MapOverlayMagic[0], SizeOf(MapOverlayMagic));
      Result := True;
    finally
      LStream.Free;
    end;
  except
    on E: Exception do begin
      if Assigned(AProgress) then
        AProgress(rssInjectResource, '[EMBED-MAP] Overlay write failed: ' + E.Message);
      Result := False;
    end;
  end;

  if Result and Assigned(AProgress) then
    AProgress(rssInjectResource, '[EMBED-MAP] Stored MAPDATA in overlay fallback');
end;

function TStackTraceManager.ValidatePEImage(const AExePath: string): Boolean;
var
  LStream: TFileStream;
  LWord: Word;
  LDword: DWORD;
  LfaNew: Int64;

  function ReadWordAt(AOffset: Int64; out AValue: Word): Boolean;
  begin
    Result := False;
    if (AOffset < 0) or (AOffset > LStream.Size - SizeOf(AValue)) then
      Exit;
    LStream.Position := AOffset;
    LStream.ReadBuffer(AValue, SizeOf(AValue));
    Result := True;
  end;

  function ReadDwordAt(AOffset: Int64; out AValue: DWORD): Boolean;
  begin
    Result := False;
    if (AOffset < 0) or (AOffset > LStream.Size - SizeOf(AValue)) then
      Exit;
    LStream.Position := AOffset;
    LStream.ReadBuffer(AValue, SizeOf(AValue));
    Result := True;
  end;

begin
  Result := False;
  if not FileExists(AExePath) then
    Exit;

  try
    LStream := TFileStream.Create(AExePath, fmOpenRead or fmShareDenyNone);
    try
      if LStream.Size < $100 then
        Exit;
      if (not ReadWordAt(0, LWord)) or (LWord <> IMAGE_DOS_SIGNATURE) then
        Exit;
      if not ReadDwordAt($3C, LDword) then
        Exit;
      LfaNew := LDword;
      if (LfaNew <= 0) or (LfaNew > LStream.Size - 24) then
        Exit;
      if (not ReadDwordAt(LfaNew, LDword)) or (LDword <> IMAGE_NT_SIGNATURE) then
        Exit;
      if (not ReadWordAt(LfaNew + 4, LWord)) or ((LWord <> $014C) and (LWord <> $8664)) then
        Exit;
      if (not ReadWordAt(LfaNew + 6, LWord)) or (LWord = 0) or (LWord > 96) then
        Exit;
      if (not ReadWordAt(LfaNew + 24, LWord)) or ((LWord <> $10B) and (LWord <> $20B)) then
        Exit;
      Result := True;
    finally
      LStream.Free;
    end;
  except
    Result := False;
  end;
end;

function TStackTraceManager.TryLoadMapFile: Boolean;
var
  LSyms: TArray<TMapSymbol>;
  LLines: TArray<TLineInfo>;
begin
  if FMapLoaded <> 0 then
    Exit(FMapLoaded = 1);

  // Try embedded resource FIRST (contains local variable data)
  if TryLoadMapFromResource then begin
    EnsureMainModuleBases;
    FMapLoaded := 1;
    Exit(True);
  end;

  // Large resource updates can be unsafe for some Delphi Win64 PE layouts.
  // Overlay keeps MAPDATA embedded in the EXE without changing PE sections.
  if TryLoadMapFromOverlay then begin
    EnsureMainModuleBases;
    FMapLoaded := 1;
    Exit(True);
  end;

  // Fall back to .map file on disk (no local variable data)
  var LMapPath := ChangeFileExt(ParamStr(0), '.map');
  if FileExists(LMapPath) then begin
    if ParseMapFile(LMapPath, LSyms, LLines) then begin
      TokenizeAndStore(LSyms, LLines);
      EnsureMainModuleBases;
      FMapLoaded := 1;
      Exit(True);
    end;
  end;

  FMapLoaded := -1;
  Result := False;
end;

procedure TStackTraceManager.StripSourcePaths(var ALines: TArray<TLineInfo>);
var
  I: Integer;
  LPrefix: string;
  LMinLen: Integer;
begin
  if Length(ALines) = 0 then
    Exit;
  LPrefix := ALines[0].SourceFile;
  LMinLen := Length(LPrefix);
  for I := 1 to High(ALines) do begin
    var LPath := ALines[I].SourceFile;
    var J := 1;
    while (J <= LMinLen) and (J <= Length(LPath)) and (CompareText(LPrefix[J], LPath[J]) = 0) do
      Inc(J);
    LMinLen := J - 1;
    if LMinLen = 0 then
      Break;
  end;
  if LMinLen > 0 then begin
    // Back up to last directory separator
    while (LMinLen > 0) and (LPrefix[LMinLen] <> '\') and (LPrefix[LMinLen] <> '/') do
      Dec(LMinLen);
    if LMinLen > 0 then
      for I := 0 to High(ALines) do
        Delete(ALines[I].SourceFile, 1, LMinLen);
  end;
end;

function TStackTraceManager.CompressBytes(const AData: TBytes): TBytes;
var
  LInput, LOutput: TMemoryStream;
  LCompressor: TZCompressionStream;
begin
  LInput := TMemoryStream.Create;
  try
    if Length(AData) > 0 then
      LInput.WriteBuffer(AData[0], Length(AData));
    LInput.Position := 0;

    LOutput := TMemoryStream.Create;
    try
      LCompressor := TZCompressionStream.Create(clMax, LOutput);
      try
        LCompressor.CopyFrom(LInput, 0);
      finally
        LCompressor.Free;
      end;
      SetLength(Result, LOutput.Size);
      if LOutput.Size > 0 then
        Move(LOutput.Memory^, Result[0], LOutput.Size);
    finally
      LOutput.Free;
    end;
  finally
    LInput.Free;
  end;
end;

function TStackTraceManager.DecompressBytes(const AData: TBytes): TBytes;
var
  LInput, LOutput: TMemoryStream;
  LDecompressor: TZDecompressionStream;
  LHeader: Byte;
begin
  if Length(AData) = 0 then
    Exit(nil);

  LHeader := AData[0];
  if LHeader <> $78 then begin
    SetLength(Result, Length(AData));
    Move(AData[0], Result[0], Length(AData));
    Exit;
  end;

  LInput := TMemoryStream.Create;
  try
    LInput.WriteBuffer(AData[0], Length(AData));
    LInput.Position := 0;

    LOutput := TMemoryStream.Create;
    try
      LDecompressor := TZDecompressionStream.Create(LInput);
      try
        LOutput.CopyFrom(LDecompressor, 0);
      finally
        LDecompressor.Free;
      end;
      SetLength(Result, LOutput.Size);
      if LOutput.Size > 0 then
        Move(LOutput.Memory^, Result[0], LOutput.Size);
    finally
      LOutput.Free;
    end;
  finally
    LInput.Free;
  end;
end;

function TStackTraceManager.EmbedMapData(const AExePath: string; AProgress: TResourceSerializeProgress): Boolean;

  procedure Log(const AStep: TResourceSerializeStep; const AMsg: string);
  begin
    if Assigned(AProgress) then
      AProgress(AStep, AMsg);
  end;

var
  LMapPath: string;
  LSyms: TArray<TMapSymbol>;
  LLines: TArray<TLineInfo>;
  LSerialized: TBytes;
  LCompressed: TBytes;
  LTargetExe: string;
  LSelfOrig: string;
  LSelfBak: string;
  LSelfNew: string;
  LCmdLine: string;
  LProcInfo: TProcessInformation;
  LStartInfo: TStartupInfo;
  LDprojDefines: TArray<string>;

  function InjectCompressedMapData(const ATargetExe: string): Boolean;
  var
    LUpdate: THandle;
    LBackupPath: string;
    LResourceWritten: Boolean;
  begin
    LResourceWritten := False;
    LBackupPath := ATargetExe + '.' + IntToStr(GetCurrentProcessId) + '.mapdata.bak';
    System.SysUtils.DeleteFile(LBackupPath);

    if CopyFile(PChar(ATargetExe), PChar(LBackupPath), False) then begin
      LUpdate := BeginUpdateResourceW(PWideChar(ATargetExe), False);
      if LUpdate = 0 then
        Log(rssInjectResource, '[EMBED-MAP] BeginUpdateResource failed (error ' + IntToStr(GetLastError) + '), using overlay fallback')
      else begin
        try
          if not UpdateResourceW(LUpdate, RT_RCDATA_W, 'MAPDATA', 0, @LCompressed[0], DWORD(Length(LCompressed))) then begin
            Log(rssInjectResource, '[EMBED-MAP] UpdateResource failed (error ' + IntToStr(GetLastError) + '), using overlay fallback');
            EndUpdateResourceW(LUpdate, True);
            LUpdate := 0;
          end
          else if not EndUpdateResourceW(LUpdate, False) then begin
            Log(rssInjectResource, '[EMBED-MAP] EndUpdateResource failed (error ' + IntToStr(GetLastError) + '), using overlay fallback');
            LUpdate := 0;
          end
          else begin
            LUpdate := 0;
            LResourceWritten := True;
          end;
        except
          on E: Exception do begin
            if LUpdate <> 0 then
              EndUpdateResourceW(LUpdate, True);
            Log(rssInjectResource, '[EMBED-MAP] ' + E.ClassName + ': ' + E.Message + ', using overlay fallback');
          end;
        end;

        if LResourceWritten and ValidatePEImage(ATargetExe) then begin
          System.SysUtils.DeleteFile(LBackupPath);
          Result := True;
          Exit;
        end;

        if LResourceWritten then
          Log(rssInjectResource, '[EMBED-MAP] Resource update produced an invalid PE, restoring backup and using overlay fallback');
        CopyFile(PChar(LBackupPath), PChar(ATargetExe), False);
      end;
    end
    else
      Log(rssInjectResource, '[EMBED-MAP] Backup copy failed (error ' + IntToStr(GetLastError) + '), using overlay fallback');

    Result := WriteMapDataOverlay(ATargetExe, LCompressed, AProgress) and ValidatePEImage(ATargetExe);
    if FileExists(LBackupPath) then
      System.SysUtils.DeleteFile(LBackupPath);
  end;

begin
  Result := False;

  LMapPath := ChangeFileExt(AExePath, '.map');
  if not FileExists(LMapPath) then begin
    Log(rssParseMap, '[EMBED-MAP] Map file not found: ' + LMapPath);
    Exit;
  end;

  if not ParseMapFile(LMapPath, LSyms, LLines) then begin
    Log(rssParseMap, '[EMBED-MAP] Failed to parse map file: ' + LMapPath);
    Exit;
  end;

  // Collect full source paths before strip
  var LFullPaths := TList<string>.Create;
  try
    for var I := 0 to High(LLines) do
      if not LFullPaths.Contains(LLines[I].SourceFile) then
        LFullPaths.Add(LLines[I].SourceFile);

    StripSourcePaths(LLines);

    Log(
        rssParseMap,
        Format(
            '[EMBED-MAP] Parsed %d symbols, %d line infos from %d unique source files',
            [Length(LSyms), Length(LLines), LFullPaths.Count]
        )
    );

    // Diagnostic: dump all source paths
    var LAstDbg := TStringList.Create;
    try
      LAstDbg.Add(Format('=== AST Extraction Diagnostic ===', []));
      LAstDbg.Add(Format('Total symbols from map: %d', [Length(LSyms)]));
      LAstDbg.Add(Format('Total source files (LFullPaths): %d', [LFullPaths.Count]));
      LAstDbg.Add('');

      // Resolve relative source paths to full paths
      var LResolvedPaths: TArray<string>;
      SetLength(LResolvedPaths, LFullPaths.Count);
      var LProjectRoot := ExtractFilePath(ExpandFileName(AExePath));

      var LSearchDirs: TList<string>;
      LSearchDirs := TList<string>.Create;
      try
        LSearchDirs.Add('');
        var LDprojPath2 := ChangeFileExt(AExePath, '.dproj');
        if FileExists(LDprojPath2) then begin
          try
            var LDprojContent2 := TFile.ReadAllText(LDprojPath2);
            var LSpStart := Pos('<DCC_UnitSearchPath>', LDprojContent2);
            if LSpStart > 0 then begin
              LSpStart := LSpStart + 20;
              var LSpEnd := Pos('</DCC_UnitSearchPath>', LDprojContent2, LSpStart);
              if LSpEnd > LSpStart then begin
                var LSpStr := Copy(LDprojContent2, LSpStart, LSpEnd - LSpStart);
                var LSpParts := LSpStr.Split([';']);
                for var K := 0 to High(LSpParts) do begin
                  var LTrimmed := Trim(LSpParts[K]);
                  if (LTrimmed <> '') and not LTrimmed.StartsWith('$(') then begin
                    if TPath.IsRelativePath(LTrimmed) then
                      LSearchDirs.Add(LTrimmed + '\')
                    else if DirectoryExists(LTrimmed) then
                      LSearchDirs.Add(IncludeTrailingPathDelimiter(LTrimmed));
                  end;
                end;
              end;
            end;
          except
            on E: Exception do
              LAstDbg.Add('  [PATH] dproj unit search path parse failed: ' + E.Message);
          end;
        end;

        // Discover Delphi RTL/VCL source paths from installed BDS registry keys.
        var LBDSRoot := '';
        var LBestBDSMajor := -1;
        var LRegistryRoots: TArray<HKEY> := [HKEY_CURRENT_USER, HKEY_LOCAL_MACHINE];
        for var LRootKey in LRegistryRoots do begin
          try
            var LReg := TRegistry.Create(KEY_READ);
            var LKeyNames := TStringList.Create;
            try
              LReg.RootKey := LRootKey;
              if LReg.OpenKeyReadOnly('Software\Embarcadero\BDS') then begin
                LReg.GetKeyNames(LKeyNames);
                LReg.CloseKey;
                for var K := 0 to LKeyNames.Count - 1 do begin
                  var LVersionText := LKeyNames[K];
                  var LMajorText := LVersionText;
                  var LDotPos := Pos('.', LMajorText);
                  if LDotPos > 0 then
                    LMajorText := Copy(LMajorText, 1, LDotPos - 1);
                  var LMajor := 0;
                  if not TryStrToInt(LMajorText, LMajor) then
                    Continue;
                  if LMajor <= LBestBDSMajor then
                    Continue;
                  if LReg.OpenKeyReadOnly('Software\Embarcadero\BDS\' + LVersionText) then begin
                    try
                      if LReg.ValueExists('RootDir') then begin
                        var LRootDir := LReg.ReadString('RootDir');
                        if (LRootDir <> '') and DirectoryExists(LRootDir) then begin
                          LBDSRoot := LRootDir;
                          LBestBDSMajor := LMajor;
                        end;
                      end;
                    finally
                      LReg.CloseKey;
                    end;
                  end;
                end;
              end
              else
                LAstDbg.Add('  [REG] OpenKeyReadOnly BDS root failed');
            finally
              LKeyNames.Free;
              LReg.Free;
            end;
          except
            on E: Exception do
              LAstDbg.Add('  [REG] BDS root scan exception: ' + E.Message);
          end;
        end;
        var LBDSKnownSrcDirs: TArray<string> :=
            [
                'source\rtl\common\',
                'source\rtl\sys\',
                'source\rtl\win\',
                'source\rtl\ext\',
                'source\vcl\',
                'source\fmx\',
                'source\data\',
                'source\internet\',
                'source\soap\',
                'source\xml\'
            ];
        if LBDSRoot <> '' then begin
          LBDSRoot := IncludeTrailingPathDelimiter(LBDSRoot);
          for var K := 0 to High(LBDSKnownSrcDirs) do begin
            var LDir := LBDSRoot + LBDSKnownSrcDirs[K];
            if DirectoryExists(LDir) then
              LSearchDirs.Add(LDir);
          end;
        end;

        LAstDbg.Add('--- Resolved Source File Paths ---');
        if LBDSRoot <> '' then
          LAstDbg.Add(Format('  BDS root: %s', [LBDSRoot]));
        LAstDbg.Add(Format('  Search dirs: %d', [LSearchDirs.Count]));
        for var I := 0 to LFullPaths.Count - 1 do begin
          var LResolved := '';
          // First try as-is (absolute path)
          if FileExists(LFullPaths[I]) then
            LResolved := ExpandFileName(LFullPaths[I])
          else begin
            // Try relative to project root (preserving subdirectory structure)
            var LCandidate2 := LProjectRoot + LFullPaths[I];
            if FileExists(LCandidate2) then
              LResolved := ExpandFileName(LCandidate2)
            else begin
              // Search in all search dirs (project + third-party + RTL) using short name
              var LShortName := ExtractFileName(LFullPaths[I]);
              for var LD in LSearchDirs do begin
                var LCandidate: string;
                if TPath.IsRelativePath(LD) then
                  LCandidate := LProjectRoot + LD + LShortName
                else
                  LCandidate := LD + LShortName;
                if FileExists(LCandidate) then begin
                  LResolved := ExpandFileName(LCandidate);
                  Break;
                end;
              end;
              // Recursive project-wide search is expensive on large projects; keep it opt-in.
              if LResolved = '' then begin
                if SameText(GetEnvironmentVariable('DAOFY_STACKTRACE_RECURSIVE_SOURCE_LOOKUP'), '1') then begin
                  try
                    var LFound := TDirectory.GetFiles(LProjectRoot, LShortName, TSearchOption.soAllDirectories);
                    if Length(LFound) > 0 then
                      LResolved := LFound[0];
                  except
                    on E: Exception do
                      LAstDbg.Add('  [PATH] recursive search under project root failed: ' + E.Message);
                  end;
                end
                else
                  LAstDbg.Add('  [PATH] recursive source lookup disabled; set DAOFY_STACKTRACE_RECURSIVE_SOURCE_LOOKUP=1 to enable');
              end;
              if LResolved = '' then
                LResolved := LFullPaths[I];
            end;
          end;
          LResolvedPaths[I] := LResolved;
          var LExists := FileExists(LResolved);
          LAstDbg.Add(
              Format(
                  '  [%d] %s -> %s  (exists=%s)',
                  [I, ExtractFileName(LFullPaths[I]), LResolved, BoolToStr(LExists, True)]
              )
          );
        end;
      finally
        LSearchDirs.Free;
      end;
      LAstDbg.Add('');

      // Read conditional defines and platform from .dproj
      LDprojDefines := [];
      var LDprojPath := ChangeFileExt(AExePath, '.dproj');
      if FileExists(LDprojPath) then begin
        try
          var LDprojContent := TFile.ReadAllText(LDprojPath);
          var LDefList := TList<string>.Create;
          try
            var LDefStart := Pos('<DCC_Define>', LDprojContent);
            if LDefStart > 0 then begin
              LDefStart := LDefStart + 13;
              var LDefEnd := Pos('</DCC_Define>', LDprojContent, LDefStart);
              if LDefEnd > LDefStart then begin
                var LDefStr := Copy(LDprojContent, LDefStart, LDefEnd - LDefStart);
                var LDefParts := LDefStr.Split([';']);
                for var K := 0 to High(LDefParts) do begin
                  var LTrimmed := Trim(LDefParts[K]);
                  if (LTrimmed <> '') and not LTrimmed.StartsWith('$(') then
                    LDefList.Add(LTrimmed);
                end;
              end;
            end;
            var LPlatformStart := Pos('<Platform>', LDprojContent);
            if LPlatformStart > 0 then begin
              LPlatformStart := LPlatformStart + 10;
              var LPlatformEnd := Pos('</Platform>', LDprojContent, LPlatformStart);
              if LPlatformEnd > LPlatformStart then begin
                var LPlatform := LowerCase(Trim(Copy(LDprojContent, LPlatformStart, LPlatformEnd - LPlatformStart)));
                if LPlatform = 'win32' then begin
                  LDefList.Add('WIN32');
                  LDefList.Add('MSWINDOWS');
                  LDefList.Add('CPUX86');
                  LDefList.Add('CPU386');
                  LDefList.Add('CPU32BITS');
                end
                else if LPlatform = 'win64' then begin
                  LDefList.Add('WIN64');
                  LDefList.Add('MSWINDOWS');
                  LDefList.Add('CPUX64');
                  LDefList.Add('CPU64BITS');
                end
                else if (LPlatform = 'osx64') or (LPlatform = 'osxarm64') then begin
                  LDefList.Add('MACOS');
                  LDefList.Add('POSIX');
                end
                else if (LPlatform = 'linux64') then begin
                  LDefList.Add('LINUX');
                  LDefList.Add('POSIX');
                end
                else if (LPlatform = 'android') or (LPlatform = 'android64') then begin
                  LDefList.Add('ANDROID');
                  LDefList.Add('POSIX');
                end
                else if (LPlatform = 'iosdevice64') or (LPlatform = 'iossimulator') then begin
                  LDefList.Add('IOS');
                  LDefList.Add('POSIX');
                end;
                LAstDbg.Add(Format('--- Platform from dproj: %s', [LPlatform]));
              end;
            end;
            LDprojDefines := LDefList.ToArray;
            LAstDbg.Add(Format('--- DCC_Define from dproj: %s', [string.Join(';', LDprojDefines)]));
          finally
            LDefList.Free;
          end;
        except
          LAstDbg.Add('--- DCC_Define: failed to read dproj');
        end;
      end;

      // Phase 5: extract local vars via registered callback (if any)
      if Assigned(FLocalVarExtractor) then
        FLocalVarExtractor(LResolvedPaths, LSyms, LDprojDefines, FLocalVarData);
      Log(rssBuildStringTable, Format('[EMBED-MAP] Local var entries: %d', [Length(FLocalVarData)]));
    finally
      LAstDbg.SaveToFile(ChangeFileExt(AExePath, '.ast-debug.txt'));
      LAstDbg.Free;
    end;
  finally
    LFullPaths.Free;
  end;

  LSerialized := SerializeSymbols(LSyms, LLines, LDprojDefines);
  Log(rssSerialize, Format('[EMBED-MAP] Serialized to %d bytes', [Length(LSerialized)]));

  LCompressed := CompressBytes(LSerialized);
  Log(
      rssBuildStringTable,
      Format(
          '[EMBED-MAP] Compressed to %d bytes (%.1f%%)',
          [Length(LCompressed), (Length(LCompressed) / Length(LSerialized)) * 100]
      )
  );

  LTargetExe := AExePath;

  // Self-injection: seamless hot-swap
  if SameText(ExpandFileName(AExePath), ExpandFileName(ParamStr(0))) then begin
    LSelfOrig := ExpandFileName(AExePath);
    LSelfBak := ChangeFileExt(LSelfOrig, '.bak.exe');
    LSelfNew := ChangeFileExt(LSelfOrig, '.embedded.exe');

    // Step 1: create copy and inject
    if not CopyFile(PChar(LSelfOrig), PChar(LSelfNew), False) then begin
      Log(rssSelfSwap, '[EMBED-MAP] Cannot copy running EXE (error ' + IntToStr(GetLastError) + ')');
      Exit;
    end;

    if not InjectCompressedMapData(LSelfNew) then begin
      System.SysUtils.DeleteFile(LSelfNew);
      Exit;
    end;
    Log(rssSelfSwap, '[EMBED-MAP] Injected into copy, swapping...');

    // Step 2: rename current EXE → .bak.exe
    System.SysUtils.DeleteFile(LSelfBak);
    if not RenameFile(LSelfOrig, LSelfBak) then begin
      Log(rssSelfSwap, '[EMBED-MAP] Failed to rename current EXE (error ' + IntToStr(GetLastError) + ')');
      System.SysUtils.DeleteFile(LSelfNew);
      Exit;
    end;

    // Step 3: rename embedded copy 鈫?original name
    if not RenameFile(LSelfNew, LSelfOrig) then begin
      Log(
          rssSelfSwap,
          '[EMBED-MAP] Failed to rename embedded copy (error ' + IntToStr(GetLastError) + '), restoring backup...'
      );
      RenameFile(LSelfBak, LSelfOrig);
      System.SysUtils.DeleteFile(LSelfNew);
      Exit;
    end;

    // Step 4: build command line 鈥?rebuild without the --embed-map part
    LCmdLine := LSelfOrig + ' --embedded-finalize';
    var LIdx := 1;
    while LIdx <= ParamCount do begin
      var LArg := ParamStr(LIdx);
      if LArg = '--embed-map' then begin
        Inc(LIdx, 2);
        Continue;
      end;
      LCmdLine := LCmdLine + ' ' + LArg;
      Inc(LIdx);
    end;

    Log(rssSelfSwap, '[EMBED-MAP] Launching: ' + LCmdLine);

    // Step 5: start new process
    FillChar(LStartInfo, SizeOf(LStartInfo), 0);
    LStartInfo.cb := SizeOf(LStartInfo);
    FillChar(LProcInfo, SizeOf(LProcInfo), 0);

    if CreateProcess(
        nil,
        PWideChar(LCmdLine),
        nil,
        nil,
        False,
        CREATE_NEW_PROCESS_GROUP or DETACHED_PROCESS,
        nil,
        nil,
        LStartInfo,
        LProcInfo) then
    begin
      CloseHandle(LProcInfo.hThread);
      CloseHandle(LProcInfo.hProcess);
      Log(rssSelfSwap, '[EMBED-MAP] New instance launched. Exiting old instance.');
      // Exit current process
      ExitProcess(0);
    end
    else begin
      Log(rssSelfSwap, '[EMBED-MAP] Failed to launch new instance (error ' + IntToStr(GetLastError) + ')');
      Log(rssSelfSwap, '[EMBED-MAP] Restoring backup...');
      RenameFile(LSelfOrig, LSelfNew);
      RenameFile(LSelfBak, LSelfOrig);
      Exit;
    end;
  end;

  // Normal (non-self) injection
  Result := InjectCompressedMapData(LTargetExe);
  if Result then
    Log(rssDone, '[EMBED-MAP] Successfully embedded into ' + ExtractFileName(AExePath));
end;

class function TStackTraceManager.GetEnabled: Boolean;
begin
  Result := Assigned(FCurrent);
end;

class procedure TStackTraceManager.SetEnabled(const AEnabled: Boolean);
begin
  if AEnabled then begin
    if not Assigned(FCurrent) then
{$IFDEF FPC}
      TStackTraceManager.FCurrent := TStackTraceManagerFPC.Create;
{$ELSE}
      TStackTraceManager.FCurrent := TStackTraceManagerDelphi.Create;
{$ENDIF}
  end
  else if Assigned(FCurrent) then
    FreeAndNil(FCurrent);
end;

procedure TStackTraceManager.EnableDefaultLogger;
begin
  Logger := TDefaultExceptionLogger.Create;
end;

function TStackTraceManager.GetGlobalVariables: TArray<TGlobalVarInfo>;
var
  I: Integer;
  LEntry: TSymbolEntry;
  LCtx: TRttiContext;
  LTypes: TArray<TRttiType>;
  LType: TRttiType;
  LField: TRttiField;
  LVarName: string;
  LSimpleName: string;
  LDotPos: Integer;
  LFound: Boolean;
begin
  if (FMapLoaded <> 1) or (FModuleBase = 0) or (Length(FSymEntries) = 0) then
    Exit(nil);
  SetLength(Result, Length(FSymEntries));
  LCtx := TRttiContext.Create;
  try
    LTypes := LCtx.GetTypes;
    for I := 0 to High(FSymEntries) do begin
      LEntry := FSymEntries[I];
      LVarName := ExpandSymbolName(I);
      Result[I].Name := LVarName;
      Result[I].Address := Pointer(MapAddrToRuntimeAddr(LEntry.Addr));
      Result[I].TypeHandle := nil;
      LDotPos := LastDelimiter('.', LVarName);
      if LDotPos > 0 then
        LSimpleName := Copy(LVarName, LDotPos + 1, MaxInt)
      else
        LSimpleName := LVarName;
      LFound := False;
      for LType in LTypes do begin
        for LField in LType.GetDeclaredFields do begin
          if LField.Name = LSimpleName then begin
            Result[I].TypeHandle := LField.FieldType.Handle;
            LFound := True;
            Break;
          end;
        end;
        if LFound then
          Break;
      end;
    end;
  finally
    LCtx.Free;
  end;
end;

function TStackTraceManager.GetMapLoadStatus: Integer;
begin
  Result := FMapLoaded;
end;

function TStackTraceManager.EnumerateFunctions(AFilter: TFunc<string, Boolean>): TArray<TQProfileMapEntry>;
var
  I: Integer;
  LEntry: TSymbolEntry;
  LName: string;
begin
  Result := nil;
  if FMapLoaded <> 1 then
    TryLoadMapFile;
  if (FMapLoaded <> 1) or (FModuleBase = 0) or (Length(FSymEntries) = 0) then
    Exit;
  for I := 0 to High(FSymEntries) do begin
    LEntry := FSymEntries[I];
    LName := ExpandSymbolName(I);
    if Assigned(AFilter) and not AFilter(LName) then
      Continue;
    SetLength(Result, Length(Result) + 1);
    Result[High(Result)].Name := LName;
    Result[High(Result)].Address := Pointer(MapAddrToRuntimeAddr(LEntry.Addr));
  end;
end;

function TStackTraceManager.GetModuleBaseAddr: NativeUInt;
begin
  Result := FModuleBase;
end;

function TStackTraceManager.TryResolveSourceLine(VA: NativeUInt; out AFile: string; out ALine: Integer): Boolean;
var
  LMapOffset: UInt64;
  L, H, LMid: Integer;
  LLineIdx: Integer;
  LFileIdx: Integer;
begin
  Result := False;
  AFile := '';
  ALine := 0;
  if FMapLoaded <> 1 then
    Exit;
  if (Length(FLineEntries) = 0) or (Length(FSourcePaths) = 0) then
    Exit;

  LMapOffset := RuntimeAddrToMapAddr(VA);
  if LMapOffset = 0 then
    Exit;
  L := 0;
  H := Length(FLineEntries) - 1;
  LLineIdx := -1;
  while L <= H do begin
    LMid := (L + H) shr 1;
    if FLineEntries[LMid].Addr <= LMapOffset then begin
      LLineIdx := LMid;
      L := LMid + 1;
    end
    else
      H := LMid - 1;
  end;

  if (LLineIdx < 0) or (LMapOffset - FLineEntries[LLineIdx].Addr >= $10000) then
    Exit;

  LFileIdx := FLineEntries[LLineIdx].FileIdx;
  if (LFileIdx < 0) or (LFileIdx >= Length(FSourcePaths)) then
    Exit;

  AFile := FSourcePaths[LFileIdx];
  ALine := FLineEntries[LLineIdx].Line;
  Result := True;
end;

procedure TStackTraceManager.EmbedFinalize(AProgress: TResourceSerializeProgress);

  procedure Log(const AStep: TResourceSerializeStep; const AMsg: string);
  begin
    if Assigned(AProgress) then
      AProgress(AStep, AMsg);
  end;

var
  LBakFile: string;
begin
  LBakFile := ChangeFileExt(ParamStr(0), '.bak.exe');
  Log(rssDone, '[EMBED-MAP] Self-injection complete! Map data embedded in: ' + ParamStr(0));
  if FileExists(LBakFile) then begin
    if System.SysUtils.DeleteFile(LBakFile) then
      Log(rssCleanup, '[EMBED-MAP] Backup cleaned up: ' + LBakFile)
    else
      Log(rssCleanup, '[EMBED-MAP] Warning: could not delete backup: ' + LBakFile);
  end;
end;

function TStackTraceManager.ResolveFromMap(VA: NativeUInt): string;
var
  L, H, M: Integer;
  LPrefAddr: UInt64;
  LFuncName: string;
  LBestLine: string;
begin
  Result := Format('  %p', [Pointer(VA)]);

  if (FMapLoaded <> 1) or (FModuleBase = 0) then
    Exit;

  LPrefAddr := RuntimeAddrToMapAddr(VA);
  if LPrefAddr = 0 then
    Exit;

  L := 0;
  H := Length(FSymEntries) - 1;
  M := -1;
  while L <= H do begin
    var LMid := (L + H) shr 1;
    if FSymEntries[LMid].Addr <= LPrefAddr then begin
      M := LMid;
      L := LMid + 1;
    end
    else
      H := LMid - 1;
  end;

  if M >= 0 then begin
    var LOff := LPrefAddr - FSymEntries[M].Addr;
    if LOff <= $10000 then begin
      if LOff > 0 then
        LFuncName := Format('%s+$%x', [ExpandSymbolName(M), LOff])
      else
        LFuncName := ExpandSymbolName(M);

      Result := Format('  %p %s', [Pointer(VA), LFuncName]);

      var LMapOffset := LPrefAddr;
      L := 0;
      H := Length(FLineEntries) - 1;
      var LLineIdx := -1;
      while L <= H do begin
        var LMid2 := (L + H) shr 1;
        if FLineEntries[LMid2].Addr <= LMapOffset then begin
          LLineIdx := LMid2;
          L := LMid2 + 1;
        end
        else
          H := LMid2 - 1;
      end;

      if (LLineIdx >= 0) and (LMapOffset - FLineEntries[LLineIdx].Addr < $10000) then begin
        LBestLine := Format(' [%s:%d]', [FSourcePaths[FLineEntries[LLineIdx].FileIdx], FLineEntries[LLineIdx].Line]);
        Result := Result + LBestLine;
      end;
    end;
  end;
end;

function TStackTraceManager.CachedResolveFromMap(VA: NativeUInt): string;
var
  LName, LSource: string;
  LLine: Integer;
begin
  // Priority 1: 叠加符号查询 (热补丁新增函数)
  if (FOverlayProvider <> nil) and FOverlayProvider.ResolveOverlaySymbol(VA, LName, LSource, LLine) then begin
    Result := Format('  %p %s', [Pointer(VA), LName]);
    if LSource <> '' then
      Result := Result + Format(' [%s:%d]', [LSource, LLine]);
    Exit;
  end;

  // Priority 2: 符号缓存
  if FSymbolCache.TryGetValue(VA, Result) then
    Exit;

  // Priority 3: 原始 MAPDATA 符号表解析
  Result := ResolveFromMap(VA);

  // 写入缓存 (仅缓存原始表结果, 不缓存叠加结果)
  if FSymbolCache.ContainsKey(VA) then
    FSymbolCache[VA] := Result
  else
    FSymbolCache.Add(VA, Result);
end;

procedure TStackTraceManager.ClearSymbolCache;
var
  I: Integer;
begin
  FSymbolCache.Clear;
  FreeAndNil(FSymNameCache);
  for I := 0 to High(FModuleTables) do
    FModuleTables[I].NameCache.Free;
  FModuleTables := nil;
  FModulesLoaded := 0;
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  BuildSymbolNameCache — 构建符号名→地址反向缓存 (延迟初始化)            }
{ ─────────────────────────────────────────────────────────────────────── }

procedure TStackTraceManager.BuildSymbolNameCache;
var
  I: Integer;
  LName: string;
begin
  if FMapLoaded <> 1 then
    TryLoadMapFile;
  if (FMapLoaded <> 1) or (Length(FSymEntries) = 0) then
    Exit;

  FSymNameCache := TDictionary<string, UInt64>.Create;
  for I := 0 to High(FSymEntries) do begin
    LName := ExpandSymbolName(I);
    if (LName <> '') and (not FSymNameCache.ContainsKey(LName)) then
      FSymNameCache.Add(LName, FSymEntries[I].Addr);
  end;
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  FindSymbolAddress — 按符号名查找运行时地址 (反向解析)                   }
{  返回的地址已包含 ASLR 偏置 (runtime module base + map/preferred-base offset)。 }
{  未找到时返回 nil。                                                     }
{ ─────────────────────────────────────────────────────────────────────── }

function TStackTraceManager.FindSymbolAddress(const AName: string): Pointer;
var
  LMapAddr: UInt64;
  LRva: UInt64;
begin
  Result := nil;
  if AName = '' then
    Exit;
  if FMapLoaded <> 1 then
    TryLoadMapFile;
  if (FMapLoaded <> 1) or (FModuleBase = 0) or (Length(FSymEntries) = 0) then
    Exit;

  // 延迟构建反向缓存
  if FSymNameCache = nil then
    BuildSymbolNameCache;
  if FSymNameCache = nil then
    Exit;

  // 查找: 精确匹配 (区分大小写, 与 ExpandSymbolName 行为一致)
  // 第一步: 查主模块 (现有 FSymNameCache)
  if FSymNameCache.TryGetValue(AName, LMapAddr) then
    Exit(Pointer(MapAddrToRuntimeAddr(LMapAddr)));

  // 第二步: 查所有已加载模块的符号表
  if FModulesLoaded = 0 then
    LoadAllModuleSymbols;
  if FModulesLoaded = 1 then begin
    for var I := 0 to High(FModuleTables) do begin
      if FModuleTables[I].NameCache.TryGetValue(AName, LRva) then begin
        if LRva <= UInt64(High(NativeUInt)) - FModuleTables[I].ModuleBase then
          Exit(Pointer(FModuleTables[I].ModuleBase + NativeUInt(LRva)));
        Exit(nil);
      end;
    end;
  end;
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  GetModulePreferredBase — 从磁盘 PE 头读取 PreferredImageBase            }
{  注意：ASLR 后映射内存头不可靠，不能作为 PreferredBase 来源。       }
{ ─────────────────────────────────────────────────────────────────────── }

function TStackTraceManager.GetModulePreferredBase(hModule: HMODULE): NativeUInt;
var
  LPath: array[0..MAX_PATH - 1] of Char;
  LLen: DWORD;
  LPreferred: UInt64;
begin
  Result := PreferredImageBase; // fallback
  if hModule = 0 then
    Exit;

  LLen := GetModuleFileName(hModule, LPath, Length(LPath));
  if (LLen = 0) or (LLen >= DWORD(Length(LPath))) then
    Exit;

  LPreferred := GetPEFilePreferredBase(string(LPath));
  if (LPreferred <> 0) and (LPreferred <= UInt64(High(NativeUInt))) then
    Result := NativeUInt(LPreferred);
end;

function TStackTraceManager.GetPEFilePreferredBase(const AExePath: string): UInt64;
var
  LStream: TFileStream;
  LWord: Word;
  LDword: DWORD;
  LUInt64: UInt64;
  LfaNew: Int64;
  LOptionalHeader: Int64;
begin
  Result := 0;
  if not FileExists(AExePath) then
    Exit;

  try
    LStream := TFileStream.Create(AExePath, fmOpenRead or fmShareDenyNone);
    try
      if LStream.Size < $100 then
        Exit;
      LStream.Position := 0;
      LStream.ReadBuffer(LWord, SizeOf(LWord));
      if LWord <> IMAGE_DOS_SIGNATURE then
        Exit;
      LStream.Position := $3C;
      LStream.ReadBuffer(LDword, SizeOf(LDword));
      LfaNew := LDword;
      LOptionalHeader := LfaNew + 24;
      if (LfaNew <= 0) or (LOptionalHeader + 32 > LStream.Size) then
        Exit;
      LStream.Position := LfaNew;
      LStream.ReadBuffer(LDword, SizeOf(LDword));
      if LDword <> IMAGE_NT_SIGNATURE then
        Exit;
      LStream.Position := LOptionalHeader;
      LStream.ReadBuffer(LWord, SizeOf(LWord));
      if LWord = $10B then begin
        LStream.Position := LOptionalHeader + 28;
        LStream.ReadBuffer(LDword, SizeOf(LDword));
        Result := LDword;
      end
      else if LWord = $20B then begin
        LStream.Position := LOptionalHeader + 24;
        LStream.ReadBuffer(LUInt64, SizeOf(LUInt64));
        Result := LUInt64;
      end;
    finally
      LStream.Free;
    end;
  except
    Result := 0;
  end;
end;

procedure TStackTraceManager.EnsureMainModuleBases;
begin
  if FModuleBase = 0 then
    FModuleBase := NativeUInt(GetModuleHandle(nil));
  if FPreferredBase = 0 then
    FPreferredBase := GetModulePreferredBase(HMODULE(FModuleBase));
end;

function TStackTraceManager.MapAddrToRuntimeAddr(AMapAddr: UInt64): NativeUInt;
begin
  EnsureMainModuleBases;
  if (FModuleBase = 0) or (AMapAddr > UInt64(High(NativeUInt)) - FModuleBase) then
    Exit(0);
  Result := FModuleBase + NativeUInt(AMapAddr);
end;

function TStackTraceManager.RuntimeAddrToMapAddr(ARuntimeAddr: NativeUInt): UInt64;
begin
  EnsureMainModuleBases;
  if (FModuleBase = 0) or (ARuntimeAddr < FModuleBase) then
    Exit(0);
  Result := UInt64(ARuntimeAddr - FModuleBase);
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  LoadAllModuleSymbols — 枚举所有已加载模块, 收集 MAPDATA 符号表          }
{  遍历 EXE + 所有 DLL, 对每个模块 FindResourceW('MAPDATA'),              }
{  如果存在则解析并加入 FModuleTables。                                    }
{ ─────────────────────────────────────────────────────────────────────── }

procedure TStackTraceManager.LoadAllModuleSymbols;
var
  LSnapshot: THandle;
  LME: TModuleEntry32;
  hRes: HRSRC;
  hGlob: THandle;
  pData: Pointer;
  dwSize: DWORD;
  LBytes: TBytes;
  LTable: TModuleSymbolTable;
  LMapData: TMapData;
  LName: string;
  LRva: UInt64;
  J: Integer;
begin
  if FModulesLoaded <> 0 then
    Exit;
  FModulesLoaded := -1; // 标记加载中, 防止重入

  LSnapshot := CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId);
  if LSnapshot = INVALID_HANDLE_VALUE then
    Exit;

  LME.dwSize := SizeOf(TModuleEntry32);
  if Module32First(LSnapshot, LME) then begin
    repeat
      // 跳过主模块 (自身 MAPDATA 已通过 TryLoadMapFromResource 加载)
      if LME.hModule = HInstance then
        Continue;

      // 查找该模块的 MAPDATA 资源
      hRes := FindResourceW(LME.hModule, 'MAPDATA', RT_RCDATA_W);
      if hRes = 0 then
        Continue;
      dwSize := SizeofResource(LME.hModule, hRes);
      if dwSize = 0 then
        Continue;
      hGlob := LoadResource(LME.hModule, hRes);
      if hGlob = 0 then
        Continue;
      pData := LockResource(hGlob);
      if pData = nil then
        Continue;

      SetLength(LBytes, dwSize);
      Move(pData^, LBytes[0], dwSize);
      UnlockResource(hGlob);
      FreeResource(hGlob);

      // 解压 + 反序列化为 TMapData (独立于主表)
      LBytes := DecompressBytes(LBytes);
      if Length(LBytes) = 0 then
        Continue;
      LMapData := TMapDataSerializer.Deserialize(LBytes);
      if LMapData.Version = 0 then
        Continue;

      // 构建 NameCache (name → RVA)
      LTable.ModuleName := string(LME.szModule);
      LTable.ModuleBase := NativeUInt(LME.modBaseAddr);
      LTable.PreferredBase := GetModulePreferredBase(LME.hModule);
      LTable.NameCache := TDictionary<string, UInt64>.Create;
      for J := 0 to High(LMapData.SymbolEntries) do begin
        LName := TMapDataSerializer.ExpandTokenName(LMapData.TokenDict, LMapData.TokenData, J, LMapData.SymbolEntries);
        if LName <> '' then begin
          LRva := LMapData.SymbolEntries[J].Addr;
          if not LTable.NameCache.ContainsKey(LName) then
            LTable.NameCache.Add(LName, LRva);
        end;
      end;

      SetLength(FModuleTables, Length(FModuleTables) + 1);
      FModuleTables[High(FModuleTables)] := LTable;

    until not Module32Next(LSnapshot, LME);
  end;
  CloseHandle(LSnapshot);
  FModulesLoaded := 1;
end;

function TStackTraceManager.GetFunctionExtent(Addr: Pointer): TFunctionExtent;
var
  LOverlayStart: Pointer;
  LOverlaySize: Integer;
  L, H, M: Integer;
  LPrefAddr: UInt64;
begin
  Result := Default(TFunctionExtent);
  Result.Found := False;

  // Priority 1: 查询叠加层函数范围 (热补丁新增函数)
  if (FOverlayProvider <> nil)
      and FOverlayProvider.GetOverlayFunctionExtent(Addr, LOverlayStart, LOverlaySize)
      and (LOverlaySize > 0) then
  begin
    Result.StartAddr := LOverlayStart;
    Result.Size := LOverlaySize;
    Result.Found := True;
    Exit;
  end;

  // Priority 2: 从符号表计算函数范围
  if (FMapLoaded <> 1) or (FModuleBase = 0) or (Length(FSymEntries) = 0) then
    Exit;

  LPrefAddr := RuntimeAddrToMapAddr(NativeUInt(Addr));
  if LPrefAddr = 0 then
    Exit;

  L := 0;
  H := Length(FSymEntries) - 1;
  M := -1;
  while L <= H do begin
    var LMid := (L + H) shr 1;
    if FSymEntries[LMid].Addr <= LPrefAddr then begin
      M := LMid;
      L := LMid + 1;
    end
    else
      H := LMid - 1;
  end;

  if M < 0 then
    Exit;

  // 确认地址在函数范围内 (上限 64KB)
  var LOff := LPrefAddr - FSymEntries[M].Addr;
  if LOff > $10000 then
    Exit;

  Result.StartAddr := Pointer(MapAddrToRuntimeAddr(FSymEntries[M].Addr));
  // 函数大小 = 下一条目地址差，最后一条默认 64KB
  if M + 1 < Length(FSymEntries) then begin
    if FSymEntries[M + 1].Addr > FSymEntries[M].Addr then begin
      var LSize64 := FSymEntries[M + 1].Addr - FSymEntries[M].Addr;
      if LSize64 > UInt64(High(Integer)) then
        Result.Size := High(Integer)
      else
        Result.Size := Integer(LSize64);
    end
    else
      Result.Size := $10000;
  end
  else
    Result.Size := $10000;
  Result.Found := True;
end;

function TStackTraceManager.ScanReturnAddresses(
    const AContext: TContext;
    const AGuardStart, AGuardEnd: Pointer
): TArray<TReturnAddrEntry>;
var
  LBP: Pointer;
  LIP: Pointer;
  LNextBP: Pointer;
  LGuardLo: NativeUInt;
  LGuardHi: NativeUInt;
  LResult: TArray<TReturnAddrEntry>;
  LCount: Integer;
begin
  Result := nil;
  LGuardLo := NativeUInt(AGuardStart);
  LGuardHi := NativeUInt(AGuardEnd);
  if (LGuardLo = 0) and (LGuardHi = 0) then
    Exit;
  if LGuardLo >= LGuardHi then
    Exit;

{$IFDEF WIN64}
  LBP := Pointer(AContext.Rbp);
{$ELSE}
  LBP := Pointer(AContext.Ebp);
{$ENDIF}

  // Check current IP (Frame 0)
{$IFDEF WIN64}
  LIP := Pointer(AContext.Rip);
{$ELSE}
  LIP := Pointer(AContext.Eip);
{$ENDIF}

  if (NativeUInt(LIP) >= LGuardLo) and (NativeUInt(LIP) < LGuardHi) then begin
    SetLength(LResult, 1);
    LResult[0].ReturnAddr := LIP;
    LResult[0].StackSlot := nil;
    LCount := 1;
  end
  else
    LCount := 0;

  // Walk EBP chain
  try
    while (LBP <> nil) and (NativeUInt(LBP) > $10000) do begin
{$IFDEF WIN64}
      LIP := Pointer(PNativeUInt(NativeUInt(LBP) + 8)^);
      LNextBP := Pointer(PNativeUInt(LBP)^);
{$ELSE}
      LIP := Pointer(PNativeUInt(NativeUInt(LBP) + 4)^);
      LNextBP := Pointer(PNativeUInt(LBP)^);
{$ENDIF}

      if (NativeUInt(LIP) >= LGuardLo) and (NativeUInt(LIP) < LGuardHi) then begin
        Inc(LCount);
        SetLength(LResult, LCount);
        LResult[LCount - 1].ReturnAddr := LIP;
{$IFDEF WIN64}
        LResult[LCount - 1].StackSlot := Pointer(NativeUInt(LBP) + 8);
{$ELSE}
        LResult[LCount - 1].StackSlot := Pointer(NativeUInt(LBP) + 4);
{$ENDIF}
      end;

      LBP := LNextBP;
      if LCount > 64 then
        Break;
    end;
  except
    // Ignore invalid memory access during stack walk
  end;

  Result := LResult;
end;

function TStackTraceManager.ReadFrameFromContext(
    const AContext: TContext;
    AFrameIndex: Integer;
    out AFrame: TFrameSnapshot
): Boolean;
var
  LBP: Pointer;
  LPrevRet: Pointer;
  LCount: Integer;
begin
  Result := False;
  AFrame := Default(TFrameSnapshot);

{$IFDEF WIN64}
  LBP := Pointer(AContext.Rbp);
  LPrevRet := Pointer(AContext.Rip);
{$ELSE}
  LBP := Pointer(AContext.Ebp);
  LPrevRet := Pointer(AContext.Eip);
{$ENDIF}

  LCount := 0;
  while (LBP <> nil) and (NativeUInt(LBP) > $10000) do begin
    if LCount = AFrameIndex then begin
      AFrame := GetFrameSnapshot(NativeUInt(LPrevRet), LBP);
      Result := True;
      Exit;
    end;
    try
{$IFDEF WIN64}
      LPrevRet := Pointer(PNativeUInt(NativeUInt(LBP) + 8)^);
      LBP := Pointer(PNativeUInt(NativeUInt(LBP))^);
{$ELSE}
      LPrevRet := Pointer(PNativeUInt(NativeUInt(LBP) + 4)^);
      LBP := Pointer(PNativeUInt(NativeUInt(LBP))^);
{$ENDIF}
    except
      Break;
    end;
    Inc(LCount);
  end;
end;

function TStackTraceManager.WalkStackFromContext(const AContext: TContext): TArray<Pointer>;
var
{$IFDEF WIN64}
  LBP: ULONG64;
  LIP: ULONG64;
{$ELSE}
  LBP: DWORD;
  LIP: DWORD;
{$ENDIF}
  LCount: Integer;
begin
  SetLength(Result, MaxStackFrames);
  LCount := 0;

{$IFDEF WIN64}
  LBP := AContext.Rbp;
  LIP := AContext.Rip;
{$ELSE}
  LBP := AContext.Ebp;
  LIP := AContext.Eip;
{$ENDIF}
  if LIP <> 0 then begin
    Result[LCount] := Pointer(LIP);
    Inc(LCount);
  end;

{$IFDEF WIN64}
  while (LBP <> 0) and (LCount < MaxStackFrames) do begin
    try
      LIP := PULONG64(LBP + 8)^;
      LBP := PULONG64(LBP)^;
    except
      Break;
    end;
    if LIP = 0 then
      Break;
    Result[LCount] := Pointer(LIP);
    Inc(LCount);
  end;
{$ELSE}
  while (LBP <> 0) and (LCount < MaxStackFrames) do begin
    try
      LIP := PDWORD(LBP + 4)^;
      LBP := PDWORD(LBP)^;
    except
      Break;
    end;
    if LIP = 0 then
      Break;
    Result[LCount] := Pointer(LIP);
    Inc(LCount);
  end;
{$ENDIF}
  SetLength(Result, LCount);
end;

constructor TStackTraceManager.Create;
begin
  inherited;
  FSymbolCache := TDictionary<NativeUInt, string>.Create;
  InstallHooks;
  TryLoadMapFile;
end;

destructor TStackTraceManager.Destroy;
begin
  UninstallHooks;
  ClearSymbolCache;
  FSymbolCache.Free;
  inherited;
end;

// === Exception Stack Trace Hook Implementations ===
{$IFDEF FPC}

procedure TStackTraceManagerFPC.InstallHooks;
begin
  FOldExceptProc := ExceptProc;
  ExceptProc := @FPExceptProc;
end;

procedure TStackTraceManagerFPC.UninstallHooks;
begin
  if Assigned(FOldExceptProc) then
    ExceptProc := FOldExceptProc;
end;

class procedure TStackTraceManagerFPC.FPExceptProc(ExceptObject: TObject; ExceptAddr: Pointer; OSException: Boolean);
var
  LData: PStackInfoData;
  LCount: DWORD;
begin
  if not Assigned(FCurrent) then
    Exit;
  LData := AllocMem(SizeOf(TStackInfoData));
  try
    LCount := RtlCaptureStackBackTrace(2, MaxStackFrames, @LData.Frames, nil);
    if LCount > 0 then
      LData.FrameCount := LCount
    else if ExceptAddr <> nil then begin
      LData.FrameCount := 1;
      except on E: Exception do FCurrent.Log(rssException, '[STACKTRACE] HandleException failed: ' + E.Message);
    end;
    if Assigned(FCurrent.FLogger) then begin
      try
        FCurrent.FLogger.HandleException(FCurrent.BuildExceptionContext(ExceptObject as Exception, LData));
      except
        on E: Exception do
          OutputDebugString(PChar('[STACKTRACE] logger failed: ' + E.Message));
      end;
    end;
  finally
    FreeMem(LData);
  end;
end;
{$ELSE}

procedure TStackTraceManagerDelphi.InstallHooks;
begin
  FOrigGetExceptionStackInfoProc := Exception.GetExceptionStackInfoProc;
  FOrigGetStackInfoStringProc := Exception.GetStackInfoStringProc;
  FOrigCleanUpStackInfoProc := Exception.CleanupStackInfoProc;
  Exception.GetExceptionStackInfoProc := ExceptionStackInfoProc;
  Exception.GetStackInfoStringProc := StackInfoStringProc;
  Exception.CleanupStackInfoProc := CleanupStackInfoProc;
  // Install VEH to capture full stack BEFORE SEH unwind
  FVEHHandle := AddVectoredExceptionHandler(1, @VEHHandler);
end;

procedure TStackTraceManagerDelphi.UninstallHooks;
begin
  if FVEHHandle <> nil then begin
    RemoveVectoredExceptionHandler(FVEHHandle);
    FVEHHandle := nil;
  end;
  Exception.GetExceptionStackInfoProc := FOrigGetExceptionStackInfoProc;
  Exception.GetStackInfoStringProc := FOrigGetStackInfoStringProc;
  Exception.CleanupStackInfoProc := FOrigCleanUpStackInfoProc;
end;

class procedure TStackTraceManagerDelphi.WriteVEHExceptionLog(ExceptionInfo: PExceptionPointers);
var
  LPath: array[0..MAX_PATH - 1] of WideChar;
  LBuffer: array[0..4095] of AnsiChar;
  LOffset: Integer;
  LFile: THandle;
  LWritten: DWORD;
  I: Integer;
begin
  if VEHLogBusy then
    Exit;
  if (ExceptionInfo = nil) or (ExceptionInfo.ExceptionRecord = nil) then
    Exit;
  if ExceptionInfo.ExceptionRecord.ExceptionCode <> EXCEPTION_ACCESS_VIOLATION then
    Exit;
  VEHLogBusy := True;
  try
    if not BuildVEHLogPath(LPath) then
      Exit;
    LOffset := 0;
    AppendLogText(LBuffer, LOffset, 'exception_code=');
    AppendLogHex(LBuffer, LOffset, ExceptionInfo.ExceptionRecord.ExceptionCode);
    AppendLogLineBreak(LBuffer, LOffset);
    AppendLogText(LBuffer, LOffset, 'exception_address=');
    AppendLogHex(LBuffer, LOffset, NativeUInt(ExceptionInfo.ExceptionRecord.ExceptionAddress));
    AppendLogLineBreak(LBuffer, LOffset);
    if ExceptionInfo.ContextRecord <> nil then begin
  {$IFDEF WIN64}
      AppendLogText(LBuffer, LOffset, 'ip=');
      AppendLogHex(LBuffer, LOffset, NativeUInt(ExceptionInfo.ContextRecord.Rip));
      AppendLogLineBreak(LBuffer, LOffset);
  {$ELSE}
      AppendLogText(LBuffer, LOffset, 'ip=');
      AppendLogHex(LBuffer, LOffset, NativeUInt(ExceptionInfo.ContextRecord.Eip));
      AppendLogLineBreak(LBuffer, LOffset);
  {$ENDIF}
    end;
    AppendLogText(LBuffer, LOffset, 'frames=');
    for I := 0 to VEHFrameCount - 1 do begin
      if I > 0 then
        AppendLogText(LBuffer, LOffset, ',');
      AppendLogHex(LBuffer, LOffset, NativeUInt(VEHFrameList[I]));
    end;
    AppendLogLineBreak(LBuffer, LOffset);
    AppendLogLineBreak(LBuffer, LOffset);
    LFile :=
        CreateFileW(
            @LPath[0],
            FILE_APPEND_DATA,
            FILE_SHARE_READ or FILE_SHARE_WRITE,
            nil,
            OPEN_ALWAYS,
            FILE_ATTRIBUTE_NORMAL,
            0
        );
    if LFile <> INVALID_HANDLE_VALUE then begin
      try
        WriteFile(LFile, LBuffer[0], LOffset, LWritten, nil);
      finally
        CloseHandle(LFile);
      end;
    end;
  finally
    VEHLogBusy := False;
  end;
end;

// VEH handler: called by Windows BEFORE stack unwind.
// Walks EBP chain from the exception context, capturing both
// return addresses and EBP values for variable capture.
class function TStackTraceManagerDelphi.VEHHandler(ExceptionInfo: PExceptionPointers): LongInt; stdcall;
var
  LBP: Pointer;
  LPrevRet: Pointer;
begin
  // Reentrancy guard: if an access violation occurs during EBP chain walk
  // inside this handler, Windows will invoke the VEH handler recursively.
  // Without this guard, the recursive invocation would also AV on the now-
  // corrupted stack, creating an infinite crash loop that kills the process
  // before Delphi's try-except has a chance to handle the original exception.
  if VEHReentrancyGuard <> 0 then
    Exit(0); // EXCEPTION_CONTINUE_SEARCH → let RTL handle it

  VEHReentrancyGuard := 1;
  try
    VEHFrameCount := 0;
    if (ExceptionInfo <> nil) and (ExceptionInfo.ContextRecord <> nil) then begin
  {$IFDEF WIN64}
      LBP := Pointer(ExceptionInfo.ContextRecord.Rbp);
  {$ELSE}
      LBP := Pointer(ExceptionInfo.ContextRecord.Ebp);
  {$ENDIF}
      // Use the instruction pointer as the return address for the innermost frame.
      // In a standard frame chain, [BP+ReturnSlot] is the return address in the CALLER,
      // NOT in the function that owns BP. We must shift by one frame so that each
      // entry's return address and BP belong to the SAME function.
      {$IFDEF WIN64}
      LPrevRet := Pointer(ExceptionInfo.ContextRecord.Rip);
      {$ELSE}
      LPrevRet := Pointer(ExceptionInfo.ContextRecord.Eip);
      {$ENDIF}
      while (LBP <> nil) and (VEHFrameCount < MaxStackFrames) do begin
        try
          VEHFrameList[VEHFrameCount] := LPrevRet;
          VEHEBPList[VEHFrameCount] := LBP;
          Inc(VEHFrameCount);
{$IFDEF WIN64}
          LPrevRet := PPointer(PByte(LBP) + 8)^;
{$ELSE}
          LPrevRet := PPointer(PByte(LBP) + 4)^;
{$ENDIF}
          LBP := PPointer(LBP)^;
        except
          Break;
        end;
      end;
    end;

    WriteVEHExceptionLog(ExceptionInfo);
    VEHDataValid := VEHFrameCount > 0;
  finally
    VEHReentrancyGuard := 0;
  end;

  Result := 0; // EXCEPTION_CONTINUE_SEARCH → let RTL handle it
end;

// GetExceptionStackInfoProc: called by Delphi RTL when an exception is raised.
// Captures the current thread's call stack and returns it as a pointer.
class function TStackTraceManagerDelphi.ExceptionStackInfoProc(P: System.PExceptionRecord): Pointer;
var
  LData: PStackInfoData;
  LCount: DWORD;
{$IFDEF WIN32}
  LBP: Pointer;
  LFrameBP: Pointer;
  LMatchIdx: Integer;
{$ENDIF}
  I: Integer;
begin
  Result := nil;
  LData := AllocMem(SizeOf(TStackInfoData));
  try
    // Use VEH-captured data (before unwind) if available.
    // VEH handler already walks from the exception context's EBP,
    // so frames start at user code — no filtering needed.
    if VEHDataValid and (VEHFrameCount > 0) then begin
      LData.FrameCount := VEHFrameCount;
      for I := 0 to VEHFrameCount - 1 do begin
        LData.Frames[I] := VEHFrameList[I];
        if I < MaxStackFrames then
          LData.FrameEBP[I] := VEHEBPList[I]
        else
          LData.FrameEBP[I] := nil;
      end;
      // Clear VEH data for this thread
      VEHDataValid := False;
      VEHFrameCount := 0;
      Result := LData;
      // Notify logger (same as non-VEH path below)
      if Assigned(FCurrent) and Assigned(FCurrent.FLogger) then begin
        try
          FCurrent.FLogger.HandleException(FCurrent.BuildExceptionContext(P.ExceptObject, Result));
        except
          on E: Exception do
            OutputDebugString(PChar('[STACKTRACE] VEH logger failed: ' + E.Message));
        end;
      end;
      Exit;
    end;

    LCount := RtlCaptureStackBackTrace(0, MaxStackFrames, @LData.Frames, nil);
    if LCount > 0 then begin
      LData.FrameCount := LCount;
{$IFDEF WIN32}
      // Walk frame chain to capture EBP for each captured frame
      asm
        mov eax, ebp
        mov LBP, eax
      end;
      // Walk EBP chain dynamically instead of blindly skipping 2 frames.
      // Validate each frame by checking if its return address ([EBP+4])
      // falls within a reasonable user-code address range.
      LFrameBP := LBP;
      LMatchIdx := 1;
      while (LFrameBP <> nil) and (LMatchIdx < 10) do begin
        if LMatchIdx >= 2 then begin
          try
            var LRetAddr := PPointer(PByte(LFrameBP) + 4)^;
            if (DWORD(LRetAddr) > $400000) and (DWORD(LRetAddr) < $80000000) then
              Break; // valid user code return address -> aligned
          except
            LFrameBP := nil;
            Break;
          end;
        end;
        try
          LFrameBP := PPointer(LFrameBP)^;
        except
          LFrameBP := nil;
        end;
        if LFrameBP <> nil then
          Inc(LMatchIdx);
      end;
      // If dynamic alignment failed, fall back to 2-frame skip
      if LFrameBP = nil then begin
        LFrameBP := LBP;
        try
          LFrameBP := PPointer(LFrameBP)^;
        except
          LFrameBP := nil;
        end;
        try
          LFrameBP := PPointer(LFrameBP)^;
        except
          LFrameBP := nil;
        end;
        LMatchIdx := 1;
      end;
      while (LFrameBP <> nil) and (LMatchIdx < Integer(LCount)) do begin
        LData.FrameEBP[LMatchIdx] := LFrameBP;
        Inc(LMatchIdx);
        try
          LFrameBP := PPointer(LFrameBP)^;
        except
          Break;
        end;
      end;
{$ENDIF}

      Result := LData;
    end
    else begin
      FreeMem(LData);
      LData := nil;
    end;
    if Assigned(FCurrent) and Assigned(FCurrent.FLogger) then begin
      try
        FCurrent.FLogger.HandleException(FCurrent.BuildExceptionContext(P.ExceptObject, Result));
      except
        on E: Exception do
          OutputDebugString(PChar('[STACKTRACE] logger failed: ' + E.Message));
      end;
    end;
  except
    if LData <> nil then
      FreeMem(LData);
  end;
end;

// CleanUpStackInfoProc: called by Delphi RTL to free the stack data
// returned by GetExceptionStackInfoProc.
class procedure TStackTraceManagerDelphi.CleanupStackInfoProc(Info: Pointer);
begin
  if Info <> nil then
    FreeMem(Info);
end;
{$ENDIF}

// Look up local variable definitions for a given symbol index.
procedure TStackTraceManager.SetLocalVarData(const AData: TArray<TLocalVarEntry>);
begin
  FLocalVarData := Copy(AData);
end;

function TStackTraceManager.FindLocalVars(SymIdx: Integer): TArray<TLocalVarInfo>;
var
  I: Integer;
begin
  for I := 0 to High(FLocalVarData) do
    if FLocalVarData[I].SymIdx = SymIdx then
      Exit(FLocalVarData[I].Vars);
  Result := nil;
end;

// Parse function prologue to determine total stack frame size and
// locate register parameter spill slots (created by Delphi compiler for
// register calling convention: EAX, EDX, ECX spilled to [EBP+disp8]).
// Typical register prologue:
// 55           PUSH EBP
// 8B EC        MOV EBP, ESP
// 89 4D FC     MOV [EBP-4], ECX    ← ECX spill
// 89 55 F8     MOV [EBP-8], EDX    ← EDX spill
// 89 45 F4     MOV [EBP-12], EAX   ← EAX spill
// 83 EC 20     SUB ESP, $20
function TStackTraceManager.ReadFunctionPrologue(
    AFuncAddr: Pointer;
    out FrameSize: Integer;
    out RegisterSpill: TArray<SmallInt>
): Boolean;
var
  P: PByte;
  LModRM, LReg: Byte;
  LOffset: Integer;
  LScanCount: Integer;
begin
  Result := False;
  FrameSize := 0;
  SetLength(RegisterSpill, 3);
  RegisterSpill[0] := -1; // EAX  (Intel Reg=000)
  RegisterSpill[1] := -1; // ECX  (Intel Reg=001)
  RegisterSpill[2] := -1; // EDX  (Intel Reg=010)
  if AFuncAddr = nil then
    Exit;
  try
    P := AFuncAddr;
{$IFDEF WIN64}
    // Win64 Delphi frames commonly start with SUB RSP,N, optionally with
    // PUSH/MOV/LEA RBP setup. We only need the local frame size here; register
    // parameter home slots are not modeled by the legacy local-var metadata.
    LScanCount := 0;
    while LScanCount < 128 do begin
      Inc(LScanCount);
      if P[0] = $55 then begin // PUSH RBP
        Inc(P, 1);
        Continue;
      end;
      if (P[0] = $48) and (P[1] = $8B) and (P[2] = $EC) then begin // MOV RBP,RSP
        Inc(P, 3);
        Continue;
      end;
      if (P[0] = $48) and (P[1] = $89) and (P[2] = $E5) then begin // MOV RBP,RSP
        Inc(P, 3);
        Continue;
      end;
      if (P[0] = $48) and (P[1] = $8D) and (P[2] = $6C) and (P[3] = $24) then begin // LEA RBP,[RSP+disp8]
        Inc(P, 5);
        Continue;
      end;
      if (P[0] = $48) and (P[1] = $83) and (P[2] = $EC) then begin // SUB RSP,imm8
        FrameSize := P[3];
        Result := True;
        Exit;
      end;
      if (P[0] = $48) and (P[1] = $81) and (P[2] = $EC) then begin // SUB RSP,imm32
        FrameSize := Integer(P[3]) or (Integer(P[4]) shl 8) or (Integer(P[5]) shl 16) or (Integer(P[6]) shl 24);
        Result := True;
        Exit;
      end;
      case P[0] of
        $40..$4F: Inc(P, 1); // REX prefix; inspect the opcode on the next pass
        $50..$5F: Inc(P, 1); // PUSH/POP reg
        $90: Inc(P, 1); // NOP
        $E8: Inc(P, 5); // CALL rel32
        $EB: Inc(P, 2); // JMP short
        $C3: Break; // RET before any stack allocation
      else
        Inc(P, 1);
      end;
    end;
    FrameSize := 0;
    Result := True;
{$ELSE}
    // PUSH EBP
    if P[0] <> $55 then
      Exit;
    Inc(P, 1);
    // MOV EBP, ESP: $8B EC or $89 E5
    if (P[0] = $8B) and (P[1] = $EC) then
      Inc(P, 2)
    else if (P[0] = $89) and (P[1] = $E5) then
      Inc(P, 2)
    else
      Exit;
    // Scan for register spills: MOV [EBP+disp], EAX/EDX/ECX
    // $89 ModRM disp8  -> 3 bytes
    // $89 ModRM disp32 -> 6 bytes
    LScanCount := 0;
    while (LScanCount < 128) do begin
      Inc(LScanCount);
      // SUB ESP, N: end of spill scan
      if (P[0] = $83) and (P[1] = $EC) then begin
        FrameSize := ShortInt(P[2]);
        if FrameSize < 0 then
          FrameSize := FrameSize + 256;
        Result := True;
        Exit;
      end;
      if (P[0] = $81) and (P[1] = $EC) then begin
        FrameSize := P[2] or (P[3] shl 8) or (P[4] shl 16) or (P[5] shl 24);
        Result := True;
        Exit;
      end;
      // MOV [EBP+disp], reg
      if P[0] = $89 then begin
        LModRM := P[1];
        LReg := (LModRM shr 3) and 7; // reg field from ModRM
        // Check ModRM: Mod must be 01 (disp8) or 10 (disp32), R/M must be 101 (EBP)
        if (LModRM and $C7) = $45 then begin
          if (LModRM and $C0) = $40 then begin
            // Mod=01 (disp8): 3 bytes
            LOffset := ShortInt(P[2]);
            if LReg <= 2 then
              RegisterSpill[LReg] := LOffset;
            Inc(P, 3);
            Continue;
          end
          else if (LModRM and $C0) = $80 then begin
            // Mod=10 (disp32): 6 bytes
            LOffset := P[2] or (P[3] shl 8) or (P[4] shl 16) or (P[5] shl 24);
            if LReg <= 2 then
              RegisterSpill[LReg] := LOffset;
            Inc(P, 6);
            Continue;
          end;
        end;
      end;
      // Not a recognized spill or SUB - skip full instruction length
      // to avoid misaligned parsing (XOR reg32 = 2B, PUSH imm32 = 5B, etc.)
      case P[0] of
        $50..$5F: Inc(P, 1); // PUSH/POP reg
        $6A: Inc(P, 2); // PUSH imm8
        $68: Inc(P, 5); // PUSH imm32
        $B0..$B7: Inc(P, 2); // MOV reg8, imm8
        $B8..$BF: Inc(P, 5); // MOV reg32, imm32
        $33, $31, $2B, $03, $01, $09, $21, $29, $39, $85, $8D, $8B: Inc(P, 2); // Common 2B ALU/MOV/LEA
        $90: Inc(P, 1); // NOP
        $D9, $DD: Inc(P, 2); // FPU op (FLD, FSTP, etc.)
        $E8: Inc(P, 5); // CALL rel32
        $EB: Inc(P, 2); // JMP short
        $F2, $F3: Inc(P, 1); // REP prefix
        $0F: Inc(P, 3); // 2-byte opcode + ModRM (pessimistic)
      else
        // Default: skip based on ModRM displacement bytes
        case (P[1] shr 6) of
          0: Inc(P, 2); // Mod=00: register or [reg]
          1: Inc(P, 3); // Mod=01: [reg+disp8]
          2: Inc(P, 6); // Mod=10: [reg+disp32]
        else
          Inc(P, 2); // Mod=11: register direct
        end;
      end;
    end;
    // No SUB ESP found but spills may have been parsed
    FrameSize := 0;
    Result := True;
{$ENDIF}
  except
    Result := False;
  end;
end;

const
  TypeKindStackSizes: array[0..20] of Byte = (
      0, // 0  tkUnknown
      4, // 1  tkInteger
      1, // 2  tkChar
      4, // 3  tkEnumeration
      4, // 4  tkFloat
      0, // 5  tkString (ShortString — handled specially)
      0, // 6  tkSet
      SizeOf(Pointer), // 7  tkClass
      0, // 8  tkMethod
      2, // 9  tkWChar
      SizeOf(Pointer), // 10 tkLString
      SizeOf(Pointer), // 11 tkWString
      0, // 12 tkVariant
      0, // 13 tkArray
      0, // 14 tkRecord
      0, // 15 tkInterface
      8, // 16 tkInt64
      0, // 17 tkDynArray
      SizeOf(Pointer), // 18 tkUString
      0, // 19 tkClassRef
      SizeOf(Pointer) // 20 tkPointer
  );

// For register conventions, register params use the spill slot if available
// (compiler spills EAX/EDX/ECX to [EBP+disp] in the prologue).
// RegisterSpill[0]=EAX, [1]=ECX, [2]=EDX  (from ModRM reg field encoding);
// -1 means not spilled.
// Delphi register calling convention: Param[0]=EAX, Param[1]=EDX, Param[2]=ECX.
// So the mapping from param index to RegisterSpill index is: [0, 2, 1].
function TStackTraceManager.ComputeVarOffsets(
    const AVars: TArray<TLocalVarInfo>;
    FrameSize, AParamCount, ACallConv: Integer;
    AIsMethod: Boolean;
    const RegisterSpill: TArray<SmallInt>;
    out Offsets: TArray<SmallInt>
): Boolean;
var
  I, LSize, LAlign, LDist: Integer;
  LRegisterParamCount: Integer;
  LRegIdx: Integer;
  LParamToReg: array[0..2] of Integer;
  LMethodShift: Integer;
begin
  LParamToReg[0] := 0; // Param[0] → EAX (Reg 0)
  LParamToReg[1] := 2; // Param[1] → EDX (Reg 2)
  LParamToReg[2] := 1; // Param[2] → ECX (Reg 1)
  SetLength(Offsets, Length(AVars));
  if Length(AVars) = 0 then
    Exit(True);

  // For ccRegister, first 3 params are in EAX/EDX/ECX (may have stack spills).
  // All other conventions put all params on stack.
  case ACallConv of
    CallConv_Register: LRegisterParamCount := 3;
    CallConv_StdCall, CallConv_CDecl, CallConv_CDeclVarArgs, CallConv_SafeCall, CallConv_WinApi, CallConv_Pascal:
      LRegisterParamCount := 0;
  else
    LRegisterParamCount := 0;
  end;
  // For methods, EAX (Reg[0]) holds Self, so the first real parameter starts at
  // Reg[1] (ECX). Shift the register param index by +1 to skip Self.
  if AIsMethod and (LRegisterParamCount > 0) then
    LMethodShift := 1
  else
    LMethodShift := 0;
  // First AParamCount entries are parameters
  var LParamDist := 8;
  for I := 0 to AParamCount - 1 do begin
    // If TD32-derived (v13+) location info is available, use it directly.
    if AVars[I].IsRegister then begin
      Offsets[I] := 0; // register-optimized param
      Continue;
    end;
    if AVars[I].StackOffset <> 0 then begin
      Offsets[I] := AVars[I].StackOffset; // compiler-accurate offset
      Continue;
    end;
    // Fall back to heuristic for MAPDATA < v13 (no TD32 location data).
    if AVars[I].MaxLen > 0 then
      LSize := AVars[I].MaxLen
    else if AVars[I].TypeKind = Byte(Ord(tkString)) then
      LSize := 256
    else if AVars[I].TypeKind = 253 then
      LSize := 10 // Extended (10 bytes on Win32)
    else if AVars[I].TypeKind > Byte(High(TypeKindStackSizes)) then
      LSize := SizeOf(Pointer)
    else
      LSize := TypeKindStackSizes[AVars[I].TypeKind];
    if LSize <= 0 then
      LSize := SizeOf(Pointer);
    if I + LMethodShift < LRegisterParamCount then begin
      // Register-optimized parameter: map to correct spill slot
      if I + LMethodShift < Length(LParamToReg) then
        LRegIdx := LParamToReg[I + LMethodShift]
      else
        LRegIdx := I + LMethodShift;
      if (LRegIdx < Length(RegisterSpill)) and (RegisterSpill[LRegIdx] >= 0) then
        Offsets[I] := RegisterSpill[LRegIdx]
      else
        Offsets[I] := 0; // not spilled → not readable
    end
    else begin
      // Stack param: minimum alignment is SizeOf(Pointer) (4 on Win32, 8 on Win64)
      LAlign := LSize;
      if LAlign < SizeOf(Pointer) then
        LAlign := SizeOf(Pointer);
      LParamDist := ((LParamDist + LAlign - 1) div LAlign) * LAlign;
      Offsets[I] := LParamDist;
      LParamDist := LParamDist + LSize;
    end;
  end;

  // Remaining entries are local variables (BP-pointer, BP-2*pointer, ...).
  LDist := SizeOf(Pointer);
  for I := AParamCount to High(AVars) do begin
    // If TD32-derived (v13+) location info is available, use it directly.
    if AVars[I].IsRegister then begin
      Offsets[I] := 0; // register-optimized local
      Continue;
    end;
    if AVars[I].StackOffset <> 0 then begin
      Offsets[I] := AVars[I].StackOffset; // compiler-accurate offset
      Continue;
    end;
    // Fall back to heuristic for MAPDATA < v13 (no TD32 location data).
    if AVars[I].MaxLen > 0 then
      LSize := AVars[I].MaxLen
    else if AVars[I].TypeKind = Byte(Ord(tkString)) then
      LSize := 256
    else if AVars[I].TypeKind = 253 then
      LSize := 10 // Extended
    else if AVars[I].TypeKind > Byte(High(TypeKindStackSizes)) then
      LSize := SizeOf(Pointer)
    else
      LSize := TypeKindStackSizes[AVars[I].TypeKind];
    if LSize <= 0 then
      LSize := SizeOf(Pointer);
    // Use pointer-sized alignment so Win64 local slots do not overlap pointer values.
    LAlign := LSize;
    if LAlign < SizeOf(Pointer) then
      LAlign := SizeOf(Pointer);
    if LAlign > SizeOf(Pointer) then
      LAlign := SizeOf(Pointer);
    LDist := ((LDist + LAlign - 1) div LAlign) * LAlign;
    Offsets[I] := -LDist;
    LDist := LDist + LSize;
  end;

  // Verify: total local area fits within frame.
  // If not, variables beyond frame size are register-optimized — mark offset=0.
  // Skip vars with TD32-derived data — their offsets are compiler-accurate.
  if (FrameSize > 0) and (AParamCount < Length(AVars)) then begin
    var LTotalLocal := LDist - SizeOf(Pointer);
    if LTotalLocal > FrameSize then begin
      // Walk backwards: mark overflow locals as register (offset=0)
      for var J := High(AVars) downto AParamCount do begin
        // Skip TD32-derived vars — their offsets are already correct.
        if AVars[J].IsRegister or (AVars[J].StackOffset <> 0) then
          Continue;
        if (-Offsets[J]) > FrameSize then
          Offsets[J] := 0 // register-optimized local
        else
          Break; // remaining fit within frame
      end;
    end;
  end;
  Result := True;
end;

// Check if a pointer looks like a valid VMT (virtual method table).
function IsValidVMT(P: Pointer): Boolean;
var
  LMI: TMemoryBasicInformation;
begin
  if P = nil then
    Exit(False);
  if VirtualQuery(P, LMI, SizeOf(LMI)) <> SizeOf(LMI) then
    Exit(False);
  if LMI.State <> MEM_COMMIT then
    Exit(False);
  if (LMI.Protect and (PAGE_READONLY or PAGE_READWRITE or PAGE_EXECUTE_READ or PAGE_EXECUTE_READWRITE)) = 0 then
    Exit(False);
  Result := True;
end;

// Safely get the class name of an object pointer using VirtualQuery + try/except.
function TStackTraceManager.TryGetObjectClassName(Obj: Pointer): string;
var
  LClass: TClass;
  LVMT: Pointer;
begin
  if Obj = nil then
    Exit('nil');
  // Check the object memory itself is valid
  if not IsValidVMT(Obj) then
    Exit('<invalid>');
  try
    LClass := TClass(Obj);
    // Check that VMT pointer looks valid
    LVMT := PPointer(LClass)^;
    if not IsValidVMT(LVMT) then
      Exit('<corrupt vmt>');
    Result := LClass.ClassName;
    if Result = '' then
      Result := '<unnamed class>';
  except
    Result := '<invalid object>';
  end;
end;

// Safely read a string value from a pointer using try/except.
// The string header format: [Length: Integer] at offset -4, [RefCnt: Integer] at offset -8,
// [ElemSize: Word] at offset -10, [CodePage: Word] at offset -12.
function TStackTraceManager.TryGetStringValue(P: Pointer): string;
var
  LLen: Integer;
begin
  if P = nil then
    Exit('""');
  try
    // Read length from string header (at offset -4 from the string data pointer)
    LLen := PInteger(PByte(P) - 4)^;
    if LLen < 0 then
      Exit('<corrupt string>');
    if LLen > MaxCapturedStringChars then
      Exit(Format('<string too long len=%d>', [LLen]));
    SetLength(Result, LLen);
    if LLen > 0 then begin
      Move(PByte(P)^, PByte(PChar(Result))^, LLen * SizeOf(Char));
    end;
    Result := '"' + Result + '"';
  except
    Result := '<invalid string>';
  end;
end;

// Read a typed value from a stack address with type-specific safety checks.
function TStackTraceManager.ReadStackVarValue(Addr: Pointer; TypeKind: Byte): string;
var
  LPtr: Pointer;
  LVal32: Integer;
  LVal64: Int64;
begin
  if Addr = nil then
    Exit('<null>');
  try
    case TypeKind of
      Ord(tkInteger): begin
        LVal32 := PInteger(Addr)^;
        Result := Format('$%.8x (%d)', [LVal32, LVal32]);
      end;
      Ord(tkInt64): begin
        LVal64 := PInt64(Addr)^;
        Result := Format('$%.16x (%d)', [LVal64, LVal64]);
      end;
      Ord(tkEnumeration): begin
        LVal32 := PInteger(Addr)^;
        if LVal32 = 0 then
          Result := 'False'
        else if LVal32 = 1 then
          Result := 'True'
        else
          Result := Format('$%.8x', [LVal32]);
      end;
      Ord(tkFloat): begin
        // Single (4 bytes) — the only type that maps to tkFloat after our refactoring
        LVal32 := PInteger(Addr)^;
        if LVal32 = 0 then
          Result := '0.0'
        else
          Result := Format('$%.8x', [LVal32]);
      end;
      Ord(tkChar): Result := Format('''%s'' ($%.2x)', [string(PAnsiChar(Addr)), PByte(Addr)^]);
      Ord(tkWChar): Result := Format('''%s'' ($%.4x)', [PWideChar(Addr), PWord(Addr)^]);
      Ord(tkClass): begin
        LPtr := PPointer(Addr)^;
        Result := TryGetObjectClassName(LPtr);
      end;
      Ord(tkUString), Ord(tkLString), Ord(tkWString): begin
        LPtr := PPointer(Addr)^;
        Result := TryGetStringValue(LPtr);
      end;
      Ord(tkString): begin
        // ShortString: first byte is length, followed by characters
        LVal32 := PByte(Addr)^;
        Result := Format('<shortstring len=%d>', [LVal32]);
      end;
      Ord(tkPointer): begin
        LPtr := PPointer(Addr)^;
        if LPtr = nil then
          Result := 'nil'
        else
          Result := Format('$%p', [LPtr]);
      end;
    else
      Result := '<unsupported type>';
    end;
  except
    Result := '<access violation>';
  end;
end;



// StackInfoStringProc: converts raw stack data into a human-readable
// string. Uses the embedded map data for symbol resolution
// and displays local variable values when available.
class function TStackTraceManager.StackInfoStringProc(Info: Pointer): string;
var
  LData: PStackInfoData;
  I, J: Integer;
  LFrame: TFrameSnapshot;
begin
  Result := '';
  if Info = nil then
    Exit;
  LData := PStackInfoData(Info);
  for I := 0 to LData.FrameCount - 1 do begin
    if LData.Frames[I] = nil then
      Break;
    if Result <> '' then
      Result := Result + LineBrk;
    LFrame := FCurrent.GetFrameSnapshot(NativeUInt(LData.Frames[I]), LData.FrameEBP[I]);
    Result := Result + Format('  %p %s', [LData.Frames[I], LFrame.FuncName]);
    if LFrame.SourceInfo <> '' then
      Result := Result + ' ' + LFrame.SourceInfo;
    if FCaptureVariables then begin
      for J := 0 to High(LFrame.Params) do
        Result := Result + LineBrk + Format('    %s = %s', [LFrame.Params[J].Name, LFrame.Params[J].Value]);
      for J := 0 to High(LFrame.Locals) do
        Result := Result + LineBrk + Format('    %s = %s', [LFrame.Locals[J].Name, LFrame.Locals[J].Value]);
    end;
  end;
end;

class function TStackTraceManager.GetStackString(Info: Pointer): string;
begin
  Result := StackInfoStringProc(Info);
end;

function TStackTraceManager.GetFrameSnapshot(VA: NativeUInt; AEBP: Pointer): TFrameSnapshot;
var
  L, H, M: Integer;
  LPrefAddr: UInt64;
  LSymIdx: Integer;
  LLocals: TArray<TLocalVarInfo>;
  LOffsets: TArray<SmallInt>;
  LFrameSize: Integer;
  LFuncAddr: Pointer;
  I: Integer;
  LVarAddr: Pointer;
  LParamCount: Integer;
  LCallConv: Byte;
  LIsMethod: Boolean;
  LOverlayName, LOverlaySource: string;
  LOverlayLine: Integer;
begin
  Result.Address := VA;
  Result.FuncName := '';
  Result.SourceInfo := '';
  Result.Params := nil;
  Result.Locals := nil;

  // Priority 1: 查询叠加符号 (热补丁新增函数)
  if (FOverlayProvider <> nil)
      and FOverlayProvider.ResolveOverlaySymbol(VA, LOverlayName, LOverlaySource, LOverlayLine) then
  begin
    Result.FuncName := LOverlayName;
    if LOverlaySource <> '' then
      Result.SourceInfo := Format('[%s:%d]', [LOverlaySource, LOverlayLine]);
    // 叠加函数不支持局部变量捕获, 直接返回
    Exit;
  end;

  if (FMapLoaded <> 1) or (FModuleBase = 0) then
    Exit;

  LPrefAddr := RuntimeAddrToMapAddr(VA);
  if LPrefAddr = 0 then
    Exit;

  L := 0;
  H := Length(FSymEntries) - 1;
  M := -1;
  while L <= H do begin
    var LMid := (L + H) shr 1;
    if FSymEntries[LMid].Addr <= LPrefAddr then begin
      M := LMid;
      L := LMid + 1;
    end
    else
      H := LMid - 1;
  end;

  if M < 0 then
    Exit;
  LSymIdx := M;

  var LOff := LPrefAddr - FSymEntries[M].Addr;
  if LOff > $10000 then
    Exit;

  if LOff > 0 then
    Result.FuncName := ExpandSymbolName(M) + '+$' + IntToHex(LOff, 1)
  else
    Result.FuncName := ExpandSymbolName(M);

  var LMapOffset := LPrefAddr;
  L := 0;
  H := Length(FLineEntries) - 1;
  var LLineIdx := -1;
  while L <= H do begin
    var LMid2 := (L + H) shr 1;
    if FLineEntries[LMid2].Addr <= LMapOffset then begin
      LLineIdx := LMid2;
      L := LMid2 + 1;
    end
    else
      H := LMid2 - 1;
  end;
  if (LLineIdx >= 0) and (LMapOffset - FLineEntries[LLineIdx].Addr < $10000) then
    Result.SourceInfo := Format('[%s:%d]', [FSourcePaths[FLineEntries[LLineIdx].FileIdx], FLineEntries[LLineIdx].Line]);

  if not FCaptureVariables then
    Exit;

  LLocals := FindLocalVars(LSymIdx);
  if Length(LLocals) = 0 then
    Exit;
  if AEBP = nil then
    Exit;

  LFuncAddr := Pointer(MapAddrToRuntimeAddr(FSymEntries[LSymIdx].Addr));

  var LRegisterSpill: TArray<SmallInt>;
  if not ReadFunctionPrologue(LFuncAddr, LFrameSize, LRegisterSpill) then
    Exit;

  LParamCount := 0;
  LCallConv := 0;
  LIsMethod := False;
  for var K := 0 to High(FLocalVarData) do
    if FLocalVarData[K].SymIdx = LSymIdx then begin
      LParamCount := FLocalVarData[K].ParamCount;
      LCallConv := FLocalVarData[K].CallConv;
      LIsMethod := FLocalVarData[K].IsMethod;
      Break;
    end;

  if not ComputeVarOffsets(LLocals, LFrameSize, LParamCount, LCallConv, LIsMethod, LRegisterSpill, LOffsets) then
    Exit;

  SetLength(Result.Params, LParamCount);
  SetLength(Result.Locals, Length(LLocals) - LParamCount);

  for I := 0 to High(LLocals) do begin
    if I < LParamCount then begin
      if (LOffsets[I] = 0) and (I < LParamCount) then begin
        Result.Params[I].Value := '<register>';
        Result.Params[I].TypeKind := LLocals[I].TypeKind;
        Result.Params[I].TypeInfo := LLocals[I].TypeInfo;
        Result.Params[I].Size := LLocals[I].GetTypeSize;
        Result.Params[I].Addr := nil;
        Result.Params[I].IsRegister := True;
      end
      else begin
        LVarAddr := Pointer(PByte(AEBP) + LOffsets[I]);
        Result.Params[I].Value := ReadStackVarValue(LVarAddr, LLocals[I].TypeKind);
        Result.Params[I].TypeKind := LLocals[I].TypeKind;
        Result.Params[I].TypeInfo := LLocals[I].TypeInfo;
        Result.Params[I].Size := LLocals[I].GetTypeSize;
        Result.Params[I].Addr := LVarAddr;
        Result.Params[I].IsRegister := False;
      end;
      Result.Params[I].Name := LLocals[I].Name;
    end
    else begin
      if LOffsets[I] = 0 then begin
        // Register-optimized local: not on stack
        Result.Locals[I - LParamCount].Value := '<register>';
        Result.Locals[I - LParamCount].Addr := nil;
        Result.Locals[I - LParamCount].IsRegister := True;
      end
      else begin
        LVarAddr := Pointer(PByte(AEBP) + LOffsets[I]);
        Result.Locals[I - LParamCount].Value := ReadStackVarValue(LVarAddr, LLocals[I].TypeKind);
        Result.Locals[I - LParamCount].Addr := LVarAddr;
        Result.Locals[I - LParamCount].IsRegister := False;
      end;
      Result.Locals[I - LParamCount].Name := LLocals[I].Name;
      Result.Locals[I - LParamCount].TypeKind := LLocals[I].TypeKind;
      Result.Locals[I - LParamCount].TypeInfo := LLocals[I].TypeInfo;
      Result.Locals[I - LParamCount].Size := LLocals[I].GetTypeSize;
    end;
  end;
end;

class function TStackTraceManager.BuildExceptionContext(AException: Exception; AData: Pointer): TExceptionContext;
var
  LData: PStackInfoData;
  I: Integer;
begin
  Result.ExceptionObj := AException;
  Result.CaptureVariables := FCaptureVariables;
  Result.Frames := nil;
  if (AData = nil) or (not Assigned(FCurrent)) then
    Exit;
  LData := PStackInfoData(AData);
  SetLength(Result.Frames, LData.FrameCount);
  for I := 0 to LData.FrameCount - 1 do begin
    if LData.Frames[I] = nil then begin
      SetLength(Result.Frames, I);
      Break;
    end;
    Result.Frames[I] := FCurrent.GetFrameSnapshot(NativeUInt(LData.Frames[I]), LData.FrameEBP[I]);
  end;
end;

{$IFNDEF FPC}

{ TStackTracer }

class function TStackTracer.EnsureSymbols: Boolean;
var
  LEntries: TArray<TQProfileMapEntry>;
  I: Integer;
begin
  Result := Length(FSymbols) > 0;
  if Result then
    Exit;

  FMapLoadError := '';
  if TStackTraceManager.Current = nil then begin
    FMapLoadError := 'stacktrace_manager_not_initialized';
    Exit(False);
  end;

  LEntries := TStackTraceManager.Current.EnumerateFunctions(nil);
  if Length(LEntries) = 0 then begin
    if TStackTraceManager.Current.GetMapLoadStatus <> 1 then
      FMapLoadError := 'map symbols not loaded'
    else
      FMapLoadError := 'map contains no functions';
    Exit(False);
  end;

  SetLength(FSymbols, Length(LEntries));
  for I := 0 to High(LEntries) do begin
    FSymbols[I].Name := LEntries[I].Name;
    FSymbols[I].Address := NativeUInt(LEntries[I].Address);
  end;
  Result := True;
end;

class function TStackTracer.LoadTextRange: Boolean;
var
  LBase: HMODULE;
  LDos: PImageDosHeader;
  LNT: PImageNtHeaders;
  LSection: PImageSectionHeader;
  LOptionalMagic: Word;
  I: Integer;
begin
  Result := False;
  FImageBase := NativeUInt(GetModuleHandle(nil));
  FTextStart := 0;
  FTextSize := 0;

  LBase := HMODULE(FImageBase);
  if LBase = 0 then begin
    FLastError := 'module_not_found';
    Exit;
  end;

  try
    LDos := PImageDosHeader(LBase);
    if LDos.e_magic <> IMAGE_DOS_SIGNATURE then begin
      FLastError := 'invalid_dos_header';
      Exit;
    end;

    LNT := PImageNtHeaders(PByte(LBase) + LDos._lfanew);
    if LNT.Signature <> IMAGE_NT_SIGNATURE then begin
      FLastError := 'invalid_nt_header';
      Exit;
    end;

    LOptionalMagic := PWord(@LNT.OptionalHeader)^;
    if (LOptionalMagic <> $10B) and (LOptionalMagic <> $20B) then begin
      FLastError := 'unsupported_optional_header';
      Exit;
    end;

    LSection := PImageSectionHeader(PByte(@LNT.OptionalHeader) + LNT.FileHeader.SizeOfOptionalHeader);
    for I := 0 to LNT.FileHeader.NumberOfSections - 1 do begin
      if (LSection.Name[0] in [Ord('.'), Ord('C')])
          and (LSection.Name[1] = Ord('t'))
          and (LSection.Name[2] = Ord('e'))
          and (LSection.Name[3] = Ord('x'))
          and (LSection.Name[4] = Ord('t')) then
      begin
        FTextStart := NativeUInt(LBase) + LSection.VirtualAddress;
        FTextSize := LSection.Misc.VirtualSize;
        Exit(FTextSize > 0);
      end;
      Inc(LSection);
    end;

    FLastError := 'text_section_not_found';
  except
    on E: Exception do
      FLastError := 'text_section_error: ' + E.Message;
  end;
end;

class function TStackTracer.ResolveSymbolStart(AAddr: NativeUInt): NativeUInt;
var
  L, H, M: Integer;
  LBest: Integer;
begin
  Result := 0;
  if not EnsureSymbols then
    Exit;

  L := 0;
  H := Length(FSymbols) - 1;
  LBest := -1;
  while L <= H do begin
    M := (L + H) shr 1;
    if FSymbols[M].Address <= AAddr then begin
      LBest := M;
      L := M + 1;
    end
    else
      H := M - 1;
  end;

  if (LBest >= 0) and (AAddr - FSymbols[LBest].Address <= $10000) then
    Result := FSymbols[LBest].Address;
end;

class function TStackTracer.ResolveSymbolName(AAddr: NativeUInt): string;
var
  L, H, M: Integer;
begin
  Result := Format('$%x', [AAddr]);
  if not EnsureSymbols then
    Exit;

  L := 0;
  H := Length(FSymbols) - 1;
  while L <= H do begin
    M := (L + H) shr 1;
    if FSymbols[M].Address = AAddr then
      Exit(FSymbols[M].Name);
    if FSymbols[M].Address < AAddr then
      L := M + 1
    else
      H := M - 1;
  end;
end;
class function TStackTracer.ResolveAddr(AAddr: NativeUInt): string;
var
  LStart: NativeUInt;
begin
  LStart := ResolveSymbolStart(AAddr);
  if LStart = 0 then
    Exit(Format('$%x', [AAddr]));

  Result := ResolveSymbolName(LStart);
  if AAddr > LStart then
    Result := Result + Format('+$%x', [AAddr - LStart]);
end;

class function TStackTracer.FindFuncAddr(const AName: string): NativeUInt;
var
  I: Integer;
  LQuery: string;
  LMethod: string;
  LDot: Integer;

  function HasNameSuffix(const ASymbol, ASuffix: string): Boolean;
  var
    LStart: Integer;
  begin
    Result := False;
    if (ASymbol = '') or (ASuffix = '') or (Length(ASymbol) <= Length(ASuffix)) then
      Exit;
    LStart := Length(ASymbol) - Length(ASuffix) + 1;
    Result := SameText(Copy(ASymbol, LStart, MaxInt), ASuffix) and (ASymbol[LStart - 1] = '.');
  end;

begin
  Result := 0;
  FLastError := '';
  LQuery := Trim(AName);
  if LQuery = '' then
    Exit;

  if not EnsureSymbols then begin
    FLastError := 'map_not_loaded';
    Exit;
  end;

  for I := 0 to High(FSymbols) do
    if SameText(FSymbols[I].Name, LQuery) then
      Exit(FSymbols[I].Address);

  for I := 0 to High(FSymbols) do
    if HasNameSuffix(FSymbols[I].Name, LQuery) then
      Exit(FSymbols[I].Address);

  LDot := LastDelimiter('.', LQuery);
  if LDot > 0 then
    LMethod := Copy(LQuery, LDot + 1, MaxInt)
  else
    LMethod := LQuery;

  for I := 0 to High(FSymbols) do
    if HasNameSuffix(FSymbols[I].Name, LMethod) then
      Exit(FSymbols[I].Address);
end;

class function TStackTracer.FormatCallGraphAddr(AAddr: NativeUInt): string;
begin
  if SizeOf(Pointer) = SizeOf(UInt64) then
    Result := Format('%.16x', [UInt64(AAddr)])
  else
    Result := Format('%.8x', [Cardinal(AAddr)]);
end;

class function TStackTracer.ResolveRelativeCallTarget(ACallSite: NativeUInt; ARel32: Integer): NativeUInt;
var
  LNext: NativeUInt;
begin
  LNext := ACallSite + 5;
  if ARel32 >= 0 then
    Result := LNext + NativeUInt(ARel32)
  else
    Result := LNext - NativeUInt(-Int64(ARel32));
end;

class procedure TStackTracer.ClearEdgeIndexes;
var
  LList: TList<Integer>;
begin
  if FCallerIndex <> nil then begin
    for LList in FCallerIndex.Values do
      LList.Free;
    FreeAndNil(FCallerIndex);
  end;

  if FCalleeIndex <> nil then begin
    for LList in FCalleeIndex.Values do
      LList.Free;
    FreeAndNil(FCalleeIndex);
  end;
end;

class procedure TStackTracer.AddEdgeIndex(AIndex: TEdgeIndex; AAddr: NativeUInt; AEdgeIndex: Integer);
var
  LList: TList<Integer>;
begin
  if AIndex = nil then
    Exit;

  if not AIndex.TryGetValue(AAddr, LList) then begin
    LList := TList<Integer>.Create;
    AIndex.Add(AAddr, LList);
  end;
  LList.Add(AEdgeIndex);
end;

class procedure TStackTracer.BuildEdgeIndexes;
var
  I: Integer;
begin
  ClearEdgeIndexes;
  FCallerIndex := TEdgeIndex.Create;
  FCalleeIndex := TEdgeIndex.Create;
  for I := 0 to High(FCallEdges) do begin
    AddEdgeIndex(FCallerIndex, FCallEdges[I].CallerAddr, I);
    AddEdgeIndex(FCalleeIndex, FCallEdges[I].CalleeAddr, I);
  end;
end;

class procedure TStackTracer.ScanCallGraph;
var
  I: NativeUInt;
  LEdges: TList<TCallEdge>;
  LEdge: TCallEdge;
  LRel: Integer;
  LCallSite: NativeUInt;
  LTarget: NativeUInt;
  LCallerStart: NativeUInt;
  LCalleeStart: NativeUInt;
  LManager: TStackTraceManager;
begin
  if FScanned then
    Exit;

  FScanned := True;
  FLastError := '';
  SetLength(FCallEdges, 0);
  ClearEdgeIndexes;


  if not EnsureSymbols then begin
    FLastError := 'map_not_loaded';
    Exit;
  end;

  if not LoadTextRange then
    Exit;

  LManager := TStackTraceManager.Current;
  LEdges := TList<TCallEdge>.Create;
  try
    I := 0;
    while I + 5 <= FTextSize do begin
      LCallSite := FTextStart + I;
      if PByte(LCallSite)^ = $E8 then begin
        LRel := PInteger(LCallSite + 1)^;
        LTarget := ResolveRelativeCallTarget(LCallSite, LRel);
        if (LTarget >= FTextStart) and (LTarget < FTextStart + FTextSize) then begin
          LCallerStart := ResolveSymbolStart(LCallSite);
          LCalleeStart := ResolveSymbolStart(LTarget);
          if (LCallerStart <> 0) and (LCalleeStart <> 0) then begin
            LEdge.CallerAddr := LCallerStart;
            LEdge.CalleeAddr := LCalleeStart;
            LEdge.CallAddr := LCallSite;
            LEdge.CallerName := ResolveSymbolName(LCallerStart);
            LEdge.CalleeName := ResolveSymbolName(LCalleeStart);
            LEdge.CalleeFile := '';
            LEdge.CalleeLine := 0;
            if LManager <> nil then
              LManager.TryResolveSourceLine(LCallSite, LEdge.CallFile, LEdge.CallLine);
            LEdges.Add(LEdge);
          end;
        end;
      end;
      Inc(I);
    end;

    FCallEdges := LEdges.ToArray;
    BuildEdgeIndexes;
  finally
    LEdges.Free;
  end;
end;

class function TStackTracer.GetCallChain(const AEntryFunc: string; AMaxDepth: Integer): TArray<TCallEdge>;
var
  LEntryAddr: NativeUInt;
  LVisited: TList<NativeUInt>;
  LQueue: TQueue<NativeUInt>;
  LDepth: TDictionary<NativeUInt, Integer>;
  LResult: TList<TCallEdge>;
  LEdgeIndexes: TList<Integer>;
  LCurr: NativeUInt;
  LEdgeIndex: Integer;
  LLevel, I: Integer;
begin
  SetLength(Result, 0);
  FLastError := '';
  if AMaxDepth < 0 then
    AMaxDepth := 0;

  if not FScanned then
    ScanCallGraph;
  if FLastError <> '' then
    Exit;

  LEntryAddr := FindFuncAddr(AEntryFunc);
  if LEntryAddr = 0 then begin
    FLastError := 'entry_not_found';
    Exit;
  end;

  LVisited := TList<NativeUInt>.Create;
  LQueue := TQueue<NativeUInt>.Create;
  LDepth := TDictionary<NativeUInt, Integer>.Create;
  LResult := TList<TCallEdge>.Create;
  try
    LQueue.Enqueue(LEntryAddr);
    LDepth.Add(LEntryAddr, 0);
    LVisited.Add(LEntryAddr);

    while LQueue.Count > 0 do begin
      LCurr := LQueue.Dequeue;
      LLevel := LDepth[LCurr];
      if LLevel >= AMaxDepth then
        Continue;

      if (FCallerIndex = nil) or (not FCallerIndex.TryGetValue(LCurr, LEdgeIndexes)) then
        Continue;
      for I := 0 to LEdgeIndexes.Count - 1 do begin
        LEdgeIndex := LEdgeIndexes[I];
        LResult.Add(FCallEdges[LEdgeIndex]);
        if not LVisited.Contains(FCallEdges[LEdgeIndex].CalleeAddr) then begin
          LVisited.Add(FCallEdges[LEdgeIndex].CalleeAddr);
          LDepth.Add(FCallEdges[LEdgeIndex].CalleeAddr, LLevel + 1);
          LQueue.Enqueue(FCallEdges[LEdgeIndex].CalleeAddr);
        end;
      end;
    end;

    Result := LResult.ToArray;
    if Length(Result) = 0 then
      FLastError := 'no_edges';
  finally
    LVisited.Free;
    LQueue.Free;
    LDepth.Free;
    LResult.Free;
  end;
end;

class function TStackTracer.GetCallerChain(const AEntryFunc: string; AMaxDepth: Integer): TArray<TCallEdge>;
var
  LEntryAddr: NativeUInt;
  LVisited: TList<NativeUInt>;
  LQueue: TQueue<NativeUInt>;
  LDepth: TDictionary<NativeUInt, Integer>;
  LResult: TList<TCallEdge>;
  LEdgeIndexes: TList<Integer>;
  LCurr: NativeUInt;
  LEdgeIndex: Integer;
  LLevel, I: Integer;
begin
  SetLength(Result, 0);
  FLastError := '';
  if AMaxDepth < 0 then
    AMaxDepth := 0;

  if not FScanned then
    ScanCallGraph;
  if FLastError <> '' then
    Exit;

  LEntryAddr := FindFuncAddr(AEntryFunc);
  if LEntryAddr = 0 then begin
    FLastError := 'entry_not_found';
    Exit;
  end;

  LVisited := TList<NativeUInt>.Create;
  LQueue := TQueue<NativeUInt>.Create;
  LDepth := TDictionary<NativeUInt, Integer>.Create;
  LResult := TList<TCallEdge>.Create;
  try
    LQueue.Enqueue(LEntryAddr);
    LDepth.Add(LEntryAddr, 0);
    LVisited.Add(LEntryAddr);

    while LQueue.Count > 0 do begin
      LCurr := LQueue.Dequeue;
      LLevel := LDepth[LCurr];
      if LLevel >= AMaxDepth then
        Continue;

      if (FCalleeIndex = nil) or (not FCalleeIndex.TryGetValue(LCurr, LEdgeIndexes)) then
        Continue;
      for I := 0 to LEdgeIndexes.Count - 1 do begin
        LEdgeIndex := LEdgeIndexes[I];
        LResult.Add(FCallEdges[LEdgeIndex]);
        if not LVisited.Contains(FCallEdges[LEdgeIndex].CallerAddr) then begin
          LVisited.Add(FCallEdges[LEdgeIndex].CallerAddr);
          LDepth.Add(FCallEdges[LEdgeIndex].CallerAddr, LLevel + 1);
          LQueue.Enqueue(FCallEdges[LEdgeIndex].CallerAddr);
        end;
      end;
    end;

    Result := LResult.ToArray;
    if Length(Result) = 0 then
      FLastError := 'no_edges';
  finally
    LVisited.Free;
    LQueue.Free;
    LDepth.Free;
    LResult.Free;
  end;
end;

class function TStackTracer.CallChainToJSON(const AChain: TArray<TCallEdge>; const ARoot, ADirection: string): string;
var
  LJson: TJSONObject;
  LArr: TJSONArray;
  LObj: TJSONObject;
  I: Integer;
begin
  LJson := TJSONObject.Create;
  try
    if ARoot <> '' then
      LJson.AddPair('root', ARoot)
    else if Length(AChain) > 0 then
      LJson.AddPair('root', AChain[0].CallerName)
    else
      LJson.AddPair('root', '');
    LJson.AddPair('direction', ADirection);

    LArr := TJSONArray.Create;
    for I := 0 to High(AChain) do begin
      LObj := TJSONObject.Create;
      LObj.AddPair('from', AChain[I].CallerName);
      LObj.AddPair('from_addr', FormatCallGraphAddr(AChain[I].CallerAddr));
      LObj.AddPair('call_addr', FormatCallGraphAddr(AChain[I].CallAddr));
      LObj.AddPair('call_file', AChain[I].CallFile);
      LObj.AddPair('call_line', TJSONNumber.Create(AChain[I].CallLine));
      LObj.AddPair('to', AChain[I].CalleeName);
      LObj.AddPair('to_addr', FormatCallGraphAddr(AChain[I].CalleeAddr));
      if AChain[I].CalleeFile <> '' then begin
        LObj.AddPair('to_file', AChain[I].CalleeFile);
        LObj.AddPair('to_line', TJSONNumber.Create(AChain[I].CalleeLine));
      end;
      LArr.AddElement(LObj);
    end;
    LJson.AddPair('calls', LArr);
    Result := LJson.ToString;
  finally
    LJson.Free;
  end;
end;

{$ENDIF}

initialization
  // 默认启用 StackTrace — 包含此单元即启用了调试端支持。
  TStackTraceManager.Enabled := True;

finalization

{$IFNDEF FPC}
  TStackTracer.ClearEdgeIndexes;
{$ENDIF}
  if Assigned(TStackTraceManager.FCurrent) then
    FreeAndNil(TStackTraceManager.FCurrent);

end.
