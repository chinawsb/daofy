unit Vcl.DaofyAutomation;

{===============================================================================
  Vcl.DaofyAutomation - VCL 框架自动化实现

  继承自 TAutomationProcessorBase，实现 VCL 特有操作：
    - 截图：Vcl.Graphics.TBitmap + Vcl.Imaging.Jpeg.TJPEGImage
    - 控件查找：TWinControl.FindChildControl
    - 鼠标模拟：SendMessage(HWND, BM_CLICK / WM_LBUTTONDOWN, ...)
    - 弹出菜单：Vcl.Menus.TPopupMenu / TMenuItem
    - 窗体枚举：Vcl.Forms.Screen

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
  System.Actions, System.Generics.Collections, System.JSON, System.Math, System.Types,
  Vcl.Forms, Vcl.Controls, Vcl.Graphics, Vcl.Imaging.Jpeg, Vcl.Menus;

type
  /// <summary>
  ///  VCL 自动化处理器。通过命名管道接收 JSON 命令，操作 VCL 窗体/控件。
  /// </summary>
  TAutomationProcessor = class(TAutomationProcessorBase)
  protected
    // ── 截图 ──

    function TakeShot(const AFile: string): string; override;

    // ── 窗体状态 ──

    function DoDump: string; override;

    // ── 弹出菜单 ──

    function DoDlgScan: string; override;
    function DoDlgClick(const Param: string): string; override;

    // ── 控件操作 ──

    function HandleCmdGoto(const ReqId, Target: string): string; override;
    function HandleCmdClick(const ReqId, Target: string): string; override;
    function HandleCmdDblClick(const ReqId, Target: string): string; override;
    function HandleCmdRightClick(const ReqId, Target: string): string; override;
    function HandleCmdHover(const ReqId, Target: string): string; override;
    function HandleCmdMove(const ReqId, Target: string; const X, Y: Integer): string; override;
    function HandleCmdDrag(const ReqId, Source, Target: string; const X, Y: Integer): string; override;
    function HandleCmdType(const ReqId, Target, Value: string): string; override;
    function HandleCmdKey(const ReqId, Target, Key: string): string; override;

    // ── RTTI ──

    function HandleRGet(const ReqId, Target, Prop: string): string; override;
    function HandleRSet(const ReqId, Target, Prop, Val: string): string; override;
    function HandleRCall(const ReqId, Target, Method, ParamsJSON: string): string; override;
    function HandleRInsp(const ReqId, Target: string): string; override;
    function HandleCmdListWnd(const ReqId: string): string; override;

    // ── 辅助 ──

    procedure DoTerminateApp; override;
    function FindNamedControl(const AName: string): TObject; override;
    function GetActiveForm: TObject; override;
    function GetRttiClasses: TArray<TClass>; override;

  public
    constructor Create(const APipeName: string);
  end;

{ ═════════════════════════════════════════════════════════════════════════════
  全局接口
  ═════════════════════════════════════════════════════════════════════════════ }

procedure AutoStart(const APipeName: string);
begin
  if TAutomationProcessorBase.Current = nil then begin
    TAutomationProcessor.Create(APipeName);
    TAutomationProcessorBase.Current.Start;
  end;
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

{ ── 截图 ── }

function TAutomationProcessor.TakeShot(const AFile: string): string;
var
  hWin: HWND;
  DC, MemDC: HDC;
  Bmp: TBitmap;
  Jpg: TJPEGImage;
  Old: HGDIOBJ;
  R: TRect;
begin
  Result := 'NO_WIN';

  // ① 优先截 MessageBox（#32770 类）
  hWin := FindWindowW('#32770', nil);
  // ② 否则取活动窗体
  if hWin = 0 then
    if Screen.ActiveForm <> nil then
      hWin := Screen.ActiveForm.Handle
    else
      hWin := GetTopWindow(0);

  if hWin = 0 then Exit;

  GetWindowRect(hWin, R);
  if (R.Width <= 0) or (R.Height <= 0) then begin
    Result := 'ZERO';
    Exit;
  end;

  DC := GetWindowDC(hWin);
  if DC = 0 then begin
    Result := 'NODC';
    Exit;
  end;

  try
    MemDC := CreateCompatibleDC(DC);
    if MemDC = 0 then begin
      Result := 'NOMC';
      Exit;
    end;
    try
      Bmp := TBitmap.Create;
      try
        Bmp.PixelFormat := pf24bit;
        Bmp.Width  := R.Width;
        Bmp.Height := R.Height;
        Old := SelectObject(MemDC, Bmp.Handle);
        BitBlt(MemDC, 0, 0, R.Width, R.Height, DC, 0, 0, SRCCOPY);
        SelectObject(MemDC, Old);

        Jpg := TJPEGImage.Create;
        try
          Jpg.Assign(Bmp);
          Jpg.CompressionQuality := JPG_Q;
          Jpg.Compress;
          ForceDirectories(ExtractFilePath(AFile));
          Jpg.SaveToFile(AFile);
          Result := 'OK';
        finally
          Jpg.Free;
        end;
      finally
        Bmp.Free;
      end;
    finally
      DeleteDC(MemDC);
    end;
  finally
    ReleaseDC(hWin, DC);
  end;
end;

{ ── 窗体状态 ── }

function TAutomationProcessor.DoDump: string;

  function DTree(Ctrl: TControl): TJSONObject;
  var
    Ctx: TRttiContext;
    Prop: TRttiProperty;
    Seen: TDictionary<string, Boolean>;
    I: Integer;
    W: TWinControl;
    Props: TJSONObject;
    Children: TJSONArray;
  begin
    Result := TJSONObject.Create;
    Result.AddPair('name', Ctrl.Name);
    Result.AddPair('class', Ctrl.ClassName);

    Props := TJSONObject.Create;
    Seen := TDictionary<string, Boolean>.Create;
    try
      Ctx := TRttiContext.Create;
      try
        for Prop in Ctx.GetType(Ctrl.ClassType).GetProperties do
          if not IsSkippedProp(Prop.Name) and IsSimpleKind(Prop.PropertyType.TypeKind)
            and not Seen.ContainsKey(Prop.Name) then
          begin
            Seen.Add(Prop.Name, True);
            Props.AddPair(Prop.Name, PropToJSON(Prop, Ctrl));
          end;
      finally
        Ctx.Free;
      end;
    finally
      Seen.Free;
    end;
    Result.AddPair('props', Props);

    if Ctrl is TWinControl then begin
      W := TWinControl(Ctrl);
      if W.ControlCount > 0 then begin
        Children := TJSONArray.Create;
        for I := 0 to W.ControlCount - 1 do
          Children.AddElement(DTree(W.Controls[I]));
        Result.AddPair('children', Children);
      end;
    end;
  end;

var
  I: Integer;
  F: TForm;
  Ctx: TRttiContext;
  Prop: TRttiProperty;
  Seen: TDictionary<string, Boolean>;
  Root: TJSONObject;
  Props: TJSONObject;
  Controls: TJSONArray;
begin
  F := Screen.ActiveForm;
  if F = nil then begin
    if Screen.FormCount > 0 then
      F := Screen.Forms[0]
    else
      Exit;
  end;

  Root := TJSONObject.Create;
  Seen := TDictionary<string, Boolean>.Create;
  try
    Root.AddPair('form', F.Name);
    Root.AddPair('class', F.ClassName);
    Root.AddPair('caption', F.Caption);

    Props := TJSONObject.Create;
    Ctx := TRttiContext.Create;
    try
      for Prop in Ctx.GetType(F.ClassType).GetProperties do
        if not IsSkippedProp(Prop.Name) and IsSimpleKind(Prop.PropertyType.TypeKind)
          and (Prop.Name <> 'Caption') and not Seen.ContainsKey(Prop.Name) then
        begin
          Seen.Add(Prop.Name, True);
          Props.AddPair(Prop.Name, PropToJSON(Prop, F));
        end;
    finally
      Ctx.Free;
    end;
    Root.AddPair('props', Props);

    Controls := TJSONArray.Create;
    for I := 0 to F.ControlCount - 1 do
      Controls.AddElement(DTree(F.Controls[I]));
    Root.AddPair('controls', Controls);

    Result := Root.ToJSON;
  finally
    Seen.Free;
    Root.Free;
  end;
end;

{ ── 弹出菜单 ── }

function TAutomationProcessor.DoDlgScan: string;
var
  F: TForm;
  PM: TPopupMenu;
  Root: TJSONObject;
  Items: TJSONArray;
  II: Integer;
  It: TMenuItem;
begin
  F := Screen.ActiveForm;
  if F = nil then Exit('NOF');
  PM := F.PopupMenu;
  if PM = nil then Exit('NOP');

  Root := TJSONObject.Create;
  try
    Root.AddPair('type', 'popup');
    Root.AddPair('menu', PM.Name);

    Items := TJSONArray.Create;
    for II := 0 to PM.Items.Count - 1 do begin
      It := PM.Items[II];
      var ItemObj := TJSONObject.Create;
      ItemObj.AddPair('name', It.Name);
      ItemObj.AddPair('caption', It.Caption);
      ItemObj.AddPair('enabled', TJSONBool.Create(It.Enabled));
      ItemObj.AddPair('visible', TJSONBool.Create(It.Visible));
      ItemObj.AddPair('checked', TJSONBool.Create(It.Checked));
      Items.AddElement(ItemObj);
    end;
    Root.AddPair('items', Items);

    Result := Root.ToJSON;
  finally
    Root.Free;
  end;
end;

function FindClick(Menu: TMenuItem; const Cap: string): string;
var I: Integer;
begin
  for I := 0 to Menu.Count - 1 do begin
    if SameText(Menu[I].Caption, Cap) then begin
      Menu[I].Click;
      Exit('OK');
    end;
    if Menu[I].Count > 0 then
      if FindClick(Menu[I], Cap) = 'OK' then Exit('OK');
  end;
  Result := 'NF';
end;

function TAutomationProcessor.DoDlgClick(const Param: string): string;
var F: TForm; PM: TPopupMenu;
begin
  F := Screen.ActiveForm;
  if F = nil then Exit('NOF');
  PM := F.PopupMenu;
  if PM = nil then Exit('NOP');
  Result := FindClick(PM.Items, Param);
end;

{ ── 控件操作 ── }

function TAutomationProcessor.HandleCmdGoto(const ReqId, Target: string): string;
var
  I: Integer;
  Found: Boolean;
begin
  Found := False;
  for I := 0 to Screen.FormCount - 1 do
    if SameText(Screen.Forms[I].ClassName, Target) or
       SameText(Screen.Forms[I].Name, Target) then
    begin
      Screen.Forms[I].Show;
      Screen.Forms[I].BringToFront;
      Screen.Forms[I].SetFocus;
      Found := True;
      Break;
    end;
  if Found then
    Result := WriteResp(ReqId, 'ok', 'OK')
  else
    Result := WriteResp(ReqId, 'err', 'NF:' + Target);
end;

function SendKeyInput(const VK: UInt16; const Unicode: Boolean): Boolean;
var
  Inputs: array[0..1] of TInput;
begin
  ZeroMemory(@Inputs, SizeOf(Inputs));
  Inputs[0].Itype := INPUT_KEYBOARD;
  Inputs[1].Itype := INPUT_KEYBOARD;
  Inputs[1].ki.dwFlags := KEYEVENTF_KEYUP;
  if Unicode then begin
    Inputs[0].ki.wScan := VK;
    Inputs[0].ki.dwFlags := KEYEVENTF_UNICODE;
    Inputs[1].ki.wScan := VK;
    Inputs[1].ki.dwFlags := KEYEVENTF_UNICODE or KEYEVENTF_KEYUP;
  end else begin
    Inputs[0].ki.wVk := VK;
    Inputs[1].ki.wVk := VK;
  end;
  Result := SendInput(2, Inputs[0], SizeOf(TInput)) = 2;
end;

function SendMouseClick(const AScreenX, AScreenY: Integer): Boolean;
var
  Inputs: array[0..2] of TInput;
  SW, SH: Integer;
begin
  SW := GetSystemMetrics(SM_CXSCREEN);
  SH := GetSystemMetrics(SM_CYSCREEN);
  ZeroMemory(@Inputs, SizeOf(Inputs));
  // Move
  Inputs[0].Itype := INPUT_MOUSE;
  Inputs[0].mi.dx := (AScreenX * 65535) div Max(SW - 1, 1);
  Inputs[0].mi.dy := (AScreenY * 65535) div Max(SH - 1, 1);
  Inputs[0].mi.dwFlags := MOUSEEVENTF_ABSOLUTE or MOUSEEVENTF_MOVE;
  // Down
  Inputs[1].Itype := INPUT_MOUSE;
  Inputs[1].mi.dwFlags := MOUSEEVENTF_LEFTDOWN;
  // Up
  Inputs[2].Itype := INPUT_MOUSE;
  Inputs[2].mi.dwFlags := MOUSEEVENTF_LEFTUP;
  Result := SendInput(3, Inputs[0], SizeOf(TInput)) = 3;
end;

function TAutomationProcessor.HandleCmdClick(const ReqId, Target: string): string;
var
  AtPos, CommaPos: Integer;
  CoordStr, CtrlName: string;
  CX, CY: Integer;
  Obj: TObject;
  Ctrl: TControl;
  Pt: TPoint;
begin
  try
    AtPos := Pos('@', Target);
    CtrlName := Target;
    CX := -1;
    CY := -1;

    if AtPos > 0 then begin
      CoordStr := Copy(Target, AtPos + 1, MaxInt);
      CtrlName := Copy(Target, 1, AtPos - 1);
      CommaPos := Pos(',', CoordStr);
      if CommaPos <= 0 then
        Exit(WriteResp(ReqId, 'err', 'bad_coords'));
      CX := StrToIntDef(Trim(Copy(CoordStr, 1, CommaPos - 1)), 0);
      CY := StrToIntDef(Trim(Copy(CoordStr, CommaPos + 1, MaxInt)), 0);
    end;

    if CtrlName = '' then
      Exit(WriteResp(ReqId, 'err', 'no target'));
    if Screen.ActiveForm = nil then
      Exit(WriteResp(ReqId, 'err', 'no active form'));

    Obj := FindNamedControl(CtrlName);
    if Obj = nil then
      Exit(WriteResp(ReqId, 'err', 'NF:' + CtrlName));
    if not (Obj is TControl) then
      Exit(WriteResp(ReqId, 'err', 'not_control:' + CtrlName));

    Ctrl := TControl(Obj);
    if not Ctrl.Visible then
      Exit(WriteResp(ReqId, 'err', 'invisible:' + CtrlName));
    if not Ctrl.Enabled then
      Exit(WriteResp(ReqId, 'err', 'disabled:' + CtrlName));

    if AtPos > 0 then
      Pt := Ctrl.ClientToScreen(Point(CX, CY))
    else
      Pt := Ctrl.ClientToScreen(Point(Ctrl.Width div 2, Ctrl.Height div 2));

    if not SendMouseClick(Pt.X, Pt.Y) then
      Exit(WriteResp(ReqId, 'err', 'SendInput_failed'));
  except
    on E: Exception do
      Exit(WriteResp(ReqId, 'err', E.Message));
  end;
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

{ ── key ── }

function TAutomationProcessor.HandleCmdKey(const ReqId, Target, Key: string): string;
const
  VK_MAP: array[0..11] of record Name: string; VK: Integer; end = (
    (Name: 'TAB'; VK: VK_TAB), (Name: 'ENTER'; VK: VK_RETURN),
    (Name: 'ESC'; VK: VK_ESCAPE), (Name: 'BACK'; VK: VK_BACK),
    (Name: 'DEL'; VK: VK_DELETE), (Name: 'HOME'; VK: VK_HOME),
    (Name: 'END'; VK: VK_END), (Name: 'UP'; VK: VK_UP),
    (Name: 'DOWN'; VK: VK_DOWN), (Name: 'LEFT'; VK: VK_LEFT),
    (Name: 'RIGHT'; VK: VK_RIGHT), (Name: 'SPACE'; VK: VK_SPACE));
var
  I: Integer;
  VK: Integer;
  WC: TWinControl;
begin
  // Focus target control if specified
  if (Target <> '') and (Screen.ActiveForm <> nil) then begin
    WC := TWinControl(FindNamedControl(Target));
    if (WC <> nil) and WC.Visible and WC.Enabled then
      Winapi.Windows.SetFocus(WC.Handle);
  end;

  // 查命名键
  VK := 0;
  for I := 0 to High(VK_MAP) do
    if SameText(Key, VK_MAP[I].Name) then begin VK := VK_MAP[I].VK; Break; end;

  // F1-F12
  if (VK = 0) and (Length(Key) > 1) and
     (UpCase(Key[1]) = 'F') then begin
    var FN := StrToIntDef(Copy(Key, 2, MaxInt), 0);
    if (FN >= 1) and (FN <= 12) then VK := VK_F1 + FN - 1;
  end;

  // Send via SendInput
  if VK = 0 then begin
    if Length(Key) = 1 then begin
      // Single character: use KEYEVENTF_UNICODE
      SendKeyInput(Ord(Key[1]), True);
    end;
  end else
    SendKeyInput(VK, False);

  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdDblClick(const ReqId, Target: string): string;
var
  AtPos, CommaPos: Integer;
  CoordStr, CtrlName: string;
  CX, CY: Integer;
  WC: TWinControl;
  Ch: HWND;
  R: TRect;
begin
  AtPos := Pos('@', Target);
  CtrlName := Target;
  if AtPos > 0 then begin
    CoordStr := Copy(Target, AtPos + 1, MaxInt);
    CtrlName := Copy(Target, 1, AtPos - 1);
    CommaPos := Pos(',', CoordStr);
    if CommaPos > 0 then begin
      CX := StrToIntDef(Trim(Copy(CoordStr, 1, CommaPos - 1)), 0);
      CY := StrToIntDef(Trim(Copy(CoordStr, CommaPos + 1, MaxInt)), 0);
      if Screen.ActiveForm <> nil then begin
        WC := TWinControl(FindNamedControl(CtrlName));
        if WC <> nil then begin
          Ch := WC.Handle;
          SendMessage(Ch, WM_LBUTTONDBLCLK, MK_LBUTTON, MakeLParam(CX, CY));
        end;
      end;
    end;
  end else begin
    if Screen.ActiveForm <> nil then begin
      WC := TWinControl(FindNamedControl(CtrlName));
      if WC <> nil then begin
        Ch := WC.Handle;
        GetWindowRect(Ch, R);
        SendMessage(Ch, WM_LBUTTONDBLCLK, MK_LBUTTON,
          MakeLParam(R.Width div 2, R.Height div 2));
      end;
    end;
  end;
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdRightClick(const ReqId, Target: string): string;
var
  WC: TWinControl;
  Ch: HWND;
  R: TRect;
begin
  if Screen.ActiveForm <> nil then begin
    WC := TWinControl(FindNamedControl(Target));
    if WC <> nil then begin
      Ch := WC.Handle;
      GetWindowRect(Ch, R);
      if Screen.ActiveForm.PopupMenu <> nil then
        Screen.ActiveForm.PopupMenu.Popup(
          R.Left + (R.Width div 2), R.Top + (R.Height div 2));
    end;
  end;
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdHover(const ReqId, Target: string): string;
var
  WC: TWinControl;
  Ch: HWND;
  R: TRect;
begin
  if Screen.ActiveForm <> nil then begin
    WC := TWinControl(FindNamedControl(Target));
    if WC <> nil then begin
      Ch := WC.Handle;
      SendMessage(Ch, WM_MOUSEMOVE, 0, MakeLParam(WC.Width div 2, WC.Height div 2));
      GetWindowRect(Ch, R);
      SetCursorPos(R.Left + WC.Width div 2, R.Top + WC.Height div 2);
      WC.Perform(CM_MOUSEENTER, 0, 0);
    end;
  end;
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdMove(const ReqId, Target: string; const X,
  Y: Integer): string;
var
  WC: TWinControl;
  R: TRect;
  CX, CY: Integer;
begin
  if Target <> '' then begin
    if Screen.ActiveForm <> nil then begin
      WC := TWinControl(FindNamedControl(Target));
      if WC <> nil then begin
        GetWindowRect(WC.Handle, R);
        CX := R.Left + (R.Width div 2);
        CY := R.Top + (R.Height div 2);
      end else
        Exit(WriteResp(ReqId, 'ok', 'OK'));
    end else
      Exit(WriteResp(ReqId, 'ok', 'OK'));
  end else if (X >= 0) and (Y >= 0) then begin
    CX := X;
    CY := Y;
  end else
    Exit(WriteResp(ReqId, 'ok', 'OK'));

  SetCursorPos(CX, CY);
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

{ ── drag ── }

function TAutomationProcessor.HandleCmdDrag(const ReqId, Source, Target: string;
  const X, Y: Integer): string;
var
  SrcCtrl: TWinControl;
  SrcCh: Winapi.Windows.HWND;
  SR, TR: TRect;
  SX, SY, TX, TY: Integer;
  I: Integer;
begin
  if (Screen.ActiveForm = nil) or (Source = '') then
    Exit(WriteResp(ReqId, 'ok', 'OK'));

  SrcCtrl := TWinControl(FindNamedControl(Source));
  if SrcCtrl = nil then Exit(WriteResp(ReqId, 'ok', 'OK'));
  SrcCh := SrcCtrl.Handle;

  // 起点 = 源控件中心
  GetWindowRect(SrcCh, SR);
  SX := SR.Left + SR.Width div 2;
  SY := SR.Top + SR.Height div 2;

  // 终点
  if Target <> '' then begin
    var DstCtrl := TWinControl(FindNamedControl(Target));
    if DstCtrl <> nil then begin
      GetWindowRect(DstCtrl.Handle, TR);
      TX := TR.Left + TR.Width div 2;
      TY := TR.Top + TR.Height div 2;
    end else Exit(WriteResp(ReqId, 'ok', 'OK'));
  end else if (X >= 0) and (Y >= 0) then begin
    TX := X; TY := Y;
  end else Exit(WriteResp(ReqId, 'ok', 'OK'));

  // 模拟拖拽
  SetCursorPos(SX, SY);
  SendMessage(SrcCh, WM_LBUTTONDOWN, MK_LBUTTON, MakeLParam(0, 0));

  // 渐进移动（平滑拖拽），发送 WM_MOUSEMOVE 消息
  for I := 1 to 10 do begin
    var MX := SX + (TX - SX) * I div 10;
    var MY := SY + (TY - SY) * I div 10;
    SetCursorPos(MX, MY);
    SendMessage(SrcCh, WM_MOUSEMOVE, MK_LBUTTON, MakeLParam(MX, MY));
    Sleep(10);
  end;

  SetCursorPos(TX, TY);
  SendMessage(SrcCh, WM_LBUTTONUP, 0, MakeLParam(TX, TY));
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdType(const ReqId, Target, Value: string): string;
var
  WC: TWinControl;
  Ch: HWND;
  C: Char;
begin
  if (Target <> '') and (Screen.ActiveForm <> nil) then begin
    WC := TWinControl(FindNamedControl(Target));
    if WC <> nil then begin
      Ch := WC.Handle;
      SetFocus(Ch);
      SendMessage(Ch, WM_SETTEXT, 0, LPARAM(PChar('')));
      for C in Value do
        SendMessage(Ch, WM_CHAR, Ord(C), 0);
      SendMessage(GetParent(Ch), WM_COMMAND, MakeWParam(GetDlgCtrlID(Ch), EN_CHANGE), LPARAM(Ch));
    end;
  end;
  Result := WriteResp(ReqId, 'ok', 'OK');
end;
function TAutomationProcessor.HandleRGet(const ReqId, Target,
  Prop: string): string;
var
  Ctrl: TControl;
  Ctx: TRttiContext;
  Pr: TRttiProperty;
  IP: TRttiIndexedProperty;
  V: TValue;
  Obj: TObject;
  Parts: TArray<string>;
  i: Integer;
  PropName: string;
  Idx: Integer;
begin
  try
    if Screen.ActiveForm = nil then Exit(WriteResp(ReqId, 'err', 'no active form'));
    Ctrl := TControl(FindNamedControl(Target));
    if Ctrl = nil then Exit(WriteResp(ReqId, 'err', 'NF:' + Target));

    Parts := Prop.Split(['.']);
    if Length(Parts) = 0 then Exit(WriteResp(ReqId, 'err', 'no property'));

    Ctx := TRttiContext.Create;
    try
      // 第一段：支持 ContrlName[Index] 索引
      ParseIndexedProp(Parts[0], PropName, Idx);
      if Idx >= 0 then begin
        IP := Ctx.GetType(Ctrl.ClassType).GetIndexedProperty(PropName);
        if IP = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + PropName));
        V := IP.GetValue(Ctrl, [TValue.From<Integer>(Idx)]);
      end else begin
        Pr := Ctx.GetType(Ctrl.ClassType).GetProperty(PropName);
        if Pr = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + PropName));
        if not Pr.IsReadable then Exit(WriteResp(ReqId, 'err', 'NR:' + PropName));
        V := Pr.GetValue(Ctrl);
      end;

      for i := 1 to High(Parts) do begin
        if V.Kind <> tkClass then Exit(WriteResp(ReqId, 'err', 'not an object: ' + Parts[i]));
        Obj := V.AsObject;
        if Obj = nil then Exit(WriteResp(ReqId, 'err', 'nil: ' + Parts[i]));

        ParseIndexedProp(Parts[i], PropName, Idx);
        if Idx >= 0 then begin
          IP := Ctx.GetType(Obj.ClassType).GetIndexedProperty(PropName);
          if IP = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + PropName));
          V := IP.GetValue(Obj, [TValue.From<Integer>(Idx)]);
        end else begin
          Pr := Ctx.GetType(Obj.ClassType).GetProperty(PropName);
          if Pr = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + PropName));
          if not Pr.IsReadable then Exit(WriteResp(ReqId, 'err', 'NR:' + PropName));
          V := Pr.GetValue(Obj);
        end;
      end;

      Result := WriteResp(ReqId, 'ok', V.ToString);
    finally
      Ctx.Free;
    end;
  except
    on E: Exception do Result := WriteResp(ReqId, 'err', E.Message);
  end;
