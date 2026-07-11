unit DaofyAutomation.TextCapture;

{===============================================================================
  DaofyAutomation.TextCapture - 文本绘制捕获管理器

  通过 IAT hook 拦截 GDI/GDI+ 文本绘制函数，在目标控件重绘到假 DC 期间
  捕获所有文本绘制调用的内容和坐标。框架无关（不引用 Vcl.Controls 或
  FMX.Controls），由调用者负责调用 PaintTo 到假 DC。

  架构（A15 假 DC + A16 GDI+ 完整处理）：
    1. 调用者创建屏幕 DC，传入 BeginCapture 获取假 DC（VCL 模式）
       或调用 BeginCaptureFMX（FMX 模式，不创建假 DC）
    2. 调用者对目标控件执行 PaintTo(假DC, 0, 0)
    3. hook 函数在 PaintTo 期间捕获所有 GDI/GDI+ 文本绘制调用
    4. 调用者调用 EndCapture 获取所有文本记录
    5. 调用者调用 FilterBySearchText 过滤匹配项

  支持的 hook API：
    GDI:   TextOutW, ExtTextOutW, DrawTextExW, PolyTextOutW, TabbedTextOutW
    GDI+:  GdipCreateFromHDC, GdipDeleteGraphics, GdipDrawString,
           GdipDrawDriverString
           (GdipMeasureString 不 hook，仅在 HookGdipDrawString 内主动调用)

  双过滤策略（A16）：
    VCL 模式（FFakeDC ≠ 0）：
      GDI 函数   → DC = FFakeDC
      GDI+ 函数  → GraphicsMap[Graphics] = FFakeDC
    FMX 模式（FFakeDC = 0）：
      GDI 函数   → DC ∈ FCapturedDCSet
      GDI+ 函数  → Graphics ∈ FCapturedGraphicsSet
===============================================================================}

interface

uses
  System.SysUtils,
  System.Classes,
  System.Generics.Collections,
  System.Types,
  Winapi.Windows,
  Winapi.Messages,
  DaofyAutomation.IATHook;

type
  TVisibleState = (vsFullyVisible, vsPartiallyVisible, vsInvisible);

  /// <summary> 单次文本绘制记录 </summary>
  TTextRecord = record
    Text: string;
    Rect: TRect; // 文本完整绘制矩形（客户区坐标）
    VisibleRect: TRect; // 实际可见矩形（DC 剪裁区域与 Rect 的交集）
    ClipRect: TRect; // API 剪裁矩形（ETO_CLIPPED/DrawTextEx Rect 参数）
    Hwnd: HWND;
    Api: string; // 来源 API 名称
    VisibleState: TVisibleState;
    HasClip: Boolean;
  end;
  TTextRecordList = TArray<TTextRecord>;

  /// <summary> 文本捕获管理器（单例） </summary>
