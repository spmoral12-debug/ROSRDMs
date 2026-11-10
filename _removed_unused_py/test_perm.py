import os, tempfile

dir_path = r"C:\DieHardROS\local_update\server_data"
test_file = os.path.join(dir_path, "test_write.tmp")
try:
    with open(test_file, "w") as f:
        f.write("hello")
    print("Write OK!")
    os.remove(test_file)
except Exception as e:
    print("Write failed:", e)

