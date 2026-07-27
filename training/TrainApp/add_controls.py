"""Add more standard VCL controls to TrainApp."""
import re

PAS = 'training/TrainApp/UMainForm.pas'

with open(PAS, 'rb') as f:
    content = f.read()

# 1. Add new control fields before the procedure declarations
old_fields_end = b'    btnAutoCollect: TButton;\r\n\r\n    procedure FormCreate'
new_fields = b'''    btnAutoCollect: TButton;
    ucSpin: TUpDown;
    dtPicker: TDateTimePicker;
    mcCalendar: TMonthCalendar;
    hcHeader: THeaderControl;
    tbToolbar: TToolBar;
    tbtnNew: TToolButton;
    tbtnOpen: TToolButton;
    tbtnSave: TToolButton;
    tbtnSep: TToolButton;
    tbtnDelete: TToolButton;

    procedure FormCreate'''

content = content.replace(old_fields_end, new_fields)

# 2. Add uses for ComCtrls (for TToolBar/TToolButton) and DateTimePicker
# These should already be in the Vcl.ComCtrls unit in interface uses

# 3. Add dynamic tab creation at end of FormCreate
formcreate_marker = b'  tbVolume.Position := 75;\r\nend;'
new_formcreate = b'''  tbVolume.Position := 75;

  // -- create extra controls programmatically --

  // Add Extra tab
  var tsExtra := TTabSheet.Create(Self);
  tsExtra.PageControl := pcMain;
  tsExtra.Caption := 'Extra';
  tsExtra.TabVisible := True;

  // TToolBar
  tbToolbar := TToolBar.Create(Self);
  tbToolbar.Parent := tsExtra;
  tbToolbar.Left := 8;
  tbToolbar.Top := 8;
  tbToolbar.Width := 400;

  tbtnNew := TToolButton.Create(Self);
  tbtnNew.Parent := tbToolbar;
  tbtnNew.Caption := 'New';
  tbtnNew.Style := tbsButton;

  tbtnOpen := TToolButton.Create(Self);
  tbtnOpen.Parent := tbToolbar;
  tbtnOpen.Caption := 'Open';

  tbtnSave := TToolButton.Create(Self);
  tbtnSave.Parent := tbToolbar;
  tbtnSave.Caption := 'Save';

  tbtnSep := TToolButton.Create(Self);
  tbtnSep.Parent := tbToolbar;
  tbtnSep.Style := tbsSeparator;
  tbtnSep.Width := 8;

  tbtnDelete := TToolButton.Create(Self);
  tbtnDelete.Parent := tbToolbar;
  tbtnDelete.Caption := 'Delete';
  tbtnDelete.Enabled := False;

  // TUpDown with buddy edit
  ucSpin := TUpDown.Create(Self);
  ucSpin.Parent := tsExtra;
  ucSpin.Left := 200;
  ucSpin.Top := 60;
  ucSpin.Min := 0;
  ucSpin.Max := 100;
  ucSpin.Position := 50;

  // TDateTimePicker
  dtPicker := TDateTimePicker.Create(Self);
  dtPicker.Parent := tsExtra;
  dtPicker.Left := 8;
  dtPicker.Top := 60;
  dtPicker.Width := 180;
  dtPicker.Date := Now;

  // TMonthCalendar
  mcCalendar := TMonthCalendar.Create(Self);
  mcCalendar.Parent := tsExtra;
  mcCalendar.Left := 8;
  mcCalendar.Top := 100;
  mcCalendar.Width := 200;
  mcCalendar.Height := 160;

  // THeaderControl
  hcHeader := THeaderControl.Create(Self);
  hcHeader.Parent := tsExtra;
  hcHeader.Left := 8;
  hcHeader.Top := 280;
  hcHeader.Width := 400;
  hcHeader.Sections.Add.TotalWidth := 120;
  hcHeader.Sections[0].Text := 'Column 1';
  hcHeader.Sections.Add.TotalWidth := 120;
  hcHeader.Sections[1].Text := 'Column 2';
  hcHeader.Sections.Add.TotalWidth := 120;
  hcHeader.Sections[2].Text := 'Column 3';
end;'''

content = content.replace(formcreate_marker, new_formcreate)

with open(PAS, 'wb') as f:
    f.write(content)

print('Controls added successfully')
