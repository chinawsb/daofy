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
  Rtti
{$ELSE}
  System.Classes,
  System.SysUtils,
  System.Generics.Collections,
  System.ZLib,
  Winapi.Windows,
  System.TypInfo,
  System.Rtti
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
  MapResMagic: array[0..3] of AnsiChar = 'MAPD';
  MapResVersion = 4;

type
  TResourceSerializeStep = (
      rssParseMap,
      rssStripPaths,
      rssBuildStringTable,
      rssSerialize,
      rssInjectResource,
      rssSelfSwap,
      rssCleanup,
      rssDone
  );

  TResourceSerializeProgress = procedure(const AStep: TResourceSerializeStep; const APrompt: string);

  IExceptionLogger = interface
    ['{5FA6454F-F37C-44E3-9042-EE91EB449DF1}']
    procedure HandleException(const AException: Exception; AExceptionInfo: Pointer);
  end;

  TGlobalVarInfo = record
    Name: string;
    TypeHandle: PTypeInfo;
    Address: Pointer;
  end;

  TStackTraceManager = class
  private
    type
      TMapSymbol = record
        Addr: DWORD;
        Name: string;
      end;

      TLineInfo = record
        Addr: DWORD;
        SourceFile: string;
        Line: Integer;
      end;

      TSymbolEntry = record
        Addr: DWORD;
        FirstToken: Integer;
        TokenCount: Integer;
      end;

      TLineEntry = record
        Addr: DWORD;
        Line: Integer;
        FileIdx: Integer;
      end;

      PStackInfoData = ^TStackInfoData;

      TStackInfoData = record
        FrameCount: Integer;
        Frames: array[0..MaxStackFrames - 1] of Pointer;
        FrameEBP: array[0..MaxStackFrames - 1] of Pointer;
      end;

      TLocalVarInfo = record
        Name: string;
        TypeKind: Byte;
        constructor Create(const AName: string; ATypeKind: Byte);
      end;

      TLocalVarEntry = record
        SymIdx: Integer;
        ParamCount: Integer;
        Vars: TArray<TLocalVarInfo>;
      end;
  private
    FDbgHelpChecked: Integer;
    FDbgHelpAvailable: Integer;
    FDbgHelpInitialized: Integer;
    FDbgHelpProcess: THandle;
    FTokenDict: TArray<string>;
    FTokenData: TArray<Integer>;
    FSymEntries: TArray<TSymbolEntry>;
    FLineEntries: TArray<TLineEntry>;
    FSourcePaths: TArray<string>;
    FMapLoaded: Integer;
    FModuleBase: DWORD;
    FLocalVarData: TArray<TLocalVarEntry>;
    class function StackInfoStringProc(Info: Pointer): string; static;
    function CheckDbgHelp: Boolean;
    function ParseMapFile(
        const AMapPath: string;
        out ASymbols: TArray<TMapSymbol>;
        out ALines: TArray<TLineInfo>
    ): Boolean;
    function WriteVarInt(AStream: TStream; Value: Integer): Integer;
    function ReadVarInt(AStream: TStream; out Value: Integer): Boolean;
    procedure TokenizeName(
        const AName: string;
        ATokens: TList<Integer>;
        ADict: TDictionary<string, Integer>;
        AOrdered: TList<string>
    );
    function ExpandSymbolName(ASymIdx: Integer): string;
    procedure TokenizeAndStore(const ASymbols: TArray<TMapSymbol>; const ALines: TArray<TLineInfo>);
    function SerializeSymbols(const ASymbols: TArray<TMapSymbol>; const ALines: TArray<TLineInfo>): TBytes;
    function DeserializeSymbols(const AData: TBytes): Boolean;
    function TryLoadMapFromResource: Boolean;
    function TryLoadMapFile: Boolean;
    procedure StripSourcePaths(var ALines: TArray<TLineInfo>);
    function ExtractLocalVarsFromSource(
        const ASourcePath: string;
        const ASymbols: TArray<TMapSymbol>;
        const ADefines: TArray<string>
    ): TArray<TLocalVarEntry>;
    function ResolveFromMap(VA: DWORD): string;
    function FindLocalVars(SymIdx: Integer): TArray<TLocalVarInfo>;
    function ReadFunctionPrologue(AFuncAddr: Pointer; out FrameSize: Integer): Boolean;
    function ComputeVarOffsets(
        const AVars: TArray<TLocalVarInfo>;
        FrameSize, AParamCount: Integer;
        out Offsets: TArray<SmallInt>
    ): Boolean;
    function ReadStackVarValue(Addr: Pointer; TypeKind: Byte): string;
    function TryGetObjectClassName(Obj: Pointer): string;
    function TryGetStringValue(P: Pointer): string;
    function FormatStackFrame(VA: DWORD; AEBP: Pointer): string;
    class function GetEnabled: Boolean; static;
    class procedure SetEnabled(const AEnabled: Boolean); static;
  private
    class var
      FCurrent: TStackTraceManager;
      FLogger: IExceptionLogger;
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
    function GetMapLoadStatus: Integer;
    function GetModuleBaseAddr: DWORD;
    class function GetStackString(Info: Pointer): string; static;
    class property Enabled: Boolean read GetEnabled write SetEnabled;
    class property Current: TStackTraceManager read FCurrent;
    class property Logger: IExceptionLogger read FLogger write FLogger;
  end;

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
  private
    FOrigGetExceptionStackInfoProc: TGetExceptionStackInfoProc;
    FOrigGetStackInfoStringProc: TGetStackInfoStringProc;
    FOrigCleanUpStackInfoProc: TCleanUpStackInfoProc;
    class function ExceptionStackInfoProc(P: System.PExceptionRecord): Pointer; static;
    class procedure CleanupStackInfoProc(Info: Pointer); static;
  protected
    procedure InstallHooks; override;
    procedure UninstallHooks; override;
  end;
{$ENDIF}

implementation

uses System.IOUtils, AST.Base, AST.Nodes, AST.NodesExpr, AST.DelphiParser, DCUParser;

{ TLocalVarInfo }

constructor TStackTraceManager.TLocalVarInfo.Create(const AName: string; ATypeKind: Byte);
begin
  Name := AName;
  TypeKind := ATypeKind;
end;

type
  TAddress = record
    Offset: ULONG64;
    Segment: WORD;
    AddrMode: DWORD;
  end;

  TStackFrame = record
    AddrPC: TAddress;
    AddrReturn: TAddress;
    AddrFrame: TAddress;
    AddrStack: TAddress;
    AddrBStore: TAddress;
    FuncTableEntry: Pointer;
    Params: array[0..3] of ULONG64;
    Far: BOOL;
    Virtual: BOOL;
    Reserved: array[0..3] of ULONG64;
    KdHelp: array[0..31] of ULONG;
  end;

  PIMAGEHLP_SYMBOL64A = ^IMAGEHLP_SYMBOL64A;

  IMAGEHLP_SYMBOL64A = record
    SizeOfStruct: DWORD;
    Address: ULONG64;
    Size: DWORD;
    Flags: DWORD;
    MaxNameLength: DWORD;
    Name: array[0..0] of AnsiChar;
  end;

  PIMAGEHLP_LINE64 = ^IMAGEHLP_LINE64;

  IMAGEHLP_LINE64 = record
    SizeOfStruct: DWORD;
    Key: Pointer;
    LineNumber: DWORD;
    FileName: PAnsiChar;
    Address: ULONG64;
  end;

  TDefaultExceptionLogger = class(TInterfacedObject, IExceptionLogger)
  private
    procedure HandleException(const AException: Exception; AExceptionInfo: Pointer);
  end;

{$IFDEF FPC}
type
  TZCompressionStream = TCompressionStream;
  TZDecompressionStream = TDecompressionStream;
{$ENDIF}

{$WARN SYMBOL_PLATFORM OFF}
function StackWalk64(
    MachineType: DWORD;
    hProcess: THandle;
    hThread: THandle;
    var StackFrame: TStackFrame;
    Context: Pointer;
    ReadMemoryRoutine: Pointer;
    FunctionTableAccessRoutine: Pointer;
    GetModuleBaseRoutine: Pointer;
    TranslateAddress: Pointer
): BOOL; stdcall; external 'dbghelp.dll' delayed;

function SymInitialize(
    hProcess: THandle;
    UserSearchPath: PAnsiChar;
    fInvadeProcess: BOOL
): BOOL; stdcall; external 'dbghelp.dll' delayed;

function SymCleanup(hProcess: THandle): BOOL; stdcall; external 'dbghelp.dll' delayed;

function SymSetOptions(SymOptions: DWORD): DWORD; stdcall; external 'dbghelp.dll' delayed;

function SymGetSymFromAddr64(
    hProcess: THandle;
    Address: ULONG64;
    var Displacement: ULONG64;
    Symbol: PIMAGEHLP_SYMBOL64A
): BOOL; stdcall; external 'dbghelp.dll' delayed;

