import os
import subprocess
import sys
import glob
import shutil
import re
import base64
import requests

BLOG_DIR = os.path.expanduser('~/Desktop/nonoka-blog/src/content/blog')


def list_article_files() -> list[str]:
    return sorted(glob.glob('output/articles/article_*.md'))


def select_file(files: list[str]) -> str:
    print('投稿する記事を選んでください：')
    for i, f in enumerate(files, 1):
        print(f'  {i}. {f}')
    while True:
        raw = input('番号を入力: ').strip()
        if raw.isdigit() and 1 <= int(raw) <= len(files):
            return files[int(raw) - 1]
        print('正しい番号を入力してください。')


def extract_slug(content: str) -> str | None:
    fm_match = re.match(r'^---\n(.*?)\n---', content, re.DOTALL)
    search_target = fm_match.group(1) if fm_match else content
    match = re.search(r'^slug:\s*["\']?(.+?)["\']?\s*$', search_target, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def fallback_slug(path: str) -> str:
    basename = os.path.basename(path)
    return basename[len('article_'):-len('.md')]


def _ensure_output_dirs():
    for d in ['output/keywords', 'output/plans', 'output/articles',
              'output/thumbnails/gbp', 'output/thumbnails/blog', 'output/thumbnails/sns',
              'output/images/nonoka', 'output/images/infographic']:
        os.makedirs(d, exist_ok=True)


def deploy_to_vercel() -> tuple[bool, str, str]:
    blog_dir = os.path.expanduser('~/Desktop/nonoka-blog')
    result = subprocess.run(
        ['vercel', '--prod', '--yes'],
        cwd=blog_dir,
        capture_output=True,
        text=True,
        timeout=180,
    )
    return result.returncode == 0, result.stdout, result.stderr


def push_to_github(article_path: str, slug: str) -> bool:
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('GITHUB_REPO')

    if not token or not repo:
        print('GITHUB_TOKENまたはGITHUB_REPOが設定されていません')
        return False

    with open(article_path, 'r', encoding='utf-8') as f:
        content = f.read()

    encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')

    file_path = f'src/content/blog/{slug}.md'
    url = f'https://api.github.com/repos/{repo}/contents/{file_path}'

    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.v3+json'
    }

    response = requests.get(url, headers=headers)
    sha = None
    if response.status_code == 200:
        sha = response.json().get('sha')

    data = {
        'message': f'Add article: {slug}',
        'content': encoded,
        'branch': 'main'
    }
    if sha:
        data['sha'] = sha

    response = requests.put(url, headers=headers, json=data)

    if response.status_code in [200, 201]:
        print(f'GitHubにpushしました: {file_path}')
        return True
    else:
        print(f'GitHubへのpush失敗: {response.status_code} {response.text}')
        return False


def save_draft_to_github(content: str, filename: str) -> bool:
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('PIPELINE_GITHUB_REPO')
    if not token or not repo:
        return False
    encoded = base64.b64encode(content.encode('utf-8')).decode('utf-8')
    file_path = f'output/articles/{filename}'
    url = f'https://api.github.com/repos/{repo}/contents/{file_path}'
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    response = requests.get(url, headers=headers)
    sha = response.json().get('sha') if response.status_code == 200 else None
    data = {'message': f'Save draft: {filename}', 'content': encoded, 'branch': 'main'}
    if sha:
        data['sha'] = sha
    response = requests.put(url, headers=headers, json=data)
    return response.status_code in [200, 201]


def sync_drafts_from_github() -> bool:
    token = os.environ.get('GITHUB_TOKEN')
    repo = os.environ.get('PIPELINE_GITHUB_REPO')
    if not token or not repo:
        return False
    headers = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
    url = f'https://api.github.com/repos/{repo}/contents/output/articles'
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return False
    files = [f for f in response.json() if isinstance(f, dict) and f.get('name', '').startswith('article_') and f.get('name', '').endswith('.md')]
    os.makedirs(os.path.join('output', 'articles'), exist_ok=True)
    for file_info in files:
        local_path = os.path.join('output', 'articles', file_info['name'])
        if os.path.exists(local_path):
            continue
        cr = requests.get(file_info['url'], headers=headers)
        if cr.status_code != 200:
            continue
        file_content = base64.b64decode(cr.json()['content']).decode('utf-8')
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(file_content)
    return True


def publish_to_blog(article_path: str, slug: str, blog_dir: str = BLOG_DIR) -> tuple[str, bool, str, str]:
    dest_path = os.path.join(blog_dir, f'{slug}.md')
    os.makedirs(blog_dir, exist_ok=True)
    shutil.copy2(article_path, dest_path)
    deploy_ok, deploy_out, deploy_err = deploy_to_vercel()
    return dest_path, deploy_ok, deploy_out, deploy_err


def main():
    files = list_article_files()
    if not files:
        print('output/ フォルダに記事ファイルが見つかりません。先に writer.py を実行してください。')
        sys.exit(1)

    selected = select_file(files)

    with open(selected, encoding='utf-8') as f:
        content = f.read()

    slug = extract_slug(content) or fallback_slug(selected)
    dest_filename = f'{slug}.md'
    dest_path = os.path.join(BLOG_DIR, dest_filename)

    if os.path.exists(dest_path):
        answer = input(f'\n⚠️  {dest_path} はすでに存在します。上書きしますか？ [y/N]: ').strip().lower()
        if answer != 'y':
            print('キャンセルしました。')
            sys.exit(0)

    print('\nVercelにデプロイ中...')
    dest_path, deploy_ok, deploy_out, deploy_err = publish_to_blog(selected, slug)

    print(f'\n✅ {selected} を')
    print(f'   {dest_path}')
    print(f'   にコピーしました！')
    if deploy_ok:
        print('\n🚀 Vercelへのデプロイ完了！')
        print(f'https://www.oshikatsu-room.com/blog/{slug}')
    else:
        print('\n⚠️  Vercelデプロイに失敗しました。')
        if deploy_err:
            print(deploy_err)


if __name__ == '__main__':
    main()
