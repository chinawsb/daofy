unit DwarfParser;

{ DWARF v2 parser: abbreviation tables, .debug_line, .debug_info }

{$mode objfpc}{$H+}

interface

uses
  SysUtils, Classes, FGL, DwarfTypes;

type
  TAbbrMapArray = specialize TFPGMap<UInt32, TDwarfAbbrTableMap>;

function ParseAbbrevTables(const AData: TBytes): TAbbrMapArray;
function ParseLineNumbers(const AData: TBytes): TLineInfoArray;
function ParseDebugInfo(const AInfoData, AStrData, ARangesData: TBytes;
  const AAbbrMaps: TAbbrMapArray): TFuncInfoArray;

implementation

function ParseAbbrevTables(const AData: TBytes): TAbbrMapArray;
var
  LPos, LTableStart: Integer;
  LCode: UInt64;
  LTag: UInt64;
  LHasChildren: Boolean;
  LAttrName, LAttrForm: UInt64;
  LTable: TDwarfAbbrTableMap;
  LEntry: TDwarfAbbrEntry;
  LPairAttrName, LPairAttrForm: UInt32;
begin
  Result := TAbbrMapArray.Create;
  LPos := 0;

  while LPos < Length(AData) do
  begin
    LTableStart := LPos;
    LTable := TDwarfAbbrTableMap.Create;

    while LPos < Length(AData) do
    begin
      LCode := ReadULeb128(AData, LPos);
      if LCode = 0 then
      begin
        { End of this abbreviation table }
        Result.Add(UInt32(LTableStart), LTable);
        Break;
      end;

      LTag := ReadULeb128(AData, LPos);
      if LPos >= Length(AData) then Break;
      LHasChildren := AData[LPos] <> 0;
      Inc(LPos);

      FillChar(LEntry, SizeOf(LEntry), 0);
      LEntry.Tag := LTag;
      LEntry.HasChildren := LHasChildren;
      SetLength(LEntry.AttrPairs, 0);

      while LPos < Length(AData) do
      begin
        LAttrName := ReadULeb128(AData, LPos);
        LAttrForm := ReadULeb128(AData, LPos);
        if (LAttrName = 0) and (LAttrForm = 0) then Break;
        LPairAttrName := UInt32(LAttrName);
        LPairAttrForm := UInt32(LAttrForm);
        SetLength(LEntry.AttrPairs, Length(LEntry.AttrPairs) + 1);
        LEntry.AttrPairs[High(LEntry.AttrPairs)].AttrName := LPairAttrName;
        LEntry.AttrPairs[High(LEntry.AttrPairs)].AttrForm := LPairAttrForm;
      end;

      LTable.Add(UInt32(LCode), LEntry);
    end;

    { If we reached end of data without a terminator 0 code, free the table }
    if Result.IndexOf(UInt32(LTableStart)) < 0 then
      LTable.Free;
  end;
end;

{ --- .debug_line parser --- }

function ParseFileTable(const AData: TBytes; var APos: Integer;
  ADirs: TStringList): TStringList;
var
  LStart: Integer;
  LName: string;
  LDirIdx: UInt64;
begin
  Result := TStringList.Create;
  while APos < Length(AData) do
  begin
    { Read null-terminated filename }
    LStart := APos;
    while (APos < Length(AData)) and (AData[APos] <> 0) do
      Inc(APos);
    if APos >= Length(AData) then Break;

    LName := '';
    if APos > LStart then
      SetString(LName, PAnsiChar(@AData[LStart]), APos - LStart);
    Inc(APos); { skip null terminator }

    { Empty name = end of table }
    if LName = '' then Break;

    { directory index (ULEB128), time (ULEB128), size (ULEB128) }
    LDirIdx := ReadULeb128(AData, APos);
    ReadULeb128(AData, APos);
    ReadULeb128(AData, APos);

    { Resolve relative path against directory }
    if (LDirIdx < UInt64(ADirs.Count)) and
       ((Length(LName) < 2) or ((LName[2] <> ':') and (Copy(LName, 1, 2) <> '\\'))) then
      LName := ADirs[Integer(LDirIdx)] + LName;

    Result.Add(LName);
  end;
end;

function ParseLineNumbers(const AData: TBytes): TLineInfoArray;
{ Parses ALL compilation units from the .debug_line section.
  FPC generates one CU per source file; each CU has its own header,
  directory table, file table, and line number program. }
