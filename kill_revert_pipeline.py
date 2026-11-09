import os, sys, shutil

# 1. Alisin ang Read-Only pansamantala
for p in [r"C:\DieHardROS", r"C:\Users\seanj\AppData\Local\DieHardROSHook"]:
    os.system(f'attrib -r "{p}\\*.*" /s 2>nul')

# 2. I-neutralize ang _dh_write_art at _dh_write_overlays sa LAHAT ng hook files
hook_files = [
    r"C:\DieHardROS\runtime\app\client\lobby_hook.py",
    r"C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py"
]

for hf in hook_files:
    if os.path.exists(hf):
        try:
            with open(hf, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            
            # Patayin ang mga function na nagbabalik ng lumang pictures
            content = content.replace("def _dh_write_art():", "def _dh_write_art():\n    return None")
            content = content.replace("def _dh_write_overlays():", "def _dh_write_overlays():\n    return None")
            
            with open(hf, "w", encoding="utf-8") as f:
                f.write(content)
            print("[DISABLED AUTO-REVERT]:", hf)
        except Exception as e:
            print("[HOOK ERROR]:", e)

# 3. Kopyahin ang bagong Sniper at Login Background
sniper = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_tactical_sniper_clean_1794047799428.jpg"
login  = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_login_clean_1794046745388.jpg"
helmet = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_pure_emblem_1794029947671.jpg"

load_dirs = [
    r"C:\DieHardROS\Documents\res\ui\images\loading",
    r"C:\DieHardROS\local_update\res\ui\images\loading"
]
for ld in load_dirs:
    os.makedirs(ld, exist_ok=True)
    for name in ["bg_loading_01.png", "loading_0.png", "pc_loading_5.png"]:
        shutil.copyfile(sniper, os.path.join(ld, name))
print("[DEPLOYED]: Bagong Tactical Sniper Loading Screen")

# 4. Palitan ang splash at icon sa parehong directory
for ic in [
    r"C:\DieHardROS\runtime\app\splash.png",
    r"C:\DieHardROS\runtime\app\icon.png",
    r"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\splash.png",
    r"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\icon.png"
]:
    if os.path.exists(os.path.dirname(ic)):
        shutil.copyfile(helmet, ic)
print("[DEPLOYED]: Tactical Crimson Helmet App Icon")

# 5. Backgrounds sa dh_brand
brand_dir = r"C:\DieHardROS\Documents\res\dh_brand"
os.makedirs(brand_dir, exist_ok=True)
for bg in ["dh_bg1.jpg", "dh_bg2.jpg", "dh_bg3.jpg", "dh_bg4.jpg"]:
    shutil.copyfile(login, os.path.join(brand_dir, bg))

# 6. I-lock sa Windows Read-Only
os.system('attrib +r "C:\\DieHardROS\\Documents\\res\\ui\\images\\loading\\*.*" /s 2>nul')
os.system('attrib +r "C:\\DieHardROS\\Documents\\res\\dh_brand\\*.*" /s 2>nul')
print("\n>>> PERMANENTENG NAKA-LOCK NA ANG MGA BAGONG GRAPHICS! <<<")
