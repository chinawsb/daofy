# .dproj Generated Structure Comparison Report

**Generated**: 2026-05-21 10:56:37
**Generator**: `_handle_create` from `src.tools.dproj_tool`
**Parser**: `DprojParser` from `src.utils.dproj_parser`


================================================================================
## Project Type: VCL App
**File**: `C:\Users\swish\AppData\Local\Temp\dproj_test_xl0e9nak\VCLApp.dproj`
**Generator Result**: ✅ 已创建 .dproj 文件: C:\Users\swish\AppData\Local\Temp\dproj_test_xl0e9nak\VCLApp.dproj

**Parsed Info**:
- ProjectGUID: {F0B84951-C286-4C90-8CD2-35D009BA7234}
- ProjectVersion: 18.2
- FrameworkType: VCL
- AppType: Application
- MainSource: VCLApp.dpr
- TargetedPlatforms: 3
## PropertyGroup Hierarchy
Total PGs: 11
### Shared Property Groups
### BT_BuildType (k)
### Console Target (j)
### DCC_DCCCompiler (r)
### ItemGroup Elements
### ProjectExtensions
### Import Elements

### Raw XML Element Inventory
| Level | Tag | Condition/Attr |
|-------|-----|----------------|
|   PropertyGroup |  |
|     ProjectGuid |  → `{F0B84951-C286-4C90-8CD2-35D009BA7234}` |
|     MainSource |  → `VCLApp.dpr` |
|     Config | Condition="'$(Config)'==''" → `Debug` |
|     ProjectVersion |  → `18.2` |
|     Base |  → `True` |
|     AppType |  → `Application` |
|     FrameworkType |  → `VCL` |
|     Platform | Condition="'$(Platform)'==''" → `Win32` |
|     TargetedPlatforms |  → `3` |
|   PropertyGroup | Condition="'$(Config)'=='Base' or '$(Base)'!=''" |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Base)'=='true') or '$(Base_Win32)'!=''" |
|     Base_Win32 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Config)'=='Debug' or '$(Cfg_1)'!=''" |
|     Cfg_1 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Cfg_1)'=='true') or '$(Cfg_1_Win32)'!=''" |
|     Cfg_1_Win32 |  → `true` |
|     CfgParent |  → `Cfg_1` |
|     Cfg_1 |  → `true` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Config)'=='Release' or '$(Cfg_2)'!=''" |
|     Cfg_2 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Cfg_2)'=='true') or '$(Cfg_2_Win32)'!=''" |
|     Cfg_2_Win32 |  → `true` |
|     CfgParent |  → `Cfg_2` |
|     Cfg_2 |  → `true` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Base)'!=''" |
|     SanitizedProjectName |  → `VCLApp` |
|     DCC_Namespace |  → `System;System.Win;Winapi;Vcl;Vcl.Forms` |
|     DCC_DcuOutput |  → `.\$(Platform)\$(Config)` |
|     DCC_ExeOutput |  → `.\$(Platform)\$(Config)` |
|     DCC_E |  → `false` |
|     DCC_N |  → `false` |
|     DCC_S |  → `false` |
|     DCC_F |  → `false` |
|     DCC_K |  → `false` |
|   PropertyGroup | Condition="'$(Base_Win32)'!=''" |
|     AppEnableRuntimeThemes |  → `true` |
|     Manifest_File |  → `$(BDS)\bin\default_app.manifest` |
|     DCC_Namespace |  → `Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml` |
|   PropertyGroup | Condition="'$(Cfg_1)'!=''" |
|     DCC_Define |  → `DEBUG;$(DCC_Define)` |
|     DCC_DebugDCUs |  → `true` |
|     DCC_Optimize |  → `false` |
|     DCC_GenerateStackFrames |  → `true` |
|     DCC_DebugInfoInExe |  → `true` |
|   PropertyGroup | Condition="'$(Cfg_2)'!=''" |
|     DCC_LocalDebugSymbols |  → `false` |
|     DCC_Define |  → `RELEASE;$(DCC_Define)` |
|     DCC_SymbolReferenceInfo |  → `0` |
|     DCC_DebugInformation |  → `0` |
|   ItemGroup |  |
|     DelphiCompile | Include="$(MainSource)" |
|       MainSource |  → `MainSource` |
|     BuildConfiguration | Include="Base" |
|       Key |  → `Base` |
|     BuildConfiguration | Include="Debug" |
|       Key |  → `Cfg_1` |
|       CfgParent |  → `Base` |
|     BuildConfiguration | Include="Release" |
|       Key |  → `Cfg_2` |
|       CfgParent |  → `Base` |
|   ProjectExtensions |  |
|     Borland.Personality |  → `Delphi.Personality.12` |
|     Borland.ProjectType |  → `Application` |
|     BorlandProject |  |
|       Delphi.Personality |  |
|         Source |  |
|           Source |  → `VCLApp.dpr` |
|       Platforms |  |
|         Platform |  → `True` |
|         Platform |  → `True` |
|     ProjectFileVersion |  → `12` |
|   Import | Condition="Exists('$(BDS)\Bin\CodeGear.Delphi.Targets')" |
|   Import | Condition="Exists('$(APPDATA)\Embarcadero\$(BDSAPPDATABASEDIR)\$(PRODUCTVERSION)\UserTools." |
|   Import | Condition="Exists('$(MSBuildProjectName).deployproj')" |

