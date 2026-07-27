unit UMainForm;

interface

uses
  Winapi.Windows, Winapi.Messages,
  System.SysUtils, System.Variants, System.Classes,
  Vcl.Graphics, Vcl.Controls, Vcl.Forms, Vcl.Dialogs,
  Vcl.StdCtrls, Vcl.ComCtrls, Vcl.ExtCtrls, Vcl.Grids,
  Vcl.Buttons, Vcl.CheckLst, Vcl.Samples.Spin;

type
  TMainForm = class(TForm)
    // ── 标准按钮 ──
    btnOK: TButton;
    btnCancel: TButton;
    btnDisabled: TButton;
    btnSmall: TButton;

    // ── 文本输入 ──
    edtName: TEdit;
    edtPassword: TEdit;
    edtReadOnly: TEdit;
    memNote: TMemo;

    // ── 选择控件 ──
    chkEnable: TCheckBox;
    chkAutoSave: TCheckBox;
    chkDisabled: TCheckBox;
    rdoMale: TRadioButton;
    rdoFemale: TRadioButton;
    rdoOther: TRadioButton;
    rgGender: TRadioGroup;
    cmbCity: TComboBox;
    lstItems: TListBox;
    clbOptions: TCheckListBox;

    // ── 容器 ──
    pnlMain: TPanel;
    pnlSidebar: TPanel;
    grpInfo: TGroupBox;
    scrlOptions: TScrollBox;

    // ── 选项卡 ──
    pcMain: TPageControl;
    tsBasic: TTabSheet;
    tsAdvanced: TTabSheet;
    tsData: TTabSheet;

    // ── 数据和列表 ──
    sgData: TStringGrid;
    lvItems: TListView;
    tvTree: TTreeView;

    // ── 进度和滚动 ──
    pbProgress: TProgressBar;
    sbHorizontal: TScrollBar;
    tbVolume: TTrackBar;

    // ── 分组控件 ──
    rgOptions: TRadioGroup;
    gbFilters: TGroupBox;

    // ── 额外 ──
    lblTitle: TLabel;
    lblStatus: TLabel;
    statBar: TStatusBar;
    btnHidden: TButton;
    btnAutoCollect: TButton;

    procedure FormCreate(Sender: TObject);
    procedure FormDestroy(Sender: TObject);
    procedure btnOKClick(Sender: TObject);
    procedure btnAutoCollectClick(Sender: TObject);
  private
    procedure CaptureCurrentState(const AIndex: Integer; const AVariantName: string);
    function  ControlsToYoloLabel: TArray<string>;
  public
    { Public declarations }
  end;

var
  MainForm: TMainForm;

implementation

{$R *.dfm}

uses
  Vcl.Themes, Vcl.Styles,
  Vcl.DaofyAutomation;


// -- Catalog helpers --
procedure AddSectionLabel(const ACaption: string; var Y: Integer; AParent: TWinControl);
var L: TLabel;
begin
  L := TLabel.Create(AParent);
  L.Parent := AParent;
  L.Caption := ACaption;
  L.Font.Style := [fsBold];
  L.Font.Size := 11;
  L.Top := Y;
  L.Left := 8;
  Y := Y + 24;
end;

procedure BuildCatalogTab(AParent: TTabSheet);
var
  sc: TScrollBox;
  TopPos: Integer;
