unit Fmx.DaofyAutomation;

{===============================================================================
  Fmx.DaofyAutomation - FMX 框架自动化实现

  继承自 TAutomationProcessorBase，实现 FMX 特有操作：
    - 截图：Win32 GDI (GetWindowDC + BitBlt) -> FMX.TBitmap -> SaveToFile
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
  System.SysUtils, System.Classes, System.Rtti, System.TypInfo, System.Types,
  System.Generics.Collections, System.JSON,
  Vcl.Graphics,
  FMX.Forms, FMX.Controls, FMX.Types, FMX.Graphics,
  FMX.Menus, FMX.Platform.Win,
  FMX.Forms3D;

type
  /// <summary>
  ///  FMX 自动化处理器。通过命名管道接收 JSON 命令，操作 FMX 窗体/控件。
  /// </summary>
  TAutomationProcessor = class(TAutomationProcessorBase)
  private
    function CtrlToJSON(Ctrl: TFmxObject): TJSONObject;
  protected
    // --- 截图 ---
    function TakeShot(const AFile: string): string; override;

    // --- 窗体状态 ---
    function DoDump: string; override;

    // --- 弹出菜单 ---
    function DoDlgScan: string; override;
    function DoDlgClick(const Param: string): string; override;

    // --- 控件操作 ---
    function HandleCmdGoto(const ReqId, Target: string): string; override;
    function HandleCmdClick(const ReqId, Target: string): string; override;
    function HandleCmdDblClick(const ReqId, Target: string): string; override;
    function HandleCmdRightClick(const ReqId, Target: string): string; override;
    function HandleCmdHover(const ReqId, Target: string): string; override;
    function HandleCmdMove(const ReqId, Target: string; const X, Y: Integer): string; override;
    function HandleCmdDrag(const ReqId, Source, Target: string; const X, Y: Integer): string; override;
    function HandleCmdType(const ReqId, Target, Value: string): string; override;
    function HandleCmdKey(const ReqId, Target, Key: string): string; override;

    // --- RTTI ---
    function HandleRGet(const ReqId, Target, Prop: string): string; override;
    function HandleRSet(const ReqId, Target, Prop, Val: string): string; override;
    function HandleRCall(const ReqId, Target, Method, ParamsJSON: string): string; override;
    function HandleRInsp(const ReqId, Target: string): string; override;
    function HandleCmdListWnd(const ReqId: string): string; override;

    // --- 辅助 ---
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

{ --- 截图 ---
  FMX 下截图流程：
  1. 选择目标窗口 HWND(对话框优先，其次 ActiveForm，最次 GetTopWindow)
  2. GDI BitBlt 捕获像素到 GDI HBITMAP
  3. GetDIBits 取出 32-bit BGRA 像素数据
  4. 转为 TBitmapSurface(RGBA)
  5. 创建 FMX.TBitmap -> SaveToFile(自动按扩展名选编码器)}

// 捕获 Win32 窗口到 JPEG 文件
function CaptureWin32WndToJPEG(hWnd: HWND; const AFile: string): string;
var
  R: TRect;
  DC, MemDC: HDC;
  BmpHandle: HBITMAP;
  Old: HGDIOBJ;
  BI: TBitmapInfo;
  Bits: Pointer;
  RowSize, Y: Integer;
  Src, Dst: PByte;
  RowBuf: Pointer;
  X: Integer;
  FMXBmp: FMX.Graphics.TBitmap;
begin
  Result := 'FAIL';
  GetWindowRect(hWnd, R);
  if (R.Width <= 0) or (R.Height <= 0) then Exit;

  DC := GetDC(0);
  if DC = 0 then Exit;
  try
    MemDC := CreateCompatibleDC(DC);
    if MemDC = 0 then Exit;
    try
      BmpHandle := CreateCompatibleBitmap(DC, R.Width, R.Height);
      if BmpHandle = 0 then Exit;
      try
        // 从屏幕 DC 直接 BitBlt（抓的是屏幕实际像素，方向一定正确）
        Old := SelectObject(MemDC, BmpHandle);
        BitBlt(MemDC, 0, 0, R.Width, R.Height, DC, R.Left, R.Top, SRCCOPY);
        SelectObject(MemDC, Old);

        // 读取像素到内存
        ZeroMemory(@BI, SizeOf(BI));
        BI.bmiHeader.biSize := SizeOf(BI.bmiHeader);
        BI.bmiHeader.biWidth := R.Width;
        BI.bmiHeader.biHeight := -R.Height; // top-down
        BI.bmiHeader.biPlanes := 1;
        BI.bmiHeader.biBitCount := 32;
        BI.bmiHeader.biCompression := BI_RGB;

        Bits := AllocMem(R.Width * R.Height * 4);
        try
          if GetDIBits(DC, BmpHandle, 0, R.Height, Bits, BI, DIB_RGB_COLORS) = 0 then
            Exit;

          // 写入 BMP 到内存流 → FMX TBitmap → JPEG（无临时文件）
          RowSize := ((R.Width * 24 + 31) div 32) * 4;
          RowBuf := AllocMem(RowSize);
          try
            var MS := TMemoryStream.Create;
            try
              // BMP 文件头
              var BFH: array[0..13] of Byte;
              FillChar(BFH, 14, 0);
              BFH[0] := $42; BFH[1] := $4D;
              PInteger(@BFH[2])^ := 14 + 40 + RowSize * R.Height;
              BFH[10] := 14 + 40;
              MS.Write(BFH, 14);
              // BMP 信息头
              var BIH: array[0..39] of Byte;
              FillChar(BIH, 40, 0);
              PInteger(@BIH[0])^ := 40;
              PInteger(@BIH[4])^ := R.Width;
              PInteger(@BIH[8])^ := R.Height;
              PWord(@BIH[12])^ := 1;
              PWord(@BIH[14])^ := 24;
              MS.Write(BIH, 40);
              // top-down 数据 → bottom-up BMP，行序反转
              for Y := R.Height - 1 downto 0 do begin
                Src := PByte(Bits) + Y * R.Width * 4;
                Dst := RowBuf;
                for X := 0 to R.Width - 1 do begin
                  Dst^ := Src^; Inc(Dst); Inc(Src);
                  Dst^ := Src^; Inc(Dst); Inc(Src);
                  Dst^ := Src^; Inc(Dst); Inc(Src);
                  Inc(Src);
                end;
                if RowSize > R.Width * 3 then
                  FillChar(Dst^, RowSize - R.Width * 3, 0);
                MS.Write(RowBuf^, RowSize);
              end;
              // 内存流 → FMX TBitmap → JPEG
              MS.Position := 0;
              FMXBmp := FMX.Graphics.TBitmap.Create;
              try
                FMXBmp.LoadFromStream(MS);
                ForceDirectories(ExtractFilePath(AFile));
                FMXBmp.SaveToFile(AFile);
                Result := 'OK';
              finally
                FMXBmp.Free;
              end;
            finally
              MS.Free;
            end;
          finally
            FreeMem(RowBuf);
          end;
        finally
          FreeMem(Bits);
        end;
      finally
        DeleteObject(BmpHandle);
      end;
    finally
      DeleteDC(MemDC);
    end;
  finally
    ReleaseDC(0, DC);
  end;
end;

function TAutomationProcessor.TakeShot(const AFile: string): string;
var
  Bmp: FMX.Graphics.TBitmap;
  F: TCommonCustomForm;
begin
  Result := 'NO_WIN';

  // Win32 对话框检测（#32770 类 = MessageBox/OpenDialog 等标准对话框）
  var hDlg := FindWindowW('#32770', nil);
  if hDlg <> 0 then begin
    Result := CaptureWin32WndToJPEG(hDlg, AFile);
    if Result = 'OK' then Exit;
    // 对话框截图失败，回落 PaintTo
  end;

  // FMX 模态对话框（MessageDlg 等）扫描
  for var I := 0 to Screen.FormCount - 1 do
    if TFmxFormState.Modal in TCommonCustomForm(Screen.Forms[I]).FormState then
    begin
      F := Screen.Forms[I] as TCommonCustomForm;
      Bmp := FMX.Graphics.TBitmap.Create(
        Trunc(F.ClientWidth), Trunc(F.ClientHeight));
      try
        if Bmp.Canvas.BeginScene then
        begin
          TCustomForm(F).PaintTo(Bmp.Canvas);
          Bmp.Canvas.EndScene;
        end;
        ForceDirectories(ExtractFilePath(AFile));
        Bmp.SaveToFile(AFile);
        Result := 'OK';
      finally
        Bmp.Free;
      end;
      Exit;
    end;

  // FMX 3D 窗体通过 Context.CopyToBitmap 截取（GPU readback）
  if Screen.ActiveForm is TCustomForm3D then
  begin
    var Form3D := TCustomForm3D(Screen.ActiveForm);
    Bmp := FMX.Graphics.TBitmap.Create(
      Round(Form3D.Width), Round(Form3D.Height));
    try
      Form3D.Context.CopyToBitmap(Bmp,
        TRect.Create(0, 0, Round(Form3D.Width), Round(Form3D.Height)));
      ForceDirectories(ExtractFilePath(AFile));
      Bmp.SaveToFile(AFile);
      Result := 'OK';
    finally
      Bmp.Free;
    end;
    Exit;
  end;

  // FMX 2D 窗体用 PaintTo 渲染到位图
  if Screen.ActiveForm <> nil then
    F := Screen.ActiveForm
  else if Screen.FormCount > 0 then
    F := Screen.Forms[0] as TCommonCustomForm
  else
    Exit;
    
  Bmp := FMX.Graphics.TBitmap.Create(
    Trunc(F.ClientWidth), Trunc(F.ClientHeight));
  try
    if Bmp.Canvas.BeginScene then
    begin
      TCustomForm(F).PaintTo(Bmp.Canvas);
      Bmp.Canvas.EndScene;
    end;
    ForceDirectories(ExtractFilePath(AFile));
    Bmp.SaveToFile(AFile);
    Result := 'OK';
  finally
    Bmp.Free;
  end;
end;

{ --- 窗体状态 --- }

function TAutomationProcessor.CtrlToJSON(Ctrl: TFmxObject): TJSONObject;
var
  Ctx: TRttiContext;
  Prop: TRttiProperty;
  Seen: TDictionary<string, Boolean>;
  I: Integer;
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

  if Ctrl.ChildrenCount > 0 then begin
    Children := TJSONArray.Create;
    for I := 0 to Ctrl.ChildrenCount - 1 do
      Children.AddElement(CtrlToJSON(Ctrl.Children[I]));
    Result.AddPair('children', Children);
  end;
end;

function TAutomationProcessor.DoDump: string;
var
  F: TCommonCustomForm;
  Ctx: TRttiContext;
  Prop: TRttiProperty;
  Seen: TDictionary<string, Boolean>;
  Root: TJSONObject;
  Props: TJSONObject;
  Controls: TJSONArray;
  I: Integer;
begin
  F := Screen.ActiveForm;
  if F = nil then begin
    if Screen.FormCount > 0 then
      F := Screen.Forms[0] as TCommonCustomForm
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
    for I := 0 to F.ChildrenCount - 1 do
      Controls.AddElement(CtrlToJSON(F.Children[I]));
    Root.AddPair('controls', Controls);

    Result := Root.ToJSON;
  finally
    Seen.Free;
    Root.Free;
  end;
end;

{ --- 弹出菜单 ---
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
var
  F: TCommonCustomForm;
  PM: TPopupMenu;
  Root: TJSONObject;
  Items: TJSONArray;
  II: Integer;
  It: TMenuItem;
begin
  F := Screen.ActiveForm;
  if F = nil then Exit('NOF');
  PM := FindPopupMenu(F);
  if PM = nil then Exit('NOP');

  Root := TJSONObject.Create;
  try
    Root.AddPair('type', 'popup');
    Root.AddPair('menu', PM.Name);

    Items := TJSONArray.Create;
    for II := 0 to PM.ItemsCount - 1 do begin
      It := PM.Items[II];
      var ItemObj := TJSONObject.Create;
      ItemObj.AddPair('name', It.Name);
      ItemObj.AddPair('text', It.Text);          // FMX: Text 而非 Caption
      ItemObj.AddPair('enabled', TJSONBool.Create(It.Enabled));
      ItemObj.AddPair('visible', TJSONBool.Create(It.Visible));
      ItemObj.AddPair('checked', TJSONBool.Create(It.IsChecked));
      Items.AddElement(ItemObj);
    end;
    Root.AddPair('items', Items);

    WriteJSON(Root);
    Result := 'OK';
  finally
    Root.Free;
  end;
end;

function TAutomationProcessor.DoDlgClick(const Param: string): string;
var
  F: TCommonCustomForm;
  PM: TPopupMenu;
  I: Integer;
begin
  F := Screen.ActiveForm;
  if F = nil then Exit('NOF');
  PM := FindPopupMenu(F);
  if PM = nil then Exit('NOP');
  for I := 0 to PM.ItemsCount - 1 do
    if SameText(PM.Items[I].Text, Param) then begin
      InvokeMenuItemClick(PM.Items[I]);
      Exit('OK');
    end;
  Result := 'NF';
end;

{ --- 控件操作 --- }

function TAutomationProcessor.HandleCmdGoto(const ReqId, Target: string): string;
var I: Integer; F: TCommonCustomForm;
begin
  for I := 0 to Screen.FormCount - 1 do begin
    F := Screen.Forms[I] as TCommonCustomForm;
    if SameText(F.ClassName, Target) or SameText(F.Name, Target) then begin
      F.Show;
      F.BringToFront;
      Break;
    end;
  end;
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdClick(const ReqId, Target: string): string;

  procedure DoClickAt(Ctrl: TComponent; X, Y: Integer);
  var
    CtrlCtl: TControl;
    Pt: TPointF;
  begin
    if Ctrl is TControl then begin
      CtrlCtl := TControl(Ctrl);
      Pt := CtrlCtl.LocalToAbsolute(TPointF.Create(X, Y));
      SetCursorPos(Round(Pt.X), Round(Pt.Y));
      var H := FormToHWND(Screen.ActiveForm as TCommonCustomForm);
      if H <> 0 then begin
        SendMessage(H, WM_LBUTTONDOWN, MK_LBUTTON,
          MakeLParam(Round(Pt.X), Round(Pt.Y)));
        SendMessage(H, WM_LBUTTONUP, 0,
          MakeLParam(Round(Pt.X), Round(Pt.Y)));
      end;
    end;
  end;

var
  Ctrl: TComponent;
  Ctx: TRttiContext;
  M: TRttiMethod;
  Evt: TRttiProperty;
  AtPos, CommaPos: Integer;
  CX, CY: Integer;
  CtrlName: string;
begin
  if Screen.ActiveForm = nil then Exit(WriteResp(ReqId, 'ok', 'OK'));

  // 解析 @x,y 坐标点击
  AtPos := Pos('@', Target);
  if AtPos > 0 then begin
    CtrlName := Copy(Target, 1, AtPos - 1);
    var CoordStr := Copy(Target, AtPos + 1, MaxInt);
    CommaPos := Pos(',', CoordStr);
    if CommaPos > 0 then begin
      CX := StrToIntDef(Trim(Copy(CoordStr, 1, CommaPos - 1)), 0);
      CY := StrToIntDef(Trim(Copy(CoordStr, CommaPos + 1, MaxInt)), 0);
      if CtrlName <> '' then begin
        Ctrl := Screen.ActiveForm.FindComponent(CtrlName);
        if Ctrl <> nil then DoClickAt(Ctrl, CX, CY);
      end else begin
        // 没有控件名，相对活动窗体坐标
        var FH := FormToHWND(Screen.ActiveForm as TCommonCustomForm);
        if FH <> 0 then begin
          SetCursorPos(CX, CY);
          SendMessage(FH, WM_LBUTTONDOWN, MK_LBUTTON, MakeLParam(CX, CY));
          SendMessage(FH, WM_LBUTTONUP, 0, MakeLParam(CX, CY));
        end;
      end;
    end;
    Exit(WriteResp(ReqId, 'ok', 'OK'));
  end;

  // 常规 RTTI 点击
  Ctrl := Screen.ActiveForm.FindComponent(Target);
  if Ctrl = nil then Exit(WriteResp(ReqId, 'ok', 'OK'));

  Ctx := TRttiContext.Create;
  try
    M := Ctx.GetType(Ctrl.ClassType).GetMethod('Click');
    if (M <> nil) and (M.MethodKind = mkProcedure) and
       (Length(M.GetParameters) = 0) then
      M.Invoke(Ctrl, [])
    else begin
      Evt := Ctx.GetType(Ctrl.ClassType).GetProperty('OnClick');
      if (Evt <> nil) and Evt.IsReadable then begin
        var V := Evt.GetValue(Ctrl);
        var PData: ^TMethod := V.GetReferenceToRawData;
        TNotifyEvent(PData^)(Ctrl);
      end;
    end;
  finally
    Ctx.Free;
  end;

  Result := WriteResp(ReqId, 'ok', 'OK');
end;

{ --- key --- }

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
  I, VK: Integer;
  Ctrl: TComponent;
  Ctx: TRttiContext;
  M: TRttiMethod;
begin
  // 焦点移到目标控件
  if (Target <> '') and (Screen.ActiveForm <> nil) then begin
    Ctrl := Screen.ActiveForm.FindComponent(Target);
    if (Ctrl <> nil) then begin
      Ctx := TRttiContext.Create;
      try
        M := Ctx.GetType(Ctrl.ClassType).GetMethod('SetFocus');
        if M <> nil then M.Invoke(Ctrl, []);
      finally
        Ctx.Free;
      end;
    end;
  end;

  // 查命名键
  VK := 0;
  for I := 0 to High(VK_MAP) do
    if SameText(Key, VK_MAP[I].Name) then begin VK := VK_MAP[I].VK; Break; end;

  // F1-F12
  if (VK = 0) and (Length(Key) > 1) and (UpCase(Key[1]) = 'F') then begin
    var FN := StrToIntDef(Copy(Key, 2, MaxInt), 0);
    if (FN >= 1) and (FN <= 12) then VK := VK_F1 + FN - 1;
  end;

  // 通过 Windows API 发送按键
  if VK <> 0 then begin
    keybd_event(VK, 0, 0, 0);
    keybd_event(VK, 0, KEYEVENTF_KEYUP, 0);
  end else if Length(Key) = 1 then begin
    keybd_event(Ord(UpCase(Key[1])), 0, 0, 0);
    keybd_event(Ord(UpCase(Key[1])), 0, KEYEVENTF_KEYUP, 0);
  end;

  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdDblClick(const ReqId, Target: string): string;
var
  Ctrl: TComponent;
  Ctx: TRttiContext;
  M: TRttiMethod;
begin
  if Screen.ActiveForm = nil then Exit(WriteResp(ReqId, 'ok', 'OK'));
  Ctrl := Screen.ActiveForm.FindComponent(Target);
  if Ctrl = nil then Exit(WriteResp(ReqId, 'ok', 'OK'));

  Ctx := TRttiContext.Create;
  try
    M := Ctx.GetType(Ctrl.ClassType).GetMethod('DblClick');
    if (M <> nil) and (M.MethodKind = mkProcedure) and
       (Length(M.GetParameters) = 0) then
      M.Invoke(Ctrl, []);
  finally
    Ctx.Free;
  end;
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdRightClick(const ReqId, Target: string): string;
var
  Ctrl: TComponent;
  F: TCommonCustomForm;
  PM: TPopupMenu;
  CtrlCtl: TControl;
  I: Integer;
begin
  if Screen.ActiveForm = nil then Exit(WriteResp(ReqId, 'ok', 'OK'));
  F := Screen.ActiveForm;
  Ctrl := F.FindComponent(Target);

  // 扫描组件列表找第一个 TPopupMenu
  PM := nil;
  for I := 0 to F.ComponentCount - 1 do
    if F.Components[I] is TPopupMenu then begin
      PM := TPopupMenu(F.Components[I]);
      Break;
    end;

  if (Ctrl <> nil) and (PM <> nil) then begin
    CtrlCtl := Ctrl as TControl;
    PM.Popup(CtrlCtl.AbsoluteRect.CenterPoint.X,
             CtrlCtl.AbsoluteRect.CenterPoint.Y);
  end;
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdHover(const ReqId, Target: string): string;
var
  Ctrl: TComponent;
  CtrlCtl: TControl;
  Pt: TPointF;
  F: TCommonCustomForm;
begin
  if Screen.ActiveForm = nil then Exit(WriteResp(ReqId, 'ok', 'OK'));
  F := Screen.ActiveForm;
  Ctrl := F.FindComponent(Target);
  if Ctrl = nil then Exit(WriteResp(ReqId, 'ok', 'OK'));
  if Ctrl is TControl then begin
    CtrlCtl := TControl(Ctrl);
    Pt := CtrlCtl.LocalToAbsolute(TPointF.Create(
      CtrlCtl.Width / 2, CtrlCtl.Height / 2));
    SetCursorPos(Round(Pt.X), Round(Pt.Y));
  end;
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdMove(const ReqId, Target: string; const X,
  Y: Integer): string;
var
  Ctrl: TComponent;
  CtrlCtl: TControl;
  Pt: TPointF;
  F: TCommonCustomForm;
  CX, CY: Integer;
begin
  if Target <> '' then begin
    if Screen.ActiveForm = nil then Exit(WriteResp(ReqId, 'ok', 'OK'));
    F := Screen.ActiveForm;
    Ctrl := F.FindComponent(Target);
    if (Ctrl <> nil) and (Ctrl is TControl) then begin
      CtrlCtl := TControl(Ctrl);
      Pt := CtrlCtl.LocalToAbsolute(TPointF.Create(
        CtrlCtl.Width / 2, CtrlCtl.Height / 2));
      CX := Round(Pt.X);
      CY := Round(Pt.Y);
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

{ --- drag --- }

function TAutomationProcessor.HandleCmdDrag(const ReqId, Source, Target: string;
  const X, Y: Integer): string;
var
  SX, SY, TX, TY, I: Integer;
  SrcCtrl, DstCtrl: TComponent;
  SrcCtl: TControl;
  Pt: TPointF;
begin
  if (Screen.ActiveForm = nil) or (Source = '') then
    Exit(WriteResp(ReqId, 'ok', 'OK'));

  SrcCtrl := Screen.ActiveForm.FindComponent(Source);
  if (SrcCtrl = nil) or not (SrcCtrl is TControl) then
    Exit(WriteResp(ReqId, 'ok', 'OK'));

  SrcCtl := TControl(SrcCtrl);
  Pt := SrcCtl.LocalToAbsolute(TPointF.Create(
    SrcCtl.Width / 2, SrcCtl.Height / 2));
  SX := Round(Pt.X); SY := Round(Pt.Y);

  if Target <> '' then begin
    DstCtrl := Screen.ActiveForm.FindComponent(Target);
    if (DstCtrl <> nil) and (DstCtrl is TControl) then begin
      Pt := TControl(DstCtrl).LocalToAbsolute(TPointF.Create(
        TControl(DstCtrl).Width / 2, TControl(DstCtrl).Height / 2));
      TX := Round(Pt.X); TY := Round(Pt.Y);
    end else Exit(WriteResp(ReqId, 'ok', 'OK'));
  end else if (X >= 0) and (Y >= 0) then begin
    TX := X; TY := Y;
  end else Exit(WriteResp(ReqId, 'ok', 'OK'));

  // 模拟拖拽：mousedown → 渐进移动 → mouseup
  SetCursorPos(SX, SY);
  mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0);

  for I := 1 to 10 do begin
    SetCursorPos(
      SX + (TX - SX) * I div 10,
      SY + (TY - SY) * I div 10);
    Sleep(8);
  end;

  SetCursorPos(TX, TY);
  mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0);
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

