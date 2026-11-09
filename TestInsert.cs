using System;
using System.Runtime.InteropServices;

public class TestInsert {
    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_open16", CallingConvention = CallingConvention.Cdecl)]
    public static extern int sqlite3_open16([MarshalAs(UnmanagedType.LPWStr)] string filename, out IntPtr db);

    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_close", CallingConvention = CallingConvention.Cdecl)]
    public static extern int sqlite3_close(IntPtr db);

    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_exec", CallingConvention = CallingConvention.Cdecl)]
    public static extern int sqlite3_exec(IntPtr db, [MarshalAs(UnmanagedType.LPStr)] string sql, IntPtr callback, IntPtr arg, out IntPtr errMsg);

    public static void Main(string[] args) {
        string dbPath = @"C:\DieHardROS\local_update\server_data\accounts.db";
        IntPtr db;
        int rc = sqlite3_open16(dbPath, out db);
        Console.WriteLine("Open rc: " + rc);

        IntPtr errMsg;
        string sql = "INSERT INTO accounts (username, created, last_login, last_server, banned, note) VALUES ('admin', 1700000000, 1700000000, 10501, 0, 'ROS Redemption');";
        rc = sqlite3_exec(db, sql, IntPtr.Zero, IntPtr.Zero, out errMsg);
        Console.WriteLine("Exec rc: " + rc);
        if (errMsg != IntPtr.Zero) {
            Console.WriteLine("Error: " + Marshal.PtrToStringAnsi(errMsg));
        }
        sqlite3_close(db);
    }
}