begin
  sc := TScrollBox.Create(AParent);
  sc.Parent := AParent;
  sc.Align := alClient;
  TopPos := 8;

  AddSectionLabel('TButton - Normal / Small / Disabled / Large / BitBtn', TopPos, sc);
  with TButton.Create(sc) do begin Parent := sc; Left := 8; Top := TopPos; Caption := 'OK'; Width := 80; Height := 30; end;
  with TButton.Create(sc) do begin Parent := sc; Left := 96; Top := TopPos + 4; Caption := 'Small'; Width := 50; Height := 22; end;
  with TButton.Create(sc) do begin Parent := sc; Left := 156; Top := TopPos; Caption := 'Disabled'; Width := 80; Height := 30; Enabled := False; end;
  with TButton.Create(sc) do begin Parent := sc; Left := 244; Top := TopPos - 6; Caption := 'Large Btn'; Width := 120; Height := 42; end;
  with TBitBtn.Create(sc) do begin Parent := sc; Left := 372; Top := TopPos; Caption := 'BitBtn'; Width := 90; Height := 30; Kind := bkOK; end;
  TopPos := TopPos + 50;

  AddSectionLabel('TEdit - Normal / Small / Large / ReadOnly / Password', TopPos, sc);
  with TEdit.Create(sc) do begin Parent := sc; Left := 8; Top := TopPos; Text := 'Normal'; Width := 120; end;
  with TEdit.Create(sc) do begin Parent := sc; Left := 136; Top := TopPos + 2; Text := 'Small'; Width := 80; Height := 18; Font.Size := 9; end;
  with TEdit.Create(sc) do begin Parent := sc; Left := 224; Top := TopPos - 2; Text := 'Large'; Width := 180; Height := 28; Font.Size := 14; end;
  with TEdit.Create(sc) do begin Parent := sc; Left := 412; Top := TopPos; Text := 'ReadOnly'; Width := 120; ReadOnly := True; Color := clBtnFace; end;
  with TEdit.Create(sc) do begin Parent := sc; Left := 540; Top := TopPos; Text := 'pwd'; Width := 100; PasswordChar := '*'; end;
  TopPos := TopPos + 34;

  AddSectionLabel('TCheckBox - Normal / Checked / Disabled / Disabled+Checked', TopPos, sc);
  with TCheckBox.Create(sc) do begin Parent := sc; Left := 8; Top := TopPos; Caption := 'Enable'; end;
  with TCheckBox.Create(sc) do begin Parent := sc; Left := 116; Top := TopPos; Caption := 'Checked'; Checked := True; end;
  with TCheckBox.Create(sc) do begin Parent := sc; Left := 224; Top := TopPos; Caption := 'Disable'; Enabled := False; end;
  with TCheckBox.Create(sc) do begin Parent := sc; Left := 332; Top := TopPos; Caption := 'Dis+Chk'; Enabled := False; Checked := True; end;
  TopPos := TopPos + 22;

  AddSectionLabel('TComboBox / TListBox', TopPos, sc);
  var cb := TComboBox.Create(sc);
  cb.Parent := sc; cb.Left := 8; cb.Top := TopPos; cb.Width := 140;
  cb.Items.AddStrings(['Item 1','Item 2','Item 3']); cb.ItemIndex := 0;
  var lb := TListBox.Create(sc);
  lb.Parent := sc; lb.Left := 156; lb.Top := TopPos; lb.Width := 120; lb.Height := 70;
  lb.Items.AddStrings(['Row A','Row B','Row C','Row D']); lb.ItemIndex := 1;
  TopPos := TopPos + 76;

  AddSectionLabel('TCheckListBox - 1 col / 2 cols', TopPos, sc);
  var clb1 := TCheckListBox.Create(sc);
  clb1.Parent := sc; clb1.Left := 8; clb1.Top := TopPos; clb1.Width := 100; clb1.Height := 80;
  clb1.Items.AddStrings(['A','B','C','D']); clb1.Checked[0] := True;
  var clb2 := TCheckListBox.Create(sc);
  clb2.Parent := sc; clb2.Left := 116; clb2.Top := TopPos; clb2.Width := 180; clb2.Height := 80;
  clb2.Columns := 2;
  clb2.Items.AddStrings(['Opt 1','Opt 2','Opt 3','Opt 4','Opt 5','Opt 6']); clb2.Checked[1] := True; clb2.Checked[3] := True;
  TopPos := TopPos + 86;

  AddSectionLabel('TRadioGroup - 1 col / 2 cols / 3 cols', TopPos, sc);
  var rg1 := TRadioGroup.Create(sc);
  rg1.Parent := sc; rg1.Left := 8; rg1.Top := TopPos; rg1.Width := 100; rg1.Height := 90;
  rg1.Caption := 'Single'; rg1.Items.AddStrings(['One','Two','Three']); rg1.ItemIndex := 1;
  var rg2 := TRadioGroup.Create(sc);
  rg2.Parent := sc; rg2.Left := 116; rg2.Top := TopPos; rg2.Width := 160; rg2.Height := 90;
  rg2.Caption := '2 Cols'; rg2.Columns := 2;
  rg2.Items.AddStrings(['1','2','3','4']); rg2.ItemIndex := 0;
  var rg3 := TRadioGroup.Create(sc);
  rg3.Parent := sc; rg3.Left := 284; rg3.Top := TopPos; rg3.Width := 220; rg3.Height := 90;
  rg3.Caption := '3 Cols'; rg3.Columns := 3;
  rg3.Items.AddStrings(['A','B','C','D','E','F']); rg3.ItemIndex := 2;
  TopPos := TopPos + 96;

  AddSectionLabel('TGroupBox / TPanel variants', TopPos, sc);
  with TGroupBox.Create(sc) do begin Parent := sc; Left := 8; Top := TopPos; Width := 160; Height := 64; Caption := 'Group'; end;
  with TPanel.Create(sc) do begin Parent := sc; Left := 176; Top := TopPos; Width := 80; Height := 64; BevelOuter := bvRaised; Caption := 'Raised'; end;
  with TPanel.Create(sc) do begin Parent := sc; Left := 264; Top := TopPos; Width := 80; Height := 64; BevelOuter := bvLowered; Caption := 'Low'; end;
  with TPanel.Create(sc) do begin Parent := sc; Left := 352; Top := TopPos; Width := 80; Height := 64; BevelOuter := bvNone; BorderStyle := bsSingle; Caption := 'Bdr'; end;
  TopPos := TopPos + 70;

  AddSectionLabel('TMemo / TListView / TTreeView', TopPos, sc);
  with TMemo.Create(sc) do begin Parent := sc; Left := 8; Top := TopPos; Width := 140; Height := 70; Lines.Text := 'Memo'#13#10'Line 2'; end;
  var lv := TListView.Create(sc);
  lv.Parent := sc; lv.Left := 156; lv.Top := TopPos; lv.Width := 140; lv.Height := 70;
  lv.ViewStyle := vsReport;
  lv.Columns.Add; lv.Columns[0].Caption := 'Name'; lv.Columns[0].Width := 100;
  lv.Items.Add.Caption := 'File A'; lv.Items.Add.Caption := 'File B';
  with TTreeView.Create(sc) do begin Parent := sc; Left := 304; Top := TopPos; Width := 130; Height := 70;
    Items.Add(nil, 'Root'); Items.AddChild(Items[0], 'Child 1'); Items.AddChild(Items[0], 'Child 2'); end;
  TopPos := TopPos + 76;

  AddSectionLabel('TStringGrid', TopPos, sc);
  var sg := TStringGrid.Create(sc);
  sg.Parent := sc; sg.Left := 8; sg.Top := TopPos; sg.Width := 240; sg.Height := 76;
  sg.ColCount := 4; sg.RowCount := 3; sg.FixedCols := 0;
  sg.Cells[0,0] := '#';

  AddSectionLabel('TProgressBar / TTrackBar / TScrollBar', TopPos, sc);
  with TProgressBar.Create(sc) do begin Parent := sc; Left := 8; Top := TopPos; Width := 200; Height := 20; Position := 65; end;
  with TTrackBar.Create(sc) do begin Parent := sc; Left := 8; Top := TopPos + 24; Width := 200; Height := 30; Position := 50; end;
  with TScrollBar.Create(sc) do begin Parent := sc; Left := 8; Top := TopPos + 56; Width := 200; Height := 18; Position := 30; end;

  // TToolBar with buttons
  with TToolBar.Create(sc) do begin Parent := sc; Left := 8; Top := TopPos + 80; Width := 300;
    with TToolButton.Create(AParent.Owner) do begin Parent := sc; Caption := 'New'; end;
    with TToolButton.Create(AParent.Owner) do begin Parent := sc; Caption := 'Open'; end;
    with TToolButton.Create(AParent.Owner) do begin Parent := sc; Caption := 'Save'; Enabled := False; end;
  end;
