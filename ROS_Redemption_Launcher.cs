using System;
using System.IO;
using System.Net;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Diagnostics;
using System.Threading;
using System.Text;

namespace RosRedemptionOnlineLauncher {
    public class ModernButton : Button {
        public Color NormalColor { get; set; }
        public Color HoverColor { get; set; }
        public Color TextColor { get; set; }
        public int CornerRadius { get; set; }
        private bool isHovered = false;

        public ModernButton() {
            this.FlatStyle = FlatStyle.Flat;
            this.FlatAppearance.BorderSize = 0;
            this.Cursor = Cursors.Hand;
            this.NormalColor = Color.FromArgb(255, 70, 85);
            this.HoverColor = Color.FromArgb(255, 95, 109);
            this.TextColor = Color.White;
            this.Font = new Font("Segoe UI", 12, FontStyle.Bold);
            this.CornerRadius = 4;
            this.DoubleBuffered = true;
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

    public class ModernTextBox : Panel {
        private TextBox innerBox;
        private Color borderColor = Color.FromArgb(45, 55, 72);
        private Color focusColor = Color.FromArgb(0, 245, 212);
        private bool isFocused = false;

        public string TextValue {
            get { return innerBox.Text; }
            set { innerBox.Text = value; }
        }

        public bool UseSystemPasswordChar {
            get { return innerBox.UseSystemPasswordChar; }
            set { innerBox.UseSystemPasswordChar = value; }
        }

        public ModernTextBox(bool isPassword = false) {
            this.Padding = new Padding(10, 8, 10, 8);
            this.BackColor = Color.FromArgb(15, 23, 33);
            this.Size = new Size(320, 38);

            innerBox = new TextBox();
            innerBox.BorderStyle = BorderStyle.None;
            innerBox.BackColor = Color.FromArgb(15, 23, 33);
            innerBox.ForeColor = Color.White;
            innerBox.Font = new Font("Segoe UI", 10.5f, FontStyle.Regular);
            innerBox.Dock = DockStyle.Fill;
            innerBox.UseSystemPasswordChar = isPassword;

            innerBox.Enter += (s, e) => { isFocused = true; this.Invalidate(); };
            innerBox.Leave += (s, e) => { isFocused = false; this.Invalidate(); };

            this.Controls.Add(innerBox);
        }

        protected override void OnPaint(PaintEventArgs e) {
            base.OnPaint(e);
            using (Pen p = new Pen(isFocused ? focusColor : borderColor, isFocused ? 1.5f : 1.0f)) {
                e.Graphics.DrawRectangle(p, 0, 0, this.Width - 1, this.Height - 1);
            }
        }
    }

    public class MainForm : Form {
        public const int WM_NCLBUTTONDOWN = 0xA1;
        public const int HT_CAPTION = 0x2;

        [DllImport("user32.dll")]
        public static extern int SendMessage(IntPtr hWnd, int Msg, int wParam, int lParam);
        [DllImport("user32.dll")]
        public static extern bool ReleaseCapture();

        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        static extern bool SetWindowText(IntPtr hWnd, string lpString);
        [DllImport("user32.dll", SetLastError = true)]
        static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
        [DllImport("user32.dll")]
        static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);
        [DllImport("user32.dll")]
        static extern IntPtr SetClassLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);
        delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        const int WM_SETICON_MSG = 0x0080;
        const int ICON_SMALL_IDX = 0;
        const int ICON_BIG_IDX = 1;
        const int GCLP_HICON_IDX = -14;
        const int GCLP_HICONSM_IDX = -34;
        const string GAME_WINDOW_TITLE = "ROS REDEMPTION";

        public static string BaseDir = AppDomain.CurrentDomain.BaseDirectory.TrimEnd('\\', '/');
        public static string PythonExe = Path.Combine(BaseDir, "runtime", "python", "python.exe");
        public static string PythonwExe = Path.Combine(BaseDir, "runtime", "python", "pythonw.exe");
        public static string AppDir = Path.Combine(BaseDir, "runtime", "app");
        public static string SessionFile = Path.Combine(BaseDir, ".online_session.json");
        public static string ServerListFile = Path.Combine(BaseDir, "online_servers.json");
        public static string ApiUrl = "http://143.14.88.9:30063";

