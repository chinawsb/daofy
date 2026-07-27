/// <summary>
///   MAPDATA v13 — shared serializer/deserializer for both Delphi and FPC.
///   Both compilers embed the same binary format for stack trace resolution.
/// </summary>
unit MapDataSerializer;

{$IFDEF FPC}
  {$mode delphi}   // Delphi-compatible mode: allows TArray<T>, TList<T>, TDictionary<K,V>
{$ENDIF}

interface

uses
{$IFDEF FPC}
  Classes,
  SysUtils,
  Generics.Collections,
  TypInfo
{$ELSE}
  System.Classes,
  System.SysUtils,
  System.Generics.Collections,
  System.Generics.Defaults,
  System.TypInfo,
  System.Math
{$ENDIF}
       ;

const
  MapResMagic: array[0..3] of AnsiChar = 'MAPD';
  MapResVersion = 13;
  MapOverlayMagic: array[0..7] of AnsiChar = 'MAPOVL01';

  CallConv_StdCall = 0;
  CallConv_CDecl = 1;
  CallConv_CDeclVarArgs = 2;
  CallConv_SafeCall = 3;
  CallConv_Register = 4;
  CallConv_Pascal = 5;
  CallConv_WinApi = 6;

  MaxCapturedStringChars = 1024;

type
  TMapSymbol = record
    Addr: UInt64;
    Name: string;
  end;

  TLineInfo = record
    Addr: UInt64;
    SourceFile: string;
    Line: Integer;
  end;

  TSymbolEntry = record
    Addr: UInt64;
    FirstToken: Integer;
    TokenCount: Integer;
  end;

  TLineEntry = record
    Addr: UInt64;
    Line: Integer;
    FileIdx: Integer;
  end;

  TLocalVarInfo = record
    Name: string;
    TypeName: string;
    TypeInfo: PTypeInfo;
    TypeKind: Byte;
    MaxLen: Word;
    StackOffset: Integer;
    IsRegister: Boolean;
    RegIndex: Byte;
  end;

  TLocalVarEntry = record
    SymIdx: Integer;
    ParamCount: Integer;
    CallConv: Byte;
    IsMethod: Boolean;
    Vars: TArray<TLocalVarInfo>;
  end;

  TMapData = record
    Version: Integer;
    Symbols: TArray<TMapSymbol>;
    SymbolEntries: TArray<TSymbolEntry>;
    LineInfo: TArray<TLineEntry>;
    LocalVars: TArray<TLocalVarEntry>;
    SourcePaths: TArray<string>;
    TokenDict: TArray<string>;
    TokenData: TArray<Integer>;
    Defines: TArray<string>;
  end;

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

  TMapDataSerializer = class
  private
    class function EncodeZigZag(AValue: Int64): UInt64; static;
    class function DecodeZigZag(AValue: UInt64): Int64; static;
    class function WriteVarInt(AStream: TStream; Value: Int64): Integer; static;
    class function ReadVarInt(AStream: TStream; out Value: Int64): Boolean; static;
  public
    class procedure TokenizeName(
        const AName: string;
        ATokens: TList<Integer>;
        ADict: TDictionary<string, Integer>;
        AOrdered: TList<string>
    ); static;
    class function ExpandTokenName(
        const ATokenDict: TArray<string>;
        const ATokenData: TArray<Integer>;
        ASymIdx: Integer;
        const ASymEntries: TArray<TSymbolEntry>
    ): string; static;
    class function Deserialize(const Data: TBytes): TMapData; static;
    class function Serialize(const MapData: TMapData): TBytes; static;
    class function Validate(const Data: TBytes): Boolean; static;
    class function DetectVersion(const Data: TBytes): Integer; static;
    class function Merge(const A, B: TMapData): TMapData; static;
  end;

function KindToTypeName(ATypeKind: Byte): string;
function TypeNameToKind(const ATypeName: string): Byte;

implementation

{ ─────────────────────────────────────────────────────────────────────── }
{  VarInt encoding/decoding                                               }
{ ─────────────────────────────────────────────────────────────────────── }

class function TMapDataSerializer.EncodeZigZag(AValue: Int64): UInt64;
begin
  if AValue < 0 then
    Result := (UInt64(-(AValue + 1)) shl 1) or 1
  else
    Result := UInt64(AValue) shl 1;
end;

class function TMapDataSerializer.DecodeZigZag(AValue: UInt64): Int64;
begin
  if (AValue and 1) = 0 then
    Result := Int64(AValue shr 1)
  else if AValue = High(UInt64) then
    Result := Low(Int64)
  else
    Result := -Int64((AValue shr 1) + 1);
end;

class function TMapDataSerializer.WriteVarInt(AStream: TStream; Value: Int64): Integer;
var
  LRaw: UInt64;
  LByte: Byte;
begin
  Result := 0;
  LRaw := EncodeZigZag(Value);
  repeat
    LByte := Byte(LRaw and $7F);
    LRaw := LRaw shr 7;
    if LRaw > 0 then
      LByte := LByte or $80;
    AStream.WriteBuffer(LByte, 1);
    Inc(Result);
  until LRaw = 0;
end;

class function TMapDataSerializer.ReadVarInt(AStream: TStream; out Value: Int64): Boolean;
var
  LRaw: UInt64;
  LByte: Byte;
  LShift: Integer;
begin
  Value := 0;
  LRaw := 0;
  LShift := 0;
  Result := True;
  while True do begin
    if AStream.Read(LByte, 1) <> 1 then
      Exit(False);
    if LShift > 63 then
      Exit(False);
    if (LShift = 63) and (((LByte and $7F) > 1) or ((LByte and $80) <> 0)) then
      Exit(False);
    LRaw := LRaw or (UInt64(LByte and $7F) shl LShift);
    if (LByte and $80) = 0 then
      Break;
    Inc(LShift, 7);
  end;
  Value := DecodeZigZag(LRaw);
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  Tokenization — split symbol name into minimal reusable tokens          }
{  Separators: . angle-brackets curly-braces dollar                       }
{ ─────────────────────────────────────────────────────────────────────── }