TTextCaptureManager = class
private
  FCapturing: Boolean;
  FRecords: TList<TTextRecord>;
  // 假 DC 资源（VCL 模式）
  FFakeDC: HDC;
  FFakeBmp: HBITMAP;
  FOldBmp: HGDIOBJ;
  FHookFailed: Boolean;
  // hook 基础设施
  FHooks: TList<TMultiIATHook>;
  FHooksInstalled: Boolean;
      // A16：GDI+ 映射
      FGraphicsMap: TDictionary<Pointer, HDC>; // GpGraphics* → 源 HDC（VCL 用）
      FCapturedGraphicsSet: TDictionary<Pointer, Boolean>; // FMX 捕获的 Graphics* 集合
      FCapturedDCSet: TDictionary<HDC, Boolean>; // FMX 捕获的 HDC 集合
      // hook trampolines（原函数地址）
      FTrampTextOutW: function(DC: HDC; X, Y: Integer; Str: PWideChar; Cnt: Integer): BOOL; stdcall;
      FTrampExtTextOutW:
          function(DC: HDC; X, Y: Integer; Options: DWORD; Rect: PRect; Str: PWideChar; Cnt: UINT; Dx: PInteger): BOOL;
          stdcall;
      FTrampDrawTextExW:
          function(DC: HDC; Str: PWideChar; Cnt: Integer; Rect: PRect; Flags: UINT; DTParams: PDrawTextParams): Integer;
          stdcall;
      FTrampPolyTextOutW: function(DC: HDC; ppt: Pointer; cStrings: Integer): BOOL; stdcall;
      FTrampTabbedTextOutW:
          function(
              DC: HDC;
              X, Y: Integer;
              Str: PWideChar;
              Cnt: Integer;
              nTabPositions: Integer;
              lpnTabStopPositions: PInteger;
              nTabOrigin: Integer
          ): LongInt; stdcall;
      FTrampGdipCreateFromHDC: function(DC: HDC; out Graphics: Pointer): Integer; stdcall;
      FTrampGdipDeleteGraphics: function(Graphics: Pointer): Integer; stdcall;
      FTrampGdipDrawString:
          function(
              Graphics: Pointer;
              Str: PWideChar;
              Len: Integer;
              Font: Pointer;
              layoutRect: PRectF;
              StringFormat: Pointer
          ): Integer; stdcall;
      FTrampGdipDrawDriverString:
          function(
              Graphics: Pointer;
              Str: PWideChar;
              Len: Integer;
              Font: Pointer;
              positions: PPointF;
              flags: Integer;
              matrix: Pointer
          ): Integer; stdcall;
      FTrampGdipMeasureString:
          function(
              Graphics: Pointer;
              Str: PWideChar;
              Len: Integer;
              Font: Pointer;
              layoutRect: PRectF;
              StringFormat: Pointer;
              boundingBox: PRectF;
              codepointsFitted: PInteger;
              linesFilled: PInteger
          ): Integer; stdcall;
    class var FInstance: TTextCaptureManager;
    procedure EnsureHooksInstalled;
    procedure AddRecord(
        const AText: string;
        const ARect: TRect;
        AHwnd: HWND;
        const AApi: string;
        const AClipRect: TRect;
        AHasClip: Boolean;
        const AVisibleRect: TRect;
        AVisibleState: TVisibleState
    );
    function IsTargetDC(DC: HDC): Boolean;
    function IsTargetGraphics(Graphics: Pointer): Boolean;
  public
    constructor Create;
    destructor Destroy; override;
    class function Instance: TTextCaptureManager;
    class procedure ReleaseInstance;

    /// <summary> VCL 模式：创建假 DC，调用者用返回的 DC 做 PaintTo </summary>
    function BeginCapture(AScreenDC: HDC; AWidth, AHeight: Integer): HDC;
    /// <summary> FMX 模式：不创建假 DC，依赖 FCapturedDCSet/FCapturedGraphicsSet </summary>
    procedure BeginCaptureFMX;
    /// <summary> 结束捕获，返回所有文本记录 </summary>
    function EndCapture: TTextRecordList;
    /// <summary> 按搜索文本过滤记录 </summary>
    function FilterBySearchText(
        const ARecords: TTextRecordList;
        const ASearchText: string;
        AIncludeInvisible: Boolean
    ): TTextRecordList;

    property Capturing: Boolean read FCapturing;
    property FakeDC: HDC read FFakeDC;
    property HookFailed: Boolean read FHookFailed;
  end;

implementation

{ ── 辅助函数 ── }

/// 从 PWideChar + 长度构造 string 并 Trim
function CaptureText(P: PWideChar; Len: Integer): string;
begin
  Result := '';
  if (P <> nil) and (Len > 0) then begin
    SetLength(Result, Len);
    Move(P^, Pointer(Result)^, Len * SizeOf(WideChar));
  end;
  Result := Trim(Result);
end;

/// A14-bis：计算 DC 剪裁区域与文本矩形的交集
function CalculateVisibleRect(DC: HDC; const ARect: TRect; out AVisible: TRect): TVisibleState;
var
  ClipRgn, TextRgn, IntersectRgn: HRGN;
  CombineResult: Integer;
  Bounds: TRect;
