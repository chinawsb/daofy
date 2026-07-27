# Fix non-ASCII in rebuild_catalog.py
with open('training/TrainApp/rebuild_catalog.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace Chinese text with English
fixes = {
    "Caption := '小'": "Caption := 'Small'",
    "Caption := '确定(O)'": "Caption := 'OK(O)'",
    "Caption := '确定'": "Caption := 'OK'",
    "Caption := '大按钮'": "Caption := 'Large'",
    "Caption := '禁用'": "Caption := 'Disabled'",
    "Caption := '启用扩展'": "Caption := 'Extend'",
    "Caption := '自动保存'": "Caption := 'AutoSave'",
    "Caption := '禁用复选框'": "Caption := 'DisChk'",
    "Caption := '禁用按钮'": "Caption := 'DisBtn'",
    "Caption := '取消(C)'": "Caption := 'Cancel(C)'",
    "Caption := 'Cancel(C)'": "Caption := 'Undo(C)'",
    "Caption := '小按钮'": "Caption := 'Tiny'",
    "Caption := '模式'": "Caption := 'Mode'",
    "Caption := '默认'": "Caption := 'Default'",
    "Caption := '增强'": "Caption := 'Enh'",
    "Caption := '最大'": "Caption := 'Max'",
    "Caption := '性别'": "Caption := 'Gender'",
    "Caption := '男'": "Caption := 'Male'",
    "Caption := '女'": "Caption := 'Female'",
    "Caption := '其他'": "Caption := 'Other'",
    "Caption := '过滤器'": "Caption := 'Filter'",
    "Caption := '信息面板'": "Caption := 'Info'",
    "Caption := '隐藏'": "Caption := 'Hide'",
    "Caption := '基本控件'": "Caption := 'Basic'",
    "Caption := '高级控件'": "Caption := 'Advanced'",
    "Caption := '数据网格'": "Caption := 'Data'",
    "Caption := 'Daofy 训练数据采集'": "Caption := 'Daofy Train'",
    "Caption := '点击自动采集获取训练数据'": "Caption := 'Click AutoCollect'",
    "Caption := '按钮和选择'": "Caption := 'Buttons'",
    "Caption := '只读文本内容'": "Text := 'ReadOnly text'",
}

for old, new in fixes.items():
    content = content.replace(old, new)

with open('training/TrainApp/rebuild_catalog.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Fixed. Checking for remaining non-ASCII...')

# Verify no non-ASCII in bytes literals
for i, line in enumerate(content.split('\n')):
    if "b'''" in line or "new_catalog" in line:
        # Check for non-ASCII in this and following lines until ''' 
        in_block = "'b'''" in line or "b'''" in line[:3]
        if in_block:
            for j in range(i, i+200):
                if j >= len(content.split('\n')):
                    break
                l = content.split('\n')[j]
                for c in l:
                    if ord(c) > 127:
                        print(f'  Non-ASCII in bytes block at line {j+1}: {l.strip()[:60]}')
                        break
                if "'''" in l and j > i:
                    break
