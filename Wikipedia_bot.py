import asyncio
import logging
import os
from threading import Thread
from typing import Dict, Optional

import requests
from flask import Flask
from deep_translator import GoogleTranslator
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# Render Port Binding ke liye Flask Server
app = Flask('')

@app.route('/')
def home():
    return "Hinglish Wiki Bot is active!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# Logging Setup
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

# Environment Variable
BOT_TOKEN = os.environ.get("BOT_TOKEN")
HEADERS = {"User-Agent": "TelegramHinglishWikipediaBot/3.0 (personal project)"}

MAX_MESSAGE_LENGTH = 3800
active_tasks: Dict[int, asyncio.Task] = {}

# Common Footer
DEV_FOOTER = "\n\n 𝙳𝚎𝚟𝚕𝚘𝚙 𝚋𝚢 @𝚙𝚞𝚜𝚙𝚊𝚊𝚊𝚖𝚖 ❤️"

import re  # Is line ko bilkul top par imports me add kar lein

def clean_wiki_text(text: str) -> str:
    if not text:
        return ""

    # Faltu Sections (References, External Links) ko hatane ke liye
    unwanted = [
        "== सन्दर्भ ==", "== संदर्भ ==", "== इन्हें भी देखें ==", 
        "== टिप्पणी सूची ==", "== बाहरी कड़ियाँ ==", "== References =="
    ]
    for sec in unwanted:
        if sec in text:
            text = text.split(sec)[0]

    # '=== Heading ===' ko '★ Heading' me badalna
    text = re.sub(r'={2,}\s*(.*?)\s*={2,}', r'\n\n★ **\1**\n', text)
    return text.strip()


def convert_to_hindi(query: str) -> str:
    """Hinglish / English query ko Hindi (Devanagari) me convert/translate karta hai."""
    try:
        translated = GoogleTranslator(source='auto', target='hi').translate(query)
        return translated if translated else query
    except Exception:
        return query


def fetch_wiki_data_hindi(query: str):
    """Hindi Wikipedia API se article fetch karna."""
    # 1. Direct query search
    search_url = f"https://hi.wikipedia.org/w/api.php?action=query&list=search&srsearch={query}&srlimit=1&format=json"
    res = requests.get(search_url, headers=HEADERS, timeout=10).json()
    results = res.get("query", {}).get("search", [])

    # 2. Agar direct result na मिले, toh Hinglish ko Hindi me translate karke search karein
    if not results:
        hindi_query = convert_to_hindi(query)
        search_url = f"https://hi.wikipedia.org/w/api.php?action=query&list=search&srsearch={hindi_query}&srlimit=1&format=json"
        res = requests.get(search_url, headers=HEADERS, timeout=10).json()
        results = res.get("query", {}).get("search", [])

    if not results:
        return None

    title = results[0]["title"]
    title_encoded = title.replace(" ", "_")

    # 3. Plain Text Extract
    extract_url = f"https://hi.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&titles={title}&format=json"
    ext_res = requests.get(extract_url, headers=HEADERS, timeout=15).json()
    pages = ext_res.get("query", {}).get("pages", {})
    extract_text = ""
    for p_id, p in pages.items():
        extract_text = p.get("extract", "")
        # Extract text ko clean karein
    extract_text = clean_wiki_text(extract_text)


    # 4. Lead Image
    summary_url = f"https://hi.wikipedia.org/api/rest_v1/page/summary/{title_encoded}"
    sum_res = requests.get(summary_url, headers=HEADERS, timeout=10)
    lead_image = None
    description = ""
    if sum_res.status_code == 200:
        data = sum_res.json()
        lead_image = data.get("originalimage", {}).get("source") or data.get("thumbnail", {}).get("source")
        description = data.get("description", "")

    # 5. Media Images & Diagrams
    media_url = f"https://hi.wikipedia.org/api/rest_v1/page/media-list/{title_encoded}"
    med_res = requests.get(media_url, headers=HEADERS, timeout=10)
    extra_images = []
    if med_res.status_code == 200:
        items = med_res.json().get("items", [])
        for item in items:
            if item.get("type") == "image":
                src = item.get("srcset", [{}])[0].get("src") or item.get("showInGallery")
                title_caption = item.get("caption", {}).get("text", "चित्र / आरेख")
                if src and not src.endswith(".svg") and not any(x in src.lower() for x in ["logo", "icon", "symbol", "padlock"]):
                    if src.startswith("//"):
                        src = "https:" + src
                    extra_images.append((src, title_caption))

    return {
        "title": title,
        "description": description,
        "extract": extract_text,
        "lead_image": lead_image,
        "images": extra_images[:5],
        "url": f"https://hi.wikipedia.org/wiki/{title_encoded}"
    }


