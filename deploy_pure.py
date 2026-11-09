import os, sys, shutil

sniper = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_tactical_sniper_clean_1794047799428.jpg"
login  = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_login_clean_1794046745388.jpg"
helmet = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_pure_emblem_1794029947671.jpg"

# 1. Tanggalin muna ang read-only lock
os.system('attrib -r "C:\\DieHardROS\\Documents\\res\\*.*" /s 2>nul')
os.system('attrib -r "C:\\DieHardROS\\runtime\\app\\*.*" 2>nul')
os.system('attrib -r "C:\\Users\\seanj\\AppData\\Local\\DieHardROSHook\\*.*" /s 2>nul')

# 2. Loading Screen Targets
load_dirs = [
    r"C:\DieHardROS\Documents\res\ui\images\loading",
    r"C:\DieHardROS\local_update\res\ui\images\loading"
]
for ld in load_dirs:
    os.makedirs(ld, exist_ok=True)
    for name in ["bg_loading_01.png", "loading_0.png", "pc_loading_5.png"]:
        dest = os.path.join(ld, name)
        shutil.copyfile(sniper, dest)
        print("[DEPLOYED LOADING]:", dest)

# 3. Splash at Launcher Icon Targets (Papatayin ang Asul na Controller!)
icon_targets = [
    r"C:\DieHardROS\runtime\app\splash.png",
    r"C:\DieHardROS\runtime\app\icon.png",
    r"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\splash.png",
    r"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\icon.png"
]
for ic in icon_targets:
    if os.path.exists(os.path.dirname(ic)):
        shutil.copyfile(helmet, ic)
        print("[DEPLOYED CRIMSON HELMET]:", ic)

# 4. Brand Wallpapers at 100% Clean Logo (Nakatatak na ang 3D logo sa wallpaper!)
brand_dir = r"C:\DieHardROS\Documents\res\dh_brand"
os.makedirs(brand_dir, exist_ok=True)
for bg in ["dh_bg1.jpg", "dh_bg2.jpg", "dh_bg3.jpg", "dh_bg4.jpg"]:
    dest = os.path.join(brand_dir, bg)
    shutil.copyfile(login, dest)
    print("[DEPLOYED LOGIN BG]:", dest)

# 1x1 transparent PNG para wala nang black box sa logo (dahil nakadikit na ang 3D Metallic logo sa wallpaper)
clear_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
for l in ["dh_logo_1.png", "dh_logo_2.png", "dh_logo_3.png", "dh_logo_4.png", "dh_logo_5.png", "dh_login_logo.png", "dh_logo_sg_cloud.png", "dh_logo_sg_cosmic.png"]:
    dest = os.path.join(brand_dir, l)
    with open(dest, "wb") as f:
        f.write(clear_png)

# 5. I-lock sa Windows Read-Only para hindi na kayang i-overwrite ng lumang game engine
os.system('attrib +r "C:\\DieHardROS\\Documents\\res\\ui\\images\\loading\\*.*" /s 2>nul')
os.system('attrib +r "C:\\DieHardROS\\Documents\\res\\dh_brand\\*.*" /s 2>nul')
print("\n>>> ALL ASSETS SUCCESSFULLY REPLACED AND PERMANENTLY LOCKED! <<<")
