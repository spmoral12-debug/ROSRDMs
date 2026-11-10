# Appended to the client lobby hook (embedded Python 2.7).
def _redemption_open_welfare(sender, event):
    if int(event) == 2:
        import Globals
        Globals.uiMgr.enter_ui('UIWelfareController')


def _redemption_open_data(sender, event):
    if int(event) == 2:
        import Globals
        try:
            Globals.uiMgr.enter_ui('UIRankList')
        except Exception:
            try:
                import sys
                cu = sys.modules.get('client_utils') or __import__('client_utils')
                cu.doUIJump(612)
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
        # Prevent dynamic overlay list from swallowing touches over fixed tabs
        if 'top-navigator/entance_list_dynamic' in path:
            try:
                shown = [i for i in (node.getItems() or []) if i.isVisible()] if hasattr(node, 'getItems') else []
                if not shown:
                    node.setTouchEnabled(False)
                if hasattr(node, 'setSwallowTouches'):
                    node.setSwallowTouches(False)
            except Exception:
                pass

        if not path.endswith('/entanceTop') or 'top-navigator' not in path:
            continue
        try:
            txt = ''
            label = node.getChildByName('text') if hasattr(node, 'getChildByName') else None
            if label is not None and hasattr(label, 'getString'):
                try:
                    txt = str(label.getString()).strip().lower()
                except Exception:
                    pass
            if not txt and '_node_text' in globals():
                try:
                    txt = str(_node_text(node) or '').strip().lower()
                except Exception:
                    pass

            target_cb = None
            if txt == 'welfare' or 'welfare' in txt:
                target_cb = _redemption_open_welfare
            elif txt == 'data' or 'data' in txt or txt in ('leaderboard', 'rank', 'ranking'):
                target_cb = _redemption_open_data

            if target_cb is not None:
                if not node.isVisible():
                    node.setVisible(True)
                    parent = node.getParent()
                    layout = getattr(parent, 'forceDoLayout', None)
                    if callable(layout):
                        layout()
                node.setTouchEnabled(True)
                node.addTouchEventListener(target_cb)
                found += 1
        except Exception:
            log_error('local-redemption-top-tab-widget-error')
    return found


def _redemption_show_welfare():
    return _redemption_show_top_tabs()


def _redemption_show_data():
    return _redemption_show_top_tabs()


def _redemption_install_top_tabs(attempt=0):
    import sys
    module = sys.modules.get('ui.main.UIMainFunctionEntrance')
    cls = getattr(module, 'UIMainFunctionEntrance', None) if module else None
    if cls is not None:
        def wrap(original):
            def update(self, *args, **kwargs):
                result = original(self, *args, **kwargs)
                call_later(0, _redemption_show_top_tabs)
                return result
            update._redemption_top_tabs = True
            return update
        for name in ('updateFunctionList', 'updateListShowState', 'onTeamStateUpdate'):
            method = getattr(cls, name, None)
            if callable(method) and not getattr(method, '_redemption_top_tabs', False):
                setattr(cls, name, wrap(method))
    visible = _redemption_show_top_tabs()
    if visible:
        log('local-redemption-top-tabs-ready', buttons=visible)
    elif attempt < 60:
        call_later(0.5, _redemption_install_top_tabs, attempt + 1)


def _redemption_install_welfare(attempt=0):
    _redemption_install_top_tabs(attempt)


call_later(0.1, _redemption_install_top_tabs)


# ==========================================================================
# WORKSHOP: VEHICLE / APPEARANCE CULTIVATION & TUNE COMPOUND FIX
# ==========================================================================