        // Colors
        private Color ValDark = Color.FromArgb(15, 23, 33);
        private Color ValDarker = Color.FromArgb(11, 17, 24);
        private Color ValCard = Color.FromArgb(20, 29, 41);
        private Color ValRed = Color.FromArgb(255, 70, 85);
        private Color ValCyan = Color.FromArgb(0, 245, 212);
        private Color ValGreen = Color.FromArgb(0, 230, 118);
        private Color ValMuted = Color.FromArgb(148, 163, 184);

        // Header controls
        private Label lblServerBadge;
        private Label lblPlayerCount;
        private Label lblPing;
        private System.Windows.Forms.Timer statusTimer;

        // Auth controls
        private Panel authPanel;
        private Button btnTabLogin;
        private Button btnTabRegister;
        private ModernTextBox txtUser;
        private ModernTextBox txtPass;
        private ModernTextBox txtEmail;
        private Label lblEmailPrompt;
        private CheckBox chkRemember;
        private ModernButton btnLaunch;
        private Label lblStatus;
        private bool isRegisterMode = false;

        // Patch Notes controls
        private RichTextBox txtPatchNotes;

        private Image bgImage = null;

        public MainForm() {
            this.Text = "ROS REDEMPTION // PRO LAUNCHER";
            this.Size = new Size(1060, 640);
            this.StartPosition = FormStartPosition.CenterScreen;
            this.FormBorderStyle = FormBorderStyle.None;
            this.BackColor = ValDarker;
            this.ForeColor = Color.White;
            this.DoubleBuffered = true;

            // Load background image
            string splashPath = Path.Combine(AppDir, "splash.png");
            if (!File.Exists(splashPath)) {
                splashPath = Path.Combine(BaseDir, "splash.png");
            }
            if (File.Exists(splashPath)) {
                try {
                    bgImage = Image.FromFile(splashPath);
                } catch { }
            }

            // Window Icon
            string icoPath = Path.Combine(AppDir, "ros.ico");
            if (File.Exists(icoPath)) {
                try {
                    this.Icon = new Icon(icoPath);
                } catch { }
            }

            BuildUI();
            LoadSavedSession();

            // Background status poller
            statusTimer = new System.Windows.Forms.Timer();
            statusTimer.Interval = 5000;
            statusTimer.Tick += (s, e) => PollServerStatsAsync();
            statusTimer.Start();

            // Initial poll
            PollServerStatsAsync();

            // Window branding thread
            Thread brandThread = new Thread(GameBrandingWatchdog);
            brandThread.IsBackground = true;
            brandThread.Start();
        }

