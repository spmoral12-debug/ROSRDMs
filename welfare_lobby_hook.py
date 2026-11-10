# Appended to the client lobby hook (embedded Python 2.7).
def _redemption_open_welfare(sender, event):
    if int(event) == 2:
        import Globals
        Globals.uiMgr.enter_ui('UIWelfareController')


def _redemption_open_rank(sender=None, event=2):
    if int(event) == 2:
        import Globals
        try:
            Globals.uiMgr.enter_ui('UIRankList')
            return
        except Exception:
            pass
        try:
            import client_utils
            client_utils.doUIJump(612)
            return
        except Exception:
            pass
        try:
            Globals.uiMgr.enter_ui('UIWeekendPush')
        except Exception:
            pass


def _redemption_show_top_tabs():
    import Globals
    manager = getattr(Globals, 'uiMgr', None)
    main = _ui_open(manager, 'UIMain') if manager is not None else None
    if main is None:
        return 0
    found = 0
    for path, node in walk_ui_nodes(main, limit=3000):
        # 1. Handle top navigator entrance tabs (Welfare, data, competition, etc.)
        if path.endswith('/entanceTop') and 'top-navigator' in path:
            try:
                label = node.getChildByName('text')
                txt = str(label.getString()).strip().lower() if label is not None else ''
            except Exception:
                txt = ''

            # Force all tabs to be visible
            try:
                if not node.isVisible():
                    node.setVisible(True)
                    parent = node.getParent()
                    layout = getattr(parent, 'forceDoLayout', None)
                    if callable(layout):
                        layout()
                node.setTouchEnabled(True)
            except Exception:
                pass

            if txt == 'welfare':
                node.addTouchEventListener(_redemption_open_welfare)
                found += 1
            elif txt in ('data', 'competition', 'rank', 'ranking', 'leaderboard'):
                node.addTouchEventListener(_redemption_open_rank)
                found += 1

        # 2. Make player rank badge in lobby clickable to open Leaderboards
        if 'team/anchor-center' in path:
            p_lower = path.lower()
            if any(k in p_lower for k in ('rank', 'badge', 'tier', 'dan')):
                try:
                    node.setTouchEnabled(True)
                    node.addTouchEventListener(_redemption_open_rank)
                    found += 1
                except Exception:
                    pass

    return found


def _redemption_install_welfare(attempt=0):
    import sys
    module = sys.modules.get('ui.main.UIMainFunctionEntrance')
    cls = getattr(module, 'UIMainFunctionEntrance', None) if module else None
    if cls is not None:
        def wrap(original):
            def update(self, *args, **kwargs):
                result = original(self, *args, **kwargs)
                call_later(0, _redemption_show_top_tabs)
                return result
            update._redemption_welfare = True
            return update
        for name in ('updateFunctionList', 'updateListShowState'):
            method = getattr(cls, name, None)
            if callable(method) and not getattr(method, '_redemption_welfare', False):
                setattr(cls, name, wrap(method))
    visible = _redemption_show_top_tabs()
    if visible:
        log('local-redemption-welfare-ready', buttons=visible)
    elif attempt < 60:
        call_later(0.5, _redemption_install_welfare, attempt + 1)


call_later(0.1, _redemption_install_welfare)