### Summary for this project type
❌ **7 missing element(s)**
    ❌ c) Base_Win64 PG: `Base_Win64` missing
    ❌ f) Cfg_1_Win64 PG: `Cfg_1_Win64` missing
    ❌ i) Cfg_2_Win64 PG: `Cfg_2_Win64` missing
    ❌ BT_BuildType in `Cfg_1` not found (PG matched but element missing)
    ❌ BT_BuildType in `Cfg_1_Win32` not found (PG matched but element missing)
    ❌ DCC_ConsoleTarget in `Cfg_1` not found (PG matched but element missing)
    ❌ DCC_ConsoleTarget in `Cfg_1_Win32` not found (PG matched but element missing)

✅ 24 elements correctly present.

================================================================================
## Project Type: FMX App
**File**: `C:\Users\swish\AppData\Local\Temp\dproj_test_xl0e9nak\FMXApp.dproj`
**Generator Result**: ✅ 已创建 .dproj 文件: C:\Users\swish\AppData\Local\Temp\dproj_test_xl0e9nak\FMXApp.dproj

**Parsed Info**:
- ProjectGUID: {D3FA5C73-F302-4417-85CC-341A027DDEC8}
- ProjectVersion: 18.2
- FrameworkType: FMX
- AppType: Application
- MainSource: FMXApp.dpr
- TargetedPlatforms: 3
## PropertyGroup Hierarchy
Total PGs: 11
### Shared Property Groups
### BT_BuildType (k)
### Console Target (j)
### DCC_DCCCompiler (r)
### ItemGroup Elements
### ProjectExtensions
### Import Elements

