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
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=20"
    res = requests.get(url, headers=headers)
    if res.status_code != 200: return []
    return res.json()

def find_deep_img(obj):
    if not obj: return ""
    if isinstance(obj, str):
        if any(ext in obj.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']) and 'http' in obj: return obj
    if isinstance(obj, dict):
        for key in['url', 'proxy_url']:
            if key in obj and isinstance(obj[key], str) and any(ext in obj[key].lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']): return obj[key]
        for v in obj.values():
            res = find_deep_img(v)
            if res: return res
    return ""

def extract_all_text_and_links(m):
    text_segments =[m.get('content', '')]
    urls = re.findall(r'(https?://[^\s]+)', m.get('content', ''))
    def process_obj(obj):
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
    return "\n".join(filter(None, text_segments)), [u.rstrip('.,!?"\')') for u in urls]

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    TASK: Extract events.
    
    RULES:
    1. Identify START DATE (YYYY-MM-DD).
    2. Identify START TIME (HH:MM) if mentioned. (Default 15:00).
    3. Identify END DATE (YYYY-MM-DD) if it's a multi-day event (like a Weekend XP event).
    4. TITLE should be short and punchy.
    5. Return ONLY JSON list.
    6. "index": use the EXACT integer index provided.
    
    Messages:
    {messages_text}

    OUTPUT FORMAT:[
      {{"index": 0, "date": "YYYY-MM-DD", "time": "HH:MM", "end_date": "YYYY-MM-DD", "title": "Title", "type": "patch/news/twitch/hero/season"}}
    ]
    """
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile", temperature=0.0)
        json_match = re.search(r'\[.*\]', chat.choices[0].message.content, re.DOTALL)
        return json.loads(json_match.group(0)) if json_match else []
    except: return []

def scrape():
    messages = get_discord_messages()
    if not messages: return
    try:
        with open('events.json', 'r') as f: old_db = json.load(f).get('events', [])
    except: old_db = []
    
    existing_ids =[str(e.get('original_id')) for e in old_db]
    to_process, ai_input_list = [], []
    
    for i, m in enumerate(messages):
        if str(m['id']) in existing_ids: continue
        txt, urls = extract_all_text_and_links(m)
        if txt:
            to_process.append({"index": i, "id": m['id'], "raw": txt, "clean": re.sub(r'<@&?\d+>', '', txt).strip(), "urls": urls, "img": find_deep_img(m), "posted": m['timestamp'][:10]})
            ai_input_list.append(f"INDEX: [{i}]\nCONTENT: {txt}")

    if not ai_input_list: return
    ai_results = ask_groq("\n---\n".join(ai_input_list))
    new_entries =[]

    for ar in ai_results:
        intel = next((x for x in to_process if x['index'] == ar.get('index')), None)
        if not intel: continue
        
        etype = ar.get('type', 'news')
        event_date = ar.get('date') or intel['posted']
        iso_date = f"{event_date}T{ar.get('time', '15:00')}:00"
        
        eurl = next((u for u in intel['urls'] if "playp.red" in u or "predecessorgame.com" in u), "https://www.predecessorgame.com/en-US/news")
        
        new_entries.append({
            "original_id": intel['id'],
            "date": event_date,
            "end_date": ar.get('end_date'), # New field
            "iso_date": iso_date,
            "title": str(ar.get('title', 'UPDATE')).upper()[:40],
            "type": etype,
            "desc": intel['clean'],
            "image": intel['img'],
            "url": eurl
        })

    final_list = old_db + new_entries
    unique_map = {f"{e['date']}_{e['original_id']}": e for e in sorted(final_list, key=lambda x: len(x['title']), reverse=True)}
    with open('events.json', 'w') as f: json.dump({"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": list(unique_map.values())}, f, indent=4)

if __name__ == "__main__": scrape()