class procedure TMapDataSerializer.TokenizeName(
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

{ ─────────────────────────────────────────────────────────────────────── }
{  Token → name expansion                                                }
{ ─────────────────────────────────────────────────────────────────────── }

class function TMapDataSerializer.ExpandTokenName(
    const ATokenDict: TArray<string>;
    const ATokenData: TArray<Integer>;
    ASymIdx: Integer;
    const ASymEntries: TArray<TSymbolEntry>
): string;
var
  I, LEndToken: Integer;
  LEntry: TSymbolEntry;
begin
  if (ASymIdx < 0) or (ASymIdx >= Length(ASymEntries)) then
    Exit('');
  LEntry := ASymEntries[ASymIdx];
  if LEntry.TokenCount = 0 then
    Exit('');
  if (LEntry.FirstToken < 0) or (LEntry.TokenCount < 0) then
    Exit('');
  LEndToken := LEntry.FirstToken + LEntry.TokenCount;
  if (LEndToken > Length(ATokenData)) or (LEndToken <= LEntry.FirstToken) then
    Exit('');
  for I := LEntry.FirstToken to LEndToken - 1 do
    if (ATokenData[I] < 0) or (ATokenData[I] >= Length(ATokenDict)) then
      Exit('');
  Result := ATokenDict[ATokenData[LEntry.FirstToken]];
  for I := LEntry.FirstToken + 1 to LEndToken - 1 do
    Result := Result + ATokenDict[ATokenData[I]];
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  Deserialize                                                           }
{ ─────────────────────────────────────────────────────────────────────── }

class function TMapDataSerializer.Deserialize(const Data: TBytes): TMapData;
var
  LStream: TMemoryStream;
  LMagic: array[0..3] of AnsiChar;
  LVersion: Integer;
  LSymCount, LFileCount, LTokenCount, LTokCount, LLineCount: Integer;
  I, J, K: Integer;
  LStrLen, LTokenId: Integer;
  LStrBytes: TBytes;
  LAddr: UInt64;
  LDelta: Int64;
  LTokenData: TList<Integer>;
  { Inline vars moved here for FPC 3.2.2 compatibility }
  LFileIdx, LSymStart: Integer;
  LEntry: TLocalVarEntry;
  LKind: Byte;
  LMaxLenInt: Integer;
  LMaxLen: Word;
  LVarName: string;
  LLen: Integer;
  LStackOffRaw: Int64;
  LFlags: Byte;
  LTNCount: Integer;
  LTypeName: string;
  LTokId: Integer;
  LNewLen: Integer;
  LDefCount: Integer;

  function ReadBoundedInt(out AValue: Integer; AMax: UInt64): Boolean;
  var
    LRaw: Int64;
  begin
    Result := False;
    AValue := 0;
    if not ReadVarInt(LStream, LRaw) then
      Exit;
    if (LRaw < 0) or (UInt64(LRaw) > AMax) or (UInt64(LRaw) > UInt64(High(Integer))) then
      Exit;
    AValue := Integer(LRaw);
    Result := True;
  end;

  function ReadMapAddr(out AValue: UInt64): Boolean;
  var
    LRaw: Int64;
  begin
    Result := False;
    AValue := 0;
    if not ReadVarInt(LStream, LRaw) then
      Exit;
    if LRaw < 0 then
      Exit;
    AValue := UInt64(LRaw);
    Result := True;
  end;

  function ApplyAddrDelta(var AValue: UInt64; ADelta: Int64): Boolean;
  var
    LMagnitude: UInt64;
  begin
    Result := False;
    if ADelta >= 0 then begin
      if UInt64(ADelta) > High(UInt64) - AValue then
        Exit;
      AValue := AValue + UInt64(ADelta);
    end
    else begin
      if ADelta = Low(Int64) then
        LMagnitude := UInt64(High(Int64)) + 1
      else
        LMagnitude := UInt64(-ADelta);
      if LMagnitude > AValue then
        Exit;
      AValue := AValue - LMagnitude;
    end;
    Result := True;
  end;
