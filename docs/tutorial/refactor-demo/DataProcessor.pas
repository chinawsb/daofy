unit DataProcessor;

interface

uses
  System.Classes, System.SysUtils;

type
  TDataProcessor = class
  public
    function ParseCSV(const ALine: string): TStringList;
    function SplitLines(const AText: string): TStringList;
    function JoinLines(ALines: TStringList): string;
  end;

implementation

{ TDataProcessor }

function TDataProcessor.ParseCSV(const ALine: string): TStringList;
var
  LFields: TStringList;
  LParts: TArray<string>;
  I: Integer;
begin
  LFields := TStringList.Create;
  try
    LParts := ALine.Split([',']);
    for I := Low(LParts) to High(LParts) do
      LFields.Add(LParts[I].Trim);
    Result := LFields;
  except
    LFields.Free;
    raise;
  end;
end;

function TDataProcessor.SplitLines(const AText: string): TStringList;
var
  LLines: TStringList;
begin
  LLines := TStringList.Create;
  try
    LLines.Text := AText;
    Result := LLines;
  except
    LLines.Free;
    raise;
  end;
end;

function TDataProcessor.JoinLines(ALines: TStringList): string;
var
  I: Integer;
  LSB: TStringBuilder;
begin
  LSB := TStringBuilder.Create;
  try
    for I := 0 to ALines.Count - 1 do
    begin
      if I > 0 then
        LSB.Append(', ');
      LSB.Append(ALines[I]);
    end;
    Result := LSB.ToString;
  finally
    LSB.Free;
  end;
end;

end.
