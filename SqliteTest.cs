using System;
using System.Runtime.InteropServices;

public class Program {
    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_open16", CallingConvention = CallingConvention.Cdecl)]
    public static extern int sqlite3_open16([MarshalAs(UnmanagedType.LPWStr)] string filename, out IntPtr db);

    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_close", CallingConvention = CallingConvention.Cdecl)]
    public static extern int sqlite3_close(IntPtr db);

    [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
    public delegate int ExecCallback(IntPtr arg, int colCount, IntPtr colValues, IntPtr colNames);

    [DllImport("winsqlite3.dll", EntryPoint = "sqlite3_exec", CallingConvention = CallingConvention.Cdecl)]
    public static extern int sqlite3_exec(IntPtr db, [MarshalAs(UnmanagedType.LPStr)] string sql, ExecCallback callback, IntPtr arg, out IntPtr errMsg);

    public static void Query(IntPtr db, string title, string sql) {
        Console.WriteLine("\n--- " + title + " ---");
        IntPtr errMsg;
        ExecCallback cb = (arg, count, values, names) => {
            string row = "";
            for (int i = 0; i < count; i++) {
                IntPtr valPtr = Marshal.ReadIntPtr(values, i * IntPtr.Size);
                IntPtr namePtr = Marshal.ReadIntPtr(names, i * IntPtr.Size);
                string colName = Marshal.PtrToStringAnsi(namePtr);
                string colVal = valPtr != IntPtr.Zero ? Marshal.PtrToStringAnsi(valPtr) : "NULL";
                row += colName + "=" + colVal + " | ";
            }
            Console.WriteLine(row);
            return 0;
        };
        sqlite3_exec(db, sql, cb, IntPtr.Zero, out errMsg);
    }

    public static void Main(string[] args) {
        string dbPath = args.Length > 0 ? args[0] : "accounts.db";
        IntPtr db;
        if (sqlite3_open16(dbPath, out db) != 0) return;

        Query(db, "ACCOUNTS", "SELECT id, username, banned, note FROM accounts;");
        Query(db, "CHARACTERS", "SELECT gid, account_id, server_id, nickname, level FROM characters;");
        Query(db, "WALLETS", "SELECT gid, gp, sp, freeYuanbao, payYuanbao FROM wallets;");
        Query(db, "MAILS", "SELECT id, gid, type, title, content, sender, unread FROM mails;");

        sqlite3_close(db);
    }
}
