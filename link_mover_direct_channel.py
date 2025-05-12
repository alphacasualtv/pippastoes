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
import urllib.parse

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
# Allowed platforms for transformation and posting
ALLOWED_DOMAINS = [
    'youtube.com', 'youtu.be',
    'twitter.com', 'x.com', 'fxtwitter.com',
    'reddit.com', 'redd.it', 'vxreddit.com',
    'instagram.com', 'ddinstagram.com',
    'tiktok.com', 'vxtiktok.com',
]

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

def is_subdomain_or_exact(netloc, domain):
    netloc_parts = netloc.split('.')
    domain_parts = domain.split('.')
    return netloc_parts[-len(domain_parts):] == domain_parts

def is_allowed_domain(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    for allowed in ALLOWED_DOMAINS:
        allowed = allowed.lower()
        netloc_parts = netloc.split('.')
        allowed_parts = allowed.split('.')
        if len(netloc_parts) >= len(allowed_parts) and netloc_parts[-len(allowed_parts):] == allowed_parts:
            logger.debug(f"[is_allowed_domain] ALLOWED: {netloc} matches {allowed}")
            return True
    logger.debug(f"[is_allowed_domain] NOT ALLOWED: {netloc}")
    return False

# Only transform URLs for allowed domains
def transform_url(url: str) -> str:
    if not is_allowed_domain(url):
        return None  # Not allowed, skip
    # Don't transform media URLs
    if is_media_url(url):
        return None
    match = re.match(URL_PATTERN, url)
    if not match:
        return url
    domain = match.group(1)
    path = match.group(2)
    logger.info(f"[DEBUG] transform_url: url={url}, domain={domain}, path={path}")
    parsed = urllib.parse.urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    # Reddit
    if netloc.endswith("reddit.com") or netloc.endswith("vxreddit.com") or netloc.endswith("redd.it"):
        base_url = url.split('?')[0]
        match_base = re.match(URL_PATTERN, base_url)
        if match_base:
            base_path = match_base.group(2)
            logger.info(f"[DEBUG] transform_url (base): base_url={base_url}, base_path={base_path}")
            if '/comments/' in base_path:
                logger.info(f"[DEBUG] Cleaned Reddit/vxreddit link: https://vxreddit.com{base_path}")
                return f'https://vxreddit.com{base_path}'
            return f'https://reddit.com{base_path}'
        return base_url
    # Twitter/X
    if netloc.endswith('twitter.com') or netloc.endswith('x.com') or netloc.endswith('fxtwitter.com'):
        return f'https://fxtwitter.com{path}'
    # YouTube
    if netloc.endswith('youtube.com') or netloc.endswith('youtu.be'):
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
    # Instagram
    if netloc.endswith('instagram.com') or netloc.endswith('ddinstagram.com'):
        return url.replace('instagram.com', 'ddinstagram.com')
    # TikTok
    if netloc.endswith('tiktok.com') or netloc.endswith('vxtiktok.com'):
        return url.replace('tiktok.com', 'vxtiktok.com')
    return url

# Patch process_nested_links_async to only process the first allowed link
async def process_first_allowed_link(content: str) -> str:
    matches = list(re.finditer(URL_PATTERN, content))
    for match in matches:
        full_url = match.group(0)
        if is_allowed_domain(full_url):
            transformed = await transform_and_expand_url(full_url)
            if transformed:
                return transformed
    return None

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
    # Only process the first allowed link, unless a second is Redgifs
    matches = list(re.finditer(URL_PATTERN, event.content))
    allowed_links = []
    redgifs_link = None
    for match in matches:
        url = match.group(0)
        if is_allowed_domain(url):
            if not allowed_links:
                allowed_links.append(url)
            elif not redgifs_link and "redgifs.com" in url:
                redgifs_link = url
                break  # Only process one Redgifs as second link
    if not allowed_links:
        return  # Ignore messages with no allowed links
    # Extract user text (excluding the reposted link(s)) and preserve mentions
    content_wo_links = event.content
    for link in allowed_links:
        content_wo_links = content_wo_links.replace(link, "")
    if redgifs_link:
        content_wo_links = content_wo_links.replace(redgifs_link, "")
    cleaned_content, mentions = extract_mentions(content_wo_links)
    user_text = cleaned_content.strip()
    if mentions:
        user_text = (user_text + " " + " ".join(mentions)).strip()
    # Compose repost message base
    repost_prefix = f"{author_mention} "
    if user_text:
        repost_prefix += user_text + "\n"
    first_allowed_link = allowed_links[0]
    parsed = urllib.parse.urlparse(first_allowed_link)
    netloc = parsed.netloc.lower()
    if netloc.startswith('www.'):
        netloc = netloc[4:]
    is_reddit = netloc.endswith('reddit.com') or netloc.endswith('redd.it') or netloc.endswith('vxreddit.com') or netloc.endswith('rxddit.com')
    norm_trans = None
    now = time.time()
    try:
        if is_reddit:
            # Always use vxreddit/rxreddit for repost
            if 'redd.it' in netloc:
                first_allowed_link = await expand_reddit_shortlink(first_allowed_link)
            post_url = normalize_reddit_post_url(first_allowed_link)
            vx_url = post_url.replace('reddit.com', 'vxreddit.com').replace('www.reddit.com', 'vxreddit.com')
            await bot.rest.create_message(DESTINATION_CHANNEL_ID, f"{repost_prefix}{vx_url}")
            norm_trans = normalize_link(vx_url.rstrip('/'))
        else:
            transformed_link = transform_url(first_allowed_link)
            if not transformed_link:
                transformed_link = first_allowed_link
            await bot.rest.create_message(DESTINATION_CHANNEL_ID, f"{repost_prefix}{transformed_link}")
            norm_trans = normalize_link(transformed_link.rstrip('/'))
        # Handle Redgifs as a second allowed link
        if redgifs_link:
            direct_mp4 = await get_redgifs_mp4(redgifs_link)
            msg = f"{repost_prefix}{direct_mp4 if direct_mp4 else redgifs_link}"
            await bot.rest.create_message(DESTINATION_CHANNEL_ID, msg)
        # Save recent link
        if norm_trans:
            recent_links[norm_trans] = [now, event.message_id, author_id]
            save_recent_links()
        await bot.rest.delete_message(event.channel_id, event.message_id)
    except hikari.ForbiddenError:
        logger.error("Bot doesn't have permission to post or delete in the destination channel")
        print_permissions_guide()
    except Exception as e:
        logger.error(f"Error posting or deleting message: {e}")

# --- REDDIT LINK HELPERS ---

REDDIT_COMMENT_REGEX = re.compile(r"(https?://(?:www\.)?reddit\.com/r/[^/]+/comments/[^/]+)(?:/[^/]+)?(?:/([a-z0-9]+))?(?:/)?(?:\?[^#]*)?(?:#.*)?", re.IGNORECASE)
REDDIT_SHORTLINK_REGEX = re.compile(r"https?://(www\.)?redd\.it/([a-zA-Z0-9]+)")

async def expand_reddit_shortlink(url: str) -> str:
    """Expand redd.it shortlinks to full Reddit URLs."""
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.head(url, allow_redirects=True) as resp:
                return str(resp.url)
    except Exception as e:
        logger.warning(f"Failed to expand Reddit shortlink {url}: {e}")
        return url

def normalize_reddit_post_url(url: str) -> str:
    """If the URL is a Reddit comment link, strip to the post URL."""
    match = REDDIT_COMMENT_REGEX.match(url)
    if match:
        return match.group(1)  # Only the post, no comment or extra path
    return url

async def fetch_reddit_post_metadata(post_url: str) -> dict:
    """Fetch Reddit post JSON and return info about type (image, gallery, video, etc)."""
    # Ensure .json at the end
    if not post_url.endswith('.json'):
        if post_url.endswith('/'):
            json_url = post_url + '.json'
        else:
            json_url = post_url + '/.json'
    else:
        json_url = post_url
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(json_url, headers={"User-Agent": "discord-link-mover-bot/1.0"}) as resp:
                if resp.status != 200:
                    logger.warning(f"Reddit metadata fetch failed: {json_url} status {resp.status}")
                    return {"type": "unknown"}
                data = await resp.json()
                post = data[0]["data"]["children"][0]["data"]
                # Detect type
                if post.get("is_gallery"):
                    # Gallery: collect all image URLs
                    items = post.get("gallery_data", {}).get("items", [])
                    media_metadata = post.get("media_metadata", {})
                    images = []
                    for item in items:
                        media_id = item["media_id"]
                        meta = media_metadata.get(media_id, {})
                        if meta.get("status") == "valid":
                            # Get best available image
                            if "s" in meta:
                                images.append(meta["s"].get("u"))
                    return {"type": "gallery", "images": images}
                elif post.get("post_hint") == "image" and post.get("url"):
                    return {"type": "image", "images": [post["url"]]}
                elif post.get("is_video") or post.get("post_hint") == "hosted:video":
                    video_url = post.get("media", {}).get("reddit_video", {}).get("fallback_url")
                    # Special: check for redgifs.com in media/fallback URL
                    if not video_url and post.get("url") and "redgifs.com" in post.get("url"):
                        video_url = post.get("url")
                    if video_url and "redgifs.com" in video_url:
                        return {"type": "redgifs", "redgifs_url": video_url}
                    return {"type": "video", "video_url": video_url}
                else:
                    # Check for redgifs in url for other types
                    if post.get("url") and "redgifs.com" in post.get("url"):
                        return {"type": "redgifs", "redgifs_url": post.get("url")}
                    return {"type": "other"}
    except Exception as e:
        logger.warning(f"Error fetching Reddit metadata for {post_url}: {e}")
        return {"type": "unknown"}

# --- REDGIFS DIRECT MP4 HELPER ---

async def get_redgifs_mp4(redgifs_url: str) -> str:
    """Try to extract the direct mp4 URL from a Redgifs page URL using the Redgifs API."""
    # Redgifs URLs are like https://redgifs.com/watch/<id>
    match = re.search(r"redgifs.com/(?:watch|ifr|embed)/([a-zA-Z0-9]+)", redgifs_url)
    if not match:
        return None
    gif_id = match.group(1)
    api_url = f"https://api.redgifs.com/v2/gifs/{gif_id}"
    try:
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(api_url, headers={"User-Agent": "discord-link-mover-bot/1.0"}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
                # Try to get the best quality mp4
                mp4_url = (
                    data.get("gif", {}).get("urls", {}).get("hd") or
                    data.get("gif", {}).get("urls", {}).get("sd") or
                    data.get("gif", {}).get("urls", {}).get("mobile")
                )
                return mp4_url
    except Exception as e:
        logger.warning(f"Failed to fetch Redgifs mp4 for {redgifs_url}: {e}")
        return None

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

# --- TESTS FOR TRANSFORM_URL ---
if __name__ == "__main__":
    # ... existing code ...
    def _test_transform_url():
        test_cases = [
            ("https://x.com/username/status/123", "https://fxtwitter.com/username/status/123"),
            ("https://twitter.com/username/status/456", "https://fxtwitter.com/username/status/456"),
            ("https://www.x.com/username/status/789", "https://fxtwitter.com/username/status/789"),
            ("https://fxtwitter.com/username/status/1011", "https://fxtwitter.com/username/status/1011"),
        ]
        for input_url, expected in test_cases:
            result = transform_url(input_url)
            print(f"transform_url({input_url}) = {result}")
            assert result == expected, f"Expected {expected}, got {result}"
        print("All transform_url tests passed.")
    _test_transform_url()
    # ... existing code ...

if __name__ == "__main__":
    main() 