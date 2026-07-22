program AutoTest;

uses
  Vcl.Forms,
  Vcl.DaofyAutomation in '..\..\..\tools\auto\Vcl.DaofyAutomation.pas',
  DaofyAutomation.Base in '..\..\..\tools\auto\DaofyAutomation.Base.pas',
  AutomationTestCases in 'AutomationTestCases.pas',
  MainForm in 'MainForm.pas' {Form1};

begin
  Vcl.DaofyAutomation.AutoStart;
  Application.Initialize;
  Application.MainFormOnTaskbar := True;
  Application.CreateForm(TForm1, Form1);
  Application.Run;
  Vcl.DaofyAutomation.AutoStop;
end.
