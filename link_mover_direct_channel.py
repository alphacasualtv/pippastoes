import os
import re
import json
import time
import asyncio
import hikari
import logging
import random
from dotenv import load_dotenv
import aiohttp

# Load environment variables from .env file
load_dotenv()

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)

# Persistent storage for recent links
RECENT_LINKS_FILE = 'recent_links.json'
RECENT_LINKS_MAX_AGE = 72 * 3600  # 72 hours in seconds

# Load or initialize recent links
if os.path.exists(RECENT_LINKS_FILE):
    try:
        with open(RECENT_LINKS_FILE, 'r') as f:
            recent_links = json.load(f)
    except Exception:
        recent_links = {}
else:
    recent_links = {}

# Helper to save recent links
def save_recent_links():
    with open(RECENT_LINKS_FILE, 'w') as f:
        json.dump(recent_links, f)

# Cleanup old links
def cleanup_recent_links():
    now = time.time()
    to_delete = [link for link, v in recent_links.items() if now - v[0] > RECENT_LINKS_MAX_AGE]
    for link in to_delete:
        del recent_links[link]
    if to_delete:
        save_recent_links()

# Normalize links for duplicate detection
def normalize_link(link: str) -> str:
    return link.strip().lower()

# Set up logging with encoding handling
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/link_mover.log", encoding='utf-8')  # Updated log path
    ]
)
logger = logging.getLogger("LinkMover")

# ==== CONFIGURATION ====
# These values are now loaded from environment variables for security and flexibility
BOT_TOKEN = os.getenv("BOT_TOKEN")
try:
    SOURCE_CHANNEL_ID = int(os.getenv("SOURCE_CHANNEL_ID"))
    DESTINATION_CHANNEL_ID = int(os.getenv("DESTINATION_CHANNEL_ID"))
except (TypeError, ValueError):
    SOURCE_CHANNEL_ID = None
    DESTINATION_CHANNEL_ID = None

if not BOT_TOKEN or not SOURCE_CHANNEL_ID or not DESTINATION_CHANNEL_ID:
    logger.error("Missing required environment variables: BOT_TOKEN, SOURCE_CHANNEL_ID, DESTINATION_CHANNEL_ID")
    print("\nERROR: Please set BOT_TOKEN, SOURCE_CHANNEL_ID, and DESTINATION_CHANNEL_ID as environment variables.")
    exit(1)

# Media file extensions to ignore (case insensitive)
MEDIA_EXTENSIONS = {
    # Images
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.tiff',
    # Videos
    '.mp4', '.webm', '.mov', '.avi', '.mkv', '.flv', '.m4v', '.gifv'
}

# Video hosting domains that should embed directly
VIDEO_DOMAINS = {
    'gfycat.com',
    'streamable.com',
    'v.redd.it',
    'clips.twitch.tv',
    'medal.tv',
    'youtube.com/shorts',
    'tenor.com',
    'giphy.com',
    'imgur.com'  # when it ends in .mp4 or .gifv
}

# URL transformations for better embedding
URL_TRANSFORMATIONS = {
    'instagram.com': 'ddinstagram.com',
    'pixiv.net': 'phixiv.net',
    'tiktok.com': 'vxtiktok.com',
    'x.com': 'fxtwitter.com',
    'twitter.com': 'fxtwitter.com',  # Also handle twitter.com
    'youtube.com': 'youtu.be',
    'bsky.app': 'bskx.app'
}

# URL regex pattern to detect links in messages - enhanced to better catch nested links
URL_PATTERN = r'https?://(?:www\.)?([^/\s]+)([^\s<>"\']*)(?=[<>\s"\']|$)'