begin
  Result.Version := 0;
  Result.Symbols := nil;
  Result.SymbolEntries := nil;
  Result.LineInfo := nil;
  Result.LocalVars := nil;
  Result.SourcePaths := nil;
  Result.TokenDict := nil;
  Result.TokenData := nil;
  Result.Defines := nil;

  if (Data = nil) or (Length(Data) = 0) then
    Exit;

  LStream := TMemoryStream.Create;
  LTokenData := TList<Integer>.Create;
  try
    LStream.WriteBuffer(Data[0], Length(Data));
    LStream.Position := 0;

    LStream.ReadBuffer(LMagic, 4);
    if (LMagic[0] <> MapResMagic[0])
        or (LMagic[1] <> MapResMagic[1])
        or (LMagic[2] <> MapResMagic[2])
        or (LMagic[3] <> MapResMagic[3]) then
      Exit;

    if not ReadBoundedInt(LVersion, MapResVersion) then
      Exit;
    if LVersion <> MapResVersion then
      Exit;
    Result.Version := LVersion;

    // Source paths
    if not ReadBoundedInt(LFileCount, 10000) then
      Exit;
    SetLength(Result.SourcePaths, LFileCount);
    for I := 0 to LFileCount - 1 do begin
      if not ReadBoundedInt(LStrLen, 10000) then
        Exit;
      if LStrLen > 0 then begin
        SetLength(LStrBytes, LStrLen);
        if LStream.Read(LStrBytes[0], LStrLen) <> LStrLen then
          Exit;
        Result.SourcePaths[I] := TEncoding.UTF8.GetString(LStrBytes);
      end;
    end;

    // Token dictionary
    if not ReadBoundedInt(LTokenCount, 100000) then
      Exit;
    SetLength(Result.TokenDict, LTokenCount);
    for I := 0 to LTokenCount - 1 do begin
      if not ReadBoundedInt(LStrLen, 10000) then
        Exit;
      if LStrLen > 0 then begin
        SetLength(LStrBytes, LStrLen);
        if LStream.Read(LStrBytes[0], LStrLen) <> LStrLen then
          Exit;
        Result.TokenDict[I] := TEncoding.UTF8.GetString(LStrBytes);
      end;
    end;

    // Symbol table (delta addresses + token sequences)
    if not ReadBoundedInt(LSymCount, 1000000) then
      Exit;
    SetLength(Result.SymbolEntries, LSymCount);

    if LSymCount > 0 then begin
      if not ReadMapAddr(LAddr) then
        Exit;
      for I := 0 to LSymCount - 1 do begin
        if not ReadVarInt(LStream, LDelta) then
          Exit;
        if not ApplyAddrDelta(LAddr, LDelta) then
          Exit;
        Result.SymbolEntries[I].Addr := LAddr;
        Result.SymbolEntries[I].FirstToken := LTokenData.Count;

        if not ReadBoundedInt(LTokCount, 1000) then
          Exit;
        Result.SymbolEntries[I].TokenCount := LTokCount;

        for J := 0 to LTokCount - 1 do begin
          if not ReadBoundedInt(LTokenId, UInt64(High(Integer))) then
            Exit;
          if (LTokenId < 0) or (LTokenId >= LTokenCount) then
            Exit;
          LTokenData.Add(LTokenId);
        end;
      end;
    end;
    Result.TokenData := LTokenData.ToArray;

    // Line info table
    if not ReadBoundedInt(LLineCount, 1000000) then
      Exit;
    SetLength(Result.LineInfo, LLineCount);

    if LLineCount > 0 then begin
      if not ReadMapAddr(LAddr) then
        Exit;
      for I := 0 to LLineCount - 1 do begin
        if not ReadVarInt(LStream, LDelta) then
          Exit;
        if not ApplyAddrDelta(LAddr, LDelta) then
          Exit;
        Result.LineInfo[I].Addr := LAddr;

        if not ReadBoundedInt(Result.LineInfo[I].Line, UInt64(High(Integer))) then
          Exit;

        LFileIdx := 0;
        if not ReadBoundedInt(LFileIdx, UInt64(High(Integer))) then
          Exit;
        if (LFileIdx < 0) or (LFileIdx >= Length(Result.SourcePaths)) then
          Exit;
        Result.LineInfo[I].FileIdx := LFileIdx;
      end;
    end;

    // Local variable table (v13 packed format)
    LSymStart := 0;
    if not ReadBoundedInt(LSymStart, 1000000) then
      Exit;

    for I := LSymStart to LSymStart + LSymCount - 1 do begin
      if I >= LSymStart + Length(Result.SymbolEntries) then
        Break;
      if not ReadBoundedInt(LTokenId, UInt64(High(Integer))) then
        Exit;
      if LTokenId = 128 then
        Continue;

      LEntry.SymIdx := I;
      LEntry.CallConv := Byte(LTokenId and 7);
      LEntry.IsMethod := (LTokenId and $08) <> 0;
      LEntry.ParamCount := LTokenId shr 4;
      LEntry.Vars := nil;

      while True do begin
        if not ReadBoundedInt(LTokenId, UInt64(High(Integer))) then
          Exit;
        if LTokenId = 128 then
          Break;

        LKind := 0;
        if LStream.Read(LKind, 1) <> 1 then
          Exit;

        LMaxLenInt := 0;
        if not ReadBoundedInt(LMaxLenInt, High(Word)) then
          Exit;
        LMaxLen := Word(LMaxLenInt);

        LVarName := '';
        if LTokenId < Length(Result.TokenDict) then
          LVarName := Result.TokenDict[LTokenId]
        else
          LVarName := Format('<token%d>', [LTokenId]);

        LLen := Length(LEntry.Vars);
        SetLength(LEntry.Vars, LLen + 1);
        LEntry.Vars[LLen].Name := LVarName;
        LEntry.Vars[LLen].TypeKind := LKind;
        LEntry.Vars[LLen].MaxLen := LMaxLen;
        LEntry.Vars[LLen].TypeInfo := nil;

        // v13 location data
        LStackOffRaw := 0;
        if not ReadVarInt(LStream, LStackOffRaw) then
          Exit;
        if (LStackOffRaw < Low(Integer)) or (LStackOffRaw > High(Integer)) then
          Exit;
        LEntry.Vars[LLen].StackOffset := Integer(LStackOffRaw);
        LFlags := 0;
        if LStream.Read(LFlags, 1) <> 1 then
          Exit;
        LEntry.Vars[LLen].IsRegister := (LFlags and 1) <> 0;
        LEntry.Vars[LLen].RegIndex := (LFlags shr 1) and $7F;

        LTNCount := 0;
        if not ReadBoundedInt(LTNCount, 100) then
          Exit;
        LTypeName := '';
        for K := 0 to LTNCount - 1 do begin
          LTokId := 0;
          if not ReadBoundedInt(LTokId, UInt64(High(Integer))) then
            Exit;
          if (LTokId >= 0) and (LTokId < Length(Result.TokenDict)) then
            LTypeName := LTypeName + Result.TokenDict[LTokId]
          else
            LTypeName := LTypeName + Format('<t%d>', [LTokId]);
        end;
        LEntry.Vars[LLen].TypeName := LTypeName;
      end;

      if Length(LEntry.Vars) > 0 then begin
        LNewLen := Length(Result.LocalVars) + 1;
        SetLength(Result.LocalVars, LNewLen);
        Result.LocalVars[LNewLen - 1] := LEntry;
      end;
    end;

    // Conditional defines
    LDefCount := 0;
    if not ReadBoundedInt(LDefCount, 10000) then
      Exit;
    SetLength(Result.Defines, LDefCount);
    for I := 0 to LDefCount - 1 do begin
      if not ReadBoundedInt(LStrLen, 10000) then
        Exit;
      if LStrLen > 0 then begin
        SetLength(LStrBytes, LStrLen);
        if LStream.Read(LStrBytes[0], LStrLen) <> LStrLen then
          Exit;
        Result.Defines[I] := TEncoding.UTF8.GetString(LStrBytes);
      end;
    end;

    // Build Symbols array from SymbolEntries (expand tokens → names)
    SetLength(Result.Symbols, Length(Result.SymbolEntries));
    for I := 0 to High(Result.SymbolEntries) do begin
      Result.Symbols[I].Addr := Result.SymbolEntries[I].Addr;
      Result.Symbols[I].Name := ExpandTokenName(Result.TokenDict, Result.TokenData, I, Result.SymbolEntries);
    end;
  finally
    LTokenData.Free;
    LStream.Free;
  end;
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  Serialize                                                             }
{ ─────────────────────────────────────────────────────────────────────── }

