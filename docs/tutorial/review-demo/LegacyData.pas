unit LegacyData;

interface

uses
  System.Classes, System.SysUtils;

type
  TDataExporter = class
  public
    function ExportData(AFileName: string): Boolean;
    function GetUserCount: Integer;
    procedure ProcessItems(AItems: TStringList);
    function CalculateTotal: Double;
  end;

implementation

{ TDataExporter }

function TDataExporter.ExportData(AFileName: string): Boolean;
var
  LFile: TStringList;
  LValue: string;
begin
  LFile := TStringList.Create;
  LValue := 'data1;data2;data3';
  LFile.Add(LValue);
  LFile.Add('line2');
  LFile.Add('line3');
  LFile.SaveToFile(AFileName);
  LFile.Free;
  Result := True;
end;

function TDataExporter.GetUserCount: Integer;
var
  LFile: TStringList;
  LCount: Integer;
begin
  if not FileExists('users.dat') then
  begin
    Result := 0;
    Exit;
  end;
  LFile := TStringList.Create;
  try
    LFile.LoadFromFile('users.dat');
    LCount := LFile.Count;
  finally
    LFile.Free;
  end;
  Result := LCount;
end;

function TDataExporter.CalculateTotal: Double;
var
  I: Integer;
  LSum: Double;
begin
  LSum := 0;
  for I := 1 to 10 do
  begin
    LSum := LSum + I * 1.5;
  end;
  if LSum > 100 then
  begin
    LSum := LSum * 0.95;
  end;
  Result := LSum;
end;

procedure TDataExporter.ProcessItems(AItems: TStringList);
var
  I: Integer;
begin
  for I := 0 to AItems.Count - 1 do
  begin
    if Pos('error', LowerCase(AItems[I])) > 0 then
    begin
      Writeln('Found error: ' + AItems[I]);
      AItems.Delete(I);
    end;
  end;
end;

end.
