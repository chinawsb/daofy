"""
测试 DFM 解析器 + PAS 声明解析器 + manage_component 增删改操作
"""

import os
import tempfile
import pytest

from src.tools.dfm_parser import (
    DfmComponent, DfmProperty,
    parse_dfm_text, serialize_component,
    collect_all_events, collect_all_units,
    resolve_event_params, resolve_component_unit,
    is_event_property, set_kb_services,
)
from src.tools.pas_decl_parser import (
    PasFieldDecl, PasMethodDecl,
    parse_pas_class, sync_pas_declarations, extract_event_handlers,
)


# ============================================================
# DFM 解析器测试
# ============================================================

SAMPLE_DFM = """\
object Form1: TForm1
  Left = 0
  Top = 0
  Caption = 'MyForm'
  OnCreate = FormCreate
  object Panel1: TPanel
    Left = 10
    Top = 20
    object Button1: TButton
      Left = 5
      Caption = 'OK'
      OnClick = BtnOKClick
    end
    object Button2: TButton
      Left = 100
      Caption = 'Cancel'
      OnClick = BtnCancelClick
    end
  end
  object Timer1: TTimer
    Interval = 1000
    OnTimer = Timer1Timer
  end
end
"""


class TestDfmParser:

    def test_parse_root(self):
        root = parse_dfm_text(SAMPLE_DFM)
        assert root is not None
        assert root.name == "Form1"
        assert root.class_name == "TForm1"

    def test_parse_children(self):
        root = parse_dfm_text(SAMPLE_DFM)
        assert len(root.children) == 2
        assert root.children[0].name == "Panel1"
        assert root.children[1].name == "Timer1"

    def test_parse_nested_children(self):
        root = parse_dfm_text(SAMPLE_DFM)
        panel = root.children[0]
        assert len(panel.children) == 2
        assert panel.children[0].name == "Button1"
        assert panel.children[1].name == "Button2"

    def test_parse_properties(self):
        root = parse_dfm_text(SAMPLE_DFM)
        btn1 = root.find_child("Button1")
        assert btn1 is not None
        cap = btn1.get_property("Caption")
        assert cap is not None
        assert cap.raw_value == "'OK'"

    def test_parse_event_properties(self):
        root = parse_dfm_text(SAMPLE_DFM)
        btn1 = root.find_child("Button1")
        onclick = btn1.get_property("OnClick")
        assert onclick is not None
        assert onclick.is_event is True
        assert onclick.value == "BtnOKClick"

    def test_collect_all_events(self):
        root = parse_dfm_text(SAMPLE_DFM)
        events = collect_all_events(root)
        event_names = [h for _, _, h in events]
        assert "BtnOKClick" in event_names
        assert "BtnCancelClick" in event_names
        assert "Timer1Timer" in event_names
        assert "FormCreate" in event_names

    def test_collect_all_units_with_kb(self):
        class MockKB:
            def search_by_name(self, name):
                unit_map = {
                    'TForm1': 'Vcl.Forms', 'TPanel': 'Vcl.ExtCtrls',
                    'TButton': 'Vcl.StdCtrls', 'TTimer': 'Vcl.ExtCtrls',
                }
                unit = unit_map.get(name)
                if unit:
                    return [{"kind_code": "TC", "file": {"full_path": "C:/src/{}.pas".format(unit)}, "definition": ""}]
                return []

        set_kb_services(delphi_kb=MockKB(), thirdparty_kb=None)
        root = parse_dfm_text(SAMPLE_DFM)
        units = collect_all_units(root)
        assert "Vcl.ExtCtrls" in units
        assert "Vcl.StdCtrls" in units
        set_kb_services(delphi_kb=None, thirdparty_kb=None)

    def test_find_child(self):
        root = parse_dfm_text(SAMPLE_DFM)
        assert root.find_child("Button1") is not None
        assert root.find_child("NonExistent") is None

    def test_find_all_by_class(self):
        root = parse_dfm_text(SAMPLE_DFM)
        buttons = root.find_all_by_class("TButton")
        assert len(buttons) == 2

    def test_remove_child(self):
        root = parse_dfm_text(SAMPLE_DFM)
        assert root.remove_child("Timer1") is True
        assert root.find_child("Timer1") is None
        assert len(root.children) == 1

    def test_all_components(self):
        root = parse_dfm_text(SAMPLE_DFM)
        all_comps = root.all_components()
        names = [c.name for c in all_comps]
        assert "Form1" in names
        assert "Panel1" in names
        assert "Button1" in names
        assert "Timer1" in names

    def test_serialize_roundtrip(self):
        root = parse_dfm_text(SAMPLE_DFM)
        text = serialize_component(root)
        root2 = parse_dfm_text(text)
        assert root2 is not None
        assert root2.name == root.name
        assert root2.class_name == root.class_name
        assert len(root2.children) == len(root.children)

    def test_parse_inherited(self):
        dfm = "inherited Form2: TForm2\n  Left = 100\nend\n"
        root = parse_dfm_text(dfm)
        assert root is not None
        assert root.prefix == "inherited"
        assert root.name == "Form2"

    def test_parse_empty(self):
        assert parse_dfm_text("") is None
        assert parse_dfm_text("   ") is None

    def test_parse_property_value_types(self):
        dfm = """\
object Form1: TForm
  Left = 0
  Caption = 'Hello World'
  Enabled = True
  Color = clBtnFace
  OnClick = FormClick
end
"""
        root = parse_dfm_text(dfm)
        assert root.get_property("Left").raw_value == "0"
        assert root.get_property("Caption").raw_value == "'Hello World'"
        assert root.get_property("Enabled").raw_value == "True"
        assert root.get_property("Color").raw_value == "clBtnFace"
        assert root.get_property("OnClick").is_event is True


