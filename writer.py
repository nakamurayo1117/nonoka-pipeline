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
- 導入文（intro）：構成のintroをベースに300字程度に膨らませる。対象読者は大人の推し活女子（20〜30代・経済的に余裕がある・推し活に本気）。落ち着いたです・ます調で書く。SNS的な砕けた表現（「わかる〜！」「笑」「〜だよね」「〜していくね」「（私だけ？）」など）は絶対に使わない
- 各H2セクション：pointsの内容をもとにです・ます調で400〜500字で執筆
- 口調：「〜ですよね」「〜かもしれませんね」「〜ではないでしょうか」のような柔らかく親しみやすい文体に統一する
- キーワードは文章に自然に溶け込ませる。キーワードそのままの形を文中に出さない
- 全国の地名（仙台・札幌・横浜・大阪・福岡など）を羅列するセクションは作らない
- 地域情報を書く場合は東京・六本木に絞る
- 導入文は読者の悩みや共感から始める。「久しぶりに〜してみたとき」のような体験談スタートではなく「〜を感じたことはありませんか」「〜という経験はないでしょうか」のように読者に語りかける書き出しにする
- 各セクションに具体的なエピソードや例を入れて読み応えを出す
- まとめ・CTA：落ち着いたトーンで締める。絵文字なし
- CTA：構成のctaをもとに予約誘導文を書く。リンクは上記「CTAリンクフォーマット」の指示に従いHTMLのaタグ（UTM・data属性付き）で出力する
- 読みやすい改行・段落を入れる
- ののかコメント：各H2セクションの末尾に吹き出しを追加する。その見出しの内容に関連した一言を、ののか口調（明るく親しみやすい話し言葉）で書く
- 目次：構成のh2_sectionsの見出しをもとに自動生成する。アンカーは見出しテキストをそのまま使う（見出し側にアンカー記述不要）
- FAQセクション：まとめの一つ前にFAQセクションを設ける。記事のキーワード・テーマに関連した質問のみ3〜4個生成する。DEARROOMの料金・人数に関するFAQは入れない（SpaceInfoコンポーネントで対応済み）。フォーマット：Q&Aに##・###見出しは使わない／**Q. 質問文** の形式で太字にする／A. 回答文 は平文で書く／Q&Aの間に空行を入れる
- summary-boxの箇条書きルール：「この記事でわかること」は1項目20字以内・3項目まで、「こんな人におすすめ」は1項目15字以内・3項目まで、末尾の「この記事のまとめ」ボックスは1項目25字以内・3項目まで

見出し構造のルール：
- H2（##）：記事の大テーマを区切る（4〜6個）。見出し冒頭に絵文字1つを使ってOK
- H2直下には必ず1〜2文の導入文を書いてからH3を始める。H2の直後にいきなりH3を置かない
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
- 導入文（P・Aセクション）：落ち着いたです・ます調で書く。SNS的な砕けた表現（「わかる〜！」「笑」「〜だよね」「〜していくね」「（私だけ？）」など）は絶対に使わない
- 口調：「〜ですよね」「〜かもしれませんね」「〜ではないでしょうか」のような柔らかく親しみやすい文体に統一する
- 地域情報は東京・六本木に絞る
- 読みやすい改行・段落を入れる
- H2の見出しは各PASBECONAセクションの内容を表す自然な日本語にする（「P：」などのプレフィックスは付けない）
- ののかコメント：各H2セクションの末尾に吹き出しを追加する。その見出しの内容に関連した一言を、ののか口調（明るく親しみやすい話し言葉）で書く
- FAQセクション：まとめの一つ前にFAQセクションを設ける。記事のキーワード・テーマに関連した質問のみ3〜4個生成する。DEARROOMの料金・人数に関するFAQは入れない（SpaceInfoコンポーネントで対応済み）。フォーマット：Q&Aに##・###見出しは使わない／**Q. 質問文** の形式で太字にする／A. 回答文 は平文で書く／Q&Aの間に空行を入れる
- summary-boxの箇条書きルール：「この記事でわかること」は1項目20字以内・3項目まで、「こんな人におすすめ」は1項目15字以内・3項目まで、末尾の「この記事のまとめ」ボックスは1項目25字以内・3項目まで

