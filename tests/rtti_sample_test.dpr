program RttiSampleTest;

{===============================================================================
  RTTI 示例测试 — 验证 TRttiDiscoverer 能正确扫描 published 方法
  并输出 JSON Schema 格式的能力描述。

  编译: dcc32 tests\rtti_sample_test.dpr -E"tests\" -U"tools\auto"
  运行: tests\RttiSampleTest.exe
===============================================================================}

{$APPTYPE CONSOLE}
{$RANGECHECKS ON}
{$OVERFLOWCHECKS ON}

uses
  System.SysUtils,
  System.JSON,
  DaofyAutomation.RttiDiscovery;

type
  /// <summary>
  ///  示例服务类 — 模拟一个实用的业务服务，展示 RTTI 发现的完整效果。
  /// </summary>
  TSampleService = class
  private
    FCallCount: Integer;
    FLastResult: string;
    constructor Create;
  published
    function Add(A, B: Integer): Integer;
    function Greet(const Name: string): string;
    function GetStatus: string;
    procedure Reset;
    property CallCount: Integer read FCallCount;
    property LastResult: string read FLastResult write FLastResult;
  end;

{ TSampleService }

constructor TSampleService.Create;
begin
  FCallCount := 0;
  FLastResult := '';
end;

function TSampleService.Add(A, B: Integer): Integer;
begin
  Result := A + B;
  FLastResult := Format('%d + %d = %d', [A, B, Result]);
  Inc(FCallCount);
end;

function TSampleService.Greet(const Name: string): string;
begin
  Result := 'Hello, ' + Name + '!';
  FLastResult := Result;
  Inc(FCallCount);
end;

function TSampleService.GetStatus: string;
begin
  Result := Format('CallCount=%d, LastResult="%s"', [FCallCount, FLastResult]);
end;

procedure TSampleService.Reset;
begin
  FCallCount := 0;
  FLastResult := '';
end;

var
  Json: TJSONObject;
begin
  try
    Json := TRttiDiscoverer.DiscoverClass(TSampleService, 'SampleService');
    try
      WriteLn(Json.Format(2));
    finally
      Json.Free;
    end;
  except
    on E: Exception do
      WriteLn('Error: ' + E.Message);
  end;
end.
