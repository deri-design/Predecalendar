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
    if res.status_code != 200:
        print(f"DISCORD ERROR {res.status_code}: {res.text}")
        return[]
    return res.json()

def find_deep_img(obj):
    if not obj: return ""
    if isinstance(obj, str):
        if any(ext in obj.lower() for ext in['.png', '.jpg', '.jpeg', '.webp']) and 'http' in obj: return obj
    if isinstance(obj, dict):
        for key in ['url', 'proxy_url']:
            if key in obj and isinstance(obj[key], str) and any(ext in obj[key].lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']): return obj[key]
        for v in obj.values():
            res = find_deep_img(v)
            if res: return res
    if isinstance(obj, list):
        for i in obj:
            res = find_deep_img(i)
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
    Today is {today}. Predecessor game announcements. 
    TASK: Extract events with exact dates and ranges.
    RULES:
    1. Identify START DATE (YYYY-MM-DD).
    2. Identify END DATE (YYYY-MM-DD). If one-day event, use same as START.
    3. Identify START TIME (HH:MM) - e.g. "2:00 PM" is 14:00. Default 14:00.
    4. MERGE DUPLICATES: If multiple messages refer to the exact same event (like "Double XP Weekend" and "Double XP is LIVE"), output only ONE event combining the earliest start date and latest end date.
    5. Return ONLY valid JSON list. "index" must match header index.
    Messages:
    {messages_text}
    OUTPUT FORMAT:[
      {{"index": 0, "date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD", "time": "HH:MM", "title": "Title", "type": "patch/news/twitch/hero"}}
    ]
    """
    try:
        chat = client.chat.completions.create(messages=[{"role": "user", "content": prompt}], model="llama-3.3-70b-versatile", temperature=0.0)
        raw = chat.choices[0].message.content
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        return json.loads(match.group(0)) if match else[]
    except: return[]

def scrape():
    messages = get_discord_messages()
    if not messages: return
    try:
        with open('events.json', 'r') as f:
            db = json.load(f)
            old_events = db.get('events', [])
    except: old_events =[]

    to_process, ai_input = [],[]
    for i, m in enumerate(messages):
        txt, urls = extract_all_text_and_links(m)
        
        # Clean Discord formatting & Custom Emojis
        clean_txt = re.sub(r'<a?:[a-zA-Z0-9_]+:\d+>', '', txt) 
        clean_txt = re.sub(r'<@&?\d+>', '', clean_txt).replace('🔔', '').strip()
        
        to_process.append({"index": i, "id": m['id'], "raw": txt, "clean": clean_txt, "urls": urls, "img": find_deep_img(m), "posted": m['timestamp'][:10]})
        ai_input.append(f"INDEX: [{i}]\nCONTENT: {txt}")

    results = ask_groq("\n---\n".join(ai_input))
    new_events =[]
    
    for ar in results:
        intel = next((x for x in to_process if x['index'] == ar.get('index')), None)
        if not intel: continue
        
        date = ar.get('date') or intel['posted']
        end_date = ar.get('end_date') or date
        time = ar.get('time', '14:00')
        iso = f"{date}T{time}:00+02:00" # FORCE CEST OFFSET

        etype = ar.get('type', 'news')
        if "twitch" in intel['raw'].lower(): etype = "twitch"
        if "patch" in intel['raw'].lower() or "v1." in intel['raw'].lower(): etype = "patch"

        new_events.append({
            "original_id": intel['id'], "date": date, "end_date": end_date, "iso_date": iso,
            "title": str(ar.get('title', 'UPDATE')).upper()[:40], "type": etype,
            "desc": intel['clean'], "image": intel['img'],
            "url": next((u for u in intel['urls'] if "playp.red" in u or "predecessor" in u), "https://www.predecessorgame.com/en-US/news")
        })

    # Combine and Deduplicate (Merges similar posts into one line)
    all_events = old_events + new_events
    deduped_map = {}
    
    for e in all_events:
        # Group by topic and month so duplicate posts merge
        title_core = "XP" if "XP" in e['title'] else e['title'].split()[0]
        month = e['date'][:7] 
        key = f"{title_core}_{month}"
        
        if key in deduped_map:
            if e['date'] < deduped_map[key]['date']:
                deduped_map[key]['date'] = e['date']
                deduped_map[key]['iso_date'] = e['iso_date']
            if e.get('end_date', e['date']) > deduped_map[key].get('end_date', deduped_map[key]['date']):
                deduped_map[key]['end_date'] = e.get('end_date', e['date'])
            if e['image'] and not deduped_map[key]['image']:
                deduped_map[key]['image'] = e['image']
        else:
            deduped_map[key] = e

    with open('events.json', 'w') as f:
        json.dump({"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": list(deduped_map.values())}, f, indent=4)

if __name__ == "__main__": scrape()