begin
  Result := vsFullyVisible;
  AVisible := ARect;

  // 快速路径：完全不可见
  if not RectVisible(DC, ARect) then begin
    Result := vsInvisible;
    AVisible := Rect(0, 0, 0, 0);
    Exit;
  end;

  ClipRgn := CreateRectRgn(0, 0, 0, 0);
  try
    // GetClipRgn 返回 0 表示无剪裁区域
    if GetClipRgn(DC, ClipRgn) = 0 then
      Exit;

    TextRgn := CreateRectRgnIndirect(ARect);
    try
      IntersectRgn := CreateRectRgn(0, 0, 0, 0);
      try
        CombineResult := CombineRgn(IntersectRgn, TextRgn, ClipRgn, RGN_AND);
        case CombineResult of
          NULLREGION: begin
            Result := vsInvisible;
            AVisible := Rect(0, 0, 0, 0);
          end;
          SIMPLEREGION: begin
            GetRgnBox(IntersectRgn, Bounds);
            AVisible := Bounds;
            if not EqualRect(Bounds, ARect) then
              Result := vsPartiallyVisible;
          end;
          COMPLEXREGION: begin
            GetRgnBox(IntersectRgn, Bounds);
            AVisible := Bounds;
            Result := vsPartiallyVisible;
          end;
        end;
      finally
        DeleteObject(IntersectRgn);
      end;
    finally
      DeleteObject(TextRgn);
    end;
  finally
    DeleteObject(ClipRgn);
  end;
end;

{ ── hook 函数前向声明 ── }

function HookTextOutW(DC: HDC; X, Y: Integer; Str: PWideChar; Cnt: Integer): BOOL; stdcall; forward;
function HookExtTextOutW(
    DC: HDC;
    X, Y: Integer;
    Options: DWORD;
    Rect: PRect;
    Str: PWideChar;
    Cnt: UINT;
    Dx: PInteger
): BOOL; stdcall; forward;
function HookDrawTextExW(
    DC: HDC;
    Str: PWideChar;
    Cnt: Integer;
    Rect: PRect;
    Flags: UINT;
    DTParams: PDrawTextParams
): Integer; stdcall; forward;
function HookPolyTextOutW(DC: HDC; ppt: Pointer; cStrings: Integer): BOOL; stdcall; forward;
function HookTabbedTextOutW(
    DC: HDC;
    X, Y: Integer;
    Str: PWideChar;
    Cnt: Integer;
    nTabPositions: Integer;
    lpnTabStopPositions: PInteger;
    nTabOrigin: Integer
): LongInt; stdcall; forward;
function HookGdipCreateFromHDC(DC: HDC; out Graphics: Pointer): Integer; stdcall; forward;
function HookGdipDeleteGraphics(Graphics: Pointer): Integer; stdcall; forward;
function HookGdipDrawString(
    Graphics: Pointer;
    Str: PWideChar;
    Len: Integer;
    Font: Pointer;
    layoutRect: PRectF;
    StringFormat: Pointer
): Integer; stdcall; forward;
function HookGdipDrawDriverString(
    Graphics: Pointer;
    Str: PWideChar;
    Len: Integer;
    Font: Pointer;
    positions: PPointF;
    flags: Integer;
    matrix: Pointer
): Integer; stdcall; forward;

{ ── GDI hook 函数实现 ── }

function HookTextOutW(DC: HDC; X, Y: Integer; Str: PWideChar; Cnt: Integer): BOOL; stdcall;
var
  Mgr: TTextCaptureManager;
  TextStr: string;
  FinalRect, VisibleRect: TRect;
  Size: TSize;
  VisState: TVisibleState;
begin
  Mgr := TTextCaptureManager.Instance;
  if Mgr.Capturing and (Cnt > 0) and (Str <> nil) and Mgr.IsTargetDC(DC) then begin
    TextStr := CaptureText(Str, Cnt);
    if TextStr <> '' then begin
      if GetTextExtentPoint32W(DC, Str, Cnt, Size) then
        FinalRect := Bounds(X, Y, Size.cx, Size.cy)
      else
        FinalRect := Bounds(X, Y, 0, 0);
      VisState := CalculateVisibleRect(DC, FinalRect, VisibleRect);
      Mgr.AddRecord(TextStr, FinalRect, 0, 'TextOutW', Rect(0, 0, 0, 0), False, VisibleRect, VisState);
    end;
  end;
  Result := Mgr.FTrampTextOutW(DC, X, Y, Str, Cnt);
end;

function HookExtTextOutW(
    DC: HDC;
    X, Y: Integer;
    Options: DWORD;
    Rect: PRect;
    Str: PWideChar;
    Cnt: UINT;
    Dx: PInteger
): BOOL; stdcall;
var
  Mgr: TTextCaptureManager;
  TextStr: string;
  FinalRect, ClipRect, VisibleRect: TRect;
  HasClip: Boolean;
  Size: TSize;
  VisState: TVisibleState;
