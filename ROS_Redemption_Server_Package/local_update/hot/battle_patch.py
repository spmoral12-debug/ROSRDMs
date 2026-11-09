# ==========================================================
# ROS REDEMPTION - BATTLE HOT PATCH
# ==========================================================
# Fixes common engine transition glitches:
# 1. iTrainSpace.refreshMapUI unpack ValueError
# 2. iPerspective.isPerspected NoneType keys error
# ==========================================================
import sys

def _patch_train_space():
    try:
        mod = sys.modules.get('iTrainSpace')
        if not mod:
            try:
                import iTrainSpace as mod
            except Exception:
                mod = None
        if mod and hasattr(mod, 'iTrainSpace'):
            cls = mod.iTrainSpace
            orig = getattr(cls, 'refreshMapUI', None)
            if orig and not getattr(orig, '_redemption_guard', False):
                def safe_refreshMapUI(self, *args, **kwargs):
                    try:
                        return orig(self, *args, **kwargs)
                    except Exception:
                        return None
                safe_refreshMapUI._redemption_guard = True
                cls.refreshMapUI = safe_refreshMapUI
                log('ros-redemption-patch', fix='iTrainSpace.refreshMapUI guarded')
    except Exception:
        pass

def _patch_perspective():
    try:
        mod = sys.modules.get('iPerspective')
        if not mod:
            try:
                import iPerspective as mod
            except Exception:
                mod = None
        if mod and hasattr(mod, 'iPerspective'):
            cls = mod.iPerspective
            orig = getattr(cls, 'isPerspected', None)
            if orig and not getattr(orig, '_redemption_guard', False):
                def safe_isPerspected(self, *args, **kwargs):
                    try:
                        return orig(self, *args, **kwargs)
                    except Exception:
                        return False
                safe_isPerspected._redemption_guard = True
                cls.isPerspected = safe_isPerspected
                log('ros-redemption-patch', fix='iPerspective.isPerspected guarded')
    except Exception:
        pass

try:
    _patch_train_space()
    _patch_perspective()
    log('ros-redemption-battle-patch-loaded', status='active')
except Exception:
    pass

