import os, glob, hashlib, struct

def get_image_info(path):
    try:
        with open(path, 'rb') as f:
            data = f.read(30)
            if data[:8] == b'\x89PNG\r\n\x1a\n':
                w, h = struct.unpack('>LL', data[16:24])
                return f'PNG {w}x{h}'
            elif data[:2] == b'\xff\xd8':
                f.seek(0)
                d = f.read()
                # find SOF0 or SOF2
                for i in range(len(d) - 9):
                    if d[i] == 0xFF and d[i+1] in (0xC0, 0xC1, 0xC2):
                        h, w = struct.unpack('>HH', d[i+5:i+9])
                        return f'JPG {w}x{h}'
    except Exception as e:
        return str(e)
    return 'UNKNOWN'

def md5(p):
    with open(p, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

print("--- Inspecting dh_brand ---")
for f in os.listdir(r'C:\DieHardROS\Documents\res\dh_brand'):
    p = os.path.join(r'C:\DieHardROS\Documents\res\dh_brand', f)
    if os.path.isfile(p):
        print(f"{f:30} size={os.path.getsize(p):7} {get_image_info(p):15} md5={md5(p)[:10]}")

print("\n--- Inspecting txt_logo_zjzc.png ---")
for p in glob.glob(r'C:\DieHardROS\**\*logo*.*', recursive=True):
    if p.lower().endswith(('.png', '.jpg')):
        print(f"{p} ({os.path.getsize(p)} bytes) {get_image_info(p)}")