function SymGetLineFromAddr64(
    hProcess: THandle;
    Address: ULONG64;
    var Displacement: DWORD;
    Line: PIMAGEHLP_LINE64
): BOOL; stdcall; external 'dbghelp.dll' delayed;

function SymFunctionTableAccess64(
    hProcess: THandle;
    AddrBase: ULONG64
): Pointer; stdcall; external 'dbghelp.dll' delayed;

function SymGetModuleBase64(hProcess: THandle; Address: ULONG64): ULONG64; stdcall; external 'dbghelp.dll' delayed;
{$WARN SYMBOL_PLATFORM ON}

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
    wLanguage: WORD;
    lpData: Pointer;
    cbData: DWORD
): BOOL; stdcall; external 'kernel32.dll';
function EndUpdateResourceW(hUpdate: THandle; fDiscard: BOOL): BOOL; stdcall; external 'kernel32.dll';

function RT_RCDATA_W: PWideChar; inline;
begin
  Result := MakeIntResource(10);
end;

{$IFDEF FPC}

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

procedure TDefaultExceptionLogger.HandleException(const AException: Exception; AExceptionInfo: Pointer);
var
  AFileName: string;
  AStream: TFileStream;
  ABytes: TBytes;
begin
  if Assigned(AException) then begin
    TMonitor.Enter(Self);
    try
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
                        AException.ClassName,
                        AException.Message,
                        TStackTraceManager.FCurrent.StackInfoStringProc(AExceptionInfo)
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

function TStackTraceManager.CheckDbgHelp: Boolean;
var
  hMod: HMODULE;
begin
  if FDbgHelpChecked = -1 then begin
    hMod := LoadLibrary('dbghelp.dll');
    FDbgHelpAvailable := Ord(hMod <> 0);
    if hMod <> 0 then
      FreeLibrary(hMod);
    FDbgHelpChecked := 1;
  end;
  Result := FDbgHelpAvailable <> 0;
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
  LSegBases: array[1..MAX_SEGMENTS] of DWORD;
  LSegCount: Integer;
begin
  Result := False;
  ASymbols := nil;
  ALines := nil;

  if not FileExists(AMapPath) then
    Exit;

  LLines := TStringList.Create;
  try
    LLines.LoadFromFile(AMapPath);

    FillChar(LSegBases, SizeOf(LSegBases), 0);
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
          var LBaseAddr := StrToIntDef('$' + LAddrStr, 0);
          if LBaseAddr > 0 then begin
            LSegBases[LSegNum] := LBaseAddr;
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
                try
                  var LOffset := StrToInt('$' + LOffsetStr);
                  var LSegNum := 1;
                  if LLine.StartsWith('0002:') then
                    LSegNum := 2;
                  var LFullAddr := LSegBases[LSegNum] + DWORD(LOffset);
                  var LSym: TMapSymbol;
                  LSym.Addr := LFullAddr;
                  LSym.Name := LSymName;
                  LSyms.Add(LSym);
                except
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
                try
                  var LOffset := StrToInt('$' + LHexAddr);
                  var LSegNum := 1;
                  if LAddrStr.StartsWith('0002:') then
                    LSegNum := 2;
                  var LFullAddr := LSegBases[LSegNum] + DWORD(LOffset);
                  var LLn := StrToInt(LLineNumStr);
                  var LInfo: TLineInfo;
                  LInfo.Addr := LFullAddr;
                  LInfo.SourceFile := LCurrentSourceFile;
                  LInfo.Line := LLn;
                  LLinesInfo.Add(LInfo);
                except
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
      for var X := 0 to High(LSymArr) - 1 do
        for var Y := X + 1 to High(LSymArr) do
          if LSymArr[X].Addr > LSymArr[Y].Addr then begin
            var LTemp := LSymArr[X];
            LSymArr[X] := LSymArr[Y];
            LSymArr[Y] := LTemp;
          end;
      ASymbols := LSymArr;

      if LLinesInfo.Count > 0 then begin
        var LLinesArr := LLinesInfo.ToArray;
        for var X := 0 to High(LLinesArr) - 1 do
          for var Y := X + 1 to High(LLinesArr) do
            if LLinesArr[X].Addr > LLinesArr[Y].Addr then begin
              var LTemp := LLinesArr[X];
              LLinesArr[X] := LLinesArr[Y];
              LLinesArr[Y] := LTemp;
            end;
        ALines := LLinesArr;
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

function TStackTraceManager.WriteVarInt(AStream: TStream; Value: Integer): Integer;
var
  LByte: Byte;
begin
  Result := 0;
  repeat
    LByte := Value and $7F;
    Value := Value shr 7;
    if Value > 0 then
      LByte := LByte or $80;
    AStream.WriteBuffer(LByte, 1);
    Inc(Result);
  until Value = 0;
end;

function TStackTraceManager.ReadVarInt(AStream: TStream; out Value: Integer): Boolean;
var
  LByte: Byte;
  LShift: Integer;
begin
  Value := 0;
  LShift := 0;
  Result := True;
  while True do begin
    if AStream.Read(LByte, 1) <> 1 then
      Exit(False);
    Value := Value or ((LByte and $7F) shl LShift);
    if (LByte and $80) = 0 then
      Break;
    Inc(LShift, 7);
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
var
  I, LStart: Integer;
  LToken: string;
  LId: Integer;
begin
  LStart := 1;
  for I := 1 to Length(AName) do begin
    if CharInSet(AName[I], ['.', '<', '>', '{', '}', '$']) then begin
      if I > LStart then begin
        LToken := Copy(AName, LStart, I - LStart);
        if not ADict.TryGetValue(LToken, LId) then begin
          LId := AOrdered.Count;
          ADict.Add(LToken, LId);
          AOrdered.Add(LToken);
        end;
        ATokens.Add(LId);
      end;
      // Emit delimiter as its own token
      LToken := AName[I];
      if not ADict.TryGetValue(LToken, LId) then begin
        LId := AOrdered.Count;
        ADict.Add(LToken, LId);
        AOrdered.Add(LToken);
      end;
      ATokens.Add(LId);
      LStart := I + 1;
    end;
  end;
  // Emit trailing text
  if LStart <= Length(AName) then begin
    LToken := Copy(AName, LStart, MaxInt);
    if not ADict.TryGetValue(LToken, LId) then begin
      LId := AOrdered.Count;
      ADict.Add(LToken, LId);
      AOrdered.Add(LToken);
    end;
    ATokens.Add(LId);
  end;
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
    const ALines: TArray<TLineInfo>
): TBytes;
var
  LStream: TMemoryStream;
  I, J: Integer;
  LStrBytes: TBytes;
  LDelta: Integer;
  LTokenIds: TList<Integer>;
  LSavedTokens: TArray<TArray<Integer>>;
  LDict: TDictionary<string, Integer>;
  LOrdered: TList<string>;
  LPathDict: TDictionary<string, Integer>;
  LPaths: TList<string>;
  LLocalTokNames: TArray<TArray<Integer>>;
  LLocalTokKinds: TArray<TArray<Byte>>;
