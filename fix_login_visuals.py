import os

hook_file = r"C:\DieHardROS\runtime\app\client\lobby_hook.py"
with open(hook_file, "r", encoding="utf-8") as f:
    src = f.read()

# 1. Alisin ang text collision na 'elect Server'
src = src.replace("elect Server", "")
src = src.replace("Select Server", "")

# 2. I-lock ang logo para ROS Redemption transparent logo LANG ang kukunin lagi
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
                
                # Malinis na Logo Replacement: Walang Black Box, Walang SkyGame
                if 'img_login_logo' in render or ('logo' in leaf and 'btn' not in leaf):
                    _dh_swap_logo_fit(node, 'dh_brand/dh_logo_1.png')
                    
                # Linisin ang text sa server selector sa ibabaw ng PLAY
                setter = _node_setter(node)
                text = _node_text(node)
                if setter is not None and text:
                    if 'elect server' in text.lower():
                        setter('Fast ROS-Redemption-Official')
            except Exception:
                pass
    except Exception:
        pass"""
        src = src[:idx] + clean_swap + src[end_idx:]

with open(hook_file, "w", encoding="utf-8") as f:
    f.write(src)

print(">>> Hook and Server text successfully cleaned!")
