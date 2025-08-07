#!/usr/bin/env python3
import os, sys, time, requests, re
from collections import Counter, defaultdict

# ───── CONFIG ─────
CACHE_FILE          = '.last_seen_sha'
MAX_PAGES           = 10
PER_PAGE            = 100
MAX_COMMIT_ADDS     = 50000
MIN_LINES_THRESHOLD = 500

# Only these languages (extensions) will be counted:
GROUPS = {
    'C/C++':   {'c','cpp','cc','cxx','h','hh','hpp','hxx'},
    'Python':  {'py'},
    'Java':    {'java'},
    'JS/TS':   {'js','jsx','ts','tsx'},
    'Go':      {'go'},
    'Rust':    {'rs'},
    'Ruby':    {'rb'},
    'PHP':     {'php'},
    'Kotlin':  {'kt','kts'},
    'Swift':   {'swift'},
    'C#':      {'cs'},
    'Scala':   {'scala'},
    'Shell':   {'sh','bash'},
    'Astro':   {'astro'},
}

# reverse map: extension -> language
EXT_TO_LANG = {ext: lang for lang, exts in GROUPS.items() for ext in exts}

# ───── CACHE HELPERS ─────
def read_last_seen():
    try:
        return open(CACHE_FILE, 'r', encoding='utf-8').read().strip()
    except FileNotFoundError:
        return None


def write_last_seen(sha):
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        f.write(sha)

# ───── FETCH COMMITS ─────
def get_commits(user, token, last=None):
    headers = {
        'Authorization': f'token {token}',
        'Accept':        'application/vnd.github.cloak-preview'
    }
    commits = []
    stop = False

    for page in range(1, MAX_PAGES+1):
        r = requests.get('https://api.github.com/search/commits',
                         headers=headers,
                         params={'q': f'author:{user}', 'page': page, 'per_page': PER_PAGE})
        if r.status_code != 200:
            print("Error fetching commits:", r.json())
            break
        items = r.json().get('items', [])
        if not items:
            break
        for it in items:
            sha = it['sha']
            if sha == last:
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
    user = sys.argv[1] if len(sys.argv)>1 else 'TheRickyZhang'
    token = os.environ.get('GH_TOKEN')
    if not token:
        print("GH_TOKEN not set")
        sys.exit(1)

    last = read_last_seen()
    print(f"Fetching commits for {user}… (since {last or 'the very beginning'})")
    commits = get_commits(user, token, last)
    print(f"→ found {len(commits)} new commits")

    if commits:
        write_last_seen(commits[0][1])

    # tally lines per language and per-extension unknowns
    lang_tally = Counter()
    lang_repo  = defaultdict(Counter)
    ext_tally  = Counter()

    for repo, sha in commits:
        print(f"Processing {repo}@{sha[:7]}…")
        r = requests.get(f'https://api.github.com/repos/{repo}/commits/{sha}',
                         headers={'Authorization': f'token {token}'})
        if r.status_code != 200:
            continue
        files = r.json().get('files', [])
        total_adds = sum(f.get('additions', 0) for f in files)
        if total_adds > MAX_COMMIT_ADDS:
            print(f"Skipping {repo}@{sha[:7]}: {total_adds:,} additions > {MAX_COMMIT_ADDS}")
            continue
        for f in files:
            ext = ext_of(f['filename'])
            adds = f.get('additions', 0)
            if not ext:
                continue
            if ext in EXT_TO_LANG:
                lang = EXT_TO_LANG[ext]
                lang_tally[lang] += adds
                lang_repo[lang][repo] += adds
            else:
                ext_tally[ext] += adds
        time.sleep(0.1)

    # debug unknown extensions
    if ext_tally:
        print("\n# Extensions not in GROUPS:")
        for ext, cnt in ext_tally.most_common():
            print(f"- .{ext}: {cnt:,} lines")

    total = sum(lang_tally.values()) or 1
    top10 = lang_tally.most_common(10)

    # debug: Markdown table of largest repo per language
    print("\n# Largest repo contributor per language:")
    print("| Language    | Lines     | Percentage | Featured Repo |")
    print("| ----------- | --------: | ---------: | ---- |")
    for lang, cnt in top10:
        repo, c = lang_repo[lang].most_common(1)[0]
        if lang == 'JS/TS':
            repo = 'ufsasewebmaster/UF-SASE-Website'
            c = lang_repo[lang].get(repo, c)
        pct = cnt / total * 100
        # omit repo link if small
        repo_cell = '' if cnt <= MIN_LINES_THRESHOLD else f"[{repo.split('/',1)[1]}](https://github.com/{repo})"
        print(f"| {lang:<11} | {c:>8,} | {pct:>9.2f}% | {repo_cell} |")

    # build main markdown stats
    output = ["### Normalized Commit Language Stats", ""]
    output.append("| Language    | Lines   | Percentage | Repo |")
    output.append("| ----------- | ------: | ---------: | ---- |")
    for lang, cnt in top10:
        if lang == 'JS/TS':
            repo = 'ufsasewebmaster/UF-SASE-Website'
        else:
            repo = lang_repo[lang].most_common(1)[0][0]
        pct = cnt / total * 100
        repo_cell = '' if cnt <= MIN_LINES_THRESHOLD else f"[{repo.split('/',1)[1]}](https://github.com/{repo})"
        output.append(f"| {lang:<11} | {cnt:>6,} | {pct:>9.2f}% | {repo_cell} |")
    new_section = "\n".join(output)

    # inject into README.md
    readme = open("README.md","r",encoding="utf-8").read()
    patched = re.sub(
        r'<!--START_COMMIT_LANG_STATS-->.*<!--END_COMMIT_LANG_STATS-->',
        f'<!--START_COMMIT_LANG_STATS-->\n{new_section}\n<!--END_COMMIT_LANG_STATS-->',
        readme, flags=re.DOTALL
    )
    with open("README.md","w",encoding="utf-8") as f:
        f.write(patched)

    print("\nREADME.md updated with new language stats.")

if __name__ == "__main__":
    main()
