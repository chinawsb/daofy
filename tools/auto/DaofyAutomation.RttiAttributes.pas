unit DaofyAutomation.RttiAttributes;

{===============================================================================
  DaofyAutomation.RttiAttributes - AI Agent 注解属性

  定义 AI Agent 可识别的自定义属性（Custom Attributes），用于标记 Delphi
  类的方法和参数，使 RTTI 发现器（RttiDiscovery）能将功能描述、参数含义、
  调用示例等信息暴露给 AI Agent。

  用法（在业务类中）：
    uses DaofyAutomation.RttiAttributes;

    type
      TMyService = class
      public
        [AIDescription('创建客户订单，返回新订单号')]
        [AIResultDescription('新创建的订单编号，失败返回 -1')]
        [AIExample('CreateOrder("张三", 100) → 10001')]
        function CreateOrder(
          [AIParamDescription('客户姓名')] const customerName: string;
          [AIParamDescription('订单金额(元)')] amount: Integer
        ): Integer;
      end;

  框架无关：仅依赖 System.Rtti，可在 VCL/FMX/控制台应用中使用。
===============================================================================}

interface

uses
  System.Rtti;

type
  /// <summary>
  ///  方法/函数功能描述。用一句话说明该方法的作用。
  /// </summary>
  AIDescriptionAttribute = class(TCustomAttribute)
  private
    FText: string;
  public
    constructor Create(const AText: string);
    /// <summary>功能描述文本</summary>
    property Text: string read FText;
  end;

  /// <summary>
  ///  参数含义描述。直接挂在参数声明上，无需按名称匹配。
  /// </summary>
  AIParamDescriptionAttribute = class(TCustomAttribute)
  private
    FText: string;
  public
    constructor Create(const AText: string);
    /// <summary>参数说明文本</summary>
    property Text: string read FText;
  end;

  /// <summary>
  ///  返回值说明。描述函数返回值代表的含义。
  /// </summary>
  AIResultDescriptionAttribute = class(TCustomAttribute)
  private
    FText: string;
  public
    constructor Create(const AText: string);
    /// <summary>返回值说明文本</summary>
    property Text: string read FText;
  end;

  /// <summary>
  ///  调用示例。展示该方法的使用方式及预期输出。
  /// </summary>
  AIExampleAttribute = class(TCustomAttribute)
  private
    FText: string;
  public
    constructor Create(const AText: string);
    /// <summary>示例内容</summary>
    property Text: string read FText;
  end;

implementation

{ ═════════════════════════════════════════════════════════════════════════════
  AIDescriptionAttribute
  ═════════════════════════════════════════════════════════════════════════════ }

constructor AIDescriptionAttribute.Create(const AText: string);
begin
  inherited Create;
  FText := AText;
end;

{ ═════════════════════════════════════════════════════════════════════════════
  AIParamDescriptionAttribute
  ═════════════════════════════════════════════════════════════════════════════ }

constructor AIParamDescriptionAttribute.Create(const AText: string);
begin
  inherited Create;
  FText := AText;
end;

{ ═════════════════════════════════════════════════════════════════════════════
  AIResultDescriptionAttribute
  ═════════════════════════════════════════════════════════════════════════════ }

constructor AIResultDescriptionAttribute.Create(const AText: string);
begin
  inherited Create;
  FText := AText;
end;

{ ═════════════════════════════════════════════════════════════════════════════
  AIExampleAttribute
  ═════════════════════════════════════════════════════════════════════════════ }

constructor AIExampleAttribute.Create(const AText: string);
begin
  inherited Create;
  FText := AText;
end;

end.
