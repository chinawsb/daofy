#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Static guards for the Delphi StackTrace callgraph facade."""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_repo_text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8-sig")


def test_stacktracer_compat_unit_is_removed():
    """The standalone StackTracer.pas compatibility unit should not be restored."""
    assert not (PROJECT_ROOT / "tools/stacktrace/StackTracer.pas").exists()

    callgraph_source = _read_repo_text("tools/auto/DaofyAutomation.CallGraph.pas")
    uses_start = callgraph_source.index("uses")
    uses_end = callgraph_source.index("const", uses_start)
    uses_block = callgraph_source[uses_start:uses_end]
    assert "StackTrace" in uses_block
    assert "StackTracer" not in uses_block


def test_stacktrace_context_uses_win64_conditionals():
    """Win64 context access must use the project/compiler WIN64 symbol."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    assert "{$IFDEF CPUX64}" not in source

    walk_start = source.index("function TStackTraceManager.WalkStackFromContext")
    walk_end = source.index("constructor TStackTraceManager.Create", walk_start)
    walk_body = source[walk_start:walk_end]
    assert "{$IFDEF WIN64}" in walk_body
    assert "AContext.Rip" in walk_body
    assert "AContext.Eip" in walk_body


def test_stacktrace_variable_capture_is_default_off_and_guarded():
    """Local variable reads must stay behind the explicit CaptureVariables switch."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")

    class_var_start = source.index("class var")
    class_var_end = source.index("protected", class_var_start)
    class_vars = source[class_var_start:class_var_end]
    assert "FCaptureVariables: Boolean;" in class_vars

    stack_string_start = source.index("class function TStackTraceManager.StackInfoStringProc")
    stack_string_end = source.index("class function TStackTraceManager.GetStackString", stack_string_start)
    stack_string_body = source[stack_string_start:stack_string_end]
    assert "if FCaptureVariables then begin" in stack_string_body
    assert stack_string_body.index("if FCaptureVariables then begin") < stack_string_body.index("LFrame.Locals")

    snapshot_start = source.index("function TStackTraceManager.GetFrameSnapshot")
    snapshot_end = source.index("class function TStackTraceManager.BuildExceptionContext", snapshot_start)
    snapshot_body = source[snapshot_start:snapshot_end]
    assert "if not FCaptureVariables then" in snapshot_body
    assert snapshot_body.index("if not FCaptureVariables then") < snapshot_body.index("FindLocalVars(LSymIdx)")


def test_stacktrace_local_var_reads_are_bounded_and_whitelisted():
    """Variable value rendering should not perform unbounded or unknown-type reads."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")

    assert "MaxCapturedStringChars = 1024;" in source

    string_start = source.index("function TStackTraceManager.TryGetStringValue")
    string_end = source.index("function TStackTraceManager.ReadStackVarValue", string_start)
    string_body = source[string_start:string_end]
    assert "if LLen > MaxCapturedStringChars then" in string_body
    assert "Move(PByte(P)^, PByte(PChar(Result))^, LLen * SizeOf(Char));" in string_body
    assert string_body.index("if LLen > MaxCapturedStringChars then") < string_body.index(
        "Move(PByte(P)^"
    )

    read_start = source.index("function TStackTraceManager.ReadStackVarValue")
    read_end = source.index("class function TStackTraceManager.StackInfoStringProc", read_start)
    read_body = source[read_start:read_end]
    assert "Ord(tkPointer): begin" in read_body
    assert "Result := '<unsupported type>';" in read_body
    unsupported_start = read_body.index("else\n      Result := '<unsupported type>';")
    assert "PPointer(Addr)^" not in read_body[unsupported_start:]


def test_exception_context_formatter_controls_param_local_output():
    """Default exception logging should share one CaptureVariables-aware formatter."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")

    decl_start = source.index("TStackTraceManager = class")
    decl_end = source.index("function GetFrameSnapshot", decl_start)
    declaration = source[decl_start:decl_end]
    assert "class function FormatExceptionContext(const AContext: TExceptionContext): string; static;" in declaration

    formatter_start = source.index("class function TStackTraceManager.FormatExceptionContext")
    formatter_end = source.index("procedure TDefaultExceptionLogger.HandleException", formatter_start)
    formatter_body = source[formatter_start:formatter_end]
    assert "if AContext.CaptureVariables then begin" in formatter_body
    assert "AContext.Frames[I].Params[J].Name" in formatter_body
    assert "AContext.Frames[I].Locals[J].Name" in formatter_body
    assert "Format('    %s: %s'" in formatter_body

    logger_start = source.index("procedure TDefaultExceptionLogger.HandleException")
    logger_end = source.index("function TStackTraceManager.ParseMapFile", logger_start)
    logger_body = source[logger_start:logger_end]
    assert "LStackText := TStackTraceManager.FormatExceptionContext(AContext);" in logger_body
    assert "AContext.Frames[I].Params" not in logger_body
    assert "AContext.Frames[I].Locals" not in logger_body


