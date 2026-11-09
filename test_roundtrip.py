import zlib, hashlib, base64

K = bytes.fromhex('2a8ec34ed7c4baa57c7b5e4adef0f454f8f854d809daa14616db06b2eac10809')

def encrypt_lobby(src_text, key):
    raw = src_text.encode('utf-8')
    compressed = zlib.compress(raw, 9)
    size = len(compressed)
    i = 0
    c = 0
    parts = []
    while i < size:
        chunk = compressed[i:i + 65536]
        blocks = (len(chunk) + 31) // 32
        ks = b''.join([hashlib.sha256(key + str(c + k).encode('ascii')).digest() for k in range(blocks)])[:len(chunk)]
        c += blocks
        xored = bytes(bytearray(a ^ b for a, b in zip(chunk, ks)))
        parts.append(xored)
        i += 65536
    encrypted_blob = b''.join(parts)
    b64 = base64.b64encode(encrypted_blob).decode('ascii')
    chunks = [b64[j:j+4000] for j in range(0, len(b64), 4000)]
    return chunks

def decrypt_lobby(chunks, key):
    raw = base64.b64decode(''.join(chunks))
    size = len(raw)
    i = 0
    c = 0
    parts = []
    while i < size:
        chunk = raw[i:i + 65536]
        blocks = (len(chunk) + 31) // 32
        ks = b''.join([hashlib.sha256(key + str(c + k).encode('ascii')).digest() for k in range(blocks)])[:len(chunk)]
        c += blocks
        xored = bytes(bytearray(a ^ b for a, b in zip(chunk, ks)))
        parts.append(xored)
        i += 65536
    decomp = zlib.decompress(b''.join(parts))
    return decomp.decode('utf-8')

# Test roundtrip
test_str = "print('Hello ROS Redemption 2026!')\n" * 500
chunks = encrypt_lobby(test_str, K)
decrypted = decrypt_lobby(chunks, K)
assert decrypted == test_str, "Roundtrip test failed!"
print("ROUNDTRIP TEST PASSED PERFECTLY!")