見出し構造のルール：
- H2（##）：PASBECONAの各セクションに対応（8個）。見出し冒頭に絵文字1つを使ってOK
- H2直下には必ず1〜2文の導入文を書いてからH3を始める。H2の直後にいきなりH3を置かない
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
- 導入文（intro）：構成のintroをベースに300字程度に膨らませる。対象読者は大人の推し活女子（20〜30代・経済的に余裕がある・推し活に本気）。落ち着いたです・ます調で書く。SNS的な砕けた表現（「わかる〜！」「笑」「〜だよね」「〜していくね」「（私だけ？）」など）は絶対に使わない
- 各H2セクション：pointsの内容をもとにです・ます調で400〜500字で執筆
- 口調：「〜ですよね」「〜かもしれませんね」「〜ではないでしょうか」のような柔らかく親しみやすい文体に統一する
- キーワードは文章に自然に溶け込ませる。キーワードそのままの形を文中に出さない
- 全国の地名（仙台・札幌・横浜・大阪・福岡など）を羅列するセクションは作らない
- 地域情報を書く場合は東京・六本木に絞る
- 導入文は読者の悩みや共感から始める。「久しぶりに〜してみたとき」のような体験談スタートではなく「〜を感じたことはありませんか」「〜という経験はないでしょうか」のように読者に語りかける書き出しにする
- 各セクションに具体的なエピソードや例を入れて読み応えを出す
- まとめ・CTA：落ち着いたトーンで締める。絵文字なし
- CTA：構成のctaをもとに予約誘導文を書く。リンクは上記「CTAリンクフォーマット」の指示に従いHTMLのaタグ（UTM・data属性付き）で出力する
- 読みやすい改行・段落を入れる
- ののかコメント：各H2セクションの末尾に吹き出しを追加する。その見出しの内容に関連した一言を、ののか口調（明るく親しみやすい話し言葉）で書く
- 目次：構成のh2_sectionsの見出しをもとに自動生成する。アンカーは見出しテキストをそのまま使う（見出し側にアンカー記述不要）
- 比較強化ルール：各H2セクションの本文末尾（ののかコメントの直前）に、DEARROOMの優位性を自然に伝える誘導文を1〜2文追加する。他の選択肢と比較したときのDEARROOMの強みが伝わるようにする
- FAQセクション：まとめの一つ前にFAQセクションを設ける。記事のキーワード・テーマに関連した質問のみ3〜4個生成する。DEARROOMの料金・人数に関するFAQは入れない（SpaceInfoコンポーネントで対応済み）。フォーマット：Q&Aに##・###見出しは使わない／**Q. 質問文** の形式で太字にする／A. 回答文 は平文で書く／Q&Aの間に空行を入れる
- summary-boxの箇条書きルール：「この記事でわかること」は1項目20字以内・3項目まで、「こんな人におすすめ」は1項目15字以内・3項目まで、末尾の「この記事のまとめ」ボックスは1項目25字以内・3項目まで

見出し構造のルール：
- H2（##）：記事の大テーマを区切る（4〜6個）。見出し冒頭に絵文字1つを使ってOK
- H2直下には必ず1〜2文の導入文を書いてからH3を始める。H2の直後にいきなりH3を置かない
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


def load_facts() -> str:
    facts_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'facts.md')
    if not os.path.exists(facts_path):
        raise FileNotFoundError(
            'facts.md が見つかりません。リポジトリ直下に facts.md を作成してください。'
        )
    with open(facts_path, encoding='utf-8') as f:
        return f.read()


