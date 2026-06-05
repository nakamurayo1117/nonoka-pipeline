import json
import os
import re
import sys
import glob
import anthropic


PROMPT_TEMPLATE = """以下のキーワードリストと記事タイトルをもとに、SEOに強いブログ記事の構成をJSON形式で作って。

キーワードリスト：{keywords}
記事タイトル：{title}

ブログの設定：
- 運営者：ののか（推し活大好きで六本木にシネマルームを作った女子）
- ターゲット：推し活が好きな女性
- 目的：記事を読んだ人をDEARROOM六本木（シネマルーム）の予約に誘導する

記事の口調ルール：
- 導入文：ののかキャラの口調で親しみやすく
- 本文：です・ます調
- 見出し：体言止めまたは疑問形
- まとめ・CTA：ののかキャラの口調で締める

出力はJSON形式のみ。余計な説明は不要。

{{
  "title": "記事タイトル",
  "slug": "url用のローマ字スラッグ",
  "meta_description": "120字以内の説明文",
  "intro": "導入文（200字程度・ののか口調）",
  "h2_sections": [
    {{
      "heading": "見出し",
      "points": ["ポイント1", "ポイント2", "ポイント3"],
      "keywords": ["使うキーワード"]
    }}
  ],
  "outro": "まとめ文（ののか口調）",
  "cta": "DEARROOM六本木への予約誘導文（ののか口調）"
}}"""


ARTICLE_TYPES = {
    '1': ('pasbecona', '悩み解決系（PASBECONA構成）'),
    '2': ('seo', '情報提供系（通常SEO構成）'),
    '3': ('comparison', '比較系（通常SEO構成＋CTA強化）'),
}


def select_article_type() -> str:
    print('\n記事タイプを選択してください：')
    for key, (_, label) in ARTICLE_TYPES.items():
        print(f'  {key}. {label}')
    while True:
        raw = input('番号を入力: ').strip()
        if raw in ARTICLE_TYPES:
            type_key, label = ARTICLE_TYPES[raw]
            print(f'選択：{label}')
            return type_key
        print('正しい番号を入力してください。')


def list_keyword_files() -> list[str]:
    files = sorted(glob.glob('output/keywords/keywords_*.json'))
    return files


def select_file(files: list[str]) -> str:
    print('キーワードファイルを選んでください：')
    for i, f in enumerate(files, 1):
        print(f'  {i}. {f}')
    while True:
        raw = input('番号を入力: ').strip()
        if raw.isdigit() and 1 <= int(raw) <= len(files):
            return files[int(raw) - 1]
        print('正しい番号を入力してください。')


def load_keywords(path: str) -> tuple[str, list[str]]:
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    return data['seed'], data['keywords']


def generate_plan(seed: str, keywords: list[str], title: str) -> str:
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('環境変数 ANTHROPIC_API_KEY が設定されていません。')

    client = anthropic.Anthropic(api_key=api_key)
    prompt = PROMPT_TEMPLATE.format(
        keywords=', '.join(keywords),
        title=title,
    )

    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=6000,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return message.content[0].text


def parse_plan_json(text: str) -> dict:
    code_block = re.search(r'```json\s*([\s\S]*?)\s*```', text)
    if code_block:
        json_str = code_block.group(1)
    else:
        start = text.find('{')
        end = text.rfind('}')
        if start == -1 or end == -1:
            raise ValueError('APIレスポンスにJSONが見つかりませんでした')
        json_str = text[start:end + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    # 曲引用符・全角引用符をストレートクォートに変換
    cleaned = json_str
    for old, new in [('“', '"'), ('”', '"'), ('‘', "'"), ('’', "'"),
                     ('「', '"'), ('」', '"'), ('『', '"'), ('』', '"')]:
        cleaned = cleaned.replace(old, new)
    # 末尾カンマ除去
    cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
    return json.loads(cleaned)


def repair_plan_json(broken_text: str) -> str:
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=6000,
        messages=[{
            'role': 'user',
            'content': f'以下のテキストからJSONを抽出し、構文エラーを修正して、有効なJSONのみを出力してください。説明は不要です。\n\n{broken_text}'
        }],
    )
    return message.content[0].text


def save_plan(seed: str, plan: dict) -> str:
    dirpath = os.path.join('output', 'plans')
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(dirpath, f'plan_{safe_filename(seed)}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    return path


def safe_filename(seed: str) -> str:
    return seed.replace(' ', '')


def main():
    files = list_keyword_files()
    if not files:
        print('output/ フォルダにキーワードファイルが見つかりません。先に collector.py を実行してください。')
        sys.exit(1)

    selected = select_file(files)
    seed, keywords = load_keywords(selected)
    print(f'\nシード：{seed}  キーワード数：{len(keywords)}件')

    title = input('記事タイトルを入力してください: ').strip()
    if not title:
        print('タイトルが入力されていません。')
        sys.exit(1)

    article_type = select_article_type()

    print('\nClaude APIで記事構成を生成中...')
    try:
        result_text = generate_plan(seed, keywords, title)
    except RuntimeError as e:
        print(f'エラー：{e}')
        sys.exit(1)

    plans_dir = os.path.join('output', 'plans')
    os.makedirs(plans_dir, exist_ok=True)
    raw_path = os.path.join(plans_dir, f'plan_raw_{safe_filename(seed)}.txt')
    try:
        plan = parse_plan_json(result_text)
    except (ValueError, json.JSONDecodeError) as e:
        print(f'エラー：JSONのパースに失敗しました: {e}')
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write(result_text)
        print(f'レスポンス全文を {raw_path} に保存しました。内容を確認してください。')
        sys.exit(1)

    plan['article_type'] = article_type
    out_path = save_plan(seed, plan)
    print(f'\n完了！{out_path} に保存しました。')


if __name__ == '__main__':
    main()
