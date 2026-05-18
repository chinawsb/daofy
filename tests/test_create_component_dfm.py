#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试 DFM 生成工具 — src/tools/create_component_dfm.py

覆盖:
  单元测试（无需编译器）:
    - _generate_dpr: 空 uses / 带 uses / 带 type_decl
    - _extract_component_name: object / inherited / 无匹配
    - generate_component_dfm: 参数校验错误

  集成测试（需要 Delphi 编译器）:
    - VCL TButton（无容器，验证 WriteComponent(nil) 行为）
    - VCL TButton（带 Form 容器，验证差异）
    - VCL TImage（含二进制属性 Picture）
    - FMX TButton
    - 编译错误处理
    - 运行时错误处理
"""

import sys
import os
import tempfile
import shutil
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from src.tools.create_component_dfm import (
    _generate_dpr, _extract_component_name, _find_dcc32,
    _unwrap_form_dfm,
    generate_component_dfm,
)


# ============================================================
# 辅助函数
# ============================================================

def _has_delphi_compiler() -> bool:
    """检查是否安装了可用的 Delphi 编译器"""
    dcc = _find_dcc32()
    if not dcc:
        return False
    try:
        import subprocess
        r = subprocess.run(
            [dcc, "--version"],
            capture_output=True, text=True, timeout=10,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        return r.returncode in (0, 1)
    except Exception:
        return False


# ============================================================
# _generate_dpr — 模板生成
# ============================================================

def test_generate_dpr_empty_uses():
    """空 uses 应生成合法 Pascal"""
    code = "function CreateComponent(AOwner: TComponent): TComponent;\nbegin\n  Result := TButton.Create(AOwner);\nend;"
    dpr = _generate_dpr(uses=[], code=code)
    assert "System.Classes;" in dpr
    assert "System.Classes;\n" in dpr, "无额外 uses 时不应有逗号"
    assert "CreateComponent" in dpr
    assert "WriteComponent" in dpr
    assert "ObjectBinaryToText" in dpr


def test_generate_dpr_with_uses():
    """带 uses 应正确插入到 System.Classes 之后"""
    code = "function CreateComponent(AOwner: TComponent): TComponent;\nbegin\n  Result := TButton.Create(AOwner);\nend;"
    dpr = _generate_dpr(uses=["Vcl.Forms", "Vcl.StdCtrls"], code=code)
    # 验证 uses 顺序
    assert "System.Classes" in dpr
    assert "Vcl.Forms" in dpr
    assert "Vcl.StdCtrls" in dpr
    # System.Classes 在 Vcl.Forms 之前
    assert dpr.index("System.Classes") < dpr.index("Vcl.Forms")
    assert dpr.index("Vcl.Forms") < dpr.index("Vcl.StdCtrls")


def test_generate_dpr_with_type_decl():
    """type_decl 应出现在 code 之前"""
    type_decl = "type\n  TGenForm = class(TForm)\n    procedure BtnClick(Sender: TObject);\n  end;"
    code = "procedure TGenForm.BtnClick(Sender: TObject);\nbegin\nend;\n\nfunction CreateComponent(...)"
    dpr = _generate_dpr(uses=[], code=code, type_decl=type_decl)
    assert "TGenForm" in dpr
    assert dpr.index("TGenForm") < dpr.index("CreateComponent")


def test_generate_dpr_empty_uses_no_trailing_comma():
    """空 uses 验证：System.Classes 后面直接跟分号"""
    code = "function CreateComponent(AOwner: TComponent): TComponent;\nbegin\n  Result := TButton.Create(AOwner);\nend;"
    dpr = _generate_dpr(uses=[], code=code)
    # 检查没有 `,` 紧接 `;` 的语法错误
    assert ",;" not in dpr
    assert "Classes;" in dpr
    # 确认 System.Classes 后直接跟分号
    lines = dpr.split('\n')
    classes_line = [l for l in lines if 'System.Classes' in l]
    assert len(classes_line) > 0
    assert classes_line[0].strip().endswith(';') or classes_line[0].strip().endswith('Classes')


def test_generate_dpr_clean_whitespace():
    """code/type_decl 两端空白应被 strip"""
    code = "  \n  function CreateComponent(AOwner: TComponent): TComponent;\nbegin\nend;\n  "
    dpr = _generate_dpr(uses=[], code=code)
    # 不应有完全空白的行来自 strip 后的空段
    assert "function CreateComponent" in dpr


# ============================================================
# _extract_component_name — DFM 名称提取
# ============================================================

def test_extract_name_object():
    dfm = "object Button1: TButton\n  Left = 10\nend"
    assert _extract_component_name(dfm) == "Button1"


def test_extract_name_inherited():
    dfm = "inherited Form1: TForm1\n  Caption = 'Test'\nend"
    assert _extract_component_name(dfm) == "Form1"


def test_extract_name_nested():
    """嵌套组件应提取最外层名称"""
    dfm = """object Panel1: TPanel
  Left = 0
  object Button1: TButton
    Left = 10
  end
