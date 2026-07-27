"""Apply catalog tab and theme switching to PAS file."""
import re

PAS = 'training/TrainApp/UMainForm.pas'

with open(PAS, 'rb') as f:
    content = f.read()

# 1. Add Vcl.Themes to implementation uses
old_uses = b'Vcl.DaofyAutomation;'
new_uses = b'Vcl.Themes, Vcl.Styles,\r\n  Vcl.DaofyAutomation;'
content = content.replace(old_uses, new_uses)

# 2. Add theme constants and catalog procedure declarations before implementation
# Find a good place - before 'procedure TMainForm.FormCreate'
marker = b'procedure TMainForm.FormCreate(Sender: TObject);'

new_decls = b'''
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
    with TToolButton.Create(Self) do begin Parent := sc; Caption := 'New'; end;
    with TToolButton.Create(Self) do begin Parent := sc; Caption := 'Open'; end;
    with TToolButton.Create(Self) do begin Parent := sc; Caption := 'Save'; Enabled := False; end;
  end;
end;

'''

# Insert new_decls before FormCreate
idx = content.find(marker)
if idx > 0:
    content = content[:idx] + new_decls + content[idx:]
    print('Inserted catalog procedures before FormCreate')
else:
    print('ERROR: marker not found')

# 3. Add catalog tab creation at the END of FormCreate (before its final end;)
# Find the last 'end;' of FormCreate
# We know FormCreate ends with tbVolume.Position := 75; end;
# Then the new catalog code is inserted

# Actually, the marker to find: the end of FormCreate procedure
end_marker = b'tbVolume.Position := 75;\r\nend;'
catalog_code = b'''
  // -- Create Catalog tab --
  var tsCat := TTabSheet.Create(Self);
  tsCat.PageControl := pcMain;
  tsCat.Caption := 'Catalog';
  BuildCatalogTab(tsCat);
'''

idx = content.find(end_marker)
if idx > 0:
    content = content[:idx + len(end_marker) - 4] + catalog_code + content[idx + len(end_marker) - 4:]
    print('Added catalog tab creation to FormCreate')
else:
    print('ERROR: end marker not found')

# 4. Modify AutoCollect to use themes
old_ac_start = b'  ImgIdx := 0;\r\n  SavedTab := pcMain.ActivePageIndex;\r\n  btnAutoCollect.Enabled := False;\r\n  try'
new_ac_start = b'''  ImgIdx := 0;
  SavedTab := pcMain.ActivePageIndex;
  btnAutoCollect.Enabled := False;
  try
    for var T := 0 to 4 do
    begin
      case T of
        0: TStyleManager.TrySetStyle('Windows', False);
        1: TStyleManager.TrySetStyle('Windows10', False);
        2: TStyleManager.TrySetStyle('Carbon', False);
        3: TStyleManager.TrySetStyle('Amakrits', False);
        4: TStyleManager.TrySetStyle('Cobalt XEM', False);
      end;
      Sleep(300);
      statBar.SimpleText := Format('Theme %d - Capturing...', [T]);'''

content = content.replace(old_ac_start, new_ac_start)

# 5. Close the theme loop after the tab loop ends
# Find the end of the main loop: after 'end;' (end of for I) then 'end' (end of try)
old_loop_end = b'      cmbCity.ItemIndex := 0;\r\n    end;\r\n\r\n    statBar.SimpleText := Format'
new_loop_end = b'''      cmbCity.ItemIndex := 0;
    end;
    end;  // end theme loop

    // restore default theme
    TStyleManager.TrySetStyle('Windows', False);
    statBar.SimpleText := Format'''

content = content.replace(old_loop_end, new_loop_end)

with open(PAS, 'wb') as f:
    f.write(content)
print('All changes applied successfully')
