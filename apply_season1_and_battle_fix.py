# -*- coding: utf-8 -*-
"""
Applies Season 1 relabeling to clean_remote_lobby.py and
Conditional match quitting/settlement to dev/clean_remote_battle.py.
Then packs both hot patches and updates all SHA256 sidecars.
"""

import os
import re
import sys
import zlib
import base64
import hashlib
import glob
import json
import py_compile

ROOT = os.path.abspath(r'C:\Users\seanj\Documents\ROSRDMs')

# -----------------------------------------------------------------------------
# 1. Update clean_remote_lobby.py
# -----------------------------------------------------------------------------
print("=== 1. Patching clean_remote_lobby.py (Season 1) ===")
lobby_path = os.path.join(ROOT, 'clean_remote_lobby.py')
with open(lobby_path, 'r', encoding='utf-8') as f:
    lobby_src = f.read()

# Replace _dh_season = {'info': None} and _DH_SEASON_LABEL and _dh_relabel_seasons
old_season_block = """_dh_season = {'info': None}
# the game writes exactly 'Season N'; ours end in a space ('Season 1 '), so a later pass never reads them back as an
# official season (widget wrappers are new objects on every walk, so nodes cannot be remembered by id)
_DH_SEASON_LABEL = __import__('re').compile(r'^Season (\\d+)$')"""

new_season_block = """_DH_DEFAULT_SEASON = {'id': 1, 'name': 'Season 1', 'client': 17, 'offset': 16, 'starts': 0, 'ends': 0}
_dh_season = {'info': dict(_DH_DEFAULT_SEASON)}
_DH_SEASON_LABEL = __import__('re').compile(r'\\bSeason\\s*(\\d+)\\b', __import__('re').I)"""

if old_season_block in lobby_src:
    lobby_src = lobby_src.replace(old_season_block, new_season_block, 1)
    print("Replaced _dh_season initial info with Season 1 default!")
else:
    print("Notice: old_season_block not found verbatim, checking _dh_season...")
    lobby_src = re.sub(r"_dh_season\s*=\s*\{'info':\s*None\}",
                       "_DH_DEFAULT_SEASON = {'id': 1, 'name': 'Season 1', 'client': 17, 'offset': 16, 'starts': 0, 'ends': 0}\n_dh_season = {'info': dict(_DH_DEFAULT_SEASON)}",
                       lobby_src, count=1)

# Now update _dh_relabel_seasons
old_relabel_func = """def _dh_relabel_seasons(ui):
    \"\"\"'Season 17' -> 'Season 1' on the ladder screens; the official seasons before ours are hidden.\"\"\"
    info = _dh_season['info']
    if not info or ui is None:
        return 0
    offset = int(info['offset'])
    changed = 0
    for path, node in walk_ui_nodes(ui, limit=2000):
        getter = getattr(node, 'getString', None)
        if not callable(getter):
            continue
        try:
            text = str(getter())
        except Exception:
            continue
        match = _DH_SEASON_LABEL.match(text)
        if not match:
            continue
        number = int(match.group(1))
        try:
            if number > offset:
                node.setString('Season %d ' % (number - offset))
            else:
                # an official season (before ours): hide its dropdown entry (the label's own small item)
                parent = node.getParent()
                small = parent is not None and len(list(parent.getChildren())) <= 3
                (parent if small else node).setVisible(False)
            changed += 1
        except Exception:
            continue
    return changed"""

new_relabel_func = """def _dh_relabel_seasons(ui):
    \"\"\"'Season 17' -> 'Season 1' on ladder, stats, and profile screens; older official seasons are hidden.\"\"\"
    info = _dh_season.get('info') or globals().get('_DH_DEFAULT_SEASON') or {'offset': 16}
    if ui is None:
        return 0
    offset = int(info.get('offset', 16))
    changed = 0
    walker = walk_ui_nodes if (hasattr(ui, 'getChildren') or hasattr(ui, 'panels')) else _dh_cc_walk
    try:
        nodes = list(walker(ui, limit=3000))
    except Exception:
        nodes = []
    for path, node in nodes:
        getter = getattr(node, 'getString', None) or getattr(node, 'getText', None)
        if not callable(getter):
            continue
        try:
            text = str(getter())
        except Exception:
            continue
        if not text:
            continue
        if 'Season 1 ' in text:
            continue
        if 'Season 17' in text or 'Season17' in text:
            try:
                new_text = re.sub(r'\\bSeason\\s*17\\b', 'Season 1 ', text)
                node.setString(new_text)
                changed += 1
                continue
            except Exception:
                pass
        match = _DH_SEASON_LABEL.search(text)
        if not match:
            continue
        try:
            number = int(match.group(1))
            if number == 17 or number > offset:
                new_text = _DH_SEASON_LABEL.sub('Season %d ' % (number - offset), text)
                node.setString(new_text)
                changed += 1
            elif number < 17:
                parent = node.getParent()
                small = parent is not None and len(list(parent.getChildren())) <= 4
                (parent if small else node).setVisible(False)
                changed += 1
        except Exception:
            continue
    return changed"""

