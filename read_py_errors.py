with open(r'C:\DieHardROS\local_update\logs\game_python_errors.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

print("Total lines in game_python_errors.log:", len(lines))
for line in lines[-40:]:
    print(line, end='')

