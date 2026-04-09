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
        if any(ext in obj.lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']) and 'http' in obj:
            return obj
    if isinstance(obj, dict):
        for key in['url', 'proxy_url']:
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
    full_text = "\n".join(filter(None, text_segments))
    return full_text, [u.rstrip('.,!?"\')') for u in urls]

def ask_groq(messages_text):
    print("Sending data to Groq AI...")
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    TASK: Extract events.
    
    RULES:
    1. Identify a SPECIFIC START DATE (YYYY-MM-DD).
    2. Identify a SPECIFIC TIME (HH:MM) if mentioned. If not, use 15:00.
    3. Extract a short, punchy TITLE.
    4. Return ONLY a valid JSON list of objects.
    5. "index": Use the EXACT integer index provided in the block header.
    
    Messages:
    {messages_text}

    OUTPUT FORMAT:[
      {{"index": 0, "date": "YYYY-MM-DD", "time": "HH:MM", "title": "Short Title", "type": "patch/news/twitch/hero"}}
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

    existing_ids =[str(e.get('original_id')) for e in old_db]
    to_process = []
    ai_input_list =[]
    
    for i, m in enumerate(messages):
        if str(m['id']) in existing_ids: continue
        
        full_text, all_urls = extract_all_text_and_links(m)
        if full_text:
            to_process.append({
                "index": i, "id": m['id'], "raw": full_text,
                "clean": re.sub(r'<@&?\d+>', '', full_text).replace('🔔', '').strip(),
                "urls": all_urls, "img": find_deep_img(m), "posted": m['timestamp'][:10]
            })
            ai_input_list.append(f"INDEX: [{i}]\nCONTENT: {full_text}")

    if not ai_input_list:
        print("No new events.")
        return

    ai_results = ask_groq("\n---\n".join(ai_input_list))
    new_entries =[]

    for ar in ai_results:
        idx = ar.get('index')
        intel = next((x for x in to_process if x['index'] == idx), None)
        if not intel: continue
        
        etype = ar.get('type', 'news')
        event_date = ar.get('date') or intel['posted']
        event_time = ar.get('time', '15:00')
        
        # Convert to ISO format (assuming CEST/Local for the announcement text)
        iso_date = f"{event_date}T{event_time}:00" 

        eurl = "https://www.predecessorgame.com/en-US/news"
        yt_url = next((u for u in intel['urls'] if "youtube.com" in u or "youtu.be" in u), None)
        pp_url = next((u for u in intel['urls'] if "playp.red" in u), None)

        if "twitch" in intel['raw'].lower() or "live stream" in intel['raw'].lower():
            etype, eurl = "twitch", "https://www.twitch.tv/predecessorgame"
            iso_date = f"{event_date}T18:00:00" # Standard stream time
        elif yt_url:
            etype, eurl = "youtube", yt_url.rstrip('.,!?"\')')
        
        if pp_url: eurl = pp_url.rstrip('.,!?"\')')

        new_entries.append({
            "original_id": intel['id'],
            "date": event_date,
            "iso_date": iso_date, # Now includes specific time
            "title": str(ar.get('title', 'UPDATE')).upper()[:40],
            "type": etype,
            "desc": intel['clean'],
            "image": intel['img'],
            "url": eurl
        })

    final_list = old_db + new_entries
    unique_map = {}
    for e in sorted(final_list, key=lambda x: len(x['title']), reverse=True):
        fingerprint = f"{e['date']}_{e['original_id']}"
        if fingerprint not in unique_map: unique_map[fingerprint] = e

    final_events = list(unique_map.values())
    output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": final_events}
    with open('events.json', 'w') as f:
        json.dump(output, f, indent=4)

if __name__ == "__main__":
    scrape()
