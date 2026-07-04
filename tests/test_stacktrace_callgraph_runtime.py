#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Runtime smoke tests for StackTrace callgraph address handling."""

import json
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DYNAMIC_BASE = 0x40


def _find_dcc(executable_name: str) -> Path | None:
    """Find a configured Delphi compiler by executable name."""
    expected_name = executable_name.lower()
    config_path = PROJECT_ROOT / "src" / "config" / "compilers.json"
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        for compiler in config.get("compilers", []):
            path_text = str(compiler.get("path", ""))
            path = Path(path_text)
            if path.name.lower() == expected_name and path.exists():
                return path

    path_text = shutil.which(executable_name)
    if path_text:
        path = Path(path_text)
        if path.exists():
            return path
    return None


def _find_dcc32() -> Path | None:
    """Find a configured Win32 Delphi compiler."""
    return _find_dcc("dcc32.exe")


def _find_dcc64() -> Path | None:
    """Find a configured Win64 Delphi compiler."""
    return _find_dcc("dcc64.exe")


def _read_pe_headers(exe_path: Path) -> dict[str, int]:
    """Read the PE image base and DllCharacteristics from an EXE."""
    data = exe_path.read_bytes()
    pe_offset = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe_offset : pe_offset + 4] != b"PE\0\0":
        raise AssertionError(f"{exe_path} is not a PE image")

    optional_header = pe_offset + 4 + 20
    optional_magic = struct.unpack_from("<H", data, optional_header)[0]
    if optional_magic == 0x20B:
        image_base = struct.unpack_from("<Q", data, optional_header + 24)[0]
    elif optional_magic == 0x10B:
        image_base = struct.unpack_from("<I", data, optional_header + 28)[0]
    else:
        raise AssertionError(f"unsupported PE optional header: 0x{optional_magic:X}")

    size_of_image = struct.unpack_from("<I", data, optional_header + 56)[0]
    dll_characteristics = struct.unpack_from("<H", data, optional_header + 0x46)[0]
    return {
        "optional_magic": optional_magic,
        "image_base": image_base,
        "size_of_image": size_of_image,
        "dll_characteristics": dll_characteristics,
    }


def _hex_to_int(value: str) -> int:
    """Parse fixed-width hexadecimal strings emitted by the Delphi smoke app."""
    return int(value, 16)


def _call_edge_exists(calls: list[dict[str, Any]], caller: str, callee: str) -> bool:
    """Return True when a callgraph edge suffix matches the expected functions."""
    return any(
        str(edge.get("from", "")).endswith(caller)
        and str(edge.get("to", "")).endswith(callee)
        for edge in calls
    )