function TAutomationProcessor.HandleCmdType(const ReqId, Target,
  Value: string): string;
var
  Ctrl: TComponent;
  Ctx: TRttiContext;
  Prop: TRttiProperty;
begin
  if (Target <> '') and (Screen.ActiveForm <> nil) then begin
    Ctrl := Screen.ActiveForm.FindComponent(Target);
    if Ctrl <> nil then begin
      Ctx := TRttiContext.Create;
      try
        Prop := Ctx.GetType(Ctrl.ClassType).GetProperty('Text');
        if (Prop <> nil) and Prop.IsWritable then
          Prop.SetValue(Ctrl, Value);
      finally
        Ctx.Free;
      end;
    end;
  end;
  Result := WriteResp(ReqId, 'ok', 'OK');
end;

{ --- RTTI --- }

function TAutomationProcessor.HandleRGet(const ReqId, Target,
  Prop: string): string;
var
  Ctrl: TComponent;
  Ctx: TRttiContext;
  Pr: TRttiProperty;
  V: TValue;
  Obj: TObject;
  Parts: TArray<string>;
  i: Integer;
begin
  try
    if Screen.ActiveForm = nil then Exit(WriteResp(ReqId, 'err', 'no active form'));
    Ctrl := Screen.ActiveForm.FindComponent(Target);
    if Ctrl = nil then Exit(WriteResp(ReqId, 'err', 'NF:' + Target));

    Parts := Prop.Split(['.']);
    if Length(Parts) = 0 then Exit(WriteResp(ReqId, 'err', 'no property'));

    Ctx := TRttiContext.Create;
    try
      Pr := Ctx.GetType(Ctrl.ClassType).GetProperty(Parts[0]);
      if Pr = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + Parts[0]));
      if not Pr.IsReadable then Exit(WriteResp(ReqId, 'err', 'NR:' + Parts[0]));
      V := Pr.GetValue(Ctrl);

      for i := 1 to High(Parts) do begin
        if V.Kind <> tkClass then Exit(WriteResp(ReqId, 'err', 'not an object: ' + Parts[i]));
        Obj := V.AsObject;
        if Obj = nil then Exit(WriteResp(ReqId, 'err', 'nil: ' + Parts[i]));
        Pr := Ctx.GetType(Obj.ClassType).GetProperty(Parts[i]);
        if Pr = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + Parts[i]));
        if not Pr.IsReadable then Exit(WriteResp(ReqId, 'err', 'NR:' + Parts[i]));
        V := Pr.GetValue(Obj);
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
  Ctrl: TComponent;
  Ctx: TRttiContext;
  Pr: TRttiProperty;
