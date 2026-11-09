import os, shutil

# Source images
winged_img = r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_loading_screen_1794065096828.jpg'
sniper_clean_img = r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_tactical_sniper_clean_1794047799428.jpg'
transparent_png = r'C:\DieHardROS\Documents\res\zjzc_wz.png' # 118 byte transparent PNG

# 1x1 transparent PNG fallback if needed:
TRANS_PNG_BYTES = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000a49444154789c6360000000020001737501180000000049454e44ae426082'
)

roots = [
    r'C:\DieHardROS\Documents\res',
    r'C:\DieHardROS\x64\Documents\res',
    r'C:\DieHardROS\runtime\Documents\res',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\Documents\res'
]

for res_dir in roots:
    dh_brand = os.path.join(res_dir, 'dh_brand')
    os.makedirs(dh_brand, exist_ok=True)
    loading_dir = os.path.join(res_dir, 'ui', 'images', 'loading')
    os.makedirs(loading_dir, exist_ok=True)
    login_dir = os.path.join(res_dir, 'ui', 'images', 'login')
    os.makedirs(login_dir, exist_ok=True)
    images_dir = os.path.join(res_dir, 'ui', 'images')
    os.makedirs(images_dir, exist_ok=True)

    print(f"\n>>> Deploying assets to {res_dir}...")

    # 1. Winged ROS Redemption wallpapers (dh_bg1 - dh_bg4, etc.)
    for name in ['dh_bg1.jpg', 'dh_bg2.jpg', 'dh_bg3.jpg', 'dh_bg4.jpg', 'dh_fireteam.jpg', 'dh_ev_06632.jpg', 'dh_ev_13933.jpg']:
        dest = os.path.join(dh_brand, name)
        shutil.copyfile(winged_img, dest)
    print(f"  [OK] Winged wallpapers copied to dh_brand")

    # 2. Clean Sniper Girl (NO skygame/diehard) to all season loading ranks (dh_rank_s1 to dh_rank_s30)
    for i in range(1, 31):
        dest = os.path.join(dh_brand, f'dh_rank_s{i}.jpg')
        shutil.copyfile(sniper_clean_img, dest)
    print(f"  [OK] Clean sniper girl copied to dh_rank_s1..s30")

    # 3. Transparent PNG for all legacy logo textures
    for name in [
        'dh_login_logo.png', 'dh_logo_1.png', 'dh_logo_2.png', 'dh_logo_3.png',
        'dh_logo_4.png', 'dh_logo_5.png', 'dh_logo_sg_cloud.png', 'dh_logo_sg_cosmic.png',
        'dh_qr.png', 'ros_redemption_transparent.png'
    ]:
        dest = os.path.join(dh_brand, name)
        with open(dest, 'wb') as f:
            f.write(TRANS_PNG_BYTES)

    for p in [
        os.path.join(res_dir, 'txt_logo_zjzc.png'),
        os.path.join(images_dir, 'txt_logo_zjzc.png'),
        os.path.join(login_dir, 'txt_logo_zjzc.png'),
        os.path.join(res_dir, 'zjzc_wz.png'),
        os.path.join(images_dir, 'zjzc_wz.png'),
        os.path.join(login_dir, 'zjzc_wz.png')
    ]:
        with open(p, 'wb') as f:
            f.write(TRANS_PNG_BYTES)
    print(f"  [OK] All legacy logo files made 100% transparent PNG")

    # 4. Loading screens in ui/images/loading
    for i in range(1, 11):
        dest = os.path.join(loading_dir, f'bg_loading_{i:02d}.png')
        shutil.copyfile(winged_img, dest)
    shutil.copyfile(winged_img, os.path.join(loading_dir, 'loading_0.png'))
    shutil.copyfile(winged_img, os.path.join(loading_dir, 'pc_loading_5.png'))
    shutil.copyfile(winged_img, os.path.join(images_dir, 'bg_loading_01.png'))
    print(f"  [OK] Loading screens in ui/images/loading updated")

print("\n>>> ALL ASSETS DEPLOYED ACROSS ALL 4 ROOTS SUCCESSFULLY! <<<")