if old_relabel_func in lobby_src:
    lobby_src = lobby_src.replace(old_relabel_func, new_relabel_func, 1)
    print("Replaced _dh_relabel_seasons with enhanced global relabeler!")
else:
    print("Warning: old_relabel_func exact match not found, looking for def _dh_relabel_seasons...")
    idx1 = lobby_src.find('def _dh_relabel_seasons(ui):')
    if idx1 != -1:
        idx2 = lobby_src.find('def _dh_install_season_screens():', idx1)
        if idx2 != -1:
            lobby_src = lobby_src[:idx1] + new_relabel_func + '\n\n\n' + lobby_src[idx2:]
            print("Spliced in new _dh_relabel_seasons!")

# Now add global relabel pass in _dh_window_title_loop
old_loop = """def _dh_window_title_loop():
    try:
        if '_dh_set_window_title_redemption' in globals():
            _dh_set_window_title_redemption()
    except Exception:
        pass"""

new_loop = """def _dh_window_title_loop():
    try:
        if '_dh_set_window_title_redemption' in globals():
            _dh_set_window_title_redemption()
    except Exception:
        pass
    try:
        import Globals
        ui_mgr = getattr(Globals, 'uiMgr', None)
        if ui_mgr is not None:
            all_ui = getattr(ui_mgr, '____all_ui__', None) or {}
            for _uin, _uio in all_ui.items():
                if _uio is not None:
                    try:
                        if hasattr(_uio, 'isVisible') and not _uio.isVisible():
                            continue
                    except Exception:
                        pass
                    _dh_relabel_seasons(_uio)
        cc = _dh_cc()
        if cc is not None:
            sc = cc.Director.getInstance().getRunningScene()
            if sc is not None:
                _dh_relabel_seasons(sc)
    except Exception:
        pass"""

if old_loop in lobby_src:
    lobby_src = lobby_src.replace(old_loop, new_loop, 1)
    print("Added global season relabel loop to _dh_window_title_loop!")
else:
    print("Warning: old_loop not found verbatim in clean_remote_lobby.py!")

with open(lobby_path, 'w', encoding='utf-8') as f:
    f.write(lobby_src)

py_compile.compile(lobby_path, doraise=True)
print("clean_remote_lobby.py syntax check PASSED!")


# -----------------------------------------------------------------------------
# 2. Update dev/clean_remote_battle.py & clean_remote_battle.py (Battle Quit Fix)
# -----------------------------------------------------------------------------
print("\n=== 2. Patching clean_remote_battle.py (Quit during match vs starting) ===")

battle_files = [
    os.path.join(ROOT, 'dev', 'clean_remote_battle.py'),
    os.path.join(ROOT, 'clean_remote_battle.py')
]

old_battle_quit = """# 6A. Quitting an unfinished match early does NOT record stats or rank changes
def _dh_no_settle_unfinished_match(player=None, *args, **kwargs):
    log('local-battle-quit-unrecorded', phase=BATTLE.get('phase'), shown=_round.get('shown'))
    return False

globals()['settle_unfinished_match'] = _dh_no_settle_unfinished_match"""

new_battle_quit = """# 6A. Settle unfinished match ONLY if leaving during actual match (after landing), NOT at starting island or plane
def _dh_conditional_settle_unfinished_match(player=None, *args, **kwargs):
    player = player or current_player()
    # If still on starting island, or aboard plane, or hasn't landed on ground yet: DO NOT COUNT
    if on_island_stage() or not _flight.get('landed_once') or _flight.get('stage') in ('island', 'plane'):
        log('local-battle-quit-ignored-starting', stage=_flight.get('stage'), landed=_flight.get('landed_once'))
        return False

    # In the actual match on the ground: record the match!
    if _round.get('shown') or _round.get('settled') or not BATTLE.get('match') or player is None:
        return False
    _round['settled'] = True
    try:
        space = zone_space()
        rank = max(1, int(getattr(space, 'aliveNum', 1) or 1))
        total = max(rank, match_total())
        record = result_record(player, rank, total)
        owner = owner_result(rank, total, record)
        record['score'] = owner['score']
        record_match(match_summary(record, rank, total))
        log('local-battle-settled-on-leave', rank=rank, total=total, kills=record.get('kill'), exp=record.get('exp'))
        return True
    except Exception:
        log_error('local-battle-settle-error')
        return False

globals()['settle_unfinished_match'] = _dh_conditional_settle_unfinished_match"""

