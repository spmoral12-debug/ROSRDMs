with open(r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\.system_generated\steps\5993\output.txt", "r") as f:
    text = f.read()

lines = text.splitlines()
record = False
for line in lines:
    if "2748 STORE_FAST" in line:
        record = True
    if "2840 " in line or "548 " in line:
        print(line)
        break
    if record:
        print(line)

