from PIL import Image, ImageDraw, ImageFont
import os

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
os.makedirs(STATIC_DIR, exist_ok=True)

BG_COLOR = '#FF69B4'
TEXT_COLOR = 'white'
CHAR = 'の'

for size in [192, 512]:
    img = Image.new('RGB', (size, size), BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_size = int(size * 0.55)
    font = None
    for path in [
        '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc',
        '/System/Library/Fonts/Hiragino Sans GB.ttc',
        '/System/Library/Fonts/Arial Unicode.ttf',
    ]:
        if os.path.exists(path):
            try:
                font = ImageFont.truetype(path, font_size)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), CHAR, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) / 2 - bbox[0]
    y = (size - text_h) / 2 - bbox[1]
    draw.text((x, y), CHAR, fill=TEXT_COLOR, font=font)

    out = os.path.join(STATIC_DIR, f'icon-{size}.png')
    img.save(out)
    print(f'生成: {out}')
