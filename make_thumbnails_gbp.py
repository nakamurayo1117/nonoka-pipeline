import os
from PIL import Image, ImageDraw, ImageFont

OUTPUT_DIR = os.path.join('output', 'thumbnails', 'gbp')
SIZE = (800, 800)

COLOR_BG      = '#1A1A2E'
COLOR_WHITE   = '#FFFFFF'
COLOR_GOLD    = '#D4AF37'
COLOR_NAVY    = '#1A1A2E'

FONT_PATHS = [
    '/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc',
    '/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc',
]

CARDS = [
    {
        'filename': 'gbp_weekday_day.png',
        'main':    '平日デイプラン',
        'price':   '¥1,300〜 / 時間',
        'hours':   '月〜木｜0:00〜17:00',
        'accent':  '推し活・鑑賞会に',
    },
    {
        'filename': 'gbp_weekday_night.png',
        'main':    '平日ナイトプラン',
        'price':   '¥1,500〜 / 時間',
        'hours':   '月〜木｜17:00〜24:00',
        'accent':  '仕事帰りの推し活に',
    },
    {
        'filename': 'gbp_weekend.png',
        'main':    '週末・祝日プラン',
        'price':   '¥1,900〜 / 時間',
        'hours':   '金・土・日・祝｜全時間',
        'accent':  '生誕祭・誕生日会に',
    },
    {
        'filename': 'gbp_6hours.png',
        'main':    '6時間パック',
        'price':   '¥1,100〜 / 時間',
        'hours':   '平日・週末プランあり',
        'accent':  'がっつり推し活に',
    },
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in FONT_PATHS:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def hex_with_alpha(hex_color: str, alpha: int) -> tuple:
    r = int(hex_color[1:3], 16)
    g = int(hex_color[3:5], 16)
    b = int(hex_color[5:7], 16)
    return (r, g, b, alpha)


def draw_centered_text(draw, y: int, text: str, font, color) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (SIZE[0] - w) // 2
    draw.text((x, y), text, font=font, fill=color)
    return bbox[3] - bbox[1]  # return text height


def draw_accent_box(img: Image.Image, draw: ImageDraw.ImageDraw, y: int, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 32, 14
    box_w = tw + pad_x * 2
    box_h = th + pad_y * 2
    box_x = (SIZE[0] - box_w) // 2
    radius = 10

    # White rounded rectangle
    overlay = Image.new('RGBA', SIZE, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rounded_rectangle(
        [box_x, y, box_x + box_w, y + box_h],
        radius=radius,
        fill=(255, 255, 255, 230),
    )
    img.alpha_composite(overlay)

    # Navy text centered in box
    tx = box_x + pad_x
    ty = y + pad_y
    draw.text((tx, ty), text, font=font, fill=COLOR_NAVY)
    return box_h


def make_card(card: dict):
    img = Image.new('RGBA', SIZE, COLOR_BG)
    draw = ImageDraw.Draw(img)

    font_main   = load_font(64)
    font_price  = load_font(38)
    font_hours  = load_font(26)
    font_accent = load_font(22)
    font_brand  = load_font(18)

    # Layout: calculate total block height to center vertically
    # main + price + hours + accent box + spacing
    spacing_after_main   = 28
    spacing_after_price  = 18
    spacing_after_hours  = 40
    spacing_brand_bottom = 28

    bbox_main  = draw.textbbox((0, 0), card['main'],  font=font_main)
    bbox_price = draw.textbbox((0, 0), card['price'], font=font_price)
    bbox_hours = draw.textbbox((0, 0), card['hours'], font=font_hours)
    bbox_accent = draw.textbbox((0, 0), card['accent'], font=font_accent)

    h_main   = bbox_main[3]  - bbox_main[1]
    h_price  = bbox_price[3] - bbox_price[1]
    h_hours  = bbox_hours[3] - bbox_hours[1]
    h_accent = bbox_accent[3] - bbox_accent[1] + 28  # +padding

    total_h = h_main + spacing_after_main + h_price + spacing_after_price + h_hours + spacing_after_hours + h_accent
    y = (SIZE[1] - total_h) // 2

    # Main text
    draw_centered_text(draw, y, card['main'], font_main, COLOR_WHITE)
    y += h_main + spacing_after_main

    # Price (gold)
    draw_centered_text(draw, y, card['price'], font_price, COLOR_GOLD)
    y += h_price + spacing_after_price

    # Hours (white 80% alpha)
    draw_centered_text(draw, y, card['hours'], font_hours, hex_with_alpha(COLOR_WHITE, 204))
    y += h_hours + spacing_after_hours

    # Accent box
    draw_accent_box(img, draw, y, card['accent'], font_accent)

    # Brand text bottom-right (60% alpha)
    brand = 'DEARROOM六本木'
    bbox_brand = draw.textbbox((0, 0), brand, font=font_brand)
    bw = bbox_brand[2] - bbox_brand[0]
    bh = bbox_brand[3] - bbox_brand[1]
    draw.text(
        (SIZE[0] - bw - 24, SIZE[1] - bh - spacing_brand_bottom),
        brand,
        font=font_brand,
        fill=hex_with_alpha(COLOR_WHITE, 153),
    )

    # Save
    out_path = os.path.join(OUTPUT_DIR, card['filename'])
    img.convert('RGB').save(out_path, 'PNG')
    return out_path


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    generated = []
    for card in CARDS:
        path = make_card(card)
        generated.append(path)
        print(f'  生成: {path}')
    print(f'\n完了！{len(generated)}枚のサムネイルを生成しました。')
    for p in generated:
        print(f'  {p}')


if __name__ == '__main__':
    main()
