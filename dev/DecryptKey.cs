using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Runtime.InteropServices;

class DecryptKey
{
    [DllImport("crypt32.dll", SetLastError = true, CharSet = CharSet.Auto)]
    static extern bool CryptUnprotectData(
        ref DATA_BLOB pDataIn,
        string szDataDescr,
        ref DATA_BLOB pOptionalEntropy,
        IntPtr pvReserved,
        IntPtr pPromptStruct,
        int dwFlags,
        ref DATA_BLOB pDataOut);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct DATA_BLOB
    {
        public int cbData;
        public IntPtr pbData;
    }

    static byte[] DpapiDecrypt(byte[] cipher)
    {
        DATA_BLOB inBlob = new DATA_BLOB();
        inBlob.cbData = cipher.Length;
        inBlob.pbData = Marshal.AllocHGlobal(cipher.Length);
        Marshal.Copy(cipher, 0, inBlob.pbData, cipher.Length);

        DATA_BLOB outBlob = new DATA_BLOB();
        DATA_BLOB entropy = new DATA_BLOB();

        try
        {
            if (CryptUnprotectData(ref inBlob, null, ref entropy, IntPtr.Zero, IntPtr.Zero, 0, ref outBlob))
            {
                byte[] plain = new byte[outBlob.cbData];
                Marshal.Copy(outBlob.pbData, plain, 0, outBlob.cbData);
                return plain;
            }
        }
        finally
        {
            if (inBlob.pbData != IntPtr.Zero) Marshal.FreeHGlobal(inBlob.pbData);
            if (outBlob.pbData != IntPtr.Zero) Marshal.FreeHGlobal(outBlob.pbData);
        }
        return null;
    }

    // BCrypt AES GCM
    [DllImport("bcrypt.dll")]
    static extern int BCryptOpenAlgorithmProvider(out IntPtr phAlgorithm, [MarshalAs(UnmanagedType.LPWStr)] string pszAlgId, [MarshalAs(UnmanagedType.LPWStr)] string pszImplementation, int dwFlags);
    [DllImport("bcrypt.dll")]
    static extern int BCryptCloseAlgorithmProvider(IntPtr hAlgorithm, int dwFlags);
    [DllImport("bcrypt.dll")]
    static extern int BCryptSetProperty(IntPtr hObject, [MarshalAs(UnmanagedType.LPWStr)] string pszProperty, [MarshalAs(UnmanagedType.LPWStr)] string pbInput, int cbInput, int dwFlags);
    [DllImport("bcrypt.dll")]
    static extern int BCryptGenerateSymmetricKey(IntPtr hAlgorithm, out IntPtr phKey, IntPtr pbKeyObject, int cbKeyObject, byte[] pbSecret, int cbSecret, int dwFlags);
    [DllImport("bcrypt.dll")]
    static extern int BCryptDestroyKey(IntPtr hKey);

    [StructLayout(LayoutKind.Sequential)]
    struct BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO
    {
        public int cbSize;
        public int dwInfoVersion;
        public IntPtr pbNonce;
        public int cbNonce;
        public IntPtr pbAuthData;
        public int cbAuthData;
        public IntPtr pbTag;
        public int cbTag;
        public IntPtr pbMacContext;
        public int cbMacContext;
        public int cbAAD;
        public long cbData;
        public int dwFlags;
    }

    [DllImport("bcrypt.dll")]
    static extern int BCryptDecrypt(IntPtr hKey, byte[] pbInput, int cbInput, ref BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO pPaddingInfo, byte[] pbIV, int cbIV, byte[] pbOutput, int cbOutput, out int pcbResult, int dwFlags);

    static byte[] AesGcmDecrypt(byte[] key, byte[] iv, byte[] cipher, byte[] tag)
    {
        IntPtr hAlg;
        BCryptOpenAlgorithmProvider(out hAlg, "AES", null, 0);
        string mode = "ChainingModeGCM";
        BCryptSetProperty(hAlg, "ChainingMode", mode, (mode.Length + 1) * 2, 0);

        IntPtr hKey;
        BCryptGenerateSymmetricKey(hAlg, out hKey, IntPtr.Zero, 0, key, key.Length, 0);

        byte[] plain = new byte[cipher.Length];
        int result;

        GCHandle ivHandle = GCHandle.Alloc(iv, GCHandleType.Pinned);
        GCHandle tagHandle = GCHandle.Alloc(tag, GCHandleType.Pinned);

        BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO info = new BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO();
        info.cbSize = Marshal.SizeOf(typeof(BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO));
        info.dwInfoVersion = 1;
        info.pbNonce = ivHandle.AddrOfPinnedObject();
        info.cbNonce = iv.Length;
        info.pbTag = tagHandle.AddrOfPinnedObject();
        info.cbTag = tag.Length;

        int status = BCryptDecrypt(hKey, cipher, cipher.Length, ref info, null, 0, plain, plain.Length, out result, 0);

        ivHandle.Free();
        tagHandle.Free();
        BCryptDestroyKey(hKey);
        BCryptCloseAlgorithmProvider(hAlg, 0);

        if (status == 0) return plain;
        Console.WriteLine("BCryptDecrypt failed with status: 0x" + status.ToString("X"));
        return null;
    }

    static void Main()
    {
        string localStatePath = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), @"DieHard ROS Online\Local State");
        string localState = File.ReadAllText(localStatePath);

        // Find encrypted_key
        int idx = localState.IndexOf("\"encrypted_key\":\"");
        if (idx < 0) { Console.WriteLine("encrypted_key not found"); return; }
        int end = localState.IndexOf("\"", idx + 17);
        string b64Key = localState.Substring(idx + 17, end - (idx + 17));
        byte[] encKeyWithHeader = Convert.FromBase64String(b64Key);

        // Skip DPAPI prefix (5 bytes: 'DPAPI')
        byte[] encKey = new byte[encKeyWithHeader.Length - 5];
        Buffer.BlockCopy(encKeyWithHeader, 5, encKey, 0, encKey.Length);
        byte[] masterKey = DpapiDecrypt(encKey);
        Console.WriteLine("Master key decrypted! Length: " + masterKey.Length);

        // Decrypt bundleKey
        string b64Bundle = "djEwgNIAYNk/ZDWieeXqvejEwWmxtx+HEIWluE3bnuOmQu8Yi04NTFOm9DT0IW+aFzT0yFd0F2fQXFKAndNf/iADR493V9LWZ+o50T5S/kgZqqf5cLQiSNYzZB31TC4=";
        byte[] encBundle = Convert.FromBase64String(b64Bundle);

        // Skip 'v10' (3 bytes)
        byte[] iv = new byte[12];
        Buffer.BlockCopy(encBundle, 3, iv, 0, 12);

        int cipherLen = encBundle.Length - 3 - 12 - 16;
        byte[] cipher = new byte[cipherLen];
        Buffer.BlockCopy(encBundle, 15, cipher, 0, cipherLen);

        byte[] tag = new byte[16];
        Buffer.BlockCopy(encBundle, encBundle.Length - 16, tag, 0, 16);

        byte[] plainBytes = AesGcmDecrypt(masterKey, iv, cipher, tag);
        if (plainBytes != null)
        {
            string plainText = Encoding.UTF8.GetString(plainBytes);
            Console.WriteLine("BUNDLE_KEY_DECRYPTED=" + plainText);
            File.WriteAllText(@"c:\Users\seanj\dev\bundle_key.txt", plainText);
        }
    }
}

