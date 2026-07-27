program TrainApp;

uses
  Vcl.Forms,
  Form.UMainForm in 'Form.UMainForm.pas';

{$R *.res}

begin
  Application.Initialize;
  Application.MainFormOnTaskbar := True;
  Application.CreateForm(TUMainFormForm, UMainFormForm);
  Application.Run;
end.
