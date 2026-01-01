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
    'Astro':   {'astro'},
    'C#':      {'cs'},
    'C/C++':   {'c','cpp','cc','cxx','h','hh','hpp','hxx', 'tpp'},
    'Elixir':  {'ex','exs'},
    'Go':      {'go'},
    'JS/TS':   {'js','jsx','ts','tsx', 'css'},
    'Java':    {'java'},
    'Kotlin':  {'kt','kts'},
    'Lua':     {'lua'},
    'PHP':     {'php'},
    'PowerShell': {'ps1','psm1','psd1'},
    'Python':  {'py'},
    'Ruby':    {'rb'},
    'Rust':    {'rs'},
    'Scala':   {'scala'},
    'Shell':   {'sh','bash','zsh','ksh'},
    'Swift':   {'swift'},
    'Typst':   {'typ'},
}

# reverse map: extension -> language
EXT_TO_LANG = {ext: lang for lang, exts in GROUPS.items() for ext in exts}

# ───── SPECIAL CPP REPO ORDER ─────
CUSTOM_CPP_REPOS = [
    ('TheRickyZhang/BattleBeyz', 'BattleBeyz'),
    ('TheRickyZhang/CompetitiveProgramming', 'CompetitiveProgramming'),
]

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

    # track net changes per file (additions - deletions)
    # key: (repo, filename) -> {'adds': int, 'dels': int}
    file_changes = defaultdict(lambda: {'adds': 0, 'dels': 0})
    ext_file_changes = defaultdict(lambda: {'adds': 0, 'dels': 0})  # for unknown extensions

    processed = 0
    for repo, sha in commits:
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
            dels = f.get('deletions', 0)
            if not ext:
                continue
            if ext in EXT_TO_LANG:
                key = (repo, f['filename'])
                file_changes[key]['adds'] += adds
                file_changes[key]['dels'] += dels
            else:
                key = (ext, repo, f['filename'])
                ext_file_changes[key]['adds'] += adds
                ext_file_changes[key]['dels'] += dels
        processed += 1
        time.sleep(0.1)

    print(f"→ processed {processed} commits")

    # compute net changes per file and tally by language
    lang_tally = Counter()
    lang_repo  = defaultdict(Counter)
    for (repo, filename), changes in file_changes.items():
        net = changes['adds'] - changes['dels']
        if net > 0:
            ext = ext_of(filename)
            lang = EXT_TO_LANG[ext]
            lang_tally[lang] += net
            lang_repo[lang][repo] += net

    # compute net for unknown extensions
    ext_tally = Counter()
    for (ext, repo, filename), changes in ext_file_changes.items():
        net = changes['adds'] - changes['dels']
        if net > 0:
            ext_tally[ext] += net

    # debug unknown extensions (only show those with ≥500 lines)
    significant_exts = [(ext, cnt) for ext, cnt in ext_tally.most_common() if cnt >= MIN_LINES_THRESHOLD]
    if significant_exts:
        print(f"\n# Extensions not in GROUPS (≥{MIN_LINES_THRESHOLD} lines):")
        for ext, cnt in significant_exts:
            print(f"- .{ext}: {cnt:,} lines")

    total = sum(lang_tally.values()) or 1
    top10 = lang_tally.most_common(10)

    # debug: top 3 repos per language (no exclusions)
    print("\n# Top 3 repos per language:")
    for lang, _ in top10:
        top3 = lang_repo[lang].most_common(3)
        repos_str = ", ".join(f"{r.split('/',1)[1]}({c:,})" for r, c in top3)
        print(f"  {lang}: {repos_str}")

    # debug: Markdown table of largest repo per language
    print("\n# Largest repo contributor per language:")
    print("| Language    | Lines     | Percentage | Featured Repo |")
    print("| ----------- | --------: | ---------: | ---- |")
    processed_langs = set()
    for lang, cnt in top10:
        # Hardcode certain repos to ensure they are displayed (may not necessarily have most, but most in-depth use)
        if lang == 'C/C++':
            cpp_total = sum(lang_repo['C/C++'].get(repo, 0) for repo, _ in CUSTOM_CPP_REPOS)
            pct = cpp_total / total * 100
            links = []
            for full_repo, name in CUSTOM_CPP_REPOS:
                c = lang_repo['C/C++'].get(full_repo, 0)
                if c > MIN_LINES_THRESHOLD:
                    links.append(f"[{name}](https://github.com/{full_repo})")
            repo_cell = ', '.join(links)
            print(f"| C/C++       | {cpp_total:>8,} | {pct:>9.2f}% | {repo_cell} |")
            processed_langs.add('C/C++')
        elif lang not in processed_langs:
            repo, c = lang_repo[lang].most_common(1)[0]
            if lang == 'JS/TS':
                repo = 'ufsasewebmaster/UF-SASE-Website'
                c = lang_repo[lang].get(repo, c)
            pct = cnt / total * 100
            repo_cell = '' if cnt <= MIN_LINES_THRESHOLD else f"[{repo.split('/',1)[1]}](https://github.com/{repo})"
            print(f"| {lang:<11} | {c:>8,} | {pct:>9.2f}% | {repo_cell} |")

    # build main markdown stats
    output = ["### Normalized Commit Language Stats", ""]
    output.append("| Language    | Lines   | Percentage | Featured Repo |")
    output.append("| ----------- | ------: | ---------: | ---- |")
    processed_langs = set()
    for lang, cnt in top10:
        if lang == 'C/C++':
            cpp_total = sum(lang_repo['C/C++'].get(repo, 0) for repo, _ in CUSTOM_CPP_REPOS)
            pct = cpp_total / total * 100
            links = []
            for full_repo, name in CUSTOM_CPP_REPOS:
                c = lang_repo['C/C++'].get(full_repo, 0)
                if c > MIN_LINES_THRESHOLD:
                    links.append(f"[{name}](https://github.com/{full_repo})")
            repo_cell = ', '.join(links)
            output.append(f"| C/C++       | {cpp_total:>6,} | {pct:>9.2f}% | {repo_cell} |")
            processed_langs.add('C/C++')
        elif lang not in processed_langs:
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
