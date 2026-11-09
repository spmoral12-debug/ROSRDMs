# ==============================================================================
# ROS REDEMPTION - MASTER LAUNCHER & ADMIN WEB CONTROL DASHBOARD
# ==============================================================================
import os
import sys
import json
import time
import socket
import sqlite3
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

PORT = 8799
BASE_DIR = r"C:\DieHardROS"
ACCOUNTS_DB = os.path.join(BASE_DIR, "local_update", "server_data", "accounts.db")
IDENTITY_JSON = os.path.join(BASE_DIR, "local_update", "local_identity.json")
RUNTIME_IDENTITY = os.path.join(BASE_DIR, "runtime", "app", "local_update", "local_identity.json")

def check_tcp_port(host, port, timeout=0.4):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False

def get_db():
    conn = sqlite3.connect(ACCOUNTS_DB)
    conn.row_factory = sqlite3.Row
    return conn

def sync_to_all_dbs(sql, params):
    dbs = [
        os.path.join(BASE_DIR, "local_update", "server_data", "accounts.db"),
        os.path.join(BASE_DIR, "runtime", "app", "local_update", "server_data", "accounts.db"),
        os.path.join(BASE_DIR, "ROS_Redemption_Server_Package", "local_update", "server_data", "accounts.db"),
        os.path.expanduser(r"~\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\local_update\server_data\accounts.db")
    ]
    for p in dbs:
        if os.path.exists(p):
            try:
                c = sqlite3.connect(p)
                c.execute(sql, params)
                c.commit()
                c.close()
            except Exception:
                pass