# Snarky comments
SNARKY_COMMENTS = [
    "maybe you should read things before you post.",
    "scroll up, genius.",
    "congrats, you just posted a rerun.",
    "reading is hard, huh?",
    "if only there was a way to see what's already been posted...",
    "deja vu? Or just not paying attention?",
    "this link is like your attention span: short and already used.",
    "I see you like recycling. Try it with your jokes, not your links.",
    "next time, try using your eyes.",
    "you must really like this link. It was here already.",
    "are you auditioning for the role of 'person who doesn't read chat'?",
    "I'd say 'nice find' but someone else found it first.",
    "originality called, it wants its link back.",
    "this link is so nice, you wanted to see it twice.",
    "pro tip: check chat history before posting.",
    "I'm starting to think you're a bot.",
    "at least pretend to read the chat.",
    "Ctrl+F is your friend.",
    "I've seen this one before. So has everyone else.",
    "if you keep this up, I'll start charging a repost fee.",
    "you're not the main character. The link was already posted.",
    "I'm not mad, just disappointed.",
    "you just invented time travel: back to when this was first posted.",
    "I hope you're better at other things than reading chat.",
    "maybe next time, try being first.",
    # 25 new snarky comments
    "You must think this link is a hidden gem. It's not.",
    "This link again? The suspense is killing no one.",
    "Reposting links won't make you popular.",
    "This link is like a rerun of a bad sitcom.",
    "If I had a nickel for every time this was posted...",
    "You just set a new record for déjà vu.",
    "This link is the boomerang of the chat.",
    "Did you mean to copy-paste that? Because you did.",
    "The link fairy has already visited.",
    "You just unlocked the 'Repost Achievement'.",
    "This link is like a zombie. It keeps coming back.",
    "You must really want us to see this. We already did.",
    "This link is the Groundhog Day of chat.",
    "If only there was a prize for reposting.",
    "This link is the sequel nobody asked for.",
    "You just summoned the ghost of links past.",
    "This link is like a boomerang. Please stop throwing it.",
    "You just made history repeat itself.",
    "This link is the echo of the chat.",
    "You just hit Ctrl+V a little too hard.",
    "This link is the chat's favorite déjà vu.",
    "You just made the chat do a double take.",
    "This link is the chat's recurring nightmare.",
    "You just pressed the replay button on this link.",
    "This link is the chat's broken record."
]

# Add a helper to detect short/mobile links that need expansion
SHORT_LINK_PATTERNS = [
    r"https?://(www\.)?reddit\.com/r/[^/]+/s/[A-Za-z0-9]+/?",  # Reddit mobile short (allow trailing slash)
    r"https?://(www\.)?redd\.it/[A-Za-z0-9]+/?",              # Reddit short
    r"https?://t\.co/[A-Za-z0-9]+/?",                         # Twitter short
    r"https?://youtu\.be/[A-Za-z0-9_-]+/?",                   # YouTube short
    r"https?://(www\.)?instagram\.com/s/[A-Za-z0-9]+/?",     # Instagram short
    r"https?://(www\.)?ig\.me/[A-Za-z0-9]+/?",               # Instagram short
]

def needs_expansion(url: str) -> bool:
    for pattern in SHORT_LINK_PATTERNS:
        if re.match(pattern, url):
            logger.info(f"[DEBUG] needs_expansion: {url} matches pattern {pattern}")
            return True
    logger.info(f"[DEBUG] needs_expansion: {url} does NOT match any short patterns")
    return False

async def expand_url(url: str) -> str:
    """Expand a short/mobile URL by following redirects. Returns the final URL or the original if expansion fails."""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(url, allow_redirects=True) as resp:
                return str(resp.url)
    except Exception as e:
        logger.warning(f"Failed to expand short URL {url}: {e}")
        return url

