unit Fpc.Test.Exception;

{$mode objfpc}{$H+}

interface

uses
  SysUtils;

procedure RunTest;

implementation

procedure RunTest;
begin
  raise Exception.Create('Test exception from Fpc.StackTrace');
end;

end.
