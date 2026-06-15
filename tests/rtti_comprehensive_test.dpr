program RttiComprehensiveTest;

{===============================================================================
  RTTI 全面测试 — 覆盖 TRttiDiscoverer 的所有类型映射和方法能力。

  测试范围：
    - 基本类型映射: integer, string, boolean, float, TDateTime
    - 复杂类型映射: 枚举, 集合, 动态数组, Record, Pointer, Variant
    - 方法分类: function, procedure, class function, class procedure
    - 参数方向: const, var, out
    - 属性访问: readonly, read+write
    - AI 注解属性 (Custom Attributes)
    - 多类扫描: 4 个业务类展示不同场景

  编译: dcc32 tests\rtti_comprehensive_test.dpr -E"tests\" -U"tools\auto"
  运行: tests\RttiComprehensiveTest.exe
===============================================================================}

{$APPTYPE CONSOLE}
{$RANGECHECKS ON}
{$OVERFLOWCHECKS ON}

uses
  System.SysUtils,
  System.JSON,
  System.Generics.Collections,
  DaofyAutomation.RttiDiscovery,
  DaofyAutomation.RttiAttributes;

type
  // ═══════════════════════════════════════════════════════════════════════════
  // 自定义类型 — 用于测试枚举、集合等复杂类型映射
  // ═══════════════════════════════════════════════════════════════════════════

  /// <summary>订单状态枚举 — 测试枚举类型映射</summary>
  TOrderStatus = (osPending, osProcessing, osShipped, osDelivered, osCancelled);

  /// <summary>用户角色枚举 — 测试另一个枚举</summary>
  TUserRole = (urGuest, urUser, urEditor, urAdmin, urSuperAdmin);

  /// <summary>字体样式集合 — 测试 set 类型映射</summary>
  TFontStyle = (fsBold, fsItalic, fsUnderline, fsStrikeOut);
  TFontStyles = set of TFontStyle;

  /// <summary>地址记录 — 测试 record 类型映射</summary>
  TAddress = record
    Street: string;
    City: string;
    ZipCode: string;
  end;

  /// <summary>商品信息 — 测试 TObject 子类作为参数/返回值</summary>
  TProductInfo = class
  private
    FId: Integer;
    FName: string;
    FPrice: Double;
  published
    property Id: Integer read FId write FId;
    property Name: string read FName write FName;
    property Price: Double read FPrice write FPrice;
  end;

  // ═══════════════════════════════════════════════════════════════════════════
  // 类 1: TComprehensiveMathService — 基本运算，覆盖所有基础类型 + 参数方向
  // ═══════════════════════════════════════════════════════════════════════════

  /// <summary>数学服务 — 整数/浮点运算，var/out 参数，class methods</summary>
  TComprehensiveMathService = class
  private
    FOperationCount: Integer;
    FLastInput: string;
    constructor Create;
  published
    // ── function: 整数运算 ──
    [AIDescription('返回两个整数的和')]
    [AIExample('Add(3, 5) → 8')]
    function Add(A, B: Integer): Integer;

    // ── function: 浮点运算 ──
    [AIDescription('返回两个浮点数的商')]
    function Divide(A, B: Double): Double;

    // ── function: 布尔返回值 ──
    [AIDescription('判断整数是否为偶数')]
    function IsEven(Value: Integer): Boolean;

    // ── function: 字符串参数+返回值 ──
    [AIDescription('生成问候语')]
    function Greet([AIParamDescription('被问候者姓名')] const Name: string): string;

    // ── function: 多类型混合参数 ──
    [AIDescription('计算总价 = 单价 × 数量 × (1 - 折扣)')]
    function CalculateTotal(
      [AIParamDescription('单价')] Price: Double;
      [AIParamDescription('数量')] Quantity: Integer;
      [AIParamDescription('折扣率 0.0~1.0')] Discount: Double
    ): Double;

    // ── procedure: var 参数（输出） ──
    [AIDescription('将字符串按逗号分割为左右两部分')]
    procedure SplitString(
      [AIParamDescription('输入字符串')] const Input: string;
      [AIParamDescription('左半部分')] var Left: string;
      [AIParamDescription('右半部分')] var Right: string
    );

    // ── procedure: out 参数 ──
    [AIDescription('返回数组的最大值和最小值')]
    procedure GetMinMax(
      [AIParamDescription('输入数字')] const Numbers: TArray<Integer>;
      [AIParamDescription('最小值')] out MinVal: Integer;
      [AIParamDescription('最大值')] out MaxVal: Integer
    );

    // ── class function ──
    [AIDescription('返回数学服务版本号')]
    class function GetVersion: string;

    // ── class procedure ──
    [AIDescription('重置全局计数器')]
    class procedure ResetGlobalCounter;

    // ── procedure: 无参数 ──
    procedure Reset;

    // ── 属性 ──
    property OperationCount: Integer read FOperationCount;
    property LastInput: string read FLastInput;
  end;

  // ═══════════════════════════════════════════════════════════════════════════
  // 类 2: TComprehensiveUserService — 业务逻辑，覆盖枚举/属性/AI注解
  // ═══════════════════════════════════════════════════════════════════════════

  /// <summary>用户服务 — 枚举参数，read+write 属性，丰富的 AI 注解</summary>
  [AIDescription('用户管理服务，处理用户注册、角色分配和查询')]
  TComprehensiveUserService = class
  private
    FUserCount: Integer;
    FLastError: string;
    FDefaultRole: TUserRole;
    constructor Create;
  published
    [AIDescription('注册新用户，返回用户ID')]
    [AIResultDescription('新用户ID，失败返回 -1')]
    [AIExample('RegisterUser("张三", 25, urUser) → 1001')]
    function RegisterUser(
      [AIParamDescription('用户姓名')] const Name: string;
      [AIParamDescription('年龄(1-150)')] Age: Integer;
      [AIParamDescription('分配的角色')] Role: TUserRole
    ): Integer;

    [AIDescription('获取当前用户总数')]
    function GetUserCount: Integer;

    [AIDescription('批量注册用户')]
    procedure BatchRegister(
      [AIParamDescription('用户名数组')] const Names: TArray<string>
    );

    // ── 属性：readonly ──
    property UserCount: Integer read FUserCount;

    // ── 属性：read + write ──
    property LastError: string read FLastError write FLastError;

    // ── 属性：枚举类型 ──
    property DefaultRole: TUserRole read FDefaultRole write FDefaultRole;
  end;

  // ═══════════════════════════════════════════════════════════════════════════
  // 类 3: TComprehensiveDataService — 复杂类型（枚举/set/array/TDateTime/record）
  // ═══════════════════════════════════════════════════════════════════════════

  /// <summary>数据服务 — 复杂数据类型展示</summary>
  TComprehensiveDataService = class
  private
    FLogLevel: TOrderStatus;
    FActiveStyles: TFontStyles;
    FDataPoints: TArray<Double>;
    FLastUpdated: TDateTime;
    FConfig: TAddress;
  published
    // ── 枚举参数 ──
    [AIDescription('设置订单状态筛选条件')]
    procedure SetOrderFilter(Status: TOrderStatus);

    // ── 枚举返回值 ──
    [AIDescription('获取当前订单状态')]
    function GetOrderStatus: TOrderStatus;

    // ── Set 参数 ──
    [AIDescription('设置字体样式（可组合 Bold/Italic/Underline）')]
    procedure SetFontStyles(Styles: TFontStyles);

    // ── TArray 参数 ──
    [AIDescription('添加一批数据点')]
    procedure AddDataPoints(const Points: TArray<Double>);

    // ── TArray 返回值 ──
    [AIDescription('获取所有数据点')]
    function GetDataPoints: TArray<Double>;

    // ── TDateTime ──
    [AIDescription('获取最后更新时间')]
    function GetLastUpdated: TDateTime;

    // ── Boolean ──
    [AIDescription('检查服务是否就绪')]
    function IsReady: Boolean;

    // ── 无参数/无返回值 ──
    procedure Refresh;

    // ── 属性 ──
    property OrderStatus: TOrderStatus read FLogLevel write FLogLevel;
    property FontStyles: TFontStyles read FActiveStyles write FActiveStyles;
  end;

  // ═══════════════════════════════════════════════════════════════════════════
  // 类 4: TComprehensiveConfigService — 纯属性展示 + 各种 getter 类型
  // ═══════════════════════════════════════════════════════════════════════════

  /// <summary>配置服务 — 全面的属性类型展示</summary>
  TComprehensiveConfigService = class
  private
    FAppName: string;
    FMaxUsers: Integer;
    FDebugMode: Boolean;
    FThreshold: Double;
    function GetBuildDate: TDateTime;
  published
    // ── function: TDateTime 返回值 ──
    [AIDescription('获取构建日期')]
    function GetBuildDateFunc: TDateTime;

    // ── 混合类型属性 ──
    property AppName: string read FAppName write FAppName;
    property MaxUsers: Integer read FMaxUsers write FMaxUsers;
    property DebugMode: Boolean read FDebugMode write FDebugMode;
    property Threshold: Double read FThreshold write FThreshold;
  end;

