unit ErrorCode;

/// <summary>
/// 修复后的版本：为 TCustomKey 实现了 IEqualityComparer<TCustomKey>，
/// 并在创建 TDictionary 时传入比较器实例。
/// </summary>

interface

uses
  System.Generics.Collections,
  System.Generics.Defaults;

type
  TCustomKey = record
    ID: Integer;
    Name: string;
  end;

  /// <summary>TCustomKey 的自定义相等比较器</summary>
  TCustomKeyComparer = class(TEqualityComparer<TCustomKey>)
  public
    function Equals(const Left, Right: TCustomKey): Boolean; override;
    function GetHashCode(const Value: TCustomKey): Integer; override;
  end;

  TDataCache = class
  private
    FCache: TDictionary<TCustomKey, string>;
    FComparer: TCustomKeyComparer;
  public
    constructor Create;
    destructor Destroy; override;
    procedure AddOrUpdate(const AKey: TCustomKey; const AValue: string);
    function TryGetValue(const AKey: TCustomKey; out AValue: string): Boolean;
  end;

implementation

{ TCustomKeyComparer }

function TCustomKeyComparer.Equals(const Left, Right: TCustomKey): Boolean;
begin
  Result := (Left.ID = Right.ID) and (Left.Name = Right.Name);
end;

function TCustomKeyComparer.GetHashCode(const Value: TCustomKey): Integer;
begin
  Result := Value.ID;
end;

{ TDataCache }

constructor TDataCache.Create;
begin
  inherited Create;
  FComparer := TCustomKeyComparer.Create;
  FCache := TDictionary<TCustomKey, string>.Create(FComparer);
end;

destructor TDataCache.Destroy;
begin
  FCache.Free;
  FComparer.Free;
  inherited;
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
