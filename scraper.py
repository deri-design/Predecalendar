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

def clean_discord_text(text):
    text = re.sub(r'<@&?\d+>', '', text)
    text = text.replace('🔔', '')
    text = re.sub(r'\n\s*\n', '\n', text)
    return text.strip()

def extract_external_link(m):
    """Finds YouTube, playp.red, or website links. Prioritizes non-Discord links."""
    text = m.get('content', '')
    # Check regular content
    urls = re.findall(r'(https?://[^\s]+)', text)
    # Check embeds
    for emb in m.get('embeds', []):
        if emb.get('url'): urls.append(emb['url'])
    # Check snapshots
    for snap in m.get('message_snapshots', []):
        msg = snap.get('message', {})
        urls.extend(re.findall(r'(https?://[^\s]+)', msg.get('content', '')))
        for emb in msg.get('embeds', []):
            if emb.get('url'): urls.append(emb['url'])
            
    for url in urls:
        url = url.rstrip('.,!?"\')')
        if 'discord.com/channels' not in url and not any(url.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
            return url
    return "https://www.predecessorgame.com/en-US/news"

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
    client = Groq(api_key=GROQ_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    prompt = f"""
    Today is {today}. Context: "Predecessor" game announcements.
    TASK: Identify release dates for patches, hero reveals, or community events.
    
    RULES:
    1. Only return events where a SPECIFIC DATE is mentioned in the text.
    2. Extract a short title (max 20 chars).
    3. Output JSON list ONLY.
    4. "original_id": Match to the ID provided.
    
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
    print("Starting 1:1 Discord News Sync...")
    messages = get_discord_messages()
    if not messages: return

    intel_pool = {}
    ai_input_list = []
    for m in messages:
        text = extract_full_content(m)
        img = find_deep_img(m)
        ext_url = extract_external_link(m)
        if text:
            intel_pool[m['id']] = {
                "text": clean_discord_text(text),
                "img": img, 
                "url": ext_url
            }
            ai_input_list.append(f"ID: {m['id']} | CONTENT: {text}")

    try:
        ai_events = ask_groq("\n---\n".join(ai_input_list))
        
        # We now keep events strictly mapped 1:1 to Message IDs
        # No more title-based deduplication
        final_events = []
        for ae in ai_events:
            mid = ae.get('original_id')
            if mid in intel_pool:
                full_text = intel_pool[mid]['text'].lower()
                etype = ae.get('type', 'news')
                if any(x in full_text for x in ["twitch", "stream"]): etype = "twitch"
                
                eurl = intel_pool[mid]['url']
                if etype == "twitch": eurl = "https://www.twitch.tv/predecessorgame"
                
                iso = ae.get('iso_date', ae['date'] + ("T18:00:00Z" if etype == "twitch" else "T00:00:00Z"))

                final_events.append({
                    "date": ae['date'], "iso_date": iso, "title": ae['title'].upper(), "type": etype,
                    "desc": intel_pool[mid]['text'], "url": eurl, "image": intel_pool[mid]['img']
                })

        output = {"last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "events": final_events}
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"Success: {len(final_events)} unique Discord messages mapped.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