def _write_aslr_smoke_project(tmp_path: Path) -> Path:
    """Create the temporary Win64 console project used by the ASLR smoke."""
    stacktrace_path = PROJECT_ROOT / "tools" / "stacktrace" / "StackTrace.pas"
    source = f"""program W64CallGraphAslrSmoke;

{{$APPTYPE CONSOLE}}
{{$O-}}
{{$INLINE OFF}}

uses
  System.SysUtils,
  System.JSON,
  Winapi.Windows,
  StackTrace in '{stacktrace_path}';

function Hex64(AValue: UInt64): string;
begin
  Result := IntToHex(AValue, 16);
end;

function SmokeLeaf: Integer;
begin
  Result := 7;
end;

function SmokeMiddle: Integer;
begin
  Result := SmokeLeaf + 1;
end;

procedure SmokeEntry;
begin
  if SmokeMiddle = 0 then
    Writeln('unreachable');
end;

procedure EmitResult;
var
  LObj: TJSONObject;
  LArr: TJSONArray;
  LEdgeObj: TJSONObject;
  LChain: TArray<TCallEdge>;
  LEntryAddr: NativeUInt;
  LFindAddr: NativeUInt;
  I: Integer;
begin
  SmokeEntry;
  LChain := TStackTracer.GetCallChain('SmokeEntry', 2);
  LEntryAddr := 0;
  LFindAddr := 0;
  if Length(LChain) > 0 then
  begin
    LEntryAddr := LChain[0].CallerAddr;
    LFindAddr := NativeUInt(TStackTraceManager.Current.FindSymbolAddress(LChain[0].CallerName));
  end;

  LObj := TJSONObject.Create;
  try
    if Length(LChain) > 0 then
      LObj.AddPair('status', 'ok')
    else
      LObj.AddPair('status', 'err');
    LObj.AddPair('module_base', Hex64(UInt64(NativeUInt(GetModuleHandle(nil)))));
    LObj.AddPair('smoke_entry_addr', Hex64(UInt64(LEntryAddr)));
    LObj.AddPair('find_symbol_addr', Hex64(UInt64(LFindAddr)));
    LObj.AddPair('map_status', TJSONNumber.Create(TStackTraceManager.Current.GetMapLoadStatus));
    LObj.AddPair('last_error', TStackTracer.LastError);
    LObj.AddPair('map_error', TStackTracer.MapLoadError);

    LArr := TJSONArray.Create;
    for I := 0 to High(LChain) do begin
      LEdgeObj := TJSONObject.Create;
      LEdgeObj.AddPair('from', LChain[I].CallerName);
      LEdgeObj.AddPair('to', LChain[I].CalleeName);
      LEdgeObj.AddPair('from_addr', Hex64(UInt64(LChain[I].CallerAddr)));
      LEdgeObj.AddPair('to_addr', Hex64(UInt64(LChain[I].CalleeAddr)));
      LEdgeObj.AddPair('call_addr', Hex64(UInt64(LChain[I].CallAddr)));
      LArr.AddElement(LEdgeObj);
    end;
    LObj.AddPair('calls', LArr);

    Writeln(LObj.ToString);
  finally
    LObj.Free;
  end;
end;

begin
  try
    EmitResult;
  except
    on E: Exception do begin
      Writeln('{{"status":"exception","error":"'
          + E.ClassName + ': ' + E.Message.Replace('"', '''') + '"}}');
      Halt(1);
    end;
  end;
end.
"""
    dpr_path = tmp_path / "W64CallGraphAslrSmoke.dpr"
    dpr_path.write_text(source, encoding="utf-8")
    return dpr_path


