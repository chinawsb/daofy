unit ErrorCode;

/// <summary>
/// 本文件包含一个微妙的编译错误：泛型约束不匹配。
/// AI 需要搜索 KB 中 TDictionary 的类型定义才能理解问题根因。
/// </summary>

interface

uses
  System.Generics.Collections,
  System.Generics.Defaults;

type
  // 自定义记录类型，未实现 IEqualityComparer
  TCustomKey = record
    ID: Integer;
    Name: string;
  end;

  TDataCache = class
  public
    // 编译错误：TCustomKey 是 record 但没有提供 EqualityComparer
    FCache: TDictionary<TCustomKey, string>;

    constructor Create;
    procedure AddOrUpdate(const AKey: TCustomKey; const AValue: string);
    function TryGetValue(const AKey: TCustomKey; out AValue: string): Boolean;
  end;

implementation

{ TDataCache }

constructor TDataCache.Create;
begin
  inherited Create;
  FCache := TDictionary<TCustomKey, string>.Create;
end;

procedure TDataCache.AddOrUpdate(const AKey: TCustomKey; const AValue: string);
begin
  if FCache.ContainsKey(AKey) then
    FCache[AKey] := AValue
  else
    FCache.Add(AKey, AValue);
end;

function TDataCache.TryGetValue(const AKey: TCustomKey;
  out AValue: string): Boolean;
begin
  Result := FCache.TryGetValue(AKey, AValue);
end;

end.
