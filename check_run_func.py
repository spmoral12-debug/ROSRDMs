with open(r'C:\DieHardROS\local_update\hot\remote-battle.py', 'rb') as f:
    text = f.read().decode('utf-8')

idx = text.find('def _dh_run():')
print(text[idx:])