begin
  Mgr := TTextCaptureManager.Instance;
  if Mgr.Capturing and (Cnt > 0) and (Str <> nil) and Mgr.IsTargetDC(DC) then begin
    TextStr := CaptureText(Str, Cnt);
    if TextStr <> '' then begin
      // C1：始终用 X/Y 作起点，宽高用 GetTextExtentPoint32W 查询
      if GetTextExtentPoint32W(DC, Str, Cnt, Size) then
        FinalRect := Bounds(X, Y, Size.cx, Size.cy)
      else
        FinalRect := Bounds(X, Y, 0, 0);

      // C1：ETO_CLIPPED 的 Rect 作为 clip_rect 字段
      HasClip := (Rect <> nil) and ((Options and ETO_CLIPPED) <> 0);
      if HasClip then
        ClipRect := Rect^
      else
        ClipRect := TRect.Create(0, 0, 0, 0);

      // A14-bis：DC 剪裁区域与文本矩形求交集
      VisState := CalculateVisibleRect(DC, FinalRect, VisibleRect);
      Mgr.AddRecord(TextStr, FinalRect, 0, 'ExtTextOutW', ClipRect, HasClip, VisibleRect, VisState);
    end;
  end;
  Result := Mgr.FTrampExtTextOutW(DC, X, Y, Options, Rect, Str, Cnt, Dx);
end;

function HookDrawTextExW(
    DC: HDC;
    Str: PWideChar;
    Cnt: Integer;
    Rect: PRect;
    Flags: UINT;
    DTParams: PDrawTextParams
): Integer; stdcall;
var
  Mgr: TTextCaptureManager;
  TextStr: string;
  FinalRect, ClipRect, VisibleRect: TRect;
  HasClip: Boolean;
  VisState: TVisibleState;
  ActualLen: Integer;
begin
  Mgr := TTextCaptureManager.Instance;
  // DrawTextExW 的 Cnt 可能是 -1（表示 null-terminated）
  ActualLen := Cnt;
  if ActualLen = -1 then
    ActualLen := StrLen(Str);
  if Mgr.Capturing and (ActualLen > 0) and (Str <> nil) and Mgr.IsTargetDC(DC) and ((Flags and DT_CALCRECT) = 0) then
  begin
    TextStr := CaptureText(Str, ActualLen);
    if TextStr <> '' then begin
      if Rect <> nil then begin
        FinalRect := Rect^;
        // 非 CALCRECT 模式，Rect 是布局/剪裁框
        HasClip := True;
        ClipRect := Rect^;
      end
      else begin
        FinalRect := TRect.Create(0, 0, 0, 0);
        HasClip := False;
        ClipRect := TRect.Create(0, 0, 0, 0);
      end;
      VisState := CalculateVisibleRect(DC, FinalRect, VisibleRect);
      Mgr.AddRecord(TextStr, FinalRect, 0, 'DrawTextExW', ClipRect, HasClip, VisibleRect, VisState);
    end;
  end;
  Result := Mgr.FTrampDrawTextExW(DC, Str, Cnt, Rect, Flags, DTParams);
end;

function HookPolyTextOutW(DC: HDC; ppt: Pointer; cStrings: Integer): BOOL; stdcall;
var
  Mgr: TTextCaptureManager;
  I: Integer;
  Entry: PPolyText;
  TextStr: string;
  FinalRect, VisibleRect: TRect;
  Size: TSize;
  VisState: TVisibleState;
begin
  Mgr := TTextCaptureManager.Instance;
  if Mgr.Capturing and (ppt <> nil) and (cStrings > 0) and Mgr.IsTargetDC(DC) then begin
    Entry := PPolyText(ppt);
    for I := 0 to cStrings - 1 do begin
      if (Entry^.lpstr <> nil) and (Entry^.n > 0) then begin
        TextStr := CaptureText(Entry^.lpstr, Entry^.n);
        if TextStr <> '' then begin
          // 用 GetTextExtentPoint32W 查询尺寸
          if GetTextExtentPoint32W(DC, Entry^.lpstr, Entry^.n, Size) then
            FinalRect := Bounds(Entry^.x, Entry^.y, Size.cx, Size.cy)
          else
            FinalRect := Bounds(Entry^.x, Entry^.y, 0, 0);
          VisState := CalculateVisibleRect(DC, FinalRect, VisibleRect);
          Mgr.AddRecord(TextStr, FinalRect, 0, 'PolyTextOutW', Entry^.rcl, True, VisibleRect, VisState);
        end;
      end;
      Inc(Entry);
    end;
  end;
  Result := Mgr.FTrampPolyTextOutW(DC, ppt, cStrings);
