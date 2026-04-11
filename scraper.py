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
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=50"
    res = requests.get(url, headers=headers)
    return res.json() if res.status_code == 200 else []

def find_deep_img(obj):
    if not obj: return ""
    if isinstance(obj, str):
        if any(ext in obj.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']) and 'http' in obj: return obj
    if isinstance(obj, dict):
        for key in ['url', 'proxy_url']:
            if key in obj and isinstance(obj[key], str) and any(ext in obj[key].lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']): return obj[key]
        for v in obj.values():
            res = find_deep_img(v)
            if res: return res
    return ""

def extract_all_text_and_links(m):
    text_segments = [m.get('content', '')]
    urls = re.findall(r'(https?://[^\s]+)', m.get('content', ''))
    def process_obj(obj):
        if 'embeds' in obj:
            for emb in obj['embeds']:
                text_segments.append(emb.get('title', ''))
                text_segments.append(emb.get('description', ''))
                if emb.get('url'): urls.append(emb['url'])
    process_obj(m)
    return "\n".join(filter(None, text_segments)), [u.rstrip('.,!?"\')') for u in urls]

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
    Today is {today}. Context: Predecessor game announcements.
    TASK: Extract events. Merge duplicate announcements for the same event into ONE range.
    RULES:
    1. Identify START and END dates (YYYY-MM-DD).
    2. Identify START TIME (HH:MM). Default to 14:00 if not found.
    3. Return ONLY a valid JSON list.
    4. Deduplicate: If two messages discuss the same 'XP Weekend', return only ONE object with the widest date range.
    Messages:
    {messages_text}
    OUTPUT FORMAT: [{{'index': 0, 'date': 'YYYY-MM-DD', 'end_date': 'YYYY-MM-DD', 'time': 'HH:MM', 'title': 'Short Title', 'type': 'patch/news/twitch/hero'}}]
    """
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile", temperature=0.0)
        return json.loads(re.search(r'\[.*\]', chat.choices[0].message.content, re.DOTALL).group(0))
    except: return []

def scrape():
    messages = get_discord_messages()
    if not messages: return
    try:
        with open('events.json', 'r') as f:
            old_db = json.load(f).get('events', [])
    except: old_db = []

    event_map = {str(e['original_id']): e for e in old_db}
    to_process, ai_input = [], []
    for i, m in enumerate(messages):
        txt, urls = extract_all_text_and_links(m)
        to_process.append({"index": i, "id": m['id'], "raw": txt, "clean": txt, "urls": urls, "img": find_deep_img(m), "posted": m['timestamp'][:10]})
        ai_input.append(f"INDEX: [{i}]\nCONTENT: {txt}")

    results = ask_groq("\n---\n".join(ai_input))
    for ar in results:
        intel = next((x for x in to_process if x['index'] == ar.get('index')), None)
        if not intel: continue
        
        # Determine unique event key for merging logic (e.g., "DOUBLE XP WEEKEND")
        event_key = str(ar.get('title', '')).upper()
        
        event_map[str(intel['id'])] = {
            "original_id": intel['id'],
            "date": ar.get('date'),
            "end_date": ar.get('end_date'),
            "iso_date": f"{ar.get('date')}T{ar.get('time', '14:00')}:00+02:00",
            "title": event_key[:40],
            "type": ar.get('type', 'news'),
            "desc": intel['clean'],
            "image": intel['img'],
            "url": next((u for u in intel['urls'] if "playp.red" in u or "predecessor" in u), "https://www.predecessorgame.com/en-US/news")
        }

    with open('events.json', 'w') as f:
        json.dump({"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": list(event_map.values())}, f, indent=4)

if __name__ == "__main__": scrape()
