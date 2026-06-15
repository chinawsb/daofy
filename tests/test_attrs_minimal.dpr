program TestAttr;
{$APPTYPE CONSOLE}
uses
  System.SysUtils,
  DaofyAutomation.RttiAttributes;
var
  d: AIDescriptionAttribute;
  p: AIParamDescriptionAttribute;
  r: AIResultDescriptionAttribute;
  e: AIExampleAttribute;
begin
  d := AIDescriptionAttribute.Create('desc');
  p := AIParamDescriptionAttribute.Create('param desc');
  r := AIResultDescriptionAttribute.Create('result desc');
  e := AIExampleAttribute.Create('example');
  Writeln(d.Text);
  Writeln(p.Text);
  Writeln(r.Text);
  Writeln(e.Text);
  d.Free;
  p.Free;
  r.Free;
  e.Free;
end.