def _write_local_var_snapshot_project(tmp_path: Path) -> Path:
    """Create a console project that injects local-var metadata at runtime."""
    stacktrace_path = PROJECT_ROOT / "tools" / "stacktrace" / "StackTrace.pas"
    source = f"""program LocalVarSnapshotSmoke;

{{$APPTYPE CONSOLE}}
{{$O-}}
{{$INLINE OFF}}

uses
  System.SysUtils,
  System.JSON,
  System.StrUtils,
  System.TypInfo,
  Winapi.Windows,
  StackTrace in '{stacktrace_path}';

var
  GRoot: TJSONObject;
  GIntSink: Integer;
  GBoolSink: LongBool;
  GTextSink: UnicodeString;
  GObjectSink: TObject;
  GPointerSink: Pointer;
  GUnsupportedSink: Pointer;

function FindSymbolIndex(const AEntries: TArray<TQProfileMapEntry>; const AName: string): Integer;
var
  I: Integer;
begin
  Result := -1;
  for I := 0 to High(AEntries) do
    if ContainsText(AEntries[I].Name, AName) then
      Exit(I);
end;

procedure AddSnapshot(const AKey: string; const AFrame: TFrameSnapshot);
var
  LObj: TJSONObject;
  LArr: TJSONArray;
  LVarObj: TJSONObject;
  I: Integer;
begin
  if GRoot.GetValue(AKey) <> nil then
    Exit;

  LObj := TJSONObject.Create;
  LObj.AddPair('function', AFrame.FuncName);
  LObj.AddPair('source', AFrame.SourceInfo);
  LObj.AddPair('local_count', TJSONNumber.Create(Length(AFrame.Locals)));
  LArr := TJSONArray.Create;
  for I := 0 to High(AFrame.Locals) do begin
    LVarObj := TJSONObject.Create;
    LVarObj.AddPair('name', AFrame.Locals[I].Name);
    LVarObj.AddPair('value', AFrame.Locals[I].Value);
    LVarObj.AddPair('is_register', BoolToStr(AFrame.Locals[I].IsRegister, True));
    LArr.AddElement(LVarObj);
  end;
  LObj.AddPair('locals', LArr);
  GRoot.AddPair(AKey, LObj);
end;

procedure AddFrameError(const AKey, AMessage: string);
var
  LObj: TJSONObject;
begin
  if GRoot.GetValue(AKey) <> nil then
    Exit;

  LObj := TJSONObject.Create;
  LObj.AddPair('error', AMessage);
  LObj.AddPair('local_count', TJSONNumber.Create(0));
  LObj.AddPair('locals', TJSONArray.Create);
  GRoot.AddPair(AKey, LObj);
end;

procedure CaptureSnapshotFromContext(const AKey, AFuncName: string; const AContext: TContext);
var
  I: Integer;
  LFrame: TFrameSnapshot;
begin
  for I := 0 to 5 do begin
    if TStackTraceManager.Current.ReadFrameFromContext(AContext, I, LFrame)
        and ContainsText(LFrame.FuncName, AFuncName) then
    begin
      AddSnapshot(AKey, LFrame);
      Exit;
    end;
  end;
  AddFrameError(AKey, 'frame_not_found');
end;

procedure CaptureSnapshotFromFrame(const AKey, AFuncName: string; AAddr, ABP: Pointer);
var
  LFrame: TFrameSnapshot;
begin
  LFrame := TStackTraceManager.Current.GetFrameSnapshot(NativeUInt(AAddr), ABP);
  if ContainsText(LFrame.FuncName, AFuncName) then
    AddSnapshot(AKey, LFrame)
  else
    AddFrameError(AKey, 'frame_not_found');
end;

procedure CaptureSnapshotFromSimulatedFrame(const AKey, AFuncName: string; AAddr: Pointer);
var
  LFrameBytes: TBytes;
  LBP: Pointer;
  LSlot: Pointer;
begin
  SetLength(LFrameBytes, 256);
  LBP := @LFrameBytes[128];
  LSlot := Pointer(PByte(LBP) - SizeOf(Pointer));

  if AKey = 'integer' then
    PInteger(LSlot)^ := 123456
  else if AKey = 'bool' then
    PInteger(LSlot)^ := 1
  else if AKey = 'string' then begin
    GTextSink := 'manual-var-smoke';
    PPointer(LSlot)^ := Pointer(GTextSink);
  end
  else if AKey = 'object' then
    PPointer(LSlot)^ := Pointer(NativeUInt(1))
  else if AKey = 'pointer' then
    PPointer(LSlot)^ := Pointer(NativeUInt($12345678))
  else if AKey = 'unsupported' then
    PPointer(LSlot)^ := Pointer(NativeUInt($87654321));

  CaptureSnapshotFromFrame(AKey, AFuncName, AAddr, LBP);
end;

procedure AddFormattedContextSamples;
var
  LContext: TExceptionContext;
begin
  LContext := Default(TExceptionContext);
  SetLength(LContext.Frames, 1);
  LContext.Frames[0].Address := 0;
  LContext.Frames[0].FuncName := 'LocalVarSnapshotSmoke.ProbeIntegerSnapshot';
  LContext.Frames[0].SourceInfo := '[LocalVarSnapshotSmoke.dpr:1]';
  SetLength(LContext.Frames[0].Params, 1);
  LContext.Frames[0].Params[0].Name := 'AParam';
  LContext.Frames[0].Params[0].Value := '$0000002A (42)';
  SetLength(LContext.Frames[0].Locals, 1);
  LContext.Frames[0].Locals[0].Name := 'LLocal';
  LContext.Frames[0].Locals[0].Value := '"formatted-local"';

  LContext.CaptureVariables := True;
  GRoot.AddPair('formatted_on', TStackTraceManager.FormatExceptionContext(LContext));
  LContext.CaptureVariables := False;
  GRoot.AddPair('formatted_off', TStackTraceManager.FormatExceptionContext(LContext));
end;

procedure InstallManualLocalVarData;
var
  LEntries: TArray<TQProfileMapEntry>;
  LData: TArray<TLocalVarEntry>;
begin
  LEntries := TStackTraceManager.Current.EnumerateFunctions(nil);
  SetLength(LData, 6);

  LData[0].SymIdx := FindSymbolIndex(LEntries, 'ProbeIntegerSnapshot');
  LData[0].ParamCount := 0;
  LData[0].CallConv := CallConv_Register;
  LData[0].IsMethod := False;
  SetLength(LData[0].Vars, 1);
  LData[0].Vars[0] := TLocalVarInfo.Create('LInt', 'Integer', Ord(tkInteger));

  LData[1].SymIdx := FindSymbolIndex(LEntries, 'ProbeBoolSnapshot');
  LData[1].ParamCount := 0;
  LData[1].CallConv := CallConv_Register;
  LData[1].IsMethod := False;
  SetLength(LData[1].Vars, 1);
  LData[1].Vars[0] := TLocalVarInfo.Create('LBool', 'LongBool', Ord(tkEnumeration));

  LData[2].SymIdx := FindSymbolIndex(LEntries, 'ProbeStringSnapshot');
  LData[2].ParamCount := 0;
  LData[2].CallConv := CallConv_Register;
  LData[2].IsMethod := False;
  SetLength(LData[2].Vars, 1);
  LData[2].Vars[0] := TLocalVarInfo.Create('LText', 'UnicodeString', Ord(tkUString));

  LData[3].SymIdx := FindSymbolIndex(LEntries, 'ProbeInvalidObjectSnapshot');
  LData[3].ParamCount := 0;
  LData[3].CallConv := CallConv_Register;
  LData[3].IsMethod := False;
  SetLength(LData[3].Vars, 1);
  LData[3].Vars[0] := TLocalVarInfo.Create('LObj', 'TObject', Ord(tkClass));

  LData[4].SymIdx := FindSymbolIndex(LEntries, 'ProbeInvalidPointerSnapshot');
  LData[4].ParamCount := 0;
  LData[4].CallConv := CallConv_Register;
  LData[4].IsMethod := False;
  SetLength(LData[4].Vars, 1);
  LData[4].Vars[0] := TLocalVarInfo.Create('LPtr', 'Pointer', Ord(tkPointer));

  LData[5].SymIdx := FindSymbolIndex(LEntries, 'ProbeUnsupportedSnapshot');
  LData[5].ParamCount := 0;
  LData[5].CallConv := CallConv_Register;
  LData[5].IsMethod := False;
  SetLength(LData[5].Vars, 1);
  LData[5].Vars[0] := TLocalVarInfo.Create('LBlob', 'UnsupportedBlob', 250);

  if (LData[0].SymIdx < 0) or (LData[1].SymIdx < 0) or (LData[2].SymIdx < 0)
      or (LData[3].SymIdx < 0) or (LData[4].SymIdx < 0) or (LData[5].SymIdx < 0) then
    raise Exception.Create('manual local-var symbol not found');

  TStackTraceManager.Current.SetLocalVarData(LData);
end;

procedure KeepInteger(var AValue: Integer);
begin
  if AValue = -1 then
    Writeln('unreachable');
end;

procedure KeepBool(var AValue: LongBool);
begin
  if not AValue then
    Writeln('unreachable');
end;

procedure KeepString(const AValue: UnicodeString);
begin
  if AValue = '' then
    Writeln('unreachable');
end;

procedure ProbeIntegerSnapshot;
var
  LInt: Integer;
  LPad: array[0..31] of Byte;
begin
  LInt := 123456;
  LPad[0] := Byte(LInt);
  GIntSink := LInt;
  GIntSink := GIntSink + LPad[0];
end;

procedure ProbeBoolSnapshot;
var
  LBool: LongBool;
  LPad: array[0..31] of Byte;
begin
  LBool := True;
  LPad[0] := Byte(LBool);
  GBoolSink := LBool;
  if LPad[0] = 255 then
    GBoolSink := False;
end;

procedure ProbeStringSnapshot;
var
  LText: UnicodeString;
  LPad: array[0..31] of Byte;
begin
  LText := 'manual-var-smoke';
  LPad[0] := Length(LText);
  GTextSink := LText;
  if LPad[0] = 0 then
    GTextSink := '';
end;

procedure ProbeInvalidObjectSnapshot;
var
  LObj: TObject;
  LPad: array[0..31] of Byte;
begin
  LObj := nil;
  LPad[0] := 0;
  GObjectSink := LObj;
  if LPad[0] = 1 then
    GObjectSink := TObject.Create;
end;

procedure ProbeInvalidPointerSnapshot;
var
  LPtr: Pointer;
  LPad: array[0..31] of Byte;
begin
  LPtr := nil;
  LPad[0] := 0;
  GPointerSink := LPtr;
  if LPad[0] = 1 then
    GPointerSink := Pointer(1);
end;

procedure ProbeUnsupportedSnapshot;
var
  LBlob: Pointer;
  LPad: array[0..31] of Byte;
begin
  LBlob := nil;
  LPad[0] := 0;
  GUnsupportedSink := LBlob;
  if LPad[0] = 1 then
    GUnsupportedSink := Pointer(1);
end;

begin
  GRoot := TJSONObject.Create;
  try
    try
      TStackTraceManager.CaptureVariables := True;
      InstallManualLocalVarData;

      ProbeIntegerSnapshot;
      ProbeBoolSnapshot;
      ProbeStringSnapshot;
      ProbeInvalidObjectSnapshot;
      ProbeInvalidPointerSnapshot;
      ProbeUnsupportedSnapshot;
      CaptureSnapshotFromSimulatedFrame('integer', 'ProbeIntegerSnapshot', @ProbeIntegerSnapshot);
      CaptureSnapshotFromSimulatedFrame('bool', 'ProbeBoolSnapshot', @ProbeBoolSnapshot);
      CaptureSnapshotFromSimulatedFrame('string', 'ProbeStringSnapshot', @ProbeStringSnapshot);
      CaptureSnapshotFromSimulatedFrame('object', 'ProbeInvalidObjectSnapshot', @ProbeInvalidObjectSnapshot);
      CaptureSnapshotFromSimulatedFrame('pointer', 'ProbeInvalidPointerSnapshot', @ProbeInvalidPointerSnapshot);
      CaptureSnapshotFromSimulatedFrame('unsupported', 'ProbeUnsupportedSnapshot', @ProbeUnsupportedSnapshot);
      AddFormattedContextSamples;

      if (GRoot.GetValue('integer') <> nil)
          and (GRoot.GetValue('bool') <> nil)
          and (GRoot.GetValue('string') <> nil)
          and (GRoot.GetValue('object') <> nil)
          and (GRoot.GetValue('pointer') <> nil)
          and (GRoot.GetValue('unsupported') <> nil)
          and (GRoot.GetValue('formatted_on') <> nil)
          and (GRoot.GetValue('formatted_off') <> nil) then
        GRoot.AddPair('status', 'ok')
      else
        GRoot.AddPair('status', 'missing_snapshot');
      GRoot.AddPair('map_status', TJSONNumber.Create(TStackTraceManager.Current.GetMapLoadStatus));
      Writeln(GRoot.ToString);
    except
      on E: Exception do
        Writeln('{{"status":"exception","error":"'
            + E.ClassName + ': ' + E.Message.Replace('"', '''') + '"}}');
    end;
  finally
    GRoot.Free;
  end;
end.
"""
    dpr_path = tmp_path / "LocalVarSnapshotSmoke.dpr"
    dpr_path.write_text(source, encoding="utf-8")
    return dpr_path


