import os
import re
import json
import time
import asyncio
import hikari
import logging
import random
from dotenv import load_dotenv

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

def is_media_url(url: str) -> bool:
    """Check if the URL is a direct link to media or a video platform that embeds well."""
    url_lower = url.lower()
    
    # Check for direct media file extensions
    if any(url_lower.endswith(ext) for ext in MEDIA_EXTENSIONS):
        return True
    
    # Check for video hosting domains (excluding YouTube shorts)
    for domain in VIDEO_DOMAINS:
        if domain in url_lower and 'youtube.com/shorts' not in url_lower:
            return True
            
    # Special checks for specific platforms
    if 'imgur.com' in url_lower and any(ext in url_lower for ext in ['.mp4', '.gifv']):
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
    
    # Special handling for Reddit domains (check this first)
    if 'reddit.com' in domain.lower():
        # Handle old.reddit.com and www.reddit.com
        clean_path = path.rstrip('/')  # Remove trailing slash if present
        # If it's a post URL (contains '/comments/' or '/r/subreddit/comments/')
        if '/comments/' in clean_path:
            return f'https://vxreddit.com{clean_path}'
        # If it's a subreddit URL or other Reddit URL, keep as is for proper embedding
        return f'https://reddit.com{clean_path}'
    
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
                    # Transform YouTube shorts to regular YouTube URLs
                    shorts_id = path.split('/shorts/')[1].split('?')[0]
                    return f'https://youtu.be/{shorts_id}'
            
            # For all other transformations
            new_domain = domain.replace(original, replacement)
            return f'https://{new_domain}{path}'
    
    return url

