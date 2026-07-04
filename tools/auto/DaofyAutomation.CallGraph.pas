unit DaofyAutomation.CallGraph;

interface

implementation

uses
  DaofyAutomation.Base,
  StackTrace,
  System.Generics.Collections,
  System.JSON,
  System.StrUtils,
  System.SysUtils;

const
  DEFAULT_PROJECT_EXCLUDES: array[0..10] of string =
      ('System.', 'SysInit.', 'Winapi.', 'Vcl.', 'FMX.', 'Fmx.', 'Data.', 'Xml.', 'Soap.', 'REST.', 'Web.');
  SYSTEM_PREFIXES: array[0..2] of string =
      ('System.', 'SysInit.', 'Winapi.');
  FRAMEWORK_PREFIXES: array[0..7] of string =
      ('Vcl.', 'FMX.', 'Fmx.', 'Data.', 'Xml.', 'Soap.', 'REST.', 'Web.');
  THIRD_PARTY_PREFIXES: array[0..9] of string =
      ('VirtualTrees.', 'QLog.', 'FastReport.', 'frx', 'DevExpress.', 'cx', 'dx', 'Jv', 'Raize.', 'Uni');

type
  TCallPath = record
    Edges: TArray<TCallEdge>;
  end;

function WriteResp(const ReqId, Status, Data: string): string;
var
  J: TJSONObject;
begin
  J := TJSONObject.Create;
  try
    J.AddPair('reqId', ReqId);
    J.AddPair('status', Status);
    J.AddPair('data', Data);
    Result := J.ToJSON;
  finally
    J.Free;
  end;
end;

function GetJSONStr(const J: TJSONObject; const K, Def: string): string;
var
  V: TJSONValue;
begin
  Result := Def;
  if J = nil then
    Exit;
  V := J.Values[K];
  if V <> nil then
    Result := V.Value;
end;

function GetJSONBool(const J: TJSONObject; const K: string; ADefault: Boolean): Boolean;
var
  V: TJSONValue;
  S: string;
begin
  Result := ADefault;
  if J = nil then
    Exit;
  V := J.Values[K];
  if V = nil then
    Exit;
  S := LowerCase(Trim(V.Value));
  if (S = '1') or (S = 'true') or (S = 'yes') or (S = 'y') then
    Result := True
  else if (S = '0') or (S = 'false') or (S = 'no') or (S = 'n') then
    Result := False;
end;

function NormalizeDirection(const AValue: string; out ADirection: string): Boolean;
var
  S: string;
begin
  S := LowerCase(Trim(AValue));
  if S = '' then
    S := 'callees';

  if (S = 'callee') or (S = 'callees') or (S = 'down') or (S = 'out') then begin
    ADirection := 'callees';
    Exit(True);
  end;

  if (S = 'caller') or (S = 'callers') or (S = 'up') or (S = 'in') then begin
    ADirection := 'callers';
    Exit(True);
  end;

  ADirection := S;
  Result := False;
end;

procedure AddStringPair(AObject: TJSONObject; const AName, AValue: string);
begin
  if (AObject <> nil) and (AValue <> '') then
    AObject.AddPair(AName, AValue);
end;

procedure AddPrefix(var AItems: TArray<string>; const AValue: string);
var
  I, N: Integer;
  P: string;
begin
  P := Trim(AValue);
  if P = '' then
    Exit;
  for I := 0 to High(AItems) do
    if SameText(AItems[I], P) then
      Exit;

  N := Length(AItems);
  SetLength(AItems, N + 1);
  AItems[N] := P;
end;

procedure AddPrefixesFromText(var AItems: TArray<string>; const AText: string);
var
  I: Integer;
  Parts: TArray<string>;
  Text: string;
begin
  Text := StringReplace(AText, ';', ',', [rfReplaceAll]);
  Text := StringReplace(Text, '|', ',', [rfReplaceAll]);
  Parts := SplitString(Text, ',');
  for I := 0 to High(Parts) do
    AddPrefix(AItems, Parts[I]);
