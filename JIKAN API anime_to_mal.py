import time
import sys
import re
import html
from difflib import SequenceMatcher

import requests

# ---------------- Configuration ----------------
INPUT_FILE = "anime_list.txt"
OUTPUT_XML = "mal_import.xml"
SKIPPED_FILE = "skipped.txt"
MATCH_THRESHOLD = 0.50          # rule 4 & 5: minimum name similarity (raise to ~0.6 for stricter)
JIKAN_BASE = "https://api.jikan.moe/v4"
REQUEST_DELAY = 1.0             # be polite to Jikan's rate limit (~3 req/sec)

# Relation types that represent "same franchise" content we want to include (rule 2)
WANTED_RELATIONS = {
    "Sequel", "Prequel", "Side story", "Side Story",
    "Alternative version", "Alternative setting", "Parent story",
    "Spin-off", "Summary", "Other",
}


def similarity(a, b):
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def best_score(query, anime):
    """Best similarity across main, English, Japanese, and all alternate titles (rule 4 & 5)."""
    candidates = [anime.get("title"), anime.get("title_english"), anime.get("title_japanese")]
    for t in anime.get("titles", []):
        candidates.append(t.get("title"))
    return max((similarity(query, c) for c in candidates if c), default=0.0)


def jikan_get(path, params=None, retries=3):
    """GET with basic retry + rate-limit handling."""
    url = f"{JIKAN_BASE}{path}"
    for attempt in range(retries):
        time.sleep(REQUEST_DELAY)
        try:
            r = requests.get(url, params=params, timeout=30)
        except requests.RequestException:
            continue
        if r.status_code == 429:        # rate limited
            time.sleep(3)
            continue
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
    return None


def search_anime(title):
    """Find the best-matching anime for a title; returns (anime, score) or (None, score)."""
    data = jikan_get("/anime", params={"q": title, "limit": 10})
    if not data or not data.get("data"):
        return None, 0.0
    scored = [(best_score(title, a), a) for a in data["data"]]
    scored.sort(key=lambda x: x[0], reverse=True)
    top_score, top_anime = scored[0]
    if top_score >= MATCH_THRESHOLD:
        return top_anime, top_score
    return None, top_score


def get_relations(mal_id):
    """Return list of related anime MAL IDs (same franchise only) -> rule 2."""
    data = jikan_get(f"/anime/{mal_id}/relations")
    related_ids = []
    if not data or not data.get("data"):
        return related_ids
    for rel in data["data"]:
        if rel.get("relation") in WANTED_RELATIONS:
            for entry in rel.get("entry", []):
                if entry.get("type") == "anime":
                    related_ids.append(entry["mal_id"])
    return related_ids


def get_anime_full(mal_id):
    data = jikan_get(f"/anime/{mal_id}")
    if data and data.get("data"):
        return data["data"]
    return None


def map_status(anime):
    """Rule 3: airing state -> MAL list status."""
    status = (anime.get("status") or "").lower()
    if "currently airing" in status:
        return "watching"
    if "not yet aired" in status:
        return "plan_to_watch"     # "planning"
    return "completed"             # "finished airing"


def gather_franchise(root_id):
    """BFS through relations to collect every related anime id (rule 2)."""
    seen = set()
    queue = [root_id]
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        for rid in get_relations(current):
            if rid not in seen:
                queue.append(rid)
    return seen


def build_xml(entries):
    """Build MAL import XML from collected entries."""
    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8" ?>')
    lines.append("<myanimelist>")
    lines.append("  <myinfo>")
    lines.append("    <user_export_type>1</user_export_type>")
    lines.append(f"    <user_total_anime>{len(entries)}</user_total_anime>")
    lines.append("  </myinfo>")
    for e in entries:
        lines.append("  <anime>")
        lines.append(f"    <series_animedb_id>{e['mal_id']}</series_animedb_id>")
        lines.append(f"    <series_title><![CDATA[{e['title']}]]></series_title>")
        lines.append(f"    <my_status>{e['status']}</my_status>")
        lines.append(f"    <my_watched_episodes>{e['episodes']}</my_watched_episodes>")
        lines.append("    <update_on_import>1</update_on_import>")
        lines.append("  </anime>")
    lines.append("</myanimelist>")
    return "\n".join(lines)


def parse_titles(raw_lines):
    """Strip a leading '12. ' / '12) ' / '12 - ' style numbering, keep the title."""
    titles = []
    for ln in raw_lines:
        cleaned = re.sub(r"^\s*\d+\s*[\.\)\-]?\s*", "", ln).strip()
        if cleaned:
            titles.append(cleaned)
    return titles


def main():
    try:
        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            raw_lines = [ln.strip() for ln in f if ln.strip()]
    except FileNotFoundError:
        print(f"Could not find {INPUT_FILE}. Create it with one title per line.")
        sys.exit(1)

    titles = parse_titles(raw_lines)

    collected = {}      # mal_id -> entry dict (dedupes across franchises)
    skipped = []        # (title, reason)

    for idx, title in enumerate(titles, 1):
        print(f"[{idx}/{len(titles)}] Searching: {title}")
        anime, score = search_anime(title)
        if not anime:
            skipped.append((title, f"no match >= {MATCH_THRESHOLD} (best {score:.2f})"))
            print(f"    SKIPPED (best score {score:.2f})")
            continue

        root_id = anime["mal_id"]
        print(f"    Matched '{anime.get('title')}' (score {score:.2f}). Gathering franchise...")
        franchise_ids = gather_franchise(root_id)

        for mal_id in franchise_ids:
            if mal_id in collected:
                continue
            full = get_anime_full(mal_id)
            if not full:
                continue
            status = map_status(full)
            episodes = full.get("episodes") or 0
            collected[mal_id] = {
                "mal_id": mal_id,
                "title": full.get("title") or "",
                "status": status,
                "episodes": episodes if status == "completed" else 0,
            }
            print(f"      + {full.get('title')} [{full.get('type')}] -> {status}")

    xml = build_xml(list(collected.values()))
    with open(OUTPUT_XML, "w", encoding="utf-8") as f:
        f.write(xml)

    with open(SKIPPED_FILE, "w", encoding="utf-8") as f:
        for title, reason in skipped:
            f.write(f"{title}\t{reason}\n")

    print(f"\nDone. {len(collected)} entries written to {OUTPUT_XML}.")
    print(f"{len(skipped)} titles skipped (see {SKIPPED_FILE}).")


if __name__ == "__main__":
    main()
