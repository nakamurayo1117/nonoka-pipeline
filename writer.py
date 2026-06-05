import json
import os
import re
import sys
import glob
import anthropic
from datetime import date


PROMPT_TEMPLATE_SEO = """以下の記事構成をもとに、ブログ記事の本文をMarkdown形式で書いて。

構成データ：{plan_json}

執筆ルール：
- 文字数：3000〜3500字
- 導入文（intro）：構成のintroをベースに300字程度に膨らませる。対象読者は大人の推し活女子（20〜30代・経済的に余裕がある・推し活に本気）。落ち着いたトーンで書く
- 各H2セクション：pointsの内容をもとにです・ます調で400〜500字で執筆
- 口調：「〜ですよね」「〜かもしれませんね」「〜ではないでしょうか」のような柔らかく親しみやすい文体に統一する
- キーワードは文章に自然に溶け込ませる。キーワードそのままの形を文中に出さない
- 全国の地名（仙台・札幌・横浜・大阪・福岡など）を羅列するセクションは作らない
- 地域情報を書く場合は東京・六本木に絞る
- 導入文は読者の悩みや共感から始める。「久しぶりに〜してみたとき」のような体験談スタートではなく「〜を感じたことはありませんか」「〜という経験はないでしょうか」のように読者に語りかける書き出しにする
- 各セクションに具体的なエピソードや例を入れて読み応えを出す
- まとめ・CTA：落ち着いたトーンで締める。絵文字なし
- CTA：構成のctaをもとに、予約リンクは[DEARROOM六本木の予約はこちら](https://spacemarket.com/p/AHbhuUbilSKvoqCw)に置き換える
- 読みやすい改行・段落を入れる
- ののかコメント：各H2セクションの末尾に吹き出しを追加する。その見出しの内容に関連した一言を、ののか口調（明るく親しみやすい話し言葉）で書く
- 目次：構成のh2_sectionsの見出しをもとに自動生成する。アンカーは見出しテキストをそのまま使う（見出し側にアンカー記述不要）
- FAQセクション：まとめの一つ前にFAQセクションを設ける。記事のキーワードに関連した質問3〜4個＋共通FAQ2個（料金・人数）を末尾に必ず追加する。料金は明記せず予約ページに誘導する。フォーマット：Q&Aに##・###見出しは使わない／**Q. 質問文** の形式で太字にする／A. 回答文 は平文で書く／Q&Aの間に空行を入れる
- summary-boxの箇条書きルール：「この記事でわかること」は1項目20字以内・3項目まで、「こんな人におすすめ」は1項目15字以内・3項目まで、末尾の「この記事のまとめ」ボックスは1項目25字以内・3項目まで

見出し構造のルール：
- H2（##）：記事の大テーマを区切る（4〜6個）。見出し冒頭に絵文字1つを使ってOK
- H3（###）：H2の中を2〜3個に細分化する。段落の途中に混入しないようにする
- 例：
  ## 🎬 カラオケ推し活の限界
  ### 画質・音質の問題
  ### 持ち込みルールの制約
  ### 空間の自由度の低さ

太字のルール：
- 各段落で最も重要な一文または共感ポイントを太字にする
- 1段落あたり1〜2箇所まで
- 推しへのメリット・DEARROOMの強みは必ず太字で強調する
- summary-box・まとめボックスの箇条書き見出しにも使う

中間CTAのルール：
- H2セクションの2〜3番目の後に1回、読者の共感・興味が最も高まった直後に挿入する
- 文脈に合わせた一言＋リンクの形式にする
- 例：
  > **大画面で推しのライブを見たい方は、[DEARROOM六本木](https://spacemarket.com/p/AHbhuUbilSKvoqCw)をチェックしてみてください。**

Markdown出力形式（この順番・構造を厳守すること）：
---
title: "タイトル"
slug: "スラッグ"
description: "メタディスクリプション"
pubDate: {today}
updatedDate: {today}
---

<div class="summary-box">

**この記事でわかること**
- ポイント1（20字以内）
- ポイント2（20字以内）
- ポイント3（20字以内）

**こんな人におすすめ**
- ターゲット読者1（15字以内）
- ターゲット読者2（15字以内）
- ターゲット読者3（15字以内）

</div>

## 目次
- [見出し1テキスト](#見出し1テキスト)
- [見出し2テキスト](#見出し2テキスト)
- [見出し3テキスト](#見出し3テキスト)
（構成のh2_sectionsに合わせて全見出しを列挙する）

<div class="cta-box">
推し活の理想の空間、六本木にあります。<br>
<a href="https://spacemarket.com/p/AHbhuUbilSKvoqCw">DEARROOM六本木の予約はこちら</a>
</div>

導入文（300字程度）

## 見出し1

本文（400〜500字）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント（その見出しの内容に関連した一言・ののか口調）</div>
</div>

## 見出し2

本文（400〜500字）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント</div>
</div>

（以下、全見出しに同様のパターンを繰り返す）

## よくある質問

（記事のキーワードに関連した質問を3〜4個生成する。Q. ～ / A. ～ 形式）

**Q. 料金はいくらですか？**
A. プランや利用時間帯によって異なります。最新の料金は予約ページからご確認ください。→[DEARROOM六本木の予約ページ](https://spacemarket.com/p/AHbhuUbilSKvoqCw)

**Q. 何人まで利用できますか？**
A. 最大10名までご利用いただけます。少人数から大人数まで対応しています。

## まとめ

まとめ文（200字）

<div class="summary-box" style="background:#FFF8E1;">

**この記事のまとめ**
- まとめポイント1
- まとめポイント2
- まとめポイント3

</div>

---

<div class="cta-box">
（CTAテキスト）<br>
<a href="https://spacemarket.com/p/AHbhuUbilSKvoqCw">DEARROOM六本木の予約はこちら</a>
</div>

---
好きを、全力で。

推しへの愛に、妥協したくない。
そんな気持ちから、六本木にシネマルームを作りました。
このブログは、推し活をもっと豊かにしたいすべての人へ向けて。"""


