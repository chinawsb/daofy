unit AutomationTestCases;

interface

uses
  System.Rtti;

type
  {$RTTI EXPLICIT METHODS([vcPublic])}
  TCalculatorFixture = class
  public
    function Add(A, B: Integer): Integer;
    function Echo(const AValue: string): string;
    function EmptyText: string;
    function BoolText(AValue: Boolean): string;
    function SleepAndReturn(AMilliseconds: Integer): string;
    function RaiseFailure: Integer;
  end;

  TDirectCalculator = class
  public
    constructor Create;
    function Multiply(A, B: Integer): Integer;
    function Describe(AValue: Integer): string; overload;
    function Describe(const AValue: string): string; overload;
  end;

implementation

uses
  System.SysUtils,
  Winapi.Windows,
  DaofyAutomation.Base;

function SetupCalculator: TValue;
begin
  Result := TValue.From<TObject>(TCalculatorFixture.Create);
end;

procedure TearDownCalculator(const AValue: TValue);
begin
  if AValue.IsObject then
    AValue.AsObject.Free;
end;

function TCalculatorFixture.Add(A, B: Integer): Integer;
begin
  Result := A + B;
end;

function TCalculatorFixture.Echo(const AValue: string): string;
begin
  Result := AValue;
end;

function TCalculatorFixture.EmptyText: string;
begin
  Result := '';
end;

function TCalculatorFixture.BoolText(AValue: Boolean): string;
begin
  if AValue then
    Result := 'true'
  else
    Result := 'false';
end;

function TCalculatorFixture.SleepAndReturn(
  AMilliseconds: Integer): string;
begin
  Sleep(AMilliseconds);
  Result := 'done';
end;

function TCalculatorFixture.RaiseFailure: Integer;
begin
  raise EInvalidOpException.Create('intentional test failure');
end;

constructor TDirectCalculator.Create;
begin
  inherited Create;
end;

function TDirectCalculator.Multiply(A, B: Integer): Integer;
begin
  Result := A * B;
end;

function TDirectCalculator.Describe(AValue: Integer): string;
begin
  Result := 'integer:' + AValue.ToString;
end;

function TDirectCalculator.Describe(const AValue: string): string;
begin
  Result := 'string:' + AValue;
end;

initialization
  TAutomationProcessorBase.RegisterFixture(
    'AutomationTestCases.TCalculatorFixture',
    SetupCalculator,
    TearDownCalculator);
  TAutomationProcessorBase.RegisterTestClass(
    TDirectCalculator,
    'AutomationTestCases.TDirectCalculator');

finalization
  TAutomationProcessorBase.UnregisterFixture(
    'AutomationTestCases.TCalculatorFixture');
  TAutomationProcessorBase.UnregisterTestClass(
    'AutomationTestCases.TDirectCalculator');

end.