end"""
    assert _extract_component_name(dfm) == "Panel1"


def test_extract_name_no_match():
    dfm = "Left = 10\nTop = 20"
    assert _extract_component_name(dfm) is None


def test_extract_name_empty():
    assert _extract_component_name("") is None


def test_extract_name_with_namespace():
    """支持带命名空间的类名"""
    dfm = "object Button1: Vcl.StdCtrls.TButton\n  Left = 10\nend"
    assert _extract_component_name(dfm) == "Button1"


# ============================================================
# generate_component_dfm — 参数校验
# ============================================================

@pytest.mark.asyncio
async def test_generate_empty_code():
    result = await generate_component_dfm(code="")
    assert result["success"] is False
    assert result["stage"] == "input"
    assert "不能为空" in result["error"]


@pytest.mark.asyncio
async def test_generate_no_createcomponent():
    result = await generate_component_dfm(code="var x: Integer;")
    assert result["success"] is False
    assert result["stage"] == "input"
    assert "CreateComponent" in result["error"]


@pytest.mark.asyncio
async def test_generate_none_code():
    result = await generate_component_dfm(code=None)  # type: ignore
    assert result["success"] is False
    assert result["stage"] == "input"


# ============================================================
# 集成测试 — 需要 Delphi 编译器
# ============================================================

VCL_BUTTON_WITH_FORM = """\
type
  TGenForm = class(TForm)
  public
    constructor Create(AOwner: TComponent); override;
  published
    procedure BtnClick(Sender: TObject);
  end;

constructor TGenForm.Create(AOwner: TComponent);
begin
  inherited CreateNew(AOwner);  // 不加载 DFM 资源
end;

procedure TGenForm.BtnClick(Sender: TObject);
begin
end;

function CreateComponent(AOwner: TComponent): TComponent;
var
  F: TGenForm;
  B: TButton;
begin
  F := TGenForm.Create(nil);
  F.Name := 'Form1';
  B := TButton.Create(F);   // owned by Form — WriteComponent 需要
  B.Name := 'Button1';
  B.Parent := F;
  B.Caption := 'Hello';
  B.Left := 10;
  B.Top := 20;
  B.OnClick := F.BtnClick;
  Result := F;  // 返回 Form，工具自动提取 Button1
end;
"""

VCL_BUTTON_NO_FORM = """\
function CreateComponent(AOwner: TComponent): TComponent;
var
  B: TButton;
begin
  B := TButton.Create(nil);
  B.Name := 'Button1';
  B.Caption := 'Hello';
  Result := B;
end;
"""

BAD_PASCAL_CODE = """\
function CreateComponent(AOwner: TComponent): TComponent;
var
  B: TButton;
begin
  B := TButton.Create(nil);
  B.ThisPropertyDoesNotExist := 42;  { 编译错误 }
  Result := B;
end;
"""

RUNTIME_ERROR_CODE = """\
function CreateComponent(AOwner: TComponent): TComponent;
begin
  raise Exception.Create('Intentional runtime error for test');