end;

function HookTabbedTextOutW(
    DC: HDC;
    X, Y: Integer;
    Str: PWideChar;
    Cnt: Integer;
    nTabPositions: Integer;
    lpnTabStopPositions: PInteger;
    nTabOrigin: Integer
): LongInt; stdcall;
var
  Mgr: TTextCaptureManager;
  TextStr: string;
  FinalRect, VisibleRect: TRect;
  Size: TSize;
  VisState: TVisibleState;
begin
  Mgr := TTextCaptureManager.Instance;
  if Mgr.Capturing and (Cnt > 0) and (Str <> nil) and Mgr.IsTargetDC(DC) then begin
    TextStr := CaptureText(Str, Cnt);
    if TextStr <> '' then begin
      // 用 GetTextExtentPoint32W 估算（不含 tab 扩展）
      if GetTextExtentPoint32W(DC, Str, Cnt, Size) then
        FinalRect := Bounds(X, Y, Size.cx, Size.cy)
      else
        FinalRect := Bounds(X, Y, 0, 0);
      VisState := CalculateVisibleRect(DC, FinalRect, VisibleRect);
      Mgr.AddRecord(TextStr, FinalRect, 0, 'TabbedTextOutW', TRect.Create(0, 0, 0, 0), False, VisibleRect, VisState);
    end;
  end;
  Result := Mgr.FTrampTabbedTextOutW(DC, X, Y, Str, Cnt, nTabPositions, lpnTabStopPositions, nTabOrigin);
end;

{ ── GDI+ hook 函数实现（A16） ── }

function HookGdipCreateFromHDC(DC: HDC; out Graphics: Pointer): Integer; stdcall;
var
  Mgr: TTextCaptureManager;
begin
  Mgr := TTextCaptureManager.Instance;
  Result := Mgr.FTrampGdipCreateFromHDC(DC, Graphics);
  // 只在捕获期间记录映射（避免平时污染映射表）
  if (Result = 0) and (Graphics <> nil) and Mgr.Capturing then begin
    Mgr.FGraphicsMap.AddOrSetValue(Graphics, DC);
    Mgr.FCapturedGraphicsSet.AddOrSetValue(Graphics, True);
    // FMX 端也记录 HDC（用于 GDI 函数过滤）
    if Mgr.FFakeDC = 0 then
      Mgr.FCapturedDCSet.AddOrSetValue(DC, True);
  end;
end;

function HookGdipDeleteGraphics(Graphics: Pointer): Integer; stdcall;
var
  Mgr: TTextCaptureManager;
begin
  Mgr := TTextCaptureManager.Instance;
  Mgr.FGraphicsMap.Remove(Graphics);
  Mgr.FCapturedGraphicsSet.Remove(Graphics);
  Result := Mgr.FTrampGdipDeleteGraphics(Graphics);
end;

function HookGdipDrawString(
    Graphics: Pointer;
    Str: PWideChar;
    Len: Integer;
    Font: Pointer;
    layoutRect: PRectF;
    StringFormat: Pointer
): Integer; stdcall;
var
  Mgr: TTextCaptureManager;
  TextStr: string;
  FinalRect: TRect;
  BoundingBox: TRectF;
  fitted, lines: Integer;