end;

procedure TMainForm.FormCreate(Sender: TObject);
begin
  // 启动 DaofyAutomation 管道（默认 \\.\pipe\daofy_auto）
  AutoStart;

  // 初始化控件状态
  btnDisabled.Enabled := False;
  edtReadOnly.ReadOnly := True;
  edtReadOnly.Text := '只读文本内容';
  chkDisabled.Enabled := False;
  btnHidden.Visible := False;

  // 填充 ComboBox
  cmbCity.Items.AddStrings(['北京', '上海', '广州', '深圳', '杭州']);
  cmbCity.ItemIndex := 0;

  // 填充 ListBox
  lstItems.Items.AddStrings(['项目 A', '项目 B', '项目 C', '项目 D']);
  lstItems.ItemIndex := 0;

  // 填充 CheckListBox
  clbOptions.Items.AddStrings(['选项 1', '选项 2', '选项 3', '选项 4']);
  clbOptions.Checked[0] := True;
  clbOptions.Checked[2] := True;

  // 填充 RadioGroup
  rgOptions.Items.AddStrings(['默认', '增强', '最大']);
  rgOptions.ItemIndex := 1;

  // 填充 ListView
  with lvItems.Items.Add do begin Caption := '文件1.txt'; SubItems.Add('12KB'); end;
  with lvItems.Items.Add do begin Caption := '文件2.log'; SubItems.Add('45KB'); end;
  with lvItems.Items.Add do begin Caption := '文件3.dat'; SubItems.Add('128KB'); end;

  // 填充 TreeView
  var RootNode := tvTree.Items.Add(nil, '根节点');
  tvTree.Items.AddChild(RootNode, '子项 1');
  tvTree.Items.AddChild(RootNode, '子项 2');

  // 初始化 StringGrid
  sgData.Cells[0, 0] := '编号';
  sgData.Cells[1, 0] := '名称';
  sgData.Cells[2, 0] := '状态';
  sgData.Cells[0, 1] := '001';
  sgData.Cells[1, 1] := '测试数据 A';
  sgData.Cells[2, 1] := '进行中';
  sgData.Cells[0, 2] := '002';
  sgData.Cells[1, 2] := '测试数据 B';
  sgData.Cells[2, 2] := '已完成';
  sgData.Cells[0, 3] := '003';
  sgData.Cells[1, 3] := '测试数据 C';
  sgData.Cells[2, 3] := '待审核';

  // 状态栏
  statBar.SimpleText := '就绪 | 共 20+ 控件 | Daofy 训练采集';

  // 进度条
  pbProgress.Position := 65;

  // TrackBar
  tbVolume.Position := 75;

  // -- Create Catalog tab --
  var tsCat := TTabSheet.Create(Self);
  tsCat.PageControl := pcMain;
  tsCat.Caption := 'Catalog';
  BuildCatalogTab(tsCat);
