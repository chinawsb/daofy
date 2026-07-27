object MainForm: TMainForm
  Left = 0
  Top = 0
  Caption = 'Daofy '#35757#32451#25968#25454#37319#38598
  ClientHeight = 720
  ClientWidth = 1024
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -12
  Font.Name = 'Segoe UI'
  Font.Style = []
  OnCreate = FormCreate
  OnDestroy = FormDestroy
  TextHeight = 15
  object statBar: TStatusBar
    Left = 0
    Top = 701
    Width = 1024
    Height = 19
    Panels = <>
    SimplePanel = True
  end
  object pnlMain: TPanel
    Left = 8
    Top = 8
    Width = 1008
    Height = 685
    TabOrder = 0
    object lblTitle: TLabel
      Left = 16
      Top = 10
      Width = 161
      Height = 23
      Caption = 'Daofy '#35757#32451#25968#25454#37319#38598
      Font.Charset = DEFAULT_CHARSET
      Font.Color = clWindowText
      Font.Height = -17
      Font.Name = 'Segoe UI'
      Font.Style = [fsBold]
      ParentFont = False
    end
    object lblStatus: TLabel
      Left = 16
      Top = 40
      Width = 156
      Height = 13
      Caption = #28857#20987#33258#21160#37319#38598#33719#21462#35757#32451#25968#25454
      Font.Charset = DEFAULT_CHARSET
      Font.Color = clGray
      Font.Height = -11
      Font.Name = 'Segoe UI'
      Font.Style = []
      ParentFont = False
    end
    object btnAutoCollect: TButton
      Left = 840
      Top = 10
      Width = 145
      Height = 33
      Caption = #33258#21160#37319#38598
      TabOrder = 1
      OnClick = btnAutoCollectClick
    end
    object pcMain: TPageControl
      Left = 8
      Top = 64
      Width = 992
      Height = 609
      ActivePage = tsData
      TabOrder = 0
      object tsBasic: TTabSheet
        Caption = #22522#26412#25511#20214
        object grpInfo: TGroupBox
          Left = 8
          Top = 8
          Width = 313
          Height = 289
          Caption = #25353#38062#21644#36873#25321
          TabOrder = 0
          object btnOK: TButton
            Left = 16
            Top = 24
            Width = 89
            Height = 33
            Caption = #30830#23450'(&O)'
            TabOrder = 0
            OnClick = btnOKClick
          end
          object btnCancel: TButton
            Left = 112
            Top = 24
            Width = 89
            Height = 33
            Caption = #21462#28040'(&C)'
            TabOrder = 1
          end
          object btnDisabled: TButton
            Left = 208
            Top = 24
            Width = 89
            Height = 33
            Caption = #31105#29992
            Enabled = False
            TabOrder = 2
          end
          object btnSmall: TButton
            Left = 16
            Top = 64
            Width = 75
            Height = 25
            Caption = #23567#25353#38062
            TabOrder = 3
          end
          object chkEnable: TCheckBox
            Left = 16
            Top = 104
            Width = 129
            Height = 17
            Caption = #21551#29992#25193#23637
            Checked = True
            State = cbChecked
            TabOrder = 4
          end
          object chkAutoSave: TCheckBox
            Left = 16
            Top = 128
            Width = 129
            Height = 17
            Caption = #33258#21160#20445#23384
            TabOrder = 5
          end
          object chkDisabled: TCheckBox
            Left = 16
            Top = 152
            Width = 129
            Height = 17
            Caption = #31105#29992#22797#36873#26694
            Enabled = False
            TabOrder = 6
          end
          object rdoMale: TRadioButton
            Left = 16
            Top = 184
            Width = 60
            Height = 17
            Caption = #30007
            Checked = True
            TabOrder = 7
            TabStop = True
          end
          object rdoFemale: TRadioButton
            Left = 80
            Top = 184
            Width = 60
            Height = 17
            Caption = #22899
            TabOrder = 8
          end
          object rdoOther: TRadioButton
            Left = 144
            Top = 184
            Width = 60
            Height = 17
            Caption = #20854#20182
            TabOrder = 9
          end
          object rgGender: TRadioGroup
            Left = 16
            Top = 208
            Width = 281
            Height = 73
            Caption = #24615#21035
            Items.Strings = (
              #30007
              #22899
              #20854#20182)
            TabOrder = 10
          end
        end
        object gbFilters: TGroupBox
          Left = 8
          Top = 304
          Width = 313
          Height = 129
          Caption = #36807#28388#22120
          TabOrder = 1
          object clbOptions: TCheckListBox
            Left = 8
            Top = 16
            Width = 289
            Height = 97
            ItemHeight = 15
            TabOrder = 0
          end
        end
        object pnlSidebar: TPanel
          Left = 336
          Top = 8
          Width = 313
          Height = 289
          BevelOuter = bvLowered
          Caption = #20449#24687#38754#26495
          TabOrder = 2
          object edtName: TEdit
            Left = 16
            Top = 32
            Width = 185
            Height = 23
            TabOrder = 0
            Text = #24352#19977
          end
          object edtPassword: TEdit
            Left = 16
            Top = 64
            Width = 185
            Height = 23
            PasswordChar = '*'
            TabOrder = 1
            Text = '123456'
          end
          object edtReadOnly: TEdit
            Left = 16
            Top = 96
            Width = 185
            Height = 23
            ReadOnly = True
            TabOrder = 2
          end
          object cmbCity: TComboBox
            Left = 16
            Top = 128
            Width = 185
            Height = 23
            Style = csDropDownList
            TabOrder = 3
          end
          object lstItems: TListBox
            Left = 16
            Top = 160
            Width = 185
            Height = 73
            ItemHeight = 15
            TabOrder = 4
          end
        end
        object scrlOptions: TScrollBox
          Left = 664
          Top = 8
          Width = 313
          Height = 425
          BevelKind = bkFlat
          TabOrder = 3
          object rgOptions: TRadioGroup
            Left = 8
            Top = 8
            Width = 281
            Height = 209
            Caption = #27169#24335
            Items.Strings = (
              #40664#35748
              #22686#24378
              #26368#22823)
            TabOrder = 0
          end
          object tbVolume: TTrackBar
            Left = 3
            Top = 241
            Width = 281
            Height = 33
            TabOrder = 1
          end
          object pbProgress: TProgressBar
            Left = 3
            Top = 280
            Width = 281
            Height = 17
            TabOrder = 2
          end
          object sbHorizontal: TScrollBar
            Left = 3
            Top = 312
            Width = 281
            Height = 17
            PageSize = 10
            Position = 50
            TabOrder = 3
          end
        end
        object lstSubItems: TListBox
          Left = 664
          Top = 440
          Width = 313
          Height = 97
          ItemHeight = 15
          Items.Strings = (
            #23376#39033#30446' 1'
            #23376#39033#30446' 2'
            #23376#39033#30446' 3'
            #23376#39033#30446' 4'
            #23376#39033#30446' 5')
          TabOrder = 4
        end
        object btnHidden: TButton
          Left = 664
          Top = 544
          Width = 89
          Height = 25
          Caption = #38544#34255
          TabOrder = 5
          Visible = False
        end
      end
      object tsAdvanced: TTabSheet
        Caption = #39640#32423#25511#20214
        ImageIndex = 1
        object lvItems: TListView
          Left = 8
          Top = 8
          Width = 465
          Height = 300
          Columns = <
            item
              Caption = #25991#20214#21517
              Width = 150
            end
            item
              Caption = #22823#23567
              Width = 100
            end>
          TabOrder = 0
          ViewStyle = vsReport
        end
        object tvTree: TTreeView
          Left = 488
          Top = 8
          Width = 241
          Height = 300
          Indent = 19
          TabOrder = 1
        end
        object memNote: TMemo
          Left = 8
          Top = 320
          Width = 465
          Height = 97
          Lines.Strings = (
            #36825#26159#19968#20010#22810#34892#25991#26412#32534#36753#26694#12290)
          TabOrder = 2
        end
      end
      object tsData: TTabSheet
        Caption = #25968#25454#32593#26684
        ImageIndex = 2
        object sgData: TStringGrid
          Left = 8
          Top = 8
          Width = 465
          Height = 225
          ColCount = 3
          FixedCols = 0
          RowCount = 4
          TabOrder = 0
          ColWidths = (
            64
            200
            64)
        end
      end
    end
  end
end
