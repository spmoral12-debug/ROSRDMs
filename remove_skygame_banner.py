import os

hook_file = r"C:\DieHardROS\runtime\app\client\lobby_hook.py"
with open(hook_file, "r", encoding="utf-8") as f:
    src = f.read()

# Palitan ang anumang direct text
src = src.replace("ros.skygame.io", "")
src = src.replace("Official website:", "")
src = src.replace("Official website", "")
src = src.replace("elect Server", "")
src = src.replace("Select Server", "")

# I-update ang _dh_run_art_swap para awtomatikong itago ang ribbon at ayusin ang text
idx = src.find("def _dh_run_art_swap(name, ui):")
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
                
                # 1. Logo Replacement (Transparent, Walang Black Box)
                if 'img_login_logo' in render or ('logo' in leaf and 'btn' not in leaf):
                    _dh_swap_logo_fit(node, 'dh_brand/dh_logo_1.png')
                
                # 2. Tanggalin nang buo ang SkyGame Website ribbon at Home Icon
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
                    
                    # 3. Linisin ang server selector sa ibabaw ng PLAY
                    if 'elect server' in t_low:
                        if setter: setter('Fast ROS-Redemption-Official')
            except Exception:
                pass
    except Exception:
        pass"""
        src = src[:idx] + clean_swap + src[end_idx:]

with open(hook_file, "w", encoding="utf-8") as f:
    f.write(src)

print(">>> Hook successfully updated: SkyGame Banner removed, Logo transparent, Server text clean!")
