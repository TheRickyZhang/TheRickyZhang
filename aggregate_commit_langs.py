import requests
import os
import sys
import re

# Use the GitHub Search API to find repositories where you committed.
def get_repos(username, token):
    headers = {
        'Authorization': f'token {token}',
        'Accept': 'application/vnd.github.cloak-preview'  # Needed for commit search
    }
    repos = set()
    page = 1
    while True:
        url = 'https://api.github.com/search/commits'
        params = {
            'q': f'author:{username}',
            'page': page,
            'per_page': 100
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print("Error fetching commits:", response.json())
            break
        data = response.json()
        items = data.get('items', [])
        if not items:
            break
        for item in items:
            repos.add(item['repository']['full_name'])
        page += 1
        if page > 5:  # Limit pages for demo purposes
            break
    return list(repos)

# For each repository, fetch its language stats.
def get_language_stats(repo, token):
    headers = {'Authorization': f'token {token}'}
    url = f'https://api.github.com/repos/{repo}/languages'
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return {}

def main():
    username = sys.argv[1] if len(sys.argv) > 1 else 'TheRickyZhang'
    token = os.environ.get('GH_TOKEN')
    if not token:
        print("GH_TOKEN not set")
        sys.exit(1)
    
    print(f"Fetching repos for {username}...")
    repos = get_repos(username, token)
    
    aggregated = {}
    for repo in repos:
        print(f"Processing {repo}...")
        stats = get_language_stats(repo, token)
        for lang, count in stats.items():
            aggregated[lang] = aggregated.get(lang, 0) + count

    # Calculate total bytes for percentage calculations.
    total_bytes = sum(aggregated.values())
    
    # Create markdown table for top 10 languages.
    top_langs = sorted(aggregated.items(), key=lambda x: x[1], reverse=True)[:10]
    output_lines = ["## Commit-Based Language Stats", ""]
    output_lines.append("| Language | Bytes | Percentage |")
    output_lines.append("| --- | ---:| ---:|")
    for lang, count in top_langs:
        perc = (count / total_bytes * 100) if total_bytes > 0 else 0
        output_lines.append(f"| {lang} | {count:,} | {perc:.2f}% |")
    new_section = "\n".join(output_lines)

    # Update README.md between markers.
    readme_path = "README.md"
    with open(readme_path, "r", encoding="utf-8") as f:
        readme = f.read()

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