# Update transform_url to handle expanded Reddit /s/ links
async def transform_and_expand_url(url: str) -> str:
    logger.info(f"[DEBUG] Entering transform_and_expand_url for: {url}")
    logger.info(f"[DEBUG] Original URL: {url}")
    expanded_url = url
    if needs_expansion(url):
        expanded_url = await expand_url(url)
        logger.info(f"[DEBUG] Expanded URL: {expanded_url}")
    else:
        logger.info(f"[DEBUG] No expansion needed for: {url}")
    transformed = transform_url(expanded_url)
    logger.info(f"[DEBUG] Transformed URL: {transformed}")
    if transformed != expanded_url:
        logger.info(f"Transformed URL: {expanded_url} -> {transformed}")
    return transformed

# Patch process_nested_links to be async and use transform_and_expand_url
async def process_nested_links_async(content: str) -> str:
    async def replace_link_async(match):
        full_url = match.group(0)
        transformed = await transform_and_expand_url(full_url)
        return transformed if transformed else full_url
    # Find and transform all URLs in the content
    # Use re.finditer to get all matches, then replace them one by one
    matches = list(re.finditer(URL_PATTERN, content))
    if not matches:
        return content
    # Replace from the end to avoid messing up indices
    new_content = content
    offset = 0
    for match in matches:
        start, end = match.start() + offset, match.end() + offset
        full_url = match.group(0)
        transformed = await transform_and_expand_url(full_url)
        if transformed and transformed != full_url:
            new_content = new_content[:start] + transformed + new_content[end:]
            offset += len(transformed) - (end - start)
    return new_content

def is_media_url(url: str) -> bool:
    """Check if the URL is a direct link to media or a video platform that embeds well."""
    url_lower = url.lower()
    
    # Check for direct media file extensions
    if any(url_lower.endswith(ext) for ext in MEDIA_EXTENSIONS):
        logger.info(f"[DEBUG] is_media_url: {url} classified as media by extension")
        return True
    
    # Check for video hosting domains (excluding YouTube shorts)
    for domain in VIDEO_DOMAINS:
        if domain in url_lower and 'youtube.com/shorts' not in url_lower:
            logger.info(f"[DEBUG] is_media_url: {url} classified as media by domain {domain}")
            return True
            
    # Special checks for specific platforms
    if 'imgur.com' in url_lower and any(ext in url_lower for ext in ['.mp4', '.gifv']):
        logger.info(f"[DEBUG] is_media_url: {url} classified as media by imgur rule")
        return True
    
    # Remove YouTube shorts check since we want to transform these
    
    # Check for common video patterns
    video_patterns = [
        r'gfycat\.com/[a-zA-Z]+$',  # Gfycat links
        r'clips\.twitch\.tv/[a-zA-Z]+$',  # Twitch clips
        r'v\.redd\.it/[a-zA-Z0-9]+$',  # Reddit videos
        r'streamable\.com/[a-zA-Z0-9]+$',  # Streamable videos
        r'medal\.tv/clips/[a-zA-Z0-9]+',  # Medal clips
        r'tenor\.com/view/[a-zA-Z0-9-]+',  # Tenor GIFs
        r'giphy\.com/gifs/[a-zA-Z0-9-]+',  # Giphy GIFs
    ]
    
    return any(re.search(pattern, url_lower) for pattern in video_patterns)

