program MainApp;

{$APPTYPE CONSOLE}

{$R *.res}

uses
  System.SysUtils,
  MainApp in 'MainApp.pas',
  LibUtils in '..\LibProject\LibUtils.pas';

var
  LApp: TAppRunner;
begin
  LApp := TAppRunner.Create;
  try
    LApp.Run;
  finally
    LApp.Free;
  end;
end.
