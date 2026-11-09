using System;
using System.IO;
using System.Net.Sockets;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Diagnostics;
using System.Threading;

namespace RosRedemptionNativeLauncher {
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
            if (!File.Exists(dbPath)) return rows;

            IntPtr db;
            if (sqlite3_open16(dbPath, out db) != 0) return rows;

            IntPtr errMsg;
            ExecCallback cb = delegate(IntPtr arg, int count, IntPtr values, IntPtr names) {
                var row = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
                for (int i = 0; i < count; i++) {
                    IntPtr valPtr = Marshal.ReadIntPtr(values, i * IntPtr.Size);
                    IntPtr namePtr = Marshal.ReadIntPtr(names, i * IntPtr.Size);
                    string colName = Marshal.PtrToStringAnsi(namePtr);
                    string colVal = valPtr != IntPtr.Zero ? Marshal.PtrToStringAnsi(valPtr) : "";
                    row[colName] = colVal;
                }
                rows.Add(row);
                return 0;
            };

            sqlite3_exec(db, sql, cb, IntPtr.Zero, out errMsg);
            sqlite3_close(db);
            return rows;
        }

        public static bool Exec(string dbPath, string sql) {
            if (!File.Exists(dbPath)) return false;
            IntPtr db;
            if (sqlite3_open16(dbPath, out db) != 0) return false;
            IntPtr errMsg;
            int rc = sqlite3_exec(db, sql, null, IntPtr.Zero, out errMsg);
            sqlite3_close(db);
            return rc == 0;
        }
    }

    public class ModernButton : Button {
        public Color NormalColor { get; set; }
        public Color HoverColor { get; set; }
        public Color TextColor { get; set; }
        private bool isHovered = false;

        public ModernButton() {
            this.FlatStyle = FlatStyle.Flat;
            this.FlatAppearance.BorderSize = 0;
            this.Cursor = Cursors.Hand;
            this.NormalColor = Color.FromArgb(255, 70, 85);
            this.HoverColor = Color.FromArgb(255, 95, 109);
            this.TextColor = Color.White;
            this.Font = new Font("Segoe UI", 11, FontStyle.Bold);
        }

        protected override void OnMouseEnter(EventArgs e) {
            base.OnMouseEnter(e);
            isHovered = true;
            this.Invalidate();
        }

        protected override void OnMouseLeave(EventArgs e) {
            base.OnMouseLeave(e);
            isHovered = false;
            this.Invalidate();
        }

        protected override void OnPaint(PaintEventArgs pevent) {
            Graphics g = pevent.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            Color bg = isHovered ? HoverColor : NormalColor;
            using (SolidBrush b = new SolidBrush(bg)) {
                g.FillRectangle(b, this.ClientRectangle);
            }
            TextRenderer.DrawText(g, this.Text, this.Font, this.ClientRectangle, TextColor, TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
        }
    }

    public class MainForm : Form {
        public const int WM_NCLBUTTONDOWN = 0xA1;
        public const int HT_CAPTION = 0x2;

        [DllImport("user32.dll")]
        public static extern int SendMessage(IntPtr hWnd, int Msg, int wParam, int lParam);
        [DllImport("user32.dll")]
        public static extern bool ReleaseCapture();

        public static string BaseDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
        public static string DbPath = Path.Combine(BaseDir, "local_update", "server_data", "accounts.db");
        public static string PythonExe = Path.Combine(BaseDir, "runtime", "python", "python.exe");
        public static string AppDir = Path.Combine(BaseDir, "runtime", "app");
        public static string RtKey = "f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf";

        // Colors
        private Color ValDark = Color.FromArgb(15, 25, 35);
        private Color ValDarker = Color.FromArgb(11, 17, 24);
        private Color ValPanel = Color.FromArgb(23, 33, 45);
        private Color ValRed = Color.FromArgb(255, 70, 85);
        private Color ValCyan = Color.FromArgb(0, 245, 212);
        private Color ValMuted = Color.FromArgb(139, 151, 165);

        // Header controls
        private Label lblServerBadge;
        private System.Windows.Forms.Timer statusTimer;

        // Content panels
        private Panel navPanel;
        private Panel contentPanel;
        private Panel pnlDeploy;
        private Panel pnlCreate;
        private Panel pnlAdmin;
        private Panel pnlServer;

        // Nav buttons
        private Button btnNavDeploy;
        private Button btnNavCreate;
        private Button btnNavAdmin;
        private Button btnNavServer;

        // Deploy tab controls
        private ComboBox cboAccounts;
        private Label lblCharName;
        private Label lblGid;
        private Label lblDia;
        private Label lblGold;

        // Create Account tab controls
        private TextBox txtRegUser;
        private TextBox txtRegNick;
        private TextBox txtRegPass;

        // Server controls
        private Label lblServerDetail;

        private Image bgImage = null;

        public MainForm() {
            this.Text = "ROS REDEMPTION // TACTICAL BATTLE ROYALE";
            this.Size = new Size(1060, 640);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.None;
            this.BackColor = ValDarker;
            this.ForeColor = Color.White;

            // Load background image if available
            string splashPath = Path.Combine(AppDir, "splash.png");
            if (File.Exists(splashPath)) {
                try {
                    bgImage = Image.FromFile(splashPath);
                } catch { }
            }

            BuildUI();

            statusTimer = new System.Windows.Forms.Timer();
            statusTimer.Interval = 2500;
            statusTimer.Tick += delegate { CheckServerStatus(); };
            statusTimer.Start();
            CheckServerStatus();
            RefreshAccountList();
        }

        private void BuildUI() {
            // 1. TOP TITLE BAR
            Panel titleBar = new Panel {
                Dock = DockStyle.Top,
                Height = 64,
                BackColor = ValDark
            };
            titleBar.MouseDown += TitleBar_MouseDown;

            // Brand Logo & Title
            Label logo = new Label {
                Text = "R",
                Font = new Font("Impact", 18, FontStyle.Bold),
                ForeColor = Color.White,
                BackColor = ValRed,
                Size = new Size(32, 32),
                Location = new Point(20, 16),
                TextAlign = ContentAlignment.MiddleCenter
            };
            logo.MouseDown += TitleBar_MouseDown;

            Label brandText = new Label {
                Text = "ROS REDEMPTION",
                Font = new Font("Segoe UI", 13, FontStyle.Bold),
                ForeColor = Color.White,
                Location = new Point(60, 12),
                AutoSize = true
            };
            brandText.MouseDown += TitleBar_MouseDown;

            Label brandSub = new Label {
                Text = "TACTICAL BATTLE ROYALE // OFFICIAL CLIENT",
                Font = new Font("Segoe UI", 8, FontStyle.Bold),
                ForeColor = ValRed,
                Location = new Point(62, 36),
                AutoSize = true
            };
            brandSub.MouseDown += TitleBar_MouseDown;

            // Server Online Badge in Header
            lblServerBadge = new Label {
                Text = "● CHECKING SERVER...",
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                ForeColor = Color.Yellow,
                Location = new Point(720, 22),
                AutoSize = true
            };
            lblServerBadge.MouseDown += TitleBar_MouseDown;

            // Minimize & Close Buttons
            Button btnMin = new Button {
                Text = "_",
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                ForeColor = Color.White,
                BackColor = ValDark,
                FlatStyle = FlatStyle.Flat,
                Size = new Size(40, 32),
                Location = new Point(965, 16),
                Cursor = Cursors.Hand
            };
            btnMin.FlatAppearance.BorderSize = 0;
            btnMin.Click += delegate { this.WindowState = FormWindowState.Minimized; };

            Button btnClose = new Button {
                Text = "✕",
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                ForeColor = Color.White,
                BackColor = ValDark,
                FlatStyle = FlatStyle.Flat,
                Size = new Size(40, 32),
                Location = new Point(1010, 16),
                Cursor = Cursors.Hand
            };
            btnClose.FlatAppearance.BorderSize = 0;
            btnClose.FlatAppearance.MouseOverBackColor = ValRed;
            btnClose.Click += delegate { Application.Exit(); };

            titleBar.Controls.Add(logo);
            titleBar.Controls.Add(brandText);
            titleBar.Controls.Add(brandSub);
            titleBar.Controls.Add(lblServerBadge);
            titleBar.Controls.Add(btnMin);
            titleBar.Controls.Add(btnClose);
            this.Controls.Add(titleBar);

            // 2. NAVIGATION BAR
            navPanel = new Panel {
                Dock = DockStyle.Top,
                Height = 44,
                BackColor = Color.FromArgb(18, 28, 38)
            };

            btnNavDeploy = CreateNavButton("DEPLOY // PLAY", 20);
            btnNavDeploy.Click += delegate { SwitchTab(0); };

            btnNavCreate = CreateNavButton("+ RECRUIT AGENT", 190);
            btnNavCreate.Click += delegate { SwitchTab(1); };

            btnNavAdmin = CreateNavButton("⚙ MASTER ADMIN", 360);
            btnNavAdmin.Click += delegate { SwitchTab(2); };

            btnNavServer = CreateNavButton("● SERVER INTEL", 530);
            btnNavServer.Click += delegate { SwitchTab(3); };

            navPanel.Controls.Add(btnNavDeploy);
            navPanel.Controls.Add(btnNavCreate);
            navPanel.Controls.Add(btnNavAdmin);
            navPanel.Controls.Add(btnNavServer);
            this.Controls.Add(navPanel);

            // 3. CONTENT CONTAINER
            contentPanel = new Panel {
                Dock = DockStyle.Fill,
                BackColor = ValDarker
            };
            this.Controls.Add(contentPanel);

            // Build Individual Tab Panels
            BuildDeployPanel();
            BuildCreatePanel();
            BuildAdminPanel();
            BuildServerPanel();

            SwitchTab(0);
        }

        private Button CreateNavButton(string text, int x) {
            Button btn = new Button {
                Text = text,
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                ForeColor = ValMuted,
                BackColor = Color.Transparent,
                FlatStyle = FlatStyle.Flat,
                Size = new Size(160, 44),
                Location = new Point(x, 0),
                Cursor = Cursors.Hand
            };
            btn.FlatAppearance.BorderSize = 0;
            btn.FlatAppearance.MouseOverBackColor = Color.FromArgb(28, 40, 55);
            return btn;
        }

        private void SwitchTab(int index) {
            pnlDeploy.Visible = (index == 0);
            pnlCreate.Visible = (index == 1);
            pnlAdmin.Visible = (index == 2);
            pnlServer.Visible = (index == 3);

            btnNavDeploy.ForeColor = (index == 0) ? ValRed : ValMuted;
            btnNavCreate.ForeColor = (index == 1) ? ValCyan : ValMuted;
            btnNavAdmin.ForeColor = (index == 2) ? Color.Gold : ValMuted;
            btnNavServer.ForeColor = (index == 3) ? Color.White : ValMuted;

            if (index == 0) RefreshAccountList();
        }

        // =====================================================================
        // TAB 1: DEPLOY / PLAY NOW
        // =====================================================================
        private void BuildDeployPanel() {
            pnlDeploy = new Panel {
                Dock = DockStyle.Fill,
                BackColor = ValDarker
            };

            // Left Hero Banner
            Panel leftHero = new Panel {
                Location = new Point(30, 25),
                Size = new Size(540, 480),
                BackColor = Color.FromArgb(20, 30, 42)
            };

            Label tag = new Label {
                Text = "TACTICAL BATTLE ROYALE // OFFICIAL",
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                ForeColor = ValRed,
                Location = new Point(25, 25),
                AutoSize = true
            };

            Label h1 = new Label {
                Text = "RULES OF SURVIVAL\nREDEMPTION",
                Font = new Font("Impact", 32, FontStyle.Regular),
                ForeColor = Color.White,
                Location = new Point(22, 50),
                Size = new Size(490, 110)
            };

            Label desc = new Label {
                Text = "Engage in intense 40-bot tactical survival across Ghillie Island. Fully optimized with custom Summer Bicycles, in-game Tango dance, responsive watercraft, and clean combat killfeed banners.",
                Font = new Font("Segoe UI", 10),
                ForeColor = ValMuted,
                Location = new Point(25, 175),
                Size = new Size(490, 70)
            };

            // BIG CRIMSON PLAY BUTTON
            ModernButton btnDeploy = new ModernButton {
                Text = "▶  DEPLOY // PLAY NOW",
                Font = new Font("Impact", 22, FontStyle.Regular),
                NormalColor = ValRed,
                HoverColor = Color.FromArgb(255, 95, 109),
                TextColor = Color.White,
                Location = new Point(25, 270),
                Size = new Size(490, 80)
            };
            btnDeploy.Click += delegate { LaunchGame(); };

            // Sub-buttons below Deploy
            ModernButton btnQuickAdmin = new ModernButton {
                Text = "🌐 OPEN WEB ADMIN DASHBOARD",
                Font = new Font("Segoe UI", 10, FontStyle.Bold),
                NormalColor = Color.FromArgb(35, 45, 60),
                HoverColor = Color.FromArgb(50, 65, 85),
                TextColor = Color.Gold,
                Location = new Point(25, 365),
                Size = new Size(490, 45)
            };
            btnQuickAdmin.Click += delegate { OpenAdminWeb(); };

            leftHero.Controls.Add(tag);
            leftHero.Controls.Add(h1);
            leftHero.Controls.Add(desc);
            leftHero.Controls.Add(btnDeploy);
            leftHero.Controls.Add(btnQuickAdmin);
            pnlDeploy.Controls.Add(leftHero);

            // Right Player Profile Card
            Panel rightCard = new Panel {
                Location = new Point(595, 25),
                Size = new Size(430, 480),
                BackColor = ValPanel
            };

            Label lblSelectHeader = new Label {
                Text = "SELECT ACTIVE AGENT",
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                ForeColor = ValCyan,
                Location = new Point(25, 20),
                AutoSize = true
            };

            cboAccounts = new ComboBox {
                Location = new Point(25, 50),
                Size = new Size(380, 36),
                DropDownStyle = ComboBoxStyle.DropDownList,
                Font = new Font("Segoe UI", 12),
                BackColor = Color.FromArgb(30, 40, 55),
                ForeColor = Color.White
            };
            cboAccounts.SelectedIndexChanged += delegate { UpdateSelectedAccountDisplay(); };

            // Profile info box
            Panel infoBox = new Panel {
                Location = new Point(25, 105),
                Size = new Size(380, 160),
                BackColor = Color.FromArgb(16, 24, 34)
            };

            lblCharName = new Label {
                Text = "CALLSIGN: ---",
                Font = new Font("Segoe UI", 13, FontStyle.Bold),
                ForeColor = Color.White,
                Location = new Point(15, 15),
                AutoSize = true
            };

            lblGid = new Label {
                Text = "AGENT GID: ---",
                Font = new Font("Segoe UI", 9),
                ForeColor = ValMuted,
                Location = new Point(17, 45),
                AutoSize = true
            };

            lblDia = new Label {
                Text = "💎 DIAMONDS: 0",
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                ForeColor = ValCyan,
                Location = new Point(16, 80),
                AutoSize = true
            };

            lblGold = new Label {
                Text = "🪙 GOLD COINS: 0",
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                ForeColor = Color.Gold,
                Location = new Point(16, 115),
                AutoSize = true
            };

            infoBox.Controls.Add(lblCharName);
            infoBox.Controls.Add(lblGid);
            infoBox.Controls.Add(lblDia);
            infoBox.Controls.Add(lblGold);

            // Perks box
            Panel perkBox = new Panel {
                Location = new Point(25, 280),
                Size = new Size(380, 175),
                BackColor = Color.FromArgb(16, 24, 34)
            };

            Label lblPerkTitle = new Label {
                Text = "OFFICIAL PERKS EQUIPPED",
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                ForeColor = ValMuted,
                Location = new Point(15, 12),
                AutoSize = true
            };

            Label p1 = new Label { Text = "🚲 Summer Bicycle (Shift+1 Spawn)", Font = new Font("Segoe UI", 9), ForeColor = Color.White, Location = new Point(15, 40), AutoSize = true };
            Label p2 = new Label { Text = "💃 Tango Dance Emote (Action Wheel)", Font = new Font("Segoe UI", 9), ForeColor = Color.White, Location = new Point(15, 68), AutoSize = true };
            Label p3 = new Label { Text = "🚩 PH Flag & Blue Combat Killfeed", Font = new Font("Segoe UI", 9), ForeColor = Color.White, Location = new Point(15, 96), AutoSize = true };
            Label p4 = new Label { Text = "📦 Full 254 Box Drops (Permanent)", Font = new Font("Segoe UI", 9), ForeColor = ValCyan, Location = new Point(15, 124), AutoSize = true };

            perkBox.Controls.Add(lblPerkTitle);
            perkBox.Controls.Add(p1);
            perkBox.Controls.Add(p2);
            perkBox.Controls.Add(p3);
            perkBox.Controls.Add(p4);

            rightCard.Controls.Add(lblSelectHeader);
            rightCard.Controls.Add(cboAccounts);
            rightCard.Controls.Add(infoBox);
            rightCard.Controls.Add(perkBox);
            pnlDeploy.Controls.Add(rightCard);

            contentPanel.Controls.Add(pnlDeploy);
        }

        // =====================================================================
        // TAB 2: CREATE ACCOUNT (NO CHEATS / NO GEMS INPUT)
        // =====================================================================
        private void BuildCreatePanel() {
            pnlCreate = new Panel {
                Dock = DockStyle.Fill,
                BackColor = ValDarker
            };

            Panel card = new Panel {
                Location = new Point(160, 40),
                Size = new Size(740, 440),
                BackColor = ValPanel
            };

            Label h1 = new Label {
                Text = "RECRUIT NEW AGENT",
                Font = new Font("Impact", 24, FontStyle.Regular),
                ForeColor = ValCyan,
                Location = new Point(40, 25),
                AutoSize = true
            };

            Label desc = new Label {
                Text = "Register a legitimate player account for ROS Redemption. New recruits are automatically assigned standard starter supplies (5,000 Gold Coins + 100 Diamonds + Summer Bicycle + Tango Emote).",
                Font = new Font("Segoe UI", 10),
                ForeColor = ValMuted,
                Location = new Point(42, 65),
                Size = new Size(650, 40)
            };

            Label lUser = new Label { Text = "ACCOUNT USERNAME (LOGIN ID):", Font = new Font("Segoe UI", 9, FontStyle.Bold), ForeColor = Color.White, Location = new Point(42, 120), AutoSize = true };
            txtRegUser = new TextBox { Location = new Point(42, 145), Size = new Size(310, 32), Font = new Font("Segoe UI", 12), BackColor = Color.FromArgb(30, 40, 55), ForeColor = Color.White, BorderStyle = BorderStyle.FixedSingle };

            Label lNick = new Label { Text = "CHARACTER CALLSIGN / NICKNAME:", Font = new Font("Segoe UI", 9, FontStyle.Bold), ForeColor = Color.White, Location = new Point(380, 120), AutoSize = true };
            txtRegNick = new TextBox { Location = new Point(380, 145), Size = new Size(310, 32), Font = new Font("Segoe UI", 12), BackColor = Color.FromArgb(30, 40, 55), ForeColor = Color.White, BorderStyle = BorderStyle.FixedSingle };

            Label lPass = new Label { Text = "PASSWORD:", Font = new Font("Segoe UI", 9, FontStyle.Bold), ForeColor = Color.White, Location = new Point(42, 200), AutoSize = true };
            txtRegPass = new TextBox { Location = new Point(42, 225), Size = new Size(648, 32), Font = new Font("Segoe UI", 12), BackColor = Color.FromArgb(30, 40, 55), ForeColor = Color.White, BorderStyle = BorderStyle.FixedSingle, UseSystemPasswordChar = true };

            Panel infoPanel = new Panel {
                Location = new Point(42, 280),
                Size = new Size(648, 55),
                BackColor = Color.FromArgb(16, 24, 34)
            };
            Label starterNote = new Label {
                Text = "✔ Starter Economy: 5,000 GP  |  100 Diamonds  |  Permanent Starter Depot  |  Anti-Cheat Protected",
                Font = new Font("Segoe UI", 9, FontStyle.Bold),
                ForeColor = ValCyan,
                Location = new Point(15, 18),
                AutoSize = true
            };
            infoPanel.Controls.Add(starterNote);

            ModernButton btnCreate = new ModernButton {
                Text = "✔  CREATE ACCOUNT & DEPLOY",
                Font = new Font("Impact", 18, FontStyle.Regular),
                NormalColor = ValCyan,
                HoverColor = Color.FromArgb(40, 255, 230),
                TextColor = Color.Black,
                Location = new Point(42, 355),
                Size = new Size(648, 55)
            };
            btnCreate.Click += delegate { DoRegisterAccount(); };

            card.Controls.Add(h1);
            card.Controls.Add(desc);
            card.Controls.Add(lUser); card.Controls.Add(txtRegUser);
            card.Controls.Add(lNick); card.Controls.Add(txtRegNick);
            card.Controls.Add(lPass); card.Controls.Add(txtRegPass);
            card.Controls.Add(infoPanel);
            card.Controls.Add(btnCreate);
            pnlCreate.Controls.Add(card);

            contentPanel.Controls.Add(pnlCreate);
        }

        // =====================================================================
        // TAB 3: MASTER ADMIN PANEL LINK
        // =====================================================================
        private void BuildAdminPanel() {
            pnlAdmin = new Panel {
                Dock = DockStyle.Fill,
                BackColor = ValDarker
            };

            Panel card = new Panel {
                Location = new Point(160, 40),
                Size = new Size(740, 440),
                BackColor = ValPanel
            };

            Label h1 = new Label {
                Text = "MASTER WEB CONTROL DASHBOARD",
                Font = new Font("Impact", 24, FontStyle.Regular),
                ForeColor = Color.Gold,
                Location = new Point(40, 25),
                AutoSize = true
            };

            Label desc = new Label {
                Text = "Centralized Web Management Center for Admin Sean. Full authority over player currency grants, account bans, hardware bans (HWID), and real-time announcements.",
                Font = new Font("Segoe UI", 10),
                ForeColor = ValMuted,
                Location = new Point(42, 65),
                Size = new Size(650, 40)
            };

            Panel p1 = new Panel { Location = new Point(42, 120), Size = new Size(310, 110), BackColor = Color.FromArgb(16, 24, 34) };
            Label t1 = new Label { Text = "🪙 CURRENCY MANAGEMENT", Font = new Font("Segoe UI", 10, FontStyle.Bold), ForeColor = Color.Gold, Location = new Point(15, 15), AutoSize = true };
            Label d1 = new Label { Text = "Grant +999M Diamonds/Gold or custom amounts to any player instantly.", Font = new Font("Segoe UI", 9), ForeColor = ValMuted, Location = new Point(15, 45), Size = new Size(280, 50) };
            p1.Controls.Add(t1); p1.Controls.Add(d1);

            Panel p2 = new Panel { Location = new Point(380, 120), Size = new Size(310, 110), BackColor = Color.FromArgb(16, 24, 34) };
            Label t2 = new Label { Text = "🔨 BAN & HWID HARDWARE LOCK", Font = new Font("Segoe UI", 10, FontStyle.Bold), ForeColor = ValRed, Location = new Point(15, 15), AutoSize = true };
            Label d2 = new Label { Text = "Ban cheaters by account or freeze machine Hardware IDs permanently.", Font = new Font("Segoe UI", 9), ForeColor = ValMuted, Location = new Point(15, 45), Size = new Size(280, 50) };
            p2.Controls.Add(t2); p2.Controls.Add(d2);

            Panel p3 = new Panel { Location = new Point(42, 245), Size = new Size(648, 65), BackColor = Color.FromArgb(16, 24, 34) };
            Label t3 = new Label { Text = "📢 LIVE SERVER ANNOUNCEMENTS", Font = new Font("Segoe UI", 10, FontStyle.Bold), ForeColor = ValCyan, Location = new Point(15, 12), AutoSize = true };
            Label d3 = new Label { Text = "Broadcast in-game notices and maintenance tickers to all online players.", Font = new Font("Segoe UI", 9), ForeColor = ValMuted, Location = new Point(15, 36), AutoSize = true };
            p3.Controls.Add(t3); p3.Controls.Add(d3);

            ModernButton btnOpenWeb = new ModernButton {
                Text = "⚡  OPEN WEB ADMIN DASHBOARD (http://127.0.0.1:8799/admin)",
                Font = new Font("Impact", 16, FontStyle.Regular),
                NormalColor = Color.Gold,
                HoverColor = Color.FromArgb(255, 220, 50),
                TextColor = Color.Black,
                Location = new Point(42, 335),
                Size = new Size(648, 60)
            };
            btnOpenWeb.Click += delegate { OpenAdminWeb(); };

            card.Controls.Add(h1);
            card.Controls.Add(desc);
            card.Controls.Add(p1);
            card.Controls.Add(p2);
            card.Controls.Add(p3);
            card.Controls.Add(btnOpenWeb);
            pnlAdmin.Controls.Add(card);

            contentPanel.Controls.Add(pnlAdmin);
        }

        // =====================================================================
        // TAB 4: SERVER CONTROLS
        // =====================================================================
        private void BuildServerPanel() {
            pnlServer = new Panel {
                Dock = DockStyle.Fill,
                BackColor = ValDarker
            };

            Panel card = new Panel {
                Location = new Point(160, 40),
                Size = new Size(740, 440),
                BackColor = ValPanel
            };

            Label h1 = new Label {
                Text = "SERVER INTEL & ENGINE CONTROLS",
                Font = new Font("Impact", 24, FontStyle.Regular),
                ForeColor = Color.White,
                Location = new Point(40, 25),
                AutoSize = true
            };

            lblServerDetail = new Label {
                Text = "Lobby Server (19000): Checking...\nBattle Host (19100): Checking...\nDatabase: accounts.db Ready",
                Font = new Font("Segoe UI", 11),
                ForeColor = ValMuted,
                Location = new Point(42, 80),
                Size = new Size(650, 80)
            };

            ModernButton btnStartServer = new ModernButton {
                Text = "▶ START STANDALONE SERVER ENGINE",
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                NormalColor = Color.FromArgb(46, 204, 113),
                HoverColor = Color.FromArgb(60, 225, 130),
                TextColor = Color.White,
                Location = new Point(42, 190),
                Size = new Size(648, 50)
            };
            btnStartServer.Click += delegate { StartServerOnly(); };

            ModernButton btnKillAll = new ModernButton {
                Text = "⏹ KILL ALL GAME & SERVER PROCESSES",
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                NormalColor = Color.FromArgb(192, 57, 43),
                HoverColor = Color.FromArgb(220, 70, 55),
                TextColor = Color.White,
                Location = new Point(42, 260),
                Size = new Size(648, 50)
            };
            btnKillAll.Click += delegate { StopAllProcesses(); };

            ModernButton btnRefreshDb = new ModernButton {
                Text = "🔄 RE-SYNC & REFRESH ACCOUNTS",
                Font = new Font("Segoe UI", 11, FontStyle.Bold),
                NormalColor = Color.FromArgb(41, 128, 185),
                HoverColor = Color.FromArgb(52, 152, 219),
                TextColor = Color.White,
                Location = new Point(42, 330),
                Size = new Size(648, 50)
            };
            btnRefreshDb.Click += delegate { RefreshAccountList(); MessageBox.Show("Database re-synchronized successfully!"); };

            card.Controls.Add(h1);
            card.Controls.Add(lblServerDetail);
            card.Controls.Add(btnStartServer);
            card.Controls.Add(btnKillAll);
            card.Controls.Add(btnRefreshDb);
            pnlServer.Controls.Add(card);

            contentPanel.Controls.Add(pnlServer);
        }

        // =====================================================================
        // FUNCTIONALITY
        // =====================================================================
        private void TitleBar_MouseDown(object sender, MouseEventArgs e) {
            if (e.Button == MouseButtons.Left) {
                ReleaseCapture();
                SendMessage(Handle, WM_NCLBUTTONDOWN, HT_CAPTION, 0);
            }
        }

        public bool IsPortOpen(int port) {
            try {
                using (var tcp = new TcpClient()) {
                    var ar = tcp.BeginConnect("127.0.0.1", port, null, null);
                    if (ar.AsyncWaitHandle.WaitOne(200)) {
                        tcp.EndConnect(ar);
                        return true;
                    }
                }
            } catch { }
            return false;
        }

        public void CheckServerStatus() {
            bool lobbyUp = IsPortOpen(19000);
            bool battleUp = IsPortOpen(19100);

            if (lobbyUp) {
                lblServerBadge.Text = "● SERVER ONLINE (19000)";
                lblServerBadge.ForeColor = ValCyan;
            } else {
                lblServerBadge.Text = "○ SERVER OFFLINE";
                lblServerBadge.ForeColor = ValRed;
            }

            if (lblServerDetail != null) {
                lblServerDetail.Text = string.Format(
                    "Lobby Server (Port 19000): {0}\nBattle Server (Port 19100): {1}\nMaster Database: {2}\nActive Accounts: {3}",
                    lobbyUp ? "ONLINE (Active)" : "OFFLINE",
                    battleUp ? "ONLINE (Ready)" : "STANDBY",
                    File.Exists(DbPath) ? "ONLINE (accounts.db)" : "MISSING",
                    cboAccounts.Items.Count
                );
            }
        }

        public void RefreshAccountList() {
            try {
                string currentSel = cboAccounts.SelectedItem != null ? cboAccounts.SelectedItem.ToString() : "";
                cboAccounts.Items.Clear();

                var rows = WinSqlite.Query(DbPath, "SELECT a.username, c.gid, c.nickname FROM accounts a LEFT JOIN characters c ON a.id = c.account_id ORDER BY a.id ASC;");
                int selIndex = 0;
                for (int i = 0; i < rows.Count; i++) {
                    string u = rows[i].ContainsKey("username") ? rows[i]["username"] : "";
                    if (!string.IsNullOrEmpty(u)) {
                        cboAccounts.Items.Add(u);
                        if (u.Equals(currentSel, StringComparison.OrdinalIgnoreCase)) {
                            selIndex = i;
                        }
                    }
                }

                if (cboAccounts.Items.Count > 0) {
                    cboAccounts.SelectedIndex = selIndex;
                    UpdateSelectedAccountDisplay();
                }
            } catch (Exception ex) {
                MessageBox.Show("Error loading accounts from database: " + ex.Message);
            }
        }

        private void UpdateSelectedAccountDisplay() {
            if (cboAccounts.SelectedItem == null) return;
            string username = cboAccounts.SelectedItem.ToString();

            try {
                var rows = WinSqlite.Query(DbPath, string.Format(@"
                    SELECT a.username, c.gid, c.nickname, w.gp, (w.freeYuanbao + w.payYuanbao) as dia
                    FROM accounts a
                    LEFT JOIN characters c ON a.id = c.account_id
                    LEFT JOIN wallets w ON c.gid = w.gid
                    WHERE a.username = '{0}';", username));

                if (rows.Count > 0) {
                    var r = rows[0];
                    string nick = r.ContainsKey("nickname") && !string.IsNullOrEmpty(r["nickname"]) ? r["nickname"] : username;
                    string gid = r.ContainsKey("gid") ? r["gid"] : "N/A";
                    long gold = 0, dia = 0;
                    if (r.ContainsKey("gp")) long.TryParse(r["gp"], out gold);
                    if (r.ContainsKey("dia")) long.TryParse(r["dia"], out dia);

                    lblCharName.Text = "CALLSIGN: " + nick;
                    lblGid.Text = "AGENT GID: " + gid + " (" + username + ")";
                    lblDia.Text = string.Format("💎 DIAMONDS: {0:N0}", dia);
                    lblGold.Text = string.Format("🪙 GOLD COINS: {0:N0}", gold);
                }
            } catch { }
        }

        private void SetActiveIdentity(string username, string nickname) {
            string payload = string.Format(@"{{
  ""aid"": ""3"",
  ""sdkuid"": ""{0}"",
  ""gas_token"": ""local-offline-token"",
  ""username"": ""{1}"",
  ""chl_sdk_json"": ""{{}}""
}}", username, nickname);

            string[] idFiles = new string[] {
                Path.Combine(BaseDir, "local_update", "local_identity.json"),
                Path.Combine(BaseDir, "runtime", "app", "local_update", "local_identity.json"),
                Path.Combine(BaseDir, "ROS_Redemption_Server_Package", "local_update", "local_identity.json")
            };

            foreach (var f in idFiles) {
                try {
                    if (Directory.Exists(Path.GetDirectoryName(f))) {
                        File.WriteAllText(f, payload);
                    }
                } catch { }
            }
        }

        public void LaunchGame() {
            string username = cboAccounts.SelectedItem != null ? cboAccounts.SelectedItem.ToString() : "Admin_Redemption";
            string nick = username;
            try {
                var r = WinSqlite.Query(DbPath, "SELECT nickname FROM characters c JOIN accounts a ON a.id = c.account_id WHERE a.username='" + username + "';");
                if (r.Count > 0 && r[0].ContainsKey("nickname")) nick = r[0]["nickname"];
            } catch { }

            // Write active identity
            SetActiveIdentity(username, nick);

            // Ensure branding helper runs silently in background
            string brandingExe = Path.Combine(BaseDir, "RosRedemptionBrandingSuite.exe");
            if (File.Exists(brandingExe)) {
                try {
                    Process[] procs = Process.GetProcessesByName("RosRedemptionBrandingSuite");
                    if (procs == null || procs.Length == 0) {
                        Process.Start(brandingExe);
                    }
                } catch { }
            }

            // Launch Game Executable
            try {
                var psi = new ProcessStartInfo();
                psi.FileName = PythonExe;
                psi.Arguments = "start_game.pyc --direct --account " + username;
                psi.WorkingDirectory = AppDir;
                psi.EnvironmentVariables["ROS_GAME_DIR"] = BaseDir;
                psi.EnvironmentVariables["ROS_RT_KEY"] = RtKey;
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                psi.UseShellExecute = false;
                psi.CreateNoWindow = false;

                Process.Start(psi);
                this.WindowState = FormWindowState.Minimized;
            } catch (Exception ex) {
                MessageBox.Show("Failed to launch game client: " + ex.Message, "Launch Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        public void DoRegisterAccount() {
            string u = txtRegUser.Text.Trim();
            string n = txtRegNick.Text.Trim();
            if (string.IsNullOrEmpty(u) || u.Length < 2) {
                MessageBox.Show("Please enter a username with at least 2 characters!", "Input Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            if (string.IsNullOrEmpty(n)) n = u;

            // Check duplicate
            var existing = WinSqlite.Query(DbPath, "SELECT id FROM accounts WHERE username='" + u + "';");
            if (existing.Count > 0) {
                MessageBox.Show("Username '" + u + "' already exists! Please choose another.", "Duplicate Username", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            long starterGold = 5000;
            long starterDia = 100;

            string accSql = string.Format("INSERT INTO accounts (username, created, last_login, last_server, banned, note) VALUES ('{0}', {1}, {1}, 10501, 0, 'Official Native Client');", u, now);
            WinSqlite.Exec(DbPath, accSql);

            var created = WinSqlite.Query(DbPath, "SELECT id FROM accounts WHERE username='" + u + "';");
            if (created.Count > 0) {
                long accId = long.Parse(created[0]["id"]);
                long gid = 10000000 + accId;

                string lobbyJson = "{\"country\":\"PH\",\"nation\":\"PH\",\"flag\":\"PH\",\"appearance\":{\"dtsBodyAppearanceList\":[],\"dtsWearableAppearanceList\":[1110326,1111326,112495],\"dtsWeaponAppearanceList\":[120016,121021],\"dtsInGameActionAppearanceIDs\":[909042,909030,909031],\"dtsInGameActionSuitAppearanceIDs\":[909042]}}";
                string charSql = string.Format("INSERT INTO characters (gid, account_id, server_id, nickname, character_type, created, base_level, level, lobby, created_at, last_login) VALUES ({0}, {1}, 10501, '{2}', 10002, 1, 1, 1, '{3}', {4}, {4});", gid, accId, n, lobbyJson, now);
                WinSqlite.Exec(DbPath, charSql);

                string wallSql = string.Format("INSERT OR REPLACE INTO wallets (gid, payYuanbao, freeYuanbao, gp) VALUES ({0}, {1}, {1}, {2});", gid, starterDia, starterGold);
                WinSqlite.Exec(DbPath, wallSql);

                string charData = "{\"depot\":{\"140073\":{\"count\":1,\"expires\":0},\"909042\":{\"count\":1,\"expires\":0}},\"equipped\":{\"dtsInGameActionAppearanceIDs\":[909042,909030,909031],\"dtsInGameActionSuitAppearanceIDs\":[909042]}}";
                string dataSql = string.Format("INSERT OR REPLACE INTO character_data (gid, data) VALUES ({0}, '{1}');", gid, charData);
                WinSqlite.Exec(DbPath, dataSql);

                // Sync to secondary databases if they exist
                string[] extraDbs = new string[] {
                    Path.Combine(BaseDir, "runtime", "app", "local_update", "server_data", "accounts.db"),
                    Path.Combine(BaseDir, "ROS_Redemption_Server_Package", "local_update", "server_data", "accounts.db")
                };
                foreach (var db in extraDbs) {
                    if (File.Exists(db)) {
                        WinSqlite.Exec(db, accSql);
                        WinSqlite.Exec(db, charSql);
                        WinSqlite.Exec(db, wallSql);
                        WinSqlite.Exec(db, dataSql);
                    }
                }

                MessageBox.Show(string.Format("SUCCESS!\n\nAgent '{0}' (Callsign: '{1}') recruited successfully!\n\nStarter Supply: 5,000 Gold Coins + 100 Diamonds + Summer Bicycle + Tango Emote equipped.", u, n), "Agent Recruited", MessageBoxButtons.OK, MessageBoxIcon.Information);

                txtRegUser.Text = "";
                txtRegNick.Text = "";
                txtRegPass.Text = "";

                RefreshAccountList();
                cboAccounts.SelectedItem = u;
                SwitchTab(0);
            }
        }

        public void OpenAdminWeb() {
            // Check if admin server is running
            if (!IsPortOpen(8799)) {
                try {
                    string serverPy = Path.Combine(BaseDir, "launcher", "launcher_server.py");
                    var psi = new ProcessStartInfo();
                    psi.FileName = PythonExe;
                    psi.Arguments = "\"" + serverPy + "\"";
                    psi.WorkingDirectory = BaseDir;
                    psi.UseShellExecute = false;
                    psi.CreateNoWindow = true;
                    Process.Start(psi);
                    Thread.Sleep(800);
                } catch { }
            }

            try {
                Process.Start("http://127.0.0.1:8799/admin");
            } catch (Exception ex) {
                MessageBox.Show("Could not open browser: " + ex.Message);
            }
        }

        public void StartServerOnly() {
            if (IsPortOpen(19000)) {
                MessageBox.Show("Server is already running on port 19000!", "Server Status", MessageBoxButtons.OK, MessageBoxIcon.Information);
                return;
            }
            try {
                var psi = new ProcessStartInfo();
                psi.FileName = PythonExe;
                psi.Arguments = "start_game.pyc --server-only";
                psi.WorkingDirectory = AppDir;
                psi.EnvironmentVariables["ROS_GAME_DIR"] = BaseDir;
                psi.EnvironmentVariables["ROS_RT_KEY"] = RtKey;
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                psi.UseShellExecute = false;
                psi.CreateNoWindow = false;

                Process.Start(psi);
                Thread.Sleep(1000);
                CheckServerStatus();
                MessageBox.Show("Dedicated Server Engine started on port 19000!", "Server Started", MessageBoxButtons.OK, MessageBoxIcon.Information);
            } catch (Exception ex) {
                MessageBox.Show("Failed to start server: " + ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        public void StopAllProcesses() {
            foreach (string p in new string[] { "ros64", "ros", "RosReborn", "python" }) {
                foreach (var proc in Process.GetProcessesByName(p)) {
                    try { proc.Kill(); } catch { }
                }
            }
            CheckServerStatus();
            MessageBox.Show("All game and server processes terminated!", "Processes Stopped", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        [STAThread]
        public static void Main() {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }
}