_INTENT_CTA_RULES = {
    'local_booking': (
        '予約CTA（DEARROOM六本木へのリンク）を冒頭・中間・締めの3か所に必ず配置する。'
        '全CTAに UTMパラメータと data属性（後述）を付与すること。'
    ),
    'national_affiliate': (
        '予約CTAは締め（まとめの後）の1回のみにする。'
        '冒頭・中間はアフィリエイトリンクや読者メリット情報を中心にする。'
        'アフィリリンクにも UTMパラメータと data属性を付与すること。'
    ),
    'soft': (
        'LINE/メルマガ等の捕捉CTAを中心に配置する。'
        '予約CTAは締めに1回のみ。'
        '捕捉CTAにも UTMパラメータと data属性を付与すること。'
    ),
}


def get_prompt_template(article_type: str) -> str:
    if article_type == 'pasbecona':
        return PROMPT_TEMPLATE_PASBECONA
    if article_type == 'comparison':
        return PROMPT_TEMPLATE_COMPARISON
    return PROMPT_TEMPLATE_SEO


# ── 決定論的後処理 ────────────────────────────────────────────────────────────
_SPACEMARKET_URL = 'https://spacemarket.com/p/AHbhuUbilSKvoqCw'


def _inject_frontmatter_intent(article: str, intent: str) -> str:
    """LLMがintentを落とした場合にfrontmatterへ決定論的に注入する。"""
    if re.search(r'^intent:', article, re.MULTILINE):
        return article  # already present
    def _add(m: re.Match) -> str:
        fm = m.group(1).rstrip('\n')
        return f'{fm}\nintent: "{intent}"\n{m.group(2)}'
    return re.sub(r'^(---\n[\s\S]*?)(^---)', _add, article, count=1, flags=re.MULTILINE)


def _enforce_cta_attributes(article: str, slug: str) -> str:
    """
    後処理: spacemarket URLへの全リンクをUTM付きHTML<a>に統一する。
    Markdown/HTML問わず文書内の出現順に top/mid/bottom を割り当てる
    （2ステップ処理だと Markdown→HTML の順序がずれるため、位置を先に収集して逆順置換）。
    """
    _pos_seq = ['top', 'mid', 'bottom']

    md_pat   = re.compile(r'\[([^\]]+)\]\(https://spacemarket\.com/p/[^)]+\)')
    html_pat = re.compile(
        r'<a\s+([^>]*href=["\']https://spacemarket\.com/p/[^"\']*["\'][^>]*)>',
        re.DOTALL,
    )

    # 全CTAを文書内の出現位置順に収集
    spans: list[tuple[int, int, str, re.Match]] = []
    for m in md_pat.finditer(article):
        spans.append((m.start(), m.end(), 'md', m))
    for m in html_pat.finditer(article):
        spans.append((m.start(), m.end(), 'html', m))
    spans.sort(key=lambda x: x[0])

    # 後ろから置換（文字位置がずれないよう逆順）
    for i, (start, end, typ, m) in reversed(list(enumerate(spans))):
        pos = _pos_seq[min(i, 2)]
        utm = f'utm_source=blog&utm_medium=cta&utm_campaign={slug}&utm_content={pos}'

        if typ == 'md':
            anchor = m.group(1)
            replacement = (
                f'<a href="{_SPACEMARKET_URL}?{utm}"'
                f' data-cta="booking" data-pos="{pos}" data-article="{slug}">'
                f'{anchor}</a>'
            )
        else:
            attrs = m.group(1)
            if 'data-cta' in attrs:
                continue  # already fully patched
            href_m = re.search(r'href=["\']([^"\']+)["\']', attrs)
            raw_href = href_m.group(1).split('?')[0] if href_m else _SPACEMARKET_URL
            replacement = (
                f'<a href="{raw_href}?{utm}"'
                f' data-cta="booking" data-pos="{pos}" data-article="{slug}">'
            )

        article = article[:start] + replacement + article[end:]

    return article