def _dh_restore_mall_and_supply_ui():
    """Restores goods panels, subtabs, and visibility for Mall and Supply when UIItemDisplay closes."""
    try:
        import Globals
        ui_mgr = getattr(Globals, 'uiMgr', None)
        if not ui_mgr:
            return
        target_screens = [
            'UIMallController', 'UIMallCloth', 'UIMall',
            'UISupplyController', 'UISupplyPackage', 'UIAdvanceSupplyPackage',
            'UIMonthlySupplyPackage', 'UIMainActionAndEmoji',
            'UIDtsAppearance', 'UIDtsAppearanceVehicleCultivate2', 'UIWorkshop'
        ]
        for scr_name in target_screens:
            scr = getattr(ui_mgr, scr_name, None)
            if scr is not None and getattr(scr, 'is_enter', False):
                try:
                    if hasattr(scr, 'setVisible'):
                        scr.setVisible(True)
                    if hasattr(scr, 'leaveFullScreen') and callable(scr.leaveFullScreen):
                        scr.leaveFullScreen()
                    if hasattr(scr, 'refreshGeneralDisplayPanel') and callable(scr.refreshGeneralDisplayPanel):
                        scr.refreshGeneralDisplayPanel()
                    if hasattr(scr, 'refresh') and callable(scr.refresh):
                        scr.refresh()
                    if hasattr(scr, 'refreshMall') and callable(scr.refreshMall):
                        scr.refreshMall()
                    if hasattr(scr, 'fillGoods') and callable(scr.fillGoods):
                        try:
                            import BigWorld
                            p = BigWorld.player()
                            if p:
                                g = getattr(p, 'recordMallGoods', None)
                                if isinstance(g, dict) and g:
                                    scr.fillGoods(g)
                        except Exception:
                            pass
                    root = getattr(scr, 'panel', None) or getattr(scr, 'widget', None)
                    if root is not None:
                        if hasattr(root, 'setVisible'):
                            root.setVisible(True)
                        for path, node in walk_ui_nodes(scr, limit=500):
                            p_low = path.lower()
                            if any(k in p_low for k in ('right', 'goods', 'cloth', 'item_list', 'listview', 'panel_1', 'panel_di', 'panel_content', 'tab')):
                                try:
                                    node.setVisible(True)
                                except Exception:
                                    pass
                except Exception:
                    pass
    except Exception:
        pass


def _dh_fix_item_display_ui():
    """Ensure UIItemDisplay's BACK, Return and Confirm buttons are active and responsive."""
    try:
        import Globals
        ui_mgr = getattr(Globals, 'uiMgr', None)
        if not ui_mgr:
            return
        disp = getattr(ui_mgr, 'UIItemDisplay', None)
        if disp is not None and getattr(disp, 'is_enter', False):
            # 1. Ensure result panel and dlg root are visible
            for p in ('dlg', 'dlg/result_panel', 'dlg/result_panel/anchor-upper-left', 'dlg/result_panel/anchor-bottom-right', 'dlg/result_panel/anchor-bottom-left'):
                try:
                    w = disp.get_widget_by_path(p)
                    if w is not None:
                        w.setVisible(True)
                except Exception:
                    pass

            def _on_leave(sender, event):
                if event == 2 or event == 0:
                    try:
                        if hasattr(disp, 'doReturnBtnClick') and callable(disp.doReturnBtnClick):
                            disp.doReturnBtnClick()
                        elif callable(getattr(disp, 'returnBtnCb', None)):
                            disp.returnBtnCb()
                            ui_mgr.leave_ui('UIItemDisplay')
                        else:
                            ui_mgr.leave_ui('UIItemDisplay')
                    except Exception:
                        try:
                            ui_mgr.leave_ui('UIItemDisplay')
                        except Exception:
                            pass
                    call_later(0.1, _dh_restore_mall_and_supply_ui)

            def _on_confirm(sender, event):
                if event == 2 or event == 0:
                    try:
                        if hasattr(disp, 'onConfirmBtnClick') and callable(disp.onConfirmBtnClick):
                            disp.onConfirmBtnClick(sender)
                        elif callable(getattr(disp, 'confirmBtnCb', None)):
                            disp.confirmBtnCb()
                            ui_mgr.leave_ui('UIItemDisplay')
                        else:
                            ui_mgr.leave_ui('UIItemDisplay')
                    except Exception:
                        try:
                            ui_mgr.leave_ui('UIItemDisplay')
                        except Exception:
                            pass
                    call_later(0.1, _dh_restore_mall_and_supply_ui)

            # 2. Wire returnBtn directly
            ret_btn = getattr(disp, 'returnBtn', None) or disp.get_widget_by_path('dlg/result_panel/anchor-upper-left/returnBtn')
            if ret_btn is not None:
                try:
                    ret_btn.setVisible(True)
                    ret_btn.setTouchEnabled(True)
                    ret_btn.addTouchEventListener(_on_leave)
                except Exception:
                    pass

            # 3. Wire confirmBtn directly
            conf_btn = getattr(disp, 'confirmBtn', None) or disp.get_widget_by_path('dlg/result_panel/anchor-bottom-right/confirmBtn')
            if conf_btn is not None:
                try:
                    conf_btn.setVisible(True)
                    conf_btn.setTouchEnabled(True)
                    conf_btn.addTouchEventListener(_on_confirm)
                except Exception:
                    pass

            # 4. Suppress duplicate "To Lobby" label
            try:
                txt = getattr(disp, 'returnBtnTxt', None)
                if txt is not None:
                    txt.setVisible(False)
            except Exception:
                pass

            # 5. Walk nodes to ensure all back/confirm/leave widgets are armed
            for path, node in walk_ui_nodes(disp, limit=400):
                p_low = path.lower()
                if 'return_btn_txt' in p_low:
                    try:
                        node.setVisible(False)
                    except Exception:
                        pass
                    continue
                if any(k in p_low for k in ('btn_back', 'btn_return', 'btnback', 'button_back', 'btn_close', 'returnbtn')):
                    if any(p_low.endswith(x) for x in ('_txt', '/text', '/txt', '_label')):
                        continue
                    try:
                        node.setVisible(True)
                        node.setTouchEnabled(True)
                        node.addTouchEventListener(_on_leave)
                    except Exception:
                        pass
                elif any(k in p_low for k in ('btn_confirm', 'btnconfirm', 'buyagain')):
                    if any(p_low.endswith(x) for x in ('_txt', '/text', '/txt', '_label')):
                        continue
                    try:
                        node.setVisible(True)
                        node.setTouchEnabled(True)
                        node.addTouchEventListener(_on_confirm)
                    except Exception:
                        pass

            # 6. Background tap to leave
            try:
                bg = getattr(disp, 'bg', None) or disp.get_widget_by_path('dlg/result_panel/BG')
                if bg is not None:
                    bg.setTouchEnabled(True)
                    bg.addTouchEventListener(_on_leave)
            except Exception:
                pass

            # 7. Floating fail-safe BACK button on running scene
            try:
                cc = _dh_cc()
                if cc:
                    sc = cc.Director.getInstance().getRunningScene()
                    if sc and sc.getChildByName('dh_item_disp_fail_safe') is None:
                        win = cc.Director.getInstance().getWinSize()
                        lbl = cc.LabelTTF.create("< BACK", "Arial", 22)
                        lbl.setColor(cc.c3b(255, 255, 255))
                        lbl.setName('dh_item_disp_fail_safe')
                        lbl.setPosition(65.0, win.height - 40.0)
                        lbl.setTouchEnabled(True)
                        lbl.addTouchEventListener(_on_leave)
                        sc.addChild(lbl, 99999)
            except Exception:
                pass
    except Exception:
        pass


