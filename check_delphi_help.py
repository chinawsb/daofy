#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查Delphi帮助文件"""

import winreg
import os

try:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Embarcadero\BDS')
    versions = []
    i = 0
    while True:
        try:
            versions.append(winreg.EnumKey(key, i))
            i += 1
        except:
            break
    winreg.CloseKey(key)
    
    versions.sort(key=lambda x: float(x) if x.replace('.', '').isdigit() else 0, reverse=True)
    print('Delphi版本:', versions)
    
    for v in versions[:3]:
        try:
            key2 = winreg.OpenKey(winreg.HKEY_CURRENT_USER, f'SOFTWARE\\Embarcadero\\BDS\\{v}')
            root = winreg.QueryValueEx(key2, 'RootDir')[0]
            winreg.CloseKey(key2)
            help_dir = os.path.join(root, 'Help', 'Doc')
            
            if os.path.exists(help_dir):
                print(f'\n版本 {v} 帮助目录: {help_dir}')
                files = [f for f in os.listdir(help_dir) if f.endswith('.chm')]
                print(f'  CHM文件数: {len(files)}')
                if len(files) > 5:
                    print(f'  文件列表: {files[:5]}...')
                else:
                    print(f'  文件列表: {files}')
        except Exception as e:
            print(f'检查版本 {v} 失败: {e}')
            
except Exception as e:
    print(f'错误: {e}')
