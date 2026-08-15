"""用 py7zr 解压 w64devkit SFX（.7z.exe）：跳过 exe stub，从 7z 魔数偏移处解压"""
import io
import py7zr

SRC = "tools/w64devkit.7z.exe"
DST = "tools/w64devkit"

with open(SRC, "rb") as f:
    data = f.read()
sig = bytes.fromhex("377abcaf271c")
idx = data.find(sig)
if idx < 0:
    raise SystemExit("未找到 7z 签名")
print(f"7z 签名偏移: {idx}")
buf = io.BytesIO(data[idx:])
with py7zr.SevenZipFile(buf) as z:
    names = z.getnames()
    print(f"归档文件数: {len(names)}")
    z.extractall(DST)
print("解压完成 ->", DST)
