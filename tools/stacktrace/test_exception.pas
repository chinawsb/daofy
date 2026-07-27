unit test_exception;

{$mode objfpc}{$H+}

interface

procedure RunTest;

implementation

procedure RunTest;
begin
  raise Exception.Create('Test exception from Fpc.StackTrace');
end;

end.