begin
  try
    if Screen.ActiveForm = nil then Exit(WriteResp(ReqId, 'err', 'no active form'));
    Ctrl := Screen.ActiveForm.FindComponent(Target);
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

{ ── RTTI 调用方法 ── }

function TAutomationProcessor.HandleRCall(const ReqId, Target,
  Method, ParamsJSON: string): string;
var
  Ctrl: TComponent;
  Ctx: TRttiContext;
  M: TRttiMethod;
  Parts: TArray<string>;
  Obj: TObject;
  i, p: Integer;
  Pr: TRttiProperty;
  V: TValue;
  ParamValues: TArray<TValue>;
  ParamArr: TJSONArray;
  ParamType: TRttiType;
begin
  try
    if Screen.ActiveForm = nil then
      Exit(WriteResp(ReqId, 'err', 'no active form'));
    Ctrl := Screen.ActiveForm.FindComponent(Target);
    if Ctrl = nil then
      Exit(WriteResp(ReqId, 'err', 'NF:' + Target));

    Parts := Method.Split(['.']);
    if Length(Parts) = 0 then
      Exit(WriteResp(ReqId, 'err', 'no method'));

    Ctx := TRttiContext.Create;
    try
      Obj := Ctrl;
      for i := 0 to Length(Parts) - 2 do begin
        Pr := Ctx.GetType(Obj.ClassType).GetProperty(Parts[i]);
        if Pr = nil then Exit(WriteResp(ReqId, 'err', 'NP:' + Parts[i]));
        V := Pr.GetValue(Obj);
        Obj := V.AsObject;
        if Obj = nil then Exit(WriteResp(ReqId, 'err', 'nil:' + Parts[i]));
      end;

      M := Ctx.GetType(Obj.ClassType).GetMethod(Parts[High(Parts)]);
      if M = nil then
        Exit(WriteResp(ReqId, 'err', 'NM:' + Parts[High(Parts)]));

      if ParamsJSON <> '' then begin
        ParamArr := TJSONObject.ParseJSONValue(ParamsJSON) as TJSONArray;
        if ParamArr <> nil then try
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
                    ParamValues[p] := TValue.From(
                      SameText(ParamArr.Items[p].Value, 'true'))
                  else
                    ParamValues[p] := TValue.From<string>(ParamArr.Items[p].Value);
              else
                ParamValues[p] := TValue.From<string>(ParamArr.Items[p].Value);
              end;
            end;
          end;
        finally ParamArr.Free; end;
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

