unit SymbolEmbedder;

{ Orchestration: read PE → parse DWARF → build MAPD v13 binary → embed RT_RCDATA }

{$mode delphi}{$H+}

interface

uses
  SysUtils, DwarfTypes, DwarfReader, DwarfParser, MapDataSerializer
{$IFDEF WINDOWS}
  , Windows
{$ENDIF}
  ;

function ProcessExecutable(const AExePath: string): Boolean;

implementation

uses
  Classes, Generics.Collections;

function BuildSymbolData(const AFuncs: TFuncInfoArray;
  const ALines: TLineInfoArray; AImageBase: UInt64): TBytes;
var
  LMapData: TMapData;
  LPathDict: TDictionary<string, Integer>;
  LPaths: TList<string>;
  LTokenDict: TDictionary<string, Integer>;
  LTokenOrdered: TList<string>;
  LTokenData: TList<Integer>;
  LTokenIds: TList<Integer>;
  I, J, LFileIdx: Integer;
  LFuncCount, LLineCount: Integer;
begin
  SetLength(Result, 0);
  LPathDict := TDictionary<string, Integer>.Create;
  LPaths := TList<string>.Create;
  LTokenDict := TDictionary<string, Integer>.Create;
  LTokenOrdered := TList<string>.Create;
  LTokenData := TList<Integer>.Create;
  LTokenIds := TList<Integer>.Create;
  try
    { Build SymbolEntries from DWARF function info (skip functions with no real address) }
    LFuncCount := 0;
    for I := 0 to Length(AFuncs) - 1 do
      if (AFuncs[I].Name <> '') and (AFuncs[I].LowPC >= AImageBase) then
        Inc(LFuncCount);

    SetLength(LMapData.SymbolEntries, LFuncCount);
    LFuncCount := 0;
    for I := 0 to Length(AFuncs) - 1 do
    begin
      if (AFuncs[I].Name = '') or (AFuncs[I].LowPC < AImageBase) then Continue;
      LMapData.SymbolEntries[LFuncCount].Addr := AFuncs[I].LowPC - AImageBase;
      LMapData.SymbolEntries[LFuncCount].FirstToken := LTokenData.Count;
      { Tokenize function name }
      LTokenIds.Clear;
      TMapDataSerializer.TokenizeName(AFuncs[I].Name, LTokenIds, LTokenDict, LTokenOrdered);
      LMapData.SymbolEntries[LFuncCount].TokenCount := LTokenIds.Count;
      for J := 0 to LTokenIds.Count - 1 do
        LTokenData.Add(LTokenIds[J]);
      Inc(LFuncCount);
    end;

    { Copy token dict/array }
    SetLength(LMapData.TokenDict, LTokenOrdered.Count);
    for I := 0 to LTokenOrdered.Count - 1 do
      LMapData.TokenDict[I] := LTokenOrdered[I];
    LMapData.TokenData := LTokenData.ToArray;

    { Build SourcePaths + LineInfo from DWARF line info }
    LLineCount := 0;
    for I := 0 to Length(ALines) - 1 do
    begin
      if (ALines[I].Address < $10000000) or (ALines[I].FileName = '') then Continue;
      Inc(LLineCount);
    end;

    SetLength(LMapData.LineInfo, LLineCount);
    LLineCount := 0;
    for I := 0 to Length(ALines) - 1 do
    begin
      if (ALines[I].Address < $10000000) or (ALines[I].FileName = '') then Continue;

      { Deduplicate source paths }
      if not LPathDict.TryGetValue(ALines[I].FileName, LFileIdx) then
      begin
        LFileIdx := LPaths.Count;
        LPathDict.Add(ALines[I].FileName, LFileIdx);
        LPaths.Add(ALines[I].FileName);
      end;

      LMapData.LineInfo[LLineCount].Addr := ALines[I].Address - AImageBase;
      LMapData.LineInfo[LLineCount].Line := ALines[I].Line;
      LMapData.LineInfo[LLineCount].FileIdx := LFileIdx;
      Inc(LLineCount);
    end;

    SetLength(LMapData.SourcePaths, LPaths.Count);
    for I := 0 to LPaths.Count - 1 do
      LMapData.SourcePaths[I] := LPaths[I];

    { No local vars or defines from DWARF embedder (yet) }
    LMapData.LocalVars := nil;
    LMapData.Defines := nil;

    WriteLn(Format('  Functions: %d, Line entries: %d, Source paths: %d, Tokens: %d',
      [LFuncCount, LLineCount, LPaths.Count, LTokenOrdered.Count]));

    { Serialize to MAPD v13 }
    Result := TMapDataSerializer.Serialize(LMapData);
  finally
    LTokenIds.Free;
    LTokenData.Free;
    LTokenOrdered.Free;
    LTokenDict.Free;
    LPaths.Free;
    LPathDict.Free;
  end;
