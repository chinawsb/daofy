program check_sizes;

{$APPTYPE CONSOLE}

uses
  System.SysUtils;

type
  Str10 = string[10];
  Str100 = string[100];
  Str255 = string[255];

  TTestPacked = packed record
    b: Boolean;
    i: Integer;
  end;

  TTestAligned = record
    b: Boolean;
    i: Integer;
  end;

  TTestFloatPacked = packed record
    s: Single;
    d: Double;
  end;

  TTestFloatAligned = record
    s: Single;
    d: Double;
  end;

begin
  Writeln('Type size check (Win32):');
  Writeln;
  Writeln('  ShortString:     ', SizeOf(ShortString), ' bytes');
  Writeln('  string[10]:      ', SizeOf(Str10), ' bytes');
  Writeln('  string[100]:     ', SizeOf(Str100), ' bytes');
  Writeln('  string[255]:     ', SizeOf(Str255), ' bytes');
  Writeln;
  Writeln('  Single:          ', SizeOf(Single), ' bytes');
  Writeln('  Double:          ', SizeOf(Double), ' bytes');
  Writeln('  Extended:        ', SizeOf(Extended), ' bytes');
  Writeln('  Currency:        ', SizeOf(Currency), ' bytes');
  Writeln;
  Writeln('  Boolean:         ', SizeOf(Boolean), ' bytes');
  Writeln('  ByteBool:        ', SizeOf(ByteBool), ' bytes');
  Writeln('  WordBool:        ', SizeOf(WordBool), ' bytes');
  Writeln('  LongBool:        ', SizeOf(LongBool), ' bytes');
  Writeln;
  Writeln('  Char:            ', SizeOf(Char), ' bytes');
  Writeln('  WideChar:        ', SizeOf(WideChar), ' bytes');
  Writeln('  AnsiChar:        ', SizeOf(AnsiChar), ' bytes');
  Writeln;
  Writeln('  Integer:         ', SizeOf(Integer), ' bytes');
  Writeln('  LongInt:         ', SizeOf(LongInt), ' bytes');
  Writeln('  Cardinal:        ', SizeOf(Cardinal), ' bytes');
  Writeln('  Word:            ', SizeOf(Word), ' bytes');
  Writeln('  Byte:            ', SizeOf(Byte), ' bytes');
  Writeln('  NativeInt:       ', SizeOf(NativeInt), ' bytes');
  Writeln('  NativeUInt:      ', SizeOf(NativeUInt), ' bytes');
  Writeln('  Int64:           ', SizeOf(Int64), ' bytes');
  Writeln('  UInt64:          ', SizeOf(UInt64), ' bytes');
  Writeln;
  Writeln('  Pointer:         ', SizeOf(Pointer), ' bytes');
  Writeln('  TObject:         ', SizeOf(TObject), ' bytes');
  Writeln('  string:          ', SizeOf(string), ' bytes');
  Writeln('  AnsiString:      ', SizeOf(AnsiString), ' bytes');
  Writeln('  WideString:      ', SizeOf(WideString), ' bytes');
  Writeln('  UnicodeString:   ', SizeOf(UnicodeString), ' bytes');
  Writeln;
  Writeln('Struct alignment test:');
  Writeln('  rec[Boolean;Integer] packed:  ', SizeOf(TTestPacked), ' bytes');
  Writeln('  rec[Boolean;Integer] aligned: ', SizeOf(TTestAligned), ' bytes');
  Writeln('  rec[Single;Double] packed:   ', SizeOf(TTestFloatPacked), ' bytes');
  Writeln('  rec[Single;Double] aligned:  ', SizeOf(TTestFloatAligned), ' bytes');
  Writeln;
end.
