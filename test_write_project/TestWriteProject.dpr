program TestWriteProject;

{$APPTYPE CONSOLE}

uses
  SysUtils;

var
  TestVar: Integer;
begin
  TestVar := 42;
  WriteLn('Original content: TestVar = ', TestVar);
  WriteLn('Press any key to exit...');
  ReadLn;
end.
