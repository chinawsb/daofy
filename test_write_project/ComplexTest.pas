unit ComplexTest;

interface

type
  TMyClass = class
  private
    FField2: string;
  public
    procedure Method1;
    function Method2: Boolean;
  end;

implementation

procedure TMyClass.Method1(const AValue: Integer);
begin
  FField1 := 100;
end;

function TMyClass.Method2(const AName: string): Boolean;
begin
  Result := True;
end;

end.