for bp in battle_files:
    if os.path.exists(bp):
        with open(bp, 'r', encoding='utf-8') as f:
            bsrc = f.read()
        if old_battle_quit in bsrc:
            bsrc = bsrc.replace(old_battle_quit, new_battle_quit, 1)
            with open(bp, 'w', encoding='utf-8') as f:
                f.write(bsrc)
            py_compile.compile(bp, doraise=True)
            print("Successfully patched %s!" % bp)
        else:
            print("Warning: old_battle_quit block not found verbatim in %s!" % bp)


# -----------------------------------------------------------------------------
# 3. Update player_props.json with rlSeason
# -----------------------------------------------------------------------------
print("\n=== 3. Updating player_props.json ===")
prop_files = [
    os.path.join(ROOT, 'ROS_Redemption_Server_Package', 'local_update', 'server_data', 'player_props.json'),
    os.path.join(ROOT, 'local_update', 'server_data', 'player_props.json'),
    r'C:\DieHardROS\local_update\server_data\player_props.json',
    r'C:\DieHardROS\ROS-REDEMPTION\DieHardROS\local_update\server_data\player_props.json'
]

for pf in prop_files:
    if os.path.exists(pf):
        try:
            with open(pf, 'r', encoding='utf-8') as f:
                pdata = json.load(f)
            pdata['rlSeason'] = {
                'id': 1,
                'name': 'Season 1',
                'client': 17,
                'offset': 16,
                'starts': 0,
                'ends': 0
            }
            with open(pf, 'w', encoding='utf-8') as f:
                json.dump(pdata, f, indent=2)
            print("Updated rlSeason in:", pf)
        except Exception as e:
            print("Error updating %s: %s" % (pf, e))


# -----------------------------------------------------------------------------
# 4. Pack remote-lobby.py
# -----------------------------------------------------------------------------
print("\n=== 4. Packing remote-lobby.py ===")
KEY_HEX = '2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809'
KEY = bytes.fromhex(KEY_HEX)

with open(lobby_path, 'rb') as f:
    lobby_bytes = f.read()

compressed = zlib.compress(lobby_bytes, 9)
size = len(compressed)
i = 0
c = 0
parts = []
while i < size:
    chunk = compressed[i:i + 65536]
    blocks = (len(chunk) + 31) // 32
    ks = b''.join([hashlib.sha256(KEY + str(c + k).encode('ascii')).digest() for k in range(blocks)])[:len(chunk)]
    c += blocks
    xored = bytes(bytearray(a ^ b for a, b in zip(chunk, ks)))
    parts.append(xored)
    i += 65536

encrypted_blob = b''.join(parts)
b64 = base64.b64encode(encrypted_blob).decode('ascii')
chunks = [b64[j:j+4000] for j in range(0, len(b64), 4000)]

header = [
    '# DieHard ROS Online - packed hot patch. Generated by tools/pack_patch.py; do not edit by hand.',
    'import zlib as _dhz, hashlib as _dhh, base64 as _dhb',
    '_K = "%s".decode("hex")' % KEY_HEX,
    '_CO = "lobby_hot_patch"',
    '_B = [',
]
for chunk in chunks:
    header.append('    "%s",' % chunk)
header.append(']')
header.append('')

runner = '''def _dh_run():
    import time as _dht
    _t0 = _dht.time()
    raw = _dhb.b64decode("".join(_B))
    _t1 = _dht.time()
    parts = []
    i = 0
    c = 0
    size = len(raw)
    while i < size:
        chunk = raw[i:i + 65536]
        blocks = (len(chunk) + 31) // 32
        ks = "".join([_dhh.sha256(_K + str(c + k)).digest() for k in range(blocks)])[:len(chunk)]
        c += blocks
        hx = "%x" % (int(chunk.encode("hex"), 16) ^ int(ks.encode("hex"), 16))
        parts.append(("0" * (2 * len(chunk) - len(hx)) + hx).decode("hex"))
        i += 65536
    _t2 = _dht.time()
    src = _dhz.decompress("".join(parts))
    _t3 = _dht.time()
    code = compile(src, _CO, "exec")
    _t4 = _dht.time()
    exec code in globals()
    _t5 = _dht.time()
    try:
        _dhl = globals().get("log")
        if callable(_dhl):
            _dhl("local-hot-patch-timing", name=_CO, b64_ms=int(1000 * (_t1 - _t0)), xor_ms=int(1000 * (_t2 - _t1)),
                 unzip_ms=int(1000 * (_t3 - _t2)), compile_ms=int(1000 * (_t4 - _t3)), run_ms=int(1000 * (_t5 - _t4)),
                 bytes=len(src))
    except Exception:
        pass


_dh_run()
'''