### Raw XML Element Inventory
| Level | Tag | Condition/Attr |
|-------|-----|----------------|
|   PropertyGroup |  |
|     ProjectGuid |  → `{D3FA5C73-F302-4417-85CC-341A027DDEC8}` |
|     MainSource |  → `FMXApp.dpr` |
|     Config | Condition="'$(Config)'==''" → `Debug` |
|     ProjectVersion |  → `18.2` |
|     Base |  → `True` |
|     AppType |  → `Application` |
|     FrameworkType |  → `FMX` |
|     Platform | Condition="'$(Platform)'==''" → `Win32` |
|     TargetedPlatforms |  → `3` |
|   PropertyGroup | Condition="'$(Config)'=='Base' or '$(Base)'!=''" |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Base)'=='true') or '$(Base_Win32)'!=''" |
|     Base_Win32 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Config)'=='Debug' or '$(Cfg_1)'!=''" |
|     Cfg_1 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Cfg_1)'=='true') or '$(Cfg_1_Win32)'!=''" |
|     Cfg_1_Win32 |  → `true` |
|     CfgParent |  → `Cfg_1` |
|     Cfg_1 |  → `true` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Config)'=='Release' or '$(Cfg_2)'!=''" |
|     Cfg_2 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Cfg_2)'=='true') or '$(Cfg_2_Win32)'!=''" |
|     Cfg_2_Win32 |  → `true` |
|     CfgParent |  → `Cfg_2` |
|     Cfg_2 |  → `true` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Base)'!=''" |
|     SanitizedProjectName |  → `FMXApp` |
|     DCC_Namespace |  → `System;System.Win;Winapi;FMX;FMX.Forms` |
|     DCC_DcuOutput |  → `.\$(Platform)\$(Config)` |
|     DCC_ExeOutput |  → `.\$(Platform)\$(Config)` |
|     DCC_E |  → `false` |
|     DCC_N |  → `false` |
|     DCC_S |  → `false` |
|     DCC_F |  → `false` |
|     DCC_K |  → `false` |
|   PropertyGroup | Condition="'$(Base_Win32)'!=''" |
|     AppEnableRuntimeThemes |  → `true` |
|     Manifest_File |  → `$(BDS)\bin\default_app.manifest` |
|     DCC_Namespace |  → `Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml` |
|   PropertyGroup | Condition="'$(Cfg_1)'!=''" |
|     DCC_Define |  → `DEBUG;$(DCC_Define)` |
|     DCC_DebugDCUs |  → `true` |
|     DCC_Optimize |  → `false` |
|     DCC_GenerateStackFrames |  → `true` |
|     DCC_DebugInfoInExe |  → `true` |
|   PropertyGroup | Condition="'$(Cfg_2)'!=''" |
|     DCC_LocalDebugSymbols |  → `false` |
|     DCC_Define |  → `RELEASE;$(DCC_Define)` |
|     DCC_SymbolReferenceInfo |  → `0` |
|     DCC_DebugInformation |  → `0` |
|   ItemGroup |  |
|     DelphiCompile | Include="$(MainSource)" |
|       MainSource |  → `MainSource` |
|     BuildConfiguration | Include="Base" |
|       Key |  → `Base` |
|     BuildConfiguration | Include="Debug" |
|       Key |  → `Cfg_1` |
|       CfgParent |  → `Base` |
|     BuildConfiguration | Include="Release" |
|       Key |  → `Cfg_2` |
|       CfgParent |  → `Base` |
|   ProjectExtensions |  |
|     Borland.Personality |  → `Delphi.Personality.12` |
|     Borland.ProjectType |  → `Application` |
|     BorlandProject |  |
|       Delphi.Personality |  |
|         Source |  |
|           Source |  → `FMXApp.dpr` |
|       Platforms |  |
|         Platform |  → `True` |
|         Platform |  → `True` |
|     ProjectFileVersion |  → `12` |
|   Import | Condition="Exists('$(BDS)\Bin\CodeGear.Delphi.Targets')" |
|   Import | Condition="Exists('$(APPDATA)\Embarcadero\$(BDSAPPDATABASEDIR)\$(PRODUCTVERSION)\UserTools." |
|   Import | Condition="Exists('$(MSBuildProjectName).deployproj')" |

### Summary for this project type
❌ **7 missing element(s)**
    ❌ c) Base_Win64 PG: `Base_Win64` missing
    ❌ f) Cfg_1_Win64 PG: `Cfg_1_Win64` missing
    ❌ i) Cfg_2_Win64 PG: `Cfg_2_Win64` missing
    ❌ BT_BuildType in `Cfg_1` not found (PG matched but element missing)
    ❌ BT_BuildType in `Cfg_1_Win32` not found (PG matched but element missing)
    ❌ DCC_ConsoleTarget in `Cfg_1` not found (PG matched but element missing)
    ❌ DCC_ConsoleTarget in `Cfg_1_Win32` not found (PG matched but element missing)

✅ 24 elements correctly present.

================================================================================
## Project Type: Console App
**File**: `C:\Users\swish\AppData\Local\Temp\dproj_test_xl0e9nak\ConsoleApp.dproj`
**Generator Result**: ✅ 已创建 .dproj 文件: C:\Users\swish\AppData\Local\Temp\dproj_test_xl0e9nak\ConsoleApp.dproj

**Parsed Info**:
- ProjectGUID: {0943FCE2-A866-4ED3-ABA0-46269C4BD756}
- ProjectVersion: 18.2
- FrameworkType: None
- AppType: Console
- MainSource: ConsoleApp.dpr
- TargetedPlatforms: 3
## PropertyGroup Hierarchy
Total PGs: 11
### Console Target (j)
### DCC_DCCCompiler (r)
### BT_BuildType (k)
### ItemGroup Elements
### ProjectExtensions
### Import Elements