class function TMapDataSerializer.Serialize(const MapData: TMapData): TBytes;
var
  LStream: TMemoryStream;
  I, J, K: Integer;
  LStrBytes: TBytes;
  LDelta: Int64;
  LTokenIds: TList<Integer>;
  LSavedTokens: TArray<TArray<Integer>>;
  LDict: TDictionary<string, Integer>;
  LOrdered: TList<string>;
  LPathDict: TDictionary<string, Integer>;
  LPaths: TList<string>;
  LLocalTokNames: TArray<TArray<Integer>>;
  LLocalTokKinds: TArray<TArray<Byte>>;
  LLocalTokMaxLens: TArray<TArray<Integer>>;
  LLocalTokTypeNames: TArray<TArray<TArray<Integer>>>;
  LLocalTokStackOffs: TArray<TArray<Integer>>;
  LLocalTokIsRegs: TArray<TArray<Boolean>>;
  LLocalTokRegIdxs: TArray<TArray<Byte>>;
  LSymVarCount: TArray<Integer>;
  LSymVarParamCount: TArray<Integer>;
  LSymVarCallConv: TArray<Byte>;
  LSymVarIsMethod: TArray<Boolean>;
  LAddr: UInt64;
  LPrevAddrInt: Int64;
  LCurAddrInt: Int64;
  LSymLookup: TArray<Integer>;
  { Inline vars moved here for FPC 3.2.2 compatibility }
  LFileIdx, LSymIdx, LVarCount: Integer;
  LFreq: TArray<Integer>;
  LSortedIdx: TArray<Integer>;
  LRemap: TArray<Integer>;
  LNewOrder: TList<string>;
  LCurAddr: UInt64;
  LNewFileIdx: Integer;
  LPacked, LVarLookup: Integer;
  LFlags: Byte;
  LTN: TArray<Integer>;
  LZero: Byte;
  LKey, J2: Integer;

  function ToInt64Addr(AAddr: UInt64; out AValue: Int64): Boolean;
  begin
    Result := AAddr <= UInt64(High(Int64));
    if Result then
      AValue := Int64(AAddr)
    else
      AValue := 0;
  end;
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
    for I := 0 to High(MapData.LineInfo) do begin
      LFileIdx := MapData.LineInfo[I].FileIdx;
      if (LFileIdx >= 0) and (LFileIdx < Length(MapData.SourcePaths)) then
        if not LPathDict.ContainsKey(MapData.SourcePaths[LFileIdx]) then begin
          LPathDict.Add(MapData.SourcePaths[LFileIdx], LPathDict.Count);
          LPaths.Add(MapData.SourcePaths[LFileIdx]);
        end;
    end;
    WriteVarInt(LStream, LPaths.Count);
    for I := 0 to LPaths.Count - 1 do begin
      LStrBytes := TEncoding.UTF8.GetBytes(LPaths[I]);
      WriteVarInt(LStream, Length(LStrBytes));
      if Length(LStrBytes) > 0 then
        LStream.WriteBuffer(LStrBytes[0], Length(LStrBytes));
    end;

    // Phase 2: tokenize all symbol names + local variable names
    SetLength(LSavedTokens, Length(MapData.SymbolEntries));
    SetLength(LLocalTokNames, Length(MapData.LocalVars));
    SetLength(LLocalTokKinds, Length(MapData.LocalVars));
    SetLength(LLocalTokMaxLens, Length(MapData.LocalVars));
    SetLength(LLocalTokTypeNames, Length(MapData.LocalVars));
    SetLength(LLocalTokStackOffs, Length(MapData.LocalVars));
    SetLength(LLocalTokIsRegs, Length(MapData.LocalVars));
    SetLength(LLocalTokRegIdxs, Length(MapData.LocalVars));

    SetLength(LSymLookup, Length(MapData.SymbolEntries));
    for I := 0 to High(MapData.SymbolEntries) do
      LSymLookup[I] := -1;
    for I := 0 to High(MapData.LocalVars) do begin
      LSymIdx := MapData.LocalVars[I].SymIdx;
      if (LSymIdx >= 0) and (LSymIdx < Length(LSymLookup)) then
        LSymLookup[LSymIdx] := I;
    end;

    for I := 0 to High(MapData.SymbolEntries) do begin
      LTokenIds.Clear;
      TokenizeName(
          ExpandTokenName(MapData.TokenDict, MapData.TokenData, I, MapData.SymbolEntries),
          LTokenIds,
          LDict,
          LOrdered
      );
      LSavedTokens[I] := LTokenIds.ToArray;
    end;

    // Tokenize local variable names + type names
    for I := 0 to High(MapData.LocalVars) do begin
      LVarCount := Length(MapData.LocalVars[I].Vars);
      if LVarCount > 0 then begin
        SetLength(LLocalTokNames[I], LVarCount);
        SetLength(LLocalTokKinds[I], LVarCount);
        SetLength(LLocalTokMaxLens[I], LVarCount);
        SetLength(LLocalTokTypeNames[I], LVarCount);
        SetLength(LLocalTokStackOffs[I], LVarCount);
        SetLength(LLocalTokIsRegs[I], LVarCount);
        SetLength(LLocalTokRegIdxs[I], LVarCount);
        for J := 0 to LVarCount - 1 do begin
          LTokenIds.Clear;
          TokenizeName(MapData.LocalVars[I].Vars[J].Name, LTokenIds, LDict, LOrdered);
          if LTokenIds.Count > 0 then
            LLocalTokNames[I][J] := LTokenIds[0]
          else
            LLocalTokNames[I][J] := 0;
          LLocalTokKinds[I][J] := MapData.LocalVars[I].Vars[J].TypeKind;
          LLocalTokMaxLens[I][J] := MapData.LocalVars[I].Vars[J].MaxLen;
          LLocalTokStackOffs[I][J] := MapData.LocalVars[I].Vars[J].StackOffset;
          LLocalTokIsRegs[I][J] := MapData.LocalVars[I].Vars[J].IsRegister;
          LLocalTokRegIdxs[I][J] := MapData.LocalVars[I].Vars[J].RegIndex;
          LTokenIds.Clear;
          if MapData.LocalVars[I].Vars[J].TypeName <> '' then
            TokenizeName(MapData.LocalVars[I].Vars[J].TypeName, LTokenIds, LDict, LOrdered);
          LLocalTokTypeNames[I][J] := LTokenIds.ToArray;
        end;
      end;
    end;

    // Phase 2a: sort token dictionary by frequency (descending)
    if LOrdered.Count > 0 then begin
      SetLength(LFreq, LOrdered.Count);
      for I := 0 to High(LFreq) do
        LFreq[I] := 0;
      for I := 0 to High(LSavedTokens) do
        for J := 0 to High(LSavedTokens[I]) do
          Inc(LFreq[LSavedTokens[I][J]]);
      for I := 0 to High(LLocalTokNames) do
        for J := 0 to High(LLocalTokNames[I]) do
          Inc(LFreq[LLocalTokNames[I][J]]);
      for I := 0 to High(LLocalTokTypeNames) do
        for J := 0 to High(LLocalTokTypeNames[I]) do
          for K := 0 to High(LLocalTokTypeNames[I][J]) do
            Inc(LFreq[LLocalTokTypeNames[I][J][K]]);

      SetLength(LSortedIdx, LOrdered.Count);
      for I := 0 to LOrdered.Count - 1 do
        LSortedIdx[I] := I;

      { Insertion sort by frequency descending (no TComparer needed) }
      for I := 1 to Length(LSortedIdx) - 1 do begin
        LKey := LSortedIdx[I];
        J2 := I - 1;
        while (J2 >= 0) and (LFreq[LSortedIdx[J2]] < LFreq[LKey]) do begin
          LSortedIdx[J2 + 1] := LSortedIdx[J2];
          Dec(J2);
        end;
        LSortedIdx[J2 + 1] := LKey;
      end;

      SetLength(LRemap, LOrdered.Count);
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
        for I := 0 to High(LLocalTokTypeNames) do
          for J := 0 to High(LLocalTokTypeNames[I]) do
            for K := 0 to High(LLocalTokTypeNames[I][J]) do
              LLocalTokTypeNames[I][J][K] := LRemap[LLocalTokTypeNames[I][J][K]];
      finally
        LNewOrder.Free;
      end;
    end;

    // Write token dictionary
    WriteVarInt(LStream, LOrdered.Count);
    for I := 0 to LOrdered.Count - 1 do begin
      LStrBytes := TEncoding.UTF8.GetBytes(LOrdered[I]);
      WriteVarInt(LStream, Length(LStrBytes));
      if Length(LStrBytes) > 0 then
        LStream.WriteBuffer(LStrBytes[0], Length(LStrBytes));
    end;

    // Phase 3: symbol table (delta addresses + token sequences)
    WriteVarInt(LStream, Length(MapData.SymbolEntries));
    if Length(MapData.SymbolEntries) > 0 then begin
      LAddr := MapData.SymbolEntries[0].Addr;
      if not ToInt64Addr(LAddr, LPrevAddrInt) then
        raise ERangeError.Create('MAPDATA symbol address exceeds Int64 range');
      WriteVarInt(LStream, LPrevAddrInt);
      for I := 0 to High(MapData.SymbolEntries) do begin
        LCurAddr := MapData.SymbolEntries[I].Addr;
        if not ToInt64Addr(LCurAddr, LCurAddrInt) then
          raise ERangeError.Create('MAPDATA symbol address exceeds Int64 range');
        LDelta := LCurAddrInt - LPrevAddrInt;
        WriteVarInt(LStream, LDelta);
        LAddr := LCurAddr;
        LPrevAddrInt := LCurAddrInt;

        WriteVarInt(LStream, MapData.SymbolEntries[I].TokenCount);
        for J := 0 to MapData.SymbolEntries[I].TokenCount - 1 do
          if J < Length(LSavedTokens[I]) then
            WriteVarInt(LStream, LSavedTokens[I][J])
          else
            WriteVarInt(LStream, 0);
      end;
    end;

    // Phase 4: line info table
    WriteVarInt(LStream, Length(MapData.LineInfo));
    if Length(MapData.LineInfo) > 0 then begin
      LAddr := MapData.LineInfo[0].Addr;
      if not ToInt64Addr(LAddr, LPrevAddrInt) then
        raise ERangeError.Create('MAPDATA line address exceeds Int64 range');
      WriteVarInt(LStream, LPrevAddrInt);
      for I := 0 to High(MapData.LineInfo) do begin
        LCurAddr := MapData.LineInfo[I].Addr;
        if not ToInt64Addr(LCurAddr, LCurAddrInt) then
          raise ERangeError.Create('MAPDATA line address exceeds Int64 range');
        LDelta := LCurAddrInt - LPrevAddrInt;
        WriteVarInt(LStream, LDelta);
        LAddr := LCurAddr;
        LPrevAddrInt := LCurAddrInt;

        WriteVarInt(LStream, MapData.LineInfo[I].Line);
      LFileIdx := MapData.LineInfo[I].FileIdx;
        LNewFileIdx := 0;
        if (LFileIdx >= 0) and (LFileIdx < Length(MapData.SourcePaths)) then
          LPathDict.TryGetValue(MapData.SourcePaths[LFileIdx], LNewFileIdx);
        WriteVarInt(LStream, LNewFileIdx);
      end;
    end;

    // Phase 5: local variable table
    SetLength(LSymVarCount, Length(MapData.SymbolEntries));
    SetLength(LSymVarParamCount, Length(MapData.SymbolEntries));
    SetLength(LSymVarCallConv, Length(MapData.SymbolEntries));
    SetLength(LSymVarIsMethod, Length(MapData.SymbolEntries));
    for I := 0 to High(LSymVarCount) do begin
      LSymVarCount[I] := 0;
      LSymVarParamCount[I] := 0;
      LSymVarCallConv[I] := CallConv_Register;
      LSymVarIsMethod[I] := False;
    end;
    for I := 0 to High(MapData.LocalVars) do begin
      LSymIdx := MapData.LocalVars[I].SymIdx;
      if (LSymIdx >= 0) and (LSymIdx < Length(LSymVarCount)) then begin
        LSymVarCount[LSymIdx] := Length(MapData.LocalVars[I].Vars);
        LSymVarParamCount[LSymIdx] := MapData.LocalVars[I].ParamCount;
        LSymVarCallConv[LSymIdx] := MapData.LocalVars[I].CallConv;
        LSymVarIsMethod[LSymIdx] := MapData.LocalVars[I].IsMethod;
      end;
    end;

    WriteVarInt(LStream, 0); // LSymStart = 0
    for I := 0 to High(MapData.SymbolEntries) do begin
      if LSymVarCount[I] = 0 then begin
        WriteVarInt(LStream, 128); // sentinel: no local vars
        Continue;
      end;
      LPacked := (LSymVarParamCount[I] shl 4) or (Integer(LSymVarIsMethod[I]) shl 3) or LSymVarCallConv[I];
      WriteVarInt(LStream, LPacked);

      LVarLookup := LSymLookup[I];
      if LVarLookup >= 0 then begin
        for J := 0 to LSymVarCount[I] - 1 do begin
          if J < Length(LLocalTokNames[LVarLookup]) then begin
            WriteVarInt(LStream, LLocalTokNames[LVarLookup][J]);
            LStream.WriteBuffer(LLocalTokKinds[LVarLookup][J], 1);
            WriteVarInt(LStream, LLocalTokMaxLens[LVarLookup][J]);
            WriteVarInt(LStream, LLocalTokStackOffs[LVarLookup][J]);
            LFlags := 0;
            if LLocalTokIsRegs[LVarLookup][J] then
              LFlags := LFlags or 1;
            LFlags := LFlags or (LLocalTokRegIdxs[LVarLookup][J] shl 1);
            LStream.WriteBuffer(LFlags, 1);
            LTN := LLocalTokTypeNames[LVarLookup][J];
            WriteVarInt(LStream, Length(LTN));
            for K := 0 to High(LTN) do
              WriteVarInt(LStream, LTN[K]);
          end
          else begin
            WriteVarInt(LStream, 0);
            LZero := 0;
            LStream.WriteBuffer(LZero, 1);
            WriteVarInt(LStream, 0);
            WriteVarInt(LStream, 0);
            WriteVarInt(LStream, 0); // StackOffset
            LStream.WriteBuffer(LZero, 1); // flags
          end;
        end;
      end;
      WriteVarInt(LStream, 128); // sentinel: end of this symbol's vars
    end;

    // Phase 6: conditional defines
    WriteVarInt(LStream, Length(MapData.Defines));
    for I := 0 to High(MapData.Defines) do begin
      LStrBytes := TEncoding.UTF8.GetBytes(MapData.Defines[I]);
      WriteVarInt(LStream, Length(LStrBytes));
      if Length(LStrBytes) > 0 then
        LStream.WriteBuffer(LStrBytes[0], Length(LStrBytes));
    end;

    SetLength(Result, LStream.Size);
    LStream.Position := 0;
    if LStream.Size > 0 then
      LStream.ReadBuffer(Result[0], LStream.Size);
  finally
    LPaths.Free;
    LPathDict.Free;
    LDict.Free;
    LOrdered.Free;
    LTokenIds.Free;
    LStream.Free;
  end;
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  Validate                                                              }
{ ─────────────────────────────────────────────────────────────────────── }