end;
procedure TMainForm.FormDestroy(Sender: TObject);
begin
  AutoStop;
end;

procedure TMainForm.btnOKClick(Sender: TObject);
begin
  ShowMessage('按钮点击测试');
end;

{ ──────────── YOLO 训练数据自动采集 ──────────── }

const
  // Delphi 控件名 → YOLO class_id
  CLASS_IDS: array[0..24] of record Name: string; Id: Integer; end = (
    (Name: 'TButton';       Id: 0), (Name: 'TBitBtn';      Id: 0),
    (Name: 'TSpeedButton';  Id: 0), (Name: 'TEdit';        Id: 1),
    (Name: 'TSpinEdit';     Id: 1), (Name: 'TLabel';       Id: 2),
    (Name: 'TComboBox';     Id: 3), (Name: 'TCheckBox';    Id: 4),
    (Name: 'TRadioButton';  Id: 5), (Name: 'TListBox';     Id: 6),
    (Name: 'TCheckListBox'; Id: 6), (Name: 'TPanel';       Id: 7),
    (Name: 'TGroupBox';     Id: 8), (Name: 'TRadioGroup';  Id: 8),
    (Name: 'TPageControl';  Id: 9), (Name: 'TTabSheet';    Id: 10),
    (Name: 'TStringGrid';   Id: 11), (Name: 'TMemo';       Id: 12),
    (Name: 'TListView';     Id: 13), (Name: 'TTreeView';   Id: 14),
    (Name: 'TProgressBar';  Id: 15), (Name: 'TTrackBar';   Id: 16),
    (Name: 'TScrollBar';    Id: 17), (Name: 'TScrollBox';  Id: 18),
    (Name: 'TStatusBar';    Id: 19)
  );

function GetClassId(const AClassName: string): Integer;
begin
  for var Item in CLASS_IDS do
    if Item.Name = AClassName then
      Exit(Item.Id);
  Result := -1;
end;


procedure TMainForm.CaptureCurrentState(const AIndex: Integer; const AVariantName: string);
var
  OutputDir, ImagesDir, LabelsDir: string;
  ImgName, TxtName: string;
  Bmp: Vcl.Graphics.TBitmap;
  Labels: TArray<string>;
  S: TStringList;
