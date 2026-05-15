unit ConfigManager;

interface

uses
  System.Classes, System.SysUtils, System.IniFiles;

type
  TConfigManager = class
  private
  public
    function LoadConfig(const AFilePath: string): TStringList;
    procedure SaveConfig(const AFilePath: string; AConfig: TStringList);
    function GetSectionNames(AConfig: TStringList): TStringList;
  end;

implementation

{ TConfigManager }

function TConfigManager.LoadConfig(const AFilePath: string): TStringList;
var
  LConfig: TStringList;
begin
  LConfig := TStringList.Create;
  try
    if FileExists(AFilePath) then
      LConfig.LoadFromFile(AFilePath);
    Result := LConfig;
  except
    LConfig.Free;
    raise;
  end;
end;

procedure TConfigManager.SaveConfig(const AFilePath: string;
  AConfig: TStringList);
begin
  AConfig.SaveToFile(AFilePath);
end;

function TConfigManager.GetSectionNames(AConfig: TStringList): TStringList;
var
  LSections: TStringList;
  I: Integer;
  LLine: string;
begin
  LSections := TStringList.Create;
  try
    for I := 0 to AConfig.Count - 1 do
    begin
      LLine := Trim(AConfig[I]);
      if (Length(LLine) > 0) and (LLine[1] = '[') then
      begin
        LSections.Add(LLine);
      end;
    end;
    Result := LSections;
  except
    LSections.Free;
    raise;
  end;
end;

end.
