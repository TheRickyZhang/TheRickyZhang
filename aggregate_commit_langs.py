#!/usr/bin/env python3
import os, sys, time, requests, re
from collections import Counter, defaultdict

# ───── CONFIG ─────
CACHE_FILE = '.last_seen_sha'
MAX_PAGES  = 10
PER_PAGE   = 100

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

EXT_TO_LANG = {ext:lang for lang,exts in GROUPS.items() for ext in exts}

def read_last_seen():
    try: return open(CACHE_FILE,'r',encoding='utf-8').read().strip()
    except: return None

def write_last_seen(sha):
    open(CACHE_FILE,'w',encoding='utf-8').write(sha)

def get_commits(user, token, last=None):
    hdr = {
        'Authorization':f'token {token}',
        'Accept':       'application/vnd.github.cloak-preview'
    }
    out=[]; stop=False
    for pg in range(1, MAX_PAGES+1):
        r = requests.get(
            'https://api.github.com/search/commits',
            headers=hdr,
            params={'q':f'author:{user}','page':pg,'per_page':PER_PAGE}
        )
        if r.status_code!=200: break
        items=r.json().get('items',[])
        if not items: break
        for it in items:
            sha=it['sha']
            if sha==last:
                stop=True; break
            out.append((it['repository']['full_name'],sha))
        if stop: break
        time.sleep(0.2)
    return out

def ext_of(path):
    fn=path.rsplit('/',1)[-1]
    if '.' not in fn: return None
    return fn.rsplit('.',1)[1].lower()

def main():
    user = sys.argv[1] if len(sys.argv)>1 else 'TheRickyZhang'
    token=os.environ.get('GH_TOKEN')
    if not token:
        print("GH_TOKEN not set"); sys.exit(1)

    last = read_last_seen()
    print(f"Fetching commits for {user}… (since {last or 'the very beginning'})")
    commits = get_commits(user, token, last)
    print(f"→ found {len(commits)} new commits")
    if commits:
        write_last_seen(commits[0][1])

    # tally both overall and per-repo
    lang_tally = Counter()
    lang_repo  = defaultdict(Counter)

    for repo,sha in commits:
        print(f"Processing {repo}@{sha[:7]}…")
        r = requests.get(
            f'https://api.github.com/repos/{repo}/commits/{sha}',
            headers={'Authorization':f'token {token}'}
        )
        if r.status_code!=200: continue
        for f in r.json().get('files',[]):
            e = ext_of(f['filename'])
            if e and e in EXT_TO_LANG:
                L = EXT_TO_LANG[e]
                adds = f.get('additions',0)
                lang_tally[L]   += adds
                lang_repo[L][repo] += adds
        time.sleep(0.1)

    total = sum(lang_tally.values()) or 1
    top10 = lang_tally.most_common(10)

    # ── DEBUG OUTPUT ──
    print("\n# Largest repo contributor per language:")
    for lang,_ in top10:
        repo,c = lang_repo[lang].most_common(1)[0]
        print(f"{lang:<11} ← {repo}  (+{c:,} lines, {c/total*100:5.2f}% of all)")

    # build markdown
    out=["### Commit-Based Language Stats",""]
    out.append("| Language    | Lines   | Percentage |")
    out.append("| ----------- | ------: | ---------: |")
    for lang,c in top10:
        pct=c/total*100
        out.append(f"| {lang:<11} | {c:>6,} | {pct:>9.2f}% |")
    block="\n".join(out)

    # inject into README.md
    txt=open("README.md","r",encoding="utf-8").read()
    patched = re.sub(
        r'<!--START_COMMIT_LANG_STATS-->.*<!--END_COMMIT_LANG_STATS-->',
        f'<!--START_COMMIT_LANG_STATS-->\n{block}\n<!--END_COMMIT_LANG_STATS-->',
        txt, flags=re.DOTALL
    )
    open("README.md","w",encoding="utf-8").write(patched)

    print("\nREADME.md updated with new language stats.")

if __name__=="__main__":
    main()
