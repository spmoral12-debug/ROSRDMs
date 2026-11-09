using System;
using System.Diagnostics;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Threading;

namespace RosIconFix {
    class Program {
        [DllImport("user32.dll", SetLastError = true)]
        static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, int wParam, IntPtr lParam);

        [DllImport("user32.dll")]
        static extern IntPtr SetClassLongPtr(IntPtr hWnd, int nIndex, IntPtr dwNewLong);

        const uint WM_SETICON = 0x0080;
        const int ICON_SMALL = 0;
        const int ICON_BIG = 1;
        const int GCLP_HICON = -14;
        const int GCLP_HICONSM = -34;

        static void Main(string[] args) {
            string icoPath = @"C:\DieHardROS\ros_redemption.ico";
            if (!System.IO.File.Exists(icoPath)) return;

            Icon ico = new Icon(icoPath, 256, 256);
            Icon icoSm = new Icon(icoPath, 32, 32);

            for (int i = 0; i < 40; i++) {
                Thread.Sleep(500);
                foreach (var proc in Process.GetProcessesByName("ros64")) {
                    IntPtr hWnd = proc.MainWindowHandle;
                    if (hWnd != IntPtr.Zero) {
                        SendMessage(hWnd, WM_SETICON, ICON_BIG, ico.Handle);
                        SendMessage(hWnd, WM_SETICON, ICON_SMALL, icoSm.Handle);
                        try {
                            SetClassLongPtr(hWnd, GCLP_HICON, ico.Handle);
                            SetClassLongPtr(hWnd, GCLP_HICONSM, icoSm.Handle);
                        } catch {}
                        return;
                    }
                }
            }
        }
    }
}
