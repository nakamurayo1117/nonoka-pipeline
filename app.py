import glob
import json
import os
import queue
import re
import threading
from flask import Flask, Response, request, jsonify

from collector import collect_with_progress, save_keywords, safe_filename
from planner import generate_plan, parse_plan_json, save_plan
from writer import generate_article, strip_code_block, save_article
from publisher import extract_slug, publish_to_blog, deploy_to_vercel, push_to_github

app = Flask(__name__)


def sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def parse_frontmatter(content: str) -> dict:
    result = {'title': '', 'pubDate': '', 'slug': ''}
    fm = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    if not fm:
        return result
    for line in fm.group(1).splitlines():
        for key in ('title', 'pubDate', 'slug'):
            m = re.match(rf'^{key}:\s*["\']?(.+?)["\']?\s*$', line)
            if m:
                result[key] = m.group(1).strip()
    return result


def list_articles() -> list:
    files = glob.glob(os.path.join('output', 'articles', 'article_*.md'))
    articles = []
    for path in sorted(files):
        filename = os.path.basename(path)
        try:
            with open(path, encoding='utf-8') as f:
                content = f.read()
        except Exception:
            continue
        meta = parse_frontmatter(content)
        meta['filename'] = filename
        articles.append(meta)
    articles.sort(key=lambda x: x.get('pubDate', ''), reverse=True)
    return articles


@app.route('/')
def index():
    return HTML, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/api/plans')
def list_plans():
    files = sorted(glob.glob(os.path.join('output', 'plans', 'plan_*.json')))
    result = []
    for path in files:
        filename = os.path.basename(path)
        if filename.startswith('plan_raw_'):
            continue
        try:
            with open(path, encoding='utf-8') as f:
                plan = json.load(f)
        except Exception:
            continue
        result.append({
            'filename': filename,
            'title': plan.get('title', filename),
            'article_type': plan.get('article_type', 'seo'),
        })
    return jsonify(result)


@app.route('/generate', methods=['POST'])
def generate():
    data = request.get_json()
    mode = int(data.get('mode', 1))
    article_type = (data.get('article_type') or 'seo').strip()

    seed = title = plan_filename = ''

    if mode in (1, 2):
        seed = (data.get('seed') or '').strip()
        title = (data.get('title') or '').strip()
        if not seed or not title:
            return jsonify({'error': 'シードキーワードと記事タイトルを入力してください'}), 400
    elif mode == 3:
        plan_filename = (data.get('plan_filename') or '').strip()
        if not plan_filename:
            return jsonify({'error': '構成ファイルを選択してください'}), 400
    else:
        return jsonify({'error': '不正なモードです'}), 400

    def stream():
        # ── Mode 1: フルパイプライン ──────────────────────────────────
        if mode == 1:
            yield sse({'step': 'collect_start', 'message': f'「{seed}」のキーワードを収集中...'})

            q = queue.Queue()
            result_holder = []

            def run_collect():
                try:
                    def on_progress(query, count):
                        q.put(('progress', query, count))
                    kws = collect_with_progress(seed, callback=on_progress)
                    result_holder.append(kws)
                    q.put(('done', None, None))
                except Exception as e:
                    q.put(('error', str(e), None))

            t = threading.Thread(target=run_collect, daemon=True)
            t.start()

            while True:
                item = q.get()
                kind = item[0]
                if kind == 'progress':
                    yield sse({'step': 'collect_progress', 'message': f'  → {item[1]}（{item[2]}件）'})
                elif kind == 'done':
                    break
                elif kind == 'error':
                    yield sse({'step': 'error', 'message': item[1]})
                    return

            t.join()
            keywords = result_holder[0]

            if len(keywords) == 0:
                yield sse({'step': 'collect_warn',
                           'message': f'収集件数0件のため、「{seed}」をそのままキーワードとして使用します（モード2に自動切替）'})
                keywords = seed.split()
                if not keywords:
                    keywords = [seed]
            else:
                save_keywords(seed, keywords)
                yield sse({'step': 'collect_done', 'message': f'収集完了！{len(keywords)}件のキーワードを取得しました'})

            # Plan
            yield sse({'step': 'plan_start', 'message': 'AIで記事構成を生成中...'})
            try:
                plan_text = generate_plan(seed, keywords, title)
            except Exception as e:
                yield sse({'step': 'error', 'message': f'[planner] generate_plan 失敗: {type(e).__name__}: {e}'})
                return
            try:
                plan = parse_plan_json(plan_text)
            except Exception as e:
                yield sse({'step': 'error', 'message': f'[planner] JSONパース失敗: {type(e).__name__}: {e} — 冒頭: {plan_text[:200]}'})
                return
            plan['article_type'] = article_type
            save_plan(seed, plan)
            yield sse({'step': 'plan_done', 'message': '記事構成の生成完了！'})

            # Write
            yield sse({'step': 'write_start', 'message': 'AIで記事本文を執筆中...'})
            try:
                article_raw = generate_article(plan)
                article = strip_code_block(article_raw)
            except Exception as e:
                yield sse({'step': 'error', 'message': f'記事の生成に失敗しました: {e}'})
                return

            safe_seed = safe_filename(seed)
            save_article(safe_seed, article)
            slug = extract_slug(article) or safe_seed
            yield sse({'step': 'done', 'message': '記事の生成が完了しました！',
                       'article': article, 'slug': slug, 'seed': safe_seed})

        # ── Mode 2: 構成生成からスタート ─────────────────────────────
        elif mode == 2:
            yield sse({'step': 'collect_skip', 'message': 'キーワード収集をスキップしました'})

            kw_input = (data.get('keywords') or '').strip()
            keywords = [k.strip() for k in re.split(r'[\s,]+', kw_input) if k.strip()]
            if not keywords:
                keywords = seed.split() or [seed]

            yield sse({'step': 'plan_start', 'message': f'キーワード{len(keywords)}件でAI構成を生成中...'})
            try:
                plan_text = generate_plan(seed, keywords, title)
            except Exception as e:
                yield sse({'step': 'error', 'message': f'[planner] generate_plan 失敗: {type(e).__name__}: {e}'})
                return
            try:
                plan = parse_plan_json(plan_text)
            except Exception as e:
                yield sse({'step': 'error', 'message': f'[planner] JSONパース失敗: {type(e).__name__}: {e}'})
                return
            plan['article_type'] = article_type
            save_plan(seed, plan)
            yield sse({'step': 'plan_done', 'message': '記事構成の生成完了！'})

            yield sse({'step': 'write_start', 'message': 'AIで記事本文を執筆中...'})
            try:
                article_raw = generate_article(plan)
                article = strip_code_block(article_raw)
            except Exception as e:
                yield sse({'step': 'error', 'message': f'記事の生成に失敗しました: {e}'})
                return

            safe_seed = safe_filename(seed)
            save_article(safe_seed, article)
            slug = extract_slug(article) or safe_seed
            yield sse({'step': 'done', 'message': '記事の生成が完了しました！',
                       'article': article, 'slug': slug, 'seed': safe_seed})

        # ── Mode 3: 執筆のみ ──────────────────────────────────────────
        elif mode == 3:
            yield sse({'step': 'collect_skip', 'message': 'キーワード収集をスキップしました'})

            plan_path = os.path.join('output', 'plans', plan_filename)
            if not os.path.exists(plan_path):
                yield sse({'step': 'error', 'message': f'構成ファイルが見つかりません: {plan_filename}'})
                return
            try:
                with open(plan_path, encoding='utf-8') as f:
                    plan = json.load(f)
            except Exception as e:
                yield sse({'step': 'error', 'message': f'構成ファイルの読み込みに失敗しました: {e}'})
                return

            plan_title = plan.get('title', plan_filename)
            yield sse({'step': 'plan_load', 'message': f'構成「{plan_title}」を読み込みました'})

            yield sse({'step': 'write_start', 'message': 'AIで記事本文を執筆中...'})
            try:
                article_raw = generate_article(plan)
                article = strip_code_block(article_raw)
            except Exception as e:
                yield sse({'step': 'error', 'message': f'記事の生成に失敗しました: {e}'})
                return

            seed_from_file = plan_filename[len('plan_'):-len('.json')]
            save_article(seed_from_file, article)
            slug = extract_slug(article) or seed_from_file
            yield sse({'step': 'done', 'message': '記事の生成が完了しました！',
                       'article': article, 'slug': slug, 'seed': seed_from_file})

    return Response(
        stream(),
        mimetype='text/event-stream',
        headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'},
    )