end;

function BuildPrefixes(const AText: string): TArray<string>;
begin
  SetLength(Result, 0);
  AddPrefixesFromText(Result, AText);
end;

function BuildExcludePrefixes(AProjectOnly: Boolean; const AText: string): TArray<string>;
var
  I: Integer;
begin
  SetLength(Result, 0);
  if AProjectOnly then
    for I := Low(DEFAULT_PROJECT_EXCLUDES) to High(DEFAULT_PROJECT_EXCLUDES) do
      AddPrefix(Result, DEFAULT_PROJECT_EXCLUDES[I]);
  AddPrefixesFromText(Result, AText);
end;

function NameHasPrefix(const AName, APrefix: string): Boolean;
var
  P: string;
begin
  P := Trim(APrefix);
  if P = '' then
    Exit(False);

  Result := SameText(Copy(AName, 1, Length(P)), P);
  if (not Result) and (P[Length(P)] <> '.') then
    Result := SameText(Copy(AName, 1, Length(P) + 1), P + '.');
end;

function NameHasAnyPrefix(const AName: string; const APrefixes: array of string): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := Low(APrefixes) to High(APrefixes) do
    if NameHasPrefix(AName, APrefixes[I]) then
      Exit(True);
end;

function EdgeMatchesPrefixes(const AEdge: TCallEdge; const APrefixes: TArray<string>): Boolean;
begin
  Result := NameHasAnyPrefix(AEdge.CallerName, APrefixes) or NameHasAnyPrefix(AEdge.CalleeName, APrefixes);
end;

function EdgeExcluded(const AEdge: TCallEdge; const APrefixes: TArray<string>): Boolean;
begin
  Result := EdgeMatchesPrefixes(AEdge, APrefixes);
end;

function EdgeIncluded(const AEdge: TCallEdge; const APrefixes: TArray<string>): Boolean;
begin
  Result := (Length(APrefixes) = 0) or EdgeMatchesPrefixes(AEdge, APrefixes);
end;

function EdgeSame(const ALeft, ARight: TCallEdge): Boolean;
begin
  Result :=
      (ALeft.CallerAddr = ARight.CallerAddr)
          and (ALeft.CalleeAddr = ARight.CalleeAddr)
          and (ALeft.CallAddr = ARight.CallAddr)
          and SameText(ALeft.CallerName, ARight.CallerName)
          and SameText(ALeft.CalleeName, ARight.CalleeName);
end;

function EdgeExists(AItems: TList<TCallEdge>; const AEdge: TCallEdge): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 0 to AItems.Count - 1 do
    if EdgeSame(AItems[I], AEdge) then
      Exit(True);
end;

function FilterChain(
    const AChain: TArray<TCallEdge>;
    const AExcludePrefixes, AIncludePrefixes: TArray<string>
): TArray<TCallEdge>;
var
  Edge: TCallEdge;
  Items: TList<TCallEdge>;
begin
  Items := TList<TCallEdge>.Create;
  try
    for Edge in AChain do
      if (not EdgeExcluded(Edge, AExcludePrefixes)) and EdgeIncluded(Edge, AIncludePrefixes)
          and (not EdgeExists(Items, Edge)) then
        Items.Add(Edge);
    Result := Items.ToArray;
  finally
    Items.Free;
  end;
end;

function ApplyEdgeLimit(const AChain: TArray<TCallEdge>; ALimit: Integer; out ATruncated: Boolean): TArray<TCallEdge>;
var
  I: Integer;
begin
  ATruncated := False;
  if (ALimit <= 0) or (Length(AChain) <= ALimit) then
    Exit(AChain);

  SetLength(Result, ALimit);
  for I := 0 to ALimit - 1 do
    Result[I] := AChain[I];
  ATruncated := True;
end;

function PrefixesToJSON(const APrefixes: TArray<string>): TJSONArray;
var
  I: Integer;