PROMPT_TEMPLATE_PASBECONA = """以下のPASBECONA構成で、ブログ記事の本文をMarkdown形式で書いて。

構成データ（タイトル・スラッグ・キーワードの参照に使用）：{plan_json}

PASBECONA構成ルール（この順番で8つのH2セクションを作成する）：
- P（問題提起）：ターゲットが抱える悩みを共感ベースで提示（200字）
- A（親近感）：その悩みは珍しくないことを伝える（150字）
- S（解決策）：DEARROOMというシネマルームで解決できることを示す（200字）
- B（ベネフィット）：利用後の理想の未来を具体的に描く（200字）
- E（証拠）：スペースマーケットのレビュー評価4.6・53件を引用（150字）
- C（中身）：DEARROOMの具体的な設備・特徴を説明（300字）
- O（提案）：今すぐ予約できることを伝える（150字）
- N（絞り込み）：こんな人におすすめと明示（150字）

共通執筆ルール：
- 口調：「〜ですよね」「〜かもしれませんね」「〜ではないでしょうか」のような柔らかく親しみやすい文体に統一する
- 地域情報は東京・六本木に絞る
- 読みやすい改行・段落を入れる
- H2の見出しは各PASBECONAセクションの内容を表す自然な日本語にする（「P：」などのプレフィックスは付けない）
- ののかコメント：各H2セクションの末尾に吹き出しを追加する。その見出しの内容に関連した一言を、ののか口調（明るく親しみやすい話し言葉）で書く
- FAQセクション：まとめの一つ前にFAQセクションを設ける。記事内容に関連した質問3〜4個＋共通FAQ2個（料金・人数）を末尾に必ず追加する。料金は明記せず予約ページに誘導する。フォーマット：Q&Aに##・###見出しは使わない／**Q. 質問文** の形式で太字にする／A. 回答文 は平文で書く／Q&Aの間に空行を入れる
- summary-boxの箇条書きルール：「この記事でわかること」は1項目20字以内・3項目まで、「こんな人におすすめ」は1項目15字以内・3項目まで、末尾の「この記事のまとめ」ボックスは1項目25字以内・3項目まで

見出し構造のルール：
- H2（##）：PASBECONAの各セクションに対応（8個）。見出し冒頭に絵文字1つを使ってOK
- H3（###）：H2の中を2〜3個に細分化して情報を整理する
- 段落の途中に##・###が混入しないようにする

太字のルール：
- 各段落で最も重要な一文または共感ポイントを太字にする
- 1段落あたり1〜2箇所まで
- 推しへのメリット・DEARROOMの強みは必ず太字で強調する
- summary-boxの箇条書き見出しにも使う

中間CTAのルール：
- S（解決策）またはB（ベネフィット）セクションの直後に1回挿入する
- 文脈に合わせた一言＋リンクの形式にする
- 例：
  > **推し活の理想の空間を体験したい方は、[DEARROOM六本木](https://spacemarket.com/p/AHbhuUbilSKvoqCw)をご覧ください。**

Markdown出力形式（この順番・構造を厳守すること）：
---
title: "タイトル"
slug: "スラッグ"
description: "メタディスクリプション"
pubDate: {today}
updatedDate: {today}
---

<div class="summary-box">

**この記事でわかること**
- ポイント1（20字以内）
- ポイント2（20字以内）
- ポイント3（20字以内）

**こんな人におすすめ**
- ターゲット読者1（15字以内）
- ターゲット読者2（15字以内）
- ターゲット読者3（15字以内）

</div>

## 目次
- [P見出しテキスト](#P見出しテキスト)
- [A見出しテキスト](#A見出しテキスト)
- [S見出しテキスト](#S見出しテキスト)
- [B見出しテキスト](#B見出しテキスト)
- [E見出しテキスト](#E見出しテキスト)
- [C見出しテキスト](#C見出しテキスト)
- [O見出しテキスト](#O見出しテキスト)
- [N見出しテキスト](#N見出しテキスト)
- [よくある質問](#よくある質問)
- [まとめ](#まとめ)

<div class="cta-box">
推し活の理想の空間、六本木にあります。<br>
<a href="https://spacemarket.com/p/AHbhuUbilSKvoqCw">DEARROOM六本木の予約はこちら</a>
</div>

## 問題提起の見出し

本文（P：問題提起・200字）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント（ののか口調）</div>
</div>

## 親近感の見出し

本文（A：親近感・150字）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント</div>
</div>

## 解決策の見出し

本文（S：解決策・200字）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント</div>
</div>

## ベネフィットの見出し

本文（B：ベネフィット・200字）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント</div>
</div>

## 証拠の見出し

本文（E：スペースマーケット評価4.6・53件を引用・150字）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント</div>
</div>

## 特徴の見出し

本文（C：DEARROOMの設備・特徴・300字）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント</div>
</div>

## 提案の見出し

本文（O：今すぐ予約への提案・150字）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント</div>
</div>

## こんな人向けの見出し

本文（N：こんな人におすすめの絞り込み・150字）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント</div>
</div>

## よくある質問

（記事内容に関連した質問を3〜4個生成する。Q. ～ / A. ～ 形式）

**Q. 料金はいくらですか？**
A. プランや利用時間帯によって異なります。最新の料金は予約ページからご確認ください。→[DEARROOM六本木の予約ページ](https://spacemarket.com/p/AHbhuUbilSKvoqCw)

**Q. 何人まで利用できますか？**
A. 最大10名までご利用いただけます。少人数から大人数まで対応しています。

## まとめ

まとめ文＋行動喚起（A：100字程度）

<div class="summary-box" style="background:#FFF8E1;">

**この記事のまとめ**
- まとめポイント1
- まとめポイント2
- まとめポイント3

</div>

---

<div class="cta-box">
（CTAテキスト）<br>
<a href="https://spacemarket.com/p/AHbhuUbilSKvoqCw">DEARROOM六本木の予約はこちら</a>
</div>

---
好きを、全力で。

推しへの愛に、妥協したくない。
そんな気持ちから、六本木にシネマルームを作りました。
このブログは、推し活をもっと豊かにしたいすべての人へ向けて。"""