@app.route('/publish', methods=['POST'])
def publish():
    data = request.get_json()
    seed = (data.get('seed') or '').strip()
    slug = (data.get('slug') or '').strip()

    if not seed or not slug:
        return jsonify({'error': 'seedまたはslugが不正です'}), 400

    article_path = os.path.join('output', 'articles', f'article_{seed}.md')
    article_content = data.get('article')
    if article_content:
        os.makedirs(os.path.join('output', 'articles'), exist_ok=True)
        with open(article_path, 'w', encoding='utf-8') as f:
            f.write(article_content)
    elif not os.path.exists(article_path):
        return jsonify({'error': '記事ファイルが見つかりません'}), 404

    try:
        results = {}

        # ローカルnonoka-blogが存在すればコピー＋Vercelデプロイ
        local_blog = os.path.expanduser('~/Desktop/nonoka-blog')
        if os.path.exists(local_blog):
            dest_path, deploy_ok, _, deploy_err = publish_to_blog(article_path, slug)
            results['dest'] = dest_path
            results['deploy_ok'] = deploy_ok
            results['deploy_err'] = deploy_err if not deploy_ok else ''

        # GITHUB_TOKENが設定されていればGitHubにpush
        github_ok = False
        if os.environ.get('GITHUB_TOKEN'):
            github_ok = push_to_github(article_path, slug)
        results['github_ok'] = github_ok

        results['url'] = f'https://www.oshikatsu-room.com/blog/{slug}'
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ののか記事ジェネレーター</title>
  <link rel="manifest" href="/static/manifest.json">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="default">
  <meta name="apple-mobile-web-app-title" content="ののか">
  <link rel="apple-touch-icon" href="/static/icon-192.png">
  <meta name="theme-color" content="#FF69B4">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script>if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/static/service-worker.js'); }</script>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Noto Sans JP', sans-serif;
      background: #F0E6FF;
      min-height: 100vh;
      color: #3d2c4e;
    }
    header {
      background: linear-gradient(90deg, #9B59B6, #FF69B4);
      color: white;
      padding: .75rem 1.5rem;
    }
    .header-inner { max-width: 800px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .5rem; }
    header h1 { font-size: 1.2rem; font-weight: 900; }
    .top-nav a { color: rgba(255,255,255,.85); text-decoration: none; font-size: .88rem; font-weight: 700; margin-left: 1.2rem; }
    .top-nav a:hover { color: white; }
    .container { max-width: 800px; margin: 0 auto; padding: 2rem 1rem; }
    .card {
      background: white;
      border-radius: 16px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 2px 12px rgba(155,89,182,0.1);
    }
    .card h2 { font-size: 1.05rem; font-weight: 700; margin-bottom: 1rem; color: #9B59B6; }
    .field-label { display: block; font-size: 0.88rem; font-weight: 700; margin-bottom: 0.35rem; color: #5a3d72; }
    input[type=text], select, .kw-input {
      width: 100%; padding: 10px 14px;
      border: 2px solid #e8d5ff; border-radius: 8px;
      font-family: inherit; font-size: 0.95rem; margin-bottom: 1rem;
      outline: none; transition: border-color 0.2s;
      background: white; color: #3d2c4e;
    }
    input[type=text]:focus, select:focus, .kw-input:focus { border-color: #FF69B4; }
    select { cursor: pointer; appearance: none; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath d='M1 1l5 5 5-5' stroke='%239B59B6' stroke-width='2' fill='none'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 14px center; padding-right: 36px; }
    .kw-input { height: 90px; resize: vertical; background: #fdf4ff; }

    /* Mode selector */
    .mode-selector { margin-bottom: 1.25rem; }
    .mode-options { display: flex; flex-direction: column; gap: .45rem; margin-top: .5rem; }
    .mode-opt {
      display: flex; align-items: flex-start; gap: .65rem;
      padding: .65rem .85rem; border-radius: 10px;
      border: 2px solid #f0e6ff; cursor: pointer;
      transition: border-color .2s, background .2s;
    }
    .mode-opt.selected { border-color: #FF69B4; background: #fff0f8; }
    .mode-opt input[type=radio] { margin-top: .18rem; accent-color: #9B59B6; flex-shrink: 0; }
    .mode-opt-label { display: flex; flex-direction: column; gap: .12rem; }
    .mode-opt-label strong { font-size: .9rem; color: #3d2c4e; }
    .mode-opt-label small { font-size: .76rem; color: #9B59B6; }

    .btn {
      display: inline-block; padding: 11px 26px;
      border: none; border-radius: 50px;
      font-family: inherit; font-size: 0.95rem; font-weight: 700;
      cursor: pointer; transition: transform 0.2s, opacity 0.2s;
    }
    .btn:hover:not(:disabled) { transform: scale(1.03); }
    .btn:disabled { opacity: 0.5; cursor: not-allowed; }
    .btn-primary { background: linear-gradient(90deg,#FF69B4,#9B59B6); color: white; box-shadow: 0 4px 14px rgba(255,105,180,0.35); }
    .btn-publish { background: linear-gradient(90deg,#9B59B6,#6c3483); color: white; box-shadow: 0 4px 14px rgba(155,89,182,0.35); }

    .steps { display: flex; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 1rem; }
    .badge {
      padding: 4px 12px; border-radius: 20px;
      font-size: 0.78rem; font-weight: 700;
      background: #f0e6ff; color: #9B59B6; border: 2px solid #e8d5ff;
      transition: background 0.3s, color 0.3s;
    }
    .badge.active { background: #FF69B4; color: white; border-color: #FF69B4; }
    .badge.done   { background: #9B59B6; color: white; border-color: #9B59B6; }
    .badge.skip   { background: #f5f5f5; color: #bbb; border-color: #e8e8e8; text-decoration: line-through; }
    .log {
      background: #fdf4ff; border-radius: 8px; padding: 1rem;
      font-size: 0.82rem; max-height: 220px; overflow-y: auto; line-height: 1.9;
    }
    .log .ok   { color: #7d3c98; font-weight: 700; }
    .log .err  { color: #e74c3c; font-weight: 700; }
    .log .warn { color: #e67e22; font-weight: 700; }

    .preview {
      background: #fdf4ff; border-radius: 8px; padding: 1.5rem;
      line-height: 1.85; max-height: 520px; overflow-y: auto; font-size: 0.92rem;
    }
    .preview h1 { font-size: 1.35rem; margin-bottom: 0.8rem; }
    .preview h2 { font-size: 1.05rem; margin: 1.4rem 0 0.5rem; color: #9B59B6; }
    .preview p  { margin-bottom: 0.75rem; }
    .preview hr { border: none; border-top: 1px solid #e8d5ff; margin: 1rem 0; }
    .pub-row { margin-top: 1rem; display: flex; gap: 1rem; align-items: center; flex-wrap: wrap; }
    .pub-status { font-size: 0.88rem; color: #9B59B6; }

    .result-box { background: #fdf4ff; border-radius: 8px; padding: 1rem; word-break: break-all; margin-top: 0.5rem; }
    .result-box a { color: #FF69B4; font-weight: 700; text-decoration: none; }
    .result-box a:hover { text-decoration: underline; }

    .editor-label { font-size: 1.05rem; font-weight: 700; color: #9B59B6; margin: 1.5rem 0 0.75rem; }
    #editor {
      width: 100%; min-height: 600px;
      padding: 1rem; border: 2px solid #e8d5ff; border-radius: 8px;
      font-family: 'Noto Sans JP', monospace; font-size: 0.85rem;
      line-height: 1.75; resize: vertical; outline: none;
      background: #fdf4ff; color: #3d2c4e;
      transition: border-color 0.2s;
    }
    #editor:focus { border-color: #FF69B4; }

    .hidden { display: none; }
    @media (max-width: 600px) {
      .btn { width: 100%; text-align: center; }
      .pub-row { flex-direction: column; }
    }
  </style>
</head>
<body>
<header>
  <div class="header-inner">
    <h1>✨ ののか記事ジェネレーター</h1>
    <nav class="top-nav">
      <a href="/">新規生成</a>
      <a href="/articles">過去の記事</a>
    </nav>
  </div>
</header>
<div class="container">

  <div class="card" id="form-card">
    <h2>記事を生成する</h2>

    <!-- モード選択 -->
    <div class="mode-selector">
      <span class="field-label">生成モード</span>
      <div class="mode-options">
        <label class="mode-opt selected" id="mode-opt-1">
          <input type="radio" name="mode" value="1" checked onchange="switchMode(1)">
          <span class="mode-opt-label">
            <strong>フルパイプライン</strong>
            <small>キーワード収集 → 構成生成 → 執筆</small>
          </span>
        </label>
        <label class="mode-opt" id="mode-opt-2">
          <input type="radio" name="mode" value="2" onchange="switchMode(2)">
          <span class="mode-opt-label">
            <strong>構成生成からスタート</strong>
            <small>キーワードを直接入力 → 構成生成 → 執筆</small>
          </span>
        </label>
        <label class="mode-opt" id="mode-opt-3">
          <input type="radio" name="mode" value="3" onchange="switchMode(3)">
          <span class="mode-opt-label">
            <strong>執筆のみ</strong>
            <small>既存の構成JSONを選択 → 執筆</small>
          </span>
        </label>
      </div>
    </div>

    <!-- モード1・2 共通フォーム -->
    <div id="form-12">
      <label for="seed" class="field-label">シードキーワード</label>
      <input type="text" id="seed" placeholder="例：カラオケ 推し活" />

      <div id="kw-row" class="hidden">
        <label for="keywords" class="field-label">キーワードリスト（スペース・改行・カンマ区切り）</label>
        <textarea id="keywords" class="kw-input" placeholder="例：推し活 カラオケ 個室&#10;オタ活 貸切 シネマルーム"></textarea>
      </div>

      <label for="title" class="field-label">記事タイトル</label>
      <input type="text" id="title" placeholder="例：カラオケで推し活！おすすめの楽しみ方5選" />

      <label for="article-type" class="field-label">記事タイプ</label>
      <select id="article-type">
        <option value="seo">情報提供系（通常SEO構成）</option>
        <option value="pasbecona">悩み解決系（PASBECONA構成）</option>
        <option value="comparison">比較系（通常SEO構成＋CTA強化）</option>
      </select>
    </div>

    <!-- モード3 フォーム -->
    <div id="form-3" class="hidden">
      <label for="plan-select" class="field-label">使用する構成ファイル</label>
      <select id="plan-select">
        <option value="">-- 構成を選択してください --</option>
      </select>
    </div>

    <button class="btn btn-primary" id="gen-btn" onclick="startGenerate()">記事を生成する 🎬</button>
  </div>

  <div class="card hidden" id="prog-card">
    <h2 id="prog-heading">生成中...</h2>
    <div class="steps">
      <span class="badge" id="b1">① キーワード収集</span>
      <span class="badge" id="b2">② 記事構成</span>
      <span class="badge" id="b3">③ 本文執筆</span>
    </div>
    <div class="log" id="log"></div>
  </div>

  <div class="card hidden" id="prev-card">
    <h2>記事プレビュー</h2>
    <div class="preview" id="preview"></div>
    <p class="editor-label">Markdown編集</p>
    <textarea id="editor" spellcheck="false"></textarea>
    <div class="pub-row">
      <button class="btn btn-publish" id="pub-btn" onclick="publishArticle()">この内容で投稿する 🚀</button>
      <span class="pub-status" id="pub-status"></span>
    </div>
  </div>

  <div class="card hidden" id="result-card">
    <h2>✅ 投稿完了！</h2>
    <p style="margin-bottom:.75rem;font-size:.9rem;">公開URLで確認してください：</p>
    <div class="result-box"><a id="result-url" href="#" target="_blank"></a></div>
  </div>

</div>
<script>
let G = { slug: '', seed: '', article: '' };
let currentMode = 1;

function switchMode(mode) {
  currentMode = mode;
  [1, 2, 3].forEach(n => {
    document.getElementById('mode-opt-' + n).classList.toggle('selected', n === mode);
  });
  document.getElementById('form-12').classList.toggle('hidden', mode === 3);
  document.getElementById('form-3').classList.toggle('hidden', mode !== 3);
  document.getElementById('kw-row').classList.toggle('hidden', mode !== 2);
  if (mode === 3) loadPlans();
}

async function loadPlans() {
  const sel = document.getElementById('plan-select');
  sel.innerHTML = '<option value="">読み込み中...</option>';
  try {
    const res   = await fetch('/api/plans');
    const plans = await res.json();
    if (!plans.length) {
      sel.innerHTML = '<option value="">構成ファイルがありません（先にフルパイプラインを実行してください）</option>';
      return;
    }
    const labels = { seo: '情報提供系', pasbecona: '悩み解決系', comparison: '比較系' };
    sel.innerHTML = '<option value="">-- 構成を選択してください --</option>' +
      plans.map(p =>
        '<option value="' + p.filename + '">[' + (labels[p.article_type] || p.article_type) + '] ' + p.title + '</option>'
      ).join('');
  } catch(e) {
    sel.innerHTML = '<option value="">読み込みエラー</option>';
  }
}

function addLog(msg, cls) {
  const el = document.getElementById('log');
  const d = document.createElement('div');
  if (cls) d.className = cls;
  d.textContent = msg;
  el.appendChild(d);
  el.scrollTop = el.scrollHeight;
}

function badge(id, state) {
  document.getElementById(id).className = 'badge ' + (state || '');
}

function show(id) { document.getElementById(id).classList.remove('hidden'); }
function hide(id) { document.getElementById(id).classList.add('hidden'); }

async function startGenerate() {
  const mode = currentMode;
  const payload = { mode };

  if (mode === 1 || mode === 2) {
    const seed  = document.getElementById('seed').value.trim();
    const title = document.getElementById('title').value.trim();
    if (!seed || !title) { alert('シードキーワードと記事タイトルを入力してください'); return; }
    payload.seed = seed;
    payload.title = title;
    payload.article_type = document.getElementById('article-type').value;
    if (mode === 2) {
      payload.keywords = document.getElementById('keywords').value.trim();
    }
  } else {
    const plan_filename = document.getElementById('plan-select').value;
    if (!plan_filename) { alert('構成ファイルを選択してください'); return; }
    payload.plan_filename = plan_filename;
  }

  document.getElementById('gen-btn').disabled = true;
  document.getElementById('log').innerHTML = '';
  document.getElementById('prog-heading').textContent = '生成中...';

  // バッジ初期化（モードに応じてスキップ表示）
  ['b1','b2','b3'].forEach(id => badge(id, ''));
  if (mode === 2) badge('b1', 'skip');
  if (mode === 3) { badge('b1', 'skip'); badge('b2', 'skip'); }

  show('prog-card');
  hide('prev-card');
  hide('result-card');

  try {
    const res = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\\n');
      buf = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try { handle(JSON.parse(line.slice(6))); } catch(e) {}
      }
    }
  } catch(e) {
    addLog('通信エラー: ' + e.message, 'err');
  }
  document.getElementById('gen-btn').disabled = false;
}

function handle(d) {
  switch(d.step) {
    case 'collect_start':    badge('b1','active'); addLog(d.message); break;
    case 'collect_progress': addLog(d.message); break;
    case 'collect_done':     badge('b1','done');  addLog(d.message, 'ok'); break;
    case 'collect_warn':     badge('b1','done');  addLog('⚠️ ' + d.message, 'warn'); break;
    case 'collect_skip':     addLog(d.message); break;
    case 'plan_start':       badge('b2','active'); addLog(d.message); break;
    case 'plan_done':        badge('b2','done');  addLog(d.message, 'ok'); break;
    case 'plan_load':        badge('b2','done');  addLog(d.message, 'ok'); break;
    case 'plan_skip':        addLog(d.message); break;
    case 'write_start':      badge('b3','active'); addLog(d.message); break;
    case 'done':
      badge('b3','done');
      addLog('生成完了！', 'ok');
      document.getElementById('prog-heading').textContent = '生成完了！';
      G = { slug: d.slug, seed: d.seed, article: d.article };
      document.getElementById('preview').innerHTML = marked.parse(d.article);
      document.getElementById('editor').value = d.article;
      document.getElementById('pub-btn').disabled = false;
      document.getElementById('pub-status').textContent = '';
      show('prev-card');
      document.getElementById('prev-card').scrollIntoView({ behavior: 'smooth' });
      break;
    case 'error':
      addLog('エラー: ' + d.message, 'err');
      break;
    default:
      if (d.message) addLog(d.message);
  }
}

async function publishArticle() {
  document.getElementById('pub-btn').disabled = true;
  document.getElementById('pub-status').textContent = '投稿・デプロイ中...';
  const article = document.getElementById('editor').value;
  try {
    const res = await fetch('/publish', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ seed: G.seed, slug: G.slug, article })
    });
    const d = await res.json();
    if (d.error) {
      document.getElementById('pub-status').textContent = 'エラー: ' + d.error;
      document.getElementById('pub-btn').disabled = false;
    } else {
      document.getElementById('pub-status').textContent = d.deploy_ok ? 'デプロイ完了！' : 'コピー完了（デプロイ失敗）';
      const a = document.getElementById('result-url');
      a.href = d.url; a.textContent = d.url;
      show('result-card');
      document.getElementById('result-card').scrollIntoView({ behavior: 'smooth' });
    }
  } catch(e) {
    document.getElementById('pub-status').textContent = '通信エラー: ' + e.message;
    document.getElementById('pub-btn').disabled = false;
  }
}
</script>
</body>
</html>"""


@app.route('/articles')
def articles_list():
    items = list_articles()
    if not items:
        rows_html = '<p class="empty-state">まだ記事がありません。新規生成から記事を作成してください。</p>'
    else:
        rows_html = ''
        for item in items:
            title   = item.get('title') or item['filename']
            pubdate = item.get('pubDate', '—')
            slug    = item.get('slug', '')
            fn      = item['filename']
            slug_tag = f'<span class="slug-tag">{slug}</span>' if slug else ''
            rows_html += (
                f'<div class="article-card" data-filename="{fn}">'
                f'<div class="article-info">'
                f'<p class="article-title">{title}</p>'
                f'<div class="article-meta"><span>{pubdate}</span>{slug_tag}</div>'
                f'</div>'
                f'<div class="article-actions">'
                f'<button class="btn btn-ghost" onclick="showPreview(\'{fn}\')">プレビュー</button>'
                f'<a href="/articles/{fn}/edit" class="btn btn-purple">編集</a>'
                f'<button class="btn btn-danger" onclick="deleteArticle(\'{fn}\')">削除</button>'
                f'</div></div>'
            )
    count_text = f'{len(items)}件'
    page = ARTICLES_HTML.replace('__ROWS__', rows_html).replace('__COUNT__', count_text)
    return page, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/articles/<filename>/edit')
def article_edit(filename):
    path = os.path.join('output', 'articles', filename)
    if not os.path.exists(path):
        return '記事が見つかりません', 404
    with open(path, encoding='utf-8') as f:
        content = f.read()
    meta  = parse_frontmatter(content)
    title = meta.get('title') or filename
    slug  = meta.get('slug', '')
    page  = (EDIT_HTML
             .replace('__FILENAME__', filename)
             .replace('__TITLE__', title)
             .replace('__SLUG__', slug)
             .replace('__CONTENT_JSON__', json.dumps(content)))
    return page, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/api/articles/<filename>/content')
def article_content(filename):
    path = os.path.join('output', 'articles', filename)
    if not os.path.exists(path):
        return jsonify({'error': 'not found'}), 404
    with open(path, encoding='utf-8') as f:
        content = f.read()
    return jsonify({'content': content})


@app.route('/api/articles/<filename>/save', methods=['POST'])
def article_save(filename):
    data    = request.get_json()
    content = data.get('content', '')
    path    = os.path.join('output', 'articles', filename)
    os.makedirs(os.path.join('output', 'articles'), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    deploy_ok, _, deploy_err = deploy_to_vercel()
    return jsonify({'ok': True, 'deploy_ok': deploy_ok, 'deploy_err': deploy_err if not deploy_ok else ''})


@app.route('/api/articles/<filename>/delete', methods=['POST'])
def article_delete(filename):
    path = os.path.join('output', 'articles', filename)
    if not os.path.exists(path):
        return jsonify({'error': 'not found'}), 404
    os.remove(path)
    deploy_ok, _, deploy_err = deploy_to_vercel()
    return jsonify({'ok': True, 'deploy_ok': deploy_ok, 'deploy_err': deploy_err if not deploy_ok else ''})


@app.route('/api/articles/<filename>/publish', methods=['POST'])
def article_publish_api(filename):
    path = os.path.join('output', 'articles', filename)
    data    = request.get_json(silent=True) or {}
    content = data.get('content')
    if content:
        os.makedirs(os.path.join('output', 'articles'), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    if not os.path.exists(path):
        return jsonify({'error': '記事ファイルが見つかりません'}), 404
    with open(path, encoding='utf-8') as f:
        saved = f.read()
    meta = parse_frontmatter(saved)
    slug = meta.get('slug') or filename[len('article_'):-len('.md')]
    try:
        results = {}

        # ローカルnonoka-blogが存在すればコピー＋Vercelデプロイ
        local_blog = os.path.expanduser('~/Desktop/nonoka-blog')
        if os.path.exists(local_blog):
            dest_path, deploy_ok, _, deploy_err = publish_to_blog(path, slug)
            results['dest'] = dest_path
            results['deploy_ok'] = deploy_ok
            results['deploy_err'] = deploy_err if not deploy_ok else ''

        # GITHUB_TOKENが設定されていればGitHubにpush
        github_ok = False
        if os.environ.get('GITHUB_TOKEN'):
            github_ok = push_to_github(path, slug)
        results['github_ok'] = github_ok

        results['url'] = f'https://www.oshikatsu-room.com/blog/{slug}'
        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ─── HTML templates for /articles and /articles/<fn>/edit ────────────────────

_NAV = '''<header>
  <div class="header-inner">
    <h1>✨ ののか記事ジェネレーター</h1>
    <nav class="top-nav">
      <a href="/">新規生成</a>
      <a href="/articles">過去の記事</a>
    </nav>
  </div>
</header>'''

_BASE_CSS = '''
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Noto Sans JP', sans-serif; background: #F0E6FF; min-height: 100vh; color: #3d2c4e; }
    header { background: linear-gradient(90deg, #9B59B6, #FF69B4); color: white; padding: .75rem 1.5rem; }
    .header-inner { max-width: 800px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: .5rem; }
    header h1 { font-size: 1.2rem; font-weight: 900; }
    .top-nav a { color: rgba(255,255,255,.85); text-decoration: none; font-size: .88rem; font-weight: 700; margin-left: 1.2rem; }
    .top-nav a:hover { color: white; }
    .container { max-width: 800px; margin: 0 auto; padding: 2rem 1rem; }
    .card { background: white; border-radius: 16px; padding: 1.5rem; margin-bottom: 1.5rem; box-shadow: 0 2px 12px rgba(155,89,182,.1); }
    .btn { display: inline-block; padding: 9px 20px; border: none; border-radius: 50px; font-family: inherit; font-size: .85rem; font-weight: 700; cursor: pointer; text-decoration: none; transition: transform .2s, opacity .2s; }
    .btn:hover:not(:disabled) { transform: scale(1.03); }
    .btn:disabled { opacity: .5; cursor: not-allowed; }
    .btn-primary { background: linear-gradient(90deg,#FF69B4,#9B59B6); color: white; box-shadow: 0 4px 14px rgba(255,105,180,.35); }
    .btn-purple  { background: linear-gradient(90deg,#FF69B4,#9B59B6); color: white; }
    .btn-ghost   { background: #f0e6ff; color: #9B59B6; }
    .btn-danger  { background: #fff0f0; color: #e74c3c; }
    .btn-outline { background: white; color: #9B59B6; border: 2px solid #e8d5ff; }
'''

ARTICLES_HTML = f'''<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>過去の記事 | ののか記事ジェネレーター</title>
  <link rel="manifest" href="/static/manifest.json">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="default">
  <meta name="apple-mobile-web-app-title" content="ののか">
  <link rel="apple-touch-icon" href="/static/icon-192.png">
  <meta name="theme-color" content="#FF69B4">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script>if ('serviceWorker' in navigator) {{ navigator.serviceWorker.register('/static/service-worker.js'); }}</script>
  <style>{_BASE_CSS}
    .card-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.25rem; }}
    .card-header h2 {{ font-size: 1.05rem; font-weight: 700; color: #9B59B6; }}
    .card-header .count {{ font-size: .85rem; color: #9B59B6; }}
    .empty-state {{ text-align: center; padding: 3rem 1rem; color: #9B59B6; font-size: .95rem; }}
    .article-card {{ display: flex; align-items: center; justify-content: space-between; gap: 1rem; padding: .9rem 0; border-bottom: 1px solid #f0e6ff; flex-wrap: wrap; }}
    .article-card:last-of-type {{ border-bottom: none; }}
    .article-info {{ flex: 1; min-width: 0; }}
    .article-title {{ font-size: .95rem; font-weight: 700; margin-bottom: .3rem; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .article-meta {{ display: flex; gap: .6rem; align-items: center; font-size: .78rem; color: #9B59B6; flex-wrap: wrap; }}
    .slug-tag {{ background: #f0e6ff; padding: 2px 8px; border-radius: 4px; }}
    .article-actions {{ display: flex; gap: .45rem; flex-shrink: 0; flex-wrap: wrap; }}
    /* Modal */
    .modal-bg {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,.5); z-index: 100; overflow-y: auto; padding: 2rem 1rem; }}
    .modal-bg.open {{ display: block; }}
    .modal-inner {{ background: white; border-radius: 16px; max-width: 720px; margin: 0 auto; padding: 1.5rem; }}
    .modal-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
    .modal-top h3 {{ font-size: 1rem; color: #9B59B6; font-weight: 700; }}
    .modal-body {{ line-height: 1.85; font-size: .92rem; }}
    .modal-body h1 {{ font-size: 1.3rem; margin-bottom: .8rem; }}
    .modal-body h2 {{ font-size: 1.05rem; margin: 1.4rem 0 .5rem; color: #9B59B6; }}
    .modal-body p  {{ margin-bottom: .75rem; }}
    .modal-body hr {{ border: none; border-top: 1px solid #e8d5ff; margin: 1rem 0; }}
    @media (max-width:600px) {{ .article-actions {{ width: 100%; }} .btn {{ flex: 1; text-align: center; }} }}
  </style>
</head>
<body>
{_NAV}
<div class="container">
  <div class="card">
    <div class="card-header">
      <h2>過去の記事</h2>
      <span class="count">__COUNT__</span>
    </div>
    __ROWS__
  </div>
</div>
<div class="modal-bg" id="modal">
  <div class="modal-inner">
    <div class="modal-top">
      <h3>記事プレビュー</h3>
      <button class="btn btn-ghost" onclick="closeModal()">✕ 閉じる</button>
    </div>
    <div class="modal-body" id="modal-body"></div>
  </div>
</div>
<script>
async function showPreview(fn) {{
  const res  = await fetch('/api/articles/' + fn + '/content');
  const data = await res.json();
  if (data.error) {{ alert('読み込みに失敗しました'); return; }}
  document.getElementById('modal-body').innerHTML = marked.parse(data.content);
  document.getElementById('modal').classList.add('open');
}}
function closeModal() {{ document.getElementById('modal').classList.remove('open'); }}
document.getElementById('modal').addEventListener('click', e => {{ if (e.target === document.getElementById('modal')) closeModal(); }});
async function deleteArticle(fn) {{
  if (!confirm(fn + ' を削除しますか？この操作は元に戻せません。')) return;
  toast('削除・デプロイ中...');
  const res  = await fetch('/api/articles/' + fn + '/delete', {{ method: 'POST' }});
  const data = await res.json();
  if (data.ok) {{
    document.querySelector('[data-filename="' + fn + '"]').remove();
    const n = document.querySelectorAll('.article-card').length;
    document.querySelector('.count').textContent = n + '件';
    if (n === 0) document.querySelector('.card').insertAdjacentHTML('beforeend', '<p class="empty-state">記事がありません。</p>');
    toast(data.deploy_ok ? '✅ 削除してVercelにデプロイしました' : '削除完了（デプロイ失敗）', data.deploy_ok ? '' : '#e74c3c');
  }} else {{
    toast('削除に失敗しました: ' + (data.error || ''), '#e74c3c');
  }}
}}
function toast(msg, color) {{
  let el = document.getElementById('_toast');
  if (!el) {{
    el = document.createElement('div');
    el.id = '_toast';
    el.style.cssText = 'position:fixed;bottom:1.2rem;right:1.2rem;padding:.65rem 1.3rem;border-radius:50px;font-size:.85rem;font-weight:700;color:white;z-index:999;transition:opacity .3s;';
    document.body.appendChild(el);
  }}
  el.style.background = color || '#9B59B6';
  el.style.opacity = '1';
  el.textContent = msg;
  clearTimeout(el._t);
  el._t = setTimeout(() => {{ el.style.opacity = '0'; }}, 3500);
}}
</script>
</body>
</html>'''


EDIT_HTML = f'''<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>編集 | ののか記事ジェネレーター</title>
  <link rel="manifest" href="/static/manifest.json">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="default">
  <meta name="apple-mobile-web-app-title" content="ののか">
  <link rel="apple-touch-icon" href="/static/icon-192.png">
  <meta name="theme-color" content="#FF69B4">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700;900&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
  <script>if ('serviceWorker' in navigator) {{ navigator.serviceWorker.register('/static/service-worker.js'); }}</script>
  <style>{_BASE_CSS}
    .page-title {{ font-size: 1.05rem; font-weight: 700; color: #9B59B6; margin-bottom: .3rem; }}
    .page-slug  {{ font-size: .8rem; color: #b39ddb; margin-bottom: 1.25rem; }}
    .tabs {{ display: flex; gap: .5rem; margin-bottom: 1rem; }}
    .tab {{ padding: 6px 16px; border-radius: 50px; font-size: .85rem; font-weight: 700; cursor: pointer; border: 2px solid #e8d5ff; background: white; color: #9B59B6; }}
    .tab.active {{ background: #9B59B6; color: white; border-color: #9B59B6; }}
    #editor {{
      width: 100%; min-height: 600px; padding: 1rem; border: 2px solid #e8d5ff; border-radius: 8px;
      font-family: 'Noto Sans JP', monospace; font-size: .85rem; line-height: 1.75;
      resize: vertical; outline: none; background: #fdf4ff; color: #3d2c4e;
      transition: border-color .2s;
    }}
    #editor:focus {{ border-color: #FF69B4; }}
    #preview-pane {{
      display: none; min-height: 600px; background: #fdf4ff; border-radius: 8px;
      padding: 1.5rem; line-height: 1.85; font-size: .92rem; overflow-y: auto;
    }}
    #preview-pane h1 {{ font-size: 1.3rem; margin-bottom: .8rem; }}
    #preview-pane h2 {{ font-size: 1.05rem; margin: 1.4rem 0 .5rem; color: #9B59B6; }}
    #preview-pane p  {{ margin-bottom: .75rem; }}
    #preview-pane hr {{ border: none; border-top: 1px solid #e8d5ff; margin: 1rem 0; }}
    .action-row {{ display: flex; gap: .75rem; flex-wrap: wrap; margin-top: 1rem; align-items: center; }}
    .status-msg {{ font-size: .88rem; color: #9B59B6; }}
    .result-box {{ background: #fdf4ff; border-radius: 8px; padding: .75rem 1rem; margin-top: 1rem; font-size: .88rem; word-break: break-all; display: none; }}
    .result-box a {{ color: #FF69B4; font-weight: 700; text-decoration: none; }}
    @media (max-width:600px) {{ .action-row {{ flex-direction: column; }} .btn {{ width: 100%; text-align: center; }} }}
  </style>
</head>
<body>
{_NAV}
<div class="container">
  <div class="card">
    <p class="page-title">__TITLE__</p>
    <p class="page-slug">slug: __SLUG__　|　__FILENAME__</p>
    <div class="tabs">
      <button class="tab active" onclick="switchTab('edit')">編集</button>
      <button class="tab" onclick="switchTab('preview')">プレビュー</button>
    </div>
    <textarea id="editor" spellcheck="false"></textarea>
    <div id="preview-pane"></div>
    <div class="action-row">
      <button class="btn btn-primary" onclick="saveArticle()">保存</button>
      <button class="btn btn-purple" onclick="publishArticle()">Astroに投稿</button>
      <a href="/articles" class="btn btn-outline">← 一覧に戻る</a>
      <span class="status-msg" id="status"></span>
    </div>
    <div class="result-box" id="result-box">
      投稿完了！　<a id="result-url" href="#" target="_blank"></a>
    </div>
  </div>
</div>
<script type="application/json" id="content-data">__CONTENT_JSON__</script>
<script>
const FILENAME = '__FILENAME__';
const content  = JSON.parse(document.getElementById('content-data').textContent);
document.getElementById('editor').value = content;

function switchTab(tab) {{
  const isEdit = tab === 'edit';
  document.getElementById('editor').style.display       = isEdit ? '' : 'none';
  document.getElementById('preview-pane').style.display = isEdit ? 'none' : '';
  document.querySelectorAll('.tab').forEach((el, i) => el.classList.toggle('active', isEdit ? i === 0 : i === 1));
  if (!isEdit) {{
    document.getElementById('preview-pane').innerHTML = marked.parse(document.getElementById('editor').value);
  }}
}}

async function saveArticle() {{
  const status = document.getElementById('status');
  status.textContent = '保存・デプロイ中...';
  const res  = await fetch('/api/articles/' + FILENAME + '/save', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ content: document.getElementById('editor').value }})
  }});
  const data = await res.json();
  if (data.ok) {{
    status.textContent = data.deploy_ok ? '✅ 保存＆デプロイ完了' : '✅ 保存完了（デプロイ失敗）';
  }} else {{
    status.textContent = 'エラー: ' + (data.error || '');
  }}
  setTimeout(() => {{ if (status.textContent.includes('完了')) status.textContent = ''; }}, 4000);
}}

async function publishArticle() {{
  const status = document.getElementById('status');
  status.textContent = '投稿・デプロイ中...';
  const res  = await fetch('/api/articles/' + FILENAME + '/publish', {{
    method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{ content: document.getElementById('editor').value }})
  }});
  const data = await res.json();
  if (data.error) {{
    status.textContent = 'エラー: ' + data.error;
  }} else {{
    status.textContent = data.deploy_ok ? '✅ デプロイ完了！' : 'コピー完了（デプロイ失敗）';
    const box = document.getElementById('result-box');
    const a   = document.getElementById('result-url');
    a.href = data.url; a.textContent = data.url;
    box.style.display = '';
    box.scrollIntoView({{ behavior: 'smooth' }});
  }}
}}
</script>
</body>
</html>'''


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
