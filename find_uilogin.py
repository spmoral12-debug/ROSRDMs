import re

with open(r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py', 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

print("unpacked_lobby length:", len(content))

# Search for UILogin class
matches = re.findall(r'class\s+UILogin[a-zA-Z0-9_]*\b[^\n]*', content)
print("UILogin classes:", matches)

# Find where UILogin is defined or created
for line in content.splitlines():
    if 'class UILogin' in line or 'def _init_ui' in line and 'login' in line.lower():
        print(line)

