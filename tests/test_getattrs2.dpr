program TestGetAttrs2;
{$APPTYPE CONSOLE}
uses
  System.SysUtils,
  System.Rtti,
  DaofyAutomation.RttiAttributes;
type
  TTestClass = class
  public
    [AIDescription('test func')]
    function Foo([AIParamDescription('x value')] X: Integer): string;
  end;
function TTestClass.Foo(X: Integer): string;
begin Result := IntToStr(X); end;
var
  ctx: TRttiContext;
  t: TRttiType;
  m: TRttiMethod;
  attrs: TArray<TCustomAttribute>;
  a: TCustomAttribute;
  vis: TMemberVisibility;
begin
  ctx := TRttiContext.Create;
  try
    t := ctx.GetType(TTestClass);
    for m in t.GetMethods do begin
      vis := m.Visibility;
      if vis <> TMemberVisibility.mvPublished then Continue;
      WriteLn('Method: ', m.Name);
      attrs := m.GetAttributes;
      WriteLn('  Attr count: ', Length(attrs));
      for a in attrs do begin
        if a is AIDescriptionAttribute then
          WriteLn('  Desc: ', AIDescriptionAttribute(a).Text);
      end;
    end;
  finally
    ctx.Free;
  end;
end.