# ============================================================
# PAS 声明解析器测试
# ============================================================

SAMPLE_PAS = """\
unit Unit1;

interface

uses
  Vcl.Forms, Vcl.StdCtrls, Vcl.ExtCtrls;

type
  TForm1 = class(TForm)
    Panel1: TPanel;
    Button1: TButton;
    Button2: TButton;
    Timer1: TTimer;
    procedure FormCreate(Sender: TObject);
    procedure BtnOKClick(Sender: TObject);
    procedure BtnCancelClick(Sender: TObject);
    procedure Timer1Timer(Sender: TObject);
  private
    FCounter: Integer;
  public
    procedure ResetCounter;
  end;

var
  Form1: TForm1;

implementation

{$R *.dfm}

procedure TForm1.FormCreate(Sender: TObject);
begin
  FCounter := 0;
end;

procedure TForm1.BtnOKClick(Sender: TObject);
begin
  //
end;

procedure TForm1.BtnCancelClick(Sender: TObject);
begin
  Close;
end;

procedure TForm1.Timer1Timer(Sender: TObject);
begin
  Inc(FCounter);
end;

procedure TForm1.ResetCounter;
begin
  FCounter := 0;
end;

end.
"""


class TestPasDeclParser:

    def test_parse_class(self):
        info = parse_pas_class(SAMPLE_PAS)
        assert info is not None
        assert info.class_name == "TForm1"
        assert info.ancestor == "TForm"

    def test_parse_fields(self):
        info = parse_pas_class(SAMPLE_PAS)
        field_names = [f.name for f in info.fields]
        assert "Panel1" in field_names
        assert "Button1" in field_names
        assert "Button2" in field_names
        assert "Timer1" in field_names

    def test_parse_methods(self):
        info = parse_pas_class(SAMPLE_PAS)
        method_names = [m.name for m in info.methods]
        assert "FormCreate" in method_names
        assert "BtnOKClick" in method_names
        assert "BtnCancelClick" in method_names
        assert "Timer1Timer" in method_names
        assert "ResetCounter" in method_names

    def test_sync_add_field(self):
        new_pas = sync_pas_declarations(
            SAMPLE_PAS,
            add_fields=[PasFieldDecl(name="Edit1", type_name="TEdit")],
        )
        assert "Edit1: TEdit;" in new_pas

    def test_sync_remove_field(self):
        new_pas = sync_pas_declarations(
            SAMPLE_PAS,
            remove_fields=["Button2"],
        )
        assert "Button2: TButton;" not in new_pas
        assert "Button1: TButton;" in new_pas

    def test_sync_add_method(self):
        new_pas = sync_pas_declarations(
            SAMPLE_PAS,
            add_methods=[PasMethodDecl(
                name="Edit1Change", params="Sender: TObject", method_type="procedure",
            )],
        )
        assert "procedure Edit1Change(Sender: TObject);" in new_pas
        assert "procedure TForm1.Edit1Change(Sender: TObject);" in new_pas

    def test_sync_remove_method(self):
        new_pas = sync_pas_declarations(
            SAMPLE_PAS,
            remove_methods=["BtnCancelClick"],
        )
        assert "procedure BtnCancelClick(Sender: TObject);" not in new_pas
        assert "procedure TForm1.BtnCancelClick" not in new_pas

    def test_sync_add_uses(self):
        new_pas = sync_pas_declarations(
            SAMPLE_PAS,
            add_uses=["Vcl.Dialogs"],
        )
        assert "Vcl.Dialogs" in new_pas

    def test_sync_remove_uses(self):
        new_pas = sync_pas_declarations(
            SAMPLE_PAS,
            remove_uses=["Vcl.ExtCtrls"],
        )
        assert "Vcl.ExtCtrls" not in new_pas

    def test_sync_no_duplicate_field(self):
        new_pas = sync_pas_declarations(
            SAMPLE_PAS,
            add_fields=[PasFieldDecl(name="Button1", type_name="TButton")],
        )
        count = new_pas.count("Button1: TButton;")
        assert count == 1

    def test_extract_event_handlers(self):
        handlers = extract_event_handlers(SAMPLE_PAS, "TForm1")
        assert "BtnOKClick" in handlers
        assert "BtnCancelClick" in handlers
        assert "Timer1Timer" in handlers

    def test_parse_class_not_found(self):
        assert parse_pas_class("no class here") is None

    def test_preserve_line_endings_crlf(self):
        pas_crlf = SAMPLE_PAS.replace('\n', '\r\n')
        new_pas = sync_pas_declarations(
            pas_crlf,
            add_fields=[PasFieldDecl(name="Edit1", type_name="TEdit")],
        )
        assert '\r\n' in new_pas