def get_active_username():
    try:
        if os.path.exists(IDENTITY_JSON):
            with open(IDENTITY_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data.get('sdkuid') or data.get('username') or 'Admin_Redemption'
    except Exception:
        pass
    return 'Admin_Redemption'

def set_active_account(username, nickname=""):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT a.id, a.username, c.gid, c.nickname FROM accounts a LEFT JOIN characters c ON a.id = c.account_id WHERE a.username = ?", (username,))
        row = c.fetchone()
        conn.close()

        aid = str(row['id']) if row else "3"
        nick = row['nickname'] if (row and row['nickname']) else (nickname or username)
        
        payload = {
            "aid": aid,
            "sdkuid": username,
            "gas_token": "local-offline-token",
            "username": nick,
            "chl_sdk_json": "{}"
        }

        for p in (IDENTITY_JSON, RUNTIME_IDENTITY):
            if os.path.exists(os.path.dirname(p)):
                with open(p, 'w', encoding='utf-8') as f:
                    json.dump(payload, f, indent=2)
        return True
    except Exception as e:
        print("Error setting active account:", e)
        return False

# ==============================================================================
# HTML: VALORANT CLIENT LAUNCHER
# ==============================================================================
LAUNCHER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ROS REDEMPTION // TACTICAL BATTLE ROYALE</title>
<style>
  :root {
    --val-red: #FF4655;
    --val-red-hover: #ff5f6d;
    --val-red-glow: rgba(255, 70, 85, 0.5);
    --val-cyan: #00F5D4;
    --val-dark: #0F1923;
    --val-darker: #0B1118;
    --val-panel: rgba(23, 33, 45, 0.90);
    --val-border: rgba(255, 255, 255, 0.12);
    --val-text: #ECE8E1;
    --val-muted: #8B97A5;
  }

  * {
    margin: 0; padding: 0; box-sizing: border-box; user-select: none;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
  }

  body {
    background: #000;
    color: var(--val-text);
    height: 100vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    position: relative;
  }

  .bg-wrapper {
    position: fixed; inset: 0; z-index: 0;
    background: radial-gradient(circle at 70% 30%, rgba(255, 70, 85, 0.15) 0%, transparent 60%),
                radial-gradient(circle at 20% 80%, rgba(0, 245, 212, 0.08) 0%, transparent 50%),
                url('/assets/bg.jpg') center center / cover no-repeat;
    filter: brightness(0.65) contrast(1.1);
  }

  .top-bar {
    position: relative; z-index: 10; height: 64px;
    background: rgba(15, 25, 35, 0.95);
    border-bottom: 1px solid var(--val-border);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 32px; backdrop-filter: blur(12px);
  }

  .brand { display: flex; align-items: center; gap: 14px; }
  .brand-logo {
    width: 32px; height: 32px; background: var(--val-red);
    display: flex; align-items: center; justify-content: center;
    font-weight: 900; font-size: 18px; color: #fff;
    clip-path: polygon(0 0, 100% 0, 85% 100%, 0 100%);
  }
  .brand-title {
    font-size: 16px; font-weight: 900; letter-spacing: 3px; color: #fff; text-transform: uppercase;
  }
  .brand-title span { color: var(--val-red); }

  .nav-tabs { display: flex; gap: 4px; margin-left: 40px; }
  .nav-tab {
    padding: 10px 22px; font-size: 12px; font-weight: 800; letter-spacing: 2px;
    text-transform: uppercase; color: var(--val-muted); cursor: pointer;
    border-bottom: 2px solid transparent; transition: all 0.2s ease;
  }
  .nav-tab:hover { color: #fff; }
  .nav-tab.active { color: #fff; border-bottom: 2px solid var(--val-red); }

  .top-right { display: flex; align-items: center; gap: 16px; margin-left: auto; }
  .server-badge {
    display: flex; align-items: center; gap: 8px; font-size: 11px;
    font-weight: 800; letter-spacing: 1.5px; color: var(--val-muted);
    background: rgba(0, 0, 0, 0.4); padding: 6px 14px;
    border: 1px solid rgba(255, 255, 255, 0.08);
  }
  .server-badge .dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: #ffa502; box-shadow: 0 0 8px #ffa502;
  }
  .user-badge {
    background: rgba(255, 70, 85, 0.12); border: 1px solid var(--val-red);
    color: #fff; padding: 6px 16px; font-size: 12px; font-weight: 800;
    letter-spacing: 1.5px; text-transform: uppercase;
  }

  .btn-admin-link {
    background: #f39c12; color: #000; font-size: 11px; font-weight: 900;
    letter-spacing: 1.5px; text-transform: uppercase; padding: 7px 14px;
    border: none; cursor: pointer; text-decoration: none;
    clip-path: polygon(0 0, calc(100% - 8px) 0, 100% 8px, 100% 100%, 8px 100%, 0 calc(100% - 8px));
    transition: all 0.2s ease;
  }
  .btn-admin-link:hover { background: #e67e22; transform: translateY(-1px); }

  .main-container {
    position: relative; z-index: 5; flex: 1; padding: 40px 60px;
    display: flex; flex-direction: column; justify-content: center;
  }

  .tab-pane { display: none; width: 100%; height: 100%; }
  .tab-pane.active { display: flex; align-items: center; justify-content: space-between; }

  /* PLAY TAB */
  .play-left { max-width: 650px; }
  .game-badge {
    display: inline-block; padding: 6px 14px; background: rgba(255, 255, 255, 0.06);
    border-left: 3px solid var(--val-red); font-size: 11px; font-weight: 800;
    letter-spacing: 2px; color: var(--val-muted); margin-bottom: 20px;
  }
  .hero-heading {
    font-size: 52px; font-weight: 900; line-height: 1.05; letter-spacing: 2px;
    text-transform: uppercase; color: #fff; margin-bottom: 16px;
    text-shadow: 0 4px 20px rgba(0, 0, 0, 0.8);
  }
  .hero-sub {
    font-size: 14px; color: var(--val-muted); max-width: 580px; margin-bottom: 24px; line-height: 1.6;
  }

  /* ANNOUNCEMENTS BANNER */
  .anno-box {
    background: rgba(15, 25, 35, 0.8); border-left: 3px solid var(--val-cyan);
    padding: 12px 18px; margin-bottom: 28px; max-width: 580px;
    border: 1px solid rgba(0, 245, 212, 0.2);
  }
  .anno-title { font-size: 11px; font-weight: 800; color: var(--val-cyan); letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 4px; }
  .anno-content { font-size: 12px; color: #fff; line-height: 1.4; }

  .btn-deploy {
    position: relative; padding: 22px 64px; background: var(--val-red);
    color: #fff; font-size: 20px; font-weight: 900; letter-spacing: 3px;
    text-transform: uppercase; border: none; cursor: pointer;
    clip-path: polygon(0 0, calc(100% - 16px) 0, 100% 16px, 100% 100%, 16px 100%, 0 calc(100% - 16px));
    box-shadow: 0 0 35px var(--val-red-glow); transition: all 0.2s ease;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
  }
  .btn-deploy:hover { background: var(--val-red-hover); transform: translateY(-2px); box-shadow: 0 0 50px rgba(255, 70, 85, 0.75); }
  .btn-deploy .btn-sub { font-size: 9px; letter-spacing: 2px; font-weight: 700; opacity: 0.85; margin-top: 3px; }

  /* AGENT CARD */
  .play-right { width: 360px; }
  .agent-card {
    background: var(--val-panel); border: 1px solid var(--val-border);
    backdrop-filter: blur(16px); padding: 24px;
    clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 0 100%);
  }
  .agent-header {
    display: flex; justify-content: space-between; align-items: flex-start;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 14px; margin-bottom: 16px;
  }
  .agent-callsign { font-size: 22px; font-weight: 900; letter-spacing: 1px; color: #fff; }
  .agent-id { font-size: 11px; color: var(--val-muted); letter-spacing: 1px; margin-top: 2px; }
  .agent-rank {
    padding: 4px 10px; background: rgba(0, 245, 212, 0.15); border: 1px solid var(--val-cyan);
    color: var(--val-cyan); font-size: 10px; font-weight: 800; letter-spacing: 1px;
  }

  .stats-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 18px; }
  .stat-box { background: rgba(0, 0, 0, 0.35); border: 1px solid rgba(255, 255, 255, 0.06); padding: 12px; }
  .stat-lbl { font-size: 10px; color: var(--val-muted); letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 4px; }
  .stat-val { font-size: 18px; font-weight: 800; color: #fff; }
  .stat-val.gold { color: #f1c40f; }
  .stat-val.dia { color: #00d2d3; }

  .loadout-title { font-size: 11px; font-weight: 800; letter-spacing: 1.5px; color: var(--val-muted); text-transform: uppercase; margin-bottom: 8px; }
  .loadout-list { display: flex; flex-direction: column; gap: 8px; }
  .loadout-pill {
    background: rgba(255, 255, 255, 0.04); border-left: 3px solid var(--val-cyan);
    padding: 8px 12px; font-size: 12px; display: flex; justify-content: space-between;
  }
  .loadout-pill span { color: var(--val-muted); font-size: 10px; font-weight: 700; letter-spacing: 1px; }

  /* FORMS */
  .form-wrapper {
    background: var(--val-panel); border: 1px solid var(--val-border);
    backdrop-filter: blur(16px); padding: 36px 44px; width: 480px; margin: 0 auto;
    clip-path: polygon(0 0, calc(100% - 16px) 0, 100% 16px, 100% 100%, 16px 100%, 0 calc(100% - 16px));
  }
  .form-title { font-size: 24px; font-weight: 900; letter-spacing: 2px; text-transform: uppercase; color: #fff; margin-bottom: 8px; }
  .form-sub { font-size: 12px; color: var(--val-muted); margin-bottom: 24px; line-height: 1.5; }

  .input-group { margin-bottom: 18px; }
  .input-lbl { font-size: 10px; font-weight: 800; letter-spacing: 1.5px; color: var(--val-muted); text-transform: uppercase; margin-bottom: 6px; display: block; }
  .val-input {
    width: 100%; padding: 14px; background: rgba(0, 0, 0, 0.4); border: 1px solid var(--val-border);
    color: #fff; font-size: 14px; outline: none; transition: border 0.2s ease;
  }
  .val-input:focus { border-color: var(--val-red); }

  .btn-submit {
    width: 100%; padding: 16px; background: var(--val-red); color: #fff;
    font-size: 14px; font-weight: 900; letter-spacing: 2px; text-transform: uppercase;
    border: none; cursor: pointer; transition: all 0.2s ease; margin-top: 10px;
  }
  .btn-submit:hover { background: var(--val-red-hover); box-shadow: 0 0 20px var(--val-red-glow); }

  /* ROSTER GRID */
  .roster-wrapper { width: 100%; height: 100%; overflow-y: auto; padding-right: 10px; }
  .roster-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 16px; margin-top: 20px; }
  .roster-card {
    background: var(--val-panel); border: 1px solid var(--val-border);
    padding: 18px; cursor: pointer; transition: all 0.2s ease;
  }
  .roster-card:hover { border-color: var(--val-red); transform: translateY(-2px); }
  .roster-card.active { border-color: var(--val-cyan); background: rgba(0, 245, 212, 0.05); }

  .toast {
    position: fixed; bottom: 30px; right: 30px; background: var(--val-dark);
    border-left: 4px solid var(--val-red); padding: 16px 24px; color: #fff;
    font-size: 13px; font-weight: 700; box-shadow: 0 8px 30px rgba(0, 0, 0, 0.8);
    display: none; z-index: 1000;
  }
</style>
</head>
<body>

  <div class="bg-wrapper"></div>

  <!-- TOP BAR -->
  <div class="top-bar">
    <div class="brand">
      <div class="brand-logo">R</div>
      <div class="brand-title">ROS <span>REDEMPTION</span></div>
    </div>

    <div class="nav-tabs">
      <div class="nav-tab active" onclick="switchTab('play')">Deploy</div>
      <div class="nav-tab" onclick="switchTab('create')">Register Agent</div>
      <div class="nav-tab" onclick="switchTab('roster')">Agent Roster</div>
    </div>

    <div class="top-right">
      <div class="server-badge">
        <div class="dot" id="serverDot"></div>
        <span id="serverStatusText">CHECKING SERVER...</span>
      </div>
      <a href="/admin" target="_blank" class="btn-admin-link">⚙️ Admin Panel</a>
      <div class="user-badge" id="topUserBadge">
        <span id="topCallsign">SEAN</span>
      </div>
    </div>
  </div>

  <!-- MAIN CONTAINER -->
  <div class="main-container">

    <!-- PLAY TAB -->
    <div class="tab-pane active" id="pane-play">
      <div class="play-left">
        <div class="game-badge">OFFICIAL LOCAL / ONLINE MASTER // GHILLIE ISLAND</div>
        <div class="hero-heading">RULES OF SURVIVAL:<br><span style="color: var(--val-red);">REDEMPTION</span></div>
        <div class="hero-sub">
          Engage in intense 40-bot survival across Ghillie Island. Equipped with customized Summer Bicycles, in-game Tango dance, responsive watercraft, and legit combat kill banners.
        </div>

        <!-- SERVER ANNOUNCEMENT BANNER -->
        <div class="anno-box" id="annoBox">
          <div class="anno-title" id="annoTitle">SERVER ANNOUNCEMENT</div>
          <div class="anno-content" id="annoContent">Connecting to master server announcements...</div>
        </div>

        <div class="play-actions">
          <button class="btn-deploy" id="btnDeploy" onclick="deployGame()">
            <span>DEPLOY // PLAY NOW</span>
            <span class="btn-sub">START GAME & JOIN BATTLEGROUND</span>
          </button>
        </div>
      </div>

      <div class="play-right">
        <div class="agent-card">
          <div class="agent-header">
            <div>
              <div class="agent-callsign" id="cardCallsign">SEAN</div>
              <div class="agent-id" id="cardUsername">User: sean</div>
            </div>
            <div class="agent-rank">READY</div>
          </div>

          <div class="stats-grid">
            <div class="stat-box">
              <div class="stat-lbl">Diamonds</div>
              <div class="stat-val dia" id="cardDia">100</div>
            </div>
            <div class="stat-box">
              <div class="stat-lbl">Gold Coins</div>
              <div class="stat-val gold" id="cardGold">5,000</div>
            </div>
          </div>

          <div class="loadout-title">Starter Perks Equipped</div>
          <div class="loadout-list">
            <div class="loadout-pill">
              🚲 Summer Bicycle
              <span>Shift + 1</span>
            </div>
            <div class="loadout-pill">
              💃 Tango Dance Emote
              <span>Action Wheel</span>
            </div>
            <div class="loadout-pill">
              🎯 Blue Kill Banner
              <span>Active</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- REGISTER ACCOUNT TAB (CLEAN: NO MONEY / CHEATS) -->
    <div class="tab-pane" id="pane-create">
      <div class="form-wrapper">
        <div class="form-title">Register New Agent</div>
        <div class="form-sub">Create a new player account on the master server. Standard server starter currencies and loadouts are automatically assigned.</div>

        <div class="input-group">
          <label class="input-lbl">Agent Username (Login ID)</label>
          <input type="text" class="val-input" id="inpUsername" placeholder="e.g. warrior99" autocomplete="off">
        </div>

        <div class="input-group">
          <label class="input-lbl">Callsign / In-Game Nickname</label>
          <input type="text" class="val-input" id="inpNickname" placeholder="e.g. Ghost_Sniper" autocomplete="off">
        </div>

        <div class="input-group">
          <label class="input-lbl">Password (Optional)</label>
          <input type="password" class="val-input" id="inpPassword" placeholder="••••••••" autocomplete="off">
        </div>

        <button class="btn-submit" onclick="createAccount()">Register Account</button>
      </div>
    </div>

    <!-- AGENT ROSTER TAB -->
    <div class="tab-pane" id="pane-roster">
      <div class="roster-wrapper">
        <div style="font-size: 22px; font-weight: 900; letter-spacing: 2px;">AGENT ROSTER (SELECT ACTIVE ACCOUNT)</div>
        <div class="roster-grid" id="rosterGrid"></div>
      </div>
    </div>

  </div>

  <div class="toast" id="toastMsg"></div>

<script>
  let activeUser = 'Admin_Redemption';
  let accountsList = [];

  function switchTab(name) {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    
    const tabs = { 'play': 0, 'create': 1, 'roster': 2 };
    document.querySelectorAll('.nav-tab')[tabs[name]].classList.add('active');
    document.getElementById('pane-' + name).classList.add('active');

    if (name === 'roster') loadAccounts();
  }

  function showToast(msg, isError) {
    const t = document.getElementById('toastMsg');
    t.innerText = msg;
    t.style.borderLeftColor = isError ? '#FF4655' : '#00F5D4';
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 3500);
  }

  async function checkServerStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      const isOnline = data.server_online;
      document.getElementById('serverDot').style.background = isOnline ? '#2ed573' : '#ffa502';
      document.getElementById('serverDot').style.boxShadow = isOnline ? '0 0 8px #2ed573' : '0 0 8px #ffa502';
      document.getElementById('serverStatusText').innerText = isOnline ? 'SERVER ONLINE (19000) • 15ms' : 'CONNECTING (OFFLINE)';

      if (data.active_account) {
        activeUser = data.active_account.username;
        document.getElementById('topCallsign').innerText = (data.active_account.nickname || activeUser).toUpperCase();
        document.getElementById('cardCallsign').innerText = (data.active_account.nickname || activeUser).toUpperCase();
        document.getElementById('cardUsername').innerText = 'User: ' + activeUser;
        document.getElementById('cardDia').innerText = Number(data.active_account.diamonds || 0).toLocaleString();
        document.getElementById('cardGold').innerText = Number(data.active_account.gold || 0).toLocaleString();
      }

      if (data.announcement) {
        document.getElementById('annoTitle').innerText = data.announcement.title || 'SERVER ANNOUNCEMENT';
        document.getElementById('annoContent').innerText = data.announcement.content || '';
      }
    } catch (e) {}
  }

  async function loadAccounts() {
    try {
      const res = await fetch('/api/accounts');
      const data = await res.json();
      accountsList = data.accounts || [];
      const grid = document.getElementById('rosterGrid');
      grid.innerHTML = '';

      accountsList.forEach(acc => {
        const card = document.createElement('div');
        const isActive = acc.username === activeUser;
        card.className = 'roster-card ' + (isActive ? 'active' : '');
        card.innerHTML = `
          <div style="font-size: 16px; font-weight: 900; color: #fff; margin-bottom: 4px;">${acc.nickname || acc.username}</div>
          <div style="font-size: 11px; color: var(--val-muted); margin-bottom: 12px;">@${acc.username} • GID: ${acc.gid || 'N/A'}</div>
          <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 700;">
            <span style="color: #00d2d3;">💎 ${Number(acc.diamonds || 0).toLocaleString()}</span>
            <span style="color: #f1c40f;">🪙 ${Number(acc.gold || 0).toLocaleString()}</span>
          </div>
        `;
        card.onclick = () => selectAccount(acc.username);
        grid.appendChild(card);
      });
    } catch(e) {}
  }

  async function selectAccount(username) {
    try {
      const res = await fetch('/api/select_account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username })
      });
      const data = await res.json();
      if (data.ok) {
        showToast('Active Account Switched: ' + username);
        checkServerStatus();
        switchTab('play');
      }
    } catch(e) {}
  }

  async function createAccount() {
    const username = document.getElementById('inpUsername').value.trim();
    const nickname = document.getElementById('inpNickname').value.trim() || username;

    if (!username) {
      showToast('Please enter an Agent Username!', true);
      return;
    }

    try {
      const res = await fetch('/api/create_account', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, nickname })
      });
      const data = await res.json();
      if (data.ok) {
        showToast('Agent Registered: ' + nickname);
        document.getElementById('inpUsername').value = '';
        document.getElementById('inpNickname').value = '';
        checkServerStatus();
        switchTab('play');
      } else {
        showToast(data.error || 'Failed to create account', true);
      }
    } catch(e) {
      showToast('Network error during recruitment', true);
    }
  }

  async function deployGame() {
    const btn = document.getElementById('btnDeploy');
    btn.disabled = true;
    btn.innerText = 'DEPLOYING BATTLEGROUND...';
    showToast('Launching ROS Redemption as ' + activeUser + '...');

    try {
      const res = await fetch('/api/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: activeUser })
      });
      const data = await res.json();
      if (data.ok) {
        btn.innerText = 'GAME RUNNING...';
        setTimeout(() => {
          btn.disabled = false;
          btn.innerHTML = '<span>DEPLOY // PLAY NOW</span><span class="btn-sub">START GAME & JOIN BATTLEGROUND</span>';
        }, 8000);
      }
    } catch(e) {
      btn.disabled = false;
      btn.innerHTML = '<span>DEPLOY // PLAY NOW</span><span class="btn-sub">START GAME & JOIN BATTLEGROUND</span>';
    }
  }

  checkServerStatus();
  setInterval(checkServerStatus, 5000);
