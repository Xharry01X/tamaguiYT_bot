import telebot
import yt_dlp
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get BOT_TOKEN from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Initialize bot
bot = telebot.TeleBot(BOT_TOKEN)

def download_video(url, message):
    try:
        # Send initial status
        status_message = bot.reply_to(message, "📥 Starting download...")
        
        ydl_opts = {
            'format': 'best[ext=mp4]/best',  # Best quality MP4
            'outtmpl': '%(title)s.%(ext)s',
            'prefer_ffmpeg': True,
            'postprocessors': [{
                'key': 'FFmpegVideoRemuxer',
                'preferedformat': 'mp4',
            }],
        }
        
        # Download the video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Get video info
            info = ydl.extract_info(url, download=False)
            filename = ydl.prepare_filename(info)
            
            # Update status
            bot.edit_message_text("⏳ Downloading...", 
                                message.chat.id, 
                                status_message.message_id)
            
            # Download
            ydl.download([url])
            
            # Send video file
            bot.edit_message_text("📤 Uploading to Telegram...", 
                                message.chat.id, 
                                status_message.message_id)
            
            with open(filename, 'rb') as video_file:
                bot.send_video(message.chat.id, 
                             video_file, 
                             caption=f"✅ {info['title']}")
            
            # Clean up
            os.remove(filename)
            bot.delete_message(message.chat.id, status_message.message_id)
            
    except Exception as e:
        bot.reply_to(message, f"❌ Error: {str(e)}")

# Handler for YouTube URLs
@bot.message_handler(func=lambda message: 'youtube.com' in message.text.lower() or 'youtu.be' in message.text.lower())
def handle_youtube_url(message):
    download_video(message.text, message)

# Handler for all other messages
@bot.message_handler(content_types=['text'])
def handle_text(message):
    if 'youtube.com' not in message.text.lower() and 'youtu.be' not in message.text.lower():
        bot.reply_to(message, "Send me a YouTube link to download the video! 🎥")

def main():
    print("Bot started! Waiting for YouTube links...")
    try:
        bot.polling(none_stop=True, interval=0)
    except Exception as e:
        print(f"Bot encountered an error: {e}")

if __name__ == "__main__":
    main()