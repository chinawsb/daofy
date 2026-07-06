unit GrepTest;

interface

uses
  SysUtils, Classes;

type
  TMyClass = class
  private
    FName: string;
    FCount: Integer;
  public
    constructor Create;
    procedure DoSomething;
  end;

  TAnotherClass = class
  public
    procedure DoSomething;
  end;

  TOldClass = class
  public
    // deprecated - will be excluded in some tests
    procedure OldMethod;
  end;

implementation

{ TMyClass }

constructor TMyClass.Create;
begin
  FName := 'test';
  FCount := 0;
end;

procedure TMyClass.DoSomething;
begin
  // TODO: implement this later
  Writeln('Hello from TMyClass');
end;

{ TAnotherClass }

procedure TAnotherClass.DoSomething;
begin
  writeln('hello from TAnotherClass');
end;

{ TOldClass }

procedure TOldClass.OldMethod;
begin
  // old implementation
end;

end.