### Raw XML Element Inventory
| Level | Tag | Condition/Attr |
|-------|-----|----------------|
|   PropertyGroup |  |
|     ProjectGuid |  → `{0943FCE2-A866-4ED3-ABA0-46269C4BD756}` |
|     MainSource |  → `ConsoleApp.dpr` |
|     Config | Condition="'$(Config)'==''" → `Debug` |
|     ProjectVersion |  → `18.2` |
|     Base |  → `True` |
|     AppType |  → `Console` |
|     FrameworkType |  → `None` |
|     Platform | Condition="'$(Platform)'==''" → `Win32` |
|     TargetedPlatforms |  → `3` |
|     DCC_DCCCompiler |  → `DCC32` |
|   PropertyGroup | Condition="'$(Config)'=='Base' or '$(Base)'!=''" |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Base)'=='true') or '$(Base_Win32)'!=''" |
|     Base_Win32 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Config)'=='Debug' or '$(Cfg_1)'!=''" |
|     Cfg_1 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Cfg_1)'=='true') or '$(Cfg_1_Win32)'!=''" |
|     Cfg_1_Win32 |  → `true` |
|     CfgParent |  → `Cfg_1` |
|     Cfg_1 |  → `true` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Config)'=='Release' or '$(Cfg_2)'!=''" |
|     Cfg_2 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Cfg_2)'=='true') or '$(Cfg_2_Win32)'!=''" |
|     Cfg_2_Win32 |  → `true` |
|     CfgParent |  → `Cfg_2` |
|     Cfg_2 |  → `true` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Base)'!=''" |
|     SanitizedProjectName |  → `ConsoleApp` |
|     DCC_Namespace |  → `System;Xml;Data;Datasnap;Web;Soap` |
|     DCC_DcuOutput |  → `.\$(Platform)\$(Config)` |
|     DCC_ExeOutput |  → `.\$(Platform)\$(Config)` |
|     DCC_E |  → `false` |
|     DCC_N |  → `false` |
|     DCC_S |  → `false` |
|     DCC_F |  → `false` |
|     DCC_K |  → `false` |
|   PropertyGroup | Condition="'$(Base_Win32)'!=''" |
|     DCC_Namespace |  → `Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml` |
|   PropertyGroup | Condition="'$(Cfg_1)'!=''" |
|     DCC_Define |  → `DEBUG;$(DCC_Define)` |
|     DCC_DebugDCUs |  → `true` |
|     DCC_Optimize |  → `false` |
|     DCC_GenerateStackFrames |  → `true` |
|     DCC_DebugInfoInExe |  → `true` |
|   PropertyGroup | Condition="'$(Cfg_2)'!=''" |
|     DCC_LocalDebugSymbols |  → `false` |
|     DCC_Define |  → `RELEASE;$(DCC_Define)` |
|     DCC_SymbolReferenceInfo |  → `0` |
|     DCC_DebugInformation |  → `0` |
|   ItemGroup |  |
|     DelphiCompile | Include="$(MainSource)" |
|       MainSource |  → `MainSource` |
|     BuildConfiguration | Include="Base" |
|       Key |  → `Base` |
|     BuildConfiguration | Include="Debug" |
|       Key |  → `Cfg_1` |
|       CfgParent |  → `Base` |
|     BuildConfiguration | Include="Release" |
|       Key |  → `Cfg_2` |
|       CfgParent |  → `Base` |
|   ProjectExtensions |  |
|     Borland.Personality |  → `Delphi.Personality.12` |
|     Borland.ProjectType |  → `Console` |
|     BorlandProject |  |
|       Delphi.Personality |  |
|         Source |  |
|           Source |  → `ConsoleApp.dpr` |
|       Platforms |  |
|         Platform |  → `True` |
|         Platform |  → `True` |
|     ProjectFileVersion |  → `12` |
|   Import | Condition="Exists('$(BDS)\Bin\CodeGear.Delphi.Targets')" |
|   Import | Condition="Exists('$(APPDATA)\Embarcadero\$(BDSAPPDATABASEDIR)\$(PRODUCTVERSION)\UserTools." |
|   Import | Condition="Exists('$(MSBuildProjectName).deployproj')" |

