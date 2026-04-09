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
    if isinstance(obj, dict):
        for key in['url', 'proxy_url']:
            if key in obj and isinstance(obj[key], str) and any(ext in obj[key].lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                return obj[key]
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
    print("Sending data to Groq AI...")
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    TASK: Extract events with HIGH PRECISION time.
    
    RULES:
    1. Identify START DATE (YYYY-MM-DD).
    2. Identify START TIME in CEST (e.g. "2:00 PM" is 14:00).
    3. If no time is mentioned, use 14:00.
    4. Return ONLY a valid JSON list of objects.
    
    Messages:
    {messages_text}

    OUTPUT FORMAT:[
      {{"index": 0, "date": "YYYY-MM-DD", "time": "HH:MM", "title": "Title", "type": "patch/news/twitch/hero"}}
    ]
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.0
        )
        raw = chat.choices[0].message.content
        json_match = re.search(r'\[.*\]', raw, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        return[]
    except Exception as e: 
        print(f"AI Request Failed: {e}")
        return[]

def scrape():
    messages = get_discord_messages()
    if not messages: return

    try:
        with open('events.json', 'r') as f:
            old_db = json.load(f).get('events', [])
    except: old_db = []

    # Map existing events by ID so we can OVERWRITE/UPDATE them
    event_map = {str(e['original_id']): e for e in old_db}
    
    to_process, ai_input_list = [], []
    for i, m in enumerate(messages):
        full_text, all_urls = extract_all_text_and_links(m)
        if full_text:
            to_process.append({
                "index": i, "id": m['id'], "raw": full_text,
                "clean": re.sub(r'<@&?\d+>', '', full_text).replace('🔔', '').strip(),
                "urls": all_urls, "img": find_deep_img(m), "posted": m['timestamp'][:10]
            })
            ai_input_list.append(f"INDEX: [{i}]\nCONTENT: {full_text}")

    if not ai_input_list: return

    ai_results = ask_groq("\n---\n".join(ai_input_list))

    for ar in ai_results:
        idx = ar.get('index')
        intel = next((x for x in to_process if x['index'] == idx), None)
        if not intel: continue
        
        event_date = ar.get('date') or intel['posted']
        event_time = ar.get('time', '14:00')
        
        # PRECISE ISO STRING WITH CEST OFFSET (+02:00)
        iso_date = f"{event_date}T{event_time}:00+02:00"

        etype = ar.get('type', 'news')
        eurl = next((u for u in intel['urls'] if "playp.red" in u or "predecessorgame" in u), "https://www.predecessorgame.com/en-US/news")

        # This will update the existing entry with corrected time
        event_map[str(intel['id'])] = {
            "original_id": intel['id'],
            "date": event_date,
            "iso_date": iso_date,
            "title": str(ar.get('title', 'UPDATE')).upper()[:40],
            "type": etype,
            "desc": intel['clean'],
            "image": intel['img'],
            "url": eurl
        }

    output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": list(event_map.values())}
    with open('events.json', 'w') as f:
        json.dump(output, f, indent=4)
    print("Scrape complete. Correction applied.")

if __name__ == "__main__":
    scrape()
