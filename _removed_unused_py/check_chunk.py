with open(r'C:\DieHardROS\local_update\hot\remote-battle.py', 'rb') as f:
    text = f.read().decode('utf-8')

for line in text.splitlines():
    line = line.strip()
    if line.startswith('"') and line.endswith('",'):
        print('Chunk length:', len(line.strip('",')))
        break