end;

{$IFDEF WINDOWS}
function EmbedResourceWin(const AExePath: string; const AData: TBytes): Boolean;
var
  LHandle: THandle;
  LPtr: Pointer;
begin
  Result := False;
  LPtr := nil;
  if Length(AData) > 0 then
    LPtr := @AData[0];
  WriteLn(Format('  BeginUpdateResource: %s (data=%d bytes, ptr=%p)',
    [AExePath, Length(AData), LPtr]));
  LHandle := BeginUpdateResourceW(PWideChar(UTF8Decode(AExePath)), True);
  if LHandle = 0 then
  begin
    WriteLn('  BeginUpdateResource failed: ', GetLastError);
    Exit;
  end;
  try
    if not UpdateResourceW(LHandle, MakeIntResourceW(RT_RCDATA), 'MAPDATA',
         MAKELANGID(LANG_NEUTRAL, SUBLANG_NEUTRAL),
         LPtr, DWORD(Length(AData))) then
    begin
      WriteLn('  UpdateResource failed: ', GetLastError);
      EndUpdateResourceW(LHandle, True);
      Exit;
    end;
    Result := EndUpdateResourceW(LHandle, False);
    if not Result then
      WriteLn('  EndUpdateResource failed: ', GetLastError);
  except
    on E: Exception do
    begin
      WriteLn('  Exception: ', E.Message);
      EndUpdateResourceW(LHandle, True);
    end;
  end;
end;
{$ENDIF}