begin
  Mgr := TTextCaptureManager.Instance;
  if Mgr.Capturing and (Graphics <> nil) and (Str <> nil) and (Len > 0) and Mgr.IsTargetGraphics(Graphics) then begin
    TextStr := CaptureText(Str, Len);
    if TextStr <> '' then begin
      // A7：layoutRect 是 PRectF，四舍五入取整
      if layoutRect <> nil then begin
        FinalRect :=
            TRect.Create(
                Round(layoutRect^.Left),
                Round(layoutRect^.Top),
                Round(layoutRect^.Left + layoutRect^.Width),
                Round(layoutRect^.Top + layoutRect^.Height)
            );
      end
      else begin
        // G6：无 layoutRect 时用 GdipMeasureString 反查实际边界
        if Assigned(Mgr.FTrampGdipMeasureString) then begin
          FillChar(BoundingBox, SizeOf(BoundingBox), 0);
          fitted := 0;
          lines := 0;
          Mgr.FTrampGdipMeasureString(Graphics, Str, Len, Font, nil, StringFormat, @BoundingBox, @fitted, @lines);
          FinalRect :=
              TRect.Create(
                  Round(BoundingBox.Left),
                  Round(BoundingBox.Top),
                  Round(BoundingBox.Left + BoundingBox.Width),
                  Round(BoundingBox.Top + BoundingBox.Height)
              );
        end
        else
          FinalRect := TRect.Create(0, 0, 0, 0);
      end;

      // GDI+ 剪裁不做精确检测（A14-bis 补充），默认 vsPartiallyVisible
      Mgr.AddRecord(
          TextStr,
          FinalRect,
          0,
          'GdipDrawString',
          TRect.Create(0, 0, 0, 0),
          False,
          FinalRect,
          vsPartiallyVisible
      );
    end;
  end;
  Result := Mgr.FTrampGdipDrawString(Graphics, Str, Len, Font, layoutRect, StringFormat);
end;

{$POINTERMATH ON}
function HookGdipDrawDriverString(
    Graphics: Pointer;
    Str: PWideChar;
    Len: Integer;
    Font: Pointer;
    positions: PPointF;
    flags: Integer;
    matrix: Pointer
): Integer; stdcall;
var
  Mgr: TTextCaptureManager;
  TextStr: string;
  FinalRect: TRect;
  I: Integer;
  MinX, MinY, MaxX, MaxY: Single;
  Pt: TPointF;
begin
  Mgr := TTextCaptureManager.Instance;
  if Mgr.Capturing and (Graphics <> nil) and (Str <> nil) and (Len > 0) and Mgr.IsTargetGraphics(Graphics) then begin
    TextStr := CaptureText(Str, Len);
    if TextStr <> '' then begin
      // positions 是每个字符的精确位置（Len 个 PointF）
      if positions <> nil then begin
        MinX := positions[0].X;
        MinY := positions[0].Y;
        MaxX := MinX;
        MaxY := MinY;
        for I := 1 to Len - 1 do begin
          Pt := positions[I];
          if Pt.X < MinX then
            MinX := Pt.X;
          if Pt.Y < MinY then
            MinY := Pt.Y;
          if Pt.X > MaxX then
            MaxX := Pt.X;
          if Pt.Y > MaxY then
            MaxY := Pt.Y;
        end;
        // MaxX/MaxY 加一个字符宽度的估算（DriverString 不返回宽高）
        FinalRect := TRect.Create(Round(MinX), Round(MinY), Round(MaxX) + 20, Round(MaxY) + 20);
      end
      else
        FinalRect := TRect.Create(0, 0, 0, 0);
      Mgr.AddRecord(
          TextStr,
          FinalRect,
          0,
          'GdipDrawDriverString',
          TRect.Create(0, 0, 0, 0),
          False,
          FinalRect,
          vsPartiallyVisible
      );
    end;
  end;
  Result := Mgr.FTrampGdipDrawDriverString(Graphics, Str, Len, Font, positions, flags, matrix);
end;

{ ── TTextCaptureManager ── }

constructor TTextCaptureManager.Create;
begin
  FRecords := TList<TTextRecord>.Create;
  FHooks := TList<TMultiIATHook>.Create;
  FGraphicsMap := TDictionary<Pointer, HDC>.Create;
  FCapturedGraphicsSet := TDictionary<Pointer, Boolean>.Create;
  FCapturedDCSet := TDictionary<HDC, Boolean>.Create;
end;

destructor TTextCaptureManager.Destroy;
var
  H: TMultiIATHook;
begin
  FRecords.Free;
  for H in FHooks do
    H.Free;
  FHooks.Free;
  FGraphicsMap.Free;
  FCapturedGraphicsSet.Free;
  FCapturedDCSet.Free;
  inherited;