        private void BuildUI() {
            // Header Bar
            Panel header = new Panel();
            header.Dock = DockStyle.Top;
            header.Height = 44;
            header.BackColor = Color.FromArgb(180, 11, 17, 24);
            header.MouseDown += (s, e) => {
                if (e.Button == MouseButtons.Left) {
                    ReleaseCapture();
                    SendMessage(Handle, WM_NCLBUTTONDOWN, HT_CAPTION, 0);
                }
            };

            Label title = new Label();
            title.Text = "ROS REDEMPTION // PRO ONLINE LAUNCHER";
            title.Font = new Font("Segoe UI", 10.5f, FontStyle.Bold);
            title.ForeColor = Color.White;
            title.AutoSize = true;
            title.Location = new Point(16, 12);
            header.Controls.Add(title);

            Button btnMin = new Button();
            btnMin.Text = "—";
            btnMin.Font = new Font("Segoe UI", 10, FontStyle.Bold);
            btnMin.FlatStyle = FlatStyle.Flat;
            btnMin.FlatAppearance.BorderSize = 0;
            btnMin.ForeColor = ValMuted;
            btnMin.BackColor = Color.Transparent;
            btnMin.Size = new Size(36, 44);
            btnMin.Location = new Point(this.Width - 80, 0);
            btnMin.Cursor = Cursors.Hand;
            btnMin.Click += (s, e) => this.WindowState = FormWindowState.Minimized;
            header.Controls.Add(btnMin);

            Button btnClose = new Button();
            btnClose.Text = "✕";
            btnClose.Font = new Font("Segoe UI", 11, FontStyle.Bold);
            btnClose.FlatStyle = FlatStyle.Flat;
            btnClose.FlatAppearance.BorderSize = 0;
            btnClose.ForeColor = ValMuted;
            btnClose.BackColor = Color.Transparent;
            btnClose.Size = new Size(44, 44);
            btnClose.Location = new Point(this.Width - 44, 0);
            btnClose.Cursor = Cursors.Hand;
            btnClose.MouseEnter += (s, e) => { btnClose.BackColor = Color.FromArgb(220, 38, 38); btnClose.ForeColor = Color.White; };
            btnClose.MouseLeave += (s, e) => { btnClose.BackColor = Color.Transparent; btnClose.ForeColor = ValMuted; };
            btnClose.Click += (s, e) => Application.Exit();
            header.Controls.Add(btnClose);

            this.Controls.Add(header);

            // Server Info Banner
            Panel banner = new Panel();
            banner.Location = new Point(24, 56);
            banner.Size = new Size(1012, 48);
            banner.BackColor = Color.FromArgb(210, 15, 23, 33);

            lblServerBadge = new Label();
            lblServerBadge.Text = "🟢  SINGAPORE DEDICATED (143.14.88.9) // ONLINE";
            lblServerBadge.Font = new Font("Segoe UI", 11, FontStyle.Bold);
            lblServerBadge.ForeColor = ValGreen;
            lblServerBadge.AutoSize = true;
            lblServerBadge.Location = new Point(16, 14);
            banner.Controls.Add(lblServerBadge);

            lblPlayerCount = new Label();
            lblPlayerCount.Text = "👥  Players In-Game: ...";
            lblPlayerCount.Font = new Font("Segoe UI", 10.5f, FontStyle.Bold);
            lblPlayerCount.ForeColor = ValCyan;
            lblPlayerCount.AutoSize = true;
            lblPlayerCount.Location = new Point(620, 15);
            banner.Controls.Add(lblPlayerCount);

            lblPing = new Label();
            lblPing.Text = "📶  Ping: -- ms";
            lblPing.Font = new Font("Segoe UI", 10, FontStyle.Bold);
            lblPing.ForeColor = ValMuted;
            lblPing.AutoSize = true;
            lblPing.Location = new Point(880, 15);
            banner.Controls.Add(lblPing);

            this.Controls.Add(banner);

            // LEFT COLUMN: Live Patch Notes / Changelog
            Panel leftCol = new Panel();
            leftCol.Location = new Point(24, 116);
            leftCol.Size = new Size(610, 450);
            leftCol.BackColor = Color.FromArgb(220, 15, 23, 33);

            Label lblPatchTitle = new Label();
            lblPatchTitle.Text = "📢  LATEST UPDATE // PATCH NOTES & CHANGELOG (v1.2.0)";
            lblPatchTitle.Font = new Font("Segoe UI", 11, FontStyle.Bold);
            lblPatchTitle.ForeColor = ValCyan;
            lblPatchTitle.Location = new Point(16, 14);
            lblPatchTitle.AutoSize = true;
            leftCol.Controls.Add(lblPatchTitle);

            txtPatchNotes = new RichTextBox();
            txtPatchNotes.Location = new Point(16, 44);
            txtPatchNotes.Size = new Size(578, 386);
            txtPatchNotes.BackColor = Color.FromArgb(12, 18, 26);
            txtPatchNotes.ForeColor = Color.FromArgb(226, 232, 240);
            txtPatchNotes.BorderStyle = BorderStyle.None;
            txtPatchNotes.ReadOnly = true;
            txtPatchNotes.Font = new Font("Segoe UI", 10f);
            txtPatchNotes.Text = "Loading live patch notes from server...";
            leftCol.Controls.Add(txtPatchNotes);

            this.Controls.Add(leftCol);

            // RIGHT COLUMN: Agent Auth & Launch Game
            authPanel = new Panel();
            authPanel.Location = new Point(650, 116);
            authPanel.Size = new Size(386, 450);
            authPanel.BackColor = Color.FromArgb(220, 15, 23, 33);

            // Tabs: LOGIN vs REGISTER
            btnTabLogin = new Button();
            btnTabLogin.Text = "LOGIN";
            btnTabLogin.Size = new Size(160, 36);
            btnTabLogin.Location = new Point(28, 16);
            btnTabLogin.FlatStyle = FlatStyle.Flat;
            btnTabLogin.FlatAppearance.BorderSize = 0;
            btnTabLogin.Font = new Font("Segoe UI", 11, FontStyle.Bold);
            btnTabLogin.ForeColor = ValCyan;
            btnTabLogin.BackColor = Color.FromArgb(25, 36, 50);
            btnTabLogin.Cursor = Cursors.Hand;
            btnTabLogin.Click += (s, e) => SwitchAuthTab(false);
            authPanel.Controls.Add(btnTabLogin);

            btnTabRegister = new Button();
            btnTabRegister.Text = "REGISTER";
            btnTabRegister.Size = new Size(160, 36);
            btnTabRegister.Location = new Point(198, 16);
            btnTabRegister.FlatStyle = FlatStyle.Flat;
            btnTabRegister.FlatAppearance.BorderSize = 0;
            btnTabRegister.Font = new Font("Segoe UI", 11, FontStyle.Bold);
            btnTabRegister.ForeColor = ValMuted;
            btnTabRegister.BackColor = Color.Transparent;
            btnTabRegister.Cursor = Cursors.Hand;
            btnTabRegister.Click += (s, e) => SwitchAuthTab(true);
            authPanel.Controls.Add(btnTabRegister);

            // Inputs
            Label lblUser = new Label();
            lblUser.Text = "USERNAME / AGENT ID";
            lblUser.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            lblUser.ForeColor = ValMuted;
            lblUser.Location = new Point(28, 68);
            lblUser.AutoSize = true;
            authPanel.Controls.Add(lblUser);

            txtUser = new ModernTextBox(false);
            txtUser.Location = new Point(28, 88);
            txtUser.Size = new Size(330, 38);
            authPanel.Controls.Add(txtUser);

            Label lblPass = new Label();
            lblPass.Text = "PASSWORD (MIN. 8 CHARS)";
            lblPass.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            lblPass.ForeColor = ValMuted;
            lblPass.Location = new Point(28, 136);
            lblPass.AutoSize = true;
            authPanel.Controls.Add(lblPass);

            txtPass = new ModernTextBox(true);
            txtPass.Location = new Point(28, 156);
            txtPass.Size = new Size(330, 38);
            authPanel.Controls.Add(txtPass);

            lblEmailPrompt = new Label();
            lblEmailPrompt.Text = "EMAIL (OPTIONAL)";
            lblEmailPrompt.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            lblEmailPrompt.ForeColor = ValMuted;
            lblEmailPrompt.Location = new Point(28, 204);
            lblEmailPrompt.AutoSize = true;
            lblEmailPrompt.Visible = false;
            authPanel.Controls.Add(lblEmailPrompt);

            txtEmail = new ModernTextBox(false);
            txtEmail.Location = new Point(28, 224);
            txtEmail.Size = new Size(330, 38);
            txtEmail.Visible = false;
            authPanel.Controls.Add(txtEmail);

            chkRemember = new CheckBox();
            chkRemember.Text = "Remember Account & Auto-Login";
            chkRemember.Font = new Font("Segoe UI", 9.5f);
            chkRemember.ForeColor = Color.FromArgb(203, 213, 225);
            chkRemember.Location = new Point(30, 204);
            chkRemember.AutoSize = true;
            chkRemember.Checked = true;
            authPanel.Controls.Add(chkRemember);

            lblStatus = new Label();
            lblStatus.Text = "Ready to launch.";
            lblStatus.Font = new Font("Segoe UI", 9.5f, FontStyle.Bold);
            lblStatus.ForeColor = ValCyan;
            lblStatus.Location = new Point(28, 275);
            lblStatus.Size = new Size(330, 24);
            lblStatus.TextAlign = ContentAlignment.MiddleCenter;
            authPanel.Controls.Add(lblStatus);

            btnLaunch = new ModernButton();
            btnLaunch.Text = "▶  LAUNCH GAME";
            btnLaunch.Location = new Point(28, 305);
            btnLaunch.Size = new Size(330, 56);
            btnLaunch.NormalColor = ValRed;
            btnLaunch.HoverColor = Color.FromArgb(255, 95, 109);
            btnLaunch.Click += (s, e) => DoLaunchOnlineGame();
            authPanel.Controls.Add(btnLaunch);

            // Community links
            Button btnDiscord = new Button();
            btnDiscord.Text = "🌐 Discord Community";
            btnDiscord.Location = new Point(28, 375);
            btnDiscord.Size = new Size(160, 32);
            btnDiscord.FlatStyle = FlatStyle.Flat;
            btnDiscord.FlatAppearance.BorderSize = 0;
            btnDiscord.BackColor = Color.FromArgb(30, 41, 59);
            btnDiscord.ForeColor = ValCyan;
            btnDiscord.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            btnDiscord.Cursor = Cursors.Hand;
            btnDiscord.Click += (s, e) => {
                try { Process.Start("https://discord.gg"); } catch { }
            };
            authPanel.Controls.Add(btnDiscord);

            Button btnAdmin = new Button();
            btnAdmin.Text = "⚙️ Admin Panel";
            btnAdmin.Location = new Point(198, 375);
            btnAdmin.Size = new Size(160, 32);
            btnAdmin.FlatStyle = FlatStyle.Flat;
            btnAdmin.FlatAppearance.BorderSize = 0;
            btnAdmin.BackColor = Color.FromArgb(30, 41, 59);
            btnAdmin.ForeColor = ValMuted;
            btnAdmin.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            btnAdmin.Cursor = Cursors.Hand;
            btnAdmin.Click += (s, e) => {
                try { Process.Start("http://127.0.0.1:8790/admin?key=wYq5VSkn6wgUschxPBxu51z1ZolmgbKt"); } catch { }
            };
            authPanel.Controls.Add(btnAdmin);

            this.Controls.Add(authPanel);

            // Footer
            Label footer = new Label();
            footer.Text = "ROS REDEMPTION ONLINE // POWERED BY DEDICATED SINGAPORE VPS // ALL RIGHTS RESERVED";
            footer.Font = new Font("Segoe UI", 8.5f, FontStyle.Bold);
            footer.ForeColor = Color.FromArgb(100, 116, 139);
            footer.Location = new Point(24, 585);
            footer.Size = new Size(1012, 24);
            footer.TextAlign = ContentAlignment.MiddleCenter;
            this.Controls.Add(footer);
        }

