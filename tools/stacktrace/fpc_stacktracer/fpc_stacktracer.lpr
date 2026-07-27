program fpc_stacktracer;

{ Standalone tool: reads DWARF debug info from FPC-compiled PE and
  embeds symbol data as RT_RCDATA 'MAPDATA' resource }

{$mode objfpc}{$H+}

uses
  SysUtils, DwarfTypes, DwarfReader, DwarfParser, SymbolEmbedder;

begin
  if ParamCount < 1 then
  begin
    WriteLn('fpc_stacktracer - DWARF symbol embedder for FPC executables');
    WriteLn;
    WriteLn('Usage: fpc_stacktracer.exe <target.exe>');
    WriteLn;
    WriteLn('Reads DWARF v2 debug info (.debug_info, .debug_line, .debug_abbrev)');
    WriteLn('from an FPC-compiled PE executable and embeds a compact symbol');
    WriteLn('resource (MAPDATA) for runtime stack trace resolution.');
    WriteLn;
    WriteLn('The target must be compiled with -gw (DWARF) or -g (debug info).');
    Halt(1);
  end;

  if not FileExists(ParamStr(1)) then
  begin
    WriteLn('Error: File not found: ', ParamStr(1));
    Halt(1);
  end;

  if not ProcessExecutable(ParamStr(1)) then
  begin
    WriteLn;
    WriteLn('FAILED.');
    Halt(1);
  end;

  WriteLn;
  WriteLn('Done.');
end.