def _compile_delphi_console(
    compiler: Path,
    dpr_path: Path,
    tmp_path: Path,
    *,
    extra_args: list[str] | None = None,
) -> None:
    """Compile a temporary Delphi console project for runtime smokes."""
    dcu_dir = tmp_path / "dcu"
    dcu_dir.mkdir(exist_ok=True)
    command = [
        str(compiler),
        "-Q",
        "-B",
        "-CC",
        "-GD",
        "-$O-",
        "--inline:off",
        "-E" + str(tmp_path),
        "-NU" + str(dcu_dir),
    ]
    if extra_args:
        command.extend(extra_args)
    command.append(str(dpr_path))

    compile_result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(tmp_path),
        env={**os.environ, "BDSAPPDATABASEDIR": "SkipUserTools"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert compile_result.returncode == 0, (
        "Delphi compiler failed\n"
        f"compiler: {compiler}\n"
        f"stdout:\n{compile_result.stdout}\n"
        f"stderr:\n{compile_result.stderr}"
    )


def _run_json_exe(exe_path: Path, tmp_path: Path) -> dict[str, Any]:
    """Run a smoke executable and parse the final JSON line."""
    run_result = subprocess.run(
        [str(exe_path)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(tmp_path),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert run_result.returncode == 0, (
        f"{exe_path.name} failed\n"
        f"stdout:\n{run_result.stdout}\n"
        f"stderr:\n{run_result.stderr}"
    )
    output_lines = [line for line in run_result.stdout.splitlines() if line.strip()]
    assert output_lines, f"{exe_path.name} produced no JSON output"
    return json.loads(output_lines[-1])


def _local_var_value(payload: dict[str, Any], key: str, name: str) -> str | None:
    """Return a named local variable value from a local-var smoke payload."""
    frame = payload.get(key, {})
    for item in frame.get("locals", []):
        if item.get("name") == name:
            return str(item.get("value"))
    return None


def _assert_local_var_snapshot_payload(payload: dict[str, Any]) -> None:
    """Assert the smoke captured the expected integer/bool/string locals."""
    assert payload["status"] == "ok", payload
    assert _local_var_value(payload, "integer", "LInt") == "$0001E240 (123456)", payload
    assert _local_var_value(payload, "bool", "LBool") == "True", payload
    assert _local_var_value(payload, "string", "LText") == '"manual-var-smoke"', payload
    assert _local_var_value(payload, "object", "LObj") == "<invalid>", payload
    pointer_value = _local_var_value(payload, "pointer", "LPtr")
    assert pointer_value is not None and pointer_value.endswith("12345678"), payload
    assert _local_var_value(payload, "unsupported", "LBlob") == "<unsupported type>", payload

    formatted_on = str(payload.get("formatted_on", ""))
    formatted_off = str(payload.get("formatted_off", ""))
    assert "LocalVarSnapshotSmoke.ProbeIntegerSnapshot" in formatted_on, payload
    assert "AParam: $0000002A (42)" in formatted_on, payload
    assert 'LLocal: "formatted-local"' in formatted_on, payload
    assert "LocalVarSnapshotSmoke.ProbeIntegerSnapshot" in formatted_off, payload
    assert "AParam:" not in formatted_off, payload
    assert "LLocal:" not in formatted_off, payload


def test_win64_callgraph_survives_dynamic_base_aslr(tmp_path: Path) -> None:
    """Win64 callgraph should resolve MAPDATA RVAs under a randomized module base."""
    if sys.platform != "win32":
        pytest.skip("Win64 Delphi ASLR smoke only runs on Windows")

    dcc64 = _find_dcc64()
    if dcc64 is None:
        pytest.skip("dcc64.exe is not configured")

    dcu_dir = tmp_path / "dcu"
    dcu_dir.mkdir()
    dpr_path = _write_aslr_smoke_project(tmp_path)
    exe_path = tmp_path / "W64CallGraphAslrSmoke.exe"

    compile_result = subprocess.run(
        [
            str(dcc64),
            "-Q",
            "-B",
            "-CC",
            "-GD",
            "-$O-",
            "--inline:off",
            "--peoptflags:0x40",
            "-E" + str(tmp_path),
            "-NU" + str(dcu_dir),
            str(dpr_path),
        ],
        capture_output=True,
        text=True,
        timeout=90,
        cwd=str(tmp_path),
        env={**os.environ, "BDSAPPDATABASEDIR": "SkipUserTools"},
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert compile_result.returncode == 0, (
        "dcc64 failed\n"
        f"stdout:\n{compile_result.stdout}\n"
        f"stderr:\n{compile_result.stderr}"
    )
    assert exe_path.exists()
    assert exe_path.with_suffix(".map").exists()

    pe_headers = _read_pe_headers(exe_path)
    assert pe_headers["optional_magic"] == 0x20B
    assert pe_headers["dll_characteristics"] & DYNAMIC_BASE

    run_result = subprocess.run(
        [str(exe_path)],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(tmp_path),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    assert run_result.returncode == 0, (
        "ASLR smoke app failed\n"
        f"stdout:\n{run_result.stdout}\n"
        f"stderr:\n{run_result.stderr}"
    )

    output_lines = [line for line in run_result.stdout.splitlines() if line.strip()]
    assert output_lines, "ASLR smoke app produced no JSON output"
    payload = json.loads(output_lines[-1])

    preferred_base = pe_headers["image_base"]
    module_base = _hex_to_int(payload["module_base"])
    smoke_entry_addr = _hex_to_int(payload["smoke_entry_addr"])
    find_symbol_addr = _hex_to_int(payload["find_symbol_addr"])
    calls = payload.get("calls", [])

    if module_base == preferred_base:
        pytest.skip("Windows loaded the dynamic-base smoke app at its preferred base")

    assert payload["status"] == "ok", payload
    assert smoke_entry_addr >= module_base, payload
    assert smoke_entry_addr < module_base + pe_headers["size_of_image"], payload
    assert find_symbol_addr == smoke_entry_addr, payload
    assert _call_edge_exists(calls, ".SmokeEntry", ".SmokeMiddle"), payload
    assert _call_edge_exists(calls, ".SmokeMiddle", ".SmokeLeaf"), payload


def test_win32_local_var_snapshot_uses_manual_metadata(tmp_path: Path) -> None:
    """Win32 should capture local values with runtime-injected metadata."""
    if sys.platform != "win32":
        pytest.skip("Win32 Delphi local-var smoke only runs on Windows")

    dcc32 = _find_dcc32()
    if dcc32 is None:
        pytest.skip("dcc32.exe is not configured")

    dpr_path = _write_local_var_snapshot_project(tmp_path)
    exe_path = tmp_path / "LocalVarSnapshotSmoke.exe"
    _compile_delphi_console(dcc32, dpr_path, tmp_path)
    assert exe_path.exists()
    assert exe_path.with_suffix(".map").exists()

    payload = _run_json_exe(exe_path, tmp_path)

    _assert_local_var_snapshot_payload(payload)


def test_win64_local_var_snapshot_uses_manual_metadata(tmp_path: Path) -> None:
    """Win64 should capture local values with runtime-injected metadata."""
    if sys.platform != "win32":
        pytest.skip("Win64 Delphi local-var smoke only runs on Windows")

    dcc64 = _find_dcc64()
    if dcc64 is None:
        pytest.skip("dcc64.exe is not configured")

    dpr_path = _write_local_var_snapshot_project(tmp_path)
    exe_path = tmp_path / "LocalVarSnapshotSmoke.exe"
    _compile_delphi_console(dcc64, dpr_path, tmp_path)
    assert exe_path.exists()
    assert exe_path.with_suffix(".map").exists()

    payload = _run_json_exe(exe_path, tmp_path)

    _assert_local_var_snapshot_payload(payload)
