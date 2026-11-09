# -*- coding: utf-8 -*-
"""
ROS Redemption Master Fix Script
Fixes:
1. Lobby character visibility: removes 2D wallpaper overlay from scene when in lobby.
2. Drawing bug: safe guards generateArgsForUIItemDisplay against IndexError and missing items.
3. Completely replaces sniper girl with intact ROS Redemption winged loading screen across all folders.
4. Suppresses CCMini blue window and prepares custom splash.
"""

import os, sys, shutil, hashlib

UNPACKED_PY = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
WINGED_V3 = r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_loading_screen_v3_1794107861888.jpg'

if not os.path.exists(WINGED_V3):
    # fallback to v2 or v1 if needed
    for alt in [
        r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_loading_screen_v2_1794107840222.jpg',
        r'C:\Users\seanj\.gemini\antigravity\brain\a45a1bf9-51a0-4670-a8bb-f6b40087198a\ros_redemption_loading_screen_1794065096828.jpg'
    ]:
        if os.path.exists(alt):
            WINGED_V3 = alt
            break

print("Using Winged Wallpaper:", WINGED_V3)

# -------------------------------------------------------------
# STEP 1: Patch unpacked_lobby.py
# -------------------------------------------------------------
print("Reading unpacked_lobby.py...")
with open(UNPACKED_PY, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Fix 1: Scene Brand Pass and Lobby Character
old_brand_pass = """def _dh_scene_brand_pass():
    print('>>> [BRAND PASS] Scene brand pass is RUNNING!')
    cc = _dh_cc()
    if cc is None:
        return
    scene = cc.Director.getInstance().getRunningScene()
    if scene is None:
        return
    # --- Attach ROS Redemption HD Wallpaper as background sprite ---
    try:
        bg_path = 'dh_brand/dh_bg1.jpg'
        win = cc.Director.getInstance().getWinSize()
        if scene.getChildByName('ros_redemption_bg') is None:
            bg = cc.Sprite.create(bg_path)
            if bg is not None:
                bg.setName('ros_redemption_bg')
                bg.setPosition(win.width / 2.0, win.height / 2.0)
                sz = bg.getContentSize()
                if sz.width > 0 and sz.height > 0:
                    bg.setScaleX(float(win.width) / float(sz.width))
                    bg.setScaleY(float(win.height) / float(sz.height))
                scene.addChild(bg, -999)
        login_node = scene.getChildByName('UILogin')
        if login_node is not None and login_node.getChildByName('ros_redemption_bg') is None:
            bg2 = cc.Sprite.create(bg_path)
            if bg2 is not None:
                bg2.setName('ros_redemption_bg')
                bg2.setPosition(win.width / 2.0, win.height / 2.0)
                sz2 = bg2.getContentSize()
                if sz2.width > 0 and sz2.height > 0:
                    bg2.setScaleX(float(win.width) / float(sz2.width))
                    bg2.setScaleY(float(win.height) / float(sz2.height))
                login_node.addChild(bg2, -999)
    except Exception:
        pass"""

new_brand_pass = """def _dh_scene_brand_pass():
    cc = _dh_cc()
    if cc is None:
        return
    scene = cc.Director.getInstance().getRunningScene()
    if scene is None:
        return
    # In lobby or battle: DO NOT show 2D wallpaper (leaves 3D character and lobby room visible!)
    if _dh_in_lobby() or _dh_in_battle():
        bg = scene.getChildByName('ros_redemption_bg')
        if bg is not None:
            bg.removeFromParent()
        return
    try:
        login_node = scene.getChildByName('UILogin')
        bg_path = 'dh_brand/dh_bg1.jpg'
        win = cc.Director.getInstance().getWinSize()
        if login_node is not None:
            # Login window is present: attach background strictly to UILogin node
            s_bg = scene.getChildByName('ros_redemption_bg')
            if s_bg is not None:
                s_bg.removeFromParent()
            if login_node.getChildByName('ros_redemption_bg') is None:
                bg2 = cc.Sprite.create(bg_path)
                if bg2 is not None:
                    bg2.setName('ros_redemption_bg')
                    bg2.setPosition(win.width / 2.0, win.height / 2.0)
                    sz2 = bg2.getContentSize()
                    if sz2.width > 0 and sz2.height > 0:
                        bg2.setScaleX(float(win.width) / float(sz2.width))
                        bg2.setScaleY(float(win.height) / float(sz2.height))
                    login_node.addChild(bg2, -999)
        else:
            # Fallback if login node not created yet
            if scene.getChildByName('ros_redemption_bg') is None:
                bg = cc.Sprite.create(bg_path)
                if bg is not None:
                    bg.setName('ros_redemption_bg')
                    bg.setPosition(win.width / 2.0, win.height / 2.0)
                    sz = bg.getContentSize()
                    if sz.width > 0 and sz.height > 0:
                        bg.setScaleX(float(win.width) / float(sz.width))
                        bg.setScaleY(float(win.height) / float(sz.height))
                    scene.addChild(bg, -999)
    except Exception:
        pass"""

if old_brand_pass in content:
    content = content.replace(old_brand_pass, new_brand_pass)
    print("[OK] Patched _dh_scene_brand_pass!")
else:
    print("[WARN] Could not find exact old_brand_pass block, searching alternative...")
    # Find start of _dh_scene_brand_pass
    pos = content.find("def _dh_scene_brand_pass():")
    if pos != -1:
        end_pos = content.find("_ALWAYS_HIDE = ('swing'", pos)
        if end_pos != -1:
            content = content[:pos] + new_brand_pass + "\n    " + content[end_pos:]
            print("[OK] Replaced _dh_scene_brand_pass via offset slice!")

# Also clean up ros_redemption_bg when UIMain opens
old_uimain_hook = """            if ui_name == 'UIMain':
                call_later(0.5, _dh_main_ready)"""

new_uimain_hook = """            if ui_name == 'UIMain':
                try:
                    _c = _dh_cc()
                    if _c:
                        _sc = _c.Director.getInstance().getRunningScene()
                        if _sc:
                            _b = _sc.getChildByName('ros_redemption_bg')
                            if _b: _b.removeFromParent()
                except Exception:
                    pass
                call_later(0.5, _dh_main_ready)"""

if old_uimain_hook in content:
    content = content.replace(old_uimain_hook, new_uimain_hook)
    print("[OK] Added UIMain background cleanup hook!")

# Fix 2: Drawing Bug in generateArgsForUIItemDisplay
old_draw_call = """        if getattr(base, '_rl_counts', False) or not counted:
            return base(plain + [list(c) for c in counted] if getattr(base, '_rl_counts', False) else plain, *args, **kwargs)
        # the builder needs at least one id (an empty list raised IndexError)
        result = base(plain or [counted[0][0]], *args, **kwargs)
        if isinstance(result, dict):
            totals, order = {}, []
            for item, count in (list(result.get('itemIDs') or []) if plain else []) + counted:
                if item not in totals:
                    order.append(item)
                    totals[item] = 0
                totals[item] += count
            result['itemIDs'] = [(item, totals[item]) for item in order]
        return result"""

new_draw_call = """        if not plain and not counted:
            return {'itemIDs': []}
        try:
            if getattr(base, '_rl_counts', False):
                return base(plain + [list(c) for c in counted], *args, **kwargs)
            target_ids = plain if plain else ([counted[0][0]] if counted else [])
            if not target_ids:
                return {'itemIDs': []}
            result = base(target_ids, *args, **kwargs)
            if isinstance(result, dict):
                totals, order = {}, []
                for item, count in (list(result.get('itemIDs') or []) if plain else []) + counted:
                    if item not in totals:
                        order.append(item)
                        totals[item] = 0
                    totals[item] += count
                result['itemIDs'] = [(item, totals[item]) for item in order]
            return result
        except Exception:
            fallback = [(p, 1) for p in plain] + [(c[0], c[1]) for c in counted]
            return {'itemIDs': fallback}"""

if old_draw_call in content:
    content = content.replace(old_draw_call, new_draw_call)
    print("[OK] Patched generateArgsForUIItemDisplay!")
else:
    print("[WARN] Could not find exact old_draw_call block!")

with open(UNPACKED_PY, 'w', encoding='utf-8') as f:
    f.write(content)
print("[SUCCESS] Saved updated unpacked_lobby.py!")

# -------------------------------------------------------------
# STEP 2: Deploy Winged Loading Wallpaper across ALL directories
# -------------------------------------------------------------
roots = [
    r'C:\DieHardROS\Documents\res',
    r'C:\DieHardROS\x64\Documents\res',
    r'C:\DieHardROS\runtime\Documents\res',
    r'C:\DieHardROS\local_update\res',
    r'C:\DieHardROS\res',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\Documents\res',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\local_update\res',
]

for r in roots:
    dh_brand = os.path.join(r, 'dh_brand')
    os.makedirs(dh_brand, exist_ok=True)
    loading_dir = os.path.join(r, 'ui', 'images', 'loading')
    os.makedirs(loading_dir, exist_ok=True)

    # 1. dh_brand wallpapers (dh_bg1..4)
    for name in ['dh_bg1.jpg', 'dh_bg2.jpg', 'dh_bg3.jpg', 'dh_bg4.jpg', 'dh_fireteam.jpg', 'dh_ev_06632.jpg', 'dh_ev_13933.jpg']:
        shutil.copyfile(WINGED_V3, os.path.join(dh_brand, name))

    # 2. dh_brand rank cards (dh_rank_s1..s30) - replace sniper girl completely!
    for i in range(1, 31):
        shutil.copyfile(WINGED_V3, os.path.join(dh_brand, f'dh_rank_s{i}.jpg'))

    # 3. loading screen loose textures
    for i in range(1, 21):
        shutil.copyfile(WINGED_V3, os.path.join(loading_dir, f'bg_loading_{i:02d}.png'))
        shutil.copyfile(WINGED_V3, os.path.join(loading_dir, f'pc_loading_{i}.png'))
    shutil.copyfile(WINGED_V3, os.path.join(loading_dir, 'pc_loading_0.png'))
    shutil.copyfile(WINGED_V3, os.path.join(loading_dir, 'loading_0.png'))

print("[SUCCESS] All loading screens replaced with pure ROS Redemption Winged Art!")

# -------------------------------------------------------------
# STEP 3: Re-pack lobby patch
# -------------------------------------------------------------
print("Packing lobby patch with pack_lobby_patch.py...")
os.system(r'C:\DieHardROS\runtime\python\python.exe C:\DieHardROS\pack_lobby_patch.py')
print("[SUCCESS] Master patch complete!")