begin
  Result := TJSONArray.Create;
  for I := 0 to High(APrefixes) do
    Result.AddElement(TJSONString.Create(APrefixes[I]));
end;

function SymbolMatches(const ASymbol, AQuery: string): Boolean;
var
  S: string;
  Q: string;
  StartPos: Integer;
begin
  Result := False;
  S := Trim(ASymbol);
  Q := Trim(AQuery);
  if (S = '') or (Q = '') then
    Exit;

  if SameText(S, Q) then
    Exit(True);

  StartPos := Length(S) - Length(Q) + 1;
  Result := (StartPos > 1) and SameText(Copy(S, StartPos, MaxInt), Q) and (S[StartPos - 1] = '.');
end;

function SymbolCategory(const AName: string): string;
begin
  if Trim(AName) = '' then
    Exit('unknown');
  if NameHasAnyPrefix(AName, SYSTEM_PREFIXES) then
    Exit('system');
  if NameHasAnyPrefix(AName, FRAMEWORK_PREFIXES) then
    Exit('framework');
  if NameHasAnyPrefix(AName, THIRD_PARTY_PREFIXES) then
    Exit('thirdparty');
  Result := 'project';
end;

function FormatCallGraphAddr(AAddr: NativeUInt): string;
begin
  if SizeOf(Pointer) = SizeOf(UInt64) then
    Result := Format('%.16x', [UInt64(AAddr)])
  else
    Result := Format('%.8x', [Cardinal(AAddr)]);
end;

function EdgeToJSON(const AEdge: TCallEdge): TJSONObject;
var
  FromCategory: string;
  ToCategory: string;
begin
  FromCategory := SymbolCategory(AEdge.CallerName);
  ToCategory := SymbolCategory(AEdge.CalleeName);
  Result := TJSONObject.Create;
  Result.AddPair('from', AEdge.CallerName);
  Result.AddPair('from_addr', FormatCallGraphAddr(AEdge.CallerAddr));
  Result.AddPair('from_category', FromCategory);
  Result.AddPair('call_addr', FormatCallGraphAddr(AEdge.CallAddr));
  Result.AddPair('call_file', AEdge.CallFile);
  Result.AddPair('call_line', TJSONNumber.Create(AEdge.CallLine));
  Result.AddPair('to', AEdge.CalleeName);
  Result.AddPair('to_addr', FormatCallGraphAddr(AEdge.CalleeAddr));
  Result.AddPair('to_category', ToCategory);
  Result.AddPair('category', ToCategory);
  if AEdge.CalleeFile <> '' then begin
    Result.AddPair('to_file', AEdge.CalleeFile);
    Result.AddPair('to_line', TJSONNumber.Create(AEdge.CalleeLine));
  end;
end;

function PathToJSON(const APath: TCallPath): TJSONArray;
var
  I: Integer;
begin
  Result := TJSONArray.Create;
  for I := 0 to High(APath.Edges) do
    Result.AddElement(EdgeToJSON(APath.Edges[I]));
end;

function ExtendPath(const APath: TCallPath; const AEdge: TCallEdge): TCallPath;
var
  N: Integer;
begin
  Result.Edges := Copy(APath.Edges);
  N := Length(Result.Edges);
  SetLength(Result.Edges, N + 1);
  Result.Edges[N] := AEdge;
end;

function PathHasAddr(const APath: TCallPath; AAddr: NativeUInt): Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 0 to High(APath.Edges) do
    if (APath.Edges[I].CallerAddr = AAddr) or (APath.Edges[I].CalleeAddr = AAddr) then
      Exit(True);
end;

function FindCallPaths(
    const AEdges: TArray<TCallEdge>;
    const ASource, ATarget: string;
    AMaxDepth, AMaxPaths: Integer;
    out ATruncated: Boolean
): TArray<TCallPath>;
var
  Edge: TCallEdge;
  Current: TCallPath;
  NextPath: TCallPath;
  LastEdge: TCallEdge;
  Paths: TList<TCallPath>;
  Queue: TQueue<TCallPath>;
  I: Integer;
