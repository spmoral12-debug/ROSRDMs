using System;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;
using System.Text;
using System.Collections.Generic;

class UnpackPatch
{
    static byte[] HexToBytes(string hex)
    {
        byte[] bytes = new byte[hex.Length / 2];
        for (int i = 0; i < bytes.Length; i++)
        {
            bytes[i] = Convert.ToByte(hex.Substring(i * 2, 2), 16);
        }
        return bytes;
    }

    static void Unpack(string inputPath, string outputPath)
    {
        Console.WriteLine("Reading " + inputPath + "...");
        string[] lines = File.ReadAllLines(inputPath);
        
        byte[] key = null;
        List<string> b64Chunks = new List<string>();
        bool inB = false;

        foreach (var line in lines)
        {
            string trimmed = line.Trim();
            if (trimmed.StartsWith("_K ="))
            {
                int q1 = trimmed.IndexOf('"');
                int q2 = trimmed.IndexOf('"', q1 + 1);
                string hexKey = trimmed.Substring(q1 + 1, q2 - q1 - 1);
                key = HexToBytes(hexKey);
            }
            else if (trimmed.StartsWith("_B = ["))
            {
                inB = true;
            }
            else if (inB)
            {
                if (trimmed.StartsWith("]"))
                {
                    inB = false;
                }
                else
                {
                    int q1 = trimmed.IndexOf('"');
                    int q2 = trimmed.LastIndexOf('"');
                    if (q1 >= 0 && q2 > q1)
                    {
                        b64Chunks.Add(trimmed.Substring(q1 + 1, q2 - q1 - 1));
                    }
                }
            }
        }

        if (key == null)
        {
            Console.WriteLine("Key not found!");
            return;
        }

        Console.WriteLine("Base64 chunks count: " + b64Chunks.Count);
        string allB64 = string.Concat(b64Chunks);
        byte[] raw = Convert.FromBase64String(allB64);
        Console.WriteLine("Raw decoded bytes: " + raw.Length);

        // Keystream XOR
        byte[] decrypted = new byte[raw.Length];
        int c = 0;
        int i = 0;
        using (SHA256 sha = SHA256.Create())
        {
            while (i < raw.Length)
            {
                int chunkSize = Math.Min(65536, raw.Length - i);
                int blocks = (chunkSize + 31) / 32;

                byte[] ks = new byte[blocks * 32];
                for (int k = 0; k < blocks; k++)
                {
                    string ctrStr = (c + k).ToString();
                    byte[] ctrBytes = Encoding.ASCII.GetBytes(ctrStr);
                    byte[] toHash = new byte[key.Length + ctrBytes.Length];
                    Buffer.BlockCopy(key, 0, toHash, 0, key.Length);
                    Buffer.BlockCopy(ctrBytes, 0, toHash, key.Length, ctrBytes.Length);
                    byte[] hash = sha.ComputeHash(toHash);
                    Buffer.BlockCopy(hash, 0, ks, k * 32, 32);
                }
                c += blocks;

                for (int j = 0; j < chunkSize; j++)
                {
                    decrypted[i + j] = (byte)(raw[i + j] ^ ks[j]);
                }
                i += chunkSize;
            }
        }

        Console.WriteLine("Decryption done. Decompressing zlib...");
        // Zlib header is 2 bytes (decrypted[0] and [1]), skip it for DeflateStream
        byte[] decompressed;
        using (MemoryStream ms = new MemoryStream(decrypted, 2, decrypted.Length - 6))
        using (DeflateStream ds = new DeflateStream(ms, CompressionMode.Decompress))
        using (MemoryStream outMs = new MemoryStream())
        {
            ds.CopyTo(outMs);
            decompressed = outMs.ToArray();
        }

        File.WriteAllBytes(outputPath, decompressed);
        Console.WriteLine("Wrote " + decompressed.Length + " bytes to " + outputPath);
    }

    static void Main(string[] args)
    {
        if (args.Length >= 2)
        {
            Unpack(args[0], args[1]);
        }
        else
        {
            Unpack(@"C:\DieHardROS\local_update\hot\remote-battle.py", @"c:\Users\seanj\dev\remote-battle-unpacked.py");
            Unpack(@"C:\DieHardROS\local_update\hot\remote-lobby.py", @"c:\Users\seanj\dev\remote-lobby-unpacked.py");
        }
    }
}

