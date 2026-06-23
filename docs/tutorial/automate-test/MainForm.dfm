object Form1: TForm1
  Left = 0
  Top = 0
  Caption = 'Daofy Automation Test'
  ClientHeight = 400
  ClientWidth = 660
  Color = clBtnFace
  Font.Charset = DEFAULT_CHARSET
  Font.Color = clWindowText
  Font.Height = -11
  Font.Name = 'Tahoma'
  Font.Style = []
  OldCreateOrder = False
  OnCreate = FormCreate
  PixelsPerInch = 96
  TextHeight = 13
  PopupMenu = PopupMenu1
  object PageControl1: TPageControl
    Left = 0
    Top = 0
    Width = 660
    Height = 400
    ActivePage = tsInteraction
    Align = alClient
    TabHeight = 24
    TabOrder = 0
    object tsInteraction: TTabSheet
      Caption = '  Interaction  '
      object BtnHello: TButton
        Left = 20
        Top = 20
        Width = 120
        Height = 30
        Caption = 'Say Hello'
        TabOrder = 0
        OnClick = BtnHelloClick
      end
      object EditName: TEdit
        Left = 20
        Top = 60
        Width = 160
        Height = 21
        TabOrder = 1
        Text = 'Daofy'
      end
      object BtnClear: TButton
        Left = 20
        Top = 95
        Width = 120
        Height = 30
        Caption = 'Clear'
        TabOrder = 2
        OnClick = BtnClearClick
      end
      object BtnMsgBox: TButton
        Left = 200
        Top = 20
        Width = 120
        Height = 30
        Caption = 'Show Message'
        TabOrder = 3
        OnClick = BtnMsgBoxClick
      end
      object BtnExit: TButton
        Left = 200
        Top = 95
        Width = 120
        Height = 30
        Caption = 'Exit'
        TabOrder = 4
        OnClick = BtnExitClick
      end
    end
    object tsControls: TTabSheet
      Caption = '  Controls  '
      object BtnCoord: TButton
        Left = 20
        Top = 20
        Width = 150
        Height = 30
        Caption = 'Point Click Test'
        TabOrder = 0
        OnClick = BtnCoordClick
      end
      object PanelHover: TPanel
        Left = 20
        Top = 60
        Width = 150
        Height = 40
        Caption = 'Hover here'
        Hint = 'Hover detected!'
        ParentShowHint = False
        ShowHint = True
        TabOrder = 1
      end
      object TreeView1: TTreeView
        Left = 300
        Top = 20
        Width = 200
        Height = 280
        Indent = 19
        PopupMenu = PopupMenu1
        TabOrder = 2
      end
      object LblTreeHint: TLabel
        Left = 20
        Top = 120
        Width = 200
        Height = 32
        Caption = 'Right-click TreeView for popup menu'
        WordWrap = True
      end
    end
    object tsGraphics: TTabSheet
      Caption = '  Graphics  '
      object ImageCaptcha: TImage
        Left = 20
        Top = 20
        Width = 150
        Height = 40
        Stretch = True
      end
      object BtnCaptcha: TButton
        Left = 20
        Top = 70
        Width = 120
        Height = 30
        Caption = 'Make Captcha'
        TabOrder = 0
        OnClick = BtnCaptchaClick
      end
      object LblCaptchaHint: TLabel
        Left = 150
        Top = 75
        Width = 120
        Height = 20
        Caption = ''
        Font.Charset = DEFAULT_CHARSET
        Font.Color = clNavy
        Font.Height = -13
        Font.Name = 'Tahoma'
        Font.Style = [fsBold]
        ParentFont = False
      end
      object BtnOpenPic: TButton
        Left = 20
        Top = 120
        Width = 150
        Height = 30
        Caption = 'Open Picture...'
        TabOrder = 1
        OnClick = BtnOpenPicClick
      end
    end
  end
  object PopupMenu1: TPopupMenu
    Left = 320
    Top = 200
    object MenuCopy: TMenuItem
      Caption = 'Copy'
      OnClick = MenuCopyClick
    end
    object MenuPaste: TMenuItem
      Caption = 'Paste'
      OnClick = MenuPasteClick
    end
    object MenuSep1: TMenuItem
      Caption = '-'
    end
    object MenuProperties: TMenuItem
      Caption = 'Properties'
      OnClick = MenuPropertiesClick
    end
  end
  object OpenPictureDialog1: TOpenPictureDialog
    Left = 380
    Top = 200
  end
end