begin
  ATruncated := False;
  SetLength(Result, 0);
  if AMaxPaths <= 0 then
    Exit;

  Paths := TList<TCallPath>.Create;
  Queue := TQueue<TCallPath>.Create;
  try
    if SameText(Trim(ASource), Trim(ATarget)) then begin
      SetLength(Current.Edges, 0);
      Paths.Add(Current);
    end;

    if AMaxDepth <= 0 then begin
      Result := Paths.ToArray;
      Exit;
    end;

    for Edge in AEdges do begin
      if not SymbolMatches(Edge.CallerName, ASource) then
        Continue;
      SetLength(Current.Edges, 1);
      Current.Edges[0] := Edge;
      if SymbolMatches(Edge.CalleeName, ATarget) then begin
        Paths.Add(Current);
        if Paths.Count >= AMaxPaths then begin
          ATruncated := True;
          Break;
        end;
      end
      else if AMaxDepth > 1 then
        Queue.Enqueue(Current);
    end;

    while (Queue.Count > 0) and (Paths.Count < AMaxPaths) do begin
      Current := Queue.Dequeue;
      if Length(Current.Edges) >= AMaxDepth then
        Continue;
      LastEdge := Current.Edges[High(Current.Edges)];
      for I := 0 to High(AEdges) do begin
        Edge := AEdges[I];
        if Edge.CallerAddr <> LastEdge.CalleeAddr then
          Continue;
        if PathHasAddr(Current, Edge.CalleeAddr) then
          Continue;
        NextPath := ExtendPath(Current, Edge);
        if SymbolMatches(Edge.CalleeName, ATarget) then begin
          Paths.Add(NextPath);
          if Paths.Count >= AMaxPaths then begin
            ATruncated := True;
            Break;
          end;
        end
        else
          Queue.Enqueue(NextPath);
      end;
    end;

    Result := Paths.ToArray;
  finally
    Queue.Free;
    Paths.Free;
  end;
end;

function PathsToJSON(const APaths: TArray<TCallPath>): TJSONArray;
var
  I: Integer;
begin
  Result := TJSONArray.Create;
  for I := 0 to High(APaths) do
    Result.AddElement(PathToJSON(APaths[I]));
end;

function ErrorPayload(const ATarget, ACode, AWarning: string): string;
var
  Obj: TJSONObject;
  Arr: TJSONArray;
begin
  Obj := TJSONObject.Create;
  try
    Obj.AddPair('root', ATarget);
    Arr := TJSONArray.Create;
    Obj.AddPair('calls', Arr);
    AddStringPair(Obj, 'error_code', ACode);
    AddStringPair(Obj, 'map_warning', AWarning);
    Result := Obj.ToJSON;
  finally
    Obj.Free;
  end;
end;

function HandleCallGraph(const ReqId, Target: string; const J: TJSONObject): string;
var
  Depth: Integer;
  EdgeCount: Integer;
  EdgeLimit: Integer;
  ReturnedCount: Integer;
  Chain: TArray<TCallEdge>;
  RawChain: TArray<TCallEdge>;
  JsonText: string;
  JsonValue: TJSONValue;
  JsonObj: TJSONObject;
  LastError: string;
  MapWarning: string;
  Status: string;
  Direction: string;
  DirectionValue: string;
  ProjectOnly: Boolean;
  Truncated: Boolean;
  ExcludePrefixes: TArray<string>;
  IncludePrefixes: TArray<string>;
