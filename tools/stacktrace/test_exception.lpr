program test_exception;

{$mode objfpc}{$H+}

uses
  Fpc.StackTrace,
  Fpc.Test.Exception,
  SysUtils;

begin
  TStackTraceManagerFPC.Initialize;
  RunTest;
  TStackTraceManagerFPC.Finalize;
end.
