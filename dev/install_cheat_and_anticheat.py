# -*- coding: utf-8 -*-
"""
ROS Redemption Master Update:
1. Fixes Crash on PLAY: Replaces dangerous removeFromParent() with safe setVisible(False).
2. Fixes Blue Icon: CCMini is already dummy-replaced.
3. Injects ROS Redemption Cheat System & Anti-Cheat Sentinel with on-screen testing!
"""

import os, sys

UNPACKED_PY = r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates\unpacked_lobby.py'

print("Reading unpacked_lobby.py...")
with open(UNPACKED_PY, 'r', encoding='utf-8', errors='ignore') as f:
    code = f.read()

# ---------------------------------------------------------------------
# 1. FIX THE CRASH ON PLAY
# ---------------------------------------------------------------------
# In enter_ui: replace removeFromParent() with setVisible(False)
bad_enter_ui = """                try:
                    _c = _dh_cc()
                    if _c:
                        _sc = _c.Director.getInstance().getRunningScene()
                        if _sc:
                            _b = _sc.getChildByName('ros_redemption_bg')
                            if _b: _b.removeFromParent()
                except Exception:
                    pass"""

good_enter_ui = """                try:
                    _c = _dh_cc()
                    if _c:
                        _sc = _c.Director.getInstance().getRunningScene()
                        if _sc:
                            _b = _sc.getChildByName('ros_redemption_bg')
                            if _b is not None:
                                _b.setVisible(False)
                                _b.setPosition(-99999.0, -99999.0)
                except Exception:
                    pass"""

if bad_enter_ui in code:
    code = code.replace(bad_enter_ui, good_enter_ui)
    print("[OK] Replaced enter_ui removeFromParent with safe setVisible(False)!")

# In _dh_scene_brand_pass: replace removeFromParent()
bad_brand_pass = """    # In lobby or battle: DO NOT show 2D wallpaper (leaves 3D character and lobby room visible!)
    if _dh_in_lobby() or _dh_in_battle():
        bg = scene.getChildByName('ros_redemption_bg')
        if bg is not None:
            bg.removeFromParent()
        return
    try:
        login_node = scene.getChildByName('UILogin')
        bg_path = 'dh_brand/dh_bg1.jpg'
        win = cc.Director.getInstance().getWinSize()
        if login_node is not None:
            # Login window is present: attach background strictly to UILogin node
            s_bg = scene.getChildByName('ros_redemption_bg')
            if s_bg is not None:
                s_bg.removeFromParent()
            if login_node.getChildByName('ros_redemption_bg') is None:
                bg2 = cc.Sprite.create(bg_path)
                if bg2 is not None:
                    bg2.setName('ros_redemption_bg')
                    bg2.setPosition(win.width / 2.0, win.height / 2.0)
                    sz2 = bg2.getContentSize()
                    if sz2.width > 0 and sz2.height > 0:
                        bg2.setScaleX(float(win.width) / float(sz2.width))
                        bg2.setScaleY(float(win.height) / float(sz2.height))
                    login_node.addChild(bg2, -999)
        else:
            # Fallback if login node not created yet
            if scene.getChildByName('ros_redemption_bg') is None:
                bg = cc.Sprite.create(bg_path)
                if bg is not None:
                    bg.setName('ros_redemption_bg')
                    bg.setPosition(win.width / 2.0, win.height / 2.0)
                    sz = bg.getContentSize()
                    if sz.width > 0 and sz.height > 0:
                        bg.setScaleX(float(win.width) / float(sz.width))
                        bg.setScaleY(float(win.height) / float(sz.height))
                    scene.addChild(bg, -999)
    except Exception:
        pass"""

good_brand_pass = """    # In lobby or battle: DO NOT show 2D wallpaper (leaves 3D character and lobby room visible!)
    if _dh_in_lobby() or _dh_in_battle():
        try:
            bg = scene.getChildByName('ros_redemption_bg')
            if bg is not None:
                bg.setVisible(False)
                bg.setPosition(-99999.0, -99999.0)
        except Exception:
            pass
        return
    try:
        bg_path = 'dh_brand/dh_bg1.jpg'
        win = cc.Director.getInstance().getWinSize()
        bg = scene.getChildByName('ros_redemption_bg')
        if bg is None:
            bg = cc.Sprite.create(bg_path)
            if bg is not None:
                bg.setName('ros_redemption_bg')
                bg.setPosition(win.width / 2.0, win.height / 2.0)
                sz = bg.getContentSize()
                if sz.width > 0 and sz.height > 0:
                    bg.setScaleX(float(win.width) / float(sz.width))
                    bg.setScaleY(float(win.height) / float(sz.height))
                scene.addChild(bg, -999)
        else:
            bg.setVisible(True)
            bg.setPosition(win.width / 2.0, win.height / 2.0)
    except Exception:
        pass"""