class function TMapDataSerializer.Validate(const Data: TBytes): Boolean;
var
  LStream: TMemoryStream;
  LMagic: array[0..3] of AnsiChar;
  LVersion: Int64;
begin
  Result := False;
  if (Data = nil) or (Length(Data) < 5) then
    Exit;

  LStream := TMemoryStream.Create;
  try
    LStream.WriteBuffer(Data[0], Length(Data));
    LStream.Position := 0;

    LStream.ReadBuffer(LMagic, 4);
    if (LMagic[0] <> MapResMagic[0])
        or (LMagic[1] <> MapResMagic[1])
        or (LMagic[2] <> MapResMagic[2])
        or (LMagic[3] <> MapResMagic[3]) then
      Exit;

    if not ReadVarInt(LStream, LVersion) then
      Exit;
    if LVersion <> MapResVersion then
      Exit;

    Result := True;
  finally
    LStream.Free;
  end;
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  DetectVersion                                                         }
{ ─────────────────────────────────────────────────────────────────────── }

class function TMapDataSerializer.DetectVersion(const Data: TBytes): Integer;
var
  LStream: TMemoryStream;
  LMagic: array[0..3] of AnsiChar;
  LVersion: Int64;
begin
  Result := 0;
  if (Data = nil) or (Length(Data) < 5) then
    Exit;

  LStream := TMemoryStream.Create;
  try
    LStream.WriteBuffer(Data[0], Length(Data));
    LStream.Position := 0;

    LStream.ReadBuffer(LMagic, 4);
    if (LMagic[0] <> MapResMagic[0])
        or (LMagic[1] <> MapResMagic[1])
        or (LMagic[2] <> MapResMagic[2])
        or (LMagic[3] <> MapResMagic[3]) then
      Exit;

    if not ReadVarInt(LStream, LVersion) then
      Exit;
    Result := LVersion;
  finally
    LStream.Free;
  end;
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  Merge — combine two MAPDATA tables (e.g. EXE + DLL symbols)          }
{ ─────────────────────────────────────────────────────────────────────── }