begin
  OutputDir := ExtractFilePath(Application.ExeName) + '..\..\..\dataset\';
  ImagesDir := OutputDir + 'images\';
  LabelsDir := OutputDir + 'labels\';
  ForceDirectories(ImagesDir);
  ForceDirectories(LabelsDir);

  ImgName := Format('train_%.3d_%s.png', [AIndex, AVariantName]);
  TxtName := Format('train_%.3d_%s.txt', [AIndex, AVariantName]);

  // 截图 - Catalog tab 需要放大表单
  var SavedH: Integer := 0;
  if (pcMain.ActivePage <> nil) and (pcMain.ActivePage.Caption = 'Catalog') then
  begin
    SavedH := Self.ClientHeight;
    Self.ClientHeight := 1200;
    Application.ProcessMessages;
    Sleep(150);
  end;

  Bmp := Self.GetFormImage;
  try
    Bmp.SaveToFile(ImagesDir + ImgName);
  finally
    Bmp.Free;
  end;

  if SavedH > 0 then
    Self.ClientHeight := SavedH;
  // 生成 YOLO 标签
  Labels := ControlsToYoloLabel;
  if Length(Labels) = 0 then
    Exit;

  S := TStringList.Create;
  try
    for var L in Labels do
      S.Add(L);
    S.WriteBOM:=false;
    S.SaveToFile(LabelsDir + TxtName, TEncoding.UTF8);
  finally
    S.Free;
  end;

  statBar.SimpleText := Format('[%d] %s: %d labels', [AIndex, AVariantName, Length(Labels)]);
  Application.ProcessMessages;
end;


function TMainForm.ControlsToYoloLabel: TArray<string>;

  procedure CollectRecursive(Parent: TWinControl; var List: TStringList; FW, FH: Single);
  var
    I: Integer;
    Ctrl: TControl;
    Cid: Integer;
    XC, YC, NW, NH: Single;
  begin
    for I := 0 to Parent.ControlCount - 1 do
    begin
      Ctrl := Parent.Controls[I];
      if not Ctrl.Visible then
        Continue;

      Cid := GetClassId(Ctrl.ClassName);
      if Cid >= 0 then
      begin
        XC := (Ctrl.Left + Ctrl.Width / 2) / FW;
        YC := (Ctrl.Top + Ctrl.Height / 2) / FH;
        NW := Ctrl.Width / FW;
        NH := Ctrl.Height / FH;

        if XC < 0.0 then XC := 0.0 else if XC > 1.0 then XC := 1.0;
        if YC < 0.0 then YC := 0.0 else if YC > 1.0 then YC := 1.0;
        if NW < 0.0 then NW := 0.0 else if NW > 1.0 then NW := 1.0;
        if NH < 0.0 then NH := 0.0 else if NH > 1.0 then NH := 1.0;

        List.Add(Format('%d %.6f %.6f %.6f %.6f', [Cid, XC, YC, NW, NH]));
      end;

      if Ctrl is TWinControl then
        CollectRecursive(TWinControl(Ctrl), List, FW, FH);
    end;
  end;

var
  FW, FH: Single;
  ResultList: TStringList;
begin
  FW := Self.ClientWidth;
  FH := Self.ClientHeight;
  if (FW <= 0) or (FH <= 0) then
  begin
    Result := nil;
    Exit;
  end;

  ResultList := TStringList.Create;
  try
    CollectRecursive(Self, ResultList, FW, FH);
    Result := ResultList.ToStringArray;
  finally
    ResultList.Free;
  end;
end;



procedure TMainForm.btnAutoCollectClick(Sender: TObject);
var
  I, ImgIdx: Integer;
  SavedTab: Integer;
  VarName: string;
begin
  ImgIdx := 0;
  SavedTab := pcMain.ActivePageIndex;
  btnAutoCollect.Enabled := False;
  try
    for var T := 0 to High(TStyleManager.StyleNames) do
    begin
      TStyleManager.TrySetStyle(TStyleManager.StyleNames[T], False);
      statBar.SimpleText := Format('Theme %d - Capturing...', [T]);
      for I := 0 to pcMain.PageCount - 1 do
      begin
        pcMain.ActivePageIndex := I;
        Update;
        Application.ProcessMessages;
        // 默认状态
        CaptureCurrentState(ImgIdx, 'default');
        Inc(ImgIdx);
        // 变异 1: 禁用按钮
        btnDisabled.Enabled := False;
        chkDisabled.Enabled := False;
        CaptureCurrentState(ImgIdx, 'disabled');
        Inc(ImgIdx);
        // 恢复默认
        btnDisabled.Enabled := True;
        chkDisabled.Enabled := True;
      end;
    end;

    btnAutoCollect.Enabled := True;
    statBar.SimpleText := Format('采集完成: %d 张图片', [ImgIdx]);
  except
    on E: Exception do
      ShowMessage('采集失败: ' + E.Message);
  end;
  pcMain.ActivePageIndex := SavedTab;
  btnAutoCollect.Enabled := True;
end;

end.