# ============================================================
# manage_component 集成测试（用临时文件）
# ============================================================

class TestManageComponentAdd:

    @pytest.fixture
    def dfm_pas_pair(self, tmp_path):
        dfm_file = tmp_path / "Unit1.dfm"
        pas_file = tmp_path / "Unit1.pas"
        dfm_file.write_text(SAMPLE_DFM.strip(), encoding="utf-8")
        pas_file.write_text(SAMPLE_PAS, encoding="utf-8")
        return str(dfm_file), str(pas_file)

    @pytest.mark.asyncio
    async def test_add_component(self, dfm_pas_pair):
        from src.tools.manage_component import manage_component
        dfm_path, pas_path = dfm_pas_pair
        result = await manage_component(
            action="add",
            target_dfm=dfm_path,
            target_pas=pas_path,
            new_component_class="TEdit",
            new_component_name="Edit1",
            properties={"Left": "200", "Top": "50", "Text": "'Hello'"},
        )
        assert result["status"] == "success"
        assert result["component_name"] == "Edit1"
        assert "Edit1: TEdit;" in open(pas_path, 'r', encoding='utf-8').read()

    @pytest.mark.asyncio
    async def test_add_component_with_event(self, dfm_pas_pair):
        from src.tools.manage_component import manage_component
        dfm_path, pas_path = dfm_pas_pair
        result = await manage_component(
            action="add",
            target_dfm=dfm_path,
            target_pas=pas_path,
            new_component_class="TButton",
            new_component_name="BtnApply",
            properties={"Caption": "'Apply'", "OnClick": "BtnApplyClick"},
        )
        assert result["status"] == "success"
        pas_text = open(pas_path, 'r', encoding='utf-8').read()
        assert "BtnApply: TButton;" in pas_text
        assert "procedure BtnApplyClick(Sender: TObject);" in pas_text


class TestManageComponentRemove:

    @pytest.fixture
    def dfm_pas_pair(self, tmp_path):
        dfm_file = tmp_path / "Unit1.dfm"
        pas_file = tmp_path / "Unit1.pas"
        dfm_file.write_text(SAMPLE_DFM.strip(), encoding="utf-8")
        pas_file.write_text(SAMPLE_PAS, encoding="utf-8")
        return str(dfm_file), str(pas_file)

    @pytest.mark.asyncio
    async def test_remove_component(self, dfm_pas_pair):
        from src.tools.manage_component import manage_component
        dfm_path, pas_path = dfm_pas_pair
        result = await manage_component(
            action="remove",
            target_dfm=dfm_path,
            target_pas=pas_path,
            component_name="Timer1",
        )
        assert result["status"] == "success"
        dfm_text = open(dfm_path, 'r', encoding='utf-8').read()
        assert "Timer1" not in dfm_text
        pas_text = open(pas_path, 'r', encoding='utf-8').read()
        assert "Timer1: TTimer;" not in pas_text

    @pytest.mark.asyncio
    async def test_remove_not_found(self, dfm_pas_pair):
        from src.tools.manage_component import manage_component
        dfm_path, pas_path = dfm_pas_pair
        result = await manage_component(
            action="remove",
            target_dfm=dfm_path,
            target_pas=pas_path,
            component_name="NonExistent",
        )
        assert result["status"] == "failed"


