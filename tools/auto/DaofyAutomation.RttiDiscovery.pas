unit DaofyAutomation.RttiDiscovery;

{ 注意：TMemberVisibility 复合比较（in / <>）在 Delphi 13 可能生成错误机器码，
  请始终使用 = 等式比较。}

{===============================================================================
  DaofyAutomation.RttiDiscovery - RTTI 能力发现

  TRttiDiscoverer：通过 Delphi Enhanced RTTI 扫描类（TClass）的
  published+public 方法和属性，返回 JSON Schema 格式的能力描述。

  用途：
    - AI Agent 发现 Delphi 应用暴露了哪些 published+public 方法/属性
    - 自动生成参数 Schema（类型、方向、必需性）
    - 支持 dot-notation 属性链类型推导

  框架无关：纯 System.Rtti，可在 VCL/FMX/控制台应用中使用。
===============================================================================}

interface

uses
  System.SysUtils,
  System.Rtti,
  System.TypInfo,
  System.JSON,
  System.Generics.Collections;

type
  /// <summary>
  ///  RTTI 能力发现器。将 Delphi 类的 published+public 成员映射为 JSON Schema 格式。
  /// </summary>
  TRttiDiscoverer = class
  public
    /// <summary>扫描 TClass 的 published+public 方法/属性，返回 JSON Schema 能力描述</summary>
    class function DiscoverClass(AClass: TClass; const AName: string = '';
      const AVisibility: string = 'public,published'): TJSONObject;

    /// <summary>将 Delphi RTTI 类型映射为 JSON Schema 对象</summary>
    class function TypeToSchema(AType: TRttiType): TJSONObject;
  end;

implementation

{ ═════════════════════════════════════════════════════════════════════════════
  TRttiDiscoverer
  ═════════════════════════════════════════════════════════════════════════════ }

class function TRttiDiscoverer.TypeToSchema(AType: TRttiType): TJSONObject;
var
  TypeData: PTypeData;
  i: Integer;
  EnumArr: TJSONArray;
  DynArrType: TRttiDynamicArrayType;
  Types: TJSONArray;
begin
  Result := TJSONObject.Create;

  if AType = nil then
  begin
    Result.AddPair('type', 'string');
    Result.AddPair('description', 'Unknown(nil)');
    Exit;
  end;

  case AType.TypeKind of
    tkInteger, tkInt64:
      begin
        // 无符号整数类型
        if SameText(AType.Name, 'Cardinal') or SameText(AType.Name, 'Byte') or
           SameText(AType.Name, 'Word') or SameText(AType.Name, 'UInt64') then
        begin
          Result.AddPair('type', 'integer');
          Result.AddPair('minimum', TJSONNumber.Create(0));
        end else
          Result.AddPair('type', 'integer');
      end;

    tkFloat:
      begin
        if SameText(AType.Name, 'TDateTime') then
        begin
          Result.AddPair('type', 'string');
          Result.AddPair('format', 'date-time');
        end else
          Result.AddPair('type', 'number');
      end;

    tkString, tkLString, tkWString, tkUString:
      Result.AddPair('type', 'string');

    tkChar, tkWChar:
      Result.AddPair('type', 'string');

    tkEnumeration:
      begin
        if SameText(AType.Name, 'Boolean') or SameText(AType.Name, 'ByteBool') or
           SameText(AType.Name, 'WordBool') or SameText(AType.Name, 'LongBool') then
          Result.AddPair('type', 'boolean')
        else begin
          Result.AddPair('type', 'string');
          TypeData := GetTypeData(AType.Handle);
          EnumArr := TJSONArray.Create;
          for i := TypeData.MinValue to TypeData.MaxValue do
            EnumArr.AddElement(TJSONString.Create(GetEnumName(AType.Handle, i)));
          Result.AddPair('enum', EnumArr);
        end;
      end;

    tkSet:
      begin
        Result.AddPair('type', 'array');
        Result.AddPair('description', 'set of ' + AType.Name);
      end;

    tkClass:
      begin
        Result.AddPair('type', 'object');
        Result.AddPair('description', AType.Name + ' object');
      end;

    tkDynArray:
      begin
        Result.AddPair('type', 'array');
        DynArrType := AType as TRttiDynamicArrayType;
        if (DynArrType <> nil) and (DynArrType.ElementType <> nil) then
          Result.AddPair('items', TypeToSchema(DynArrType.ElementType));
      end;

    tkArray:
      begin
        Result.AddPair('type', 'array');
      end;

    tkRecord:
      begin
        Result.AddPair('type', 'object');
        Result.AddPair('description', 'record ' + AType.Name);
      end;

    tkVariant:
      begin
        Types := TJSONArray.Create;
        Types.AddElement(TJSONString.Create('string'));
        Types.AddElement(TJSONString.Create('number'));
        Types.AddElement(TJSONString.Create('boolean'));
        Types.AddElement(TJSONNull.Create);
        Result.AddPair('type', Types);
      end;

    tkPointer:
      begin
        Result.AddPair('type', 'string');
        Result.AddPair('description', 'Pointer');
      end;

    tkInterface:
      begin
        Result.AddPair('type', 'object');
        Result.AddPair('description', 'interface ' + AType.Name);
      end;
  else
    // tkMethod, tkClassRef, tkProcedure, tkUnknown
    Result.AddPair('type', 'string');
    Result.AddPair('description', AType.Name);
  end;