def split_text(text: str, max_length: int = MAX_MESSAGE_LENGTH):
    """Text ko paragraphs ke basis par clean division dena."""
    chunks = []
    while len(text) > max_length:
        split_at = text.rfind('\n', 0, max_length)
        if split_at == -1:
            split_at = text.rfind(' ', 0, max_length)
        if split_at == -1:
            split_at = max_length

        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()

    if text:
        chunks.append(text)
    return chunks


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    welcome_text = (
        " **𝚆𝚎𝚕𝚌𝚘𝚖𝚎 𝚝𝚘 @𝙷𝚒𝚠𝚒𝚔𝚒𝚋𝚘𝚝.𝚃𝚈𝙿𝙴 𝚈𝙾𝚄𝚁 𝚃𝙾𝙿𝙸𝙲** \n"
    © 𝙳𝙴𝚅𝙻𝙾𝙿 𝙱𝚈 𝚝.𝚖𝚎/@𝚙𝚞𝚜𝚙𝚊𝚊𝚊𝚖𝚖 ❤️ )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = (update.message.text or "").strip()
    if not query:
        return

    chat_id = update.effective_chat.id
    previous = active_tasks.get(chat_id)
    if previous and not previous.done():
        previous.cancel()

    active_tasks[chat_id] = asyncio.create_task(process_search(update, query))


async def process_search(update: Update, query: str) -> None:
    try:
        await update.effective_chat.send_action("typing")
        
        data = await asyncio.to_thread(fetch_wiki_data_hindi, query)
        if not data or not data["extract"]:
            await update.message.reply_text(f'❌ "{query}" unavilable ')
            return

        title = data["title"]
        desc = f"_\n▸ {data['description']}_" if data['description'] else ""

        # Step 1: Main Photo & Title Alignment
        header_text = f"📖 **{title.upper()}**{desc}\n●----------------●"

        if data["lead_image"]:
            try:
                await update.message.reply_photo(
                    photo=data["lead_image"], 
                    caption=header_text, 
                    parse_mode="Markdown"
                )
            except Exception:
                await update.message.reply_text(header_text, parse_mode="Markdown")
        else:
            await update.message.reply_text(header_text, parse_mode="Markdown")

        # Step 2: Article Text Chunking
        chunks = split_text(data["extract"])
        for chunk in chunks:
            # Clean Quote-Block Alignment for text
            formatted_chunk = f"```text\n{chunk}\n```" if len(chunk) < 200 else chunk
            await update.message.reply_text(chunk)
            await asyncio.sleep(0.3)

        # Step 3: Extra Images & Diagrams
        if data["images"]:
            await update.message.reply_text(" **RELATED DIAGRAMS & IMAGES:**\n━━━━━━━━━━", parse_mode="Markdown")
            for img_url, caption in data["images"]:
                try:
                    await update.message.reply_photo(photo=img_url, caption=f"📷 _{caption[:100]}_", parse_mode="Markdown")
                    await asyncio.sleep(0.4)
                except Exception:
                    continue

        # Step 4: Footer & Web Link
        footer_text = f"━━━━━━━━━━\n🔗 **[Click Here to Read Full Article on Wikipedia]({data['url']})**" + DEV_FOOTER
        await update.message.reply_text(footer_text, parse_mode="Markdown")

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Sorry")


def main() -> None:
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN is missing in Environment Variables!")

    app_bot = Application.builder().token(BOT_TOKEN).build()
    app_bot.add_handler(CommandHandler("start", start))
    app_bot.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Wiki Bot with Clean Alignment is running...")
    app_bot.run_polling()


if __name__ == "__main__":
    Thread(target=run_flask, daemon=True).start()
    main()

