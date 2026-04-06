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
    return res.json() if res.status_code == 200 else[]

def find_deep_img(obj):
    if not obj: return ""
    if isinstance(obj, str):
        if any(ext in obj.lower() for ext in['.png', '.jpg', '.jpeg', '.webp']) and 'http' in obj:
            return obj
    if isinstance(obj, dict):
        for key in ['url', 'proxy_url']:
            if key in obj and isinstance(obj[key], str) and any(ext in obj[key].lower() for ext in['.png', '.jpg', '.jpeg', '.webp']):
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
    full_text = "\n".join(filter(None, text_segments))
    return full_text, [u.rstrip('.,!?"\')') for u in urls]

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    TASK: Extract precise event data.
    
    RULES:
    1. "date": If a specific future date is mentioned, use YYYY-MM-DD. If it says "LIVE NOW", "Today", or "is live!", output exactly "TODAY". If neither, output "NONE".
    2. "time": Extract the UTC time in 24-hour format (HH:MM:SS). e.g., 6PM UTC = "18:00:00". If no time, output "NONE".
    3. "version": Extract version (e.g., V1.13). If none, output "NONE".
    4. "title": Short and specific. DO NOT add words like "Announcement", "Update", or "Release". Examples of good titles: "V1.13 PATCH", "DAYBREAK V4", "ADELE REVEAL".
    5. "original_id": The EXACT BLOCK_ID.
    
    Messages:
    {messages_text}
    """
    try:
        chat = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.0
        )
        raw = chat.choices[0].message.content
        return json.loads(re.search(r'\[.*\]', raw, re.DOTALL).group(0))
    except: return[]

def scrape():
    print("--- Starting Date & Title Enforcement Scrape ---")
    messages = get_discord_messages()
    if not messages: return

    try:
        with open('events.json', 'r') as f:
            db_data = json.load(f)
            master_events = db_data.get('events',[])
    except: master_events = []

    existing_ids =[str(e.get('original_id')) for e in master_events]
    intel_pool = {}
    ai_input_list =[]
    
    for m in messages:
        if str(m['id']) in existing_ids: continue # Persistence
        
        full_text, all_urls = extract_all_text_and_links(m)
        if full_text:
            intel_pool[str(m['id'])] = {
                "raw": full_text,
                "clean": re.sub(r'<@&?\d+>', '', full_text).replace('🔔', '').strip(),
                "all_urls": all_urls,
                "img": find_deep_img(m),
                "posted": m['timestamp'][:10]
            }
            ai_input_list.append(f"BLOCK_ID: {m['id']}\nCONTENT: {full_text}")

    if not ai_input_list:
        print("No new events.")
        return

    ai_results = ask_groq("\n---\n".join(ai_input_list))
    new_entries =[]

    for ar in ai_results:
        mid = str(ar.get('original_id') or ar.get('BLOCK_ID'))
        if mid not in intel_pool: continue
        
        intel = intel_pool[mid]
        text_lower = intel['raw'].lower()
        urls = intel['all_urls']
        
        # --- DATE HIERARCHY ---
        ai_date = str(ar.get('date')).strip().upper()
        version = str(ar.get('version')).strip().upper()
        
        if ai_date == "TODAY":
            event_date = intel['posted']
        elif re.match(r'^\d{4}-\d{2}-\d{2}$', ai_date):
            event_date = ai_date
        else:
            event_date = None
        
        # Version Sync (Only if date is entirely missing)
        if not event_date and version and version != "NONE":
            for old in (master_events + new_entries):
                if version in old['title'].upper() or version in old['desc'].upper():
                    event_date = old['date']
                    break
        
        # Absolute Fallback
        if not event_date:
            event_date = intel['posted']

        # --- CATEGORY & LINK ASSIGNMENT ---
        etype = "patch" 
        eurl = "https://www.predecessorgame.com/en-US/news"
        
        yt_url = next((u for u in urls if "youtube.com" in u or "youtu.be" in u), None)
        pp_url = next((u for u in urls if "playp.red" in u), None)

        if any(x in text_lower for x in ["twitch", "live stream"]):
            etype, eurl = "twitch", "https://www.twitch.tv/predecessorgame"
        elif yt_url:
            etype, eurl = "youtube", yt_url.rstrip('.,!?"\')')
        
        if pp_url: eurl = pp_url.rstrip('.,!?"\')')

        # --- TIME PARSING ---
        ai_time = str(ar.get('time')).strip()
        if not re.match(r'^\d{2}:\d{2}:\d{2}$', ai_time):
            ai_time = "18:00:00" if etype == "twitch" else "15:00:00"

        new_entries.append({
            "original_id": mid,
            "date": event_date,
            "iso_date": f"{event_date}T{ai_time}Z",
            "title": ar.get('title', 'UPDATE').upper(),
            "type": etype,
            "desc": intel['clean'],
            "image": intel['img'],
            "url": eurl
        })

    output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": master_events + new_entries}
    with open('events.json', 'w') as f:
        json.dump(output, f, indent=4)
    print(f"Success. Added {len(new_entries)} items.")

if __name__ == "__main__":
    scrape()
