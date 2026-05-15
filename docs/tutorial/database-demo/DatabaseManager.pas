unit DatabaseManager;

/// <summary>
/// SQLite 数据库管理单元
/// 使用 FireDAC 组件连接 SQLite 数据库，提供 CRUD 操作
/// AI 通过搜索 KB 中 TFDConnection、TFDQuery、TFDParams 的 API 签名后生成
/// </summary>

interface

uses
  System.SysUtils,
  System.Classes,
  FireDAC.Stan.Intf,
  FireDAC.Stan.Option,
  FireDAC.Stan.Error,
  FireDAC.UI.Intf,
  FireDAC.Phys.Intf,
  FireDAC.Stan.Def,
  FireDAC.Stan.Pool,
  FireDAC.Stan.Async,
  FireDAC.Phys,
  FireDAC.Phys.SQLite,
  FireDAC.Phys.SQLiteDef,
  FireDAC.Comp.Client,
  FireDAC.Comp.DataSet,
  FireDAC.DApt;

type
  /// <summary>数据库连接配置</summary>
  TDatabaseConfig = record
    DatabasePath: string;
    PoolSize: Integer;
    Timeout: Integer;
  end;

  /// <summary>SQLite 数据库管理器</summary>
  TDatabaseManager = class
  private
    FConnection: TFDConnection;
    FDriverLink: TFDPhysSQLiteDriverLink;
    FConfig: TDatabaseConfig;
  public
    constructor Create(const AConfig: TDatabaseConfig);
    destructor Destroy; override;

    /// <summary>打开数据库连接</summary>
    procedure Connect;
    /// <summary>关闭数据库连接</summary>
    procedure Disconnect;
    /// <summary>执行 SQL 语句（INSERT/UPDATE/DELETE）</summary>
    function Execute(const ASQL: string; const AParams: TArray<TVarRec>): Integer;
    /// <summary>执行查询并返回数据集</summary>
    function Query(const ASQL: string): TFDQuery;
    /// <summary>测试连接是否正常</summary>
    function TestConnection: Boolean;
  end;

implementation

const
  DEFAULT_POOL_SIZE = 10;
  DEFAULT_TIMEOUT = 30;

{ TDatabaseManager }

constructor TDatabaseManager.Create(const AConfig: TDatabaseConfig);
begin
  inherited Create;
  FConfig := AConfig;
  if FConfig.PoolSize <= 0 then
    FConfig.PoolSize := DEFAULT_POOL_SIZE;
  if FConfig.Timeout <= 0 then
    FConfig.Timeout := DEFAULT_TIMEOUT;

  FDriverLink := TFDPhysSQLiteDriverLink.Create(nil);
  FConnection := TFDConnection.Create(nil);
end;

destructor TDatabaseManager.Destroy;
begin
  Disconnect;
  FConnection.Free;
  FDriverLink.Free;
  inherited;
end;

procedure TDatabaseManager.Connect;
begin
  if FConnection.Connected then
    Exit;
  FConnection.DriverName := 'SQLite';
  FConnection.Params.Clear;
  FConnection.Params.AddPair('Database', FConfig.DatabasePath);
  FConnection.Params.AddPair('PoolSize', FConfig.PoolSize.ToString);
  FConnection.LoginPrompt := False;
  FConnection.Open;
end;

procedure TDatabaseManager.Disconnect;
begin
  if FConnection.Connected then
    FConnection.Close;
end;

function TDatabaseManager.Execute(const ASQL: string;
  const AParams: TArray<TVarRec>): Integer;
var
  LQuery: TFDQuery;
  I: Integer;
begin
  Connect;
  LQuery := TFDQuery.Create(nil);
  try
    LQuery.Connection := FConnection;
    LQuery.SQL.Text := ASQL;
    for I := 0 to Length(AParams) - 1 do
      LQuery.Params[I].Value := AParams[I].VPointer;
    LQuery.ExecSQL;
    Result := LQuery.RowsAffected;
  finally
    LQuery.Free;
  end;
end;

function TDatabaseManager.Query(const ASQL: string): TFDQuery;
begin
  Connect;
  Result := TFDQuery.Create(nil);
  Result.Connection := FConnection;
  Result.SQL.Text := ASQL;
  Result.Open;
end;

function TDatabaseManager.TestConnection: Boolean;
var
  LQuery: TFDQuery;
begin
  try
    Connect;
    LQuery := TFDQuery.Create(nil);
    try
      LQuery.Connection := FConnection;
      LQuery.SQL.Text := 'SELECT 1';
      LQuery.Open;
      Result := LQuery.Fields[0].AsInteger = 1;
    finally
      LQuery.Free;
    end;
  except
    Result := False;
  end;
end;

end.