### Summary for this project type
❌ **7 missing element(s)**
    ❌ c) Base_Win64 PG: `Base_Win64` missing
    ❌ f) Cfg_1_Win64 PG: `Cfg_1_Win64` missing
    ❌ i) Cfg_2_Win64 PG: `Cfg_2_Win64` missing
    ❌ DCC_ConsoleTarget in `Cfg_1` not found (PG matched but element missing)
    ❌ DCC_ConsoleTarget in `Cfg_2` not found (PG matched but element missing)
    ❌ DCC_ConsoleTarget in `'$(Base)'` not found (PG matched but element missing)
    ❌ BT_BuildType in `Cfg_1_Win32` not found (PG matched but element missing)

✅ 18 elements correctly present.

================================================================================
## Project Type: Package
**File**: `C:\Users\swish\AppData\Local\Temp\dproj_test_xl0e9nak\Package.dproj`
**Generator Result**: ✅ 已创建 .dproj 文件: C:\Users\swish\AppData\Local\Temp\dproj_test_xl0e9nak\Package.dproj

**Parsed Info**:
- ProjectGUID: {F225CD61-5681-4C5B-8B97-915EBFEC32D0}
- ProjectVersion: 18.2
- FrameworkType: VCL
- AppType: Package
- MainSource: Package.dpr
- TargetedPlatforms: 3
## PropertyGroup Hierarchy
Total PGs: 9
### Package-specific Properties (p)
### DCC_DCCCompiler (r)
### ProjectExtensions
### Import Elements
### ItemGroup Elements

### Raw XML Element Inventory
| Level | Tag | Condition/Attr |
|-------|-----|----------------|
|   PropertyGroup |  |
|     ProjectGuid |  → `{F225CD61-5681-4C5B-8B97-915EBFEC32D0}` |
|     MainSource |  → `Package.dpr` |
|     Config | Condition="'$(Config)'==''" → `Debug` |
|     ProjectVersion |  → `18.2` |
|     Base |  → `True` |
|     AppType |  → `Package` |
|     FrameworkType |  → `VCL` |
|     Platform | Condition="'$(Platform)'==''" → `Win32` |
|     TargetedPlatforms |  → `3` |
|   PropertyGroup | Condition="'$(Config)'=='Base' or '$(Base)'!=''" |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Config)'=='Debug' or '$(Cfg_1)'!=''" |
|     Cfg_1 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Config)'=='Release' or '$(Cfg_2)'!=''" |
|     Cfg_2 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Cfg_2)'=='true') or '$(Cfg_2_Win32)'!=''" |
|     Cfg_2_Win32 |  → `true` |
|     CfgParent |  → `Cfg_2` |
|     Cfg_2 |  → `true` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Base)'!=''" |
|     SanitizedProjectName |  → `Package` |
|     DCC_Namespace |  → `System;System.Win;Winapi;Vcl;Vcl.Forms` |
|     DCC_DcuOutput |  → `.\$(Platform)\$(Config)` |
|     DCC_ExeOutput |  → `.\$(Platform)\$(Config)` |
|     DCC_E |  → `false` |
|     DCC_N |  → `false` |
|     DCC_S |  → `true` |
|     DCC_F |  → `true` |
|     DCC_K |  → `false` |
|     DCC_BRCC |  → `true` |
|     DCC_Bsc |  → `false` |
|     DCC_UseDesignIde |  → `true` |
|     DCC_SymbolReferenceInfo |  → `0` |
|     DCC_Define |  → `DEBUG` |
|     DCC_DcuPackage |  → `Package.dcp` |
|     DCC_BplOutput |  → `..\..\$(Platform)\$(Config)` |
|     DCC_DcpOutput |  → `.\$(Platform)\$(Config)` |
|   PropertyGroup | Condition="'$(Base_Win32)'!=''" |
|     DCC_Namespace |  → `Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml` |
|   PropertyGroup | Condition="'$(Cfg_1)'!=''" |
|     DCC_Define |  → `DEBUG;$(DCC_Define)` |
|     DCC_DebugDCUs |  → `true` |
|     DCC_Optimize |  → `false` |
|     DCC_GenerateStackFrames |  → `true` |
|     DCC_DebugInfoInExe |  → `true` |
|   PropertyGroup | Condition="'$(Cfg_2)'!=''" |
|     DCC_LocalDebugSymbols |  → `false` |
|     DCC_Define |  → `RELEASE;$(DCC_Define)` |
|     DCC_SymbolReferenceInfo |  → `0` |
|     DCC_DebugInformation |  → `0` |
|   ItemGroup |  |
|     DelphiCompile | Include="$(MainSource)" |
|       MainSource |  → `MainSource` |
|     BuildConfiguration | Include="Base" |
|       Key |  → `Base` |
|     BuildConfiguration | Include="Debug" |
|       Key |  → `Cfg_1` |
|       CfgParent |  → `Base` |
|     BuildConfiguration | Include="Release" |
|       Key |  → `Cfg_2` |
|       CfgParent |  → `Base` |
|   ProjectExtensions |  |
|     BorlandProject |  |
|       Deployment |  |
|       Platforms |  |
|         Platform |  → `True` |
|         Platform |  → `True` |
|   Import | Condition="Exists('$(BDS)\Bin\CodeGear.Delphi.Targets')" |
|   Import | Condition="Exists('$(APPDATA)\Embarcadero\$(BDSAPPDATABASEDIR)\$(PRODUCTVERSION)\UserTools." |