        private void SwitchAuthTab(bool register) {
            isRegisterMode = register;
            if (register) {
                btnTabRegister.BackColor = Color.FromArgb(25, 36, 50);
                btnTabRegister.ForeColor = ValCyan;
                btnTabLogin.BackColor = Color.Transparent;
                btnTabLogin.ForeColor = ValMuted;

                lblEmailPrompt.Visible = true;
                txtEmail.Visible = true;
                chkRemember.Location = new Point(30, 268);
                btnLaunch.Text = "✨  CREATE ACCOUNT & PLAY";
            } else {
                btnTabLogin.BackColor = Color.FromArgb(25, 36, 50);
                btnTabLogin.ForeColor = ValCyan;
                btnTabRegister.BackColor = Color.Transparent;
                btnTabRegister.ForeColor = ValMuted;

                lblEmailPrompt.Visible = false;
                txtEmail.Visible = false;
                chkRemember.Location = new Point(30, 204);
                btnLaunch.Text = "▶  LAUNCH GAME";
            }
        }

        private void LoadSavedSession() {
            try {
                if (File.Exists(SessionFile)) {
                    string json = File.ReadAllText(SessionFile);
                    string u = ExtractJsonField(json, "username");
                    if (!string.IsNullOrEmpty(u)) {
                        txtUser.TextValue = u;
                        lblStatus.Text = "Welcome back, " + u + "!";
                    }
                }
            } catch { }
        }