function ProcessExecutable(const AExePath: string): Boolean;
var
  LData: TBytes;
  LImage: TPEImage;
  LAbbrevData, LInfoData, LLineData, LStrData, LRangesData: TBytes;
  LAbbrevIdx, LInfoIdx, LLineIdx, LStrIdx, LRangesIdx: Integer;
  LAbbrMaps: TAbbrMapArray;
  LFuncs: TFuncInfoArray;
  LLines: TLineInfoArray;
  LImageBase: UInt64;
  LResData: TBytes;
  I, LNonEmpty: Integer;
{$IFNDEF WINDOWS}
  LSymPath: string;
  LOut: TFileStream;
{$ENDIF}
begin
  Result := False;

  WriteLn('Loading PE file...');
  LData := LoadPEFile(AExePath);
  if Length(LData) = 0 then
  begin
    WriteLn('  Failed to load file.');
    Exit;
  end;

  WriteLn('Parsing PE headers...');
  if not ParsePE(LData, LImage) then
  begin
    WriteLn('  Invalid PE file.');
    Exit;
  end;

  LImageBase := LImage.ImageBase;
  if LImage.Is64Bit then
    WriteLn(Format('  ImageBase: 0x%X, Sections: %d, 64-bit',
      [LImageBase, Length(LImage.Sections)]))
  else
    WriteLn(Format('  ImageBase: 0x%X, Sections: %d, 32-bit',
      [LImageBase, Length(LImage.Sections)]));

  // Print section table for debugging
  for I := 0 to Length(LImage.Sections) - 1 do
    WriteLn(Format('  [%2d] %-20s VA=0x%08X Size=0x%08X Raw=0x%08X',
      [I, LImage.Sections[I].Name, LImage.Sections[I].VirtualAddress,
       LImage.Sections[I].VirtualSize, LImage.Sections[I].RawDataSize]));

  // Find DWARF sections
  LAbbrevIdx := FindSection(LImage, '.debug_abbrev');
  LInfoIdx := FindSection(LImage, '.debug_info');
  LLineIdx := FindSection(LImage, '.debug_line');
  LStrIdx := FindSection(LImage, '.debug_str');
  LRangesIdx := FindSection(LImage, '.debug_ranges');

  if LInfoIdx < 0 then
  begin
    WriteLn('  .debug_info section not found. Was the file compiled with -gw?');
    Exit;
  end;
  if LAbbrevIdx < 0 then
  begin
    WriteLn('  .debug_abbrev section not found.');
    Exit;
  end;
  if LLineIdx < 0 then
  begin
    WriteLn('  .debug_line section not found.');
    Exit;
  end;

  WriteLn('Reading DWARF sections...');
  LAbbrevData := ReadSectionData(LData, LImage, LAbbrevIdx);
  LInfoData := ReadSectionData(LData, LImage, LInfoIdx);
  LLineData := ReadSectionData(LData, LImage, LLineIdx);
  if LStrIdx >= 0 then
    LStrData := ReadSectionData(LData, LImage, LStrIdx)
  else
    SetLength(LStrData, 0);
  if LRangesIdx >= 0 then
    LRangesData := ReadSectionData(LData, LImage, LRangesIdx)
  else
    SetLength(LRangesData, 0);

  WriteLn(Format('  .debug_abbrev: %d bytes', [Length(LAbbrevData)]));
  WriteLn(Format('  .debug_info: %d bytes', [Length(LInfoData)]));
  WriteLn(Format('  .debug_line: %d bytes', [Length(LLineData)]));
  WriteLn(Format('  .debug_str: %d bytes', [Length(LStrData)]));
  WriteLn(Format('  .debug_ranges: %d bytes', [Length(LRangesData)]));

  // Parse abbreviation tables
  WriteLn('Parsing abbreviation tables...');
  LAbbrMaps := ParseAbbrevTables(LAbbrevData);
  LNonEmpty := 0;
  for I := 0 to LAbbrMaps.Count - 1 do
    if LAbbrMaps.Data[I].Count > 0 then
      Inc(LNonEmpty);
  WriteLn(Format('  Found %d abbreviation tables (%d non-empty)',
    [LAbbrMaps.Count, LNonEmpty]));
  for I := 0 to LAbbrMaps.Count - 1 do
    if LAbbrMaps.Data[I].Count > 0 then
      WriteLn(Format('    Table at offset %d: %d entries',
        [LAbbrMaps.Keys[I], LAbbrMaps.Data[I].Count]));

  // Parse .debug_info
  WriteLn('Parsing .debug_info...');
  LFuncs := ParseDebugInfo(LInfoData, LStrData, LRangesData, LAbbrMaps);
  WriteLn(Format('  Found %d functions', [Length(LFuncs)]));
  for I := 0 to Length(LFuncs) - 1 do
    WriteLn(Format('    %s: 0x%X - 0x%X', [LFuncs[I].Name, LFuncs[I].LowPC, LFuncs[I].HighPC]));

  // Parse .debug_line
  WriteLn('Parsing .debug_line...');
  LLines := ParseLineNumbers(LLineData);
  WriteLn(Format('  Found %d line entries', [Length(LLines)]));

  // Build MAPD v13 symbol data
  WriteLn('Building MAPD v13 symbol data...');
  LResData := BuildSymbolData(LFuncs, LLines, LImageBase);
  WriteLn(Format('  MAPDATA resource: %d bytes', [Length(LResData)]));

  // Free abbreviation maps
  for I := 0 to LAbbrMaps.Count - 1 do
    LAbbrMaps.Data[I].Free;
  LAbbrMaps.Free;

  // Embed resource
  WriteLn('Embedding MAPDATA resource...');
{$IFDEF WINDOWS}
  Result := EmbedResourceWin(AExePath, LResData);
  if Result then
    WriteLn('  Success!')
  else
    WriteLn('  Failed to embed resource.');
{$ELSE}
  WriteLn('  Resource embedding not supported on this platform.');
  LSymPath := ChangeFileExt(AExePath, '.sym');
  WriteLn('  Symbol data saved to: ', LSymPath);
  LOut := TFileStream.Create(LSymPath, fmCreate);
  try
    LOut.WriteBuffer(LResData[0], Length(LResData));
  finally
    LOut.Free;
  end;
  Result := True;
{$ENDIF}
end;

end.
