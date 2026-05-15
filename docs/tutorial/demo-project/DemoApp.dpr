program DemoApp;

{$APPTYPE CONSOLE}

{$R *.res}

uses
  System.SysUtils,
  MainForm in 'MainForm.pas',
  JsonConfigManager in 'JsonConfigManager.pas';

begin
  try
    MainForm.Run;
  except
    on E: Exception do
      Writeln(E.ClassName, ': ', E.Message);
  end;
  Readln;
end.
