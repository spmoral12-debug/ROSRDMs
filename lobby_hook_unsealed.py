# -*- coding: utf-8 -*-
"""DieHard ROS lobby hook -- runs INSIDE ros64.exe (embedded Python 2.7).

client/inject_lobby.embedded_source() loads this file, seeds a CONFIG dict
and executes it as the module ``ros_local_lobby``.  Keep the syntax valid for
both Python 2.7 and 3 (no print statements, no ``except X, e``) so it can be
syntax-checked outside the game.

Flow
    BigWorld.logOn           -> answered locally with FORCE_STATUS (1 = ok); the
                                account and the server picked in the server list
                                log in to the backend (ROS_LOCAL_LOGIN_V1)
    character resources      -> loading bar, then UISelectCharacter (with a
                                saved character it stays hidden under the
                                loading screen and logs in at once)
    create / saved character -> local Athlete entity, profile saved in the
                                account database (per account and server)
    lobby                    -> scene + team + UIMain + dressed self model
    lobby buttons            -> player.base is a LocalServerMailbox: every
                                server call goes to backend_server/pyserver.py
                                and its reply callbacks run on the player
    discovery                -> local_update/logs/rpc_catalog.json lists the
                                server calls player code and lobby panels make

Logs: local_update/logs/new_ros_logon.jsonl (one JSON object per line).
"""

import BigWorld
import gc
import itertools
import copy
import json
import random
import os
import re
import socket
import struct
import sys
import time
import traceback
import zlib
import types

try:
    CONFIG
except NameError:
    CONFIG = {}

LOG_PATH = CONFIG.get('log_path')


def _mirror_address():
    """The runtime's local update mirror: 127.0.0.1:80/443 unless it had to use
    other ports (local_update/mirror_ports.json, written by start_game)."""
    try:
        folder = os.path.dirname(os.path.dirname(os.path.abspath(LOG_PATH)))
        with open(os.path.join(folder, 'mirror_ports.json'), 'rb') as handle:
            info = json.loads(handle.read().decode('utf-8'))
        http, https = int(info.get('http') or 0), int(info.get('https') or 0)
        if http and https:
            return [str(info.get('host') or '127.0.0.1'), http, https]
    except Exception:
        pass
    return ['127.0.0.1', 80, 443]
FORCE_STATUS = CONFIG.get('force_status')
ENTER_CHARACTER = bool(CONFIG.get('enter_character'))
ENTER_CHARACTER_NOW = bool(CONFIG.get('enter_character_now'))
DEBUG = bool(CONFIG.get('debug'))
AUTO_START = bool(CONFIG.get('auto_start'))            # launcher --auto-start
# launcher --max-fps: the frame-rate cap.  The game's own PC modes stop at
# 30/45/60/120 (graphic_settings FrameRateMap); 0 leaves the game's choice.
try:
    MAX_FPS = max(0, int(CONFIG.get('max_fps', 300) or 0))
except (TypeError, ValueError):
    MAX_FPS = 300
# Seconds after the lobby is up before --auto-start presses START: the mode
# panel (UIMain.uiModes) is built a moment after the lobby itself.
AUTO_START_DELAY = 5.0
CATALOG_PATH = CONFIG.get('catalog_path')
ERRORS_PATH = CONFIG.get('errors_path')
# The game server the hook talks to: this PC, or the online server (launcher
# --remote-servers) - then the login carries the launcher's login token.
BACKEND_HOST = str(CONFIG.get('backend_host') or '127.0.0.1')
LOGIN_TOKEN = CONFIG.get('token') or None
DEFAULT_PORT = int(CONFIG.get('game_port') or 19000)
FORCED_PORT = int(CONFIG.get('server_port') or 0)      # launcher --server
FORCED_ACCOUNT = CONFIG.get('account') or None         # launcher --account

LOGIN_PREFIX = 'ROS_LOCAL_LOGIN_V1 '
STATE_REQUEST = 'ROS_LOCAL_STATE_V1'
STATE_SAVE = 'ROS_LOCAL_SAVE_V1 '
RPC_PREFIX = 'ROS_LOCAL_RPC_V1 '
PROPS_REQUEST = 'ROS_LOCAL_PROPS_V1'
ITEMS_REQUEST = 'ROS_LOCAL_ITEMS_V1'
CHAT_REQUEST = 'ROS_LOCAL_CHAT_V1'

LOGIN_WAIT_SECONDS = 1.5
LOADING_MIN_SECONDS = 2.0
LOADING_ANIMATION_SECONDS = 15.0
LOADING_FINISH_SECONDS = 0.25
LOBBY_ENTER_DELAY = 3.0
DEFAULT_CHARACTER_TYPE = 10002
DEFAULT_GID = 10001
SHOW_MODEL_PATH = 'character/dataosha_male/male.gim'
SHOW_MODEL_PARTS = (
    'character/dataosha_male/male_hair/male_hair_show.gim',
    'character/dataosha_male/male_head/male_head_show.gim',
    'character2/dataosha_male/male_body/male_show_new/male_show_new.gim',
    'character2/dataosha_male/male_leg/male_show_new/male_show_new.gim',
)
FEMALE_SHOW_MODEL_PARTS = (
    'character/dataosha_female/female_hair/female_hair_show.gim',
    'character/dataosha_female/female_head/female_head_show.gim',
    'character/dataosha_female/female_body/female_body_show.gim',
    'character/dataosha_female/female_leg/female_leg_show.gim',
)


def show_model_parts(model_path):
    """The bare show parts that go with a character model (male or female)."""
    return FEMALE_SHOW_MODEL_PARTS if 'female' in model_path.lower() else SHOW_MODEL_PARTS
# Lobby preview placement; overridable in local_lobby_state.json -> "lobbyModel".
#   scale    : model scale (the full-size show model is too big for this camera)
#   distance : push the model back from the camera along the ground (1.0 = no
#              change). Further back = smaller and feet higher, like online.
#   offsetX  : sideways shift in world units (positive = left on screen here)
LOBBY_MODEL_DEFAULTS = {'scale': 0.6, 'distance': 1.1, 'offsetX': 0.9,
                        'hideRanked': False, 'hideTeamSlots': False}

try:
    string_types = basestring  # noqa: F821 (Python 2)
except NameError:
    string_types = str
try:
    long_type = long  # noqa: F821 (Python 2)
except NameError:
    long_type = int


# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

def safe(value, limit=1000):
    try:
        return repr(value)[:limit]
    except Exception:
        return '<repr failed>'


LOG_LIMIT = 10 * 1024 * 1024
LOG_CHECK_EVERY = 500
# Lines are kept and written together about once a second through one open
# file (log_error writes at once: crash evidence).  An open/append/close per
# line on the game thread cost 45-107 ms per 30 s in the lobby, one of them
# 38 ms (disk / antivirus busy), and a panel open writes ~5 lines.
# 0 (the tests): every line at once, no file kept open.
try:
    LOG_FLUSH_SECONDS = max(0.0, float(CONFIG.get('log_flush_seconds', 1.0)))
except (TypeError, ValueError):
    LOG_FLUSH_SECONDS = 1.0
LOG_FLUSH_LINES = 200
_log_writes = [0]
_log_out = {'lines': [], 'file': None, 'path': None, 'timer': False, 'rotate': False}


def log(event, **fields):
    if not LOG_PATH:
        return
    started = perf_clock()
    row = {'timestamp': time.time(), 'event': event}
    row.update(fields)
    _log_writes[0] += 1
    if _log_writes[0] % LOG_CHECK_EVERY == 1:
        _log_out['rotate'] = True
    try:
        # No sort_keys: with it Python 2.7 drops to its pure-Python encoder
        # (several times slower); every reader parses the line anyway.
        _log_out['lines'].append(json.dumps(row) + '\n')
    except Exception:
        pass
    if LOG_FLUSH_SECONDS <= 0 or len(_log_out['lines']) >= LOG_FLUSH_LINES:
        flush_log()
    elif not _log_out['timer']:
        _log_out['timer'] = True
        try:
            BigWorld.callback(LOG_FLUSH_SECONDS, flush_log_timer)
        except Exception:
            _log_out['timer'] = False
            flush_log()
    lobby_perf_add('log', (perf_clock() - started) * 1000.0)


def flush_log_timer():
    _log_out['timer'] = False
    started = perf_clock()
    flush_log()
    lobby_perf_add('log', (perf_clock() - started) * 1000.0)


def flush_log():
    lines = _log_out['lines']
    if not lines or not LOG_PATH:
        return
    _log_out['lines'] = []
    try:
        if _log_out['rotate']:
            _log_out['rotate'] = False
            close_log_file()                        # Windows cannot rename an open file
            rotate_error_log(LOG_PATH, LOG_LIMIT)
        if LOG_FLUSH_SECONDS <= 0:
            with open(LOG_PATH, 'a') as output_file:
                output_file.write(''.join(lines))
            return
        if _log_out['file'] is None or _log_out['path'] != LOG_PATH:
            close_log_file()
            _log_out['file'], _log_out['path'] = open(LOG_PATH, 'a'), LOG_PATH
        # one write of whole lines: another hook instance (a re-injection)
        # appending to the same file never splits a line
        _log_out['file'].write(''.join(lines))
        _log_out['file'].flush()
    except Exception:
        close_log_file()


def close_log_file():
    handle, _log_out['file'] = _log_out['file'], None
    if handle is not None:
        try:
            handle.close()
        except Exception:
            pass


def _flush_log_at_exit():
    flush_log()
    close_log_file()


if LOG_FLUSH_SECONDS > 0:
    try:
        import atexit
        atexit.register(_flush_log_at_exit)
    except Exception:
        pass


def debug(event, **fields):
    if DEBUG:
        log(event, **fields)


def log_error(event, **fields):
    """Log the current exception; add frame detail only in debug mode."""
    exc_info = sys.exc_info()
    fields['error'] = traceback.format_exc()
    if DEBUG:
        try:
            fields['frames'] = exception_frames(exc_info[2])
        except Exception:
            fields['frames'] = [{'capture_error': traceback.format_exc()}]
    log(event, **fields)
    flush_log()                 # not kept for the timer: the game may be about to die


def exception_frames(tb):
    frames = []
    while tb is not None:
        frame = tb.tb_frame
        frames.append({
            'file': frame.f_code.co_filename,
            'function': frame.f_code.co_name,
            'line': tb.tb_lineno,
            'locals': dict(
                (str(key), '%s: %s' % (type(value).__name__, safe(value, 300)))
                for key, value in frame.f_locals.items()
            ),
        })
        tb = tb.tb_next
    return frames


def call_later(delay, function, *args):
    """BigWorld.callback that never lets an exception reach the engine."""
    def run():
        mark = perf_mark()
        try:
            function(*args)
        except Exception:
            log_error('local-callback-error', function=getattr(function, '__name__', safe(function)))
        finally:
            perf_done(getattr(function, '__name__', 'callback'), mark)
    BigWorld.callback(delay, run)


# --------------------------------------------------------------------------
# Lobby frame profiler
# --------------------------------------------------------------------------
# "Stutters every 3 seconds": nothing measured the lobby's frames, so a hitch
# could not be seen nor blamed.  Like battle_hook's local-perf: every frame
# one clock read; the hook's callbacks, RPC answers, UI opens and waits on the
# backend add their time; every 30 s one 'local-lobby-perf' line with frame
# p50/p95/max and what ran in the slowest frames.  It runs in the lobby only
# (a battle has its own local-perf).

LOBBY_PERF_EVERY = 30.0
LOBBY_PERF_SLOW_MS = 50.0
LOBBY_PERF_SLOW_KEEP = 8
# Frame times go into 0.1 ms buckets up to 100 ms (+ one for the rest): the
# report was a full sort of every frame (9,000-87,000 of them) on the game
# thread - a hitch of its own every 30 s in the frames it measured.
LOBBY_PERF_BUCKETS = 1000
LOBBY_PERF_BUCKET_MS = 0.1


def perf_clock():
    try:
        return time.perf_counter()
    except AttributeError:
        return time.clock() if sys.platform == 'win32' else time.time()


def _game_frame_count():
    try:
        import game3d
        return int(game3d.get_frame_count())
    except Exception:
        return None


def _lobby_perf_blank(now):
    return {'start': now, 'last': None, 'count': 0, 'buckets': [0] * (LOBBY_PERF_BUCKETS + 1),
            'max': 0.0, 'hitches': 0, 'parts': {}, 'frame_work': {}, 'slow': [], 'hook_ms': 0.0,
            'ui_ms': 0.0, 'gc_full': 0, 'gc_seen': None, 'logs': _log_writes[0],
            'game_frames': _game_frame_count()}


_lobby_perf = _lobby_perf_blank(perf_clock())
_lobby_perf.update(running=False, token=None, driver=None)
# Parts are nested (a callback holds its RPCs and log lines, a poll its
# replies): only the outermost one counts towards hook_ms_per_s, or the same
# time was added two and three times.
_perf_depth = [0]
_PERF_OFF = object()


def lobby_perf_add(name, ms, total='hook_ms'):
    if not _lobby_perf['running']:
        return
    part = _lobby_perf['parts'].get(name)
    if part is None:
        part = _lobby_perf['parts'][name] = [0, 0.0, 0.0]
    part[0] += 1
    part[1] += ms
    part[2] = max(part[2], ms)
    work = _lobby_perf['frame_work']
    work[name] = work.get(name, 0.0) + ms
    if _perf_depth[0] == 0:
        _lobby_perf[total] += ms


def perf_mark():
    """Before a timed hook call: the profiler window it starts in."""
    _perf_depth[0] += 1
    return (_lobby_perf['token'] if _lobby_perf['running'] else _PERF_OFF), perf_clock()


def perf_done(name, mark, total='hook_ms', nested=True):
    if nested:
        _perf_depth[0] = max(0, _perf_depth[0] - 1)
    token, started = mark
    # started before this window (finish_local_lobby_entry starts the
    # profiler inside its own 16-18 s): not this window's time
    if _lobby_perf['running'] and _lobby_perf['token'] is token:
        lobby_perf_add(name, (perf_clock() - started) * 1000.0, total)


def lobby_perf_frame(now=None):
    if now is None:
        now = perf_clock()
    perf = _lobby_perf
    last = perf['last']
    perf['last'] = now
    if last is not None:
        took = (now - last) * 1000.0
        perf['count'] += 1
        perf['buckets'][min(LOBBY_PERF_BUCKETS, int(took / LOBBY_PERF_BUCKET_MS))] += 1
        if took > perf['max']:
            perf['max'] = took
        if took >= LOBBY_PERF_SLOW_MS:
            perf['hitches'] += 1
        try:
            # a full (gen 2) collection empties generation 2: it shows as a fall
            count = gc.get_count()[2]
            if perf['gc_seen'] is not None and count < perf['gc_seen']:
                perf['gc_full'] += 1
                perf['frame_work']['gc-full'] = 0.0
            perf['gc_seen'] = count
        except Exception:
            pass
        if took >= LOBBY_PERF_SLOW_MS and len(perf['slow']) < LOBBY_PERF_SLOW_KEEP:
            work = sorted(perf['frame_work'].items(), key=lambda item: -item[1])[:4]
            perf['slow'].append([round(took, 1)] + [[name, round(ms, 2)] for name, ms in work])
    perf['frame_work'] = {}
    if now - perf['start'] >= LOBBY_PERF_EVERY:
        lobby_perf_report(now)


def _percentile(perf, share):
    """The frame time below which ``share`` of the frames were (bucket
    middle; past the last bucket: the slowest frame)."""
    if not perf['count']:
        return 0.0
    wanted = min(perf['count'] - 1, int(perf['count'] * share))
    seen = 0
    for index, count in enumerate(perf['buckets']):
        seen += count
        if seen > wanted:
            if index >= LOBBY_PERF_BUCKETS:
                return perf['max']
            return min(perf['max'], (index + 0.5) * LOBBY_PERF_BUCKET_MS)
    return perf['max']


def lobby_perf_report(now):
    perf = _lobby_perf
    seconds = max(0.001, now - perf['start'])
    parts = sorted(perf['parts'].items(), key=lambda item: -item[1][1])
    game_frames = _game_frame_count()
    game_fps = None
    if game_frames is not None and perf['game_frames'] is not None:
        game_fps = round((game_frames - perf['game_frames']) / seconds, 1)
    keep = dict((key, perf[key]) for key in ('running', 'token', 'driver'))
    # parts are inclusive (nested); hook_ms_per_s counts each moment once,
    # ui_ms_per_s is mostly the game's own panel building
    log('local-lobby-perf', seconds=round(seconds, 1), fps=round(perf['count'] / seconds, 1), game_fps=game_fps,
        frame_ms={'p50': round(_percentile(perf, 0.5), 1), 'p95': round(_percentile(perf, 0.95), 1),
                  'p99': round(_percentile(perf, 0.99), 1), 'max': round(perf['max'], 1)},
        hitches=perf['hitches'],
        parts=[[name, part[0], round(part[1], 1), round(part[2], 2)] for name, part in parts[:10]],
        hook_ms_per_s=round(perf['hook_ms'] / seconds, 2), ui_ms_per_s=round(perf['ui_ms'] / seconds, 2),
        slow_frames=perf['slow'], gc_full=perf['gc_full'], log_lines=_log_writes[0] - perf['logs'],
        pending=len(_rpc_pending), driver=keep['driver'])
    perf.clear()
    perf.update(_lobby_perf_blank(now))
    perf.update(keep)
    perf['last'] = now


def start_lobby_perf(player):
    """Measure the lobby's frames from now until it is left (each lobby entry,
    the return from a battle too)."""
    try:
        token = object()
        BigWorld._rl_lobby_perf = token         # a re-injected hook / a new lobby stops the old loop
        _lobby_perf.clear()
        _lobby_perf.update(_lobby_perf_blank(perf_clock()))
        _lobby_perf.update(running=True, token=token, driver='coroutine')
        try:
            # once per rendered frame (battle_hook's motion_frames runs this way)
            player.behaviour.StartCoroutine(lobby_perf_frames(player, token))
        except Exception:
            # engine ticks instead of frames: the report says which
            _lobby_perf['driver'] = 'callback'
            BigWorld.callback(0.0, lambda: lobby_perf_tick(player, token))
        log('local-lobby-perf-started', driver=_lobby_perf['driver'])
    except Exception:
        log_error('local-lobby-perf-error')


def _lobby_perf_on(player, token):
    try:
        return (getattr(BigWorld, '_rl_lobby_perf', None) is token and BigWorld.player() is player
                and not in_battle())
    except Exception:
        return False


def lobby_perf_frames(player, token):
    while _lobby_perf_on(player, token):
        yield None
        if not _lobby_perf_on(player, token):
            break
        try:
            lobby_perf_frame()
        except Exception:
            log_error('local-lobby-perf-error')
    if _lobby_perf.get('token') is token:
        _lobby_perf['running'] = False


def lobby_perf_tick(player, token):
    if not _lobby_perf_on(player, token):
        if _lobby_perf.get('token') is token:
            _lobby_perf['running'] = False
        return
    try:
        lobby_perf_frame()
    except Exception:
        log_error('local-lobby-perf-error')
    BigWorld.callback(0.0, lambda: lobby_perf_tick(player, token))


# --------------------------------------------------------------------------
# Backend session (backend_server/game_server.py, one UDP port per server)
# --------------------------------------------------------------------------
# The server picked in the game's server list is the port BigWorld.logOn is
# called with; every later request goes to that port and carries the session
# token the login returned, so the backend knows the account and character.

_backend = {'address': (BACKEND_HOST, FORCED_PORT or DEFAULT_PORT), 'session': None,
            'account': None, 'server': None, 'error': None}
_state = {'value': None}


def _udp_exchange(payload, size=16384, timeout=0.5, retries=None):
    """One request to the backend - a wait on the game's thread for the
    reply.  Each one is counted (backend_calls, reported every minute)."""
    client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    started = time.time()
    kind = (payload[:payload.find(' ')] if ' ' in payload[:40] else payload[:24]) if isinstance(payload, str) else '?'
    try:
        client.settimeout(timeout)
        data = payload if isinstance(payload, bytes) else payload.encode('utf-8')
        retry_check = data
        data = pack_request(data)
        client.sendto(data, _backend['address'])
        # A lost packet over the internet: requests that can be repeated are sent
        # again (a login, the lobby state...); an RPC (a purchase) never is.
        if retries is None:
            retries = 0 if retry_check.startswith(b'ROS_LOCAL_RPC_V1') else EXCHANGE_RETRIES
        pieces = PieceBuffer()
        deadline = time.time() + timeout
        while True:
            try:
                data_in, _peer = client.recvfrom(max(size, 65535))
            except socket.timeout:
                if pieces.message is not None and pieces.ask_missing(client, _backend['address']):
                    deadline = time.time() + timeout
                    client.settimeout(timeout)
                    continue
                if pieces.message is None and retries > 0:
                    retries -= 1
                    client.sendto(data, _backend['address'])
                    deadline = time.time() + timeout
                    client.settimeout(timeout)
                    continue
                raise
            reply = pieces.feed(data_in)
            if reply is not None:
                return reply
            client.settimeout(max(0.05, deadline - time.time()))
    finally:
        client.close()
        backend_call_done(kind, (time.time() - started) * 1000.0)


BACKEND_REPORT_EVERY = 60.0
EXCHANGE_RETRIES = 2
_backend_calls = {'since': time.time(), 'calls': {}}


def backend_call_done(kind, ms):
    """Requests to the backend: how many, and how long the game waited for them."""
    if not kind.startswith('RPC '):
        lobby_perf_add('wait ' + kind, ms)      # a real wait (an 'RPC x' went without waiting)
    entry = _backend_calls['calls'].setdefault(kind, [0, 0.0, 0.0])
    entry[0] += 1
    entry[1] += ms
    entry[2] = max(entry[2], ms)
    now = time.time()
    if now - _backend_calls['since'] >= BACKEND_REPORT_EVERY:
        calls = sorted(_backend_calls['calls'].items(), key=lambda item: -item[1][1])
        log('local-backend-calls', seconds=round(now - _backend_calls['since']),
            calls=[[name, value[0], round(value[1]), round(value[2])] for name, value in calls])
        _backend_calls['since'] = now
        _backend_calls['calls'] = {}


def _with_session(prefix, fields=None, pieces=True):
    body = dict(fields or {})
    if _backend['session']:
        body['session'] = _backend['session']
    if pieces:
        body['rrc'] = 1                 # big replies in pieces (backend_server/chunks.py),
        body['rrz'] = 1                 # compressed: a lost piece loses the whole reply
    return prefix + json.dumps(body)


# --------------------------------------------------------------------------
# Replies in pieces (backend_server/chunks.py): a reply bigger than one
# network packet came as one datagram the internet split up and often lost
# (the supply list: always there on this PC, never from the online server).
# --------------------------------------------------------------------------

PIECE_MAGIC = b'RRC1'
PIECE_HEADER = struct.Struct('>IHH')
MISSING_PREFIX = b'RRCMISS '
PIECE_ASK_AFTER = 0.3                   # s without a new piece: ask for the missing ones
PIECE_ASKS = 8                          # (the caller's own wait ends it sooner: RPC_WAIT 3 s)
PACKED_MAGIC = b'RRZ1'                  # a reply compressed first (we asked: "rrz": 1)


REQUEST_PACKED = b'RRQ1'
REQUEST_PACK_MIN = 900                  # bytes: under one packet goes as it is


def pack_request(data):
    """A request bigger than one packet, compressed (backend_server/chunks.py
    unpack_request): a match's records are ~5 KB, and the way to the online
    server dropped every split-up datagram - each save timed out."""
    if not _backend.get('zreq') or len(data) < REQUEST_PACK_MIN or data.startswith(REQUEST_PACKED):
        return data
    packed = REQUEST_PACKED + zlib.compress(data, 6)
    return packed if len(packed) < len(data) else data


def unpacked(data):
    """A reply the server compressed (backend_server/chunks.py pack), as it was."""
    if data.startswith(PACKED_MAGIC):
        return zlib.decompress(data[len(PACKED_MAGIC):])
    return data


class PieceBuffer(object):
    def __init__(self):
        self.message = None
        self.count = 0
        self.parts = {}
        self.last = time.time()
        self.asks = 0

    def feed(self, data):
        """A datagram: the whole reply once it is complete (a reply that came in
        one piece at once), else None."""
        if not data.startswith(PIECE_MAGIC):
            return unpacked(data)
        message, index, count = PIECE_HEADER.unpack(data[4:12])
        if self.message is None:
            self.message, self.count = message, count
        if message != self.message:
            return None                 # a piece of an older reply
        self.parts[index] = data[12:]
        self.last = time.time()
        if len(self.parts) >= self.count:
            return unpacked(b''.join(self.parts[number] for number in range(self.count)))
        return None

    def ask_missing(self, client, address):
        """Ask again for the pieces that did not come (True if asked)."""
        if self.message is None or self.asks >= PIECE_ASKS or time.time() - self.last < PIECE_ASK_AFTER:
            return False
        missing = [index for index in range(self.count) if index not in self.parts]
        try:
            request = MISSING_PREFIX + json.dumps({'id': self.message, 'missing': missing}).encode('ascii')
            client.sendto(request, address)
        except Exception:
            return False
        self.asks += 1
        self.last = time.time()
        return True


def account_from_login(username):
    """logOn's username is '<uid>@<channel domain>'; the uid names the account."""
    if FORCED_ACCOUNT:
        return FORCED_ACCOUNT
    text = username if isinstance(username, string_types) else ''
    return text.split('@', 1)[0] or 'local-player-001'


def backend_login(username, port):
    """Log the account in to the chosen server; caches the returned state."""
    try:
        port = int(FORCED_PORT or port or DEFAULT_PORT)
    except Exception:
        port = DEFAULT_PORT
    _backend['address'] = (BACKEND_HOST, port)
    account = account_from_login(username)
    _backend['account'] = account
    try:
        request = {'account': account, 'port': port, 'rrc': 1, 'rrz': 1}
        if LOGIN_TOKEN:
            request['token'] = LOGIN_TOKEN
        reply = json.loads(_udp_exchange(LOGIN_PREFIX + json.dumps(request),
                                         65535, timeout=2.0))
    except Exception:
        _backend['error'] = 'Server is offline.' if LOGIN_TOKEN else 'The local server did not answer.'
        log_error('local-login-error', account=account, port=port)
        if LOGIN_TOKEN:
            show_offline_tip('Server is offline', True)
        return False
    if not reply.get('ok'):
        _backend['error'] = reply.get('message') or reply.get('error') or 'login refused'
        log('local-login-refused', account=account, port=port, error=safe(_backend['error']))
        return False
    _backend['session'] = reply.get('session')
    _lobby.pop('kicked', None)
    _backend['dedupe'] = bool(reply.get('dedupe'))      # it answers a request sent again only once
    _backend['zreq'] = bool(reply.get('zreq'))          # it reads compressed requests (pack_request)
    _backend['error'] = None
    state = reply.get('state') or {}
    _backend['server'] = state.get('server')
    _state['value'] = normalized_state(state)
    # saves still waiting for a retry: load_state merged them, and the
    # character screen now skips that load for a fresh LOGIN state
    merge_changes(_state['value'], _unsaved['changes'])
    _state['at'] = time.time()
    player = _state['value']['player']
    if LOGIN_TOKEN:
        name = (_backend['server'] or {}).get('name') or 'online'
        call_later(3.0, show_offline_tip, 'Connected to the online server %s' % name, True)
    log('local-login', account=account, port=port, server=safe((_backend['server'] or {}).get('name')),
        character=safe(player.get('nickname') if player.get('created') else None),
        gid=player.get('gid'))
    return True


def normalized_state(state):
    if not isinstance(state, dict):
        state = {}
    state.setdefault('player', {})
    state.setdefault('lobby', {})
    return state


STATE_FRESH_SECONDS = 10.0             # the LOGIN reply's state: not asked for again so soon


def load_state(refresh=False):
    if _state['value'] is not None and not refresh:
        return _state['value']
    try:
        state = json.loads(_udp_exchange(_with_session(STATE_REQUEST + ' '), 65535))
        if not isinstance(state, dict):
            raise ValueError('local lobby state must be an object')
        debug('local-lobby-state-loaded', player=safe(state.get('player'), 2000),
              lobby=safe(state.get('lobby'), 2000))
        _state['at'] = time.time()
    except Exception:
        log_error('local-lobby-state-error')
        state = _state['value'] or {}
    _state['value'] = normalized_state(state)
    merge_changes(_state['value'], _unsaved['changes'])     # not yet on the backend
    return _state['value']


def rank_score():
    """The solo ranked score: lobby badge and the result screen's rank page."""
    try:
        return max(0, int(load_state().get('lobby', {}).get('rankScore', 0) or 0))
    except Exception:
        return 0


def own_flag():
    """Your national flag as the backend keeps it (set with the /flag chat
    command: the game itself only ever reports 'UN')."""
    try:
        return to_native_str(load_state().get('lobby', {}).get('nationalFlag') or '')
    except Exception:
        return ''


def hall_theme_id():
    """The lobby theme (player.dtsHallThemeID): the one chosen in the Depot,
    else the game's default.  With 0 HallTheme has no theme data and every
    Depot screen that sets the light or an idle animation raised half-way
    through its enter / leave."""
    try:
        lobby = load_state().get('lobby', {})
        worn = lobby.get('appearance') if isinstance(lobby.get('appearance'), dict) else {}
        chosen = int(worn.get('dtsHallThemeID') or lobby.get('dtsHallThemeID', 0) or 0)
    except Exception:
        chosen = 0
    if chosen:
        return chosen
    try:
        return int(__import__('const').DEFAULT_HALL_THEME_ID)
    except Exception:
        return 0


def appearance_gender():
    """The Depot's male / female choice (player.dtsAppearanceGender), 0 = never set."""
    try:
        return int(load_state().get('lobby', {}).get('dtsAppearanceGender', 0) or 0)
    except Exception:
        return 0


SERVER_SILENT = 'The local server did not answer.'


UNSAVED_RETRY_SECONDS = 3.0
_unsaved = {'changes': {}, 'retrying': False, 'sending': False}


def merge_changes(into, changes):
    for section, values in changes.items():
        into.setdefault(section, {}).update(values)
    return into


def flush_unsaved():
    """Send what is not on the backend yet; again later while it stays silent.
    Online it goes without waiting (send_later): a save that timed out held
    the whole game for 1.5 s - in the lobby, and in a battle every 3 s."""
    _unsaved['retrying'] = False
    pending = _unsaved['changes']
    if not pending:
        return True
    if RPC_ASYNC:
        if _unsaved.get('sending'):
            return False                            # the answer to the last one comes first
        _unsaved['changes'] = {}
        _unsaved['sending'] = True
        send_later('save', _with_session(STATE_SAVE, pending, pieces=False),
                   lambda reply: unsaved_reply(pending, reply))
        return True
    _unsaved['changes'] = {}
    ok, _reason = save_state(**pending)
    if not ok and _reason == SERVER_SILENT:
        save_state_durable(**pending)               # still silent: keep it, try again
    if ok:
        log('local-state-unsaved-flushed', sections=sorted(pending))
    return ok


def unsaved_reply(pending, reply):
    _unsaved['sending'] = False
    if reply is None:
        # silent: keep it (what changed since is newer) and try again later
        _unsaved['changes'] = merge_changes(merge_changes({}, pending), _unsaved['changes'])
        log('local-state-save-queued', sections=sorted(pending))
        schedule_unsaved(UNSAVED_RETRY_SECONDS)
        return False
    ok = reply.startswith('ROS_LOCAL_SAVE_OK')
    reason = None if ok else (reply[len('ROS_LOCAL_SAVE_ERR'):].strip() or 'save refused')
    log('local-state-saved', ok=ok, reason=safe(reason), changes=safe(pending, 2000))
    if _unsaved['changes']:
        schedule_unsaved(0.0)                       # changed while this one was on its way
    return ok


def schedule_unsaved(delay):
    if not _unsaved['retrying']:
        _unsaved['retrying'] = True
        call_later(delay, flush_unsaved)


def save_state_durable(player=None, lobby=None):
    """A match's result, a setting: kept in the lobby state at once and sent
    to the backend - now, or as soon as it answers again (a launcher restart
    in the middle of a match must not lose the match)."""
    changes = {}
    if player:
        changes['player'] = player
    if lobby:
        changes['lobby'] = lobby
    if not changes:
        return False, 'nothing to save'
    if RPC_ASYNC:
        merge_changes(_unsaved['changes'], changes)
        merge_changes(load_state(), changes)
        schedule_unsaved(0.0)
        return True, None
    ok, reason = save_state(**changes)
    if ok or reason != SERVER_SILENT:
        return ok, reason
    merge_changes(_unsaved['changes'], changes)
    merge_changes(load_state(), changes)
    if not _unsaved['retrying']:
        _unsaved['retrying'] = True
        call_later(UNSAVED_RETRY_SECONDS, flush_unsaved)
    log('local-state-save-queued', sections=sorted(changes))
    return True, None


def save_state(player=None, lobby=None):
    """Returns (ok, reason); reason is the backend's message on refusal."""
    changes = {}
    if player:
        changes['player'] = player
    if lobby:
        changes['lobby'] = lobby
    if not changes:
        return False, 'nothing to save'
    if _unsaved['changes'] and not _unsaved['retrying']:
        pending, _unsaved['changes'] = _unsaved['changes'], {}
        changes = merge_changes(merge_changes({}, pending), changes)
    try:
        # a save's reply is small; and a server before TRANSPORT_KEYS took "rrc" for a section
        reply = _udp_exchange(_with_session(STATE_SAVE, changes, pieces=False))
    except Exception:
        log_error('local-state-save-error', changes=safe(changes, 2000))
        return False, SERVER_SILENT
    ok = reply.startswith('ROS_LOCAL_SAVE_OK')
    reason = None if ok else (reply[len('ROS_LOCAL_SAVE_ERR'):].strip() or 'save refused')
    if not ok and reason and 'not logged in' in reason and not _unsaved.get('relogin'):
        _unsaved['relogin'] = True
        try:
            port = (_backend.get('address') or (None, DEFAULT_PORT))[1]
            if backend_login(_backend.get('account') or FORCED_ACCOUNT or '', port):
                log('local-session-relogin', ok=True)
                return save_state(player=player, lobby=lobby)
            log('local-session-relogin', ok=False)
        except Exception:
            log_error('local-session-relogin-error')
        finally:
            _unsaved['relogin'] = False
    if ok:
        state = load_state()
        for section, values in changes.items():
            state.setdefault(section, {}).update(values)
    log('local-state-saved', ok=ok, reason=safe(reason), changes=safe(changes, 2000))
    return ok, reason


def to_native_str(value):
    """json.loads gives unicode in Python 2; the engine and the name widgets
    use UTF-8 byte strings (like names typed in the game)."""
    if value is not None and not isinstance(value, str):
        try:
            return value.encode('utf-8')
        except Exception:
            return value
    return value


def saved_character():
    player = load_state().get('player', {})
    name = to_native_str(player.get('nickname'))
    if not player.get('created') or not name:
        return None
    try:
        character_type = int(player.get('characterType') or DEFAULT_CHARACTER_TYPE)
    except Exception:
        character_type = DEFAULT_CHARACTER_TYPE
    return name, character_type


def local_gid():
    try:
        return int(load_state().get('player', {}).get('gid') or DEFAULT_GID)
    except Exception:
        return DEFAULT_GID


# --------------------------------------------------------------------------
# Offline robustness helpers
# --------------------------------------------------------------------------

LIST_SUFFIXES = ('List', 'Array', 'Items', 'Records', 'IDs', 'Ids', 'Gids', 'GIDs')
DICT_SUFFIXES = ('Dict', 'Info', 'Infos', 'Data', 'Map', 'Record', 'Table', 'Snapshot')


def empty_value_for(name):
    if name.endswith(LIST_SUFFIXES):
        return []
    if name.endswith(DICT_SUFFIXES):
        return {}
    return None


# Attributes some lobby code reads that a local entity never receives at all.
MISSING_PLAYER_DEFAULTS = {
    'monthPayRebateSpecialAwardInfo': lambda: {'awards': {}},
    # UILimitWelfareController.on_enter
    'personalRecommendCanBuy': lambda: False,
    # iRosLandDrone.toShowDroneUnlockBadge (UIMain.on_enter)
    'hasDroneRewardToGet': lambda: False,
    'iLuckyCarnivalIsSuper': lambda: False,
    # iLuckyCarnival: set by refreshLuckyCarnivalData from onUpdateLuckyCarnivalData;
    # read by UILuckyCarnivalAdvance.refreshLotteryItems and
    # iNewMonthcard.onCheckNewMonthcardActive (len()) before the backend answers
    'iLuckyCarnivalRoundGift': list,
    'iLuckyCarnivalRoundGiftValue': list,
    'iLuckyCarnivalRoundGotIndex': list,
    'iLuckyCarnivalSeasonGiftGotState': list,
    'iLuckyCarnivalItemId2Value': dict,
    'iLuckyCarnivalSeasonCharge': lambda: 0,
    'iLuckyCarnivalSeasonDraws': lambda: 0,
    'iLuckyCarnivalRoundDraws': lambda: 0,
    'iLuckyCarnivalSeasonNo': lambda: 0,
    'iLuckyCarnivalRoundNo': lambda: 0,
    'iLuckyCarnivalByRecommend': lambda: False,
    # UIBattlegroundsInGameActionAndEmoji.fillActionItems
    'dtsInGameActionAppearanceIDs': lambda: [],
    # UIPersonalSpace._getPersonInfo (your own space)
    'portrait': lambda: 0,
    # SUPPLY (iSupplement / UIMonthlySupplyPackage / UIHotActivity): online
    # pushes that never arrive offline.  The *Times names would otherwise get
    # int 0 from the name rules and crash .items() / [sid] lookups.
    'hasAlreadyShowSupplyID': lambda: 0,
    'iLuckyCarnivalRoundState': lambda: {},
    'curBlackFridaySupplementDiscounts': lambda: {},
    # UIMall.fillGoods / doClothMallSaLogging: recordMallGoods.update(...)
    'recordMallGoods': lambda: {},
    # DtsAppearanceFilterAndSortUtils.getMallGoodSortLevel: goodID in clientBuyTimes
    'clientBuyTimes': lambda: {},
    # UIMain.displayAll -> showRedPoint(player.redPoints): only gmsyncRedPoints
    # (a GM push) ever sets it; the name rules would answer int 0 ('Points')
    'redPoints': lambda: {},
    # the hosted client's own (2026) properties
    'personalRecommendState': lambda: 0,
    'personalRecommendGift': lambda: {},
    'accumulateChargeClickState': lambda: 0,
    'accumulateWeeklyGiftState': lambda: 0,
    'dtsShareAppearanceSuit': lambda: {},
    'ethnicity': lambda: 0,
    'rlMonthlyOfferEnd': lambda: 0,
    'rlTopUpEnabled': lambda: True,
    'shareAddtionShow': lambda: False,
}
# Supply props that are dicts (usually keyed by supplement id) online.
SUPPLY_DICT_PROPS = ('multipleOpenTimes', 'openSupplyTimes', 'openMallTimes',
                     'openHalfMonthPackageTimes', 'openItemConvertTimes', 'openSupplyGiftInfo',
                     'availableOpenSupplyGift', 'freeLotteryTimesDict', 'weekendBuySupplementCntDict',
                     'accumulateBuySupplementCntDict', 'weekendAwardReceivedRecord',
                     'supplementWatchAdData', 'supplementFreeLotteryTimeStampDict',
                     # iLimitPackage.canBuy*Pack: `packID in self.limitPackageBuyTimes` -
                     # an int from the name rules crashed UILimitWelfareController.on_enter
                     'limitPackageBuyTimes', 'halfMonthPackageBuyTimes', 'dtsLimitPackageExtraBoxBuyTimes',
                     'availableLimitPackage', 'availableHalfMonthPackage')
for _supply_prop in SUPPLY_DICT_PROPS:
    MISSING_PLAYER_DEFAULTS[_supply_prop] = dict
del _supply_prop
# Reply parameters (_smart_value) that take these defaults too; the older
# entries above (portrait...) keep their own reply rules.
SUPPLY_PARAM_DEFAULTS = frozenset(SUPPLY_DICT_PROPS + (
    'hasAlreadyShowSupplyID', 'iLuckyCarnivalRoundState', 'curBlackFridaySupplementDiscounts'))
# availableXxx reply parameters that are counters/flags/times, not dicts.
AVAIL_SCALAR_SUFFIXES = ('cnt', 'count', 'num', 'times', 'time', 'ts', 'timestamp', 'stamp', 'id',
                         'ids', 'list', 'flag', 'state', 'status', 'type', 'score', 'level', 'lv',
                         'index', 'idx', 'amount', 'price')

# Name patterns local_getattribute answers for the local player when the
# online snapshot never delivered the attribute (see missing_player_default).
BOOL_PREFIX = re.compile(r'^(is|has|can|need|show|enable|should)[A-Z]')
BOOL_INFIX = re.compile(r'(Can|Is)[A-Z]')  # personalRecommendCanBuy, iLuckyCarnivalIsSuper
BOOL_SUFFIXES = ('Flag',)
INT_SUFFIXES = ('Count', 'Cnt', 'Num', 'Times', 'Score', 'Level', 'Lv', 'Time', 'Timestamp',
                'TimeStamp', 'Stamp', 'Point', 'Points', 'ID', 'Id', 'Flags',
                'Buff')                 # speed buffs are added up (Avatar.getSpeedExtraFactor)
# Multipliers: a missing one has to read as "no change", not 0.  The
# battleground's move_unit multiplies by jumpFactor on every character reset,
# and a 0 there is a player who cannot jump (or move).
FLOAT_ONE_SUFFIXES = ('Factor', 'Scale', 'Ratio', 'Multiplier')
# Missing names with these prefixes are almost certainly methods; answering
# 0/[]/{} would only turn the AttributeError into "not callable".
METHOD_PREFIX = re.compile(r'^(get|set|on|req|request|query|sync|send|do|refresh|update|try|'
                           r'check|add|del|remove|open|close|init|reset|clear)[A-Z_]')
_NO_DEFAULT = object()
# A field, not a method, though it starts like one: onPlaneID, onVehicleID...
BATTLE_ID_FIELD = re.compile(r'^on[A-Z]\w*(ID|Id)$')


def missing_player_default(name):
    """Safe empty value for an online-only player property, or _NO_DEFAULT."""
    if name.startswith('_'):
        return _NO_DEFAULT
    factory = MISSING_PLAYER_DEFAULTS.get(name)
    if factory is not None:
        return factory()
    if BOOL_PREFIX.match(name):
        return False
    if METHOD_PREFIX.match(name):
        return _NO_DEFAULT
    # Containers first: code may iterate a hasXList, and [] is falsy anyway.
    if name.endswith(LIST_SUFFIXES):
        return []
    if name.endswith(DICT_SUFFIXES):
        return {}
    if name.endswith(FLOAT_ONE_SUFFIXES):
        return 1.0
    if name.endswith(INT_SUFFIXES):
        return 0
    if BOOL_INFIX.search(name) or name.endswith(BOOL_SUFFIXES):
        return False
    return _NO_DEFAULT


# Names that read as an empty list when nothing else matches (plurals).
PLURAL_SUFFIX = re.compile(r'(?:[a-z]s|IDs|Ids|List|Array)$')


# libclaudia's Object.DestroyImmediate reads this off whatever it is handed; a
# stand-in raising there aborts the whole leaveWorld chain of the battle body.
DESTROYED_FLAG = '____destroyed__'


class LocalUnknown(object):
    """Stands in for anything a battle server would have sent and the local
    one has not.

    In a battleground the client reads and calls a great deal off the player
    and the space, every frame.  A missing name raising AttributeError stops
    the entry; answering None or 0 only moves the failure one line down
    ("'int' object is not callable" from PlayerFPAppear.onInitDress,
    "unsupported operand type(s) for *: 'float' and 'NoneType'" from
    move_unit.setJumpHeight).  This reads as empty, counts as zero, calls as
    a no-op and keeps handing itself back, so the client's own code carries
    on to the next thing.

    RISK: it is true for hasattr and silently swallows logic, so a feature
    check on one of these names takes the "absent/zero" branch.  That is the
    trade while the battleground has no real server behind it; every name is
    logged (local-player-attribute-defaulted) so they can be filled in."""

    __slots__ = ('_rl_name',)

    def __init__(self, name=''):
        object.__setattr__(self, '_rl_name', name)

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, name):
        if name == DESTROYED_FLAG:
            return True             # Object.DestroyImmediate asks: nothing to destroy
        if name.startswith('__'):
            raise AttributeError(name)
        return LocalUnknown('%s.%s' % (object.__getattribute__(self, '_rl_name'), name))

    def __setattr__(self, name, value):
        pass

    def __getitem__(self, key):
        return self

    def __setitem__(self, key, value):
        pass

    def __len__(self):
        return 0

    def __iter__(self):
        return iter(())

    def __contains__(self, item):
        return False

    def __nonzero__(self):          # Python 2
        return False

    __bool__ = __nonzero__          # Python 3

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __index__(self):
        return 0

    # Arithmetic counts as zero, whichever side it is on.
    def __add__(self, other):
        return other

    __radd__ = __add__

    def __sub__(self, other):
        return 0

    __rsub__ = __sub__

    def __mul__(self, other):
        return 0

    __rmul__ = __mul__

    def __div__(self, other):
        return 0

    __truediv__ = __div__
    __rdiv__ = __div__
    __rtruediv__ = __div__

    def __mod__(self, other):
        return 0

    __rmod__ = __mod__              # UIDtsMap.replaceInBuildingDistanceStr: x % 10
    __floordiv__ = __mod__
    __rfloordiv__ = __mod__
    __pow__ = __mod__
    __rpow__ = __mod__

    def __neg__(self):
        return 0

    __pos__ = __neg__
    __abs__ = __neg__
    __invert__ = __neg__

    def __lt__(self, other):
        return 0 < other

    def __le__(self, other):
        return 0 <= other

    def __gt__(self, other):
        return 0 > other

    def __ge__(self, other):
        return 0 >= other

    def __eq__(self, other):
        return other is self or other is None or other == 0

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return 0

    def __str__(self):
        return ''

    def __repr__(self):
        return '<local-unknown %s>' % object.__getattribute__(self, '_rl_name')


for _rl_op in ('__and__', '__rand__', '__or__', '__ror__', '__xor__', '__rxor__', '__lshift__', '__rlshift__',
               '__rshift__', '__rrshift__', '__mod__', '__rmod__', '__floordiv__', '__rfloordiv__',
               '__truediv__', '__rtruediv__', '__div__', '__rdiv__', '__pow__', '__rpow__', '__add__', '__radd__',
               '__sub__', '__rsub__', '__mul__', '__rmul__', '__neg__', '__pos__', '__abs__', '__invert__',
               '__int__', '__index__', '__float__', '__long__'):
    if _rl_op not in LocalUnknown.__dict__:
        setattr(LocalUnknown, _rl_op, (lambda self, *args: 0.0) if _rl_op == '__float__' else (lambda self, *args: 0))
del _rl_op


def battle_player_default(name):
    """Like missing_player_default, but for a player in a battleground.

    There the client builds the whole world locally and no online data
    arrives at all, while one AttributeError in the entry path
    (``Avatar.enterWorld`` -> ``onPlayerInit`` -> ...) stops the entry dead.
    So anything that is not obviously a method is answered, and every name is
    logged - the log is how the list gets filled in properly.
    """
    value = missing_player_default(name)
    if value is not _NO_DEFAULT:
        return value
    if BATTLE_ID_FIELD.match(name):
        # onPlaneID reads like a callback but is the plane the player is on;
        # ClientEntity.prerequisites reads it for every entity, every frame.
        return 0
    if name.startswith('_') or METHOD_PREFIX.match(name):
        return _NO_DEFAULT
    if name.endswith(DICT_SUFFIXES):
        return {}
    if PLURAL_SUFFIX.search(name):
        return []
    # Not a container and not obviously a number: it may be read, called,
    # indexed or multiplied, so hand back something that survives all four.
    return LocalUnknown(name)


def fill_missing_defaults(obj):
    added = []
    for name, factory in MISSING_PLAYER_DEFAULTS.items():
        try:
            if getattr(obj, name, None) is None:
                setattr(obj, name, factory())
                added.append(name)
        except Exception:
            pass
    if added:
        log('local-missing-defaults', names=added)


def fill_none_defaults(obj, label):
    """Online snapshots fill these containers; offline they stay None and
    code such as UIMain.showRedPoint iterates them."""
    filled = []
    try:
        names = set(getattr(obj, '__dict__', {}).keys())
    except Exception:
        names = set()
    try:
        names.update(name for name in dir(obj) if name.endswith(LIST_SUFFIXES + DICT_SUFFIXES))
    except Exception:
        pass
    for name in sorted(names):
        if name.startswith('_') or empty_value_for(name) is None:
            continue
        try:
            if getattr(obj, name) is not None:
                continue
        except Exception:
            continue
        value = empty_value_for(name)
        if value is None:
            continue
        try:
            setattr(obj, name, value)
            filled.append(name)
        except Exception:
            pass
    log('local-none-defaults', target=label, count=len(filled), names=filled[:200])
    return filled


_guard_reported = set()


UIMAIN_GUARDED_METHODS = ('showRedPoint',)

# Other screens' methods that crash on data only the online server sent.
# Only plain methods called directly (not libclaudia SendMessage targets).
UI_GUARDED_METHODS = {
    # Friends -> Meet -> personal space: needs the appearance from requireBaseInfo.
    ('ui.UIPersonalSpace', 'UIPersonalSpace'): ('setCurPersonAppear',),
    # SUPPLY -> monthly package: its gift config comes from the online server.
    # Leaving it: _resumeHallScene (called by on_leave, which UIMgr._leave_ui_general
    # calls directly - neither is a SendMessage target) raised "a world.scene is
    # required!" and aborted tab switches and Close of UISupplyController.
    ('ui.UIMonthlySupplyPackage', 'UIMonthlySupplyPackage'): ('Awake', 'on_leave', '_resumeHallScene'),
    # Leaving the lobby for a battleground: SceneSystem.loadMap destroys the
    # hall space and UIMain's widget teardown then touches it ("invalid space
    # object which has been deleted").  It is raised inside
    # Application._late_update -> _destroy_current_level, every frame, so the
    # level never finishes being destroyed and the map load never completes.
    # The battle hook closes UIMain first; this is the net for what it misses.
    ('ui.UIMain', 'UIMain'): ('_on_widget_destroy',),
    # Limited Welfare tabs: on_enter aborting leaves currentUI unset.
    ('ui.UILimitWelfareController', 'UILimitWelfareController'): (
        '_doSelectHotActivityBtn', '_doSelectTimeLimitActivityBtn', '_doSelectPayRebateBtn',
        '_doSelectMallBtn', '_doSelectActivityBtn', '_doSelectHuiliuRecallBtn',
        '_doSelectPersonalRecommend'),
    # Back from a battle the hall Athlete becomes the player again outside
    # apply_local_profile; tryActiveWeekendPushRedBadge iterating a None unwound
    # the whole PlayerAthlete.onCreate mixin chain (iFriend, iRank, iDayTask,
    # iActivityLimitTime... skipped everything after super()).
    ('iWeekendPush', 'iWeekendPush'): ('tryActiveWeekendPushRedBadge',),
}


# Screens fed by the lobby's web services (msHttpAP -> update_server, which
# answers {}).  Their onGet* handlers get the reply as a LocalReply instead,
# so 'Ret' reads 0 and every missing count reads 0 instead of raising and
# leaving designer placeholders (Matched/Liked Me/I Liked "68").
# Empty: wrapping methods of these screens broke libclaudia's SendMessage
# delivery (the stats panel never got onGetRecordData / onGetBaseInfo).  The
# backend now answers the Meet web calls with complete JSON instead.
WEB_REPLY_SCREENS = ()


def _deep_reply(value, profile):
    if isinstance(value, LocalReply):
        return value
    if isinstance(value, dict):
        reply = _nested_reply(profile)
        for key, item in value.items():
            dict.__setitem__(reply, key, _deep_reply(item, profile))
        return reply
    if isinstance(value, list):
        return [_deep_reply(item, profile) for item in value]
    return value


def adapt_web_replies(cls):
    if cls.__dict__.get('_rl_web_adapted'):
        return 0
    if not any(name.startswith('onGet') for name in cls.__dict__):
        return 0
    count = 0
    for name, value in list(cls.__dict__.items()):
        if not name.startswith('onGet') or not isinstance(value, types.FunctionType):
            continue

        def make(original):
            def adapted(self, *args, **kwargs):
                if any(isinstance(arg, dict) and not isinstance(arg, LocalReply) for arg in args):
                    profile = _local_profile()
                    args = tuple(_deep_reply(arg, profile) for arg in args)
                return original(self, *args, **kwargs)
            adapted.__name__ = original.__name__
            adapted._rl_original = original
            return adapted
        setattr(cls, name, make(value))
        count += 1
    cls._rl_web_adapted = True
    if count:
        log('local-web-replies-adapted', ui=cls.__name__, methods=count)
    return count


def install_ui_guards():
    for (module_name, class_name), methods in UI_GUARDED_METHODS.items():
        try:
            module = __import__(module_name, fromlist=[class_name])
            guard_class_methods(getattr(module, class_name), only=methods)
        except Exception:
            log_error('local-ui-guard-error', ui=class_name)
    for module_name, class_name in WEB_REPLY_SCREENS:
        try:
            module = __import__(module_name, fromlist=[class_name])
            # onGetCurUserData lives on a helper class of the module, not on
            # the screen class itself: adapt every class defined there.
            for value in list(vars(module).values()):
                if isinstance(value, type) and getattr(value, '__module__', None) == module.__name__:
                    adapt_web_replies(value)
                elif type(value).__name__ == 'classobj' and \
                        getattr(value, '__module__', None) == module.__name__:   # Python 2 old-style class
                    adapt_web_replies(value)
        except Exception:
            log_error('local-web-reply-adapter-error', ui=class_name)


def guard_class_methods(cls, only=()):
    """Wrap a UI class's own methods so one failure (usually missing online
    data) is logged and skipped instead of aborting the whole panel."""
    # Per method, not per class: a re-injected hook with a longer list (e.g.
    # on_leave added for UIMonthlySupplyPackage) still guards the new names,
    # and a method guarded before is never wrapped twice.
    try:
        handlers = set(getattr(cls, '____messageHandlers__', None) or ())
    except Exception:
        handlers = set()
    count = 0
    for name, value in list(cls.__dict__.items()):
        if name not in only or not isinstance(value, types.FunctionType):
            continue
        if getattr(value, '_rl_guard', False):
            continue
        if name not in SCREEN_LIFECYCLE and (name in handlers or
                                             getattr(value, '____isMessageHandler__', False)):
            # wrapping a libclaudia message handler breaks SendMessage dispatch
            log('local-ui-guard-skipped', ui=cls.__name__, method=name, reason='message-handler')
            continue

        def make_guard(method_name, original):
            def guarded(*args, **kwargs):
                try:
                    return original(*args, **kwargs)
                except Exception:
                    key = (cls.__name__, method_name)
                    if key not in _guard_reported:
                        _guard_reported.add(key)
                        log_error('local-ui-guarded-error', ui=cls.__name__, method=method_name)
                    return None
            guarded.__name__ = original.__name__
            guarded.__doc__ = original.__doc__
            guarded.__module__ = original.__module__
            guarded.__dict__.update(getattr(original, '__dict__', {}))
            guarded._rl_original = original
            guarded._rl_guard = True
            return guarded

        try:
            setattr(cls, name, make_guard(name, value))
            count += 1
        except Exception:
            pass
    if count:
        log('local-ui-guard-installed', ui=cls.__name__, methods=count)
    return count


# Message boxes that only make sense online (connection lost, server busy...).
# Everything else (quit prompt, purchase confirmations) is shown normally.
ONLINE_ONLY_MSGBOX = re.compile(r'network|disconnect|connection|reconnect|server|maintenance|'
                                r'timed? ?out|login failed|relogin|kicked', re.I)
# ROS 2 needs NetEase's DLC CDN (gone) and its own hall scene: entering it
# failed half-way, left the hall team switched and logged the player out.
ROS2_TIP = 'ROS 2 is not available on this server.'
UNAVAILABLE_SCREENS = {'UIR2FlowActivity': ROS2_TIP, 'UIR2Main': ROS2_TIP}
UI_TRACE_METHODS = re.compile(r'enter|leave|back|close|push|pop|return|escape|esc|stack', re.I)
_ui_trace = {'last': None}


def _msgbox_text(args, kwargs):
    parts = []
    for value in list(args) + list(kwargs.values()):
        if isinstance(value, dict):
            parts.extend(str(value.get(key, '')) for key in ('msg', 'title', 'content', 'text'))
        elif isinstance(value, string_types):
            parts.append(value)
    return ' '.join(parts)


FOCUS_POPUP = '____focus_popup_ui__'


def screen_shown(screen):
    if screen is None or not getattr(screen, 'is_enter', False):
        return False
    try:
        return bool(screen.isVisible())
    except Exception:
        return True


def prune_focus(ui_mgr):
    """Back (Esc) closes the top of current_focus.  Store tabs leave hidden
    helper panels (UIProbabilityTipsSupplySingle) and closed tabs there, and a
    popup that failed to open keeps the focus: Back then closed nothing."""
    focus = getattr(ui_mgr, 'current_focus', None)
    dropped = []
    if isinstance(focus, list):
        for name in list(focus):
            if not screen_shown(getattr(ui_mgr, name, None)):
                focus.remove(name)
                dropped.append(name)
    popup = getattr(ui_mgr, FOCUS_POPUP, None)
    if popup is not None:
        screen = getattr(ui_mgr, popup, None) if isinstance(popup, string_types) else popup
        if not screen_shown(screen):
            setattr(ui_mgr, FOCUS_POPUP, None)
            dropped.append('popup')
    if dropped:
        log('local-back-focus-pruned', dropped=dropped)
    return dropped


def install_back_key(ui_mgr):
    original = getattr(ui_mgr, 'AndroidUIBack', None)
    if original is None or getattr(original, '_rl_back_key', False):
        return False

    def back_key(*args, **kwargs):
        try:
            prune_focus(ui_mgr)
        except Exception:
            log_error('local-back-focus-error')
        return original(*args, **kwargs)
    back_key._rl_back_key = True
    ui_mgr.AndroidUIBack = back_key
    return True


CARNIVAL_SCREENS = ('UILuckyCarnival', 'UILuckyCarnivalAdvance', 'UILuckyCarnivalSuper')
CARNIVAL_ROUND_OPEN = 1   # const.LuckyCarnivalConst.ROUND_STATE_OPEN
CARNIVAL_CLOSED_TIP = 'Lucky Carnival is closed for now.'


def carnival_open(player=None):
    """True once the backend sent an open round with prizes.  The panels index
    the round's prize list in on_enter; with no round they crashed
    (UILuckyCarnivalAdvance.refreshLotteryItems)."""
    try:
        if player is None:
            player = BigWorld.player()
        return (getattr(player, 'iLuckyCarnivalRoundState', None) == CARNIVAL_ROUND_OPEN
                and len(getattr(player, 'iLuckyCarnivalRoundGift', None) or ()) > 0)
    except Exception:
        return False


# Top-up is off until the backend says otherwise (topup_packs.json "enabled",
# sent once at lobby entry as rlTopUpEnabled).  Off, the TOP-UP button and every
# real-money buy show the admin message and nothing reaches the pay SDK.
TOPUP_PROP = 'rlTopUpEnabled'
TOPUP_URL = 'http://172.16.69.27/topup'
TOPUP_DISABLED_TIP = 'Top up on our website (opening it now): ' + TOPUP_URL


def open_topup_site():
    """The in-game pay buttons cannot take real money here: open the website's
    top-up page in the player's browser instead."""
    try:
        os.startfile(TOPUP_URL)
        return True
    except Exception:
        pass
    try:
        import ctypes
        ctypes.windll.shell32.ShellExecuteW(None, u'open', TOPUP_URL, None, None, 1)
        return True
    except Exception:
        log_error('local-topup-open-site-error')
        return False

TOPUP_SCREENS = ('UIPayment', 'UIPCPaySelect', 'UIPaymentMol')
TOPUP_CONTROLLER = 'UIPayController'
TOPUP_TAB = 1                    # UIPayController.targetTypeToArgs[1]: UIPayment, the default tab
PAY_LOADING_SCREEN = 'UIPayLoading'
PAY_REFUSED_SECONDS = 3.0        # the buy buttons enter UIPayLoading right after requsetPayGoods
PAY_RPCS = frozenset(['requestRealNameAuthenCheckBeforeRequsetingPayGoods', 'checkPurchaseLimitAndTime'])
TOPUP_GATED = frozenset((TOPUP_CONTROLLER, PAY_LOADING_SCREEN) + TOPUP_SCREENS)
_topup = {'refused': 0.0}


def topup_open(player=None):
    """True only once the backend sent rlTopUpEnabled=True; a missing prop (or
    a MISSING_PLAYER_DEFAULTS stand-in) counts as closed."""
    try:
        if player is None:
            player = BigWorld.player()
        return getattr(player, TOPUP_PROP, False) is True
    except Exception:
        return False


def _ui_tab_type(args, kwargs):
    """UIPayController's tabType: a keyword, inside an 'args' dict, or in a
    positional dict (its on_enter reads args.get('tabType'))."""
    if 'tabType' in kwargs:
        return kwargs.get('tabType')
    for value in [kwargs.get('args')] + list(args):
        if isinstance(value, dict) and 'tabType' in value:
            return value.get('tabType')
    return None


def topup_screen(ui_mgr, ui_name, args, kwargs):
    if ui_name == TOPUP_CONTROLLER:
        # TOP-UP passes only parent, gotoPayPanel tabType=1.  Limit packs (2/5),
        # month card (3) and accumulate charge (4) still open: their buys are
        # refused in requsetPayGoods.
        try:
            tab = _ui_tab_type(args, kwargs)
            return tab is None or int(tab) in (0, TOPUP_TAB)
        except Exception:
            return True
    if ui_name in TOPUP_SCREENS:
        # inside an open controller its own tab still draws (a missing child
        # would leave the controller half built); the buy on it is refused
        return not screen_shown(getattr(ui_mgr, TOPUP_CONTROLLER, None))
    if ui_name == PAY_LOADING_SCREEN:
        return time.time() - _topup['refused'] < PAY_REFUSED_SECONDS
    return False


def close_pay_loading():
    """A refused pay must not leave the game 'paying': IS_PAYING blocks the
    next buy and UIPayLoading covers the screen (the game's own failure
    callback only shows a tip)."""
    try:
        __import__('pay_utils').closePay()
    except Exception:
        log_error('local-topup-close-pay-error')
    try:
        import Globals
        loading = getattr(Globals.uiMgr, PAY_LOADING_SCREEN, None)
        if loading is not None and getattr(loading, 'is_enter', False):
            Globals.uiMgr.leave_ui(PAY_LOADING_SCREEN)
    except Exception:
        log_error('local-topup-close-loading-error')


def refuse_pay(name):
    _topup['refused'] = time.time()
    log('local-topup-refused', via=name)
    show_offline_tip(TOPUP_DISABLED_TIP, force=True)
    close_pay_loading()
    open_topup_site()


def install_pay_gate():
    """Every real-money buy (TOP-UP packs, month card, limit / half-month
    packages, first-charge welfare, the PC pay select) goes through
    iPay.requsetPayGoods: refused there before any RPC, screen or SDK work."""
    try:
        pay_class = __import__('iPay').iPay
    except Exception:
        log_error('local-pay-gate-error')
        return False
    original = pay_class.__dict__.get('requsetPayGoods')
    if original is None or getattr(original, '_rl_pay_gate', False):
        return False

    def requsetPayGoods(self, goodsID, *args, **kwargs):
        if not topup_open(self):
            refuse_pay('requsetPayGoods')
            return None
        return original(self, goodsID, *args, **kwargs)
    requsetPayGoods._rl_pay_gate = True
    pay_class.requsetPayGoods = requsetPayGoods
    return True


def install_ui_manager_hooks(Globals):
    """Filter online-only message boxes and trace screen navigation."""
    ui_mgr = Globals.uiMgr
    if getattr(ui_mgr, '_rl_hooks_installed', False):
        return
    original = ui_mgr.enter_ui

    def local_enter_ui(ui_name, *args, **kwargs):
        # not a nesting level: the hook's work inside (RPCs, log lines) still
        # counts as hook time, the panel itself as ui time
        mark = (_lobby_perf['token'] if _lobby_perf['running'] else _PERF_OFF), perf_clock()
        try:
            return enter_ui_watched(ui_name, *args, **kwargs)
        finally:
            perf_done('ui ' + str(ui_name), mark, 'ui_ms', nested=False)

    def enter_ui_watched(ui_name, *args, **kwargs):
        if isinstance(ui_name, string_types) and ui_name in UNAVAILABLE_SCREENS:
            # UIMain's ROS2 button, Activity panel 4 and tryEnterUIR2Main all come here
            log('local-ui-unavailable', ui=ui_name)
            show_offline_tip(UNAVAILABLE_SCREENS[ui_name], force=True)
            return None
        if not HORSE_RACING_OPEN and isinstance(ui_name, string_types) and HORSE_SCREENS.match(ui_name):
            # Happy Derby is closed; jump links (activity centre, mail) can still open it
            log('local-horse-racing-screen-blocked', ui=ui_name)
            show_offline_tip(HORSE_RACING_TIP, force=True)
            return None
        if ui_name in CARNIVAL_SCREENS and not carnival_open():
            # every way in (tile, ads, season panel) ends here; with no round the panel crashed
            log('local-carnival-closed', ui=ui_name)
            show_offline_tip(CARNIVAL_CLOSED_TIP, force=True)
            return None
        if (ui_name in TOPUP_GATED and not topup_open()
                and topup_screen(ui_mgr, ui_name, args, kwargs)):
            # TOP-UP button, gotoPayPanel, the PC pay select; and the loading
            # overlay a refused buy opens right after requsetPayGoods (no 2nd tip)
            log('local-topup-closed', ui=ui_name)
            if ui_name != PAY_LOADING_SCREEN:
                show_offline_tip(TOPUP_DISABLED_TIP, force=True)
            return None
        if ui_name == 'UIMsgBox':
            text = _msgbox_text(args, kwargs)
            if ONLINE_ONLY_MSGBOX.search(text):
                log('local-lobby-msgbox-suppressed', text=text[:300])
                return None
            log('local-lobby-msgbox-shown', text=text[:300])
        if ui_name in APPEARANCE_SCREENS:
            restore_model_size()
        if isinstance(ui_name, string_types) and ui_name.startswith(MANUAL_SCREEN_PREFIX):
            install_manual_screens()        # before the screen's module builds it
        result = original(ui_name, *args, **kwargs)
        if ui_name in ACTIVITY_PANEL_SCREENS:
            try:
                mark_activity_seen()
            except Exception:
                log_error('local-activity-seen-error', ui=ui_name)
        if returning_from_battle() and ui_name in LOGIN_SCREENS:
            keep_hidden(ui_mgr, ui_name)
        log('local-ui-entered', ui=ui_name)
        if _lobby.get('entered') and ui_name not in _catalog['panels']:
            # its code walk later, not inside the open (the first open of a panel hitched)
            panel = getattr(ui_mgr, ui_name, None)
            if panel is not None:
                call_later(CATALOG_PANEL_DELAY, catalog_panel_class, ui_name, type(panel))
        try:
            if isinstance(ui_name, string_types) and SCREEN_UI_WATCH.search(ui_name):
                call_later(0.5, dump_screen_code, 'ui:' + ui_name)
        except Exception:
            log_error('local-screen-code-schedule-error', ui=safe(ui_name))
        return result

    ui_mgr._rl_original_enter_ui = original
    ui_mgr.enter_ui = local_enter_ui
    install_back_key(ui_mgr)
    ui_mgr._rl_hooks_installed = True
    trace_ui_manager(type(ui_mgr))
    log('local-ui-hooks-installed')


UI_CLOSE_WATCH = ('UIBattlegroundsResult',)
UI_CLOSE_CALLS = re.compile(r'^(leave|close|destroy|back|hide|pop)', re.I)


def trace_ui_manager(cls):
    """Log navigation calls (enter/leave/back/close/...) on the UI manager
    class, including the internal ones controllers use, and any exception
    they raise - this is how a broken back button shows up in the log."""
    if cls.__dict__.get('_rl_traced'):
        return
    traced = []
    for name, value in list(cls.__dict__.items()):
        if name.startswith('__') or not isinstance(value, types.FunctionType):
            continue
        if not UI_TRACE_METHODS.search(name):
            continue

        def make_tracer(method_name, function):
            def traced_method(self, *args, **kwargs):
                target = args[0] if args and isinstance(args[0], string_types) else None
                key = (method_name, target)
                if target is not None and key != _ui_trace['last']:
                    _ui_trace['last'] = key
                    # 4 lines per screen opened (280 in 30 s browsing, 66 ms of
                    # the game's time): 'local-ui-entered' says it once
                    debug('local-ui-nav', call=method_name, ui=target)
                if target in UI_CLOSE_WATCH and UI_CLOSE_CALLS.search(method_name):
                    # who closes the result screen: the game's own code, not the hook,
                    # closed it at once on the online server (Chicken Dinner)
                    log('local-ui-closed-by', call=method_name, ui=target,
                        stack=[line.strip() for line in traceback.format_stack(limit=14)[:-1]])
                try:
                    return function(self, *args, **kwargs)
                except Exception:
                    log_error('local-ui-nav-error', call=method_name, ui=target)
                    raise
            traced_method.__name__ = function.__name__
            traced_method._rl_original = function
            return traced_method

        try:
            setattr(cls, name, make_tracer(name, value))
            traced.append(name)
        except Exception:
            pass
    cls._rl_traced = True
    log('local-ui-trace-installed', methods=sorted(traced))


class _ErrorTee(object):
    """sys.stderr wrapper: the game prints script tracebacks (e.g. from
    button callbacks) to stderr, which nobody sees; copy them to a file.

    A traceback raised every frame (ClientEntity.prerequisites, once per
    entity per frame) wrote 60 KB a second and cost real frame time, so text
    is gathered into whole tracebacks and a repeat is only counted: the first
    REPEAT_SHOWN copies are written, then one line at 10, 100, 1000... repeats.
    The game's own stderr gets the same treatment."""

    REPEAT_SHOWN = 3
    PENDING_LIMIT = 400             # lines; a traceback that never ends is written anyway

    def __init__(self, stream, path):
        self._stream = stream
        self._path = path
        self._file = None
        self._pending = []
        self._seen = {}

    def write(self, text):
        if not text:
            return
        self._pending.append(text)
        if not text.endswith('\n'):
            return
        block = ''.join(self._pending)
        lines = block.splitlines()
        if lines and lines[0].startswith('Traceback') and len(lines) < self.PENDING_LIMIT:
            last = lines[-1]
            if not last or last[0] in ' \t' or last.startswith('Traceback'):
                return              # the traceback is still being printed
        self._pending = []
        self._emit(block)

    def _emit(self, block):
        if not block.lstrip().startswith('Traceback'):
            self._out(block)
            return
        if len(self._seen) > 5000:
            self._seen.clear()      # distinct tracebacks only; never grows without end
        count = self._seen.get(block, 0) + 1
        self._seen[block] = count
        if count <= self.REPEAT_SHOWN:
            self._out(block)
            return
        if len(str(count)) > len(str(count - 1)):            # 10, 100, 1000...
            last = block.rstrip().splitlines()[-1]
            self._out('[repeated %d times] %s\n' % (count, last))

    def _out(self, text):
        try:
            if self._stream is not None:
                self._stream.write(text)
        except Exception:
            pass
        try:
            if self._file is None:
                self._file = open(self._path, 'a')
            self._file.write(text)
            self._file.flush()
        except Exception:
            self._file = None

    def flush(self):
        try:
            if self._stream is not None:
                self._stream.flush()
        except Exception:
            pass

    def close_file(self):
        if self._file is not None:
            try:
                self._file.close()
            except Exception:
                pass
            self._file = None

    _rl_error_tee = True

    def __getattr__(self, name):
        return getattr(self._stream, name)


# --------------------------------------------------------------------------
# Frame rate
# --------------------------------------------------------------------------

# GraphicsManager methods that set the game's own cap (game3d.set_frame_rate):
# run on settings load, on a graphics change and on map loads.
FRAME_RATE_SETTERS = ('_updateFrameRate', 'setPcFrameRateWithDefault')


def apply_frame_rate():
    """game3d.set_frame_rate(MAX_FPS): the cap is the game's logic frame rate
    (render runs far above it) - 30 in "Normal" mode, which is where the
    frame rate sat in the lobby and the battleground."""
    if MAX_FPS <= 0:
        return False
    try:
        import game3d
        game3d.set_frame_rate(MAX_FPS)
    except Exception:
        log_error('local-frame-rate-error', fps=MAX_FPS)
        return False
    return True


def make_frame_rate_setter(fps, importer=__import__):
    def apply(_fps=fps, _import=importer):
        try:
            _import('game3d').set_frame_rate(_fps)
            return True
        except Exception:
            return False
    return apply


def _keeping_frame_rate(original, name):
    def keep(self, *args, **kwargs):
        try:
            return original(self, *args, **kwargs)
        finally:
            setter = getattr(type(self), '_rl_frame_rate_apply', None)
            if callable(setter):
                setter()
    keep.__name__ = name
    return keep


def unlock_frame_rate():
    """Apply MAX_FPS, and keep it: the game's own setters put its cap back,
    so each one is followed by ours."""
    if MAX_FPS <= 0:
        return False
    applied = apply_frame_rate()
    try:
        import Globals
        manager = getattr(Globals, 'graphicsMgr', None)
    except Exception:
        manager = None
    cls = type(manager) if manager is not None else None
    wrapped = []
    if cls is not None:
        try:
            cls._rl_frame_rate_apply = staticmethod(make_frame_rate_setter(MAX_FPS))
        except Exception:
            pass
    if cls is not None and not cls.__dict__.get('_rl_frame_rate_kept'):
        for name in FRAME_RATE_SETTERS:
            original = getattr(cls, name, None)
            if not callable(original):
                continue
            try:
                setattr(cls, name, _keeping_frame_rate(original, name))
                wrapped.append(name)
            except Exception:
                pass
        if wrapped:
            cls._rl_frame_rate_kept = True
    if applied and (wrapped or not _frame_rate['logged']):
        _frame_rate['logged'] = True
        log('local-frame-rate', fps=MAX_FPS, kept=wrapped)
    return applied


_frame_rate = {'logged': False}


# --------------------------------------------------------------------------
# Settings files (Documents/graphics_settings.txt, basic_settings.txt)
# --------------------------------------------------------------------------
# The game reads them once at start and writes all of them back every time it
# applies settings (each map load: login, lobby, battle, the way back).  Two
# game windows share one Documents folder: the window whose settings were not
# touched wrote its old values over the ones just chosen in the other - after
# a restart they were "reset".  And Settings.__init__ puts the graphics
# manager on its defaults (resetDefaultSettings) after the manager had read
# the file.  Here a write that changes nothing this window knows of, over a
# file another window changed since, is dropped - and this window takes the
# newer settings instead; and the defaults at init leave graphics alone.

SETTINGS_FILES = ('graphics_settings.txt', 'basic_settings.txt')
SETTINGS_MODULES = ('helpers.graphic_settings', 'helpers.settings')
GRAPHICS_FIELDS = (('GRAPHIC_LEVEL', '_qualityLevel'), ('FRAME_RATE_LEVEL', '_frameRateMode'),
                   ('AOI_8K_LEVEL', '_aoi8KLevel'), ('CSM_LEVEL', '_csmLevel'), ('RESOLUTION', '_resolution'),
                   ('IS_MSAA_ON', '_isMsaaOn'), ('USE_NEXT_GEN_BAKE', '_useNextGenBake'))
_settings_seen = {}             # file name -> what this window last read or wrote there
try:
    _real_open = open
except NameError:
    _real_open = None


def _read_text(path, opener=None):
    try:
        handle = (opener or _real_open)(path, 'r')
        try:
            return handle.read()
        finally:
            handle.close()
    except Exception:
        return None


class SettingsWrite(object):
    """open(path, 'w') of a settings file: the text is kept until close(),
    then written - or not (settle_settings_write)."""

    def __init__(self, path):
        self.path = path
        self.parts = []
        self.closed = False

    def write(self, text):
        self.parts.append(text)

    def flush(self):
        pass

    def close(self):
        if not self.closed:
            self.closed = True
            settle_settings_write(self.path, ''.join(self.parts))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()
        return False


def settings_open(path, mode='r', *args):
    name = os.path.basename(str(path))
    if name not in SETTINGS_FILES:
        return _real_open(path, mode, *args)
    if 'w' in mode:
        return SettingsWrite(path)
    handle = _real_open(path, mode, *args)
    try:
        text = handle.read()
    finally:
        handle.close()
    _settings_seen[name] = text
    try:
        from cStringIO import StringIO
    except ImportError:
        from io import StringIO
    return StringIO(text)


def settle_settings_write(path, text, opener=None, later=None):
    name = os.path.basename(str(path))
    seen = _settings_seen.get(name)
    disk = _read_text(path, opener)
    if seen is not None and text == seen and disk is not None and disk != seen:
        # nothing changed here; another window saved newer settings: keep
        # them, and use them here too
        _settings_seen[name] = disk
        (later or call_later)(0.0, adopt_settings_file, name)
        log('local-settings-kept', file=name)
        return False
    handle = (opener or _real_open)(path, 'w')
    try:
        handle.write(text)
    finally:
        handle.close()
    if seen is not None and text != seen:
        log('local-settings-saved', file=name)
    _settings_seen[name] = text
    return True


def adopt_settings_file(name):
    """Take the settings another window saved (and apply them here)."""
    try:
        import Globals
    except Exception:
        return False
    try:
        if name == 'graphics_settings.txt':
            manager = getattr(Globals, 'graphicsMgr', None)
            data = json.loads(_settings_seen.get(name) or '{}')
            if manager is None or not isinstance(data, dict):
                return False
            for key, field in GRAPHICS_FIELDS:
                if key in data:
                    setattr(manager, field, data[key])
            manager.applySettings()
        elif name == 'basic_settings.txt':
            settings = getattr(Globals, 'settings', None)
            if settings is None:
                return False
            settings.loadBasicSettings()
        return True
    except Exception:
        log_error('local-settings-adopt-error', file=name)
        return False


def graphics_snapshot(manager):
    return dict((field, getattr(manager, field)) for _key, field in GRAPHICS_FIELDS if hasattr(manager, field))


def keeping_graphics(original):
    """Settings.resetDefaultSettings from Settings.__init__ put the graphics
    manager - which had read the player's file already - on the defaults,
    and the next map load saved them.  Only the Reset button resets them."""
    def resetDefaultSettings(self, *args, **kwargs):
        keep = None
        try:
            if sys._getframe(1).f_code.co_name == '__init__':
                import Globals
                manager = getattr(Globals, 'graphicsMgr', None)
                keep = (manager, graphics_snapshot(manager)) if manager is not None else None
        except Exception:
            keep = None
        try:
            return original(self, *args, **kwargs)
        finally:
            if keep is not None:
                for field, value in keep[1].items():
                    try:
                        setattr(keep[0], field, value)
                    except Exception:
                        pass
    resetDefaultSettings._rl_keeps_graphics = True
    return resetDefaultSettings


def guard_settings_files():
    """Install the file guard in the game's settings modules (and keep the
    graphics through Settings' own init).  Safe to call again."""
    guarded = []
    for name in SETTINGS_MODULES:
        # Never imported here: at the hook's start the game has not loaded
        # them yet, and loading helpers.settings that early stopped the game
        # from getting past its start.  Guarded once the lobby is up.
        module = sys.modules.get(name)
        if module is None:
            continue
        if getattr(module, 'open', None) is not settings_open:
            try:
                module.open = settings_open
                guarded.append(name)
            except Exception:
                log_error('local-settings-guard-error', module=name)
    cls = getattr(sys.modules.get('helpers.settings'), 'Settings', None)
    original = getattr(cls, 'resetDefaultSettings', None) if cls is not None else None
    if original is not None and not getattr(original, '_rl_keeps_graphics', False):
        try:
            cls.resetDefaultSettings = keeping_graphics(original)
            guarded.append('resetDefaultSettings')
        except Exception:
            log_error('local-settings-reset-guard-error')
    if guarded:
        remember_settings_files()
        log('local-settings-guarded', parts=guarded)
    return guarded


def remember_settings_files():
    """What the files hold as this window starts guarding them (it read
    them at its start, before the guard)."""
    try:
        from libclaudia.Settings.CanvasManager import Application
        folder = Application.persistentDataPath
    except Exception:
        return False
    for name in SETTINGS_FILES:
        if name not in _settings_seen:
            text = _read_text(os.path.join(folder, name))
            if text is not None:
                _settings_seen[name] = text
    return True


def make_server_clock(start, origin, clock=time.time):
    state = {'start': float(start), 'origin': float(origin)}

    def server_time(_state=state, _clock=clock):
        return _state['start'] + _clock() - _state['origin']

    server_time._rl_real_clock = True
    server_time._rl_state = state
    return server_time


OFFLINE_SERVER_TIME = 1.0


def use_real_server_clock():
    current = getattr(BigWorld, 'serverTime', None)
    state = getattr(current, '_rl_state', None)
    replaced = isinstance(state, dict)
    start = OFFLINE_SERVER_TIME
    if replaced:
        try:
            start = state['start'] + time.time() - state['origin']
        except Exception:
            start = OFFLINE_SERVER_TIME
    try:
        if not replaced:
            BigWorld._rl_engine_server_time = current
        BigWorld.serverTime = make_server_clock(start, time.time())
    except Exception:
        log_error('local-server-clock-error')
        return False
    log('local-server-clock', start=round(start, 3), replaced=replaced)
    return True


ERRORS_LOG_LIMIT = 10 * 1024 * 1024


def rotate_error_log(path, limit=ERRORS_LOG_LIMIT):
    """Start a fresh log once it is past the limit, keeping one old copy."""
    try:
        if os.path.getsize(path) <= limit:
            return False
        old = path + '.old'
        if os.path.exists(old):
            os.remove(old)
        os.rename(path, old)
        return True
    except Exception:
        return False


def capture_game_errors():
    if not ERRORS_PATH or isinstance(sys.stderr, _ErrorTee):
        return
    stream = sys.stderr
    if getattr(stream, '_rl_error_tee', False):
        try:
            stream = object.__getattribute__(stream, '_stream')
        except Exception:
            pass
    rotate_error_log(ERRORS_PATH)
    sys.stderr = _ErrorTee(stream, ERRORS_PATH)
    try:
        with open(ERRORS_PATH, 'a') as output_file:
            output_file.write('\n==== DieHard ROS session %s ====\n' % time.strftime('%Y-%m-%d %H:%M:%S'))
    except Exception:
        pass
    log('local-error-capture-installed', path=ERRORS_PATH)


# --------------------------------------------------------------------------
# Offline tips
# --------------------------------------------------------------------------

_tip = {'function': None, 'searched': False, 'last': 0.0, 'candidates': []}
TIP_NAME = re.compile(r'^(show|add|pop|push)_?\w*(tip|toast)s?$', re.I)


def _find_tip_function():
    if _tip['searched']:
        return _tip['candidates']
    _tip['searched'] = True
    candidates = []
    for module_name in ('client_utils', 'ui.UITips', 'ui.UIMsgTip', 'ui.UITip'):
        try:
            module = __import__(module_name, fromlist=['*'])
        except Exception:
            continue
        for name in dir(module):
            if TIP_NAME.match(name) and callable(getattr(module, name, None)):
                candidates.append((module_name, name, getattr(module, name)))
    try:
        import Globals
        for name in dir(Globals.uiMgr):
            if TIP_NAME.match(name):
                candidates.append(('Globals.uiMgr', name, getattr(Globals.uiMgr, name)))
    except Exception:
        pass
    log('local-tip-candidates', names=['%s.%s' % (module, name) for module, name, _ in candidates])
    _tip['candidates'] = candidates
    return candidates


def show_offline_tip(text, force=False):
    now = time.time()
    if not force and now - _tip['last'] < 2.0:
        return
    _tip['last'] = now
    candidates = _find_tip_function()
    if _tip['function'] is not None:
        candidates = [(None, _tip.get('name'), _tip['function'])]
    shown = None
    for module, name, function in candidates:
        try:
            function(text)
        except Exception:
            debug('local-tip-error', function='%s.%s' % (module, name), error=traceback.format_exc())
            continue
        _tip['function'] = function
        _tip['name'] = '%s.%s' % (module, name)
        shown = _tip['name']
        break
    log('local-offline-tip', text=text, shown_with=shown)


# --------------------------------------------------------------------------
# Local server mailbox (replaces player.base in the lobby)
# --------------------------------------------------------------------------

QUERY_PREFIXES = ('get', 'query', 'request', 'req', 'ask', 'fetch', 'load', 'refresh',
                  'check', 'sync', 'report', 'upload', 'log', 'record', 'notify', 'handshake',
                  'heartbeat', 'ping', 'update', 'save', 'set', 'mark', 'clear', 'read')
REQUEST_PREFIXES = ('request', 'req', 'ask', 'try', 'do', 'client')
MATCH_WORDS = re.compile(r'(match|battle|queue|startgame|enterroom|ready)', re.I)
MATCH_ACTIONS = re.compile(r'(start|begin|sign|apply|join|enter|ready|confirm)', re.I)
# The match calls the backend answers (backend_server/battle_rpc.py): no reply
# means it was lost on the way, not that the call is unsupported.
BACKEND_MATCH_CALLS = frozenset(['getReadyForBattleGround', 'notReadyForBattleGround',
                                 'cancelMatchBattleGround'])
MATCH_NO_ANSWER = 'The server did not answer - press START again.'
# Calls that only fed NetEase's analytics and anti-cheat: the online server
# stored or compared the values and never answered.  handle_rpc drops them
# first: no backend packet, no smart reply, no log line (a battle sends
# several a second: FPS, verify..., trajectories).
QUIET_RPCS = frozenset([
    'verifyClientValue', 'verifyClientWeaponValue', 'verifyClientConstantValue',
    'verifyRC2ClientValue', 'verifyRC4ClientValue', 'verifyCurrentWeaponProperty',
    'verifyClientGameValue', 'verifyClientWeaponMechanical', 'veriftClientRawinputMessage',
    'veriftClientProcessNum', 'checkAnticheatValue', 'notifyGodObserverDrawTrajectory',
    'requestFileList', 'onRecvClientFPS', 'onRecvClientFrameLevel', 'uploadGameNpkVersionInfo',
    'sSyncSettingDataToServer', 'recordTalkTime', 'cleanRedBadge', 'delRedHint',
    'onNewPlayerTaskMsg'])
# saLogX / doSALogX analytics, logX / clientLogX reports - never the session
# calls (saLogin, logOut, logOn...): the backend BOOKKEEPING rule.  Spelled
# case by case: Python 2.7 has no scoped (?-i:) flags.
_SESSION_TAIL = r'(?!(?:[iI]n|[oO]ut|[oO]ff|[oO]n)(?:[A-Z_0-9]|$))'
QUIET_RPC = re.compile(r'^(?:[dD]o)?[sS][aA]_?[lL]og' + _SESSION_TAIL +
                       r'|^(?:[cC]lient)?[lL]og' + _SESSION_TAIL + r'[A-Z]')
_quiet_seen = {}
NO_ECHO =re.compile(r'(enterhall|leavehall|logout|logoff|destroy|quit|exit|become|disconnect|'
                     r'reconnect|kick|delete|remove|pay|buy|recharge)', re.I)
_rpc_seen = {}
_rpc_active = set()
_lobby_ready = {'value': False, 'at': 0.0}


def _cap(text):
    return text[:1].upper() + text[1:]


def is_quiet_rpc(name):
    if name in RPC_HANDLERS:            # a real handler (battle hook, hot patch) wins
        return False
    quiet = _quiet_seen.get(name)
    if quiet is None:
        quiet = _quiet_seen[name] = name in QUIET_RPCS or bool(QUIET_RPC.match(name))
    return quiet


def _echo_candidates(name):
    stripped = name
    for prefix in REQUEST_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix) and name[len(prefix)].isupper():
            stripped = name[len(prefix):]
            break
    rest = _cap(stripped)
    candidates = ['on' + rest, 'on' + rest + 'Result', 'on' + rest + 'Callback',
                  name + 'Callback', name + 'CB', name + 'Result', 'on' + _cap(name)]
    if stripped != name:
        candidates.append(stripped[:1].lower() + stripped[1:])
    for verb in ('change', 'set', 'update', 'modify', 'switch'):
        if stripped.lower().startswith(verb):
            tail = stripped[len(verb):]
            candidates.extend(['sync' + tail, 'on' + tail + 'Changed', 'onUpdate' + tail,
                               'onSync' + tail, 'update' + tail])
            break
    core = _reply_core(name)
    if core != stripped:
        rest = _cap(core)
        low = core[:1].lower() + core[1:]
        candidates.extend(['on' + rest, 'on' + rest + 'Result', 'on' + rest + 'Callback',
                           'on' + rest + 'CB', low + 'CB', low + 'Callback', low + 'Result'])
    seen = []
    for candidate in candidates:
        if candidate != name and candidate not in seen:
            seen.append(candidate)
    return seen


# Extra prefixes stripped only to find reply callbacks (requireBaseInfo ->
# onBaseInfo, baseInfoCB...); REQUEST_PREFIXES keeps its old meaning.
REPLY_STRIP_PREFIXES = ('require', 'request', 'query', 'get', 'set', 'check',
                        'req', 'ask', 'try', 'do', 'client')


def _reply_core(name):
    """requireBaseInfo -> BaseInfo (the part a reply callback is named after)."""
    for prefix in REPLY_STRIP_PREFIXES:
        if name.startswith(prefix) and len(name) > len(prefix) and name[len(prefix)].isupper():
            return name[len(prefix):]
    return name


RPC_HANDLERS = {}


def rpc_handler(*names):
    def register(function):
        for name in names:
            RPC_HANDLERS[name] = function
        return function
    return register


# --------------------------------------------------------------------------
# Client-data replies: store goods / supply boxes come from the game's own
# tables.  The reply format is picked by testing candidates against the
# game's filter functions (mallFilter, generalSupplementFilter...) first.
# --------------------------------------------------------------------------

TABLE_WORDS = {
    'mall': re.compile(r'mall|goods|shop|store', re.I),
    'supplement': re.compile(r'supplement|supply|box', re.I),
}
FEATURE_FILTERS = {
    'mall': ('onQueryAvailableMallGoods', 'mallFilter'),
    'supplement': ('onQueryAvailableSupplement', 'generalSupplementFilter'),
}
VALUE_SHAPES = (
    ('entry', lambda key, entry: entry),
    ('empty-dict', lambda key, entry: {}),
    ('one', lambda key, entry: 1),
    ('true', lambda key, entry: True),
    ('none', lambda key, entry: None),
    ('zero-pair', lambda key, entry: (0, 0)),
)
_feature_data = {}


def _int_keyed_dict(value, minimum=5):
    """A game data table: a mapping (dict or the game's TableItemDict) keyed by ids."""
    if isinstance(value, (type, types.ModuleType)) or isinstance(value, string_types):
        return False
    try:
        if not callable(getattr(value, 'items', None)) or len(value) < minimum:
            return False
        keys = list(itertools.islice(iter(value), 5))   # no full key list (py2 .keys())
    except Exception:
        return False
    for key in keys:
        if isinstance(key, bool) or not isinstance(key, (int, long_type)):
            return False
    return True


def _function_code(function):
    function = getattr(function, 'im_func', function)
    return getattr(function, 'func_code', None) or getattr(function, '__code__', None)


def _function_globals(function):
    function = getattr(function, 'im_func', function)
    return getattr(function, 'func_globals', None) or getattr(function, '__globals__', None) or {}


def _code_names(function):
    code = _function_code(function)
    names = []
    if code is None:
        return names
    for nested in _code_objects(getattr(function, 'im_func', function)):
        for name in nested.co_names:
            if name not in names:
                names.append(name)
    return names


def _called_functions(function):
    """Functions a function reaches through its globals: f(), mod.f(), obj.f()."""
    namespace = _function_globals(function)
    names = _code_names(function)
    found = []
    for owner_name in names:
        owner = namespace.get(owner_name)
        if owner is None:
            continue
        if _function_code(owner) is not None:
            found.append((owner_name, owner))
            continue
        for attr in names:
            if attr == owner_name:
                continue
            try:
                candidate = getattr(owner, attr, None)
            except Exception:
                continue
            if candidate is not None and _function_code(candidate) is not None:
                found.append(('%s.%s' % (owner_name, attr), candidate))
    return found


def _tables_named_by(function, label):
    """Id-keyed tables a function reads from its globals (x or x.y)."""
    found = []
    namespace = _function_globals(function)
    names = _code_names(function)
    for name in names:
        value = namespace.get(name)
        if value is None or _function_code(value) is not None:
            continue
        if _int_keyed_dict(value):
            found.append(('%s -> %s' % (label, name), value))
            continue
        for attr in names:
            try:
                sub_value = getattr(value, attr, None)
            except Exception:
                continue
            if sub_value is not None and _int_keyed_dict(sub_value):
                found.append(('%s -> %s.%s' % (label, name, attr), sub_value))
    return found


def accessor_tables(filter_function, depth=3):
    """Tables behind the accessors a feature filter calls.

    mallFilter((goodId, value)) calls properties.getMallData(goodId), whose
    table is the store's goods table; generalSupplementFilter calls
    supplement_utils.getSupplementKind, which calls a data accessor in turn.
    Accessors are followed up to ``depth`` calls deep."""
    found, accessors = [], []
    if filter_function is None:
        return found, accessors
    seen = set()
    frontier = [('filter', filter_function)]
    for _level in range(depth):
        next_frontier = []
        for label, function in frontier:
            for sub_label, sub_function in _called_functions(function):
                code = _function_code(sub_function)
                if code is None or id(code) in seen:
                    continue
                seen.add(id(code))
                accessors.append((sub_label, sub_function))
                found.extend(_tables_named_by(sub_function, sub_label))
                next_frontier.append((sub_label, sub_function))
        frontier = next_frontier
    return found, [(label, callback_signature(function)) for label, function in accessors[:40]]


def all_id_tables(limit=600):
    """Every id-keyed table in loaded modules (last resort, no name filter)."""
    found = []
    for module_name, module in list(sys.modules.items()):
        if module is None:
            continue
        try:
            items = list(vars(module).items())
        except Exception:
            continue
        for attr, value in items:
            if _int_keyed_dict(value, minimum=20):
                found.append(('%s.%s' % (module_name, attr), value))
    found.sort(key=lambda item: -len(item[1]))
    return found[:limit]


def _unique_tables(found):
    unique, seen = [], set()
    for name, table in found:
        if id(table) not in seen:
            seen.add(id(table))
            unique.append((name, table))
    return unique


def candidate_tables(feature):
    words = TABLE_WORDS[feature]
    found = []
    for module_name, module in list(sys.modules.items()):
        if module is None:
            continue
        try:
            items = list(vars(module).items())
        except Exception:
            continue
        for attr, value in items:
            if not words.search(module_name + '.' + attr):
                continue
            if _int_keyed_dict(value):
                found.append(('%s.%s' % (module_name, attr), value))
            elif hasattr(value, '__dict__') and not isinstance(value, type):
                # data holder objects such as mall_data.data
                for sub_attr, sub_value in list(getattr(value, '__dict__', {}).items())[:50]:
                    if _int_keyed_dict(sub_value):
                        found.append(('%s.%s.%s' % (module_name, attr, sub_attr), sub_value))
    unique = _unique_tables(found)
    unique.sort(key=lambda item: -len(item[1]))
    return unique[:25]


def feature_filter(player, feature):
    callback_name, filter_name = FEATURE_FILTERS[feature]
    callback = getattr(type(player), callback_name, None)
    function = getattr(callback, '_rl_original', None) or getattr(callback, 'im_func', callback)
    namespace = getattr(function, 'func_globals', None) or getattr(function, '__globals__', {})
    return namespace.get(filter_name)


def _score_table(filter_function, table, report, table_name, sample_size=60):
    """Best (passed, shape_name, shape) of a table against the feature filter."""
    try:
        pairs = table.iteritems() if hasattr(table, 'iteritems') else iter(table.items())
        sample = list(itertools.islice(pairs, sample_size))
    except Exception:
        return None
    best = None
    for shape_name, shape in VALUE_SHAPES:
        passed = failed = 0
        for key, entry in sample:
            try:
                if filter_function is None or filter_function((key, shape(key, entry))):
                    passed += 1
            except Exception:
                failed += 1
        if report is not None:
            report.append({'table': table_name, 'size': len(table), 'shape': shape_name,
                           'passed': passed, 'failed': failed,
                           'sample': safe(sample[0], 300) if sample else None})
        # Tables mixing hidden goods raise for some ids; accept a clear
        # majority, and never a table where only one or two ids fit.
        if passed >= min(3, len(sample)) and failed <= passed // 4 and \
                (best is None or passed > best[0]):
            best = (passed, shape_name, shape)
    return best


def resolve_feature_data(player, feature):
    """Return (table_name, shape_name, dict) for a query reply, cached.

    Candidates, in order: tables behind the accessors the game's own filter
    calls, tables whose names mention the feature, then every id-keyed table
    in memory.  The one whose ids pass the filter best wins."""
    if feature in _feature_data:
        return _feature_data[feature]
    filter_function = feature_filter(player, feature)
    report = {'filter': callback_signature(filter_function) if filter_function else None,
              'candidates': [], 'accessors': []}
    via_accessor, report['accessors'] = accessor_tables(filter_function)
    stages = (('accessor', lambda: via_accessor), ('name', lambda: candidate_tables(feature)))
    if filter_function is not None:
        # Without the game's filter every table would "pass": never guess from a full scan.
        stages += (('scan', all_id_tables),)
    deadline = time.time() + 1.5   # this runs on the game thread
    best = None
    tried = set()
    for stage, tables in stages:
        for table_name, table in _unique_tables(tables()):
            if stage == 'scan' and time.time() > deadline:
                log('local-feature-scan-budget', feature=feature, tried=len(tried))
                break
            if id(table) in tried:
                continue
            tried.add(id(table))
            detail = report['candidates'] if stage != 'scan' or len(report['candidates']) < 400 else None
            scored = _score_table(filter_function, table, detail, table_name,
                                  sample_size=60 if stage != 'scan' else 20)
            if scored and (best is None or scored[0] > best[0]):
                best = (scored[0], table_name, scored[1], table, scored[2], stage)
        if best is not None:
            break
    _catalog.setdefault('feature_data', {})[feature] = report
    write_rpc_catalog()
    if best is None:
        _feature_data[feature] = None
        log('local-feature-data-missing', feature=feature, candidates=len(report['candidates']),
            accessors=[label for label, _signature in report['accessors']])
        return None
    _, table_name, shape_name, table, shape, stage = best
    data = {}
    for key, entry in table.items():
        try:
            value = shape(key, entry)
            if filter_function is None or filter_function((key, value)):
                data[key] = value
        except Exception:
            continue
    _feature_data[feature] = (table_name, shape_name, data)
    log('local-feature-data', feature=feature, table=table_name, shape=shape_name, size=len(data),
        found_by=stage)
    return _feature_data[feature]


def _reply_with_feature_data(player, feature, callback_name, build_args):
    resolved = resolve_feature_data(player, feature)
    data = resolved[2] if resolved else {}
    callback = getattr(player, callback_name, None)
    if not callable(callback):
        return
    try:
        callback(*build_args(data))
        log('local-client-data-reply', callback=callback_name, size=len(data))
    except Exception:
        log_error('local-client-data-reply-error', callback=callback_name)


# --------------------------------------------------------------------------
# DEPOT: wearing / trying on appearances.  The game's shared
# dts_appearance.DtsAppearance has the server rules for every appearance
# type (equipAppearanceRequestServer...); they run here on a host made of the
# lobby player, and their host.update<Prop>() pushes reach the player's
# onUpdate<Prop> callbacks as the server's did.
# --------------------------------------------------------------------------

EQUIPPED_APPEARANCE_PROPS = (
    'dtsBodyAppearanceList', 'dtsWearableAppearanceList', 'dtsWeaponAppearanceList',
    'dtsFlyingAccessoryList', 'dtsDyeingAppearanceList', 'dtsBattlegroundPropAppearanceList',
    'dtsVehicleAppearanceList', 'dtsPetAppearance', 'dtsTagAppearanceList', 'dtsHallThemeID',
    'dtsPaintAppearanceIDs', 'dtsJetWingsAppearanceID', 'dtsNameplateAppearance',
    'dtsPlayerSfxAppearanceIDs', 'dtsShowAircraftAppearanceID', 'dtsVehiclePlateNumberAppearanceID',
    'dtsPendantAppearanceList', 'dtsHallVehicleAppearanceList', 'dtsOutGameWeapon',
    'dtsOutGameWeaponPos', 'dtsOutGameBag', 'dtsOutGameWeaponMale', 'dtsOutGameWeaponPosMale',
    'dtsOutGameWeaponFemale', 'dtsOutGameWeaponPosFemale', 'dtsInGameActionAppearanceIDs',
    'dtsInGameActionSuitAppearanceIDs')
# What the lobby character shows: the equipped list plus try-ons.
SHOWN_APPEARANCE_PROPS = {
    'dtsShowBodyAppearanceList': 'dtsBodyAppearanceList',
    'dtsShowWearableAppearanceList': 'dtsWearableAppearanceList',
    'dtsShowWeaponAppearanceList': 'dtsWeaponAppearanceList',
    'dtsShowFlyingAccessoryList': 'dtsFlyingAccessoryList',
    'dtsShowDyeingAppearanceList': 'dtsDyeingAppearanceList',
    'dtsShowBattlegroundPropAppearanceList': 'dtsBattlegroundPropAppearanceList',
    'dtsShowVehicleAppearanceList': 'dtsVehicleAppearanceList',
    'dtsShowTagAppearanceList': 'dtsTagAppearanceList',
    'dtsShowPendantList': 'dtsPendantAppearanceList',
}
APPEARANCE_STATE_KEY = 'appearance'


def stored_appearance():
    try:
        stored = load_state().get('lobby', {}).get(APPEARANCE_STATE_KEY)
    except Exception:
        stored = None
    return stored if isinstance(stored, dict) else {}


def id_list(value):
    """An appearance list prop as a plain list of ids (the entity's lists are
    the engine's own list type), None when the prop is a single id."""
    if value is None or isinstance(value, (bool, int, long_type)) or isinstance(value, string_types):
        return None
    try:
        return [int(item) for item in value if isinstance(item, (int, long_type)) and not isinstance(item, bool)]
    except TypeError:
        return None


def player_value(player, prop):
    """A replicated prop: some (dtsHallThemeID) are entity properties that
    never show up in the instance __dict__."""
    value = player.__dict__.get(prop)
    if value is None:
        try:
            value = getattr(player, prop, None)
        except Exception:
            value = None
    return value


def save_appearance(player):
    """The equipped appearances, kept for the next login (try-ons are not)."""
    kept = {}
    for prop in EQUIPPED_APPEARANCE_PROPS:
        value = player_value(player, prop)
        items = id_list(value)
        if items is not None:
            kept[prop] = items
        elif isinstance(value, (int, long_type)) and not isinstance(value, bool):
            kept[prop] = int(value)
    outfits = player.__dict__.get(GENDER_OUTFITS_ATTR)
    if outfits:
        kept[GENDER_OUTFITS_KEY] = outfits
    try:
        save_state_durable(lobby={APPEARANCE_STATE_KEY: kept})
    except Exception:
        log_error('local-appearance-save-error')
    return kept


def apply_stored_appearance(player):
    """Login: what was worn last time, shown as worn (no try-ons)."""
    stored = stored_appearance()
    for prop, value in stored.items():
        if prop in EQUIPPED_APPEARANCE_PROPS:
            try:
                setattr(player, prop, list(value) if isinstance(value, list) else value)
            except Exception:
                pass
    if isinstance(stored.get(GENDER_OUTFITS_KEY), dict):
        setattr(player, GENDER_OUTFITS_ATTR, dict(stored[GENDER_OUTFITS_KEY]))
    gender = int_arg(player.__dict__.get('dtsAppearanceGender'))
    if gender:
        for prop in GENDERED_OUTFIT_PROPS:
            items = id_list(player.__dict__.get(prop))
            if items is not None:
                setattr(player, prop, [item for item in items if fits_gender(item, gender)])
    for shown, equipped in SHOWN_APPEARANCE_PROPS.items():
        items = id_list(player.__dict__.get(equipped))
        if items is not None:
            try:
                setattr(player, shown, items)
            except Exception:
                pass
    return stored


def prop_callback_name(prop):
    return 'onUpdate' + prop[0].upper() + prop[1:]


class LocalAppearanceHost(object):
    """``self.host`` of the shared DtsAppearance server rules: the lobby
    player's data, its client callbacks, and the server's push helpers."""

    def __init__(self, player):
        object.__setattr__(self, '_rl_player', player)
        object.__setattr__(self, '_rl_pushed', [])

    def __getattr__(self, name):
        player = object.__getattribute__(self, '_rl_player')
        if name == 'client':
            return player
        if name.startswith('update') and name[6:7].isupper():
            prop = name[6].lower() + name[7:]
            return lambda *args: self._rl_push(prop)
        if name.startswith('notify') and name[6:7].isupper():
            callback = getattr(player, 'onNotify' + name[6:], None)
            return callback if callable(callback) else (lambda *args: None)
        if name == 'systemJumpTip':
            return appearance_tip
        if name in HOST_REQUESTS:
            # A new skin for the gun / backpack shown in the lobby takes that
            # one off first (host.setOutGameWeapon(0, 0, 0)).
            return lambda *args: RPC_HANDLERS[HOST_REQUESTS[name]](player, *args)
        return getattr(player, name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, '_rl_player'), name, value)

    def _rl_push(self, prop):
        player = object.__getattribute__(self, '_rl_player')
        callback = getattr(player, prop_callback_name(prop), None)
        value = player_value(player, prop)
        if callable(callback) and value is not None:
            callback(value)
        object.__getattribute__(self, '_rl_pushed').append(prop)


# Server methods the shared appearance rules call on their host.  A tag
# appearance (a VIP medallion) sets the badge shown by the name: the
# equip failed on host.setIdentifyTag before.
HOST_REQUESTS = {'setOutGameWeapon': 'setOutGameWeapon', 'setOutGameBag': 'setOutGameBag',
                 'setIdentifyTag': 'setIdentifyTag', 'unsetIdentifyTag': 'unsetIdentifyTag'}


def show_identify_tag(player, tag):
    """Your badge now (iIdentifyTag.setIdentifyTagID refreshes the lobby name
    and team slot), and on the backend for everyone else's cards."""
    try:
        tag = int(tag or 0)
    except (TypeError, ValueError):
        tag = 0
    setter = getattr(player, 'setIdentifyTagID', None)
    try:
        if callable(setter):
            setter(tag)
        else:
            player.identifyTagID = tag
    except Exception:
        log_error('local-identify-tag-error', tag=tag)
        player.__dict__['identifyTagID'] = tag
    save_state_durable(lobby={'identifyTagID': tag})
    # the lobby nameplate draws the team slot's tag (UIMain.onMemberIdentifyTagIDChange)
    sync_team = getattr(player, 'syncHallTeamMemberIdentifyTagID', None)
    try:
        if callable(sync_team):
            sync_team(local_gid(), tag)
    except Exception:
        log_error('local-identify-tag-team-error', tag=tag)
    log('local-identify-tag', tag=tag)
    return tag


def saved_identify_tag(player=None):
    """The badge worn: the player's own (set this session), else the saved one."""
    for value in (getattr(player, 'identifyTagID', None) if player is not None else None,
                  load_state().get('lobby', {}).get('identifyTagID')):
        try:
            if int(value or 0):
                return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def install_meet_edit_fix():
    """UIMeetEdit.canEditGender reads curUser['LastUpdateGenderTime'] (a gender
    change waits 7 days); the profile it gets lacks it, so Edit profile raised
    KeyError and never opened.  0 = never changed: the gender may be edited."""
    try:
        cls = __import__('ui.UIMeetEdit', fromlist=['UIMeetEdit']).UIMeetEdit
    except Exception:
        return False
    original = cls.__dict__.get('canEditGender')
    if original is None or getattr(original, '_rl_gender_time', False):
        return False

    def canEditGender(self, *args, **kwargs):
        user = getattr(self, 'curUser', None)
        if isinstance(user, dict) and 'LastUpdateGenderTime' not in user:
            dict.__setitem__(user, 'LastUpdateGenderTime', 0)
        return original(self, *args, **kwargs)
    canEditGender._rl_gender_time = True
    cls.canEditGender = canEditGender
    return True


def wear_saved_identify_tag(player):
    """The badge you wore last time (backend lobby state), without saving it again."""
    try:
        tag = int(load_state().get('lobby', {}).get('identifyTagID') or 0)
    except Exception:
        tag = 0
    if not tag:
        return 0
    try:
        player.__dict__['identifyTagID'] = tag
    except Exception:
        log_error('local-identify-tag-restore-error', tag=tag)
        return 0
    return tag


@rpc_handler('setIdentifyTag')
def _rpc_set_identify_tag(player, tag=0, *args):
    return show_identify_tag(player, tag)


@rpc_handler('unsetIdentifyTag')
def _rpc_unset_identify_tag(player, *args):
    return show_identify_tag(player, 0)


def appearance_tip(text, *args):
    try:
        import Globals
        Globals.uiMgr.systemJumpTip(text)
    except Exception:
        pass


def appearance_rules(appearance_id, host):
    try:
        module = [m for name, m in list(sys.modules.items())
                  if m is not None and name.endswith('DtsAppearance') and hasattr(m, 'DtsAppearanceProxy')][0]
        return module.DtsAppearanceProxy(host, int(appearance_id))
    except Exception:
        log_error('local-appearance-rules-missing', appearance=safe(appearance_id))
        return None


def run_appearance_request(player, request, appearance_id):
    host = LocalAppearanceHost(player)
    rules = appearance_rules(appearance_id, host)
    if rules is None:
        return False
    try:
        getattr(rules, request)()
    except Exception:
        log_error('local-appearance-request-error', request=request, appearance=safe(appearance_id))
        return False
    pushed = object.__getattribute__(host, '_rl_pushed')
    if any(prop in EQUIPPED_APPEARANCE_PROPS for prop in pushed):
        save_appearance(player)
    log('local-appearance-request', request=request, appearance=safe(appearance_id), pushed=pushed)
    return True


@rpc_handler('equipAppearance')
def _rpc_equip_appearance(player, appearance_id=None, *args):
    run_appearance_request(player, 'equipAppearanceRequestServer', appearance_id)


@rpc_handler('unloadAppearance')
def _rpc_unload_appearance(player, appearance_id=None, *args):
    run_appearance_request(player, 'unloadAppearanceRequestServer', appearance_id)


@rpc_handler('tryOnAppearance')
def _rpc_try_on_appearance(player, appearance_id=None, *args):
    run_appearance_request(player, 'tryOnAppearanceRequestServer', appearance_id)


@rpc_handler('tryOffAppearance')
def _rpc_try_off_appearance(player, appearance_id=None, *args):
    run_appearance_request(player, 'tryOffAppearanceRequestServer', appearance_id)


def suit_pieces(suit_id):
    try:
        utils = __import__('appearance_suit_utils')
        return [int(piece) for piece in utils.getAppearanceSuitElementAppearanceIDs(int(suit_id))]
    except Exception:
        log_error('local-appearance-suit-missing', suit=safe(suit_id))
        return []


def owns_appearance(player, appearance_id):
    try:
        return player.dtsAppearancePackage.getItemCnt(appearance_id) > 0
    except Exception:
        return False


@rpc_handler('putOnAppearanceClothSuit')
def _rpc_put_on_suit(player, suit_id=None, *args):
    """Depot Set: the pieces you own are worn, the others tried on."""
    for piece in suit_pieces(suit_id):
        request = 'equipAppearanceRequestServer' if owns_appearance(player, piece) else 'tryOnAppearanceRequestServer'
        run_appearance_request(player, request, piece)


@rpc_handler('takeOffAppearanceClothSuit')
def _rpc_take_off_suit(player, suit_id=None, *args):
    for piece in suit_pieces(suit_id):
        try:
            worn = player.isAppearanceEquiped(piece)
        except Exception:
            worn = False
        request = 'unloadAppearanceRequestServer' if worn else 'tryOffAppearanceRequestServer'
        run_appearance_request(player, request, piece)


@rpc_handler('cancelTryOnAllRequest')
def _rpc_cancel_try_on(player, *args):
    """Leaving the Depot: the character shows only what is worn again."""
    for shown, equipped in SHOWN_APPEARANCE_PROPS.items():
        worn = id_list(player.__dict__.get(equipped))
        if worn is None or id_list(player.__dict__.get(shown)) == worn:
            continue
        setattr(player, shown, worn)
        callback = getattr(player, prop_callback_name(shown), None)
        if callable(callback):
            try:
                callback(player.__dict__[shown])
            except Exception:
                log_error('local-appearance-cancel-error', prop=shown)



def int_arg(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def gender_suffix(gender):
    return 'Female' if int_arg(gender) == 2 else 'Male'


def wear_out_game_weapon(player, appearance_id, pose):
    """The lobby gun: the server keeps one per gender (dtsOutGameWeaponMale /
    Female) and shows the current gender's (dtsOutGameWeapon)."""
    callback = getattr(player, 'onUpdateOutGameWeapon', None)
    if callable(callback):
        callback(appearance_id, pose)
    else:
        player.dtsOutGameWeapon, player.dtsOutGameWeaponPos = appearance_id, pose


@rpc_handler('setOutGameWeapon')
def _rpc_set_out_game_weapon(player, gun_id=None, appearance_id=None, pose=None, *args):
    """Depot > Firearms "show in lobby" (0, 0, 0 = take it off) and its pose."""
    appearance_id, pose = int_arg(appearance_id), int_arg(pose)
    suffix = gender_suffix(appearance_gender() or player.__dict__.get('dtsAppearanceGender'))
    setattr(player, 'dtsOutGameWeapon' + suffix, appearance_id)
    setattr(player, 'dtsOutGameWeaponPos' + suffix, pose)
    wear_out_game_weapon(player, appearance_id, pose)
    save_appearance(player)
    log('local-appearance-out-game-weapon', gun=safe(gun_id), appearance=appearance_id, pose=pose)


@rpc_handler('setOutGameBag')
def _rpc_set_out_game_bag(player, bag_id=None, *args):
    """Depot > Others "show backpack in lobby" (0 = none)."""
    bag_id = int_arg(bag_id)
    callback = getattr(player, 'onUpdateOutGameBag', None)
    if callable(callback):
        callback(bag_id)
    else:
        player.dtsOutGameBag = bag_id
    save_appearance(player)


def set_hall_vehicles(player, vehicles):
    callback = getattr(player, 'onUpdateHallVehicleAppearanceList', None)
    if callable(callback):
        callback(vehicles)
    else:
        player.dtsHallVehicleAppearanceList = vehicles
    save_appearance(player)


@rpc_handler('setDtsHallVehicleAppearance')
def _rpc_set_hall_vehicle(player, appearance_id=None, *args):
    """Depot > Vehicles "show in lobby": the lobby theme parks this one."""
    appearance_id = int_arg(appearance_id)
    if appearance_id:
        set_hall_vehicles(player, [appearance_id])


@rpc_handler('cancelDtsHallVehicleAppearance')
def _rpc_cancel_hall_vehicle(player, appearance_id=None, *args):
    appearance_id = int_arg(appearance_id)
    shown = id_list(player.__dict__.get('dtsHallVehicleAppearanceList')) or []
    set_hall_vehicles(player, [item for item in shown if item != appearance_id])


def switch_out_game_weapon(player, gender):
    """Switching gender shows that gender's lobby gun (kept apart)."""
    suffix = gender_suffix(gender)
    if 'dtsOutGameWeapon' + suffix not in player.__dict__:
        return
    player.dtsOutGameWeapon = int_arg(player.__dict__.get('dtsOutGameWeapon' + suffix))
    player.dtsOutGameWeaponPos = int_arg(player.__dict__.get('dtsOutGameWeaponPos' + suffix))

# Body, clothes and flying accessories exist per gender (each item's
# PROP_TYPE.GENDER: 1 male, 2 female, 0 both); a female model cannot wear a
# male mesh (AsyncLoader "Add Mesh Error") and came out invisible.  Like the
# lobby gun, each gender keeps its own outfit.
GENDERED_OUTFIT_PROPS = {
    'dtsBodyAppearanceList': 'dtsShowBodyAppearanceList',
    'dtsWearableAppearanceList': 'dtsShowWearableAppearanceList',
    'dtsFlyingAccessoryList': 'dtsShowFlyingAccessoryList',
}
GENDER_OUTFITS_ATTR = '_rlGenderOutfits'
GENDER_OUTFITS_KEY = 'genderOutfits'


def appearance_item_gender(item_id):
    try:
        legacy = __import__('helpers.character_scene', fromlist=['legacyProperties']).legacyProperties
        return int(getattr(legacy.getDtsHallPropData(int(item_id)).PROP_TYPE, 'GENDER', 0) or 0)
    except Exception:
        return 0


def fits_gender(item_id, gender):
    item_gender = appearance_item_gender(item_id)
    return not item_gender or not gender or item_gender == int(gender)


def character_gender(character_type):
    return int(getattr(character_data(character_type), 'GENDER', 0) or 0)


def outfit_for_gender(player, gender):
    """What that gender wears: its kept outfit, else what is worn now that
    fits it."""
    kept = (player.__dict__.get(GENDER_OUTFITS_ATTR) or {}).get(str(gender)) or {}
    outfit = {}
    for prop in GENDERED_OUTFIT_PROPS:
        items = kept[prop] if prop in kept else (id_list(player.__dict__.get(prop)) or [])
        outfit[prop] = [int(item) for item in items if fits_gender(item, gender)]
    return outfit


def wear_outfit(player, outfit):
    for prop, items in outfit.items():
        setattr(player, prop, list(items))
        setattr(player, GENDERED_OUTFIT_PROPS[prop], list(items))


def switch_gender_outfit(player, old_gender, new_gender):
    """Keep what the old gender wore, put on what the new one wore."""
    outfits = dict(player.__dict__.get(GENDER_OUTFITS_ATTR) or {})
    if old_gender:
        outfits[str(old_gender)] = dict((prop, id_list(player.__dict__.get(prop)) or [])
                                        for prop in GENDERED_OUTFIT_PROPS)
    setattr(player, GENDER_OUTFITS_ATTR, outfits)
    wear_outfit(player, outfit_for_gender(player, new_gender))
    save_appearance(player)


def with_outfit(player, outfit, function, *args):
    """Run ``function`` (an off-screen build) with ``outfit`` worn."""
    worn = dict((prop, player.__dict__.get(prop)) for prop in outfit)
    try:
        for prop, items in outfit.items():
            setattr(player, prop, list(items))
        return function(*args)
    finally:
        for prop, items in worn.items():
            if items is not None:
                setattr(player, prop, items)

CHARACTER_TYPE_RANGE = range(10001, 10021)
CODE_SEPARATOR = '\xef\xbc\x9a'          # the full-width colon of NAME ("Code G: ...")


def character_data(character_type):
    try:
        properties = __import__('shared.lib.gametoolslib.properties', fromlist=['getCharactersData'])
        get = getattr(properties, '_rl_original_get_characters_data', properties.getCharactersData)
        return get(int(character_type))
    except Exception:
        return None


def gender_character_type(character_type, gender):
    """The character of the other gender with the same code (10002 male
    "G" <-> 10005 female "G"): what getCharacterType() becomes when the
    Depot switches gender."""
    data = character_data(character_type)
    if data is None or not gender or int(getattr(data, 'GENDER', 0) or 0) == int(gender):
        return character_type
    code = str(getattr(data, 'NAME', '')).split(CODE_SEPARATOR)[0]
    for candidate in CHARACTER_TYPE_RANGE:
        other = character_data(candidate)
        if other is None or int(getattr(other, 'GENDER', 0) or 0) != int(gender):
            continue
        if str(getattr(other, 'NAME', '')).split(CODE_SEPARATOR)[0] == code:
            return candidate
    return character_type


@rpc_handler('setDtsAppearanceGender')
def _rpc_set_appearance_gender(player, gender=None, *args):
    """Depot male / female switch: the server kept the choice, switched the
    character (baseCharacterType) and echoed it; onSetDtsAppearanceGender
    rebuilds the lobby character from getCharacterType()."""
    try:
        gender = int(gender)
    except (TypeError, ValueError):
        return None
    old_gender = int_arg(player.__dict__.get('dtsAppearanceGender') or appearance_gender())
    try:
        save_state_durable(lobby={'dtsAppearanceGender': gender})
    except Exception:
        log_error('local-appearance-gender-save-error')
    try:
        player.baseCharacterType = gender_character_type(player.baseCharacterType, gender)
    except Exception:
        log_error('local-appearance-gender-character-error')
    try:
        switch_out_game_weapon(player, gender)
    except Exception:
        log_error('local-appearance-gender-weapon-error')
    try:
        if old_gender != gender:
            switch_gender_outfit(player, old_gender, gender)
    except Exception:
        log_error('local-appearance-gender-outfit-error')
    callback = getattr(player, 'onSetDtsAppearanceGender', None)
    if callable(callback):
        callback(gender)
    log('local-appearance-gender', gender=gender)
    return None


MALL_FULL_PRICE = 100


def mall_properties(player):
    """The game's data accessor module, as iMall's mallFilter sees it."""
    return _function_globals(feature_filter(player, 'mall')).get('properties')


def mall_field(row, name, default=0):
    try:
        value = getattr(row, name)
    except Exception:
        return default
    return default if value is None else value


def mall_good_value(row, buy_times=0):
    """One good of the server's reply: UIMall reads CURRENCY_ID / PRICE
    (_getMallGoodCurrencyAndPrice), DISCOUNT and BUY_TIMES (fillGoods)."""
    return {'CURRENCY_ID': mall_field(row, 'CURRENCY_ID'), 'PRICE': mall_field(row, 'PRICE'),
            'DISCOUNT': mall_field(row, 'CURRENT_DISCOUNT') or MALL_FULL_PRICE, 'BUY_TIMES': buy_times}


def mall_goods(player):
    """Every good of the game's own mall table (properties.iterMallData);
    each mall screen keeps its own goods with its filter."""
    cached = _feature_data.get('mall-goods')
    if cached is not None:
        return cached
    properties = mall_properties(player)
    try:
        rows = list(properties.iterMallData())
    except Exception:
        log_error('local-mall-goods-error')
        return {}
    goods = {}
    for goods_id, row in rows:
        goods[goods_id] = mall_good_value(row)
    _feature_data['mall-goods'] = goods
    log('local-mall-goods', size=len(goods))
    return goods


MALL_BUY_RPCS = ('buyMallGood', 'buyMallGoodInAppearanceMall')
HALL_PROP_BUY_RPCS = ('buyDtsHallProp',)


def mall_buy_details(player, args):
    """base.buyMallGood(goodID, num, cashCoupons, logStr) names only the good:
    the backend gets what it costs (iMall.buyMallGood's price * discount)
    and the hall prop it gives, from the game's own mall table."""
    try:
        goods_id = int(args[0])
        row = mall_properties(player).getMallData(goods_id)
    except Exception:
        return {}
    discount = mall_field(row, 'CURRENT_DISCOUNT') or MALL_FULL_PRICE
    item = mall_field(row, 'HALL_PROP_ID') or goods_id
    try:
        count = max(1, int(args[1]))
    except Exception:
        count = 1
    opened = []
    for _index in range(count):
        opened.extend(open_hall_prop(item))
    return {'item': item, 'items': opened,
            'currency_id': mall_field(row, 'CURRENCY_ID'),
            'price': int(mall_field(row, 'PRICE') * discount / MALL_FULL_PRICE)}


def hall_prop_buy_details(player, args):
    """base.buyDtsHallProp(hallPropID, cashCoupons, logStr) buys the hall
    prop itself: its price is the game's (mall_utils.getDtsHallPropBuyCurrencyID
    / Price, what iMall.buyDtsHallProp shows)."""
    try:
        item = int(args[0])
        utils = __import__('mall_utils')
        currency_id = int(utils.getDtsHallPropBuyCurrencyID(item) or 0)
        price = int(utils.getDtsHallPropBuyCurrencyPrice(item) or 0)
    except Exception:
        log_error('local-hall-prop-price-error', args=safe(args))
        return {}
    return {'item': item, 'items': open_hall_prop(item), 'currency_id': currency_id, 'price': price}


PURCHASE_RESULT_SCREEN = 'UIItemDisplay'
PURCHASE_RESULT_DELAY = 0.2


def install_item_display_counts():
    """dts_hall_prop_utils.generateArgsForUIItemDisplay takes item ids and
    counts repeats (3 x 201001 shows x3).  A mail's 2000 diamonds came as one
    id and showed x1: [id, count] pairs are taken too, without repeating an
    id 2000 times.  A list of plain ids works as before."""
    try:
        utils = __import__('dts_hall_prop_utils')
    except Exception:
        return False
    original = getattr(utils, 'generateArgsForUIItemDisplay', None)
    if not callable(original) or getattr(original, '_rl_counts', False):
        return False

    def generateArgsForUIItemDisplay(ids, *args, **kwargs):
        plain, counted = [], []
        for entry in ids or []:
            if isinstance(entry, (list, tuple)) and len(entry) >= 2:
                counted.append((int(entry[0]), int(entry[1])))
            else:
                plain.append(entry)
        if not counted:
            return original(ids, *args, **kwargs)
        # the builder needs at least one id (an empty list raised IndexError)
        result = original(plain or [counted[0][0]], *args, **kwargs)
        if isinstance(result, dict):
            totals, order = {}, []
            for item, count in (list(result.get('itemIDs') or []) if plain else []) + counted:
                if item not in totals:
                    order.append(item)
                    totals[item] = 0
                totals[item] += count
            result['itemIDs'] = [(item, totals[item]) for item in order]
        return result

    generateArgsForUIItemDisplay._rl_counts = True
    utils.generateArgsForUIItemDisplay = generateArgsForUIItemDisplay
    return True


def show_bought_items(items, currency_id=0):
    """The "you got" screen UIMall._showMallResult shows after a purchase;
    the skin screens (UIMallWeaponRecommand, Depot) have none of their own."""
    if not items:
        return False
    try:
        import Globals
        ui_mgr = Globals.uiMgr
        shown = getattr(ui_mgr, PURCHASE_RESULT_SCREEN, None)
        if shown is not None and getattr(shown, 'is_enter', False):
            return False                                  # UIMall already showed it
        utils = __import__('dts_hall_prop_utils')
        args = utils.generateArgsForUIItemDisplay(
            [int(item) for item in items], lambda: None, lambda: None,
            isBGShow=len(items) > 1, currencyID=int(currency_id or 0), isConfirmBtnShow=False)
        ui_mgr.enter_ui(PURCHASE_RESULT_SCREEN, args)
        return True
    except Exception:
        log_error('local-purchase-result-error', items=safe(items))
        return False


DECOMPOSE_RPCS = ('requestDecomposeAppearance', 'requestDecomposeAllRepeation')
COMPOSE_RPCS = ('composeItem',)


def compose_details(player, args):
    """Depot "Compose": what making the appearance from shards costs
    (DtsAppearanceMiscPanel.onComposeAppearanceBtnClicked shows the same)."""
    try:
        item = int(args[0])
        utils = __import__('dts_appearance_utils')
        return {'currency_id': int(utils.getDtsAppearanceComposeCurrencyID(item) or 0),
                'price': int(utils.getDtsAppearanceComposePrice(item) or 0)}
    except Exception:
        log_error('local-compose-details-error', args=safe(args))
        return {}


def decompose_details(player, args):
    """Convert Repeats names the appearances; the backend gets each one's
    shards per copy from the game's table (what UIDecomposeAppearance shows).
    "Convert all" names none: the game's own list of repeats is used."""
    try:
        if args and args[0] is not None:
            ids = [int(item) for item in args[0]]
        else:
            ids = [int(entry['appearanceID']) for entry in player.getDecomposeAppearance()]
        utils = __import__('dts_appearance_utils')
        rates = dict((str(item), [int(utils.getDtsAppearanceDecomposeCurrencyID(item) or 0),
                                  int(utils.getDtsAppearanceDecomposeNum(item) or 0)]) for item in ids)
    except Exception:
        log_error('local-decompose-details-error', args=safe(args))
        return {}
    return {'appearance_ids': ids, 'decompose': rates}


def _entry_field(data, key, default):
    try:
        return data[key]
    except Exception:
        return default


def remove_appearance_copies(player, item_id, count):
    """Take ``count`` permanent copies out of the client's appearance package
    (the server's onDelDtsAppearanceItem / onUpdateDtsAppearanceItemNumber)."""
    try:
        entries = player.dtsAppearancePackage._getItemById(item_id) or {}
        entries = list(entries.items())
    except Exception:
        log_error('local-decompose-package-error', item=item_id)
        return 0
    removed = 0
    for uuid, data in entries:
        if count <= 0:
            break
        if int(_entry_field(_entry_field(data, 'info', {}), 'ex_tm', 0) or 0):
            continue                      # timed copies are not repeats
        number = int(_entry_field(data, 'number', 0) or 0)
        if number <= count:
            player.onDelDtsAppearanceItem(item_id, uuid)
            taken = number
        else:
            player.onUpdateDtsAppearanceItemNumber(item_id, uuid, number - count)
            taken = count
        count -= taken
        removed += taken
    return removed


def _local_decomposed(player, removed, chips):
    """Backend reply to Convert Repeats: the converted copies leave the
    depot and iChips.showDecomposeChips plays "+N shards"."""
    for item_id, count in removed or []:
        remove_appearance_copies(player, int(item_id), int(count))
    gained = [ItemEntry(id=int(chip['id']), num=int(chip['num'])) for chip in chips or []]
    show = getattr(player, 'showDecomposeChips', None)
    if gained and callable(show):
        show(gained)


LOCAL_CALLBACKS = {'rlDecomposed': _local_decomposed}


# --------------------------------------------------------------------------
# DATA leaderboards (backend_server/features/ranking.py)
# --------------------------------------------------------------------------

RANK_LIST_CALLBACKS = {
    'force': 'onRequireBattleGroundForceRankList',
    'winning': 'onRequireBattleGroundWinningRankList',
    'killing': 'onRequireBattleGroundKillingRankList',
    'weapon': 'onRequireWeaponProficiencyRankList',
    # the platoon screen's rank tab (rows read as objects: row.name, row.exp...)
    'team': 'onRequireRosMatchTeamRankList',
}


def _local_rank_list(player, rank_type, start, rows, version, kind):
    """A board for UIRankList: rows are read as objects (itemInfo.value...)."""
    callback = getattr(player, RANK_LIST_CALLBACKS.get(kind, 'onRequireBattleGroundForceRankList'), None)
    if callable(callback):
        callback(int(start), [ItemEntry(row) for row in rows or []], int(version), int(rank_type))


def _local_my_rank(player, rank_type, info, kind):
    """Your own row of a board (rank 0 shows as "-")."""
    if kind == 'team':
        # the platoon rank tab: (rank, my platoon's dict or None)
        callback = getattr(player, 'onGetMyRosMatchTeamRankInfo', None)
        info = info if isinstance(info, dict) else {}
        if callable(callback):
            callback(int(info.get('rank') or 0), info.get('team'))
        return
    name = 'onGetWeaponProficiencyRank' if kind == 'weapon' else 'onGetPlayerBattleGroundRank'
    callback = getattr(player, name, None)
    if callable(callback):
        callback(int(rank_type), ItemEntry(info or {'rank': 0}))


LOCAL_CALLBACKS['rlRankList'] = _local_rank_list
LOCAL_CALLBACKS['rlMyRank'] = _local_my_rank


# --------------------------------------------------------------------------
# Friends (backend_server/chat.py FriendServer)
# --------------------------------------------------------------------------
# Every iFriend call is answered by the backend from its database; what other
# players do (a request to us, an accept, a removal) arrives as "pushes" on
# the world chat pull.  The game has no reply of its own worth guessing: a
# smart reply could invent a "LocalPlayer" friend.
FRIEND_RPCS = frozenset(['getFriendList', 'requestFriend', 'acceptFriend', 'refuseFriend', 'removeFriend',
                         'searchPlayerByName', 'searchPlayerByGidList', 'requestSuggestFriends',
                         'requestFriendOnlineStatus', 'memoryRequestFriend', 'addNearByFriend',
                         'setSocialSignature'])
FRIEND_ACTION_RPCS = frozenset(['requestFriend', 'acceptFriend', 'removeFriend'])


def _friend_value(value):
    # Screens read a friend as an object (friend.gid, .nickname, .dtsLevel);
    # fields the backend does not send read as safe defaults.
    if isinstance(value, dict) and 'gid' in value:
        return LocalReply(value)
    if isinstance(value, list):
        return [_friend_value(item) for item in value]
    return value


# The newest online status of each friend: a status change arrives alone
# (the backend pushes onRequestFriendOnlineStatus for that friend), and a
# friend list shown again from RPC_CACHE gets it laid over its own.
_friend_status = {}
FRIEND_STATUS_KEEP = 500


def _remember_friend_cards(value):
    """Friend / search cards: the avatars (batchGetPlayerData) answer from them."""
    if isinstance(value, dict) and 'gid' in value:
        remember_player_card(value)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and 'gid' in item:
                remember_player_card(item)


def _status_entry(entry):
    """iFriend and the lobby invite panel read [online status, in a team];
    a backend before party.py sent [status, last seen time]: not a team."""
    if isinstance(entry, (list, tuple)) and entry:
        in_team = entry[1] if len(entry) > 1 and isinstance(entry[1], bool) else False
        return [entry[0], in_team]
    return entry


def _friend_statuses(method, args):
    args = list(args)
    if method == 'onRequestFriendOnlineStatus' and len(args) > 1 and isinstance(args[1], dict):
        if len(_friend_status) > FRIEND_STATUS_KEEP:
            _friend_status.clear()
        status = dict((gid, _status_entry(entry)) for gid, entry in args[1].items())
        _friend_status.update(status)
        args[1] = status
    elif method == 'onGetFriendList' and len(args) > 2 and isinstance(args[2], dict):
        status = dict((gid, _status_entry(entry)) for gid, entry in args[2].items())
        for gid in status:
            if gid in _friend_status:
                status[gid] = _friend_status[gid]
        args[2] = status
    return args



def _local_friend(player, method, *args):
    callback = getattr(player, str(method), None)
    if callable(callback):
        for arg in args:
            _remember_friend_cards(arg)
        args = _friend_statuses(str(method), args)
        callback(*[_friend_value(arg) for arg in args])


def ask_friend_lists(player):
    """The incoming requests (red point) and the friends, once per lobby:
    iFriend.onCreate, which asked them online, never runs on this player."""
    for kind in (5, 2):
        ask_friend_list(player, kind)


def ask_friend_list(player, kind, tries=0):
    ask_backend('getFriendList', [kind], {}, lambda reply: friend_list_reply(player, kind, reply, tries))


def friend_list_reply(player, kind, reply, tries):
    """A lost list (online ~17% loss, or ask_backend refused during the
    lobby-entry burst) is asked again: else no request red point and no
    friend statuses until a friend screen asked itself."""
    if isinstance(reply, dict) and reply.get('handled'):
        return apply_backend_reply(player, 'getFriendList', reply)
    lost = reply is None or (isinstance(reply, dict) and reply.get('error'))
    if lost and tries < ENTRY_RETRIES and _same_player(player):
        call_later(ENTRY_RETRY_DELAY, ask_friend_list, player, kind, tries + 1)
    return None


LOCAL_CALLBACKS['rlFriend'] = _local_friend


# --------------------------------------------------------------------------
# Parties (the hall team across players; backend_server/party.py)
# --------------------------------------------------------------------------
# The game's own screens ask (the lobby invite panel, the invitation dialog,
# kick / leave); the backend decides and tells every player concerned with an
# rlParty push on the chat pull.  Never a guessed reply: a team nobody else
# is in.  A second click on the same thing within PARTY_REPEAT seconds is
# dropped here (the backend refuses repeats too).
PARTY_RPCS = frozenset(['inviteHallTeamPlayer', 'acceptHallTeamInvitation', 'refuseHallTeamInvitation',
                        'ignoreHallTeamInvitation', 'leaveHallTeam', 'kickHallTeamMember',
                        'changeHallTeamModeSetting'])
PARTY_REPEAT = 1.5
PARTY_TIPS_KEEP = 200
_party = {'sent': {}, 'tips': {}}


def party_details(player, args):
    """What the backend needs of my team to check an invitation (the game
    sends only the invitee and the team type)."""
    return {'teamSize': int(getattr(player, 'hallTeamSize', 1) or 1),
            'teamType': int(getattr(player, 'hallTeamType', 0) or 0),
            'mapGroup': int(getattr(player, 'hallTeamMapGroup', 0) or 0)}


def party_repeat(name, args):
    """True: the same party call went less than PARTY_REPEAT seconds ago."""
    try:
        key = name + '|' + json.dumps(to_json_value(list(args)[:4]), sort_keys=True)
    except Exception:
        return False
    now = time.time()
    sent = _party['sent']
    if now - sent.get(key, 0.0) < PARTY_REPEAT:
        debug('local-party-repeat', method=name)
        return True
    if len(sent) > 50:
        sent.clear()
    sent[key] = now
    return False


def _party_tip(text, key):
    """Each tip once (a push asked twice, an answer and a push saying the same)."""
    tips = _party['tips']
    key = str(key or text)
    if key in tips:
        return False
    if len(tips) > PARTY_TIPS_KEEP:
        tips.clear()
    tips[key] = time.time()
    show_offline_tip(to_native_str(text), force=True)
    return True


def _team_gids(player):
    try:
        return set(int(gid) for gid in (getattr(player, 'hallTeamData', None) or {}))
    except Exception:
        return set()


def team_weapon(value, position=0):
    """A team slot's outGameWeapon: [weapon, position] (set_state adds a list to it)."""
    if isinstance(value, (list, tuple)):
        return list(value)
    try:
        return [int(value or 0), int(position or 0)]
    except (TypeError, ValueError):
        return [0, 0]


def team_character_type(member):
    """A teammate's model type: UIMain._getMemberCharacterType uses the slot's
    characterType as it is for ethnicity 0 (human), so it must already be the
    gendered one (DtsEthnicity MAILID 10002 / FEMAILID 10005), not the
    account's base type - a female outfit on the male body showed no skin."""
    gender = member.get('dtsAppearanceGender', 1)
    try:
        tables = _ethnicity_tables()
        if tables is not None:
            row = tables.DtsEthnicity[int(member.get('ethnicity') or 0)]
            return int(row['MAILID'] if gender == 1 else row['FEMAILID'])
    except Exception:
        debug('local-team-character-type-error', gender=gender)
    return 10002 if gender == 1 else 10005


_tables_module = {}


def _ethnicity_tables():
    if 'module' not in _tables_module:
        found = None
        for name, module in list(sys.modules.items()):
            if module is not None and name.endswith('tables') and hasattr(module, 'DtsEthnicity'):
                found = module
                break
        if found is None:
            return None                 # not imported yet: asked again next time
        _tables_module['module'] = found
    return _tables_module['module']


def _party_member(player, card):
    if isinstance(card, dict) and int(card.get('gid', 0) or 0) == int(local_player.gid):
        return local_team_member(player)        # mine: from the live player, not the saved outfit
    remember_player_card(card)
    member = LocalHallTeamMember(dict(card))
    member['outGameWeapon'] = team_weapon(card.get('outGameWeapon'), card.get('outGameWeaponPos'))
    if member.get('ethnicity') is None:
        member['ethnicity'] = 0
    member['characterType'] = team_character_type(member)
    return member


def _ui_screen(name):
    try:
        import Globals
        return _ui_open(Globals.uiMgr, name)
    except Exception:
        return None


def _party_invite_answered(gid):
    """My invitation to ``gid`` is no longer pending: its button is usable again."""
    panel = _ui_screen('UIMainBattleGroundInvite')
    if panel is None:
        return
    try:
        invited = getattr(panel, '_invited', None)
        if invited is not None:
            invited.discard(gid)
        panel._restore_invite_for(gid)
    except Exception:
        debug('local-party-panel-error', gid=gid)


def _party_close_invitation(player, team_id, inviter):
    last = getattr(player, 'lastInvitation', None)
    if last is not None and getattr(last, 'teamID', None) not in (team_id, None):
        return False                            # another invitation is shown
    player.lastInvitation = None
    try:
        import Globals
        if _ui_open(Globals.uiMgr, 'UIInvitationDialog') is not None:
            Globals.uiMgr.leave_ui('UIInvitationDialog')
    except Exception:
        log_error('local-party-dialog-close-error')
    return True


def _local_party(player, kind, *args):
    kind = str(kind)
    log('local-party', kind=kind, args=[safe(arg, 120) for arg in args])
    if kind == 'tip':
        _party_tip(args[0] if args else '', args[1] if len(args) > 1 else '')
    elif kind == 'invited' and len(args) >= 6:
        team_id, name, team_type, inviter, duration, msg = args[:6]
        if len(args) > 6:
            remember_player_card(args[6])
        last = getattr(player, 'lastInvitation', None)
        if (last is not None and getattr(last, 'teamID', None) == team_id
                and _ui_screen('UIInvitationDialog') is not None):
            return                              # shown already (a push read twice)
        player.onInvitedToHallTeam(team_id, to_native_str(name), team_type, inviter, duration, to_native_str(msg))
    elif kind == 'enter' and len(args) >= 4:
        team_type, leader, size, cards = args[:4]
        map_group = args[4] if len(args) > 4 else getattr(player, 'hallTeamMapGroup', 0)
        members = [_party_member(player, card) for card in cards or [] if isinstance(card, dict)]
        enter_hall_team(player, team_type, leader, size, members, map_group,
                        args[5] if len(args) > 5 else False, args[6] if len(args) > 6 else 1)
    elif kind == 'add' and args and isinstance(args[0], dict):
        if int(args[0].get('gid', 0) or 0) not in _team_gids(player):
            team_call(player, 'addHallTeamMember', _party_member(player, args[0]))
    elif kind == 'del' and args:
        if int(args[0]) in _team_gids(player):
            team_call(player, 'delHallTeamMember', int(args[0]))
    elif kind == 'member' and args and isinstance(args[0], dict):
        _party_member_changed(player, args[0])
    elif kind == 'leader' and args:
        player.updateHallTeamLeaderGID(int(args[0]))
    elif kind == 'mode' and len(args) >= 3:
        player.syncHallTeamModeSetting(args[0], args[1], args[2])
        # kept with the character: the next lobby opens on this mode
        save_state_durable(lobby={'teamMapGroup': int(args[0]), 'teamType': int(args[1]), 'teamSize': int(args[2])})
    elif kind == 'left':
        if len(_team_gids(player)) > 1:
            player.onLeaveHallTeam()
        sync_local_team(player)                 # back to my own one-player team
    elif kind == 'ready' and len(args) >= 2:
        if int(args[0]) in _team_gids(player):
            team_call(player, 'syncReadyState', int(args[0]), bool(args[1]), 0)
    elif kind == 'start' and args and isinstance(args[0], dict):
        _party_tip('The leader started the match.', 'start-%d' % int(time.time()))
        deliver_battle_ticket(player, args[0])          # the whole team enters together
    elif kind == 'cancel' and args:
        _party_close_invitation(player, args[0], args[1] if len(args) > 1 else None)
    if kind in ('enter', 'add', 'del', 'left'):
        party_voice(player)
    elif kind == 'answered' and args:
        _party_invite_answered(int(args[0]))


# A teammate's card field -> the iHallTeam method that shows the change
# (each updates the slot, its model and the team theme score).
MEMBER_SYNCS = (('hallThemeID', 'syncHallTeamMemberThemeID'),
                ('hallVehicleAppearanceList', 'syncHallTeamMemberHallVehicleAppearanceList'),
                ('identifyTagID', 'syncHallTeamMemberIdentifyTagID'),
                ('dtsAppearanceGender', 'onTeammateUpdateGender'),
                ('dtsWearableAppearanceList', 'onTeammateUpdateWearableAppearance'),
                ('dtsBodyAppearanceList', 'onTeammateUpdateBodyAppearance'),
                ('dtsBattlegroundPropAppearanceList', 'onTeammateUpdateBattlegroundPropAppearance'),
                ('dtsFlyingAccessoryList', 'onTeammateUpdateFlyingAccessory'),
                ('dtsPendantAppearanceList', 'onTeammateUpdatePendantAppearance'),
                ('outGameWeapon', 'syncHallTeamMemberOutGameWeapon'),
                ('outGameBag', 'syncHallTeamMemberOutGameBag'))


def _party_member_changed(player, card):
    try:
        gid = int(card.get('gid', 0) or 0)
        member = (getattr(player, 'hallTeamData', None) or {}).get(gid)
    except Exception:
        return
    if member is None or gid == int(local_player.gid):
        return
    remember_player_card(card)
    for field, method in MEMBER_SYNCS:
        if field not in card:
            continue
        try:
            same = member.get(field) == card[field] if hasattr(member, 'get') else False
        except Exception:
            same = False
        if same:
            continue
        try:
            member[field] = card[field]
        except Exception:
            pass
        value = card[field]
        if field == 'outGameWeapon':
            value = member[field] = team_weapon(value, card.get('outGameWeaponPos'))
        elif field == 'dtsAppearanceGender':
            member['characterType'] = team_character_type(member)       # the other body
        if callable(getattr(player, method, None)):
            team_call(player, method, gid, value)


def party_voice(player):
    """The team voice buttons (UIMain btns_cc) while in a party: the game shows
    them after its NetEase voice login (onCCVoiceLogin), which never happens
    offline.  The buttons toggle the game's own talk / listen state."""
    in_team = len(_team_gids(player)) > 1
    if _party.get('voice') == in_team:
        return
    ui = _ui_screen('UIMain')
    if ui is None:
        return
    try:
        ui.onCCVoiceLogin(in_team)
        _party['voice'] = in_team
    except Exception:
        log_error('local-party-voice-error')


def ask_party_state(player):
    """A new lobby: my team and the invitations still waiting for me."""
    ask_backend('rlPartyState', [], {}, lambda reply: apply_backend_reply(player, 'rlPartyState', reply))


LOCAL_CALLBACKS['rlParty'] = _local_party


# --------------------------------------------------------------------------
# Kicked by the server (a ban from the admin page: backend_server/admin.py)
# --------------------------------------------------------------------------
# rlKick(message) on the chat pull: the game goes back to its login screen
# (ConnectMonitor.backToLogin, as the game does after a disconnect) and shows
# the message in a dialog there.  Logging in again is refused by the backend
# with the same message (shown the same way).
KICK_SCREEN_TRIES = 40
KICK_TITLE = 'Disconnected'


def show_message_dialog(text, title=KICK_TITLE):
    """A dialog the player has to close (UIDialog); a tip if it cannot open."""
    text = to_native_str(text)
    try:
        import Globals
        Globals.uiMgr.enter_ui('UIDialog', {'title': to_native_str(title), 'des': text,
                                            'confirmCB': lambda *args: None})
        log('local-message-dialog', text=text)
        return True
    except Exception:
        log_error('local-message-dialog-error')
    show_offline_tip(text, force=True)
    return False


def _local_kick(player, message='', *args):
    message = to_native_str(message or 'You were disconnected by the server.')
    if _lobby.get('kicked'):
        return                                      # on the way out already
    _lobby['kicked'] = message
    log('local-kicked', message=message)
    try:
        from helpers.ConnectMonitor import ConnectMonitor
        ConnectMonitor.getInstance().backToLogin()
    except Exception:
        log_error('local-kick-error')
    call_later(1.0, show_kick_message, 0)


def show_kick_message(attempt):
    """Once the login screen is up: the reason, in a dialog."""
    message = _lobby.get('kicked')
    if not message:
        return
    try:
        import Globals
        login = _ui_open(Globals.uiMgr, 'UILogin')
    except Exception:
        login = None
    if login is None and attempt < KICK_SCREEN_TRIES:
        call_later(0.5, show_kick_message, attempt + 1)
        return
    show_message_dialog(message, 'Account banned' if 'banned' in message.lower() else KICK_TITLE)


LOCAL_CALLBACKS['rlKick'] = _local_kick


# --------------------------------------------------------------------------
# Platoon (the game's RosMatchTeam; backend_server/features/platoon.py)
# --------------------------------------------------------------------------
# Platoons are shared by the server's players and live in the backend
# database: every iRosMatch call is answered there.  A guessed reply would be
# a fake platoon (a "created" team that does not exist, an "applied" that
# nobody sees), so none of them ever gets a smart reply.  What other players
# change in my platoon arrives as an rlPlatoon push on the chat pull.
PLATOON_RPCS = frozenset([
    'getMyRosMatchTeamInfo', 'checkCreateRosMatchTeamInfoValidation', 'createRosMatchTeam',
    'getRosMatchTeamList', 'searchRosMatchTeam', 'getRosMatchTeamData', 'applyRosMatchTeam',
    'quitRosMatchTeam', 'rosMatchTeamLeaderOperation', 'getRosMatchTeamPlayerList', 'getRosMatchTeamPlayer',
    'getRosMatchTeamApplyList', 'getRosMatchTeamEventList', 'modifyRosMatchTeamBasicInfo',
    'modifyRosMatchTeamLogo', 'rosMatchTeamSignIn', 'openRosMatchTeamTaskMain', 'getRosMatchTeamWeekActReward',
    'openRosMatchTeamShopMain', 'buyRosMatchTeamMallGoods', 'getRosMatchTeamLvRewardProps',
    'getAthleteRosMatchTeamBriefData', 'getAthleteRosMatchTeamLogo', 'checkRosMatchTeamWeekRank1Player',
    'checkShowWeekRank1TeamInRankList', 'getRosMatchTeamRankListDetail'])
# Calls that change a platoon: a lost answer gets a tip, and each clears the
# cached platoon reads before it goes (modifyRosMatchTeamBasicInfo ends in
# "Info" and looks like a read to READ_LIKE).
PLATOON_WRITES = frozenset(['createRosMatchTeam', 'applyRosMatchTeam', 'quitRosMatchTeam',
                            'rosMatchTeamLeaderOperation', 'modifyRosMatchTeamBasicInfo', 'modifyRosMatchTeamLogo',
                            'rosMatchTeamSignIn'])
PLATOON_READS = ('getMyRosMatchTeamInfo', 'getRosMatchTeamList', 'searchRosMatchTeam', 'getRosMatchTeamData',
                 'getRosMatchTeamPlayerList', 'getRosMatchTeamApplyList', 'getRosMatchTeamEventList',
                 'getAthleteRosMatchTeamBriefData', 'getAthleteRosMatchTeamLogo', 'requireRankInfo',
                 'requireRankList')
PLATOON_SCREEN = 'UINewRosMatchTeam'


def _platoon_screen():
    try:
        import Globals
        return _ui_open(Globals.uiMgr, PLATOON_SCREEN)
    except Exception:
        return None


def _platoon_widget_shown(screen, name):
    try:
        widget = getattr(screen, name, None)
        return widget is not None and bool(widget.isVisible())
    except Exception:
        return False


def _platoon_redraw(player, screen, whole=False):
    """An open platoon screen after another player's change: the member tab
    asks its list again (the push cleared the cache), the homepage is drawn
    again from player.rosMatchTeamData; ``whole`` (joined / removed): the
    screen switches between its no-platoon and platoon views.  Never
    onGetMyRosMatchTeamInfoCallback: it enters the screen (it would pop up)."""
    if screen is None:
        return False
    in_team = bool(getattr(player, 'rosMatchTeamData', None))
    try:
        if in_team and not whole and _platoon_widget_shown(screen, 'memberWidget'):
            player.getRosMatchTeamPlayerList()
        elif whole or _platoon_widget_shown(screen, 'homepageWidget'):
            screen.refreshRosMatchTeamInfo()
    except Exception:
        log_error('local-platoon-redraw-error')
        return False
    return True


def _platoon_tip(text, *names):
    try:
        show_offline_tip(text % tuple(to_native_str(name) for name in names), force=True)
    except Exception:
        log_error('local-platoon-tip-error')


def _local_platoon(player, kind, *args):
    """rlPlatoon pushes: 'team' (my platoon changed), 'joined' (my apply was
    accepted), 'left' (I was removed), 'apply' (someone asks to join: leader /
    deputies), 'refused' (my apply was refused / the platoon disbanded),
    'changed' (a sign-in: the cached reads are stale, nothing to draw)."""
    screen = _platoon_screen()
    if kind in ('team', 'joined') and args and isinstance(args[0], dict):
        player.rosMatchTeamData = args[0]
        if kind == 'joined':
            _platoon_tip('You joined the platoon %s.', args[0].get('Name', ''))
        _platoon_redraw(player, screen, whole=kind == 'joined')
    elif kind == 'left':
        try:
            player.resetRosMatchTeamData()
        except Exception:
            player.rosMatchTeamData = None
        _platoon_tip('You were removed from the platoon %s.', args[2] if len(args) > 2 else '')
        _platoon_redraw(player, screen, whole=True)
    elif kind == 'apply':
        data = getattr(player, 'rosMatchTeamData', None)
        if isinstance(data, dict) and args and data.get('TeamID') == args[0] and len(args) > 1:
            data['ApplyCnt'] = args[1]
        try:
            player.onShowRosMatchTeamRedDot()
        except Exception:
            log_error('local-platoon-red-dot-error')
        if _platoon_widget_shown(screen, 'memberWidget'):
            _platoon_redraw(player, screen)
    elif kind == 'refused':
        _platoon_tip('The platoon %s did not take your application.', args[1] if len(args) > 1 else '')
    return True


LOCAL_CALLBACKS['rlPlatoon'] = _local_platoon


def install_rank_requests():
    """National (LBS 96/97) and Friend (85-95) boards are asked through
    their own server calls; offline they are the server's players, from the
    same database boards (requireRankList / requireRankInfo)."""
    try:
        rank_class = __import__('iRank').iRank
    except Exception:
        log_error('local-rank-requests-error')
        return False
    if getattr(rank_class.__dict__.get('requireLBSRankList'), '_rl_board', False):
        return False

    def requireLBSRankList(self, rankType, version=0, nexBatch=False):
        self.base.requireRankInfo(rankType)
        self.base.requireRankList(rankType, version, 0, nexBatch)

    def requireFriendRankList(self, rankType, version=0):
        self.base.requireRankInfo(rankType)
        self.base.requireRankList(rankType, version, 0, False)
    for function in (requireLBSRankList, requireFriendRankList):
        function._rl_board = True
        setattr(rank_class, function.__name__, function)
    return True


# --------------------------------------------------------------------------
# HAPPY DERBY (horse racing betting): closed
# The lobby widget ("Betting mm:ss / In Play mm:ss") is pure client code:
# it counts down from the local clock and horse_racing_common's constants
# whenever shared.switches.EnableHorseRacing is on.  No server has a race
# schedule, the athlete / bet tables are not in client_tables.json and the
# winnings were paid by system mail, so the feature is closed the way the
# live game closed it: the switch off, and the panel's RPCs answered with
# nothing instead of guessed replies.
# --------------------------------------------------------------------------

HORSE_RACING_OPEN = False      # no server-side race schedule / bet tables yet
HORSE_RACING_TIP = 'Happy Derby is not available on this server yet.'
HORSE_SCREENS = re.compile(r'^UIHor[sc]e')   # UIHorseRace*, UIHorceRacingBarrage (game typo)
HORSE_SWITCH_MODULES = ('shared.switches', 'switches')
HORSE_QUERY_RPCS = (
    'getCurHorseRacingMatch', 'getNextHorseRacingMatch', 'getCurMatchTopWins', 'getHorseBetList',
    'getHorseEndMatchList', 'getHorseLastEndedMatch', 'getHorseMatchWinInfo', 'getHorseTopCommentList',
    'getHorseTopWinBetList', 'getTopWinToday', 'getRecentPlayerWinInfo', 'getHorseRaceWeeklyTaskProgress',
    'openHorseRacingShopMain', 'setBetVisitRookie',
)
HORSE_ACTION_RPCS = (
    'horseBet', 'horseBetWithTicker', 'horseBid', 'cancelHorseBid', 'horseComment', 'horseLike',
    'horseLikeAthlete', 'sendHorseBulletScreen', 'buyHorseRacingShopGoods', 'getHorseRaceWeeklyTaskAward',
)
_horse = {'closed': False}


def close_horse_racing():
    """Turn the game's own switch off, as the live server did when the event
    ended.  With it off UIMain._get_ui builds no entrance widget (no fake
    countdown), onClickHorseRaceEntrance shows the game's 'not open' tip and
    the top-left coin is gold again instead of Horse Racing Coin."""
    if HORSE_RACING_OPEN:
        return False
    modules = []
    for module in [_find_module(HORSE_SWITCH_MODULES)] + [sys.modules.get(name) for name in HORSE_SWITCH_MODULES]:
        # 'switches' and 'shared.switches' may be two module objects; UI code reads either
        if module is not None and not any(module is seen for seen in modules):
            modules.append(module)
    if not modules:
        log('local-horse-racing-switch-missing')
        return False
    try:
        for module in modules:
            module.EnableHorseRacing = False
    except Exception:
        log_error('local-horse-racing-close-error')
        return False
    if not _horse['closed']:
        _horse['closed'] = True
        log('local-horse-racing-closed', modules=[getattr(module, '__name__', '') for module in modules])
    return True


@rpc_handler(*HORSE_QUERY_RPCS)
def _horse_query_closed(player, *args, **kwargs):
    # No guessed reply: an empty LocalReply became curHorseRacingMatch
    # (StartTs 0, so the panel counted down from 1970).  Unanswered, the
    # game keeps its own MATCH_NO_OPEN state.
    return None


@rpc_handler(*HORSE_ACTION_RPCS)
def _horse_action_closed(player, *args, **kwargs):
    show_offline_tip(HORSE_RACING_TIP)
    return None


# --------------------------------------------------------------------------
# BENEFITS: level packs and the 7-day login (backend_server/features/welfare.py)
# --------------------------------------------------------------------------

SIGN_IN_SCREEN = 'UIDtsSign'
SIGN_IN_DAYS = 7
SIGN_IN_POLL = 0.5
WELFARE_STATE_RPC = 'rlWelfareState'
PH_OFFSET = 8 * 3600


def _claimed_level_awards(player):
    """The levels whose pack the game shows as claimed."""
    try:
        return set(int(level) for level in player.childClientProperty2['gotLevelAwardList'])
    except Exception:
        return set()


def level_award_items(player, args):
    """requestDtsLevelAward(level): the level's pack (ExpLevelTable
    levelAward) opened with the game's tables, plus every other reached,
    unclaimed level's pack: one Get click claims them all (Claim All - the
    screen has only a per-row button).  The backend still refuses levels above
    characters.level or already claimed, so an extra level here costs nothing."""
    try:
        level = int(args[0])
        tables = __import__('shared.tables', fromlist=['getExpLevelTable'])
        award = int(tables.getExpLevelTable(level)['levelAward'] or 0)
    except Exception:
        log_error('local-level-award-error', args=safe(args))
        return {}
    items = open_hall_prop(award) if award else []
    if player is None:
        return {'items': items}
    levels = {}
    if award:
        levels[str(level)] = items
    claimed = _claimed_level_awards(player)
    try:
        top = int(getattr(player, 'dtsLevel', 0) or 0)
    except Exception:
        top = 0
    for other in range(1, top + 1):
        if other == level or other in claimed:
            continue
        try:
            pack = int(tables.getExpLevelTable(other)['levelAward'] or 0)
        except Exception:
            continue                    # no row for this level: no pack
        if pack:
            levels[str(other)] = open_hall_prop(pack)
    # 'items' alone is what a backend from before Claim All reads
    return {'items': items, 'levels': levels}


def sign_in_items(player, args):
    """requestDtsSigninAward(): every day's reward (properties.iterDtsSigninData
    awardID); the backend picks the day it allows."""
    try:
        legacy = __import__('helpers.character_scene', fromlist=['legacyProperties']).legacyProperties
        days = dict((str(int(day)), open_hall_prop(int(data.awardID))) for day, data in legacy.iterDtsSigninData())
    except Exception:
        log_error('local-sign-in-items-error')
        return {}
    return {'day_items': days}


WELFARE_DETAILS = {'requestDtsLevelAward': level_award_items, 'requestDtsSigninAward': sign_in_items}


WELFARE_PROP = 'rlWelfare'
WELFARE_KEYS = ('sign_level', 'sign_time', 'sign_day', 'can_sign', 'sign_days', 'level_awards',
                'next_day_at', 'now')
SIGN_IN_WAIT = 4.0              # seconds the login popup waits for a late state, then the slider


def _welfare_gid():
    try:
        return local_player.gid
    except Exception:
        return None


def welfare_cache():
    """This account's last welfare state (lobby props, a claim's reply), or
    None: _lobby outlives a logout, another account's copy is never used."""
    state = _lobby.get('welfare')
    if isinstance(state, dict) and state.get('gid') == _welfare_gid():
        return state
    return None


def welfare_stale():
    """True once the PH day of the cached state is over (or nothing cached).
    The server's own clock decides: the deadline is kept as local time when
    the state arrived (expires), so a wrong device clock cannot move it."""
    state = welfare_cache()
    if state is None:
        return True
    try:
        return time.time() >= float(state.get('expires') or 0)
    except Exception:
        return True


def apply_welfare_state(player, state):
    """The 7-day login state and the claimed level packs from the database
    (lobby prop rlWelfare, a sign-in reply, a re-sync).  Kept in _lobby so a
    new lobby entity (back from a battle) has it at once, even when the props
    request is lost; the game's own properties are set only when they differ
    (onSetSignAwardLevel redraws an open UIDtsSign)."""
    if not isinstance(state, dict):
        return False
    cached = welfare_cache() or {}
    merged = dict(cached)
    for key in WELFARE_KEYS:
        if key in state:
            merged[key] = state[key]
    merged['gid'] = _welfare_gid()
    try:
        next_day_at, server_now = int(merged.get('next_day_at') or 0), int(state.get('now') or 0)
        if 'next_day_at' in state and next_day_at:
            # server time -> local time: the device clock may be off by hours
            merged['expires'] = time.time() + (next_day_at - server_now if server_now else
                                               next_day_at - time.time())
    except Exception:
        log_error('local-welfare-expires-error')
    _lobby['welfare'] = merged
    _lobby['can_sign'] = bool(merged.get('can_sign'))
    _lobby['sign_level'] = int(merged.get('sign_level') or 0)
    if merged.get('sign_days'):
        _lobby['sign_days'] = int(merged['sign_days'])
    try:
        props = player.childBaseClientProperty
        current = (props['signAwardTime'], props['signAwardLevel'])
    except Exception:
        current = (None, None)
    for index, name, key in ((0, 'onSetSignAwardTime', 'sign_time'), (1, 'onSetSignAwardLevel', 'sign_level')):
        value = int(merged.get(key) or 0)
        if key not in state or current[index] == value:
            continue
        callback = getattr(player, name, None)
        if callable(callback):
            try:
                callback(value)
            except Exception:
                log_error('local-welfare-state-error', callback=name)
    if isinstance(state.get('level_awards'), (list, tuple)):
        set_level_awards(player, list(state['level_awards']))
    refresh_welfare_badges(player)
    if _lobby.pop('sign_waiting', False):
        # show_login_popups ran before the state arrived: it decides now
        open_login_popup()
    return True


def _local_welfare_state(player, sign_level, sign_time, can_sign, level_awards, *rest):
    """rlWelfareState (a re-sync, or a backend without the rlWelfare prop)."""
    return apply_welfare_state(player, {'sign_level': sign_level, 'sign_time': sign_time,
                                        'can_sign': can_sign, 'level_awards': list(level_awards or [])})


def _local_welfare_sync(player, state=None, code=None):
    """A refused sign-in (already_signed, week_done): the reply carries the
    current state; the open UIDtsSign is redrawn with it (no network)."""
    if isinstance(state, dict):
        apply_welfare_state(player, state)
    else:
        _lobby['can_sign'] = False
    try:
        import Globals
        screen = _ui_open(Globals.uiMgr, SIGN_IN_SCREEN)
        if screen is not None:
            screen.refresh_init_ui()
    except Exception:
        log_error('local-sign-in-refresh-error', code=safe(code))
    return True


def set_level_awards(player, levels):
    """The claimed level packs from the database (a lobby prop, a claim's
    reply, a refused claim's re-sync).  Edited in place: the game holds the
    list object.  An open Level Award screen and the Benefits red dots are
    redrawn.  True when the list changed."""
    if not isinstance(levels, (list, tuple)):
        return False
    try:
        claimed = player.childClientProperty2['gotLevelAwardList']
        wanted = sorted(set(int(level) for level in levels))
        changed = list(claimed) != wanted
        claimed[:] = wanted
        player.orderdLevelAwardList = sorted(claimed)
    except Exception:
        log_error('local-level-awards-error')
        return False
    cached = welfare_cache()
    if cached is not None:
        cached['level_awards'] = list(wanted)
    else:
        _lobby['welfare'] = {'gid': _welfare_gid(), 'level_awards': list(wanted)}
    if changed:
        try:
            import Globals
            screen = _ui_open(Globals.uiMgr, 'UILevelAward')
            if screen is not None:
                screen.refreshUI()
        except Exception:
            log_error('local-level-awards-refresh-error')
        refresh_welfare_badges(player)
    return changed


def welfare_red_hint():
    """UIRedHintEnum.UI_TYPE_WELFARE, from the modules that use it."""
    for name in ('ui.UIWelfareController', 'ui.main.UIMainFunctionEntrance', 'shared.Enum.UIRedHintEnum'):
        module = sys.modules.get(name)
        if module is None:
            continue
        enum = getattr(module, 'UIRedHintEnum', module)
        value = getattr(enum, 'UI_TYPE_WELFARE', None)
        if value is not None:
            return value
    return None


def refresh_welfare_badges(player):
    """The Benefits red dots after the state changed under built screens: the
    lobby entrance badge (what UIWelfareController.on_leave sets) and the
    Level Award tab dot of an open Benefits screen.  Not refreshLevelAwardRedPoint:
    it may enter UIG89WelfareController.  Each step alone: the game thread."""
    try:
        import Globals
        ui_mgr = Globals.uiMgr
    except Exception:
        return False
    try:
        level_dot = bool(player.isHaveLevelAwardGot())
    except Exception:
        return False
    try:
        # a property on iDailyActivity (a method in other builds)
        daily = player.hasDailyActivityReward
        daily_dot = bool(daily() if callable(daily) else daily)
    except Exception:
        daily_dot = False
    try:
        welfare = _ui_open(ui_mgr, 'UIWelfareController')
        if welfare is not None:
            welfare.get_widget_by_path('TabBtns/btn_level_award/red_point').setVisible(level_dot)
    except Exception:
        log_error('local-welfare-tab-dot-error')
    try:
        main = _ui_open(ui_mgr, 'UIMain')
        hint = welfare_red_hint()
        if main is not None and hint is not None:
            main.GetComponent('UIMainFunctionEntrance').updateRedPointByType(hint, level_dot or daily_dot)
    except Exception:
        log_error('local-welfare-badge-error')
    return True


def sign_in_day_count():
    """How many days the game's sign-in table rewards (5 in this build,
    though const.DTS_SIGN_IN_AWARD_MAX says 7)."""
    try:
        legacy = __import__('helpers.character_scene', fromlist=['legacyProperties']).legacyProperties
        return len(list(legacy.iterDtsSigninData())) or SIGN_IN_DAYS
    except Exception:
        return SIGN_IN_DAYS


def can_sign_today():
    return bool(_lobby.get('can_sign')) and _lobby.get('sign_level', 0) < sign_in_day_count()


def _local_signed(player, *args):
    _lobby['can_sign'] = False


LOCAL_CALLBACKS['rlWelfareState'] = _local_welfare_state
LOCAL_CALLBACKS['rlWelfareSync'] = _local_welfare_sync
LOCAL_CALLBACKS['rlSigned'] = _local_signed
LOCAL_CALLBACKS['rlLevelAwards'] = lambda player, levels=None: set_level_awards(player, levels)


# --------------------------------------------------------------------------
# BENEFITS > Activity Pts (ui.UIDailyActivity, iDailyActivity; the backend's
# features/activity.py owns the tasks, points and boxes).  The whole state is
# a lobby prop (rlDailyActivity, once per entry - the day's login); a claim,
# a match, a share answer only what moved, as the rlDailyActivity callback:
#   {"progress": [[id, n]], "state": [[id, s]], "daily": n, "weekly": n,
#    "daily_boxes": [[i, s]], "weekly_boxes": [[i, s]], "exp": n, "full": bool}
# The game keeps the lists in childBaseClientProperty (no setter: written in
# place) and redraws through its own sync* methods.
# --------------------------------------------------------------------------

DAILY_ACTIVITY_PROP = 'rlDailyActivity'
DAILY_ACTIVITY_RPC = 'rlDailyActivity'
DAILY_ACTIVITY_MATCH_RPC = 'rlMatchPlayed'
DAILY_ACTIVITY_RESYNC = 2.0             # s after the game's own midnight reset
DAILY_ACTIVITY_LISTS = (
    # changes key, where the game keeps it, its single-entry sync method
    ('progress', 'activityProgress', 'syncSingleActivityProgress'),
    ('state', 'activityState', 'syncSingleActivityState'),
    ('daily_boxes', 'dailyActivityRewardState', 'syncSingleDailyActivityRewardState'),
    ('weekly_boxes', None, 'syncSingleWeeklyActivityRewardState'),
)


def _activity_list(player, key):
    if key is None:
        return player.weeklyActivityRewardState     # a top-level PyArrayDataInstance
    return player.childBaseClientProperty[key]


def _set_activity_entry(entries, index, value):
    """True when the entry changed.  Padded with 0 (UnmetNeeds / no progress)."""
    while len(entries) <= index:
        entries.append(0)
    if entries[index] == value:
        return False
    entries[index] = value
    return True


def apply_daily_activity(player, changes):
    """Write the backend's Activity state into the game's lists and redraw
    only what changed (UIDailyActivity, the lobby tile, the red dots)."""
    if not isinstance(changes, dict):
        return False
    fill_daily_activity(player)
    moved = False
    for key, where, sync in DAILY_ACTIVITY_LISTS:
        pairs = changes.get(key)
        if not isinstance(pairs, (list, tuple)):
            continue
        try:
            entries = _activity_list(player, where)
        except Exception:
            log_error('local-daily-activity-list-error', key=key)
            continue
        for pair in pairs:
            try:
                index, value = int(pair[0]), int(pair[1])
            except Exception:
                continue
            try:
                if not _set_activity_entry(entries, index, value):
                    continue
            except Exception:
                # an array without item assignment: the game's own sync below
                # writes it its way
                log_error('local-daily-activity-write-error', key=key)
            moved = True
            _call_game(player, sync, index, value)
    for key, name, sync in (('daily', 'dailyActivity', 'syncDailyActivity'),
                            ('weekly', 'weeklyActivity', 'syncWeeklyActivity')):
        if key not in changes:
            continue
        try:
            value = int(changes[key])
        except Exception:
            continue
        if getattr(player, name, None) == value:
            continue
        moved = True
        if not _call_game(player, sync, value):
            try:
                setattr(player, name, value)
            except Exception:
                log_error('local-daily-activity-points-error', name=name)
    if moved or changes.get('full'):
        _call_game(player, '_refresh_activity_red_badges')
        refresh_welfare_badges(player)
    if changes.get('exp'):
        try:
            # a claimed task's experience (only a successful claim carries it)
            add_exp(int(changes['exp']), player=player)
        except Exception:
            log_error('local-daily-activity-exp-error')
    return moved


def _call_game(player, name, *args):
    """One of the game's iDailyActivity methods; a screen that is not built
    yet must not stop the rest (the lists are written already)."""
    method = getattr(player, name, None)
    if not callable(method):
        return False
    try:
        method(*args)
        return True
    except Exception:
        log_error('local-daily-activity-sync-error', method=name)
        return False


def _local_daily_activity(player, changes=None):
    return apply_daily_activity(player, changes)


LOCAL_CALLBACKS['rlDailyActivity'] = _local_daily_activity


# --------------------------------------------------------------------------
# MANUAL: Special Distinction = the game's Brave Book 2, activity-system
# activity 100008 (ui.activities.UIBraveBook2*; the backend's features/
# manual.py owns the training points, missions, rewards and the bought
# distinction).  The whole state comes once per lobby entry (rlManualState,
# which also reports the online time since the last entry); every call after
# that answers only what changed, as the game's own asOnUpdateActivities /
# asOnUpdateTasks / asOnUpdateAwards / asOnGetAwards callbacks - the game
# keeps them in asActivityRecords & co.  What the hook adds:
#   rlManualSeason   the backend's season window: the screen's "LEFT n day"
#                    counted to the 2022 ranked season's end (LEFT -1593 day)
#   selectWeek       Training Missions indexed an empty week list (KeyError: 0)
#                    when it opened before the week task's record
#   updateWeekTask   the screen's week list is extended to the backend's weeks
# --------------------------------------------------------------------------

MANUAL_STATE_RPC = 'rlManualState'
MANUAL_SCREEN_PREFIX = 'UIBraveBook2'
MANUAL_TAB = ('ui.activities.UIBraveBook2Tab', 'UIBraveBook2Tab')
MANUAL_TASKS = ('ui.activities.UIBraveBook2Task', 'UIBraveBook2Task')
MANUAL_ONLINE_MAX = 12 * 3600          # one report never counts more (a sleeping PC)
MANUAL_LEFT_NUMBER = re.compile(r'-?\d+')
_manual = {'season': None, 'online_mark': None, 'screens': 0}


def manual_online_seconds(now=None):
    """Seconds online since the last report (lobby and battles alike); the
    first report of a run only starts the count."""
    now = time.time() if now is None else now
    mark = _manual.get('online_mark')
    _manual['online_mark'] = now
    if mark is None:
        return 0
    return int(max(0, min(MANUAL_ONLINE_MAX, now - mark)))


def ask_manual_state(player):
    """Once per lobby entry (show_login_popups): no polling - a match, a claim
    or a buy answers its own changes."""
    return backend_call(player, MANUAL_STATE_RPC, [manual_online_seconds()])


def manual_left_days(now=None):
    season = _manual.get('season') or {}
    try:
        end = float(season['end'])
    except Exception:
        return None
    now = time.time() if now is None else now
    return int(max(0, (end - now + 86399) // 86400))


def _local_manual_season(player, season=None):
    """rlManualSeason (first of the lobby entry's callbacks)."""
    if not isinstance(season, dict):
        return False
    _manual['season'] = dict(season)
    install_manual_screens()
    extend_week_handlers(season.get('weekly'))
    refresh_manual_season_view()
    log('local-manual-season', season=season.get('season'), left=manual_left_days(),
        level=season.get('level'), points=season.get('points'))
    return True


LOCAL_CALLBACKS['rlManualSeason'] = _local_manual_season


def _manual_class(where):
    module = __import__(where[0], fromlist=[where[1]])
    return getattr(module, where[1])


def install_manual_screens():
    """Wrap the two screen methods once (the modules load on first use: also
    called when a UIBraveBook2 screen is entered)."""
    if _manual['screens'] >= 2:
        return False
    for where, wrap in ((MANUAL_TAB, _wrap_season_view), (MANUAL_TASKS, _wrap_select_week)):
        try:
            if wrap(_manual_class(where)):
                _manual['screens'] += 1
        except Exception:
            log_error('local-manual-screens-error', screen=where[1])
    return True


def _wrap_season_view(cls):
    original = cls.__dict__.get('_UpdateSeasonView')
    if original is None or getattr(original, '_rl_manual', False):
        return False

    def _UpdateSeasonView(self, *args, **kwargs):
        result = None
        try:
            result = original(self, *args, **kwargs)
        except Exception:
            # the 2022 season table: a broken date must not stop the tab switch
            log_error('local-manual-season-view-error')
        set_manual_left_days(self)
        return result
    _UpdateSeasonView._rl_manual = True
    cls._UpdateSeasonView = _UpdateSeasonView
    return True


def _wrap_select_week(cls):
    original = cls.__dict__.get('selectWeek')
    if original is None or getattr(original, '_rl_manual', False):
        return False

    def selectWeek(self, week, *args, **kwargs):
        tabs = getattr(self, 'weekTabRedPoints', None)
        if not tabs:
            # no week tab yet: the week task's record had not come when the
            # screen was built; the game indexed the empty dict (KeyError: 0)
            debug('local-manual-no-weeks', week=safe(week))
            return None
        if isinstance(tabs, dict) and week not in tabs:
            # week 0 ("the current one" before any was picked): the latest week
            week = max(tabs)
        try:
            return original(self, week, *args, **kwargs)
        except KeyError:
            log_error('local-manual-select-week-error', week=safe(week))
            return None
    selectWeek._rl_manual = True
    cls.selectWeek = selectWeek
    return True


def set_manual_left_days(screen, now=None):
    """The season label's number becomes the backend season's days left (the
    game's own text and format kept: only the number changes)."""
    left = manual_left_days(now)
    widget = getattr(screen, 'uiSeasonRemainingTime', None)
    if left is None or widget is None:
        return False
    try:
        text = widget.getString()
        if not MANUAL_LEFT_NUMBER.search(text or ''):
            return False
        fixed = MANUAL_LEFT_NUMBER.sub(str(left), text, 1)
        if fixed != text:
            widget.setString(fixed)
        return True
    except Exception:
        log_error('local-manual-left-days-error')
        return False


def refresh_manual_season_view():
    try:
        import Globals
        screen = getattr(Globals.uiMgr, MANUAL_TAB[1], None)
    except Exception:
        return False
    if screen is None or not getattr(screen, 'is_enter', False):
        return False
    return set_manual_left_days(screen)


def extend_week_handlers(weekly):
    """UIBraveBook2Task.task_handler_map['updateWeekTask'] is the week list the
    screen indexes (12 a week): the backend's weeks must all be in it."""
    try:
        ids = [int(task) for task in weekly or []]
    except Exception:
        return False
    if not ids:
        return False
    try:
        handlers = getattr(_manual_class(MANUAL_TASKS), 'task_handler_map', None)
        week = handlers.get('updateWeekTask') if isinstance(handlers, dict) else None
        if week is None:
            return False
        missing = [task for task in ids if task not in week]
        if not missing:
            return False
        if isinstance(week, list):
            week.extend(missing)
        else:
            handlers['updateWeekTask'] = list(week) + missing
        log('local-manual-week-handlers', added=len(missing))
        return True
    except Exception:
        log_error('local-manual-week-handlers-error')
        return False


def install_daily_activity_reset():
    """UIMainDailyActivity.pastMidNight zeroes every list at the device's
    midnight (resetDailyActivityState): the server's state is asked once
    after it (an event, not polling) - it counts the new day's login, or puts
    back today's progress when the device's midnight is not the server's."""
    try:
        activity_class = __import__('iDailyActivity').iDailyActivity
    except Exception:
        log_error('local-daily-activity-reset-error')
        return False
    original = activity_class.__dict__.get('resetDailyActivityState')
    if original is None or getattr(original, '_rl_server_day', False):
        return False

    def resetDailyActivityState(self, *args, **kwargs):
        delay = DAILY_ACTIVITY_RESYNC
        state = welfare_cache()
        try:
            # the server's own midnight a moment away: asked just after it
            until = float((state or {}).get('expires') or 0) - time.time()
            if 0 < until < 120:
                delay = until + DAILY_ACTIVITY_RESYNC
        except Exception:
            pass
        call_later(delay, backend_call, self, DAILY_ACTIVITY_RPC)
        return original(self, *args, **kwargs)
    resetDailyActivityState._rl_server_day = True
    activity_class.resetDailyActivityState = resetDailyActivityState
    return True


# --------------------------------------------------------------------------
# DEMON HUNTER: the lobby tile (doUIJump 100055) opens UIGuiMieTurnable, the
# limited-time ("LT") lottery wheel of iActivityLimitTime.  The wheel asks
# requestGenerateDtsLTBaseTable for its prizes; unanswered it stayed blank.
# Its prizes come from the game's own tables (no backend, nothing shared).
# Draws are not run: the event's version, currency and rules are not in the
# dumped scripts, so the backend acknowledges them with a tip (rpc_routes).
# onGenerateDtsLTBaseTable is wrapped by client_utils.funcLog (no visible
# arguments); its (grid, hasGot) shape is that of onGenerateDtsLTBaseTableVersion
# and of the April Fool twin onGenerateDtsAprilFoolBaseTable.
# --------------------------------------------------------------------------

LT_SCREEN = 'UIGuiMieTurnable'
LT_POOL_TABLE = 'DtsAprilFoolBasePool'      # legacyProperties.getDtsAprilFoolBasePoolData(version)
LT_COMMON = ('activity_limit_time_common', 'ui.activity_limit_time_common')
LT_NAME_WORDS = re.compile(r'demon|guimie|slayer|hunter', re.I)
LT_CLOSED_TIP = 'Demon Hunter draws have ended - the wheel shows the event prizes.'


def _lt_screen_version(keys):
    """A *VERSION* int constant on the open wheel screen or its module."""
    try:
        import Globals
        ui = getattr(Globals.uiMgr, LT_SCREEN, None)
    except Exception:
        return None
    if ui is None:
        return None
    for owner in (ui, sys.modules.get(getattr(type(ui), '__module__', None) or '')):
        if owner is None:
            continue
        try:
            for name in dir(owner):
                if 'VERSION' not in name:
                    continue
                value = getattr(owner, name, None)
                if _int_arg(value) and (not keys or value in keys):
                    return value
        except Exception:
            continue
    return None


def lt_version():
    """The LT pool version of the Demon Hunter wheel, or None: a VERSION on
    the screen, else the pool row whose name says so, else the newest row
    (GuiMie is the newest LT event: 100055 is doUIJump's last jump)."""
    if _lobby.get('lt_version') is not None:
        return _lobby['lt_version']
    keys, names, version = [], [], None
    try:
        common = _find_module(LT_COMMON)
        props = getattr(common, 'legacyProperties', None) or _find_module((PROPS_MODULE,))
        keys = [key for key in (_table_keys(_table_getter(props, LT_POOL_TABLE)) or []) if _int_arg(key)]
        version = _lt_screen_version(keys)
        namer = getattr(common, 'getLimitActivityName', None)
        if version is None and callable(namer):
            for key in keys:
                try:
                    name = to_native_str(namer(key))
                except Exception:
                    name = ''
                names.append(safe(name, 60))
                if version is None and isinstance(name, string_types) and LT_NAME_WORDS.search(name):
                    version = key
        if version is None and keys:
            version = max(keys)
    except Exception:
        version = None
    if version is not None:
        _lobby['lt_version'] = version
        log('local-lt-version', version=version, keys=keys[:40], names=names[:40])
    return version


def lt_base_grid(player, version):
    """The wheel's prize ids at the player's current round
    (activity_limit_time_common.getDtsLTBaseGridProp)."""
    try:
        common = _find_module(LT_COMMON)
        round_cnt = int(getattr(player, 'dtsLTBaseLotteryRoundCnt', 0) or 0)
        return [int(prop) for prop in common.getDtsLTBaseGridProp(round_cnt, version) or [] if _int_arg(prop)]
    except Exception:
        if not _lobby.get('lt_grid_error'):
            _lobby['lt_grid_error'] = True
            log_error('local-lt-base-grid-error', version=version)
        return []


@rpc_handler('requestGenerateDtsLTBaseTable')
def _rpc_lt_base_table(player, *args, **kwargs):
    # The screen asks twice per open (~12 ms apart): one answer, later, so
    # the screen has built its components.  No network call.
    if _lobby.get('lt_pending'):
        return None
    _lobby['lt_pending'] = True
    call_later(SMART_REPLY_DELAY, _deliver_lt_base, player)
    return None


def _deliver_lt_base(player):
    _lobby.pop('lt_pending', None)
    if not _same_player(player):
        return
    version = lt_version()
    grid = lt_base_grid(player, version) if version is not None else []
    if not grid:
        log('local-lt-base-empty', version=version)
        show_offline_tip(LT_CLOSED_TIP, force=True)
        return
    try:
        # Set first: if the wrapped callback wants another shape, the next
        # open still draws the wheel (the client only asks while it is empty).
        player.dtsLTCurrBaseGrid = grid
        player.dtsLTCurrBaseGridHasGot = []
    except Exception:
        log_error('local-lt-base-attr-error')
    _deliver_callback(player, 'onGenerateDtsLTBaseTable', (grid, []), 0)
    log('local-lt-base-table', version=version, count=len(grid))


def backend_call(player, name, args=(), kwargs=None):
    """A backend route the hook calls itself: props, items and callbacks
    applied like a game RPC's reply."""
    return ask_backend(name, list(args), kwargs or {}, lambda reply: apply_backend_reply(player, name, reply))


def apply_backend_reply(player, name, reply):
    if not (isinstance(reply, dict) and reply.get('handled')):
        return None
    apply_server_props(player, reply.get('props'))
    push_server_items(player, reply.get('items'), reason=name)
    for item in list(reply.get('callbacks') or []):
        apply_server_callback(player, name, item)
    return reply


def install_sign_in_day():
    """iDtsSignin.checkDtsSigninNotSameDay compares the device clock; the
    backend decides the day (server clock, Philippine time)."""
    try:
        sign_class = __import__('iDtsSignin').iDtsSignin
    except Exception:
        log_error('local-sign-in-day-error')
        return False
    original = sign_class.__dict__.get('checkDtsSigninNotSameDay')
    if original is None or getattr(original, '_rl_server_day', False):
        return False

    def checkDtsSigninNotSameDay(self):
        if 'can_sign' in _lobby:
            state = welfare_cache()
            if state is not None and welfare_stale() and _lobby.get('welfare_resync') != state.get('expires'):
                # the PH day changed while in the lobby: one re-sync per day
                # (its reply redraws UIDtsSign through onSetSignAwardLevel)
                _lobby['welfare_resync'] = state.get('expires')
                backend_call(BigWorld.player(), WELFARE_STATE_RPC)
            return can_sign_today()
        return original(self)
    checkDtsSigninNotSameDay._rl_server_day = True
    sign_class.checkDtsSigninNotSameDay = checkDtsSigninNotSameDay
    return True


def ph_today():
    return time.strftime('%Y%m%d', time.gmtime(time.time() + PH_OFFSET))


def show_login_popups():
    """Entering the lobby: the 7-day login reward first (once a day, until
    claimed), then the event slider.  The login state is the cached copy
    (lobby props); only when it is missing (props late or lost, an older
    backend) or its PH day is over is it asked once, and the popup is decided
    when the answer lands (apply_welfare_state) - never by racing it."""
    player = BigWorld.player()
    if player is None:
        return False
    flush_pending_matches()             # their Activity progress, before you look at it
    backend_call(player, ACTIVITY_STATE_RPC)
    ask_manual_state(player)            # Special Distinction: once per entry, after the matches
    state = welfare_cache()
    if state is None or 'can_sign' not in state or welfare_stale():
        _lobby['sign_waiting'] = True
        backend_call(player, WELFARE_STATE_RPC)
        call_later(SIGN_IN_WAIT, sign_wait_over)
        return False
    return open_login_popup()


def sign_wait_over():
    """No login state came: the slider alone (the popup shows next entry)."""
    if _lobby.pop('sign_waiting', False):
        log('local-sign-in-state-late')
        show_event_ads()


def open_login_popup():
    if can_sign_today() and _lobby.get('sign_prompted') != ph_today():
        _lobby['sign_prompted'] = ph_today()
        try:
            import Globals
            Globals.uiMgr.enter_ui(SIGN_IN_SCREEN)
            call_later(SIGN_IN_POLL, ads_after_sign_in)
            return True
        except Exception:
            log_error('local-sign-in-screen-error')
    return show_event_ads()


def ads_after_sign_in():
    """The event slider once the 7-day login screen is closed."""
    try:
        import Globals
        screen = getattr(Globals.uiMgr, SIGN_IN_SCREEN, None)
        if screen is not None and getattr(screen, 'is_enter', False):
            call_later(SIGN_IN_POLL, ads_after_sign_in)
            return False
    except Exception:
        pass
    return show_event_ads()


# --------------------------------------------------------------------------
# ACTIVITY: the lobby "Activity" tile (Season Bounty picture, NEW! badge).
# The events on are a server calendar (backend welfare.activities); every
# event of this client has ended, so normally none is on and the panel shows
# "no events".  The game shows NEW! from Globals.HotActivityOpenState, which
# is runtime-only, so it came back every launch: here NEW! shows only while
# this account has not opened the panel for the current calendar version.
# --------------------------------------------------------------------------

ACTIVITY_STATE_RPC = 'rlActivityState'
ACTIVITY_SEEN_RPC = 'rlActivitySeen'
ACTIVITY_PANEL_SCREENS = ('UILimitWelfareController', 'UIHotActivity')
ACTIVITY_PANEL_MODULE = 'ui.main.UIMainActivityRightTop'


def activity_new_allowed():
    """Before the backend answers, or with no event on, NEW! never shows."""
    version = _lobby.get('activity_version') or ''
    return bool(version) and _lobby.get('activity_seen') != version


def _local_activity_state(player, active, version, seen):
    """rlActivityState: open the active entrances, close the ones that ended."""
    _lobby['activity_version'] = str(version or '')
    if _lobby.get('activity_seen') != _lobby['activity_version']:
        # an optimistic "seen" (mark_activity_seen) survives a stale answer
        _lobby['activity_seen'] = str(seen or '')
    opened = []
    try:
        import client_utils
    except Exception:
        log_error('local-activity-open-error')
        client_utils = None
    for row in active or []:
        try:
            jump_id = int(row['jump_id'])
            opened.append(jump_id)
            if client_utils is not None:
                client_utils.onMainActivityOpen(jump_id, int(row.get('starts') or 0))
        except Exception:
            log_error('local-activity-open-error', row=safe(row))
    for jump_id in _lobby.get('activity_open') or []:
        if jump_id in opened or client_utils is None:
            continue
        try:
            client_utils.onMainActivityClose(jump_id)
        except Exception:
            log_error('local-activity-close-error', jump_id=jump_id)
    _lobby['activity_open'] = opened
    log('local-activity-state', active=opened, version=_lobby['activity_version'],
        new=activity_new_allowed())
    refresh_activity_badge()


LOCAL_CALLBACKS['rlActivityState'] = _local_activity_state


def install_activity_badge():
    """UIMainActivityRightTop.updateActivityBadge: hide NEW! unless allowed
    (the hook never shows it; the game decides that as before)."""
    try:
        cls = __import__(ACTIVITY_PANEL_MODULE, fromlist=['UIMainActivityRightTop']).UIMainActivityRightTop
    except Exception:
        log_error('local-activity-badge-error')
        return False
    original = cls.__dict__.get('updateActivityBadge')
    if not isinstance(original, types.FunctionType) or getattr(original, '_rl_activity_badge', False):
        return False
    try:
        handlers = set(getattr(cls, '____messageHandlers__', None) or ())
    except Exception:
        handlers = set()
    if 'updateActivityBadge' in handlers or getattr(original, '____isMessageHandler__', False):
        # wrapping a libclaudia message handler breaks SendMessage dispatch
        log('local-activity-badge-skipped', reason='message-handler')
        return False

    def updateActivityBadge(self, *args, **kwargs):
        result = original(self, *args, **kwargs)
        if not activity_new_allowed():
            try:
                self.panelActivityRpNew.setVisible(False)
            except Exception:
                log_error('local-activity-badge-error')
        return result
    updateActivityBadge._rl_activity_badge = True
    updateActivityBadge._rl_original = original
    cls.updateActivityBadge = updateActivityBadge
    return True


def refresh_activity_badge():
    """Redraw the tile's badges now (the lobby may not be built yet)."""
    try:
        import Globals
        main = Globals.uiMgr.UIMain
        # UIMain._get_ui keeps the component as uiMainActivityRightTop
        tile = getattr(main, 'uiMainActivityRightTop', None)
        if tile is None:
            tile = main.GetComponent('UIMainActivityRightTop')
        tile.updateActivityBadge()
    except Exception:
        debug('local-activity-badge-refresh-skipped')


def mark_activity_seen():
    """The Activity panel was opened: NEW! is off for this calendar, saved
    per account.  Set here first so a lost packet cannot bring it back."""
    if not activity_new_allowed():
        return False
    version = _lobby['activity_version']
    _lobby['activity_seen'] = version
    player = BigWorld.player()
    if player is not None:
        backend_call(player, ACTIVITY_SEEN_RPC, [version])
    refresh_activity_badge()
    return True


HALL_PROP_DEPTH = 6


def hall_prop_tables():
    try:
        utils = __import__('dts_hall_prop_utils')
        legacy = __import__('helpers.character_scene', fromlist=['legacyProperties']).legacyProperties
        return utils, legacy
    except Exception:
        return None, None


def roll_random_item(entries, rand=None):
    """One PROP_ID of a RandomItem's PROP_LIST, weighted by PROBABILITY."""
    import random
    rand = rand or random.random
    weighted = []
    for entry in entries:
        try:
            weighted.append((int(entry.PROP_ID), max(0, int(entry.PROBABILITY))))
        except Exception:
            continue
    total = sum(weight for _prop, weight in weighted)
    if not total:
        return None
    point = rand() * total
    for prop_id, weight in weighted:
        point -= weight
        if point < 0:
            return prop_id
    return weighted[-1][0]


def open_hall_prop(prop_id, depth=0, rand=None):
    """What a store good gives, as the server opened it: a GiftBag gives its
    PROP_LIST, a RandomItem one weighted roll of its PROP_LIST."""
    utils, legacy = hall_prop_tables()
    if utils is None or depth >= HALL_PROP_DEPTH:
        return [prop_id]
    try:
        kind = utils.getDtsHallPropType(prop_id)
        contents = list(legacy.getDtsHallPropData(prop_id).PROP_TYPE.PROP_LIST)
    except Exception:
        return [prop_id]
    if kind == 'GiftBag':
        opened = []
        for content in contents:
            opened.extend(open_hall_prop(int(content), depth + 1, rand))
        return opened
    if kind == 'RandomItem':
        rolled = roll_random_item(contents, rand)
        return open_hall_prop(rolled, depth + 1, rand) if rolled is not None else []
    return [prop_id]


MALL_REPLY_DELAY = 0.1


def reply_mall_goods(player, callback_name, build_args):
    """Mall screens ask while they are still entering, and iMall only passes
    the goods to a screen that is_enter: answer a moment later, as the
    server did."""
    if not callable(getattr(player, callback_name, None)):
        return False
    call_later(MALL_REPLY_DELAY, deliver_mall_goods, player, callback_name, build_args)
    return True


def deliver_mall_goods(player, callback_name, build_args):
    callback = getattr(player, callback_name, None)
    if not callable(callback):
        return False
    goods = mall_goods(player)
    try:
        callback(*build_args(dict(goods)))
    except Exception:
        log_error('local-client-data-reply-error', callback=callback_name)
        return False
    log('local-client-data-reply', callback=callback_name, size=len(goods))
    return True


@rpc_handler('queryAvailableMallGoods')
def _rpc_query_mall(player, *args):
    reply_mall_goods(player, 'onQueryAvailableMallGoods', lambda data: [data])


def mall_location_fields(types):
    """mall_utils.GoodsLocationTypeToPropertieDataField: the table flags of
    the screens a GoodsLocationType bit mask names (0 = every screen)."""
    try:
        fields = __import__('mall_utils').GoodsLocationTypeToPropertieDataField
        mask = int(types or 0)
    except Exception:
        return None
    if not mask:
        return None
    return [field for bit, field in fields.items() if mask & int(bit)]


def mall_goods_for(player, types, goods):
    """The goods of the screens queryAvailableMallGoodsByType asked for
    (Packs gets the packs, Looks the clothes...), as the server sent them."""
    fields = mall_location_fields(types)
    if fields is None:
        return goods
    properties = mall_properties(player)
    picked = {}
    for goods_id, value in goods.items():
        try:
            row = properties.getMallData(goods_id)
        except Exception:
            continue
        if any(mall_field(row, field, False) for field in fields):
            picked[goods_id] = value
    return picked


@rpc_handler('queryAvailableMallGoodsByType')
def _rpc_query_mall_by_type(player, types=None, *args):
    reply_mall_goods(player, 'onQueryAvailableMallGoodsByType',
                     lambda data: [types, mall_goods_for(player, types, data)])


@rpc_handler('queryAvailableMallGoodsForAppearanceMall')
def _rpc_query_appearance_mall(player, *args):
    reply_mall_goods(player, 'onQueryAvailableMallGoodsForAppearanceMall', lambda data: [data])


_supplement_asks = {'waiting': []}


@rpc_handler('queryAvailableSupplement')
def _rpc_query_supplement(player, *args, **kwargs):
    """Backend first (its catalog knows the real supplement ids); the old
    guess from the game's tables only when the backend cannot answer.  Both
    are delivered later: every supply tab asks while it is being built - one
    question goes out, every tab gets its answer."""
    waiting = _supplement_asks['waiting']
    waiting.append(player)
    if len(waiting) > 1:
        return None
    ask_backend('queryAvailableSupplement', args, kwargs, supplement_replies)
    return None


def supplement_replies(reply):
    import copy
    waiting, _supplement_asks['waiting'] = _supplement_asks['waiting'], []
    for number, player in enumerate(waiting):
        supplement_reply(player, reply if number == 0 else copy.deepcopy(reply))   # fixed up in place


def supplement_reply(player, reply):
    if isinstance(reply, dict) and reply.get('handled'):
        fix_supplement_reply(reply)
        call_later(_reply_delay(reply) or SMART_REPLY_DELAY, _deliver_server_reply, player,
                   'queryAvailableSupplement', reply)
        return None
    data = {}
    try:
        resolved = resolve_feature_data(player, 'supplement')
        data = _plain_supplement_entries(resolved[2] if resolved else {})
    except Exception:
        log_error('local-supplement-fallback-error')
    log('local-supplement-query-fallback', size=len(data), backend=reply is not None)
    call_later(SMART_REPLY_DELAY, _deliver_callback, player, 'onQueryAvailableSupplement',
               (data,), 0)
    return None


@rpc_handler('createCharacter')
def _rpc_create_character(player, character_id, input_name, *rest):
    log('local-rpc-create-character-ignored', name=safe(input_name))
    return None


def _is_match_request(name):
    # setHasAlreadyShowMonthSupply: the 'ready' in 'Already' is no START
    name = name.replace('Already', '').replace('already', '')
    return bool(MATCH_WORDS.search(name)) and bool(MATCH_ACTIONS.search(name))


# --------------------------------------------------------------------------
# Smart replies: when nothing answers a server call, run the client's reply
# callback with values shaped by its parameter names (never the request args
# as-is: a CB expecting a dict must not get the gid).
# --------------------------------------------------------------------------

GID_PARAM_NAMES = ('gid', 'uid', 'targetgid', 'playergid', 'entityid', 'avatarid', 'srcgid',
                   'dstgid', 'fromgid', 'togid', 'othergid', 'ownergid', 'friendgid',
                   'targetuid', 'playeruid', 'roleid', 'playerid', 'targetid', 'avatargid')
NAME_PARAM_NAMES = ('name', 'nickname', 'playername', 'rolename', 'nick', 'targetname')
SUCCESS_PARAM_NAMES = ('succ', 'ok', 'success', 'succeed', 'issucc', 'issuccess', 'isok',
                       'bsucc', 'bok', 'bsuccess')
STATUS_PARAM_NAMES = ('ret', 'code', 'err', 'errno', 'status', 'retcode', 'errcode',
                      'error', 'errorcode', 'rtn')
INDEX_PARAM_WORDS = ('page', 'idx', 'index', 'type', 'kind')
LIST_PARAM_ENDINGS = ('list', 'ids', 'gids', 'array', 'arr', 'lst', 'items', 'comments',
                      'records', 'details')
DICT_PARAM_WORDS = ('dict', 'info', 'data', 'record', 'detail', 'result', 'map', 'comment',
                    'space', 'base')
REPLY_DEFAULTS = {'creditScore': 100, 'level': 1, 'baseLevel': 1, 'lv': 1}
# Dict parameters that really are the player's own profile: only these get a
# reply pre-filled with gid/nickname/level...  Every other data dict (stats,
# weapons, records, *Info) starts EMPTY, or the UI lists the profile keys as
# stats rows / fake weapons.
PROFILE_PARAM_NAMES = ('playerinfo', 'baseinfo', 'profile', 'userinfo', 'selfinfo', 'myinfo',
                       'roleinfo', 'playerprofile', 'selfprofile', 'playerbaseinfo',
                       'avatarinfo', 'selfbaseinfo', 'mybaseinfo')
NATION_PARAM_NAMES = ('nationalflag', 'nation', 'nationflag', 'countrycode', 'country',
                      'nationcode')
SERVER_PARAM_NAMES = ('serverid', 'hostnum', 'hostid', 'svrid', 'serverno',
                      'curserverid', 'homeserverid')
# Fields shown as text: a missing one must print as '' (not 0 or '{}').
TEXT_NAMES = ('sign', 'signature', 'desc', 'text', 'title', 'msg', 'url', 'icon', 'head',
              'content', 'message', 'description', 'remark', 'intro', 'slogan', 'motto',
              'headurl', 'headicon', 'headimg', 'avatarurl', 'photo', 'str', 'tips', 'tip')
TEXT_ENDINGS = ('name', 'sign', 'signature', 'desc', 'description', 'text', 'title', 'msg',
                'message', 'url', 'content', 'remark', 'intro', 'str', 'string', 'tips')
NUMBER_ENDINGS = ('id', 'idx', 'num', 'cnt', 'count', 'times', 'type', 'level', 'lv',
                  'score', 'time', 'stamp', 'index', 'rank', 'value', 'exp')
_smart_logged = set()
_scan_logged = set()
_scan_cache = {}


def _local_profile(player=None):
    """Known profile of the local player: backend state, then live objects."""
    profile = {'gid': DEFAULT_GID, 'nickname': 'LocalPlayer', 'level': 1, 'baseLevel': 1,
               'characterType': DEFAULT_CHARACTER_TYPE, 'creditScore': 100}
    try:
        state = load_state().get('player', {}) or {}
    except Exception:
        state = {}
    try:
        profile['gid'] = local_player.gid
        profile['nickname'] = local_player.nickname
        profile['characterType'] = local_player.characterId
    except Exception:
        pass
    for key in ('gid', 'nickname', 'level', 'baseLevel', 'characterType', 'creditScore'):
        value = state.get(key)
        if value not in (None, ''):
            profile[key] = value
    if player is not None:
        for key in ('gid', 'nickname', 'level', 'baseLevel', 'characterType', 'creditScore'):
            try:
                value = getattr(player, key, None)
            except Exception:
                value = None
            if value not in (None, '') and not callable(value):
                profile[key] = value
    try:
        profile['gid'] = int(profile['gid'])
    except Exception:
        profile['gid'] = DEFAULT_GID
    return profile


def _current_server_id():
    """Id of the server the account logged in to (10501...), else 0."""
    for source in (lambda: load_state().get('server'), lambda: _backend.get('server')):
        try:
            server = source() or {}
            value = server.get('id') if isinstance(server, dict) else None
            if value not in (None, ''):
                return int(value)
        except Exception:
            pass
    return 0


def _bool_name(name):
    for prefix in ('is', 'has', 'can', 'need', 'enable'):
        if name == prefix or (name.startswith(prefix) and name[len(prefix):][:1].isupper()):
            return True
    return False


def _is_text_name(name):
    """Name of a field the game shows as text (sign, desc, title, headUrl...)."""
    low = name.lower()
    if _bool_name(name) or low.endswith(NUMBER_ENDINGS):
        return False
    return low in TEXT_NAMES or low in NATION_PARAM_NAMES or low.endswith(TEXT_ENDINGS)


def _reply_default(name, profile=None):
    """Safe value for a field the offline reply does not know: '' for text,
    0 for numbers, an empty LocalReply only for dict-like names."""
    low = name.lower()
    if name in REPLY_DEFAULTS:
        return REPLY_DEFAULTS[name]
    if low in NAME_PARAM_NAMES or low in ('playername', 'basenickname'):
        return (profile or {}).get('nickname', 'LocalPlayer')
    if low in ('gid', 'uid', 'entityid'):
        return (profile or {}).get('gid', DEFAULT_GID)
    if low in NATION_PARAM_NAMES:
        return ''
    if low in SERVER_PARAM_NAMES:
        return _current_server_id()
    if low in ('dtslevel', 'playerlevel'):
        return (profile or {}).get('level', 1) or 1
    if low.startswith('credit') and low.endswith('score'):
        return 100
    if low in ('charactertype', 'dtscharactertype', 'charactertypeid', 'charactorid', 'characterid'):
        return (profile or {}).get('characterType', DEFAULT_CHARACTER_TYPE)
    if low in ('gender', 'dtsappearancegender', 'sex'):
        return 1
    if _is_text_name(name):
        return ''
    known, value = _team_member_default(name)
    if known:
        if isinstance(value, dict):
            return _nested_reply(profile)
        return value
    return 0


def _nested_reply(profile):
    """An empty LocalReply for nested sections (data['Data'], ...)."""
    reply = LocalReply()
    reply.__dict__['_rl_profile'] = dict(profile or {})
    return reply


class LocalReply(dict):
    """Reply payload for a callback whose real server data is unknown: any
    missing key (or attribute) reads as a safe default for its name."""

    def __init__(self, *args, **kwargs):
        dict.__init__(self, *args, **kwargs)
        self.__dict__['_rl_profile'] = dict(self)

    # A missing value formatted into a label ('%s' % data.sign) shows as ''
    # instead of '{}'.  __repr__ stays dict's, so logs (safe() uses repr)
    # still show the real contents; a filled reply prints like a dict.
    def __str__(self):
        return '' if not self else dict.__repr__(self)

    def __unicode__(self):
        return u'' if not self else u'%s' % dict.__repr__(self)

    def __missing__(self, name):
        if isinstance(name, (int, long_type)) and not isinstance(name, bool):
            return _nested_reply(self.__dict__.get('_rl_profile'))   # data[season][...]
        return _reply_default(str(name), self.__dict__.get('_rl_profile'))

    def get(self, name, default=None):
        # Screens read fields with .get(); a None there left designer
        # placeholder numbers (13, 234m, 68...) on screen.
        if name in self:
            return dict.__getitem__(self, name)
        if default is not None:
            return default
        return self.__missing__(name)

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return self[name]

    # Used where the server sent a number: behave like 0.
    def __int__(self):
        return 0
    __long__ = __int__

    def __float__(self):
        return 0.0

    def __index__(self):
        return 0

    def _number(self, other):
        return isinstance(other, (int, long_type, float)) and not isinstance(other, bool)

    def __add__(self, other):
        return other if self._number(other) else NotImplemented
    __radd__ = __add__

    def __sub__(self, other):
        return -other if self._number(other) else NotImplemented

    def __rsub__(self, other):
        return other if self._number(other) else NotImplemented

    def __mul__(self, other):
        return 0 if self._number(other) else NotImplemented
    __rmul__ = __mul__

    def __div__(self, other):
        return 0 if self._number(other) else NotImplemented
    __truediv__ = __floordiv__ = __mod__ = __div__

    def __neg__(self):
        return 0

    def __lt__(self, other):
        return (0 < other) if self._number(other) else NotImplemented

    def __le__(self, other):
        return (0 <= other) if self._number(other) else NotImplemented

    def __gt__(self, other):
        return (0 > other) if self._number(other) else NotImplemented

    def __ge__(self, other):
        return (0 >= other) if self._number(other) else NotImplemented

    def __setattr__(self, name, value):
        self[name] = value


def local_reply(player=None):
    """Reply pre-filled with the player's profile: only for parameters that
    are the profile itself (playerInfo, baseInfo...)."""
    return LocalReply(_local_profile(player))


def empty_reply(profile=None, player=None):
    """Empty data dict (stats, weapons, records...): no keys, but missing
    nickname/gid lookups still read the player's profile."""
    return _nested_reply(profile if profile is not None else _local_profile(player))


def _int_arg(value):
    return isinstance(value, (int, long_type)) and not isinstance(value, bool)


DICT_METHOD_NAMES = frozenset(('items', 'iteritems', 'keys', 'iterkeys', 'values', 'itervalues',
                               'get', 'has_key', 'setdefault'))


def _smart_value(param, player, request_args, used, profile, uses=(), callback=''):
    low = param.lower()

    def next_int():
        for index, value in enumerate(request_args):
            if index not in used and _int_arg(value):
                used.add(index)
                return value
        return None

    if low == 'identifytagid':                      # ends in 'gid' but is no gid
        return 0
    if param in SUPPLY_PARAM_DEFAULTS:              # supply dicts named *Times
        return MISSING_PLAYER_DEFAULTS[param]()
    if low.startswith('avail') and low not in ('avail', 'available', 'availble') and \
            not low.endswith(AVAIL_SCALAR_SUFFIXES):
        return {}                                   # availableOpenSupplyGift: a dict
    if low in GID_PARAM_NAMES or low.endswith(('gid', 'uid')):
        value = next_int()
        return profile['gid'] if value is None else value
    if low in NATION_PARAM_NAMES:
        return ''                                   # country code: '' / 'PH'
    if low in SERVER_PARAM_NAMES:
        return _current_server_id()
    if low in ('dtslevel', 'level', 'lv', 'playerlevel'):
        return profile.get('level', 1) or 1
    if low == 'baselevel':
        return profile.get('baseLevel', 1) or 1
    if low in ('gender', 'sex', 'dtsappearancegender'):
        return 1
    if low == 'sharesourcetype':
        return request_args[0] if request_args and _int_arg(request_args[0]) else 0
    if low.startswith('credit') or (low == 'score' and 'credit' in callback.lower()):
        return 100                                  # queryCreditScoreCB(score, ...)
    if 'score' in low:
        return 0
    if low in SUCCESS_PARAM_NAMES:
        return True
    for prefix in ('is', 'has', 'can'):
        if low == prefix or (param.startswith(prefix) and param[len(prefix):][:1].isupper()):
            return False
    if 'visited' in low or 'flag' in low:
        return False
    if low in STATUS_PARAM_NAMES or low.endswith(('code', 'errno', 'status')):
        return 0
    if low.endswith(('level', 'lv', 'lvl')):
        return 1
    if low in NAME_PARAM_NAMES or low.endswith('name'):
        return profile['nickname']
    if _is_text_name(param):
        return ''
    if any(word in low for word in INDEX_PARAM_WORDS):
        value = next_int()
        return 0 if value is None else value
    if low.endswith(LIST_PARAM_ENDINGS) or 'list' in low:
        return []
    if low in PROFILE_PARAM_NAMES:
        return LocalReply(profile)
    if any(word in low for word in DICT_PARAM_WORDS):
        return empty_reply(profile)
    if DICT_METHOD_NAMES.intersection(uses):
        # e.g. getHighestProficiencyWeaponsCB(weapons): body sorts .items(),
        # so it must be empty or the profile keys become fake weapons.
        return empty_reply(profile)
    return 0


def smart_reply_args(player, function, request_args):
    """Positional args for reply callback ``function`` chosen by parameter
    name; only required parameters are filled (optional ones keep defaults)."""
    raw = getattr(function, 'im_func', None) or getattr(function, '__func__', None) or function
    code = getattr(raw, 'func_code', None) or getattr(raw, '__code__', None)
    if code is None:
        return []
    params = list(code.co_varnames[:code.co_argcount])
    if params and params[0] in ('self', 'cls'):
        params = params[1:]
    defaults = getattr(raw, 'func_defaults', None) or getattr(raw, '__defaults__', None) or ()
    required = params[:len(params) - len(defaults)]
    profile = _local_profile(player)
    used = set()
    uses = set()
    for nested in _code_objects(raw):
        uses.update(nested.co_names)
    callback = getattr(raw, '__name__', '') or ''
    return [_smart_value(param, player, list(request_args or ()), used, profile, uses, callback)
            for param in required]


def _scan_reply_candidates(player, name, tried):
    """Reply-looking methods of the player class whose name contains the
    call's core name (requireBaseInfo -> ...baseinfo...)."""
    key = (type(player), name)
    if key in _scan_cache:
        return list(_scan_cache[key])   # dir() of the player class: once per class and call name
    core = _reply_core(name).lower()
    if len(core) < 4:
        _scan_cache[key] = ()
        return []
    found = []
    try:
        names = dir(type(player))
    except Exception:
        names = []
    for attr in names:
        low = attr.lower()
        if attr == name or attr in tried or core not in low:
            continue
        if not (low.startswith('on') or low.endswith(('cb', 'callback'))):
            continue
        if callable(getattr(player, attr, None)):
            found.append(attr)
    _scan_cache[key] = tuple(found)
    if name not in _scan_logged:
        _scan_logged.add(name)
        log('local-rpc-reply-candidates', method=name, core=core, found=found)
    return found


def _smart_reply(player, name, args):
    """Run the first reply callback that accepts smart args; True if one ran."""
    static = _echo_candidates(name)
    candidates = [c for c in static if callable(getattr(player, c, None))]
    if not candidates:
        candidates = _scan_reply_candidates(player, name, static)
    for candidate in candidates:
        target = getattr(player, candidate, None)
        if not callable(target):
            continue
        try:
            reply_args = smart_reply_args(player, target, args)
        except Exception:
            log_error('local-rpc-echo-error', method=name, callback=candidate)
            return True
        fields = {'method': name, 'callback': candidate,
                  'args': [type(value).__name__ for value in reply_args]}
        try:
            code = getattr(target, 'func_code', None) or getattr(target, '__code__', None)
            names = list(code.co_varnames[:code.co_argcount])
            if names and names[0] in ('self', 'cls'):
                names = names[1:]
            fields['arg_names'] = names[:len(reply_args)]
        except Exception:
            pass
        if name not in _smart_logged:
            try:
                fields['signature'] = callback_signature(
                    getattr(target, 'im_func', None) or getattr(target, '__func__', None) or target)
            except Exception:
                fields['signature'] = None
        try:
            result = target(*reply_args)
        except TypeError:
            debug('local-rpc-echo-signature', method=name, callback=candidate,
                  error=traceback.format_exc())
            continue
        except Exception as error:
            if 'not picked up' in _error_text(error):
                # the screen that shows this reply is not built yet
                debug('local-rpc-reply-early', method=name, callback=candidate)
                return 'retry'
            log_error('local-rpc-echo-error', method=name, callback=candidate)
            return True
        fields['result'] = safe(result, 300)
        if name not in _smart_logged or DEBUG:
            _smart_logged.add(name)
            log('local-rpc-smart-reply', **fields)
        return True
    return False


# Stats (Meet -> STATS): UIBattleGroundRecordPanel.onGetRecordData picks
# data[RecordTypeToName[type]] and reads these fields (screen_code.json).
RECORD_FIELDS = ('fightCount', 'fight-count', 'top5Rate', 'top5-rate', 'not-rate', 'win-count',
                 'winCount', 'firstNum', 'totalCoin', 'addCoin', 'totalYB', 'addYB', 'headShot',
                 'hitCount', 'headShotRate', 'fireCount', 'hitRate', 'maxTotalCoin', 'maxAddCoin',
                 'maxRoundKill', 'maxFightTime', 'maxTotalYB', 'maxAddYB', 'maxKillDis',
                 'maxRoundMoveDis', 'maxRoundHealCount', 'killCount', 'assistCount',
                 'maxRoundAssist', 'damage', 'surviveTime')


def zero_record(profile=None):
    record = _nested_reply(profile)
    for field in RECORD_FIELDS:
        dict.__setitem__(record, field, 0)
    return record


class RecordReply(LocalReply):
    """Record data: every record type (known or not) is an all-zero record."""

    def __missing__(self, name):
        return zero_record(self.__dict__.get('_rl_profile'))


def record_type_names():
    names = []
    try:
        import const
        mapping = getattr(const, 'RecordTypeToName', None) or {}
        names = list(mapping.values()) + list(mapping.keys())
    except Exception:
        pass
    return names


# A solo ranked match counts in these records (const.RecordTypeToName):
# total / ranked, overall / solo, all-time / season; each N+1 ("Rank...")
# is read for the headline numbers.
MATCH_RECORD_TYPES = (1, 3, 11, 13, 31, 33, 41, 43)
RECORDS_KEY = 'records'
SUM_FIELDS = (('fightCount', None), ('kill', 'kills'), ('killCount', 'kills'), ('damage', 'damage'),
              ('fightTime', 'surviveTime'), ('surviveTime', 'surviveTime'), ('collectCount', 'collectCount'),
              ('headShot', 'headshots'), ('hitCount', 'hits'), ('fireCount', 'fired'))
MAX_FIELDS = (('maxRoundKill', 'kills'), ('maxFightTime', 'surviveTime'), ('maxKillDis', 'maxKillDis'),
              ('maxRoundMoveDis', 'moveDis'))


def stored_records():
    try:
        records = load_state().get('lobby', {}).get(RECORDS_KEY)
    except Exception:
        records = None
    return dict(records) if isinstance(records, dict) else {}


def add_match(record, match):
    """One match into a record's totals and bests."""
    record = dict(record or {})
    won = int(match.get('rank', 0)) == 1
    for field, source in SUM_FIELDS:
        record[field] = record.get(field, 0) + (1 if source is None else match.get(source, 0))
    for field, source in MAX_FIELDS:
        record[field] = max(record.get(field, 0), match.get(source, 0))
    record['firstNum'] = record.get('firstNum', 0) + (1 if won else 0)
    record['winCount'] = record['firstNum']
    record['dead'] = record.get('dead', 0) + (0 if won else 1)
    record['top5'] = record.get('top5', 0) + (1 if int(match.get('rank', 99)) <= 5 else 0)
    fights = max(1, record['fightCount'])
    record['top5Rate'] = int(round(record['top5'] * 100.0 / fights))
    record['headShotRate'] = int(round(record.get('headShot', 0) * 100.0 / max(1, record.get('hitCount', 0))))
    record['hitRate'] = int(round(record.get('hitCount', 0) * 100.0 / max(1, record.get('fireCount', 0))))
    return record


def exp_to_next(level):
    try:
        row = __import__('shared.tables', fromlist=['getExpLevelTable']).getExpLevelTable(int(level))
        return int(row['levelExp'])
    except Exception:
        return 0


def gain_exp(level, exp, gained):
    """Level and experience after ``gained`` (data_exp_level_table: each
    level's levelExp leads to the next)."""
    level, exp = max(1, int(level)), max(0, int(exp)) + max(0, int(gained))
    while True:
        need = exp_to_next(level)
        if need <= 0 or exp < need:
            return level, exp
        exp -= need
        level += 1


def record_match(match):
    """Battle hook, at the result screen: the match goes into the STATS
    records and its experience into the level."""
    records = stored_records()
    names = record_type_names_by_id()
    for record_type in MATCH_RECORD_TYPES:
        name = names.get(record_type, str(record_type))
        records[name] = add_match(records.get(name), match)
        rank_name = names.get(record_type + 1)
        if rank_name:
            records[rank_name] = records[name]
    lobby = load_state().get('lobby', {})
    weapons = merge_weapon_stats(lobby.get(WEAPON_STATS_KEY), match.get('weapons'))
    # one save: the records, the weapons and the experience go together
    level, exp = add_exp(match.get('exp', 0), {RECORDS_KEY: records, WEAPON_STATS_KEY: weapons})
    player = _lobby.get('player')
    if match.get('weapons'):
        show_weapon_proficiency(player, weapons)
        # the best-weapon title is the server's to say (other players count too): asked again
        clear_rpc_cache(('getHighestProficiencyWeapons',), 'battle')
    report_match_activity(match)
    log('local-match-recorded', level=level, exp=exp, kills=match.get('kills'), rank=match.get('rank'))
    return records


def add_exp(gained, lobby_changes=None, player=None):
    """Experience into the level (a match, a claimed Activity task): saved
    durably, then shown the game's own way (onAddDtsExp: bar, level-up popup)."""
    state = load_state()
    lobby, player_state = state.get('lobby', {}), state.get('player', {})
    old_level = int(player_state.get('level', 1) or 1)
    level, exp = gain_exp(old_level, lobby.get('dtsExp', 0) or 0, gained)
    changes = dict(lobby_changes or {})
    changes['dtsExp'] = exp
    save_state_durable(lobby=changes)
    if level != old_level:
        save_state_durable(player={'level': level, 'baseLevel': level})
    if player is None:
        player = _lobby.get('player')
    shown = getattr(player, 'onAddDtsExp', None)
    try:
        if callable(shown):
            shown(exp, level, level > old_level)     # iDtsLevelSystem: level, bar, level-up popup
    except Exception:
        log_error('local-match-exp-error')
    for name, value in (('level', level), ('baseLevel', level), ('exp', exp)):
        try:
            setattr(player, name, value)
        except Exception:
            pass
    return level, exp


# What the backend's Activity tasks read from a match (features/activity.py);
# the per-weapon totals stay here (they are saved with the lobby state).
ACTIVITY_MATCH_KEYS = ('match_id', 'map', 'rank', 'total', 'kills', 'damage', 'surviveTime', 'moveDis',
                       'collectCount', 'vehicle', 'friends',
                       # the Special Distinction missions (features/manual.py): team size,
                       # kills per gun, battle items picked up and used
                       'teamSize', 'ranked', 'weapons', 'pickups', 'uses')
PENDING_MATCHES_KEEP = 10
_pending_matches = []


def report_match_activity(match):
    """The match result moves the Activity tasks (Rookie, Intrepid...).  Sent
    at the result screen without waiting (ask_backend is not gated in a
    battle); unanswered it waits in _pending_matches and show_login_popups
    sends it again - the backend counts a match id once.  In a battle the
    reply is not applied: the lobby's props carry the new state."""
    summary = dict((key, match[key]) for key in ACTIVITY_MATCH_KEYS if key in match)
    if not summary:
        return False
    return _send_match_activity(_welfare_gid(), summary)


def _send_match_activity(gid, summary):
    def done(reply):
        if not (isinstance(reply, dict) and reply.get('handled')):
            if len(_pending_matches) < PENDING_MATCHES_KEEP:
                _pending_matches.append((gid, summary))
            return None
        player = _lobby.get('player')
        if player is not None and not in_battle() and _welfare_gid() == gid:
            apply_backend_reply(player, DAILY_ACTIVITY_MATCH_RPC, reply)
        return reply
    return ask_backend(DAILY_ACTIVITY_MATCH_RPC, [summary], {}, done)


def flush_pending_matches():
    """Matches whose report was lost (this account's only), sent again."""
    gid = _welfare_gid()
    waiting = [entry for entry in _pending_matches if entry[0] == gid]
    _pending_matches[:] = [entry for entry in _pending_matches if entry[0] != gid]
    for _gid, summary in waiting:
        _send_match_activity(gid, summary)
    return len(waiting)


# Per-weapon battle totals (lobby JSON weaponStats, {str gunID: {kills,
# damage, hits, fired}}): the backend computes every player's weapon
# proficiency and best-weapon title from them (features/profile.py).  The
# rule is mirrored here so the weapon screens show a match at once instead of
# at the next lobby entry; INITIAL is rank_list_utils.INITIAL_WEAPON_PROFICIENCY.
WEAPON_STATS_KEY = 'weaponStats'
WEAPON_FIELDS = ('kills', 'damage', 'hits', 'fired')
PROFICIENCY_INITIAL = 1000
PROFICIENCY_MAX = 99999
PROFICIENCY_PER_KILL = 10
PROFICIENCY_DAMAGE_STEP = 100


def merge_weapon_stats(saved, match):
    """saved + one match's totals (both {gunID: {field: n}}), keys as str."""
    merged = {}
    for source in (saved, match):
        if not isinstance(source, dict):
            continue
        for gun, counts in source.items():
            if not isinstance(counts, dict):
                continue
            entry = merged.setdefault(str(gun), {})
            for field in WEAPON_FIELDS:
                try:
                    value = max(0, int(counts.get(field) or 0))
                except (TypeError, ValueError):
                    value = 0
                if value:
                    entry[field] = entry.get(field, 0) + value
    return dict((gun, entry) for gun, entry in merged.items() if entry)


def weapon_proficiency_props(stats):
    """iWeaponIllustration.onUpdateWeaponProficiency's three dicts, int-keyed."""
    proficiency, damage, hitrate = {}, {}, {}
    for gun, counts in (stats or {}).items():
        try:
            gun_id = int(gun)
        except (TypeError, ValueError):
            continue
        value = (PROFICIENCY_INITIAL + counts.get('kills', 0) * PROFICIENCY_PER_KILL
                 + counts.get('damage', 0) // PROFICIENCY_DAMAGE_STEP)
        proficiency[gun_id] = max(0, min(PROFICIENCY_MAX, value))
        damage[gun_id] = counts.get('damage', 0)
        hitrate[gun_id] = counts.get('hits', 0) * 100 // max(1, counts.get('fired', 0))
    return proficiency, damage, hitrate


def show_weapon_proficiency(player, stats):
    if player is None:
        return False
    values = weapon_proficiency_props(stats)
    update = getattr(player, 'onUpdateWeaponProficiency', None)
    try:
        if callable(update):
            update(*values)
        else:
            player.weaponProficiency, player.weaponAccumulateDamage, player.weaponHitrate = values
        return True
    except Exception:
        log_error('local-weapon-proficiency-error')
        return False


def record_type_names_by_id():
    try:
        import const
        return dict(getattr(const, 'RecordTypeToName', None) or {})
    except Exception:
        return {}


def record_reply(profile, played):
    """onGetRecordData's data: every record type, the played ones filled in
    (the panel reads data[RecordTypeToName[type]] for any type)."""
    data = RecordReply()
    data.__dict__['_rl_profile'] = profile
    for name in record_type_names():
        record = zero_record(profile)
        for field, value in (played.get(name) or {}).items():
            dict.__setitem__(record, field, value)
        dict.__setitem__(data, name, record)
    dict.__setitem__(data, 'top5Rate', 0)
    return data


def _is_other_gid(gid, profile):
    try:
        return _int_arg(gid) and int(gid) != int(profile['gid'])
    except Exception:
        return False


@rpc_handler('requireRecordData')
def _rpc_require_record(player, gid=None, *args):
    profile = _local_profile(player)
    if _is_other_gid(gid, profile):
        blank = record_reply({'gid': gid, 'nickname': ''}, {})
        return ask_other_profile(player, 'requireRecordData', (gid,) + tuple(args), 'onGetRecordData',
                                 (gid, blank))
    # your own: the local state already has the last match, saved or not
    gid = profile['gid'] if gid is None else gid   # echo what the screen asked for
    data = record_reply(profile, stored_records())
    call_later(SMART_REPLY_DELAY, _deliver_callback, player, 'onGetRecordData', (gid, data), 0)


def _local_record_data(player, gid, records):
    """Another player's STATS from the backend (ranking.records)."""
    data = record_reply({'gid': gid, 'nickname': ''}, records if isinstance(records, dict) else {})
    call_later(0, _deliver_callback, player, 'onGetRecordData', (gid, data), 0)


LOCAL_CALLBACKS['rlRecordData'] = _local_record_data


def _local_own_flag(player, code):
    """/flag changed your flag on the backend: the cached state (own_flag,
    your own card) follows now, not at the next relog."""
    load_state().setdefault('lobby', {})['nationalFlag'] = to_native_str(code or '')


LOCAL_CALLBACKS['rlOwnFlag'] = _local_own_flag


# --------------------------------------------------------------------------
# Friends > Meet profile tabs (backend features/profile.py), any gid
# --------------------------------------------------------------------------

def intimate_ids():
    """The intimate relationship IDs of the game's own table (Soulmate, Bro...)."""
    try:
        utils = __import__('intimacy_utils')
        return sorted(int(key) for key in utils.getIntimateRelationshipImportanceDict().keys())
    except Exception:
        pass
    try:
        legacy = __import__('helpers.character_scene', fromlist=['legacyProperties']).legacyProperties
        return sorted(int(row[0]) for row in legacy.iterIntimateRelationshipData())
    except Exception:
        return []


def complete_intimate_info(info):
    """{intimateID: {gid: (state, name)}} with every ID of the table present:
    the panel reads info[id] for each (marry_utils.INTIMATE_IDNEX for the true
    love), and an empty dict shows the "hidden by the player" tip."""
    complete = {}
    for intimate_id, members in (info.items() if isinstance(info, dict) else []):
        if isinstance(members, dict):
            complete[intimate_id] = dict((gid, tuple(value) if isinstance(value, list) else value)
                                         for gid, value in members.items())
    for intimate_id in intimate_ids():
        complete.setdefault(intimate_id, {})
    return complete


def _local_intimate_info(player, gid, info, requests, others=False):
    """requestIntimateRelationshipInfo (your own: the list and the requests)
    or requestOthersIntimateRelationshipInfo(gid).  The candidate scan once
    answered your own request with the 'others' callback, filled with your
    profile keys as intimate IDs."""
    info = complete_intimate_info(info)
    if others:
        call_later(0, _deliver_callback, player, 'onGetOthersIntimateRelationshipInfo', (gid, info), 0)
    else:
        call_later(0, _deliver_callback, player, 'onUpdateIntimateRelationship',
                   (info, list(requests or [])), 0)


LOCAL_CALLBACKS['rlIntimateInfo'] = _local_intimate_info


def _local_marriage_info(player, gid, info):
    """UIMarriageSpace.callbackFillMarriageInfo: a key the backend did not send
    reads a default from this card, never from your own profile."""
    info = info if isinstance(info, dict) else {}
    call_later(0, _deliver_callback, player, 'onGetOthersMarriageInfo', (gid, _deep_reply(info, info)), 0)


LOCAL_CALLBACKS['rlMarriageInfo'] = _local_marriage_info


def _local_proficiency(player, gid, weapons):
    """The best-weapon title: UIMeetPage reads getWeaponIllustrationData(id)
    [NAME] for the IDs it gets, so an ID the weapon table does not know (a
    battle-only gun) is dropped instead of raising there."""
    known = {}
    try:
        legacy = __import__('helpers.character_scene', fromlist=['legacyProperties']).legacyProperties
        lookup = legacy.getWeaponIllustrationData
    except Exception:
        lookup = None
    for gun, value in (weapons.items() if isinstance(weapons, dict) else []):
        try:
            if lookup is None or lookup(int(gun)):
                known[int(gun)] = value
        except Exception:
            continue
    call_later(0, _deliver_callback, player, 'getHighestProficiencyWeaponsCB', (known,), 0)


LOCAL_CALLBACKS['rlProficiency'] = _local_proficiency


# Meet page Data (meethttp.httpMeetMyInfo): the game's web call went to the
# local update server only, which reads this PC's accounts.db - online
# players' cards were blank.  It is asked from the backend instead
# (requestMeetInfo, any gid); the web call stays the fallback.
_meet_pending = {}


def _meet_key(gid):
    try:
        return int(gid or 0)
    except (TypeError, ValueError):
        return 0


def _local_meet_info(player, gid, data):
    callbacks = _meet_pending.pop(_meet_key(gid), [])
    text = json.dumps({'Ret': 0, 'Data': to_json_value(data if isinstance(data, dict) else {})})
    for callback in callbacks:
        try:
            callback(text)          # the body HttpHelper handed over: onGetCurUserData json.loads it
        except Exception:
            log_error('local-meet-info-callback-error', gid=safe(gid))


LOCAL_CALLBACKS['rlMeetInfo'] = _local_meet_info


def install_meet_info():
    try:
        meethttp = __import__('meethttp')
    except Exception:
        return False
    original = getattr(meethttp, 'httpMeetMyInfo', None)
    if not callable(original) or getattr(original, '_rl_meet_info', False):
        return False

    def httpMeetMyInfo(gid, cb, *args, **kwargs):
        key = _meet_key(gid)
        waiting = _meet_pending.setdefault(key, [])
        waiting.append(cb)
        if len(waiting) > 1:
            return None                 # asked already: that answer serves both

        def done(reply):
            if isinstance(reply, dict) and reply.get('handled') and reply.get('callbacks'):
                finish_rpc(_lobby.get('player'), 'requestMeetInfo', [gid], {}, reply, 1)
                if key not in _meet_pending:
                    return None         # rlMeetInfo answered every caller
            note_unhandled('requestMeetInfo', reply)
            for callback in _meet_pending.pop(key, []):
                try:
                    original(gid, callback, *args, **kwargs)     # the local web page
                except Exception:
                    log_error('local-meet-info-fallback-error', gid=safe(gid))
            return None
        if not asks_backend('requestMeetInfo'):
            return done(None)
        return ask_backend('requestMeetInfo', [gid], {}, done)
    httpMeetMyInfo._rl_meet_info = True
    meethttp.httpMeetMyInfo = httpMeetMyInfo
    return True


def ask_other_profile(player, name, args, fallback, fallback_args):
    """Another player's card: only the server knows it - never filled from
    our own state.  Not answered (lost, an older backend without the route,
    in a battle): a blank card, never your own name.  A card shown a moment
    ago is shown again from RPC_CACHE (each STATS tab asks for it again)."""
    cached = cached_rpc_reply(name, list(args), {})
    if cached is not None:
        _rpc_cache_hits[name] = _rpc_cache_hits.get(name, 0) + 1
        call_later(0.0, finish_rpc, player, name, list(args), {}, cached, 1)
        return None

    def done(reply):
        if isinstance(reply, dict) and reply.get('handled') and reply.get('callbacks'):
            remember_rpc_reply(name, list(args), {}, reply)
            return finish_rpc(player, name, list(args), {}, reply, 1)
        note_unhandled(name, reply)
        log('local-profile-unanswered', method=name, gid=safe(args[0]))
        call_later(SMART_REPLY_DELAY, _deliver_callback, player, fallback, fallback_args, 0)
    if not asks_backend(name):
        return done(None)
    return ask_backend(name, list(args), {}, done)


def solo_menu(main_ui):
    """onFormTeam (it draws your own slot and nameplate) also tells the
    top-right menu you are in a team, which shows only CONTESTS / Settings.
    Alone, the whole menu shows: Lucky Club, Benefits, data..."""
    try:
        if load_state().get('lobby', {}).get('formed'):
            return False
        main_ui.uiMainFunctionEntrance.onTeamStateUpdate(False)
        return True
    except Exception:
        log_error('local-lobby-solo-menu-error')
        return False


def local_server_id():
    try:
        return int((load_state().get('server') or {}).get('groupId') or 0)
    except Exception:
        return 0


@rpc_handler('requireBaseInfo')
def _rpc_require_base_info(player, gid=None, *args):
    """Profile card (Meet / STATS): your rank score (the badge and Rating),
    level and flag; another player's card comes from the server."""
    profile = _local_profile(player)
    if _is_other_gid(gid, profile):
        return ask_other_profile(player, 'requireBaseInfo', (gid,), 'onGetBaseInfo',
                                 (gid, '', False, 0, local_server_id(), 0, 1, ''))
    gid = profile['gid'] if gid is None else gid
    level = int(getattr(player, 'level', 0) or profile.get('level') or 1)
    reply = (gid, profile['nickname'], False, rank_score(), local_server_id(), 0, level, own_flag())
    call_later(SMART_REPLY_DELAY, _deliver_callback, player, 'onGetBaseInfo', reply, 0)


@rpc_handler('getPlayerTip')
def _rpc_get_player_tip(player, gid=None, from_ui='', position=None, other='{}', *args):
    """Clicking a player (leaderboard, chat bubble, intimate list):
    onGetPlayerTip opens UIPlayerTip at the touch position the client sent.
    That is a Vector2 and is handed back as it came (a guessed int raised
    "'int' object has no attribute 'x'"); only the gid goes to the backend,
    which answers that player's card.  otherInfo stays the JSON text the
    client made (onGetPlayerTip json.loads it)."""
    def done(reply):
        card = reply.get('card') if isinstance(reply, dict) else None
        note_unhandled('getPlayerTip', reply)
        if not isinstance(card, dict):
            profile = _local_profile(player)
            if _is_other_gid(gid, profile):
                card = {'gid': gid, 'nickname': ''}     # never your own name on someone else
            else:
                card = {'gid': profile['gid'], 'nickname': profile['nickname'], 'level': profile['level'],
                        'characterType': profile['characterType'], 'rankScore': rank_score()}
        card.setdefault('nickname', '')
        info = _deep_reply(card, card)      # a missing key reads a default, from this card
        call_later(SMART_REPLY_DELAY, _deliver_callback, player, 'onGetPlayerTip',
                   (info, from_ui, position, other), 0)
    if not asks_backend('getPlayerTip'):
        return done(None)
    return ask_backend('getPlayerTip', [gid], {}, done)


def _deliver_callback(player, callback_name, args, attempt):
    if not _same_player(player):
        return
    target = getattr(player, callback_name, None)
    if not callable(target):
        log('local-pyserver-callback-missing', callback=callback_name)
        return
    try:
        target(*args)
        log('local-client-data-reply', callback=callback_name, attempt=attempt)
    except Exception as error:
        if 'not picked up' in _error_text(error) and attempt < SMART_REPLY_RETRIES:
            call_later(0.5, _deliver_callback, player, callback_name, args, attempt + 1)
            return
        log_error('local-client-data-reply-error', callback=callback_name)


SMART_REPLY_DELAY = 0.3
SMART_REPLY_RETRIES = 4


def _has_reply_candidate(player, name):
    static = _echo_candidates(name)
    if any(callable(getattr(player, c, None)) for c in static):
        return True
    return bool(_scan_reply_candidates(player, name, static))


_smart_pending = {}


def _same_player(player):
    """A delayed reply is dropped when the player entity changed (logout, relog)."""
    try:
        current = BigWorld.player()
    except Exception:
        return True
    return current is None or current is player or _lobby.get('player') is player


def _entry_player(player):
    """A lobby-entry retry still belongs to the current lobby character."""
    return _same_player(player) and _lobby.get('player') is player


def _error_text(error):
    message = error.args[0] if getattr(error, 'args', None) else ''
    return message if isinstance(message, string_types) else repr(message)


def _deliver_smart_reply(player, name, args, attempt):
    args = _smart_pending.get(name, args)
    if not _same_player(player):
        _smart_pending.pop(name, None)
        return
    if name in _rpc_active:
        _smart_pending.pop(name, None)
        return
    _rpc_active.add(name)
    try:
        outcome = _smart_reply(player, name, args)
    finally:
        _rpc_active.discard(name)
    if outcome == 'retry' and attempt < SMART_REPLY_RETRIES:
        call_later(0.5, _deliver_smart_reply, player, name, args, attempt + 1)
        return
    _smart_pending.pop(name, None)
    if outcome is False:
        log('local-rpc-unsupported', method=name, kind='no-matching-reply')


def handle_rpc(mailbox, name, args, kwargs):
    mark = perf_mark()
    try:
        return _answer_rpc(mailbox, name, args, kwargs)
    finally:
        perf_done('rpc ' + str(name), mark)


def _answer_rpc(mailbox, name, args, kwargs):
    player = mailbox._rl_owner
    counter = getattr(sys.modules.get('ros_local_battle'), 'count_rpc', None)
    if counter is not None:
        counter(name)
    if is_quiet_rpc(name):
        return None                     # analytics / anti-cheat: nobody answers it
    count = _rpc_seen.get(name, 0) + 1
    _rpc_seen[name] = count
    if count <= 3 or DEBUG:
        log('local-rpc', target=mailbox._rl_kind, method=name, count=count,
            args=[safe(item, 300) for item in args],
            kwargs=dict((str(key), safe(value, 300)) for key, value in kwargs.items()))

    handler = RPC_HANDLERS.get(name)
    if handler is not None:
        try:
            return handler(player, *args, **kwargs)
        except Exception:
            log_error('local-rpc-handler-error', method=name)
            return None

    if name in MALL_BUY_RPCS:
        kwargs = dict(kwargs, **mall_buy_details(player, args))
    elif name in HALL_PROP_BUY_RPCS:
        kwargs = dict(kwargs, **hall_prop_buy_details(player, args))
    elif name in DECOMPOSE_RPCS:
        kwargs = dict(kwargs, **decompose_details(player, args))
    elif name in COMPOSE_RPCS:
        kwargs = dict(kwargs, **compose_details(player, args))
    elif name in WELFARE_DETAILS:
        kwargs = dict(kwargs, **WELFARE_DETAILS[name](player, args))
    elif name in PARTY_RPCS:
        if party_repeat(name, args):
            return None
        if name == 'inviteHallTeamPlayer':
            kwargs = dict(kwargs, **party_details(player, args))
    if name in PAY_RPCS and not topup_open(player):
        # requsetPayGoods is gated already; a pay RPC sent another way is
        # refused here too, without the network
        refuse_pay(name)
        return None
    if asks_backend(name):
        rpc_changes(name)
        cached = cached_rpc_reply(name, args, kwargs)
        if cached is not None:
            # answered already (RPC_CACHE): the screen gets it as from the backend,
            # a moment later (screens show their loading state first)
            _rpc_cache_hits[name] = _rpc_cache_hits.get(name, 0) + 1
            call_later(0.0, finish_rpc, player, name, args, kwargs, cached, count)
            return None
        if RPC_ASYNC:
            # asked without waiting: the rest runs when the answer comes (finish_rpc)
            ask_backend_later(player, name, args, kwargs, count)
            return None
        reply = call_pyserver(name, args, kwargs)
        remember_rpc_reply(name, args, kwargs, reply)
        return finish_rpc(player, name, args, kwargs, reply, count)
    # skipped: as if the backend had no answer - the guessed replies below still run
    return finish_rpc(player, name, args, kwargs, None, count)


def finish_rpc(player, name, args, kwargs, reply, count):
    """What an RPC does with the backend's answer (None: no answer)."""
    note_unhandled(name, reply)
    if reply is not None and reply.get('handled'):
        if reply.get('battle'):
            # START / CANCEL: the ticket names the local battle host.
            deliver_battle_ticket(player, reply['battle'])
        delay = _reply_delay(reply)
        if delay is not None:
            # Typed backend replies (supply...): the calling screen shows a
            # loading overlay first, so the answer must arrive later.
            call_later(delay, _deliver_server_reply, player, name, reply)
            return None
        applied = apply_server_props(player, reply.get('props'))
        refresh_currency_ui(player, applied)
        push_server_items(player, reply.get('items'), reason=name)
        if name in HALL_PROP_BUY_RPCS and reply.get('ok'):
            call_later(PURCHASE_RESULT_DELAY, show_bought_items, kwargs.get('items'), kwargs.get('currency_id'))
        callbacks = list(reply.get('callbacks') or [])
        for index, item in enumerate(callbacks):
            if apply_server_callback(player, name, item) == 'retry':
                # the screen is not built yet: finish later, with retries
                call_later(0.5, _deliver_server_callbacks, player, name, callbacks, index, 1)
                break
        if reply.get('tip'):
            show_offline_tip(reply['tip'], force=True)
        if name in PAY_RPCS and not reply.get('ok'):
            # switched off while this player was in the lobby (its prop is
            # stale): the backend refused, the buy's loading overlay must go
            close_pay_loading()
        return None

    user_action = _lobby_ready['value'] and time.time() - _lobby_ready['at'] > 3.0
    if name in FRIEND_RPCS:
        # Only the backend knows the friends: never a guessed reply.
        if user_action and name in FRIEND_ACTION_RPCS:
            show_offline_tip('Friends: the server did not answer, try again.')
        return None

    if name in PARTY_RPCS:
        # Only the backend knows the teams: never a guessed reply.
        if user_action:
            show_offline_tip('Team: the server did not answer, try again.')
        return None

    if name in PLATOON_RPCS:
        # Only the backend knows the platoons: never a guessed reply.
        if user_action and name in PLATOON_WRITES:
            show_offline_tip('Platoon: the server did not answer, try again.')
        return None

    if name in NO_SMART_REPLY:
        # A guessed success callback for a purchase would show goods the
        # backend never granted (it may still charge after a timeout).
        answer_unanswered_purchase(player, name, args, reply)
        if name in PAY_RPCS:
            close_pay_loading()         # no answer: the buy's overlay must not stay
        return None

    if name in SERVER_ONLY_REPLIES:
        # A guess is wrong data: onGetHistoricMaxRankInfo(0) zeroed your best
        # rank, a guessed card showed your own name.  Nothing is better.
        if count <= 3:
            log('local-rpc-unanswered', method=name, timeout=reply is None)
        return None

    # Before the lobby is up, calls are automatic (queries, handshakes): log only.
    if not user_action or name in _rpc_active or NO_ECHO.search(name):
        return None
    if not _is_match_request(name) and _has_reply_candidate(player, name):
        # The online server answers over the network, after the calling
        # screen has built its components; answering inside the call made
        # SendMessage fail ("not picked up by any component").  Repeated
        # calls while a reply is pending share it (newest args win).
        first = name not in _smart_pending
        _smart_pending[name] = tuple(args)
        if first:
            call_later(SMART_REPLY_DELAY, _deliver_smart_reply, player, name, tuple(args), 0)
        return None

    if _is_match_request(name):
        if count <= 3:
            log('local-rpc-unsupported', method=name, kind='match')
        if not battle_running():
            if reply is None and name in BACKEND_MATCH_CALLS:
                show_offline_tip(MATCH_NO_ANSWER)     # lost on the way, not unsupported
            else:
                # START itself is answered by the backend (battle_rpc.py); this
                # is one of the other match calls, which nothing plays yet.
                show_offline_tip('Offline mode: that match call is not supported yet.')
        return None
    if name.lower().startswith(QUERY_PREFIXES):
        if count == 1:
            debug('local-rpc-query-ignored', method=name)
        return None
    # No popup: most unanswered calls are background bookkeeping; they are
    # listed in unknown_rpcs.json so they can be bound in rpc_routes.json.
    if count <= 3:
        log('local-rpc-unsupported', method=name, kind='action')
    return None


_pyserver = {'failures': 0}


def to_json_value(value, depth=0):
    if isinstance(value, bytes) and isinstance(value, string_types):
        # Python 2 str: json.dumps decodes it as UTF-8 and raised on binary
        # report data (saLogFromClient module hashes) - the call was lost.
        try:
            value.decode('utf-8')
        except UnicodeDecodeError:
            return value.decode('latin-1')
        return value
    if value is None or isinstance(value, (bool, int, float)) or isinstance(value, string_types):
        return value
    try:
        if isinstance(value, long):  # noqa: F821 (Python 2)
            return value
    except NameError:
        pass
    if depth < 6 and isinstance(value, (list, tuple, set)):
        return [to_json_value(item, depth + 1) for item in value]
    if depth < 6 and isinstance(value, dict):
        return dict((str(key), to_json_value(item, depth + 1)) for key, item in value.items())
    return safe(value, 300)


# Asking the backend is a round trip on the game's own thread: nothing while
# the answer travels.  On this PC that was under a millisecond; on the online
# server it is the network's latency (70 ms and more) - and a battle makes
# many calls the backend has no answer for (every shot, jump, landing): the
# game stood still for each, the frame rate fell.  In a battle the backend is
# not asked (the battle host and the battle hook do the battle), and a call
# it once said it does not know is not asked again.
_pyserver_unhandled = set()


def note_unhandled(name, reply):
    """A backend that knows nothing of an RPC is never asked it again.  A
    reply with 'error' (not logged in: online sessions die with every server
    restart; a dispatch that raised) is no answer, not a verdict: one of them
    turned the friends or the player cards off for the whole game session."""
    if not isinstance(reply, dict) or reply.get('handled'):
        return
    if reply.get('error'):
        if reply.get('error') == 'not logged in' and not _session_lost[0]:
            _session_lost[0] = True
            log('local-session-lost', method=name)
        return
    _pyserver_unhandled.add(name)


_session_lost = [False]
BATTLE_PHASES = ('entering', 'fighting', 'over')
# What a battle still asks the backend for: chat (it keeps the history and
# answers the chat commands) - a message, not every frame.
BATTLE_BACKEND_CALLS = frozenset(['chat', 'chatPrivate'])


def in_battle():
    module = sys.modules.get('ros_local_battle')
    battle = getattr(module, 'BATTLE', None)
    return isinstance(battle, dict) and battle.get('phase') in BATTLE_PHASES


def asks_backend(name):
    if name in _pyserver_unhandled:
        return False
    if in_battle() and name not in BATTLE_BACKEND_CALLS:
        if name not in _battle_skipped:
            _battle_skipped.add(name)
            debug('local-rpc-battle-skipped', method=name)
        return False
    return True


_battle_skipped = set()
_rpc_cache_hits = {}


# --------------------------------------------------------------------------
# Backend RPCs without waiting
# --------------------------------------------------------------------------
# Measured on the online server (Test A, a lobby): 58 RPCs a minute, the game
# frozen for each until the answer came back - 100 ms on average, 300 ms when
# it timed out - 5.8 s of every minute; browsing the mall it stuttered at
# every click.  Each RPC now goes out on its own non-blocking socket and the
# game goes on; a poll every frame or so picks the answers up and finishes
# the call (finish_rpc) - as the online server's callbacks always arrived.

RPC_ASYNC = True                        # False: the old waiting calls (the unit tests' fake backends)
RPC_WAIT = 3.0                          # s: no answer by then = no answer
# Nothing at all back after this long: the request (or every piece of the
# answer) was lost on the way - send it again, with the same id, when the
# backend answers a repeated request once (login "dedupe"; never done twice).
RPC_RESEND_AFTER = 0.7
RPC_RESENDS = 2
RPC_POLL = 0.02
_rpc_pending = []
_rpc_poll = {'running': False}
WOULD_BLOCK = (10035, 11, 35)           # WSAEWOULDBLOCK, EAGAIN (Linux / BSD)


def ask_backend_later(player, name, args, kwargs, count):
    def answered(reply):
        remember_rpc_reply(name, args, kwargs, reply)
        return finish_rpc(player, name, args, kwargs, reply, count)
    return ask_backend(name, args, kwargs, answered)


# --------------------------------------------------------------------------
# Answers the lobby already has
# --------------------------------------------------------------------------
# Measured in a 27 min local lobby session (local-backend-calls): the team
# card was asked 107 times (every panel that shows the team asks again), the
# friend list 25 (each time the panel opens), ranks 21, battle gifts/times 16,
# the supply list 8...  Online each is a round trip on a link losing 16-19 %
# of its packets.  Reads that only change when something happens are answered
# from the last reply until that something happens:
#   seconds  the answer is kept that long at most (what other players change
#            - friends online, the leaderboard - is read again after it)
#   None     kept until a call or event that changes it clears it
RPC_CACHE = {
    'getAthleteRosMatchTeamBriefData': 60.0,
    # Platoon reads (PLATOON_READS): cleared by every platoon write and by an
    # rlPlatoon push; the lists other players change are read again after a while
    'getMyRosMatchTeamInfo': 300.0,
    'getRosMatchTeamList': 30.0,
    'searchRosMatchTeam': 30.0,
    'getRosMatchTeamData': 30.0,
    'getRosMatchTeamPlayerList': 30.0,
    'getRosMatchTeamApplyList': None,
    'getRosMatchTeamEventList': 60.0,
    'getAthleteRosMatchTeamLogo': 300.0,
    'getFriendList': 120.0,
    'requireRankInfo': 120.0,
    'requireRankList': 120.0,
    'queryAvailableBattleGift': None,
    'checkBattleTimes': None,
    'queryAvailableSupplement': None,
    'queryAvailableMallGoodsByType': None,
    'queryBlackMarketInfo': None,
    'queryAvailableAdvertisement': None,
    # Friends > Meet profile tabs (features/profile.py): each tab of the
    # profile asks again when it is shown.  Yours change only with a battle
    # or a title change (cleared then); other players' cards are read again
    # after a while (their battles).
    'getHighestProficiencyWeapons': 60.0,
    'queryCreditScore': None,
    'queryOtherCreditScore': 300.0,
    'querySubCreditScoreRecord': None,
    'requestIntimateRelationshipInfo': None,
    'requestOthersIntimateRelationshipInfo': 120.0,
    'requestOtherMarryshipInfo': 120.0,
    'requestOthersMarriageInfo': 120.0,
    'requestMessageForMarriage': 120.0,
    'queryPersonalSpaceLikeCnt': 60.0,
    'queryPersonalSpaceComment': 60.0,
    'judgeSpacePartnerShow': 120.0,
    'queryPersonalInfo': 60.0,
    'requireBaseInfo': 60.0,            # another player's card (ask_other_profile)
    'requireRecordData': 60.0,
}
# What clears what: a call that reaches the backend and matches a pattern
# clears those answers before it goes (the next read asks the backend again).
RPC_CACHE_CLEARED_BY = (
    (re.compile(r'friend|blacklist|black(?:list)?Player', re.I), ('getFriendList',)),
    (re.compile(r'team|platoon|invite|kick', re.I), ('getAthleteRosMatchTeamBriefData',)),
    (re.compile(r'supply|supplement|lottery|draw|exchange', re.I),
     ('queryAvailableSupplement', 'queryAvailableMallGoodsByType', 'queryBlackMarketInfo')),
    (re.compile(r'buy|purchase|recharge|pay', re.I),
     ('queryAvailableMallGoodsByType', 'queryBlackMarketInfo', 'queryAvailableSupplement')),
    (re.compile(r'gift|award|reward|claim|receive|sign', re.I), ('queryAvailableBattleGift',)),
    (re.compile(r'BestWeaponTitle', re.I), ('getHighestProficiencyWeapons',)),
)
# A battle changes ranks, battle gifts and play counts (cleared on the way
# back to the lobby); a friend push from the backend changes the friend list.
BATTLE_CHANGES = ('requireRankInfo', 'requireRankList', 'queryAvailableBattleGift', 'checkBattleTimes',
                  'getAthleteRosMatchTeamBriefData', 'getMyRosMatchTeamInfo', 'getRosMatchTeamPlayerList',
                  # the best-weapon title and the STATS cards move with a battle
                  'getHighestProficiencyWeapons', 'requireRecordData', 'requireBaseInfo')
RPC_CACHE_KEEP = 200
_rpc_cache = {}
# Writes the game repeats with the same value (changeOccupation: 52 in 27 min,
# nearly all the same): sent when the value changes, answered as before otherwise.
# The Meet page reports its TanTan sex / picture count on every visit, and
# the intimate visibility setting came 227 times in one session.
SAME_VALUE_WRITES = frozenset(['changeOccupation', 'changeTantanSex', 'changeTantanPicCount',
                               'updateIsIntimateRelationshipVisibleInTeam'])
_last_write = {}


def _rpc_cache_key(name, args, kwargs):
    try:
        return name + '|' + json.dumps([to_json_value(list(args)), to_json_value(kwargs)], sort_keys=True)
    except Exception:
        return None                     # not plain data: never cached


def cached_rpc_reply(name, args, kwargs):
    """The last answer to this read (a copy: replies are fixed up in place), or None."""
    if name in SAME_VALUE_WRITES:
        key = _rpc_cache_key(name, args, kwargs)
        kept = _last_write.get(name)
        return _replayed(kept[1]) if kept is not None and key is not None and kept[0] == key else None
    if name not in RPC_CACHE:
        return None
    key = _rpc_cache_key(name, args, kwargs)
    kept = _rpc_cache.get(key) if key is not None else None
    if kept is None:
        return None
    ttl = RPC_CACHE[name]
    if ttl is not None and time.time() - kept[0] > ttl:
        _rpc_cache.pop(key, None)
        return None
    return _replayed(kept[1])


def _replayed(reply):
    """A kept answer, shown again: its callbacks only.  Its props (every
    backend reply carries the wallet) and items were applied when it came;
    applied again they put back the coins of a minute ago and pushed the
    same items into the depot twice."""
    reply = copy.deepcopy(reply)
    reply.pop('props', None)
    reply.pop('items', None)
    return reply


def remember_rpc_reply(name, args, kwargs, reply):
    if not isinstance(reply, dict) or not reply.get('handled') or reply.get('ok') is False:
        return False                    # no answer, or a refusal: asked again next time
    if name in SAME_VALUE_WRITES:
        key = _rpc_cache_key(name, args, kwargs)
        if key is not None:
            _last_write[name] = (key, copy.deepcopy(reply))
        return key is not None
    if name not in RPC_CACHE:
        if reply.get('props') or reply.get('items'):
            # the wallet or the depot changed (a purchase, a reward): what the
            # shops and gifts showed may be wrong now
            clear_rpc_cache(('queryAvailableMallGoodsByType', 'queryBlackMarketInfo',
                             'queryAvailableSupplement', 'queryAvailableBattleGift'), name)
        return False
    key = _rpc_cache_key(name, args, kwargs)
    if key is None:
        return False
    if len(_rpc_cache) >= RPC_CACHE_KEEP:
        _rpc_cache.pop(min(_rpc_cache, key=lambda k: _rpc_cache[k][0]), None)
    _rpc_cache[key] = (time.time(), copy.deepcopy(reply))
    return True


def clear_rpc_cache(names, reason):
    names = tuple(names)
    gone = [key for key in _rpc_cache if key.split('|', 1)[0] in names]
    for key in gone:
        _rpc_cache.pop(key, None)
    if gone:
        debug('local-rpc-cache-cleared', names=list(names), reason=reason, count=len(gone))
    return len(gone)


# reads (requestFriendOnlineStatus, getRosMatchTeamList...) change nothing
READ_LIKE = re.compile(r'^(?:get|query|require|search|check|is|has|load|fetch)[A-Z]|(?:Status|Info|List|Data)$')


def rpc_changes(name):
    """A call that reaches the backend: clear the answers it may change."""
    if name in PLATOON_WRITES:
        # before READ_LIKE: modifyRosMatchTeamBasicInfo ends in "Info"
        return clear_rpc_cache(PLATOON_READS, name)
    if name in RPC_CACHE or READ_LIKE.search(name):
        return 0
    cleared = 0
    for pattern, names in RPC_CACHE_CLEARED_BY:
        if pattern.search(name):
            cleared += clear_rpc_cache(names, name)
    return cleared


def ask_backend(name, args, kwargs, on_reply):
    """Ask the backend to answer an RPC; ``on_reply(reply or None)`` runs when
    the answer comes (at once when not RPC_ASYNC - the tests' fake backends)."""
    if not RPC_ASYNC:
        return on_reply(call_pyserver(name, args, kwargs))
    if _pyserver['failures'] >= 3 and time.time() - _pyserver.get('failed_at', 0) < 5.0:
        return on_reply(None)                   # unreachable: tried again in 5 s
    if _pyserver['failures'] >= 3:
        _pyserver['failures'] = 2
    try:
        request = _with_session(RPC_PREFIX, {'method': name, 'args': to_json_value(list(args)),
                                             'kwargs': to_json_value(kwargs), 'rid': request_id()})
        request = pack_request(request if isinstance(request, bytes) else request.encode('utf-8'))
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.setblocking(0)
        client.sendto(request, _backend['address'])
    except Exception:
        log_error('local-pyserver-send-error', method=safe(name, 120))
        return on_reply(None)
    _rpc_pending.append({'socket': client, 'sent': time.time(), 'name': name, 'on_reply': on_reply,
                         'pieces': PieceBuffer(), 'request': request, 'last_send': time.time(), 'resends': 0})
    if not _rpc_poll['running']:
        _rpc_poll['running'] = True
        call_later(RPC_POLL, poll_backend_replies)
    return None


def send_later(name, request, on_reply):
    """A request that can be repeated (a save), without waiting: ``on_reply(text
    or None)`` when the answer comes - the game never stops for the network."""
    try:
        data = pack_request(request if isinstance(request, bytes) else request.encode('utf-8'))
        client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.setblocking(0)
        client.sendto(data, _backend['address'])
    except Exception:
        log_error('local-send-later-error', request=safe(name, 120))
        return on_reply(None)
    now = time.time()
    _rpc_pending.append({'socket': client, 'sent': now, 'name': name, 'on_reply': on_reply, 'raw': True,
                         'pieces': PieceBuffer(), 'request': data, 'last_send': now, 'resends': 0,
                         'repeatable': True})
    if not _rpc_poll['running']:
        _rpc_poll['running'] = True
        call_later(RPC_POLL, poll_backend_replies)
    return None


def request_id():
    return '%016x' % random.getrandbits(64)


def resend_rpc(entry, now):
    if not (_backend.get('dedupe') or entry.get('repeatable')) or entry.get('request') is None \
            or entry['resends'] >= RPC_RESENDS:
        return False
    if now - entry['last_send'] < RPC_RESEND_AFTER:
        return False
    try:
        entry['socket'].sendto(entry['request'], _backend['address'])
    except Exception:
        return False
    entry['resends'] += 1
    entry['last_send'] = now
    return True


def poll_backend_replies():
    now = time.time()
    finished, waiting = [], []
    for entry in _rpc_pending:
        data = None
        failed = False
        while data is None:
            try:
                data = entry['pieces'].feed(entry['socket'].recv(65535))
            except socket.error as error:
                code = error.args[0] if error.args else None
                failed = code not in WOULD_BLOCK      # the backend is not there
                break
            except Exception:
                failed = True
                break
        if data is None and not failed and now - entry['sent'] < RPC_WAIT:
            if entry['pieces'].message is None:
                resend_rpc(entry, now)
            else:
                entry['pieces'].ask_missing(entry['socket'], _backend['address'])
            waiting.append(entry)
            continue
        try:
            entry['socket'].close()
        except Exception:
            pass
        finished.append((entry, data))
    _rpc_pending[:] = waiting
    for entry, data in finished:
        reply = None
        backend_call_done('RPC ' + entry['name'], (now - entry['sent']) * 1000.0)
        if data is None and entry['pieces'].message is None:
            # nothing came back at all: the backend may be gone.  (Part of a reply
            # means it answered and pieces were lost on the way - not "unreachable",
            # which would answer every call with nothing for 5 s.)
            _pyserver['failures'] += 1
            _pyserver['failed_at'] = now
            if _pyserver['failures'] == 3:
                log_error('local-pyserver-unreachable')
        elif data is None:
            log('local-pyserver-reply-incomplete', method=safe(entry['name'], 120),
                got=len(entry['pieces'].parts), count=entry['pieces'].count)
        elif entry.get('raw'):
            _pyserver['failures'] = 0
            reply = data if isinstance(data, str) else data.decode('utf-8', 'replace')
        else:
            _pyserver['failures'] = 0
            try:
                reply = from_json_value(json.loads(data))
            except Exception:
                reply = None
            if not isinstance(reply, dict):
                log('local-pyserver-bad-reply', method=safe(entry['name'], 120), reply=safe(reply, 300))
                reply = None
        mark = perf_mark()
        try:
            entry['on_reply'](reply)
        except Exception:
            log_error('local-rpc-finish-error', method=entry['name'])
        finally:
            perf_done('reply ' + str(entry['name']), mark)
    if _rpc_pending:
        call_later(RPC_POLL, poll_backend_replies)
    else:
        _rpc_poll['running'] = False


def call_pyserver(name, args, kwargs):
    """Ask backend_server/pyserver.py (through the game server) to answer an RPC."""
    if _pyserver['failures'] >= 3:
        # Backend unreachable: retry every 5 s instead of giving up for good.
        if time.time() - _pyserver.get('failed_at', 0) < 5.0:
            return None
        _pyserver['failures'] = 2
    try:
        request = _with_session(RPC_PREFIX, {'method': name, 'args': to_json_value(list(args)),
                                             'kwargs': to_json_value(kwargs)})
        payload = _udp_exchange(request, 65535, timeout=0.3)
        _pyserver['failures'] = 0
        reply = from_json_value(json.loads(payload))
        if not isinstance(reply, dict):
            log('local-pyserver-bad-reply', method=safe(name, 120), reply=safe(reply, 300))
            return None
        return reply
    except Exception:
        _pyserver['failures'] += 1
        _pyserver['failed_at'] = time.time()
        if _pyserver['failures'] == 3:
            log_error('local-pyserver-unreachable')
        return None


# Parameter-name aliases for "named" server replies: the server says what a
# value *is* (text, gid, name...) and the hook passes it to whichever
# parameter of the client callback means that, whatever it is called.
NAMED_ALIASES = {
    'channel': ('channel', 'chatchannel', 'channeltype', 'chnl', 'chanel', 'type', 'msgtype'),
    'text': ('msg', 'text', 'content', 'message', 'chatmsg', 'words', 'chatcontent', 'str'),
    'gid': ('gid', 'sendergid', 'fromgid', 'srcgid', 'entityid', 'uid', 'playergid', 'speaker'),
    'name': ('name', 'nickname', 'sendername', 'fromname', 'playername', 'speakername'),
    'sender': ('senderinfo', 'sender', 'playerinfo', 'roleinfo', 'fromplayer', 'speakerinfo'),
    'extra': ('extra', 'params', 'info', 'extrainfo', 'ext', 'extradata', 'chatinfo', 'exinfo'),
    'nationalFlag': ('nationalflag', 'flag_nation', 'nation'),
    'time': ('time', 'timestamp', 'ts', 'sendtime', 'msgtime'),
    'flag': ('issystem', 'broadcast'),
}


def callback_arguments(function, named):
    """Build positional args for ``function`` from a {meaning: value} dict."""
    function = getattr(function, 'im_func', function)
    code = getattr(function, 'func_code', None) or getattr(function, '__code__', None)
    if code is None:
        return None
    params = list(code.co_varnames[:code.co_argcount])
    if params and params[0] == 'self':
        params = params[1:]
    defaults = getattr(function, 'func_defaults', None) or ()
    required = len(params) - len(defaults)
    lowered = dict((str(key).lower(), value) for key, value in named.items())
    args = []
    for index, param in enumerate(params):
        low = param.lower()
        if low in lowered:
            args.append(lowered[low])
            continue
        match = None
        for meaning, aliases in NAMED_ALIASES.items():
            if low in aliases and meaning in named:
                match = (named[meaning],)
                break
        if match is not None:
            args.append(match[0])
        elif index >= required:
            break          # leave the rest to their defaults
        else:
            args.append(None)
    return args


def apply_server_callback(player, rpc_name, item):
    """Run one backend reply callback now; returns 'ok', 'missing', 'retry'
    (the screen that shows it is not built yet) or 'error'."""
    method = item.get('method') if isinstance(item, dict) else None
    local = LOCAL_CALLBACKS.get(str(method)) if method else None
    if local is not None:
        try:
            local(player, *(item.get('args') or []))
            log('local-pyserver-callback', rpc=rpc_name, callback=method, args=None)
            return 'ok'
        except Exception:
            log_error('local-pyserver-callback-error', rpc=rpc_name, callback=method)
            return 'error'
    target = getattr(player, str(method), None) if method else None
    if not callable(target):
        log('local-pyserver-callback-missing', rpc=rpc_name, callback=safe(method))
        return 'missing'
    args = []
    try:
        if 'named' in item:
            args = callback_arguments(target, item['named'] or {})
            if args is None:
                args = []
        else:
            args = item.get('args') or []
        target(*args)
        log('local-pyserver-callback', rpc=rpc_name, callback=method,
            args=[safe(value, 120) for value in args] if 'named' in item else None)
        return 'ok'
    except Exception as error:
        if 'not picked up' in _error_text(error):
            debug('local-pyserver-callback-early', rpc=rpc_name, callback=method)
            return 'retry'
        log_error('local-pyserver-callback-error', rpc=rpc_name, callback=method)
        return 'error'


# --------------------------------------------------------------------------
# Supplement / typed backend replies
# --------------------------------------------------------------------------
# JSON loses the Python types the game's supply code relies on (int dict keys,
# tuples) and turns every string into unicode in Python 2.  The backend
# (backend_server/pycodec.py) wraps such values in markers:
#     {"__py__": "intdict", "items": [[30001, {...}], [2, 5]]} -> dict
#     {"__py__": "tuple", "items": [...]}                      -> tuple
#     {"__py__": "unicode", "value": "..."}                    -> unicode kept
# every other string becomes a native str (UTF-8 bytes in Python 2).
# A reply carrying "delay" is delivered later (props, then callbacks, with the
# same "not picked up" retries as smart replies).

WIRE_MARKER = '__py__'
WIRE_MAX_DEPTH = 32
_unicode_type = type(u'')              # unicode in Python 2, str in Python 3


def _hashable(value):
    if isinstance(value, list):
        return tuple(_hashable(item) for item in value)
    if isinstance(value, dict):
        return tuple(sorted((_hashable(k), _hashable(v)) for k, v in value.items()))
    return value


def from_json_value(value, depth=0):
    """json.loads result -> Python values the game expects (see above).
    Never raises; beyond WIRE_MAX_DEPTH values are returned as they are."""
    try:
        if isinstance(value, string_types):
            return to_native_str(value)
        if depth >= WIRE_MAX_DEPTH or not isinstance(value, (dict, list)):
            return value
        if isinstance(value, list):
            return [from_json_value(item, depth + 1) for item in value]
        kind = value.get(WIRE_MARKER)
        if kind == 'unicode' and isinstance(value.get('value'), string_types):
            text = value['value']
            if not isinstance(text, _unicode_type):
                try:
                    text = text.decode('utf-8', 'replace')
                except Exception:
                    pass
            return text
        items = value.get('items')
        if kind == 'intdict' and isinstance(items, list):
            result = {}
            for pair in items:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    continue
                key = _hashable(from_json_value(pair[0], depth + 1))
                try:
                    result[key] = from_json_value(pair[1], depth + 1)
                except TypeError:
                    result[safe(key, 200)] = from_json_value(pair[1], depth + 1)
            return result
        if kind == 'tuple' and isinstance(items, list):
            return tuple(from_json_value(item, depth + 1) for item in items)
        return dict((to_native_str(key) if isinstance(key, string_types) else key,
                     from_json_value(item, depth + 1)) for key, item in value.items())
    except Exception:
        log_error('local-wire-decode-error', value=safe(value, 300))
        return value


def _reply_delay(reply):
    delay = reply.get('delay') if isinstance(reply, dict) else None
    if isinstance(delay, bool) or not isinstance(delay, (int, long_type, float)):
        return None
    if delay != delay or delay <= 0:
        return None
    return min(float(delay), 10.0)


def _deliver_server_reply(player, rpc_name, reply):
    """Delayed backend reply: props once, then callbacks, then the tip."""
    if not _same_player(player):
        log('local-pyserver-reply-dropped', rpc=rpc_name, reason='player-changed')
        return
    try:
        applied = apply_server_props(player, reply.get('props'))
        refresh_currency_ui(player, applied)
    except Exception:
        log_error('local-pyserver-props-error', rpc=rpc_name)
    try:
        push_server_items(player, reply.get('items'), reason=rpc_name)
    except Exception:
        log_error('local-depot-push-failed', rpc=rpc_name)
    if reply.get('tip'):
        try:
            show_offline_tip(reply['tip'], force=True)
        except Exception:
            log_error('local-pyserver-tip-error', rpc=rpc_name)
    _deliver_server_callbacks(player, rpc_name, list(reply.get('callbacks') or []), 0, 0)


def _deliver_server_callbacks(player, rpc_name, callbacks, index, attempt):
    if not _same_player(player):
        log('local-pyserver-reply-dropped', rpc=rpc_name, reason='player-changed')
        return
    while index < len(callbacks):
        outcome = apply_server_callback(player, rpc_name, callbacks[index])
        if outcome == 'retry':
            if attempt < SMART_REPLY_RETRIES:
                call_later(0.5, _deliver_server_callbacks, player, rpc_name, callbacks, index,
                           attempt + 1)
                return
            log('local-pyserver-callback-error', rpc=rpc_name,
                callback=safe(callbacks[index].get('method')), error='not picked up after retries')
        index += 1
        attempt = 0


# --------------------------------------------------------------------------
# START / battleground (client/battle_hook.py, injected as ros_local_battle)
# --------------------------------------------------------------------------
# The backend answers the START call with a "battle" field: the local battle
# host's address and the match settings.  Everything the battleground needs
# lives in the other module; without it START behaves as it did before.

class _LobbyBridge(object):
    """What the battle hook may use from this module (log, call_later...)."""

    def __getattr__(self, name):
        try:
            return globals()[name]
        except KeyError:
            raise AttributeError(name)


_battle = {'module': None, 'attached': False, 'missing': False}


def battle_module():
    module = _battle['module']
    if module is None:
        if _battle['missing']:
            return None
        module = sys.modules.get('ros_local_battle')
        if module is None:
            _battle['missing'] = True
            log('local-battle-hook-missing')
            return None
        _battle['module'] = module
    if not _battle['attached']:
        try:
            module.attach(_LobbyBridge())
            _battle['attached'] = True
        except Exception:
            log_error('local-battle-attach-error')
            _battle['missing'] = True
            _battle['module'] = None
            return None
    return module


BATTLE_ATTACH_POLL = 1.0
BATTLE_ATTACH_TRIES = 300


def attach_battle_hook(tries=0):
    """Attach the battle hook at startup, not on the first START: it also
    fixes lobby texts (mode names) before the lobby draws them."""
    if sys.modules.get('ros_local_battle') is not None:
        return battle_module() is not None
    if tries < BATTLE_ATTACH_TRIES:
        call_later(BATTLE_ATTACH_POLL, attach_battle_hook, tries + 1)
    return False


def deliver_battle_ticket(player, ticket):
    """Hand a reply's battle field to the battle hook."""
    module = battle_module()
    if module is None:
        show_offline_tip('Offline mode: the battleground hook is not loaded.')
        return False
    try:
        return bool(module.on_ticket(player, from_json_value(ticket)))
    except Exception:
        log_error('local-battle-ticket-error', ticket=safe(ticket, 300))
        return False


def battle_running():
    module = _battle['module']
    try:
        return module is not None and module.BATTLE['phase'] not in ('idle', 'over')
    except Exception:
        return False


CURRENCY_PROPS = frozenset(['gp', 'sp', 'freeYuanbao', 'payYuanbao'])
CURRENCY_UI_TYPES = (1, 2, 3)          # const.MallCurrencyType GP, YUANBAO, SP


def refresh_currency_ui(player, applied):
    """Top bar / currency panels listen to onCurrencyChanged (iCurrency)."""
    try:
        if not applied or not CURRENCY_PROPS.intersection(applied):
            return
        refresh = getattr(player, 'onCurrencyChangedToUI', None)
        if not callable(refresh):
            return
    except Exception:
        return
    for currency_type in CURRENCY_UI_TYPES:
        try:
            refresh(currency_type)
        except Exception as error:
            if 'not picked up' in _error_text(error):
                continue      # no currency widget open: nothing to redraw
            log_error('local-currency-ui-error', currency=currency_type)


# --------------------------------------------------------------------------
# DEPOT: items the local server grants
# --------------------------------------------------------------------------
# What the player owns lives in the client's own package objects; online the
# server pushed every new item to them:
#     player.onAddDtsAppearanceItem(itemID, changedItemList, itemSrc, number)
#     player.onAddItemIntoRepertoryPackage(itemID, changedItemList, itemSrc, number)
# and the package stores each changedItemList entry under its uuid
# (package_client/PackageClient3.onAddItem: 'uuid', 'number', 'info';
# DtsRosPackageClient3.onAddItem adds 'layout').  'info' carries the expiry the
# appearance screens read as 'ex_tm'.
# The backend sends {"item": id, "count": n, "expires": epoch or 0} in an RPC
# reply's "items", and the whole depot once at lobby entry (ITEMS_REQUEST).

ITEM_ADD_CALLBACKS = {
    'appearance': 'onAddDtsAppearanceItem',
    'repertory': 'onAddItemIntoRepertoryPackage',
}
ITEM_CALLBACK_ORDER = ('appearance', 'repertory')
ITEM_SOURCE_LOCAL = 0           # itemSrc: what gave the item (0 = unspecified)
_item_uuid = {'next': 0}


def _new_item_uuid(item_id):
    """A uuid for a granted item.  The client's own generator is used when it
    is there, so the value looks like any other item's."""
    try:
        netease = sys.modules.get('Netease')
        generator = getattr(netease, 'getUUID', None) if netease is not None else None
        if callable(generator):
            value = generator()
            if value:
                return value
    except Exception:
        debug('local-depot-uuid-fallback', item=item_id)
    _item_uuid['next'] += 1
    return int(item_id) * 100000 + _item_uuid['next']


class ItemEntry(dict):
    """A changedItemList entry: the packages read it as a dict, the
    "you got X" tip of onAddDtsAppearanceItem as an object (entry.info)."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def _item_entry(item_id, count, expires):
    """One changedItemList entry, with the keys the client's packages read."""
    # onAddDtsAppearanceItem reads info['ex_tm'] (0 = permanent) for its tip
    info = {'ex_tm': int(expires or 0)}
    return ItemEntry(uuid=_new_item_uuid(item_id), itemID=int(item_id),
                     number=int(count), info=info, layout=0)


ITEM_PACKAGE_RULES = (('appearance', 'shouldDtsHallPropPutInAppearancePackage'),
                      ('repertory', 'shouldDtsHallPropPutInRepertoryPackage'))


NO_PACKAGE = 'none'


def item_package(item_id):
    """The package the game puts a hall prop in (outfits: appearance,
    multi-use props: repertory), NO_PACKAGE for props kept in neither (gift
    bags open on purchase), None when the game cannot say."""
    try:
        utils = __import__('dts_hall_prop_utils')
    except Exception:
        return None
    answered = False
    for name, rule in ITEM_PACKAGE_RULES:
        try:
            if getattr(utils, rule)(int(item_id)):
                return name
            answered = True
        except Exception:
            continue
    return NO_PACKAGE if answered else None


def _push_one_item(player, item_id, count, expires, package=None):
    """Hand one item to the client's package; returns the package that took it.

    Only one package is tried when the game says which: the appearance
    callback stores the item before its tip, so a failure there must not
    hand the same item to the repertory too."""
    entry = _item_entry(item_id, count, expires)
    if not (isinstance(package, string_types) and package in ITEM_ADD_CALLBACKS):
        package = item_package(item_id)
    if package == NO_PACKAGE:
        debug('local-depot-push-skipped', item=item_id)
        return None
    order = (package,) if package in ITEM_ADD_CALLBACKS else ITEM_CALLBACK_ORDER
    for name in order:
        callback = getattr(player, ITEM_ADD_CALLBACKS[name], None)
        if not callable(callback):
            continue
        try:
            callback(item_id, [entry], ITEM_SOURCE_LOCAL, int(count))
            return name
        except Exception:
            log_error('local-depot-push-error', package=name, item=item_id)
    return None


def hall_prop_type(item_id):
    """(type name, PROP_TYPE) of a hall prop from the game's table."""
    try:
        legacy = __import__('helpers.character_scene', fromlist=['legacyProperties']).legacyProperties
        prop_type = legacy.getDtsHallPropData(int(item_id)).PROP_TYPE
        return type(prop_type).__name__, prop_type
    except Exception:
        return None, None


def owned_permanent(player, item_id):
    try:
        return int(player.getPermanentDtsAppearanceItemCnt(int(item_id)) or 0)
    except Exception:
        return 0


def depot_settlement(player, items):
    """What the server did with a grant that the depot never kept:
    currency props ("200 Gold", tickets) went into the wallet, and a
    permanent appearance that cannot be converted to shards stays one copy.
    Returns (items to push, currency [[item, count, currency id, each]],
    trims [[item, extra copies]])."""
    keep, currency, trims = [], [], []
    for item in items:
        try:
            item_id, count = int(item.get('item')), int(item.get('count', 1))
        except (AttributeError, TypeError, ValueError):
            keep.append(item)
            continue
        kind, prop_type = hall_prop_type(item_id)
        if kind == 'CurrencyPropType' and count > 0:
            currency.append([item_id, count, int(getattr(prop_type, 'CURRENCY_ID', 0) or 0),
                             int(getattr(prop_type, 'NUM', 0) or 0)])
            continue
        permanent = not int(item.get('expires') or 0)
        if (permanent and count > 0 and prop_type is not None and hasattr(prop_type, 'CAN_DECOMPOSE')
                and not getattr(prop_type, 'CAN_DECOMPOSE', False)):
            wanted = max(0, 1 - owned_permanent(player, item_id))
            if count > wanted:
                trims.append([item_id, count - wanted])
                if not wanted:
                    continue
                item = dict(item, count=wanted)
        keep.append(item)
    return keep, currency, trims


SETTLE_RPC = 'rlSettleDepot'


def settle_depot(player, currency, trims):
    """Tell the backend (currency in, extra copies out) and show the new
    amounts."""
    if not currency and not trims:
        return None
    try:
        # without waiting (it ran inside RPC answers: a 0.3 s freeze each);
        # ask_backend sends it again only to a backend that answers it once
        ask_backend(SETTLE_RPC, [], {'currency': currency, 'trim': trims},
                    lambda reply: depot_settled(player, currency, trims, reply))
    except Exception:
        log_error('local-depot-settle-error')
    return None


def depot_settled(player, currency, trims, reply):
    if reply is not None and reply.get('ok', True):
        applied = apply_server_props(player, reply.get('props'))
        refresh_currency_ui(player, applied)
    log('local-depot-settled', currency=safe(currency, 400), trim=safe(trims, 400),
        ok=safe(reply.get('ok') if isinstance(reply, dict) else None))
    return reply


def push_server_items(player, items, reason='reply'):
    """Put the items the local server granted into the game's DEPOT."""
    if not items or not isinstance(items, (list, tuple)):
        return 0
    items, currency, trims = depot_settlement(player, [item for item in items if isinstance(item, dict)])
    settle_depot(player, currency, trims)
    pushed = []
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            item_id = int(item.get('item'))
            count = int(item.get('count', 1))
        except (TypeError, ValueError):
            continue
        if count <= 0:
            continue
        taken = _push_one_item(player, item_id, count, item.get('expires') or 0,
                               item.get('package'))
        if taken is not None:
            pushed.append((item_id, count, taken))
    if pushed:
        log('local-depot-push', reason=reason, count=len(pushed),
            items=[{'item': entry[0], 'count': entry[1], 'package': entry[2]}
                   for entry in pushed[:20]])
    missing = len([item for item in items if isinstance(item, dict)]) - len(pushed)
    if missing > 0:
        log('local-depot-push-missed', reason=reason, count=missing)
    return len(pushed)


# --------------------------------------------------------------------------
# World chat between game windows
# --------------------------------------------------------------------------
# Every message goes to the local backend (chat RPC) and is kept there; each
# lobby asks it once a second for what the others said on the world /
# recruiting channels since its last ask, and shows it as the server's onChat.

CHAT_POLL = 1.0
CHAT_TIMEOUT = 0.1
CHAT_WAIT = 3.0                         # s an ask may go unanswered before it counts as a miss
CHAT_BACKOFF = 20.0                     # s between asks once the backend stops answering (an older one)
CHAT_MISSES = 3
# Online 16-19% of datagrams are lost: an ask unanswered this long goes again
# (it only reads, so twice is harmless) instead of waiting out CHAT_WAIT.
CHAT_RESEND = 0.7
CHAT_RESENDS = 2
# 'pafter': the newest event (backend player_events: friend requests...) this
# lobby has, -1 until the backend has said where they are.  'seq' numbers the
# asks; a backend that echoes it lets a late answer to an older ask be dropped.
_chat_sync = {'after': -1, 'pafter': -1, 'player': None, 'running': False, 'misses': 0,
              'gid': None, 'seq': 0}


def start_chat_sync(player):
    gid = local_gid()
    if _chat_sync.get('gid') != gid:
        # another character: its own place in the chat.  The same one back
        # from a battle keeps it, so what was said meanwhile still arrives.
        _chat_sync.update(after=-1, gid=gid)
    _chat_sync.update(pafter=-1, player=player, asked=None, pieces=None)
    install_player_cards()
    if not _chat_sync['running']:
        _chat_sync['running'] = True
        call_later(CHAT_POLL, chat_sync_tick)
    return True


def chat_sync_tick():
    player = _chat_sync.get('player')
    try:
        if player is not None and BigWorld.player() is player:      # in the lobby, not a battle
            pull_world_chat(player)
    except Exception:
        log_error('local-chat-sync-error')
    call_later(CHAT_POLL if _chat_sync['misses'] < CHAT_MISSES else CHAT_BACKOFF, chat_sync_tick)


def pull_world_chat(player):
    """The answer to last second's ask (if it came), then the next ask - the
    game never waits for the backend (it waited 75 ms a second online)."""
    if not RPC_ASYNC:
        try:
            return show_world_chat(player, json.loads(_udp_exchange(
                _with_session(CHAT_REQUEST + ' ', _chat_cursors()), 65535, CHAT_TIMEOUT)))
        except Exception:
            _chat_sync['misses'] += 1
            return 0
    client = _chat_sync.get('socket')
    if client is None:
        client = _chat_sync['socket'] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        client.setblocking(0)
    reply = None
    while reply is None:
        pieces = _chat_sync.get('pieces') or PieceBuffer()
        _chat_sync['pieces'] = pieces
        try:
            data = pieces.feed(client.recv(65535))
        except Exception:
            break
        if data is not None:
            _chat_sync['pieces'] = None
            reply = _chat_reply(data)   # None: a late answer to an older ask - read on
    if reply is None and _chat_sync.get('asked'):
        pieces = _chat_sync.get('pieces') or PieceBuffer()
        if not pieces.ask_missing(client, _backend['address']):
            _resend_chat_ask(client, pieces)
    if _chat_sync.get('asked') and reply is None and time.time() - _chat_sync['asked'] > CHAT_WAIT:
        _chat_sync['misses'] += 1       # no answer: a backend without world chat - asked less often
        _chat_sync['asked'] = None
    try:
        if reply is None and not _chat_sync.get('asked'):
            _chat_sync['seq'] = _chat_sync.get('seq', 0) + 1
            request = _with_session(CHAT_REQUEST + ' ', _chat_cursors())
            request = request if isinstance(request, bytes) else request.encode('utf-8')
            _chat_sync['pieces'] = PieceBuffer()
            _chat_sync.update(request=request, resends=0)
            client.sendto(request, _backend['address'])
            _chat_sync['asked'] = _chat_sync['sent_at'] = time.time()
    except Exception:
        pass
    if reply is None:
        return 0
    _chat_sync['asked'] = None
    return show_world_chat(player, reply)


def _chat_reply(data):
    """The answer to the open ask, or None (junk, or an older ask's answer
    that came late - its messages are shown, its pushes would be twice)."""
    try:
        reply = json.loads(data)
    except Exception:
        return None
    if not _chat_sync.get('asked') or not isinstance(reply, dict):
        return None
    seq = reply.get('seq')
    if seq is not None and seq != _chat_sync.get('seq'):
        return None
    return reply


def _resend_chat_ask(client, pieces):
    """The ask again once nothing of its answer came for CHAT_RESEND s."""
    now = time.time()
    if pieces.message is not None or _chat_sync.get('resends', 0) >= CHAT_RESENDS:
        return False
    if not _chat_sync.get('request') or now - (_chat_sync.get('sent_at') or now) < CHAT_RESEND:
        return False
    try:
        client.sendto(_chat_sync['request'], _backend['address'])
    except Exception:
        return False
    _chat_sync['resends'] = _chat_sync.get('resends', 0) + 1
    _chat_sync['sent_at'] = now
    return True


def show_world_chat(player, reply):
    _chat_sync['misses'] = 0
    reply = from_json_value(reply)      # native str: names and the pickled params['info']
    if not isinstance(reply, dict):
        return 0
    try:
        last = int(reply.get('last', -1))
    except (TypeError, ValueError):
        last = -1
    shown = 0
    after = _chat_sync['after']
    for item in reply.get('messages') or []:
        mid = item.get('id') if isinstance(item, dict) else None
        if (isinstance(mid, (int, long_type)) and not isinstance(mid, bool)
                and after >= 0 and mid <= after):
            continue                    # shown already (an ask sent twice, both answered)
        if isinstance(item, dict):
            remember_player_card(item.get('card'))
        if apply_server_callback(player, 'chat-sync', item) == 'ok':
            shown += 1
    if last >= 0:
        _chat_sync['after'] = last
    # What other players sent this one (friend request, accept...); an older
    # backend sends no 'plast'.  The cursor only moves with a reply that came,
    # so a lost one is sent again.
    for item in reply.get('pushes') or []:
        item = from_json_value(item)
        if isinstance(item, dict) and item.get('method') == 'rlPlatoon':
            clear_rpc_cache(PLATOON_READS, 'push')      # another player changed our platoon
        else:
            clear_rpc_cache(('getFriendList',), 'push')     # another player changed our friends
        apply_server_callback(player, 'push', item)
    plast = reply.get('plast')
    if isinstance(plast, (int, long_type)) and not isinstance(plast, bool) and plast >= 0:
        first = _chat_sync['pafter'] < 0
        _chat_sync['pafter'] = plast
        if first:
            # asked once the cursor exists: nothing between the lists and
            # the first push is lost
            ask_friend_lists(player)
            ask_party_state(player)
    return shown


def _chat_cursors():
    return {'after': _chat_sync['after'], 'pafter': _chat_sync['pafter'], 'seq': _chat_sync.get('seq', 0)}


# Chat avatars and rank frames: the chat bubble asks
# helpers.msf_client.batchGetPlayerData(gids, props, cb) for the sender's
# characterType and score (the frame is rank_utils.getSection(score)) - HTTP
# to msHttpAP, which is 127.0.0.1 here and never answers.  Each relayed
# message carries its sender's card; those gids are answered from it with
# cb(0, {gid: {...}}) (msf_client.onGetPlayerData's shape).  No fileID or
# portrait: the game's defaults mean "no custom photo".
CARD_PROPS = ('characterType', 'score', 'level', 'nickname')
CARDS_KEEP = 500
_player_cards = {}


def remember_player_card(card):
    try:
        gid = int(card['gid'])
    except Exception:
        return False
    if len(_player_cards) >= CARDS_KEEP and gid not in _player_cards:
        _player_cards.clear()
    # merged: a card with fewer fields (a team slot, a search row) keeps the avatar known
    known = _player_cards.setdefault(gid, {})
    known.update((key, card[key]) for key in CARD_PROPS if card.get(key) not in (None, ''))
    return True


def install_player_cards():
    try:
        msf = __import__('helpers.msf_client', fromlist=['batchGetPlayerData'])
    except Exception:
        return False
    if getattr(msf, '_rl_cards', False):
        return True
    original = getattr(msf, 'batchGetPlayerData', None)
    if not callable(original):
        return False

    def batchGetPlayerData(gids, props, cb, *args, **kwargs):
        # the original's signature was never dumped: pass anything extra on,
        # and any surprise goes to the original (chat, intimacy and the
        # leaderboards all call this on the game thread)
        try:
            known, unknown = {}, []
            for gid in gids or ():
                card = _player_cards.get(int(gid))
                if card is None:
                    unknown.append(gid)
                else:
                    known[int(gid)] = dict((name, card[name]) for name in props or () if name in card)
            if known:
                call_later(0.0, cb, 0, known)
                if unknown:
                    return original(unknown, props, cb, *args, **kwargs)
                return None
        except Exception:
            log_error('local-player-cards-error')
        return original(gids, props, cb, *args, **kwargs)

    msf._rl_original = original
    msf.batchGetPlayerData = batchGetPlayerData
    msf._rl_cards = True
    return True


_depot_synced = {'gid': None, 'player': None}
# The account's items as the backend last sent them: back from a battle the
# new lobby character is filled from these at once (the DEPOT was empty until
# the backend answered), then only what is new in the backend's answer is added.
_items_cache = {'gid': None, 'items': None}


def _item_key(item):
    return (item.get('item'), item.get('package'), item.get('expires') or 0)


def new_items(before, now):
    """What ``now`` has more of than ``before`` (pushing adds: never twice)."""
    had = {}
    for item in before or []:
        if isinstance(item, dict):
            key = _item_key(item)
            had[key] = had.get(key, 0) + int(item.get('count', 1) or 0)
    added = []
    for item in now or []:
        if not isinstance(item, dict):
            continue
        key = _item_key(item)
        count = int(item.get('count', 1) or 0)
        left = had.get(key, 0)
        if count > left:
            added.append(dict(item, count=count - left))
        had[key] = max(0, left - count)
    return added


def load_server_items(player, force=False, tries=0):
    """Fill the DEPOT with what the account owns, once per lobby character.
    Back from a battle the lobby is a new character (logOff, the hall built
    again) with empty packages: it was skipped as "the same gid" - owned
    items were gone until a restart.  The account's items are filled into
    each new lobby character."""
    if tries and not _entry_player(player):
        return 0                # a retry for an older character: it would undo the new one's mark
    gid = local_gid()
    if not force and _depot_synced['gid'] == gid and _depot_synced['player'] is player:
        return 0
    if RPC_ASYNC:
        # asked without waiting (a lobby entry froze for it online); marked
        # first, so a second call while the answer travels does not ask again
        _depot_synced.update(gid=gid, player=player)
        shown = None
        if not tries and _items_cache['gid'] == gid and _items_cache['items']:
            shown = _items_cache['items']               # filled now, never empty
            push_server_items(player, shown, reason='lobby-cache')
        send_later('items', _with_session(ITEMS_REQUEST + ' '),
                   lambda text: server_items_reply(player, gid, text, tries, shown))
        return 0
    try:
        reply = from_json_value(json.loads(
            _udp_exchange(_with_session(ITEMS_REQUEST + ' '), 65535)))
    except Exception:
        log_error('local-depot-items-error')
        return 0
    items = reply.get('items') if isinstance(reply, dict) else None
    _depot_synced.update(gid=gid, player=player)
    return push_server_items(player, items, reason='lobby')


def server_items_reply(player, gid, text, tries, shown=None):
    reply = None
    if text is not None:
        try:
            reply = from_json_value(json.loads(text))
        except Exception:
            log_error('local-depot-items-error')
    if _depot_synced['player'] is not player:
        return 0                # a newer lobby character asked for its own
    if not isinstance(reply, dict):
        _depot_synced.update(gid=None, player=None)     # not filled: the next call asks again
        if shown is not None:
            _depot_synced.update(gid=gid, player=player)   # the cached items are in: no second fill
        elif tries < ENTRY_RETRIES:
            log('local-depot-items-retry', tries=tries + 1)
            call_later(ENTRY_RETRY_DELAY, load_server_items, player, False, tries + 1)
        return 0
    items = reply.get('items')
    if isinstance(items, (list, tuple)):
        _items_cache.update(gid=gid, items=list(items))
    if shown is not None:
        return push_server_items(player, new_items(shown, items), reason='lobby-new')
    return push_server_items(player, items, reason='lobby')


# Purchases / box opens: never guess a success reply.  When the backend did
# not answer (or cannot handle it) the screen gets its failure callback so the
# pay-loading overlay closes.
# Leaderboards and other players' cards: only the backend's answer is shown.
SERVER_ONLY_REPLIES = frozenset(['requireRankInfo', 'requireRankList', 'queryPersonalInfo', 'requireBaseInfo',
                                 'requireRecordData',
                                 # Meet profile tabs (features/profile.py): a guess filled
                                 # someone's card with your own profile
                                 'requestIntimateRelationshipInfo', 'requestOthersIntimateRelationshipInfo',
                                 'requestOtherMarryshipInfo', 'requestOthersMarriageInfo',
                                 'requestMessageForMarriage', 'getHighestProficiencyWeapons',
                                 'queryOtherCreditScore', 'queryPersonalSpaceComment',
                                 'queryPersonalSpaceLikeCnt', 'judgePersonalSpaceLike', 'judgeSpacePartnerShow',
                                 # Activity Pts claims (features/activity.py): a guessed
                                 # success would show points and boxes never granted
                                 'getActivityReward', 'getDailyActivityReward',
                                 'getWeeklyActivityReward',
                                 # Special Distinction (features/manual.py): a guess would
                                 # show missions, rewards or a distinction never granted
                                 'asOnRequestCompleteTask', 'asOnRequestGetAwards',
                                 'asOnRequestCompensateAwards', 'asOnRequestActivityInfo',
                                 'asKeepOrChangeSeasonChoose'])
NO_SMART_REPLY = frozenset([
    'openSupplyBox', 'openMultipleSupplyBox', 'openFreeSupplyBox', 'kofOpenSupplyBox',
    'kofOpenMultipleSupplyBox', 'buyMallGood', 'buyMallGoodInAppearanceMall', 'buyDtsHallProp',
    'buyDtsHallPropWithPrice', 'buyDtsFestivalDiscountProp', 'buyRosMatchTeamMallGoods',
    'buyNewMonthcardShopGoods', 'buyChritsmas2021Good', 'businessBuyGoods', 'buyRKUBraveBook',
    'buyRKUBraveBookBundle', 'buyTitanBookType', 'batchBuyTitanBookType', 'buyLimitPackage',
    'buyHalfMonthPackage', 'requestBuyTacticalProp', 'exchangeGift', 'requestExchange',
    'openThirdAnniversarySupply', 'getOpenSupplyGift',
    # Demon Hunter wheel draws: a guessed onDtsLTDoLottery would show a prize
    # the server never gave (no failure callback: a tip only).
    'requestDtsLTDoLottery', 'requestDtsLTDoAdvanceLottery',
    # a guessed onCheckPurchaseLimitAndTime would run pay_utils.startPay
    # (IS_PAYING stuck, an SDK order) for a top-up the server never allowed
    'requestRealNameAuthenCheckBeforeRequsetingPayGoods', 'checkPurchaseLimitAndTime',
    # Benefits rewards: a guessed onRequestDtsLevelAward without items crashed
    # generateArgsForUIItemDisplay (IndexError) and showed a reward never given;
    # unanswered, the player gets the tip and clicks again
    'requestDtsLevelAward', 'requestDtsSigninAward',
])
SUPPLY_FAILURE_CALLBACKS = {
    'openSupplyBox': 'onOpenSupplyBoxFailed',
    'openFreeSupplyBox': 'onOpenSupplyBoxFailed',
    'openMultipleSupplyBox': 'onMultiOpenSupplyBoxFailed',
}
SERVER_CANNOT = 'The local server cannot do this yet.'


def answer_unanswered_purchase(player, name, args, reply):
    try:
        if reply is None:
            tip = SERVER_SILENT
        else:
            tip = reply.get('tip') or reply.get('error') or SERVER_CANNOT
            if not isinstance(tip, string_types):
                tip = SERVER_CANNOT
        tip = to_native_str(tip)
        log('local-rpc-purchase-unanswered', method=name, timeout=reply is None,
            args=[safe(item, 120) for item in args])
        show_offline_tip(tip, force=True)
        callback = SUPPLY_FAILURE_CALLBACKS.get(name)
        if callback is not None:
            supplement_id = args[0] if args else 0
            call_later(SMART_REPLY_DELAY, _deliver_callback, player, callback,
                       (supplement_id, tip), 0)
        elif name == 'buyMallGood':
            # onBuyMallGoodFailed(tips, mallGoodID, num, currencyID, price,
            #                     useCashCouponList, logStr): all required
            padded = (list(args) + [0, 1, 0, 0])[:4]
            call_later(SMART_REPLY_DELAY, _deliver_callback, player, 'onBuyMallGoodFailed',
                       tuple([tip] + padded + [[], '']), 0)
    except Exception:
        log_error('local-rpc-purchase-unanswered-error', method=name)


# The supply schedule (monthly Supreme box, sale windows) ends in 2022; the
# supply code reads the clock as if it were still the game's last season.
SERVICE_DATE = '2022.03.01 12:00:00'


class ServiceClock(object):
    """A ``time`` module for supplement_utils: running, but shifted back to
    SERVICE_DATE (only time.time() changes)."""

    def __init__(self, real, service_date=SERVICE_DATE):
        self._rl_real = real
        self._rl_offset = real.time() - real.mktime(real.strptime(service_date, '%Y.%m.%d %H:%M:%S'))

    def time(self):
        return self._rl_real.time() - self._rl_offset

    def __getattr__(self, name):
        return getattr(self._rl_real, name)


def install_service_clock():
    try:
        module = __import__('supplement_utils')
    except Exception:
        return False
    if isinstance(getattr(module, 'time', None), ServiceClock):
        return False
    module.time = ServiceClock(time)
    log('local-service-clock', date=SERVICE_DATE, module='supplement_utils')
    return True


# UIMain._get_ui writes the lobby's "Monthly Offer" tile (panel_monthly/
# panel_countdown_month txt_2 / txt_2_0) from this function, which counts down
# to the 2021 event table's OFFLINE_TIME against the real clock: always 00d00h.
# The backend says when this month's offer ends (supplement props).
MONTHLY_OFFER_END_PROP = 'rlMonthlyOfferEnd'
MONTHLY_OFFER_FUNCTION = 'monthPayRebateCountDonwFun'


def monthly_offer_left(end, now):
    # Exactly '%02dd%02dh': _get_ui splits it at 'd' and 'h'.
    hours = max(0, int(end - now)) // 3600
    return '%02dd%02dh' % (min(hours // 24, 99), hours % 24)


def install_monthly_offer_countdown(player):
    """Patch whichever class of the player defines monthPayRebateCountDonwFun
    (inherited or copied mixin method) to count down to the backend's end."""
    owner = None
    for klass in getattr(type(player), '__mro__', ()):
        if MONTHLY_OFFER_FUNCTION in getattr(klass, '__dict__', {}):
            owner = klass
            break
    if owner is None:
        try:
            owner = __import__('iMonthPayRebateSpecialAward').iMonthPayRebateSpecialAward
        except Exception:
            return False
    original = owner.__dict__.get(MONTHLY_OFFER_FUNCTION)
    if original is None or getattr(original, '_rl_monthly_offer', False):
        return False

    def monthPayRebateCountDonwFun(self):
        try:
            # __dict__, not getattr: local_getattribute's defaults must not answer.
            end = getattr(self, '__dict__', {}).get(MONTHLY_OFFER_END_PROP)
            if isinstance(end, bool) or not isinstance(end, (int, long_type, float)) or end <= 0:
                return original(self)
            text = monthly_offer_left(end, time.time())
            if not _lobby.get('offer_logged'):
                _lobby['offer_logged'] = True
                log('local-monthly-offer-countdown', text=text)
            return text
        except Exception:
            log_error('local-monthly-offer-error')
            return original(self)
    monthPayRebateCountDonwFun._rl_monthly_offer = True
    setattr(owner, MONTHLY_OFFER_FUNCTION, monthPayRebateCountDonwFun)
    log('local-monthly-offer-installed', owner=getattr(owner, '__name__', '?'))
    return True


def supplement_prices(supplement_id):
    """CURRENCY_ID / BUY_TIMES_PRICE / BUY_MULTIPLE_TIMES_PRICE of a box as
    the server sent them, from its CURRENCY_OPTION: pairs for the two-currency
    boxes (UISupplyPackage._selectBox unpacks them), single values otherwise."""
    try:
        option = __import__('supplement_utils').legacyProperties.getSupplementData(
            int(supplement_id)).CURRENCY_OPTION
    except Exception:
        return {}

    def field(name):
        try:
            return getattr(option, name)
        except Exception:
            return None
    if field('CURRENCY_TYPE1') is not None:
        prices = {'CURRENCY_ID': (field('CURRENCY_TYPE1'), field('CURRENCY_TYPE2')),
                  'BUY_TIMES_PRICE': (field('PRICE1'), field('PRICE2'))}
        if field('MULTIPLE_BUY_PRICE1') is not None:
            prices['BUY_MULTIPLE_TIMES_PRICE'] = (field('MULTIPLE_BUY_PRICE1'), field('MULTIPLE_BUY_PRICE2'))
    elif field('CURRENCY_TYPE') is not None:
        prices = {'CURRENCY_ID': field('CURRENCY_TYPE'), 'BUY_TIMES_PRICE': field('PRICE')}
        if field('MULTIPLE_BUY_PRICE') is not None:
            prices['BUY_MULTIPLE_TIMES_PRICE'] = field('MULTIPLE_BUY_PRICE')
    else:
        return {}
    prices['NEXT_BUY_TIMES_PRICE'] = prices['BUY_TIMES_PRICE']
    return prices


def fix_supplement_entries(available):
    if not isinstance(available, dict):
        return available
    for supplement_id, entry in list(available.items()):
        if isinstance(entry, dict):
            entry.update(supplement_prices(supplement_id))
    return available


def fix_supplement_reply(reply):
    for callback in reply.get('callbacks') or []:
        if isinstance(callback, dict) and callback.get('method') == 'onQueryAvailableSupplement':
            args = callback.get('args') or []
            if args:
                fix_supplement_entries(args[0])
    return reply


def _plain_supplement_entries(data):
    """availSupplementDict: {int supplementID: dict record}.  The table guess
    (resolve_feature_data) found RANK_TO_SCORE once - int values under small
    int keys that the tabs would show as boxes 1, 2...; only int-keyed dict
    records are kept (_initBoxWidget_generalBox calls .get on each)."""
    result = {}
    try:
        for key, value in list(data.items()):
            if isinstance(key, bool) or not isinstance(key, (int, long_type)):
                continue
            if isinstance(value, dict):
                result[key] = value
    except Exception:
        log_error('local-supplement-entries-error')
    return result


class LocalServerMailbox(object):
    """Stands in for the BigWorld base/cell mailbox of the local player."""

    def __init__(self, owner, kind, native=None):
        object.__setattr__(self, '_rl_owner', owner)
        object.__setattr__(self, '_rl_kind', kind)
        object.__setattr__(self, '_rl_native', native)

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        mailbox = self

        def local_rpc(*args, **kwargs):
            # A remote call never raises in the caller online; nor may ours.
            try:
                return handle_rpc(mailbox, name, args, kwargs)
            except Exception:
                log_error('local-rpc-error', method=safe(name, 120))
                return None
        local_rpc.__name__ = str(name)
        return local_rpc

    def __nonzero__(self):
        return True
    __bool__ = __nonzero__

    def __repr__(self):
        return '<LocalServerMailbox %s>' % self._rl_kind


_mailbox_target = {'player': None, 'mailbox': None}
_missing_reported = set()


def _report_missing_attribute(name):
    if name not in _missing_reported:
        _missing_reported.add(name)
        log('local-player-attribute-defaulted', name=name)


def install_local_mailboxes(player, kinds=('base',)):
    """Route player.base to a LocalServerMailbox.

    PlayerAthlete.base is resolved by the entity's C getattr before Python
    class attributes are consulted, and cannot be assigned.  Overriding
    __getattribute__ on the Python class runs first for every lookup, so
    'base' can be answered there for the local player only; every other
    attribute (and every other entity) goes straight to the native lookup.
    """
    player_class = type(player)
    native = player.base
    mailbox = LocalServerMailbox(player, 'base', native)
    _mailbox_target['player'] = player
    _mailbox_target['mailbox'] = mailbox
    # The battleground talks to its cell (the waypoint, shooting, pickups,
    # the plane): routed too when asked, so those calls reach the PyServer
    # and are logged instead of vanishing into a cell that does not exist.
    _mailbox_target['cell'] = None
    if 'cell' in kinds:
        try:
            native_cell = player.cell
        except Exception:
            native_cell = None
        _mailbox_target['cell'] = LocalServerMailbox(player, 'cell', native_cell)
    if not player_class.__dict__.get('_rl_getattribute_installed'):
        original = player_class.__getattribute__
        target = _mailbox_target

        def local_getattribute(self, name):
            if self is target['player']:
                if name == 'base':
                    return target['mailbox']
                if name == 'cell' and target.get('cell') is not None:
                    return target['cell']
                try:
                    return original(self, name)
                except AttributeError:
                    # Online-only snapshot properties the local entity never
                    # received (dtsInGameActionAppearanceIDs, personalRecommendCanBuy,
                    # hasDroneRewardToGet...): answer an empty/false value.
                    # RISK: hasattr(player, X) is now True for every name matching
                    # missing_player_default's patterns, so client code that uses
                    # hasattr as a feature check (typically on *Data/*Info) takes
                    # the "feature present" branch with an empty value.  That is
                    # why only the listed name patterns are answered, never
                    # '_private' names or method-looking names; anything else
                    # still raises.
                    value = missing_player_default(name)
                    if value is _NO_DEFAULT and battle_running():
                        value = battle_player_default(name)
                    if value is _NO_DEFAULT:
                        raise
                    _report_missing_attribute(name)
                    if isinstance(value, (list, dict)):
                        # Keep containers so the caller's appends/updates stick.
                        try:
                            setattr(self, name, value)
                        except Exception:
                            pass
                    return value
            return original(self, name)

        try:
            player_class.__getattribute__ = local_getattribute
            player_class._rl_getattribute_installed = True
        except Exception:
            log_error('local-mailbox-install-error', kind='base')
            return
    ok = getattr(player, 'base', None) is mailbox
    routed = (['base'] if ok else []) + (['cell'] if _mailbox_target.get('cell') is not None
                                          and getattr(player, 'cell', None) is _mailbox_target['cell']
                                          else [])
    log('local-mailbox-installed', kinds=routed, native=type(native).__name__,
        via='%s.__getattribute__' % player_class.__name__)


# --------------------------------------------------------------------------
# Discovery: which server calls can the lobby make?
# --------------------------------------------------------------------------
# The game's scripts are encrypted on disk, but code objects in memory still
# carry their names.  A function whose co_names contain 'base' followed by X
# calls player.base.X(...), so X is a server RPC.  Results are written to
# local_update/logs/rpc_catalog.json (see backend_server/README.md).

BUTTON_WORDS = re.compile(r'store|mall|shop|supply|recharge|topup|top_up|pay|manual|legion|'
                          r'platoon|package|depot|bag|warehouse|book|rku|team|Event$|^onClick|Btn', re.I)
# Reply callbacks (server -> client) of the six lobby features, by name.
CALLBACK_WORDS = re.compile(r'mall|supplement|supplybox|pay|yuanbao|rosmatchteam|bravebook|rku|'
                            r'package|repertory|appearance|item|chat|friend|mail', re.I)
# Keeps rpc_catalog.json reasonable; CALLBACK_WORDS matches are always kept.
MAX_CATALOG_CALLBACKS = 4000
_catalog = {'player_rpcs': {}, 'rpc_owners': {}, 'lobby_buttons': {}, 'panels': {},
            'callbacks': {}}


def _code_objects(function):
    code = getattr(function, 'func_code', None) or getattr(function, '__code__', None)
    pending = [code] if code is not None else []
    while pending:
        current = pending.pop()
        yield current
        for const in current.co_consts:
            if hasattr(const, 'co_names'):
                pending.append(const)


def _rpc_names(function):
    """Names used right after 'base' in a function (and its nested code)."""
    found = []
    for code in _code_objects(function):
        names = list(code.co_names)
        for index, name in enumerate(names):
            if name == 'base':
                for candidate in names[index + 1:index + 3]:
                    if candidate not in found and candidate not in ('base', 'player', 'BigWorld'):
                        found.append(candidate)
    return found


def _ui_strings(function):
    strings = []
    for code in _code_objects(function):
        for const in code.co_consts:
            if isinstance(const, string_types) and re.match(r'^UI[A-Z]\w+$', const):
                if const not in strings:
                    strings.append(const)
    return strings


def _class_functions(cls):
    seen = set()
    for klass in getattr(cls, '__mro__', (cls,)):
        for name, value in getattr(klass, '__dict__', {}).items():
            if name in seen or not isinstance(value, types.FunctionType):
                continue
            seen.add(name)
            yield klass.__name__, name, getattr(value, '_rl_original', value)


def callback_signature(function):
    """Argument names plus the names/strings the body uses - enough to see
    what shape of data a server reply callback expects."""
    code = getattr(function, 'func_code', None) or getattr(function, '__code__', None)
    if code is None:
        return None
    strings = []
    for nested in _code_objects(function):
        for const in nested.co_consts:
            if isinstance(const, string_types) and 0 < len(const) < 40 and const not in strings:
                strings.append(const)
    return {
        'args': list(code.co_varnames[:code.co_argcount]),
        'defaults': len(getattr(function, 'func_defaults', None) or ()),
        'uses': list(code.co_names)[:60],
        'strings': strings[:30],
    }


def catalog_player(player):
    for owner, name, function in _class_functions(type(player)):
        # Every reply-shaped method (profile replies such as onRequireBaseInfo,
        # queryCreditScore callbacks...), not only the CALLBACK_WORDS features.
        if ((name.startswith(('on', '_On', 'sync')) and CALLBACK_WORDS.search(name)) or
                ((name.startswith('on') or name.endswith(('CB', 'Cb', 'Callback'))) and
                 len(_catalog['callbacks']) < MAX_CATALOG_CALLBACKS)):
            if name not in _catalog['callbacks']:
                signature = callback_signature(function)
                if signature:
                    signature['owner'] = owner
                    _catalog['callbacks'][name] = signature
        rpcs = _rpc_names(function)
        if rpcs:
            _catalog['player_rpcs'][name] = rpcs
            for rpc_name in rpcs:
                owners = _catalog['rpc_owners'].setdefault(rpc_name, [])
                if '%s.%s' % (owner, name) not in owners:
                    owners.append('%s.%s' % (owner, name))


def _panel_calls(function):
    """Server RPCs a UI method triggers: direct base.X calls, plus player
    wrapper methods (player.reqX()) resolved through the player catalog."""
    calls = list(_rpc_names(function))
    for code in _code_objects(function):
        for name in code.co_names:
            for rpc_name in _catalog['player_rpcs'].get(name, ()):
                entry = '%s->%s' % (name, rpc_name)
                if entry not in calls:
                    calls.append(entry)
    return calls


def catalog_ui_class(cls, button_filter=False):
    methods = {}
    for owner, name, function in _class_functions(cls):
        if owner in ('object', 'Component', 'MonoBehaviour', 'UIBase'):
            continue
        if button_filter and not BUTTON_WORDS.search(name):
            continue
        entry = {}
        ui_names = _ui_strings(function)
        calls = _panel_calls(function)
        if ui_names:
            entry['opens'] = ui_names
        if calls:
            entry['rpcs'] = calls
        if entry or button_filter:
            methods[name] = entry
    return methods


# The discovery files (rpc_catalog.json ~600 KB, screen_code.json ~500 KB) were
# written whole, indented and key-sorted - Python 2.7's pure-Python encoder,
# ~30 ms a write on the game's thread - at every panel's first open and every
# watched screen.  Now one compact write of each, 20 s after the first change.
CATALOG_WRITE_DELAY = 20.0
CATALOG_PANEL_DELAY = 2.0
_catalog_writes = {'due': set(), 'built': False}


def write_rpc_catalog():
    schedule_catalog_write('rpc')


def schedule_catalog_write(kind):
    if not CATALOG_PATH:
        return
    if not _catalog_writes['due']:
        call_later(CATALOG_WRITE_DELAY, flush_catalog_writes)
    _catalog_writes['due'].add(kind)


def screen_code_path():
    return os.path.join(os.path.dirname(CATALOG_PATH), 'screen_code.json')


def flush_catalog_writes():
    due, _catalog_writes['due'] = _catalog_writes['due'], set()
    if 'rpc' in due:
        _write_json(CATALOG_PATH, _catalog)
    if 'screen' in due:
        _write_json(screen_code_path(), _screen_code['dumped'])


def _write_json(path, value):
    try:
        text = json.dumps(value)        # no indent / sort_keys: the C encoder (5 ms, not 30)
        with open(path, 'w') as output_file:
            output_file.write(text)
    except Exception:
        log_error('local-catalog-write-error', path=safe(path))


def build_lobby_catalog():
    """Once per game: the lobby player's class and UIMain do not change (each
    lobby entry walked them again and doubled rpc_owners)."""
    if _catalog_writes['built']:
        return
    try:
        import Globals
        player = _lobby.get('player')
        if player is not None:
            catalog_player(player)
        main_ui = getattr(Globals.uiMgr, 'UIMain', None)
        if main_ui is not None:
            _catalog['lobby_buttons'] = catalog_ui_class(type(main_ui), button_filter=True)
        _catalog_writes['built'] = player is not None and main_ui is not None
        write_rpc_catalog()
        log('local-rpc-catalog-written', player_rpcs=len(_catalog['player_rpcs']),
            callbacks=len(_catalog['callbacks']),
            lobby_buttons=sorted(_catalog['lobby_buttons'].keys())[:80])
    except Exception:
        log_error('local-rpc-catalog-error')


def catalog_panel(ui_name, ui_object):
    if ui_object is not None:
        catalog_panel_class(ui_name, type(ui_object))


def catalog_panel_class(ui_name, cls):
    if ui_name in _catalog['panels'] or cls is None:
        return
    try:
        _catalog['panels'][ui_name] = catalog_ui_class(cls)
        write_rpc_catalog()
        log('local-panel-catalogued', ui=ui_name, methods=len(_catalog['panels'][ui_name]))
    except Exception:
        log_error('local-panel-catalog-error', ui=ui_name)


# --------------------------------------------------------------------------
# Screen code dump: which names/keys the profile screens' code reads
# --------------------------------------------------------------------------
# Scripts are encrypted on disk, but loaded code objects still expose the
# attribute names (co_names) and dict keys / string constants (co_consts) a
# screen uses. Dumping them for the Meet / Personal Space / Credit / Record
# modules shows which reply fields the offline server has to provide.

SCREEN_MODULE_WATCH = re.compile(
    r'(^|\.)(UIMeet|UIPersonalSpace|UICreditSystem|UIRecord|UIStat|UIMeetPage|UIIntimate|'
    r'UIWeaponIllustration|meethttp|msf_client|HttpHelper|iRecord|iPersonalSpace|'
    r'iCreditSystem|iWeaponIllustration|iIntimate|TanTan|'
    # SUPPLY probe: every supply screen, the supplement mixins/utils and the
    # item package code (what an item push to the client must look like).
    r'UISupplyController|UISupplyPackage|UIAdvanceSupplyPackage|UIMonthlySupplyPackage|'
    r'UIHeroSupplyPackage|UIKofSupplyPackage|UIBraveBook2Supply|UIBraveBookChest|'
    r'UITimeLimitActivityOpenSupplyGift|UIItemDisplay|UIGiftBagConfirm|iSupplement|'
    r'supplement_utils|iOpenSupplyGift|PackageClient3|Package3|iDtsAppearancePackage|'
    r'iDtsRepertoryPackage|iPackage3|iCurrency|'
    # ACTIVITY probe: what UILimitActivity reads from onQueryAvailableActivity
    r'UIHotActivity|UILimitWelfareController|UILimitActivity|UIDtsActivity|'
    r'UIMainActivityRightTop|UIRankSeasonBounty|dts_main_entrance_utils)', re.I)
SCREEN_UI_WATCH = re.compile(r'Meet|PersonalSpace|Credit|Record|Intimate|Stat|Supply|Supplement|'
                             r'ItemDisplay|GiftBagConfirm|'
                             r'HotActivity|LimitWelfare|LimitActivity|DtsActivity|SeasonBounty')
MAX_SCREEN_CODE_ENTRIES = 3000
_screen_code = {'dumped': {}}


def _unwrap_callable(value):
    if isinstance(value, (staticmethod, classmethod)):
        value = getattr(value, '__func__', None)
    value = getattr(value, '_rl_original', value)
    if isinstance(value, types.MethodType):
        value = getattr(value, '__func__', value)
    if isinstance(value, types.FunctionType):
        return value
    return None


def _code_entry(function):
    code = getattr(function, 'func_code', None) or getattr(function, '__code__', None)
    if code is None:
        return None
    names = []
    strings = []
    numbers = []
    for nested in _code_objects(function):
        for name in nested.co_names:
            if name not in names:
                names.append(name)
        for const in nested.co_consts:
            if isinstance(const, string_types) and len(const) < 60 and const not in strings:
                strings.append(const)
            elif isinstance(const, (int, long_type, float)) and not isinstance(const, bool) \
                    and const not in numbers and len(numbers) < 40:
                numbers.append(const)   # e.g. the Ret value that means success
    return {
        'args': list(code.co_varnames[:code.co_argcount]),
        'names': names,
        'strings': strings,
        'numbers': numbers,
        'line': code.co_firstlineno,
    }


def dump_module_code(module):
    """{'Class.method' or 'function': {args, names, strings, line}} for the
    functions and class methods defined in this module."""
    result = {}
    module_name = getattr(module, '__name__', None)
    try:
        members = list(vars(module).items())
    except Exception:
        return result
    for name, value in members:
        if len(result) >= MAX_SCREEN_CODE_ENTRIES:
            break
        try:
            if getattr(value, '__module__', None) != module_name:
                continue
            if isinstance(value, type) or type(value).__name__ == 'classobj':
                for attr_name, attr in list(value.__dict__.items()):
                    if len(result) >= MAX_SCREEN_CODE_ENTRIES:
                        break
                    function = _unwrap_callable(attr)
                    if function is None:
                        continue
                    entry = _code_entry(function)
                    if entry is not None:
                        result['%s.%s' % (name, attr_name)] = entry
            else:
                function = _unwrap_callable(value)
                if function is None:
                    continue
                entry = _code_entry(function)
                if entry is not None:
                    result[name] = entry
        except Exception:
            continue
    return result


def dump_screen_code(reason=''):
    """Dump the watched profile-screen modules once each to screen_code.json."""
    if not CATALOG_PATH:
        return
    # nothing imported since the last look: one len() (the 10 s poll scanned
    # ~2,600 module names with a regex each time)
    count = len(sys.modules)
    if count == _screen_code.get('modules_seen'):
        return
    _screen_code['modules_seen'] = count
    try:
        dumped = _screen_code['dumped']
        added = {}
        for module_name, module in list(sys.modules.items()):
            if module is None or module_name in dumped:
                continue
            if not SCREEN_MODULE_WATCH.search(module_name):
                continue
            try:
                dumped[module_name] = dump_module_code(module)
            except Exception:
                log_error('local-screen-code-module-error', module=module_name)
                dumped[module_name] = {}
            added[module_name] = len(dumped[module_name])
        if not added:
            return
        schedule_catalog_write('screen')
        log('local-screen-code-dumped', reason=reason, modules=added, total=len(dumped))
    except Exception:
        log_error('local-screen-code-error', reason=reason)


# --------------------------------------------------------------------------
# Client table export: the game's own supply config for the backend
# --------------------------------------------------------------------------
# Supply boxes, prices and pools live in the data-property system
# (shared.lib.gametoolslib.properties: get<Camel>Data(key) accessors whose
# closure holds the table module and a parse cache; the module's raw ``data``
# dict shrinks as rows are parsed).  Once per game session, after the lobby is
# up, the rows are read a few at a time per tick and written to
# local_update/logs/client_tables.json (next to CATALOG_PATH):
#   {"version": 1,
#    "tables": {<Camel>: {str(key): {FIELD: value}}},
#    "raw":    {<Camel>: {str(key): <raw row>}}      (first rows, field names)
#    "enums":  {"MallCurrencyType": {NAME: id}, "SupplementKindEnum": {...}, ...},
#    "kinds":  {str(supplementID): supplement_utils.getSupplementKind(id)},
#    "missing": [<Camel>...], "errors": {...}, "exported_at": <unix time>}
# backend_server/supplement_catalog.py reads it.  Read-only: nothing in the
# game is patched.

CLIENT_TABLES_VERSION = 1
CLIENT_TABLES_DELAY = 8.0
CLIENT_TABLES_TICK_SECONDS = 0.004     # work per tick on the game thread (< 1/4 frame)
CLIENT_TABLES_TICK_DELAY = 0.05
CLIENT_TABLES_MAX_BYTES = 32 * 1024 * 1024
CLIENT_TABLES_WRITE_CHUNKS = 256       # json chunks written per step
PROPS_MODULE = 'shared.lib.gametoolslib.properties'
EXPORT_TABLES = (   # the <Camel> part of get<Camel>Data
    'Supplement', 'SupplementDiscount', 'SupplementWeekendAward',
    'SupplementWeekendAwardResetprogressTime', 'SupplyShowProbability', 'HallPropShowProbability',
    'MonthSupplementParam', 'SpringFestivalMonthSupplementParam', 'AppearanceSupplementSuit',
    'TransformAppearanceSupplement', 'OpenSupplyGift', 'OpenSupplyResetTime', 'Currency',
    # groundwork for a working Happy Derby (exported with the next version bump)
    'HorseRacingAthletes', 'HorseRacingBetConfs', 'HorseRacingBetConfsList',
)
EXPORT_ENUMS = (    # (module candidates, attribute, name in "enums")
    (('const',), 'MallCurrencyType', 'MallCurrencyType'),
    (('const',), 'HallPropQuality', 'HallPropQuality'),
    (('const',), 'CURRENCY_ID_2_CURRENCY_ITEM_ID', 'CURRENCY_ID_2_CURRENCY_ITEM_ID'),
    (('shared.shared_const', 'shared_const'), 'SupplementKindEnum', 'SupplementKindEnum'),
    (('shared.shared_const', 'shared_const'), 'ItemAddEnum', 'ItemAddEnum'),
    (('supplement_utils', 'common.supplement_utils'), 'suppleKindToName', 'suppleKindToName'),
) + tuple((('horse_racing_common', 'ui.horse_racing_common'), name, 'HorseRacing.' + name) for name in (
    'OPEN_WEEDAYS', 'OPEN_TIME', 'BET_TIME', 'MATCH_TIME', 'BET_CELL', 'RESULT_BET_MAP',
    'ATHLETE_RESULT_IDXS', 'MATCH_ATHLETE_NUM', 'HORSE_RACE_DIAMOND_RATE'))
EXPORT_MAX_DEPTH = 6
EXPORT_MAX_ITEMS = 2000
EXPORT_MAX_STR = 1000
EXPORT_MAX_ROWS = 20000
EXPORT_MAX_FIELDS = 200
EXPORT_RAW_ROWS = 3
EXPORT_MAX_PROP_IDS = 20000
EXPORT_MAX_TOTAL_ROWS = 60000          # all tables together
EXPORT_MAX_NODES = 20000               # values converted per export_plain call
_EXPORT_SCALARS = (bool, int, long_type, float, type(None))
_client_tables = {'started': False, 'done': False}


def _export_text(value):
    if not isinstance(value, _unicode_type):
        try:
            value = value.decode('utf-8', 'replace')
        except Exception:
            try:
                value = _unicode_type(repr(value))
            except Exception:
                value = u'<text>'
    return value[:EXPORT_MAX_STR]


def _export_key(key):
    if isinstance(key, string_types) or isinstance(key, bytes):
        return _export_text(key)
    if isinstance(key, bool):
        return str(key)
    if isinstance(key, (int, long_type)):
        return str(key)
    try:
        return _export_text(repr(key)[:200])
    except Exception:
        return u'<key>'


def _export_fields(obj):
    """Field names of a typed data row (_types.X): instance dict, __slots__,
    descriptors, then public non-callable names from dir() (UPPER_SNAKE)."""
    names = []
    try:
        names.extend(key for key in vars(obj) if isinstance(key, string_types) and
                     not key.startswith('_'))
    except Exception:
        pass
    try:
        for klass in getattr(type(obj), '__mro__', ()):
            slots = klass.__dict__.get('__slots__', ())
            if isinstance(slots, string_types):
                slots = (slots,)
            names.extend(slot for slot in slots if not slot.startswith('_'))
    except Exception:
        pass
    try:
        for key in dir(obj):
            if not key.startswith('_') and key not in names:
                names.append(key)
    except Exception:
        pass
    seen, result = set(), []
    for name in names:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result[:EXPORT_MAX_FIELDS * 2]


def _export_class_values(value, depth, stack, budget=None):
    result = {}
    try:
        members = list(vars(value).items())
    except Exception:
        members = []
    for key, item in members:
        if not isinstance(key, string_types) or key.startswith('_'):
            continue
        if isinstance(item, _EXPORT_SCALARS) or isinstance(item, string_types):
            result[_export_key(key)] = export_plain(item, depth + 1, stack, budget)
        elif isinstance(item, (dict, list, tuple)) and depth + 1 < EXPORT_MAX_DEPTH:
            result[_export_key(key)] = export_plain(item, depth + 1, stack, budget)
    return result


def export_plain(value, depth=0, stack=None, budget=None):
    """Any game value -> JSON-safe value.  Never raises; caps depth, sizes,
    string length and the number of values per call (EXPORT_MAX_NODES);
    unknown objects become {"__type__", "__repr__"}."""
    if budget is None:
        budget = [EXPORT_MAX_NODES]
    budget[0] -= 1
    if budget[0] < 0:
        return '<truncated>'
    try:
        if isinstance(value, _EXPORT_SCALARS):
            if isinstance(value, float) and (value != value or value in (float('inf'), float('-inf'))):
                return None
            return value
        if isinstance(value, string_types) or isinstance(value, bytes):
            return _export_text(value)
        if depth >= EXPORT_MAX_DEPTH:
            return {'__type__': type(value).__name__, '__repr__': _export_text(safe(value, 200))}
        if stack is None:
            stack = set()
        if id(value) in stack:
            return '<cycle>'
        stack.add(id(value))
        try:
            if hasattr(value, '_asdict') and isinstance(value, tuple):       # namedtuple
                return export_plain(dict(value._asdict()), depth, stack, budget)
            if isinstance(value, (list, tuple, set, frozenset)):
                items = list(itertools.islice(iter(value), EXPORT_MAX_ITEMS))
                return [export_plain(item, depth + 1, stack, budget) for item in items]
            if isinstance(value, (type, types.ModuleType)) or type(value).__name__ == 'classobj':
                if isinstance(value, types.ModuleType):
                    return {'__type__': 'module', '__repr__': _export_text(safe(value, 200))}
                return _export_class_values(value, depth, stack, budget)               # enum-like class
            pairs = getattr(value, 'iteritems', None) or getattr(value, 'items', None)
            if callable(pairs):                                                # dict, TableItemDict
                result = {}
                for index, pair in enumerate(pairs()):
                    if index >= EXPORT_MAX_ITEMS:
                        result['__truncated__'] = True
                        break
                    key, item = pair
                    result[_export_key(key)] = export_plain(item, depth + 1, stack, budget)
                return result
            result = {'__type__': type(value).__name__}
            count = 0
            for name in _export_fields(value):
                if count >= EXPORT_MAX_FIELDS:
                    result['__truncated__'] = True
                    break
                try:
                    attr = getattr(value, name)
                except Exception:
                    continue
                if isinstance(attr, types.ModuleType) or (callable(attr) and not hasattr(attr, 'items')):
                    continue
                result[_export_key(name)] = export_plain(attr, depth + 1, stack, budget)
                count += 1
            if len(result) == 1:
                result['__repr__'] = _export_text(safe(value, 200))
            return result
        finally:
            stack.discard(id(value))
    except Exception as error:
        return {'__type__': safe(type(value).__name__, 80), '__error__': _export_text(safe(error, 200))}


def _export_row(value):
    plain = export_plain(value)
    if isinstance(plain, dict):
        return plain
    return {'__value__': plain}


def _find_module(names):
    for name in names:
        module = sys.modules.get(name)
        if module is not None:
            return module
    for name in names:
        suffix = '.' + name.split('.')[-1]
        for module_name, module in list(sys.modules.items()):
            if module is not None and module_name.endswith(suffix):
                return module
    for name in names:
        try:
            __import__(name)            # never fromlist '*': no package-wide imports
            module = sys.modules.get(name)
            if module is not None:
                return module
        except Exception:
            continue
    return None


def _accessor_parts(function):
    """(table module, parse cache) from a get<Camel>Data closure."""
    function = getattr(function, 'im_func', function)
    cells = getattr(function, 'func_closure', None) or getattr(function, '__closure__', None) or ()
    module = cache = None
    for cell in cells:
        try:
            content = cell.cell_contents
        except Exception:
            continue
        if isinstance(content, types.ModuleType):
            module = content
        elif isinstance(content, dict) and cache is None:
            cache = content
    return module, cache


def _table_keys(getter):
    """Every key of a properties table: unparsed rows + already parsed ones.
    None when the accessor's closure cannot be read."""
    module, cache = _accessor_parts(getter)
    if module is None and cache is None:
        return None
    keys = []
    seen = set()
    sources = [cache or {}]
    for attr in ('data', 'staticData'):
        table = getattr(module, attr, None) if module is not None else None
        if table is not None and hasattr(table, 'keys'):
            sources.append(table)
    for source in sources:
        try:
            for key in list(source.keys()):
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        except Exception:
            continue
    try:
        keys.sort()
    except Exception:
        pass
    return keys


def _table_getter(props, camel):
    """The game's get<Camel>Data accessor.  It is only ever called with keys
    the table itself lists (never a probe key such as -1)."""
    getter = getattr(props, 'get%sData' % camel, None)
    return getter if callable(getter) else None


def _raw_rows(props, camel, limit=EXPORT_RAW_ROWS):
    iterator = getattr(props, 'iter%sRawData' % camel, None)
    rows = {}
    if not callable(iterator):
        return rows
    try:
        for entry in itertools.islice(iterator(), limit):
            if isinstance(entry, tuple) and len(entry) == 2:
                rows[_export_key(entry[0])] = export_plain(entry[1])
            else:
                rows[str(len(rows))] = export_plain(entry)
    except Exception:
        log_error('local-client-tables-raw-error', table=camel)
    return rows


def _collect_ints(value, found, depth=0):
    if len(found) >= EXPORT_MAX_PROP_IDS or depth > EXPORT_MAX_DEPTH + 2:
        return
    if isinstance(value, bool):
        return
    if isinstance(value, (int, long_type)):
        if value >= 1000:
            found.add(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, string_types) and key.isdigit():
                found.add(int(key))
            _collect_ints(item, found, depth + 1)
    elif isinstance(value, list):
        for item in value:
            _collect_ints(item, found, depth + 1)


def _export_table_steps(props, camel, result, original_keys):
    """Generator: export one table, one row per step."""
    getter = _table_getter(props, camel)
    if getter is None:
        result['missing'].append(camel)
        return
    table = result['tables'].setdefault(camel, {})
    result['raw'][camel] = _raw_rows(props, camel)
    keys = _table_keys(getter)
    if keys is None:
        # No closure to read: fall back to the generated iterator.
        iterator = getattr(props, 'iter%sData' % camel, None)
        if not callable(iterator):
            result['errors'][camel] = 'no keys and no iterator'
            return
        rows = iterator()
        while len(table) < EXPORT_MAX_ROWS:
            try:
                entry = next(rows)
            except StopIteration:
                break
            except Exception:
                log_error('local-client-tables-row-error', table=camel)
                result['errors'][camel] = 'iterator failed'
                break
            if isinstance(entry, tuple) and len(entry) == 2:
                key, row = entry
            else:
                key, row = getattr(entry, 'ID', len(table)), entry
            table[_export_key(key)] = _export_row(row)
            original_keys.setdefault(camel, []).append(key)
            yield
        return
    for key in keys[:EXPORT_MAX_ROWS]:
        try:
            row = getter(key)
        except Exception:
            result['errors'].setdefault(camel, safe(sys.exc_info()[1], 300))
            yield
            continue
        if row is not None:
            table[_export_key(key)] = _export_row(row)
            original_keys.setdefault(camel, []).append(key)
        yield


def _export_row_budget(result):
    """Rows exported so far stay under EXPORT_MAX_TOTAL_ROWS."""
    return sum(len(rows) for rows in result['tables'].values()) < EXPORT_MAX_TOTAL_ROWS


def _export_steps(result):
    """Generator: the whole export, one small step per next(); every section
    is guarded so one failure only loses that section."""
    props = _find_module((PROPS_MODULE,))
    if props is None:
        result['missing'].append(PROPS_MODULE)
    original_keys = {}
    if props is not None:
        for camel in EXPORT_TABLES:
            if not _export_row_budget(result):
                result['errors'][camel] = 'row budget exhausted'
                continue
            try:
                for _step in _export_table_steps(props, camel, result, original_keys):
                    yield
                    if not _export_row_budget(result):
                        result['errors'][camel] = 'row budget exhausted'
                        break
            except Exception:
                log_error('local-client-tables-table-error', table=camel)
                result['errors'][camel] = 'export failed'
    # Kinds: supplement_utils.getSupplementKind(id) (decorated: just call it).
    try:
        utils = _find_module(('supplement_utils', 'common.supplement_utils'))
        kind_of = getattr(utils, 'getSupplementKind', None) if utils is not None else None
    except Exception:
        kind_of = None
    if callable(kind_of):
        for key in original_keys.get('Supplement', []):
            try:
                result['kinds'][_export_key(key)] = export_plain(kind_of(key))
            except Exception:
                result['errors'].setdefault('kinds', safe(sys.exc_info()[1], 300))
            yield
    else:
        result['missing'].append('supplement_utils.getSupplementKind')
    # Hall props the exported supply rows mention (appearance / prop ids).
    if props is not None:
        try:
            getter = _table_getter(props, 'DtsHallProp')
            keys = _table_keys(getter) if getter is not None else None
        except Exception:
            getter = keys = None
            result['errors']['DtsHallProp'] = safe(sys.exc_info()[1], 300)
        if keys is None:
            result['missing'].append('DtsHallProp')
        else:
            known = set(keys)
            wanted = set()
            for camel, rows in list(result['tables'].items()):
                try:
                    _collect_ints(rows, wanted)
                except Exception:
                    pass
                yield
            table = result['tables'].setdefault('DtsHallProp', {})
            for prop_id in sorted(wanted):
                if prop_id not in known:
                    continue            # never ask the accessor for unknown ids
                if not _export_row_budget(result):
                    result['errors']['DtsHallProp'] = 'row budget exhausted'
                    break
                try:
                    row = getter(prop_id)
                    if row is not None:
                        table[_export_key(prop_id)] = _export_row(row)
                except Exception:
                    result['errors'].setdefault('DtsHallProp', safe(sys.exc_info()[1], 300))
                yield
    for module_names, attr, label in EXPORT_ENUMS:
        try:
            module = _find_module(module_names)
            if module is not None and hasattr(module, attr):
                result['enums'][label] = export_plain(getattr(module, attr))
            else:
                result['missing'].append(label)
        except Exception:
            log_error('local-client-tables-enum-error', enum=label)
        yield


def client_tables_path():
    if not CATALOG_PATH:
        return None
    return os.path.join(os.path.dirname(CATALOG_PATH), 'client_tables.json')


def _dh_jsonable(value, depth=0):
    """A copy json can always encode: str keys, lists, plain scalars, repr() for the rest."""
    if depth > 14:
        return repr(value)[:200]
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not isinstance(key, string_types):
                try:
                    key = str(key)
                except Exception:
                    key = repr(key)
            out[_dh_jsonable(key)] = _dh_jsonable(item, depth + 1)
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_dh_jsonable(item, depth + 1) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, float):
        return value if value == value and value not in (float('inf'), float('-inf')) else None
    if isinstance(value, (int, long)):
        return value
    if isinstance(value, str):
        try:
            return value.decode('utf-8')
        except Exception:
            return value.decode('latin-1')
    if isinstance(value, string_types):
        return value
    try:
        return repr(value)[:200]
    except Exception:
        return '<unrepr>'


def _write_steps(result, started):
    """Generator: encode + write client_tables.json a few chunks per step (a
    single json.dump of a big export would stall a frame), then swap it in."""
    path = client_tables_path()
    temp_path = path + '.tmp'
    result['exported_at'] = time.time()
    written = 0
    output_file = open(temp_path, 'w')
    try:
        chunks = iter(json.JSONEncoder(sort_keys=True).iterencode(_dh_jsonable(result)))
        while True:
            batch = list(itertools.islice(chunks, CLIENT_TABLES_WRITE_CHUNKS))
            if not batch:
                break
            text = ''.join(batch)
            output_file.write(text)
            written += len(text)
            if written > CLIENT_TABLES_MAX_BYTES:
                raise ValueError('client tables export exceeds %d bytes' % CLIENT_TABLES_MAX_BYTES)
            yield
    except Exception:
        output_file.close()
        try:
            os.remove(temp_path)
        except Exception:
            pass
        raise
    output_file.close()
    try:
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass
    os.rename(temp_path, path)
    log('local-client-tables-exported', path=path, seconds=round(time.time() - started, 2),
        bytes=written, sizes=dict((name, len(rows)) for name, rows in result['tables'].items()),
        enums=sorted(result['enums'].keys()), kinds=len(result['kinds']),
        missing=result['missing'], errors=result['errors'])


def _client_table_steps(result, started):
    for _step in _export_steps(result):
        yield
    for _step in _write_steps(result, started):
        yield
    _client_tables['done'] = True
    try:
        with open(client_tables_marker(), 'w') as marker:
            marker.write(str(CLIENT_TABLES_VERSION))
    except Exception:
        log_error('local-client-tables-marker-error')


def client_tables_marker():
    return client_tables_path() + '.version'


def client_tables_current():
    """The game's tables do not change between sessions: once exported
    (this export version), later logins skip the ~30 s export."""
    try:
        if not os.path.exists(client_tables_path()):
            return False
        with open(client_tables_marker()) as marker:
            return marker.read().strip() == str(CLIENT_TABLES_VERSION)
    except Exception:
        return False


def _run_client_table_export(steps, result, started, ticks=0):
    """One time slice (CLIENT_TABLES_TICK_SECONDS) of the export per callback."""
    deadline = time.time() + CLIENT_TABLES_TICK_SECONDS
    try:
        while True:
            next(steps)
            if time.time() >= deadline:
                break
    except StopIteration:
        return
    except Exception:
        log_error('local-client-tables-error', ticks=ticks)
        return
    call_later(CLIENT_TABLES_TICK_DELAY, _run_client_table_export, steps, result, started,
               ticks + 1)


def start_client_table_export():
    """Once per game session (a re-injected hook does not export again)."""
    try:
        if _client_tables['started'] or getattr(BigWorld, '_rl_client_tables_started', False):
            return False
        if client_tables_path() is None:
            return False
        if client_tables_current():
            debug('local-client-tables-current')
            return False
        _client_tables['started'] = True
        try:
            BigWorld._rl_client_tables_started = True
        except Exception:
            pass
        result = {'version': CLIENT_TABLES_VERSION, 'tables': {}, 'raw': {}, 'enums': {},
                  'kinds': {}, 'missing': [], 'errors': {}}
        log('local-client-tables-started')
        started = time.time()
        call_later(0.0, _run_client_table_export, _client_table_steps(result, started), result,
                   started)
        return True
    except Exception:
        log_error('local-client-tables-start-error')
        return False


# --------------------------------------------------------------------------
# Server list: your character (name, level) on each server
# --------------------------------------------------------------------------
# UIServerList and the login panel's server box ask
# helpers.UserInfoMgr.userInfoMgr.getCharacterInfo(<server name>) for the
# character on a server.  Online that is the role list of the account; here
# it is the account's characters in accounts.db (ROS_LOCAL_ROLES_V1), and
# None for servers without a character (nothing is shown for them).

ROLES_REQUEST = 'ROS_LOCAL_ROLES_V1'
SERVER_LIST_WATCH = re.compile(r'(^|\.)(UIServerList|UILogin|UserInfoMgr|ServerNameTranslation|UILoading)$')
_server_roles = {'roles': None, 'servers': None, 'fetched': 0.0, 'patched': None, 'dumped': False,
                 'seen': {}, 'keys': [], 'login_refreshed': None, 'error_logged': False,
                 'prepared': False}


def _plain_text(value):
    """A native str for comparing server names (unicode -> UTF-8 in Python 2)."""
    if value is None:
        return ''
    if not isinstance(value, str):
        try:
            value = value.encode('utf-8') if isinstance(value, string_types) else str(value)
        except Exception:
            return ''
    return value.strip()


def login_screen_account():
    """The account the server list belongs to: the launcher's --account, the
    account of this game's last login, else the backend's default identity."""
    return FORCED_ACCOUNT or _backend.get('account') or None


def fetch_server_roles(force=False):
    now = time.time()
    cached = _server_roles['roles']
    if not force and cached is not None and now - _server_roles['fetched'] < 5.0:
        return cached
    body = {}
    account = login_screen_account()
    if account:
        body['account'] = account
    if RPC_ASYNC and not force and cached is not None:
        # stale: the cached names now, fresh ones when the answer comes (the
        # server list asks for each cell; a wait here was up to 1.5 s online)
        if not _server_roles.get('asking'):
            _server_roles['asking'] = True
            send_later('roles', ROLES_REQUEST + ' ' + json.dumps(body), server_roles_reply)
        return cached
    try:
        reply = json.loads(_udp_exchange(ROLES_REQUEST + ' ' + json.dumps(body), 65535, timeout=0.5))
        if not isinstance(reply, dict):
            raise ValueError('roles reply must be an object')
    except Exception:
        if not _server_roles['error_logged']:
            _server_roles['error_logged'] = True
            log_error('local-server-roles-error', account=safe(account))
        # remembered as a (blank) answer: else every server-list cell and
        # every login-watch tick waited up to 1.5 s again while it was down;
        # past 5 s the next ask goes without waiting (send_later above)
        _server_roles.update(roles=_server_roles['roles'] or {}, fetched=time.time())
        return _server_roles['roles']
    return _store_server_roles(reply, now)


def server_roles_reply(text):
    _server_roles['asking'] = False
    try:
        reply = json.loads(text) if text is not None else None
    except Exception:
        reply = None
    if isinstance(reply, dict):
        _store_server_roles(reply, time.time())


def _store_server_roles(reply, now):
    roles = {}
    for name, role in (reply.get('roles') or {}).items():
        if not isinstance(role, dict):
            continue
        clean = {}
        for key, value in role.items():
            clean[str(key)] = to_native_str(value) if isinstance(value, string_types) else value
        roles[_plain_text(name).lower()] = clean
        if clean.get('serverId') is not None:
            roles[str(clean['serverId'])] = clean
    servers = set(_plain_text(name).lower() for name in (reply.get('servers') or []))
    servers.update(str(server_id) for server_id in (reply.get('serverIds') or []))
    if _server_roles['roles'] != roles:
        log('local-server-roles', account=safe(reply.get('account')),
            roles=safe(dict((name, role.get('nickname')) for name, role in roles.items())))
    _server_roles.update(roles=roles, servers=servers, fetched=now)
    return roles


def _role_key_default(key):
    lowered = str(key).lower()
    if 'name' in lowered or 'nick' in lowered or 'str' in lowered or 'text' in lowered:
        return ''
    if lowered in ('lv', 'level') or lowered.endswith('level'):
        return 1
    return 0


class ServerRoleInfo(dict):
    """The character on one server.  Keys the game asks for that the backend
    does not send get a neutral value and are logged (local-server-role-key)."""

    def _note(self, key):
        if key not in _server_roles['keys'] and len(_server_roles['keys']) < 100:
            _server_roles['keys'].append(key)
            log('local-server-role-key', key=safe(key))

    def __missing__(self, key):
        self._note(key)
        return _role_key_default(key)

    def get(self, key, default=None):
        if key in self:
            return dict.get(self, key)
        self._note(key)
        return default

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        return self[name]


def local_server_role(server, original_result):
    """What getCharacterInfo(server) returns: the local character, or None."""
    name = _plain_text(server)
    roles = fetch_server_roles()
    known = _server_roles['servers'] or set()
    key = name.lower()
    if key not in known and key not in roles:
        return original_result      # not a server name: leave the game's answer
    role = roles.get(key)
    if key not in _server_roles['seen']:
        _server_roles['seen'][key] = True
        log('local-server-role', server=name, original=safe(original_result, 600),
            character=safe(role and role.get('nickname')), level=safe(role and role.get('level')))
    if role is None:
        return None
    info = ServerRoleInfo()
    if isinstance(original_result, dict):
        info.update(original_result)
    info.update(role)
    for alias in ('name', 'roleName', 'playerName', 'nickName'):
        info.setdefault(alias, role.get('nickname', ''))
    info.setdefault('lv', role.get('level', 1))
    return info


def patch_user_info_mgr():
    """Wrap userInfoMgr.getCharacterInfo once (a plain helper, not a UI component)."""
    module = sys.modules.get('helpers.UserInfoMgr')
    if module is None:
        try:
            module = __import__('helpers.UserInfoMgr', fromlist=['userInfoMgr'])
        except Exception:
            return False
    manager = getattr(module, 'userInfoMgr', None)
    if manager is None:
        return False
    if _server_roles['patched'] is manager:
        return True
    original = getattr(manager, 'getCharacterInfo', None)
    if not callable(original):
        return False
    original = getattr(original, '_rl_original', original)

    def local_get_character_info(*args, **kwargs):
        try:
            result = original(*args, **kwargs)
        except Exception:
            log_error('local-server-role-original-error', args=safe(args))
            result = None
        try:
            server = args[0] if args else (list(kwargs.values())[0] if kwargs else None)
            return local_server_role(server, result)
        except Exception:
            log_error('local-server-role-error', args=safe(args))
            return result

    local_get_character_info._rl_original = original
    try:
        manager.getCharacterInfo = local_get_character_info
    except Exception:
        log_error('local-server-role-patch-error')
        return False
    _server_roles['patched'] = manager
    log('local-server-roles-patched')
    return True


def _ui_open(ui_mgr, name):
    ui = getattr(ui_mgr, name, None)
    if ui is None:
        try:
            ui = getattr(ui_mgr, '____all_ui__', {}).get(name)
        except Exception:
            ui = None
    return ui if ui is not None and getattr(ui, 'is_enter', False) else None


SCREEN_LIFECYCLE = frozenset(['Awake', 'Start', 'Update', 'LateUpdate', 'FixedUpdate', 'OnDestroy',
                              'OnEnable', 'OnDisable'])


def guard_screen_class(cls):
    """Guard every own method of a screen class except engine lifecycle calls
    and libclaudia message handlers (wrapping those breaks SendMessage)."""
    handlers = set(getattr(cls, '____messageHandlers__', None) or ())
    names = []
    for name, value in list(cls.__dict__.items()):
        if not isinstance(value, types.FunctionType) or name.startswith('__'):
            continue
        if name in SCREEN_LIFECYCLE or name in handlers or getattr(value, '____isMessageHandler__', False):
            continue
        names.append(name)
    return guard_class_methods(cls, only=names)


def prepare_server_list_screen(Globals):
    """Once, on the login screen: dump the server-list code, guard the list's
    methods (one failing cell stopped the whole list and its close button)
    and trace screen navigation so errors are logged."""
    if _server_roles['prepared']:
        return
    _server_roles['prepared'] = True
    try:
        trace_ui_manager(type(Globals.uiMgr))
    except Exception:
        log_error('local-login-trace-error')
    try:
        module = __import__('ui.UIServerList', fromlist=['UIServerList'])
    except Exception:
        log_error('local-server-list-import-error')
        module = None
    if module is not None:
        for value in list(vars(module).values()):
            try:
                if (isinstance(value, type) or type(value).__name__ == 'classobj') and \
                        getattr(value, '__module__', None) == module.__name__:
                    guard_screen_class(value)
            except Exception:
                log_error('local-server-list-guard-error', cls=safe(value))
    try:
        dumped = _screen_code['dumped']
        for module_name, loaded in list(sys.modules.items()):
            if loaded is not None and module_name not in dumped and SERVER_LIST_WATCH.search(module_name):
                dumped[module_name] = dump_module_code(loaded)
        schedule_catalog_write('screen')
        log('local-server-list-code-dumped', modules=sorted(name for name in dumped
                                                            if SERVER_LIST_WATCH.search(name)))
    except Exception:
        log_error('local-server-list-code-error')


def walk_ui_nodes(ui, limit=600):
    """(path, node) for the widget trees a UI object holds, depth first."""
    found = []
    seen = set()

    def walk(node, path, depth):
        if node is None or depth > 14 or len(found) >= limit or id(node) in seen:
            return
        seen.add(id(node))
        try:
            name = node.getName()
        except Exception:
            name = '?'
        here = '%s/%s' % (path, name)
        found.append((here, node))
        try:
            children = list(node.getChildren())
        except Exception:
            children = []
        for child in children:
            walk(child, here, depth + 1)
    for attr_name, value in list(getattr(ui, '__dict__', {}).items()):
        if hasattr(value, 'getChildren'):
            walk(value, str(attr_name), 0)
    return found


def _node_visible(node):
    try:
        return bool(node.isVisible())
    except Exception:
        return None


def _node_percent(node):
    getter = getattr(node, 'getPercent', None)
    if not callable(getter):
        return None
    try:
        return getter()
    except Exception:
        return None


def describe_ui(ui, event, limit=300):
    """Log a UI's text widgets / progress bars (with visibility) and plain attributes."""
    widgets = []
    try:
        for path, node in walk_ui_nodes(ui):
            text = _node_text(node)
            percent = _node_percent(node)
            if text or percent is not None:
                widgets.append([path[-120:], safe(text, 80) if text else None, percent,
                                _node_visible(node)])
                if len(widgets) >= limit:
                    break
    except Exception:
        log_error(event + '-widgets-error')
    attributes = {}
    try:
        for attr_name, value in list(getattr(ui, '__dict__', {}).items())[:200]:
            if not hasattr(value, 'getChildren'):
                attributes[str(attr_name)] = safe(value, 300)
    except Exception:
        pass
    log(event, widgets=widgets, attributes=attributes)


def dump_server_list_screen(ui):
    """Once: the server list's text widgets and attributes (what it shows)."""
    if _server_roles['dumped']:
        return
    _server_roles['dumped'] = True
    describe_ui(ui, 'local-server-list-screen')


# --------------------------------------------------------------------------
# Loading screen progress bar
# --------------------------------------------------------------------------
# Every loading screen showed no progress bar.  The bar is a ccui.LoadingBar
# (it has getPercent/setPercent) in UILoading's widget tree; show it and the
# containers above it when they are hidden, and fill it with our progress.
_loading_bars = {'described': False, 'shown': set(), 'chain_for': None}
LOADING_BAR_CHAIN_DEPTH = 16


def describe_loading_bar(ui, node):
    if _loading_bars['chain_for'] == id(ui):
        return
    _loading_bars['chain_for'] = id(ui)
    chain = []
    target = node
    for _level in range(LOADING_BAR_CHAIN_DEPTH):
        if target is None:
            break
        try:
            chain.append([target.getName(), _node_visible(target), target.getOpacity()])
            target = target.getParent()
        except Exception:
            break
    try:
        position = node.getWorldPosition()
        size = node.getContentSize()
        where = [round(position.x, 1), round(position.y, 1), round(size.width, 1), round(size.height, 1)]
    except Exception:
        where = None
    log('local-loading-bar-state', chain=chain, percent=_node_percent(node), where=where)
LOADING_BAR_NAME = re.compile(r'load|progress|bar|process', re.I)


LOADING_BAR_REWALK = 1.0                # s: no bar found yet - look again after this long
LOADING_BAR_KEEP = 10.0                 # s: a found bar is looked up again after this long


def loading_bar_nodes(ui):
    """The bar nodes of this loading screen.  set_loading runs every 0.1 s
    and the login watcher every 0.25 s; each walked up to 600 widgets and the
    loading animation hitched - the walk is now done once per screen."""
    now = time.time()
    cached = _loading_bars.get('nodes')
    if cached is not None and cached[0] is ui and             now - _loading_bars.get('walked_at', 0.0) < (LOADING_BAR_KEEP if cached[1] else LOADING_BAR_REWALK):
        return cached[1]
    found = []
    for path, node in walk_ui_nodes(ui):
        if not callable(getattr(node, 'setPercent', None)) or not callable(getattr(node, 'getPercent', None)):
            continue
        if not LOADING_BAR_NAME.search(path.rsplit('/', 1)[-1] or ''):
            continue
        found.append((path, node))
    _loading_bars['nodes'] = (ui, found)
    _loading_bars['walked_at'] = now
    return found


def show_loading_bars(ui, fraction=None):
    shown = []
    try:
        nodes = loading_bar_nodes(ui)
    except Exception:
        log_error('local-loading-bar-walk-error')
        return 0
    for path, node in nodes:
        target = node
        for _level in range(LOADING_BAR_CHAIN_DEPTH):
            if target is None:
                break
            if _node_visible(target) is False:
                try:
                    target.setVisible(True)
                    shown.append(path)
                except Exception:
                    pass
            try:
                if target.getOpacity() < 255:
                    target.setOpacity(255)
            except Exception:
                pass
            try:
                target = target.getParent()
            except Exception:
                target = None
        describe_loading_bar(ui, node)
        if fraction is not None:
            try:
                node.setPercent(max(0.0, min(100.0, float(fraction) * 100.0)))
            except Exception:
                pass
    new = [path for path in shown if path not in _loading_bars['shown']]
    if new:
        _loading_bars['shown'].update(new)
        log('local-loading-bar-shown', paths=new[:20])
    return len(shown)


def watch_loading_screen(ui_mgr):
    """Called by the login/lobby watcher: fix the bar of any loading screen."""
    loading = _ui_open(ui_mgr, 'UILoading')
    if loading is None:
        return False
    if not _loading_bars['described']:
        _loading_bars['described'] = True
        describe_ui(loading, 'local-loading-screen')
    show_loading_bars(loading)
    return True


_WATCH_TOKEN = object()
BigWorld._rl_login_watch = _WATCH_TOKEN     # a re-injected hook stops the old loop


def watch_login_screen():
    """Poll (cheap) while the login screen is up: patch the role lookup, dump
    the server list once, and refresh the server box's character name."""
    if getattr(BigWorld, '_rl_login_watch', None) is not _WATCH_TOKEN:
        return
    delay = 1.0
    try:
        import Globals
        ui_mgr = Globals.uiMgr
    except Exception:
        ui_mgr = None
    if ui_mgr is not None:
        try:
            if watch_loading_screen(ui_mgr):
                delay = 0.25
        except Exception:
            log_error('local-loading-watch-error')
        login = _ui_open(ui_mgr, 'UILogin')
        server_list = _ui_open(ui_mgr, 'UIServerList')
        if login is None and server_list is None:
            delay = min(delay, 3.0) if delay < 1.0 else 3.0
        elif patch_user_info_mgr():
            if login is not None:
                prepare_server_list_screen(Globals)
            if server_list is not None:
                fetch_server_roles(force=not _server_roles['dumped'])
                call_later(0.5, dump_server_list_screen, server_list)
            if login is not None and _server_roles['login_refreshed'] is not login:
                _server_roles['login_refreshed'] = login
                refresh = getattr(login, 'setDefaultServerNickname', None)
                if callable(refresh):
                    fetch_server_roles(force=True)
                    try:
                        refresh()
                        log('local-server-box-refreshed')
                    except Exception:
                        log_error('local-server-box-refresh-error')
    poll_screen_code()
    call_later(delay, watch_login_screen)


SCREEN_CODE_POLL_SECONDS = 10.0
_screen_code_poll = {'at': 0.0}


def poll_screen_code():
    """In the lobby, dump watched modules (supply screens, package code) soon
    after the game first imports them."""
    try:
        if not _lobby.get('entered'):
            return
        now = time.time()
        if now - _screen_code_poll['at'] < SCREEN_CODE_POLL_SECONDS:
            return
        _screen_code_poll['at'] = now
        dump_screen_code('poll')
    except Exception:
        log_error('local-screen-code-poll-error')


# --------------------------------------------------------------------------
# Loading bar (0..1 for UILoading.SetLoadingProcess)
# --------------------------------------------------------------------------

_loading = {'started': None, 'last': None}


def _loading_ui(Globals):
    loading = getattr(Globals.uiMgr, 'UILoading', None)
    if loading is None and hasattr(Globals.uiMgr, 'get_ui_obj'):
        loading = Globals.uiMgr.get_ui_obj('UILoading')
    return loading


def begin_loading(Globals, show=True, keep_progress=False):
    _loading['started'] = time.time()
    if not keep_progress:
        _loading['last'] = None
    _loading_bars['nodes'] = None           # a screen entered again may hold new widgets
    if show:
        try:
            Globals.uiMgr.enter_ui('UILoading')
            loading = _loading_ui(Globals)
            if loading is not None and hasattr(loading, 'firstLoad'):
                loading.firstLoad()
            log('local-loading-ui-entered')
        except Exception:
            log_error('local-loading-ui-warning')
    set_loading(Globals, 0.03, True)


def set_loading(Globals, fraction, force_log=False):
    try:
        fraction = max(0.0, min(1.0, float(fraction)))
        if _loading['last'] is not None:
            fraction = max(fraction, _loading['last'])
        loading = _loading_ui(Globals)
        if loading is None or not hasattr(loading, 'SetLoadingProcess'):
            return
        loading.SetLoadingProcess(fraction * 100.0)
        show_loading_bars(loading, fraction)
        solid_loading_bar(loading, fraction)
        log_loading_frames(fraction)
        if force_log or _loading['last'] is None or fraction - _loading['last'] >= 0.1:
            log('local-loading-progress', percent=round(fraction * 100.0, 1))
        _loading['last'] = fraction
    except Exception:
        log_error('local-loading-progress-warning')


LOADING_TEXT = 'Loading... %d%%'
LOADING_FILL_COLOR = (255, 204, 0, 255)
LOADING_FILL_Z = 100


def visible_span(parent, left, right):
    try:
        import cc
        screen = cc.Director.getInstance().getWinSize()
        screen_left = parent.convertToNodeSpace(cc.Vec2(0.0, 0.0)).x
        screen_right = parent.convertToNodeSpace(cc.Vec2(screen.width, 0.0)).x
    except Exception:
        return left, right
    if screen_right <= screen_left:
        return left, right
    return screen_left, screen_right


def solid_loading_bar(loading, fraction):
    bar = getattr(loading, 'load_bar', None)
    if bar is None:
        return None
    try:
        parent = bar.getParent()
        size = bar.getContentSize()
        position = bar.getPosition()
        anchor = bar.getAnchorPoint()
    except Exception:
        return None
    if parent is None:
        return None
    left, right = visible_span(parent, position.x - anchor.x * size.width,
                               position.x + (1.0 - anchor.x) * size.width)
    width = max(0.0, min(1.0, float(fraction))) * (right - left)
    bottom = position.y - anchor.y * size.height
    fill = _loading.get('fill')
    if fill is not None and _loading.get('fill_parent') is not parent:
        fill = None
    try:
        import cc
        if fill is None:
            red, green, blue, alpha = LOADING_FILL_COLOR
            fill = cc.LayerColor.create(cc.Color4B(red, green, blue, alpha), max(1.0, width), size.height)
            parent.addChild(fill, LOADING_FILL_Z)
            _loading['fill'] = fill
            _loading['fill_parent'] = parent
        fill.setPosition(cc.Vec2(left, bottom))
        fill.setContentSize(cc.Size(max(1.0, width), size.height))
        fill.setVisible(width > 0.0)
    except Exception:
        _loading['fill'] = None
        _loading['fill_parent'] = None
        if not _loading.get('fill_error_logged'):
            _loading['fill_error_logged'] = True
            log_error('local-loading-fill-error')
        return None
    return fill


def show_loading_text(Globals, fraction=None):
    try:
        loading = _loading_ui(Globals)
    except Exception:
        return False
    label = getattr(loading, 'tips_txt', None) if loading is not None else None
    setter = getattr(label, 'setString', None)
    if not callable(setter):
        return False
    if fraction is None:
        fraction = _loading['last'] or 0.0
    try:
        setter(LOADING_TEXT % int(round(max(0.0, min(1.0, fraction)) * 100.0)))
        return True
    except Exception:
        return False


def log_loading_frames(fraction):
    now = time.time()
    if now - _loading.get('frames_logged_at', 0.0) < LOADING_FRAMES_LOG_SECONDS:
        return
    _loading['frames_logged_at'] = now
    frames = render = None
    try:
        import game3d
        frames = game3d.get_frame_count()
    except Exception:
        pass
    try:
        import profiling
        render = round(float(profiling.get_render_rate()), 1)
    except Exception:
        pass
    ui_frames = running = attached = None
    try:
        import cc
        director = cc.Director.getInstance()
        ui_frames = director.getTotalFrames()
        scene = director.getRunningScene()
        running = safe(scene, 40)
        import Globals
        loading = _loading_ui(Globals)
        node = getattr(loading, 'load_bar', None) if loading is not None else None
        top = None
        while node is not None:
            top = node
            try:
                node = node.getParent()
            except Exception:
                node = None
        attached = top is not None and scene is not None and top == scene
    except Exception:
        pass
    log('local-loading-frames', percent=round(fraction * 100.0, 1), frames=frames, render_rate=render,
        ui_frames=ui_frames, running_scene=running, bar_in_running_scene=attached)


def animated_loading(Globals, seconds, resource_fraction=0.0):
    elapsed = max(0.0, time.time() - (_loading['started'] or time.time()))
    time_fraction = min(0.95, 0.03 + (elapsed / seconds) * 0.92)
    return max(time_fraction, 0.03 + resource_fraction * 0.92)


def end_loading(Globals):
    try:
        Globals.uiMgr.leave_ui('UILoading')
        log('local-loading-ui-left')
    except Exception:
        log_error('local-loading-ui-leave-warning')


# --------------------------------------------------------------------------
# Local player objects used by the character screen and the lobby
# --------------------------------------------------------------------------

class LocalCharacterBase(object):
    def __init__(self, player):
        self.player = player

    def createCharacter(self, character_id, input_name):
        import ui.UISelectCharacter as select_module
        if getattr(select_module, '_rl_create_pending', False):
            log('local-character-create-duplicate-ignored')
            return
        select_module._rl_create_pending = True
        self.player.nickname = input_name
        self.player.characterId = character_id
        log('local-character-create-request', name=safe(input_name), character_id=safe(character_id))
        call_later(0.35, finish_local_character, input_name, character_id)


class LocalCharacterPlayer(object):
    def __init__(self):
        self.gid = DEFAULT_GID
        self.id = DEFAULT_GID
        self.nickname = 'LocalPlayer'
        self.characterId = DEFAULT_CHARACTER_TYPE
        self.base = LocalCharacterBase(self)


class LocalBigWorldView(object):
    """BigWorld seen by UISelectCharacter only: player() is the local stub."""

    def __init__(self, module, player):
        self._module = module
        self._player = player

    def player(self):
        return self._player

    def __getattr__(self, name):
        return getattr(self._module, name)


# Every field a team slot is read for (UIMain._display_member_info, the
# lobby models): a teammate's card from the backend lacks some - a missing
# intimateRelationship stopped the whole team refresh, no teammate drawn.
TEAM_MEMBER_DEFAULTS = {'creditScore': 100, 'intimateRelationship': {}, 'intimacyDegree': 0, 'nationality': 0,
                        'nationalFlag': '', 'inWorld': False, 'ready': False, 'supportSeason': 0,
                        'dtsAppearanceGender': 1, 'exoID': 0,
                        'dtsEmojiID': 0, 'outGameBag': 0, 'outGameWeapon': [0, 0], 'dtsNameplateAppearance': 0,
                        'hallThemeID': 0, 'headFrameTag': 0, 'occupation': 0, 'isHuiliu': False,
                        # a teammate's model (UIMain._display_member_model.set_state):
                        # ethnicity is a DtsEthnicity key (0 human), the share suit a
                        # dict, the out-of-game weapon [weapon, position]; ROS 2 fields
                        'ethnicity': 0, 'dtsShareAppearanceSuit': {}, 'ros2Camp': 0, 'ros2ExoInfo': {},
                        'dtsRos2Level': 0}


def _team_member_default(name):
    if name in TEAM_MEMBER_DEFAULTS:
        return True, TEAM_MEMBER_DEFAULTS[name]
    if name.endswith(('Score', 'Level', 'Lv', 'Count', 'Cnt', 'Num', 'Times', 'ID', 'Id')):
        return True, 0
    if name.startswith(('is', 'has', 'can', 'need', 'enable')):
        return True, False
    if name.endswith(('List', 'Array', 'IDs', 'Ids')):
        return True, []
    if name.endswith(('Data', 'Dict', 'Info', 'Map')):
        return True, {}
    return False, None


class LocalHallTeamMember(dict):
    """Game code treats a hall member as both a mapping and an object, and
    reads fields only the online server filled (creditScore...)."""

    def __missing__(self, name):
        known, value = _team_member_default(str(name))
        if not known:
            raise KeyError(name)
        if isinstance(value, (list, dict)):
            value = copy.deepcopy(value)        # each member its own (TEAM_MEMBER_DEFAULTS is shared)
            self[name] = value      # keep writes the game makes to it
        return value

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value


# Online hall-scene methods the offline scene lacks; STORE / SUPPLY call
# enter/leaveControllerTranslateCamera when they open and close.
HALL_SCENE_NOOP_PREFIXES = ('refresh', 'update', 'sync', 'set', 'on', 'req', 'release', 'destroy',
                            'clear', 'remove', 'reset', 'hide', 'show', 'play', 'stop', 'enter',
                            'leave', 'move', 'change', 'switch', 'load', 'unload', 'add', 'del',
                            'start', 'end', 'begin', 'finish', 'focus', 'rotate', 'zoom', 'init',
                            'tick', 'apply', 'restore', 'recover', 'enable', 'disable', 'toggle',
                            'lock', 'unlock', 'attach', 'detach', 'create', 'bind', 'unbind')
# The online HallScene's own methods run on the offline scene: the camera
# slide of the store / outfit / supply screens, the store previews
# (createOtherDressModel, createItemModel, setModelVisible...).  These stay
# offline-owned: they build or tear down the lobby's own character.
HALL_SCENE_OWN = frozenset(['__init__', 'init', 'release', 'gmReloadConfig',
                            'setDirLightShadowMap', 'enableDirLightShadow', 'enableDOF', 'disableDOF'])
# Only the methods known to work offline (outfit, item and weapon previews,
# camera slide): borrowing all of them crashed the engine itself on the Packs
# tab, which no try/except catches.
HALL_SCENE_BORROWED = frozenset([
    'init_cam_trans', 'translateCameraAndPlayer', '_moveCameraTimerCallback', '_cancelMoveCameraTimer',
    'enterControllerTranslateCamera', 'leaveControllerTranslateCamera',
    'createOtherDressModel', 'onLoadOtherDressModel', 'createItemModel', 'onCreateItemModel',
    'setModelVisible', 'getModelVisible',
    'initDressInfo', 'getPartsStyles', 'filterRos2Props', 'dressRos2EquipPackage', 'getRos2EquipPackageData',
    '_contains_team_info_wear', '_isTeamInfoItem', 'shouldBanPendant', 'updatePendantInfo',
    'onLoadPendantCallBack', 'takeOffAllPendent', 'shouldBanOutGameWeapon', 'bindOutGameWeapon',
    'takeOffOutGameWeapon', 'bindWeapon', 'createOutGameWeaponBag', 'bindWeaponBag',
    'showHallScene', 'showBgEffectOnly',
    # the lobby character itself and its dressing (Depot try-on / wear)
    'createDressModelAsync', 'onLoadDressModel', 'resetCharacterModel', 'loadDoneCallback',
    'applySoftPhysics', 'refreshPlayerDressInfo', 'refreshDressInfo', 'refreshFlyingAccessoryInfo',
    'updateFlyDecatoreEff', 'refreshOutGameWeapon', '_put_on_team_info_wear', 'refreshFlyDecorateInfo',
    'changeOutGameWeaponAnim'])
# HallScene.__init__ fields those methods read
HALL_SCENE_FIELDS = {'selfLoader': None, 'characterType': 0, 'loadDoneFlag': False, 'sfx_mgr': None,
                     'bg_effect': None, 'bg_motor_visible': False, 'curFlyDecorateID': 0,
                     'translateCameraTimer': None, 'cameraTranslateParam': None}
_hall_method_failed = set()


def real_hall_method(name):
    if name in HALL_SCENE_OWN or name not in HALL_SCENE_BORROWED:
        return None
    try:
        hall_class = __import__('helpers.character_scene', fromlist=['HallScene']).HallScene
    except Exception:
        return None
    function = hall_class.__dict__.get(name)
    return function if isinstance(function, types.FunctionType) else None


def hall_sfx_manager(hall):
    """HallScene.__init__ finds the SfxMgr component; the offline scene
    looks it up on first use (it exists once the lobby level is loaded)."""
    if hall.__dict__.get('sfx_mgr') is not None:
        return hall.sfx_mgr
    try:
        scene_module = __import__('helpers.character_scene', fromlist=['GameObject'])
        holder = scene_module.GameObject.Find('SfxMgr')
        hall.sfx_mgr = holder.GetComponent('SfxMgr') if holder else None
    except Exception:
        hall.sfx_mgr = None
    return hall.sfx_mgr


class HallSceneView(object):
    """``self`` for a borrowed HallScene method: everything is the offline
    scene's, except ``scene``, which is the engine scene (models are created
    into it: resObj.create_model(self.scene))."""

    def __init__(self, hall):
        object.__setattr__(self, '_rl_hall', hall)

    def __getattr__(self, name):
        hall = object.__getattribute__(self, '_rl_hall')
        if name == 'scene':
            return hall._native_scene
        return getattr(hall, name)

    def __setattr__(self, name, value):
        setattr(object.__getattribute__(self, '_rl_hall'), name, value)


def borrowed_hall_method(hall, name, function):
    def call(*args, **kwargs):
        try:
            return function(HallSceneView(hall), *args, **kwargs)
        except Exception:
            if name not in _hall_method_failed:
                _hall_method_failed.add(name)
                log_error('local-hall-scene-method-error', method=name)
            return None
    call.__name__ = name
    return call


def lobby_dress_character_type():
    try:
        import BigWorld
        return int(BigWorld.player().getCharacterType() or 0)
    except Exception:
        return 0


class LocalHallScene(object):
    """UIMain calls player.hallScene.scene.createDressModelAsync; the offline
    loader only gives a raw world scene, so wrap it and delegate.

    The online hall scene also owns the dressed preview (``model``, set by
    UIMain._init_self_model) and its async ``loaders``; outfit screens and
    Athlete.onBecomeNonPlayer (game exit) read them before they exist."""
    _rl_hall_scene_wrapper = True       # see native_scene / install_world_scene_unwrap

    def __init__(self, scene):
        self._native_scene = scene
        self.scene = self
        self.model = None
        self.loaders = []          # HallScene.__init__: a list (onLoadDressModel appends)
        self.modelVisible = True
        self._local_noops = {}
        for field, value in HALL_SCENE_FIELDS.items():
            setattr(self, field, value)

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)
        function = real_hall_method(name)
        if function is not None:
            return borrowed_hall_method(self, name, function)
        try:
            return getattr(self._native_scene, name)
        except AttributeError:
            if name.startswith(HALL_SCENE_NOOP_PREFIXES):
                if name not in self._local_noops:
                    def local_noop(*args, **kwargs):
                        debug('local-hall-scene-call', method=name)
                        return None
                    self._local_noops[name] = local_noop
                return self._local_noops[name]
            raise

    def showHallScene(self, show, *args, **kwargs):
        """Supply / store screens hide the lobby behind their showcase."""
        real = real_hall_method('showHallScene')
        result = borrowed_hall_method(self, 'showHallScene', real)(show, *args, **kwargs) if real else None
        try:
            show_lobby_backdrop(show)
        except Exception:
            log_error('local-lobby-backdrop-error')
        return result

    def showBgEffectOnly(self, show):
        """The Firearms supply's backdrop effect (HALL_WEAPON_BG_EFFECT)."""
        hall_sfx_manager(self)
        if show and self.__dict__.get('sfx_mgr') is None:
            return None
        real = real_hall_method('showBgEffectOnly')
        return borrowed_hall_method(self, 'showBgEffectOnly', real)(show) if real else None

    def showBgEffect(self, show, useTurnGray=False):
        """HallScene.showBgEffect: the effect replaces the lobby.  Leaving the
        Firearms supply calls showBgEffect(False) - that brings the lobby
        back, so it cannot be a missing method."""
        self.showBgEffectOnly(show)
        return self.showHallScene(not show)

    def resetCharacterModel(self, characterType=None):
        """UIMain.resetMainModel (gender switch): the current character is
        kept, hidden, for its model path - switching back shows it again at
        once instead of loading it anew (createDressModelAsync)."""
        if real_hall_method('createDressModelAsync') is not None:
            stash_character_model(self)
            if characterType is not None:
                self.characterType = characterType
            return None
        self._rl_dress_generation = self.__dict__.get('_rl_dress_generation', 0) + 1
        retire_hall_model(self, None)
        if characterType is not None:
            self.characterType = characterType

    def createDressModelAsync(self, *args, **kwargs):
        """The lobby character, built by HallScene.onLoadDressModel: its
        AsyncDressLoader (selfLoader) is what the Depot dresses and undresses
        (refreshPlayerDressInfo).  The merged-model loader below is the
        fallback when the game's scene code is missing."""
        real = real_hall_method('createDressModelAsync')
        if real is not None:
            args = list(args)
            model_path = args[0] if args else kwargs.get('modelPath')
            callback = args[2] if len(args) > 2 else kwargs.get('callback')
            generation = self.__dict__.get('_rl_dress_generation', 0) + 1
            self._rl_dress_generation = generation
            if reuse_character_model(self, model_path, callback):
                return None
            waiting = self.__dict__.get('_rl_preloading') or {}
            if model_path in waiting:
                waiting[model_path].append(tag_generation(callback, generation))
                return None
            self._rl_model_path = model_path
            tagged = tag_generation(callback, generation)
            if len(args) > 2:
                args[2] = tagged
            else:
                kwargs['callback'] = tagged
            return borrowed_hall_method(self, 'createDressModelAsync', real)(*args, **kwargs)
        return self.buildMergedModel(*args, **kwargs)

    def onLoadDressModel(self, resObj, dressInfo, callback=None):
        """A load that a newer request (quick gender toggling) superseded
        does not take over the lobby character."""
        generation = getattr(callback, '_rl_generation', None)
        if generation is not None and generation != self.__dict__.get('_rl_dress_generation'):
            debug('local-lobby-dress-model-superseded')
            return None
        real = real_hall_method('onLoadDressModel')
        if real is None:
            return None
        if self.__dict__.get('model') is None:
            # Online HallScene.__init__ knew the character; here only
            # resetCharacterModel sets it, which onLoadDressModel skips for
            # the first model - initDressInfo then failed on type 0 and the
            # login character came up without the saved outfit.
            character_type = lobby_dress_character_type()
            if character_type:
                self.characterType = character_type
        result = borrowed_hall_method(self, 'onLoadDressModel', real)(resObj, dressInfo, callback)
        hide_cached_models(self)
        return result

    def buildMergedModel(self, *args, **kwargs):
        import world
        import ui.UISelectCharacter as select_module
        model_path = None
        completion = kwargs.get('callback')
        for value in args:
            if isinstance(value, string_types) and value.lower().endswith('.gim'):
                model_path = value
            elif callable(value):
                completion = value
        if model_path is None:
            model_path = SHOW_MODEL_PATH
        if not callable(completion):
            raise TypeError('createDressModelAsync callback is missing')
        appearance_paths = (model_path,) + tuple(p for p in show_model_parts(model_path) if p != model_path)
        loaded = {}
        native_scene = self._native_scene
        hall = self
        # A newer request (quick male / female toggling) supersedes this one.
        generation = self.__dict__.get('_rl_dress_generation', 0) + 1
        self._rl_dress_generation = generation
        log('local-lobby-dress-model-request', path=model_path)

        def finish_merged_model():
            preserved_ui = getattr(select_module, '_rl_select_ui', None)
            merge = getattr(select_module, 'mergeModel', None)
            if not callable(merge):
                merge = getattr(preserved_ui, 'mergeModel', None)
            if not callable(merge):
                raise AttributeError('mergeModel is unavailable')
            if preserved_ui is not None:
                preserved_ui.resObj_cache = loaded
            base_model = loaded.get(model_path)
            merged = merge(base_model, [p for p in appearance_paths if p != model_path], False)
            if merged is not None:
                base_model = merged
            if hall.__dict__.get('_rl_dress_generation') != generation:
                destroy_model(base_model)
                debug('local-lobby-dress-model-superseded', path=model_path)
                return
            retire_hall_model(hall, base_model)
            native_scene.add_object(base_model)
            log('local-lobby-dress-model-merged', path=model_path, parts=len(loaded))
            BigWorld.callback(0.0, lambda: completion(base_model))

        def make_loaded(resource_path):
            def on_loaded(model, *loader_args):
                loaded[resource_path] = model
                if len(loaded) == len(appearance_paths):
                    try:
                        finish_merged_model()
                    except Exception:
                        log_error('local-lobby-dress-model-error', path=model_path)
                        raise
            return on_loaded

        return [
            world.create_model_async(path, make_loaded(path), index)
            for index, path in enumerate(appearance_paths)
        ]


SHADOW_HALL_METHODS = frozenset(['createDressModelAsync', 'onLoadDressModel', 'resetCharacterModel',
                                 'loadDoneCallback', 'applySoftPhysics', 'initDressInfo', 'getPartsStyles',
                                 'filterRos2Props', 'dressRos2EquipPackage', 'getRos2EquipPackageData'])
PREBUILD_DELAY = 3.0


class ShadowHall(object):
    """A HallScene of its own for building a character off-screen: the
    game's loader runs on it, its model / loaders stay here."""

    def __init__(self, hall):
        object.__setattr__(self, '_rl_hall', hall)
        object.__setattr__(self, '_rl_own', {'model': None, 'selfLoader': None, 'loaders': [],
                                             'characterType': 0, 'loadDoneFlag': False,
                                             'modelVisible': False})

    def __getattr__(self, name):
        own = object.__getattribute__(self, '_rl_own')
        hall = object.__getattribute__(self, '_rl_hall')
        if name in own:
            return own[name]
        if name == 'scene':
            return hall._native_scene
        if name in SHADOW_HALL_METHODS:
            try:
                hall_class = __import__('helpers.character_scene', fromlist=['HallScene']).HallScene
                method = types.MethodType(hall_class.__dict__[name], self)
            except Exception:
                raise AttributeError(name)
            target = own.get('_rl_target_type')
            if name == 'resetCharacterModel' and target:
                # onLoadDressModel asks the player for the type (the gender on
                # screen); this character is the other one.
                return lambda *args: method(target)
            if name == 'onLoadDressModel' and target:
                # ...and dresses it from the player's lists: wear that gender's
                # outfit for the build.
                player = BigWorld.player()
                outfit = outfit_for_gender(player, character_gender(target))
                return lambda *args: with_outfit(player, outfit, method, *args)
            return method
        return getattr(hall, name)

    def __setattr__(self, name, value):
        object.__getattribute__(self, '_rl_own')[name] = value


CHARACTER_MODEL_ENDINGS = ('male.gim', 'female.gim')
SELECT_SCREEN_SPOT = (0.0, 0.0, 50.0)       # where the character screen stood its model
BACKDROP_PATH_WORDS = ('model\\background', 'model/background')


def scene_models(scene):
    """Every model of an engine scene, read by index (get_models() stops at
    the first destroyed one)."""
    models = []
    try:
        count = scene.get_model_count()
    except Exception:
        return models
    for index in range(count):
        try:
            model = scene.get_model(index)
            models.append((model, str(model.filename).lower()))
        except Exception:
            continue
    return models


def at_spot(model, spot, tolerance=0.5):
    try:
        position = model.position
        return all(abs(a - b) < tolerance for a, b in zip((position.x, position.y, position.z), spot))
    except Exception:
        return False


def is_backdrop_name(name):
    return any(word in name for word in BACKDROP_PATH_WORDS)


def same_model(model, models):
    """``model`` is one of ``models``: identity, as clear_stray_characters
    compares engine models (hall.scn's originals and a theme's copies share
    file name and spot, so nothing else tells them apart)."""
    return any(other is model for other in models)


def hide_native_hall_models(scene):
    """Lobby entry, before UIMain builds HallTheme: hide the login level's own
    backdrop (hall.scn: plane_bg1 / plane_bg2 and the plane_motor vehicle).
    Online SceneSystem.loadHallScene destroys hall.scn (destroyDefaultMap) and
    the theme copies only plane_bg_1/2 from a private load of it; offline the
    login level stays the lobby, so its originals - the vehicle above all -
    stood in the lobby under every theme.  Taken here, before the theme's
    copies load, the snapshot holds hall.scn's models only; the character
    screen (before the lobby) keeps its backdrop."""
    natives = []
    for model, name in scene_models(scene):
        if not is_backdrop_name(name):
            continue
        try:
            model.visible = False
        except Exception:
            continue
        natives.append(model)
    _lobby['native_hall_models'] = natives
    _lobby['retired_hall_models'] = []
    log('local-lobby-native-hall-hidden', count=len(natives))
    return len(natives)


def show_lobby_backdrop(show):
    """HallScene.showHallScene -> HallTheme.onShowScene hides the theme's own
    backdrop; it came back over the supply showcases (Supreme).  It follows
    showHallScene - for the live theme's backdrop only: hall.scn's own models
    (hide_native_hall_models) and a theme switched away from
    (retire_old_theme_models) stay hidden, re-showing them was the old
    theme / vehicle left in the lobby after leaving the Depot."""
    player = BigWorld.player()
    hall = getattr(player, 'hallScene', None)
    if not isinstance(hall, LocalHallScene):
        return 0
    natives = _lobby.get('native_hall_models') or []
    retired = _lobby.get('retired_hall_models') or []
    changed = 0
    live = []
    for model, name in scene_models(hall._native_scene):
        if not is_backdrop_name(name):
            continue
        live.append(model)
        visible = bool(show) and not same_model(model, natives) and not same_model(model, retired)
        try:
            if bool(model.visible) != visible:
                model.visible = visible
                changed += 1
        except Exception:
            continue
    if retired:
        # models a theme switch destroyed are gone from the scene: forget them
        _lobby['retired_hall_models'] = [model for model in retired if same_model(model, live)]
    hidden = not show
    if hidden and not _lobby.get('backdrop_hidden'):
        call_later(BACKDROP_RECHECK, keep_backdrop_hidden)
    _lobby['backdrop_hidden'] = hidden
    return changed


def theme_backdrop_models():
    """The backdrop models in the lobby scene that are not hall.scn's own:
    the live theme's copies (and any not yet destroyed old one)."""
    hall = getattr(BigWorld.player(), 'hallScene', None)
    if not isinstance(hall, LocalHallScene):
        return []
    natives = _lobby.get('native_hall_models') or []
    return [model for model, name in scene_models(hall._native_scene)
            if is_backdrop_name(name) and not same_model(model, natives)]


def retire_old_theme_models(before):
    """After HallTheme._clearOldTheme: a model of the old theme still in the
    scene is a leftover - hidden for good, never re-shown by
    show_lobby_backdrop(True) (leaving the Depot right after a theme
    switch)."""
    natives = _lobby.get('native_hall_models') or []
    leftovers = [model for model in theme_backdrop_models() if same_model(model, before)]
    retired = _lobby.setdefault('retired_hall_models', [])
    for model in leftovers:
        try:
            model.visible = False
        except Exception:
            pass
        if not same_model(model, retired):
            retired.append(model)
    for model in natives:
        try:
            model.visible = False
        except Exception:
            pass
    if leftovers:
        log('local-hall-theme-leftovers-hidden', count=len(leftovers))
    return len(leftovers)


def install_hall_theme_cleanup():
    """A lobby theme switch (Depot, Theme Mall preview) runs
    HallTheme.onThemeChange -> _clearOldTheme + _createNewTheme; the hook
    follows it so nothing of the old theme stays (retire_old_theme_models)
    and a copy that loads while a showcase hides the lobby stays hidden
    until the lobby comes back."""
    try:
        cls = __import__('ui.main.HallTheme', fromlist=['HallTheme']).HallTheme
    except Exception:
        return False
    clear = cls.__dict__.get('_clearOldTheme')
    loaded = cls.__dict__.get('baseModelLoadDoneCallback')
    if clear is None or getattr(clear, '_rl_theme_cleanup', False):
        return False

    def _clearOldTheme(self, *args, **kwargs):
        try:
            before = theme_backdrop_models()
        except Exception:
            before = []
        result = clear(self, *args, **kwargs)
        try:
            retire_old_theme_models(before)
        except Exception:
            log_error('local-hall-theme-cleanup-error', step='clear')
        return result
    _clearOldTheme._rl_theme_cleanup = True
    cls._clearOldTheme = _clearOldTheme

    if loaded is not None:
        def baseModelLoadDoneCallback(self, *args, **kwargs):
            result = loaded(self, *args, **kwargs)
            try:
                # (model, themeData): the new theme's copy.  Should the
                # engine hand the old copy's object out again, it is the
                # live theme's now, not a leftover.
                model = args[0] if args else kwargs.get('model')
                retired = _lobby.get('retired_hall_models') or []
                if model is not None and same_model(model, retired):
                    _lobby['retired_hall_models'] = [other for other in retired if other is not model]
                    model.visible = not _lobby.get('backdrop_hidden')
                for native in _lobby.get('native_hall_models') or []:
                    native.visible = False
                if _lobby.get('backdrop_hidden'):
                    show_lobby_backdrop(False)
            except Exception:
                log_error('local-hall-theme-cleanup-error', step='loaded')
            return result
        baseModelLoadDoneCallback._rl_theme_cleanup = True
        cls.baseModelLoadDoneCallback = baseModelLoadDoneCallback
    return True


BACKDROP_RECHECK = 0.3


def forget_hall_backdrop():
    """Relog / back from a battle: the old lobby scene's models are gone;
    the next lobby entry snapshots the new login level."""
    for key in ('native_hall_models', 'retired_hall_models', 'backdrop_hidden'):
        _lobby.pop(key, None)


def keep_backdrop_hidden():
    """The theme's own backdrop models come back visible a moment after
    onShowScene(False): keep them hidden while a showcase owns the screen."""
    if not _lobby.get('backdrop_hidden'):
        return
    try:
        _lobby['backdrop_hidden'] = False      # show_lobby_backdrop re-arms the check
        show_lobby_backdrop(False)
    except Exception:
        log_error('local-lobby-backdrop-error')


def clear_stray_characters(player=None):
    """Lobby ready: the character screen's model (left at its own spot,
    (0, 0, 50)) still stood in the scene - store / supply showcases that look
    that way showed a second, bare character.  Only the lobby character and
    the kept other-gender one stay."""
    player = player or BigWorld.player()
    hall = getattr(player, 'hallScene', None)
    if not isinstance(hall, LocalHallScene):
        return 0
    keep = [hall.__dict__.get('model')] + [entry[0] for entry in (hall.__dict__.get('_rl_model_cache') or {}).values()]
    stray = []
    for model, name in scene_models(hall._native_scene):
        if 'dataosha' not in name or any(model is kept for kept in keep if kept is not None):
            continue
        # the character screen's base model, and its separate show parts
        if name.endswith(CHARACTER_MODEL_ENDINGS) or at_spot(model, SELECT_SCREEN_SPOT):
            stray.append(model)
    kept = game_preloaded_models()
    for model in stray:
        if any(model is other for other in kept):
            try:
                model.visible = False        # the game destroys it itself (Globals.unloadDefaultScene)
            except Exception:
                pass
        else:
            destroy_model(model)
    if stray:
        log('local-lobby-stray-characters-cleared', count=len(stray))
    return len(stray)


def game_preloaded_models():
    """Models the game keeps in Globals.perloadResource (the character
    screen's): Globals.unloadDefaultScene destroys them when a battle loads
    its map, and one destroyed before raised "invalid space object which
    has been deleted" - the map never loaded."""
    try:
        import Globals
        return [model for model in (getattr(Globals, 'perloadResource', None) or {}).values() if model is not None]
    except Exception:
        return []


def build_character_offscreen(hall, character_type, path, dress, on_built=None):
    """Build a dressed character hidden, into the gender cache (ShadowHall:
    the game's own loader, its model kept apart from the lobby's)."""
    cache = hall.__dict__.setdefault('_rl_model_cache', {})
    if path in cache or hall.__dict__.get('_rl_model_path') == path:
        return False
    shadow = ShadowHall(hall)
    shadow._rl_target_type = character_type
    shadow.characterType = character_type      # initDressInfo reads it (no model to reset yet)

    def built(model, *args):
        own = object.__getattribute__(shadow, '_rl_own')
        try:
            model.visible = False
        except Exception:
            pass
        if path in cache or hall.__dict__.get('_rl_model_path') == path:
            destroy_model(model)       # the player switched first and built it already
        else:
            cache[path] = (model, own.get('selfLoader'), own.get('loaders'), own.get('_rl_target_type'))
            log('local-lobby-prebuilt', path=path)
        if callable(on_built):
            on_built(path)
    try:
        shadow.createDressModelAsync(path, dress, built)
    except Exception:
        log_error('local-lobby-prebuild-error')
        return False
    return True


def prebuild_other_gender(player=None):
    """Lobby ready: build the other gender's character hidden, into the gender
    cache, so even the first Depot male / female switch is instant."""
    player = player or BigWorld.player()
    hall = getattr(player, 'hallScene', None)
    if not isinstance(hall, LocalHallScene) or real_hall_method('createDressModelAsync') is None:
        return False
    try:
        current = player.getCharacterType()
        data = character_data(current)
        other_gender = 2 if int(getattr(data, 'GENDER', 1) or 1) == 1 else 1
        other = character_data(gender_character_type(current, other_gender))
        if other is None or other is data:
            return False
        path, dress = other.dts_show_model_path, other.dtsShowDressInfo
    except Exception:
        log_error('local-lobby-prebuild-error')
        return False
    return build_character_offscreen(hall, gender_character_type(current, other_gender), path, dress)


def preload_lobby_character(player=None):
    """Loading screen: start building your own dressed character while the
    lobby screens load (their loading blocks the game for several seconds;
    the model's files load meanwhile).  The lobby's request for it is then
    answered from the cache, or waits for this build instead of starting a
    second one."""
    player = player or BigWorld.player()
    hall = getattr(player, 'hallScene', None)
    if not isinstance(hall, LocalHallScene) or real_hall_method('createDressModelAsync') is None:
        return False
    try:
        current = player.getCharacterType()
        data = character_data(current)
        path, dress = data.dts_show_model_path, data.dtsShowDressInfo
    except Exception:
        log_error('local-lobby-preload-error')
        return False
    waiting = hall.__dict__.setdefault('_rl_preloading', {})
    if path in waiting:
        return False
    waiting[path] = []

    def done(built_path):
        for callback in waiting.pop(built_path, []):
            reuse_character_model(hall, built_path, callback)
        log('local-lobby-preloaded', path=built_path)
    if not build_character_offscreen(hall, current, path, dress, done):
        waiting.pop(path, None)
        return False
    return True


def tag_generation(callback, generation):
    def tagged(*args, **kwargs):
        if callable(callback):
            return callback(*args, **kwargs)
        return None
    tagged._rl_generation = generation
    return tagged


def stash_character_model(hall):
    """Hide the lobby character and keep it (with its dress loader) under its
    model path: male and female are each loaded once."""
    state = hall.__dict__
    model = state.get('model')
    if model is None:
        return False
    cache = state.setdefault('_rl_model_cache', {})
    path = state.get('_rl_model_path')
    old = cache.get(path)
    if old is not None and old[0] is not model:
        destroy_model(old[0])
    try:
        model.visible = False
    except Exception:
        pass
    cache[path] = (model, state.get('selfLoader'), state.get('loaders'), state.get('characterType'))
    hall.model = None
    hall.selfLoader = None
    hall.loaders = []
    debug('local-lobby-model-stashed', path=safe(path))
    return True


def adopt_loader(hall, loader):
    """A character built off-screen keeps a dress loader that reports to the
    builder (ShadowHall: hidden); handed to the lobby, its dressing must
    report to the lobby's scene, or finishing the dress hid the character
    again (it only came back after a Depot visit)."""
    if loader is None:
        return False
    try:
        loader.isVisible = True
        loader.loadDoneCallback = hall.loadDoneCallback
        loader.dressLoadCallback = hall.applySoftPhysics
        return True
    except Exception:
        log_error('local-lobby-loader-adopt-error')
        return False


def reuse_character_model(hall, model_path, callback):
    """A stashed character for this model path: show it again at once."""
    cache = hall.__dict__.get('_rl_model_cache') or {}
    cached = cache.pop(model_path, None)
    if cached is None or not callable(callback):
        return False
    model, loader, loaders = cached[:3]
    character_type = cached[3] if len(cached) > 3 else None
    adopt_loader(hall, loader)
    hall.model = model
    hall.selfLoader = loader
    hall.loaders = loaders if loaders is not None else []
    if character_type:
        hall.characterType = character_type
    hall._rl_model_path = model_path
    try:
        model.visible = bool(hall.__dict__.get('modelVisible', True))
    except Exception:
        pass
    debug('local-lobby-model-reused', path=safe(model_path))

    def deliver():
        if hall.__dict__.get('model') is not model:
            return            # switched again first: this one is back in the cache, hidden
        callback(model)
        hide_cached_models(hall)
    BigWorld.callback(0.0, deliver)
    return True


def hide_cached_models(hall):
    """Only the lobby character shows; the kept other gender stays hidden
    (quick switching could hand a kept one to the screen after it was put
    back)."""
    current = hall.__dict__.get('model')
    hidden = 0
    for entry in list((hall.__dict__.get('_rl_model_cache') or {}).values()):
        model = entry[0]
        if model is current:
            continue
        try:
            if model.visible:
                model.visible = False
                hidden += 1
        except Exception:
            continue
    return hidden


def destroy_model(model):
    try:
        model.destroy()
    except Exception:
        try:
            model.visible = False
        except Exception:
            pass
        log_error('local-lobby-model-retire-error')


def retire_hall_model(hall, new_model):
    """HallScene.resetCharacterModel: one lobby character at a time - the old
    one (and any other this scene built) goes when its replacement (gender
    switch, outfit) is built."""
    state = hall.__dict__
    built = state.setdefault('_rl_built_models', [])
    old = state.get('model')
    retired = [model for model in built + [old] if model is not None and model is not new_model]
    seen = set()
    for model in retired:
        if id(model) in seen:
            continue
        seen.add(id(model))
        destroy_model(model)
    built[:] = [new_model] if new_model is not None else []
    if old is not None and old is not new_model:
        hall.model = None
    if retired:
        debug('local-lobby-model-retired', count=len(seen))
    return bool(retired)


def _is_hall_scene_wrapper(value):
    """A LocalHallScene of this or of an earlier injection of the hook (the
    class object differs after a re-injection, so match by marker)."""
    try:
        kind = type(value)
        if getattr(kind, '_rl_hall_scene_wrapper', False):
            return True
        # an older hook build's wrapper (no marker yet)
        return kind.__name__ == 'LocalHallScene' and '_native_scene' in value.__dict__
    except Exception:
        return False


def native_scene(value):
    """The engine's world.scene behind a LocalHallScene (or the value itself)."""
    if _is_hall_scene_wrapper(value):
        try:
            return value.__dict__.get('_native_scene')
        except Exception:
            return None
    return value


# UIMonthlySupplyPackage._resumeHallScene (line 134) raised "TypeError: a
# world.scene is required!" - the native type check of world.set_active_scene
# (the only scene setter of the engine's world module; the runtime dump lists
# get_active_scene / set_active_scene / set_scene_delta_time).  Offline,
# player.hallScene.scene is our LocalHallScene (its .scene is itself), so a
# screen resuming the hall passes the wrapper.  Only that case is changed: a
# None argument (a screen whose Awake failed) still reaches the engine
# unchanged - the UI_GUARDED_METHODS guard on _resumeHallScene covers it, and
# the engine may accept None elsewhere.  Only world.set_active_scene is
# wrapped: it is called on scene switches, not per frame.  CONFIG
# "world_scene_unwrap": false turns it off (and removes a wrapper an earlier
# injection installed).
WORLD_SCENE_UNWRAP = CONFIG.get('world_scene_unwrap', True) is not False
WORLD_SCENE_UNWRAP_FUNCTIONS = ('set_active_scene',)
WORLD_SCENE_LOG_LIMIT = 20
_world_unwrap = {'token': object(), 'logged': 0}


def _log_scene_substitution(function_name, reason):
    if _world_unwrap['logged'] < WORLD_SCENE_LOG_LIMIT:
        _world_unwrap['logged'] += 1
        log('local-world-scene-substituted', function=function_name, reason=reason)


def _make_scene_unwrap(function, function_name):
    def unwrapped(*args, **kwargs):
        call_args = args
        try:
            if args:
                first = args[0]
                if _is_hall_scene_wrapper(first):
                    call_args = (native_scene(first),) + tuple(args[1:])
                    _log_scene_substitution(function_name, 'wrapper')
            elif kwargs:
                for key, item in list(kwargs.items()):
                    if _is_hall_scene_wrapper(item):
                        kwargs[key] = native_scene(item)
                        _log_scene_substitution(function_name, 'wrapper')
        except Exception:
            call_args = args            # never let the unwrap itself fail the call
        return function(*call_args, **kwargs)
    unwrapped.__name__ = function_name
    unwrapped._rl_original = function
    unwrapped._rl_token = _world_unwrap['token']
    return unwrapped


def uninstall_world_scene_unwrap():
    """Put the engine functions back (this or an earlier injection's wrapper)."""
    try:
        import world
    except Exception:
        return 0
    return _restore_world_functions(world, None)


def _restore_world_functions(world, keep):
    """Undo hook wrappers on world.*scene* functions except the names in keep
    (an earlier build wrapped every such function)."""
    restored = []
    try:
        names = [name for name in dir(world) if 'scene' in name.lower()]
    except Exception:
        names = list(WORLD_SCENE_UNWRAP_FUNCTIONS)
    for name in names:
        if keep and name in keep:
            continue
        try:
            original = getattr(getattr(world, name, None), '_rl_original', None)
            if original is not None:
                setattr(world, name, original)
                restored.append(name)
        except Exception:
            log_error('local-world-unwrap-error', function=name, step='restore')
    if restored:
        log('local-world-scene-unwrap-removed', functions=restored)
    return len(restored)


def install_world_scene_unwrap():
    """Wrap world.set_active_scene so it gets the engine scene behind a
    LocalHallScene.  Idempotent: a re-injected hook re-wraps the engine's
    original function (never a wrapper)."""
    if not WORLD_SCENE_UNWRAP:
        uninstall_world_scene_unwrap()
        return 0
    try:
        import world
    except Exception:
        log_error('local-world-unwrap-error', step='import')
        return 0
    _restore_world_functions(world, WORLD_SCENE_UNWRAP_FUNCTIONS)
    wrapped = []
    for name in WORLD_SCENE_UNWRAP_FUNCTIONS:
        try:
            current = getattr(world, name, None)
            if current is None:
                continue
            if getattr(current, '_rl_token', None) is _world_unwrap['token']:
                continue                # already ours (this injection)
            original = getattr(current, '_rl_original', None) or current
            if not callable(original):
                continue
            setattr(world, name, _make_scene_unwrap(original, name))
            wrapped.append(name)
        except Exception:
            log_error('local-world-unwrap-error', function=name)
    if wrapped:
        log('local-world-scene-unwrap-installed', functions=wrapped)
    return len(wrapped)


local_player = LocalCharacterPlayer()


# --------------------------------------------------------------------------
# Character screen
# --------------------------------------------------------------------------

def install_character_screen_hooks():
    try:
        import ui.UISelectCharacter as select_module
        select_class = select_module.UISelectCharacter
        if not hasattr(select_module, '_rl_bigworld'):
            select_module._rl_player = local_player
            select_module._rl_create_pending = False
            select_module._rl_real_bigworld = BigWorld
            select_module._rl_bigworld = LocalBigWorldView(BigWorld, local_player)
            # Only this UI module sees the synthetic player. Other game modules
            # keep the real BigWorld and receive the Athlete lobby handoff.
            select_module.BigWorld = select_module._rl_bigworld

        if not hasattr(select_class, '_rl_original_create_success'):
            original_create_success = select_class.onCreateCharacterSuccess
            select_class._rl_original_create_success = original_create_success

            def local_create_success(self, *args, **kwargs):
                try:
                    return original_create_success(self, *args, **kwargs)
                except Exception:
                    log_error('local-character-create-success-error')
                    raise

            select_class.onCreateCharacterSuccess = local_create_success

        if not hasattr(select_class, '_rl_original_update_interval') and \
                callable(getattr(select_class, 'UpdateInterval', None)):
            original_update = select_class.UpdateInterval
            select_class._rl_original_update_interval = original_update

            def local_update_interval(self, *args, **kwargs):
                # The screen's repeat timer keeps animating the creation model
                # after the lobby replaced it ("Invalid model which has been destroyed").
                if _lobby.get('character_screen_closed'):
                    return None
                try:
                    return original_update(self, *args, **kwargs)
                except Exception:
                    if not (_lobby.get('character_created') or _lobby.get('character_screen_closed')):
                        raise
                    debug('local-character-update-skipped', error=traceback.format_exc())
                    return None

            select_class.UpdateInterval = local_update_interval
        log('local-character-hooks-installed')
    except Exception:
        log_error('local-character-hooks-error')


def selected_character_id(ui):
    index = getattr(ui, 'currentCharacterIdx', None)
    if index is None:
        index = getattr(ui, '_currentCharacterIdx', None)
    character_id = getattr(ui, 'character_map', {}).get(index, None)
    return character_id if character_id is not None else DEFAULT_CHARACTER_TYPE


def bind_create_button(Globals):
    try:
        import ui.UISelectCharacter as select_module
        ui = getattr(Globals.uiMgr, 'UISelectCharacter', None)
        if ui is None:
            log('local-create-button-bind-warning', error='UISelectCharacter is missing')
            return
        button_wrapper = getattr(ui, 'BtnEnterGame', None)
        button = getattr(button_wrapper, '____ccwidget__', None) or button_wrapper
        add_listener = getattr(button, 'addTouchEventListener', None)
        if not callable(add_listener):
            log('local-create-button-bind-warning', error='addTouchEventListener is missing')
            return

        def on_touch(*args):
            phase = args[-1] if args else None
            try:
                ended = int(phase) == 2
            except Exception:
                ended = 'ended' in str(getattr(getattr(phase, 'touch', None), 'phase', phase)).lower()
            if not ended or getattr(select_module, '_rl_create_pending', False):
                return
            try:
                input_name = ui.inputName.getString()
                if not input_name or not input_name.strip():
                    log('local-character-name-empty')
                    return
                if hasattr(ui, 'checkInputName') and not ui.checkInputName(input_name):
                    log('local-character-name-rejected', name=safe(input_name))
                    return
                local_player.base.createCharacter(selected_character_id(ui), input_name)
                try:
                    button_wrapper.setEnabled(False)
                except Exception:
                    pass
            except Exception:
                log_error('local-create-button-error')

        ui._rl_create_touch = on_touch
        add_listener(on_touch)
        log('local-create-button-bound')
    except Exception:
        log_error('local-create-button-bind-error')


def enter_character_screen(Globals):
    """New players get the creation screen.  With a character on this server
    the screen is still opened (the lobby hand-off needs it) but stays hidden
    under the loading screen, and the saved character logs in at once."""
    local_player.gid = local_player.id = local_gid()
    saved = saved_character()
    if saved is None:
        end_loading(Globals)
    try:
        Globals.hasLogonServer = True
        install_character_screen_hooks()
        try:
            Globals.uiMgr.destroy_ui_obj('UISelectCharacter')
        except Exception:
            debug('local-character-ui-destroy-warning', error=traceback.format_exc())
        Globals.uiMgr.enter_ui('UISelectCharacter', [])
        bind_create_button(Globals)
        if saved is None:
            log('local-character-ui-entered')
        else:
            ui = getattr(Globals.uiMgr, 'UISelectCharacter', None)
            hidden = hide_select_widgets(ui) if ui is not None else 0
            keep_loading_on_top(Globals)
            log('local-character-ui-skipped', hidden_widgets=hidden)
    except Exception:
        log_error('local-character-ui-error')
        if saved is not None:
            end_loading(Globals)   # never leave a returning player under the loading screen
        return

    if saved is not None:
        name, character_type = saved
        log('local-character-auto-login', name=safe(name), character_id=character_type)
        call_later(0.1, local_player.base.createCharacter, character_type, name)


def keep_loading_on_top(Globals):
    """Re-open the loading screen above the (hidden) character screen."""
    try:
        Globals.uiMgr.enter_ui('UILoading')
        set_loading(Globals, max(_loading['last'] or 0.0, LOGIN_LOADING_SHARE), True)
    except Exception:
        debug('local-loading-reopen-error', error=traceback.format_exc())


def prepare_character_screen(attempt=0):
    try:
        import Globals
        ready = (
            getattr(Globals, 'loginScene', None) is not None and
            getattr(Globals, 'perloadResource', None) is not None and
            bool(getattr(Globals, 'ASYNC_LOAD_MODEL', False))
        )
        if ready and time.time() - (_loading['started'] or time.time()) >= LOADING_MIN_SECONDS:
            log('local-character-resources-ready', attempt=attempt)
            set_loading(Globals, LOGIN_LOADING_SHARE, True)
            call_later(LOADING_FINISH_SECONDS, enter_character_screen, Globals)
            return
        if attempt == 0:
            # the login has just brought the state: a second round trip (0.1-1.5 s
            # online) froze the loading screen
            load_state(refresh=time.time() - _state.get('at', 0) > STATE_FRESH_SECONDS)
            begin_loading(Globals)
            Globals.loadDefaultScene()
            log('local-character-resource-load-started')
        resource_fraction = 0.0
        scene = getattr(Globals, 'loginScene', None)
        if attempt > 1 and scene is not None and hasattr(scene, 'get_progress'):
            try:
                resource_fraction = max(0.0, min(1.0, float(scene.get_progress()) / 100.0))
            except Exception:
                resource_fraction = 0.0
        set_loading(Globals, LOGIN_LOADING_SHARE * animated_loading(Globals, LOADING_ANIMATION_SECONDS,
                                                                    resource_fraction))
        show_loading_text(Globals)
        if attempt >= 6000:
            log('local-character-resource-timeout', attempt=attempt)
            return
        call_later(0.1, prepare_character_screen, attempt + 1)
    except Exception:
        log_error('local-character-resource-error')


def create_local_athlete(input_name, character_id):
    try:
        entity = BigWorld.createEntity(
            'Athlete', 0, 0, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0),
            {
                'gid': local_player.gid,
                'nickname': input_name,
                'baseNickname': input_name,
                'characterType': int(character_id or DEFAULT_CHARACTER_TYPE),
            },
        )
        log('local-athlete-created', entity=safe(entity))
        if entity is not None and hasattr(BigWorld, 'setProxy'):
            try:
                BigWorld.setProxy(entity)
            except Exception:
                BigWorld.setProxy(getattr(entity, 'id', entity))
        return entity
    except Exception:
        log_error('local-athlete-create-error')
        return None


def finish_local_character(input_name, character_id):
    try:
        import Globals
        import ui.UISelectCharacter as select_module
        Globals.playerNickname = input_name
        Globals.hasLogonServer = True
        character_type = int(character_id or DEFAULT_CHARACTER_TYPE)
        ok, reason = save_state(player={'nickname': input_name, 'characterType': character_type,
                                        'created': True})
        if not ok and reason != SERVER_SILENT:
            # The backend refused (name taken, invalid name, not logged in):
            # stay on the creation screen.  Only a silent backend is ignored.
            reopen_character_creation(Globals, reason or 'The character could not be saved.')
            return
        _lobby['character_created'] = True
        local_player.gid = local_player.id = local_gid()
        create_local_athlete(input_name, character_type)
        ui = getattr(Globals.uiMgr, 'UISelectCharacter', None)
        if ui is None:
            log('local-character-create-ui-missing')
            begin_loading(Globals, show=False, keep_progress=True)
            call_later(0.1, start_local_lobby)
            call_later(0.1, poll_lobby_loading, Globals, 0)
            return
        select_module._rl_select_ui = ui
        preload_resources = getattr(Globals, 'perloadResource', {}) or {}
        select_module._rl_preloaded_model = preload_resources.get(SHOW_MODEL_PATH)
        ui.newNickName = input_name
        ui.onCreateCharacterSuccess()
        # keep_progress: with a saved character the bar is already near full.
        begin_loading(Globals, show=False, keep_progress=True)
        call_later(0.1, start_local_lobby)
        call_later(0.1, poll_lobby_loading, Globals, 0)
        log('local-character-create-complete', name=safe(input_name), character_id=character_type)
    except Exception:
        log_error('local-character-create-complete-error')


RETURN_POLL = 0.2
RETURN_TRIES = 150
RETURN_SETTLE_TRIES = 15


def return_to_lobby(attempt=0):
    """After a battle: once the client is back on its login level (the battle
    hook asked ConnectMonitor.backToLogin), log the saved character in again
    under the loading screen - the same path as a fresh start."""
    try:
        import Globals
        login_up = getattr(Globals.uiMgr, 'UILogin', None) is not None
    except Exception:
        login_up = False
    login_up = login_up or bool(_lobby.get('login_seen'))
    hide_login_screens()
    player_gone = BigWorld.player() is None
    settled = login_up or attempt >= RETURN_SETTLE_TRIES
    if not (player_gone and settled) and attempt < RETURN_TRIES:
        call_later(RETURN_POLL, return_to_lobby, attempt + 1)
        return False
    reset_login_flow()
    forget_old_lobby()
    _depot_synced.update(gid=None, player=None)    # the lobby character is built anew: fill its DEPOT again
    clear_rpc_cache(BATTLE_CHANGES, 'battle')     # ranks, gifts, play counts moved in the battle
    _lobby.pop('login_seen', None)
    _lobby['returned'] = True
    _loading['started'] = None
    log('local-lobby-return', attempt=attempt)
    prepare_character_screen(0)
    return True


def follow_lobby_scene(Globals):
    """After a battle Application still hands out the battle map's scene (the
    battle hook gave it that one).  New screens and models go into
    Application.GetScene(): make it the lobby's scene again - nothing until
    the login level has made one, the way it is at game start."""
    try:
        canvas_module = __import__('libclaudia.Settings.CanvasManager', fromlist=['Application'])
        application = canvas_module.Application
    except Exception:
        log_error('local-lobby-scene-follow-error')
        return False
    try:
        application.GetScene = lambda: getattr(Globals, 'loginScene', None)
        _lobby['scene_override'] = ('instance', application)
    except Exception:
        log_error('local-lobby-scene-follow-error')
        return False
    log('local-lobby-scene-following')
    return True


OLD_LOBBY_SCREENS = ('UIMain', 'UISelectCharacter')
OLD_SCENE_FIELDS = ('hallScene', 'loginScene', 'perloadResource')


def forget_old_lobby():
    """The first lobby's scene was destroyed when the battle map loaded:
    drop every reference to it so the lobby is built again from scratch."""
    try:
        import Globals
    except Exception:
        return False
    for name in OLD_LOBBY_SCREENS:
        try:
            Globals.uiMgr.destroy_ui_obj(name)
        except Exception:
            pass
    for name in OLD_SCENE_FIELDS:
        try:
            setattr(Globals, name, None)
        except Exception:
            pass
    _lobby.pop('scene_override', None)
    forget_hall_backdrop()
    follow_lobby_scene(Globals)
    try:
        import ui.UISelectCharacter as select_module
        select_module._rl_preloaded_model = None
        select_module._rl_select_ui = None
    except Exception:
        pass
    _lobby['player'] = None
    log('local-lobby-forgotten')
    return True


LOGIN_SCREENS = ('UILogin', 'UILanguageBtn', 'UIFollowonFacebook', 'UIJumpTip', 'UILoginLoop')


def hide_login_screens():
    """backToLogin puts the login screen up; on the way back from a battle
    only the loading screen is meant to be seen."""
    try:
        import Globals
        ui_mgr = Globals.uiMgr
    except Exception:
        return 0
    hidden = 0
    for name in LOGIN_SCREENS:
        try:
            if getattr(ui_mgr, name, None) is not None:
                ui_mgr.leave_ui(name)
                hidden += 1
        except Exception:
            continue
    return hidden


JUMP_TIP_SCREEN = 'UIJumpTip'


def ensure_jump_tips():
    """UIMgr.systemJumpTip only adds to an open UIJumpTip (the layer of the
    small "Converted repeats into...", "equipped..." tips).  The login flow
    that opens it is skipped or closed with the login screens, so the lobby
    opens it again; it draws nothing until a tip comes."""
    try:
        import Globals
        ui_mgr = Globals.uiMgr
        screen = getattr(ui_mgr, JUMP_TIP_SCREEN, None)
        if screen is None:
            ui_mgr.enter_ui(JUMP_TIP_SCREEN)
            screen = getattr(ui_mgr, JUMP_TIP_SCREEN, None)
        if screen is not None:
            screen.setVisible(True)
        return screen is not None
    except Exception:
        log_error('local-jump-tip-error')
        return False


RETURN_HIDE_SECONDS = 90.0


def returning_from_battle():
    started = _lobby.get('returning')
    return started is not None and time.time() - started < RETURN_HIDE_SECONDS


RETURN_SILENT_CALLS = ('showLogOffUI', 'logoutAudio')


def return_guard(name, original):
    def guarded(self, *args, **kwargs):
        if returning_from_battle():
            _lobby['login_seen'] = True
            log('local-lobby-return-skipped', call=name)
            return None
        return original(self, *args, **kwargs)
    guarded._rl_return_guard = True
    return guarded


def install_return_guards(Globals):
    """ConnectMonitor.backToLogin drops the loading screen, then puts up the
    login screens and the login music.  On the way back from a battle the
    loading screen stays and the lobby follows it directly."""
    try:
        from helpers.ConnectMonitor import ConnectMonitor
    except Exception:
        log_error('local-return-guard-error')
        return False
    for name in RETURN_SILENT_CALLS:
        original = ConnectMonitor.__dict__.get(name)
        if original is not None and not getattr(original, '_rl_return_guard', False):
            setattr(ConnectMonitor, name, return_guard(name, original))
    clear = getattr(Globals, 'clearLoadingState', None)
    if clear is not None and not getattr(clear, '_rl_return_guard', False):
        def clear_loading_state(*args, **kwargs):
            result = clear(*args, **kwargs)
            if returning_from_battle():
                show_return_loading()
            return result
        clear_loading_state._rl_return_guard = True
        Globals.clearLoadingState = clear_loading_state
    return True


def keep_hidden(ui_mgr, name):
    """backToLogin opens the login screens over the loading screen: hide
    them before they are ever drawn (return_to_lobby closes them)."""
    screen = getattr(ui_mgr, name, None)
    try:
        screen.setVisible(False)
        return True
    except Exception:
        pass
    try:
        ui_mgr.leave_ui(name)
        return True
    except Exception:
        return False


EVENT_ADS_SCREEN = 'UIAdvertisementCenter'
EVENT_ADS_DELAY = 1.5
EVENT_ADS_NEXT = 9999
EVENT_ADS_WEB_WAYS = (1, 993, 10000)


def texture_loads(path):
    try:
        import ui.UIAdvertisementCenter as screen_module
        cache = screen_module.cc.Director.getInstance().getTextureCache()
        return bool(path) and bool(cache.addImage(path))
    except Exception:
        return False


def advertisement_rows():
    try:
        import ui.UIAdvertisementCenter as screen_module
        table = screen_module.tables.Advertisement
        return [dict(table[key]) for key in sorted(table.keys())]
    except Exception:
        log_error('local-event-ads-table-error')
        return []


def event_ads(rows, loads=texture_loads):
    """The online server picked the ads of the day from the game's own
    Advertisement table; offline every ad whose picture is installed shows,
    on every lobby entry, and the web links only turn the page."""
    ads, seen = {}, set()
    for row in rows:
        image = row.get('imgPath')
        if image in seen or not loads(image):
            continue
        seen.add(image)
        ad = dict(row)
        ad.update(isCenterShow=True, isPopShow=False, isBattleEndShow=1, isPCShow=True,
                  isBannerShow=bool(row.get('isBannerShow')) and loads(row.get('thumbnail')))
        ad.pop('isShowOncePerDay', None)
        if ad.get('open_way') in EVENT_ADS_WEB_WAYS or ad.get('host'):
            ad['open_way'] = EVENT_ADS_NEXT
        ads[len(ads) + 1] = ad
    return ads


def show_event_ads():
    """The event pages that pop up over the lobby (UIAdvertisementCenter)."""
    try:
        import Globals
        ui_mgr = Globals.uiMgr
    except Exception:
        return False
    player = BigWorld.player()
    if player is None or getattr(ui_mgr, 'UIMain', None) is None:
        return False
    ads = event_ads(advertisement_rows())
    if not ads:
        return False
    try:
        if getattr(ui_mgr, EVENT_ADS_SCREEN, None) is None:
            ui_mgr.enter_ui(EVENT_ADS_SCREEN)
        player.onQueryAvailableAdvertisement(ads)
    except Exception:
        log_error('local-event-ads-error')
        return False
    log('local-event-ads-shown', count=len(ads))
    return True


def ensure_hall_music():
    """Back from a battle: the battle hook puts back the music the lobby was
    playing when START was pressed."""
    module = sys.modules.get('ros_local_battle')
    restore = getattr(module, 'restore_lobby_music', None) if module is not None else None
    if not callable(restore):
        return False
    try:
        return bool(restore())
    except Exception:
        log_error('local-lobby-music-error')
        return False


def show_return_loading():
    try:
        import Globals
        _lobby['returning'] = time.time()
        begin_loading(Globals)
        set_loading(Globals, 0.05, True)
        return True
    except Exception:
        log_error('local-lobby-return-loading-error')
        return False


def reopen_character_creation(Globals, reason):
    import ui.UISelectCharacter as select_module
    select_module._rl_create_pending = False
    ui = getattr(Globals.uiMgr, 'UISelectCharacter', None)
    try:
        ui.BtnEnterGame.setEnabled(True)
    except Exception:
        pass
    show_offline_tip(reason, force=True)
    log('local-character-name-taken', reason=safe(reason))


# --------------------------------------------------------------------------
# Lobby
# --------------------------------------------------------------------------

_lobby = {'player': None, 'entered': False, 'scene_started': False}


LOGIN_LOADING_SHARE = 0.5
LOBBY_LOADING_SECONDS = 18.0
LOBBY_BOUND_FRACTION = 0.8
LOBBY_FINAL_FRACTION = 0.98
LOBBY_EASE_STEP = 0.08
LOADING_FRAMES_LOG_SECONDS = 2.0


def lobby_resource_fraction(Globals):
    best = 0.0
    for name in ('hallScene',):
        scene = getattr(Globals, name, None)
        getter = getattr(scene, 'get_progress', None) if scene is not None else None
        if not callable(getter):
            continue
        try:
            value = float(getter())
        except Exception:
            continue
        if value > 1.0:
            value = value / 100.0
        best = max(best, min(1.0, max(0.0, value)))
    return best


def poll_lobby_loading(Globals, attempt=0):
    if _lobby['entered'] or getattr(Globals, 'hallSceneReady', False):
        set_loading(Globals, 1.0, True)
        log('local-lobby-ready', attempt=attempt)
        if _lobby.pop('returned', False):
            _lobby.pop('returning', None)
            hide_login_screens()
            ensure_hall_music()
        ensure_jump_tips()
        call_later(EVENT_ADS_DELAY, show_login_popups)
        call_later(PREBUILD_DELAY, clear_stray_characters)
        call_later(PREBUILD_DELAY + 0.5, prebuild_other_gender)
        return
    base = LOGIN_LOADING_SHARE + (1.0 - LOGIN_LOADING_SHARE) * animated_loading(
        Globals, LOBBY_LOADING_SECONDS, lobby_resource_fraction(Globals))
    last = _loading['last'] or 0.0
    if last >= LOBBY_BOUND_FRACTION:
        base = max(base, last + (LOBBY_FINAL_FRACTION - last) * LOBBY_EASE_STEP)
    set_loading(Globals, min(base, LOBBY_FINAL_FRACTION))
    show_loading_text(Globals)
    if attempt >= 450:
        log('local-lobby-loading-timeout', hall_scene_ready=safe(getattr(Globals, 'hallSceneReady', None)))
        return
    call_later(0.1, poll_lobby_loading, Globals, attempt + 1)


def apply_local_profile(lobby_player):
    player_state = load_state().get('player', {})
    for name in ('canNotMatchGameTypes', 'weekendPushRewardsHaveGotten', 'dragonDanceItems'):
        if getattr(lobby_player, name, None) is None:
            setattr(lobby_player, name, [])
    for name in ('matchedPlayerSelectionInfo', 'customControlSchemeDicts', 'vidMallSnapshot'):
        if getattr(lobby_player, name, None) is None:
            setattr(lobby_player, name, {})
    fill_none_defaults(lobby_player, 'PlayerAthlete')
    fill_missing_defaults(lobby_player)

    character_type = int(local_player.characterId or DEFAULT_CHARACTER_TYPE)
    lobby_player.gid = local_player.gid
    lobby_player.characterType = character_type
    try:
        lobby_player.dtsCharacterType = character_type
    except Exception:
        pass
    def lobby_character_type():
        # Athlete.getCharacterType is baseCharacterType: the Depot's gender
        # switch changes it (male "G" 10002 <-> female "G" 10005).
        chosen = lobby_player.__dict__.get('baseCharacterType')
        return int(chosen or local_player.characterId or DEFAULT_CHARACTER_TYPE)
    try:
        lobby_player.getCharacterType = lobby_character_type
    except Exception:
        player_class = type(lobby_player)
        if not hasattr(player_class, '_rl_original_get_character_type'):
            original = player_class.getCharacterType
            player_class._rl_original_get_character_type = original

            def local_get_character_type(self):
                if self is lobby_player:
                    return lobby_character_type()
                return original(self)
            player_class.getCharacterType = local_get_character_type

    # Entity defaults are designer/test values until a server snapshot
    # arrives; use a clean local profile so the lobby never shows them.
    profile = {
        'nickname': local_player.nickname,
        'playerName': local_player.nickname,
        'baseNickname': local_player.nickname,
        'baseLevel': player_state.get('baseLevel', 1),
        'level': player_state.get('level', 1),
        'gp': player_state.get('gp', 0),
        'sp': player_state.get('sp', 0),
        'freeYuanbao': player_state.get('freeYuanbao', 0),
        'payYuanbao': player_state.get('payYuanbao', 0),
        'iLuckyCarnivalIsSuper': False,
        'creditScore': getattr(lobby_player, 'creditScore', None) or 100,
        # Personal space (_getPersonInfo) builds your model from these.
        'baseCharacterType': character_type,
        'dtsLevel': player_state.get('level', 1),
        'dtsExp': int(load_state().get('lobby', {}).get('dtsExp', 0) or 0),
        'exp': int(load_state().get('lobby', {}).get('dtsExp', 0) or 0),
        'score': rank_score(),
        'hasDroneRewardToGet': False,
        'isHuiliu': False,
    }
    gender = appearance_gender()
    if gender:
        profile['dtsAppearanceGender'] = gender
        profile['baseCharacterType'] = gender_character_type(character_type, gender)
    theme = hall_theme_id()
    if theme:
        profile['dtsHallThemeID'] = theme
    if not getattr(lobby_player, 'vipInfo', None):
        profile['vipInfo'] = default_vip_info()
    for name, value in profile.items():
        try:
            setattr(lobby_player, name, value)
        except Exception:
            pass
    apply_stored_appearance(lobby_player)
    fill_daily_activity(lobby_player)
    restore_welfare_cache(lobby_player)
    lobby_player.msHttpAP = _mirror_address()
    load_server_props(lobby_player)
    load_server_items(lobby_player)
    start_chat_sync(lobby_player)


def restore_welfare_cache(lobby_player):
    """A new lobby entity starts with the game's defaults (no claimed level
    packs: every pack red-dotted and claimable): the kept copy goes on at
    once, before the props request answers (or if it is lost).  Another
    account's copy is dropped."""
    state = welfare_cache()
    if state is None:
        for key in ('welfare', 'can_sign', 'sign_level', 'sign_days', 'sign_waiting', 'welfare_resync'):
            _lobby.pop(key, None)
        return False
    # without next_day_at/now: the kept deadline (expires) stays as it was
    return apply_welfare_state(lobby_player, dict((key, value) for key, value in state.items()
                                                  if key not in ('next_day_at', 'now')))


ENTRY_RETRIES = 2
ENTRY_RETRY_DELAY = 1.0


def load_server_props(lobby_player, tries=0):
    """Account wallet + local_update/server_data/player_props.json, applied
    when the lobby opens (replicated online properties).  Asked without
    waiting: online the wait (0.2-1.5 s) froze the lobby's loading bar at
    every entry and every return from a battle."""
    if tries and not _entry_player(lobby_player):
        return                  # a retry for an older character: not onto a stale entity
    if RPC_ASYNC:
        send_later('props', _with_session(PROPS_REQUEST + ' '),
                   lambda text: server_props_reply(lobby_player, text, tries))
        return
    try:
        props = from_json_value(json.loads(_udp_exchange(_with_session(PROPS_REQUEST + ' '), 65535)))
    except Exception:
        log_error('local-server-props-error')
        return
    apply_server_props(lobby_player, props, refresh=False)


def server_props_reply(player, text, tries):
    if text is None:
        if tries < ENTRY_RETRIES:
            log('local-server-props-retry', tries=tries + 1)
            call_later(ENTRY_RETRY_DELAY, load_server_props, player, tries + 1)
        else:
            log('local-server-props-error', error='no answer')
        return
    try:
        props = from_json_value(json.loads(text))
    except Exception:
        log_error('local-server-props-error')
        return
    # before the lobby is up nothing shows them yet; after, the wallet is redrawn
    apply_server_props(player, props, refresh=bool(_lobby.get('entered')))


def _show_platoon_dot(player):
    try:
        if getattr(player, 'rmtRosMatchTeamRedDot', False):
            return False
        player.onShowRosMatchTeamRedDot()
        return True
    except Exception:
        log_error('local-platoon-red-dot-error')
        return False


def apply_server_props(player, props, refresh=True):
    """Set replicated props on the player; returns the names that changed."""
    if not props or not isinstance(props, dict):
        return []
    applied, failed = [], []
    for name, value in props.items():
        if name == 'gotLevelAwardList':
            # the claimed level packs live in childClientProperty2 (the game
            # holds that list): never a top-level player attribute
            if set_level_awards(player, value):
                applied.append(name)
            continue
        if name == WELFARE_PROP:
            # the 7-day login state: kept by the hook, set into the game's
            # own properties (lobby entry and every sign-in reply)
            if apply_welfare_state(player, value):
                applied.append(name)
            continue
        if name == DAILY_ACTIVITY_PROP:
            # Activity Pts: lists inside childBaseClientProperty, never a
            # top-level attribute (written in place, see apply_daily_activity)
            if apply_daily_activity(player, value):
                applied.append(name)
            continue
        if name == 'rmtRosMatchTeamRedDot':
            # applies wait for this leader / deputy: the platoon button's dot
            # (onShowRosMatchTeamRedDot sets the prop and draws it)
            if value and _show_platoon_dot(player):
                applied.append(name)
                continue
        if name == 'currencyList':
            value = currency_entries(value)
        elif name == 'vipInfo':
            value = complete_vip_info(value)
        try:
            if getattr(player, str(name), None) != value:
                setattr(player, str(name), value)
                applied.append(name)
        except Exception:
            failed.append(name)
    if applied or failed:
        log('local-server-props-applied', applied=applied[:200], failed=failed[:50])
    if refresh and 'currencyList' in applied:
        refresh_game_currencies(player)
    if refresh and applied:
        refresh_lobby_profile()
    return applied


def fill_daily_activity(player):
    """Benefits > Daily Activity reads one progress / state per activity
    (properties.iterDailyActivityData) and one state per reward milestone;
    empty, the Benefits screen raised IndexError and would not open."""
    try:
        import const
        legacy = __import__('helpers.character_scene', fromlist=['legacyProperties']).legacyProperties
        activities = len(list(legacy.iterDailyActivityData()))
        daily = len(legacy.getActivityRewardData(const.DAILY_ACTIVITY_DATA_ID).reward)
        weekly = len(legacy.getActivityRewardData(const.WEEKLY_ACTIVITY_DATA_ID).reward)
        unmet = int(const.RewardState.UnmetNeeds)
        props = player.childBaseClientProperty
    except Exception:
        log_error('local-daily-activity-error')
        return False
    filled = []
    for key, size, value in (('activityProgress', activities, 0), ('activityState', activities, unmet),
                             ('dailyActivityRewardState', daily, unmet)):
        try:
            entries = props[key]
            while len(entries) < size:
                entries.append(value)
            filled.append(key)
        except Exception:
            log_error('local-daily-activity-fill-error', key=key)
    try:
        weekly_state = player.weeklyActivityRewardState
        while len(weekly_state) < weekly:
            weekly_state.append(unmet)
        filled.append('weeklyActivityRewardState')
    except Exception:
        log_error('local-daily-activity-fill-error', key='weeklyActivityRewardState')
    return filled


VIP_CARD_DEFAULTS = (('level', 0), ('num', 0), ('exp', 0), ('rebateCoupon', {}), ('redPoint', False),
                     ('activeTime', 0))


def complete_vip_info(info):
    """Every key UIVipPrivilege reads on each card ('num' setRightPanel, 'redPoint'
    refreshVipinfo, 'activeTime' refreshTimer - each missing one stopped the
    screen half drawn), whatever backend sent the vipInfo."""
    if not isinstance(info, dict):
        return default_vip_info()
    for card in info.values():
        if isinstance(card, dict):
            for key, value in VIP_CARD_DEFAULTS:
                card.setdefault(key, copy.deepcopy(value))
            card.setdefault('rewardStatus', {})
    return info


def install_vip_sync_guard():
    """iVip.syncVipInfo (after a claim or a top-up): completed the same way."""
    try:
        vip_class = __import__('iVip').iVip
    except Exception:
        return False
    original = vip_class.__dict__.get('syncVipInfo')
    if original is None or getattr(original, '_rl_complete', False):
        return False

    def syncVipInfo(self, vipInfo, *args, **kwargs):
        return original(self, complete_vip_info(vipInfo), *args, **kwargs)
    syncVipInfo._rl_complete = True
    vip_class.syncVipInfo = syncVipInfo
    return True


def default_vip_info():
    """player.vipInfo of a player with no VIP level: {TYPE_SILVER / TYPE_GOLD:
    {'level', 'rewardStatus' per level, 'rebateCoupon'}}.  Empty, the Looks
    Supply payment dialog (UIAdvanceBoxConfirm reads vipInfo[TYPE_GOLD]) and
    the VIP screen raised KeyError and did nothing."""
    try:
        vip = __import__('const').Vip
        types_ = (int(vip.TYPE_SILVER), int(vip.TYPE_GOLD))
        not_yet = int(vip.REWARD_NA)
    except Exception:
        types_, not_yet = (0, 1), 0
    try:
        top = __import__('dts_vip_utils').MAX_VIP_LEVEL
    except Exception:
        top = {}
    info = {}
    for vip_type in types_:
        try:
            levels = int(top[vip_type])
        except Exception:
            levels = 10
        # 'num': the top-up total UIVipPrivilege.setRightPanel draws the bar from
        # (without it the screen raised KeyError 'num'), 'redPoint' (refreshVipinfo,
        # KeyError 'redPoint': a reward waits); the backend's vipInfo
        # (features/vip.py) replaces this at lobby entry
        info[vip_type] = {'level': 0, 'num': 0, 'exp': 0, 'rebateCoupon': {}, 'redPoint': False, 'activeTime': 0,
                          'rewardStatus': dict((level, not_yet) for level in range(1, levels + 1))}
    return info


def install_currency_entries():
    """iCurrency._setCurrencyAmount appends {'id', 'num'} dicts for a
    currency it has not seen (supply tickets...), while _getCurrencyAmount
    reads entries as objects: after one such update every currency read
    raised.  New entries are objects too."""
    try:
        currency_class = __import__('iCurrency').iCurrency
    except Exception:
        log_error('local-currency-entries-error')
        return False
    original = currency_class.__dict__.get('_setCurrencyAmount')
    if original is None or getattr(original, '_rl_entries', False):
        return False

    def _setCurrencyAmount(self, currencyID, num):
        entries = self.currencyList
        for index, entry in enumerate(list(entries)):
            if isinstance(entry, dict) and not isinstance(entry, ItemEntry):
                entries[index] = entry = ItemEntry(entry)
            if entry.id == currencyID:
                entry['num'] = num
                entry.__dict__.pop('num', None)      # an attribute would hide the key
                return
        entries.append(ItemEntry(id=currencyID, num=num))
    _setCurrencyAmount._rl_entries = True
    currency_class._setCurrencyAmount = _setCurrencyAmount
    return True


def currency_entries(value):
    """iCurrency reads currencyList entries as objects (currency.id / .num)."""
    entries = []
    for entry in value if isinstance(value, (list, tuple)) else []:
        try:
            entries.append(ItemEntry(id=int(entry['id']), num=int(entry['num'])))
        except Exception:
            continue
    return entries


def refresh_game_currencies(player):
    changed = getattr(player, 'onCurrencyChangedToUI', None)
    if not callable(changed):
        return
    for entry in list(getattr(player, 'currencyList', None) or []):
        try:
            changed(entry.id)
        except Exception:
            log_error('local-currency-refresh-error', currency=safe(getattr(entry, 'id', None)))


def refresh_lobby_profile():
    """Redraw the top bar (currencies, level) after the server changed them."""
    try:
        import Globals
        main_ui = getattr(Globals.uiMgr, 'UIMain', None)
        refresh = getattr(main_ui, '_init_profile', None)
        if callable(refresh):
            refresh()
    except Exception:
        log_error('local-profile-refresh-error')


def start_local_lobby():
    try:
        import Globals
        lobby_player = BigWorld.player()
        if lobby_player is None or not hasattr(lobby_player, 'onBecomePlayer'):
            log('local-lobby-lifecycle-missing', player=safe(lobby_player))
            return
        _lobby['player'] = lobby_player
        try:
            _cls = type(lobby_player)
            if not getattr(_cls, '_dh_getattr_installed', False):
                def _dh_getattr(self, name):
                    value = battle_player_default(name)
                    if value is _NO_DEFAULT:
                        raise AttributeError(name)
                    try:
                        object.__setattr__(self, name, value)
                    except Exception:
                        pass
                    log('local-player-attribute-defaulted', name=name, kind=type(value).__name__)
                    return value
                _cls.__getattr__ = _dh_getattr
                _cls._dh_getattr_installed = True
                log('local-player-fallback-installed', cls=_cls.__name__)
        except Exception:
            log_error('local-player-fallback-error')
        apply_local_profile(lobby_player)
        try:
            _cls = type(lobby_player)
            if hasattr(_cls, '_initPCAntiCheatSDKParams'):
                _cls._initPCAntiCheatSDKParams = lambda self, *args, **kwargs: None
                log('local-anticheat-init-skipped')
        except Exception:
            log_error('local-anticheat-skip-error')
        lobby_player.onBecomePlayer()
        log('local-lobby-lifecycle-started', is_in_hall=safe(getattr(Globals, 'isInHall', None)))
        # The real server calls enterHall after the account entity becomes the
        # player; do it locally once the loading bar has had time to animate.
        call_later(LOBBY_ENTER_DELAY, finish_local_lobby_entry, Globals, lobby_player)
    except Exception:
        log_error('local-lobby-lifecycle-error')


def bind_lobby_scene(Globals, login_scene):
    # CanvasManager reads Globals.hallScene / Application.GetScene(); the
    # offline loader only populates Globals.loginScene.
    if getattr(Globals, 'hallScene', None) is None:
        Globals.hallScene = login_scene
    try:
        canvas_module = __import__('libclaudia.Settings.CanvasManager', fromlist=['Application'])
        application = canvas_module.Application
        if application.GetScene() is None:
            try:
                application.GetScene = lambda: login_scene
                _lobby['scene_override'] = ('instance', application)
            except Exception:
                _lobby['scene_override'] = ('class', type(application), type(application).__dict__.get('GetScene'))
                type(application).GetScene = lambda self: login_scene
    except Exception:
        log_error('local-lobby-application-scene-error')
    log('local-lobby-scene-bound', scene=safe(login_scene))


def saved_hall_vehicles(lobby_player):
    """The lobby vehicles worn (Depot), from the player or the saved appearance."""
    try:
        vehicles = id_list(player_value(lobby_player, 'dtsHallVehicleAppearanceList'))
    except Exception:
        vehicles = None
    if vehicles:
        return vehicles
    return id_list(stored_appearance().get('dtsHallVehicleAppearanceList')) or []


def sync_local_team(lobby_player):
    """My own one-player team (the lobby's slot shows my character)."""
    lobby_state = load_state().get('lobby', {})
    enter_hall_team(lobby_player, lobby_player.hallTeamType, local_player.gid, lobby_state.get('teamSize', 1),
                    [local_team_member(lobby_player)], lobby_player.hallTeamMapGroup,
                    lobby_state.get('matchingRandom', False), lobby_state.get('matchingRandomSize', 1))


def local_team_member(lobby_player):
    player_state = load_state().get('player', {})
    member = LocalHallTeamMember({
        'gid': local_player.gid,
        'nickname': local_player.nickname,
        'baseNickname': local_player.nickname,
        'characterType': local_player.characterId,
        'baseLevel': player_state.get('baseLevel', 1),
        'level': player_state.get('level', 1),
        'ready': False,
        # the saved theme: iHallTeam's themeScoreData / HallTheme.onFormTeam
        # read the team slot (theme 0 has no theme data)
        'hallThemeID': hall_theme_id(),
        'hallVehicleAppearanceList': saved_hall_vehicles(lobby_player),
        # the nameplate reads the team slot, not the player: the saved badge
        'identifyTagID': saved_identify_tag(lobby_player),
        'dtsNameplateAppearance': 0,
        'intimateRelationship': {},
        'nationality': 0,
        'nationalFlag': '',
        'inWorld': False,
        'supportSeason': 0,
        'rankScore': rank_score(),
        'rankLevel': 0,
        'seasonScore': 0,
        'creditScore': getattr(lobby_player, 'creditScore', None) or 100,
        'dtsAppearanceGender': getattr(lobby_player, 'dtsAppearanceGender', 1),
        'ethnicity': getattr(lobby_player, 'ethnicity', None) or 0,
        'dtsShareAppearanceSuit': getattr(lobby_player, 'dtsShareAppearanceSuit', 0),
        'exoID': getattr(lobby_player, 'exoID', 0),
        'dtsEmojiID': getattr(lobby_player, 'dtsEmojiID', 0),
        'outGameBag': getattr(lobby_player, 'dtsOutGameBag', 0),
        'outGameWeapon': team_weapon(getattr(lobby_player, 'dtsOutGameWeapon', 0),
                                     getattr(lobby_player, 'dtsOutGameWeaponPos', 0)),
    })
    for name in ('dtsShowWearableAppearanceList', 'dtsShowBodyAppearanceList',
                 'dtsShowDyeingAppearanceList', 'dtsShowWeaponAppearanceList',
                 'dtsShowVehicleAppearanceList', 'dtsShowPendantList', 'dtsBodyAppearanceList',
                 'dtsWearableAppearanceList', 'dtsFlyingAccessoryList',
                 'dtsBattlegroundPropAppearanceList', 'dtsPendantAppearanceList'):
        member[name] = list(getattr(lobby_player, name, None) or [])
    return member


def enter_hall_team(lobby_player, team_type, leader, size, members, map_group, matching_random,
                    matching_random_size):
    if team_call(lobby_player, 'onEnterHallTeam', team_type, leader, size, members, map_group,
                 matching_random, matching_random_size):
        log('local-lobby-team-synced', member_count=safe(lobby_player.getHallTeamMemberCnt()))


def _safe_theme_score(original):
    """The theme's real score (the team theme goes to the best one,
    UITeamThemeChoose); 0 for a theme the game has no data for (theme 0)."""
    def getHallThemeScore(*args, **kwargs):
        try:
            return original(*args, **kwargs) or 0
        except Exception:
            return 0
    return getHallThemeScore


def team_call(lobby_player, method, *args):
    """An iHallTeam method with the theme score switched off: entering and
    joining score each member's lobby theme (dts_hall_prop_utils.
    getHallThemeScore), which fails for a theme without data (0)."""
    score_utils = None
    original_score = None
    try:
        function = getattr(lobby_player, method)
        team_function = getattr(function, 'im_func', function)
        score_utils = getattr(team_function, 'func_globals', {}).get('dts_hall_prop_utils')
        if score_utils is not None:
            original_score = getattr(score_utils, 'getHallThemeScore', None)
            if callable(original_score):
                score_utils.getHallThemeScore = _safe_theme_score(original_score)
        try:
            function(*args)
        except TypeError as _te:
            if 'bool' in str(_te):
                return True
            raise
        return True
    except Exception as _e:
        if 'bool' not in str(_e):
            log_error('local-lobby-team-sync-error', method=method)
        return False
    finally:
        if score_utils is not None and original_score is not None:
            score_utils.getHallThemeScore = original_score


def bind_character_data(lobby_player):
    """Return (original, local) getCharactersData so UIMain aliases can be patched."""
    properties = __import__('shared.lib.gametoolslib.properties', fromlist=['getCharactersData'])
    original = getattr(properties, '_rl_original_get_characters_data', properties.getCharactersData)
    if not hasattr(properties, '_rl_original_get_characters_data'):
        properties._rl_original_get_characters_data = original

        class LocalCharacterData(object):
            dts_show_model_path = SHOW_MODEL_PATH

        local_data = LocalCharacterData()

        def local_get_characters_data(character_type):
            native = original(character_type)
            if native is not None:
                return native
            try:
                if int(character_type) == int(local_player.characterId):
                    return local_data
            except Exception:
                pass
            return None

        properties.getCharactersData = local_get_characters_data
    data = properties.getCharactersData(lobby_player.getCharacterType())
    log('local-lobby-character-data-ready', model_path=safe(getattr(data, 'dts_show_model_path', None)))
    return original, properties.getCharactersData


def patch_main_ui_class(original_get_data, local_get_data):
    main_module = __import__('ui.UIMain', fromlist=['UIMain'])
    if local_get_data is not None:
        for alias_name, alias_value in list(main_module.__dict__.items()):
            if alias_name == 'getCharactersData' or alias_value is original_get_data:
                main_module.__dict__[alias_name] = local_get_data
    main_class = main_module.UIMain

    if not hasattr(main_class, '_rl_original_init_self_model'):
        original_init_self_model = main_class._init_self_model
        main_class._rl_original_init_self_model = original_init_self_model

        def local_init_self_model(self, model):
            result = original_init_self_model(self, model)
            try:
                if appearance_screen_open():
                    # DEPOT / outfits frame the model themselves at full size.
                    restore_model_size(model)
                else:
                    place_lobby_model(model)
            except Exception:
                log_error('local-lobby-model-place-error')
            hall_scene = getattr(BigWorld.player(), 'hallScene', None)
            if isinstance(hall_scene, LocalHallScene):
                # DtsAppearance (DEPOT / outfits) dresses player.hallScene.model
                hall_scene.model = model
            hide_character_screen()
            for name, value in (('visible', True), ('cast_shadow', True), ('receive_shadow', True)):
                try:
                    setattr(model, name, value)
                except Exception:
                    pass
            try:
                self.modelVisible = True
            except Exception:
                pass
            log('local-lobby-self-model-ready', models=safe(getattr(self, 'models', None), 1000))
            return result

        main_class._init_self_model = local_init_self_model

    if not hasattr(main_class, '_rl_original_on_enter'):
        original_on_enter = main_class.on_enter
        main_class._rl_original_on_enter = original_on_enter

        def local_on_enter(self, *args, **kwargs):
            result = None
            try:
                result = original_on_enter(self, *args, **kwargs)
            except Exception:
                log_error('local-lobby-main-optional-error')
            for core_name in ('_init_profile', '_init_ui_widgets', '_refresh_members'):
                core = getattr(self, core_name, None)
                if callable(core):
                    try:
                        core()
                    except Exception:
                        log_error('local-lobby-main-core-error', method=core_name)
            return result

        main_class.on_enter = local_on_enter

    # Only methods known to crash on missing online data. Wrapping every
    # method breaks libclaudia SendMessage dispatch (move_invitation_remind).
    guard_class_methods(main_class, only=UIMAIN_GUARDED_METHODS)
    install_ui_guards()
    return main_class


def lobby_model_settings():
    settings = dict(LOBBY_MODEL_DEFAULTS)
    stored = load_state().get('lobbyModel')
    if isinstance(stored, dict):
        settings.update(stored)
    return settings


def _vector_xyz(value):
    return float(value.x), float(value.y), float(value.z)


_model_spots = {}   # id(model) -> (original position, position we placed it at)


def _same_spot(first, second):
    return first is not None and second is not None and \
        all(abs(a - b) < 0.01 for a, b in zip(first, second))


def game_staged_spot(position):
    """True when the model is not at the bare spawn spot (0, 0, 0) of the
    local hall scene, i.e. the game placed it on its lobby stage itself."""
    try:
        return max(abs(float(value)) for value in position) > 0.5
    except Exception:
        return False


APPEARANCE_SCREENS = ('UIDtsAppearanceMainController', 'UIDtsAppearanceCostume',
                      'UIDtsAppearanceMall', 'UIPersonalSpace')


def appearance_screen_open():
    try:
        import Globals
        ui_mgr = Globals.uiMgr
    except Exception:
        return False
    for name in APPEARANCE_SCREENS:
        ui = getattr(ui_mgr, name, None)
        if ui is not None and getattr(ui, 'is_enter', False):
            return True
    return False


def restore_model_size(model=None):
    """Undo the lobby preview scale (the lobby re-applies it on return)."""
    if model is None:
        hall_scene = getattr(_lobby.get('player'), 'hallScene', None)
        model = getattr(hall_scene, 'model', None)
    if model is None:
        return
    stage = game_stage()
    if stage is not None:
        stage_lobby_model(model, stage)
        return
    try:
        import math3d
        model.scale = math3d.vector(1.0, 1.0, 1.0)
        debug('local-lobby-model-full-size')
    except Exception:
        log_error('local-lobby-model-restore-error')


def game_stage():
    """The online HallScene's stage (legacyProperties.getSelectcharacterData(1)):
    the camera spot, and the character's spot, scale and facing."""
    try:
        scene_module = __import__('helpers.character_scene', fromlist=['legacyProperties'])
        data = scene_module.legacyProperties.getSelectcharacterData(1)
        return {'camera': tuple(data.CAMERA_POS), 'model': tuple(data.CHARACTER_POS),
                'scale': tuple(data.CHARACTER_SCALE), 'euler': tuple(data.DEFAULT_EULER)}
    except Exception:
        return None


def hall_camera_phase():
    hall_scene = getattr(BigWorld.player(), 'hallScene', None)
    state = getattr(hall_scene, '__dict__', {})
    return state.get('cameraPhaseTarget', 0) or 0


def stage_lobby_model(model, stage):
    """Put the character where HallScene.onLoadDressModel does, and the camera
    on its lobby spot unless a store / outfit screen has slid it aside."""
    import math3d
    import Globals
    try:
        model.position = math3d.vector(*stage['model'])
        model.scale = math3d.vector(*stage['scale'])
        model.rotation_matrix = math3d.euler_to_matrix(math3d.vector(*stage['euler']))
    except Exception:
        log_error('local-lobby-model-stage-error')
        return False
    if not hall_camera_phase():
        scene = getattr(Globals, 'hallScene', None) or getattr(Globals, 'loginScene', None)
        camera = getattr(scene, 'active_camera', None)
        try:
            camera.position = math3d.vector(*stage['camera'])
        except Exception:
            log_error('local-lobby-camera-stage-error')
    debug('local-lobby-model-staged', **stage)
    return True


def place_lobby_model(model):
    """Scale the preview model and move it back from the camera along the
    ground so it sits like the online lobby preview.

    UIMain re-runs _init_self_model every time the lobby comes back to the
    front, on the same model.  The move is always computed from the model's
    original spot; computing it from the current spot pushed the model
    further away each time until it left the screen."""
    import math3d
    import Globals
    stage = game_stage()
    if stage is not None:
        stage_lobby_model(model, stage)
        return
    settings = lobby_model_settings()

    def number(key):
        # local_lobby_state.json is edited by hand: fall back on bad values.
        try:
            return float(settings.get(key))
        except (TypeError, ValueError):
            return float(LOBBY_MODEL_DEFAULTS[key])
    scale = number('scale') or 1.0
    distance = number('distance') or 1.0
    offset_x = number('offsetX')
    placement = {'scale': scale, 'distance': distance, 'offsetX': offset_x}
    try:
        model_position = _vector_xyz(model.position)
        original, placed = _model_spots.get(id(model), (None, None))
        origin = model_position if original is None or not _same_spot(model_position, placed) \
            else original
        if game_staged_spot(origin):
            # The game put the model on its own lobby stage (after DEPOT /
            # outfits / store screens load the real hall scene).  It is framed
            # for full size there; shrinking and pushing it back made the
            # character half-size after pressing Back.
            scale, distance, offset_x = 1.0, 1.0, 0.0
            placement.update(scale=scale, distance=distance, offsetX=offset_x, staged=True)
    except Exception:
        log_error('local-lobby-model-stage-check-error')
    try:
        model.scale = math3d.vector(scale, scale, scale)
    except Exception:
        log_error('local-lobby-model-scale-error')
    try:
        scene = getattr(Globals, 'hallScene', None) or getattr(Globals, 'loginScene', None)
        camera = getattr(scene, 'active_camera', None)
        camera_position = None
        for name in ('world_position', 'position'):
            try:
                camera_position = _vector_xyz(getattr(camera, name))
                break
            except Exception:
                pass
        model_position = _vector_xyz(model.position)
        placement['camera'] = camera_position
        placement['model_before'] = model_position
        original, placed = _model_spots.get(id(model), (None, None))
        if original is None or not _same_spot(model_position, placed):
            # First placement, or the game moved the model itself: new origin.
            original = model_position
        placement['origin'] = original
        # Until moved below, the model stays where it is now.
        _model_spots[id(model)] = (original, model_position)
        if placement.get('staged') and not _same_spot(model_position, original):
            # Back onto the game's own spot (undo an earlier lobby move).
            model.position = math3d.vector(*original)
            _model_spots[id(model)] = (original, original)
            placement['model_after'] = original
        elif camera_position is not None and (distance != 1.0 or offset_x):
            cx, cy, cz = camera_position
            mx, my, mz = original
            # Keep the model's height (on the ground); only move it away
            # from the camera horizontally, then sideways.
            new_position = (cx + (mx - cx) * distance + offset_x, my, cz + (mz - cz) * distance)
            model.position = math3d.vector(*new_position)
            _model_spots[id(model)] = (original, new_position)
            placement['model_after'] = new_position
    except Exception:
        log_error('local-lobby-model-place-error')
    if placement.get('model_before') != placement.get('model_after'):
        log('local-lobby-model-placed', **placement)
    else:
        debug('local-lobby-model-placed', **placement)


def _cc_widget(value):
    return getattr(value, '____ccwidget__', None) or value


def hide_character_screen():
    """With a saved character the creation screen is only open for a moment.
    leave_ui does not hide it here, so hide its widgets directly and then
    destroy the screen so the name box / Enter button never cover the lobby."""
    if _lobby.get('character_screen_closed'):
        return False
    try:
        import Globals
        ui_mgr = Globals.uiMgr
        ui = getattr(ui_mgr, 'UISelectCharacter', None)
        hidden = hide_select_widgets(ui) if ui is not None else 0
        stop_character_screen_timer(ui)
        _lobby['character_screen_closed'] = True
        for step in ('leave_ui', 'destroy_ui_obj'):
            try:
                getattr(ui_mgr, step)('UISelectCharacter')
            except Exception:
                debug('local-character-screen-%s-error' % step, error=traceback.format_exc())
        log('local-character-screen-closed', hidden_widgets=hidden)
        return True
    except Exception:
        log_error('local-character-screen-close-error')
        return False


def hide_select_widgets(ui):
    """Hide the creation screen's widgets (name box, Enter button, panels)."""
    hidden = 0
    targets = [getattr(ui, 'inputName', None), getattr(ui, 'BtnEnterGame', None)]
    # Widget panels owned by the screen (name bar background, buttons).
    for value in getattr(ui, '__dict__', {}).values():
        if hasattr(_cc_widget(value), 'setVisible'):
            targets.append(value)
    seen = set()
    for target in targets:
        widget = _cc_widget(target)
        if widget is None or id(widget) in seen:
            continue
        seen.add(id(widget))
        try:
            widget.setVisible(False)
            hidden += 1
        except Exception:
            pass
        # The input field's own panel holds the "Tap to Enter NAME" bar.
        try:
            parent = widget.getParent()
            if parent is not None and id(parent) not in seen and target in (
                getattr(ui, 'inputName', None), getattr(ui, 'BtnEnterGame', None)
            ):
                seen.add(id(parent))
                parent.setVisible(False)
                hidden += 1
        except Exception:
            pass
    return hidden


def stop_character_screen_timer(ui):
    """UISelectCharacter.on_enter starts a repeat timer (self._timer)."""
    timer = getattr(ui, '_timer', None) if ui is not None else None
    if timer is None:
        return
    try:
        import ui.UISelectCharacter as select_module
        timers = getattr(select_module, 'Timer', None)
        remove = getattr(timers, 'delTimer', None)
        if callable(remove):
            remove(timer)
            ui._timer = None
            debug('local-character-timer-stopped')
    except Exception:
        debug('local-character-timer-stop-error', error=traceback.format_exc())


def ensure_self_model(main_ui):
    if getattr(main_ui, 'models', None) or getattr(main_ui, 'mainModelCreating', False):
        return
    import Globals
    import ui.UISelectCharacter as select_module
    model = getattr(select_module, '_rl_preloaded_model', None)
    if model is None:
        model = (getattr(Globals, 'perloadResource', {}) or {}).get(SHOW_MODEL_PATH)
    if model is None:
        log('local-lobby-preloaded-model-missing')
        return
    main_ui._init_self_model(model)
    log('local-lobby-preserved-model-used')


def hide_empty_team_slots(main_ui):
    hidden = [0]
    visited = set()

    def hide(value, depth=0):
        if value is None or depth > 4 or id(value) in visited:
            return
        visited.add(id(value))
        if isinstance(value, dict):
            for child in value.values():
                hide(child, depth + 1)
            return
        if isinstance(value, (list, tuple, set)):
            for child in value:
                hide(child, depth + 1)
            return
        set_visible = getattr(value, 'setVisible', None)
        if callable(set_visible):
            try:
                set_visible(False)
                hidden[0] += 1
            except Exception:
                pass
        for child_name in ('widget', 'panel', 'gameObject', 'root', 'node'):
            try:
                hide(getattr(value, child_name), depth + 1)
            except Exception:
                pass

    for slot_name in ('team', 'newMember', 'memberInTimeLine'):
        hide(getattr(main_ui, slot_name, None))
    log('local-lobby-team-slots-hidden', count=hidden[0])


def finish_local_lobby_entry(Globals, lobby_player, scene_attempt=0):
    if _lobby['entered']:
        return
    if lobby_player is None or not hasattr(lobby_player, 'enterHall'):
        log('local-lobby-enter-missing', player=safe(lobby_player))
        return
    login_scene = getattr(Globals, 'loginScene', None)
    active_camera = getattr(login_scene, 'active_camera', None) if login_scene is not None else None
    if active_camera is None and scene_attempt < 100:
        if not _lobby['scene_started']:
            _lobby['scene_started'] = True
            Globals.loadDefaultScene()
            log('local-lobby-scene-started')
        call_later(0.1, finish_local_lobby_entry, Globals, lobby_player, scene_attempt + 1)
        return

    try:
        bind_lobby_scene(Globals, login_scene)
        try:
            hide_native_hall_models(login_scene)     # before UIMain: its HallTheme copies load after
        except Exception:
            log_error('local-hall-theme-cleanup-error', step='native')
        # firstLoginToday=True opens every promotional panel, which needs an
        # online account snapshot; keep the lobby in its already-seen state.
        Globals.skipHallPopupUI = 1
        Globals.popupUIMaxNum = 0
        Globals.isFirstTimeEnterHall = False
        capture_game_errors()
        unlock_frame_rate()
        guard_settings_files()
        install_ui_manager_hooks(Globals)
        install_return_guards(Globals)
        install_service_clock()
        install_monthly_offer_countdown(lobby_player)   # before UIMain._get_ui
        wear_saved_identify_tag(lobby_player)           # before UIMain shows your name
        install_vip_sync_guard()
        install_meet_edit_fix()
        install_item_display_counts()
        install_meet_info()
        install_currency_entries()
        install_pay_gate()
        install_sign_in_day()
        install_daily_activity_reset()
        install_activity_badge()
        install_rank_requests()
        install_hall_theme_cleanup()
        try:
            close_horse_racing()      # before UIMain is built: _get_ui / on_enter read the switch
        except Exception:
            log_error('local-horse-racing-close-error')
        set_loading(Globals, LOBBY_BOUND_FRACTION, True)
        sync_local_team(lobby_player)

        # onBecomePlayer already marks the local entity as in-hall; calling
        # enterHall again destroys the camera scene (black background).
        if not getattr(Globals, 'isInHall', False):
            lobby_player.enterHall(False)
        set_hall_scene_ready(Globals)

        player_scene = getattr(lobby_player, 'hallScene', None)
        if player_scene is None or getattr(player_scene, 'scene', None) is None:
            lobby_player.hallScene = LocalHallScene(login_scene)
        try:
            install_world_scene_unwrap()
        except Exception:
            log_error('local-world-unwrap-error', step='install')

        original_get_data, local_get_data = None, None
        try:
            original_get_data, local_get_data = bind_character_data(lobby_player)
        except Exception:
            log_error('local-lobby-character-data-error')
        try:
            patch_main_ui_class(original_get_data, local_get_data)
        except Exception:
            log_error('local-lobby-main-wrapper-error')
        install_local_mailboxes(lobby_player)
        try:
            preload_lobby_character(lobby_player)
        except Exception:
            log_error('local-lobby-preload-error')
        try:
            Globals.uiMgr.enter_ui('UIMain')
        except Exception:
            log_error('local-lobby-main-enter-error')

        main_ui = getattr(Globals.uiMgr, 'UIMain', None)
        if main_ui is not None:
            refresh = getattr(main_ui, 'onFormTeam', None)
            if callable(refresh):
                try:
                    refresh(False)
                except Exception:
                    log_error('local-lobby-main-refresh-error', method='onFormTeam')
            solo_menu(main_ui)
            try:
                ensure_self_model(main_ui)
            except Exception:
                log_error('local-lobby-preloaded-model-error')
            # The team slots also hold your own nameplate + rank badge under
            # the character, so they stay visible unless hideTeamSlots is set.
            if lobby_model_settings().get('hideTeamSlots'):
                hide_empty_team_slots(main_ui)

        end_loading(Globals)
        _lobby['entered'] = True
        set_hall_scene_ready(Globals)
        _lobby_ready['value'] = True
        _lobby_ready['at'] = time.time()
        start_lobby_perf(lobby_player)
        log('local-lobby-entered', nickname=safe(local_player.nickname),
            is_in_hall=safe(getattr(Globals, 'isInHall', None)))
        keep_lobby_cursor()
        clean_lobby_ui()
        call_later(1.0, _find_tip_function)
        call_later(2.0, build_lobby_catalog)
        call_later(3.0, dump_screen_code, 'lobby')
        call_later(CLIENT_TABLES_DELAY, start_client_table_export)
        if AUTO_START and not _auto_start['pressed']:
            call_later(AUTO_START_DELAY, press_start)
    except Exception:
        log_error('local-lobby-enter-error')


_auto_start = {'pressed': False}


def press_start():
    """--auto-start: press START once, the way the button does.

    UIModes._doGoMatch is what the button runs (maintenance check first, then
    doGoEvent -> getReadyForBattleGround); doGoEvent is the fallback.  Only
    once per session - while matching, START is CANCEL."""
    if _auto_start['pressed']:
        return
    try:
        import Globals
        modes = getattr(getattr(Globals.uiMgr, 'UIMain', None), 'uiModes', None)
    except Exception:
        modes = None
    for name in ('_doGoMatch', 'doGoEvent'):
        function = getattr(modes, name, None) if modes is not None else None
        if not callable(function):
            continue
        _auto_start['pressed'] = True
        try:
            function()
            log('local-auto-start', via=name)
        except Exception:
            log_error('local-auto-start-error', via=name)
        return
    log('local-auto-start-missing', modes=safe(modes, 80))


def set_hall_scene_ready(Globals):
    # The online server advances this flag during the enterHall handoff.
    if hasattr(Globals, 'setHallSceneReady'):
        Globals.setHallSceneReady(True)
    else:
        Globals.hallSceneReady = True


# --------------------------------------------------------------------------
# Lobby polish: cursor + leftover online widgets
# --------------------------------------------------------------------------

def guard_input_messages():
    """The lobby keeps the game-look input component inactive so the OS
    cursor stays free; screens such as the Esc dialog then send it
    IptMsg_ShowSysMouse and abort with "message is not picked up by any
    component".  Drop only those undelivered IptMsg_* messages."""
    try:
        module = __import__('libclaudia.Classes.GameObject', fromlist=['GameObject'])
        game_object = module.GameObject
    except Exception:
        log_error('local-input-guard-error')
        return
    try:
        _install_input_guard(game_object)
    except Exception:
        log_error('local-input-guard-error')


def _install_input_guard(game_object):
    if game_object.__dict__.get('_rl_input_guarded'):
        return
    original = game_object.SendMessage

    def local_send_message(self, method_name, *args, **kwargs):
        try:
            return original(self, method_name, *args, **kwargs)
        except Exception as error:
            if 'not picked up' not in str(error):
                raise
            # IptMsg_* always: the Esc dialog sends them to the inactive input
            # component.  Anything else only while the battleground is being
            # entered, where one undelivered message (breakFire) would
            # otherwise abort the whole map load.
            input_message = isinstance(method_name, string_types) and \
                method_name.startswith('IptMsg_')
            if input_message or battle_running():
                if method_name not in _missing_reported:
                    _missing_reported.add(method_name)
                    log('local-input-message-dropped', message=safe(method_name),
                        battle=not input_message)
                return None
            raise

    local_send_message.__name__ = getattr(original, '__name__', 'SendMessage')
    local_send_message._rl_original = original
    game_object.SendMessage = local_send_message
    game_object._rl_input_guarded = True
    log('local-input-guard-installed')


_game_input = {'released': False}


def set_game_input(active):
    """Hand the game-look input component to the game, or take it away again.

    The lobby keeps it inactive so the OS pointer stays free (active game look
    captures and recenters it).  A battleground needs it back: it is how you
    play, and the scene loader sends it messages on the way in
    (``SceneSystem.beforeLoadMap`` -> ``breakFire``), which fail while the
    component is inactive and abort the map load."""
    active = bool(active)
    _game_input['released'] = active
    try:
        import Globals
        import game3d
        user_input = getattr(Globals, 'userInput', None)
        if user_input is not None and hasattr(user_input, 'SetActive'):
            user_input.SetActive(active)
        for name in ('set_sys_cursor', 'show_sys_mouse'):
            function = getattr(game3d, name, None)
            if callable(function):
                try:
                    function(not active)
                except Exception:
                    pass
        log('local-game-input', active=active)
        return True
    except Exception:
        log_error('local-game-input-error', active=active)
        return False


def keep_lobby_cursor(attempt=0):
    if attempt == 0:
        guard_input_messages()
    if _game_input['released']:
        # The battleground has the input now; leave it alone.
        return
    try:
        import Globals
        import game3d
        user_input = getattr(Globals, 'userInput', None)
        if user_input is not None and hasattr(user_input, 'SetActive'):
            # Active game-look input captures and recenters the OS pointer.
            user_input.SetActive(False)
        for name in ('set_sys_cursor', 'show_sys_mouse'):
            function = getattr(game3d, name, None)
            if callable(function):
                try:
                    function(True)
                except Exception:
                    pass
    except Exception:
        if attempt == 0:
            log_error('local-lobby-cursor-error')
    if attempt < 20:
        call_later(0.5, keep_lobby_cursor, attempt + 1)


NAME_NODE_MARKERS = ('nickname', 'playername', 'player_name', 'rolename', 'role_name',
                     'username', 'user_name', 'name_txt', 'name_text', 'txt_name', 'label_name')
TEAM_NODE_MARKERS = ('teammember', 'team_member', 'memberitem', 'member_item')
# 283283 is the Cocos designer placeholder shown when no currency update arrives.
PLACEHOLDER_TEXT = ('283283', '888888')


def _node_text(node):
    for getter_name in ('getString', 'getText', 'getStringValue'):
        getter = getattr(node, getter_name, None)
        if callable(getter):
            try:
                text = getter()
                if text:
                    return text
            except Exception:
                pass
    return ''


def _node_setter(node):
    for setter_name in ('setString', 'setText', 'setStringValue'):
        setter = getattr(node, setter_name, None)
        if callable(setter):
            return setter
    return None


def _hide_ancestor(node, levels):
    target = node
    for _index in range(levels):
        try:
            parent = target.getParent()
        except Exception:
            parent = None
        if parent is None:
            break
        target = parent
    try:
        target.setVisible(False)
        return True
    except Exception:
        return False


def _lobby_root_nodes(Globals):
    roots = []
    try:
        import cc
        scene = cc.Director.getInstance().getRunningScene()
        if scene is not None:
            roots.append(scene)
    except Exception:
        pass
    try:
        for ui_object in getattr(Globals.uiMgr, '____all_ui__', {}).values():
            for value in getattr(ui_object, '__dict__', {}).values():
                if hasattr(value, 'getChildren'):
                    roots.append(value)
    except Exception:
        pass
    return roots


def clean_lobby_ui(attempt=0):
    changed = hidden = 0
    seen = set()
    if attempt == 0:
        _lobby.pop('clean_changed_at', None)      # a new lobby: an older one's changes do not count
    try:
        import Globals
        hide_ranked = bool(lobby_model_settings().get('hideRanked'))
        if attempt >= 2:
            hide_character_screen()
        pending = _lobby_root_nodes(Globals)
        while pending and len(seen) < 5000:
            node = pending.pop()
            if id(node) in seen:
                continue
            seen.add(id(node))
            try:
                pending.extend(list(node.getChildren()))
            except Exception:
                pass
            try:
                node_name = str(node.getName() or '').lower()
            except Exception:
                node_name = ''
            text = _node_text(node)
            try:
                normalized = text.strip().lower().replace(unichr(0x2019), "'")  # noqa: F821
            except Exception:
                try:
                    normalized = text.strip().lower()
                except Exception:
                    normalized = ''
            compact = ''.join(normalized.split())
            setter = _node_setter(node)

            if setter is not None and normalized in PLACEHOLDER_TEXT:
                setter('0')
                changed += 1
            if setter is not None and any(marker in node_name for marker in NAME_NODE_MARKERS):
                if text != local_player.nickname:
                    try:
                        setter(local_player.nickname)
                        changed += 1
                    except Exception:
                        pass
            # The Ranked card stays (as online) unless lobbyModel.hideRanked is set.
            if hide_ranked and (normalized == 'ranked' or 'ghillie' in normalized):
                hidden += _hide_ancestor(node, 2)
            # Team-bonus banner and empty team-member cards.
            broken_team_text = ("haven't paid" in normalized or 'additional 20%' in normalized or
                                'additional20%' in compact or 'allteammembersreceive' in compact)
            if broken_team_text:
                hidden += _hide_ancestor(node, 4)
            elif any(marker in node_name for marker in TEAM_NODE_MARKERS):
                hidden += _hide_ancestor(node, 1)
        if attempt == 0 or changed:
            log('local-lobby-ui-cleaned', attempt=attempt, scanned=len(seen),
                changed_text=changed, hidden_nodes=hidden)
    except Exception:
        if attempt == 0:
            log_error('local-lobby-ui-clean-error')
    if changed or hidden:
        _lobby['clean_changed_at'] = attempt
    # Panels keep building for a few seconds after UIMain opens; a lobby that
    # had nothing left to fix for a while stops being walked (21 full walks in
    # 10 s changed nothing - the logs: changed_text=0, hidden_nodes=0).
    if attempt < CLEAN_LOBBY_TRIES and (attempt < CLEAN_LOBBY_MIN_TRIES or changed or hidden or
                                        _lobby.get('clean_changed_at', -1) >= attempt - 2):
        call_later(0.5, clean_lobby_ui, attempt + 1)


CLEAN_LOBBY_TRIES = 20
CLEAN_LOBBY_MIN_TRIES = 6


# --------------------------------------------------------------------------
# Login hook
# --------------------------------------------------------------------------

def _wrap_logon_callback(callback, index):
    def observed_callback(*args, **kwargs):
        debug('logon-callback', index=index, args=[safe(item) for item in args])
        return callback(*args, **kwargs)
    return observed_callback


LOGIN_FAILED_STATUS = 0


def _logon_target(args):
    """(username, port) from BigWorld.logOn(host, username, password, port, callback).

    The port may also come as a digit string or as 'host:port' in args[0]."""
    username = args[1] if len(args) > 1 and isinstance(args[1], string_types) else ''
    port = None
    # args[3] is the port; never read the password (args[2]) as one.
    candidates = [args[3]] if len(args) > 3 else []
    candidates += [value for index, value in enumerate(args) if index >= 4]
    for value in candidates:
        if isinstance(value, string_types) and value.isdigit() and value is not username:
            value = int(value)
        if isinstance(value, bool) or not isinstance(value, (int, long_type)):
            continue
        if 0 < value < 65536:
            port = value
            break
    if port is None and args and isinstance(args[0], string_types) and ':' in args[0]:
        tail = args[0].rsplit(':', 1)[-1]
        if tail.isdigit() and 0 < int(tail) < 65536:
            port = int(tail)
    return username, port


def reset_login_flow():
    """A new logOn in the same game process (relog, other server) starts clean."""
    try:
        import ui.UISelectCharacter as select_module
        select_module._rl_create_pending = False
    except Exception:
        pass
    _lobby.update(entered=False, scene_started=False, character_screen_closed=False,
                  character_created=False)
    # NEW! state belongs to an account: the next one asks the backend again
    _lobby.pop('activity_version', None)
    _lobby.pop('activity_seen', None)
    forget_hall_backdrop()
    _lobby_ready['value'] = False
    _pyserver['failures'] = 0


def _finish_local_login(callback, username, port):
    reset_login_flow()
    _lobby.pop('kicked', None)          # a new login: a later kick is shown again
    if not backend_login(username, port):
        error = _backend['error'] or 'unknown error'
        if 'banned' in str(error).lower():
            show_message_dialog(error, 'Account banned')
        else:
            show_offline_tip('Login failed: %s' % error, force=True)
        callback(LOGIN_FAILED_STATUS)
        return
    callback(FORCE_STATUS)
    if ENTER_CHARACTER and FORCE_STATUS == 1:
        prepare_character_screen(0)


def _battle_host_logon(args):
    """ConnectMonitor.doConnectBattleHost calls logOn with a dict, not a host
    string.  The battleground is entered locally (battle_hook.py), so such a
    call must not be taken for a new lobby login."""
    return bool(args) and isinstance(args[0], dict) and 'servername' in args[0]


def observed_logOn(*args, **kwargs):
    if _battle_host_logon(args):
        log('logon-battle-host-ignored', target=safe(args[0], 300),
            battle=battle_running())
        for value in reversed(args):
            if callable(value):
                call_later(0.0, value, FORCE_STATUS or 1, False)
                break
        return None
    username, port = _logon_target(args)
    log('logon-call', account=safe(account_from_login(username)), port=port)
    wrapped = [
        _wrap_logon_callback(value, index) if callable(value) else value
        for index, value in enumerate(args)
    ]
    if FORCE_STATUS is not None:
        for value in reversed(wrapped):
            if callable(value):
                log('logon-local-result', status=FORCE_STATUS, wait=LOGIN_WAIT_SECONDS)
                call_later(LOGIN_WAIT_SECONDS, _finish_local_login, value, username, port)
                return None
    return BigWorld._local_original_logOn(*tuple(wrapped), **kwargs)


if hasattr(BigWorld, '_local_original_logOn'):
    BigWorld.logOn = BigWorld._local_original_logOn
else:
    BigWorld._local_original_logOn = BigWorld.logOn
BigWorld.logOn = observed_logOn
log('observer-installed', force_status=FORCE_STATUS, debug=DEBUG,
    forced_server_port=FORCED_PORT or None, forced_account=safe(FORCED_ACCOUNT))
if ENTER_CHARACTER_NOW:
    prepare_character_screen(0)
try:
    capture_game_errors()        # login-screen tracebacks too (server list)
except Exception:
    log_error('local-error-capture-early-error')
try:
    unlock_frame_rate()
except Exception:
    log_error('local-frame-rate-early-error')
try:
    use_real_server_clock()
except Exception:
    log_error('local-server-clock-early-error')
call_later(1.0, watch_login_screen)
call_later(BATTLE_ATTACH_POLL, attach_battle_hook)


# --- DieHard: live brand text rewrite + placeholder team-slot cleanup ---------------------
_dh_brand = {'rewritten': 0, 'done_paths': set()}
DH_BRAND_TEXT = (
    ('dicord.roslegacy.net', 'our Discord'), ('discord.roslegacy.net', 'our Discord'),
    ('roslegacy.net', 'DieHard ROS Online'), ('ros legacy', 'DieHard ROS'), ('roslegacy', 'DieHard ROS'),
    ('mirae labs', 'DieHard ROS'), ('mirae', 'DieHard'), ('t2.16163.com', 'DieHard ROS Online'),
    ('cc.163.com/t2', 'DieHard ROS Online'), ('legacy', 'DieHard'),
)
DH_SLOT_NEEDLES = ("haven't paid", "additional 20%", "\xe5\xb0\x8f\xe5\xb0\x8f\xe7\x99\xbd", "goddess")


def _dh_lower(text):
    try:
        return text.lower() if isinstance(text, str) else text.encode('utf-8', 'replace').lower()
    except Exception:
        return ''


def _dh_scene_nodes():
    try:
        import Globals
        return list(_lobby_root_nodes(Globals))
    except Exception:
        try:
            import cc
            return [cc.Director.getInstance().getRunningScene()]
        except Exception:
            return []


def _dh_rewrite_texts():
    changed = []
    pending = _dh_scene_nodes()
    seen = set()
    while pending and len(seen) < 6000:
        node = pending.pop()
        if node is None or id(node) in seen:
            continue
        seen.add(id(node))
        try:
            pending.extend(list(node.getChildren()))
        except Exception:
            pass
        text = _node_text(node)
        if not text:
            continue
        low = _dh_lower(text)
        if not any(k in low for k in ('legacy', 'mirae', '16163', 'dicord', 'discord')):
            continue
        new = text if isinstance(text, str) else text.encode('utf-8', 'replace')
        for old, rep in DH_BRAND_TEXT:
            idx = new.lower().find(old)
            while idx >= 0:
                new = new[:idx] + rep + new[idx + len(old):]
                idx = new.lower().find(old, idx + len(rep))
        setter = _node_setter(node)
        if setter is not None and new != text:
            try:
                setter(new)
                changed.append((text[:60], new[:60]))
            except Exception:
                pass
    if changed:
        _dh_brand['rewritten'] += len(changed)
        log('local-brand-text-rewritten', changes=changed[:20])


def _dh_slot_sweep():
    try:
        import Globals
        main_ui = getattr(Globals.uiMgr, 'UIMain', None)
        if main_ui is None:
            return
        nodes = walk_ui_nodes(main_ui, limit=4000)
        by_path = dict(nodes)
        hits = [path for path, node in nodes if any(n in _dh_lower(_node_text(node) or '') for n in DH_SLOT_NEEDLES)]
        hidden = []
        for path in hits:
            parts = path.split('/')
            target = None
            for depth in range(len(parts) - 1, 1, -1):
                name = parts[depth - 1].lower()
                if any(k in name for k in ('slot', 'member', 'team', 'mate', 'player')):
                    target = '/'.join(parts[:depth])
                    break
            if target is None and len(parts) > 3:
                target = '/'.join(parts[:-2])
            node = by_path.get(target)
            if node is not None and target not in _dh_brand['done_paths']:
                try:
                    node.setVisible(False)
                    hidden.append(target)
                    _dh_brand['done_paths'].add(target)
                except Exception:
                    pass
        if hidden:
            log('local-slot-sweep', hits=hits[:20], hidden=hidden[:20])
    except Exception:
        log_error('local-slot-sweep-error')


def _dh_brand_tick():
    try:
        _dh_rewrite_texts()
        _dh_slot_sweep()
    except Exception:
        log_error('local-brand-tick-error')
    call_later(2.0, _dh_brand_tick)


try:
    call_later(1.0, _dh_brand_tick)
    log('local-brand-watcher-installed')
except Exception:
    log_error('local-brand-watcher-error')
