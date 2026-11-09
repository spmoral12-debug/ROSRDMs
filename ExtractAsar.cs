using System;
using System.IO;
using System.Text;
using System.Collections.Generic;

class ExtractAsar
{
    static void Main(string[] args)
    {
        string asarPath = @"C:\Program Files\DieHard ROS Online\app-1.0.40\resources\app.asar";
        string outDir = @"c:\Users\seanj\dev\diehard_app";

        using (FileStream fs = File.OpenRead(asarPath))
        using (BinaryReader br = new BinaryReader(fs))
        {
            uint u1 = br.ReadUInt32();
            uint headerSize = br.ReadUInt32();
            uint headerObjSize = br.ReadUInt32();
            uint headerLen = br.ReadUInt32();

            Console.WriteLine("Header len: " + headerLen);
            byte[] headerBytes = br.ReadBytes((int)headerLen);
            string headerJson = Encoding.UTF8.GetString(headerBytes);
            File.WriteAllText(Path.Combine(outDir, "header.json"), headerJson);
            Console.WriteLine("Saved header.json");

            long dataOffset = 16 + headerLen;
            Console.WriteLine("Data offset: " + dataOffset);
        }
    }
}