def test_embed_map_discovers_bds_root_without_version_hardcoding():
    """Source path resolution should not hardcode specific RAD Studio BDS versions."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")

    discovery_start = source.index("// Discover Delphi RTL/VCL source paths from installed BDS registry keys.")
    discovery_end = source.index("var LBDSKnownSrcDirs", discovery_start)
    discovery_body = source[discovery_start:discovery_end]

    assert "LReg.OpenKeyReadOnly('Software\\Embarcadero\\BDS')" in discovery_body
    assert "LReg.GetKeyNames(LKeyNames);" in discovery_body
    assert "LBestBDSMajor" in discovery_body
    assert "'Software\\Embarcadero\\BDS\\' + LVersionText" in discovery_body
    assert "BDS\\22.0" not in source
    assert "BDS\\23.0" not in source


def test_embed_map_recursive_source_lookup_is_opt_in():
    """Project-wide recursive source lookup should not run by default."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")

    recursive_start = source.index("DAOFY_STACKTRACE_RECURSIVE_SOURCE_LOOKUP")
    recursive_body = source[recursive_start - 300:recursive_start + 700]
    assert "SameText(GetEnvironmentVariable('DAOFY_STACKTRACE_RECURSIVE_SOURCE_LOOKUP'), '1')" in recursive_body
    assert "TDirectory.GetFiles(LProjectRoot, LShortName, TSearchOption.soAllDirectories)" in recursive_body
    assert recursive_body.index("DAOFY_STACKTRACE_RECURSIVE_SOURCE_LOOKUP") < recursive_body.index(
        "TDirectory.GetFiles"
    )
    assert "recursive source lookup disabled" in recursive_body


def _put_u16(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 2] = value.to_bytes(2, "little")


def _put_u32(data: bytearray, offset: int, value: int) -> None:
    data[offset:offset + 4] = value.to_bytes(4, "little")


def _build_pe_text_fixture(*, pe32_plus: bool) -> bytes:
    """Build a minimal PE fixture with a .text section for parser tests."""
    data = bytearray(0x300)
    pe_offset = 0x80
    optional_size = 0xF0 if pe32_plus else 0xE0
    optional_magic = 0x20B if pe32_plus else 0x10B
    file_header = pe_offset + 4
    optional_header = file_header + 20
    section_header = optional_header + optional_size

    data[0:2] = b"MZ"
    _put_u32(data, 0x3C, pe_offset)
    data[pe_offset:pe_offset + 4] = b"PE\0\0"
    _put_u16(data, file_header + 2, 1)  # NumberOfSections
    _put_u16(data, file_header + 16, optional_size)
    _put_u16(data, optional_header, optional_magic)

    data[section_header:section_header + 8] = b".text\0\0\0"
    _put_u32(data, section_header + 8, 0x1234)  # VirtualSize
    _put_u32(data, section_header + 12, 0x1000)  # VirtualAddress
    return bytes(data)


def _parse_text_range_from_pe_fixture(data: bytes) -> tuple[int, int]:
    """Parse .text range from a fixed PE fixture using PE32/PE32+ section rules."""
    pe_offset = int.from_bytes(data[0x3C:0x40], "little")
    assert data[pe_offset:pe_offset + 4] == b"PE\0\0"
    file_header = pe_offset + 4
    section_count = int.from_bytes(data[file_header + 2:file_header + 4], "little")
    optional_size = int.from_bytes(data[file_header + 16:file_header + 18], "little")
    optional_header = file_header + 20
    optional_magic = int.from_bytes(data[optional_header:optional_header + 2], "little")
    assert optional_magic in (0x10B, 0x20B)

    section_header = optional_header + optional_size
    for index in range(section_count):
        entry = section_header + index * 40
        name = data[entry:entry + 8].rstrip(b"\0")
        if name == b".text":
            virtual_size = int.from_bytes(data[entry + 8:entry + 12], "little")
            virtual_address = int.from_bytes(data[entry + 12:entry + 16], "little")
            return virtual_address, virtual_size
    raise AssertionError(".text section not found")


def _build_e8_rel32_fixture(call_site: int, target: int) -> bytes:
    """Build bytes for a direct near call instruction at a fixed call site."""
    rel32 = target - (call_site + 5)
    assert -(1 << 31) <= rel32 < (1 << 31)
    return b"\xE8" + rel32.to_bytes(4, "little", signed=True)


