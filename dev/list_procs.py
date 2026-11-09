import subprocess

out = subprocess.check_output(['tasklist'], encoding='utf-8', errors='ignore')
for line in out.splitlines():
    for word in ['ros', 'python', 'launcher', 'brand', 'suite', 'controller', 'icon', 'diehard', 'splash']:
        if word in line.lower():
            print(line)
            break

