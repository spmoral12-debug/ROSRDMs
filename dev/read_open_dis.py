with open(r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\.system_generated\steps\5880\output.txt", "r") as f:
    text = f.read()

# Find lines between 180 and 225
lines = text.splitlines()
capture = False
for line in lines:
    if line.startswith("185 ") or line.startswith("190 ") or line.startswith("195 ") or line.startswith("200 ") or line.startswith("205 ") or line.startswith("210 ") or line.startswith("215 ") or line.startswith("220 "):
        capture = True
    if line.startswith("225 "):
        break
    if capture:
        print(line)

