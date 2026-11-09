# Appended to the client lobby hook (embedded Python 2.7).
def _redemption_open_welfare(sender, event):
    if int(event) == 2:
        import Globals
        Globals.uiMgr.enter_ui('UIWelfareController')


def _redemption_show_welfare():
    import Globals
    manager = getattr(Globals, 'uiMgr', None)
    main = _ui_open(manager, 'UIMain') if manager is not None else None
    if main is None:
        return 0
    found = 0
    for path, node in walk_ui_nodes(main, limit=3000):
        if not path.endswith('/entanceTop') or 'top-navigator/entance_list_fixed/' not in path:
            continue
        try:
            label = node.getChildByName('text')
            if label is None or str(label.getString()).strip().lower() != 'welfare':
                continue
            if not node.isVisible():
                node.setVisible(True)
                parent = node.getParent()
                layout = getattr(parent, 'forceDoLayout', None)
                if callable(layout):
                    layout()
            node.setTouchEnabled(True)
            node.addTouchEventListener(_redemption_open_welfare)
            found += 1
        except Exception:
            log_error('local-redemption-welfare-widget-error')
    return found


def _redemption_install_welfare(attempt=0):
    import sys
    module = sys.modules.get('ui.main.UIMainFunctionEntrance')
    cls = getattr(module, 'UIMainFunctionEntrance', None) if module else None
    if cls is not None:
        def wrap(original):
            def update(self, *args, **kwargs):
                result = original(self, *args, **kwargs)
                call_later(0, _redemption_show_welfare)
                return result
            update._redemption_welfare = True
            return update
        for name in ('updateFunctionList', 'updateListShowState'):
            method = getattr(cls, name, None)
            if callable(method) and not getattr(method, '_redemption_welfare', False):
                setattr(cls, name, wrap(method))
    visible = _redemption_show_welfare()
    if visible:
        log('local-redemption-welfare-ready', buttons=visible)
    elif attempt < 60:
        call_later(0.5, _redemption_install_welfare, attempt + 1)


call_later(0.1, _redemption_install_welfare)
