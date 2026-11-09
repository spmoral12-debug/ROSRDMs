using System;
using System.IO;
using RosRedemption;

public class InitDb {
    public static void Main() {
        Console.WriteLine("[SETUP] Updating server files for ROS Redemption...");
        ServerManager.SetMaintenance(false, "Welcome to ROS Redemption! Official Server is ONLINE.");
        
        Console.WriteLine("[SETUP] Creating initial Admin player and wallet...");
        ServerManager.CreateAccountAndChar("admin", "Admin_Redemption", 99999, 500000);
        
        Console.WriteLine("[SETUP] Dispatching Welcome Mail with Rewards...");
        ServerManager.SendMail(0, "Welcome to ROS Redemption!", "Welcome to ROS Redemption private server! Your control suite is ready with full maintenance, mail, and top-up systems.", "ROS Redemption HQ", 2500, 50000);
        
        Console.WriteLine("[SUCCESS] Initial setup complete!");
    }
}