def transform_url(url: str) -> str:
    """Transform URLs to their embedding-friendly versions."""
    # Don't transform media URLs
    if is_media_url(url):
        return None  # Return None to indicate this URL should be skipped

    match = re.match(URL_PATTERN, url)
    if not match:
        return url

    domain = match.group(1)
    path = match.group(2)
    logger.info(f"[DEBUG] transform_url: url={url}, domain={domain}, path={path}")

    # New: Transform all Reddit links to vxreddit.com for embedding
    if 'reddit.com' in domain.lower() or 'vxreddit.com' in domain.lower():
        # Always strip query string from the full URL for post links
        base_url = url.split('?')[0]
        # Re-parse to get the path after stripping query
        match_base = re.match(URL_PATTERN, base_url)
        if match_base:
            base_domain = match_base.group(1)
            base_path = match_base.group(2)
            logger.info(f"[DEBUG] transform_url (base): base_url={base_url}, base_domain={base_domain}, base_path={base_path}")
            if '/comments/' in base_path:
                logger.info(f"[DEBUG] Cleaned Reddit/vxreddit link: https://vxreddit.com{base_path}")
                return f'https://vxreddit.com{base_path}'
            return f'https://reddit.com{base_path}'
        # Fallback if re-parse fails
        return base_url

    # Special handling for Twitter/X domains
    if any(twitter_domain in domain for twitter_domain in ['twitter.com', 'x.com']):
        # Remove any www. prefix if present
        clean_domain = domain.replace('www.', '')
        # Replace either twitter.com or x.com with fxtwitter.com
        return f'https://fxtwitter.com{path}'

    # Check if this domain needs transformation
    for original, replacement in URL_TRANSFORMATIONS.items():
        if original in domain:
            # Special handling for YouTube
            if original == 'youtube.com':
                if 'watch?v=' in path:
                    video_id = re.search(r'watch\?v=([^&\s]+)', path)
                    if video_id:
                        return f'https://youtu.be/{video_id.group(1)}'
                elif '/shorts/' in path:
                    shorts_id = path.split('/shorts/')[1].split('?')[0]
                    return f'https://youtu.be/{shorts_id}'
                elif '/live/' in path:
                    live_id = path.split('/live/')[1].split('?')[0]
                    return f'https://youtu.be/{live_id}'
            # For all other transformations
            new_domain = domain.replace(original, replacement)
            return f'https://{new_domain}{path}'

    return url

logger.info("==== Configuration ====")
logger.info("Configuration loaded from environment variables.")
logger.info(f"SOURCE_CHANNEL_ID: {SOURCE_CHANNEL_ID}")
logger.info(f"DESTINATION_CHANNEL_ID: {DESTINATION_CHANNEL_ID}")

# Initialize the bot with proper intents
intents = hikari.Intents.GUILD_MESSAGES | hikari.Intents.MESSAGE_CONTENT
bot = hikari.GatewayBot(token=BOT_TOKEN, intents=intents)

def print_permissions_guide():
    """Print a guide for setting up bot permissions."""
    print("\n=== BOT PERMISSIONS GUIDE ===")
    print("The bot needs the following permissions in the DESTINATION channel:")
    print("1. View Channel")
    print("2. Send Messages")
    print("\nTo fix permissions:")
    print("1. Go to your Discord server settings")
    print("2. Click on 'Roles'")
    print("3. Find the bot's role")
    print("4. Make sure it has the above permissions")
    print("5. Check channel-specific permissions")
    print("\nOr use this quick fix:")
    print(f"1. Right-click the destination channel (ID: {DESTINATION_CHANNEL_ID})")
    print("2. Click 'Edit Channel'")
    print("3. Go to 'Permissions'")
    print("4. Click the '+' button")
    print("5. Add the bot's role")
    print("6. Enable 'View Channel' and 'Send Messages'")
    print("7. Click 'Save Changes'")
    print("\nAfter fixing permissions, restart the bot.")
    print("=====================================")

def extract_mentions(content: str) -> tuple[str, list[str]]:
    """Extract mentions from message content and return cleaned content and list of mentions."""
    # Discord mention pattern (both user and role mentions)
    mention_pattern = r'<@!?&?\d+>'
    mentions = re.findall(mention_pattern, content)
    
    # Remove mentions from content but preserve spacing
    cleaned_content = content
    for mention in mentions:
        cleaned_content = cleaned_content.replace(mention, '')
    
    # Clean up extra spaces
    cleaned_content = ' '.join(cleaned_content.split())
    
    return cleaned_content, mentions

