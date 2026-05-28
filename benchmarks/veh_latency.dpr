program veh_latency;

{==============================================================================
  VEH Latency Benchmark — Delphi 11 Win32 compatible
  Measures CPU cycle overhead of VEH callbacks

  Scenarios:
    1. Baseline (no VEH): INT3 -> SEH only
    2. VEH empty handler: registered, returns CONTINUE_SEARCH
    3. VEH check code: reads ExceptionRecord.ExceptionCode
    4. VEH read context: reads Eip and Ebp (minimal stack-walk simulation)

  Each scenario outputs: min/avg/p50/p99 cycles + microseconds
==============================================================================}

{$APPTYPE CONSOLE}
{$R+}

uses
  Windows,
  SysUtils;

{------------------------------------------------------------------------------
  Local type definitions — avoids Windows unit resolution quirks on D11
------------------------------------------------------------------------------}
type
  PExcRec = ^TExcRec;
  TExcRec = packed record
    ExceptionCode: DWORD;
    ExceptionFlags: DWORD;
    OuterException: Pointer;
    ExceptionAddress: Pointer;
    NumberParameters: DWORD;
    ExceptionInformation: array[0..14] of Pointer;
  end;

  PWinContext = ^TWinContext;
  TWinContext = packed record
    ContextFlags: DWORD;
    Dr0: DWORD;
    Dr1: DWORD;
    Dr2: DWORD;
    Dr3: DWORD;
    Dr6: DWORD;
    Dr7: DWORD;
    FloatSave: array[0..27] of DWORD;
    SegGs: DWORD;
    SegFs: DWORD;
    SegEs: DWORD;
    SegDs: DWORD;
    Edi: DWORD;
    Esi: DWORD;
    Ebx: DWORD;
    Edx: DWORD;
    Ecx: DWORD;
    Eax: DWORD;
    Ebp: DWORD;
    Eip: DWORD;
    SegCs: DWORD;
    EFlags: DWORD;
    Esp: DWORD;
    SegSs: DWORD;
  end;

  PExcPointers = ^TExcPointers;
  TExcPointers = packed record
    ExceptionRecord: PExcRec;
    ContextRecord: PWinContext;
  end;

  TVectoredHandler = function(ExceptionInfo: PExcPointers): LongInt; stdcall;

  TTestScenario = (
    tsBaseline,
    tsEmptyHandler,
    tsCheckCode,
    tsReadContext
  );

const
  SCENARIO_NAMES: array[TTestScenario] of string = (
    'Baseline (no VEH)',
    'VEH empty handler',
    'VEH check exception code',
    'VEH read Eip+Ebp'
  );

  ITERATIONS = 100000;
  WARMUP = 5000;

var
  g_Results: array[TTestScenario] of array of Int64;
  g_CurrentScenario: TTestScenario;
  g_CalibrationFreq: Int64;

  { Dynamically loaded VEH functions }
  _AddVectoredExceptionHandler: function(First: LongInt; Handler: Pointer): Pointer; stdcall;
  _RemoveVectoredExceptionHandler: function(Handle: Pointer): LongInt; stdcall;

{------------------------------------------------------------------------------
  ReadTSC — RDTSC wrapper (Win32)
  Win32 Int64 return: EAX = low 32 bits, EDX = high 32 bits.
  RDTSC already puts low in EAX, high in EDX — nothing more to do.
------------------------------------------------------------------------------}
function ReadTSC: Int64; assembler;
asm
  RDTSC
end;

{------------------------------------------------------------------------------
  VEH callback — does NOT record timing; timing is done at call site.
------------------------------------------------------------------------------}
function VEHCallback(ExceptionInfo: PExcPointers): LongInt; stdcall;
begin
  case g_CurrentScenario of
    tsEmptyHandler:
      begin
        // nothing to inspect
      end;

    tsCheckCode:
      begin
        // int 3 generates EXCEPTION_BREAKPOINT ($80000003)
        if ExceptionInfo^.ExceptionRecord^.ExceptionCode = $80000003 then
          ;
      end;

    tsReadContext:
      begin
        if (ExceptionInfo^.ExceptionRecord^.ExceptionCode <> 0) and
           (ExceptionInfo^.ContextRecord^.Eip <> 0) then
          ;
      end;
  end;

  Result := 0; { EXCEPTION_CONTINUE_SEARCH }
