unit IniConfigManager;

/// <summary>
/// INI 配置文件管理单元
/// 提供 INI 配置文件的读写功能，支持字符串、整数、布尔值的读取
/// </summary>

interface

uses
  System.SysUtils,
  System.IniFiles,
  System.IOUtils;

type
  /// <summary>INI 配置管理器</summary>
  TIniConfigManager = class
  private
  public
    /// <summary>读取字符串值</summary>
    function ReadString(const AFileName, ASection, AKey,
      ADefault: string): string;
    /// <summary>读取整数值</summary>
    function ReadInteger(const AFileName, ASection, AKey: string;
      ADefault: Integer): Integer;
    /// <summary>读取布尔值</summary>
    function ReadBool(const AFileName, ASection, AKey: string;
      ADefault: Boolean): Boolean;
    /// <summary>写入字符串值</summary>
    procedure WriteString(const AFileName, ASection, AKey,
      AValue: string);
    /// <summary>写入整数值</summary>
    procedure WriteInteger(const AFileName, ASection, AKey: string;
      AValue: Integer);
    /// <summary>写入布尔值</summary>
    procedure WriteBool(const AFileName, ASection, AKey: string;
      AValue: Boolean);
  end;

implementation

{ TIniConfigManager }

function TIniConfigManager.ReadString(const AFileName, ASection, AKey,
  ADefault: string): string;
var
  LIni: TIniFile;
begin
  LIni := TIniFile.Create(AFileName);
  try
    Result := LIni.ReadString(ASection, AKey, ADefault);
  finally
    LIni.Free;
  end;
end;

function TIniConfigManager.ReadInteger(const AFileName, ASection,
  AKey: string; ADefault: Integer): Integer;
var
  LIni: TIniFile;
begin
  LIni := TIniFile.Create(AFileName);
  try
    Result := LIni.ReadInteger(ASection, AKey, ADefault);
  finally
    LIni.Free;
  end;
end;

function TIniConfigManager.ReadBool(const AFileName, ASection, AKey: string;
  ADefault: Boolean): Boolean;
var
  LIni: TIniFile;
begin
  LIni := TIniFile.Create(AFileName);
  try
    Result := LIni.ReadBool(ASection, AKey, ADefault);
  finally
    LIni.Free;
  end;
end;

procedure TIniConfigManager.WriteString(const AFileName, ASection, AKey,
  AValue: string);
var
  LIni: TIniFile;
begin
  LIni := TIniFile.Create(AFileName);
  try
    LIni.WriteString(ASection, AKey, AValue);
  finally
    LIni.Free;
  end;
end;

procedure TIniConfigManager.WriteInteger(const AFileName, ASection,
  AKey: string; AValue: Integer);
var
  LIni: TIniFile;
begin
  LIni := TIniFile.Create(AFileName);
  try
    LIni.WriteInteger(ASection, AKey, AValue);
  finally
    LIni.Free;
  end;
end;

procedure TIniConfigManager.WriteBool(const AFileName, ASection, AKey: string;
  AValue: Boolean);
var
  LIni: TIniFile;
begin
  LIni := TIniFile.Create(AFileName);
  try
    LIni.WriteBool(ASection, AKey, AValue);
  finally
    LIni.Free;
  end;
end;

end.