class TestManageComponentModify:

    @pytest.fixture
    def dfm_pas_pair(self, tmp_path):
        dfm_file = tmp_path / "Unit1.dfm"
        pas_file = tmp_path / "Unit1.pas"
        dfm_file.write_text(SAMPLE_DFM.strip(), encoding="utf-8")
        pas_file.write_text(SAMPLE_PAS, encoding="utf-8")
        return str(dfm_file), str(pas_file)

    @pytest.mark.asyncio
    async def test_modify_property(self, dfm_pas_pair):
        from src.tools.manage_component import manage_component
        dfm_path, _ = dfm_pas_pair
        result = await manage_component(
            action="modify",
            target_dfm=dfm_path,
            component_name="Button1",
            properties={"Caption": "'Confirm'"},
        )
        assert result["status"] == "success"
        dfm_text = open(dfm_path, 'r', encoding='utf-8').read()
        assert "'Confirm'" in dfm_text

    @pytest.mark.asyncio
    async def test_modify_event_change(self, dfm_pas_pair):
        from src.tools.manage_component import manage_component
        dfm_path, pas_path = dfm_pas_pair
        result = await manage_component(
            action="modify",
            target_dfm=dfm_path,
            target_pas=pas_path,
            component_name="Button1",
            properties={"OnClick": "BtnConfirmClick"},
        )
        assert result["status"] == "success"
        pas_text = open(pas_path, 'r', encoding='utf-8').read()
        assert "procedure BtnConfirmClick(Sender: TObject);" in pas_text


# ============================================================
# KB 事件签名解析测试
# ============================================================

class TestEventSignatureResolver:

    def test_no_kb_fallback(self):
        set_kb_services(delphi_kb=None, thirdparty_kb=None)
        params = resolve_event_params("TButton", "OnClick")
        assert params == "Sender: TObject"

    def test_non_event_name_fallback(self):
        set_kb_services(delphi_kb=None, thirdparty_kb=None)
        params = resolve_event_params("TButton", "Caption")
        assert params == "Sender: TObject"

    def test_kb_with_mock_service(self):
        class MockKB:
            def search_by_name(self, name):
                if name == "OnClick":
                    return [
                        {
                            "kind_code": "MP",
                            "definition": "Event OnClick: TNotifyEvent read FOnClick write FOnClick",
                            "file": {"full_path": ""},
                        }
                    ]
                if name == "TNotifyEvent":
                    return [
                        {
                            "kind_code": "MM",
                            "definition": "Method Pointer TNotifyEvent = procedure of object",
                            "file": {"full_path": ""},
                        }
                    ]
                return []

        set_kb_services(delphi_kb=MockKB(), thirdparty_kb=None)
        params = resolve_event_params("TButton", "OnClick")
        assert params == "Sender: TObject"

    def test_kb_with_source_file(self, tmp_path):
        source_file = tmp_path / "Vcl.Controls.pas"
        source_file.write_text(
            "property OnClick: TNotifyEvent read FOnClick write FOnClick;\n"
            "TNotifyEvent = procedure(Sender: TObject) of object;\n"
            "TMouseEvent = procedure(Sender: TObject; Button: TMouseButton; Shift: TShiftState; X, Y: Integer) of object;\n",
            encoding="utf-8",
        )

        class MockKB:
            def __init__(self, path):
                self._path = str(path)

            def search_by_name(self, name):
                if name == "OnClick":
                    return [
                        {
                            "kind_code": "MP",
                            "definition": "Event OnClick: TNotifyEvent read FOnClick write FOnClick",
                            "file": {"full_path": self._path},
                        }
                    ]
                if name == "TNotifyEvent":
                    return [
                        {
                            "kind_code": "MM",
                            "definition": "Method Pointer TNotifyEvent = procedure of object",
                            "file": {"full_path": self._path},
                        }
                    ]
                return []

        set_kb_services(delphi_kb=MockKB(source_file), thirdparty_kb=None)
        params = resolve_event_params("TButton", "OnClick")
        assert params == "Sender: TObject"

    def test_kb_mouse_event_from_source(self, tmp_path):
        source_file = tmp_path / "Vcl.Controls.pas"
        source_file.write_text(
            "property OnMouseDown: TMouseEvent read FOnMouseDown write FOnMouseDown;\n"
            "TMouseEvent = procedure(Sender: TObject; Button: TMouseButton; Shift: TShiftState; X, Y: Integer) of object;\n",
            encoding="utf-8",
        )

        class MockKB:
            def __init__(self, path):
                self._path = str(path)

            def search_by_name(self, name):
                if name == "OnMouseDown":
                    return [
                        {
                            "kind_code": "MP",
                            "definition": "Event OnMouseDown: TMouseEvent read FOnMouseDown write FOnMouseDown",
                            "file": {"full_path": self._path},
                        }
                    ]
                if name == "TMouseEvent":
                    return [
                        {
                            "kind_code": "MM",
                            "definition": "Method Pointer TMouseEvent = procedure of object",
                            "file": {"full_path": self._path},
                        }
                    ]
                return []

        set_kb_services(delphi_kb=MockKB(source_file), thirdparty_kb=None)
        params = resolve_event_params("TControl", "OnMouseDown")
        assert "TMouseButton" in params
        assert "X, Y: Integer" in params