var
  LPos: Integer;
  LUnitLength: UInt32;
  LVersion: UInt16;
  LHeaderLength: UInt32;
  LHeaderEnd: Integer;
  LMinInstLen: Byte;
  LMaxOpsPerInst: Byte;
  LDefaultIsStmt: Boolean;
  LLineBase: ShortInt;
  LLineRange: Byte;
  LOpcodeBase: Byte;
  LStdLens: array of Byte;
  LFileTable: TStringList;
  LDirs: TStringList;

  { State machine }
  LAddr: UInt64;
  LLine: Int64;
  LFileIdx: Integer;
  LIsStmt: Boolean;
  LEntries: TLineInfoArray;
  LEntryCount: Integer;

  { Local vars for loops }
  I: Integer;
  LStart: Integer;
  LS: string;
  LFName: string;
  LOp: Byte;
  LExtLen: UInt64;
  LExtEnd: Integer;
  LExtOp: Byte;
  LAdv: UInt64;
  LAdj: UInt64;
  LAdjOp: Integer;
  LAdvS: Int64;
  LFixedAdv: UInt16;
  LSkip: Integer;
  LDirIdx: UInt64;
  LCuCount: Integer;
  LNewUnitLen: UInt32;
  LNewVersion: UInt16;
  LNewHdrLen: UInt32;

  procedure AddEntry;
  begin
    if LEntryCount >= Length(LEntries) then
      SetLength(LEntries, (LEntryCount + 256) and not 255);
    LEntries[LEntryCount].Address := LAddr;
    LEntries[LEntryCount].Line := LLine;
    if (LFileIdx >= 0) and (LFileIdx < LFileTable.Count) then
      LEntries[LEntryCount].FileName := LFileTable[LFileIdx]
    else
      LEntries[LEntryCount].FileName := '';
    Inc(LEntryCount);
  end;

  procedure DoAdvanceAddr(AAdv: UInt64);
  var
    LAdjCalc: UInt64;
  begin
    if LMaxOpsPerInst = 0 then
      LMaxOpsPerInst := 1;
    LAdjCalc := AAdv * LMinInstLen * LMaxOpsPerInst;
    LAddr := LAddr + LAdjCalc;
  end;

  { Try to parse a CU header at LPos. Returns True if successful and
    advances LPos past the header fields (LHeaderEnd is set). }
  function TryReadCUHeader: Boolean;
  begin
    Result := False;
    if LPos + 11 > Length(AData) then Exit;

    Move(AData[LPos], LNewUnitLen, 4);
    if LNewUnitLen = 0 then Exit;
    { Validate: unit_length should not exceed remaining data }
    if LPos + 4 + Integer(LNewUnitLen) > Length(AData) then Exit;

    Move(AData[LPos + 4], LNewVersion, 2);
    { DWARF version must be 2..5 }
    if (LNewVersion < 2) or (LNewVersion > 5) then Exit;

    Move(AData[LPos + 6], LNewHdrLen, 4);
    { header_length sanity: must fit within unit_length }
    if LPos + 4 + 4 + 4 + Integer(LNewHdrLen) > LPos + 4 + Integer(LNewUnitLen) then Exit;

    { Looks like a valid CU header -- accept it }
    LUnitLength := LNewUnitLen;
    LVersion := LNewVersion;
    LHeaderLength := LNewHdrLen;
    Inc(LPos, 4); { skip unit_length }
    Inc(LPos, 2); { skip version }
    Inc(LPos, 4); { skip header_length }
    LHeaderEnd := LPos + Integer(LHeaderLength);
    if LHeaderEnd > Length(AData) then Exit;

    Result := True;
  end;

