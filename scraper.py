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
    url = f"https://discord.com/api/v10/channels/{CHANNEL_ID}/messages?limit=20"
    res = requests.get(url, headers=headers)
    return res.json() if res.status_code == 200 else []

def extract_intel(m):
    """Gathers text and images from any message type (Standard, Forwarded, or Embed)."""
    text = m.get('content', '')
    img = ""
    
    def find_img(msg_obj):
        for att in msg_obj.get('attachments', []):
            if any(ext in att.get('url', '').lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                return att.get('url')
        for emb in msg_obj.get('embeds', []):
            if 'image' in emb: return emb['image'].get('url')
            if 'thumbnail' in emb: return emb['thumbnail'].get('url')
        return ""

    img = find_img(m)

    if 'message_snapshots' in m:
        for snapshot in m['message_snapshots']:
            snap_msg = snapshot.get('message', {})
            text += f"\n[FORWARDED]: {snap_msg.get('content', '')}"
            if not img: img = find_img(snap_msg)
            for emb in snap_msg.get('embeds', []):
                text += f"\n[EMBED INFO]: {emb.get('title', '')} {emb.get('description', '')}"

    if 'embeds' in m:
        for emb in m['embeds']:
            text += f"\n[EMBED INFO]: {emb.get('title', '')} {emb.get('description', '')}"

    return text.strip(), img

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_KEY)
    today = datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""
    Today's Date: {today}. 
    You are a high-level Tactical Intelligence AI for the game "Predecessor".
    
    TASK: Extract all upcoming events from the provided Discord logs.
    
    RULES:
    1. Output a JSON list ONLY.
    2. "date": Extract the actual date the event/patch starts (YYYY-MM-DD).
    3. "title": Short, high-impact title.
    4. "desc": Provide a 2-3 sentence 'Tactical Briefing'. Mention EVERY specific feature or change (e.g., Level caps, new heroes, specific rewards).
    5. "type": "patch" if it has a version number (V1.xx), otherwise "news".
    
    Messages to analyze:
    {messages_text}

    OUTPUT FORMAT:
    [
      {{"date": "YYYY-MM-DD", "title": "Name", "desc": "Summary...", "type": "patch/news", "url": "link", "image": "img_url"}}
    ]
    """
    
    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.3-70b-versatile",
        temperature=0.1
    )
    
    raw_text = chat_completion.choices[0].message.content
    json_match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    return json.loads(json_match.group(0)) if json_match else []

def scrape():
    messages = get_discord_messages()
    if not messages: return

    combined_intel = []
    for m in messages:
        text, img = extract_intel(m)
        if text:
            combined_intel.append({
                "timestamp": m['timestamp'],
                "text": text,
                "img": img,
                "url": f"https://discord.com/channels/1055546338907017278/{CHANNEL_ID}/{m['id']}"
            })

    ai_input = "\n---\n".join([f"SENT: {i['timestamp']} | CONTENT: {i['text']}" for i in combined_intel])

    try:
        events = ask_groq(ai_input)
        
        # Link the images found by the scraper to the AI's categorized events
        for event in events:
            for i in combined_intel:
                # If the AI title is mentioned in the original text, use that message's image
                if not event.get('image') and event['title'].lower()[:10] in i['text'].lower():
                    event['image'] = i['img']
                if not event.get('url'):
                    event['url'] = i['url']

        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": events}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"SUCCESS: Roadmaps updated for all upcoming operations.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
