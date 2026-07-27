# Fix the missing end; for theme loop
with open('training/TrainApp/UMainForm.pas', 'rb') as f:
    content = f.read()

# The pattern: after '    end;' (end of for I) there should be '    end;' (end of for T)
# Find the for I end marker and add for T end after it
old = b'    end;\r\n\r\n    btnAutoCollect.Enabled := True;\r\n    statBar.SimpleText'
new = b'    end;\r\n    end;\r\n\r\n    btnAutoCollect.Enabled := True;\r\n    statBar.SimpleText'

if old in content:
    content = content.replace(old, new)
    with open('training/TrainApp/UMainForm.pas', 'wb') as f:
        f.write(content)
    print('Fixed: added end; for theme loop')
else:
    print('Pattern not found - checking...')
    idx = content.find(b'btnAutoCollect.Enabled := True;')
    if idx > 0:
        print(content[idx-50:idx+80])
