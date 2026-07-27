unit DwarfReader;

{ PE format reader — parses DOS/PE headers, finds DWARF sections }

{$mode objfpc}{$H+}

interface

uses
  SysUtils, DwarfTypes;

function LoadPEFile(const APath: string): TBytes;
function ParsePE(const AData: TBytes; out AImage: TPEImage): Boolean;
function FindSection(const AImage: TPEImage; const AName: string): Integer;
function ReadSectionData(const AData: TBytes; const AImage: TPEImage; ASectionIdx: Integer): TBytes;
function GetImageBase(const AImage: TPEImage): UInt64;

implementation

function LoadPEFile(const APath: string): TBytes;
var
  LFile: file of Byte;
  LSize: Int64;
begin
  SetLength(Result, 0);
  AssignFile(LFile, APath);
  Reset(LFile, 1);
  try
    LSize := FileSize(LFile);
    if LSize <= 0 then Exit;
    SetLength(Result, LSize);
    BlockRead(LFile, Result[0], LSize);
  finally
    CloseFile(LFile);
  end;
end;

{ Read a null-terminated string starting at AData[AOffset] }
function ReadNullStr(const AData: TBytes; AOffset: Integer): string;
var
  LEnd: Integer;
begin
  Result := '';
  LEnd := AOffset;
  while (LEnd < Length(AData)) and (AData[LEnd] <> 0) do
    Inc(LEnd);
  if LEnd > AOffset then
    SetString(Result, PAnsiChar(@AData[AOffset]), LEnd - AOffset);
end;

function ParsePE(const AData: TBytes; out AImage: TPEImage): Boolean;
var
  LPos: Integer;
  LDosSig: UInt16;
  LPeOff: UInt32;
  LPeSig: UInt32;
  LCoffMachine: UInt16;
  LNumSections: UInt16;
  LOptHdrSize: UInt16;
  LOptMagic: UInt16;
  LSectionStart: Integer;
  I, J: Integer;
  LNameBytes: array[0..7] of Byte;
  LName: string;
  LCoffStrOff: UInt32;
  LCoffNumSyms: UInt32;
  LStrTabBase: Integer;
  LStrTabTotalSize: UInt32;
  LStrOff: Integer;
  LNumDigits: Integer;