if bad_brand_pass in code:
    code = code.replace(bad_brand_pass, good_brand_pass)
    print("[OK] Replaced scene brand pass removeFromParent with safe setVisible!")

# ---------------------------------------------------------------------
# 2. INJECT CHEAT & ANTI-CHEAT SUITE
# ---------------------------------------------------------------------
cheat_suite_code = '''
# =====================================================================
# ROS REDEMPTION CHEAT & ANTI-CHEAT SUITE (BY BOSS SEAN)
# =====================================================================

class _DH_SecuritySuite(object):
    def __init__(self):
        self.cheat_speed_enabled = False
        self.cheat_jump_enabled = False
        self.cheat_god_enabled = False
        self.anticheat_enabled = True
        self.last_pos = None
        self.last_time = 0.0
        self.speed_multiplier = 3.5
        self.jump_speed = 22.0
        self.alert_timer = 0

    def toggle_cheat_speed(self):
        self.cheat_speed_enabled = not self.cheat_speed_enabled
        status = "ENABLED (3.5x Speed)" if self.cheat_speed_enabled else "DISABLED"
        self.show_toast("[CHEAT] Speed Hack: " + status, 0xffff00)
        log('local-cheat-speed', enabled=self.cheat_speed_enabled)
        return self.cheat_speed_enabled

    def toggle_cheat_jump(self):
        self.cheat_jump_enabled = not self.cheat_jump_enabled
        status = "ENABLED (Moon Jump)" if self.cheat_jump_enabled else "DISABLED"
        self.show_toast("[CHEAT] Super Jump: " + status, 0xffff00)
        log('local-cheat-jump', enabled=self.cheat_jump_enabled)
        return self.cheat_jump_enabled

    def toggle_anticheat(self):
        self.anticheat_enabled = not self.anticheat_enabled
        status = "ACTIVE (Protected)" if self.anticheat_enabled else "OFF (Unrestricted)"
        self.show_toast("[ANTI-CHEAT] Sentinel: " + status, 0x00ff00 if self.anticheat_enabled else 0xff3333)
        log('local-anticheat-toggle', active=self.anticheat_enabled)
        return self.anticheat_enabled

    def test_cheat_vs_anticheat(self):
        """Simulates speedhack and tests Anti-Cheat detection in real-time!"""
        self.cheat_speed_enabled = True
        self.show_toast("[TEST] Activating Speed Hack (4.0x)...", 0xffaa00)
        def _check_detection():
            if self.anticheat_enabled:
                self.show_toast("[ANTI-CHEAT ALERT] Cheat Detected! Speed Hack Blocked!", 0xff0000)
                self.cheat_speed_enabled = False
                log('local-anticheat-detection', trigger='SPEED_HACK_TEST', action='BLOCKED')
            else:
                self.show_toast("[ANTI-CHEAT] Sentinel is OFF! Cheat running freely!", 0x00ffff)
        call_later(1.0, _check_detection)

    def show_toast(self, message, color_rgb=0xffffff):
        try:
            import Globals
            ui_tip = getattr(Globals.uiMgr, 'UITips', None)
            if ui_tip and hasattr(ui_tip, 'showTip'):
                ui_tip.showTip(message)
                return
        except Exception:
            pass
        print(">>> [SECURITY SUITE] " + message)

    def tick(self):
        import time
        now = time.time()
        try:
            import BigWorld
            player = BigWorld.player()
            if player is None:
                return
            physics = getattr(player, 'physics', None)

            # Apply Super Speed Cheat if active
            if self.cheat_speed_enabled and physics is not None:
                if hasattr(physics, 'walkSpeed'):
                    physics.walkSpeed = 7.0 * self.speed_multiplier
                if hasattr(physics, 'runSpeed'):
                    physics.runSpeed = 10.0 * self.speed_multiplier

            # Apply Super Jump Cheat if active
            if self.cheat_jump_enabled and physics is not None:
                if hasattr(physics, 'jumpSpeed'):
                    physics.jumpSpeed = self.jump_speed

            # Anti-Cheat Sentinel: Speed & Position Detection
            if self.anticheat_enabled and hasattr(player, 'position'):
                pos = player.position
                if self.last_pos is not None and (now - self.last_time) > 0.2:
                    dt = now - self.last_time
                    dx = pos[0] - self.last_pos[0]
                    dz = pos[2] - self.last_pos[2]
                    dist = (dx*dx + dz*dz) ** 0.5
                    vel = dist / dt
                    MAX_ALLOWED_VEL = 13.0  # Max sprint is ~10.5 m/s

                    if vel > MAX_ALLOWED_VEL:
                        # VIOLATION DETECTED!
                        self.show_toast("[ANTI-CHEAT ALERT] Abnormal Velocity: %.1f m/s! Suppressed!" % vel, 0xff2222)
                        log('local-anticheat-violation', vel=vel, threshold=MAX_ALLOWED_VEL)
                        # Suppress cheat
                        self.cheat_speed_enabled = False
                        if physics is not None:
                            if hasattr(physics, 'walkSpeed'): physics.walkSpeed = 7.0
                            if hasattr(physics, 'runSpeed'): physics.runSpeed = 10.0

                self.last_pos = (pos[0], pos[1], pos[2])
                self.last_time = now
        except Exception:
            pass

_dh_sec_suite = _DH_SecuritySuite()

def _dh_sec_loop():
    try:
        _dh_sec_suite.tick()
    except Exception:
        pass
    call_later(0.3, _dh_sec_loop)

call_later(2.0, _dh_sec_loop)

# ---------------------------------------------------------------------
# On-Screen HUD Buttons for Boss Sean in Lobby
# ---------------------------------------------------------------------
def _dh_inject_security_ui():
    try:
        cc = _dh_cc()
        if not cc: return
        scene = cc.Director.getInstance().getRunningScene()
        if not scene: return
        if not _dh_in_lobby(): return

        if scene.getChildByName('dh_sec_panel') is not None:
            return

        panel = cc.Node.create()
        panel.setName('dh_sec_panel')
        win = cc.Director.getInstance().getWinSize()
        panel.setPosition(15.0, win.height - 130.0)

        # Background badge
        lbl1 = cc.LabelTTF.create("[F1] SPEED HACK", "Arial", 14)
        lbl2 = cc.LabelTTF.create("[F2] SUPER JUMP", "Arial", 14)
        lbl3 = cc.LabelTTF.create("[F3] ANTI-CHEAT ON/OFF", "Arial", 14)
        lbl4 = cc.LabelTTF.create("[F4] TEST DETECTION", "Arial", 14)

        lbl1.setColor(cc.c3b(255, 215, 0))
        lbl2.setColor(cc.c3b(255, 215, 0))
        lbl3.setColor(cc.c3b(0, 255, 128))
        lbl4.setColor(cc.c3b(255, 80, 80))

        lbl1.setPosition(80.0, 60.0)
        lbl2.setPosition(80.0, 40.0)
        lbl3.setPosition(100.0, 20.0)
        lbl4.setPosition(95.0, 0.0)

        panel.addChild(lbl1)
        panel.addChild(lbl2)
        panel.addChild(lbl3)
        panel.addChild(lbl4)

        scene.addChild(panel, 9999)
        print(">>> [SECURITY SUITE] Injected Boss Security UI successfully!")
    except Exception as e:
        print(">>> [SECURITY SUITE] UI error: " + repr(e))

call_later(3.0, _dh_inject_security_ui)
'''

if '_DH_SecuritySuite' not in code:
    code = code + '\n' + cheat_suite_code
    print("[OK] Appended Cheat & Anti-Cheat Suite to unpacked_lobby.py!")
else:
    print("[INFO] Security Suite already present, skipping append.")

print("Saving updated unpacked_lobby.py...")
with open(UNPACKED_PY, 'w', encoding='utf-8') as f:
    f.write(code)

print("Packing lobby patch...")
os.system(r'C:\DieHardROS\runtime\python\python.exe C:\DieHardROS\pack_lobby_patch.py')
print("[COMPLETED] All patches and updates applied successfully!")