begin
  SetLength(Result, 0);
  LEntryCount := 0;
  LPos := 0;
  LCuCount := 0;

  { Outer loop: iterate over all compilation units }
  while LPos < Length(AData) do
  begin
    { --- Parse CU header --- }
    if not TryReadCUHeader then Break;

    { Read minimum_instruction_length }
    if LPos >= Length(AData) then Break;
    LMinInstLen := AData[LPos]; Inc(LPos);

    LMaxOpsPerInst := 1;
    if LVersion >= 3 then
    begin
      if LPos >= Length(AData) then Break;
      LMaxOpsPerInst := AData[LPos]; Inc(LPos);
    end;

    if LPos >= Length(AData) then Break;
    LDefaultIsStmt := AData[LPos] <> 0; Inc(LPos);
    if LPos >= Length(AData) then Break;
    LLineBase := ShortInt(AData[LPos]); Inc(LPos);
    if LPos >= Length(AData) then Break;
    LLineRange := AData[LPos]; Inc(LPos);
    if LPos >= Length(AData) then Break;
    LOpcodeBase := AData[LPos]; Inc(LPos);

    SetLength(LStdLens, LOpcodeBase - 1);
    for I := 0 to LOpcodeBase - 2 do
    begin
      if LPos < Length(AData) then
      begin
        LStdLens[I] := AData[LPos];
        Inc(LPos);
      end
      else
        LStdLens[I] := 0;
    end;

    { --- Parse directory table --- }
    LDirs := TStringList.Create;
    try
      while LPos < LHeaderEnd do
      begin
        LStart := LPos;
        while (LPos < LHeaderEnd) and (AData[LPos] <> 0) do
          Inc(LPos);
        LS := '';
        if LPos > LStart then
          SetString(LS, PAnsiChar(@AData[LStart]), LPos - LStart);
        Inc(LPos); { skip null }
        if LS = '' then Break; { empty = end }
        LDirs.Add(LS);
      end;

      { --- Parse file table --- }
      LFileTable := ParseFileTable(AData, LPos, LDirs);
      try
        { --- Execute line number program --- }
        LAddr := 0;
        LLine := 1;
        LFileIdx := 0;
        LIsStmt := LDefaultIsStmt;
        LPos := LHeaderEnd;

        while LPos < Length(AData) do
        begin
          LOp := AData[LPos]; Inc(LPos);

          if LOp = 0 then
          begin
            { Extended opcode }
            LExtLen := ReadULeb128(AData, LPos);
            LExtEnd := LPos + Integer(LExtLen);
            if LPos >= Length(AData) then Break;
            LExtOp := AData[LPos]; Inc(LPos);

            case LExtOp of
              DW_LNE_end_sequence:
              begin
                AddEntry;
                LAddr := 0;
                LLine := 1;
                LFileIdx := 0;
                { This CU is done -- break out of opcode loop }
                LPos := LExtEnd;
                Break;
              end;
              DW_LNE_set_address:
              begin
                if LExtLen >= 8 then
                begin
                  Move(AData[LPos], LAddr, 8);
                  Inc(LPos, 8);
                end;
              end;
            end;

            LPos := LExtEnd;
          end
          else if LOp < LOpcodeBase then
          begin
            { Standard opcode }
            case LOp of
              DW_LNS_copy:
              begin
                AddEntry;
              end;
              DW_LNS_advance_pc:
              begin
                LAdv := ReadULeb128(AData, LPos);
                DoAdvanceAddr(LAdv);
              end;
              DW_LNS_advance_line:
              begin
                LAdvS := ReadSLeb128(AData, LPos);
                LLine := LLine + LAdvS;
              end;
              DW_LNS_set_file:
              begin
                LFileIdx := Integer(ReadULeb128(AData, LPos));
              end;
              DW_LNS_set_column:
              begin
                ReadULeb128(AData, LPos);
              end;
              DW_LNS_negate_stmt:
              begin
                LIsStmt := not LIsStmt;
              end;
              DW_LNS_set_basic_block:
              begin
                { ignore }
              end;
              DW_LNS_const_add_pc:
              begin
                if LLineRange > 0 then
                begin
                  LAdj := (255 - UInt64(LOpcodeBase)) div UInt64(LLineRange);
                  DoAdvanceAddr(LAdj);
                end;
              end;
              DW_LNS_fixed_advance_pc:
              begin
                if LPos + 2 <= Length(AData) then
                begin
                  Move(AData[LPos], LFixedAdv, 2);
                  Inc(LPos, 2);
                  LAddr := LAddr + UInt64(LFixedAdv);
                end;
              end;
            else
              { Unknown standard opcode -- skip its operands }
              if (LOp - 1) < Length(LStdLens) then
              begin
                for LSkip := 0 to LStdLens[LOp - 1] - 1 do
                  ReadULeb128(AData, LPos);
              end;
            end;
          end
          else
          begin
            { Special opcode }
            LAdjOp := LOp - LOpcodeBase;
            if LLineRange > 0 then
            begin
              LLine := LLine + (LAdjOp div LLineRange) + LLineBase;
              DoAdvanceAddr(UInt64(LAdjOp mod LLineRange));
            end;
            AddEntry;
          end;
        end;

        Inc(LCuCount);
      finally
        LFileTable.Free;
      end;
    finally
      LDirs.Free;
    end;

    { After end_sequence, LPos should point right after the extended opcode.
      The next bytes should be either another CU header or end of data.
      TryReadCUHeader will validate and break if nothing valid follows. }
  end;

  WriteLn(Format('  [DWARF] Parsed %d compilation units, %d total line entries',
    [LCuCount, LEntryCount]));

  SetLength(LEntries, LEntryCount);
  Result := LEntries;
