import sys, os

hook_file = r"C:\DieHardROS\runtime\app\client\lobby_hook.py"
with open(hook_file, "r", encoding="utf-8") as f:
    src = f.read()

# 1. Patayin ang _dh_write_art para HINDI na mag-extract ng lumang sniper base64
idx = src.find("def _dh_write_art(")
if idx >= 0:
    end_idx = src.find("\ndef ", idx + 10)
    if end_idx >= 0:
        src = src[:idx] + "def _dh_write_art(*args, **kwargs):\n    return None\n\n" + src[end_idx+1:]

# 2. Siguraduhing tama ang brand dir
src = src.replace(r"C:\ROS RedemptionROS\Documents\res\dh_brand", r"C:\DieHardROS\Documents\res\dh_brand")

# 3. Linisin ang mga salitang skygame at server overlap
src = src.replace("ros.skygame.io", "")
src = src.replace("Official website:", "")
src = src.replace("Official website", "")
src = src.replace("elect Server", "")
src = src.replace("Select Server", "")

# 4. Linisin ang screen swap function
swap_marker = "def _dh_run_art_swap(name, ui):"
idx = src.find(swap_marker)
if idx >= 0:
    end_idx = src.find("\ndef _dh_check_screens():", idx)
    if end_idx >= 0:
        clean_swap = """def _dh_run_art_swap(name, ui):
    try:
        for path, node in walk_ui_nodes(ui, limit=1000):
            try:
                leaf = path.split('/')[-1].lower()
                render = ''
                for getter in ('getRenderFile', 'getTextureFile', 'getBackGroundImageFile'):
                    fn = getattr(node, getter, None)
                    if callable(fn):
                        try:
                            render = str(fn()).lower()
                            break
                        except Exception:
                            pass
                
                # 1. Loading screen swap (Kahit anong loading bg, gawing ROS Redemption)
                if 'loading' in name.lower():
                    if 'bg' in leaf or 'background' in leaf or 'loading' in leaf or 'pic' in leaf or 'img' in leaf:
                        _dh_swap_texture(node, 'dh_brand/dh_bg1.jpg')
                
                # 2. Login Screen Logo (Transparent, walang black box)
                if 'img_login_logo' in render or ('logo' in leaf and 'btn' not in leaf):
                    _dh_swap_logo_fit(node, 'dh_brand/dh_logo_1.png')
                
                # 3. Tanggalin nang buo ang SkyGame Website banner at Home icon
                text = _node_text(node)
                setter = _node_setter(node)
                if text:
                    t_low = text.lower()
                    if 'skygame' in t_low or 'official website' in t_low or 'website' in t_low:
                        try:
                            node.setVisible(False)
                            parent = node.getParent()
                            if parent: parent.setVisible(False)
                        except Exception:
                            pass
                        if setter: setter('')
                    
                    if 'elect server' in t_low:
                        if setter: setter('Fast ROS-Redemption-Official')
            except Exception:
                pass
    except Exception:
        pass"""
        src = src[:idx] + clean_swap + src[end_idx:]

with open(hook_file, "w", encoding="utf-8") as f:
    f.write(src)

print(">>> Lobby Hook successfully patched and validated!")
