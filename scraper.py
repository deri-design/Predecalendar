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

def python_date_finder(text):
    """Fallback Python logic to find dates like 'April 7' or '01 April'"""
    text = text.lower()
    months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    # Look for Month + Day
    match = re.search(r'(\d{1,2})?\s*(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*(\d{1,2})?', text)
    if match:
        m_str = match.group(2)
        d_str = match.group(1) or match.group(3)
        if d_str:
            try:
                dt = datetime.strptime(f"{m_str.capitalize()} {d_str} 2026", "%b %d %Y")
                return dt.strftime("%Y-%m-%d")
            except: pass
    return None

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    TASK: Extract events.
    
    CRITICAL DATE RULES:
    1. Scan the CONTENT for specific start dates (e.g., "April 7th"). 
    2. If a date is mentioned in the text, that is the EVENT DATE. 
    3. If NO date is mentioned, check for a version like "V1.13".
    
    Output Format: JSON list of objects with "date" (YYYY-MM-DD), "version", "title", and "original_id".
    
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
    except: return []

def scrape():
    messages = get_discord_messages()
    if not messages: return
    try:
        with open('events.json', 'r') as f:
            old_db = json.load(f).get('events', [])
    except: old_db = []

    existing_ids = [str(e.get('original_id')) for e in old_db]
    to_process, ai_input = [], ""
    
    for m in messages:
        if str(m['id']) in existing_ids: continue
        full_text, all_urls = extract_all_text_and_links(m)
        if full_text:
            to_process.append({
                "id": m['id'], "raw": full_text, "all_urls": all_urls,
                "clean": re.sub(r'<@&?\d+>', '', full_text).replace('🔔', '').strip(),
                "img": find_deep_img(m), "posted": m['timestamp'][:10]
            })
            ai_input += f"BLOCK_ID: {m['id']}\nCONTENT: {full_text}\n---\n"

    if not to_process: return

    ai_results = ask_groq(ai_input)
    new_entries = []

    for ar in ai_results:
        mid = str(ar.get('original_id'))
        intel = next((x for x in to_process if str(x['id']) == mid), None)
        if not intel: continue
        
        # --- DATE HIERARCHY ---
        # 1. Direct Mention (AI or Python Regex)
        event_date = ar.get('date') or python_date_finder(intel['raw'])
        
        # 2. Version Sync
        version = ar.get('version')
        if (not event_date or event_date == "None") and version:
            for old in (old_db + new_entries):
                if version.lower() in old['title'].lower() or version.lower() in old['desc'].lower():
                    event_date = old['date']
                    break
        
        # 3. Fallback
        if not event_date or event_date == "None":
            event_date = intel['posted']

        # --- CATEGORY & LINK ASSIGNMENT ---
        etype, eurl = "patch", "https://www.predecessorgame.com/en-US/news"
        urls = intel['all_urls']
        yt_url = next((u for u in urls if "youtube.com" in u or "youtu.be" in u), None)
        pp_url = next((u for u in urls if "playp.red" in u), None)

        if "twitch" in intel['raw'].lower() or "live stream" in intel['raw'].lower():
            etype, eurl = "twitch", "https://www.twitch.tv/predecessorgame"
        elif yt_url:
            etype, eurl = "youtube", yt_url
        
        if pp_url: eurl = pp_url

        new_entries.append({
            "original_id": mid, "date": event_date, "iso_date": event_date + ("T18:00:00Z" if etype == "twitch" else "T15:00:00Z"),
            "title": ar.get('title', 'UPDATE').upper(), "type": etype, "desc": intel['clean'], "image": intel['img'], "url": eurl
        })

    output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": old_db + new_entries}
    with open('events.json', 'w') as f:
        json.dump(output, f, indent=4)

if __name__ == "__main__":
    scrape()
