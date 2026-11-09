using System;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Threading;
using System.Diagnostics;

namespace RosRedemption {
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
            IntPtr db;
            if (sqlite3_open16(dbPath, out db) != 0) return false;

            IntPtr errMsg;
            int rc = sqlite3_exec(db, sql, null, IntPtr.Zero, out errMsg);
            sqlite3_close(db);
            return rc == 0;
        }
    }

    public class ServerProcessManager {
        public static Process ServerProcess = null;
        public static string PythonExe = @"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\python\python.exe";
        public static string AppDir = @"C:\Users\seanj\AppData\Local\DieHardROSHook\runtime\2026.10.28.0025-diehard25\app";
        public static string RtKey = "f7491bdbce9412b42ff5aa04a311e319d9b24c387902d85974c786fc282d5eaf";

        public static bool IsPortOpen(int port, int timeoutMs = 250) {
            try {
                using (var tcp = new TcpClient()) {
                    var ar = tcp.BeginConnect("127.0.0.1", port, null, null);
                    if (ar.AsyncWaitHandle.WaitOne(timeoutMs)) {
                        tcp.EndConnect(ar);
                        return true;
                    }
                }
            } catch {}
            return false;
        }

        public static bool StartServer() {
            if (IsPortOpen(19000)) return true;
            try {
                var psi = new ProcessStartInfo();
                psi.FileName = PythonExe;
                psi.Arguments = "start_game.pyc --server-only";
                psi.WorkingDirectory = AppDir;
                psi.EnvironmentVariables["ROS_GAME_DIR"] = @"C:\DieHardROS";
                psi.EnvironmentVariables["ROS_RT_KEY"] = RtKey;
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                psi.UseShellExecute = false;
                psi.CreateNoWindow = false;
                ServerProcess = Process.Start(psi);
                return true;
            } catch (Exception ex) {
                Console.WriteLine("[ERROR] StartServer: " + ex.Message);
                return false;
            }
        }

        public static bool StopServer() {
            try {
                if (ServerProcess != null && !ServerProcess.HasExited) {
                    ServerProcess.Kill();
                    ServerProcess = null;
                }
                foreach (var p in Process.GetProcessesByName("python")) {
                    try { p.Kill(); } catch {}
                }
                return true;
            } catch (Exception ex) {
                Console.WriteLine("[ERROR] StopServer: " + ex.Message);
                return false;
            }
        }

        public static bool LaunchClient(string account = "Admin_Redemption") {
            try {
                var psi = new ProcessStartInfo();
                psi.FileName = PythonExe;
                psi.Arguments = "start_second.pyc --account " + (string.IsNullOrEmpty(account) ? "Admin_Redemption" : account);
                psi.WorkingDirectory = AppDir;
                psi.EnvironmentVariables["ROS_GAME_DIR"] = @"C:\DieHardROS";
                psi.EnvironmentVariables["ROS_RT_KEY"] = RtKey;
                psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
                psi.EnvironmentVariables["PYTHONUNBUFFERED"] = "1";
                psi.EnvironmentVariables["PYTHONDONTWRITEBYTECODE"] = "1";
                psi.UseShellExecute = false;
                psi.CreateNoWindow = false;
                Process.Start(psi);
                return true;
            } catch (Exception ex) {
                Console.WriteLine("[ERROR] LaunchClient: " + ex.Message);
                return false;
            }
        }
    }

    public class ServerManager {
        public static string BaseDir = @"C:\DieHardROS\local_update";
        public static string ServerListFile = Path.Combine(BaseDir, "server_list_pc.txt");
        public static string ServersJsonFile = Path.Combine(BaseDir, "servers.json");
        public static string LobbyControlFile = Path.Combine(BaseDir, @"logs\lobby_control.json");
        public static string AccountsDbFile = Path.Combine(BaseDir, @"server_data\accounts.db");

        static ServerManager() {
            if (!Directory.Exists(BaseDir)) {
                BaseDir = @"c:\Users\seanj\dev";
                ServerListFile = Path.Combine(BaseDir, "server_list_pc.txt");
                ServersJsonFile = Path.Combine(BaseDir, "servers.json");
                LobbyControlFile = Path.Combine(BaseDir, "lobby_control.json");
                AccountsDbFile = Path.Combine(BaseDir, "accounts.db");
            }
        }

        public static bool IsMaintenance() {
            if (!File.Exists(ServerListFile)) return false;
            try {
                string line = File.ReadAllLines(ServerListFile)[0];
                string[] parts = line.Split(' ');
                if (parts.Length > 1) {
                    return parts[1] == "0";
                }
            } catch {}
            return false;
        }

        public static void SetMaintenance(bool maintenance, string noticeText) {
            if (File.Exists(ServerListFile)) {
                try {
                    string[] lines = File.ReadAllLines(ServerListFile);
                    for (int i = 0; i < lines.Length; i++) {
                        string[] parts = lines[i].Split(' ');
                        if (parts.Length > 6) {
                            parts[1] = maintenance ? "0" : "1";
                            parts[5] = "ROS-Redemption";
                            lines[i] = string.Join(" ", parts);
                        }
                    }
                    File.WriteAllLines(ServerListFile, lines);
                } catch (Exception ex) {
                    Console.WriteLine("[ERROR] Failed to update server_list_pc.txt: " + ex.Message);
                }
            }

            if (File.Exists(ServersJsonFile)) {
                try {
                    string json = File.ReadAllText(ServersJsonFile);
                    json = json.Replace("PH-DieHard", "ROS-Redemption");
                    json = json.Replace("PC-Rene-Baterbonia", "ROS-Redemption-Official");
                    File.WriteAllText(ServersJsonFile, json);
                } catch {}
            }

            if (File.Exists(LobbyControlFile)) {
                try {
                    string content = File.ReadAllText(LobbyControlFile);
                    string enabledStr = maintenance ? "\"enabled\":true" : "\"enabled\":false";
                    string escapedText = (noticeText ?? "").Replace("\"", "\\\"");
                    string textStr = "\"text\":\"" + escapedText + "\"";
                    string titleStr = "\"title\":\"ROS REDEMPTION NOTICE\"";
                    
                    int noticeIdx = content.IndexOf("\"notice\":");
                    if (noticeIdx >= 0) {
                        int endBrace = content.IndexOf("}", noticeIdx);
                        if (endBrace > noticeIdx) {
                            string newNotice = "\"notice\":{" + enabledStr + "," + textStr + "," + titleStr + "}";
                            content = content.Substring(0, noticeIdx) + newNotice + content.Substring(endBrace + 1);
                            File.WriteAllText(LobbyControlFile, content);
                        }
                    }
                } catch (Exception ex) {
                    Console.WriteLine("[ERROR] Failed to update lobby_control.json: " + ex.Message);
                }
            }
        }

        public static void TopUp(long gid, long addGp, long addDiamonds) {
            var rows = WinSqlite.Query(AccountsDbFile, "SELECT gid, gp, payYuanbao FROM wallets WHERE gid=" + gid + ";");
            if (rows.Count == 0) {
                string insertSql = string.Format("INSERT INTO wallets (gid, gp, sp, freeYuanbao, payYuanbao) VALUES ({0}, {1}, 0, {2}, {2});",
                    gid, Math.Max(0, addGp), Math.Max(0, addDiamonds));
                WinSqlite.Exec(AccountsDbFile, insertSql);
            } else {
                string updateSql = string.Format("UPDATE wallets SET gp = MAX(0, gp + {0}), freeYuanbao = MAX(0, freeYuanbao + {1}), payYuanbao = MAX(0, payYuanbao + {1}) WHERE gid={2};",
                    addGp, addDiamonds, gid);
                WinSqlite.Exec(AccountsDbFile, updateSql);
            }
        }

        public static void SendMail(long targetGid, string title, string content, string sender, long diamonds, long gold) {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            long deadline = now + (30 * 86400);
            
            string cleanTitle = (title ?? "System Mail").Replace("'", "''");
            string cleanContent = (content ?? "").Replace("'", "''");
            string cleanSender = (sender ?? "ROS Redemption Admin").Replace("'", "''");

            string propsJson = "[]";
            if (diamonds > 0 || gold > 0) {
                propsJson = string.Format("[{{\\\"type\\\":\\\"currency\\\",\\\"gp\\\":{0},\\\"payYuanbao\\\":{1},\\\"freeYuanbao\\\":{1}}}]", gold, diamonds);
            }

            if (targetGid == 0) {
                var chars = WinSqlite.Query(AccountsDbFile, "SELECT gid FROM characters;");
                foreach (var c in chars) {
                    long gid = long.Parse(c["gid"]);
                    string sql = string.Format(
                        "INSERT INTO mails (gid, type, title, content, sender, sender_gid, props, created, deadline, unread, deleted) " +
                        "VALUES ({0}, 0, '{1}', '{2}', '{3}', 0, '{4}', {5}, {6}, 1, 0);",
                        gid, cleanTitle, cleanContent, cleanSender, propsJson, now, deadline);
                    WinSqlite.Exec(AccountsDbFile, sql);
                    if (diamonds > 0 || gold > 0) {
                        TopUp(gid, gold, diamonds);
                    }
                }
            } else {
                string sql = string.Format(
                    "INSERT INTO mails (gid, type, title, content, sender, sender_gid, props, created, deadline, unread, deleted) " +
                    "VALUES ({0}, 0, '{1}', '{2}', '{3}', 0, '{4}', {5}, {6}, 1, 0);",
                    targetGid, cleanTitle, cleanContent, cleanSender, propsJson, now, deadline);
                WinSqlite.Exec(AccountsDbFile, sql);
                if (diamonds > 0 || gold > 0) {
                    TopUp(targetGid, gold, diamonds);
                }
            }
        }

        public static void CreateAccountAndChar(string username, string nickname, long diamonds, long gold) {
            long now = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
            string cleanUser = (username ?? "player1").Trim().Replace("'", "''");
            string cleanNick = (nickname ?? cleanUser).Trim().Replace("'", "''");

            string accSql = string.Format("INSERT OR IGNORE INTO accounts (username, created, last_login, last_server, banned, note) VALUES ('{0}', {1}, {1}, 10501, 0, 'ROS Redemption');", cleanUser, now);
            WinSqlite.Exec(AccountsDbFile, accSql);

            var accRows = WinSqlite.Query(AccountsDbFile, "SELECT id FROM accounts WHERE username='" + cleanUser + "';");
            if (accRows.Count == 0) return;
            long accId = long.Parse(accRows[0]["id"]);

            long gid = 10000000 + accId;

            string charSql = string.Format(
                "INSERT OR IGNORE INTO characters (gid, account_id, server_id, nickname, character_type, created, base_level, level, lobby, created_at, last_login) " +
                "VALUES ({0}, {1}, 10501, '{2}', 10002, 1, 1, 1, '{{}}', {3}, {3});",
                gid, accId, cleanNick, now);
            WinSqlite.Exec(AccountsDbFile, charSql);

            TopUp(gid, gold, diamonds);
        }

        public static void SetBan(long accountId, bool ban, string reason) {
            string cleanReason = (reason ?? "Rule violation").Replace("'", "''");
            int banFlag = ban ? 1 : 0;
            long until = ban ? DateTimeOffset.UtcNow.ToUnixTimeSeconds() + (365 * 86400) : 0;
            string sql = string.Format("UPDATE accounts SET banned = {0}, ban_reason = '{1}', ban_until = {2} WHERE id = {3};",
                banFlag, cleanReason, until, accountId);
            WinSqlite.Exec(AccountsDbFile, sql);
        }
    }

    public class TcpWebServer {
        private TcpListener _listener;
        private int _port;
        private bool _running;

        public TcpWebServer(int port) {
            _port = port;
            _listener = new TcpListener(IPAddress.Loopback, _port);
        }

        public void Start() {
            _listener.Start();
            _running = true;
            Console.WriteLine("[INFO] ROS Redemption Web Controller listening on http://127.0.0.1:" + _port);
            ThreadPool.QueueUserWorkItem((o) => {
                while (_running) {
                    try {
                        var client = _listener.AcceptTcpClient();
                        ThreadPool.QueueUserWorkItem((c) => HandleClient((TcpClient)c), client);
                    } catch {}
                }
            });
        }

        private void HandleClient(TcpClient client) {
            try {
                using (var stream = client.GetStream()) {
                    var reader = new StreamReader(stream, Encoding.UTF8);
                    string reqLine = reader.ReadLine();
                    if (string.IsNullOrEmpty(reqLine)) return;

                    string[] reqParts = reqLine.Split(' ');
                    if (reqParts.Length < 2) return;
                    string method = reqParts[0].ToUpper();
                    string path = reqParts[1];

                    int contentLength = 0;
                    string header;
                    while (!string.IsNullOrEmpty(header = reader.ReadLine())) {
                        if (header.StartsWith("Content-Length:", StringComparison.OrdinalIgnoreCase)) {
                            int.TryParse(header.Substring(15).Trim(), out contentLength);
                        }
                    }

                    string body = "";
                    if (contentLength > 0) {
                        char[] buf = new char[contentLength];
                        int read = 0;
                        while (read < contentLength) {
                            int r = reader.Read(buf, read, contentLength - read);
                            if (r <= 0) break;
                            read += r;
                        }
                        body = new string(buf, 0, read);
                    }

                    ProcessRoute(stream, method, path, body);
                }
            } catch {}
            finally {
                try { client.Close(); } catch {}
            }
        }

        private void ProcessRoute(NetworkStream stream, string method, string path, string body) {
            if (path == "/" || path == "/index.html") {
                byte[] html = Encoding.UTF8.GetBytes(HtmlContent.GetPage());
                SendResponse(stream, "200 OK", "text/html; charset=utf-8", html);
                return;
            }

            if (path == "/api/status" && method == "GET") {
                bool maintenance = ServerManager.IsMaintenance();
                var accounts = WinSqlite.Query(ServerManager.AccountsDbFile, "SELECT COUNT(*) as cnt FROM accounts;");
                var chars = WinSqlite.Query(ServerManager.AccountsDbFile, "SELECT COUNT(*) as cnt FROM characters;");
                var mails = WinSqlite.Query(ServerManager.AccountsDbFile, "SELECT COUNT(*) as cnt FROM mails;");
                var walletStats = WinSqlite.Query(ServerManager.AccountsDbFile, "SELECT SUM(gp) as total_gp, SUM(payYuanbao) as total_diamonds FROM wallets;");

                string totalAccounts = accounts.Count > 0 ? accounts[0]["cnt"] : "0";
                string totalChars = chars.Count > 0 ? chars[0]["cnt"] : "0";
                string totalMails = mails.Count > 0 ? mails[0]["cnt"] : "0";
                string totalGp = (walletStats.Count > 0 && walletStats[0]["total_gp"] != "") ? walletStats[0]["total_gp"] : "0";
                string totalDiamonds = (walletStats.Count > 0 && walletStats[0]["total_diamonds"] != "") ? walletStats[0]["total_diamonds"] : "0";

                bool gameServerUp = ServerProcessManager.IsPortOpen(19000);
                bool adminUp = ServerProcessManager.IsPortOpen(8790);

                string json = string.Format(
                    "{{\"serverName\":\"ROS Redemption\",\"status\":\"{0}\",\"maintenance\":{1},\"accounts\":{2},\"characters\":{3},\"mails\":{4},\"totalGold\":{5},\"totalDiamonds\":{6},\"gameServerUp\":{7},\"adminUp\":{8}}}",
                    maintenance ? "MAINTENANCE" : (gameServerUp ? "ONLINE" : "STANDBY"),
                    maintenance ? "true" : "false",
                    totalAccounts, totalChars, totalMails, totalGp, totalDiamonds,
                    gameServerUp ? "true" : "false", adminUp ? "true" : "false");

                SendResponse(stream, "200 OK", "application/json; charset=utf-8", Encoding.UTF8.GetBytes(json));
                return;
            }

            if (path == "/api/server_ctrl" && method == "POST") {
                string action = GetJsonString(body, "action");
                if (action == "start") {
                    bool ok = ServerProcessManager.StartServer();
                    SendResponse(stream, "200 OK", "application/json", Encoding.UTF8.GetBytes("{\"success\":" + (ok ? "true" : "false") + "}"));
                    return;
                }
                if (action == "stop") {
                    bool ok = ServerProcessManager.StopServer();
                    SendResponse(stream, "200 OK", "application/json", Encoding.UTF8.GetBytes("{\"success\":" + (ok ? "true" : "false") + "}"));
                    return;
                }
                if (action == "launch_client") {
                    string acc = GetJsonString(body, "account") ?? "Admin_Redemption";
                    bool ok = ServerProcessManager.LaunchClient(acc);
                    SendResponse(stream, "200 OK", "application/json", Encoding.UTF8.GetBytes("{\"success\":" + (ok ? "true" : "false") + "}"));
                    return;
                }
            }

            if (path == "/api/players" && method == "GET") {
                string sql = @"SELECT c.gid, c.nickname, c.level, c.last_login, a.id as account_id, a.username, a.banned, a.ban_reason,
                               IFNULL(w.gp, 0) as gp, IFNULL(w.payYuanbao, 0) as diamonds 
                               FROM characters c 
                               JOIN accounts a ON c.account_id = a.id 
                               LEFT JOIN wallets w ON c.gid = w.gid 
                               ORDER BY c.gid DESC LIMIT 100;";
                var list = WinSqlite.Query(ServerManager.AccountsDbFile, sql);
                StringBuilder sb = new StringBuilder("[");
                for (int i = 0; i < list.Count; i++) {
                    var r = list[i];
                    sb.Append(string.Format(
                        "{{\"gid\":{0},\"nickname\":\"{1}\",\"level\":{2},\"accountId\":{3},\"username\":\"{4}\",\"banned\":{5},\"banReason\":\"{6}\",\"gp\":{7},\"diamonds\":{8}}}",
                        r["gid"], r["nickname"], r["level"], r["account_id"], r["username"], r["banned"] == "1" ? "true" : "false", r["ban_reason"], r["gp"], r["diamonds"]));
                    if (i < list.Count - 1) sb.Append(",");
                }
                sb.Append("]");
                SendResponse(stream, "200 OK", "application/json; charset=utf-8", Encoding.UTF8.GetBytes(sb.ToString()));
                return;
            }

            if (path == "/api/mails" && method == "GET") {
                string sql = @"SELECT m.id, m.gid, m.title, m.content, m.sender, m.created, m.unread, c.nickname 
                               FROM mails m 
                               LEFT JOIN characters c ON m.gid = c.gid 
                               ORDER BY m.id DESC LIMIT 50;";
                var list = WinSqlite.Query(ServerManager.AccountsDbFile, sql);
                StringBuilder sb = new StringBuilder("[");
                for (int i = 0; i < list.Count; i++) {
                    var r = list[i];
                    sb.Append(string.Format(
                        "{{\"id\":{0},\"gid\":{1},\"nickname\":\"{2}\",\"title\":\"{3}\",\"content\":\"{4}\",\"sender\":\"{5}\",\"created\":{6},\"unread\":{7}}}",
                        r["id"], r["gid"], r["nickname"], r["title"], r["content"], r["sender"], r["created"], r["unread"] == "1" ? "true" : "false"));
                    if (i < list.Count - 1) sb.Append(",");
                }
                sb.Append("]");
                SendResponse(stream, "200 OK", "application/json; charset=utf-8", Encoding.UTF8.GetBytes(sb.ToString()));
                return;
            }

            if (method == "POST") {
                if (path == "/api/maintenance") {
                    bool maintenance = body.Contains("\"maintenance\":true");
                    string notice = "ROS Redemption is currently under maintenance. We are patching bugs and optimizing performance!";
                    int textIdx = body.IndexOf("\"notice\":\"");
                    if (textIdx >= 0) {
                        int end = body.IndexOf("\"", textIdx + 10);
                        if (end > textIdx) {
                            notice = body.Substring(textIdx + 10, end - (textIdx + 10));
                        }
                    }
                    ServerManager.SetMaintenance(maintenance, notice);
                    SendResponse(stream, "200 OK", "application/json", Encoding.UTF8.GetBytes("{\"success\":true,\"maintenance\":" + (maintenance ? "true" : "false") + "}"));
                    return;
                }

                if (path == "/api/topup") {
                    long gid = GetJsonLong(body, "gid");
                    long gp = GetJsonLong(body, "gp");
                    long diamonds = GetJsonLong(body, "diamonds");

                    ServerManager.TopUp(gid, gp, diamonds);
                    SendResponse(stream, "200 OK", "application/json", Encoding.UTF8.GetBytes("{\"success\":true,\"message\":\"Top-up successful!\"}"));
                    return;
                }

                if (path == "/api/sendmail") {
                    long targetGid = GetJsonLong(body, "targetGid");
                    string title = GetJsonString(body, "title") ?? "System Rewards";
                    string content = GetJsonString(body, "content") ?? "Enjoy your ROS Redemption rewards!";
                    string sender = GetJsonString(body, "sender") ?? "ROS Redemption Admin";
                    long diamonds = GetJsonLong(body, "diamonds");
                    long gold = GetJsonLong(body, "gold");

                    ServerManager.SendMail(targetGid, title, content, sender, diamonds, gold);
                    SendResponse(stream, "200 OK", "application/json", Encoding.UTF8.GetBytes("{\"success\":true,\"message\":\"Mail dispatched successfully!\"}"));
                    return;
                }

                if (path == "/api/ban") {
                    long accountId = GetJsonLong(body, "accountId");
                    bool ban = body.Contains("\"banned\":true");
                    string reason = GetJsonString(body, "reason") ?? "Violation of Server Rules";

                    ServerManager.SetBan(accountId, ban, reason);
                    SendResponse(stream, "200 OK", "application/json", Encoding.UTF8.GetBytes("{\"success\":true,\"message\":\"Ban status updated!\"}"));
                    return;
                }

                if (path == "/api/create_player") {
                    string username = GetJsonString(body, "username") ?? "Player" + new Random().Next(100, 999);
                    string nickname = GetJsonString(body, "nickname") ?? username;
                    long diamonds = GetJsonLong(body, "diamonds");
                    long gold = GetJsonLong(body, "gold");

                    ServerManager.CreateAccountAndChar(username, nickname, diamonds, gold);
                    SendResponse(stream, "200 OK", "application/json", Encoding.UTF8.GetBytes("{\"success\":true,\"message\":\"Player created successfully!\"}"));
                    return;
                }
            }

            byte[] notFound = Encoding.UTF8.GetBytes("{\"error\":\"Not Found\"}");
            SendResponse(stream, "404 Not Found", "application/json", notFound);
        }

        private static void SendResponse(NetworkStream stream, string status, string contentType, byte[] data) {
            string header = string.Format(
                "HTTP/1.1 {0}\r\nContent-Type: {1}\r\nContent-Length: {2}\r\nConnection: close\r\nAccess-Control-Allow-Origin: *\r\n\r\n",
                status, contentType, data.Length);
            byte[] headerBytes = Encoding.UTF8.GetBytes(header);
            stream.Write(headerBytes, 0, headerBytes.Length);
            stream.Write(data, 0, data.Length);
            stream.Flush();
        }

        private static string GetJsonString(string json, string key) {
            string pattern = "\"" + key + "\":\"";
            int idx = json.IndexOf(pattern);
            if (idx < 0) return null;
            int start = idx + pattern.Length;
            int end = json.IndexOf("\"", start);
            if (end < 0) return null;
            return json.Substring(start, end - start);
        }

        private static long GetJsonLong(string json, string key) {
            string pattern = "\"" + key + "\":";
            int idx = json.IndexOf(pattern);
            if (idx < 0) return 0;
            int start = idx + pattern.Length;
            int end = json.IndexOfAny(new char[] { ',', '}', ' ' }, start);
            if (end < 0) end = json.Length;
            string numStr = json.Substring(start, end - start).Trim().Replace("\"", "");
            long val;
            long.TryParse(numStr, out val);
            return val;
        }
    }

    public static class HtmlContent {
        public static string GetPage() {
            return @"<!DOCTYPE html>
<html lang=""en"">
<head>
    <meta charset=""UTF-8"">
    <meta name=""viewport"" content=""width=device-width, initial-scale=1.0"">
    <title>ROS Redemption - Master Server Controller</title>
    <style>
        :root {
            --bg-base: #0a0d14;
            --bg-card: #131824;
            --bg-card-alt: #1c2333;
            --border: #28334a;
            --accent: #ff4757;
            --accent-glow: rgba(255, 71, 87, 0.35);
            --gold: #ffa502;
            --gold-glow: rgba(255, 165, 2, 0.3);
            --cyan: #00d2d3;
            --green: #2ed573;
            --text-main: #f1f2f6;
            --text-muted: #8395a7;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
        body { background: var(--bg-base); color: var(--text-main); line-height: 1.5; padding: 20px; }
        .container { max-width: 1350px; margin: 0 auto; }
        
        header {
            display: flex; justify-content: space-between; align-items: center;
            background: linear-gradient(135deg, #182030, #111622);
            padding: 20px 28px; border-radius: 12px; border: 1px solid var(--border);
            margin-bottom: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.4);
        }
        .brand h1 { font-size: 26px; font-weight: 800; letter-spacing: 1px; color: #fff; }
        .brand h1 span { color: var(--accent); }
        .brand p { font-size: 13px; color: var(--text-muted); }

        .ctrl-bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
        .btn {
            background: var(--bg-card-alt); color: #fff; border: 1px solid var(--border);
            padding: 9px 16px; border-radius: 6px; font-size: 13px; font-weight: 600;
            cursor: pointer; transition: all 0.2s ease; display: inline-flex; align-items: center; gap: 8px;
        }
        .btn:hover { border-color: var(--cyan); box-shadow: 0 0 10px rgba(0, 210, 211, 0.3); }
        .btn-primary { background: linear-gradient(135deg, #ff4757, #c0392b); border: none; }
        .btn-primary:hover { box-shadow: 0 0 15px var(--accent-glow); transform: translateY(-1px); }
        .btn-green { background: linear-gradient(135deg, #2ed573, #26af5f); border: none; }
        .btn-green:hover { box-shadow: 0 0 15px rgba(46, 213, 115, 0.4); }
        .btn-gold { background: linear-gradient(135deg, #ffa502, #e67e22); border: none; color: #000; }
        .btn-gold:hover { box-shadow: 0 0 15px var(--gold-glow); }
        .btn-outline { background: transparent; border: 1px solid var(--border); }

        .stats-grid {
            display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
            gap: 16px; margin-bottom: 24px;
        }
        .stat-card {
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 10px; padding: 18px; position: relative; overflow: hidden;
        }
        .stat-card::before {
            content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%;
            background: var(--accent);
        }
        .stat-card.gold::before { background: var(--gold); }
        .stat-card.green::before { background: var(--green); }
        .stat-card.cyan::before { background: var(--cyan); }
        .stat-title { font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: var(--text-muted); }
        .stat-value { font-size: 26px; font-weight: 700; margin-top: 6px; }

        .main-layout { display: grid; grid-template-columns: 2fr 1fr; gap: 24px; }
        @media(max-width: 1000px) { .main-layout { grid-template-columns: 1fr; } }

        .panel {
            background: var(--bg-card); border: 1px solid var(--border);
            border-radius: 12px; padding: 22px; margin-bottom: 24px;
        }
        .panel-header {
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid var(--border); padding-bottom: 14px; margin-bottom: 18px;
        }
        .panel-header h2 { font-size: 17px; font-weight: 700; color: #fff; }

        .form-group { margin-bottom: 14px; }
        .form-group label { display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px; }
        .form-control {
            width: 100%; background: var(--bg-base); border: 1px solid var(--border);
            border-radius: 6px; padding: 9px 12px; color: #fff; font-size: 13px;
        }
        .form-control:focus { outline: none; border-color: var(--accent); }
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

        table { width: 100%; border-collapse: collapse; font-size: 13px; }
        th { text-align: left; padding: 10px 12px; color: var(--text-muted); border-bottom: 1px solid var(--border); }
        td { padding: 12px; border-bottom: 1px solid #1a2233; }
        tr:hover td { background: var(--bg-card-alt); }
        .badge {
            display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 700;
        }
        .badge-active { background: rgba(46, 213, 115, 0.15); color: var(--green); }
        .badge-banned { background: rgba(255, 71, 87, 0.15); color: var(--accent); }
        .badge-maint { background: rgba(255, 165, 2, 0.15); color: var(--gold); }
    </style>
</head>
<body>
    <div class=""container"">
        <header>
            <div class=""brand"">
                <h1>ROS <span>REDEMPTION</span></h1>
                <p>Master Dedicated Server Controller &bull; Rules of Survival Private Revive</p>
            </div>
            <div class=""ctrl-bar"">
                <button class=""btn btn-green"" onclick=""serverAction('start')"">▶ Start Server</button>
                <button class=""btn btn-outline"" onclick=""serverAction('stop')"">⏹ Stop Server</button>
                <button class=""btn btn-primary"" onclick=""serverAction('launch_client')"">🎮 Launch Game</button>
                <a href=""http://127.0.0.1:8790/admin"" target=""_blank"" class=""btn btn-gold"" style=""text-decoration:none;"">⚙ Advanced Admin</a>
            </div>
        </header>

        <div class=""stats-grid"">
            <div class=""stat-card cyan"">
                <div class=""stat-title"">Server Status</div>
                <div class=""stat-value"" id=""statStatus"">CONNECTING...</div>
            </div>
            <div class=""stat-card green"">
                <div class=""stat-title"">Characters Active</div>
                <div class=""stat-value"" id=""statChars"">0</div>
            </div>
            <div class=""stat-card gold"">
                <div class=""stat-title"">Total Diamonds in Economy</div>
                <div class=""stat-value"" id=""statDia"">0 💎</div>
            </div>
            <div class=""stat-card"">
                <div class=""stat-title"">Total Gold in Economy</div>
                <div class=""stat-value"" id=""statGold"">0 🪙</div>
            </div>
        </div>

        <div class=""main-layout"">
            <div>
                <!-- PLAYERS TABLE -->
                <div class=""panel"">
                    <div class=""panel-header"">
                        <h2>Registered Accounts & Characters</h2>
                        <button class=""btn btn-outline"" onclick=""loadPlayers()"">🔄 Refresh List</button>
                    </div>
                    <div style=""overflow-x:auto;"">
                        <table>
                            <thead>
                                <tr>
                                    <th>GID</th>
                                    <th>Nickname</th>
                                    <th>Level</th>
                                    <th>Account UID</th>
                                    <th>Diamonds</th>
                                    <th>Gold</th>
                                    <th>Status</th>
                                    <th>Action</th>
                                </tr>
                            </thead>
                            <tbody id=""playerList"">
                                <tr><td colspan=""8"" style=""text-align:center;"">Loading characters...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- MAIL LOG -->
                <div class=""panel"">
                    <div class=""panel-header"">
                        <h2>In-Game Mail System Log</h2>
                        <button class=""btn btn-outline"" onclick=""loadMails()"">🔄 Refresh Mails</button>
                    </div>
                    <div style=""overflow-x:auto;"">
                        <table>
                            <thead>
                                <tr>
                                    <th>Mail ID</th>
                                    <th>Recipient</th>
                                    <th>Subject</th>
                                    <th>Sender</th>
                                    <th>State</th>
                                </tr>
                            </thead>
                            <tbody id=""mailList"">
                                <tr><td colspan=""5"" style=""text-align:center;"">Loading mailbox...</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>

            <div>
                <!-- MAINTENANCE MODE -->
                <div class=""panel"">
                    <div class=""panel-header"">
                        <h2>Maintenance Control</h2>
                        <span id=""maintBadge"" class=""badge badge-active"">ONLINE</span>
                    </div>
                    <div class=""form-group"">
                        <label>Maintenance Broadcast Notice</label>
                        <textarea id=""maintNotice"" class=""form-control"" rows=""3"">ROS Redemption is currently under maintenance. We are patching bugs and optimizing servers. Stay tuned!</textarea>
                    </div>
                    <div style=""display:flex; gap:10px;"">
                        <button class=""btn btn-primary"" style=""flex:1;"" onclick=""toggleMaintenance(true)"">Enable Maintenance</button>
                        <button class=""btn btn-green"" style=""flex:1;"" onclick=""toggleMaintenance(false)"">End Maintenance</button>
                    </div>
                </div>

                <!-- TOP-UP MANAGER -->
                <div class=""panel"">
                    <div class=""panel-header"">
                        <h2>Instant Top-Up (Currencies)</h2>
                    </div>
                    <div class=""form-group"">
                        <label>Target Character</label>
                        <select id=""topupTarget"" class=""form-control"">
                            <option value="""">Select Player...</option>
                        </select>
                    </div>
                    <div class=""form-group"">
                        <label>Current Character Balance</label>
                        <input id=""topupBalanceView"" class=""form-control"" readonly value=""-- Select Player --"" style=""color:var(--gold);"">
                    </div>
                    <div class=""form-row"">
                        <div class=""form-group"">
                            <label>Add Diamonds (payYuanbao)</label>
                            <input type=""number"" id=""topupDiamonds"" class=""form-control"" value=""5000"">
                        </div>
                        <div class=""form-group"">
                            <label>Add Gold (gp)</label>
                            <input type=""number"" id=""topupGold"" class=""form-control"" value=""50000"">
                        </div>
                    </div>
                    <div style=""display:flex; gap:6px; margin-bottom:14px;"">
                        <button class=""btn btn-outline"" style=""font-size:11px; padding:4px 8px;"" onclick=""setTopupPreset(2500, 20000)"">+Starter Pack</button>
                        <button class=""btn btn-outline"" style=""font-size:11px; padding:4px 8px;"" onclick=""setTopupPreset(10000, 100000)"">+VIP Pack</button>
                        <button class=""btn btn-outline"" style=""font-size:11px; padding:4px 8px;"" onclick=""setTopupPreset(50000, 500000)"">+Whale Pack</button>
                    </div>
                    <button class=""btn btn-gold"" style=""width:100%;"" onclick=""submitTopup()"">⚡ Grant Currencies Now</button>
                </div>

                <!-- DISPATCH MAIL -->
                <div class=""panel"">
                    <div class=""panel-header"">
                        <h2>Send In-Game Mail & Rewards</h2>
                    </div>
                    <div class=""form-group"">
                        <label>Recipient</label>
                        <select id=""mailTarget"" class=""form-control"">
                            <option value=""0"">📢 Broadcast to ALL Registered Players</option>
                        </select>
                    </div>
                    <div class=""form-group"">
                        <label>Mail Subject</label>
                        <input type=""text"" id=""mailTitle"" class=""form-control"" value=""Welcome to ROS Redemption!"">
                    </div>
                    <div class=""form-group"">
                        <label>Mail Body Message</label>
                        <textarea id=""mailContent"" class=""form-control"" rows=""2"">Thank you for playing ROS Redemption private server! Enjoy these starter gifts.</textarea>
                    </div>
                    <div class=""form-group"">
                        <label>Sender Name</label>
                        <input type=""text"" id=""mailSender"" class=""form-control"" value=""ROS Redemption HQ"">
                    </div>
                    <div class=""form-row"">
                        <div class=""form-group"">
                            <label>Attach Diamonds</label>
                            <input type=""number"" id=""mailDiamonds"" class=""form-control"" value=""1000"">
                        </div>
                        <div class=""form-group"">
                            <label>Attach Gold</label>
                            <input type=""number"" id=""mailGold"" class=""form-control"" value=""25000"">
                        </div>
                    </div>
                    <button class=""btn btn-primary"" style=""width:100%;"" onclick=""sendMail()"">✉ Dispatch In-Game Mail</button>
                </div>

                <!-- QUICK ACCOUNT GEN -->
                <div class=""panel"">
                    <div class=""panel-header"">
                        <h2>Create New Player Profile</h2>
                    </div>
                    <div class=""form-row"">
                        <div class=""form-group"">
                            <label>Account Login UID</label>
                            <input type=""text"" id=""newUsername"" class=""form-control"" placeholder=""player002"">
                        </div>
                        <div class=""form-group"">
                            <label>Character In-Game Name</label>
                            <input type=""text"" id=""newNickname"" class=""form-control"" placeholder=""SniperElite"">
                        </div>
                    </div>
                    <div class=""form-row"">
                        <div class=""form-group"">
                            <label>Initial Diamonds</label>
                            <input type=""number"" id=""newDiamonds"" class=""form-control"" value=""10000"">
                        </div>
                        <div class=""form-group"">
                            <label>Initial Gold</label>
                            <input type=""number"" id=""newGold"" class=""form-control"" value=""100000"">
                        </div>
                    </div>
                    <button class=""btn btn-green"" style=""width:100%;"" onclick=""createPlayer()"">+ Create Account & Character</button>
                </div>
            </div>
        </div>
    </div>

    <script>
        let cachedPlayers = [];

        async function serverAction(action) {
            try {
                const res = await fetch('/api/server_ctrl', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ action: action, account: 'Admin_Redemption' })
                });
                const d = await res.json();
                if (d.success) {
                    alert('Action executed: ' + action);
                } else {
                    alert('Failed to execute: ' + action);
                }
                setTimeout(refreshStatus, 1500);
            } catch (err) {
                alert('Error connecting to controller: ' + err);
            }
        }

        async function refreshStatus() {
            try {
                const res = await fetch('/api/status');
                const data = await res.json();

                const statusEl = document.getElementById('statStatus');
                const maintBadge = document.getElementById('maintBadge');
                
                if (data.maintenance) {
                    statusEl.innerText = 'MAINTENANCE';
                    statusEl.style.color = 'var(--gold)';
                    maintBadge.innerText = 'MAINTENANCE MODE';
                    maintBadge.className = 'badge badge-maint';
                } else if (data.gameServerUp) {
                    statusEl.innerText = 'ONLINE (Port 19000)';
                    statusEl.style.color = 'var(--green)';
                    maintBadge.innerText = 'SERVER ONLINE';
                    maintBadge.className = 'badge badge-active';
                } else {
                    statusEl.innerText = 'STANDBY (Server Stopped)';
                    statusEl.style.color = 'var(--accent)';
                    maintBadge.innerText = 'STANDBY';
                    maintBadge.className = 'badge badge-banned';
                }

                document.getElementById('statChars').innerText = data.characters;
                document.getElementById('statDia').innerText = Number(data.totalDiamonds).toLocaleString() + ' 💎';
                document.getElementById('statGold').innerText = Number(data.totalGold).toLocaleString() + ' 🪙';
            } catch (err) {
                document.getElementById('statStatus').innerText = 'OFFLINE';
            }
        }

        async function loadPlayers() {
            try {
                const res = await fetch('/api/players');
                cachedPlayers = await res.json();

                const topupTarget = document.getElementById('topupTarget');
                const mailTarget = document.getElementById('mailTarget');
                topupTarget.innerHTML = '<option value="""">Select Player...</option>';
                mailTarget.innerHTML = '<option value=""0"">📢 Broadcast to ALL Registered Players</option>';

                const tbody = document.getElementById('playerList');
                if (cachedPlayers.length === 0) {
                    tbody.innerHTML = '<tr><td colspan=""8"" style=""text-align:center; color:var(--text-muted);"">No characters created yet. Use Quick Generator!</td></tr>';
                    return;
                }

                tbody.innerHTML = '';
                cachedPlayers.forEach(p => {
                    topupTarget.innerHTML += `<option value=""${p.gid}"">${p.nickname} (GID: ${p.gid})</option>`;
                    mailTarget.innerHTML += `<option value=""${p.gid}"">${p.nickname} (GID: ${p.gid})</option>`;

                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td><strong>${p.gid}</strong></td>
                        <td>${p.nickname}</td>
                        <td>Lv. ${p.level}</td>
                        <td>${p.username}</td>
                        <td style=""color:var(--gold);"">${Number(p.diamonds).toLocaleString()} 💎</td>
                        <td>${Number(p.gp).toLocaleString()} 🪙</td>
                        <td><span class=""badge ${p.banned ? 'badge-banned' : 'badge-active'}"">${p.banned ? 'BANNED' : 'ACTIVE'}</span></td>
                        <td>
                            <button class=""btn btn-outline"" style=""padding:4px 8px; font-size:12px;"" onclick=""toggleBan(${p.accountId}, ${!p.banned})"">
                                ${p.banned ? 'Unban' : 'Ban'}
                            </button>
                        </td>
                    `;
                    tbody.appendChild(row);
                });
            } catch (err) {
                console.error('Failed to load players:', err);
            }
        }

        async function loadMails() {
            try {
                const res = await fetch('/api/mails');
                const list = await res.json();
                const tbody = document.getElementById('mailList');
                if (list.length === 0) {
                    tbody.innerHTML = '<tr><td colspan=""5"" style=""text-align:center; color:var(--text-muted);"">No mails sent yet.</td></tr>';
                    return;
                }
                tbody.innerHTML = '';
                list.forEach(m => {
                    const row = document.createElement('tr');
                    row.innerHTML = `
                        <td>${m.id}</td>
                        <td>${m.gid === 0 ? 'ALL PLAYERS' : (m.nickname || m.gid)}</td>
                        <td><strong>${m.title}</strong></td>
                        <td>${m.sender}</td>
                        <td><span class=""badge ${m.unread ? 'badge-active' : ''}"">${m.unread ? 'UNREAD' : 'READ'}</span></td>
                    `;
                    tbody.appendChild(row);
                });
            } catch (err) {}
        }

        document.getElementById('topupTarget').addEventListener('change', (e) => {
            const p = cachedPlayers.find(x => x.gid == e.target.value);
            if (p) {
                document.getElementById('topupBalanceView').value = `${Number(p.diamonds).toLocaleString()} 💎 | ${Number(p.gp).toLocaleString()} 🪙`;
            } else {
                document.getElementById('topupBalanceView').value = '-- Select Player --';
            }
        });

        function setTopupPreset(dia, gp) {
            document.getElementById('topupDiamonds').value = dia;
            document.getElementById('topupGold').value = gp;
        }

        async function toggleMaintenance(state) {
            const notice = document.getElementById('maintNotice').value;
            await fetch('/api/maintenance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ maintenance: state, notice })
            });
            refreshStatus();
        }

        async function submitTopup() {
            const gid = document.getElementById('topupTarget').value;
            if (!gid) return alert('Please select a character!');
            const diamonds = parseInt(document.getElementById('topupDiamonds').value) || 0;
            const gp = parseInt(document.getElementById('topupGold').value) || 0;

            await fetch('/api/topup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ gid, diamonds, gp })
            });
            alert('Top-Up successfully credited!');
            refreshStatus();
            loadPlayers();
        }

        async function sendMail() {
            const targetGid = parseInt(document.getElementById('mailTarget').value) || 0;
            const title = document.getElementById('mailTitle').value;
            const content = document.getElementById('mailContent').value;
            const sender = document.getElementById('mailSender').value;
            const diamonds = parseInt(document.getElementById('mailDiamonds').value) || 0;
            const gold = parseInt(document.getElementById('mailGold').value) || 0;

            if (!title) return alert('Subject is required!');

            await fetch('/api/sendmail', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ targetGid, title, content, sender, diamonds, gold })
            });
            alert('Mail sent successfully!');
            document.getElementById('mailTitle').value = '';
            document.getElementById('mailContent').value = '';
            refreshStatus();
            loadPlayers();
            loadMails();
        }

        async function toggleBan(accountId, banned) {
            const reason = prompt(banned ? 'Reason for ban:' : 'Unban note:', banned ? 'Server rule violation' : 'Appeal granted');
            if (reason === null) return;
            await fetch('/api/ban', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ accountId, banned, reason })
            });
            loadPlayers();
        }

        async function createPlayer() {
            const username = document.getElementById('newUsername').value;
            const nickname = document.getElementById('newNickname').value;
            const diamonds = parseInt(document.getElementById('newDiamonds').value) || 0;
            const gold = parseInt(document.getElementById('newGold').value) || 0;

            await fetch('/api/create_player', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username, nickname, diamonds, gold })
            });
            alert('Account & Character created in database!');
            refreshStatus();
            loadPlayers();
        }

        refreshStatus();
        loadPlayers();
        loadMails();
        setInterval(refreshStatus, 8000);
    </script>
</body>
</html>";
        }
    }

    public class Program {
        public static void Main(string[] args) {
            Console.WriteLine("====================================================");
            Console.WriteLine("         ROS REDEMPTION - SERVER CONTROLLER         ");
            Console.WriteLine("====================================================");
            Console.WriteLine("[INFO] Database Target: " + ServerManager.AccountsDbFile);
            Console.WriteLine("[INFO] Server List: " + ServerManager.ServerListFile);

            int port = 8888;
            if (args.Length > 0) int.TryParse(args[0], out port);

            var server = new TcpWebServer(port);
            server.Start();

            var reset = new ManualResetEvent(false);
            Console.CancelKeyPress += (s, e) => reset.Set();
            Console.WriteLine("[INFO] ROS Redemption Controller running. Press Ctrl+C to terminate.");
            reset.WaitOne();
        }
    }
}