end;

function TAutomationProcessor.HandleRSet(const ReqId, Target, Prop,
  Val: string): string;
var
  Ctrl: TControl;
  Ctx: TRttiContext;
  Pr: TRttiProperty;
begin
  try
    if Screen.ActiveForm = nil then Exit(WriteResp(ReqId, 'err', 'no active form'));
    Ctrl := TControl(FindNamedControl(Target));
    if Ctrl = nil then Exit(WriteResp(ReqId, 'err', 'NF:' + Target));

    Ctx := TRttiContext.Create;
    try
      Pr := Ctx.GetType(Ctrl.ClassType).GetProperty(Prop);
      if Pr = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + Prop));
      if not Pr.IsWritable then Exit(WriteResp(ReqId, 'err', 'NW:' + Prop));

      case Pr.PropertyType.TypeKind of
        tkString, tkUString, tkWString, tkLString:
          Pr.SetValue(Ctrl, Val);
        tkInteger, tkInt64:
          Pr.SetValue(Ctrl, StrToIntDef(Val, 0));
        tkFloat:
          Pr.SetValue(Ctrl, StrToFloatDef(Val, 0));
        tkEnumeration:
          if SameText(Pr.PropertyType.Name, 'Boolean') then
            Pr.SetValue(Ctrl, SameText(Val, 'true'))
          else
            Pr.SetValue(Ctrl, TValue.FromOrdinal(Pr.PropertyType.Handle,
              GetEnumValue(Pr.PropertyType.Handle, Val)));
      else
        Exit(WriteResp(ReqId, 'err', 'unsupported type'));
      end;

      Result := WriteResp(ReqId, 'ok', 'OK');
    finally
      Ctx.Free;
    end;
  except
    on E: Exception do Result := WriteResp(ReqId, 'err', E.Message);
  end;
