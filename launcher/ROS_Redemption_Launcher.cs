using System;
using System.IO;
using System.Net.Sockets;
using System.Diagnostics;
using System.Threading;

namespace ROSRedemption
{
    class Program
    {
        static void Main(string[] args)
        {
            string baseDir = @"C:\DieHardROS";
            string launcherScript = Path.Combine(baseDir, "launcher", "launcher_server.py");
            string pythonExe = Path.Combine(baseDir, "runtime", "python", "python.exe");
            if (!File.Exists(pythonExe))
            {
                pythonExe = Path.Combine(baseDir, "ROS_Redemption_Server_Package", "python", "python.exe");
            }

            int port = 8799;

            // 1. Check if launcher_server is already running
            if (!IsPortOpen("127.0.0.1", port))
            {
                if (File.Exists(pythonExe) && File.Exists(launcherScript))
                {
                    ProcessStartInfo psi = new ProcessStartInfo();
                    psi.FileName = pythonExe;
                    psi.Arguments = "\"" + launcherScript + "\"";
                    psi.WorkingDirectory = baseDir;
                    psi.UseShellExecute = false;
                    psi.CreateNoWindow = true;
                    psi.WindowStyle = ProcessWindowStyle.Hidden;
                    Process.Start(psi);
                }

                // Wait for port to become active
                for (int i = 0; i < 20; i++)
                {
                    Thread.Sleep(150);
                    if (IsPortOpen("127.0.0.1", port))
                        break;
                }
            }

            // 2. Open Valorant-Style Window using Edge App Mode
            string url = "http://127.0.0.1:" + port;
            string edge86 = @"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe";
            string edge64 = @"C:\Program Files\Microsoft\Edge\Application\msedge.exe";
            string edgeExe = File.Exists(edge86) ? edge86 : (File.Exists(edge64) ? edge64 : null);

            if (edgeExe != null)
            {
                ProcessStartInfo edgePsi = new ProcessStartInfo();
                edgePsi.FileName = edgeExe;
                edgePsi.Arguments = "--app=\"" + url + "\" --window-size=1260,780";
                edgePsi.UseShellExecute = false;
                Process.Start(edgePsi);
            }
            else
            {
                Process.Start(url);
            }
        }

        static bool IsPortOpen(string host, int port)
        {
            try
            {
                using (TcpClient client = new TcpClient())
                {
                    var result = client.BeginConnect(host, port, null, null);
                    bool success = result.AsyncWaitHandle.WaitOne(200);
                    if (!success) return false;
                    client.EndConnect(result);
                    return true;
                }
            }
            catch
            {
                return false;
            }
        }
    }
}