</script>
</body>
</html>
"""

# ==============================================================================
# HTML: MASTER WEB ADMIN DASHBOARD
# ==============================================================================
ADMIN_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ROS REDEMPTION // MASTER WEB ADMIN DASHBOARD</title>
<style>
  :root {
    --bg-dark: #0A0E14;
    --panel-bg: #131922;
    --panel-border: rgba(255, 255, 255, 0.08);
    --accent-red: #FF4655;
    --accent-gold: #f39c12;
    --accent-cyan: #00F5D4;
    --text-main: #ECE8E1;
    --text-muted: #7E8A98;
  }

  * { margin:0; padding:0; box-sizing:border-box; font-family:'Segoe UI', sans-serif; }
  body { background: var(--bg-dark); color: var(--text-main); height: 100vh; display: flex; flex-direction: column; }

  header {
    height: 60px; background: var(--panel-bg); border-bottom: 1px solid var(--panel-border);
    display: flex; align-items: center; justify-content: space-between; padding: 0 28px;
  }
  .title { font-size: 16px; font-weight: 900; letter-spacing: 2px; text-transform: uppercase; }
  .title span { color: var(--accent-red); }
  
  nav { display: flex; gap: 8px; }
  .nav-btn {
    background: none; border: 1px solid transparent; color: var(--text-muted);
    padding: 8px 16px; font-size: 12px; font-weight: 800; letter-spacing: 1.5px;
    cursor: pointer; text-transform: uppercase; transition: all 0.2s;
  }
  .nav-btn:hover { color: #fff; }
  .nav-btn.active { background: rgba(255, 70, 85, 0.15); border-color: var(--accent-red); color: #fff; }

  main { flex: 1; padding: 24px 32px; overflow-y: auto; }
  .page { display: none; }
  .page.active { display: block; }

  /* STATS CARDS */
  .stats-row { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
  .stat-card {
    background: var(--panel-bg); border: 1px solid var(--panel-border); padding: 18px;
    border-left: 3px solid var(--accent-red);
  }
  .stat-card.cyan { border-left-color: var(--accent-cyan); }
  .stat-card.gold { border-left-color: var(--accent-gold); }
  .stat-card.green { border-left-color: #2ed573; }
  .stat-lbl { font-size: 11px; color: var(--text-muted); font-weight: 700; text-transform: uppercase; margin-bottom: 6px; }
  .stat-num { font-size: 24px; font-weight: 900; color: #fff; }

  /* TABLES */
  .panel-box {
    background: var(--panel-bg); border: 1px solid var(--panel-border); padding: 20px; margin-bottom: 24px;
  }
  .box-title { font-size: 14px; font-weight: 900; letter-spacing: 1.5px; text-transform: uppercase; margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; padding: 12px; color: var(--text-muted); font-size: 11px; text-transform: uppercase; border-bottom: 1px solid var(--panel-border); }
  td { padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.03); }
  tr:hover td { background: rgba(255,255,255,0.02); }

  .badge-banned { color: #ff4757; background: rgba(255,71,87,0.15); padding: 4px 8px; font-size: 10px; font-weight: 800; border-radius: 3px; }
  .badge-active { color: #2ed573; background: rgba(46,213,115,0.15); padding: 4px 8px; font-size: 10px; font-weight: 800; border-radius: 3px; }

  .btn-action {
    background: rgba(255, 255, 255, 0.08); border: 1px solid var(--panel-border);
    color: #fff; padding: 6px 12px; font-size: 11px; font-weight: 700; cursor: pointer; margin-right: 4px;
  }
  .btn-action:hover { background: rgba(255, 255, 255, 0.15); }
  .btn-action.red { background: rgba(255, 70, 85, 0.2); border-color: var(--accent-red); color: var(--accent-red); }
  .btn-action.cyan { background: rgba(0, 245, 212, 0.15); border-color: var(--accent-cyan); color: var(--accent-cyan); }

  .form-group { margin-bottom: 16px; }
  .form-lbl { font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; margin-bottom: 6px; display: block; }
  .form-input {
    width: 100%; max-width: 450px; padding: 10px; background: rgba(0,0,0,0.4);
    border: 1px solid var(--panel-border); color: #fff; font-size: 13px; outline: none;
  }
  .form-input:focus { border-color: var(--accent-red); }
  .btn-save {
    padding: 12px 24px; background: var(--accent-red); color: #fff; border: none; font-weight: 800;
    letter-spacing: 1.5px; text-transform: uppercase; cursor: pointer;
  }
</style>
</head>
<body>

  <header>
    <div class="title">ROS <span>REDEMPTION</span> // MASTER ADMIN DASHBOARD</div>
    <nav>
      <button class="nav-btn active" onclick="switchPage('overview')">Overview</button>
      <button class="nav-btn" onclick="switchPage('players')">Player & Economy Manager</button>
      <button class="nav-btn" onclick="switchPage('hwid')">HWID Ban Manager</button>
      <button class="nav-btn" onclick="switchPage('anno')">Server Announcements</button>
    </nav>
  </header>

  <main>

    <!-- OVERVIEW -->
    <div class="page active" id="page-overview">
      <div class="stats-row">
        <div class="stat-card green">
          <div class="stat-lbl">Lobby Server (19000)</div>
          <div class="stat-num" id="statLobby">ONLINE</div>
        </div>
        <div class="stat-card cyan">
          <div class="stat-lbl">Battleground Server (19100)</div>
          <div class="stat-num" id="statBattle">ONLINE</div>
        </div>
        <div class="stat-card gold">
          <div class="stat-lbl">Total Registered Players</div>
          <div class="stat-num" id="statPlayers">0</div>
        </div>
        <div class="stat-card">
          <div class="stat-lbl">Banned Accounts / HWIDs</div>
          <div class="stat-num" id="statBans">0</div>
        </div>
      </div>

      <div class="panel-box">
        <div class="box-title">System Status & Environment</div>
        <div style="font-size: 13px; color: var(--text-muted); line-height: 1.8;">
          • <b>Lobby & Game Port:</b> 19000 TCP/UDP<br>
          • <b>Battleground Port:</b> 19100 UDP<br>
          • <b>Database Storage:</b> local_update/server_data/accounts.db (Synced)<br>
          • <b>Supply Boxes:</b> 254 Custom Boxes Active with 5-Draw Guarantee<br>
          • <b>Admin Operator:</b> Sean (Full God Mode Access)
        </div>
      </div>
    </div>

    <!-- PLAYERS & ECONOMY -->
    <div class="page" id="page-players">
      <div class="panel-box">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
          <div class="box-title" style="margin: 0;">Registered Accounts & Economy</div>
          <button class="btn-action" onclick="loadPlayers()">🔄 Refresh Table</button>
        </div>

        <table>
          <thead>
            <tr>
              <th>GID</th>
              <th>Username</th>
              <th>Callsign</th>
              <th>Diamonds</th>
              <th>Gold</th>
              <th>Status</th>
              <th>Actions (Grant / Ban)</th>
            </tr>
          </thead>
          <tbody id="playerTableBody"></tbody>
        </table>
      </div>
    </div>

    <!-- HWID BAN MANAGER -->
    <div class="page" id="page-hwid">
      <div class="panel-box">
        <div class="box-title">Ban New Machine ID (HWID)</div>
        <div style="display: flex; gap: 12px; align-items: flex-end; margin-bottom: 24px;">
          <div class="form-group" style="margin: 0;">
            <label class="form-lbl">Hardware ID / Machine Hash</label>
            <input type="text" class="form-input" id="inpHwid" placeholder="e.g. 4B82-99FA-1002-EC81">
          </div>
          <div class="form-group" style="margin: 0;">
            <label class="form-lbl">Ban Reason</label>
            <input type="text" class="form-input" id="inpHwidReason" placeholder="e.g. Speedhack / Wallhack">
          </div>
          <button class="btn-save" onclick="banHwid()">Ban HWID</button>
        </div>

        <div class="box-title">Active HWID Hardware Bans</div>
        <table>
          <thead>
            <tr>
              <th>HWID</th>
              <th>Reason</th>
              <th>Banned At</th>
              <th>Banned By</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody id="hwidTableBody"></tbody>
        </table>
      </div>
    </div>

    <!-- ANNOUNCEMENTS -->
    <div class="page" id="page-anno">
      <div class="panel-box">
        <div class="box-title">Publish Server Announcement (Launcher & In-Game Ticker)</div>
        <div class="form-group">
          <label class="form-lbl">Announcement Title</label>
          <input type="text" class="form-input" id="inpAnnoTitle" placeholder="e.g. SERVER MAINTENANCE AT 12:00 AM">
        </div>
        <div class="form-group">
          <label class="form-lbl">Message Content</label>
          <textarea class="form-input" id="inpAnnoContent" style="height: 80px;" placeholder="Full announcement text..."></textarea>
        </div>
        <button class="btn-save" onclick="saveAnnouncement()">Publish Announcement</button>
      </div>
    </div>

  </main>

<script>
  function switchPage(name) {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const map = { 'overview': 0, 'players': 1, 'hwid': 2, 'anno': 3 };
    document.querySelectorAll('.nav-btn')[map[name]].classList.add('active');
    document.getElementById('page-' + name).classList.add('active');

    if (name === 'overview') loadOverview();
    if (name === 'players') loadPlayers();
    if (name === 'hwid') loadHwids();
  }

  async function loadOverview() {
    try {
      const res = await fetch('/api/admin/overview');
      const data = await res.json();
      document.getElementById('statLobby').innerText = data.lobby_online ? 'ONLINE' : 'STANDBY';
      document.getElementById('statBattle').innerText = data.battle_online ? 'ONLINE' : 'STANDBY';
      document.getElementById('statPlayers').innerText = data.total_players || 0;
      document.getElementById('statBans').innerText = data.total_bans || 0;
    } catch(e) {}
  }

  async function loadPlayers() {
    try {
      const res = await fetch('/api/admin/players');
      const data = await res.json();
      const body = document.getElementById('playerTableBody');
      body.innerHTML = '';

      (data.players || []).forEach(p => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><b>${p.gid || 'N/A'}</b></td>
          <td>${p.username}</td>
          <td><b>${p.nickname || p.username}</b></td>
          <td style="color: #00d2d3;">💎 ${Number(p.diamonds || 0).toLocaleString()}</td>
          <td style="color: #f1c40f;">🪙 ${Number(p.gold || 0).toLocaleString()}</td>
          <td>${p.banned ? '<span class="badge-banned">BANNED</span>' : '<span class="badge-active">ACTIVE</span>'}</td>
          <td>
            <button class="btn-action cyan" onclick="grantCurrency(${p.gid}, 999999999, 999999999)">+999M Max</button>
            <button class="btn-action" onclick="promptCustomCurrency(${p.gid})">Edit Coins</button>
            ${p.banned ? 
              `<button class="btn-action" onclick="toggleBan('${p.username}', false)">Unban</button>` : 
              `<button class="btn-action red" onclick="toggleBan('${p.username}', true)">Ban</button>`}
          </td>
        `;
        body.appendChild(tr);
      });
    } catch(e) {}
  }

  async function grantCurrency(gid, dia, gold) {
    if (!gid) return alert('Invalid GID');
    const res = await fetch('/api/admin/grant_currency', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gid, diamonds: dia, gold })
    });
    const d = await res.json();
    if (d.ok) {
      alert('Granted ' + Number(dia).toLocaleString() + ' Diamonds & ' + Number(gold).toLocaleString() + ' Gold to GID ' + gid);
      loadPlayers();
    } else {
      alert(d.error || 'Failed');
    }
  }

  function promptCustomCurrency(gid) {
    const dia = prompt('Enter new Diamonds amount:', '100000');
    if (dia === null) return;
    const gold = prompt('Enter new Gold amount:', '500000');
    if (gold === null) return;
    grantCurrency(gid, parseInt(dia) || 0, parseInt(gold) || 0);
  }

  async function toggleBan(username, banned) {
    const reason = banned ? (prompt('Enter Ban Reason:', 'Server Rules Violation') || 'Violation') : '';
    const res = await fetch('/api/admin/ban_account', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, banned, reason })
    });
    const d = await res.json();
    if (d.ok) {
      alert((banned ? 'Banned ' : 'Unbanned ') + username);
      loadPlayers();
    }
  }

  async function loadHwids() {
    try {
      const res = await fetch('/api/admin/hwids');
      const data = await res.json();
      const body = document.getElementById('hwidTableBody');
      body.innerHTML = '';
      (data.hwids || []).forEach(h => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><code>${h.hwid}</code></td>
          <td>${h.reason}</td>
          <td>${new Date(h.banned_at * 1000).toLocaleString()}</td>
          <td>${h.banned_by}</td>
          <td><button class="btn-action red" onclick="unbanHwid('${h.hwid}')">Unban HWID</button></td>
        `;
        body.appendChild(tr);
      });
    } catch(e) {}
  }

  async function banHwid() {
    const hwid = document.getElementById('inpHwid').value.trim();
    const reason = document.getElementById('inpHwidReason').value.trim() || 'Admin Hardware Ban';
    if (!hwid) return alert('Enter HWID');
    const res = await fetch('/api/admin/ban_hwid', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hwid, reason, banned: true })
    });
    const d = await res.json();
    if (d.ok) {
      alert('HWID Banned Successfully: ' + hwid);
      document.getElementById('inpHwid').value = '';
      loadHwids();
    }
  }

  async function unbanHwid(hwid) {
    const res = await fetch('/api/admin/ban_hwid', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hwid, banned: false })
    });
    const d = await res.json();
    if (d.ok) {
      alert('HWID Unbanned: ' + hwid);
      loadHwids();
    }
  }

  async function saveAnnouncement() {
    const title = document.getElementById('inpAnnoTitle').value.trim();
    const content = document.getElementById('inpAnnoContent').value.trim();
    if (!title || !content) return alert('Title and Content required');
    const res = await fetch('/api/admin/announcement', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, content })
    });
    const d = await res.json();
    if (d.ok) {
      alert('Announcement Published to Launcher & Game Ticker!');
    }
  }

  loadOverview();
</script>
</body>
</html>
"""