### Summary for this project type
❌ **4 missing element(s)**
    ❌ GenPackage not found (expected for Package)
    ❌ RuntimeOnlyPackage not found (expected for Package)
    ❌ GenDll not found (expected for Package)
      ❌ ProjectFileVersion: not found

✅ 18 elements correctly present.

================================================================================
## Project Type: Library
**File**: `C:\Users\swish\AppData\Local\Temp\dproj_test_xl0e9nak\Library.dproj`
**Generator Result**: ✅ 已创建 .dproj 文件: C:\Users\swish\AppData\Local\Temp\dproj_test_xl0e9nak\Library.dproj

**Parsed Info**:
- ProjectGUID: {A729D4C0-D384-45DA-AF62-3EA33728984B}
- ProjectVersion: 18.2
- FrameworkType: None
- AppType: Library
- MainSource: Library.dpr
- TargetedPlatforms: 1
## PropertyGroup Hierarchy
Total PGs: 11
### Library-specific Properties (q)
### ProjectExtensions
### DCC_DCCCompiler (r)
### ItemGroup Elements
### Import Elements

### Raw XML Element Inventory
| Level | Tag | Condition/Attr |
|-------|-----|----------------|
|   PropertyGroup |  |
|     ProjectGuid |  → `{A729D4C0-D384-45DA-AF62-3EA33728984B}` |
|     MainSource |  → `Library.dpr` |
|     Config | Condition="'$(Config)'==''" → `Debug` |
|     ProjectVersion |  → `18.2` |
|     Base |  → `True` |
|     AppType |  → `Library` |
|     FrameworkType |  → `None` |
|     Platform | Condition="'$(Platform)'==''" → `Win32` |
|     TargetedPlatforms |  → `1` |
|     DCC_DCCCompiler |  → `DCC32` |
|   PropertyGroup | Condition="'$(Config)'=='Base' or '$(Base)'!=''" |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Base)'=='true') or '$(Base_Win32)'!=''" |
|     Base_Win32 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Config)'=='Debug' or '$(Cfg_1)'!=''" |
|     Cfg_1 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Cfg_1)'=='true') or '$(Cfg_1_Win32)'!=''" |
|     Cfg_1_Win32 |  → `true` |
|     CfgParent |  → `Cfg_1` |
|     Cfg_1 |  → `true` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Config)'=='Release' or '$(Cfg_2)'!=''" |
|     Cfg_2 |  → `true` |
|     CfgParent |  → `Base` |
|     Base |  → `true` |
|   PropertyGroup | Condition="('$(Platform)'=='Win32' and '$(Cfg_2)'=='true') or '$(Cfg_2_Win32)'!=''" |
|     Cfg_2_Win32 |  → `true` |
|     CfgParent |  → `Cfg_2` |
|     Cfg_2 |  → `true` |
|     Base |  → `true` |
|   PropertyGroup | Condition="'$(Base)'!=''" |
|     SanitizedProjectName |  → `Library` |
|     DCC_Namespace |  → `System;Xml;Data;Datasnap;Web;Soap` |
|     DCC_DcuOutput |  → `.\$(Platform)\$(Config)` |
|     DCC_ExeOutput |  → `.\$(Platform)\$(Config)` |
|     DCC_E |  → `false` |
|     DCC_N |  → `false` |
|     DCC_S |  → `false` |
|     DCC_F |  → `false` |
|     DCC_K |  → `false` |
|   PropertyGroup | Condition="'$(Base_Win32)'!=''" |
|     DCC_Namespace |  → `Winapi;System.Win;Data.Win;Datasnap.Win;Web.Win;Soap.Win;Xml` |
|     GenDll |  → `true` |
|   PropertyGroup | Condition="'$(Cfg_1)'!=''" |
|     DCC_Define |  → `DEBUG;$(DCC_Define)` |
|     DCC_DebugDCUs |  → `true` |
|     DCC_Optimize |  → `false` |
|     DCC_GenerateStackFrames |  → `true` |
|     DCC_DebugInfoInExe |  → `true` |
|   PropertyGroup | Condition="'$(Cfg_2)'!=''" |
|     DCC_LocalDebugSymbols |  → `false` |
|     DCC_Define |  → `RELEASE;$(DCC_Define)` |
|     DCC_SymbolReferenceInfo |  → `0` |
|     DCC_DebugInformation |  → `0` |
|   ItemGroup |  |
|     DelphiCompile | Include="$(MainSource)" |
|       MainSource |  → `MainSource` |
|     BuildConfiguration | Include="Base" |
|       Key |  → `Base` |
|     BuildConfiguration | Include="Debug" |
|       Key |  → `Cfg_1` |
|       CfgParent |  → `Base` |
|     BuildConfiguration | Include="Release" |
|       Key |  → `Cfg_2` |
|       CfgParent |  → `Base` |
|   ProjectExtensions |  |
|     Borland.Personality |  → `Delphi.Personality.12` |
|     Borland.ProjectType |  |
|     BorlandProject |  |
|       Delphi.Personality |  |
|         Source |  |
|           Source |  → `Library.dpr` |
|         Parameters |  |
|           Parameters |  |
|       Platforms |  |
|         Platform |  → `True` |
|     ProjectFileVersion |  → `12` |
|   Import | Condition="Exists('$(BDS)\Bin\CodeGear.Delphi.Targets')" |
|   Import | Condition="Exists('$(APPDATA)\Embarcadero\$(BDSAPPDATABASEDIR)\$(PRODUCTVERSION)\UserTools." |
|   Import | Condition="Exists('$(MSBuildProjectName).deployproj')" |

