unit DaofyAutomation.IATHook;

{===============================================================================
  DaofyAutomation.IATHook - 自实现 IAT Hook 库

  纯 Win32 API，无第三方依赖（不依赖 ImageHlp/DbgHelp）。通过修改进程
  导入表（IAT）项指向 hook 函数，实现 GDI/GDI+ 函数拦截。

  特点：
    - 不修改函数字节（比 inline hook 更稳定、更隐蔽）
    - 不依赖 ImageHlp/DbgHelp（自解析 PE 头）
    - 支持多模块 hook（遍历 exe + 所有已加载 bpl/dll）
    - 可逆（析构时恢复 IAT 原值）

  用法：
    var H := TMultiIATHook.Create('gdi32.dll', 'ExtTextOutW', @MyHook);
    try
      // hook 生效期间操作，FTramp 保存原函数地址
    finally
      H.Free;  // 恢复原 IAT
    end;
===============================================================================}

interface

uses
  System.SysUtils,
  System.Generics.Collections,
  Winapi.Windows,
  Winapi.TlHelp32;

type
  /// <summary>
  ///  IAT hook 单条记录。修改单个模块的 IAT 中的一个函数项。
  /// </summary>
  TIATHook = class
  private
    FModule: HMODULE;
    FIATEntry: PPointer; // 修改的 IAT 表项指针
    FOriginalFunc: Pointer; // 原函数地址（trampoline）
    FHookFunc: Pointer; // hook 函数地址
    FApplied: Boolean; // 是否成功应用
  public
    constructor Create(AModule: HMODULE; const ADllName, AFuncName: string; AHookFunc: Pointer);
    destructor Destroy; override;
    property Original: Pointer read FOriginalFunc;
    property Applied: Boolean read FApplied;
  end;

  /// <summary>
  ///  多模块 IAT hook。遍历当前进程所有已加载模块（exe + bpl + dll），
  ///  对每个模块的 IAT 都 hook，覆盖使用运行时包的 Delphi 应用。
  /// </summary>
  TMultiIATHook = class
  private
    FHooks: TList<TIATHook>;
    FTramp: Pointer; // 任一 hook 的 Original 都可作 trampoline
  public
    constructor Create(const ADllName, AFuncName: string; AHookFunc: Pointer);
    destructor Destroy; override;
    property Trampoline: Pointer read FTramp;
  end;

implementation

{ ── PE 头解析辅助（A12：不依赖 ImageHlp，自解析） ── }

/// 从模块基址找到 IMAGE_DIRECTORY_ENTRY_IMPORT 目录
function GetImportDirectory(AModule: HMODULE; out ASize: Cardinal): PImageImportDescriptor;
var
  DOSHeader: PImageDosHeader;
  NTHeaders: PImageNtHeaders;
  DataDir: PImageDataDirectory;
begin
  Result := nil;
  ASize := 0;
  if AModule = 0 then
    Exit;

  DOSHeader := PImageDosHeader(AModule);
  if DOSHeader^.e_magic <> IMAGE_DOS_SIGNATURE then
    Exit;
  if DWORD(DOSHeader^._lfanew) = 0 then
    Exit;

  NTHeaders := PImageNtHeaders(AModule + DWORD(DOSHeader^._lfanew));
  if NTHeaders^.Signature <> IMAGE_NT_SIGNATURE then
    Exit;

  DataDir := @NTHeaders^.OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
  if DataDir^.VirtualAddress = 0 then
    Exit;

  ASize := DataDir^.Size;
  Result := PImageImportDescriptor(AModule + DataDir^.VirtualAddress);
end;

{ ── TIATHook ── }

constructor TIATHook.Create(AModule: HMODULE; const ADllName, AFuncName: string; AHookFunc: Pointer);
var
  Size: Cardinal;
  ImportDesc: PImageImportDescriptor;
  IATEntry: PPointer;
  NameEntry: PImageThunkData;
  OldProtect: DWORD;
  FuncNameUpper, DllNameUpper: string;
  ImportByName: PImageImportByName;
begin
  FModule := AModule;
  FHookFunc := AHookFunc;
  FApplied := False;

  DllNameUpper := AnsiUpperCase(ADllName);
  FuncNameUpper := AnsiUpperCase(AFuncName);

  ImportDesc := GetImportDirectory(AModule, Size);
  if ImportDesc = nil then
    Exit;

  while ImportDesc^.Name <> 0 do begin
    if AnsiUpperCase(string(PAnsiChar(AModule + ImportDesc^.Name))) = DllNameUpper then begin
      IATEntry := PPointer(AModule + ImportDesc^.FirstThunk);
      // INT（OriginalFirstThunk）保存函数名 hint/name，用于按名查找
      if ImportDesc^.OriginalFirstThunk <> 0 then
        NameEntry := PImageThunkData(AModule + ImportDesc^.OriginalFirstThunk)
      else
        NameEntry := PImageThunkData(AModule + ImportDesc^.FirstThunk);

      while IATEntry^ <> nil do begin
        // 检查是否按名导入（非按序号）
        if (NameEntry^.Ordinal and IMAGE_ORDINAL_FLAG) = 0 then begin
          ImportByName := PImageImportByName(AModule + NameEntry^.AddressOfData);
          if AnsiUpperCase(string(PAnsiChar(@ImportByName^.Name))) = FuncNameUpper then begin
            FIATEntry := IATEntry;
            FOriginalFunc := IATEntry^;

            VirtualProtect(IATEntry, SizeOf(Pointer), PAGE_READWRITE, OldProtect);
            IATEntry^ := AHookFunc;
            VirtualProtect(IATEntry, SizeOf(Pointer), OldProtect, OldProtect);

            FApplied := True;
            Exit;
          end;
        end;
        Inc(IATEntry);
        Inc(NameEntry);
      end;
    end;
    Inc(ImportDesc);
  end;
  // 未找到目标导入项（模块未导入该函数）
end;

destructor TIATHook.Destroy;
var
  OldProtect: DWORD;
begin
  if FApplied and (FIATEntry <> nil) then begin
    VirtualProtect(FIATEntry, SizeOf(Pointer), PAGE_READWRITE, OldProtect);
    FIATEntry^ := FOriginalFunc;
    VirtualProtect(FIATEntry, SizeOf(Pointer), OldProtect, OldProtect);
    FApplied := False;
  end;
  inherited;
end;

{ ── TMultiIATHook ── }

constructor TMultiIATHook.Create(const ADllName, AFuncName: string; AHookFunc: Pointer);
var
  Snap: THandle;
  ME: TModuleEntry32;
  Hook: TIATHook;
begin
  FHooks := TList<TIATHook>.Create;

  Snap := CreateToolhelp32Snapshot(TH32CS_SNAPMODULE, GetCurrentProcessId);
  if Snap <> INVALID_HANDLE_VALUE then
    try
      ME.dwSize := SizeOf(ME);
      if Module32First(Snap, ME) then
        repeat
          Hook := TIATHook.Create(ME.hModule, ADllName, AFuncName, AHookFunc);
          if Hook.Applied then begin
            if FTramp = nil then
              FTramp := Hook.Original; // 同一函数在所有模块地址相同
            FHooks.Add(Hook);
          end
          else
            Hook.Free;
        until not Module32Next(Snap, ME);
    finally
      CloseHandle(Snap);
    end;
end;

destructor TMultiIATHook.Destroy;
var
  H: TIATHook;
begin
  for H in FHooks do
    H.Free;
  FHooks.Free;
  inherited;
end;

end.