def _resolve_e8_rel32_fixture_target(call_site: int, instruction: bytes) -> int:
    """Resolve an E8 rel32 target from fixture bytes."""
    assert instruction[0] == 0xE8
    rel32 = int.from_bytes(instruction[1:5], "little", signed=True)
    return call_site + 5 + rel32


def _map_rva_to_runtime_addr(map_rva: int, module_base: int) -> int:
    """Convert a MAPDATA RVA to a runtime address."""
    return module_base + map_rva


def _runtime_addr_to_map_rva(runtime_addr: int, module_base: int) -> int:
    """Convert a runtime address back to a MAPDATA RVA."""
    if runtime_addr < module_base:
        return 0
    return runtime_addr - module_base


def _parse_hex_uint64(text: str) -> int:
    """Parse a Delphi-style hex token with UInt64 semantics."""
    if not text:
        raise ValueError("empty hex token")
    value = 0
    for char in text:
        if "0" <= char <= "9":
            digit = ord(char) - ord("0")
        elif "A" <= char <= "F":
            digit = ord(char) - ord("A") + 10
        elif "a" <= char <= "f":
            digit = ord(char) - ord("a") + 10
        else:
            raise ValueError(f"invalid hex token: {text}")
        value = (value << 4) | digit
        if value > 0xFFFFFFFFFFFFFFFF:
            raise ValueError(f"hex token overflows UInt64: {text}")
    return value


def _parse_stacktrace_map_fixture(
    text: str,
    *,
    preferred_base: int = 0,
) -> tuple[list[tuple[int, str]], list[tuple[int, str, int]]]:
    """Parse the subset of Delphi .map syntax used by StackTrace.pas fixtures."""
    lines = [line.strip() for line in text.splitlines()]
    segment_bases: dict[int, int] = {}
    symbols: list[tuple[int, str]] = []
    line_info: list[tuple[int, str, int]] = []
    in_publics_by_value = False
    in_line_numbers = False
    current_source = ""

    for line in lines[:16]:
        if len(line) <= 20 or line[4] != ":" or not line[0].isdigit():
            continue
        space = line.find(" ")
        if space < 0:
            continue
        rem = line[space + 1:].strip()
        len_token = rem.split()[0] if rem else ""
        if len_token.endswith("H"):
            segment_base = _parse_hex_uint64(line[5:space])
            if preferred_base and segment_base >= preferred_base:
                segment_base -= preferred_base
            segment_bases[int(line[:4], 16)] = segment_base

    def add_segment_addr(seg: int, offset_text: str) -> int | None:
        full_addr = segment_bases.get(seg, 0) + _parse_hex_uint64(offset_text)
        if full_addr > 0xFFFFFFFFFFFFFFFF:
            return None
        return full_addr

    for line in lines:
        if not line:
            continue
        if "Publics by Value" in line:
            in_publics_by_value = True
            in_line_numbers = False
            continue
        if line.startswith("Line numbers for "):
            in_publics_by_value = False
            in_line_numbers = True
            start = line.find("(")
            end = line.find(")")
            current_source = line[start + 1:end] if start >= 0 and end > start else ""
            continue

        if in_publics_by_value and line.startswith(("0001:", "0002:")):
            space = line.find(" ")
            if space < 0:
                continue
            name = line[space + 1:].strip()
            if not name or name.startswith("_"):
                continue
            addr = add_segment_addr(int(line[:4], 16), line[5:space])
            if addr is not None:
                symbols.append((addr, name))

        if in_line_numbers and current_source and line[0].isdigit():
            tokens = line.split()
            for index in range(0, len(tokens) - 1, 2):
                line_num_text = tokens[index]
                addr_text = tokens[index + 1]
                if not addr_text.startswith(("0001:", "0002:")):
                    continue
                addr = add_segment_addr(int(addr_text[:4], 16), addr_text[5:])
                if addr is not None:
                    line_info.append((addr, current_source, int(line_num_text)))

    return symbols, line_info