        private void PollServerStatsAsync() {
            ThreadPool.QueueUserWorkItem((state) => {
                try {
                    Stopwatch sw = Stopwatch.StartNew();
                    HttpWebRequest req = (HttpWebRequest)WebRequest.Create(ApiUrl + "/api/health");
                    req.Timeout = 3000;
                    req.Method = "GET";

                    using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse()) {
                        sw.Stop();
                        using (StreamReader reader = new StreamReader(resp.GetResponseStream())) {
                            string raw = reader.ReadToEnd();
                            int count = ExtractJsonInt(raw, "players_online");
                            if (count <= 0) count = 1;

                            // Extract patch notes
                            List<string> notes = ExtractJsonArray(raw, "patch_notes");

                            this.BeginInvoke((MethodInvoker)delegate {
                                lblServerBadge.Text = "🟢  SINGAPORE DEDICATED (143.14.88.9) // ONLINE";
                                lblServerBadge.ForeColor = ValGreen;
                                lblPlayerCount.Text = "👥  Players In-Game: " + count;
                                lblPing.Text = "📶  Ping: " + sw.ElapsedMilliseconds + " ms";

                                if (notes.Count > 0) {
                                    StringBuilder sb = new StringBuilder();
                                    sb.AppendLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
                                    sb.AppendLine("  🔥 ROS REDEMPTION ONLINE - ACTIVE DEPLOYMENT v1.2.0");
                                    sb.AppendLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n");
                                    foreach (var n in notes) {
                                        sb.AppendLine("  " + n + "\n");
                                    }
                                    sb.AppendLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
                                    sb.AppendLine("  Singapore Dedicated Server: 143.14.88.9:30061 (Tick: 60Hz)");
                                    sb.AppendLine("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━");
                                    txtPatchNotes.Text = sb.ToString();
                                }
                            });
                        }
                    }
                } catch {
                    this.BeginInvoke((MethodInvoker)delegate {
                        lblServerBadge.Text = "🟡  CONNECTING TO VPS (143.14.88.9)...";
                        lblServerBadge.ForeColor = Color.FromArgb(250, 204, 21);
                        lblPing.Text = "📶  Ping: -- ms";
                    });
                }
            });
        }