begin
  Result := False;
  FillChar(AImage, SizeOf(AImage), 0);

  if Length(AData) < 64 then Exit;

  // DOS header
  Move(AData[0], LDosSig, 2);
  if LDosSig <> IMAGE_DOS_SIGNATURE then Exit;

  // PE offset at DOS header offset $3C
  Move(AData[$3C], LPeOff, 4);
  if Integer(LPeOff) + 4 > Length(AData) then Exit;

  // PE signature
  Move(AData[LPeOff], LPeSig, 4);
  if LPeSig <> IMAGE_NT_SIGNATURE then Exit;

  LPos := LPeOff + 4;

  // COFF header (20 bytes)
  if LPos + 20 > Length(AData) then Exit;
  Move(AData[LPos], LCoffMachine, 2);      Inc(LPos, 2);
  Move(AData[LPos], LNumSections, 2);       Inc(LPos, 2);
  Inc(LPos, 4); // TimeDateStamp
  Move(AData[LPos], LCoffStrOff, 4);        Inc(LPos, 4); // PointerToSymbolTable
  Move(AData[LPos], LCoffNumSyms, 4);       Inc(LPos, 4); // NumberOfSymbols
  Move(AData[LPos], LOptHdrSize, 2);        Inc(LPos, 2);
  Inc(LPos, 2); // Characteristics (2 bytes, end of 20-byte COFF header)

  AImage.Machine := LCoffMachine;

  // Optional header magic
  if LPos + 2 > Length(AData) then Exit;
  Move(AData[LPos], LOptMagic, 2);
  AImage.Is64Bit := (LOptMagic = $020B);

  // Read ImageBase from optional header
  if AImage.Is64Bit then
  begin
    if LPos + 32 > Length(AData) then Exit;
    // PE32+: ImageBase at optional header offset +24 (from start of opt header)
    Move(AData[LPos + 24], AImage.ImageBase, 8);
  end
  else
  begin
    if LPos + 28 + 4 > Length(AData) then Exit;
    // PE32: ImageBase at optional header offset +28
    Move(AData[LPos + 28], AImage.ImageBase, 4);
  end;

  // Section headers start right after COFF header + optional header
  LSectionStart := LPeOff + 4 + 20 + LOptHdrSize;

  // Parse section headers
  SetLength(AImage.Sections, LNumSections);
  LPos := LSectionStart;

  for I := 0 to LNumSections - 1 do
  begin
    if LPos + 40 > Length(AData) then Exit;

    // Section name (8 bytes)
    Move(AData[LPos], LNameBytes[0], 8);

    // Check if name uses COFF string table (/offset)
    if (LNameBytes[0] = Ord('/')) and (LNameBytes[1] >= Ord('0')) and (LNameBytes[1] <= Ord('9')) then
    begin
      // Parse numeric offset
      LNumDigits := 0;
      LName := '';
      for J := 1 to 7 do
      begin
        if (LNameBytes[J] >= Ord('0')) and (LNameBytes[J] <= Ord('9')) then
        begin
          LName := LName + Char(LNameBytes[J]);
          Inc(LNumDigits);
        end
        else
          Break;
      end;
      // Placeholder — will resolve below
      AImage.Sections[I].Name := '/' + LName;
    end
    else
    begin
      LName := '';
      for J := 0 to 7 do
      begin
        if LNameBytes[J] = 0 then Break;
        LName := LName + Char(LNameBytes[J]);
      end;
      AImage.Sections[I].Name := LName;
    end;

    Inc(LPos, 8);
    Move(AData[LPos], AImage.Sections[I].VirtualSize, 4);    Inc(LPos, 4);
    Move(AData[LPos], AImage.Sections[I].VirtualAddress, 4);  Inc(LPos, 4);
    Move(AData[LPos], AImage.Sections[I].RawDataSize, 4);     Inc(LPos, 4);
    Move(AData[LPos], AImage.Sections[I].RawDataOffset, 4);   Inc(LPos, 4);
    Inc(LPos, 12); // PointerToRelocations + PointerToLinenumbers + NumberOfRelocations/Linenums
    Move(AData[LPos], AImage.Sections[I].Characteristics, 4); Inc(LPos, 4);
  end;

  // ── Resolve COFF string table names ──
  // String table base = PointerToSymbolTable + NumberOfSymbols * 18
  // First 4 bytes of string table = its total size
  // COFF string offsets are relative to byte 0 of the string table (including the 4-byte size)
  // So a string at COFF offset N lives at file position: StringTableBase + N
  if (LCoffStrOff > 0) and (LCoffNumSyms > 0) then
  begin
    LStrTabBase := Integer(LCoffStrOff) + Integer(LCoffNumSyms) * 18;
    if (LStrTabBase + 4) <= Length(AData) then
    begin
      Move(AData[LStrTabBase], LStrTabTotalSize, 4);

      for I := 0 to Length(AImage.Sections) - 1 do
      begin
        LName := AImage.Sections[I].Name;
        if (Length(LName) > 1) and (LName[1] = '/') then
        begin
          // Parse numeric offset from '/NNN'
          LCoffStrOff := 0;
          for J := 2 to Length(LName) do
          begin
            if (LName[J] >= '0') and (LName[J] <= '9') then
              LCoffStrOff := LCoffStrOff * 10 + (UInt32(Ord(LName[J])) - UInt32(Ord('0')))
            else
              Break;
          end;

          LStrOff := LStrTabBase + Integer(LCoffStrOff);
          if (LStrOff >= LStrTabBase) and (LStrOff < LStrTabBase + Integer(LStrTabTotalSize)) then
          begin
            AImage.Sections[I].Name := ReadNullStr(AData, LStrOff);
          end;
        end;
      end;
    end;
  end;

  Result := True;
end;

function FindSection(const AImage: TPEImage; const AName: string): Integer;
var
  I: Integer;
begin
  Result := -1;
  for I := 0 to Length(AImage.Sections) - 1 do
  begin
    if SameText(AImage.Sections[I].Name, AName) then
      Exit(I);
  end;
end;

function ReadSectionData(const AData: TBytes; const AImage: TPEImage; ASectionIdx: Integer): TBytes;
var
  LSec: TPESection;
begin
  SetLength(Result, 0);
  if (ASectionIdx < 0) or (ASectionIdx >= Length(AImage.Sections)) then Exit;
  LSec := AImage.Sections[ASectionIdx];
  if LSec.RawDataOffset = 0 then Exit;
  if Integer(LSec.RawDataOffset) + Integer(LSec.RawDataSize) > Length(AData) then Exit;
  SetLength(Result, LSec.RawDataSize);
  if LSec.RawDataSize > 0 then
    Move(AData[LSec.RawDataOffset], Result[0], LSec.RawDataSize);
end;

function GetImageBase(const AImage: TPEImage): UInt64;
begin
  Result := AImage.ImageBase;
end;

end.