class function TMapDataSerializer.Merge(const A, B: TMapData): TMapData;
var
  LDict: TDictionary<string, Integer>;
  LOrdered: TList<string>;
  LTokenIds: TList<Integer>;
  I: Integer;
  { Inline vars moved here for FPC 3.2.2 compatibility }
  LAllEntries: TArray<TSymbolEntry>;
  LPathDict: TDictionary<string, Integer>;
  LPaths: TList<string>;
  LDefDict: TDictionary<string, Integer>;
  LDefs: TList<string>;
begin
  Result.Version := A.Version;
  if B.Version > Result.Version then
    Result.Version := B.Version;

  // Merge symbols (B appended after A)
  SetLength(Result.Symbols, Length(A.Symbols) + Length(B.Symbols));
  for I := 0 to High(A.Symbols) do
    Result.Symbols[I] := A.Symbols[I];
  for I := 0 to High(B.Symbols) do
    Result.Symbols[Length(A.Symbols) + I] := B.Symbols[I];

  // Merge symbol entries (rebuild token data for merged result)
  LDict := TDictionary<string, Integer>.Create;
  LOrdered := TList<string>.Create;
  LTokenIds := TList<Integer>.Create;
  try
    // Build token dict from A
    SetLength(Result.TokenDict, 0);
    SetLength(Result.TokenData, 0);

    // Re-tokenize all merged symbol names
    SetLength(LAllEntries, Length(A.Symbols) + Length(B.Symbols));
    for I := 0 to High(A.Symbols) do begin
      LAllEntries[I].Addr := A.Symbols[I].Addr;
      LTokenIds.Clear;
      TokenizeName(A.Symbols[I].Name, LTokenIds, LDict, LOrdered);
      LAllEntries[I].FirstToken := Length(Result.TokenData);
      LAllEntries[I].TokenCount := LTokenIds.Count;
      Result.TokenData := Result.TokenData + LTokenIds.ToArray;
    end;
    for I := 0 to High(B.Symbols) do begin
      LAllEntries[Length(A.Symbols) + I].Addr := B.Symbols[I].Addr;
      LTokenIds.Clear;
      TokenizeName(B.Symbols[I].Name, LTokenIds, LDict, LOrdered);
      LAllEntries[Length(A.Symbols) + I].FirstToken := Length(Result.TokenData);
      LAllEntries[Length(A.Symbols) + I].TokenCount := LTokenIds.Count;
      Result.TokenData := Result.TokenData + LTokenIds.ToArray;
    end;
    Result.SymbolEntries := LAllEntries;
    Result.TokenDict := LOrdered.ToArray;
  finally
    LDict.Free;
    LOrdered.Free;
    LTokenIds.Free;
  end;

  // Merge line info
  SetLength(Result.LineInfo, Length(A.LineInfo) + Length(B.LineInfo));
  for I := 0 to High(A.LineInfo) do
    Result.LineInfo[I] := A.LineInfo[I];
  for I := 0 to High(B.LineInfo) do
    Result.LineInfo[Length(A.LineInfo) + I] := B.LineInfo[I];

  // Merge source paths (dedup)
  LPathDict := TDictionary<string, Integer>.Create;
  LPaths := TList<string>.Create;
  try
    for I := 0 to High(A.SourcePaths) do begin
      if not LPathDict.ContainsKey(A.SourcePaths[I]) then begin
        LPathDict.Add(A.SourcePaths[I], LPaths.Count);
        LPaths.Add(A.SourcePaths[I]);
      end;
    end;
    for I := 0 to High(B.SourcePaths) do begin
      if not LPathDict.ContainsKey(B.SourcePaths[I]) then begin
        LPathDict.Add(B.SourcePaths[I], LPaths.Count);
        LPaths.Add(B.SourcePaths[I]);
      end;
    end;
    Result.SourcePaths := LPaths.ToArray;
  finally
    LPathDict.Free;
    LPaths.Free;
  end;

  // Merge local vars
  SetLength(Result.LocalVars, Length(A.LocalVars) + Length(B.LocalVars));
  for I := 0 to High(A.LocalVars) do
    Result.LocalVars[I] := A.LocalVars[I];
  for I := 0 to High(B.LocalVars) do
    Result.LocalVars[Length(A.LocalVars) + I] := B.LocalVars[I];

  // Merge defines
  LDefDict := TDictionary<string, Integer>.Create;
  LDefs := TList<string>.Create;
  try
    for I := 0 to High(A.Defines) do begin
      if not LDefDict.ContainsKey(A.Defines[I]) then begin
        LDefDict.Add(A.Defines[I], LDefs.Count);
        LDefs.Add(A.Defines[I]);
      end;
    end;
    for I := 0 to High(B.Defines) do begin
      if not LDefDict.ContainsKey(B.Defines[I]) then begin
        LDefDict.Add(B.Defines[I], LDefs.Count);
        LDefs.Add(B.Defines[I]);
      end;
    end;
    Result.Defines := LDefs.ToArray;
  finally
    LDefDict.Free;
    LDefs.Free;
  end;
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  Type name helpers                                                     }
{ ─────────────────────────────────────────────────────────────────────── }