def _dh_rpc_appearance_cultivate_compound(player, *args, **kwargs):
    """Handle Workshop Tune: base.appearanceCultivateCompound(srcID, targetID, flag).
    Deducts 1x src item and 1000 Gold, grants 1x target item, and calls onAppearanceCultivateCompound."""
    try:
        src_id = kwargs.get('src_id') if kwargs.get('src_id') is not None else (args[0] if len(args) > 0 else 0)
        target_id = kwargs.get('target_id') if kwargs.get('target_id') is not None else (args[1] if len(args) > 1 else 0)
        flag = kwargs.get('flag') if kwargs.get('flag') is not None else (args[2] if len(args) > 2 else 0)
        src_id = int(src_id or 0)
        target_id = int(target_id or 0)
    except Exception:
        log_error('local-cultivate-parse-error', args=safe(args))
        return None

    if not target_id:
        log('local-cultivate-no-target', src_id=src_id, target_id=target_id)
        return None

    try:
        import BigWorld
        BigWorld._dh_last_cultivate_target = target_id
    except Exception:
        pass

    log('local-cultivate-start', src_id=src_id, target_id=target_id)

    # 1. Deduct cost / source appearance item (1 copy)
    if src_id:
        try:
            remove_appearance_copies(player, src_id, 1)
        except Exception:
            log_error('local-cultivate-remove-src-error', src_id=src_id)

    # 2. Deduct Gold (1000 GP)
    cost = 1000
    try:
        current_gp = getattr(player, 'gp', 0) or 0
        if current_gp >= cost:
            setattr(player, 'gp', current_gp - cost)
            refresh_currency_ui(player, set(['gp']))
            refresh_lobby_profile()
    except Exception:
        log_error('local-cultivate-gp-error')

    # 3. Add target appearance item to player's package
    try:
        _push_one_item(player, target_id, 1, 0, package='appearance')
    except Exception:
        log_error('local-cultivate-push-target-error', target_id=target_id)

    # 4. Notify backend server if reachable to persist in database
    try:
        call_pyserver('appearanceCultivateCompound', (src_id, target_id, flag), kwargs)
    except Exception:
        pass

    # 5. Deliver callback onAppearanceCultivateCompound to player
    cb = getattr(player, 'onAppearanceCultivateCompound', None)
    if callable(cb):
        try:
            call_later(0.1, cb, target_id)
        except Exception:
            log_error('local-cultivate-cb-error', target_id=target_id)

    # 6. Safety check: ensure UIItemDisplay BACK button is armed
    try:
        call_later(0.3, _dh_fix_item_display_ui)
        call_later(1.0, _dh_fix_item_display_ui)
        call_later(2.0, _dh_fix_item_display_ui)
    except Exception:
        pass

    return True

try:
    RPC_HANDLERS['appearanceCultivateCompound'] = _dh_rpc_appearance_cultivate_compound
except Exception:
    pass

