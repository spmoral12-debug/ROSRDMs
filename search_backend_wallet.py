import os

for root, dirs, files in os.walk(r'C:\DieHardROS\runtime\app\backend_server'):
    for f in files:
        if f.endswith('.py'):
            p = os.path.join(root, f)
            with open(p, 'rb') as fp:
                c = fp.read()
                if b'wallets' in c or b'payYuanbao' in c:
                    print(f"Match in {p}")