end;

class function TRttiDiscoverer.DiscoverClass(AClass: TClass;
  const AName, AVisibility: string): TJSONObject;
var
  Ctx: TRttiContext;
  RType: TRttiType;
  Method: TRttiMethod;
  Param: TRttiParameter;
  Prop: TRttiProperty;
  ToolsArray: TJSONArray;
  ResourcesArray: TJSONArray;
  ToolObj: TJSONObject;
  ResObj: TJSONObject;
  ParamProps: TJSONObject;
  Required: TJSONArray;
  ParamContainer: TJSONObject;
  VisSet: set of TMemberVisibility;
  VisParts: TArray<string>;
  VisItem: string;
begin
  Result := TJSONObject.Create;
  Ctx := TRttiContext.Create;
  try
    // 解析 visibility 参数
    VisSet := [mvPublic, mvPublished];
    if AVisibility <> '' then begin
      VisSet := [];
      VisParts := AVisibility.Split([',']);
      for VisItem in VisParts do begin
        var VisLower := VisItem.Trim.ToLower;
        if VisLower = 'private' then Include(VisSet, mvPrivate)
        else if VisLower = 'protected' then Include(VisSet, mvProtected)
        else if VisLower = 'public' then Include(VisSet, mvPublic)
        else if VisLower = 'published' then Include(VisSet, mvPublished);
      end;
    end;

    RType := Ctx.GetType(AClass);

    if AName = '' then
      Result.AddPair('className', TJSONString.Create(AClass.ClassName))
    else
      Result.AddPair('className', TJSONString.Create(AName));

    if AClass.ClassParent <> nil then
      Result.AddPair('ancestor', TJSONString.Create(AClass.ClassParent.ClassName));

    // ── 扫描可见度范围内的方法 → "tools" 数组 ──

    ToolsArray := TJSONArray.Create;
    for Method in RType.GetMethods do
    begin
      if not (Method.Visibility in VisSet) then
        Continue;

      // 排除构造/析构
      if Method.MethodKind in [mkConstructor, mkDestructor] then Continue;

      ToolObj := TJSONObject.Create;
      ToolObj.AddPair('name', TJSONString.Create(Method.Name));

      // 方法分类
      case Method.MethodKind of
        mkFunction:
          begin
            ToolObj.AddPair('kind', 'function');
            if Method.ReturnType <> nil then
              ToolObj.AddPair('returnType', TypeToSchema(Method.ReturnType));
          end;
        mkProcedure:
          ToolObj.AddPair('kind', 'procedure');
        mkClassFunction:
          begin
            ToolObj.AddPair('kind', 'class function');
            if Method.ReturnType <> nil then
              ToolObj.AddPair('returnType', TypeToSchema(Method.ReturnType));
          end;
        mkClassProcedure:
          ToolObj.AddPair('kind', 'class procedure');
      else
        ToolObj.AddPair('kind', 'method');
      end;

      // ── 读取 AI 注解（方法级）
      // Attrs := Method.GetAttributes;
      // for LAttr in Attrs do
      // begin
      //   if LAttr is AIDescriptionAttribute then
      //     ToolObj.AddPair('description', TJSONString.Create(AIDescriptionAttribute(LAttr).Text));
      //   if LAttr is AIResultDescriptionAttribute then
      //     ToolObj.AddPair('resultDescription', TJSONString.Create(AIResultDescriptionAttribute(LAttr).Text));
      //   if LAttr is AIExampleAttribute then
      //     ToolObj.AddPair('example', TJSONString.Create(AIExampleAttribute(LAttr).Text));
      // end;

      // ── 参数 JSON Schema ──
      ParamProps := TJSONObject.Create;
      Required := TJSONArray.Create;

      for Param in Method.GetParameters do
      begin
        // 参数类型可能为 nil（某些 inherited 方法的 RTTI 信息不完整）
        if Param.ParamType = nil then Continue;

        var ParamSchema: TJSONObject := TypeToSchema(Param.ParamType);

        // 参数方向
        if pfVar in Param.Flags then
          ParamSchema.AddPair('direction', TJSONString.Create('var'))
        else if pfOut in Param.Flags then
          ParamSchema.AddPair('direction', TJSONString.Create('out'));

        // ── 读取 AI 注解（参数级）
        // Attrs := Param.GetAttributes;
        // for LAttr in Attrs do
        // begin
        //   if LAttr is AIParamDescriptionAttribute then
        //     ParamSchema.AddPair('description', TJSONString.Create(AIParamDescriptionAttribute(LAttr).Text));
        // end;

        // 默认不标记 Required（所有参数都视为必须，除非有默认值）
        // 注：Delphi RTTI 不直接提供 HasDefaultValue 标志

        ParamProps.AddPair(Param.Name, ParamSchema);
      end;

      if ParamProps.Count > 0 then
      begin
        ParamContainer := TJSONObject.Create;
        ParamContainer.AddPair('type', TJSONString.Create('object'));
        ParamContainer.AddPair('properties', ParamProps);
        if Required.Count > 0 then
          ParamContainer.AddPair('required', Required);
        ToolObj.AddPair('parameters', ParamContainer);
      end;

      ToolsArray.AddElement(ToolObj);
    end;
    Result.AddPair('tools', ToolsArray);

    // ── 扫描可见度范围内的属性 → "properties" 数组 ──

    ResourcesArray := TJSONArray.Create;
    for Prop in RType.GetProperties do
    begin
      if not (Prop.Visibility in VisSet) then
        Continue;

      ResObj := TJSONObject.Create;
      ResObj.AddPair('name', TJSONString.Create(Prop.Name));
      if Prop.PropertyType <> nil then
        ResObj.AddPair('schema', TypeToSchema(Prop.PropertyType))
      else
        ResObj.AddPair('schema', TJSONObject.Create);  // unknown type
      ResObj.AddPair('readable', TJSONBool.Create(Prop.IsReadable));
      ResObj.AddPair('writable', TJSONBool.Create(Prop.IsWritable));
      ResourcesArray.AddElement(ResObj);
    end;
    Result.AddPair('properties', ResourcesArray);

  finally
    Ctx.Free;
  end;
end;

end.