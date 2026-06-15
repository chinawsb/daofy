program TestMin;
{$APPTYPE CONSOLE}
{$DEFINITIONINFO ON}
uses
  System.SysUtils,
  System.Rtti,
  System.JSON,
  DaofyAutomation.RttiDiscovery;
type
  TTest = class
  published
    function Foo: Integer;
  end;
function TTest.Foo: Integer;
begin Result := 42; end;
var
  J: TJSONObject;
begin
  try
    J := TRttiDiscoverer.DiscoverClass(TTest, 'test');
    try
      WriteLn(J.Format(2));
    finally J.Free; end;
  except
    on E: Exception do
    begin
      WriteLn('Error: ', E.Message);
      WriteLn('Class: ', E.ClassName);
      {$IF DEFINED(DELPHI_XE2_UP) or (RTLVersion >= 23)}
      if E.StackTrace <> '' then
        WriteLn('StackTrace:', sLineBreak, E.StackTrace);
      {$ENDIF}
    end;
  end;
end.
