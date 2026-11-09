with open(r'C:\DieHardROS\Documents\res\dh_brand\dh_rank_s1.jpg', 'rb') as f:
    data = f.read()

print("File size:", len(data))
# Check if there are text markers in jpeg comments or exif
import re
print("Strings in dh_rank_s1.jpg:", re.findall(rb'[A-Za-z0-9_\-\.]{5,}', data[:2000]))

