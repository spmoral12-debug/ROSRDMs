using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Threading;
using System.Text;

namespace RosRedemption {
    public class BrandingInjector {
        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        public static extern bool SetWindowText(IntPtr hWnd, string lpString);

        [DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Auto)]
        public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

        [DllImport("user32.dll", SetLastError = true)]
        public static extern int GetWindowTextLength(IntPtr hWnd);

        [DllImport("user32.dll", CharSet = CharSet.Auto)]
        public static extern IntPtr SendMessage(IntPtr hWnd, uint Msg, IntPtr wParam, IntPtr lParam);

        [DllImport("user32.dll")]
        public static extern IntPtr LoadImage(IntPtr hinst, string lpszName, uint uType, int cxDesired, int cyDesired, uint fuLoad);

        [DllImport("user32.dll")]
        public static extern bool IsWindowVisible(IntPtr hWnd);

        [DllImport("user32.dll")]
        public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);

        public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

        [DllImport("user32.dll")]
        public static extern bool EnumWindows(EnumWindowsProc enumProc, IntPtr lParam);

        [DllImport("user32.dll", EntryPoint = "SetClassLongPtr")]
        public static extern IntPtr SetClassLongPtr64(IntPtr hWnd, int nIndex, IntPtr dwNewLong);

        [DllImport("user32.dll", EntryPoint = "SetClassLong")]
        public static extern IntPtr SetClassLong32(IntPtr hWnd, int nIndex, IntPtr dwNewLong);

        public static IntPtr SetClassLong(IntPtr hWnd, int nIndex, IntPtr dwNewLong) {
            if (IntPtr.Size == 8)
                return SetClassLongPtr64(hWnd, nIndex, dwNewLong);
            else
                return SetClassLong32(hWnd, nIndex, dwNewLong);
        }

        public const uint WM_SETICON = 0x0080;
        public const int ICON_SMALL = 0;
        public const int ICON_BIG = 1;
        public const int GCLP_HICON = -14;
        public const int GCLP_HICONSM = -34;
        public const uint IMAGE_ICON = 1;
        public const uint LR_LOADFROMFILE = 0x00000010;

        public static void Main(string[] args) {
            string iconPath = @"C:\DieHardROS\ros_redemption.ico";
            IntPtr hIconBig = IntPtr.Zero;
            IntPtr hIconSmall = IntPtr.Zero;

            if (File.Exists(iconPath)) {
                try {
                    hIconBig = LoadImage(IntPtr.Zero, iconPath, IMAGE_ICON, 48, 48, LR_LOADFROMFILE);
                    hIconSmall = LoadImage(IntPtr.Zero, iconPath, IMAGE_ICON, 16, 16, LR_LOADFROMFILE);
                    if (hIconBig == IntPtr.Zero) {
                        hIconBig = LoadImage(IntPtr.Zero, iconPath, IMAGE_ICON, 0, 0, LR_LOADFROMFILE);
                        hIconSmall = hIconBig;
                    }
                } catch {}
            }

            string targetTitle = "ROS Redemption 1.610660.519384";

            while (true) {
                try {
                    EnumWindows((hWnd, lParam) => {
                        try {
                            if (!IsWindowVisible(hWnd)) return true;

                            int len = GetWindowTextLength(hWnd);
                            if (len <= 0) return true;

                            var sb = new StringBuilder(len + 32);
                            GetWindowText(hWnd, sb, sb.Capacity);
                            string currentTitle = sb.ToString();

                            if (currentTitle != targetTitle && (
                                currentTitle.IndexOf("Rules of Survival", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                currentTitle.IndexOf("DieHard", StringComparison.OrdinalIgnoreCase) >= 0 ||
                                currentTitle.StartsWith("ROS ", StringComparison.OrdinalIgnoreCase))) {
                                
                                SetWindowText(hWnd, targetTitle);

                                if (hIconBig != IntPtr.Zero) {
                                    SendMessage(hWnd, WM_SETICON, (IntPtr)ICON_BIG, hIconBig);
                                    SendMessage(hWnd, WM_SETICON, (IntPtr)ICON_SMALL, hIconSmall);
                                    SetClassLong(hWnd, GCLP_HICON, hIconBig);
                                    SetClassLong(hWnd, GCLP_HICONSM, hIconSmall);
                                }
                            }
                        } catch {}
                        return true;
                    }, IntPtr.Zero);
                } catch {}

                Thread.Sleep(200);
            }
        }
    }
}
