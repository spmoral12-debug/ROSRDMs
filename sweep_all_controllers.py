import os, sys, shutil

helmet = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_pure_emblem_1794029947671.jpg"
splash = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_splash_clean_1794018381576.jpg"
logo   = r"C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_title_logo_1794018691342.jpg"

search_folders = [
    r"C:\DieHardROS",
    r"C:\Users\seanj\AppData\Local\DieHardROSHook",
    r"C:\Users\seanj\dev"
]

replaced_count = 0
for folder in search_folders:
    if not os.path.exists(folder):
        continue
    for root, dirs, files in os.walk(folder):
        for f in files:
            fl = f.lower()
            dest = os.path.join(root, f)
            
            # 1. Palitan ang lahat ng splash at icons sa crimson helmet
            if fl in ['splash.png', 'icon.png', 'app.ico', 'ros.ico', 'legacy.ico', 'dh_logo_sg_cloud.png', 'dh_logo_sg_cosmic.png'] or ('splash' in fl and fl.endswith(('.png', '.jpg'))):
                try:
                    os.chmod(dest, 0o777)
                    shutil.copyfile(helmet, dest)
                    print(f"[REPLACED ICON/SPLASH] {dest}")
                    replaced_count += 1
                except Exception as e:
                    pass

            # 2. Palitan ang lahat ng background sa ROS Redemption splash
            elif fl.startswith('dh_bg') and fl.endswith('.jpg'):
                try:
                    os.chmod(dest, 0o777)
                    shutil.copyfile(splash, dest)
                    print(f"[REPLACED BG] {dest}")
                    replaced_count += 1
                except:
                    pass

            # 3. Palitan ang logos
            elif fl.startswith('dh_logo_') and fl.endswith('.png'):
                try:
                    os.chmod(dest, 0o777)
                    shutil.copyfile(logo, dest)
                    print(f"[REPLACED LOGO] {dest}")
                    replaced_count += 1
                except:
                    pass

print(f"\n>>> MATAGUMPAY! {replaced_count} files ang napalitan sa buong system!")