function KindToTypeName(ATypeKind: Byte): string;
begin
  case TTypeKind(ATypeKind) of
    tkInteger: Result := 'Integer';
    tkChar: Result := 'Char';
    tkEnumeration: Result := 'Enumeration';
    tkFloat: Result := 'Float';
    tkString: Result := 'String';
    tkSet: Result := 'Set';
    tkClass: Result := 'Class';
    tkMethod: Result := 'Method';
    tkWChar: Result := 'WideChar';
    tkLString: Result := 'AnsiString';
    tkWString: Result := 'WideString';
    tkVariant: Result := 'Variant';
    tkArray: Result := 'Array';
    tkRecord: Result := 'Record';
    tkInterface: Result := 'Interface';
    tkInt64: Result := 'Int64';
    tkDynArray: Result := 'DynArray';
    tkUString: Result := 'UnicodeString';
    tkClassRef: Result := 'ClassRef';
    tkPointer: Result := 'Pointer';
    tkProcedure: Result := 'Procedure';
  else
    Result := Format('Unknown(%d)', [ATypeKind]);
  end;
end;

function TypeNameToKind(const ATypeName: string): Byte;
var
  LLower: string;
begin
  LLower := LowerCase(ATypeName);
  if LLower = 'integer' then Result := Ord(tkInteger)
  else if LLower = 'char' then Result := Ord(tkChar)
  else if LLower = 'enumeration' then Result := Ord(tkEnumeration)
  else if LLower = 'float' then Result := Ord(tkFloat)
  else if LLower = 'string' then Result := Ord(tkString)
  else if LLower = 'set' then Result := Ord(tkSet)
  else if LLower = 'class' then Result := Ord(tkClass)
  else if LLower = 'method' then Result := Ord(tkMethod)
  else if LLower = 'widechar' then Result := Ord(tkWChar)
  else if LLower = 'ansistring' then Result := Ord(tkLString)
  else if LLower = 'widestring' then Result := Ord(tkWString)
  else if LLower = 'variant' then Result := Ord(tkVariant)
  else if LLower = 'array' then Result := Ord(tkArray)
  else if LLower = 'record' then Result := Ord(tkRecord)
  else if LLower = 'interface' then Result := Ord(tkInterface)
  else if LLower = 'int64' then Result := Ord(tkInt64)
  else if LLower = 'dynarray' then Result := Ord(tkDynArray)
  else if LLower = 'unicodestring' then Result := Ord(tkUString)
  else if LLower = 'classref' then Result := Ord(tkClassRef)
  else if LLower = 'pointer' then Result := Ord(tkPointer)
  else if LLower = 'procedure' then Result := Ord(tkProcedure)
  else Result := 0;
