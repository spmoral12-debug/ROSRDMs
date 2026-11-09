import os

new_branding_func = '''
def _dh_apply_screen_branding(name, ui):
    if ui is None:
        return
    try:
        # Force official server values on UI object
        try:
            setattr(ui, '_currentSelectServerName', 'ROS-Redemption-Official')
            setattr(ui, '_currentSelectGroupId', 10501)
            setattr(ui, '_currentSelectServerIp', '127.0.0.1')
            setattr(ui, '_currentSelectServerPort', 19000)
            setattr(ui, '_currentSelectZoneName', 'ROS-Redemption')
        except Exception:
            pass

        # 1. Stop and remove layer_swing, QR code, Facebook from UILogin
        for attr in ('layer_swing', 'qrcode_img', 'UIFollowonFacebook', 'btn_agreement'):
            w = getattr(ui, attr, None)
            if w is not None:
                try:
                    if hasattr(w, 'stopAllActions'): w.stopAllActions()
                    w.setVisible(False)
                    w.setPosition(-99999, -99999)
                    if hasattr(w, 'removeFromParent'): w.removeFromParent()
                except Exception:
                    pass

        # 2. Add full-screen ROS Redemption Wallpaper on Cocos2D panel
        panel = getattr(ui, 'panel', None)
        if panel is not None and not getattr(ui, '_has_redemption_bg', False):
            try:
                import cc
                win = cc.Director.getInstance().getWinSize()
                bg = cc.Sprite.create('dh_brand/dh_bg1.jpg')
                if bg:
                    bg.setPosition(win.width / 2.0, win.height / 2.0)
                    sz = bg.getContentSize()
                    if sz.width > 0 and sz.height > 0:
                        bg.setScaleX(float(win.width) / float(sz.width))
                        bg.setScaleY(float(win.height) / float(sz.height))
                    panel.addChild(bg, 0)
                    ui._has_redemption_bg = True
            except Exception:
                pass

        # 3. Iterate all widgets
        for path, node in walk_ui_nodes(ui, limit=1500):
            try:
                p_low = path.lower()
                leaf = path.split('/')[-1].lower()

                # Remove street squad, QR code, Facebook, old animated layers
                if any(k in p_low for k in ('swing', 'panel_di', 'panel_che', 'qrcode', 'facebook', 'icon_facebook', 'bg_login_word', 'vng_logo', 'erweima')):
                    try:
                        if hasattr(node, 'stopAllActions'): node.stopAllActions()
                        node.setVisible(False)
                        node.setPosition(-99999, -99999)
                        if hasattr(node, 'removeFromParent'): node.removeFromParent()
                    except Exception:
                        pass
                    continue

                # Hide the login screen logo widget because dh_bg1.jpg already has the 3D winged ROS Redemption Battle Royale logo!
                if 'logo' in leaf and 'btn' not in leaf and 'icon' not in leaf:
                    try:
                        node.setVisible(False)
                        node.setPosition(-99999, -99999)
                    except Exception:
                        pass
                    continue

                render = ''
                for g in ('getRenderFile', 'getTextureFile', 'getBackGroundImageFile'):
                    fn = getattr(node, g, None)
                    if callable(fn):
                        try:
                            render = str(fn()).lower()
                            break
                        except Exception:
                            pass

                # Background textures
                if 'bg' in leaf or 'background' in leaf or 'bg_loading' in render:
                    _dh_swap_tex(node, 'dh_brand/dh_bg1.jpg')

                # Server List & Zone text rebranding
                text = _node_text(node)
                setter = _node_setter(node)
                if text:
                    t_low = text.lower()
                    if any(k in t_low for k in ('skygame', 'official website', 'ros.skygame.io', 'dicord', 'discord')):
                        try:
                            node.setVisible(False)
                            p = node.getParent()
                            if p: p.setVisible(False)
                        except Exception:
                            pass
                        if setter: setter('')
                    elif any(k in t_low for k in ('ph-diehard', 'my-asia', 'pc-asia', 'diehard', 'legacy', 'pc-manila', 'pc-singapore', 'pc-tokyo', 'pc-sandbox')):
                        if setter: setter('ROS-Redemption-Official')
                    elif t_low in ('asia', 'america', 'europe', 'north america', 'pc', 'pc-america', 'pc-europe'):
                        if setter: setter('ROS-Redemption')
                    elif 'select server' in t_low or 'elect server' in t_low:
                        if setter: setter('ROS-Redemption-Official')
            except Exception:
                pass
    except Exception:
        pass
'''

target_files = [
    r'C:\DieHardROS\runtime\app\client\lobby_hook.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app\client\lobby_hook.py'
]

for p in target_files:
    if os.path.exists(p):
        with open(p, 'r', encoding='utf-8', errors='ignore') as f:
            src = f.read()

        s = src.find('def _dh_apply_screen_branding(')
        e = src.find('\ndef _dh_check_login_screens():', s)
        if s >= 0 and e >= 0:
            src = src[:s] + new_branding_func.strip() + '\n\n' + src[e+1:]
            with open(p, 'w', encoding='utf-8') as f:
                f.write(src)
            print("Successfully updated _dh_apply_screen_branding in:", p)
        else:
            print("Could not locate boundary in:", p)

