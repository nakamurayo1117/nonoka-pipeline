import re
import glob
import sys


def fix_file(filepath: str) -> int:
    with open(filepath, encoding='utf-8') as f:
        content = f.read()

    original = content

    # Build map: anchorN → heading text (before stripping anchors)
    anchor_map: dict[str, str] = {}
    for m in re.finditer(r'^#{1,6}\s+(.+?)\s+\{#(anchor\d+)\}', content, re.MULTILINE):
        heading_text, anchor_id = m.group(1).strip(), m.group(2)
        anchor_map[anchor_id] = heading_text

    # Remove ' {#anchorN}' from headings
    content = re.sub(r'\s+\{#anchor\d+\}', '', content)

    # Fix TOC links: (#anchorN) → (#heading-text)
    def replace_link(m: re.Match) -> str:
        anchor_id = m.group(1)
        if anchor_id in anchor_map:
            return f'(#{anchor_map[anchor_id]})'
        return m.group(0)

    content = re.sub(r'\(#(anchor\d+)\)', replace_link, content)

    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return 1
    return 0


def main(dirs: list[str]) -> None:
    total = 0
    for d in dirs:
        files = glob.glob(f'{d}/**/*.md', recursive=True) + glob.glob(f'{d}/*.md')
        for filepath in sorted(set(files)):
            changed = fix_file(filepath)
            if changed:
                print(f'  fixed: {filepath}')
                total += 1
    print(f'\n{total} file(s) updated.')


if __name__ == '__main__':
    targets = sys.argv[1:] if len(sys.argv) > 1 else [
        'output/articles',
    ]
    main(targets)