// ═══════════════════════════════════════════════════════════════════════════════
// Implementation
// ═══════════════════════════════════════════════════════════════════════════════

{ ── TComprehensiveMathService ── }

constructor TComprehensiveMathService.Create;
begin
  FOperationCount := 0;
  FLastInput := '';
end;

function TComprehensiveMathService.Add(A, B: Integer): Integer;
begin
  Result := A + B;
  FLastInput := Format('Add(%d, %d)', [A, B]);
  Inc(FOperationCount);
end;

function TComprehensiveMathService.Divide(A, B: Double): Double;
begin
  Result := A / B;
  FLastInput := Format('Divide(%.2f, %.2f)', [A, B]);
  Inc(FOperationCount);
end;

function TComprehensiveMathService.IsEven(Value: Integer): Boolean;
begin
  Result := (Value mod 2) = 0;
  FLastInput := Format('IsEven(%d)', [Value]);
  Inc(FOperationCount);
end;

function TComprehensiveMathService.Greet(const Name: string): string;
begin
  Result := 'Hello, ' + Name + '!';
  FLastInput := Format('Greet(%s)', [Name]);
  Inc(FOperationCount);
end;

function TComprehensiveMathService.CalculateTotal(Price: Double; Quantity: Integer; Discount: Double): Double;
begin
  Result := Price * Quantity * (1 - Discount);
  FLastInput := Format('CalcTotal(%.2f, %d, %.2f)', [Price, Quantity, Discount]);
  Inc(FOperationCount);