begin
  LStream := TMemoryStream.Create;
  LTokenIds := TList<Integer>.Create;
  LDict := TDictionary<string, Integer>.Create;
  LOrdered := TList<string>.Create;
  LPathDict := TDictionary<string, Integer>.Create;
  LPaths := TList<string>.Create;
  try
    // Magic + version
    LStream.WriteBuffer(MapResMagic, 4);
    WriteVarInt(LStream, MapResVersion);

    // Phase 1: source path string table
    for I := 0 to High(ALines) do
      if not LPathDict.ContainsKey(ALines[I].SourceFile) then begin
        LPathDict.Add(ALines[I].SourceFile, LPathDict.Count);
        LPaths.Add(ALines[I].SourceFile);
      end;
    WriteVarInt(LStream, LPaths.Count);
    for I := 0 to LPaths.Count - 1 do begin
      LStrBytes := TEncoding.UTF8.GetBytes(LPaths[I]);
      WriteVarInt(LStream, Length(LStrBytes));
      if Length(LStrBytes) > 0 then
        LStream.WriteBuffer(LStrBytes[0], Length(LStrBytes));
    end;

    // Phase 2: tokenize all symbol names + local variable names
    SetLength(LSavedTokens, Length(ASymbols));
    SetLength(LLocalTokNames, Length(FLocalVarData));
    SetLength(LLocalTokKinds, Length(FLocalVarData));
    for I := 0 to High(ASymbols) do begin
      LTokenIds.Clear;
      TokenizeName(ASymbols[I].Name, LTokenIds, LDict, LOrdered);
      LSavedTokens[I] := LTokenIds.ToArray;
    end;
    for I := 0 to High(FLocalVarData) do
      if FLocalVarData[I].SymIdx < Length(ASymbols) then begin
        var LVarCount := Length(FLocalVarData[I].Vars);
        if LVarCount > 0 then begin
          SetLength(LLocalTokNames[I], LVarCount);
          SetLength(LLocalTokKinds[I], LVarCount);
          for J := 0 to LVarCount - 1 do begin
            LTokenIds.Clear;
            TokenizeName(FLocalVarData[I].Vars[J].Name, LTokenIds, LDict, LOrdered);
            if LTokenIds.Count > 0 then
              LLocalTokNames[I][J] := LTokenIds[0]
            else
              LLocalTokNames[I][J] := 0;
            LLocalTokKinds[I][J] := FLocalVarData[I].Vars[J].TypeKind;
          end;
        end;
      end;

    // Phase 2a: sort token dictionary by frequency (descending) so that
    // frequent tokens get small varint IDs -> fewer bytes.
    if LOrdered.Count > 0 then begin
      var LFreq: TArray<Integer>;
      SetLength(LFreq, LOrdered.Count);
      for I := 0 to High(LSavedTokens) do
        for J := 0 to High(LSavedTokens[I]) do
          Inc(LFreq[LSavedTokens[I][J]]);
      for I := 0 to High(LLocalTokNames) do
        for J := 0 to High(LLocalTokNames[I]) do
          Inc(LFreq[LLocalTokNames[I][J]]);

      var LSortedIdx: TArray<Integer>;
      SetLength(LSortedIdx, LOrdered.Count);
      for I := 0 to LOrdered.Count - 1 do
        LSortedIdx[I] := I;
      for var X := 0 to Length(LSortedIdx) - 2 do
        for var Y := X + 1 to Length(LSortedIdx) - 1 do
          if LFreq[LSortedIdx[X]] < LFreq[LSortedIdx[Y]] then begin
            var LTemp := LSortedIdx[X];
            LSortedIdx[X] := LSortedIdx[Y];
            LSortedIdx[Y] := LTemp;
          end;

      var LRemap: TArray<Integer>;
      SetLength(LRemap, LOrdered.Count);
      var LNewOrder: TList<string>;
      LNewOrder := TList<string>.Create;
      try
        for I := 0 to Length(LSortedIdx) - 1 do begin
          LRemap[LSortedIdx[I]] := I;
          LNewOrder.Add(LOrdered[LSortedIdx[I]]);
        end;
        LOrdered.Clear;
        for I := 0 to LNewOrder.Count - 1 do
          LOrdered.Add(LNewOrder[I]);

        for I := 0 to High(LSavedTokens) do
          for J := 0 to High(LSavedTokens[I]) do
            LSavedTokens[I][J] := LRemap[LSavedTokens[I][J]];
        for I := 0 to High(LLocalTokNames) do
          for J := 0 to High(LLocalTokNames[I]) do
            LLocalTokNames[I][J] := LRemap[LLocalTokNames[I][J]];
      finally
        LNewOrder.Free;
      end;
    end;

    // Write token dictionary (frequency-sorted)
    WriteVarInt(LStream, LOrdered.Count);
    for I := 0 to LOrdered.Count - 1 do begin
      LStrBytes := TEncoding.UTF8.GetBytes(LOrdered[I]);
      WriteVarInt(LStream, Length(LStrBytes));
      if Length(LStrBytes) > 0 then
        LStream.WriteBuffer(LStrBytes[0], Length(LStrBytes));
    end;

    // Phase 3: write symbol table (delta addresses + saved token sequences)
    WriteVarInt(LStream, Length(ASymbols));
    if Length(ASymbols) > 0 then begin
      WriteVarInt(LStream, ASymbols[0].Addr);
      for I := 0 to High(ASymbols) do begin
        if I = 0 then
          LDelta := 0
        else
          LDelta := ASymbols[I].Addr - ASymbols[I - 1].Addr;
        WriteVarInt(LStream, LDelta);

        WriteVarInt(LStream, Length(LSavedTokens[I]));
        for J := 0 to High(LSavedTokens[I]) do
          WriteVarInt(LStream, LSavedTokens[I][J]);
      end;
    end;

    // Phase 4: write line info table (delta addresses + source path indices)
    WriteVarInt(LStream, Length(ALines));
    if Length(ALines) > 0 then begin
      WriteVarInt(LStream, ALines[0].Addr);
      for I := 0 to High(ALines) do begin
        if I = 0 then
          LDelta := 0
        else
          LDelta := ALines[I].Addr - ALines[I - 1].Addr;
        WriteVarInt(LStream, LDelta);
        WriteVarInt(LStream, ALines[I].Line);
        WriteVarInt(LStream, LPathDict[ALines[I].SourceFile]);
      end;
    end;

    // Phase 5: local variable table
    // Build symbol-indexed lookup from FLocalVarData using already-remapped token IDs
    var LSymVarCount: TArray<Integer>;
    var LSymVarParamCount: TArray<Integer>;
    var LSymVarTokens: TArray<TArray<Integer>>;
    var LSymVarKinds: TArray<TArray<Byte>>;
    SetLength(LSymVarCount, Length(ASymbols));
    SetLength(LSymVarParamCount, Length(ASymbols));
    SetLength(LSymVarTokens, Length(ASymbols));
    SetLength(LSymVarKinds, Length(ASymbols));
    for I := 0 to High(FLocalVarData) do begin
      var LSymIdx := FLocalVarData[I].SymIdx;
      if (LSymIdx >= 0) and (LSymIdx < Length(ASymbols)) then begin
        var LVarCount := Length(FLocalVarData[I].Vars);
        if LVarCount > 0 then begin
          LSymVarCount[LSymIdx] := LVarCount;
          LSymVarParamCount[LSymIdx] := FLocalVarData[I].ParamCount;
          // Use already-tokenized-and-frequency-remapped LLocalTokNames/LLocalTokKinds
          if (I < Length(LLocalTokNames)) and (Length(LLocalTokNames[I]) >= LVarCount) then begin
            LSymVarTokens[LSymIdx] := LLocalTokNames[I];
            LSymVarKinds[LSymIdx] := LLocalTokKinds[I];
          end else begin
            // Fallback: re-tokenize (should not happen, but keep for safety)
            SetLength(LSymVarTokens[LSymIdx], LVarCount);
            SetLength(LSymVarKinds[LSymIdx], LVarCount);
            for J := 0 to LVarCount - 1 do begin
              LTokenIds.Clear;
              TokenizeName(FLocalVarData[I].Vars[J].Name, LTokenIds, LDict, LOrdered);
              if LTokenIds.Count > 0 then
                LSymVarTokens[LSymIdx][J] := LTokenIds[0]
              else
                LSymVarTokens[LSymIdx][J] := 0;
              LSymVarKinds[LSymIdx][J] := FLocalVarData[I].Vars[J].TypeKind;
            end;
          end;
        end;
      end;
    end;
    WriteVarInt(LStream, 0); // sym_start_idx
    for I := 0 to High(ASymbols) do begin
      if LSymVarCount[I] > 0 then begin
        WriteVarInt(LStream, LSymVarParamCount[I]);
        for J := 0 to LSymVarCount[I] - 1 do begin
          WriteVarInt(LStream, LSymVarTokens[I][J]);
          LStream.WriteBuffer(LSymVarKinds[I][J], 1);
        end;
      end;
      WriteVarInt(LStream, 128); // sentinel
    end;

    // No compression — raw output
    SetLength(Result, LStream.Size);
    Move(LStream.Memory^, Result[0], LStream.Size);
  finally
    LPathDict.Free;
    LPaths.Free;
    LDict.Free;
    LOrdered.Free;
    LTokenIds.Free;
    LStream.Free;
  end;
end;

function TStackTraceManager.DeserializeSymbols(const AData: TBytes): Boolean;
var
  LStream: TMemoryStream;
  LMagic: array[0..3] of AnsiChar;
  LVersion: Integer;
  LSymCount, LFileCount, LTokenCount, LTokCount, LLineCount: Integer;
  I, J: Integer;
  LStrLen, LTokenId: Integer;
  LStrBytes: TBytes;
  LAddr: DWORD;
  LDelta: Integer;
  LTokenData: TList<Integer>;