end;
"""


@pytest.mark.skipif(not _has_delphi_compiler(), reason="需要 Delphi 编译器")
@pytest.mark.asyncio
async def test_vcl_button_with_form():
    """VCL TButton + Form 容器 — 验证 DFM 输出正确"""
    result = await generate_component_dfm(
        code=VCL_BUTTON_WITH_FORM,
        uses=["Vcl.Forms", "Vcl.StdCtrls"],
        init_code="RegisterClass(TGenForm);",
    )
    assert result["success"], f"生成失败: {result.get('error')}"
    dfm = result["dfm_text"]
    assert "object Button1: TButton" in dfm
    assert "Caption = 'Hello'" in dfm
    assert "Left = 10" in dfm
    assert "Top = 20" in dfm
    assert "OnClick = BtnClick" in dfm
    assert result["component_name"] == "Button1"


@pytest.mark.skipif(not _has_delphi_compiler(), reason="需要 Delphi 编译器")
@pytest.mark.asyncio
async def test_vcl_button_no_form():
    """VCL TButton 无容器 — 验证 WriteComponent(nil) 的行为"""
    result = await generate_component_dfm(
        code=VCL_BUTTON_NO_FORM,
        uses=["Vcl.StdCtrls"],
    )
    assert result["success"], f"生成失败: {result.get('error')}"
    dfm = result["dfm_text"]
    # 无容器的基本属性应正确输出
    assert "object Button1: TButton" in dfm
    assert "Caption = 'Hello'" in dfm
    # Parent 不会是必需的输出（没有设置过，或者序列化时跳过）
    # ParentFont = False 不会出现（默认 True）
    assert result["component_name"] == "Button1"


@pytest.mark.skipif(not _has_delphi_compiler(), reason="需要 Delphi 编译器")
@pytest.mark.asyncio
async def test_vcl_image_with_binary():
    """TImage + 二进制 Picture — 验证二进制属性被序列化"""
    code = """\
function CreateComponent(AOwner: TComponent): TComponent;
var
  F: TForm;
  Img: TImage;
  Bmp: TBitmap;
begin
  F := TForm.CreateNew(nil);
  F.Name := 'Form1';
  Img := TImage.Create(F);   // owned by Form
  Img.Name := 'Image1';
  Img.Parent := F;
  Img.Left := 0;
  Img.Top := 0;
  Img.Width := 50;
  Img.Height := 50;
  Bmp := TBitmap.Create;
  try
    Bmp.Width := 10;
    Bmp.Height := 10;
    Bmp.Canvas.Pixels[0, 0] := clRed;
    Img.Picture.Assign(Bmp);
  finally
    Bmp.Free;
  end;
  Result := F;  // 返回 Form，工具自动提取 Image1
end;
"""
    result = await generate_component_dfm(
        code=code,
        uses=["Vcl.Forms", "Vcl.ExtCtrls", "Vcl.Graphics"],
    )
    assert result["success"], f"生成失败: {result.get('error')}"
    dfm = result["dfm_text"]
    assert "object Image1: TImage" in dfm
    # Picture 是二进制数据，DFM 中应该有 Picture.Data
    assert "Picture.Data" in dfm
    assert result["component_name"] == "Image1"


@pytest.mark.skipif(not _has_delphi_compiler(), reason="需要 Delphi 编译器")
@pytest.mark.asyncio
async def test_fmx_button():
    """FMX TButton — 验证 FMX 组件也能正确生成"""
    # FMX 的 TButton 在 FMX.StdCtrls 中
    code = """\
function CreateComponent(AOwner: TComponent): TComponent;
var
  B: TButton;
begin
  B := TButton.Create(nil);
  B.Name := 'FMXButton1';
  B.Text := 'FMX Hello';
  B.Position.X := 10;
  B.Position.Y := 20;
  B.Width := 120;
  B.Height := 35;
  Result := B;
