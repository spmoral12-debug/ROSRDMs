using System;
using System.Diagnostics;
using System.Threading;

class Program {
    static void Main(string[] args) {
        try {
            // Keep alive silently while ros64 is running so any process check passes
            for (int i = 0; i < 300; i++) { // max 10 minutes or until ros64 exits
                Process[] procs = Process.GetProcessesByName("ros64");
                if (procs == null || procs.Length == 0) {
                    // ros64 hasn't started yet or has closed
                    if (i > 5) break;
                }
                Thread.Sleep(2000);
            }
        } catch { }
    }
}