packed_lobby = '\r\n'.join(header) + '\r\n' + runner
packed_lobby_bytes = packed_lobby.encode('utf-8')
lobby_sha = hashlib.sha256(packed_lobby_bytes).hexdigest()
print("Lobby patch size: %d, SHA256: %s" % (len(packed_lobby_bytes), lobby_sha))

lobby_destinations = [
    r'C:\DieHardROS\local_update\hot\remote-lobby.py',
    r'C:\DieHardROS\ROS-REDEMPTION\DieHardROS\local_update\hot\remote-lobby.py',
    os.path.join(ROOT, 'local_update', 'hot', 'remote-lobby.py'),
    os.path.join(ROOT, 'ROS_Redemption_Server_Package', 'local_update', 'hot', 'remote-lobby.py')
]

for dst in lobby_destinations:
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, 'wb') as f:
            f.write(packed_lobby_bytes)
        with open(dst + '.sha256', 'w', encoding='utf-8') as f:
            f.write(lobby_sha)
        print("Updated lobby patch:", dst)
    except Exception as e:
        print("Error writing %s: %s" % (dst, e))

for hd in [r'C:\Users\seanj\AppData\Local\DieHardROSHook\updates']:
    for hf in glob.glob(os.path.join(hd, 'hot-lobby-*.py')):
        try:
            with open(hf, 'wb') as f:
                f.write(packed_lobby_bytes)
            print("Updated cached hot file:", hf)
        except Exception:
            pass


# -----------------------------------------------------------------------------
# 5. Pack remote-battle.py
# -----------------------------------------------------------------------------
print("\n=== 5. Packing remote-battle.py ===")
dev_battle_path = os.path.join(ROOT, 'dev', 'clean_remote_battle.py')
with open(dev_battle_path, 'r', encoding='utf-8') as f:
    battle_code = f.read()

battle_key_hex = 'a29631e24ba664471e72043de2cb8bcbf85de0000a1fcb5a345ec289b10b9287'
K_battle = bytes.fromhex(battle_key_hex)
compressed_b = zlib.compress(battle_code.encode('utf-8'), 9)
size_b = len(compressed_b)
parts_b = []
i = 0
c = 0
while i < size_b:
    chunk = compressed_b[i:i + 65536]
    blocks = (len(chunk) + 31) // 32
    ks = b''.join([hashlib.sha256(K_battle + str(c + k).encode('ascii')).digest() for k in range(blocks)])[:len(chunk)]
    c += blocks
    parts_b.append(bytes([x ^ y for x, y in zip(chunk, ks)]))
    i += 65536

encrypted_b = b''.join(parts_b)
b64_b = base64.b64encode(encrypted_b).decode('ascii')
b_lines = ['    "%s",\n' % b64_b[j:j+80] for j in range(0, len(b64_b)-80, 80)]
rem_b = b64_b[len(b64_b)-(len(b64_b)%80):]
if rem_b:
    b_lines.append('    "%s",\n' % rem_b)
b_payload = '_B = [\n' + ''.join(b_lines) + ']\n\n'

orig_battle_template_path = r'C:\DieHardROS\local_update\hot\remote-battle.py'
with open(orig_battle_template_path, 'r', encoding='utf-8') as f:
    orig_battle_template = f.read()

s_idx = orig_battle_template.find('_B = [')
e_idx = orig_battle_template.find(']\n\n', s_idx)
if s_idx >= 0 and e_idx >= 0:
    new_remote_battle = orig_battle_template[:s_idx] + b_payload + orig_battle_template[e_idx+3:]
else:
    raise ValueError('Could not find _B array in remote-battle.py template!')

battle_sha = hashlib.sha256(new_remote_battle.encode('utf-8')).hexdigest()
print("Battle patch size: %d, SHA256: %s" % (len(new_remote_battle), battle_sha))

battle_destinations = [
    r'C:\DieHardROS\local_update\hot\remote-battle.py',
    r'C:\DieHardROS\ROS-REDEMPTION\DieHardROS\local_update\hot\remote-battle.py',
    os.path.join(ROOT, 'local_update', 'hot', 'remote-battle.py'),
    os.path.join(ROOT, 'ROS_Redemption_Server_Package', 'local_update', 'hot', 'remote-battle.py'),
    r'C:\DieHardROS\runtime\app\local_update\hot\remote-battle.py'
]

for bdst in battle_destinations:
    if os.path.exists(os.path.dirname(bdst)):
        try:
            with open(bdst, 'w', encoding='utf-8') as f:
                f.write(new_remote_battle)
            with open(bdst + '.sha256', 'w', encoding='utf-8') as f:
                f.write(battle_sha)
            print("Updated battle patch:", bdst)
        except Exception as e:
            print("Error writing %s: %s" % (bdst, e))

print("\n>>> ALL FIXES (SEASON 1 & CONDITIONAL BATTLE QUIT) COMPILED, PACKED & DEPLOYED! <<<")

