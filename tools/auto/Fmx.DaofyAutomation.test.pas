unit Fmx.DaofyAutomation.Test;

{===============================================================================
  Fmx.DaofyAutomation - FMX 框架自动化实现

  继承自 TAutomationProcessorBase，实现 FMX 特有操作：
    - 截图：Win32 GDI (GetWindowDC + BitBlt) → FMX.TBitmap → SaveToFile
    - 控件查找：TComponent.FindComponent
    - 模拟操作：RTTI 调用方法 / 设属性
    - 弹出菜单：FMX.TPopup

  使用者 uses 此单元即可，无需直接引用 DaofyAutomation.Base。
===============================================================================}
interface

uses
  DaofyAutomation.Base;

procedure AutoStart(const APipeName: string = '\\.\pipe\daofy_auto');
procedure AutoStop;
procedure AutoCapture(const AName: string);
procedure SetScreenshotDir(const ADir: string);

implementation

uses
  Winapi.Windows, Winapi.Messages,
  System.SysUtils, System.Classes, System.Rtti, System.TypInfo,
  System.Generics.Collections, System.JSON,
  FMX.Forms, FMX.Controls, FMX.Graphics, FMX.Surfaces, FMX.Types,
  FMX.Menus;

type
  /// <summary>
  ///  FMX 自动化处理器。通过命名管道接收 JSON 命令，操作 FMX 窗体/控件。
  /// </summary>
  TAutomationProcessor = class(TAutomationProcessorBase)
  private
    function CtrlToJSON(Ctrl: TFmxObject): TJSONObject;
  protected
    // ── 截图 ──
    function TakeShot(const AFile: string): string; override;

    // ── 窗体状态 ──
    function DoDump: string; override;

    // ── 弹出菜单 ──
    function DoDlgScan: string; override;
    function DoDlgClick(const Param: string): string; override;

    // ── 控件操作 ──
    function HandleCmdGoto(const Target: string): string; override;
    function HandleCmdClick(const Target: string): string; override;
    function HandleCmdDblClick(const Target: string): string; override;
    function HandleCmdRightClick(const Target: string): string; override;
    function HandleCmdHover(const Target: string): string; override;
    function HandleCmdType(const Target, Value: string): string; override;

    // ── RTTI ──
    function HandleRGet(const ReqId, Target, Prop: string): string; override;
    function HandleRSet(const ReqId, Target, Prop, Val: string): string; override;
    function HandleRInsp(const ReqId, Target: string): string; override;

    // ── 辅助 ──
    procedure DoTerminateApp; override;
    function FindNamedControl(const AName: string): TObject; override;
    function GetActiveForm: TObject; override;

  public
    constructor Create(const APipeName: string);
  end;

{ ═════════════════════════════════════════════════════════════════════════════
  全局接口
  ═════════════════════════════════════════════════════════════════════════════ }

procedure AutoStart(const APipeName: string);
begin
  if TAutomationProcessorBase.Current = nil then
    TAutomationProcessor.Create(APipeName);
  TAutomationProcessorBase.Current.SetSSDir('');
end;

procedure AutoStop;
begin
  if TAutomationProcessorBase.Current <> nil then
    TAutomationProcessorBase.Current.Terminate;
end;

procedure AutoCapture(const AName: string);
begin
  if TAutomationProcessorBase.Current <> nil then
    TAutomationProcessorBase.Current.DoCapPub(AName);
end;

procedure SetScreenshotDir(const ADir: string);
begin
  if TAutomationProcessorBase.Current <> nil then begin
    TAutomationProcessorBase.Current.SetSSDir(ADir);
    ForceDirectories(ADir);
  end;
end;

{ ═════════════════════════════════════════════════════════════════════════════
  TAutomationProcessor
  ═════════════════════════════════════════════════════════════════════════════ }

constructor TAutomationProcessor.Create(const APipeName: string);
begin
  inherited Create(APipeName);
  TAutomationProcessorBase.Current := Self;
end;

{ ── 截图 ──
  FMX 下截图流程：
  1. 选择目标窗口 HWND（对话框优先，其次 ActiveForm，最次 GetTopWindow）
  2. GDI BitBlt 捕获像素到 GDI HBITMAP
  3. GetDIBits 取出 32-bit BGRA 像素数据
  4. 转为 TBitmapSurface（RGBA）
  5. 创建 FMX.TBitmap → SaveToFile（自动按扩展名选编码器）}

function TAutomationProcessor.TakeShot(const AFile: string): string;
begin
  Result := 'TODO';
end;

{ ── 窗体状态 ── }

function TAutomationProcessor.CtrlToJSON(Ctrl: TFmxObject): TJSONObject;
begin
end;

function TAutomationProcessor.DoDump: string;
begin
  Result := 'TODO';
end;

{ ── 弹出菜单 ──
  FMX 中弹出菜单通过 TPopupMenu 组件实现，不直接挂在 Form 上。
  通过扫描 Form.Components 查找第一个 TPopupMenu。}

function FindPopupMenu(const F: TCommonCustomForm): TPopupMenu;
var I: Integer;
begin
  for I := 0 to F.ComponentCount - 1 do
    if F.Components[I] is TPopupMenu then
      Exit(TPopupMenu(F.Components[I]));
  Result := nil;
end;

function InvokeMenuItemClick(const MI: TMenuItem): Boolean;
var
  Ctx: TRttiContext;
  M: TRttiMethod;
begin
  Ctx := TRttiContext.Create;
  try
    M := Ctx.GetType(TMenuItem).GetMethod('Click');
    if (M <> nil) and (M.MethodKind = mkProcedure) then begin
      M.Invoke(MI, []);
      Exit(True);
    end;
  finally
    Ctx.Free;
  end;
  Result := False;
end;

function TAutomationProcessor.DoDlgScan: string;
begin
  Result := 'TODO';
end;

function TAutomationProcessor.DoDlgClick(const Param: string): string;
begin
  Result := 'TODO';
end;

{ ── 控件操作 ── }

function TAutomationProcessor.HandleCmdGoto(const Target: string): string;
begin
  Result := 'TODO';
end;

function TAutomationProcessor.HandleCmdClick(const Target: string): string;
begin
  Result := 'TODO';
end;

function TAutomationProcessor.HandleCmdDblClick(const Target: string): string;
begin
  Result := 'TODO';
end;

function TAutomationProcessor.HandleCmdRightClick(const Target: string): string;
begin
  Result := 'TODO';
end;

function TAutomationProcessor.HandleCmdHover(const Target: string): string;
begin
  Result := 'TODO';
end;

function TAutomationProcessor.HandleCmdType(const Target,
begin
end;

{ ── RTTI ── }

function TAutomationProcessor.HandleRGet(const ReqId, Target,
begin
end;

function TAutomationProcessor.HandleRSet(const ReqId, Target, Prop,
begin
end;

function TAutomationProcessor.HandleRInsp(const ReqId, Target: string): string;
begin
  Result := 'TODO';
end;

{ ── 辅助 ── }

procedure TAutomationProcessor.DoTerminateApp;
begin
end;

function TAutomationProcessor.FindNamedControl(const AName: string): TObject;
begin
  Result := 'TODO';
end;

function TAutomationProcessor.GetActiveForm: TObject;
begin
end;

end.

