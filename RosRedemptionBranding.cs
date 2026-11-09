using System;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

namespace RosRedemptionBranding {
    class Program {
        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        static extern bool SetWindowText(IntPtr hWnd, string lpString);

        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

        [DllImport("user32.dll", SetLastError = true)]
        static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        [DllImport("user32.dll")]
        static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, int wParam, IntPtr lParam);

        [DllImport("user32.dll")]
        static extern IntPtr SetClassLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);

        [DllImport("user32.dll")]
        static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

        delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        const uint WM_SETICON = 0x0080;
        const int ICON_SMALL = 0;
        const int ICON_BIG = 1;
        const int GCLP_HICON = -14;
        const int GCLP_HICONSM = -34;
        const int SW_HIDE = 0;

        const string TARGET_TITLE = "ROS REDEMPTION";

        static void Main(string[] args) {
            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string icoPath = Path.Combine(baseDir, "ros_redemption.ico");
            if (!File.Exists(icoPath)) {
                icoPath = @"C:\DieHardROS\ros_redemption.ico";
            }
            Icon iconBig = null;
            Icon iconSmall = null;

            if (File.Exists(icoPath)) {
                try {
                    iconBig = new Icon(icoPath, 256, 256);
                    iconSmall = new Icon(icoPath, 32, 32);
                } catch { }
            }

            int notRunningCount = 0;

            while (true) {
                try {
                    Process[] rosProcs = Process.GetProcessesByName("ros64");
                    if (rosProcs == null || rosProcs.Length == 0) {
                        notRunningCount++;
                        // If ros64 is not running for 60 seconds (120 * 500ms), exit
                        if (notRunningCount > 120) {
                            break;
                        }
                    } else {
                        notRunningCount = 0;

                        // Find all windows belonging to ros64
                        foreach (var proc in rosProcs) {
                            uint pid = (uint)proc.Id;
                            EnumWindows((hWnd, lParam) => {
                                uint winPid;
                                GetWindowThreadProcessId(hWnd, out winPid);
                                if (winPid == pid) {
                                    StringBuilder sb = new StringBuilder(256);
                                    GetWindowText(hWnd, sb, 256);
                                    string currentTitle = sb.ToString();

                                    // If window has a title and it's not already our target title
                                    if (!string.IsNullOrEmpty(currentTitle) && currentTitle != TARGET_TITLE) {
                                        SetWindowText(hWnd, TARGET_TITLE);
                                    }

                                    // Apply custom icon
                                    if (iconBig != null && iconSmall != null) {
                                        SendMessage(hWnd, WM_SETICON, ICON_BIG, iconBig.Handle);
                                        SendMessage(hWnd, WM_SETICON, ICON_SMALL, iconSmall.Handle);
                                        try {
                                            SetClassLongPtr(hWnd, GCLP_HICON, iconBig.Handle);
                                            SetClassLongPtr(hWnd, GCLP_HICONSM, iconSmall.Handle);
                                        } catch { }
                                    }
                                }
                                return true;
                            }, IntPtr.Zero);
                        }

                        // Also silently suppress any CCMini or NetEase CC windows
                        Process[] ccProcs = Process.GetProcessesByName("CCMini");
                        if (ccProcs != null) {
                            foreach (var cp in ccProcs) {
                                uint ccPid = (uint)cp.Id;
                                EnumWindows((hWnd, lParam) => {
                                    uint winPid;
                                    GetWindowThreadProcessId(hWnd, out winPid);
                                    if (winPid == ccPid) {
                                        ShowWindow(hWnd, SW_HIDE);
                                    }
                                    return true;
                                }, IntPtr.Zero);
                            }
                        }
                    }
                } catch { }

                Thread.Sleep(500);
            }
        }
    }
}

