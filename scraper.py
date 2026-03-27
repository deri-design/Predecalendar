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

def extract_message_text(m):
    """
    Extracts text from standard messages AND forwarded messages (snapshots).
    """
    full_text = m.get('content', '')

    # Check for Discord's newer "Forwarded" message format
    if 'message_snapshots' in m:
        for snapshot in m['message_snapshots']:
            snap_msg = snapshot.get('message', {})
            snap_content = snap_msg.get('content', '')
            if snap_content:
                full_text += f"\n[FORWARDED CONTENT]: {snap_content}"
    
    # Handle Embeds (often used in official announcements)
    if 'embeds' in m:
        for embed in m['embeds']:
            embed_text = f"{embed.get('title', '')} {embed.get('description', '')}"
            if embed_text.strip():
                full_text += f"\n[EMBED CONTENT]: {embed_text}"

    return full_text.strip()

def ask_groq(messages_text):
    client = Groq(api_key=GROQ_KEY)
    today = datetime.now().strftime("%A, %B %d, %Y")
    
    prompt = f"""
    Today's Date: {today}. 
    Context: Announcements for the game "Predecessor".
    
    Task: Extract planned events, patches, or releases.
    Rules:
    1. Identify the ACTUAL start date (YYYY-MM-DD). 
    2. If a message refers to "Forwarded Content", treat that as the source of truth.
    3. Output as a strict JSON list only.
    
    Messages:
    {messages_text}

    OUTPUT FORMAT:
    [
      {{"date": "YYYY-MM-DD", "title": "Name", "type": "patch/news", "url": "link", "image": "img_url"}}
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
    print("Fetching messages (including forwarded content)...")
    messages = get_discord_messages()
    if not messages:
        print("No messages found.")
        return

    combined = ""
    for m in messages:
        # We use our new extraction function here
        text = extract_message_text(m)
        if text:
            combined += f"SENT: {m['timestamp']} | MSG: {text}\n---\n"

    if not combined:
        print("No readable text found in the last 20 messages.")
        return

    print("Consulting Groq AI...")
    try:
        events = ask_groq(combined)
        output = {
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "events": events
        }
        with open('events.json', 'w') as f:
            json.dump(output, f, indent=4)
        print(f"SUCCESS: {len(events)} events extracted.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape()
