import re

with open('training/TrainApp/UMainForm.pas', 'rb') as f:
    content = f.read()

# Find the btnAutoCollectClick function
marker = b'procedure TMainForm.btnAutoCollectClick'
idx = content.find(marker)
end_idx = content.rfind(b'end;', 0, content.rfind(b'end.'))

func_bytes = content[idx:end_idx+5]

# Replace double-quoted strings with single-quoted
def fix_quotes(m):
    inner = m.group(1)
    # Escape any single quotes inside
    inner = inner.replace(b"'", b"''")
    return b"'" + inner + b"'"

fixed = re.sub(b'"([^"]*?)"', fix_quotes, func_bytes)

new_content = content[:idx] + fixed + content[end_idx+5:]
with open('training/TrainApp/UMainForm.pas', 'wb') as f:
    f.write(new_content)

orig_dq = func_bytes.count(b'"')
new_sq = fixed.count(b"'")
print(f'Fixed: {orig_dq} double quotes replaced')