PROMPT_TEMPLATE_COMPARISON = """以下の記事構成をもとに、比較系ブログ記事の本文をMarkdown形式で書いて。

構成データ：{plan_json}

執筆ルール：
- 文字数：3000〜3500字
- 導入文（intro）：構成のintroをベースに300字程度に膨らませる。対象読者は大人の推し活女子（20〜30代・経済的に余裕がある・推し活に本気）。落ち着いたトーンで書く
- 各H2セクション：pointsの内容をもとにです・ます調で400〜500字で執筆
- 口調：「〜ですよね」「〜かもしれませんね」「〜ではないでしょうか」のような柔らかく親しみやすい文体に統一する
- キーワードは文章に自然に溶け込ませる。キーワードそのままの形を文中に出さない
- 全国の地名（仙台・札幌・横浜・大阪・福岡など）を羅列するセクションは作らない
- 地域情報を書く場合は東京・六本木に絞る
- 導入文は読者の悩みや共感から始める。「久しぶりに〜してみたとき」のような体験談スタートではなく「〜を感じたことはありませんか」「〜という経験はないでしょうか」のように読者に語りかける書き出しにする
- 各セクションに具体的なエピソードや例を入れて読み応えを出す
- まとめ・CTA：落ち着いたトーンで締める。絵文字なし
- CTA：構成のctaをもとに、予約リンクは[DEARROOM六本木の予約はこちら](https://spacemarket.com/p/AHbhuUbilSKvoqCw)に置き換える
- 読みやすい改行・段落を入れる
- ののかコメント：各H2セクションの末尾に吹き出しを追加する。その見出しの内容に関連した一言を、ののか口調（明るく親しみやすい話し言葉）で書く
- 目次：構成のh2_sectionsの見出しをもとに自動生成する。アンカーは見出しテキストをそのまま使う（見出し側にアンカー記述不要）
- 比較強化ルール：各H2セクションの本文末尾（ののかコメントの直前）に、DEARROOMの優位性を自然に伝える誘導文を1〜2文追加する。他の選択肢と比較したときのDEARROOMの強みが伝わるようにする
- FAQセクション：まとめの一つ前にFAQセクションを設ける。比較記事のキーワードに関連した質問3〜4個＋共通FAQ2個（料金・人数）を末尾に必ず追加する。料金は明記せず予約ページに誘導する。フォーマット：Q&Aに##・###見出しは使わない／**Q. 質問文** の形式で太字にする／A. 回答文 は平文で書く／Q&Aの間に空行を入れる
- summary-boxの箇条書きルール：「この記事でわかること」は1項目20字以内・3項目まで、「こんな人におすすめ」は1項目15字以内・3項目まで、末尾の「この記事のまとめ」ボックスは1項目25字以内・3項目まで

見出し構造のルール：
- H2（##）：記事の大テーマを区切る（4〜6個）。見出し冒頭に絵文字1つを使ってOK
- H3（###）：H2の中を2〜3個に細分化する。段落の途中に混入しないようにする
- 例：
  ## 🎬 カラオケ推し活の限界
  ### 画質・音質の問題
  ### 持ち込みルールの制約
  ### 空間の自由度の低さ

太字のルール：
- 各段落で最も重要な一文または共感ポイントを太字にする
- 1段落あたり1〜2箇所まで
- 推しへのメリット・DEARROOMの強みは必ず太字で強調する
- summary-box・まとめボックスの箇条書き見出しにも使う

中間CTAのルール：
- H2セクションの2〜3番目の後に1回、読者の共感・興味が最も高まった直後に挿入する
- 文脈に合わせた一言＋リンクの形式にする
- 例：
  > **比較して選びたい方は、[DEARROOM六本木](https://spacemarket.com/p/AHbhuUbilSKvoqCw)をチェックしてみてください。**

Markdown出力形式（この順番・構造を厳守すること）：
---
title: "タイトル"
slug: "スラッグ"
description: "メタディスクリプション"
pubDate: {today}
updatedDate: {today}
---

<div class="summary-box">

**この記事でわかること**
- ポイント1（20字以内）
- ポイント2（20字以内）
- ポイント3（20字以内）

**こんな人におすすめ**
- ターゲット読者1（15字以内）
- ターゲット読者2（15字以内）
- ターゲット読者3（15字以内）

</div>

## 目次
- [見出し1テキスト](#見出し1テキスト)
- [見出し2テキスト](#見出し2テキスト)
- [見出し3テキスト](#見出し3テキスト)
（構成のh2_sectionsに合わせて全見出しを列挙する）

<div class="cta-box">
推し活の理想の空間、六本木にあります。<br>
<a href="https://spacemarket.com/p/AHbhuUbilSKvoqCw">DEARROOM六本木の予約はこちら</a>
</div>

導入文（300字程度）

## 見出し1

本文（400〜500字）

DEARROOMへの自然な誘導文（1〜2文）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント（その見出しの内容に関連した一言・ののか口調）</div>
</div>

## 見出し2

本文（400〜500字）

DEARROOMへの自然な誘導文（1〜2文）

<div class="nonoka-comment">
<img src="/images/nonoka-icon.png" alt="ののか">
<div class="bubble">ののかの一言コメント</div>
</div>

（以下、全見出しに同様のパターンを繰り返す）

## よくある質問

（記事のキーワードに関連した質問を3〜4個生成する。Q. ～ / A. ～ 形式）

**Q. 料金はいくらですか？**
A. プランや利用時間帯によって異なります。最新の料金は予約ページからご確認ください。→[DEARROOM六本木の予約ページ](https://spacemarket.com/p/AHbhuUbilSKvoqCw)

**Q. 何人まで利用できますか？**
A. 最大10名までご利用いただけます。少人数から大人数まで対応しています。

## まとめ

まとめ文（200字）

<div class="summary-box" style="background:#FFF8E1;">

**この記事のまとめ**
- まとめポイント1
- まとめポイント2
- まとめポイント3

</div>

---

<div class="cta-box">
（CTAテキスト）<br>
<a href="https://spacemarket.com/p/AHbhuUbilSKvoqCw">DEARROOM六本木の予約はこちら</a>
</div>

---
好きを、全力で。

推しへの愛に、妥協したくない。
そんな気持ちから、六本木にシネマルームを作りました。
このブログは、推し活をもっと豊かにしたいすべての人へ向けて。"""


