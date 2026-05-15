unit MainForm;

interface

procedure Run;

implementation

uses
  System.SysUtils,
  System.JSON,
  JsonConfigManager;

procedure Run;
var
  LConfig: TJsonConfigManager;
  LPort: Integer;
  LHost: string;
begin
  LConfig := TJsonConfigManager.Create('config.json');
  try
    LHost := LConfig.GetValue('server.host', 'localhost');
    LPort := LConfig.GetValue('server.port', 8080);
    Writeln(Format('Server starting at %s:%d...', [LHost, LPort]));
    LConfig.SetValue('server.last_start', DateTimeToStr(Now));
    LConfig.SaveConfig;
    Writeln('Configuration saved.');
  finally
    LConfig.Free;
  end;
end;

end.
