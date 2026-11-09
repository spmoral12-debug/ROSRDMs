with open(r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\.system_generated\steps\5993\output.txt", "r") as f:
    text = f.read()

lines = text.splitlines()
found = False
for i, line in enumerate(lines):
    if "2748 STORE_FAST" in line:
        for j in range(i, min(i+40, len(lines))):
            print(lines[j])
        break

