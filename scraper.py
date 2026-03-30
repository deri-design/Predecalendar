import os
import requests
import json
import re
from groq import Groq
from datetime import datetime

# Configuration
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GROQ_KEY = os.getenv("GROQ_API_KEY")
CHANNEL_ID = "1487129767865225261" 

def get_discord_messages():
    headers = {"Authorization": f"Bot {DISCORD_TOKEN}"}
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=25"
    res = requests.get(url, headers=headers)
    return res.json() if res.status_code == 200 else[]

def extract_image(m):
    """Deepest search specifically targeted at Discord attachments and embeds."""
    # 1. Standard attachments
    for a in m.get('attachments', []):
        if a.get('url'): return a['url']
    # 2. Standard embeds
    for e in m.get('embeds',[]):
        if 'image' in e and 'url' in e['image']: return e['image']['url']
        if 'thumbnail' in e and 'url' in e['thumbnail']: return e['thumbnail']['url']
    # 3. Forwarded Messages (Snapshots) -> Where Daybreak and Quests images live
    for snap in m.get('message_snapshots',[]):
        msg = snap.get('message', {})
        for a in msg.get('attachments',[]):
            if a.get('url'): return a['url']
        for e in msg.get('embeds', []):
            if 'image' in e and 'url' in e['image']: return e['image']['url']
            if 'thumbnail' in e and 'url' in e['thumbnail']: return e['thumbnail']['url']
    return ""

def clean_discord_text(text):
    text = re.sub(r'<@&?\d+>', '', text)
    text = text.replace('🔔', '')
    return re.sub(r'\n\s*\n', '\n', text).strip()

def extract_full_content(m):
    text = m.get('content', '')
    if 'message_snapshots' in m:
        for snap in m['message_snapshots']:
            msg = snap.get('message', {})
            text += f"\n{msg.get('content', '')}"
            for emb in msg.get('embeds',[]):
                text += f"\n{emb.get('title', '')}\n{emb.get('description', '')}"
    if 'embeds' in m:
        for emb in m['embeds']:
            text += f"\n{emb.get('title', '')}\n{emb.get('description', '')}"
    return text.strip()

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_KEY)
    today = datetime.now().strftime("%Y-%m-%d")
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    Create a specific event for EACH message provided. Do not combine them.
    Give each event a specific title (e.g. "Daybreak V4", "Quests", "V1.13 Patch").
    
    RULES: JSON list only. date: YYYY-MM-DD. title: short feature name. original_id: MUST MATCH the ID. type: patch/hero/season/twitch. iso_date: YYYY-MM-DDTHH:MM:SSZ.
    Messages: {messages_text}
    """
    chat = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.1
    )
    raw = chat.choices[0].message.content
    return json.loads(re.search(r'\[.*\]', raw, re.DOTALL).group(0))

def scrape():
    print("Starting Message-ID Sync...")
    messages = get_discord_messages()
    if not messages: return

    intel_pool = {}
    ai_input_list =[]
    for m in messages:
        text = extract_full_content(m)
        img = extract_image(m)
        if text:
            intel_pool[m['id']] = {
                "text": clean_discord_text(text),
                "img": img, 
                "url": f"https://discord.com/channels/1055546338907017278/{CHANNEL_ID}/{m['id']}"
            }
            ai_input_list.append(f"ID: {m['id']} | CONTENT: {text}")

    try:
        ai_events = ask_groq("\n---\n".join(ai_input_list))
        
        try:
            with open('events.json', 'r') as f:
                old_data = json.load(f)
                master_list = old_data.get('events', [])
        except: master_list =[]

        for ae in ai_events:
            mid = ae.get('original_id')
            if mid in intel_pool:
                full_text = intel_pool[mid]['text'].lower()
                etype = ae.get('type', 'news')
                if any(x in full_text for x in ["twitch", "stream"]): etype = "twitch"
                
                eurl = "https://www.twitch.tv/predecessorgame" if etype == "twitch" else intel_pool[mid]['url']
                iso = ae.get('iso_date', ae['date'] + ("T18:00:00Z" if etype == "twitch" else "T00:00:00Z"))

                new_obj = {
                    "original_id": mid, # KEY FIX: Track by ID to stop false duplicates
                    "date": ae['date'], "iso_date": iso, "title": ae['title'].upper(), "type": etype,
                    "desc": intel_pool[mid]['text'], "url": eurl, "image": intel_pool[mid]['img']
                }

                # Update if we already have this exact Discord message
                exists = next((i for i, x in enumerate(master_list) if x.get('original_id') == mid), -1)
                if exists > -1:
                    master_list[exists] = new_obj
                else:
                    master_list.append(new_obj)

        master_list =[e for e in master_list if e.get('desc') and e['date'] >= "2026-02-01"]

        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": master_list}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print("Success: Processed events with high-res image tracking.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