def test_stacktrace_callgraph_win64_enters_shared_scan_path():
    """Win64 callgraph should no longer fail closed now that MAPDATA stores 64-bit addresses."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    start = source.index("class procedure TStackTracer.ScanCallGraph;")
    end = source.index("class function TStackTracer.GetCallChain", start)
    scan_body = source[start:end]

    assert "if SizeOf(Pointer) <> SizeOf(DWORD) then" not in scan_body
    assert "FLastError := 'win64_not_supported';" not in scan_body
    assert "if not EnsureSymbols then begin" in scan_body
    assert "if not LoadTextRange then" in scan_body


def test_pe_text_fixture_parser_handles_pe32_and_pe32_plus():
    """The fixed PE fixtures should expose .text through SizeOfOptionalHeader offsets."""
    assert _parse_text_range_from_pe_fixture(
        _build_pe_text_fixture(pe32_plus=False)
    ) == (0x1000, 0x1234)
    assert _parse_text_range_from_pe_fixture(
        _build_pe_text_fixture(pe32_plus=True)
    ) == (0x1000, 0x1234)


def test_stacktrace_load_text_range_accepts_pe32_and_pe32_plus_headers():
    """LoadTextRange should distinguish PE32/PE32+ before walking sections."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    start = source.index("class function TStackTracer.LoadTextRange")
    end = source.index("class function TStackTracer.ResolveSymbolStart", start)
    body = source[start:end]

    assert "LOptionalMagic := PWord(@LNT.OptionalHeader)^;" in body
    assert "(LOptionalMagic <> $10B) and (LOptionalMagic <> $20B)" in body
    assert "FLastError := 'unsupported_optional_header';" in body
    assert "LNT.FileHeader.SizeOfOptionalHeader" in body
    assert "SizeOf(TImageOptionalHeader)" not in body


def test_mapdata_rva_conversion_distinguishes_runtime_module_base():
    """MAPDATA stores RVAs; runtime conversion should only add/remove the loaded module base."""
    runtime_base = 0x00007FF700000000
    map_rva = 0x23450
    runtime_addr = runtime_base + 0x23450

    assert _map_rva_to_runtime_addr(map_rva, runtime_base) == runtime_addr
    assert _runtime_addr_to_map_rva(runtime_addr, runtime_base) == map_rva
    assert _runtime_addr_to_map_rva(runtime_base - 1, runtime_base) == 0


def test_stacktrace_main_module_address_conversion_uses_rva_mapdata():
    """Main-module symbol paths should use normalized MAPDATA RVAs, not runtime address-model guesses."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    manager_start = source.index("TStackTraceManager = class")
    manager_decl_end = source.index("protected", manager_start)
    manager_decl = source[manager_start:manager_decl_end]
    helper_start = source.index("procedure TStackTraceManager.EnsureMainModuleBases")
    helper_end = source.index("{ ─────────────────────────────────────────────────────────────────────── }", helper_start)
    helper_body = source[helper_start:helper_end]

    assert "FPreferredBase: NativeUInt;" in manager_decl
    assert "function GetPEFilePreferredBase(const AExePath: string): UInt64;" in manager_decl
    assert "function MapAddrToRuntimeAddr(AMapAddr: UInt64): NativeUInt;" in manager_decl
    assert "function RuntimeAddrToMapAddr(ARuntimeAddr: NativeUInt): UInt64;" in manager_decl
    assert "FPreferredBase := GetModulePreferredBase(HMODULE(FModuleBase));" in helper_body
    assert "Result := FModuleBase + NativeUInt(AMapAddr);" in helper_body
    assert "Result := UInt64(ARuntimeAddr - FModuleBase);" in helper_body
    assert "MapDataUsesPreferredBase" not in source
    assert "FModuleBase + (LEntry.Addr - PreferredImageBase)" not in source
    assert "PreferredImageBase + (VA - FModuleBase)" not in source
    assert "FModuleBase + (LRva - PreferredImageBase)" not in source
    assert "FModuleBase + (FSymEntries" not in source
    assert "DWORD(PreferredImageBase + (AAddr - LBase))" not in source


def test_stacktrace_module_preferred_base_reads_disk_pe_header():
    """ASLR-mapped module headers must not be used as the PreferredBase source."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    start = source.index("function TStackTraceManager.GetModulePreferredBase")
    end = source.index("function TStackTraceManager.GetPEFilePreferredBase", start)
    body = source[start:end]

    assert "GetModuleFileName(hModule, LPath, Length(LPath))" in body
    assert "LPreferred := GetPEFilePreferredBase(string(LPath));" in body
    assert "pNt.OptionalHeader.ImageBase" not in body
    assert "PImageNtHeaders(PByte(hModule)" not in body


def test_stacktrace_symbol_name_caches_ignore_duplicate_symbols():
    """Duplicate MAP symbols should not make FindSymbolAddress raise EListError."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    main_start = source.index("procedure TStackTraceManager.BuildSymbolNameCache")
    main_end = source.index("function TStackTraceManager.FindSymbolAddress", main_start)
    main_body = source[main_start:main_end]
    module_start = source.index("procedure TStackTraceManager.LoadAllModuleSymbols")
    module_end = source.index("function TStackTraceManager.GetFunctionExtent", module_start)
    module_body = source[module_start:module_end]

    assert "not FSymNameCache.ContainsKey(LName)" in main_body
    assert "not LTable.NameCache.ContainsKey(LName)" in module_body
    assert "FSymNameCache.Add(LName, FSymEntries[I].Addr);" in main_body
    assert "LTable.NameCache.Add(LName, LRva);" in module_body


def test_map_fixture_parser_accepts_long_hex_offsets_with_uint64_model():
    """Win64-style long MAP hex fields should parse into UInt64 MAPDATA addresses."""
    map_text = """