def load_rules() -> str:
    rules_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rules.md')
    if os.path.exists(rules_path):
        with open(rules_path, encoding='utf-8') as f:
            return f.read()
    return ''


def get_prompt_template(article_type: str) -> str:
    if article_type == 'pasbecona':
        return PROMPT_TEMPLATE_PASBECONA
    if article_type == 'comparison':
        return PROMPT_TEMPLATE_COMPARISON
    return PROMPT_TEMPLATE_SEO


def list_plan_files() -> list[str]:
    return sorted(glob.glob('output/plans/plan_*.json'))


def select_file(files: list[str]) -> str:
    print('構成ファイルを選んでください：')
    for i, f in enumerate(files, 1):
        print(f'  {i}. {f}')
    while True:
        raw = input('番号を入力: ').strip()
        if raw.isdigit() and 1 <= int(raw) <= len(files):
            return files[int(raw) - 1]
        print('正しい番号を入力してください。')


def load_plan(path: str) -> dict:
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def seed_from_path(path: str) -> str:
    basename = os.path.basename(path)
    return basename[len('plan_'):-len('.json')]


def generate_article(plan: dict) -> str:
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('環境変数 ANTHROPIC_API_KEY が設定されていません。')

    client = anthropic.Anthropic(api_key=api_key)
    article_type = plan.get('article_type', 'seo')
    rules = load_rules()
    template = get_prompt_template(article_type)
    rules_section = f'# 執筆ルール（必ず遵守すること）\n\n{rules}\n\n---\n\n' if rules else ''
    prompt = rules_section + template.format(
        plan_json=json.dumps(plan, ensure_ascii=False, indent=2),
        today=str(date.today()),
    )

    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=8000,
        messages=[{'role': 'user', 'content': prompt}],
    )
    return message.content[0].text


