#!/usr/bin/env python3
"""Rebuild TrainApp with single-page catalog layout."""
import re

PAS = 'training/TrainApp/UMainForm.pas'

with open(PAS, 'rb') as f:
    content = f.read()

# 1. Add Catalog tab to DFM - we'll add it programmatically in FormCreate
# We need a TTabSheet slot. The existing DFM has tsBasic, tsAdvanced, tsData.
# We'll create tsCatalog dynamically, but we need to add it to the DFM or create in code.

# Actually, let's add the catalog tab programmatically in FormCreate
# Find the end of FormCreate to add tab creation code

# Find the marker for where to insert catalog code
# The last line of FormCreate is: tbVolume.Position := 75;
# Then the dynamic controls code was added after.

# Let's replace the entire FormCreate end section
old_end = b'''  tbVolume.Position := 75;

  // -- create extra controls programmatically --'''

# We'll replace from after TrackBar initialization through the end of the 
# dynamic controls section
new_catalog = b'''  tbVolume.Position := 75;

  // ===== Catalog tab: each control type in multiple variants =====
  var tsCatalog := TTabSheet.Create(Self);
  tsCatalog.PageControl := pcMain;
  tsCatalog.Caption := 'Catalog';
  tsCatalog.TabVisible := True;

  var scCatalog := TScrollBox.Create(Self);
  scCatalog.Parent := tsCatalog;
  scCatalog.Align := alClient;

  var TopPos: Integer := 8;
  var Gap: Integer := 8;

  // --- helper to create section label ---
  procedure AddSectionLabel(const ACaption: string; var Y: Integer);
  var L: TLabel;
  begin
    L := TLabel.Create(Self);
    L.Parent := scCatalog;
    L.Caption := ACaption;
    L.Font.Style := [fsBold];
    L.Font.Size := 11;
    L.Top := Y;
    L.Left := 8;
    Y := Y + 24;
  end;

  // --- TButton ---
  AddSectionLabel('TButton - Normal / Small / Disabled / Large / BitBtn', TopPos);
  with TButton.Create(Self) do begin Parent := scCatalog; Left := 8; Top := TopPos; Caption := 'OK(O)'; Width := 80; Height := 30; end;
  with TButton.Create(Self) do begin Parent := scCatalog; Left := 96; Top := TopPos + 4; Caption := 'Small'; Width := 50; Height := 22; end;
  with TButton.Create(Self) do begin Parent := scCatalog; Left := 154; Top := TopPos; Caption := 'Disabled'; Width := 80; Height := 30; Enabled := False; end;
  with TButton.Create(Self) do begin Parent := scCatalog; Left := 242; Top := TopPos - 6; Caption := 'Large'; Width := 120; Height := 42; end;
  with TBitBtn.Create(Self) do begin Parent := scCatalog; Left := 370; Top := TopPos; Caption := 'BitBtn'; Width := 90; Height := 30; Kind := bkOK; end;
  TopPos := TopPos + 50;

  // --- TEdit ---
  AddSectionLabel('TEdit - Normal / Small / Large / ReadOnly / Password', TopPos);
  with TEdit.Create(Self) do begin Parent := scCatalog; Left := 8; Top := TopPos; Text := 'Normal'; Width := 120; end;
  with TEdit.Create(Self) do begin Parent := scCatalog; Left := 136; Top := TopPos + 2; Text := 'Small'; Width := 80; Height := 18; Font.Size := 9; end;
  with TEdit.Create(Self) do begin Parent := scCatalog; Left := 224; Top := TopPos - 2; Text := 'Large'; Width := 180; Height := 28; Font.Size := 14; end;
  with TEdit.Create(Self) do begin Parent := scCatalog; Left := 412; Top := TopPos; Text := 'ReadOnly'; Width := 120; ReadOnly := True; Color := clBtnFace; end;
  with TEdit.Create(Self) do begin Parent := scCatalog; Left := 540; Top := TopPos; Text := 'pwd'; Width := 100; PasswordChar := '*'; end;
  TopPos := TopPos + 34;

  // --- TCheckBox ---
  AddSectionLabel('TCheckBox - Normal / Checked / Disabled / Disabled+Checked', TopPos);
  with TCheckBox.Create(Self) do begin Parent := scCatalog; Left := 8; Top := TopPos; Caption := 'Enable'; Width := 100; end;
  with TCheckBox.Create(Self) do begin Parent := scCatalog; Left := 116; Top := TopPos; Caption := 'Checked'; Width := 100; Checked := True; end;
  with TCheckBox.Create(Self) do begin Parent := scCatalog; Left := 224; Top := TopPos; Caption := 'Disabled'; Width := 100; Enabled := False; end;
  with TCheckBox.Create(Self) do begin Parent := scCatalog; Left := 332; Top := TopPos; Caption := 'Dis+Chk'; Width := 100; Enabled := False; Checked := True; end;
  TopPos := TopPos + 22;

  // --- TRadioButton ---
  AddSectionLabel('TRadioButton - Horizontal row', TopPos);
  with TRadioButton.Create(Self) do begin Parent := scCatalog; Left := 8; Top := TopPos; Caption := 'Option A'; Checked := True; end;
  with TRadioButton.Create(Self) do begin Parent := scCatalog; Left := 90; Top := TopPos; Caption := 'Option B'; end;
  with TRadioButton.Create(Self) do begin Parent := scCatalog; Left := 180; Top := TopPos; Caption := 'Option C'; end;
  TopPos := TopPos + 22;

  // --- TComboBox ---
  AddSectionLabel('TComboBox - Normal / Wide / With selection', TopPos);
  var cb1 := TComboBox.Create(Self);
  cb1.Parent := scCatalog; cb1.Left := 8; cb1.Top := TopPos; cb1.Width := 120;
  cb1.Items.AddStrings(['Item 1','Item 2','Item 3']); cb1.ItemIndex := 0;
  var cb2 := TComboBox.Create(Self);
  cb2.Parent := scCatalog; cb2.Left := 136; cb2.Top := TopPos; cb2.Width := 220;
  cb2.Items.AddStrings(['Long Item Name A','Long Item Name B','Long Item Name C']); cb2.ItemIndex := 1;
  TopPos := TopPos + 26;

  // --- TListBox ---
  AddSectionLabel('TListBox - Normal / Tall', TopPos);
  var lb1 := TListBox.Create(Self);
  lb1.Parent := scCatalog; lb1.Left := 8; lb1.Top := TopPos; lb1.Width := 120; lb1.Height := 60;
  lb1.Items.AddStrings(['Row 1','Row 2','Row 3','Row 4']); lb1.ItemIndex := 1;
  var lb2 := TListBox.Create(Self);
  lb2.Parent := scCatalog; lb2.Left := 136; lb2.Top := TopPos; lb2.Width := 120; lb2.Height := 90;
  lb2.Items.AddStrings(['Long Row 1','Long Row 2','Long Row 3','Long Row 4','Long Row 5']);
  TopPos := TopPos + 96;

  // --- TCheckListBox single vs multi-column ---
  AddSectionLabel('TCheckListBox - Single column / 2 columns', TopPos);
  var clb1 := TCheckListBox.Create(Self);
  clb1.Parent := scCatalog; clb1.Left := 8; clb1.Top := TopPos; clb1.Width := 120; clb1.Height := 80;
  clb1.Items.AddStrings(['Opt 1','Opt 2','Opt 3','Opt 4']); clb1.Checked[0] := True; clb1.Checked[2] := True;
  var clb2 := TCheckListBox.Create(Self);
  clb2.Parent := scCatalog; clb2.Left := 136; clb2.Top := TopPos; clb2.Width := 200; clb2.Height := 80;
  clb2.Columns := 2;
  clb2.Items.AddStrings(['A','B','C','D','E','F']); clb2.Checked[0] := True; clb2.Checked[3] := True;
  TopPos := TopPos + 86;

  // --- TRadioGroup single vs multi-column ---
  AddSectionLabel('TRadioGroup - 1 column / 2 columns / 3 columns', TopPos);
  var rg1 := TRadioGroup.Create(Self);
  rg1.Parent := scCatalog; rg1.Left := 8; rg1.Top := TopPos; rg1.Width := 120; rg1.Height := 90;
  rg1.Caption := 'Single'; rg1.Items.AddStrings(['One','Two','Three']); rg1.ItemIndex := 1;
  var rg2 := TRadioGroup.Create(Self);
  rg2.Parent := scCatalog; rg2.Left := 136; rg2.Top := TopPos; rg2.Width := 180; rg2.Height := 90;
  rg2.Caption := '2 Cols'; rg2.Columns := 2;
  rg2.Items.AddStrings(['1','2','3','4']); rg2.ItemIndex := 0;
  var rg3 := TRadioGroup.Create(Self);
  rg3.Parent := scCatalog; rg3.Left := 324; rg3.Top := TopPos; rg3.Width := 240; rg3.Height := 90;
  rg3.Caption := '3 Cols'; rg3.Columns := 3;
  rg3.Items.AddStrings(['A','B','C','D','E','F']); rg3.ItemIndex := 2;
  TopPos := TopPos + 96;

  // --- TGroupBox ---
  AddSectionLabel('TGroupBox - Normal / With different caption', TopPos);
  var gb1 := TGroupBox.Create(Self);
  gb1.Parent := scCatalog; gb1.Left := 8; gb1.Top := TopPos; gb1.Width := 180; gb1.Height := 70;
  gb1.Caption := 'Group Box';
  var gb2 := TGroupBox.Create(Self);
  gb2.Parent := scCatalog; gb2.Left := 196; gb2.Top := TopPos; gb2.Width := 220; gb2.Height := 70;
  gb2.Caption := 'Longer Caption Here';
  TopPos := TopPos + 76;

  // --- TMemo ---
  AddSectionLabel('TMemo - Small / Large', TopPos);
  with TMemo.Create(Self) do begin Parent := scCatalog; Left := 8; Top := TopPos; Width := 180; Height := 60;
    Lines.Text := 'Small memo'#13#10'Line 2'; end;
  with TMemo.Create(Self) do begin Parent := scCatalog; Left := 196; Top := TopPos; Width := 280; Height := 80;
    Lines.Text := 'Large memo with more text'#13#10'Line 2'#13#10'Line 3'; end;
  TopPos := TopPos + 86;

  // --- TListView ---
  AddSectionLabel('TListView - Report / List / Small icons', TopPos);
  var lv1 := TListView.Create(Self);
  lv1.Parent := scCatalog; lv1.Left := 8; lv1.Top := TopPos; lv1.Width := 180; lv1.Height := 80;
  lv1.ViewStyle := vsReport;
  lv1.Columns.Add; lv1.Columns[0].Caption := 'Name'; lv1.Columns[0].Width := 100;
  lv1.Items.Add.Caption := 'File1.txt';
  lv1.Items.Add.Caption := 'File2.log';
  var lv2 := TListView.Create(Self);
  lv2.Parent := scCatalog; lv2.Left := 196; lv2.Top := TopPos; lv2.Width := 140; lv2.Height := 80;
  lv2.ViewStyle := vsList;
  lv2.Items.Add.Caption := 'Item A';
  lv2.Items.Add.Caption := 'Item B';
  lv2.Items.Add.Caption := 'Item C';
  TopPos := TopPos + 86;

  // --- TTreeView ---
  AddSectionLabel('TTreeView', TopPos);
  var tv1 := TTreeView.Create(Self);
  tv1.Parent := scCatalog; tv1.Left := 8; tv1.Top := TopPos; tv1.Width := 160; tv1.Height := 80;
  var tvRoot := tv1.Items.Add(nil, 'Root');
  tv1.Items.AddChild(tvRoot, 'Child 1');
  tv1.Items.AddChild(tvRoot, 'Child 2');
  tv1.Items.AddChild(tvRoot, 'Child 3');
  TopPos := TopPos + 86;

  // --- TStringGrid ---
  AddSectionLabel('TStringGrid - 3 cols / 5 cols', TopPos);
  var sg1 := TStringGrid.Create(Self);
  sg1.Parent := scCatalog; sg1.Left := 8; sg1.Top := TopPos; sg1.Width := 200; sg1.Height := 80;
  sg1.ColCount := 3; sg1.RowCount := 3; sg1.FixedCols := 0;
  sg1.Cells[0,0] := 'ID'; sg1.Cells[1,0] := 'Name'; sg1.Cells[2,0] := 'Status';
  sg1.Cells[0,1] := '1'; sg1.Cells[1,1] := 'Alpha'; sg1.Cells[2,1] := 'OK';
  TopPos := TopPos + 86;

  // --- TProgressBar / TTrackBar / TScrollBar ---
  AddSectionLabel('TProgressBar / TTrackBar / TScrollBar', TopPos);
  with TProgressBar.Create(Self) do begin Parent := scCatalog; Left := 8; Top := TopPos; Width := 200; Height := 20; Position := 65; end;
  with TTrackBar.Create(Self) do begin Parent := scCatalog; Left := 8; Top := TopPos + 24; Width := 200; Height := 30; Position := 50; end;
  with TScrollBar.Create(Self) do begin Parent := scCatalog; Left := 8; Top := TopPos + 56; Width := 200; Height := 18; Position := 30; end;
  TopPos := TopPos + 80;

  // --- TPanel - Bevel variations ---
  AddSectionLabel('TPanel - Raised / Lowered / None / Border', TopPos);
  with TPanel.Create(Self) do begin Parent := scCatalog; Left := 8; Top := TopPos; Width := 100; Height := 60; BevelOuter := bvRaised; Caption := 'Raised'; end;
  with TPanel.Create(Self) do begin Parent := scCatalog; Left := 116; Top := TopPos; Width := 100; Height := 60; BevelOuter := bvLowered; Caption := 'Lowered'; end;
  with TPanel.Create(Self) do begin Parent := scCatalog; Left := 224; Top := TopPos; Width := 100; Height := 60; BevelOuter := bvNone; BorderStyle := bsSingle; Caption := 'Border'; end;
  with TPanel.Create(Self) do begin Parent := scCatalog; Left := 332; Top := TopPos; Width := 120; Height := 60; BevelOuter := bvNone; Caption := 'Flat'; end;
  TopPos := TopPos + 66;

  // --- HeaderControl (for column header style) ---
  AddSectionLabel('THeaderControl', TopPos);
  var hc := THeaderControl.Create(Self);
  hc.Parent := scCatalog; hc.Left := 8; hc.Top := TopPos; hc.Width := 400;
  with hc.Sections.Add do begin Text := 'Column 1'; Width := 120; end;
  with hc.Sections.Add do begin Text := 'Column 2'; Width := 120; end;
  with hc.Sections.Add do begin Text := 'Column 3'; Width := 120; end;
  TopPos := TopPos + 24;

  // --- TToolBar ---
  AddSectionLabel('TToolBar with TToolButtons', TopPos);
  var tb := TToolBar.Create(Self);
  tb.Parent := scCatalog; tb.Left := 8; tb.Top := TopPos; tb.Width := 350;
  with TToolButton.Create(Self) do begin Parent := tb; Caption := 'New'; end;
  with TToolButton.Create(Self) do begin Parent := tb; Caption := 'Open'; end;
  with TToolButton.Create(Self) do begin Parent := tb; Caption := 'Save'; end;
  with TToolButton.Create(Self) do begin Parent := tb; Style := tbsSeparator; Width := 8; end;
  with TToolButton.Create(Self) do begin Parent := tb; Caption := 'Delete'; Enabled := False; end;
  TopPos := TopPos + 30;

  // --- TUpDown ---
  AddSectionLabel('TUpDown', TopPos);
  with TUpDown.Create(Self) do begin Parent := scCatalog; Left := 8; Top := TopPos; Min := 0; Max := 100; Position := 50; Width := 20; Height := 24; end;
  TopPos := TopPos + 30;
'''

# Find and replace the old FormCreate ending
idx = content.find(old_end)
if idx < 0:
    print('ERROR: old marker not found')
    exit(1)
    
content = content[:idx] + new_catalog + content[idx + len(old_end):]

# Now update AutoCollect to use Catalog tab (index 3) as the main capture target
# Instead of iterating tabs, just activate Catalog and capture with different themes

old_ac = b'    for I := 0 to pcMain.PageCount - 1 do'
new_ac = b'''    // Catalog tab is at index 3 - capture it with theme/size variations
    pcMain.ActivePageIndex := I;
    // (the old tab loop still works, but Catalog tab provides richer data)
    for I := 0 to pcMain.PageCount - 1 do'''

content = content.replace(old_ac, new_ac, 1)

with open(PAS, 'wb') as f:
    f.write(content)
print('Catalog tab added successfully')
print(f'File size: {len(content)} bytes')