end;

{ --- .debug_info parser --- }

function ReadFormValue(const AData: TBytes; var APos: Integer;
  AForm: UInt32; AAddrSize: UInt32; const AStrData: TBytes): UInt64;
var
  LLen: Integer;
  LEnd: Integer;
  LBLen4: UInt32;
begin
  Result := 0;
  case AForm of
    DW_FORM_addr:
    begin
      if APos + AAddrSize <= UInt32(Length(AData)) then
        Move(AData[APos], Result, AAddrSize);
      Inc(APos, AAddrSize);
    end;
    DW_FORM_data1:
    begin
      if APos < Length(AData) then
        Result := AData[APos];
      Inc(APos);
    end;
    DW_FORM_data2:
    begin
      if APos + 2 <= Length(AData) then
        Move(AData[APos], Result, 2);
      Inc(APos, 2);
    end;
    DW_FORM_data4:
    begin
      if APos + 4 <= Length(AData) then
        Move(AData[APos], Result, 4);
      Inc(APos, 4);
    end;
    DW_FORM_data8:
    begin
      if APos + 8 <= Length(AData) then
        Move(AData[APos], Result, 8);
      Inc(APos, 8);
    end;
    DW_FORM_string:
    begin
      { Inline null-terminated -- skip }
      LEnd := APos;
      while (LEnd < Length(AData)) and (AData[LEnd] <> 0) do
        Inc(LEnd);
      Inc(APos, LEnd - APos + 1);
    end;
    DW_FORM_strp:
    begin
      if APos + 4 <= Length(AData) then
        Move(AData[APos], Result, 4);
      Inc(APos, 4);
    end;
    DW_FORM_flag:
    begin
      if APos < Length(AData) then
        Result := AData[APos];
      Inc(APos);
    end;
    DW_FORM_sdata:
    begin
      Result := UInt64(ReadSLeb128(AData, APos));
    end;
    DW_FORM_udata:
    begin
      Result := ReadULeb128(AData, APos);
    end;
    DW_FORM_ref_addr:
    begin
      if APos + 4 <= Length(AData) then
        Move(AData[APos], Result, 4);
      Inc(APos, 4);
    end;
    DW_FORM_ref1:
    begin
      if APos < Length(AData) then
        Result := AData[APos];
      Inc(APos);
    end;
    DW_FORM_ref2:
    begin
      if APos + 2 <= Length(AData) then
        Move(AData[APos], Result, 2);
      Inc(APos, 2);
    end;
    DW_FORM_ref4:
    begin
      if APos + 4 <= Length(AData) then
        Move(AData[APos], Result, 4);
      Inc(APos, 4);
    end;
    DW_FORM_ref8:
    begin
      if APos + 8 <= Length(AData) then
        Move(AData[APos], Result, 8);
      Inc(APos, 8);
    end;
    DW_FORM_block1:
    begin
      if APos < Length(AData) then
        LLen := AData[APos]
      else
        LLen := 0;
      Inc(APos, 1 + LLen);
    end;
    DW_FORM_block2:
    begin
      if APos + 2 <= Length(AData) then
        Move(AData[APos], LLen, 2)
      else
        LLen := 0;
      Inc(APos, 2 + LLen);
    end;
    DW_FORM_block4:
    begin
      if APos + 4 <= Length(AData) then
      begin
        Move(AData[APos], LBLen4, 4);
        LLen := Integer(LBLen4);
      end
      else
        LLen := 0;
      Inc(APos, 4 + LLen);
    end;
    DW_FORM_block:
    begin
      LLen := Integer(ReadULeb128(AData, APos));
      Inc(APos, LLen);
    end;
    DW_FORM_flag_present:
    begin
      Result := 1;
    end;
  else
    Result := 0;
  end;
end;

function ReadFormString(const AData: TBytes; var APos: Integer;
  AForm: UInt32; AAddrSize: UInt32; const AStrData: TBytes): string;
var
  LOffset: UInt32;
  LEnd: Integer;