end;

{------------------------------------------------------------------------------
  CalibrateTSC — measure CPU frequency via 1-second sleep
------------------------------------------------------------------------------}
function CalibrateTSC: Int64;
var
  start, stop: Int64;
begin
  start := ReadTSC;
  Sleep(1000);
  stop := ReadTSC;
  Result := stop - start;
end;

{------------------------------------------------------------------------------
  TriggerINT3 — execute INT3 instruction inline
  VEH catches it first (if registered), then SEH catches it.
------------------------------------------------------------------------------}
procedure TriggerINT3;
begin
  try
    asm
      int 3
    end;
  except
    // SEH catch (baseline scenario without VEH)
  end;
end;

{------------------------------------------------------------------------------
  RunScenario — times each TriggerINT3 call at the call site
  Measures total time from INT3 to SEH return, for all scenarios.
------------------------------------------------------------------------------}
procedure RunScenario(Scenario: TTestScenario; IsWarmup: Boolean);
var
  i: Integer;
  h: Pointer;
  t: Int64;
begin
  g_CurrentScenario := Scenario;

  if Scenario <> tsBaseline then
    h := _AddVectoredExceptionHandler(0, @VEHCallback);

  for i := 0 to ITERATIONS - 1 do
  begin
    t := ReadTSC;
    TriggerINT3;
    g_Results[Scenario][i] := ReadTSC - t;
  end;

  if (Scenario <> tsBaseline) and (h <> nil) then
    _RemoveVectoredExceptionHandler(h);
end;

{------------------------------------------------------------------------------
  SortInt64Array
------------------------------------------------------------------------------}
procedure SortInt64Array(var A: array of Int64; L, R: Integer);
var
  I, J: Integer;
  Pivot, Tmp: Int64;
begin
  I := L;
  J := R;
  Pivot := A[(L + R) shr 1];
  repeat
    while A[I] < Pivot do Inc(I);
    while A[J] > Pivot do Dec(J);
    if I <= J then
    begin
      Tmp := A[I];
      A[I] := A[J];
      A[J] := Tmp;
      Inc(I);
      Dec(J);
    end;
  until I > J;
  if L < J then SortInt64Array(A, L, J);
  if I < R then SortInt64Array(A, I, R);
end;

function Median(const Data: array of Int64): Int64;
var
  Sorted: array of Int64;
  i: Integer;
begin
  SetLength(Sorted, Length(Data));
  for i := 0 to High(Data) do
    Sorted[i] := Data[i];

  SortInt64Array(Sorted, 0, High(Sorted));
  Result := Sorted[Length(Sorted) div 2];
end;

function Percentile(const Data: array of Int64; P: Integer): Int64;
var
  Sorted: array of Int64;
  i, idx: Integer;
begin
  SetLength(Sorted, Length(Data));
  for i := 0 to High(Data) do
    Sorted[i] := Data[i];

  SortInt64Array(Sorted, 0, High(Sorted));

  idx := (Length(Sorted) * P) div 100;
  if idx >= Length(Sorted) then
    idx := Length(Sorted) - 1;
  Result := Sorted[idx];
end;

{------------------------------------------------------------------------------
  ReportRow
------------------------------------------------------------------------------}
procedure ReportRow(const Name: string; Scenario: TTestScenario; cyclesPerUs: Double);
var
  i: Integer;
  v, total, mn, mx, avg, p99: Int64;
begin
  total := 0;
  mn := High(Int64);
  mx := 0;
  for i := 0 to ITERATIONS - 1 do
  begin
    v := g_Results[Scenario][i];
    total := total + v;
    if v < mn then mn := v;
    if v > mx then mx := v;
  end;
  avg := total div ITERATIONS;
  p99 := Percentile(g_Results[Scenario], 99);

  Writeln(Format('%-30s %10d %10d %10d %10d %10.2f', [
    Name, mn, avg, Median(g_Results[Scenario]), p99, avg / cyclesPerUs
  ]));