end;

class function TTextCaptureManager.Instance: TTextCaptureManager;
begin
  if FInstance = nil then
    FInstance := TTextCaptureManager.Create;
  Result := FInstance;
end;

class procedure TTextCaptureManager.ReleaseInstance;
begin
  FreeAndNil(FInstance);
end;

procedure TTextCaptureManager.EnsureHooksInstalled;
var
  H: TMultiIATHook;
  GdiplusMod: HMODULE;
begin
  if FHooksInstalled then
    Exit;
  FHooksInstalled := True;

  // === GDI hooks ===
  H := TMultiIATHook.Create('gdi32.dll', 'TextOutW', @HookTextOutW);
  FHooks.Add(H);
  if H.Trampoline <> nil then
    @FTrampTextOutW := H.Trampoline;

  H := TMultiIATHook.Create('gdi32.dll', 'ExtTextOutW', @HookExtTextOutW);
  FHooks.Add(H);
  if H.Trampoline <> nil then
    @FTrampExtTextOutW := H.Trampoline;

  H := TMultiIATHook.Create('user32.dll', 'DrawTextExW', @HookDrawTextExW);
  FHooks.Add(H);
  if H.Trampoline <> nil then
    @FTrampDrawTextExW := H.Trampoline;

  H := TMultiIATHook.Create('gdi32.dll', 'PolyTextOutW', @HookPolyTextOutW);
  FHooks.Add(H);
  if H.Trampoline <> nil then
    @FTrampPolyTextOutW := H.Trampoline;

  H := TMultiIATHook.Create('gdi32.dll', 'TabbedTextOutW', @HookTabbedTextOutW);
  FHooks.Add(H);
  if H.Trampoline <> nil then
    @FTrampTabbedTextOutW := H.Trampoline;

  // === GDI+ hooks（gdiplus.dll 可能未加载）===
  GdiplusMod := GetModuleHandle('gdiplus.dll');
  if GdiplusMod <> 0 then begin
    // A16：GDI+ 生命周期 hook
    H := TMultiIATHook.Create('gdiplus.dll', 'GdipCreateFromHDC', @HookGdipCreateFromHDC);
    FHooks.Add(H);
    if H.Trampoline <> nil then
      @FTrampGdipCreateFromHDC := H.Trampoline;

    H := TMultiIATHook.Create('gdiplus.dll', 'GdipDeleteGraphics', @HookGdipDeleteGraphics);
    FHooks.Add(H);
    if H.Trampoline <> nil then
      @FTrampGdipDeleteGraphics := H.Trampoline;

    // GdipDrawString hook（A7 原有）
    H := TMultiIATHook.Create('gdiplus.dll', 'GdipDrawString', @HookGdipDrawString);
    FHooks.Add(H);
    if H.Trampoline <> nil then
      @FTrampGdipDrawString := H.Trampoline;

    // A16：GdipDrawDriverString（精确字符定位）
    H := TMultiIATHook.Create('gdiplus.dll', 'GdipDrawDriverString', @HookGdipDrawDriverString);
    FHooks.Add(H);
    if H.Trampoline <> nil then
      @FTrampGdipDrawDriverString := H.Trampoline;

    // GdipMeasureString 不 hook（A16），通过 GetProcAddress 获取地址
    @FTrampGdipMeasureString := GetProcAddress(GdiplusMod, 'GdipMeasureString');
  end;
end;

procedure TTextCaptureManager.AddRecord(
    const AText: string;
    const ARect: TRect;
    AHwnd: HWND;
    const AApi: string;
    const AClipRect: TRect;
    AHasClip: Boolean;
    const AVisibleRect: TRect;
    AVisibleState: TVisibleState
);
var
  Rec: TTextRecord;
begin
  Rec.Text := AText;
  Rec.Rect := ARect;
  Rec.VisibleRect := AVisibleRect;
  Rec.ClipRect := AClipRect;
  Rec.Hwnd := AHwnd;
  Rec.Api := AApi;
  Rec.VisibleState := AVisibleState;
  Rec.HasClip := AHasClip;
  FRecords.Add(Rec);
end;

