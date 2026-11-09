import os

for p in [
    r'C:\DieHardROS\local_update\logs\game_python_errors.log',
    r'C:\DieHardROS\local_update\logs\hook_install_errors.log',
    r'C:\DieHardROS\local_update\logs\local_game_server.jsonl',
    r'C:\DieHardROS\local_update\logs\local_update_server.jsonl'
]:
    if os.path.exists(p):
        print(f"=== {p} ===")
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        for line in lines[-25:]:
            print(line, end='')