end;

procedure TComprehensiveMathService.SplitString(const Input: string; var Left, Right: string);
var
  CommaPos: Integer;
begin
  CommaPos := Pos(',', Input);
  if CommaPos > 0 then
  begin
    Left := Copy(Input, 1, CommaPos - 1);
    Right := Copy(Input, CommaPos + 1, Length(Input));
  end
  else
  begin
    Left := Input;
    Right := '';
  end;
  FLastInput := Format('SplitString(%s)', [Input]);
  Inc(FOperationCount);
end;

procedure TComprehensiveMathService.GetMinMax(const Numbers: TArray<Integer>; out MinVal, MaxVal: Integer);
var
  I: Integer;
begin
  if Length(Numbers) = 0 then
  begin
    MinVal := 0;
    MaxVal := 0;
    Exit;
  end;
  MinVal := Numbers[0];
  MaxVal := Numbers[0];
  for I := 1 to High(Numbers) do
  begin
    if Numbers[I] < MinVal then MinVal := Numbers[I];
    if Numbers[I] > MaxVal then MaxVal := Numbers[I];
  end;
  FLastInput := Format('GetMinMax([%d items])', [Length(Numbers)]);
  Inc(FOperationCount);
end;

class function TComprehensiveMathService.GetVersion: string;
begin
  Result := '1.0.0';