end;
"""
    result = await generate_component_dfm(
        code=code,
        uses=["FMX.StdCtrls"],
    )
    assert result["success"], f"FMX 生成失败: {result.get('error')}"
    dfm = result["dfm_text"]
    assert "object FMXButton1: TButton" in dfm
    assert "Text = 'FMX Hello'" in dfm
    assert result["component_name"] == "FMXButton1"


@pytest.mark.skipif(not _has_delphi_compiler(), reason="需要 Delphi 编译器")
@pytest.mark.asyncio
async def test_compilation_error():
    """非法 Pascal 代码应返回编译错误"""
    result = await generate_component_dfm(
        code=BAD_PASCAL_CODE,
        uses=["Vcl.StdCtrls"],
    )
    assert result["success"] is False
    assert result["stage"] == "compile"
    assert "编译失败" in result["error"] or "Field" in result["error"]


@pytest.mark.skipif(not _has_delphi_compiler(), reason="需要 Delphi 编译器")
@pytest.mark.asyncio
async def test_runtime_error():
    """编译通过但运行时崩溃应返回执行错误"""
    result = await generate_component_dfm(
        code=RUNTIME_ERROR_CODE,
        uses=[],
    )
    assert result["success"] is False
    assert result["stage"] == "execute"
    assert "Intentional runtime error" in result["error"] or "runtime" in result.get("error", "").lower()


@pytest.mark.skipif(not _has_delphi_compiler(), reason="需要 Delphi 编译器")
@pytest.mark.asyncio
async def test_vcl_button_with_form_and_font():
    """验证 Form 容器能正确影响 Font/ParentFont 序列化"""
    code = """\
type
  TGenForm = class(TForm)
  public
    constructor Create(AOwner: TComponent); override;
  end;

constructor TGenForm.Create(AOwner: TComponent);
begin
  inherited CreateNew(AOwner);  // 不加载 DFM 资源
  Font.Name := 'Tahoma';
  Font.Size := 12;
end;

    function CreateComponent(AOwner: TComponent): TComponent;
    var
      F: TGenForm;
      B: TButton;
    begin
      F := TGenForm.Create(nil);
      F.Name := 'Form1';
      B := TButton.Create(F);   // owned by Form
      B.Name := 'Button1';
      B.Parent := F;
      B.Caption := 'Styled';
      // 使用 ParentFont=True（默认），所以 Font 不应被显式序列化
      Result := F;  // 返回 Form，工具自动提取 Button1
    end;
"""
    result = await generate_component_dfm(
        code=code,
        uses=["Vcl.Forms", "Vcl.StdCtrls"],
        init_code="RegisterClass(TGenForm);",
    )
    assert result["success"], f"生成失败: {result.get('error')}"
    dfm = result["dfm_text"]
    # ParentFont=True 是默认值，不会被 WriteComponent 输出
    assert "ParentFont" not in dfm
    # Font 未被显式修改，不应出现
    assert "Font." not in dfm
    # 基本属性应正确
    assert "Caption = 'Styled'" in dfm


# ============================================================
# _unwrap_form_dfm — Form 容器解包
# ============================================================

def test_unwrap_form_simple_child():
    """Form 带一个子组件 — 应提取子组件"""
    dfm = """object Form1: TForm1
  Left = 0
  object Button1: TButton
    Left = 10
    Caption = 'Click'
  end
  Top = 0
end"""
    result = _unwrap_form_dfm(dfm)
    assert result is not None
    assert "object Button1: TButton" in result
    assert "Caption = 'Click'" in result
    assert "Form1" not in result  # 不应包含 Form 声明


def test_unwrap_form_multiple_children():
    """Form 带多个子组件 — 应提取第一个"""
    dfm = """object Form1: TForm1
  Caption = 'Test'
  object Button1: TButton
    Left = 10
  end
  object Edit1: TEdit
    Left = 100
  end
end"""
    result = _unwrap_form_dfm(dfm)
    assert result is not None
    assert "object Button1: TButton" in result
    assert "Edit1" not in result  # 只提取第一个子组件


def test_unwrap_form_no_child():
    """Form 无子组件 — 返回 None"""
    dfm = "object Form1: TForm1\n  Caption = 'Empty'\nend"
    result = _unwrap_form_dfm(dfm)
    assert result is None


def test_unwrap_non_form_root():
    """根节点不是 Form — 不解包"""
    dfm = "object Button1: TButton\n  Left = 10\nend"
    result = _unwrap_form_dfm(dfm)
    assert result is None


def test_unwrap_inherited_form():
    """inherited Form — 也应解包子组件"""
    dfm = """inherited Form1: TForm1
  Caption = 'Inherited'
  object Button1: TButton
    Left = 10
  end