end;

function TAutomationProcessor.HandleRInsp(const ReqId, Target: string): string;
var
  Ctrl: TControl;
  Ctx: TRttiContext;
  Ty: TRttiType;
  M: TRttiMethod;
  PR: TRttiProperty;
  Root: TJSONObject;
  Methods: TJSONArray;
  Props: TJSONArray;
begin
  try
    if Screen.ActiveForm = nil then
      Exit(WriteResp(ReqId, 'err', 'no active form'));

    Ctrl := TControl(FindNamedControl(Target));
    if Ctrl = nil then
      Exit(WriteResp(ReqId, 'err', 'NF:' + Target));

    Root := TJSONObject.Create;
    try
      Ctx := TRttiContext.Create;
      Ty := Ctx.GetType(Ctrl.ClassType);
      try
        Root.AddPair('name', Ctrl.Name);
        Root.AddPair('class', Ctrl.ClassName);

        Methods := TJSONArray.Create;
        for M in Ty.GetMethods do
          if (M.Visibility = mvPublic) and (M.MethodKind = mkProcedure)
            and (Length(M.GetParameters) = 0) then
            Methods.AddElement(TJSONString.Create(M.Name));
        Root.AddPair('methods', Methods);

        Props := TJSONArray.Create;
        for PR in Ty.GetProperties do
          if PR.IsReadable and PR.IsWritable then begin
            var PObj := TJSONObject.Create;
            PObj.AddPair('name', PR.Name);
            PObj.AddPair('type', PR.PropertyType.Name);
            Props.AddElement(PObj);
          end;
        Root.AddPair('props', Props);

        Result := WriteResp(ReqId, 'ok', Root.ToJSON);
      finally
        Ctx.Free;
      end;
    finally
      Root.Free;
    end;
  except
    on E: Exception do
      Result := WriteResp(ReqId, 'err', E.Message);
  end;
