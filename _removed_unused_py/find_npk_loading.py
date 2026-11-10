with open(r"C:\DieHardROS\res\ui.npk", "rb") as f:
    chunk_size = 10 * 1024 * 1024
    pos = 0
    found = []
    while True:
        chunk = f.read(chunk_size)
        if not chunk: break
        idx = chunk.find(b"bg_loading_01")
        if idx >= 0:
            found.append(pos + idx)
            print(f"Found bg_loading_01 at offset: {pos + idx}")
            print("Surrounding bytes:", chunk[max(0, idx-20):idx+60])
            break
        pos += len(chunk)
    if not found:
        print("bg_loading_01 NOT found in ui.npk!")