function TAutomationProcessor.HandleRInsp(const ReqId, Target: string): string;
var
  Ctrl: TComponent;
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

    Ctrl := Screen.ActiveForm.FindComponent(Target);
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

{ --- listwnd --- }

function TAutomationProcessor.HandleCmdListWnd(const ReqId: string): string;
var
  Root: TJSONObject;
  Items: TJSONArray;
  I: Integer;
  F: TCommonCustomForm;
  Item: TJSONObject;
begin
  Root := TJSONObject.Create;
  try
    Items := TJSONArray.Create;
    for I := 0 to Screen.FormCount - 1 do begin
      F := Screen.Forms[I] as TCommonCustomForm;
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

{ --- 辅助 --- }

procedure TAutomationProcessor.DoTerminateApp;
begin
  Terminate;  // 管道线程下次循环检查到 Terminated 会自行退出
  Application.Terminate;
  PostQuitMessage(0);  // 向主线程消息队列发 WM_QUIT，确保 Run 退出
end;

function TAutomationProcessor.FindNamedControl(const AName: string): TObject;
begin
  if Screen.ActiveForm <> nil then
    Result := Screen.ActiveForm.FindComponent(AName)
  else
    Result := nil;
end;

function TAutomationProcessor.GetActiveForm: TObject;
begin
  Result := Screen.ActiveForm;
end;

end.