function TTextCaptureManager.IsTargetDC(DC: HDC): Boolean;
begin
  if FFakeDC <> 0 then
    // VCL 模式：精确 DC 比较
    Result := (DC = FFakeDC)
  else
    // FMX 模式：集合查找
    Result := FCapturedDCSet.ContainsKey(DC);
end;

function TTextCaptureManager.IsTargetGraphics(Graphics: Pointer): Boolean;
var
  SrcDC: HDC;
begin
  if FFakeDC <> 0 then begin
    // VCL 模式：查 Graphics* → HDC 映射
    if FGraphicsMap.TryGetValue(Graphics, SrcDC) and (SrcDC = FFakeDC) then
      Result := True
    else
      Result := False;
  end
  else
    // FMX 模式：集合查找
    Result := FCapturedGraphicsSet.ContainsKey(Graphics);
end;

function TTextCaptureManager.BeginCapture(AScreenDC: HDC; AWidth, AHeight: Integer): HDC;
var
  FakeDC: HDC;
  Bmp: HBITMAP;
begin
  EnsureHooksInstalled;
  FRecords.Clear;
  FGraphicsMap.Clear;
  FCapturedGraphicsSet.Clear;
  FCapturedDCSet.Clear;
  FHookFailed := False;

  // 检查至少有一个 GDI 文本 hook 被安装
  if not Assigned(FTrampExtTextOutW) and not Assigned(FTrampTextOutW) and not Assigned(FTrampDrawTextExW) then begin
    FHookFailed := True;
    Exit(0);
  end;

  // A15：创建假 DC（Memory DC + 兼容位图）
  FakeDC := CreateCompatibleDC(AScreenDC);
  Bmp := CreateCompatibleBitmap(AScreenDC, AWidth, AHeight);
  if (FakeDC = 0) or (Bmp = 0) then begin
    if FakeDC <> 0 then
      DeleteDC(FakeDC);
    if Bmp <> 0 then
      DeleteObject(Bmp);
    FHookFailed := True;
    Exit(0);
  end;

  FFakeBmp := Bmp;
  FOldBmp := SelectObject(FakeDC, Bmp);
  // 白色背景，匹配屏幕默认
  PatBlt(FakeDC, 0, 0, AWidth, AHeight, WHITENESS);

  FFakeDC := FakeDC;
  FCapturing := True;
  Result := FakeDC;
end;

procedure TTextCaptureManager.BeginCaptureFMX;
begin
  EnsureHooksInstalled;
  FRecords.Clear;
  FFakeDC := 0;
  FFakeBmp := 0;
  FOldBmp := 0;
  FGraphicsMap.Clear;
  FCapturedGraphicsSet.Clear;
  FCapturedDCSet.Clear;
  FHookFailed := False;
  FCapturing := True;
end;

function TTextCaptureManager.EndCapture: TTextRecordList;
begin
  FCapturing := False;
  Result := FRecords.ToArray;
  FRecords.Clear;

  // 清理假 DC 资源（VCL 模式）
  if FFakeDC <> 0 then begin
    SelectObject(FFakeDC, FOldBmp);
    DeleteObject(FFakeBmp);
    DeleteDC(FFakeDC);
    FFakeDC := 0;
    FFakeBmp := 0;
    FOldBmp := 0;
  end;

  // 清理 FMX 集合
  FCapturedGraphicsSet.Clear;
  FCapturedDCSet.Clear;
  FGraphicsMap.Clear;
end;

function TTextCaptureManager.FilterBySearchText(
    const ARecords: TTextRecordList;
    const ASearchText: string;
    AIncludeInvisible: Boolean
): TTextRecordList;
var
  Rec: TTextRecord;
  SearchUpper: string;
  Matches: TList<TTextRecord>;
begin
  SearchUpper := AnsiUpperCase(Trim(ASearchText));
  Matches := TList<TTextRecord>.Create;
  try
    for Rec in ARecords do begin
      if (AnsiUpperCase(Rec.Text) = SearchUpper) or (Pos(SearchUpper, AnsiUpperCase(Rec.Text)) > 0) then begin
        // 默认过滤完全不可见的记录（避免噪音）
        if (not AIncludeInvisible) and (Rec.VisibleState = vsInvisible) then
          Continue;
        Matches.Add(Rec);
      end;
    end;
    Result := Matches.ToArray;
  finally
    Matches.Free;
  end;
end;

end.