# ==============================================================================
# HTTP REQUEST HANDLER
# ==============================================================================
class LauncherHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(LAUNCHER_HTML.encode("utf-8"))
            return

        if path == "/admin":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(ADMIN_HTML.encode("utf-8"))
            return

        if path.startswith("/assets/"):
            filename = os.path.basename(path)
            file_path = os.path.join(BASE_DIR, "launcher", "assets", filename)
            if os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower()
                mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                with open(file_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            self.send_response(404)
            self.end_headers()
            return

        if path == "/api/status":
            is_server = check_tcp_port("127.0.0.1", 19000, 0.3)
            is_battle = check_tcp_port("127.0.0.1", 19100, 0.3)
            active_name = get_active_username()

            active_info = {"username": active_name, "nickname": active_name, "diamonds": 100, "gold": 5000}
            anno = {"title": "SERVER ONLINE", "content": "Dedicated ROS Redemption master server is ready."}
            try:
                conn = get_db()
                c = conn.cursor()
                c.execute('''
                    SELECT a.username, c.nickname, w.gp, (w.freeYuanbao + w.payYuanbao) AS dia
                    FROM accounts a
                    LEFT JOIN characters c ON a.id = c.account_id
                    LEFT JOIN wallets w ON c.gid = w.gid
                    WHERE a.username = ?
                ''', (active_name,))
                r = c.fetchone()
                if r:
                    active_info["nickname"] = r["nickname"] or active_name
                    active_info["gold"] = r["gp"] or 0
                    active_info["diamonds"] = r["dia"] or 0

                c.execute('SELECT title, content FROM server_announcements WHERE active = 1 ORDER BY id DESC LIMIT 1')
                ann_row = c.fetchone()
                if ann_row:
                    anno = {"title": ann_row["title"], "content": ann_row["content"]}
                conn.close()
            except Exception:
                pass

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "server_online": is_server,
                "battle_online": is_battle,
                "active_account": active_info,
                "announcement": anno
            }).encode("utf-8"))
            return

        if path == "/api/accounts":
            accounts = []
            try:
                conn = get_db()
                c = conn.cursor()
                c.execute('''
                    SELECT a.id, a.username, c.gid, c.nickname, c.level, w.gp as gold, (w.freeYuanbao + w.payYuanbao) as diamonds
                    FROM accounts a
                    LEFT JOIN characters c ON a.id = c.account_id
                    LEFT JOIN wallets w ON c.gid = w.gid
                    ORDER BY a.id ASC
                ''')
                for r in c.fetchall():
                    accounts.append({
                        "id": r["id"], "username": r["username"], "gid": r["gid"],
                        "nickname": r["nickname"] or r["username"],
                        "diamonds": r["diamonds"] or 0, "gold": r["gold"] or 0
                    })
                conn.close()
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"accounts": accounts}).encode("utf-8"))
            return

        # ADMIN API ENDPOINTS
        if path == "/api/admin/overview":
            is_server = check_tcp_port("127.0.0.1", 19000, 0.3)
            is_battle = check_tcp_port("127.0.0.1", 19100, 0.3)
            total_players = 0
            total_bans = 0
            try:
                conn = get_db()
                c = conn.cursor()
                c.execute('SELECT COUNT(*) FROM accounts')
                total_players = c.fetchone()[0]
                c.execute('SELECT COUNT(*) FROM accounts WHERE banned = 1')
                acc_bans = c.fetchone()[0]
                c.execute('SELECT COUNT(*) FROM banned_hwids')
                hwid_bans = c.fetchone()[0]
                total_bans = acc_bans + hwid_bans
                conn.close()
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "lobby_online": is_server,
                "battle_online": is_battle,
                "total_players": total_players,
                "total_bans": total_bans
            }).encode("utf-8"))
            return

        if path == "/api/admin/players":
            players = []
            try:
                conn = get_db()
                c = conn.cursor()
                c.execute('''
                    SELECT a.username, a.banned, c.gid, c.nickname, w.gp as gold, (w.freeYuanbao + w.payYuanbao) as diamonds
                    FROM accounts a
                    LEFT JOIN characters c ON a.id = c.account_id
                    LEFT JOIN wallets w ON c.gid = w.gid
                    ORDER BY c.gid ASC
                ''')
                for r in c.fetchall():
                    players.append({
                        "username": r["username"], "gid": r["gid"], "nickname": r["nickname"] or r["username"],
                        "gold": r["gold"] or 0, "diamonds": r["diamonds"] or 0, "banned": bool(r["banned"])
                    })
                conn.close()
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"players": players}).encode("utf-8"))
            return

        if path == "/api/admin/hwids":
            hwids = []
            try:
                conn = get_db()
                c = conn.cursor()
                c.execute('SELECT hwid, reason, banned_at, banned_by FROM banned_hwids ORDER BY banned_at DESC')
                for r in c.fetchall():
                    hwids.append({"hwid": r["hwid"], "reason": r["reason"], "banned_at": r["banned_at"], "banned_by": r["banned_by"]})
                conn.close()
            except Exception:
                pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"hwids": hwids}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8')
        data = {}
        try:
            data = json.loads(body)
        except Exception:
            pass

        if path == "/api/select_account":
            username = data.get("username", "")
            if set_active_account(username):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                return
            self.send_response(400)
            self.end_headers()
            return

        # CLEAN ACCOUNT REGISTRATION (NO CHEAT / NO MONEY INPUT)
        if path == "/api/create_account":
            username = data.get("username", "").strip()
            nickname = data.get("nickname", "").strip() or username
            
            # Standard legitimate starter economy
            dia = 100
            gold = 5000

            if not username or len(username) < 2:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": "Username must be at least 2 characters!"}).encode("utf-8"))
                return

            try:
                conn = get_db()
                c = conn.cursor()
                c.execute("SELECT id FROM accounts WHERE username = ?", (username,))
                if c.fetchone():
                    conn.close()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ok": False, "error": "Username already exists!"}).encode("utf-8"))
                    return

                now = int(time.time())
                c.execute("INSERT INTO accounts (username, created, last_login, last_server, banned, note, ban_reason, ban_until) VALUES (?, ?, ?, 10501, 0, 'Official Client', '', 0)", (username, now, now))
                acc_id = c.lastrowid

                c.execute("SELECT MAX(gid) FROM characters")
                max_gid = c.fetchone()[0] or 10000000
                new_gid = max_gid + 1

                lobby_dict = {
                    "country": "PH", "nation": "PH", "flag": "PH",
                    "appearance": {
                        "dtsBodyAppearanceList": [],
                        "dtsWearableAppearanceList": [1110326, 1111326, 112495],
                        "dtsWeaponAppearanceList": [120016, 121021],
                        "dtsInGameActionAppearanceIDs": [909042, 909030, 909031],
                        "dtsInGameActionSuitAppearanceIDs": [909042]
                    }
                }

                c.execute('''
                    INSERT INTO characters (gid, account_id, server_id, nickname, character_type, created, base_level, level, lobby, created_at, last_login)
                    VALUES (?, ?, 10501, ?, 10002, 1, 1, 1, ?, ?, ?)
                ''', (new_gid, acc_id, nickname, json.dumps(lobby_dict), now, now))

                c.execute("INSERT INTO wallets (gid, gp, sp, freeYuanbao, payYuanbao) VALUES (?, ?, 0, ?, 0)", (new_gid, gold, dia))

                char_data = {
                    "depot": {
                        "140073": {"count": 1, "expires": 0},
                        "909042": {"count": 1, "expires": 0}
                    },
                    "equipped": {
                        "dtsInGameActionAppearanceIDs": [909042, 909030, 909031],
                        "dtsInGameActionSuitAppearanceIDs": [909042]
                    }
                }
                c.execute("INSERT INTO character_data (gid, data) VALUES (?, ?)", (new_gid, json.dumps(char_data)))

                conn.commit()
                conn.close()

                # Sync to all target databases
                sync_to_all_dbs("INSERT OR IGNORE INTO accounts (id, username, created, last_login, last_server, banned, note, ban_reason, ban_until) VALUES (?, ?, ?, ?, 10501, 0, 'Official Client', '', 0)", (acc_id, username, now, now))
                sync_to_all_dbs("INSERT OR IGNORE INTO characters (gid, account_id, server_id, nickname, character_type, created, base_level, level, lobby, created_at, last_login) VALUES (?, ?, 10501, ?, 10002, 1, 1, 1, ?, ?, ?)", (new_gid, acc_id, nickname, json.dumps(lobby_dict), now, now))
                sync_to_all_dbs("INSERT OR IGNORE INTO wallets (gid, gp, sp, freeYuanbao, payYuanbao) VALUES (?, ?, 0, ?, 0)", (new_gid, gold, dia))

                set_active_account(username, nickname)

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "gid": new_gid, "username": username, "nickname": nickname}).encode("utf-8"))
                return
            except Exception as e:
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
                return

        # ADMIN ACTION: GRANT CURRENCY
        if path == "/api/admin/grant_currency":
            gid = int(data.get("gid", 0))
            dia = int(data.get("diamonds", 0))
            gold = int(data.get("gold", 0))
            try:
                sync_to_all_dbs("UPDATE wallets SET gp = ?, freeYuanbao = ?, payYuanbao = ? WHERE gid = ?", (gold, dia, dia, gid))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
                return

        # ADMIN ACTION: BAN / UNBAN ACCOUNT
        if path == "/api/admin/ban_account":
            username = data.get("username", "")
            banned = 1 if data.get("banned", False) else 0
            reason = data.get("reason", "")
            try:
                sync_to_all_dbs("UPDATE accounts SET banned = ?, ban_reason = ? WHERE username = ?", (banned, reason, username))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
                return

        # ADMIN ACTION: BAN / UNBAN HWID
        if path == "/api/admin/ban_hwid":
            hwid = data.get("hwid", "").strip()
            banned = data.get("banned", True)
            reason = data.get("reason", "Admin Machine Ban")
            now = int(time.time())
            try:
                if banned:
                    sync_to_all_dbs("INSERT OR REPLACE INTO banned_hwids (hwid, reason, banned_at, banned_by) VALUES (?, ?, ?, 'Admin Sean')", (hwid, reason, now))
                else:
                    sync_to_all_dbs("DELETE FROM banned_hwids WHERE hwid = ?", (hwid,))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
                return

        # ADMIN ACTION: PUBLISH ANNOUNCEMENT
        if path == "/api/admin/announcement":
            title = data.get("title", "").strip()
            content = data.get("content", "").strip()
            now = int(time.time())
            try:
                sync_to_all_dbs("INSERT INTO server_announcements (title, content, priority, created_at, active) VALUES (?, ?, 'HIGH', ?, 1)", (title, content, now))
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
                return

        # LAUNCH GAME CLIENT
        if path == "/api/launch":
            username = data.get("username", "") or get_active_username()
            try:
                app_dir = os.path.join(BASE_DIR, "runtime", "app")
                python_exe = os.path.join(BASE_DIR, "runtime", "python", "python.exe")
                cmd = [python_exe, "start_game.pyc", "--direct", "--account", username]
                
                env = dict(os.environ)
                env["ROS_GAME_DIR"] = BASE_DIR
                env["ROS_RT_KEY"] = "f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf"
                env["PYTHONIOENCODING"] = "utf-8"

                subprocess.Popen(cmd, cwd=app_dir, env=env)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode("utf-8"))
                return
            except Exception as e:
                self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode("utf-8"))
                return

        self.send_response(404)
        self.end_headers()

def run_server():
    HTTPServer.allow_reuse_address = True
    server = HTTPServer(("127.0.0.1", PORT), LauncherHandler)
    print(f"=== ROS REDEMPTION MASTER LAUNCHER & ADMIN DASHBOARD ON http://127.0.0.1:{PORT} ===")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    run_server()