def strip_code_block(text: str) -> str:
    text = re.sub(r'^```(?:markdown)?\n?', '', text.strip())
    text = re.sub(r'\n?```$', '', text.strip())
    return text


def save_article(seed: str, article: str) -> str:
    dirpath = os.path.join('output', 'articles')
    os.makedirs(dirpath, exist_ok=True)
    path = os.path.join(dirpath, f'article_{seed}.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(article)
    return path


def main():
    files = list_plan_files()
    if not files:
        print('output/ フォルダに構成ファイルが見つかりません。先に planner.py を実行してください。')
        sys.exit(1)

    selected = select_file(files)
    plan = load_plan(selected)
    seed = seed_from_path(selected)

    article_type = plan.get('article_type', 'seo')
    type_labels = {'pasbecona': '悩み解決系（PASBECONA構成）', 'seo': '情報提供系（通常SEO構成）', 'comparison': '比較系（通常SEO構成＋CTA強化）'}
    print(f'\n記事タイプ：{type_labels.get(article_type, article_type)}')

    print('\n記事本文を生成中...')
    try:
        article_raw = generate_article(plan)
    except RuntimeError as e:
        print(f'エラー：{e}')
        sys.exit(1)

    article = strip_code_block(article_raw)
    out_path = save_article(seed, article)
    print(f'完了！{out_path} に保存しました。')


if __name__ == '__main__':
    main()
