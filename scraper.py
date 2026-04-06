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

def extract_all_content_and_links(m):
    text_segments = [m.get('content', '')]
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
    TASK: Identify release dates and version numbers.
    
    RULES:
    1. For each block, identify a START DATE (YYYY-MM-DD) if explicitly mentioned.
    2. Identify a VERSION NUMBER (e.g., V1.13) if mentioned.
    3. Extract a short, uppercase TITLE.
    4. Return ONLY a JSON list of objects: [{{"msg_index": 0, "date": "...", "version": "...", "title": "..."}}]
    
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
    print("--- Starting Discord-Timestamp Sync Scrape ---")
    messages = get_discord_messages()
    if not messages: return

    try:
        with open('events.json', 'r') as f:
            db = json.load(f)
            master_list = db.get('events', [])
    except: master_list = []

    existing_ids = [str(e.get('original_id')) for e in master_list]
    to_process = []
    ai_input = ""
    
    for m in messages:
        if str(m['id']) in existing_ids: continue 
        
        full_text, all_urls = extract_all_content_and_links(m)
        if full_text:
            # We capture the message's actual timestamp here
            posted_timestamp = m['timestamp'][:10] # YYYY-MM-DD
            
            to_process.append({
                "id": m['id'], 
                "raw": full_text, 
                "all_urls": all_urls,
                "clean": re.sub(r'<@&?\d+>', '', full_text).replace('🔔', '').strip(),
                "img": find_deep_img(m), 
                "posted": posted_timestamp # THIS IS THE FALLBACK DATE
            })
            ai_input += f"BLOCK_INDEX: {len(to_process)-1}\nCONTENT: {full_text}\n---\n"

    if not to_process:
        print("Persistence active. No new messages.")
        return

    ai_results = ask_groq(ai_input)
    new_entries = []

    for ar in ai_results:
        idx = ar.get('msg_index')
        if idx is None or idx >= len(to_process): continue
        
        intel = to_process[idx]
        text_lower = intel['raw'].lower()
        urls = intel['all_urls']
        
        # --- DATE DETERMINATION HIERARCHY ---
        event_date = ar.get('date') # 1. Direct Mention
        version = ar.get('version')
        
        if (not event_date or event_date == "None") and version: # 2. Version Sync
            for old in (master_list + new_entries):
                if version.lower() in old['title'].lower() or version.lower() in old['desc'].lower():
                    event_date = old['date']
                    break
        
        if not event_date or event_date == "None": # 3. DISCORD POST DATE FALLBACK
            event_date = intel['posted'] # Use the date the message was sent

        # --- CATEGORY & LINK ASSIGNMENT ---
        etype, eurl = "patch", "https://www.predecessorgame.com/en-US/news"
        yt_url = next((u for u in urls if "youtube.com" in u or "youtu.be" in u), None)
        pp_url = next((u for u in urls if "playp.red" in u), None)

        if "twitch" in text_lower or "live stream" in text_lower:
            etype, eurl = "twitch", "https://www.twitch.tv/predecessorgame"
        elif yt_url:
            etype, eurl = "youtube", yt_url
        
        if pp_url: eurl = pp_url 

        new_entries.append({
            "original_id": intel['id'],
            "date": event_date,
            "iso_date": event_date + ("T18:00:00Z" if etype == "twitch" else "T00:00:00Z"),
            "title": ar.get('title', 'UPDATE').upper(),
            "type": etype,
            "desc": intel['clean'],
            "image": intel['img'],
            "url": eurl
        })

    output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": master_list + new_entries}
    with open('events.json', 'w') as f:
        json.dump(output, f, indent=4)
    print(f"Success. Added {len(new_entries)} events using Discord timestamps.")

if __name__ == "__main__":
    scrape()