begin
  try
    if Target = '' then
      Exit(WriteResp(ReqId, 'err', ErrorPayload('', 'missing_target', '')));

    DirectionValue := GetJSONStr(J, 'direction', GetJSONStr(J, 'mode', 'callees'));
    if not NormalizeDirection(DirectionValue, Direction) then
      Exit(WriteResp(ReqId, 'err', ErrorPayload(Target, 'invalid_direction', DirectionValue)));

    Depth := StrToIntDef(GetJSONStr(J, 'max_depth', '5'), 5);
    if Depth < 0 then
      Depth := 0
    else if Depth > 20 then
      Depth := 20;

    EdgeLimit := StrToIntDef(GetJSONStr(J, 'edge_limit', '0'), 0);
    if EdgeLimit < 0 then
      EdgeLimit := 0
    else if EdgeLimit > 5000 then
      EdgeLimit := 5000;

    ProjectOnly := GetJSONBool(J, 'project_only', False);
    ExcludePrefixes :=
        BuildExcludePrefixes(ProjectOnly, GetJSONStr(J, 'exclude_prefixes', GetJSONStr(J, 'exclude', '')));
    IncludePrefixes := BuildPrefixes(GetJSONStr(J, 'include_prefixes', GetJSONStr(J, 'include', '')));

    if Direction = 'callers' then
      RawChain := TStackTracer.GetCallerChain(Target, Depth)
    else
      RawChain := TStackTracer.GetCallChain(Target, Depth);

    Chain := FilterChain(RawChain, ExcludePrefixes, IncludePrefixes);
    EdgeCount := Length(Chain);
    Chain := ApplyEdgeLimit(Chain, EdgeLimit, Truncated);
    ReturnedCount := Length(Chain);

    JsonText := TStackTracer.CallChainToJSON(Chain, Target, Direction);
    LastError := TStackTracer.LastError;
    if (LastError = '') and (Length(RawChain) > 0) and (EdgeCount = 0) then
      LastError := 'filtered_empty';
    MapWarning := TStackTracer.MapLoadError;

    Status := 'ok';
    if (LastError <> '') and (LastError <> 'no_edges') and (LastError <> 'filtered_empty') then
      Status := 'err';

    JsonValue := TJSONObject.ParseJSONValue(JsonText);
    try
      if JsonValue is TJSONObject then
        JsonObj := TJSONObject(JsonValue)
      else begin
        JsonValue.Free;
        JsonValue := TJSONObject.Create;
        JsonObj := TJSONObject(JsonValue);
        JsonObj.AddPair('root', Target);
        JsonObj.AddPair('direction', Direction);
        JsonObj.AddPair('calls', TJSONArray.Create);
      end;

      if Length(Chain) = 0 then
        JsonObj.AddPair('requested_root', Target);
      JsonObj.AddPair('max_depth', TJSONNumber.Create(Depth));
      JsonObj.AddPair('edge_limit', TJSONNumber.Create(EdgeLimit));
      JsonObj.AddPair('edge_count', TJSONNumber.Create(EdgeCount));
      JsonObj.AddPair('returned_count', TJSONNumber.Create(ReturnedCount));
      JsonObj.AddPair('truncated', TJSONBool.Create(Truncated));
      JsonObj.AddPair('project_only', TJSONBool.Create(ProjectOnly));
      JsonObj.AddPair('exclude_prefixes', PrefixesToJSON(ExcludePrefixes));
      JsonObj.AddPair('include_prefixes', PrefixesToJSON(IncludePrefixes));
      AddStringPair(JsonObj, 'error_code', LastError);
      AddStringPair(JsonObj, 'map_warning', MapWarning);
      JsonText := JsonObj.ToJSON;
    finally
      JsonValue.Free;
    end;

    Result := WriteResp(ReqId, Status, JsonText);
  except
    on E: Exception do
      Result := WriteResp(ReqId, 'err', ErrorPayload(Target, 'exception', E.ClassName + ': ' + E.Message));
  end;
end;
function HandleCallGraphPath(const ReqId, Target: string; const J: TJSONObject): string;
var
  SourceValue: string;
  TargetValue: string;
  Depth: Integer;
  MaxPaths: Integer;
  RawChain: TArray<TCallEdge>;
  Chain: TArray<TCallEdge>;
  Paths: TArray<TCallPath>;
  JsonObj: TJSONObject;
  LastError: string;
  MapWarning: string;
  Status: string;
  ProjectOnly: Boolean;
  Truncated: Boolean;
  ExcludePrefixes: TArray<string>;
  IncludePrefixes: TArray<string>;
