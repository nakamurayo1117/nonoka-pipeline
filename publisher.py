import os
import subprocess
import sys
import glob
import shutil
import re

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
        ['vercel', '--prod'],
        cwd=blog_dir,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, result.stdout, result.stderr


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
