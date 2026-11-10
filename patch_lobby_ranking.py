# -*- coding: utf-8 -*-
import os

target_files = [
    r'clean_remote_lobby.py',
    r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'
]

old_pattern = """def _dh_open_competition(cu):
    \"\"\"competition: the official tournament site is gone, so the tab opens our live competition (Weekend Rush and
    its rank board), else the ranking boards.\"\"\"
    import Globals
    try:
        Globals.uiMgr.enter_ui('UIWeekendPush')
        return 'UIWeekendPush'
    except Exception:
        log_error('local-competition-open-error')
    cu.doUIJump(612)
    return 'rank'


def _dh_bind_top_tabs(ui):
    \"\"\"Each top tab gets its own click listener that jumps to its destination (the panel object that normally
    receives the click message is inactive in this lobby).\"\"\"
    module = _dh_sys.modules.get('ui.main.UIMainFunctionEntrance')
    data = getattr(module, 'legacyProperties', None) if module else None
    if data is None:
        return 0
    dest = {}
    for n, entry in enumerate(data.iterMainEntranceFunctionData()):
        item = entry[1] if isinstance(entry, tuple) and len(entry) == 2 else entry
        try:
            dest[str(getattr(item, 'NAME', '')).strip()] = int(item.JUMP_ID.JUMP_DESTINATION)
        except Exception:
            continue
    cu = _dh_sys.modules.get('client_utils') or __import__('client_utils')
    bound = 0
    for path, node in walk_ui_nodes(ui, limit=3000):
        if not path.endswith('/entanceTop') or 'top-navigator' not in path:
            continue
        try:
            label = node.getChildByName('text')
            name = str(label.getString()).strip() if label is not None else ''
        except Exception:
            continue
        target = dest.get(name)
        if target is None:
            continue

        def on_touch(sender, event, _target=target):
            if int(event) == 2:          # ccui TOUCH_EVENT_ENDED
                try:
                    if _target in _DH_WEB_JUMPS:
                        _dh_open_competition(cu)
                    else:
                        cu.doUIJump(_target)
                except Exception:
                    log_error('local-top-tab-jump-error', target=_target)
        node.addTouchEventListener(on_touch)
        bound += 1
    return bound"""

new_replacement = """def _dh_open_competition(cu):
    \"\"\"ROS REDEMPTION: Opens the Leaderboards / Ranking List (UIRankList)!\"\"\"
    import Globals
    try:
        Globals.uiMgr.enter_ui('UIRankList')
        return 'UIRankList'
    except Exception:
        pass
    try:
        if cu and hasattr(cu, 'doUIJump'):
            cu.doUIJump(612)
            return 'rank'
    except Exception:
        pass
    try:
        Globals.uiMgr.enter_ui('UIWeekendPush')
        return 'UIWeekendPush'
    except Exception:
        pass
    return 'rank'


def _dh_bind_top_tabs(ui):
    \"\"\"ROS REDEMPTION: Unhides and binds Welfare, Data, Competition, and player rank badge to Leaderboards!\"\"\"
    module = _dh_sys.modules.get('ui.main.UIMainFunctionEntrance')
    data = getattr(module, 'legacyProperties', None) if module else None
    dest = {}
    if data is not None:
        for n, entry in enumerate(data.iterMainEntranceFunctionData()):
            item = entry[1] if isinstance(entry, tuple) and len(entry) == 2 else entry
            try:
                dest[str(getattr(item, 'NAME', '')).strip().lower()] = int(item.JUMP_ID.JUMP_DESTINATION)
            except Exception:
                continue
    cu = _dh_sys.modules.get('client_utils') or __import__('client_utils')
    bound = 0
    for path, node in walk_ui_nodes(ui, limit=3000):
        if not path.endswith('/entanceTop') or 'top-navigator' not in path:
            continue
        try:
            node.setVisible(True)
            node.setTouchEnabled(True)
            parent = node.getParent()
            if parent and hasattr(parent, 'forceDoLayout'):
                parent.forceDoLayout()
        except Exception:
            pass

        try:
            label = node.getChildByName('text')
            name = str(label.getString()).strip().lower() if label is not None else ''
        except Exception:
            name = ''

        # All ranking / competition / data entrances open the Leaderboard!
        if name in ('competition', 'data', 'rank', 'ranking', 'leaderboard', 'rankings', 'ladder'):
            def on_rank_touch(sender, event):
                if int(event) == 2:
                    _dh_open_competition(cu)
            node.addTouchEventListener(on_rank_touch)
            bound += 1
            continue

        target = dest.get(name)
        if target is None:
            continue

        def on_touch(sender, event, _target=target):
            if int(event) == 2:
                try:
                    if _target in _DH_WEB_JUMPS:
                        _dh_open_competition(cu)
                    else:
                        cu.doUIJump(_target)
                except Exception:
                    log_error('local-top-tab-jump-error', target=_target)
        node.addTouchEventListener(on_touch)
        bound += 1

    try:
        import Globals
        for path, node in walk_ui_nodes(ui, limit=3000):
            if 'team/anchor-center' in path:
                p_lower = path.lower()
                if any(k in p_lower for k in ('rank', 'badge', 'tier', 'dan', 'level')):
                    def on_badge_touch(sender, event):
                        if int(event) == 2:
                            _dh_open_competition(cu)
                    node.setTouchEnabled(True)
                    node.addTouchEventListener(on_badge_touch)
    except Exception:
        pass

    return bound"""

for file_path in target_files:
    if os.path.exists(file_path):
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Normalize newlines
        content_norm = content.replace('\r\n', '\n')
        old_norm = old_pattern.replace('\r\n', '\n')
        new_norm = new_replacement.replace('\r\n', '\n')
        
        if old_norm in content_norm:
            content_norm = content_norm.replace(old_norm, new_norm)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content_norm.replace('\n', '\r\n'))
            print("Successfully patched:", file_path)
        elif new_norm in content_norm:
            print("Already patched:", file_path)
        else:
            print("Pattern not found in:", file_path)
    else:
        print("File does not exist:", file_path)

