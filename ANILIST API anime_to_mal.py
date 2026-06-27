import requests
import time
import difflib
import xml.etree.ElementTree as ET
from xml.dom import minidom
import os

# --- CONFIGURATION ---
INPUT_FILE = "anime_list.txt"
OUTPUT_XML = "mal_export.xml"
SKIPPED_FILE = "skipped.txt"
SIMILARITY_THRESHOLD = 0.45  # Lowered slightly to 45% to be a bit more forgiving

processed_mal_ids = set()
xml_anime_entries = []
skipped_anime = []

ANILIST_API_URL = "https://graphql.anilist.co"

GRAPHQL_QUERY = """
query ($search: String) {
  Page (perPage: 5) {
    media (search: $search, type: ANIME) {
      id
      idMal
      status
      title {
        romaji
        english
        native
      }
      synonyms
      relations {
        nodes {
          id
          idMal
          type
          status
          title {
            romaji
            english
            native
          }
        }
      }
    }
  }
}
"""

def get_similarity(query, text):
    if not text:
        return 0
    return difflib.SequenceMatcher(None, query.lower(), text.lower()).ratio()

def call_anilist_api(search_title):
    time.sleep(0.8)  # Slightly increased delay for safety
    variables = {"search": search_title}
    
    try:
        response = requests.post(ANILIST_API_URL, json={"query": GRAPHQL_QUERY, "variables": variables})
        
        if response.status_code == 200:
            return response.json().get("data", {}).get("Page", {}).get("media", [])
        elif response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            print(f"  -> Rate limit hit! Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            return call_anilist_api(search_title)
        else:
            print(f"  -> API Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"  -> Network error: {e}")
    return []

def map_status(anilist_status):
    if anilist_status == "FINISHED": return "Completed"
    elif anilist_status == "RELEASING": return "Watching"
    elif anilist_status == "NOT_YET_RELEASED": return "Plan to Watch"
    return "Completed"

def parse_best_title(title_node):
    if not title_node: return "Unknown Title"
    return title_node.get("english") or title_node.get("romaji") or title_node.get("native")

def check_and_append_entry(media_node):
    mal_id = media_node.get("idMal")
    if not mal_id or mal_id in processed_mal_ids:
        return False

    title = parse_best_title(media_node.get("title"))
    status = map_status(media_node.get("status"))

    xml_anime_entries.append({"id": str(mal_id), "title": title, "status": status})
    processed_mal_ids.add(mal_id)
    print(f"  -> Added: {title} [{status}]")
    return True

def analyze_and_process(query_title):
    # Clean the string: remove invisible BOM markers, newlines, and excess spaces
    clean_query = query_title.strip('\ufeff').strip()
    
    print(f"\nSearching for: [{clean_query}]...")
    
    # If the line is empty after cleaning, skip it
    if not clean_query:
        return

    search_results = call_anilist_api(clean_query)

    if not search_results:
        print("  -> Refused: Zero matched items found on AniList.")
        skipped_anime.append(clean_query)
        return

    best_match_node = None
    highest_calculated_score = 0.0

    for media in search_results:
        potential_strings = []
        titles = media.get("title", {})
        
        if titles:
            if titles.get("romaji"): potential_strings.append(titles["romaji"])
            if titles.get("english"): potential_strings.append(titles["english"])
            if titles.get("native"): potential_strings.append(titles["native"])
            
        synonyms = media.get("synonyms", [])
        if synonyms:
            potential_strings.extend(synonyms)

        for text_string in potential_strings:
            score = get_similarity(clean_query, text_string)
            if score > highest_calculated_score:
                highest_calculated_score = score
                best_match_node = media

    if highest_calculated_score >= SIMILARITY_THRESHOLD and best_match_node:
        print(f"  -> Match Found! ({int(highest_calculated_score * 100)}% similarity)")
        check_and_append_entry(best_match_node)
        
        relations = best_match_node.get("relations", {}).get("nodes", [])
        if relations:
            for related_node in relations:
                if related_node.get("type") == "ANIME":
                    check_and_append_entry(related_node)
    else:
        print(f"  -> Skipped: Best match was only {int(highest_calculated_score * 100)}% similar.")
        skipped_anime.append(clean_query)

def compile_xml_document():
    root = ET.Element("myanimelist")
    myinfo = ET.SubElement(root, "myinfo")
    ET.SubElement(myinfo, "user_export_type").text = "1"
    
    for item in xml_anime_entries:
        anime_node = ET.SubElement(root, "anime")
        ET.SubElement(anime_node, "series_animedb_id").text = item["id"]
        ET.SubElement(anime_node, "series_title").text = item["title"]
        ET.SubElement(anime_node, "my_status").text = item["status"]
        ET.SubElement(anime_node, "my_watched_episodes").text = "0"
        ET.SubElement(anime_node, "update_on_import").text = "1"
        
    raw_string = ET.tostring(root, "utf-8")
    dom_object = minidom.parseString(raw_string)
    formatted_xml = dom_object.toprettyxml(indent="  ")
    
    with open(OUTPUT_XML, "w", encoding="utf-8") as file_out:
        file_out.write(formatted_xml)

def main():
    if not os.path.exists(INPUT_FILE):
        print(f"Error: '{INPUT_FILE}' does not exist.")
        return

    # Force python to read the file as UTF-8
    with open(INPUT_FILE, "r", encoding="utf-8") as file_in:
        execution_queue = file_in.readlines()

    print(f"Found {len(execution_queue)} items to process.")

    for target_query in execution_queue:
        analyze_and_process(target_query)

    print("\nBuilding XML document...")
    compile_xml_document()

    if skipped_anime:
        with open(SKIPPED_FILE, "w", encoding="utf-8") as file_skip:
            for item in skipped_anime:
                file_skip.write(item + "\n")

    print("\nFinished! Check 'mal_export.xml'.")

if __name__ == "__main__":
    main()