begin
  Result := False;

  LStream := TMemoryStream.Create;
  LTokenData := TList<Integer>.Create;
  try
    // Clear previous data
    FTokenDict := nil;
    FTokenData := nil;
    FSymEntries := nil;
    FLineEntries := nil;
    FSourcePaths := nil;

    LStream.WriteBuffer(AData[0], Length(AData));
    LStream.Position := 0;

    // Magic + version
    LStream.ReadBuffer(LMagic, 4);
    if (LMagic[0] <> MapResMagic[0])
        or (LMagic[1] <> MapResMagic[1])
        or (LMagic[2] <> MapResMagic[2])
        or (LMagic[3] <> MapResMagic[3]) then
      Exit;

    if not ReadVarInt(LStream, LVersion) then
      Exit;
    if (LVersion < 3) or (LVersion > 4) then
      Exit;

    // Read source path string table
    if not ReadVarInt(LStream, LFileCount) then
      Exit;
    if (LFileCount < 0) or (LFileCount > 10000) then
      Exit;
    SetLength(FSourcePaths, LFileCount);
    for I := 0 to LFileCount - 1 do begin
      if not ReadVarInt(LStream, LStrLen) then
        Exit;
      if (LStrLen < 0) or (LStrLen > 10000) then
        Exit;
      if LStrLen > 0 then begin
        SetLength(LStrBytes, LStrLen);
        if LStream.Read(LStrBytes[0], LStrLen) <> LStrLen then
          Exit;
        FSourcePaths[I] := TEncoding.UTF8.GetString(LStrBytes);
      end;
    end;

    // Read token dictionary
    if not ReadVarInt(LStream, LTokenCount) then
      Exit;
    if (LTokenCount < 0) or (LTokenCount > 100000) then
      Exit;
    SetLength(FTokenDict, LTokenCount);
    for I := 0 to LTokenCount - 1 do begin
      if not ReadVarInt(LStream, LStrLen) then
        Exit;
      if (LStrLen < 0) or (LStrLen > 10000) then
        Exit;
      if LStrLen > 0 then begin
        SetLength(LStrBytes, LStrLen);
        if LStream.Read(LStrBytes[0], LStrLen) <> LStrLen then
          Exit;
        FTokenDict[I] := TEncoding.UTF8.GetString(LStrBytes);
      end;
    end;

    // Read symbol table (delta addresses + token sequences)
    if not ReadVarInt(LStream, LSymCount) then
      Exit;
    if (LSymCount < 0) or (LSymCount > 1000000) then
      Exit;
    SetLength(FSymEntries, LSymCount);

    if LSymCount > 0 then begin
      if not ReadVarInt(LStream, Integer(LAddr)) then
        Exit;
      for I := 0 to LSymCount - 1 do begin
        if not ReadVarInt(LStream, LDelta) then
          Exit;
        LAddr := LAddr + DWORD(LDelta);
        FSymEntries[I].Addr := LAddr;
        FSymEntries[I].FirstToken := LTokenData.Count;

        // Read token count for this symbol
        if not ReadVarInt(LStream, LTokCount) then
          Exit;
        if (LTokCount < 0) or (LTokCount > 1000) then
          Exit;
        FSymEntries[I].TokenCount := LTokCount;

        // Read token indices
        for J := 0 to LTokCount - 1 do begin
          if not ReadVarInt(LStream, LTokenId) then
            Exit;
          if (LTokenId < 0) or (LTokenId >= LTokenCount) then
            Exit;
          LTokenData.Add(LTokenId);
        end;
      end;
    end;
    FTokenData := LTokenData.ToArray;

    // Read line info table
    if not ReadVarInt(LStream, LLineCount) then
      Exit;
    if (LLineCount < 0) or (LLineCount > 1000000) then
      Exit;
    SetLength(FLineEntries, LLineCount);

    if LLineCount > 0 then begin
      if not ReadVarInt(LStream, Integer(LAddr)) then
        Exit;
      for I := 0 to LLineCount - 1 do begin
        if not ReadVarInt(LStream, LDelta) then
          Exit;
        LAddr := LAddr + DWORD(LDelta);
        FLineEntries[I].Addr := LAddr;

        if not ReadVarInt(LStream, FLineEntries[I].Line) then
          Exit;

        if not ReadVarInt(LStream, Integer(LFileCount)) then // reuse LFileCount as file index
          Exit;
        if (LFileCount < 0) or (LFileCount >= Length(FSourcePaths)) then
          Exit;
        FLineEntries[I].FileIdx := LFileCount;
      end;
    end;

    // Phase 5: local variable table (version 4+)
    FLocalVarData := nil;
    if LVersion >= 4 then begin
      var LSymStart: Integer;
      if not ReadVarInt(LStream, LSymStart) then
        Exit;
      if (LSymStart < 0) or (LSymStart > 1000000) then
        Exit;
      FLocalVarData := nil;
      var LTokId: Integer;
      for I := LSymStart to LSymStart + LSymCount - 1 do begin
        if I >= LSymStart + Length(FSymEntries) then
          Break;
        var LEntry: TLocalVarEntry;
        LEntry.SymIdx := I;
        LEntry.ParamCount := 0;
        LEntry.Vars := nil;
        var LIsFirst: Boolean := True;
        while True do begin
          if not ReadVarInt(LStream, LTokId) then
            Exit;
          if LTokId = 128 then
            Break;
          if LIsFirst then begin
            LIsFirst := False;
            LEntry.ParamCount := LTokId;
            Continue;
          end;
          var LKind: Byte;
          if LStream.Read(LKind, 1) <> 1 then
            Exit;
          var LVarName: string;
          if LTokId < Length(FTokenDict) then
            LVarName := FTokenDict[LTokId]
          else
            LVarName := Format('<token%d>', [LTokId]);
          var LLen := Length(LEntry.Vars);
          SetLength(LEntry.Vars, LLen + 1);
          LEntry.Vars[LLen].Name := LVarName;
          LEntry.Vars[LLen].TypeKind := LKind;
        end;
        if Length(LEntry.Vars) > 0 then begin
          var LNewLen := Length(FLocalVarData) + 1;
          SetLength(FLocalVarData, LNewLen);
          FLocalVarData[LNewLen - 1] := LEntry;
        end;
      end;
    end;

    Result := True;
  finally
    LTokenData.Free;
    LStream.Free;
  end;
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

function TStackTraceManager.TryLoadMapFile: Boolean;
var
  LSyms: TArray<TMapSymbol>;
  LLines: TArray<TLineInfo>;