end;

{ ── RTTI 调用方法 ── }

function TAutomationProcessor.HandleRCall(const ReqId, Target,
  Method, ParamsJSON: string): string;
var
  Ctrl: TObject;
  Ctx: TRttiContext;
  M: TRttiMethod;
  Parts: TArray<string>;
  Obj: TObject;
  i, p: Integer;
  Pr: TRttiProperty;
  IP: TRttiIndexedProperty;
  V: TValue;
  PropName: string;
  Idx: Integer;
  ParamValues: TArray<TValue>;
  ParamArr: TJSONArray;
  ParamValue: TJSONValue;
  ParamText: string;
  ParamType: TRttiType;
begin
  try
    if Screen.ActiveForm = nil then
      Exit(WriteResp(ReqId, 'err', 'no active form'));
    Ctrl := FindNamedControl(Target);
    if Ctrl = nil then
      Exit(WriteResp(ReqId, 'err', 'NF:' + Target));

    Parts := Method.Split(['.']);
    if Length(Parts) = 0 then
      Exit(WriteResp(ReqId, 'err', 'no method'));

    Ctx := TRttiContext.Create;
    try
      // 遍历属性链（除最后一段外都是属性名）
      Obj := Ctrl;
      for i := 0 to Length(Parts) - 2 do begin
        ParseIndexedProp(Parts[i], PropName, Idx);
        if Idx >= 0 then begin
          IP := Ctx.GetType(Obj.ClassType).GetIndexedProperty(PropName);
          if IP = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + PropName));
          V := IP.GetValue(Obj, [TValue.From<Integer>(Idx)]);
        end else begin
          Pr := Ctx.GetType(Obj.ClassType).GetProperty(PropName);
          if Pr = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + PropName));
          V := Pr.GetValue(Obj);
        end;
        Obj := V.AsObject;
        if Obj = nil then Exit(WriteResp(ReqId, 'err', 'nil:' + PropName));
      end;

      // 最后一段是方法名
      M := Ctx.GetType(Obj.ClassType).GetMethod(Parts[High(Parts)]);
      if M = nil then begin
        if (Length(Parts) = 1) and SameText(Parts[0], 'Execute') and (Obj is TBasicAction) then begin
          TBasicAction(Obj).Execute;
          Exit(WriteResp(ReqId, 'ok', 'OK'));
        end;
        Exit(WriteResp(ReqId, 'err', 'NM:' + Parts[High(Parts)]));
      end;

      // 解析参数
      if Trim(ParamsJSON) <> '' then begin
        ParamText := Trim(ParamsJSON);
        if (Length(ParamText) >= 2) and (ParamText[1] = '"') then begin
          ParamValue := TJSONObject.ParseJSONValue(ParamText);
          try
            if ParamValue is TJSONString then
              ParamText := TJSONString(ParamValue).Value;
          finally
            ParamValue.Free;
          end;
        end;

        ParamValue := TJSONObject.ParseJSONValue(ParamText);
        try
          if not (ParamValue is TJSONArray) then
            Exit(WriteResp(ReqId, 'err', 'invalid params'));
          ParamArr := ParamValue as TJSONArray;
          SetLength(ParamValues, ParamArr.Count);
          for p := 0 to ParamArr.Count - 1 do begin
            if p < Length(M.GetParameters) then begin
              ParamType := M.GetParameters[p].ParamType;
              case ParamType.TypeKind of
                tkInteger, tkInt64:
                  ParamValues[p] := TValue.From(StrToIntDef(ParamArr.Items[p].Value, 0));
                tkFloat:
                  ParamValues[p] := TValue.From(StrToFloatDef(ParamArr.Items[p].Value, 0.0));
                tkEnumeration:
                  if SameText(ParamType.Name, 'Boolean') then
                    ParamValues[p] := TValue.From(SameText(ParamArr.Items[p].Value, 'true'))
                  else
                    ParamValues[p] := TValue.From<string>(ParamArr.Items[p].Value);
              else
                ParamValues[p] := TValue.From<string>(ParamArr.Items[p].Value);
              end;
            end;
          end;
        finally
          ParamValue.Free;
        end;
      end;

      M.Invoke(Obj, ParamValues);
      Result := WriteResp(ReqId, 'ok', 'OK');
    finally
      Ctx.Free;
    end;
  except
    on E: Exception do
      Result := WriteResp(ReqId, 'err', E.Message);
  end;
