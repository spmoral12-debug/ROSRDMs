# Appended to the client lobby hook before injection (embedded Python 2.7).
def _redemption_patch_screen_tick(tick=0):
    import re
    try:
        import Globals
        manager = getattr(Globals, 'uiMgr', None)
        patch = _ui_open(manager, 'UIPatch') if manager is not None else None
        if patch is not None:
            for path, node in walk_ui_nodes(patch, limit=800):
                try:
                    path = path.strip('/').lower()
                    if path.endswith('ui_patch/bg'):
                        art = 'dh_brand/dh_redemption_loading.jpg'
                        get_file = getattr(node, 'getTextureFilename', None)
                        current = get_file() if callable(get_file) else None
                        loader = getattr(node, 'loadTexture', None) or getattr(node, 'setTexture', None)
                        if callable(loader) and art != current and (
                                current is not None or not getattr(patch, '_redemption_art_loaded', False)):
                            loader(art)
                            if not getattr(patch, '_redemption_art_loaded', False):
                                patch._redemption_art_loaded = True
                                log('local-redemption-patch-art', path=path)
                    text = _node_text(node)
                    if text and 'skygame.io' in text.lower():
                        setter = _node_setter(node)
                        if setter is not None:
                            updated = re.sub(r'(?:https?://)?(?:ros\.|www\.)?skygame\.io',
                                             'www.ros-redemption.com', text, flags=re.I)
                            if updated != text:
                                setter(updated)
                                if not getattr(patch, '_redemption_url_loaded', False):
                                    patch._redemption_url_loaded = True
                                    log('local-redemption-patch-website', path=path)
                except Exception:
                    pass
    except Exception:
        log_error('local-redemption-patch-screen-error')
    if tick < 400:
        call_later(0.15, _redemption_patch_screen_tick, tick + 1)


call_later(0.05, _redemption_patch_screen_tick)
