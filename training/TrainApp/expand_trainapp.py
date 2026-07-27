#!/usr/bin/env python3
"""Expand TrainApp with theme switching and size variations."""
import os

DIR = os.path.dirname(os.path.abspath(__file__))
PAS_PATH = os.path.join(DIR, 'UMainForm.pas')

with open(PAS_PATH, 'rb') as f:
    content = f.read()

# 1. Add Vcl.Themes to uses
old_uses = b'uses\r\n  Vcl.DaofyAutomation;\r\n'
new_uses = b'uses\r\n  Vcl.Themes, Vcl.Styles,\r\n  Vcl.DaofyAutomation;\r\n'
if old_uses in content:
    content = content.replace(old_uses, new_uses)
    print('1. Added Vcl.Themes to uses')
else:
    print('1. SKIP: uses not found')

# 2. Find and replace btnAutoCollectClick
marker_start = b'procedure TMainForm.btnAutoCollectClick(Sender: TObject);'

# Find where the function ends - look for 'end.' at file end
idx_start = content.find(marker_start)
idx_end_file = content.rfind(b'end.')
# Find the last 'end;\r\n' before 'end.'
idx_func_end = content.rfind(b'end;\r\n', 0, idx_end_file)
if idx_func_end < 0:
    idx_func_end = content.rfind(b'end;', 0, idx_end_file)

if idx_start < 0 or idx_func_end < 0:
    print(f'ERROR: markers not found. start={idx_start}, func_end={idx_func_end}')