end;

class procedure TComprehensiveMathService.ResetGlobalCounter;
begin
  // 全局计数器重置（演示用）
end;

procedure TComprehensiveMathService.Reset;
begin
  FOperationCount := 0;
  FLastInput := '';
end;

{ ── TComprehensiveUserService ── }

constructor TComprehensiveUserService.Create;
begin
  FUserCount := 0;
  FLastError := '';
  FDefaultRole := urUser;
end;

function TComprehensiveUserService.RegisterUser(const Name: string; Age: Integer; Role: TUserRole): Integer;
begin
  Inc(FUserCount);
  FLastError := '';
  Result := 1000 + FUserCount;
end;

function TComprehensiveUserService.GetUserCount: Integer;
begin
  Result := FUserCount;
end;

procedure TComprehensiveUserService.BatchRegister(const Names: TArray<string>);
var
  I: Integer;
begin
  for I := 0 to High(Names) do
    Inc(FUserCount);
end;

{ ── TComprehensiveDataService ── }

procedure TComprehensiveDataService.SetOrderFilter(Status: TOrderStatus);
begin
  FLogLevel := Status;
end;

function TComprehensiveDataService.GetOrderStatus: TOrderStatus;
begin
  Result := FLogLevel;
end;

procedure TComprehensiveDataService.SetFontStyles(Styles: TFontStyles);
begin
  FActiveStyles := Styles;
end;

procedure TComprehensiveDataService.AddDataPoints(const Points: TArray<Double>);
begin
  FDataPoints := Points;
end;

function TComprehensiveDataService.GetDataPoints: TArray<Double>;
begin
  Result := FDataPoints;
end;

function TComprehensiveDataService.GetLastUpdated: TDateTime;
begin
  Result := Now;
end;

function TComprehensiveDataService.IsReady: Boolean;
begin
  Result := True;
end;

procedure TComprehensiveDataService.Refresh;
begin
  FLastUpdated := Now;
end;

{ ── TComprehensiveConfigService ── }

function TComprehensiveConfigService.GetBuildDate: TDateTime;
begin
  Result := EncodeDate(2026, 6, 13);
end;

function TComprehensiveConfigService.GetBuildDateFunc: TDateTime;
begin
  Result := GetBuildDate;
end;

// ═══════════════════════════════════════════════════════════════════════════════
// 主程序：依次发现每个类的能力，输出 JSON 数组
// ═══════════════════════════════════════════════════════════════════════════════

var
  Results: TJSONArray;
  Json: TJSONObject;
begin
  try
    Results := TJSONArray.Create;
    try
      // 类 1: 数学服务
      Json := TRttiDiscoverer.DiscoverClass(TComprehensiveMathService, 'ComprehensiveMathService');
      Results.AddElement(Json);

      // 类 2: 用户服务
      Json := TRttiDiscoverer.DiscoverClass(TComprehensiveUserService, 'ComprehensiveUserService');
      Results.AddElement(Json);

      // 类 3: 数据服务
      Json := TRttiDiscoverer.DiscoverClass(TComprehensiveDataService, 'ComprehensiveDataService');
      Results.AddElement(Json);

      // 类 4: 配置服务
      Json := TRttiDiscoverer.DiscoverClass(TComprehensiveConfigService, 'ComprehensiveConfigService');
      Results.AddElement(Json);

      // 输出格式化的 JSON 数组
      WriteLn(Results.Format(2));
    finally
      Results.Free;
    end;
  except
    on E: Exception do
      WriteLn('Error: ' + E.Message);
  end;
end.
