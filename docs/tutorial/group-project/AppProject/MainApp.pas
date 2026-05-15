unit MainApp;

interface

uses
  System.SysUtils,
  LibUtils;

type
  TAppRunner = class
  public
    procedure Run;
  end;

implementation

{ TAppRunner }

procedure TAppRunner.Run;
var
  LInput: string;
  LParts: TArray<string>;
  LJoined: string;
begin
  Writeln('Enter a comma-separated list:');
  Readln(LInput);
  LParts := TStringHelper.SplitString(LInput, ',');
  LJoined := TStringHelper.JoinStrings(LParts, ' | ');
  Writeln('Result: ' + LJoined);
end;

end.
