unit UserManager;

interface

uses
  System.Classes, System.SysUtils;

type
  TUser = record
    Name: string;
    Age: Integer;
    Email: string;
  end;

  TUserManager = class
  public
    function LoadUsers(const AFilePath: string): TStringList;
    function FindUser(AUsers: TStringList; const AName: string): TUser;
    function GetUserEmails(AUsers: TStringList): TStringList;
    function SortUsers(AUsers: TStringList): TStringList;
  end;

implementation

{ TUserManager }

function TUserManager.LoadUsers(const AFilePath: string): TStringList;
var
  LUsers: TStringList;
begin
  LUsers := TStringList.Create;
  try
    if FileExists(AFilePath) then
      LUsers.LoadFromFile(AFilePath);
    Result := LUsers;
  except
    LUsers.Free;
    raise;
  end;
end;

function TUserManager.FindUser(AUsers: TStringList;
  const AName: string): TUser;
var
  I: Integer;
  LParts: TArray<string>;
begin
  Result.Name := '';
  Result.Age := 0;
  Result.Email := '';
  for I := 0 to AUsers.Count - 1 do
  begin
    LParts := AUsers[I].Split(['|']);
    if (Length(LParts) >= 3) and (LParts[0] = AName) then
    begin
      Result.Name := LParts[0];
      Result.Age := StrToIntDef(LParts[1], 0);
      Result.Email := LParts[2];
      Break;
    end;
  end;
end;

function TUserManager.GetUserEmails(AUsers: TStringList): TStringList;
var
  I: Integer;
  LParts: TArray<string>;
  LEmails: TStringList;
begin
  LEmails := TStringList.Create;
  try
    for I := 0 to AUsers.Count - 1 do
    begin
      LParts := AUsers[I].Split(['|']);
      if Length(LParts) >= 3 then
        LEmails.Add(LParts[2]);
    end;
    Result := LEmails;
  except
    LEmails.Free;
    raise;
  end;
end;

function TUserManager.SortUsers(AUsers: TStringList): TStringList;
begin
  AUsers.Sort;
  Result := AUsers;
end;

end.