end"""
    result = _unwrap_form_dfm(dfm)
    assert result is not None
    assert "object Button1: TButton" in result


def test_unwrap_nested_components():
    """子组件内部还有嵌套组件"""
    dfm = """object Form1: TForm1
  object Panel1: TPanel
    Left = 0
    object Button1: TButton
      Left = 10
    end
  end
end"""
    result = _unwrap_form_dfm(dfm)
    assert result is not None, f"expected unwrapped DFM, got None"
    assert "object Panel1: TPanel" in result
    # Panel 的嵌套 Button 也应保留
    assert "object Button1: TButton" in result
    assert "Left = 10" in result


def test_unwrap_empty_string():
    """空字符串 — 返回 None"""
    assert _unwrap_form_dfm("") is None
    assert _unwrap_form_dfm("  ") is None


def test_unwrap_form_with_spaces():
    """Form 声明前有缩进"""
    dfm = """  object Form1: TForm1
    Caption = 'Test'
    object Button1: TButton
      Left = 10
    end
  end"""
    result = _unwrap_form_dfm(dfm)
    assert result is not None
    assert "object Button1: TButton" in result
    # 提取的子组件保留原缩进
    assert "  Left = 10" in result


# ============================================================
# 调试用：手动运行集成测试
# ============================================================

if __name__ == "__main__":
    # 快速验证（仅供调试）
    from src.tools.create_component_dfm import generate_component_dfm as gen
    import asyncio

    async def main():
        # 测试空 uses 模板生成
        dpr = _generate_dpr(uses=[], code="function CreateComponent(AOwner: TComponent): TComponent;\nbegin\nend;")
        print("=== 空 uses ===")
        print(dpr)
        print()
        assert ",;" not in dpr

        # 测试带 uses 生成
        dpr2 = _generate_dpr(
            uses=["Vcl.Forms", "Vcl.StdCtrls"],
            code="function CreateComponent(AOwner: TComponent): TComponent;\nbegin\nend;",
        )
        print("=== 带 uses ===")
        print(dpr2)
        print()

        # 测试名称提取
        assert _extract_component_name("object Foo: TBar\nend") == "Foo"
        print("名称提取: OK")

        # 如果有编译器，运行集成测试
        if _has_delphi_compiler():
            print("=== 集成测试: VCL Button + Form ===")
            r = await gen(
                code=VCL_BUTTON_WITH_FORM,
                uses=["Vcl.Forms", "Vcl.StdCtrls"],
                init_code="RegisterClass(TGenForm);",
            )
            print(f"Success: {r.get('success')}")
            if r.get('success'):
                print(r['dfm_text'])
            else:
                print(f"Error: {r.get('error')}")
            print()
            print("=== 集成测试: VCL Button no Form ===")
            r2 = await gen(
                code=VCL_BUTTON_NO_FORM,
                uses=["Vcl.StdCtrls"],
            )
            print(f"Success: {r2.get('success')}")
            if r2.get('success'):
                print(r2['dfm_text'])
            else:
                print(f"Error: {r2.get('error')}")
            print()

            print("=== 集成测试: 编译错误 ===")
            r3 = await gen(
                code=BAD_PASCAL_CODE,
                uses=["Vcl.StdCtrls"],
            )
            print(f"Error (expected): {r3.get('error')[:200]}")
            print()

            print("=== 集成测试: 运行时错误 ===")
            r4 = await gen(
                code=RUNTIME_ERROR_CODE,
                uses=[],
            )
            print(f"Error (expected): {r4.get('error')}")
        else:
            print("跳过集成测试（无 Delphi 编译器）")
        print("全部基本测试: OK")

    asyncio.run(main())