# Create event listeners
@bot.listen()
async def on_ready(event: hikari.ShardReadyEvent) -> None:
    """Event fired when the bot is ready to process events."""
    logger.info("==== Bot Ready ====")
    logger.info(f"Logged in as {bot.get_me().username}")
    logger.info(f"Bot ID: {bot.get_me().id}")
    logger.info(f"Monitoring source channel: {SOURCE_CHANNEL_ID}")
    logger.info(f"Posting links to channel: {DESTINATION_CHANNEL_ID}")
    logger.info("URL transformations enabled for: " + ", ".join(URL_TRANSFORMATIONS.keys()))
    
    # Verify the destination channel exists and bot has permissions
    try:
        channel = await bot.rest.fetch_channel(DESTINATION_CHANNEL_ID)
        logger.info(f"Successfully found destination channel: #{channel.name}")
        
        # Try to send a test message
        test_message = await bot.rest.create_message(
            DESTINATION_CHANNEL_ID,
            "Bot startup test message - will be deleted"
        )
        await bot.rest.delete_message(DESTINATION_CHANNEL_ID, test_message)
        logger.info("Successfully verified bot permissions in destination channel")
        
    except hikari.ForbiddenError:
        logger.error("ERROR: Bot doesn't have permission to post in the destination channel!")
        print_permissions_guide()
    except Exception as e:
        logger.error(f"Error accessing destination channel: {e}")

