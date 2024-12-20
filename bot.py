import telebot
import yt_dlp
import os
from pathlib import Path
import logging
from urllib.parse import urlparse
from dotenv import load_dotenv
import ffmpeg

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize bot
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables!")

bot = telebot.TeleBot(BOT_TOKEN)

# Create downloads directory
DOWNLOAD_DIR = Path("downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)

def is_valid_youtube_url(url):
    """Validate if the given URL is a YouTube URL"""
    try:
        parsed = urlparse(url)
        return any(
            domain in parsed.netloc
            for domain in ['youtube.com', 'youtu.be', 'm.youtube.com', 'www.youtube.com']
        )
    except Exception:
        return False

def get_safe_filename(title):
    """Convert title to safe filename"""
    return "".join(x for x in title if x.isalnum() or x in (' ', '-', '_')).rstrip()

def process_video(input_file, output_file):
    """Process video with ffmpeg-python for better quality"""
    try:
        # Input video stream
        stream = ffmpeg.input(input_file)
        
        # Apply video processing
        stream = ffmpeg.output(stream, output_file,
            # Video settings
            vcodec='libx264',        # H.264 codec
            crf=18,                  # High quality (18-23 is very good)
            preset='slow',           # Slower encoding = better quality
            profile='high',          # High profile
            level='4.1',            # Compatibility level
            pix_fmt='yuv420p',      # Standard pixel format
            # Audio settings
            acodec='aac',           # AAC audio codec
            audio_bitrate='192k',    # Audio bitrate
            # Additional options
            movflags='+faststart',   # Enable fast streaming
            **{'max_muxing_queue_size': '1024'} # Prevent muxing errors
        )
        
        # Run ffmpeg
        ffmpeg.run(stream, overwrite_output=True, capture_stdout=True, capture_stderr=True)
        return True
    except ffmpeg.Error as e:
        logger.error(f"FFmpeg error: {e.stderr.decode()}")
        return False
    except Exception as e:
        logger.error(f"Processing error: {str(e)}")
        return False

def download_video(url, message):
    """Download YouTube video and send to Telegram"""
    status_message = None
    downloaded_file = None
    processed_file = None
    
    try:
        # Send initial status
        status_message = bot.reply_to(message, "📥 Starting download...")
        
        # Configure yt-dlp options
        ydl_opts = {
            'format': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[ext=mp4]/best',
            'outtmpl': str(DOWNLOAD_DIR / '%(title)s.%(ext)s'),
            'merge_output_format': 'mp4'
        }
        
        # Clean up existing files
        for file in DOWNLOAD_DIR.glob("*"):
            try:
                file.unlink()
            except Exception as e:
                logger.error(f"Error cleaning up file {file}: {e}")

        # Extract video information
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            bot.edit_message_text("⌛ Fetching video information...", 
                                message.chat.id, 
                                status_message.message_id)
            
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError("Could not fetch video information")

            # Check video duration (limit to 10 minutes)
            if info.get('duration', 0) > 600:
                raise ValueError("Video is too long (maximum 10 minutes)")

            # Get safe filename
            title = info.get('title', 'video')
            safe_title = get_safe_filename(title)
            downloaded_file = DOWNLOAD_DIR / f"{safe_title}_raw.mp4"
            processed_file = DOWNLOAD_DIR / f"{safe_title}.mp4"

            # Download video
            bot.edit_message_text("⏳ Downloading video in 1080p...", 
                                message.chat.id, 
                                status_message.message_id)
            
            ydl.download([url])
            
            # Find the downloaded file
            potential_files = list(DOWNLOAD_DIR.glob("*"))
            if not potential_files:
                raise FileNotFoundError("No files found in download directory")
            
            downloaded_file = max(potential_files, key=lambda x: x.stat().st_mtime)
            
            # Process video with FFmpeg
            bot.edit_message_text("🎬 Processing video for better quality...", 
                                message.chat.id, 
                                status_message.message_id)
            
            if not process_video(str(downloaded_file), str(processed_file)):
                raise ValueError("Failed to process video")
            
            # Check file size
            file_size = os.path.getsize(processed_file)
            if file_size > 50 * 1024 * 1024:  # 50MB limit
                raise ValueError("Processed video is too large for Telegram (>50MB). Try a shorter video.")

            # Upload to Telegram
            bot.edit_message_text("📤 Uploading to Telegram...", 
                                message.chat.id, 
                                status_message.message_id)
            
            with open(processed_file, 'rb') as video_file:
                bot.send_video(
                    message.chat.id,
                    video_file,
                    caption=f"✅ {title}\n🎥 Enhanced 1080p quality",
                    supports_streaming=True,
                    timeout=60
                )
            
            bot.edit_message_text("✅ Download and processing completed!", 
                                message.chat.id, 
                                status_message.message_id)

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        logger.error(error_message)
        if status_message:
            bot.edit_message_text(f"❌ {error_message}", 
                                message.chat.id, 
                                status_message.message_id)

    finally:
        # Clean up files
        for file in [downloaded_file, processed_file]:
            if file and file.exists():
                try:
                    file.unlink()
                except Exception as e:
                    logger.error(f"Error removing file {file}: {e}")

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    """Handle /start and /help commands"""
    welcome_text = """
🎥 *Enhanced YouTube Download Bot*

Send me a YouTube link and I'll download it in enhanced 1080p quality!

*Features:*
• High quality 1080p video
• Enhanced video processing
• Improved audio quality (192kbps AAC)
• Optimized streaming

*Limitations:*
• Maximum video size: 50MB (Telegram limit)
• Maximum duration: 10 minutes
• Supported URLs: YouTube only

Simply paste a YouTube link to start downloading!
"""
    bot.reply_to(message, welcome_text, parse_mode='Markdown')

@bot.message_handler(func=lambda message: message.text and is_valid_youtube_url(message.text))
def handle_youtube_url(message):
    """Handle YouTube URLs"""
    download_video(message.text, message)

@bot.message_handler(func=lambda message: True)
def handle_invalid_message(message):
    """Handle all other messages"""
    bot.reply_to(message, "Please send a valid YouTube link! 🎥")

def main():
    """Main function to run the bot"""
    logger.info("Bot started! Waiting for YouTube links...")
    while True:
        try:
            bot.polling(none_stop=True, interval=1, timeout=60)
        except Exception as e:
            logger.error(f"Bot polling error: {e}")
            continue

if __name__ == "__main__":
    main()