unit LibUtils;

interface

uses
  System.SysUtils, System.Classes;

type
  TStringHelper = class
  public
    class function JoinStrings(const AStrings: TArray<string>;
      const ASeparator: string): string; static;
    class function SplitString(const AText, ASeparator: string): TArray<string>; static;
  end;

implementation

{ TStringHelper }

class function TStringHelper.JoinStrings(const AStrings: TArray<string>;
  const ASeparator: string): string;
var
  I: Integer;
begin
  Result := '';
  for I := Low(AStrings) to High(AStrings) do
  begin
    if I > Low(AStrings) then
      Result := Result + ASeparator;
    Result := Result + AStrings[I];
  end;
end;

class function TStringHelper.SplitString(const AText,
  ASeparator: string): TArray<string>;
begin
  Result := AText.Split([ASeparator], TStringSplitOptions.ExcludeEmpty);
end;

end.
