import os
import sys
import time
import requests
import re
from collections import Counter

# Configuration
CACHE_FILE = '.last_seen_sha'
EXCLUDED_EXTS = {'mdx', 'css', 'html', 'cmake'}
EXCLUDED_FILENAMES = {'Makefile', 'CMakeLists.txt'}
MAX_PAGES = 10
PER_PAGE = 100

def read_last_seen():
    try:
        return open(CACHE_FILE, 'r', encoding='utf-8').read().strip()
    except FileNotFoundError:
        return None

def write_last_seen(sha):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        f.write(sha)

def get_commits(username, token, last_seen=None):
    headers = {
        'Authorization': f'token {token}',
        'Accept':        'application/vnd.github.cloak-preview'
    }
    commits = []
    stop = False

    for page in range(1, MAX_PAGES + 1):
        params = {
            'q':        f'author:{username}',
            'page':     page,
            'per_page': PER_PAGE
        }
        response = requests.get('https://api.github.com/search/commits',
                                headers=headers, params=params)
        if response.status_code != 200:
            print("Error fetching commits:", response.json())
            break

        items = response.json().get('items', [])
        if not items:
            break

        for it in items:
            sha = it['sha']
            if sha == last_seen:
                stop = True
                break
            commits.append((it['repository']['full_name'], sha))

        if stop:
            break
        time.sleep(0.2)

    return commits

def ext_of(path):
    fn = path.rsplit('/', 1)[-1]
    if fn in EXCLUDED_FILENAMES or '.' not in fn:
        return None
    e = fn.rsplit('.', 1)[1].lower()
    return None if e in EXCLUDED_EXTS else e

def main():
    username = sys.argv[1] if len(sys.argv) > 1 else 'TheRickyZhang'
    token = os.environ.get('GH_TOKEN')
    if not token:
        print("GH_TOKEN not set")
        sys.exit(1)

    last = read_last_seen()
    print(f"Fetching commits for {username}… (since {last or 'the very beginning'})")
    commits = get_commits(username, token, last)
    print(f"→ found {len(commits)} commits")

    if commits:
        # cache the newest SHA for next run
        _, newest_sha = commits[0]
        write_last_seen(newest_sha)

    tally = Counter()
    for repo, sha in commits:
        print(f"Processing {repo}@{sha[:7]}…")
        r = requests.get(
            f'https://api.github.com/repos/{repo}/commits/{sha}',
            headers={'Authorization': f'token {token}'}
        )
        if r.status_code != 200:
            continue
        for f in r.json().get('files', []):
            e = ext_of(f['filename'])
            if e:
                tally[e] += f.get('additions', 0)
        time.sleep(0.1)

    total = sum(tally.values()) or 1
    top10 = tally.most_common(10)

    # build markdown block
    output_lines = ["### Commit-Based Language Stats", ""]
    output_lines.append("| Language | Bytes | Percentage |")
    output_lines.append("| --- | ---:| ---:|")
    for lang, cnt in top10:
        pct = cnt / total * 100
        output_lines.append(f"| {lang} | {cnt:,} | {pct:.2f}% |")
    new_section = "\n".join(output_lines)

    # inject into README.md
    readme_path = "README.md"
    readme = open(readme_path, "r", encoding="utf-8").read()
    new_readme = re.sub(
        r'<!--START_COMMIT_LANG_STATS-->.*<!--END_COMMIT_LANG_STATS-->',
        f'<!--START_COMMIT_LANG_STATS-->\n{new_section}\n<!--END_COMMIT_LANG_STATS-->',
        readme,
        flags=re.DOTALL
    )
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(new_readme)

    print("README.md updated with new language stats.")

if __name__ == "__main__":
    main()
