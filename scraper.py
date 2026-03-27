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
    if res.status_code != 200:
        print(f"DISCORD ERROR: {res.status_code}")
        return []
    return res.json()

def extract_intel(m):
    """Gathers all text and the best image from standard and forwarded messages."""
    text = m.get('content', '')
    img = ""
    
    # Helper to find image in a message object
    def find_img(msg_obj):
        # 1. Check Attachments
        for att in msg_obj.get('attachments', []):
            if any(ext in att.get('url', '').lower() for ext in ['.png', '.jpg', '.jpeg', '.webp']):
                return att.get('url')
        # 2. Check Embeds
        for emb in msg_obj.get('embeds', []):
            if 'image' in emb: return emb['image'].get('url')
            if 'thumbnail' in emb: return emb['thumbnail'].get('url')
        return ""

    img = find_img(m)

    # Handle Forwarded Snapshots
    if 'message_snapshots' in m:
        for snapshot in m['message_snapshots']:
            snap_msg = snapshot.get('message', {})
            snap_content = snap_msg.get('content', '')
            if snap_content: text += f"\n[INTEL]: {snap_content}"
            if not img: img = find_img(snap_msg)
            # Check forwarded embeds
            for emb in snap_msg.get('embeds', []):
                text += f"\n[INTEL]: {emb.get('title', '')} {emb.get('description', '')}"

    # Handle Regular Embeds
    if 'embeds' in m:
        for emb in m['embeds']:
            text += f"\n[INTEL]: {emb.get('title', '')} {emb.get('description', '')}"

    return text.strip(), img

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_KEY)
    today = datetime.now().strftime("%Y-%m-%d")
    
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    TASK: Build a roadmap database from these messages.
    
    RULES:
    1. Output JSON list ONLY.
    2. "date": Use the actual release/event date mentioned (YYYY-MM-DD).
    3. "title": Short name (e.g. "V1.13: Throne of Thorns").
    4. "desc": Detailed summary. Include all specific news mentioned (like Level Cap increases, hero names, etc).
    5. "type": "patch" if it's a version update, else "news".
    
    Messages:
    {messages_text}

    OUTPUT FORMAT:
    [
      {{"date": "YYYY-MM-DD", "title": "Name", "desc": "Detailed intel...", "type": "patch/news", "url": "link", "image": "img_url"}}
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
                "msg_id": m['id']
            })

    # Prepare for AI
    ai_input = "\n---\n".join([f"SENT: {i['timestamp']} | CONTENT: {i['text']}" for i in combined_intel])

    try:
        events = ask_groq(ai_input)
        
        # Attach the images we found manually to the AI results if AI missed them
        for event in events:
            if not event.get('image'):
                # Try to find a matching image from our intel list
                for i in combined_intel:
                    if event['title'].lower() in i['text'].lower() and i['img']:
                        event['image'] = i['img']
                        break
            if not event.get('url'):
                event['url'] = f"https://discord.com/channels/1055546338907017278/{CHANNEL_ID}"

        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": events}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"SUCCESS: Synced {len(events)} detailed events.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
