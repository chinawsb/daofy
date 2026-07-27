unit DwarfTypes;

{ DWARF v2 constants, LEB128 helpers, PE types }

{$mode objfpc}{$H+}

interface

uses
  SysUtils, FGL;

const
  { DWARF Tags }
  DW_TAG_compile_unit     = $11;
  DW_TAG_subprogram       = $2E;
  DW_TAG_lexical_block    = $1D;
  DW_TAG_formal_parameter = $05;
  DW_TAG_variable         = $03;
  DW_TAG_pointer_type     = $16;
  DW_TAG_base_type        = $24;
  DW_TAG_subroutine_type  = $13;
  DW_TAG_typedef          = $1C;

  { DWARF Attributes }
  DW_AT_name              = $03;
  DW_AT_stmt_list         = $10;
  DW_AT_low_pc            = $11;
  DW_AT_high_pc           = $12;
  DW_AT_language          = $13;
  DW_AT_ranges            = $19;
  DW_AT_comp_dir          = $1B;
  DW_AT_producer          = $25;
  DW_AT_abstract_origin   = $21;
  DW_AT_specification     = $47;
  DW_AT_linkage_name      = $6E;
  DW_AT_declaration       = $3C;

  { DWARF Forms }
  DW_FORM_addr         = $01;
  DW_FORM_block2       = $03;
  DW_FORM_block4       = $04;
  DW_FORM_data2        = $05;
  DW_FORM_data4        = $06;
  DW_FORM_data8        = $07;
  DW_FORM_string       = $08;
  DW_FORM_block        = $09;
  DW_FORM_block1       = $0A;
  DW_FORM_data1        = $0B;
  DW_FORM_flag         = $0C;
  DW_FORM_sdata        = $0D;
  DW_FORM_strp         = $0E;
  DW_FORM_udata        = $0F;
  DW_FORM_ref_addr     = $10;
  DW_FORM_ref1         = $11;
  DW_FORM_ref2         = $12;
  DW_FORM_ref4         = $13;
  DW_FORM_ref8         = $14;
  DW_FORM_flag_present = $19;

  { Line number standard opcodes }
  DW_LNS_copy             = 1;
  DW_LNS_advance_pc       = 2;
  DW_LNS_advance_line     = 3;
  DW_LNS_set_file         = 4;
  DW_LNS_set_column       = 5;
  DW_LNS_negate_stmt      = 6;
  DW_LNS_set_basic_block  = 7;
  DW_LNS_const_add_pc     = 8;
  DW_LNS_fixed_advance_pc = 9;

  { Line number extended opcodes }
  DW_LNE_end_sequence = 1;
  DW_LNE_set_address  = 2;

  { Range list entries (base address = DWARF4) }
  DW_RLE_end_of_list     = 0;
  DW_RLE_base_addressx   = 1;
  DW_RLE_startx_length   = 2;
  DW_RLE_offset_pair     = 3;
  DW_RLE_startx_endx     = 4;
  DW_RLE_start_length    = 5;

  { PE constants }
  IMAGE_DOS_SIGNATURE = $5A4D;
  IMAGE_NT_SIGNATURE  = $00004550;
  RT_RCDATA           = 10;

type
  TPESection = record
    Name: string;
    VirtualAddress: UInt32;
    VirtualSize: UInt32;
    RawDataOffset: UInt32;
    RawDataSize: UInt32;
    Characteristics: UInt32;
  end;
  TPESectionArray = array of TPESection;

  TPEImage = record
    ImageBase: UInt64;
    Sections: TPESectionArray;
    EntryPoint: UInt32;
    Machine: UInt16;
    Is64Bit: Boolean;
  end;

  TDwarfAbbrEntry = record
    Tag: UInt32;
    HasChildren: Boolean;
    AttrPairs: array of record
      AttrName: UInt32;
      AttrForm: UInt32;
    end;
  end;

  TDwarfAbbrTableMap = specialize TFPGMap<UInt32, TDwarfAbbrEntry>;

  TLineInfo = record
    Address: UInt64;
    FileName: string;
    Line: UInt32;
  end;
  TLineInfoArray = array of TLineInfo;

  TFuncInfo = record
    Name: string;
    LowPC: UInt64;
    HighPC: UInt64;
  end;
  TFuncInfoArray = array of TFuncInfo;

function ReadULeb128(const AData: TBytes; var APos: Integer): UInt64;
function ReadSLeb128(const AData: TBytes; var APos: Integer): Int64;

implementation

function ReadULeb128(const AData: TBytes; var APos: Integer): UInt64;
var
  B: Byte;
  Shift: Integer;
begin
  Result := 0;
  Shift := 0;
  repeat
    if APos >= Length(AData) then Exit;
    B := AData[APos];
    Inc(APos);
    Result := Result or (UInt64(B and $7F) shl Shift);
    Inc(Shift, 7);
  until (B and $80) = 0;
end;

function ReadSLeb128(const AData: TBytes; var APos: Integer): Int64;
var
  B: Byte;
  Shift: Integer;
begin
  Result := 0;
  Shift := 0;
  repeat
    if APos >= Length(AData) then Exit;
    B := AData[APos];
    Inc(APos);
    Result := Result or (Int64(B and $7F) shl Shift);
    Inc(Shift, 7);
  until (B and $80) = 0;
  if (B and $40) <> 0 then
    Result := Result or (Int64(-1) shl Shift);
end;

end.
