import os

with open(r'C:\DieHardROS\script.npk', 'rb') as f:
    data = f.read()

print("script.npk size:", len(data))
idx = 0
found = []
while True:
    idx = data.find(b'UILogin', idx)
    if idx == -1:
        break
    found.append(idx)
    # print surrounding bytes
    snippet = data[max(0, idx-30):min(len(data), idx+60)]
    print(f"Offset {idx}: {snippet}")
    idx += 7
    if len(found) > 10:
        break