begin
  if FMapLoaded <> 0 then
    Exit(FMapLoaded = 1);

  // Try embedded resource FIRST (contains local variable data)
  if TryLoadMapFromResource then begin
    FModuleBase := DWORD(GetModuleHandle(nil));
    FMapLoaded := 1;
    Exit(True);
  end;

  // Fall back to .map file on disk (no local variable data)
  var LMapPath := ChangeFileExt(ParamStr(0), '.map');
  if FileExists(LMapPath) then begin
    if ParseMapFile(LMapPath, LSyms, LLines) then begin
      TokenizeAndStore(LSyms, LLines);
      FModuleBase := DWORD(GetModuleHandle(nil));
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
  hUpdate: THandle;
  LTargetExe: string;
  LSelfOrig: string;
  LSelfBak: string;
  LSelfNew: string;
  LCmdLine: string;
  LProcInfo: TProcessInformation;
  LStartInfo: TStartupInfo;
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
      var LSearchDirs: TArray<string> :=
          [
              '',
              'AST\',
              'Engine\',
              'Diagnostics\',
              'Processors\',
              'Rules\AST\',
              'Rules\DCU\',
              'Rules\DFM\',
              'Rules\Line\',
              'Utils\',
              'docs\',
              'demos\',
              'Tests\'
          ];

      LAstDbg.Add('--- Resolved Source File Paths ---');
      for var I := 0 to LFullPaths.Count - 1 do begin
        var LResolved := '';
        var LShortName := ExtractFileName(LFullPaths[I]);
        // First try as-is
        if FileExists(LFullPaths[I]) then
          LResolved := ExpandFileName(LFullPaths[I])
        else begin
          // Search in known subdirectories
          for var LD in LSearchDirs do begin
            var LCandidate := LProjectRoot + LD + LShortName;
            if FileExists(LCandidate) then begin
              LResolved := LCandidate;
              Break;
            end;
          end;
          // If still not found, try the original path
          if LResolved = '' then
            LResolved := LFullPaths[I];
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
      LAstDbg.Add('');

      // Read conditional defines from .dproj
      var LDprojDefines: TArray<string> := [];
      var LDprojPath := ChangeFileExt(AExePath, '.dproj');
      if FileExists(LDprojPath) then begin
        try
          var LDprojContent := TFile.ReadAllText(LDprojPath);
          var LDefStart := Pos('<DCC_Define>', LDprojContent);
          if LDefStart > 0 then begin
            LDefStart := LDefStart + 13; // Length of '<DCC_Define>'
            var LDefEnd := Pos('</DCC_Define>', LDprojContent, LDefStart);
            if LDefEnd > LDefStart then begin
              var LDefStr := Copy(LDprojContent, LDefStart, LDefEnd - LDefStart);
              var LDefParts := LDefStr.Split([';']);
              var LDefList := TList<string>.Create;
              try
                for var K := 0 to High(LDefParts) do begin
                  var LTrimmed := Trim(LDefParts[K]);
                  if (LTrimmed <> '') and not LTrimmed.StartsWith('$(') then
                    LDefList.Add(LTrimmed);
                end;
                LDprojDefines := LDefList.ToArray;
              finally
                LDefList.Free;
              end;
              LAstDbg.Add(Format('--- DCC_Define from dproj: %s', [string.Join(';', LDprojDefines)]));
            end;
          end;
        except
          LAstDbg.Add('--- DCC_Define: failed to read dproj');
        end;
      end;

      // Phase 5 preparation: extract local vars from source files via AST
      FLocalVarData := nil;
      var LAllVars := TList<TLocalVarEntry>.Create;
      try
        for var I := 0 to LFullPaths.Count - 1 do begin
          var LVars := ExtractLocalVarsFromSource(LResolvedPaths[I], LSyms, LDprojDefines);
          if Length(LVars) > 0 then begin
            for var J := 0 to High(LVars) do
              LAllVars.Add(LVars[J]);
            Log(
                rssBuildStringTable,
                Format(
                    '[EMBED-MAP] Extracted %d funcs with local vars from %s',
                    [Length(LVars), ExtractFileName(LFullPaths[I])]
                )
            );
          end;
        end;
        FLocalVarData := LAllVars.ToArray;
        Log(
            rssBuildStringTable,
            Format('[EMBED-MAP] Total %d function entries with local vars', [Length(FLocalVarData)])
        );

        // Debug: dump all matched local vars
        var LDbg := TStringList.Create;
        try
          LDbg.Add(Format('=== Local Variable Dump (%d entries) ===', [Length(FLocalVarData)]));
          for var I := 0 to High(FLocalVarData) do begin
            if FLocalVarData[I].SymIdx < Length(LSyms) then
              LDbg.Add(Format('[%d] %s  (sym %d)', [I, LSyms[FLocalVarData[I].SymIdx].Name, FLocalVarData[I].SymIdx]))
            else
              LDbg.Add(Format('[%d] <unknown sym idx %d>', [I, FLocalVarData[I].SymIdx]));
            for var J := 0 to High(FLocalVarData[I].Vars) do
              LDbg.Add(
                  Format(
                      '    var[%d] name="%s" typekind=%d',
                      [J, FLocalVarData[I].Vars[J].Name, FLocalVarData[I].Vars[J].TypeKind]
                  )
              );
          end;
          LDbg.SaveToFile(ChangeFileExt(AExePath, '.lv-debug.txt'));
        finally
          LDbg.Free;
        end;

        LAstDbg.Add(Format('--- Final Summary ---', []));
        LAstDbg.Add(Format('  Total local var entries: %d', [Length(FLocalVarData)]));
        LAstDbg.Add('');
        // Tally matched functions per unit
        var LUnitCounts := TDictionary<string, Integer>.Create;
        try
          for var I := 0 to High(FLocalVarData) do
            if FLocalVarData[I].SymIdx < Length(LSyms) then begin
              var LSymName := LSyms[FLocalVarData[I].SymIdx].Name;
              var LDot := Pos('.', LSymName);
              var LUnit: string := '?';
              if LDot > 0 then
                LUnit := Copy(LSymName, 1, LDot - 1);
              var LCnt := 0;
              if LUnitCounts.TryGetValue(LUnit, LCnt) then
                LUnitCounts[LUnit] := LCnt + 1
              else
                LUnitCounts.Add(LUnit, 1);
            end;
          for var LKey in LUnitCounts.Keys do
            LAstDbg.Add(Format('  Unit "%s": %d matched funcs', [LKey, LUnitCounts[LKey]]));
        finally
          LUnitCounts.Free;
        end;
      finally
        LAllVars.Free;
      end;
      LAstDbg.SaveToFile(ChangeFileExt(AExePath, '.ast-debug.txt'));
    finally
      LAstDbg.Free;
    end;
  finally
    LFullPaths.Free;
  end;

  LSerialized := SerializeSymbols(LSyms, LLines);
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

    hUpdate := BeginUpdateResourceW(PWideChar(LSelfNew), False);
    if hUpdate = 0 then begin
      Log(rssInjectResource, '[EMBED-MAP] BeginUpdateResource failed (error ' + IntToStr(GetLastError) + ')');
      System.SysUtils.DeleteFile(LSelfNew);
      Exit;
    end;

    try
      if not UpdateResourceW(hUpdate, RT_RCDATA_W, 'MAPDATA', 0, @LCompressed[0], DWORD(Length(LCompressed))) then begin
        Log(rssInjectResource, '[EMBED-MAP] UpdateResource failed (error ' + IntToStr(GetLastError) + ')');
        EndUpdateResourceW(hUpdate, True);
        System.SysUtils.DeleteFile(LSelfNew);
        Exit;
      end;
      if not EndUpdateResourceW(hUpdate, False) then begin
        Log(rssInjectResource, '[EMBED-MAP] EndUpdateResource failed (error ' + IntToStr(GetLastError) + ')');
        System.SysUtils.DeleteFile(LSelfNew);
        Exit;
      end;
    except
      on E: Exception do begin
        EndUpdateResourceW(hUpdate, True);
        System.SysUtils.DeleteFile(LSelfNew);
        Log(rssInjectResource, '[EMBED-MAP] ' + E.ClassName + ': ' + E.Message);
        Exit;
      end;
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
      Result := True;
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
  hUpdate := BeginUpdateResourceW(PWideChar(LTargetExe), False);
  if hUpdate = 0 then begin
    Log(
        rssInjectResource,
        '[EMBED-MAP] BeginUpdateResource failed (error ' + IntToStr(GetLastError) + '). Is the EXE in use?'
    );
    Exit;
  end;

  try
    if not UpdateResourceW(hUpdate, RT_RCDATA_W, 'MAPDATA', 0, @LCompressed[0], DWORD(Length(LCompressed))) then begin
      Log(rssInjectResource, '[EMBED-MAP] UpdateResource failed (error ' + IntToStr(GetLastError) + ')');
      Exit;
    end;

    if not EndUpdateResourceW(hUpdate, False) then begin
      Log(rssInjectResource, '[EMBED-MAP] EndUpdateResource failed (error ' + IntToStr(GetLastError) + ')');
      Exit;
    end;

    Log(rssDone, '[EMBED-MAP] Successfully injected into ' + ExtractFileName(AExePath));
    Result := True;
  except
    on E: Exception do begin
      EndUpdateResourceW(hUpdate, True);
      Log(rssInjectResource, '[EMBED-MAP] ' + E.ClassName + ': ' + E.Message);
    end;
  end;
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
      Result[I].Address := Pointer(FModuleBase + LEntry.Addr);
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

function TStackTraceManager.GetModuleBaseAddr: DWORD;
begin
  Result := FModuleBase;
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

function TypeNameToKind(const ATypeName: string): Byte;
var
  LName: string;
begin
  LName := UpperCase(Trim(ATypeName));
  if (LName = 'INTEGER')
      or (LName = 'LONGINT')
      or (LName = 'SMALLINT')
      or (LName = 'SHORTINT')
      or (LName = 'NATIVEINT')
      or (LName = 'CARDINAL')
      or (LName = 'LONGWORD')
      or (LName = 'WORD')
      or (LName = 'BYTE')
      or (LName = 'NATIVEUINT') then
    Exit(Ord(tkInteger));
  if (LName = 'INT64') or (LName = 'UINT64') then
    Exit(Ord(tkInt64));
  if (LName = 'BOOLEAN') or (LName = 'BYTEBOOL') or (LName = 'WORDBOOL') or (LName = 'LONGBOOL') then
    Exit(Ord(tkEnumeration));
  if (LName = 'SINGLE') or (LName = 'DOUBLE') or (LName = 'EXTENDED') or (LName = 'CURRENCY') then
    Exit(Ord(tkFloat));
  if LName = 'STRING' then
    Exit(Ord(tkUString));
  if LName = 'CHAR' then
    Exit(Ord(tkWChar));
  if LName = 'ANSICHAR' then
    Exit(Ord(tkChar));
  if LName = 'WIDECHAR' then
    Exit(Ord(tkWChar));
  if LName = 'UNICODESTRING' then
    Exit(Ord(tkUString));
  if LName = 'WIDESTRING' then
    Exit(Ord(tkWString));
  if LName = 'ANSISTRING' then
    Exit(Ord(tkLString));
  if LName = 'SHORTSTRING' then
    Exit(Ord(tkString));
  if (LName = 'POINTER') or (LName.StartsWith('P') and (Length(LName) > 1)) then
    Exit(Ord(tkPointer));
  if LName.StartsWith('T') then
    Exit(Ord(tkClass));
  Result := Ord(tkUnknown);
end;

procedure WalkProcDecls(ANode: TASTNode; AResults: TList<TProcedureDecl>);
var
  I: Integer;
begin
  if ANode = nil then
    Exit;
  if ANode is TProcedureDecl then
    AResults.Add(TProcedureDecl(ANode));
  for I := 0 to ANode.ChildCount - 1 do
    WalkProcDecls(ANode.Children[I], AResults);
  if ANode is TUnitDeclaration then begin
    WalkProcDecls(TUnitDeclaration(ANode).InterfaceSection, AResults);
    WalkProcDecls(TUnitDeclaration(ANode).ImplementationSection, AResults);
  end;
