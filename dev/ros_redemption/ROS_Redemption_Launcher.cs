using System;
using System.IO;
using System.Net.Sockets;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Diagnostics;
using System.Drawing;
using System.Windows.Forms;

namespace RosRedemptionLauncher {
    public class WinSqlite {
        [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_open16", CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_open16([MarshalAs(UnmanagedType.LPWStr)] string filename, out IntPtr db);

        [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_close", CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_close(IntPtr db);

        [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
        public delegate int ExecCallback(IntPtr arg, int colCount, IntPtr colValues, IntPtr colNames);

        [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_exec", CallingConvention = CallingConvention.Cdecl)]
        public static extern int sqlite3_exec(IntPtr db, [MarshalAs(UnmanagedType.LPStr)] string sql, ExecCallback callback, IntPtr arg, out IntPtr errMsg);

        public static List<Dictionary<string, string>> Query(string dbPath, string sql) {
            var rows = new List<Dictionary<string, string>>();
            IntPtr db;
            if (sqlite3_open16(dbPath, out db) != 0) return rows;

            IntPtr errMsg;
            ExecCallback cb = (arg, count, values, names) => {
                var row = new Dictionary<string, string>();
                for (int i = 0; i < count; i++) {
                    IntPtr valPtr = Marshal.ReadIntPtr(values, i * IntPtr.Size);
                    IntPtr namePtr = Marshal.ReadIntPtr(names, i * IntPtr.Size);
                    string colName = Marshal.PtrToStringAnsi(namePtr);
                    string colVal = valPtr == IntPtr.Zero ? "" : Marshal.PtrToStringAnsi(valPtr);
                    row[colName] = colVal;
                }
                rows.Add(row);
                return 0;
            };

            sqlite3_exec(db, sql, cb, IntPtr.Zero, out errMsg);
            sqlite3_close(db);
            return rows;
        }

        public static int Exec(string dbPath, string sql) {
            IntPtr db;
            if (sqlite3_open16(dbPath, out db) != 0) return -1;
            IntPtr errMsg;
            int rc = sqlite3_exec(db, sql, null, IntPtr.Zero, out errMsg);
            sqlite3_close(db);
            return rc;
        }
    }

    public class AccountItem {
        public long Id { get; set; }
        public string Username { get; set; }
        public string Nickname { get; set; }
        public long Gid { get; set; }
        public long Diamonds { get; set; }
        public long Gold { get; set; }

        public override string ToString() {
            return string.Format("{0} (Character: {1})", Username, string.IsNullOrEmpty(Nickname) ? "No Character" : Nickname);
        }
    }

    public class LauncherForm : Form {
        public static string BaseDir = @"C:\DieHardROS";
        public static string AccountsDb = @"C:\DieHardROS\local_update\server_data\accounts.db";
        public static string PythonExe = @"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\python\python.exe";
        public static string AppDir = @"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app";
        public static string RtKey = "f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf";

        private ComboBox cmbAccounts;
        private TextBox txtEditNick;
        private Label lblSelectedDia;
        private Label lblSelectedGold;
        private Label lblServerStatus;
        private Button btnLaunch;
        private TextBox txtNewUser;
        private TextBox txtNewNick;
        private TextBox txtNewDia;
        private TextBox txtNewGold;
        private Timer statusTimer;

        public LauncherForm() {
            InitializeUI();
            LoadAccounts();
            CheckServerStatus();

            statusTimer = new Timer();
            statusTimer.Interval = 2500;
            statusTimer.Tick += (s, e) => CheckServerStatus();
            statusTimer.Start();
        }

        private void InitializeUI() {
            this.Text = "ROS REDEMPTION - MASTER LAUNCHER & SERVER SUITE";
            this.Size = new Size(880, 680);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.FixedDialog;
            this.MaximizeBox = false;
            this.BackColor = Color.FromArgb(12, 16, 24);
            this.ForeColor = Color.White;
            this.Font = new Font("Segoe UI", 9.5f, FontStyle.Regular);

            string icoPath = Path.Combine(BaseDir, "ros_redemption.ico");
            if (File.Exists(icoPath)) {
                try { this.Icon = new Icon(icoPath); } catch {}
            }

            // HEADER
            Panel header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 90;
            header.BackColor = Color.FromArgb(18, 24, 38);
            header.Paint += (s, e) => {
                using (Pen p = new Pen(Color.FromArgb(40, 52, 75), 1)) {
                    e.Graphics.DrawLine(p, 0, header.Height - 1, header.Width, header.Height - 1);
                }
            };

            Label lblTitle = new Label();
            lblTitle.Text = "ROS REDEMPTION";
            lblTitle.Font = new Font("Segoe UI", 24f, FontStyle.Bold);
            lblTitle.ForeColor = Color.FromArgb(235, 47, 60);
            lblTitle.Location = new Point(24, 10);
            lblTitle.AutoSize = true;
            header.Controls.Add(lblTitle);

            Label lblSub = new Label();
            lblSub.Text = "TACTICAL BATTLE ROYALE • DEDICATED PRIVATE SERVER & CLIENT SUITE";
            lblSub.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            lblSub.ForeColor = Color.FromArgb(131, 149, 167);
            lblSub.Location = new Point(27, 56);
            lblSub.AutoSize = true;
            header.Controls.Add(lblSub);

            lblServerStatus = new Label();
            lblServerStatus.Text = "SERVER: CHECKING...";
            lblServerStatus.Font = new Font("Segoe UI", 9.5f, FontStyle.Bold);
            lblServerStatus.ForeColor = Color.FromArgb(255, 165, 2);
            lblServerStatus.Location = new Point(580, 32);
            lblServerStatus.Size = new Size(260, 25);
            lblServerStatus.TextAlign = ContentAlignment.MiddleRight;
            header.Controls.Add(lblServerStatus);

            this.Controls.Add(header);

            // LEFT PANEL (ACTIVE CHARACTER & PLAY)
            Panel pnlLeft = new Panel();
            pnlLeft.Location = new Point(24, 110);
            pnlLeft.Size = new Size(410, 510);
            pnlLeft.BackColor = Color.FromArgb(19, 26, 40);
            pnlLeft.Paint += (s, e) => {
                using (Pen p = new Pen(Color.FromArgb(38, 50, 72), 1)) {
                    e.Graphics.DrawRectangle(p, 0, 0, pnlLeft.Width - 1, pnlLeft.Height - 1);
                }
            };
            this.Controls.Add(pnlLeft);

            Label lblPlayTitle = new Label();
            lblPlayTitle.Text = "ACTIVE CHARACTER PROFILE";
            lblPlayTitle.Font = new Font("Segoe UI", 12f, FontStyle.Bold);
            lblPlayTitle.ForeColor = Color.White;
            lblPlayTitle.Location = new Point(18, 14);
            lblPlayTitle.AutoSize = true;
            pnlLeft.Controls.Add(lblPlayTitle);

            Label lblChoose = new Label();
            lblChoose.Text = "Select Account:";
            lblChoose.ForeColor = Color.FromArgb(164, 176, 190);
            lblChoose.Location = new Point(18, 45);
            lblChoose.AutoSize = true;
            pnlLeft.Controls.Add(lblChoose);

            cmbAccounts = new ComboBox();
            cmbAccounts.DropDownStyle = ComboBoxStyle.DropDownList;
            cmbAccounts.Location = new Point(18, 68);
            cmbAccounts.Size = new Size(370, 28);
            cmbAccounts.BackColor = Color.FromArgb(10, 14, 22);
            cmbAccounts.ForeColor = Color.White;
            cmbAccounts.SelectedIndexChanged += CmbAccounts_SelectedIndexChanged;
            pnlLeft.Controls.Add(cmbAccounts);

            // STATS & ACTION BOX
            Panel pnlDetails = new Panel();
            pnlDetails.Location = new Point(18, 108);
            pnlDetails.Size = new Size(370, 195);
            pnlDetails.BackColor = Color.FromArgb(14, 19, 30);
            pnlDetails.Paint += (s, e) => {
                using (Pen p = new Pen(Color.FromArgb(45, 60, 85), 1)) {
                    e.Graphics.DrawRectangle(p, 0, 0, pnlDetails.Width - 1, pnlDetails.Height - 1);
                }
            };
            pnlLeft.Controls.Add(pnlDetails);

            Label lblNickTag = new Label();
            lblNickTag.Text = "Change Nickname:";
            lblNickTag.Location = new Point(12, 10);
            lblNickTag.ForeColor = Color.FromArgb(131, 149, 167);
            lblNickTag.AutoSize = true;
            pnlDetails.Controls.Add(lblNickTag);

            txtEditNick = new TextBox();
            txtEditNick.Location = new Point(12, 30);
            txtEditNick.Size = new Size(230, 26);
            txtEditNick.BackColor = Color.FromArgb(10, 14, 22);
            txtEditNick.ForeColor = Color.FromArgb(0, 210, 211);
            pnlDetails.Controls.Add(txtEditNick);

            Button btnSaveNick = new Button();
            btnSaveNick.Text = "Save";
            btnSaveNick.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            btnSaveNick.BackColor = Color.FromArgb(0, 210, 211);
            btnSaveNick.ForeColor = Color.Black;
            btnSaveNick.FlatStyle = FlatStyle.Flat;
            btnSaveNick.Location = new Point(248, 29);
            btnSaveNick.Size = new Size(110, 28);
            btnSaveNick.Click += BtnSaveNick_Click;
            pnlDetails.Controls.Add(btnSaveNick);

            lblSelectedDia = new Label();
            lblSelectedDia.Text = "💎 0 Diamonds";
            lblSelectedDia.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            lblSelectedDia.ForeColor = Color.FromArgb(255, 165, 2);
            lblSelectedDia.Location = new Point(12, 68);
            lblSelectedDia.Size = new Size(170, 25);
            pnlDetails.Controls.Add(lblSelectedDia);

            lblSelectedGold = new Label();
            lblSelectedGold.Text = "🪙 0 Gold";
            lblSelectedGold.Font = new Font("Segoe UI", 10f, FontStyle.Bold);
            lblSelectedGold.ForeColor = Color.FromArgb(241, 196, 15);
            lblSelectedGold.Location = new Point(190, 68);
            lblSelectedGold.Size = new Size(170, 25);
            pnlDetails.Controls.Add(lblSelectedGold);

            Button btnQuickTopup = new Button();
            btnQuickTopup.Text = "💎 +50,000 Diamonds & 100,000 Gold";
            btnQuickTopup.Font = new Font("Segoe UI", 9f, FontStyle.Bold);
            btnQuickTopup.BackColor = Color.FromArgb(40, 60, 20);
            btnQuickTopup.ForeColor = Color.FromArgb(46, 213, 115);
            btnQuickTopup.FlatStyle = FlatStyle.Flat;
            btnQuickTopup.FlatAppearance.BorderColor = Color.FromArgb(60, 100, 30);
            btnQuickTopup.Location = new Point(12, 105);
            btnQuickTopup.Size = new Size(346, 32);
            btnQuickTopup.Click += BtnQuickTopup_Click;
            pnlDetails.Controls.Add(btnQuickTopup);

            Button btnSetFlag = new Button();
            btnSetFlag.Text = "🇵🇭 Set Philippine Flag (PH)";
            btnSetFlag.Font = new Font("Segoe UI", 9f, FontStyle.Bold);
            btnSetFlag.BackColor = Color.FromArgb(30, 45, 70);
            btnSetFlag.ForeColor = Color.White;
            btnSetFlag.FlatStyle = FlatStyle.Flat;
            btnSetFlag.FlatAppearance.BorderColor = Color.FromArgb(50, 75, 115);
            btnSetFlag.Location = new Point(12, 147);
            btnSetFlag.Size = new Size(346, 32);
            btnSetFlag.Click += BtnSetFlag_Click;
            pnlDetails.Controls.Add(btnSetFlag);

            // PLAY BUTTON
            btnLaunch = new Button();
            btnLaunch.Text = "⚡ PLAY ROS REDEMPTION";
            btnLaunch.Font = new Font("Segoe UI", 14f, FontStyle.Bold);
            btnLaunch.BackColor = Color.FromArgb(235, 47, 60);
            btnLaunch.ForeColor = Color.White;
            btnLaunch.FlatStyle = FlatStyle.Flat;
            btnLaunch.FlatAppearance.BorderSize = 0;
            btnLaunch.Location = new Point(18, 318);
            btnLaunch.Size = new Size(370, 58);
            btnLaunch.Cursor = Cursors.Hand;
            btnLaunch.Click += BtnLaunch_Click;
            pnlLeft.Controls.Add(btnLaunch);

            Button btnWeb = new Button();
            btnWeb.Text = "🌐 Web Controller Panel (Port 8888)";
            btnWeb.Font = new Font("Segoe UI", 9.5f, FontStyle.Bold);
            btnWeb.BackColor = Color.FromArgb(26, 36, 56);
            btnWeb.ForeColor = Color.FromArgb(0, 210, 211);
            btnWeb.FlatStyle = FlatStyle.Flat;
            btnWeb.FlatAppearance.BorderColor = Color.FromArgb(45, 65, 95);
            btnWeb.Location = new Point(18, 388);
            btnWeb.Size = new Size(370, 36);
            btnWeb.Cursor = Cursors.Hand;
            btnWeb.Click += (s, e) => Process.Start("http://127.0.0.1:8888");
            pnlLeft.Controls.Add(btnWeb);

            Button btnServerToggle = new Button();
            btnServerToggle.Text = "⚙ Start Dedicated Server Only";
            btnServerToggle.Font = new Font("Segoe UI", 9f, FontStyle.Regular);
            btnServerToggle.BackColor = Color.FromArgb(20, 28, 42);
            btnServerToggle.ForeColor = Color.FromArgb(164, 176, 190);
            btnServerToggle.FlatStyle = FlatStyle.Flat;
            btnServerToggle.FlatAppearance.BorderColor = Color.FromArgb(35, 48, 70);
            btnServerToggle.Location = new Point(18, 432);
            btnServerToggle.Size = new Size(370, 32);
            btnServerToggle.Click += BtnServerToggle_Click;
            pnlLeft.Controls.Add(btnServerToggle);

            Button btnRefresh = new Button();
            btnRefresh.Text = "🔄 Refresh Account List";
            btnRefresh.Font = new Font("Segoe UI", 8.5f, FontStyle.Regular);
            btnRefresh.BackColor = Color.Transparent;
            btnRefresh.ForeColor = Color.FromArgb(131, 149, 167);
            btnRefresh.FlatStyle = FlatStyle.Flat;
            btnRefresh.FlatAppearance.BorderSize = 0;
            btnRefresh.Location = new Point(18, 472);
            btnRefresh.Size = new Size(370, 26);
            btnRefresh.Click += (s, e) => LoadAccounts();
            pnlLeft.Controls.Add(btnRefresh);

            // RIGHT PANEL (CREATE NEW ACCOUNT & MAIL)
            Panel pnlRight = new Panel();
            pnlRight.Location = new Point(450, 110);
            pnlRight.Size = new Size(400, 510);
            pnlRight.BackColor = Color.FromArgb(19, 26, 40);
            pnlRight.Paint += (s, e) => {
                using (Pen p = new Pen(Color.FromArgb(38, 50, 72), 1)) {
                    e.Graphics.DrawRectangle(p, 0, 0, pnlRight.Width - 1, pnlRight.Height - 1);
                }
            };
            this.Controls.Add(pnlRight);

            Label lblCreateTitle = new Label();
            lblCreateTitle.Text = "CREATE NEW ACCOUNT";
            lblCreateTitle.Font = new Font("Segoe UI", 12f, FontStyle.Bold);
            lblCreateTitle.ForeColor = Color.FromArgb(46, 213, 115);
            lblCreateTitle.Location = new Point(18, 14);
            lblCreateTitle.AutoSize = true;
            pnlRight.Controls.Add(lblCreateTitle);

            Label lblUserTag = new Label();
            lblUserTag.Text = "Account Username (Login UID):";
            lblUserTag.Location = new Point(18, 45);
            lblUserTag.ForeColor = Color.FromArgb(164, 176, 190);
            lblUserTag.AutoSize = true;
            pnlRight.Controls.Add(lblUserTag);

            txtNewUser = new TextBox();
            txtNewUser.Location = new Point(18, 68);
            txtNewUser.Size = new Size(360, 26);
            txtNewUser.BackColor = Color.FromArgb(10, 14, 22);
            txtNewUser.ForeColor = Color.White;
            txtNewUser.Text = "Player" + new Random().Next(100, 999);
            pnlRight.Controls.Add(txtNewUser);

            Label lblNickCreateTag = new Label();
            lblNickCreateTag.Text = "Character In-Game Name:";
            lblNickCreateTag.Location = new Point(18, 105);
            lblNickCreateTag.ForeColor = Color.FromArgb(164, 176, 190);
            lblNickCreateTag.AutoSize = true;
            pnlRight.Controls.Add(lblNickCreateTag);

            txtNewNick = new TextBox();
            txtNewNick.Location = new Point(18, 128);
            txtNewNick.Size = new Size(360, 26);
            txtNewNick.BackColor = Color.FromArgb(10, 14, 22);
            txtNewNick.ForeColor = Color.White;
            txtNewNick.Text = "Redemption_Pro";
            pnlRight.Controls.Add(txtNewNick);

            Label lblDiaCreateTag = new Label();
            lblDiaCreateTag.Text = "Starting Diamonds:";
            lblDiaCreateTag.Location = new Point(18, 165);
            lblDiaCreateTag.ForeColor = Color.FromArgb(164, 176, 190);
            lblDiaCreateTag.AutoSize = true;
            pnlRight.Controls.Add(lblDiaCreateTag);

            txtNewDia = new TextBox();
            txtNewDia.Location = new Point(18, 188);
            txtNewDia.Size = new Size(360, 26);
            txtNewDia.BackColor = Color.FromArgb(10, 14, 22);
            txtNewDia.ForeColor = Color.FromArgb(255, 165, 2);
            txtNewDia.Text = "100000";
            pnlRight.Controls.Add(txtNewDia);

            Label lblGoldCreateTag = new Label();
            lblGoldCreateTag.Text = "Starting Gold:";
            lblGoldCreateTag.Location = new Point(18, 225);
            lblGoldCreateTag.ForeColor = Color.FromArgb(164, 176, 190);
            lblGoldCreateTag.AutoSize = true;
            pnlRight.Controls.Add(lblGoldCreateTag);

            txtNewGold = new TextBox();
            txtNewGold.Location = new Point(18, 248);
            txtNewGold.Size = new Size(360, 26);
            txtNewGold.BackColor = Color.FromArgb(10, 14, 22);
            txtNewGold.ForeColor = Color.FromArgb(241, 196, 15);
            txtNewGold.Text = "500000";
            pnlRight.Controls.Add(txtNewGold);

            Button btnCreate = new Button();
            btnCreate.Text = "+ CREATE ACCOUNT & CHARACTER";
            btnCreate.Font = new Font("Segoe UI", 11f, FontStyle.Bold);
            btnCreate.BackColor = Color.FromArgb(46, 213, 115);
            btnCreate.ForeColor = Color.Black;
            btnCreate.FlatStyle = FlatStyle.Flat;
            btnCreate.FlatAppearance.BorderSize = 0;
            btnCreate.Location = new Point(18, 295);
            btnCreate.Size = new Size(360, 48);
            btnCreate.Cursor = Cursors.Hand;
            btnCreate.Click += BtnCreate_Click;
            pnlRight.Controls.Add(btnCreate);

            // SEND MAIL PANEL
            Panel pnlMailBox = new Panel();
            pnlMailBox.Location = new Point(18, 360);
            pnlMailBox.Size = new Size(360, 135);
            pnlMailBox.BackColor = Color.FromArgb(14, 19, 30);
            pnlMailBox.Paint += (s, e) => {
                using (Pen p = new Pen(Color.FromArgb(45, 60, 85), 1)) {
                    e.Graphics.DrawRectangle(p, 0, 0, pnlMailBox.Width - 1, pnlMailBox.Height - 1);
                }
            };
            pnlRight.Controls.Add(pnlMailBox);

            Label lblMailH = new Label();
            lblMailH.Text = "✉ IN-GAME REWARD MAIL";
            lblMailH.Font = new Font("Segoe UI", 9.5f, FontStyle.Bold);
            lblMailH.ForeColor = Color.FromArgb(0, 210, 211);
            lblMailH.Location = new Point(12, 10);
            lblMailH.AutoSize = true;
            pnlMailBox.Controls.Add(lblMailH);

            Button btnSendAllMail = new Button();
            btnSendAllMail.Text = "Send 50k Diamonds Mail (To All Players)";
            btnSendAllMail.Font = new Font("Segoe UI", 9f, FontStyle.Bold);
            btnSendAllMail.BackColor = Color.FromArgb(30, 45, 65);
            btnSendAllMail.ForeColor = Color.FromArgb(0, 210, 211);
            btnSendAllMail.FlatStyle = FlatStyle.Flat;
            btnSendAllMail.FlatAppearance.BorderColor = Color.FromArgb(45, 75, 110);
            btnSendAllMail.Location = new Point(12, 38);
            btnSendAllMail.Size = new Size(336, 36);
            btnSendAllMail.Click += (s, e) => SendServerMail(0, "ROS Redemption Grand Gift", "Welcome to ROS Redemption! Here are 50,000 Diamonds & 100,000 Gold.", 50000, 100000);
            pnlMailBox.Controls.Add(btnSendAllMail);

            Label lblInfo = new Label();
            lblInfo.Text = "💡 Pindutin ang START sa game para pumasok sa Ghillie Island (Map 700) kasama ang 40 bots!";
            lblInfo.ForeColor = Color.FromArgb(131, 149, 167);
            lblInfo.Font = new Font("Segoe UI", 8.5f, FontStyle.Italic);
            lblInfo.Location = new Point(12, 85);
            lblInfo.Size = new Size(336, 40);
            pnlMailBox.Controls.Add(lblInfo);
        }

        private void CheckServerStatus() {
            try {
                using (var tcp = new TcpClient()) {
                    var ar = tcp.BeginConnect("127.0.0.1", 19000, null, null);
                    if (ar.AsyncWaitHandle.WaitOne(250)) {
                        tcp.EndConnect(ar);
                        lblServerStatus.Text = "● SERVER: ONLINE (Port 19000)";
                        lblServerStatus.ForeColor = Color.FromArgb(46, 213, 115);
                        return;
                    }
                }
            } catch {}
            lblServerStatus.Text = "○ SERVER: STANDBY";
            lblServerStatus.ForeColor = Color.FromArgb(255, 165, 2);
        }

        private void LoadAccounts() {
            cmbAccounts.Items.Clear();
            if (!File.Exists(AccountsDb)) return;

            string sql = "SELECT a.id, a.username, c.gid, c.nickname, IFNULL(w.freeYuanbao, 0) as freeDia, IFNULL(w.payYuanbao, 0) as payDia, IFNULL(w.gp, 0) as gp " +
                         "FROM accounts a " +
                         "LEFT JOIN characters c ON a.id = c.account_id " +
                         "LEFT JOIN wallets w ON c.gid = w.gid " +
                         "ORDER BY a.id ASC;";

            var rows = WinSqlite.Query(AccountsDb, sql);
            foreach (var r in rows) {
                long accId = 0, gid = 0, freeDia = 0, payDia = 0, gold = 0;
                long.TryParse(r.ContainsKey("id") ? r["id"] : "0", out accId);
                long.TryParse(r.ContainsKey("gid") ? r["gid"] : "0", out gid);
                long.TryParse(r.ContainsKey("freeDia") ? r["freeDia"] : "0", out freeDia);
                long.TryParse(r.ContainsKey("payDia") ? r["payDia"] : "0", out payDia);
                long.TryParse(r.ContainsKey("gp") ? r["gp"] : "0", out gold);

                var item = new AccountItem {
                    Id = accId,
                    Username = r.ContainsKey("username") ? r["username"] : "Unknown",
                    Nickname = r.ContainsKey("nickname") ? r["nickname"] : "",
                    Gid = gid,
                    Diamonds = Math.Max(freeDia, payDia),
                    Gold = gold
                };
                cmbAccounts.Items.Add(item);
            }

            if (cmbAccounts.Items.Count > 0) {
                // Select sean or Admin_Redemption by default if available
                int targetIdx = 0;
                for (int i = 0; i < cmbAccounts.Items.Count; i++) {
                    var it = cmbAccounts.Items[i] as AccountItem;
                    if (it != null && (it.Nickname == "sean" || it.Username == "Admin_Redemption")) {
                        targetIdx = i;
                        break;
                    }
                }
                cmbAccounts.SelectedIndex = targetIdx;
            }
        }

        private void CmbAccounts_SelectedIndexChanged(object sender, EventArgs e) {
            var item = cmbAccounts.SelectedItem as AccountItem;
            if (item != null) {
                txtEditNick.Text = item.Nickname;
                lblSelectedDia.Text = string.Format("💎 {0:N0} Diamonds", item.Diamonds);
                lblSelectedGold.Text = string.Format("🪙 {0:N0} Gold", item.Gold);
            }
        }

        private void BtnQuickTopup_Click(object sender, EventArgs e) {
            var item = cmbAccounts.SelectedItem as AccountItem;
            if (item == null || item.Gid == 0) {
                MessageBox.Show("Please select an account with a character first!", "Warning", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            string sql = string.Format(
                "UPDATE wallets SET freeYuanbao = freeYuanbao + 50000, payYuanbao = payYuanbao + 50000, gp = gp + 100000 WHERE gid = {0};",
                item.Gid);
            WinSqlite.Exec(AccountsDb, sql);

            // Also send a mail so in-game notification triggers
            SendServerMail(item.Gid, "Top-Up Claim", "You have received 50,000 Diamonds & 100,000 Gold!", 50000, 100000);

            MessageBox.Show("SUCCESS!\n\nAdded 50,000 Diamonds & 100,000 Gold to character: " + item.Nickname, "Top-Up Complete", MessageBoxButtons.OK, MessageBoxIcon.Information);
            int idx = cmbAccounts.SelectedIndex;
            LoadAccounts();
            if (idx >= 0 && idx < cmbAccounts.Items.Count) cmbAccounts.SelectedIndex = idx;
        }

        private void SendServerMail(long targetGid, string title, string content, long dia, long gold) {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            long deadline = now + (30 * 86400);
            string propsJson = string.Format("[{{\\\"type\\\":\\\"currency\\\",\\\"payYuanbao\\\":{0},\\\"freeYuanbao\\\":{0},\\\"gp\\\":{1}}}]", dia, gold);

            if (targetGid == 0) {
                var chars = WinSqlite.Query(AccountsDb, "SELECT gid FROM characters;");
                foreach (var c in chars) {
                    long gid = 0;
                    long.TryParse(c["gid"], out gid);
                    if (gid > 0) {
                        string sql = string.Format(
                            "INSERT INTO mails (gid, type, title, content, sender, sender_gid, props, created, deadline, unread, deleted) " +
                            "VALUES ({0}, 1, '{1}', '{2}', 'ROS Redemption HQ', 0, '{3}', {4}, {5}, 1, 0);",
                            gid, title, content, propsJson, now, deadline);
                        WinSqlite.Exec(AccountsDb, sql);
                    }
                }
                MessageBox.Show("SUCCESS!\n\nReward mail sent to all active characters!", "Mail Broadcast Sent", MessageBoxButtons.OK, MessageBoxIcon.Information);
            } else {
                string sql = string.Format(
                    "INSERT INTO mails (gid, type, title, content, sender, sender_gid, props, created, deadline, unread, deleted) " +
                    "VALUES ({0}, 1, '{1}', '{2}', 'ROS Redemption HQ', 0, '{3}', {4}, {5}, 1, 0);",
                    targetGid, title, content, propsJson, now, deadline);
                WinSqlite.Exec(AccountsDb, sql);
            }
        }

        private void BtnSaveNick_Click(object sender, EventArgs e) {
            var item = cmbAccounts.SelectedItem as AccountItem;
            if (item == null || item.Gid == 0) {
                MessageBox.Show("Please select an account with a character first!", "Warning", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            string newNick = txtEditNick.Text.Trim();
            if (string.IsNullOrEmpty(newNick)) {
                MessageBox.Show("Please enter a new nickname!", "Warning", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            string clean = newNick.Replace("'", "''");
            string sql = string.Format("UPDATE characters SET nickname = '{0}' WHERE gid = {1};", clean, item.Gid);
            WinSqlite.Exec(AccountsDb, sql);

            MessageBox.Show("SUCCESS!\n\nNickname changed to: " + newNick, "Name Changed", MessageBoxButtons.OK, MessageBoxIcon.Information);
            int idx = cmbAccounts.SelectedIndex;
            LoadAccounts();
            if (idx >= 0 && idx < cmbAccounts.Items.Count) cmbAccounts.SelectedIndex = idx;
        }

        private void BtnSetFlag_Click(object sender, EventArgs e) {
            var item = cmbAccounts.SelectedItem as AccountItem;
            if (item == null || item.Gid == 0) {
                MessageBox.Show("Please select an account with a character first!", "Warning", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            string sql = string.Format("UPDATE characters SET lobby = '{{\"country\":\"PH\",\"nation\":\"PH\",\"flag\":\"PH\"}}' WHERE gid = {0};", item.Gid);
            WinSqlite.Exec(AccountsDb, sql);

            MessageBox.Show("SUCCESS!\n\nPhilippine Flag (PH 🇵🇭) set on character " + item.Nickname + "!", "Flag Updated", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        private void BtnCreate_Click(object sender, EventArgs e) {
            string user = txtNewUser.Text.Trim();
            string nick = txtNewNick.Text.Trim();
            if (string.IsNullOrEmpty(user)) {
                MessageBox.Show("Please enter a username!", "Warning", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            if (string.IsNullOrEmpty(nick)) nick = user;

            long dia = 100000, gold = 500000;
            long.TryParse(txtNewDia.Text.Trim(), out dia);
            long.TryParse(txtNewGold.Text.Trim(), out gold);

            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            string cleanUser = user.Replace("'", "''");
            string cleanNick = nick.Replace("'", "''");

            string accSql = string.Format("INSERT OR IGNORE INTO accounts (username, created, last_login, last_server, banned, note) VALUES ('{0}', {1}, {1}, 10501, 0, 'ROS Redemption');", cleanUser, now);
            WinSqlite.Exec(AccountsDb, accSql);

            var accRows = WinSqlite.Query(AccountsDb, "SELECT id FROM accounts WHERE username='" + cleanUser + "';");
            if (accRows.Count == 0) {
                MessageBox.Show("Account username already exists or database locked!", "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return;
            }
            long accId = long.Parse(accRows[0]["id"]);
            long gid = 10000000 + accId;

            string charSql = string.Format(
                "INSERT OR IGNORE INTO characters (gid, account_id, server_id, nickname, character_type, created, base_level, level, lobby, created_at, last_login) " +
                "VALUES ({0}, {1}, 10501, '{2}', 10002, 1, 1, 1, '{{\"country\":\"PH\",\"nation\":\"PH\",\"flag\":\"PH\"}}', {3}, {3});",
                gid, accId, cleanNick, now);
            WinSqlite.Exec(AccountsDb, charSql);

            string wallSql = string.Format(
                "INSERT OR REPLACE INTO wallets (gid, freeYuanbao, payYuanbao, gp) VALUES ({0}, {1}, {1}, {2});",
                gid, dia, gold);
            WinSqlite.Exec(AccountsDb, wallSql);

            MessageBox.Show("SUCCESS!\n\nAccount '" + user + "' with character '" + nick + "' created with Philippine Flag & " + dia.ToString("N0") + " Diamonds!", "Account Created", MessageBoxButtons.OK, MessageBoxIcon.Information);

            LoadAccounts();

            for (int i = 0; i < cmbAccounts.Items.Count; i++) {
                var it = cmbAccounts.Items[i] as AccountItem;
                if (it != null && it.Username == user) {
                    cmbAccounts.SelectedIndex = i;
                    break;
                }
            }

            txtNewUser.Text = "Player" + new Random().Next(100, 999);
            txtNewNick.Text = "Redemption_" + new Random().Next(10, 99);
        }

        private void BtnServerToggle_Click(object sender, EventArgs e) {
            try {
                var srvPsi = new ProcessStartInfo();
                srvPsi.FileName = PythonExe;
                srvPsi.Arguments = "start_game.pyc --server-only";
                srvPsi.WorkingDirectory = AppDir;
                srvPsi.EnvironmentVariables["ROS_GAME_DIR"] = BaseDir;
                srvPsi.EnvironmentVariables["ROS_RT_KEY"] = RtKey;
                srvPsi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                srvPsi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                srvPsi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                srvPsi.UseShellExecute = false;
                srvPsi.CreateNoWindow = false;
                Process.Start(srvPsi);
                MessageBox.Show("Dedicated server process started! Listening on Port 19000 & Battle 19100.", "Server Started", MessageBoxButtons.OK, MessageBoxIcon.Information);
            } catch (Exception ex) {
                MessageBox.Show("Failed to start server: " + ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        private void BtnLaunch_Click(object sender, EventArgs e) {
            var item = cmbAccounts.SelectedItem as AccountItem;
            string accountName = (item != null) ? item.Username : "Admin_Redemption";

            btnLaunch.Text = "STARTING...";
            btnLaunch.Enabled = false;

            try {
                // 1. Ensure Branding Injector runs
                string brandingExe = Path.Combine(BaseDir, "RosRedemptionBranding.exe");
                if (File.Exists(brandingExe)) {
                    var brandPsi = new ProcessStartInfo();
                    brandPsi.FileName = brandingExe;
                    brandPsi.WorkingDirectory = BaseDir;
                    brandPsi.UseShellExecute = false;
                    brandPsi.CreateNoWindow = true;
                    Process.Start(brandPsi);
                }

                // 2. Check if Server is running
                bool serverRunning = false;
                try {
                    using (var tcp = new TcpClient()) {
                        var ar = tcp.BeginConnect("127.0.0.1", 19000, null, null);
                        if (ar.AsyncWaitHandle.WaitOne(300)) {
                            tcp.EndConnect(ar);
                            serverRunning = true;
                        }
                    }
                } catch {}

                if (!serverRunning) {
                    // Start All-in-One Direct mode
                    var directPsi = new ProcessStartInfo();
                    directPsi.FileName = PythonExe;
                    directPsi.Arguments = "start_game.pyc --direct --account " + accountName;
                    directPsi.WorkingDirectory = AppDir;
                    directPsi.EnvironmentVariables["ROS_GAME_DIR"] = BaseDir;
                    directPsi.EnvironmentVariables["ROS_RT_KEY"] = RtKey;
                    directPsi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                    directPsi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                    directPsi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                    directPsi.UseShellExecute = false;
                    directPsi.CreateNoWindow = false;
                    Process.Start(directPsi);
                } else {
                    // Server is already running; start client instance
                    var cliPsi = new ProcessStartInfo();
                    cliPsi.FileName = PythonExe;
                    cliPsi.Arguments = "start_second.pyc --account " + accountName;
                    cliPsi.WorkingDirectory = AppDir;
                    cliPsi.EnvironmentVariables["ROS_GAME_DIR"] = BaseDir;
                    cliPsi.EnvironmentVariables["ROS_RT_KEY"] = RtKey;
                    cliPsi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                    cliPsi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                    cliPsi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                    cliPsi.UseShellExecute = false;
                    cliPsi.CreateNoWindow = false;
                    Process.Start(cliPsi);
                }

                btnLaunch.Text = "GAME RUNNING!";
                btnLaunch.BackColor = Color.FromArgb(46, 213, 115);

                var t = new Timer();
                t.Interval = 5000;
                t.Tick += (ts, te) => {
                    btnLaunch.Text = "⚡ PLAY ROS REDEMPTION";
                    btnLaunch.BackColor = Color.FromArgb(235, 47, 60);
                    btnLaunch.Enabled = true;
                    t.Stop();
                };
                t.Start();
            } catch (Exception ex) {
                MessageBox.Show("Error launching game: " + ex.Message, "Launch Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                btnLaunch.Text = "⚡ PLAY ROS REDEMPTION";
                btnLaunch.BackColor = Color.FromArgb(235, 47, 60);
                btnLaunch.Enabled = true;
            }
        }

        [STAThread]
        public static void Main() {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new LauncherForm());
        }
    }
}