begin
  try
    SourceValue := GetJSONStr(J, 'source', GetJSONStr(J, 'from', ''));
    TargetValue := Target;
    if TargetValue = '' then
      TargetValue := GetJSONStr(J, 'target', GetJSONStr(J, 'to', ''));

    if SourceValue = '' then
      Exit(WriteResp(ReqId, 'err', ErrorPayload('', 'missing_source', '')));
    if TargetValue = '' then
      Exit(WriteResp(ReqId, 'err', ErrorPayload(SourceValue, 'missing_target', '')));

    Depth := StrToIntDef(GetJSONStr(J, 'max_depth', GetJSONStr(J, 'depth', '5')), 5);
    if Depth < 0 then
      Depth := 0
    else if Depth > 20 then
      Depth := 20;

    MaxPaths := StrToIntDef(GetJSONStr(J, 'max_paths', '10'), 10);
    if MaxPaths < 1 then
      MaxPaths := 1
    else if MaxPaths > 100 then
      MaxPaths := 100;

    ProjectOnly := GetJSONBool(J, 'project_only', False);
    ExcludePrefixes :=
        BuildExcludePrefixes(ProjectOnly, GetJSONStr(J, 'exclude_prefixes', GetJSONStr(J, 'exclude', '')));
    IncludePrefixes := BuildPrefixes(GetJSONStr(J, 'include_prefixes', GetJSONStr(J, 'include', '')));

    RawChain := TStackTracer.GetCallChain(SourceValue, Depth);
    Chain := FilterChain(RawChain, ExcludePrefixes, IncludePrefixes);
    Paths := FindCallPaths(Chain, SourceValue, TargetValue, Depth, MaxPaths, Truncated);
    LastError := TStackTracer.LastError;
    MapWarning := TStackTracer.MapLoadError;

    Status := 'ok';
    if (LastError <> '') and (LastError <> 'no_edges') then
      Status := 'err';

    JsonObj := TJSONObject.Create;
    try
      JsonObj.AddPair('source', SourceValue);
      JsonObj.AddPair('target', TargetValue);
      JsonObj.AddPair('found', TJSONBool.Create(Length(Paths) > 0));
      JsonObj.AddPair('paths', PathsToJSON(Paths));
      JsonObj.AddPair('path_count', TJSONNumber.Create(Length(Paths)));
      JsonObj.AddPair('max_depth', TJSONNumber.Create(Depth));
      JsonObj.AddPair('max_paths', TJSONNumber.Create(MaxPaths));
      JsonObj.AddPair('edge_count', TJSONNumber.Create(Length(Chain)));
      JsonObj.AddPair('truncated', TJSONBool.Create(Truncated));
      JsonObj.AddPair('project_only', TJSONBool.Create(ProjectOnly));
      JsonObj.AddPair('exclude_prefixes', PrefixesToJSON(ExcludePrefixes));
      JsonObj.AddPair('include_prefixes', PrefixesToJSON(IncludePrefixes));
      AddStringPair(JsonObj, 'error_code', LastError);
      AddStringPair(JsonObj, 'map_warning', MapWarning);
      Result := WriteResp(ReqId, Status, JsonObj.ToJSON);
    finally
      JsonObj.Free;
    end;
  except
    on E: Exception do
      Result := WriteResp(ReqId, 'err', ErrorPayload(Target, 'exception', E.ClassName + ': ' + E.Message));
  end;
end;

initialization
  TAutomationProcessorBase.RegisterCommandHandler('callgraph', HandleCallGraph);
  TAutomationProcessorBase.RegisterCommandHandler('callgraph_path', HandleCallGraphPath);

finalization
  TAutomationProcessorBase.UnregisterCommandHandler('callgraph_path');
  TAutomationProcessorBase.UnregisterCommandHandler('callgraph');

end.
