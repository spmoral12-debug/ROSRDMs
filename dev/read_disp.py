with open(r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\.system_generated\steps\5993\output.txt", "r") as f:
    text = f.read()

lines = text.splitlines()
capture = False
for line in lines:
    if any(line.startswith(f"{i} ") for i in range(538, 548)):
        capture = True
    if line.startswith("548 "):
        break
    if capture:
        print(line)

