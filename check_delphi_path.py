#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查Delphi安装路径"""

import winreg

def check_delphi_paths():
    """检查Delphi安装路径"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Embarcadero\BDS')
        print('Delphi安装路径:')
        i = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, i)
                subkey = winreg.OpenKey(key, subkey_name)
                try:
                    root_dir = winreg.QueryValueEx(subkey, 'RootDir')[0]
                    print(f'  {subkey_name}: {root_dir}')
                except:
                    pass
                winreg.CloseKey(subkey)
                i += 1
            except:
                break
        winreg.CloseKey(key)
    except Exception as e:
        print(f"无法读取注册表: {e}")

if __name__ == "__main__":
    check_delphi_paths()