0001:00000000F0000000 00002000H .text CODE
0002:0000000000001000 00000100H .idata DATA
Publics by Value
0001:0000000000001234 Unit.HighSymbol
0002:0000000000000020 Unit.ImportThunk
Line numbers for Unit(Unit.pas) segment .text
42 0001:0000000000001240 45 0002:0000000000000030
"""

    symbols, line_info = _parse_stacktrace_map_fixture(map_text)

    assert symbols == [
        (0xF0001234, "Unit.HighSymbol"),
        (0x00001020, "Unit.ImportThunk"),
    ]
    assert line_info == [
        (0xF0001240, "Unit.pas", 42),
        (0x00001030, "Unit.pas", 45),
    ]


def test_map_fixture_parser_accepts_real_win64_msbuild_addresses():
    """MAPDATA v12 stores UInt64 RVAs, so real Win64 MAP addresses must not truncate."""
    map_text = """
0001:0000000140001000 0016AA9CH .text CODE
0002:000000014016C000 00024D50H .data DATA
Publics by Value
0001:00162390 DaofyAutomation.RttiDiscovery..TRttiDiscoverer
0001:00164070 DaofyAutomation.RttiDiscovery.DaofyAutomation.RttiDiscovery
Line numbers for Unit(Unit.pas) segment .text
42 0001:00164080
"""

    symbols, line_info = _parse_stacktrace_map_fixture(map_text, preferred_base=0x0000000140000000)

    assert symbols == [
        (0x00163390, "DaofyAutomation.RttiDiscovery..TRttiDiscoverer"),
        (0x00165070, "DaofyAutomation.RttiDiscovery.DaofyAutomation.RttiDiscovery"),
    ]
    assert line_info == [
        (0x00165080, "Unit.pas", 42),
    ]


def test_stacktrace_parse_map_file_uses_uint64_address_storage():
    """ParseMapFile should avoid signed Integer parsing and DWORD truncation."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    start = source.index("function TStackTraceManager.ParseMapFile")
    end = source.index("procedure TStackTraceManager.TokenizeName", start)
    body = source[start:end]

    assert "LSegRvas: array[1..MAX_SEGMENTS] of UInt64;" in body
    assert "LPreferredBase := GetPEFilePreferredBase(ChangeFileExt(AMapPath, '.exe'));" in body
    assert "function TryParseHexUInt64(const AText: string; out AValue: UInt64): Boolean;" in body
    assert "function TrySegmentMapRva(ASegNum: Integer; AOffset: UInt64; out AAddr: UInt64): Boolean;" in body
    assert "LSegRvas[LSegNum] := LBaseAddr - LPreferredBase" in body
    assert "if LFullAddr > UInt64($FFFFFFFF) then" not in body
    assert "TryParseHexUInt64(LOffsetStr, LOffset)" in body
    assert "TryParseHexUInt64(LHexAddr, LOffset)" in body
    assert "TryStrToInt('$' + LOffsetStr" not in body
    assert "TryStrToInt('$' + LHexAddr" not in body
    assert "DWORD(LOffset)" not in body


def test_stacktrace_mapdata_v13_varint_uses_zigzag_int64_with_existing_names():
    """MAPDATA v13 should keep ReadVarInt/WriteVarInt names while using ZigZag Int64 payloads."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    serializer_start = source.index("TMapDataSerializer = class")
    serializer_end = source.index("public", serializer_start)
    serializer_decl = source[serializer_start:serializer_end]
    deserialize_start = source.index("class function TMapDataSerializer.Deserialize")
    deserialize_end = source.index("class function TMapDataSerializer.Serialize", deserialize_start)
    deserialize_body = source[deserialize_start:deserialize_end]
    serialize_start = source.index("class function TMapDataSerializer.Serialize")
    serialize_end = source.index("class function TMapDataSerializer.Validate", serialize_start)
    serialize_body = source[serialize_start:serialize_end]

    assert "MapResVersion = 13;" in source
    assert "class function WriteVarInt(AStream: TStream; Value: Int64): Integer; static;" in serializer_decl
    assert "class function ReadVarInt(AStream: TStream; out Value: Int64): Boolean; static;" in serializer_decl
    assert "class function TMapDataSerializer.EncodeZigZag(AValue: Int64): UInt64;" in source
    assert "class function TMapDataSerializer.DecodeZigZag(AValue: UInt64): Int64;" in source
    assert "WriteVarUInt64" not in source
    assert "ReadVarUInt64" not in source
    assert "WriteVarInt64" not in source
    assert "ReadVarInt64" not in source
    assert "if LVersion <> MapResVersion then" in deserialize_body
    assert "LVersion < 8" not in deserialize_body
    assert "LDelta: Int64;" in deserialize_body
    assert "LDelta: Int64;" in serialize_body
    assert "Integer(LAddr)" not in serialize_body
    assert "Integer(LCurAddr)" not in serialize_body


def test_stacktrace_mapdata_stack_offset_reads_signed_varint():
    """StackOffset is signed, so deserialization must not use the non-negative bounded reader."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    deserialize_start = source.index("class function TMapDataSerializer.Deserialize")
    deserialize_end = source.index("class function TMapDataSerializer.Serialize", deserialize_start)
    deserialize_body = source[deserialize_start:deserialize_end]
    location_start = deserialize_body.index("{ Read v13+ location data }")
    location_end = deserialize_body.index("var LFlags: Byte;", location_start)
    location_block = deserialize_body[location_start:location_end]

    assert "ReadVarInt(LStream, LStackOffRaw)" in location_block
    assert "LStackOffRaw < Low(Integer)" in location_block
    assert "LStackOffRaw > High(Integer)" in location_block
    assert "ReadBoundedInt" not in location_block


