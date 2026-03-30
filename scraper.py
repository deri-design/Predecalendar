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

def get_discord_image(m):
    """Directly grabs the first image attachment or embed from anywhere in the message."""
    # 1. Main message attachments
    if m.get('attachments'):
        return m['attachments'][0].get('url', '')
    
    # 2. Main message embeds
    for emb in m.get('embeds', []):
        if 'image' in emb: return emb['image'].get('url', '')
        if 'thumbnail' in emb: return emb['thumbnail'].get('url', '')
        
    # 3. Forwarded snapshots (This targets your Daybreak screenshot)
    if 'message_snapshots' in m:
        for snap in m['message_snapshots']:
            sm = snap.get('message', {})
            if sm.get('attachments'):
                return sm['attachments'][0].get('url', '')
            for emb in sm.get('embeds', []):
                if 'image' in emb: return emb['image'].get('url', '')
                if 'thumbnail' in emb: return emb['thumbnail'].get('url', '')
    return ""

def clean_discord_text(text):
    text = re.sub(r'<@&?\d+>', '', text)
    text = text.replace('🔔', '')
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

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
    Identify ACTUAL release/event dates and titles.
    
    CRITICAL RULE: Create EXACTLY ONE event per Discord message. 
    Do NOT split a message into multiple events (e.g. if a message mentions "V1.13", "Quests", and "Daybreak", combine them into ONE title like "V1.13: Throne of Thorns").
    
    Format: JSON list only. date: YYYY-MM-DD. title: short. original_id: match to ID. type: patch/hero/season/twitch.
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
    print("Starting Consolidated Scrape...")
    messages = get_discord_messages()
    if not messages: return

    intel_pool = {}
    ai_input_list =[]
    
    for m in messages:
        text = extract_full_content(m)
        img = get_discord_image(m) # New unbreakable image finder
        if text:
            intel_pool[m['id']] = {
                "text": clean_discord_text(text),
                "img": img, 
                "url": f"https://discord.com/channels/1055546338907017278/{CHANNEL_ID}/{m['id']}"
            }
            ai_input_list.append(f"ID: {m['id']} | CONTENT: {text}")

    try:
        ai_events = ask_groq("\n---\n".join(ai_input_list))
        
        # We use a dictionary to absolutely enforce 1 event per Message ID per Date
        unique_events = {}

        for ae in ai_events:
            mid = ae.get('original_id')
            if mid in intel_pool:
                etype = ae['type']
                eurl = intel_pool[mid]['url']
                full_text = intel_pool[mid]['text'].lower()
                
                if any(x in full_text for x in["twitch", "stream"]):
                    etype, eurl = "twitch", "https://www.twitch.tv/predecessorgame"
                
                iso = ae.get('iso_date', ae['date'] + ("T18:00:00Z" if etype == "twitch" else "T00:00:00Z"))

                event_obj = {
                    "date": ae['date'], "iso_date": iso, "title": ae['title'].upper(), "type": etype,
                    "desc": intel_pool[mid]['text'], "url": eurl, "image": intel_pool[mid]['img']
                }

                # Force Single Card per Message Logic
                key = f"{ae['date']}_{mid}"
                if key not in unique_events:
                    unique_events[key] = event_obj
                else:
                    # If AI still tried to make two cards for one message, keep the one with the longer title
                    if len(event_obj['title']) > len(unique_events[key]['title']):
                        unique_events[key] = event_obj

        final_list = sorted(list(unique_events.values()), key=lambda x: x['date'])

        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": final_list}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"Success: {len(final_list)} clean, unique events saved.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