begin
  Result := '';
  case AForm of
    DW_FORM_string:
    begin
      LEnd := APos;
      while (LEnd < Length(AData)) and (AData[LEnd] <> 0) do
        Inc(LEnd);
      if LEnd > APos then
        SetString(Result, PAnsiChar(@AData[APos]), LEnd - APos);
      Inc(APos, LEnd - APos + 1);
    end;
    DW_FORM_strp:
    begin
      LOffset := 0;
      if APos + 4 <= Length(AData) then
        Move(AData[APos], LOffset, 4);
      Inc(APos, 4);
      if (AStrData <> nil) and (LOffset < UInt32(Length(AStrData))) then
      begin
        LEnd := LOffset;
        while (LEnd < Length(AStrData)) and (AStrData[LEnd] <> 0) do
          Inc(LEnd);
        if LEnd > Integer(LOffset) then
          SetString(Result, PAnsiChar(@AStrData[LOffset]), LEnd - Integer(LOffset));
      end;
    end;
  else
    ReadFormValue(AData, APos, AForm, AAddrSize, AStrData);
    Result := '';
  end;
end;

function ParseDebugInfo(const AInfoData, AStrData, ARangesData: TBytes;
  const AAbbrMaps: TAbbrMapArray): TFuncInfoArray;
var
  LPos, LUnitEnd: Integer;
  LUnitLength: UInt32;
  LVersion: UInt16;
  LAbbrOffset: UInt32;
  LAddrSize: UInt32;
  LAbbrTable: TDwarfAbbrTableMap;
  LEntryCount: Integer;
  LDepth: Integer;
  LCompDir: string;
  LBaseAddr: UInt64;

  { Per-DIE locals }
  LCode: UInt64;
  LAbbrEntry: TDwarfAbbrEntry;
  LSubName: string;
  LLowPC, LHighPC: UInt64;
  LHasLowPC, LHasHighPC, LHasRanges: Boolean;
  LRangesOffset: UInt64;
  LA: Integer;
  LAttrName, LAttrForm: UInt32;
  LS: string;

  { Range resolution locals }
  LROff, LREnd: Integer;
  LRangePair: array[0..1] of UInt64;
  LBaseAddrRange: UInt64;
  LI: Integer;
  LPairCount: Integer;
  LIsDeclaration: Boolean;

  { Diagnostic counters }
  LSubprogCount, LSubprogLowPC, LSubprogRanges, LDeclCount: Integer;

  procedure AddFunc(const AName: string; ALow, AHigh: UInt64);
  begin
    if AName = '' then Exit;
    if LEntryCount >= Length(Result) then
      SetLength(Result, (LEntryCount + 64) and not 63);
    Result[LEntryCount].Name := AName;
    Result[LEntryCount].LowPC := ALow;
    Result[LEntryCount].HighPC := AHigh;
    Inc(LEntryCount);
  end;

  procedure ResolveRanges(AOffset: UInt64; const ABase: UInt64);
  begin
    if (ARangesData = nil) then Exit;
    LROff := Integer(AOffset);
    LREnd := Length(ARangesData);
    LBaseAddrRange := ABase;

    while LROff + 16 <= LREnd do
    begin
      Move(ARangesData[LROff], LRangePair[0], 8);
      Move(ARangesData[LROff + 8], LRangePair[1], 8);
      Inc(LROff, 16);

      if (LRangePair[0] = 0) and (LRangePair[1] = 0) then
        Break; { End of range list }

      AddFunc(LSubName, LBaseAddrRange + LRangePair[0],
              LBaseAddrRange + LRangePair[1]);
    end;
  end;