def test_stacktrace_mapdata_serializer_writes_per_symbol_token_indexes():
    """MAPDATA serialization must not compare global FirstToken with a per-symbol token array."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    serialize_start = source.index("class function TMapDataSerializer.Serialize")
    serialize_end = source.index("class function TMapDataSerializer.Validate", serialize_start)
    serialize_body = source[serialize_start:serialize_end]

    assert "if J < Length(LSavedTokens[I]) then" in serialize_body
    assert "LStart + J < Length(LSavedTokens[I])" not in serialize_body


def test_x64_e8_rel32_fixture_resolves_forward_and_backward_targets():
    """Fixed x64 E8 rel32 fixtures should resolve forward and backward call targets."""
    call_site = 0x00007FF700001000
    forward_target = 0x00007FF700002345
    backward_target = 0x00007FF6FFFFF100

    forward = _build_e8_rel32_fixture(call_site, forward_target)
    backward = _build_e8_rel32_fixture(call_site, backward_target)

    assert forward == b"\xE8" + (forward_target - (call_site + 5)).to_bytes(
        4, "little", signed=True
    )
    assert _resolve_e8_rel32_fixture_target(call_site, forward) == forward_target
    assert _resolve_e8_rel32_fixture_target(call_site, backward) == backward_target


def test_stacktrace_scan_uses_rel32_target_helper():
    """ScanCallGraph should use a single rel32 target helper for x86/x64 direct calls."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    decl_start = source.index("TStackTracer = class")
    decl_end = source.index("public", decl_start)
    declaration = source[decl_start:decl_end]
    helper_start = source.index("class function TStackTracer.ResolveRelativeCallTarget")
    helper_end = source.index("class procedure TStackTracer.ClearEdgeIndexes", helper_start)
    helper_body = source[helper_start:helper_end]
    scan_start = source.index("class procedure TStackTracer.ScanCallGraph;")
    scan_end = source.index("class function TStackTracer.GetCallChain", scan_start)
    scan_body = source[scan_start:scan_end]

    assert "class function ResolveRelativeCallTarget(ACallSite: NativeUInt; ARel32: Integer): NativeUInt; static;" in declaration
    assert "LNext := ACallSite + 5;" in helper_body
    assert "Result := LNext + NativeUInt(ARel32)" in helper_body
    assert "Result := LNext - NativeUInt(-Int64(ARel32));" in helper_body
    assert "LRel := PInteger(LCallSite + 1)^;" in scan_body
    assert "LTarget := ResolveRelativeCallTarget(LCallSite, LRel);" in scan_body
    assert "NativeUInt(Int64(LCallSite) + 5 + LRel)" not in scan_body


def test_callgraph_handler_serializes_runtime_error_code():
    """The automation extension must preserve TStackTracer.LastError in JSON data."""
    source = _read_repo_text("tools/auto/DaofyAutomation.CallGraph.pas")
    start = source.index("function HandleCallGraph")
    end = source.index("initialization", start)
    handler_body = source[start:end]

    assert "LastError := TStackTracer.LastError;" in handler_body
    assert "AddStringPair(JsonObj, 'error_code', LastError);" in handler_body
    assert "Status := 'err';" in handler_body


