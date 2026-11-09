import os

targets = [
    r'C:\DieHardROS\runtime\app\client\lobby_hook.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\client\lobby_hook.py'
]

for p in targets:
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        code = code.replace(
            "'dtsInGameActionAppearanceIDs': lambda: []",
            "'dtsInGameActionAppearanceIDs': lambda: [909042, 909030, 909031]"
        )

        bad_stmt = "if hasattr(w if 'w' in dir() else node, 'setOpacity'): (w if 'w' in dir() else node).setOpacity(0)"
        good_stmt = "if hasattr(node, 'setOpacity'): node.setOpacity(0)"
        if bad_stmt in code:
            code = code.replace(bad_stmt, good_stmt)

        with open(p, 'w', encoding='utf-8') as f:
            f.write(code)
        print("Updated lobby_hook.py:", p)