def process_nested_links(content: str) -> str:
    """Process content to transform any nested links while preserving the main content structure."""
    def replace_link(match):
        full_url = match.group(0)
        transformed = transform_url(full_url)
        return transformed if transformed else full_url
    
    # Find and transform all URLs in the content
    return re.sub(URL_PATTERN, replace_link, content)

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
    """Event fired when a message is created."""
    # Ignore messages from the bot itself
    if event.is_bot or not event.content:
        return
    
    # Get message author information
    author = event.author
    author_name = author.username if author else "Unknown User"
    author_mention = f"<@{author.id}>" if author else "Unknown User"
    author_id = str(author.id) if author else None
    
    # Process content for nested links first
    processed_content = process_nested_links(event.content)
    
    # Extract all URLs from the processed message
    urls = re.findall(URL_PATTERN, processed_content)
    full_urls = [f"https://{domain}{path}" for domain, path in urls]
    normalized_urls = [normalize_link(url) for url in full_urls]
    
    # Cleanup old links before checking
    cleanup_recent_links()
    now = time.time()
    
    # Check for duplicates in both channels (original and transformed links)
    for orig_url in full_urls:
        norm_orig_url = normalize_link(orig_url)
        transformed_url = transform_url(orig_url)
        norm_trans_url = normalize_link(transformed_url) if transformed_url else None

        # Check original
        is_dup = False
        dup_is_self = False
        entry = recent_links.get(norm_orig_url)
        if entry:
            # Backward compatibility: [ts, msg_id] or [ts, msg_id, user_id]
            ts, orig_msg_id = entry[0], entry[1]
            entry_user_id = entry[2] if len(entry) > 2 else None
            if now - ts <= RECENT_LINKS_MAX_AGE:
                if entry_user_id and author_id:
                    if author_id == entry_user_id:
                        # Self repost: allow after 48h
                        if now - ts < 48 * 3600:
                            is_dup = True
                            dup_is_self = True
                    else:
                        is_dup = True
                else:
                    # Old format: treat as duplicate for all users
                    is_dup = True
        # Check transformed (if different)
        if norm_trans_url and norm_trans_url != norm_orig_url:
            entry = recent_links.get(norm_trans_url)
            if entry:
                ts, orig_msg_id = entry[0], entry[1]
                entry_user_id = entry[2] if len(entry) > 2 else None
                if now - ts <= RECENT_LINKS_MAX_AGE:
                    if entry_user_id and author_id:
                        if author_id == entry_user_id:
                            if now - ts < 48 * 3600:
                                is_dup = True
                                dup_is_self = True
                        else:
                            is_dup = True
                    else:
                        is_dup = True
        if is_dup:
            try:
                await bot.rest.delete_message(event.channel_id, event.message_id)
            except Exception as e:
                logger.error(f"Error deleting duplicate message: {e}")
            try:
                # Check if original message still exists
                try:
                    orig_msg = await bot.rest.fetch_message(event.channel_id, orig_msg_id)
                except hikari.NotFoundError:
                    return  # Original message deleted, do nothing
                snarky_comment = random.choice(SNARKY_COMMENTS)
                # Reply to the original message, @ the user, and include the snarky comment
                await bot.rest.create_message(
                    event.channel_id,
                    f"{author_mention} {snarky_comment}",
                    reply_to=orig_msg_id
                )
            except Exception as e:
                logger.error(f"Error replying to original message: {e}")
            return  # Only need to respond to the first duplicate found

    # If not duplicate, add all normalized URLs (original and transformed) to the record
    for orig_url in full_urls:
        norm_orig_url = normalize_link(orig_url)
        transformed_url = transform_url(orig_url)
        norm_trans_url = normalize_link(transformed_url) if transformed_url else None
        recent_links[norm_orig_url] = [now, event.message_id, author_id]
        if norm_trans_url and norm_trans_url != norm_orig_url:
            recent_links[norm_trans_url] = [now, event.message_id, author_id]
    save_recent_links()

    # Handle messages based on channel
    if event.channel_id == SOURCE_CHANNEL_ID:
        # Original source channel handling
        urls = re.findall(URL_PATTERN, processed_content)
        
        if urls:
            logger.info(f"Found {len(urls)} links in source channel")
            logger.info(f"Original content: {event.content}")
            logger.info(f"Processed content: {processed_content}")
            
            # Extract any mentions from the original message
            cleaned_content, mentions = extract_mentions(processed_content)
            mentions_str = ' '.join(mentions) if mentions else ''
            
            # Get channel name
            try:
                source_channel = await bot.rest.fetch_channel(SOURCE_CHANNEL_ID)
                source_channel_name = source_channel.name
            except Exception as e:
                logger.error(f"Error fetching source channel name: {e}")
                source_channel_name = f"channel-{SOURCE_CHANNEL_ID}"
            
            # Post links to destination channel
            success_count = 0
            
            # Reconstruct full URLs from regex matches and transform them
            full_urls = [f"https://{domain}{path}" for domain, path in urls]
            
            # First check if any URLs are direct media links
            if any(is_media_url(url) for url in full_urls):
                logger.info("Message contains direct media links - keeping in original channel")
                return
            
            # Transform non-media URLs
            transformed_urls = [transform_url(url) for url in full_urls]
            
            # Log URL transformations
            for orig, trans in zip(full_urls, transformed_urls):
                if trans:
                    logger.info(f"URL Transformation: {orig} -> {trans}")
                else:
                    logger.info(f"URL skipped (media content): {orig}")
            
            # Filter out None values (which indicate media links)
            url_pairs = [(orig, trans) for orig, trans in zip(full_urls, transformed_urls) if trans is not None]
            
            if not url_pairs:  # If all URLs were media or no valid URLs
                return
                
            for original_url, transformed_url in url_pairs:
                try:
                    # Format the message with mentions first, then the link
                    # Use zero-width space after mentions to ensure proper embedding
                    if mentions:
                        message_content = f"{mentions_str}\u200b{transformed_url}"
                        context_message = f"Link from #{source_channel_name} by {author_mention}"
                    else:
                        message_content = transformed_url
                        context_message = f"Link from #{source_channel_name} by {author_mention}"
                        
                    # Send context message first
                    await bot.rest.create_message(DESTINATION_CHANNEL_ID, context_message)
                    
                    # Send the link in a separate message for better embedding
                    await bot.rest.create_message(DESTINATION_CHANNEL_ID, message_content)
                    
                    logger.info(f"Successfully moved link to destination channel: {transformed_url}")
                    success_count += 1
                except hikari.ForbiddenError:
                    logger.error("Error: Bot doesn't have permission to post in the destination channel")
                    print_permissions_guide()
                    return
                except Exception as e:
                    logger.error(f"Error posting link to destination channel: {e}")
            
            # Delete the original message if at least one link was moved successfully
            if success_count > 0:
                try:
                    await bot.rest.delete_message(SOURCE_CHANNEL_ID, event.message_id)
                    logger.info("Deleted original message containing links")
                except hikari.ForbiddenError:
                    logger.error("Error: Bot doesn't have permission to delete messages in source channel")
                except Exception as e:
                    logger.error(f"Error deleting original message: {e}")
            else:
                logger.warning("No links were successfully moved, keeping original message")
                
    elif event.channel_id == DESTINATION_CHANNEL_ID:
        # Handle messages posted directly in destination channel
        urls = re.findall(URL_PATTERN, event.content)
        
        if urls:
            logger.info(f"Found {len(urls)} links in destination channel")
            
            # Extract any mentions from the original message
            cleaned_content, mentions = extract_mentions(event.content)
            mentions_str = ' '.join(mentions) if mentions else ''
            
            # Reconstruct full URLs from regex matches
            full_urls = [f"https://{domain}{path}" for domain, path in urls]
            
            # Don't transform if it's a media URL
            if any(is_media_url(url) for url in full_urls):
                logger.info("Message contains direct media links - keeping as is")
                return
                
            # Transform non-media URLs
            transformed_urls = [transform_url(url) for url in full_urls]
            
            # Filter out None values and unchanged URLs
            url_pairs = [(orig, trans) for orig, trans in zip(full_urls, transformed_urls) 
                        if trans is not None and trans != orig]
            
            if url_pairs:  # If we have any URLs to transform
                try:
                    # Start with the original message content
                    new_content = event.content
                    
                    # Replace each URL with its transformed version
                    for original_url, transformed_url in url_pairs:
                        logger.info(f"Original URL: {original_url}")
                        logger.info(f"Transformed URL: {transformed_url}")
                        # Make sure we're replacing the exact URL
                        if original_url in new_content:
                            new_content = new_content.replace(original_url, transformed_url)
                        else:
                            # Try with www. version
                            www_url = original_url.replace('https://', 'https://www.')
                            if www_url in new_content:
                                new_content = new_content.replace(www_url, transformed_url)
                        logger.info(f"Content after replacement: {new_content}")
                    
                    # Create the new message with all mentions at the start
                    if mentions:
                        # Remove mentions from content and add them at the start
                        for mention in mentions:
                            new_content = new_content.replace(mention, '')
                        # Clean up extra spaces
                        new_content = ' '.join(new_content.split())
                        new_message = f"{author_mention} {mentions_str}: {new_content}"
                    else:
                        new_message = f"{author_mention}: {new_content}"
                    
                    # Delete the original message first
                    await bot.rest.delete_message(DESTINATION_CHANNEL_ID, event.message_id)
                    
                    # Post the new message
                    await bot.rest.create_message(
                        DESTINATION_CHANNEL_ID,
                        new_message
                    )
                    logger.info("Successfully transformed links in destination channel message")
                    
                except hikari.ForbiddenError:
                    logger.error("Error: Bot doesn't have permission to manage messages in destination channel")
                except Exception as e:
                    logger.error(f"Error transforming links in destination channel: {e}")

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