def test_stacktrace_callgraph_edges_capture_callsite_location():
    """Direct-call scan should store the call instruction address and source line."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    edge_start = source.index("TCallEdge = record")
    edge_end = source.index("TStackSnapshot = record", edge_start)
    edge_decl = source[edge_start:edge_end]
    scan_start = source.index("class procedure TStackTracer.ScanCallGraph;")
    scan_end = source.index("class function TStackTracer.GetCallChain", scan_start)
    scan_body = source[scan_start:scan_end]

    assert "CallerAddr: NativeUInt;" in edge_decl
    assert "CalleeAddr: NativeUInt;" in edge_decl
    assert "CallAddr: NativeUInt;" in edge_decl
    assert "CallFile: string;" in edge_decl
    assert "CallLine: Integer;" in edge_decl
    assert "LEdge.CallerAddr := LCallerStart;" in scan_body
    assert "LEdge.CalleeAddr := LCalleeStart;" in scan_body
    assert "LEdge.CallAddr := LCallSite;" in scan_body
    assert "ResolveSourceLine(LCallSite, LEdge.CallFile, LEdge.CallLine);" in scan_body


def test_callgraph_source_line_resolution_uses_manager_api():
    """Callgraph should use the manager-owned line resolver instead of private tables."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    manager_decl_start = source.index("TStackTraceManager = class")
    manager_decl_end = source.index("TStackSnapshot = record", manager_decl_start)
    manager_decl = source[manager_decl_start:manager_decl_end]
    manager_impl_start = source.index("function TStackTraceManager.TryResolveSourceLine")
    manager_impl_end = source.index("procedure TStackTraceManager.EmbedFinalize", manager_impl_start)
    manager_impl = source[manager_impl_start:manager_impl_end]
    tracer_decl_start = source.index("TStackTracer = class")
    tracer_decl_end = source.index("public", tracer_decl_start)
    tracer_decl = source[tracer_decl_start:tracer_decl_end]
    scan_start = source.index("class procedure TStackTracer.ScanCallGraph;")
    scan_end = source.index("class function TStackTracer.GetCallChain", scan_start)
    scan_body = source[scan_start:scan_end]

    assert "function TryResolveSourceLine(VA: NativeUInt; out AFile: string; out ALine: Integer): Boolean;" in manager_decl
    assert "FLineEntries" in manager_impl
    assert "FSourcePaths" in manager_impl
    assert "ResolveSourceLine" not in tracer_decl
    assert "LManager.TryResolveSourceLine(LCallSite, LEdge.CallFile, LEdge.CallLine)" in scan_body
    assert "FLineEntries" not in scan_body
    assert "FSourcePaths" not in scan_body


def test_stacktrace_callgraph_runtime_addresses_use_nativeuint():
    """W64-1 should remove 32-bit truncation from runtime callgraph address paths."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    decl_start = source.index("TStackTracer = class")
    decl_end = source.index("public", decl_start)
    declaration = source[decl_start:decl_end]
    find_start = source.index("class function TStackTracer.FindFuncAddr")
    index_start = source.index("class procedure TStackTracer.AddEdgeIndex", find_start)
    find_body = source[find_start:index_start]
    scan_start = source.index("class procedure TStackTracer.ScanCallGraph;")
    call_start = source.index("class function TStackTracer.GetCallChain", scan_start)
    caller_start = source.index("class function TStackTracer.GetCallerChain", call_start)
    json_start = source.index("class function TStackTracer.CallChainToJSON", caller_start)
    scan_body = source[scan_start:call_start]
    call_body = source[call_start:caller_start]
    caller_body = source[caller_start:json_start]
    json_body = source[json_start:source.index("{$ENDIF}", json_start)]

    assert "TEdgeIndex = TDictionary<NativeUInt, TList<Integer>>;" in declaration
    assert "class function FindFuncAddr(const AName: string): NativeUInt; static;" in declaration
    assert "class procedure AddEdgeIndex(AIndex: TEdgeIndex; AAddr: NativeUInt;" in declaration
    assert "Exit(DWORD(FSymbols[I].Address))" not in find_body
    assert "LEdge.CallerAddr := DWORD(" not in scan_body
    assert "LEdge.CalleeAddr := DWORD(" not in scan_body
    assert "LEdge.CallAddr := DWORD(" not in scan_body
    assert "TList<DWORD>" not in call_body
    assert "TQueue<DWORD>" not in call_body
    assert "TDictionary<DWORD, Integer>" not in call_body
    assert "TList<DWORD>" not in caller_body
    assert "TQueue<DWORD>" not in caller_body
    assert "TDictionary<DWORD, Integer>" not in caller_body
    assert "FormatCallGraphAddr(AChain[I].CallerAddr)" in json_body
    assert "Format('%.8x', [AChain[I]" not in json_body


def test_stacktrace_callgraph_json_includes_callsite_fields():
    """Callgraph JSON should expose call_addr/call_file/call_line for audit navigation."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    start = source.index("class function TStackTracer.CallChainToJSON")
    end = source.index("{$ENDIF}", start)
    json_body = source[start:end]

    assert "LObj.AddPair('call_addr'" in json_body
    assert "LObj.AddPair('call_file'" in json_body
    assert "LObj.AddPair('call_line'" in json_body
    assert "FormatCallGraphAddr(AChain[I].CallAddr)" in json_body


