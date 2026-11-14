using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

internal sealed class PlayerLauncher : Form
{
    private static readonly Color Ink = Color.FromArgb(15, 16, 21);
    private static readonly Color Muted = Color.FromArgb(168, 175, 188);
    private static readonly Color Red = Color.FromArgb(206, 29, 46);
    private readonly string home = AppDomain.CurrentDomain.BaseDirectory;
    private readonly TextBox account = new TextBox();
    private readonly TextBox password = new TextBox();
    private bool signInAfterRegistration;
    private PlayButton play;
    private readonly Label status = new Label();
    private readonly Label state = new Label();

    [STAThread]
    private static void Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);
        using (var guard = new System.Threading.Mutex(false, @"Local\ROS-Redemption-Player-Launcher"))
        {
            if (!guard.WaitOne(0)) return;
            try
            {
                using (var window = new PlayerLauncher())
                {
                    if (Array.IndexOf(args, "--preview") >= 0)
                        window.Shown += delegate
                        {
                            window.status.Text = "Game patches are ready.";
                            window.play.Enabled = true;
                            using (var bitmap = new Bitmap(window.Width, window.Height))
                            {
                                window.DrawToBitmap(bitmap, new Rectangle(0, 0, window.Width, window.Height));
                                bitmap.Save(Path.Combine(Path.GetTempPath(), "ROS Redemption Launcher Preview.png"));
                            }
                            window.Close();
                        };
                    else window.Shown += async delegate { await window.CheckUpdates(); };
                    Application.Run(window);
                }
            }
            finally { guard.ReleaseMutex(); }
        }
    }

    public PlayerLauncher()
    {
        Text = "ROS Redemption";
        Icon = Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(1200, 720);
        FormBorderStyle = FormBorderStyle.None;
        BackColor = Ink;
        ForeColor = Color.White;
        Font = new Font("Segoe UI", 10);
        AutoScaleMode = AutoScaleMode.None;
        DoubleBuffered = true;

        var header = new Panel { Bounds = new Rectangle(1, 1, 1198, 43),
                                 BackColor = Color.FromArgb(24, 19, 22) };
        Controls.Add(header);
        header.MouseDown += DragWindow;
        LabelAt(header, "ROS", 18, 0, 78, 39, 21, Color.White, true);
        LabelAt(header, "REDEMPTION", 96, 13, 190, 25, 11, Color.FromArgb(255, 79, 82), true);
        state.Bounds = new Rectangle(760, 6, 290, 30);
        state.TextAlign = ContentAlignment.MiddleRight;
        state.ForeColor = Color.FromArgb(66, 223, 153);
        state.Text = "●   SINGAPORE PLAYTEST";
        header.Controls.Add(state);
        HeaderButton(header, "—", 1096, delegate { WindowState = FormWindowState.Minimized; });
        HeaderButton(header, "×", 1150, delegate { Close(); });

        var hero = new ArtPanel(Path.Combine(home, "launcher", "artwork.jpg"))
        {
            Bounds = new Rectangle(390, 44, 809, 570)
        };
        Controls.Add(hero);

        var sidebar = new Panel { Bounds = new Rectangle(1, 44, 389, 570),
                                  BackColor = Color.FromArgb(20, 17, 19) };
        Controls.Add(sidebar);
        LabelAt(sidebar, "●  ONLINE PLAYTEST", 30, 38, 310, 24, 10, Color.FromArgb(66, 223, 153), true);
        LabelAt(sidebar, "THE ISLAND", 26, 74, 343, 51, 32, Color.White, true);
        LabelAt(sidebar, "IS BACK.", 26, 122, 343, 51, 32, Color.FromArgb(255, 92, 85), true);
        LabelAt(sidebar, "Join the ROS Redemption playtest on\nthe Singapore server.", 31, 193, 328, 50, 12, Muted, false);
        LabelAt(sidebar, "PLAYTEST INFO", 31, 284, 320, 25, 10, Muted, true);
        InfoRow(sidebar, "01", "Game updates", "Lobby and battle patches download automatically.", 319);
        InfoRow(sidebar, "02", "Your account", null, 400);
        var createAccount = new Button
        {
            Bounds = new Rectangle(74, 438, 156, 29),
            Text = "Create account",
            TextAlign = ContentAlignment.MiddleLeft,
            FlatStyle = FlatStyle.Flat,
            BackColor = Color.FromArgb(38, 26, 30),
            ForeColor = Color.White,
            Cursor = Cursors.Hand
        };
        createAccount.FlatAppearance.BorderColor = Color.FromArgb(87, 52, 57);
        createAccount.Click += delegate { ShowRegistration(); };
        sidebar.Controls.Add(createAccount);
        InfoRow(sidebar, "03", "Install guide", "Extract the full folder, then open this launcher.", 480);

        Controls.Add(new Panel { Bounds = new Rectangle(1, 614, 1198, 1), BackColor = Red });
        var footer = new Panel { Bounds = new Rectangle(1, 615, 1198, 104),
                                 BackColor = Color.FromArgb(10, 11, 14) };
        Controls.Add(footer);
        LabelAt(footer, "R", 25, 29, 42, 52, 27, Color.FromArgb(255, 78, 78), true);
        LabelAt(footer, "ROS REDEMPTION", 77, 27, 235, 24, 12, Color.White, true);
        LabelAt(footer, "PLAYER LAUNCHER", 78, 53, 230, 23, 9, Muted, true);
        LabelAt(footer, "GAME STATUS", 388, 24, 180, 23, 10, Color.FromArgb(66, 223, 153), true);
        status.Bounds = new Rectangle(388, 51, 490, 42);
        status.Text = "Waiting to check installed patches.";
        status.ForeColor = Color.White;
        status.AutoEllipsis = true;
        footer.Controls.Add(status);
        play = new PlayButton { Bounds = new Rectangle(903, 18, 268, 60), Enabled = false };
        footer.Controls.Add(play);
        play.Click += async delegate { await Play(); };
        LabelAt(footer, "ONLINE CLIENT", 983, 82, 180, 21, 9, Muted, false);
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern bool ReleaseCapture();

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr SendMessage(IntPtr handle, int message, IntPtr parameter, IntPtr data);

    private void DragWindow(object sender, MouseEventArgs e)
    {
        if (e.Button != MouseButtons.Left) return;
        ReleaseCapture();
        SendMessage(Handle, 0xA1, new IntPtr(2), IntPtr.Zero);
    }

    private static void HeaderButton(Control parent, string text, int x, EventHandler click)
    {
        var button = new Button { Bounds = new Rectangle(x, 0, 48, 42), Text = text,
                                  FlatStyle = FlatStyle.Flat, ForeColor = Muted,
                                  BackColor = parent.BackColor };
        button.FlatAppearance.BorderSize = 0;
        button.Click += click;
        parent.Controls.Add(button);
    }

    private static void InfoRow(Control parent, string number, string title, string description, int y)
    {
        parent.Controls.Add(new Panel { Bounds = new Rectangle(32, y, 324, 1),
                                        BackColor = Color.FromArgb(62, 46, 49) });
        LabelAt(parent, number, 31, y + 13, 30, 21, 9, Color.FromArgb(254, 103, 95), true);
        LabelAt(parent, title, 70, y + 10, 282, 25, 12, Color.White, true);
        if (description != null)
            LabelAt(parent, description, 70, y + 35, 280, 40, 10, Muted, false);
    }

    private sealed class ArtPanel : Panel
    {
        private readonly Image artwork;
        public ArtPanel(string path)
        {
            DoubleBuffered = true;
            BackColor = Color.FromArgb(19, 15, 18);
            if (File.Exists(path))
                using (var original = Image.FromFile(path)) artwork = new Bitmap(original);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            if (artwork == null) return;
            float scale = Math.Max((float)Width / artwork.Width, (float)Height / artwork.Height);
            float w = artwork.Width * scale;
            float h = artwork.Height * scale;
            e.Graphics.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;
            e.Graphics.DrawImage(artwork, (Width - w) / 2, (Height - h) / 2, w, h);
        }

        protected override void Dispose(bool disposing)
        {
            if (disposing && artwork != null) artwork.Dispose();
            base.Dispose(disposing);
        }
    }

    private sealed class PlayButton : Control
    {
        public PlayButton()
        {
            DoubleBuffered = true;
            Cursor = Cursors.Hand;
            AccessibleName = "Play";
            AccessibleRole = AccessibleRole.PushButton;
            TabStop = true;
        }

        protected override void OnKeyDown(KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Space || e.KeyCode == Keys.Enter) OnClick(EventArgs.Empty);
            base.OnKeyDown(e);
        }

        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            Point[] corners = { new Point(16, 0), new Point(Width, 0), new Point(Width, Height - 16),
                                new Point(Width - 16, Height), new Point(0, Height), new Point(0, 16) };
            using (var fill = new System.Drawing.Drawing2D.LinearGradientBrush(ClientRectangle,
                   Color.FromArgb(242, 30, 47), Color.FromArgb(155, 7, 22), 90f))
                e.Graphics.FillPolygon(fill, corners);
            using (var type = new Font("Segoe UI", 17, FontStyle.Bold))
                TextRenderer.DrawText(e.Graphics, "▶   PLAY", type, ClientRectangle, Color.White,
                    TextFormatFlags.HorizontalCenter | TextFormatFlags.VerticalCenter);
            if (!Enabled && FindForm().Visible)
                using (var shade = new SolidBrush(Color.FromArgb(65, 0, 0, 0)))
                    e.Graphics.FillPolygon(shade, corners);
            if (Focused) ControlPaint.DrawFocusRectangle(e.Graphics, Rectangle.Inflate(ClientRectangle, -9, -6));
        }
    }

    private bool ReadLogin(out string username, out string secret)
    {
        username = "";
        secret = "";
        if (!signInAfterRegistration && File.Exists(Path.Combine(Game, ".online_session.json"))) return true;
        using (var dialog = new Form { Text = "Sign in to ROS Redemption", ClientSize = new Size(408, 260),
                                       StartPosition = FormStartPosition.CenterParent,
                                       FormBorderStyle = FormBorderStyle.FixedDialog, MaximizeBox = false,
                                       MinimizeBox = false, BackColor = Ink, ForeColor = Color.White })
        {
            LabelAt(dialog, "Username", 30, 27, 300, 23, 11, Muted, false);
            AddInput(dialog, account, 56);
            LabelAt(dialog, "Password", 30, 104, 300, 23, 11, Muted, false);
            AddInput(dialog, password, 133);
            password.UseSystemPasswordChar = true;
            var submit = new Button { Bounds = new Rectangle(30, 190, 296, 40), Text = "SIGN IN",
                                      BackColor = Red, ForeColor = Color.White, FlatStyle = FlatStyle.Flat,
                                      DialogResult = DialogResult.OK };
            dialog.Controls.Add(submit);
            dialog.AcceptButton = submit;
            bool accepted = dialog.ShowDialog(this) == DialogResult.OK;
            username = account.Text.Trim();
            secret = password.Text;
            password.Clear();
            dialog.Controls.Remove(account);
            dialog.Controls.Remove(password);
            return accepted && username.Length > 0 && secret.Length > 0;
        }
    }

    private void ShowRegistration()
    {
        using (var dialog = new Form
        {
            Text = "Create a ROS Redemption account",
            ClientSize = new Size(356, 342),
            StartPosition = FormStartPosition.CenterParent,
            FormBorderStyle = FormBorderStyle.FixedDialog,
            MaximizeBox = false,
            MinimizeBox = false,
            BackColor = Ink,
            ForeColor = Color.White
        })
        {
            var username = new TextBox();
            var secret = new TextBox { UseSystemPasswordChar = true };
            var confirm = new TextBox { UseSystemPasswordChar = true };
            LabelAt(dialog, "Username", 30, 20, 296, 22, 11, Muted, false);
            AddInput(dialog, username, 45);
            LabelAt(dialog, "Password (8 characters minimum)", 30, 86, 296, 22, 11, Muted, false);
            AddInput(dialog, secret, 111);
            LabelAt(dialog, "Confirm password", 30, 152, 296, 22, 11, Muted, false);
            AddInput(dialog, confirm, 177);

            var feedback = new Label { Bounds = new Rectangle(30, 217, 296, 53), ForeColor = Color.White };
            var submit = new Button
            {
                Bounds = new Rectangle(30, 280, 296, 38),
                Text = "CREATE ACCOUNT",
                BackColor = Red,
                ForeColor = Color.White,
                FlatStyle = FlatStyle.Flat
            };
            dialog.Controls.Add(feedback);
            dialog.Controls.Add(submit);
            dialog.AcceptButton = submit;
            dialog.FormClosing += delegate(object sender, FormClosingEventArgs e)
            {
                if (!submit.Enabled) e.Cancel = true;
            };
            submit.Click += async delegate
            {
                string name = username.Text.Trim();
                string pass = secret.Text.Trim();
                if (name.Length == 0 || pass.Length < 8)
                {
                    feedback.Text = "Enter a username and a password of at least 8 characters.";
                    return;
                }
                if (name.IndexOfAny(new[] {'"', '\\', '\r', '\n'}) >= 0)
                {
                    feedback.Text = "Remove quotation marks and backslashes from the username.";
                    return;
                }
                if (secret.Text != confirm.Text)
                {
                    feedback.Text = "The passwords do not match.";
                    return;
                }

                submit.Enabled = username.Enabled = secret.Enabled = confirm.Enabled = false;
                feedback.Text = "Creating your account…";
                try
                {
                    string message = "";
                    int result = await Task.Run(() => RegisterAccount(name, pass, out message));
                    if (result != 0)
                    {
                        feedback.Text = result == 2 && message.Length > 0
                            ? message
                            : "Could not create your account. Try again.";
                        return;
                    }
                    account.Text = name;
                    signInAfterRegistration = true;
                    status.Text = "Account created. Click Play to sign in.";
                    dialog.DialogResult = DialogResult.OK;
                }
                catch (Exception)
                {
                    feedback.Text = "Could not start registration. Check that the full game folder was extracted.";
                }
                finally
                {
                    submit.Enabled = username.Enabled = secret.Enabled = confirm.Enabled = true;
                    if (dialog.DialogResult == DialogResult.OK) dialog.Close();
                }
            };
            dialog.ShowDialog(this);
        }
    }

    private int RegisterAccount(string username, string secret, out string message)
    {
        // Reuse the API helper and server address in the already distributed Game folder.
        const string registration = @"
import sys
sys.path.insert(0, '.')
from connect_online import DEFAULT_API_URL, http_post

username = sys.stdin.readline().rstrip('\r\n')
password = sys.stdin.readline().rstrip('\r\n')
result = http_post(DEFAULT_API_URL + '/api/register', {'username': username, 'password': password})
if not result.get('ok'):
    print(result.get('message') or result.get('error') or 'Could not create your account.')
    sys.exit(2)
";
        var command = Command("-c \"" + registration + "\"");
        command.RedirectStandardInput = true;
        return Run(command, username + "\n" + secret, null, out message);
    }

    private static void LabelAt(Control parent, string text, int x, int y, int w, int h, int pts, Color color, bool bold)
    {
        var label = new Label { Text = text, Bounds = new Rectangle(x, y, w, h),
                                ForeColor = color, Font = new Font("Segoe UI", pts, bold ? FontStyle.Bold : FontStyle.Regular) };
        parent.Controls.Add(label);
    }

    private static void AddInput(Control parent, TextBox input, int y)
    {
        input.Bounds = new Rectangle(30, y, 296, 31);
        input.Font = new Font("Segoe UI", 13);
        input.BackColor = Color.FromArgb(37, 40, 49);
        input.ForeColor = Color.White;
        input.BorderStyle = BorderStyle.FixedSingle;
        parent.Controls.Add(input);
    }

    private string Game { get { return Path.Combine(home, "Game"); } }

    private ProcessStartInfo Command(string entry)
    {
        var psi = new ProcessStartInfo(Path.Combine(Game, "runtime", "python", "python.exe"), "-u " + entry);
        psi.WorkingDirectory = Game;
        psi.CreateNoWindow = true;
        psi.UseShellExecute = false;
        psi.RedirectStandardOutput = true;
        psi.RedirectStandardError = true;
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
        return psi;
    }

    private ProcessStartInfo OnlineCommand(string username)
    {
        // Older player packages can use the current online launcher without a second download.
        string encoded;
        using (var stream = typeof(PlayerLauncher).Assembly.GetManifestResourceStream("connect_online.py"))
        using (var script = new MemoryStream())
        {
            stream.CopyTo(script);
            encoded = Convert.ToBase64String(script.ToArray());
        }
        const string bootstrap = "import base64, os, sys; " +
            "source = base64.b64decode(sys.argv.pop(1)); " +
            "sys.argv[0] = os.path.abspath('connect_online.py'); " +
            "exec(compile(source, sys.argv[0], 'exec'), {'__name__': '__main__', '__file__': sys.argv[0]})";
        return Command("-c \"" + bootstrap + "\" " + encoded + " --launcher-input" +
                       (username.Length == 0 ? "" : " --username \"" + username + "\""));
    }

    private static int Run(ProcessStartInfo command, string input, string logPath, out string lastMessage)
    {
        using (var process = Process.Start(command))
        {
            var stdout = process.StandardOutput.ReadToEndAsync();
            var stderr = process.StandardError.ReadToEndAsync();
            if (input != null)
            {
                try
                {
                    byte[] bytes = System.Text.Encoding.UTF8.GetBytes(input + "\n");
                    process.StandardInput.BaseStream.Write(bytes, 0, bytes.Length);
                }
                catch (IOException) { }
                finally { process.StandardInput.Close(); }
            }
            process.WaitForExit();
            string errors = stderr.Result;
            string[] lines = (stdout.Result + "\n" + errors).Split(new[] {'\r', '\n'}, StringSplitOptions.RemoveEmptyEntries);
            lastMessage = lines.Length == 0 ? "" : lines[lines.Length - 1];
            if (logPath != null) File.WriteAllText(logPath, stdout.Result + errors);
            return process.ExitCode;
        }
    }

    private async Task CheckUpdates()
    {
        status.Text = "Checking for game patches...";
        if (Process.GetProcessesByName("ros64").Length > 0)
        {
            status.Text = "Close the running game before checking for updates.";
            return;
        }
        if (!File.Exists(Path.Combine(Game, "x64", "ros64.exe")))
        {
            status.Text = "Game files are missing. Extract the complete player folder.";
            return;
        }
        try
        {
            int result = await Task.Run(() =>
            {
                string message;
                return Run(Command("player_update.py"), null, null, out message);
            });
            status.Text = result == 0 ? "Game patches are ready."
                        : result == 2 ? "Update server unavailable. Installed patches verified."
                        : "Game patches could not be verified. Reopen the launcher to retry.";
            play.Enabled = result == 0 || result == 2;
        }
        catch (Exception)
        {
            status.Text = "The update check could not start. Check that the full folder was extracted.";
        }
    }

    private async Task Play()
    {
        string username, secret;
        if (!ReadLogin(out username, out secret)) return;
        if ((username.Length == 0) != (secret.Length == 0) ||
            username.IndexOfAny(new[] {'"', '\\', '\r', '\n'}) >= 0)
        {
            status.Text = "Enter both username and password, or leave both blank for saved login.";
            return;
        }
        play.Enabled = false;
        status.Text = "Connecting to ROS Redemption...";
        string report = Path.Combine(Game, "local_update", "logs", "launcher.log");
        try
        {
            var command = OnlineCommand(username);
            command.RedirectStandardInput = true;
            Directory.CreateDirectory(Path.GetDirectoryName(report));
            string message = "";
            int result = await Task.Run(() => Run(command, secret, report, out message));
            if (result == 0) signInAfterRegistration = false;
            status.Text = result == 0 ? "Game closed."
                        : message.StartsWith("Sign in") || message.StartsWith("[-]")
                          || message.StartsWith("Failed to reach") ? message
                        : "The game could not start. See Game\\local_update\\logs\\launcher.log.";
        }
        catch (Exception)
        {
            status.Text = "The game could not start. Check that the full folder was extracted.";
        }
        finally { play.Enabled = true; }
    }
}
