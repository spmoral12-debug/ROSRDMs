# -*- coding: utf-8 -*-
import os

target_files = [
    r'clean_remote_lobby.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
]

for file_path in target_files:
    if not os.path.exists(file_path):
        continue
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    changed = 0
    for i in range(len(lines)):
        line_clean = lines[i].rstrip('\r\n')
        if line_clean.endswith('\\'):
            # Find next non-empty line
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines) and j > i + 1:
                # Join line i and line j
                lines[i] = line_clean[:-1].rstrip() + ' ' + lines[j].lstrip()
                lines[j] = '\n'
                changed += 1

    with open(file_path, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    print(f'Fixed {changed} line continuation issues in {file_path}')