else:
    new_func = (
        b'procedure TMainForm.btnAutoCollectClick(Sender: TObject);\r\n'
        b'const\r\n'
        b'  THEME_NAMES: array[0..4] of string = (\r\n'
        b"    'Windows', 'Windows10', 'Carbon', 'Amakrits', 'Cobalt XEM');\r\n"
        b'var\r\n'
        b'  T, I, ImgIdx: Integer;\r\n'
        b'  SavedTab: Integer;\r\n'
        b'  ThemeName: string;\r\n'
        b'\r\n'
        b'  procedure Snap(const AVarName: string);\r\n'
        b'  begin\r\n'
        b'    Sleep(80);\r\n'
        b'    Application.ProcessMessages;\r\n'
        b'    CaptureCurrentState(ImgIdx, AVarName);\r\n'
        b'    Inc(ImgIdx);\r\n'
        b'  end;\r\n'
        b'\r\n'
        b'  procedure SetCtrlSizes(Mult: Integer);\r\n'
        b'  begin\r\n'
        b'    btnOK.Width := 50 + Mult * 25;  btnOK.Height := 18 + Mult * 10;\r\n'
        b'    btnCancel.Width := 50 + Mult * 25; btnCancel.Height := 18 + Mult * 10;\r\n'
        b'    btnDisabled.Width := 50 + Mult * 25; btnDisabled.Height := 18 + Mult * 10;\r\n'
        b'    btnSmall.Width := 40 + Mult * 20; btnSmall.Height := 16 + Mult * 6;\r\n'
        b'    edtName.Width := 100 + Mult * 40; edtName.Height := 16 + Mult * 6;\r\n'
        b'    chkEnable.Height := 12 + Mult * 5;\r\n'
        b'    cmbCity.Width := 120 + Mult * 30;\r\n'
        b'    lstItems.Width := 120 + Mult * 30;\r\n'
        b'  end;\r\n'
        b'\r\n'
        b'begin\r\n'
        b'  ImgIdx := 0;\r\n'
        b'  SavedTab := pcMain.ActivePageIndex;\r\n'
        b'  btnAutoCollect.Enabled := False;\r\n'
        b'\r\n'
        b'  for T := 0 to High(THEME_NAMES) do\r\n'
        b'  begin\r\n'
        b'    ThemeName := THEME_NAMES[T];\r\n'
        b'    try\r\n'
        b'      TStyleManager.TrySetStyle(ThemeName, False);\r\n'
        b'    except\r\n'
        b'      Continue;\r\n'
        b'    end;\r\n'
        b'    Sleep(300);\r\n'
        b'    statBar.SimpleText := Format(\"Theme: %s [#%d]\", [ThemeName, ImgIdx]);\r\n'
        b'\r\n'
        b'    for I := 0 to pcMain.PageCount - 1 do\r\n'
        b'    begin\r\n'
        b'      pcMain.ActivePageIndex := I;\r\n'
        b'      Application.ProcessMessages;\r\n'
        b'      Sleep(200);\r\n'
        b'\r\n'
        b'      // 3 sizes: small(1), normal(2), large(3)\r\n'
        b'      SetCtrlSizes(1); Snap(ThemeName + \"_s\");\r\n'
        b'      SetCtrlSizes(2); Snap(ThemeName + \"_m\");\r\n'
        b'      SetCtrlSizes(3); Snap(ThemeName + \"_l\");\r\n'
        b'      SetCtrlSizes(2); // restore\r\n'
        b'\r\n'
        b'      // disabled\r\n'
        b'      btnDisabled.Enabled := False;\r\n'
        b'      chkDisabled.Enabled := False;\r\n'
        b'      edtReadOnly.Enabled := False;\r\n'
        b'      Snap(ThemeName + \"_dis\");\r\n'
        b'      btnDisabled.Enabled := True;\r\n'
        b'      chkDisabled.Enabled := True;\r\n'
        b'      edtReadOnly.Enabled := True;\r\n'
        b'\r\n'
        b'      // check toggle\r\n'
        b'      chkEnable.Checked := False;\r\n'
        b'      chkAutoSave.Checked := True;\r\n'
        b'      Snap(ThemeName + \"_chk\");\r\n'
        b'      chkEnable.Checked := True;\r\n'
        b'      chkAutoSave.Checked := False;\r\n'
        b'\r\n'
        b'      // text changed\r\n'
        b'      edtName.Text := \"Alice Wang\";\r\n'
        b'      edtPassword.Text := \"mySecret!\";\r\n'
        b'      Snap(ThemeName + \"_txt\");\r\n'
        b'      edtName.Text := \"Zhang San\";\r\n'
        b'      edtPassword.Text := \"123456\";\r\n'
        b'\r\n'
        b'      // readonly\r\n'
        b'      edtName.ReadOnly := True;\r\n'
        b'      edtName.Color := clBtnFace;\r\n'
        b'      Snap(ThemeName + \"_ro\");\r\n'
        b'      edtName.ReadOnly := False;\r\n'
        b'      edtName.Color := clWindow;\r\n'
        b'\r\n'
        b'      // font large + bold\r\n'
        b'      Self.Font.Size := 14;\r\n'
        b'      Self.Font.Style := [fsBold];\r\n'
        b'      Snap(ThemeName + \"_font\");\r\n'
        b'      Self.Font.Size := 12;\r\n'
        b'      Self.Font.Style := [];\r\n'
        b'\r\n'
        b'      // radio toggle\r\n'
        b'      rdoMale.Checked := False;\r\n'
        b'      rdoFemale.Checked := True;\r\n'
        b'      Snap(ThemeName + \"_rd1\");\r\n'
        b'      rdoFemale.Checked := False;\r\n'
        b'      rdoOther.Checked := True;\r\n'
        b'      Snap(ThemeName + \"_rd2\");\r\n'
        b'      rdoOther.Checked := False;\r\n'
        b'      rdoMale.Checked := True;\r\n'
        b'\r\n'
        b'      // layout: no sidebar\r\n'
        b'      pnlSidebar.Visible := False;\r\n'
        b'      gbFilters.Visible := False;\r\n'
        b'      Snap(ThemeName + \"_ns\");\r\n'
        b'      pnlSidebar.Visible := True;\r\n'
        b'      gbFilters.Visible := True;\r\n'
        b'\r\n'
        b'      // layout: sidebar right, filters hidden\r\n'
        b'      pnlSidebar.Left := 664;\r\n'
        b'      Snap(ThemeName + \"_sr\");\r\n'
        b'      pnlSidebar.Left := 336;\r\n'
        b'    end;\r\n'
        b'  end;\r\n'
        b'\r\n'
        b'  TStyleManager.TrySetStyle(\"Windows\", False);\r\n'
        b'  statBar.SimpleText := Format(\"Done: %d images\", [ImgIdx]);\r\n'
        b'  btnAutoCollect.Enabled := True;\r\n'
        b'  pcMain.ActivePageIndex := SavedTab;\r\n'
        b'end;'
    )

    content = content[:idx_start] + new_func + content[idx_func_end+5:]
    print(f'2. AutoCollect rewritten ({idx_start}-{idx_func_end})')

with open(PAS_PATH, 'wb') as f:
    f.write(content)
print('3. Saved')