def test_callgraph_json_includes_categories_and_include_filtering():
    """Automation callgraph JSON should classify edges and expose include filters."""
    source = _read_repo_text("tools/auto/DaofyAutomation.CallGraph.pas")
    edge_start = source.index("function EdgeToJSON")
    edge_end = source.index("function PathToJSON", edge_start)
    edge_body = source[edge_start:edge_end]
    filter_start = source.index("function FilterChain")
    filter_end = source.index("function ApplyEdgeLimit", filter_start)
    filter_body = source[filter_start:filter_end]
    handler_start = source.index("function HandleCallGraph")
    handler_end = source.index("function HandleCallGraphPath", handler_start)
    handler_body = source[handler_start:handler_end]

    assert "Result.AddPair('from_category', FromCategory);" in edge_body
    assert "Result.AddPair('to_category', ToCategory);" in edge_body
    assert "Result.AddPair('category', ToCategory);" in edge_body
    assert "FormatCallGraphAddr(AEdge.CallAddr)" in edge_body
    assert "EdgeIncluded(Edge, AIncludePrefixes)" in filter_body
    assert "IncludePrefixes := BuildPrefixes" in handler_body
    assert "JsonObj.AddPair('include_prefixes', PrefixesToJSON(IncludePrefixes));" in handler_body


def test_callgraph_output_dedupe_preserves_distinct_callsites():
    """Automation-layer de-dupe must not merge separate call instructions on the same edge."""
    source = _read_repo_text("tools/auto/DaofyAutomation.CallGraph.pas")
    start = source.index("function EdgeSame")
    end = source.index("function EdgeExists", start)
    edge_same = source[start:end]

    assert "ALeft.CallAddr = ARight.CallAddr" in edge_same


def test_callgraph_path_handler_is_registered_and_serializes_paths():
    """The automation extension should expose bounded source-to-target path queries."""
    source = _read_repo_text("tools/auto/DaofyAutomation.CallGraph.pas")
    start = source.index("function HandleCallGraphPath")
    end = source.index("initialization", start)
    handler_body = source[start:end]

    assert "TAutomationProcessorBase.RegisterCommandHandler('callgraph_path'" in source
    assert "TAutomationProcessorBase.UnregisterCommandHandler('callgraph_path')" in source
    assert "JsonObj.AddPair('found'" in handler_body
    assert "JsonObj.AddPair('paths', PathsToJSON(Paths));" in handler_body
    assert "JsonObj.AddPair('path_count'" in handler_body
    assert "FindCallPaths(Chain, SourceValue, TargetValue" in handler_body


def test_callgraph_path_depth_zero_does_not_traverse_edges():
    """Depth zero path queries should only allow the source==target empty path."""
    source = _read_repo_text("tools/auto/DaofyAutomation.CallGraph.pas")
    start = source.index("function FindCallPaths")
    end = source.index("function PathsToJSON", start)
    path_body = source[start:end]

    assert "if AMaxDepth <= 0 then begin" in path_body
    assert path_body.index("if AMaxDepth <= 0 then begin") < path_body.index(
        "for Edge in AEdges do begin"
    )


def test_stacktrace_callgraph_queries_use_edge_indexes():
    """BFS queries should use caller/callee edge indexes instead of scanning all edges."""
    source = _read_repo_text("tools/stacktrace/StackTrace.pas")
    decl_start = source.index("TStackTracer = class")
    decl_end = source.index("public", decl_start)
    declaration = source[decl_start:decl_end]
    scan_start = source.index("class procedure TStackTracer.ScanCallGraph;")
    call_start = source.index("class function TStackTracer.GetCallChain", scan_start)
    caller_start = source.index("class function TStackTracer.GetCallerChain", call_start)
    json_start = source.index("class function TStackTracer.CallChainToJSON", caller_start)
    scan_body = source[scan_start:call_start]
    call_body = source[call_start:caller_start]
    caller_body = source[caller_start:json_start]

    assert "FCallerIndex: TEdgeIndex;" in declaration
    assert "FCalleeIndex: TEdgeIndex;" in declaration
    assert "BuildEdgeIndexes;" in scan_body
    assert "FCallerIndex.TryGetValue(LCurr, LEdgeIndexes)" in call_body
    assert "FCalleeIndex.TryGetValue(LCurr, LEdgeIndexes)" in caller_body
    assert "for I := 0 to High(FCallEdges)" not in call_body
    assert "for I := 0 to High(FCallEdges)" not in caller_body