end;

function StripConditionalDirectives(const ASource: string; const ADefines: TArray<string>): string;

  // Search for SubStr in S starting from Offset (1-based)
  function PosFrom(const SubStr, S: string; Offset: Integer): Integer;
  var
    LSearch: string;
  begin
    if Offset > Length(S) then
      Exit(0);
    LSearch := Copy(S, Offset, MaxInt);
    Result := Pos(SubStr, LSearch);
    if Result > 0 then
      Inc(Result, Offset - 1);
  end;

var
  LLines: TArray<string>;
  LResult: TStringList;
  LDefines: TDictionary<string, Boolean>;
  LBranch: array[0..31] of Boolean;
  LDepth: Integer;
  I: Integer;
  LSrcPos, LClose: Integer;
  LDir, LSymbol, LCond: string;
  LLineOut: string;
  LIsKeep: Boolean;
begin
  LDepth := 0;
  LDefines := TDictionary<string, Boolean>.Create;
  try
    LDefines.Add('VER350', True);
    LDefines.Add('WIN32', True);
    LDefines.Add('MSWINDOWS', True);
    LDefines.Add('CPUX86', True);
    LDefines.Add('CONSOLE', True);
    for var K := 0 to High(ADefines) do
      if ADefines[K] <> '' then
        LDefines.AddOrSetValue(UpperCase(Trim(ADefines[K])), True);

    LLines := ASource.Split([#13#10, #10], TStringSplitOptions.None);
    LResult := TStringList.Create;
    try
      for I := 0 to High(LLines) do begin
        LLineOut := '';
        LSrcPos := 1;

        while LSrcPos <= Length(LLines[I]) do begin
          // 1. String literal → skip to end
          if LLines[I][LSrcPos] = '''' then begin
            var LStrEnd := LSrcPos + 1;
            while LStrEnd <= Length(LLines[I]) do begin
              if LLines[I][LStrEnd] = '''' then begin
                if (LStrEnd + 1 <= Length(LLines[I])) and (LLines[I][LStrEnd + 1] = '''') then
                  Inc(LStrEnd, 2)
                else begin
                  Inc(LStrEnd);
                  Break;
                end;
              end
              else
                Inc(LStrEnd);
            end;
            LIsKeep := True;
            for var J := 0 to LDepth - 1 do
              if not LBranch[J] then begin
                LIsKeep := False;
                Break;
              end;
            if LIsKeep then
              LLineOut := LLineOut + Copy(LLines[I], LSrcPos, LStrEnd - LSrcPos);
            LSrcPos := LStrEnd;
            Continue;
          end;

          // 2. // comment → rest of line is comment, output as-is
          if (LLines[I][LSrcPos] = '/') and (LSrcPos < Length(LLines[I])) and (LLines[I][LSrcPos + 1] = '/') then begin
            LIsKeep := True;
            for var J := 0 to LDepth - 1 do
              if not LBranch[J] then begin
                LIsKeep := False;
                Break;
              end;
            if LIsKeep then
              LLineOut := LLineOut + Copy(LLines[I], LSrcPos, MaxInt);
            Break;
          end;

          // 3. {$ directive
          if (LLines[I][LSrcPos] = '{') and (LSrcPos < Length(LLines[I])) and (LLines[I][LSrcPos + 1] = '$') then begin
            LClose := PosFrom('}', LLines[I], LSrcPos + 2);
            if LClose > 0 then begin
              LDir := UpperCase(Trim(Copy(LLines[I], LSrcPos + 2, LClose - LSrcPos - 2)));

              // --- Process the directive ---
              if LDir.StartsWith('IFDEF ') then begin
                LSymbol := UpperCase(Trim(Copy(LDir, 7, MaxInt)));
                LBranch[LDepth] := LDefines.ContainsKey(LSymbol);
                Inc(LDepth);
              end
              else if LDir.StartsWith('IFNDEF ') then begin
                LSymbol := UpperCase(Trim(Copy(LDir, 8, MaxInt)));
                LBranch[LDepth] := not LDefines.ContainsKey(LSymbol);
                Inc(LDepth);
              end
              else if LDir.StartsWith('IF ') then begin
                LCond := UpperCase(Trim(Copy(LDir, 4, MaxInt)));
                if LCond.StartsWith('DEFINED(') and LCond.EndsWith(')') then begin
                  LSymbol := Trim(Copy(LCond, 9, Length(LCond) - 9));
                  LBranch[LDepth] := LDefines.ContainsKey(LSymbol);
                end
                else if LCond.StartsWith('NOT DEFINED(') and LCond.EndsWith(')') then begin
                  LSymbol := Trim(Copy(LCond, 14, Length(LCond) - 14));
                  LBranch[LDepth] := not LDefines.ContainsKey(LSymbol);
                end
                else if LCond.StartsWith('NOT ') then begin
                  LSymbol := Trim(Copy(LCond, 5, MaxInt));
                  LBranch[LDepth] := not LDefines.ContainsKey(LSymbol);
                end
                else
                  LBranch[LDepth] := LDefines.ContainsKey(LCond);
                Inc(LDepth);
              end
              else if LDir.StartsWith('ELSEIF ') then begin
                if LDepth > 0 then begin
                  if not LBranch[LDepth - 1] then begin
                    LCond := UpperCase(Trim(Copy(LDir, 8, MaxInt)));
                    if LCond.StartsWith('DEFINED(') and LCond.EndsWith(')') then begin
                      LSymbol := Trim(Copy(LCond, 9, Length(LCond) - 9));
                      LBranch[LDepth - 1] := LDefines.ContainsKey(LSymbol);
                    end
                    else if LCond.StartsWith('NOT DEFINED(') and LCond.EndsWith(')') then begin
                      LSymbol := Trim(Copy(LCond, 14, Length(LCond) - 14));
                      LBranch[LDepth - 1] := not LDefines.ContainsKey(LSymbol);
                    end
                    else
                      LBranch[LDepth - 1] := LDefines.ContainsKey(LCond);
                  end;
                end;
              end
              else if LDir = 'ELSE' then begin
                if LDepth > 0 then
                  LBranch[LDepth - 1] := not LBranch[LDepth - 1];
              end
              else if LDir.StartsWith('ENDIF') then begin
                if LDepth > 0 then
                  Dec(LDepth);
              end
              else if LDir.StartsWith('DEFINE ') then begin
                LIsKeep := True;
                for var J := 0 to LDepth - 1 do
                  if not LBranch[J] then begin
                    LIsKeep := False;
                    Break;
                  end;
                if LIsKeep then
                  LDefines.AddOrSetValue(UpperCase(Trim(Copy(LDir, 8, MaxInt))), True);
              end
              else if LDir.StartsWith('UNDEF ') then begin
                LIsKeep := True;
                for var J := 0 to LDepth - 1 do
                  if not LBranch[J] then begin
                    LIsKeep := False;
                    Break;
                  end;
                if LIsKeep then
                  LDefines.Remove(UpperCase(Trim(Copy(LDir, 7, MaxInt))));
              end
              else begin
                // Non-conditional directives ({$ALIGN}, {$MINSTACKSIZE}, etc.) → pass through
                LIsKeep := True;
                for var J := 0 to LDepth - 1 do
                  if not LBranch[J] then begin
                    LIsKeep := False;
                    Break;
                  end;
                if LIsKeep then
                  LLineOut := LLineOut + Copy(LLines[I], LSrcPos, LClose - LSrcPos + 1);
              end;

              LSrcPos := LClose + 1;
              Continue;
            end
            else begin
              // No closing brace → output rest as-is
              LIsKeep := True;
              for var J := 0 to LDepth - 1 do
                if not LBranch[J] then begin
                  LIsKeep := False;
                  Break;
                end;
              if LIsKeep then
                LLineOut := LLineOut + Copy(LLines[I], LSrcPos, MaxInt);
              Break;
            end;
          end;

          // 4. Regular character → output if in keep mode
          LIsKeep := True;
          for var J := 0 to LDepth - 1 do
            if not LBranch[J] then begin
              LIsKeep := False;
              Break;
            end;
          if LIsKeep then
            LLineOut := LLineOut + LLines[I][LSrcPos];
          Inc(LSrcPos);
        end;

        if LLineOut <> '' then
          LResult.Add(LLineOut);
      end;
      Result := LResult.Text;
    finally
      LResult.Free;
    end;
  finally
    LDefines.Free;
  end;
end;

function TStackTraceManager.ExtractLocalVarsFromSource(
    const ASourcePath: string;
    const ASymbols: TArray<TMapSymbol>;
    const ADefines: TArray<string>
): TArray<TLocalVarEntry>;
var
  LParser: TDelphiParser;
  LUnit: TUnitDeclaration;
  LProcDecls: TList<TProcedureDecl>;
  LProc: TProcedureDecl;
  LVarDecl: TVariableDeclaration;
  LParam: TParameterDeclaration;
  I, J, K: Integer;
  LVarList: TList<TLocalVarInfo>;
  LResult: TList<TLocalVarEntry>;
  LSimpleName: string;
  LDotPos: Integer;
  LSourceText: string;
  LMatched: Boolean;
  LUnmatchedLog: TStringList;
  LTopSample: Integer;
begin
  Result := nil;
  var LFileName := ExtractFileName(ASourcePath);
  if not FileExists(ASourcePath) then begin
    WriteLn(Format('[AST-DBG] FILE NOT FOUND: %s', [ASourcePath]));
    Exit;
  end;
  try
    LSourceText := TFile.ReadAllText(ASourcePath);
  except
    on E: Exception do begin
      WriteLn(Format('[AST-DBG] READ ERROR %s: %s', [LFileName, E.Message]));
      Exit;
    end;
  end;
  var LPreproc := StripConditionalDirectives(LSourceText, ADefines);
  WriteLn(
      Format(
          '[AST-DBG] Parsing %s (%d bytes -> %d after preproc)...',
          [LFileName, Length(LSourceText), Length(LPreproc)]
      )
  );
  LParser := TDelphiParser.Create;
  try
    LParser.Load(LPreproc, LFileName);
    try
      LUnit := LParser.Parse;
    except
      on E: Exception do begin
        WriteLn(Format('[AST-DBG] PARSE ERROR %s: %s', [LFileName, E.Message]));
        LUnit := nil;
      end;
    end;
  except
    LParser.Free;
    WriteLn(Format('[AST-DBG] PARSER CRASH %s', [LFileName]));
    Exit;
  end;
  if LUnit = nil then begin
    LParser.Free;
    WriteLn(Format('[AST-DBG] PARSE RESULT NIL: %s', [LFileName]));
    Exit;
  end;
  LProcDecls := TList<TProcedureDecl>.Create;
  try
    WalkProcDecls(LUnit, LProcDecls);
    WriteLn(Format('[AST-DBG] %s: %d TProcedureDecl found', [LFileName, LProcDecls.Count]));
    if LProcDecls.Count = 0 then begin
      WriteLn(Format('[AST-DBG] %s: NO PROCS FOUND - checking Unit children...', [LFileName]));
      WriteLn(
          Format(
              '[AST-DBG] %s: Unit.ChildCount=%d, Interface=%s, Implementation=%s',
              [
                  LFileName,
                  LUnit.ChildCount,
                  BoolToStr(LUnit.InterfaceSection <> nil, True),
                  BoolToStr(LUnit.ImplementationSection <> nil, True)
              ]
          )
      );
    end;
    LUnmatchedLog := TStringList.Create;
    try
      LResult := TList<TLocalVarEntry>.Create;
      try
        for I := 0 to LProcDecls.Count - 1 do begin
          LProc := LProcDecls[I];
          LVarList := TList<TLocalVarInfo>.Create;
          try
            for J := 0 to LProc.Parameters.Count - 1 do begin
              LParam := LProc.Parameters[J];
              LVarList.Add(TLocalVarInfo.Create(LParam.Name, TypeNameToKind(LParam.TypeName)));
            end;
            if LProc.LocalDeclarations <> nil then
              for J := 0 to LProc.LocalDeclarations.Count - 1 do
                if LProc.LocalDeclarations[J] is TVariableDeclaration then begin
                  LVarDecl := TVariableDeclaration(LProc.LocalDeclarations[J]);
                  LVarList.Add(TLocalVarInfo.Create(LVarDecl.Name, TypeNameToKind(LVarDecl.TypeName)));
                end;
            for J := 0 to LProc.ChildCount - 1 do
              if LProc.Children[J] is TVariableDeclaration then begin
                LVarDecl := TVariableDeclaration(LProc.Children[J]);
                LVarList.Add(TLocalVarInfo.Create(LVarDecl.Name, TypeNameToKind(LVarDecl.TypeName)));
              end;
            if LVarList.Count = 0 then
              Continue;
            // Unit name from source filename (e.g. "AST.Base" from "AST.Base.pas")
            var LUnitFilter := ChangeFileExt(ExtractFileName(ASourcePath), '') + '.';
            var LUnitFilterLen := Length(LUnitFilter);
            LMatched := False;
            // Extract short name from AST proc (handle ClassName.MethodName)
            var LDotPos2 := LastDelimiter('.', LProc.Name);
            var LProcShortName: string;
            if LDotPos2 > 0 then
              LProcShortName := Copy(LProc.Name, LDotPos2 + 1, MaxInt)
            else
              LProcShortName := LProc.Name;
            for J := 0 to High(ASymbols) do begin
              // Unit prefix must match (eliminates false positives from other units)
              if not SameText(Copy(ASymbols[J].Name, 1, LUnitFilterLen), LUnitFilter) then
                Continue;
              LDotPos := LastDelimiter('.', ASymbols[J].Name);
              if LDotPos >= LUnitFilterLen then
                LSimpleName := Copy(ASymbols[J].Name, LDotPos + 1, MaxInt)
              else
                LSimpleName := ASymbols[J].Name;
              if SameText(LSimpleName, LProcShortName) then begin
                var LEntry: TLocalVarEntry;
                LEntry.SymIdx := J;
                LEntry.ParamCount := LProc.Parameters.Count;
                LEntry.Vars := LVarList.ToArray;
                LResult.Add(LEntry);
                LMatched := True;
                Break;
              end;
            end;
            if not LMatched then begin
              // Log unmatched proc names (cap at 20 per file)
              if LUnmatchedLog.Count < 20 then
                LUnmatchedLog.Add(
                    Format(
                        '    UNMATCHED: "%s" -> short="%s"  (OwnerClass="%s", Kind=%d)',
                        [LProc.Name, LProcShortName, LProc.OwnerClassName, Ord(LProc.Kind)]
                    )
                );
            end;
          finally
            LVarList.Free;
          end;
        end;
        Result := LResult.ToArray;
        WriteLn(
            Format('[AST-DBG] %s: %d matched, %d unmatched entries', [LFileName, LResult.Count, LUnmatchedLog.Count])
        );
        if LUnmatchedLog.Count > 0 then begin
          WriteLn(Format('[AST-DBG] %s: unmatched proc names (first %d):', [LFileName, LUnmatchedLog.Count]));
          for I := 0 to LUnmatchedLog.Count - 1 do
            WriteLn(LUnmatchedLog[I]);
        end;
      finally
        LResult.Free;
      end;
    finally
      LUnmatchedLog.Free;
    end;
  finally
    LProcDecls.Free;
    LParser.Free;
  end;
end;

function TStackTraceManager.ResolveFromMap(VA: DWORD): string;
var
  L, H, M: Integer;
  LPrefAddr: DWORD;
  LFuncName: string;
  LBestLine: string;
begin
  Result := Format('  %p', [Pointer(VA)]);

  if (FMapLoaded <> 1) or (FModuleBase = 0) then
    Exit;

  LPrefAddr := PreferredImageBase + (VA - FModuleBase);

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
  FDbgHelpChecked := -1;
  InstallHooks;
  TryLoadMapFile;
  CheckDbgHelp;
end;

destructor TStackTraceManager.Destroy;
begin
  UninstallHooks;
  if FDbgHelpInitialized <> 0 then
    SymCleanup(FDbgHelpProcess);
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
      LData.Frames[0] := ExceptAddr;
    end;
    if Assigned(FCurrent.FLogger) then begin
      try
        FCurrent.FLogger.HandleException(ExceptObject as Exception, LData);
      except
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
end;

procedure TStackTraceManagerDelphi.UninstallHooks;
begin
  Exception.GetExceptionStackInfoProc := FOrigGetExceptionStackInfoProc;
  Exception.GetStackInfoStringProc := FOrigGetStackInfoStringProc;
  Exception.CleanupStackInfoProc := FOrigCleanUpStackInfoProc;
end;

// GetExceptionStackInfoProc: called by Delphi RTL when an exception is raised.
// Captures the current thread's call stack and returns it as a pointer.
class function TStackTraceManagerDelphi.ExceptionStackInfoProc(P: System.PExceptionRecord): Pointer;
var
  LData: PStackInfoData;
  LCount: DWORD;
  LBP: Pointer;
  LFrameBP: Pointer;
  LMatchIdx: Integer;
begin
  Result := nil;
  LData := AllocMem(SizeOf(TStackInfoData));
  try
    LCount := RtlCaptureStackBackTrace(0, MaxStackFrames, @LData.Frames, nil);
    if LCount > 0 then begin
      LData.FrameCount := LCount;

      // Walk frame chain to capture EBP for each captured frame
{$IFDEF WIN32}
      asm
        mov eax, ebp
        mov LBP, eax
      end;
      LFrameBP := LBP;
      // Skip 2 frames: ExceptionStackInfoProc + Delphi RTL exception handler
      // (matches RtlCaptureStackBackTrace's 2-frame skip)
      try LFrameBP := PPointer(LFrameBP)^; except LFrameBP := nil; end;
      try LFrameBP := PPointer(LFrameBP)^; except LFrameBP := nil; end;
{$ELSE}
      LFrameBP := nil;
{$ENDIF}
      LMatchIdx := 1; // skip ExceptionStackInfoProc frame (first frame = RTL caller)
      while (LFrameBP <> nil) and (LMatchIdx < Integer(LCount)) do begin
        LData.FrameEBP[LMatchIdx] := LFrameBP;
        Inc(LMatchIdx);
        try
          LFrameBP := PPointer(LFrameBP)^;
        except
          Break;
        end;
      end;

      Result := LData;
    end
    else begin
      FreeMem(LData);
      LData := nil;
    end;
    if Assigned(FCurrent) and Assigned(FCurrent.FLogger) then begin
      try
        FCurrent.FLogger.HandleException(P.ExceptObject, Result);
      except
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
function TStackTraceManager.FindLocalVars(SymIdx: Integer): TArray<TLocalVarInfo>;
var
  I: Integer;
begin
  for I := 0 to High(FLocalVarData) do
    if FLocalVarData[I].SymIdx = SymIdx then
      Exit(FLocalVarData[I].Vars);
  Result := nil;
end;

// Parse function prologue to determine total stack frame size.
// Supports x86 prologue: PUSH EBP ($55); MOV EBP, ESP ($8B EC/$89 E5); SUB ESP, N ($83 EC xx / $81 EC xxxxxxxx)
function TStackTraceManager.ReadFunctionPrologue(AFuncAddr: Pointer; out FrameSize: Integer): Boolean;
var
  P: PByte;
begin
  Result := False;
  FrameSize := 0;
  if AFuncAddr = nil then
    Exit;
  try
    P := AFuncAddr;
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
    // SUB ESP, N: $83 EC xx (3 bytes, N < 128)
    if (P[0] = $83) and (P[1] = $EC) then begin
      FrameSize := ShortInt(P[2]);
      if FrameSize < 0 then
        FrameSize := FrameSize + 256;
      Result := True;
      Exit;
    end;
    // SUB ESP, N: $81 EC xx xx xx xx (6 bytes)
    if (P[0] = $81) and (P[1] = $EC) then begin
      FrameSize := P[2] or (P[3] shl 8) or (P[4] shl 16) or (P[5] shl 24);
      Result := True;
      Exit;
    end;
    // No SUB ESP → frame size 0 (leaf function or register-only)
    FrameSize := 0;
    Result := True;
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

// Compute expected EBP offsets for variables based on declaration order, type sizes,
// and total stack frame size. Parameters are at positive offsets (EBP+8, EBP+12, ...),
// local variables at negative offsets (EBP-4, EBP-8, ...).
// Uses natural alignment (min of type size and 4 bytes).
function TStackTraceManager.ComputeVarOffsets(
    const AVars: TArray<TLocalVarInfo>;
    FrameSize, AParamCount: Integer;
    out Offsets: TArray<SmallInt>): Boolean;
var
  I, LSize, LAlign, LDist: Integer;
begin
  SetLength(Offsets, Length(AVars));
  if Length(AVars) = 0 then
    Exit(True);

  // First AParamCount entries are parameters (EBP+8, EBP+12, ...)
  // For register calling convention, first 3 params may be register-optimized;
  // debug builds often retain shadow copies on stack.
  var LParamDist := 8;
  for I := 0 to AParamCount - 1 do begin
    if AVars[I].TypeKind > Byte(High(TypeKindStackSizes)) then
      LSize := SizeOf(Pointer)
    else
      LSize := TypeKindStackSizes[AVars[I].TypeKind];
    if AVars[I].TypeKind = Byte(Ord(tkString)) then
      LSize := 256;
    if LSize <= 0 then
      LSize := SizeOf(Pointer);
    LAlign := LSize;
    if LAlign > 4 then
      LAlign := 4;
    if LAlign < 1 then
      LAlign := 1;
    LParamDist := ((LParamDist + LAlign - 1) div LAlign) * LAlign;
    Offsets[I] := LParamDist;
    LParamDist := LParamDist + LSize;
  end;

  // Remaining entries are local variables (EBP-4, EBP-8, ...)
  LDist := 4;
  for I := AParamCount to High(AVars) do begin
    if AVars[I].TypeKind > Byte(High(TypeKindStackSizes)) then
      LSize := SizeOf(Pointer)
    else
      LSize := TypeKindStackSizes[AVars[I].TypeKind];
    if AVars[I].TypeKind = Byte(Ord(tkString)) then
      LSize := 256;
    if LSize <= 0 then
      LSize := SizeOf(Pointer);
    LAlign := LSize;
    if LAlign > 4 then
      LAlign := 4;
    if LAlign < 1 then
      LAlign := 1;
    LDist := ((LDist + LAlign - 1) div LAlign) * LAlign;
    Offsets[I] := -LDist;
    LDist := LDist + LSize;
  end;

  // Verify: total local area fits within frame
  if (FrameSize > 0) and (AParamCount < Length(AVars)) then begin
    var LTotalLocal := LDist - 4;
    if LTotalLocal > FrameSize then
      Exit(False);
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
    if (LLen < 0) or (LLen > 65535) then
      Exit('<corrupt string>');
    SetLength(Result, LLen);
    if LLen > 0 then begin
{$IFDEF WIN64}
      Move(PByte(P)^, PByte(PChar(Result))^, LLen * 2);
{$ELSE}
      Move(PAnsiChar(P)^, PAnsiChar(PChar(Result))^, LLen);
{$ENDIF}
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
        LVal64 := PInt64(Addr)^;
        if LVal64 = 0 then
          Result := '0.0'
        else
          Result := Format('$%.16x', [LVal64]);
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
      // Unknown type: read as hex pointer
      LPtr := PPointer(Addr)^;
      Result := Format('$%p', [LPtr]);
    end;
  except
    Result := '<access violation>';
  end;
end;

// Format a single stack frame with function name, source location, and local variable values.
function TStackTraceManager.FormatStackFrame(VA: DWORD; AEBP: Pointer): string;
var
  L, H, M: Integer;
  LPrefAddr: DWORD;
  LFuncName: string;
  LBestLine: string;
  LSymIdx: Integer;
  LLocals: TArray<TLocalVarInfo>;
  LOffsets: TArray<SmallInt>;
  LFrameSize: Integer;
  LFuncAddr: Pointer;
  I: Integer;
  LVarAddr: Pointer;
  LVarValue: string;
begin
  Result := Format('  %p', [Pointer(VA)]);

  if (FMapLoaded <> 1) or (FModuleBase = 0) then
    Exit;

  LPrefAddr := PreferredImageBase + (VA - FModuleBase);

  // Binary search for symbol
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

  // Function name
  if LOff > 0 then
    LFuncName := Format('%s+$%x', [ExpandSymbolName(M), LOff])
  else
    LFuncName := ExpandSymbolName(M);
  Result := Format('  %p %s', [Pointer(VA), LFuncName]);

  // Source location
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

  // Local variable values
  LLocals := FindLocalVars(LSymIdx);
  if Length(LLocals) = 0 then
    Exit;
  if AEBP = nil then
    Exit;

  // Get function code address for prologue parsing
  LFuncAddr := Pointer(FModuleBase + (FSymEntries[LSymIdx].Addr - PreferredImageBase));

  if not ReadFunctionPrologue(LFuncAddr, LFrameSize) then
    Exit;

  // Look up ParamCount from FLocalVarData
  var LParamCount: Integer := 0;
  for var K := 0 to High(FLocalVarData) do
    if FLocalVarData[K].SymIdx = LSymIdx then begin
      LParamCount := FLocalVarData[K].ParamCount;
      Break;
    end;

  if not ComputeVarOffsets(LLocals, LFrameSize, LParamCount, LOffsets) then
    Exit;

  for I := 0 to High(LLocals) do begin
    LVarAddr := Pointer(PByte(AEBP) + LOffsets[I]);
    LVarValue := ReadStackVarValue(LVarAddr, LLocals[I].TypeKind);
    Result := Result + LineBrk + Format('    %s: %s', [LLocals[I].Name, LVarValue]);
  end;
end;

// StackInfoStringProc: converts raw stack data into a human-readable
// string. Uses the embedded map data for symbol resolution
// and displays local variable values when available.
class function TStackTraceManager.StackInfoStringProc(Info: Pointer): string;
var
  LData: PStackInfoData;
  I: Integer;
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
    Result := Result + FCurrent.FormatStackFrame(DWORD(LData.Frames[I]), LData.FrameEBP[I]);
  end;
end;

class function TStackTraceManager.GetStackString(Info: Pointer): string;
begin
  Result := StackInfoStringProc(Info);
end;

initialization

finalization

  if Assigned(TStackTraceManager.FCurrent) then
    FreeAndNil(TStackTraceManager.FCurrent);

end.