        private void DoLaunchOnlineGame() {
            string user = txtUser.TextValue.Trim();
            string pass = txtPass.TextValue.Trim();

            if (string.IsNullOrEmpty(user) || user.Length < 2) {
                MessageBox.Show("Please enter a valid Username (at least 2 characters).", "Input Error", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            btnLaunch.Enabled = false;
            lblStatus.Text = "Authenticating with Singapore VPS...";

            ThreadPool.QueueUserWorkItem((s) => {
                try {
                    string token = "";
                    long accountId = 0;

                    // Read saved session
                    if (File.Exists(SessionFile)) {
                        string saved = File.ReadAllText(SessionFile);
                        if (ExtractJsonField(saved, "username") == user && string.IsNullOrEmpty(pass)) {
                            token = ExtractJsonField(saved, "token");
                            accountId = ExtractJsonLong(saved, "account_id");
                        }
                    }

                    if (string.IsNullOrEmpty(token)) {
                        if (string.IsNullOrEmpty(pass) || pass.Length < 8) {
                            this.BeginInvoke((MethodInvoker)delegate {
                                btnLaunch.Enabled = true;
                                lblStatus.Text = "Password must be at least 8 characters.";
                                MessageBox.Show("Please enter a password with at least 8 characters.", "Password Required", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                            });
                            return;
                        }

                        string endpoint = isRegisterMode ? "/api/register" : "/api/login";
                        string postBody = isRegisterMode 
                            ? "{\"username\":\"" + user + "\",\"password\":\"" + pass + "\",\"email\":\"" + (txtEmail.TextValue.Trim().Length > 0 ? txtEmail.TextValue.Trim() : user + "@game.net") + "\"}"
                            : "{\"identity\":\"" + user + "\",\"password\":\"" + pass + "\"}";

                        HttpWebRequest req = (HttpWebRequest)WebRequest.Create(ApiUrl + endpoint);
                        req.Method = "POST";
                        req.ContentType = "application/json";
                        req.Timeout = 8000;
                        byte[] bytes = Encoding.UTF8.GetBytes(postBody);
                        req.ContentLength = bytes.Length;
                        using (Stream os = req.GetRequestStream()) {
                            os.Write(bytes, 0, bytes.Length);
                        }

                        using (HttpWebResponse resp = (HttpWebResponse)req.GetResponse())
                        using (StreamReader sr = new StreamReader(resp.GetResponseStream())) {
                            string reply = sr.ReadToEnd();
                            token = ExtractJsonField(reply, "token");
                            accountId = ExtractJsonLong(reply, "account_id");
                        }
                    }

                    if (string.IsNullOrEmpty(token)) {
                        this.BeginInvoke((MethodInvoker)delegate {
                            btnLaunch.Enabled = true;
                            lblStatus.Text = "Authentication failed.";
                            MessageBox.Show("Could not authenticate with server. Check credentials or VPS.", "Login Failed", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        });
                        return;
                    }

                    // Save session
                    if (chkRemember.Checked) {
                        string sessJson = "{\n  \"username\": \"" + user + "\",\n  \"account_id\": " + accountId + ",\n  \"token\": \"" + token + "\"\n}";
                        File.WriteAllText(SessionFile, sessJson);
                    }

                    // Save online_servers.json
                    string srvJson = "{\n  \"servers\": [\n    {\n      \"id\": 10501,\n      \"name\": \"Singapore-Dedicated\",\n      \"port\": 30061,\n      \"host\": \"143.14.88.9\",\n      \"zone\": \"Singapore-Dedicated\"\n    }\n  ]\n}";
                    File.WriteAllText(ServerListFile, srvJson);

                    // Launch python process silently
                    string py = File.Exists(PythonwExe) ? PythonwExe : PythonExe;
                    string script = Path.Combine(BaseDir, "start_diehard_local.py");

                    ProcessStartInfo psi = new ProcessStartInfo();
                    psi.FileName = py;
                    psi.Arguments = "-u \"" + script + "\" --direct --remote-servers \"" + ServerListFile + "\" --account \"" + user + "\" --token \"" + token + "\" --account-id " + accountId;
                    psi.WorkingDirectory = BaseDir;
                    psi.EnvironmentVariables["ROS_GAME_DIR"] = BaseDir;
                    psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                    psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                    psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                    psi.UseShellExecute = false;
                    psi.CreateNoWindow = true;
                    psi.WindowStyle = ProcessWindowStyle.Hidden;

                    Process.Start(psi);

                    this.BeginInvoke((MethodInvoker)delegate {
                        lblStatus.Text = "Game Launched! Enjoy, " + user + "!";
                        btnLaunch.Enabled = true;
                        this.WindowState = FormWindowState.Minimized;
                    });
                } catch (Exception ex) {
                    this.BeginInvoke((MethodInvoker)delegate {
                        btnLaunch.Enabled = true;
                        lblStatus.Text = "Launch error.";
                        MessageBox.Show("Failed to launch game: " + ex.Message, "Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    });
                }
            });
        }

        private static string ExtractJsonField(string json, string field) {
            string pattern = "\"" + field + "\"";
            int idx = json.IndexOf(pattern);
            if (idx == -1) return "";
            int colon = json.IndexOf(":", idx);
            if (colon == -1) return "";
            int quote1 = json.IndexOf("\"", colon);
            if (quote1 == -1) return "";
            int quote2 = json.IndexOf("\"", quote1 + 1);
            if (quote2 == -1) return "";
            return json.Substring(quote1 + 1, quote2 - quote1 - 1);
        }

        private static int ExtractJsonInt(string json, string field) {
            try {
                string pattern = "\"" + field + "\"";
                int idx = json.IndexOf(pattern);
                if (idx == -1) return 0;
                int colon = json.IndexOf(":", idx);
                if (colon == -1) return 0;
                int start = colon + 1;
                while (start < json.Length && (json[start] == ' ' || json[start] == '\t')) start++;
                int end = start;
                while (end < json.Length && char.IsDigit(json[end])) end++;
                return int.Parse(json.Substring(start, end - start));
            } catch { return 0; }
        }

        private static long ExtractJsonLong(string json, string field) {
            try {
                string pattern = "\"" + field + "\"";
                int idx = json.IndexOf(pattern);
                if (idx == -1) return 0;
                int colon = json.IndexOf(":", idx);
                if (colon == -1) return 0;
                int start = colon + 1;
                while (start < json.Length && (json[start] == ' ' || json[start] == '\t')) start++;
                int end = start;
                while (end < json.Length && char.IsDigit(json[end])) end++;
                return long.Parse(json.Substring(start, end - start));
            } catch { return 0; }
        }

        private static List<string> ExtractJsonArray(string json, string field) {
            var list = new List<string>();
            try {
                string pattern = "\"" + field + "\"";
                int idx = json.IndexOf(pattern);
                if (idx == -1) return list;
                int openBracket = json.IndexOf("[", idx);
                int closeBracket = json.IndexOf("]", openBracket);
                if (openBracket == -1 || closeBracket == -1) return list;
                string inner = json.Substring(openBracket + 1, closeBracket - openBracket - 1);
                string[] parts = inner.Split(new char[] { ',' }, StringSplitOptions.RemoveEmptyEntries);
                foreach (var p in parts) {
                    string clean = p.Trim().Trim('"', '\\', ' ', '\r', '\n');
                    if (!string.IsNullOrEmpty(clean)) list.Add(clean);
                }
            } catch { }
            return list;
        }

        private void GameBrandingWatchdog() {
            IntPtr hIcon = IntPtr.Zero;
            string icoPath = Path.Combine(AppDir, "ros.ico");
            if (File.Exists(icoPath)) {
                try {
                    using (Icon icon = new Icon(icoPath, 64, 64)) {
                        hIcon = icon.Handle;
                    }
                } catch { }
            }

            while (true) {
                try {
                    Process[] rosProcs = Process.GetProcessesByName("ros64");
                    if (rosProcs != null && rosProcs.Length > 0) {
                        foreach (var proc in rosProcs) {
                            try {
                                EnumWindows((hWnd, lParam) => {
                                    uint procId;
                                    GetWindowThreadProcessId(hWnd, out procId);
                                    if (procId == proc.Id) {
                                        SetWindowText(hWnd, GAME_WINDOW_TITLE);
                                        if (hIcon != IntPtr.Zero) {
                                            SendMessage(hWnd, WM_SETICON_MSG, ICON_SMALL_IDX, (int)hIcon);
                                            SendMessage(hWnd, WM_SETICON_MSG, ICON_BIG_IDX, (int)hIcon);
                                        }
                                    }
                                    return true;
                                }, IntPtr.Zero);
                            } catch { }
                        }
                    }
                } catch { }
                Thread.Sleep(1500);
            }
        }

        [STAThread]
        public static void Main() {
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.Run(new MainForm());
        }
    }
}