begin
  SetLength(Result, 0);
  LEntryCount := 0;
  LPos := 0;
  LSubprogCount := 0;
  LSubprogLowPC := 0;
  LSubprogRanges := 0;
  LDeclCount := 0;

  if Length(AInfoData) < 11 then Exit;

  { Loop through ALL compile units }
  while LPos + 11 <= Length(AInfoData) do
  begin
    { CU header }
    Move(AInfoData[LPos], LUnitLength, 4);
    if LUnitLength = 0 then Break;
    Inc(LPos, 4);
    LUnitEnd := LPos + Integer(LUnitLength);
    if LUnitEnd > Length(AInfoData) then Break;

    Move(AInfoData[LPos], LVersion, 2); Inc(LPos, 2);
    Move(AInfoData[LPos], LAbbrOffset, 4); Inc(LPos, 4);
    LAddrSize := AInfoData[LPos]; Inc(LPos);

    { Find abbreviation table for THIS compile unit }
    LAbbrTable := nil;
    if AAbbrMaps.IndexOf(LAbbrOffset) >= 0 then
      LAbbrTable := AAbbrMaps[LAbbrOffset]
    else if AAbbrMaps.Count > 0 then
      LAbbrTable := AAbbrMaps.Data[AAbbrMaps.Keys[0]];

    if LAbbrTable = nil then
    begin
      { Skip this CU, advance to next }
      LPos := LUnitEnd;
      Continue;
    end;

    LCompDir := '';
    LBaseAddr := 0;
    LDepth := 0;

    { Walk DIEs within this compile unit }
    while LPos < LUnitEnd do
    begin
      LCode := ReadULeb128(AInfoData, LPos);
      if LCode = 0 then
      begin
        { End of children }
        Dec(LDepth);
        if LDepth < 0 then LDepth := 0;
        Continue;
      end;

      if LAbbrTable.IndexOf(UInt32(LCode)) < 0 then
        Continue;

      LAbbrEntry := LAbbrTable[UInt32(LCode)];

      { Read attributes }
      LSubName := '';
      LLowPC := 0;
      LHighPC := 0;
      LHasLowPC := False;
      LHasHighPC := False;
      LHasRanges := False;
      LRangesOffset := 0;
      LIsDeclaration := False;

      for LA := 0 to Length(LAbbrEntry.AttrPairs) - 1 do
      begin
        LAttrName := LAbbrEntry.AttrPairs[LA].AttrName;
        LAttrForm := LAbbrEntry.AttrPairs[LA].AttrForm;

        case LAttrName of
          DW_AT_name, DW_AT_linkage_name:
          begin
            LS := ReadFormString(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
            if LS <> '' then
            begin
              if LAbbrEntry.Tag = DW_TAG_compile_unit then
                LCompDir := LS
              else
                LSubName := LS;
            end;
          end;
          DW_AT_comp_dir:
          begin
            LCompDir := ReadFormString(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
          end;
          DW_AT_stmt_list:
          begin
            ReadFormValue(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
          end;
          DW_AT_language:
          begin
            ReadFormValue(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
          end;
          DW_AT_producer:
          begin
            ReadFormString(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
          end;
          DW_AT_low_pc:
          begin
            LLowPC := ReadFormValue(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
            LHasLowPC := True;
          end;
          DW_AT_high_pc:
          begin
            LHighPC := ReadFormValue(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
            LHasHighPC := True;
            { DWARF2: high_pc may be offset from low_pc }
            if (LAttrForm = DW_FORM_data4) or (LAttrForm = DW_FORM_data1) or
               (LAttrForm = DW_FORM_data2) or (LAttrForm = DW_FORM_udata) then
              LHighPC := LLowPC + LHighPC;
          end;
          DW_AT_ranges:
          begin
            LRangesOffset := ReadFormValue(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
            LHasRanges := True;
          end;
          DW_AT_abstract_origin, DW_AT_specification:
          begin
            ReadFormValue(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
          end;
          DW_AT_declaration:
          begin
            LIsDeclaration := True;
            ReadFormValue(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
          end;
        else
          ReadFormValue(AInfoData, LPos, LAttrForm, LAddrSize, AStrData);
        end;
      end;

      { Process compile_unit }
      if (LAbbrEntry.Tag = DW_TAG_compile_unit) and LHasLowPC then
        LBaseAddr := LLowPC;

      { Process subprogram — skip declarations (forward decls, abstract origins) }
      if (LAbbrEntry.Tag = DW_TAG_subprogram) then
      begin
        if LIsDeclaration then
          Inc(LDeclCount)
        else
        begin
          Inc(LSubprogCount);

          if LHasLowPC then
          begin
            Inc(LSubprogLowPC);
            if LHasHighPC then
              AddFunc(LSubName, LLowPC, LHighPC)
            else
              AddFunc(LSubName, LLowPC, LLowPC + 1);
          end
          else if LHasRanges then
          begin
            Inc(LSubprogRanges);
            ResolveRanges(LRangesOffset, LBaseAddr);
          end;
        end;
      end;

      if LAbbrEntry.HasChildren then
        Inc(LDepth);
    end;
  end;

  WriteLn(Format('  [DWARF] subprograms: %d total (%d decl), %d with low_pc, %d with ranges',
    [LSubprogCount + LDeclCount, LDeclCount, LSubprogLowPC, LSubprogRanges]));

  SetLength(Result, LEntryCount);
end;

end.
