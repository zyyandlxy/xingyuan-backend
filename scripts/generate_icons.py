"""生成 PWA 图标（纯 Python，无外部依赖）"""
import struct, zlib, base64
from pathlib import Path

def create_png(width: int, path: Path):
    """生成带 GLM 文字的简单图标"""
    from io import BytesIO

    # 创建 32-bit RGBA 图像数据
    raw = bytearray()
    center = width // 2
    r = width // 3

    for y in range(width):
        raw.append(0)  # filter byte per row
        for x in range(width):
            # 圆形渐变背景
            dx, dy = x - center, y - center
            dist = (dx * dx + dy * dy) ** 0.5
            if dist < r:
                # 紫色渐变
                t = dist / r
                raw.extend([80 + int(60 * (1 - t)), 60 + int(80 * (1 - t)), 200 - int(40 * t), 255])
            elif dist < r + 2:
                raw.extend([99, 102, 241, 100])
            else:
                raw.extend([15, 23, 42, 0])  # 透明背景

    def make_chunk(ctype: bytes, data: bytes) -> bytes:
        c = ctype + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack('>IIBBBBB', width, width, 8, 6, 0, 0, 0)
    buf = b'\x89PNG\r\n\x1a\n'
    buf += make_chunk(b'IHDR', ihdr)
    buf += make_chunk(b'IDAT', zlib.compress(bytes(raw)))
    buf += make_chunk(b'IEND', b'')

    path.write_bytes(buf)
    print(f"  ✓ {path.name} ({width}×{width})")


if __name__ == '__main__':
    static = Path(__file__).parent.parent / 'static'
    static.mkdir(parents=True, exist_ok=True)
    create_png(192, static / 'icon-192.png')
    create_png(512, static / 'icon-512.png')
    print('PWA 图标生成完成！')