def postprocess_article(article: str, slug: str, intent: str) -> str:
    """frontmatter intent注入 + CTA属性付与の決定論的後処理。"""
    article = _inject_frontmatter_intent(article, intent)
    article = _enforce_cta_attributes(article, slug)
    return article


# ── 禁止コンテンツ検出（決定論的・後処理） ────────────────────────────────────

def _mask_exclusion_zones(article: str) -> str:
    """
    検査スコープ外領域を空白で埋め、行番号を保持したまま誤検知対象外にする。
    除外: frontmatter / <a>タグのhref属性値
    """
    masked = list(article)

    def blank(start: int, end: int) -> None:
        for i in range(start, end):
            if masked[i] != '\n':
                masked[i] = ' '

    # frontmatter（pubDate等の数値を評価スコアと誤検知しないため）
    fm = re.match(r'^---\n[\s\S]*?\n---\n?', article)
    if fm:
        blank(0, fm.end())

    # <a>タグのhref値（UTMパラメータの数字を金額・件数と誤検知しないため）
    for m in re.finditer(r'<a\b[^>]*>', article, re.DOTALL):
        tag_start = m.start()
        for hm in re.finditer(r'href=(["\'])([^"\']*)\1', m.group(0)):
            blank(tag_start + hm.start(2), tag_start + hm.end(2))

    # nonoka-comment ブロック（ののかの演出コメント・事実検証不要）
    _nc_pat = re.compile(
        r'<div\s+class=["\']nonoka-comment["\'][^>]*>'
        r'(?:(?!</div>)[\s\S])*</div>'
        r'(?:(?!</div>)[\s\S])*</div>',
        re.DOTALL,
    )
    for m in _nc_pat.finditer(article):
        blank(m.start(), m.end())

    return ''.join(masked)