### Summary for this project type
✅ All 21 checks passed — no missing or unexpected elements.

================================================================================
## Overall Summary

| Project Type | Correct | Missing | Unexpected | Verdict |
|-------------|---------|---------|------------|---------|
| VCL App | 24 | 7 | 0 | ❌ 7 MISSING |
| FMX App | 24 | 7 | 0 | ❌ 7 MISSING |
| Console App | 18 | 7 | 0 | ❌ 7 MISSING |
| Package | 18 | 4 | 0 | ❌ 4 MISSING |
| Library | 21 | 0 | 0 | ✅ PASS |

## Cross-Cutting Issues & Gaps

The following are systematically missing or incorrectly implemented across project types:

- **VCL App**: `Base_Win64`, `Cfg_1_Win64`, `Cfg_2_Win64` PGs are ALL missing
  → The template `_add_property_group_hierarchy` only generates Win32 platform PGs, never Win64

- **BT_BuildType**: Not generated at any level. The template does not emit this element.
  → Real .dproj files have `<BT_BuildType>Debug</BT_BuildType>` in Cfg_1/Cfg_1_Win32 PGs
  → Real .dproj files have `<BT_BuildType>Release</BT_BuildType>` in Cfg_2/Cfg_2_Win32 PGs

- **DCC_ConsoleTarget**: Not generated for Console apps.
  → Real console .dproj files have `<DCC_ConsoleTarget>true</DCC_ConsoleTarget>`

- **Package-specific elements**: `GenPackage`, `RuntimeOnlyPackage`, `GenDll` are not generated.
  → Real Delphi package .dproj files include these to mark the project as a package.

- **Manifest_File**: Generated in `'$(Base_Win32)'!=''` PG (correct)
  ✅ The template correctly adds `<Manifest_File>` for VCL/FMX applications.

- **Deployment element in Package ProjectExtensions**: 
  ✅ Package has simplified `BorlandProject` with `Deployment` + `Platforms` (no `Borland.Personality`)

- **Library HostApplication**: 
  ✅ Library has `Parameters/HostApplication` in ProjectExtensions (correct)