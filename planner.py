import json
import os
import re
import sys
import glob
import anthropic


PROMPT_TEMPLATE = """以下の情報をもとに、SEOに強いブログ記事の構成をJSON形式で作って。

キーワードリスト：{keywords}
記事タイトル：{title}

---
## DEARROOMファクトシート（facts.md）
{facts}

## 既存記事一覧（corpus.json）
{corpus}
---

ブログの設定：
- 運営者：ののか（推し活大好きで六本木にシネマルームを作った女子）
- ターゲット：推し活が好きな女性
- 目的：記事を読んだ人をDEARROOM六本木（シネマルーム）の予約に誘導する

記事の口調ルール：
- 導入文：読者に語りかける柔らかいです・ます調。SNS的な砕けた表現（「わかる〜！」「笑」「〜だよね」など）は使わない
- 本文：です・ます調
- 見出し：体言止めまたは疑問形
- まとめ・CTA：落ち着いたトーンで締める。絵文字なし

**intent の判定ルール（必ず1つ選ぶ）**:
- "local_booking" … 場所比較・生誕祭・誕生日会・貸切上映会・東京/六本木エリア系（予約が自然なゴール）
- "national_affiliate" … 節約・お金・健康・恋愛・ひとり推し活・遠征など全国読者向けで予約に来ない層が主体
- "soft" … 上記の中間。LINE/メルマガ等の捕捉を主目的にする記事

**firsthand_block の規則（厳守）**:
- facts.md の内容から、この記事のキーワードに最も関連する事実を1つ選ぶ
- content は facts.md に書かれた内容のみ使用すること。創作・推測・誇張は絶対禁止
- 関連する事実がない（<TODO>のまま、または記事KWと無関係）場合は null にする

**internal_links の規則**:
- 既存記事一覧から同主題クラスタの関連記事を2〜3本選んで入れる
- 既存記事がない、または関連記事がなければ空配列

**include_faq の規則**:
- 疑問解決性・YMYL性が高くFAQが読者に有益な場合のみ true にする
- 全記事に一律FAQを付けない（テンプレ同一化防止）

**カニバリゼーションチェック**:
- 既存記事一覧の slug・title と記事KWを照合する
- 主題が重複する既存記事があれば cannibalization_warning: true と conflicting_slug を出力する
- 重複がなければ cannibalization_warning: false（conflicting_slug は省略）

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
  "cta": "DEARROOM六本木への予約誘導文（ののか口調）",
  "intent": "local_booking",
  "firsthand_block": {{
    "type": "price | photo | experience | comparison_table",
    "content": "facts.mdから選んだ一次情報のテキスト（創作禁止）",
    "insert_after_h2_index": 2
  }},
  "internal_links": [
    {{ "slug": "既存記事のslug", "anchor": "アンカーテキスト", "reason": "同クラスタ等" }}
  ],
  "include_faq": true,
  "cannibalization_warning": false
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


def load_facts() -> str:
    facts_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'facts.md')
    if not os.path.exists(facts_path):
        raise FileNotFoundError(
            'facts.md が見つかりません。リポジトリ直下に facts.md を作成してください。'
        )
    with open(facts_path, encoding='utf-8') as f:
        return f.read()


def load_corpus() -> list:
    corpus_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'corpus.json')
    if not os.path.exists(corpus_path):
        return []
    try:
        with open(corpus_path, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []


def generate_plan(seed: str, keywords: list[str], title: str) -> str:
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('環境変数 ANTHROPIC_API_KEY が設定されていません。')

    facts = load_facts()
    corpus = load_corpus()
    corpus_summary = json.dumps(
        [{'slug': a.get('slug', ''), 'title': a.get('title', ''), 'cluster': a.get('cluster', '')} for a in corpus],
        ensure_ascii=False,
    ) if corpus else '[]'

    client = anthropic.Anthropic(api_key=api_key)
    prompt = PROMPT_TEMPLATE.format(
        keywords=', '.join(keywords),
        title=title,
        facts=facts,
        corpus=corpus_summary,
    )

    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=6000,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return message.content[0].text


def _fix_json_literals(s):
    # 文字列リテラル内の改行・タブをエスケープ
    result = []
    in_str = False
    skip = False
    for ch in s:
        if skip:
            result.append(ch); skip = False; continue
        if ch == "\\" and in_str:
            skip = True; result.append(ch); continue
        if ch == "\"":
            in_str = not in_str; result.append(ch); continue
        if in_str and ch == "\n":
            result.append("\\n"); continue
        if in_str and ch == "\r":
            continue
        if in_str and ch == "\t":
            result.append("\\t"); continue
        result.append(ch)
    return "".join(result)


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

    # 曲引用符・全角引用符をストレートクォートに変換（unicodeエスケープで記述）
    cleaned = json_str
    replacements = [
        ("\u201c", "\""), ("\u201d", "\""),
        ("\u2018", "'"), ("\u2019", "'"),
        ("\u300c", "\""), ("\u300d", "\""),
        ("\u300e", "\""), ("\u300f", "\""),
    ]
    for old, new in replacements:
        cleaned = cleaned.replace(old, new)
    # 末尾カンマ除去
    cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
    # 文字列内リテラル改行を除去
    cleaned = _fix_json_literals(cleaned)
    return json.loads(cleaned)

def fill_plan_defaults(plan: dict) -> dict:
    """新スキーマフィールドが欠落していた場合のデフォルト補完。パイプラインを落とさない。"""
    plan.setdefault('intent', 'local_booking')
    plan.setdefault('firsthand_block', None)
    plan.setdefault('internal_links', [])
    plan.setdefault('include_faq', True)
    plan.setdefault('cannibalization_warning', False)
    return plan


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
