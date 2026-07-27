import sys, json
sys.path.insert(0, '.')

from src.tools.ocr import handle_ocr
from src.services.automation_service import _check_assert

# Run analyze on a training image
result = handle_ocr({'action': 'analyze', 'image_path': 'training/dataset/images/train_000_default.png'})
print('Elements:', result.get('element_count'))
print('Summary:', result.get('summary'))
print()

# Test assert_expr that AI might use
tests = [
    ("len(elements) > 20", "should detect many elements"),
    ("any(e['type']=='button' for e in elements)", "should find button"),
    ("any(e['type']=='checkbox' and e['state']=='enabled' for e in elements)", "should find enabled checkbox"),
    ("any(e['type']=='edit' and e['text']!='' for e in elements)", "should find edit with text"),
    ("sum(1 for e in elements if e['confidence']>0.5) > 10", "over 10 elements with high conf"),
]

local_vars = {'elements': result.get('elements', [])}

for expr, desc in tests:
    try:
        ar = _check_assert({'assert_expr': expr, 'cmd': 'analyze'}, result)
        status = 'PASS' if ar.get('passed') else 'FAIL'
        print('  %s: %s  (%s)' % (status, expr, desc))
    except Exception as e:
        print('  ERR: %s -> %s' % (expr, e))