end;

{ ─────────────────────────────────────────────────────────────────────── }
{  TLocalVarInfo helpers (FPC doesn't support record constructors)        }
{ ─────────────────────────────────────────────────────────────────────── }

function MakeLocalVarInfo(const AName, ATypeName: string; ATypeKind: Byte): TLocalVarInfo; overload;
begin
  Result.Name := AName;
  Result.TypeName := ATypeName;
  Result.TypeInfo := nil;
  Result.TypeKind := ATypeKind;
  Result.MaxLen := 0;
  Result.StackOffset := 0;
  Result.IsRegister := False;
  Result.RegIndex := 0;
end;

function MakeLocalVarInfo(const AName, ATypeName: string; ATypeKind: Byte; AMaxLen: Word): TLocalVarInfo; overload;
begin
  Result.Name := AName;
  Result.TypeName := ATypeName;
  Result.TypeInfo := nil;
  Result.TypeKind := ATypeKind;
  Result.MaxLen := AMaxLen;
  Result.StackOffset := 0;
  Result.IsRegister := False;
  Result.RegIndex := 0;
end;

function GetLocalVarTypeSize(const AVar: TLocalVarInfo): Integer;
begin
  if AVar.TypeInfo <> nil then
    Result := GetTypeData(AVar.TypeInfo)^.RecSize
  else
    Result := 0;
end;

end.
