#!/usr/bin/env python3
import os
import sys
import time
import requests
import re
from collections import Counter

# ───── CONFIG ─────
CACHE_FILE = '.last_seen_sha'
MAX_PAGES  = 10
PER_PAGE   = 100

# Only these languages (extensions) will be counted:
GROUPS = {
    'C/C++':      {'c','cpp','cc','cxx','h','hh','hpp','hxx'},
    'Python':     {'py'},
    'Java':       {'java'},
    'JavaScript': {'js','jsx'},
    'TypeScript': {'ts','tsx'},
    'Go':         {'go'},
    'Rust':       {'rs'},
    'Ruby':       {'rb'},
    'PHP':        {'php'},
    'Kotlin':     {'kt','kts'},
    'Swift':      {'swift'},
    'C#':         {'cs'},
    'Scala':      {'scala'},
    'Shell':      {'sh','bash'},
}

# build a reverse map ext -> language
EXT_TO_LANG = {
    ext: lang
    for lang, exts in GROUPS.items()
    for ext in exts
}

# ───── CACHE HELPERS ─────
def read_last_seen():
    try:
        return open(CACHE_FILE, 'r', encoding='utf-8').read().strip()
    except FileNotFoundError:
        return None

def write_last_seen(sha):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        f.write(sha)

# ───── FETCH YOUR COMMITS ─────
def get_commits(username, token, last_seen=None):
    headers = {
        'Authorization': f'token {token}',
        'Accept':        'application/vnd.github.cloak-preview'
    }
    commits = []
    stop = False

    for page in range(1, MAX_PAGES+1):
        params = {
            'q':        f'author:{username}',
            'page':     page,
            'per_page': PER_PAGE
        }
        r = requests.get('https://api.github.com/search/commits',
                         headers=headers, params=params)
        if r.status_code != 200:
            print("Error fetching commits:", r.json())
            break

        items = r.json().get('items', [])
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

# ───── EXTRACT EXTENSION ─────
def ext_of(path):
    fn = path.rsplit('/', 1)[-1]
    if '.' not in fn:
        return None
    return fn.rsplit('.', 1)[1].lower()

# ───── MAIN ─────
def main():
    # args & token
    username = sys.argv[1] if len(sys.argv)>1 else 'TheRickyZhang'
    token    = os.environ.get('GH_TOKEN')
    if not token:
        print("GH_TOKEN not set"); sys.exit(1)

    # read cache & fetch only new commits
    last = read_last_seen()
    print(f"Fetching commits for {username}… (since {last or 'the very beginning'})")
    commits = get_commits(username, token, last)
    print(f"→ found {len(commits)} new commits")

    # update cache to newest
    if commits:
        _, newest = commits[0]
        write_last_seen(newest)

    # tally lines per language
    lang_tally = Counter()
    for repo, sha in commits:
        print(f"Processing {repo}@{sha[:7]}…")
        r = requests.get(f'https://api.github.com/repos/{repo}/commits/{sha}',
                         headers={'Authorization':f'token {token}'})
        if r.status_code != 200:
            continue
        for f in r.json().get('files', []):
            e = ext_of(f['filename'])
            if e and e in EXT_TO_LANG:
                lang = EXT_TO_LANG[e]
                lang_tally[lang] += f.get('additions', 0)
        time.sleep(0.1)

    # build markdown
    total = sum(lang_tally.values()) or 1
    top10 = lang_tally.most_common(10)

    output = ["### Commit-Based Language Stats", ""]
    output.append("| Language    | Lines   | Percentage |")
    output.append("| ----------- | ------: | ---------: |")
    for lang, cnt in top10:
        pct = cnt/total*100
        output.append(f"| {lang:<11} | {cnt:>6,} | {pct:>9.2f}% |")
    new_section = "\n".join(output)

    # inject into README.md
    readme_path = "README.md"
    text = open(readme_path, "r", encoding="utf-8").read()
    patched = re.sub(
        r'<!--START_COMMIT_LANG_STATS-->.*<!--END_COMMIT_LANG_STATS-->',
        f'<!--START_COMMIT_LANG_STATS-->\n{new_section}\n<!--END_COMMIT_LANG_STATS-->',
        text,
        flags=re.DOTALL
    )
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(patched)

    print("README.md updated with new language stats.")

if __name__ == "__main__":
    main()
