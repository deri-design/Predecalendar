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

def extract_full_content(m):
    text = m.get('content', '')
    if 'message_snapshots' in m:
        for snap in m['message_snapshots']:
            msg = snap.get('message', {})
            text += f"\n{msg.get('content', '')}"
            for emb in msg.get('embeds', []):
                text += f"\n{emb.get('title', '')}\n{emb.get('description', '')}"
    if 'embeds' in m:
        for emb in m['embeds']:
            text += f"\n{emb.get('title', '')}\n{emb.get('description', '')}"
    return text.strip()

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_API_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    TASK: Process Discord messages into structured data.
    
    RULES:
    1. Identify a SPECIFIC START DATE if mentioned in text (YYYY-MM-DD).
    2. Identify a VERSION NUMBER if mentioned (e.g., "V1.13").
    3. Extract a short, punchy TITLE.
    4. Return ONLY a JSON list of objects.
    
    Messages: {messages_text}
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

    # Load existing database for Persistence Rule and Version Sync
    try:
        with open('events.json', 'r') as f:
            db_data = json.load(f)
            master_list = db_data.get('events', [])
    except:
        master_list = []

    existing_ids = [str(e.get('original_id')) for e in master_list]
    
    intel_pool = {}
    ai_input_list = []
    for m in messages:
        # Rule: Card Creation per post
        # Rule: Persistence - skip if already in DB
        if str(m['id']) in existing_ids:
            continue

        content = extract_full_content(m)
        img = find_deep_img(m)
        if content:
            intel_pool[m['id']] = {
                "raw_text": content,
                "clean_text": re.sub(r'<@&?\d+>', '', content).replace('🔔', '').strip(),
                "img": img,
                "posted": m['timestamp'][:10]
            }
            ai_input_list.append(f"ID: {m['id']} | CONTENT: {content}")

    if not ai_input_list:
        print("No new posts to process.")
        return

    try:
        ai_results = ask_groq("\n---\n".join(ai_input_list))
        
        for ar in ai_results:
            mid = ar.get('original_id')
            if mid not in intel_pool: continue
            
            intel = intel_pool[mid]
            full_text = intel['raw_text']
            
            # --- DATE DETERMINATION HIERARCHY ---
            event_date = ar.get('date') # 1. Direct Mention
            
            # 2. Version Sync
            version = ar.get('version')
            if (not event_date or event_date == "None") and version:
                for old in master_list:
                    if version in old['title'] or version in old['desc']:
                        event_date = old['date']
                        break
            
            # 3. Creation Date Fallback
            if not event_date or event_date == "None":
                event_date = intel['posted']

            # --- CATEGORY & LINK ASSIGNMENT ---
            etype = "patch" # Default
            eurl = "https://www.predecessorgame.com/en-US/news" # Default fallback
            
            # Link check for YouTube
            yt_match = re.search(r'(https?://(?:www\.)?(?:youtube\.com|youtu\.be)/[^\s]+)', full_text)
            
            # 1.0 Twitch Priority
            if any(x in full_text.lower() for x in ["twitch", "live stream"]):
                etype = "twitch"
                eurl = "https://www.twitch.tv/predecessorgame"
            # 2.0 YouTube Secondary
            elif yt_match:
                etype = "youtube"
                eurl = yt_match.group(0).rstrip('.,!?"\')')
            
            # 3.0 Special Link Handling (playp.red priority)
            pp_match = re.search(r'(https://playp\.red/[^\s]+)', full_text)
            if pp_match:
                eurl = pp_match.group(0).rstrip('.,!?"\')')

            master_list.append({
                "original_id": mid,
                "date": event_date,
                "iso_date": event_date + ("T18:00:00Z" if etype == "twitch" else "T15:00:00Z"),
                "title": ar.get('title', 'UPDATE').upper(),
                "type": etype,
                "desc": intel['clean_text'],
                "image": intel['img'],
                "url": eurl
            })

        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": master_list}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print("Scrape successful. Persistence and Hierarchies enforced.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
