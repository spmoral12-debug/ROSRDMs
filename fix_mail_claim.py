import sqlite3
import json
import os
import shutil

print("=== FIXING MAIL CLAIM & UIItemDisplay KeyError: 0 ===")

BASE_DIR = r"C:\DieHardROS"

# --------------------------------------------------------------------------
# 1. Update accounts.db: normalize all mail attachments to [[item, count]]
# --------------------------------------------------------------------------
db_paths = [
    os.path.join(BASE_DIR, "local_update", "server_data", "accounts.db"),
    os.path.join(BASE_DIR, "runtime", "app", "local_update", "server_data", "accounts.db"),
    os.path.join(BASE_DIR, "ROS_Redemption_Server_Package", "local_update", "server_data", "accounts.db")
]

for db_path in db_paths:
    if not os.path.exists(db_path):
        continue
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, props FROM mails WHERE deleted = 0")
    rows = c.fetchall()
    updated = 0
    for mail_id, props_str in rows:
        try:
            data = json.loads(props_str)
            if isinstance(data, str):
                data = json.loads(data)
        except Exception:
            data = []

        new_props = []
        needs_update = False
        for p in data:
            if isinstance(p, dict):
                needs_update = True
                gp = p.get('gp') or p.get('gold')
                dia = p.get('payYuanbao') or p.get('freeYuanbao') or p.get('diamonds')
                if gp and int(gp) > 0:
                    new_props.append([200001, int(gp)])
                if dia and int(dia) > 0:
                    new_props.append([201001, int(dia)])
                item = p.get('item') or p.get('item_id') or p.get('prop_id')
                if item and int(item) > 0:
                    new_props.append([int(item), int(p.get('count', 1))])
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                new_props.append([int(p[0]), int(p[1])])

        if needs_update or props_str.startswith('[{\\"'):
            c.execute("UPDATE mails SET props = ? WHERE id = ?", (json.dumps(new_props), mail_id))
            updated += 1

    conn.commit()
    conn.close()
    print(f"Normalized {updated} mails in {db_path}")

# --------------------------------------------------------------------------
# 2. Patch server_patch.py with MailServer robust detail & award
# --------------------------------------------------------------------------
sp_paths = [
    os.path.join(BASE_DIR, "local_update", "hot", "server_patch.py"),
    os.path.join(BASE_DIR, "runtime", "app", "local_update", "hot", "server_patch.py"),
    os.path.join(BASE_DIR, "ROS_Redemption_Server_Package", "local_update", "hot", "server_patch.py")
]

mail_patch_code = '''
# ----------------------------------------------------------
# 9. MailServer Robust Detail & Award Hook (Fix KeyError: 0)
# ----------------------------------------------------------
try:
    from backend_server import chat
    import json

    def _redemption_norm_mail_props(props):
        norm = []
        if isinstance(props, str):
            try:
                props = json.loads(props)
                if isinstance(props, str):
                    props = json.loads(props)
            except Exception:
                props = []
        for p in (props or []):
            if isinstance(p, dict):
                gp = p.get('gp') or p.get('gold')
                dia = p.get('payYuanbao') or p.get('freeYuanbao') or p.get('diamonds')
                if gp and int(gp) > 0:
                    norm.append([200001, int(gp)])
                if dia and int(dia) > 0:
                    norm.append([201001, int(dia)])
                item = p.get('item') or p.get('item_id') or p.get('prop_id')
                if item and int(item) > 0:
                    norm.append([int(item), int(p.get('count', 1))])
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                norm.append([int(p[0]), int(p[1])])
        return norm

    def redemption_mail_detail(self, args):
        mail_id = chat._int(args[0], -1) if args else -1
        row = self.db.mail_row(self.account.gid, mail_id)
        if not row:
            return [{'method': 'onLoadMailDetailFailed', 'args': [mail_id]}]
        self.db.read_mail(self.account.gid, mail_id)
        props = _redemption_norm_mail_props(row['props'])
        extra = {'props': props, 'gid': int(row['sender_gid'])}
        return [{'method': 'onLoadMailDetail', 'args': [mail_id, row['content'], extra]}]

    def redemption_mail_award(self, args):
        mail_id = chat._int(args[0], -1) if args else -1
        with self.db.transaction() as conn:
            raw_props = self.db.take_mail_props_in(conn, self.account.gid, mail_id)
        props = _redemption_norm_mail_props(raw_props)
        if not props:
            return {'ok': False, 'callbacks': [], 'tip': 'Nothing to take from this mail.'}

        taken = []
        with self.account.edit() as data:
            for prop in props:
                item = prop[0]
                count = prop[1]
                days = prop[2] if len(prop) > 2 else 0
                if item in chat.MAIL_CURRENCY_PROPS:
                    self.account.grant(data, chat.MAIL_CURRENCY_PROPS[item], count, 'mail:%s' % mail_id)
                else:
                    self.account.add_item(data, item, count, days)
                taken.append([item, count])

        print('[server] ROS Redemption: Awarded mail %s to player: %r' % (mail_id, taken), flush=True)
        return [
            {'method': 'onGetAwardFromMail', 'args': [taken]},
            self.update()
        ]

    chat.MailServer.detail = redemption_mail_detail
    chat.MailServer.award = redemption_mail_award
    print('[server] ROS Redemption: MailServer robust detail & award patch active!', flush=True)
except Exception as e:
    print('[server] Error patching MailServer:', e, flush=True)
'''

for sp_path in sp_paths:
    if os.path.exists(sp_path):
        with open(sp_path, "r", encoding="utf-8") as f:
            content = f.read()
        if "redemption_mail_award" not in content:
            content = content.rstrip() + "\n" + mail_patch_code
            with open(sp_path, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"Patched server_patch.py at {sp_path}")
        else:
            print(f"server_patch.py already contains mail patch at {sp_path}")

# --------------------------------------------------------------------------
# 3. Guard generateArgsForUIItemDisplay in clean_remote_lobby.py
# --------------------------------------------------------------------------
crl_path = r"c:\Users\seanj\dev\clean_remote_lobby.py"
if os.path.exists(crl_path):
    with open(crl_path, "r", encoding="utf-8") as f:
        crl = f.read()

    # If empty ids returned, avoid KeyError: 0
    old_target = "if not plain and not counted:\n            return {'itemIDs': []}"
    new_target = "if not plain and not counted:\n            return {'itemIDs': [(200001, 1)]}"
    if old_target in crl:
        crl = crl.replace(old_target, new_target)
        with open(crl_path, "w", encoding="utf-8") as f:
            f.write(crl)
        print("Guarded generateArgsForUIItemDisplay in clean_remote_lobby.py")

print("=== MAIL CLAIM FIX COMPLETE ===")