@bot.listen()
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    # Only process messages from source or destination channel
    if event.is_bot or not event.content or event.channel_id not in {SOURCE_CHANNEL_ID, DESTINATION_CHANNEL_ID}:
        return

    author = event.author
    author_mention = f"<@{author.id}>" if author else "Unknown User"
    author_id = str(author.id) if author else None
    channel_mention = f"<#{event.channel_id}>"

    # Extract mentions and preserve formatting
    cleaned_content, mentions = extract_mentions(event.content)
    mention_str = " ".join([author_mention] + mentions) if mentions else author_mention

    # Find all URLs in the message
    matches = list(re.finditer(URL_PATTERN, event.content))
    full_urls = [match.group(0) for match in matches]
    if not full_urls:
        return

    cleanup_recent_links()
    now = time.time()

    # Classify links: reddit images/gifs, reddit videos, other links
    reddit_image_domains = ["i.redd.it", "preview.redd.it"]
    reddit_image_exts = [".jpg", ".jpeg", ".png", ".gif", ".webp"]
    reddit_gif_exts = [".gif", ".gifv"]
    reddit_video_domains = ["v.redd.it"]
    allowed_transform_domains = list(URL_TRANSFORMATIONS.keys())
    reddit_images = []
    reddit_gifs = []
    reddit_videos = []
    other_links = []
    # Build a mapping of original URL -> transformed URL for allowed links
    url_replacements = {}
    for url in full_urls:
        url_lower = url.lower()
        domain_match = re.match(URL_PATTERN, url)
        domain = domain_match.group(1) if domain_match else ""
        # Reddit image/gif
        if any(domain.endswith(d) for d in reddit_image_domains) and any(url_lower.endswith(ext) for ext in reddit_image_exts + reddit_gif_exts):
            if any(url_lower.endswith(ext) for ext in reddit_gif_exts):
                reddit_gifs.append(url)
            else:
                reddit_images.append(url)
        # Reddit video
        elif any(d in domain for d in reddit_video_domains):
            transformed = await transform_and_expand_url(url)
            if transformed and transformed != url:
                reddit_videos.append(transformed)
                url_replacements[url] = transformed
        # Allowed transformation domains
        elif any(allowed_domain in domain for allowed_domain in allowed_transform_domains):
            transformed = await transform_and_expand_url(url)
            if transformed and transformed != url:
                other_links.append(transformed)
                url_replacements[url] = transformed
        # Otherwise, skip (not allowed)
        else:
            continue
    # If no allowed links, ignore the message
    if not (reddit_images or reddit_gifs or reddit_videos or other_links):
        return

    # Replace allowed links in the original message with their transformed versions
    new_content = event.content
    for orig_url, transformed_url in url_replacements.items():
        new_content = new_content.replace(orig_url, transformed_url)

    # Extract mentions and preserve formatting
    cleaned_content, mentions = extract_mentions(new_content)
    mention_str = " ".join([author_mention] + mentions) if mentions else author_mention
    text_content = cleaned_content.strip()
    if text_content:
        final_message = f"{mention_str} {text_content}".strip()
    else:
        final_message = mention_str

    # Prepare embeds for images/gifs
    embeds = []
    for img_url in reddit_images:
        embeds.append(hikari.Embed().set_image(img_url))
    for gif_url in reddit_gifs:
        embeds.append(hikari.Embed().set_image(gif_url))
    # Discord allows up to 10 embeds per message
    embeds = embeds[:10]

    # Post the new message to the destination channel (if not already there)
    try:
        if event.channel_id == SOURCE_CHANNEL_ID:
            # Post the message and get the created message object
            created_message = await bot.rest.create_message(DESTINATION_CHANNEL_ID, final_message, embeds=embeds if embeds else None)
            logger.info(f"[DEBUG] Posted transformed message to destination: {final_message}")
            # Save recent links
            for check_url in url_replacements.values():
                norm_trans = normalize_link(check_url.rstrip('/'))
                recent_links[norm_trans] = [now, event.message_id, author_id]
            save_recent_links()
            # Delete the original message
            await bot.rest.delete_message(event.channel_id, event.message_id)
            logger.info(f"[DEBUG] Deleted original message after moving links.")

            # === VXREDDIT EMBED CHECK AND CORRECTION ===
            vxreddit_links = [url for url in reddit_videos if url.startswith('https://vxreddit.com')]
            if vxreddit_links:
                await asyncio.sleep(3)  # Wait for embed to load
                try:
                    msg = await bot.rest.fetch_message(DESTINATION_CHANNEL_ID, created_message.id)
                    failed = False
                    if msg.embeds:
                        for embed in msg.embeds:
                            if (embed.title and 'failed to get data from reddit' in embed.title.lower()) or \
                               (embed.description and 'failed to get data from reddit' in embed.description.lower()) or \
                               any('failed to get data from reddit' in (f.value or '').lower() for f in getattr(embed, 'fields', [])):
                                failed = True
                                break
                    if failed:
                        corrected_message = final_message.replace('vxreddit.com', 'rxddit.com')
                        await bot.rest.edit_message(DESTINATION_CHANNEL_ID, created_message.id, corrected_message)
                        logger.info(f"[DEBUG] Edited message to use rxddit.com due to vxreddit embed failure: {corrected_message}")
                except Exception as e:
                    logger.error(f"[VXREDDIT CHECK] Error during vxreddit embed check or correction: {e}")
        elif event.channel_id == DESTINATION_CHANNEL_ID:
            await bot.rest.delete_message(event.channel_id, event.message_id)
            await bot.rest.create_message(DESTINATION_CHANNEL_ID, final_message, embeds=embeds if embeds else None)
            logger.info(f"[DEBUG] Transformed and reposted message in destination channel: {final_message}")
            for check_url in url_replacements.values():
                norm_trans = normalize_link(check_url.rstrip('/'))
                recent_links[norm_trans] = [now, event.message_id, author_id]
            save_recent_links()
    except hikari.ForbiddenError:
        logger.error("Bot doesn't have permission to post or delete in the destination channel")
        print_permissions_guide()
    except Exception as e:
        logger.error(f"Error posting or deleting message: {e}")

def main():
    logger.info("Starting Discord Link Mover Bot (Direct Channel Version)...")
    logger.info("Connecting to Discord...")
    
    try:
        # Run the bot
        bot.run()
    except Exception as e:
        logger.error(f"Error running bot: {e}")
        print("\nPress Enter to exit...")
        input()

if __name__ == "__main__":
    main() 