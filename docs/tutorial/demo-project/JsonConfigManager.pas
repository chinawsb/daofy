unit JsonConfigManager;

/// <summary>
/// JSON 配置文件管理单元
/// 提供 JSON 配置文件的读写、获取/设置配置值的功能
/// </summary>

interface

uses
  System.SysUtils,
  System.JSON,
  System.IOUtils;

type
  /// <summary>JSON 配置管理器</summary>
  TJsonConfigManager = class
  private
    FFilePath: string;
    FRoot: TJSONObject;
    FModified: Boolean;
    function GetNestedObject(AJson: TJSONObject; const APath: string;
      ACreate: Boolean): TJSONObject;
  public
    constructor Create(const AFilePath: string);
    destructor Destroy; override;

    /// <summary>从文件加载配置</summary>
    procedure LoadConfig;
    /// <summary>保存配置到文件</summary>
    procedure SaveConfig;
    /// <summary>获取字符串值，不存在时返回默认值</summary>
    function GetValue(const APath: string; const ADefault: string): string; overload;
    /// <summary>获取整数值，不存在时返回默认值</summary>
    function GetValue(const APath: string; const ADefault: Integer): Integer; overload;
    /// <summary>获取布尔值，不存在时返回默认值</summary>
    function GetValue(const APath: string; const ADefault: Boolean): Boolean; overload;
    /// <summary>设置字符串值</summary>
    procedure SetValue(const APath: string; const AValue: string); overload;
    /// <summary>设置整数值</summary>
    procedure SetValue(const APath: string; const AValue: Integer); overload;
    /// <summary>设置布尔值</summary>
    procedure SetValue(const APath: string; const AValue: Boolean); overload;
  end;

implementation

const
  PATH_SEPARATOR = '.';

{ TJsonConfigManager }

constructor TJsonConfigManager.Create(const AFilePath: string);
begin
  inherited Create;
  FFilePath := AFilePath;
  FRoot := TJSONObject.Create;
  FModified := False;
  if TFile.Exists(AFilePath) then
    LoadConfig;
end;

destructor TJsonConfigManager.Destroy;
begin
  if FModified then
    SaveConfig;
  FRoot.Free;
  inherited;
end;

function TJsonConfigManager.GetNestedObject(AJson: TJSONObject;
  const APath: string; ACreate: Boolean): TJSONObject;
var
  LParts: TArray<string>;
  I: Integer;
  LChild: TJSONObject;
  LObj: TJSONObject;
begin
  LParts := APath.Split([PATH_SEPARATOR]);
  LObj := AJson;
  for I := 0 to Length(LParts) - 2 do
  begin
    if LObj.TryGetValue<TJSONObject>(LParts[I], LChild) then
      LObj := LChild
    else if ACreate then
    begin
      LChild := TJSONObject.Create;
      LObj.AddPair(LParts[I], LChild);
      LObj := LChild;
    end
    else
      Exit(nil);
  end;
  Result := LObj;
end;

procedure TJsonConfigManager.LoadConfig;
var
  LJsonStr: string;
  LParsed: TJSONValue;
begin
  LJsonStr := TFile.ReadAllText(FFilePath, TEncoding.UTF8);
  LParsed := TJSONObject.ParseJSONValue(LJsonStr);
  if LParsed is TJSONObject then
  begin
    FRoot.Free;
    FRoot := LParsed as TJSONObject;
  end
  else
    LParsed.Free;
end;

procedure TJsonConfigManager.SaveConfig;
var
  LJsonStr: string;
begin
  LJsonStr := FRoot.Format(2);
  TFile.WriteAllText(FFilePath, LJsonStr, TEncoding.UTF8);
  FModified := False;
end;

function TJsonConfigManager.GetValue(const APath: string;
  const ADefault: string): string;
var
  LObj: TJSONObject;
  LValue: string;
begin
  LObj := GetNestedObject(FRoot, APath, False);
  if (LObj <> nil) and LObj.TryGetValue<string>(ExtractFileName(APath), LValue) then
    Result := LValue
  else
    Result := ADefault;
end;

function TJsonConfigManager.GetValue(const APath: string;
  const ADefault: Integer): Integer;
var
  LObj: TJSONObject;
  LValue: Integer;
begin
  LObj := GetNestedObject(FRoot, APath, False);
  if (LObj <> nil) and LObj.TryGetValue<Integer>(ExtractFileName(APath), LValue) then
    Result := LValue
  else
    Result := ADefault;
end;

function TJsonConfigManager.GetValue(const APath: string;
  const ADefault: Boolean): Boolean;
var
  LObj: TJSONObject;
  LValue: Boolean;
begin
  LObj := GetNestedObject(FRoot, APath, False);
  if (LObj <> nil) and LObj.TryGetValue<Boolean>(ExtractFileName(APath), LValue) then
    Result := LValue
  else
    Result := ADefault;
end;

procedure TJsonConfigManager.SetValue(const APath: string;
  const AValue: string);
var
  LObj: TJSONObject;
  LKey: string;
begin
  LObj := GetNestedObject(FRoot, APath, True);
  LKey := ExtractFileName(APath);
  LObj.AddPair(LKey, AValue);
  FModified := True;
end;

procedure TJsonConfigManager.SetValue(const APath: string;
  const AValue: Integer);
var
  LObj: TJSONObject;
  LKey: string;
begin
  LObj := GetNestedObject(FRoot, APath, True);
  LKey := ExtractFileName(APath);
  LObj.AddPair(LKey, TJSONNumber.Create(AValue));
  FModified := True;
end;

procedure TJsonConfigManager.SetValue(const APath: string;
  const AValue: Boolean);
var
  LObj: TJSONObject;
  LKey: string;
begin
  LObj := GetNestedObject(FRoot, APath, True);
  LKey := ExtractFileName(APath);
  LObj.AddPair(LKey, TJSONBool.Create(AValue));
  FModified := True;
end;

end.