def detect_forbidden_content(article: str, facts_text: str) -> list[dict]:
    """
    生成記事から禁止コンテンツを検出して Finding リストを返す。
    自動削除・修正はしない（検出・警告のみ）。

    Finding 構造:
      category:     "rating" | "review_count" | "price" | "review_fabrication"
      severity:     "block" | "warn"
      matched_text: 検出した実文字列
      line_no:      該当行番号（1始まり）
      message:      対処メッセージ
    """
    def _line_no(pos: int) -> int:
        return article[:pos].count('\n') + 1

    def _in_facts(text: str) -> bool:
        return text.strip() in facts_text

    masked = _mask_exclusion_zones(article)
    findings: list[dict] = []

    # ── Category 1: 評価スコア（block）──────────────────────────────────────
    _RATING_PATS = [
        re.compile(r'[★☆⭐]\s*\d+\.?\d*'),
        re.compile(r'評価\s*\d+\.\d+'),
        re.compile(r'(?<!\d)\d+\.\d+\s*点(?!満点)'),
        re.compile(r'(?<!\d)\d+\.\d+\s*[/／]\s*5(?!\d)'),
        re.compile(r'5\s*点満点中\s*\d+\.\d+'),
    ]
    for pat in _RATING_PATS:
        for m in pat.finditer(masked):
            text = article[m.start():m.end()].strip()
            if _in_facts(text):
                continue
            findings.append({
                'category': 'rating',
                'severity': 'block',
                'matched_text': text,
                'line_no': _line_no(m.start()),
                'message': 'facts.md非掲載の評価スコアです。削除し「スペースマーケットで高い評価をいただいています」等の定性表現に置換してください。',
            })

    # ── Category 2: レビュー件数（block）────────────────────────────────────
    _COUNT_PATS = [
        re.compile(r'\d+\s*件.{0,15}(レビュー|口コミ|評価|の声|コメント|投票)', re.DOTALL),
        re.compile(r'(レビュー|口コミ|評価|の声|コメント|投票).{0,15}\d+\s*件', re.DOTALL),
        re.compile(r'\d+\s*件の(レビュー|口コミ|評価)'),
    ]
    for pat in _COUNT_PATS:
        for m in pat.finditer(masked):
            text = article[m.start():m.end()].strip()
            if _in_facts(text):
                continue
            findings.append({
                'category': 'review_count',
                'severity': 'block',
                'matched_text': text,
                'line_no': _line_no(m.start()),
                'message': 'レビュー件数が記載されています。件数は変動するため削除し、定性表現に置換してください。',
            })

    # ── Category 3: 金額（warn）──────────────────────────────────────────────
    _PRICE_PATS = [
        re.compile(r'¥\s*\d[\d,]*'),
        re.compile(r'\d{1,3}(?:,\d{3})+\s*円'),
        re.compile(r'(?<!\d)\d{4,}\s*円'),
        re.compile(r'(?<!\d)\d+\s*万円'),
    ]
    _PRICE_ALLOW = re.compile(r'^(0\s*円|無料)')
    for pat in _PRICE_PATS:
        for m in pat.finditer(masked):
            text = article[m.start():m.end()].strip()
            if _PRICE_ALLOW.match(text) or _in_facts(text):
                continue
            findings.append({
                'category': 'price',
                'severity': 'warn',
                'matched_text': text,
                'line_no': _line_no(m.start()),
                'message': '具体的な金額が記載されています。料金は変動するため削除し、予約ページへの誘導に置換してください。',
            })

    # ── Category 4: 口コミ創作疑い（warn）───────────────────────────────────
    _QUOTE_CLUSTER = re.compile(r'(?:「[^」]{5,}」[\s、。]*){3,}')
    _PRESENTATION  = re.compile(r'という声|寄せられ|好評|多く寄せ|コメントが|感想|口コミ')
    for m in _QUOTE_CLUSTER.finditer(masked):
        ctx = masked[max(0, m.start() - 100):min(len(masked), m.end() + 100)]
        if not _PRESENTATION.search(ctx):
            continue
        text = article[m.start():m.end()].strip()
        short = text[:80] + ('…' if len(text) > 80 else '')
        findings.append({
            'category': 'review_fabrication',
            'severity': 'warn',
            'matched_text': short,
            'line_no': _line_no(m.start()),
            'message': '複数の口コミが並んでいます。実在するレビューのみ引用可。創作口コミは削除してください。',
        })

    # 重複除去（同一 category + line_no + matched_text）
    seen: set[tuple] = set()
    unique: list[dict] = []
    for f in findings:
        key = (f['category'], f['line_no'], f['matched_text'])
        if key not in seen:
            seen.add(key)
            unique.append(f)

    return unique


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

    facts = load_facts()
    client = anthropic.Anthropic(api_key=api_key)
    article_type = plan.get('article_type', 'seo')
    intent = plan.get('intent', 'local_booking')
    slug = plan.get('slug', 'unknown')
    include_faq = plan.get('include_faq', True)
    firsthand_block = plan.get('firsthand_block')
    internal_links = plan.get('internal_links', [])

    rules = load_rules()
    template = get_prompt_template(article_type)

    rules_section = f'# 執筆ルール（必ず遵守すること）\n\n{rules}\n\n---\n\n' if rules else ''

    facts_section = (
        '# DEARROOMファクトシート（使用可能な一次情報・厳守）\n'
        '以下に記載された内容だけが事実として使用可能。\n'
        '料金・設備スペック・アクセス・イベント実績・口コミ等のファクトは、\n'
        'このシートに書かれた内容のみ使用し、**ここに書かれていない事実を新規に創作・推測・誇張することは絶対禁止**。\n'
        'facts.md に該当記事KWに関連する情報が無い（または<TODO>のまま）場合は、\n'
        'firsthand_block を null にして事実の創作を行わないこと。\n\n'
        + facts
        + '\n\n---\n\n'
    )

    firsthand_section = ''
    if firsthand_block:
        idx = firsthand_block.get('insert_after_h2_index', 2)
        content = firsthand_block.get('content', '')
        firsthand_section = (
            f'# 一次情報ブロック（必ず本文に展開すること）\n'
            f'{idx + 1}番目のH2セクションの後に、以下の一次情報を文脈に合わせて1〜2段落で自然に展開する。\n'
            f'内容を改変・誇張しないこと。facts.md の内容のまま具体的に伝えること。\n\n'
            f'{content}\n\n---\n\n'
        )

    faq_section = (
        '# FAQセクション\n'
        + ('よくある質問セクションを含める（記事のキーワードに関連した質問3〜4問、Q./A.形式）。\n'
           if include_faq else
           'FAQセクションは含めない（include_faq=false）。\n')
        + '\n---\n\n'
    )

    cta_rule = _INTENT_CTA_RULES.get(intent, _INTENT_CTA_RULES['local_booking'])
    utm_section = (
        f'# CTAリンクフォーマット（すべてのCTA・アフィリリンクに適用・厳守）\n'
        f'intent: {intent}\n'
        f'CTA方針: {cta_rule}\n\n'
        f'CTA/アフィリリンクはMarkdownリンクではなく生HTMLのaタグで出力し、以下を必ず付与する:\n'
        f'- href に UTMパラメータ: ?utm_source=blog&utm_medium=cta&utm_campaign={slug}&utm_content=<top|mid|bottom>\n'
        f'- data-cta="booking|affiliate|soft"\n'
        f'- data-pos="top|mid|bottom"\n'
        f'- data-article="{slug}"\n\n'
        f'出力例（冒頭CTA）:\n'
        f'<a href="https://spacemarket.com/p/AHbhuUbilSKvoqCw?utm_source=blog&utm_medium=cta&utm_campaign={slug}&utm_content=top"\n'
        f'   data-cta="booking" data-pos="top" data-article="{slug}">DEARROOM六本木の予約はこちら</a>\n'
        f'\n---\n\n'
    )

    frontmatter_section = (
        f'# frontmatterへの追記（必須）\n'
        f'生成する記事のfrontmatterに以下フィールドを必ず含めること:\n'
        f'intent: "{intent}"\n'
        f'\n---\n\n'
    )

    internal_links_section = ''
    if internal_links:
        links_text = '\n'.join(
            f'- [{l.get("anchor", l.get("slug", ""))}](/blog/{l.get("slug", "")}) （{l.get("reason", "")}）'
            for l in internal_links
        )
        internal_links_section = (
            '# 内部リンク（本文中に自然な形で配置すること）\n'
            '以下の関連記事を本文中の適切な箇所にMarkdownリンクとして1〜2本挿入する:\n\n'
            + links_text
            + '\n\n---\n\n'
        )

    prompt = (
        rules_section
        + facts_section
        + firsthand_section
        + faq_section
        + utm_section
        + frontmatter_section
        + internal_links_section
        + template.format(
            plan_json=json.dumps(plan, ensure_ascii=False, indent=2),
            today=str(date.today()),
        )
    )

    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=8000,
        messages=[{'role': 'user', 'content': prompt}],
    )
    raw = strip_code_block(message.content[0].text)
    article = postprocess_article(raw, slug, intent)
    findings = detect_forbidden_content(article, facts)
    return article, findings


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
        article_raw, findings = generate_article(plan)
    except RuntimeError as e:
        print(f'エラー：{e}')
        sys.exit(1)

    article = strip_code_block(article_raw)
    out_path = save_article(seed, article)
    print(f'完了！{out_path} に保存しました。')
    if findings:
        print(f'\n⚠️ 品質チェック: {len(findings)}件の問題が検出されました')
        for f in findings:
            icon = '🔴' if f['severity'] == 'block' else '🟡'
            print(f'  {icon} [{f["category"]}] 行{f["line_no"]}: {f["matched_text"][:60]}')
            print(f'     → {f["message"]}')


if __name__ == '__main__':
    main()
