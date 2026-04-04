import os
import requests
import json
import re
from groq import Groq
from datetime import datetime

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CHANNEL_ID = "1487129767865225261" 

def get_discord_messages():
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=25"
    res = requests.get(url, headers=headers)
    return res.json() if res.status_code == 200 else []

def find_deep_img(obj):
    if not obj: return ""
    if isinstance(obj, str):
        if any(ext in obj.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']) and 'http' in obj:
            return obj
    if isinstance(obj, dict):
        for key in ['url', 'proxy_url']:
            if key in obj and isinstance(obj[key], str) and any(ext in obj[key].lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                return obj[key]
        for v in obj.values():
            res = find_deep_img(v)
            if res: return res
    if isinstance(obj, list):
        for i in obj:
            res = find_deep_img(i)
            if res: return res
    return ""

def extract_all_text_and_links(m):
    """Gathers all text and all URLs from content, snapshots, and embeds."""
    text_segments = [m.get('content', '')]
    urls = re.findall(r'(https?://[^\s]+)', m.get('content', ''))

    def process_obj(obj):
        nonlocal urls
        if 'message_snapshots' in obj:
            for snap in obj['message_snapshots']:
                snap_msg = snap.get('message', {})
                text_segments.append(snap_msg.get('content', ''))
                urls.extend(re.findall(r'(https?://[^\s]+)', snap_msg.get('content', '')))
                process_obj(snap_msg)
        if 'embeds' in obj:
            for emb in obj['embeds']:
                text_segments.append(emb.get('title', ''))
                text_segments.append(emb.get('description', ''))
                if emb.get('url'): urls.append(emb['url'])

    process_obj(m)
    full_text = "\n".join(filter(None, text_segments))
    # Clean URLs (remove trailing punctuation)
    clean_urls = [u.rstrip('.,!?"\')') for u in urls]
    return full_text, clean_urls

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    TASK: Extract events.
    RULES:
    1. Identify a SPECIFIC START DATE (YYYY-MM-DD) if mentioned.
    2. Identify a VERSION NUMBER (e.g., V1.13) mentioned.
    3. Extract a short, punchy TITLE.
    4. "original_id": Use the EXACT ID provided in the BLOCK_ID line.
    
    Messages:
    {messages_text}
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.1
        )
        raw = chat.choices[0].message.content
        return json.loads(re.search(r'\[.*\]', raw, re.DOTALL).group(0))
    except: return []

def scrape():
    messages = get_discord_messages()
    if not messages: return

    try:
        with open('events.json', 'r') as f:
            old_db = json.load(f).get('events', [])
    except: old_db = []

    existing_ids = [str(e.get('original_id')) for e in old_db]
    intel_pool = {}
    ai_input_list = []
    
    for m in messages:
        if str(m['id']) in existing_ids: continue
        
        full_text, all_urls = extract_all_text_and_links(m)
        if full_text:
            intel_pool[str(m['id'])] = {
                "full_text": full_text,
                "clean_text": re.sub(r'<@&?\d+>', '', full_text).replace('🔔', '').strip(),
                "all_urls": all_urls,
                "img": find_deep_img(m),
                "posted": m['timestamp'][:10]
            }
            ai_input_list.append(f"BLOCK_ID: {m['id']}\nCONTENT: {full_text}")

    if not ai_input_list:
        print("No new updates found.")
        return

    ai_results = ask_groq("\n---\n".join(ai_input_list))
    new_entries = []

    for ar in ai_results:
        mid = str(ar.get('original_id') or ar.get('BLOCK_ID'))
        if mid not in intel_pool: continue
        
        intel = intel_pool[mid]
        text_lower = intel['full_text'].lower()
        urls = intel['all_urls']
        
        # --- DATE DETERMINATION ---
        event_date = ar.get('date')
        if (not event_date or event_date == "None") and ar.get('version'):
            for old in (old_db + new_entries):
                if ar['version'].lower() in old['title'].lower():
                    event_date = old['date']
                    break
        if not event_date or event_date == "None":
            event_date = intel['posted']

        # --- CATEGORY & LINK ASSIGNMENT (THE REVISED HIERARCHY) ---
        etype = "patch" # 4.0 Default
        eurl = "https://www.predecessorgame.com/en-US/news"

        # Find YouTube URL if it exists
        yt_url = next((u for u in urls if "youtube.com" in u or "youtu.be" in u), None)
        # Find playp.red URL if it exists
        pp_url = next((u for u in urls if "playp.red" in u), None)

        # 1.0 Twitch Priority
        if "twitch" in text_lower or "live stream" in text_lower:
            etype = "twitch"
            eurl = "https://www.twitch.tv/predecessorgame"
        # 2.0 YouTube Secondary
        elif yt_url:
            etype = "youtube"
            eurl = yt_url

        # 3.0 Special Link Handling (playp.red overrides link regardless of category)
        if pp_url:
            eurl = pp_url

        new_entries.append({
            "original_id": mid,
            "date": event_date,
            "iso_date": event_date + ("T18:00:00Z" if etype == "twitch" else "T00:00:00Z"),
            "title": ar.get('title', 'UPDATE').upper(),
            "type": etype,
            "desc": intel['clean_text'],
            "image": intel['img'],
            "url": eurl
        })

    final_list = old_db + new_entries
    output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": final_list}
    with open('events.json', 'w') as f:
        json.dump(output, f, indent=4)
    print(f"Added {len(new_entries)} events.")

if __name__ == "__main__":
    scrape()
