unit TestUnit;

interface

procedure TestProcedure(const AParam: string);

implementation

procedure TestProcedure;
begin
  WriteLn('Modified content - param: ', AParam);
end;

end.
