import os

p1 = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_splash_clean_1794018381576.jpg"
p2 = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_title_logo_1794018691342.jpg"

print("Splash exists:", os.path.exists(p1))
print("Logo exists:", os.path.exists(p2))

if os.path.exists(p1):
    with open(p1, "rb") as f:
        d = f.read()
        print(f"Splash size: {len(d)} bytes")

if os.path.exists(p2):
    with open(p2, "rb") as f:
        d = f.read()
        print(f"Logo size: {len(d)} bytes")