end;

{ ── listwnd ── }

function TAutomationProcessor.HandleCmdListWnd(const ReqId: string): string;
var
  Root: TJSONObject;
  Items: TJSONArray;
  I: Integer;
  F: TForm;
  Item: TJSONObject;
begin
  Root := TJSONObject.Create;
  try
    Items := TJSONArray.Create;
    for I := 0 to Screen.FormCount - 1 do begin
      F := Screen.Forms[I];
      Item := TJSONObject.Create;
      Item.AddPair('name', F.Name);
      Item.AddPair('class', F.ClassName);
      Item.AddPair('caption', F.Caption);
      if F = Screen.ActiveForm then
        Item.AddPair('active', 'true')
      else
        Item.AddPair('active', 'false');
      Items.AddElement(Item);
    end;
    Root.AddPair('windows', Items);
    Result := WriteResp(ReqId, 'ok', Root.ToJSON);
  finally
    Root.Free;
  end;
end;

{ ── 辅助 ── }

procedure TAutomationProcessor.DoTerminateApp;
begin
  Terminate;
  Application.Terminate;
  PostQuitMessage(0);
end;

function TAutomationProcessor.FindNamedControl(const AName: string): TObject;

  function FindRecursive(Parent: TWinControl): TObject;
  var
    I: Integer;
    C: TControl;
  begin
    for I := 0 to Parent.ControlCount - 1 do begin
      C := Parent.Controls[I];
      if SameText(C.Name, AName) then Exit(C);
      if C is TWinControl then begin
        Result := FindRecursive(TWinControl(C));
        if Result <> nil then Exit;
      end;
    end;
    Result := nil;
  end;

var
  Component: TComponent;
begin
  Result := nil;
  if Screen.ActiveForm = nil then
    Exit;
  if SameText(Screen.ActiveForm.Name, AName) then
    Exit(Screen.ActiveForm);
  Component := Screen.ActiveForm.FindComponent(AName);
  if Component <> nil then
    Exit(Component);
  Result := FindRecursive(Screen.ActiveForm);
end;

function TAutomationProcessor.GetActiveForm: TObject;
begin
  Result := Screen.ActiveForm;
end;

function TAutomationProcessor.GetRttiClasses: TArray<TClass>;
var
  I: Integer;
begin
  SetLength(Result, Screen.FormCount);
  for I := 0 to Screen.FormCount - 1 do
    Result[I] := Screen.Forms[I].ClassType;
end;

end.
