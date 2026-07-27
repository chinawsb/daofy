import sys
sys.path.insert(0, '.')
from src.tools.ocr import handle_ocr

tests = [
    ('Training image', 'training/dataset/images/train_000_default.png'),
    ('Settings (cross-app)', 'docs/copyright/snapshots/frmSettings.jpg'),
    ('Main form (cross-app)', 'docs/copyright/snapshots/frmMain.png'),
]

for label, path in tests:
    print('=== %s ===' % label)
    r = handle_ocr({'action': 'analyze', 'image_path': path})
    print('Elements: %d  Backend: %s' % (r['element_count'], r.get('backend', '?')))
    print('Summary: %s' % r['summary'])
    for el in r['elements'][:6]:
        t = el['text'][:18] if el['text'] else ''
        print('  %-12s conf=%.2f rect=(%d,%d,%d,%d) text=%s' % (
            el['type'], el['confidence'],
            el['rect']['x'], el['rect']['y'], el['rect']['w'], el['rect']['h'],
            repr(t)))
    print()
