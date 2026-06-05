import json
import os
import time
import requests
from datetime import date

HIRAGANA = list('あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん')
SUGGEST_URL = 'https://suggestqueries.google.com/complete/search'


def fetch_suggests(query: str) -> list:
    params = {'client': 'firefox', 'hl': 'ja', 'q': query}
    try:
        resp = requests.get(SUGGEST_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data[1] if len(data) > 1 else []
    except Exception:
        return []


def collect(seed: str) -> list:
    seen = set()
    for kana in HIRAGANA:
        query = f'{seed} {kana}'
        print(f'  → {query}')
        for kw in fetch_suggests(query):
            seen.add(kw)
        time.sleep(1.5)
    return sorted(seen)


def collect_with_progress(seed: str, callback=None) -> list:
    seen = set()
    for kana in HIRAGANA:
        query = f'{seed} {kana}'
        for kw in fetch_suggests(query):
            seen.add(kw)
        if callback:
            callback(query, len(seen))
        else:
            print(f'  → {query}')
        time.sleep(1.5)
    return sorted(seen)


def save_keywords(seed: str, keywords: list) -> str:
    dirpath = os.path.join('output', 'keywords')
    os.makedirs(dirpath, exist_ok=True)
    record = {
        'seed': seed,
        'keywords': keywords,
        'count': len(keywords),
        'collected_at': str(date.today()),
    }
    path = os.path.join(dirpath, f'keywords_{safe_filename(seed)}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
    return path


def safe_filename(seed: str) -> str:
    return seed.replace(' ', '')


def main():
    raw = input('キーワードを入力（複数はカンマ区切り）: ').strip()
    seeds = [s.strip() for s in raw.split(',') if s.strip()]

    total = 0

    for i, seed in enumerate(seeds, 1):
        print(f'\n[{i}/{len(seeds)}] {seed} を収集中...')
        keywords = collect(seed)
        count = len(keywords)
        total += count
        print(f'  → {count}件取得')

        record = {
            'seed': seed,
            'keywords': keywords,
            'count': count,
            'collected_at': str(date.today()),
        }

        dirpath = os.path.join('output', 'keywords')
        os.makedirs(dirpath, exist_ok=True)
        path = os.path.join(dirpath, f'keywords_{safe_filename(seed)}.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False, indent=2)

    print(f'\n完了！output/に保存しました。')
    print(f'合計：{total}件')


if __name__ == '__main__':
    main()