end;

{------------------------------------------------------------------------------
  LoadVEH — load VEH API dynamically
------------------------------------------------------------------------------}
function LoadVEH: Boolean;
var
  hMod: HMODULE;
begin
  hMod := GetModuleHandle('kernel32.dll');
  if hMod = 0 then
  begin
    Result := False;
    Exit;
  end;
  @_AddVectoredExceptionHandler := GetProcAddress(hMod, 'AddVectoredExceptionHandler');
  @_RemoveVectoredExceptionHandler := GetProcAddress(hMod, 'RemoveVectoredExceptionHandler');
  Result := Assigned(_AddVectoredExceptionHandler) and
            Assigned(_RemoveVectoredExceptionHandler);
end;

{------------------------------------------------------------------------------
  Main
------------------------------------------------------------------------------}
var
  Scenario: TTestScenario;
  cyclesPerUs: Double;
  b, e, c, r: Int64;
begin
  if not LoadVEH then
  begin
    Writeln('FATAL: VEH API not available on this system');
    Halt(1);
  end;

  Writeln('=== VEH Latency Benchmark ===');
  Writeln;

  Writeln('Calibrating RDTSC (1s)...');
  g_CalibrationFreq := CalibrateTSC;
  cyclesPerUs := g_CalibrationFreq / 1000000.0;
  Writeln(Format('  CPU Frequency: %.2f GHz', [g_CalibrationFreq / 1e9]));
  Writeln(Format('  Cycles per '#$B5's: %.0f', [cyclesPerUs]));
  Writeln;

  for Scenario := Low(TTestScenario) to High(TTestScenario) do
    SetLength(g_Results[Scenario], ITERATIONS);

  Writeln('Warmup...');
  RunScenario(tsBaseline, True);

  for Scenario := Low(TTestScenario) to High(TTestScenario) do
  begin
    Write(Format('Running [%-25s] %6d iterations...', [SCENARIO_NAMES[Scenario], ITERATIONS]));
    RunScenario(Scenario, False);
    Writeln(' done');
  end;

  Writeln;
  Writeln('=== Results ===');
  Writeln;
  Writeln(Format('%-30s %10s %10s %10s %10s %10s', [
    'Scenario', 'Min(cyc)', 'Avg(cyc)', 'P50(cyc)', 'P99(cyc)', 'Avg('#$B5's)'
  ]));
  Writeln(StringOfChar('-', 90));

  for Scenario := Low(TTestScenario) to High(TTestScenario) do
    ReportRow(SCENARIO_NAMES[Scenario], Scenario, cyclesPerUs);

  Writeln;
  Writeln('=== Analysis ===');
  Writeln;
  Writeln('VEH empty handler overhead = VEH(empty) - Baseline');
  Writeln('VEH check code overhead    = VEH(check) - Baseline');
  Writeln('VEH read context overhead  = VEH(read)  - Baseline');
  Writeln;

  b := Median(g_Results[tsBaseline]);
  e := Median(g_Results[tsEmptyHandler]);
  c := Median(g_Results[tsCheckCode]);
  r := Median(g_Results[tsReadContext]);

  Writeln(Format('  VEH registration overhead : %5d cycles  (%.2f '#$B5's)', [e - b, (e - b) / cyclesPerUs]));
  Writeln(Format('  +ExceptionCode check      : %5d cycles  (%.2f '#$B5's)', [c - e, (c - e) / cyclesPerUs]));
  Writeln(Format('  +Eip+Ebp read             : %5d cycles  (%.2f '#$B5's)', [r - c, (r - c) / cyclesPerUs]));
  Writeln;
  Writeln('Note: VEH handler entry/exit overhead is included in all scenarios.');
  Writeln('Target: <400 cycles (<5'#$B5's at 2.5GHz) per VEH invocation for Tier I-II.');
end.
