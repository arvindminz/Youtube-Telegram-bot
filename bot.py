import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import tempfile
import glob
import time

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Get bot token from environment variable
BOT_TOKEN = os.environ.get('BOT_TOKEN')
if not BOT_TOKEN:
    raise ValueError("No BOT_TOKEN found in environment variables!")

class YouTubeBot:
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message."""
        await update.message.reply_text(
            "🎬 **YouTube Downloader Bot**\n\n"
            "Send me a YouTube link and I'll help you download it!\n\n"
            "**Commands:**\n"
            "/start - Show this message\n"
            "/cancel - Cancel operation\n\n"
            "**Features:**\n"
            "• Download videos (MP4) in 360p, 720p, 1080p\n"
            "• Download audio (MP3) in 128kbps, 320kbps\n"
            "• Fast downloads with quality options",
            parse_mode='Markdown'
        )
    
    def get_ydl_opts(self):
        """Get yt-dlp options with proper headers to avoid 403 error."""
        return {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'ignoreerrors': True,
            'no_color': True,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            # Add headers to mimic a real browser
            'headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-us,en;q=0.5',
                'Sec-Fetch-Mode': 'navigate',
            }
        }
    
    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle YouTube URLs."""
        url = update.message.text.strip()
        
        # Send typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        # Initial message
        status_msg = await update.message.reply_text("🔍 Fetching video information...")
        
        try:
            # Get video info with proper headers
            ydl_opts = self.get_ydl_opts()
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            # Store info
            context.user_data['url'] = url
            context.user_data['title'] = info.get('title', 'Unknown')
            context.user_data['uploader'] = info.get('uploader', 'Unknown')
            context.user_data['duration'] = info.get('duration', 0)
            
            # Create selection buttons
            keyboard = [
                [InlineKeyboardButton("🎬 Video (MP4)", callback_data='type_video')],
                [InlineKeyboardButton("🎵 Audio (MP3)", callback_data='type_audio')],
                [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Format duration
            duration = self.format_duration(info.get('duration', 0))
            
            # Update message
            await status_msg.edit_text(
                f"📹 **{info.get('title', 'Unknown')}**\n\n"
                f"👤 **Uploader:** {info.get('uploader', 'Unknown')}\n"
                f"⏱️ **Duration:** {duration}\n\n"
                f"What would you like to download?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Error: {str(e)}")
    
    async def button_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle button presses."""
        query = update.callback_query
        await query.answer()
        
        if query.data == 'cancel':
            await query.edit_message_text("❌ Operation cancelled.")
            context.user_data.clear()
            return
        
        elif query.data == 'type_video':
            # Video quality options
            keyboard = [
                [InlineKeyboardButton("360p (Smallest file)", callback_data='video_360')],
                [InlineKeyboardButton("720p (Good quality)", callback_data='video_720')],
                [InlineKeyboardButton("1080p (HD)", callback_data='video_1080')],
                [InlineKeyboardButton("🔙 Back", callback_data='back')]
            ]
            await query.edit_message_text(
                "🎬 **Select video quality:**\n\n"
                "Higher quality = Larger file size",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif query.data == 'type_audio':
            # Audio quality options
            keyboard = [
                [InlineKeyboardButton("128 kbps (Small file)", callback_data='audio_128')],
                [InlineKeyboardButton("320 kbps (Best quality)", callback_data='audio_320')],
                [InlineKeyboardButton("🔙 Back", callback_data='back')]
            ]
            await query.edit_message_text(
                "🎵 **Select audio quality:**\n\n"
                "Higher quality = Better sound + Larger file",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif query.data.startswith('video_') or query.data.startswith('audio_'):
            await query.edit_message_text("⏬ **Downloading...** This may take a minute", parse_mode='Markdown')
            await self.download_and_send(update, context, query.data)
        
        elif query.data == 'back':
            keyboard = [
                [InlineKeyboardButton("🎬 Video (MP4)", callback_data='type_video')],
                [InlineKeyboardButton("🎵 Audio (MP3)", callback_data='type_audio')],
                [InlineKeyboardButton("❌ Cancel", callback_data='cancel')]
            ]
            await query.edit_message_text(
                "**Choose download type:**",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
    
    def find_downloaded_file(self, temp_dir, expected_ext=None):
        """Better file finding function."""
        # Wait a moment for files to be written
        time.sleep(2)
        
        # List all files in temp directory
        all_files = glob.glob(f'{temp_dir}/*')
        
        # Filter out directories, only keep files
        files = [f for f in all_files if os.path.isfile(f)]
        
        if not files:
            return None
        
        # If we have an expected extension, try to find files with that extension first
        if expected_ext:
            ext_files = [f for f in files if f.lower().endswith(expected_ext.lower())]
            if ext_files:
                # Return the largest file with correct extension
                return max(ext_files, key=os.path.getsize)
        
        # Otherwise return the largest file (likely the main download)
        return max(files, key=os.path.getsize)
    
    async def download_and_send(self, update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str):
        """Download and send the file."""
        query = update.callback_query
        url = context.user_data.get('url')
        
        if not url:
            await query.edit_message_text("❌ Session expired. Please send the URL again.")
            return
        
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Base yt-dlp options with headers
                ydl_opts = self.get_ydl_opts()
                ydl_opts['outtmpl'] = f'{temp_dir}/%(title)s.%(ext)s'
                
                if choice.startswith('audio_'):
                    # Audio download
                    quality = choice.replace('audio_', '')
                    ydl_opts['format'] = 'bestaudio/best'
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': quality,
                    }]
                    expected_ext = '.mp3'
                else:
                    # Video download
                    quality = choice.replace('video_', '')
                    ydl_opts['format'] = f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]'
                    ydl_opts['merge_output_format'] = 'mp4'
                    expected_ext = '.mp4'
                
                # Add more options to avoid 403 error
                ydl_opts.update({
                    'socket_timeout': 30,
                    'retries': 10,
                    'fragment_retries': 10,
                    'file_access_retries': 10,
                    'extractor_retries': 10,
                    'skip_unavailable_fragments': True,
                })
                
                # Download
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                # Find the downloaded file
                downloaded_file = self.find_downloaded_file(temp_dir, expected_ext)
                
                if downloaded_file and os.path.exists(downloaded_file):
                    file_size = os.path.getsize(downloaded_file) / (1024 * 1024)  # Size in MB
                    file_name = os.path.basename(downloaded_file)
                    
                    logger.info(f"Found file: {file_name}, Size: {file_size:.1f}MB")
                    
                    # Check if file is too large for Telegram (50MB limit)
                    if file_size > 45:  # Leave some margin
                        await query.edit_message_text(
                            f"❌ File too large for Telegram ({file_size:.1f}MB > 45MB limit)\n"
                            f"Try a lower quality or audio only."
                        )
                        return
                    
                    # Upload to Telegram
                    await query.edit_message_text(f"📤 **Uploading...** ({file_size:.1f}MB)", parse_mode='Markdown')
                    
                    with open(downloaded_file, 'rb') as f:
                        if choice.startswith('audio_'):
                            await context.bot.send_audio(
                                chat_id=update.effective_chat.id,
                                audio=f,
                                title=context.user_data.get('title', 'Audio'),
                                performer=context.user_data.get('uploader', 'YouTube'),
                                caption=f"✅ Downloaded via @{context.bot.username}",
                                read_timeout=60,
                                write_timeout=60,
                                connect_timeout=60,
                                pool_timeout=60
                            )
                        else:
                            await context.bot.send_video(
                                chat_id=update.effective_chat.id,
                                video=f,
                                caption=f"✅ Downloaded via @{context.bot.username}",
                                supports_streaming=True,
                                read_timeout=60,
                                write_timeout=60,
                                connect_timeout=60,
                                pool_timeout=60
                            )
                    
                    await query.delete_message()
                else:
                    # List all files in temp_dir for debugging
                    all_files = glob.glob(f'{temp_dir}/*')
                    logger.error(f"Files in temp dir: {all_files}")
                    
                    await query.edit_message_text(
                        "❌ Could not find downloaded file. This might be a temporary issue.\n"
                        "Please try again with a different quality option."
                    )
                    
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Download error: {error_msg}")
                
                if "403" in error_msg:
                    await query.edit_message_text(
                        "❌ YouTube is blocking the download. Please try:\n"
                        "• A different video\n"
                        "• A lower quality\n"
                        "• Wait a few minutes and try again"
                    )
                else:
                    await query.edit_message_text(f"❌ Download error: {error_msg[:200]}")
            
            finally:
                context.user_data.clear()
    
    def format_duration(self, seconds):
        """Format duration in seconds to MM:SS or HH:MM:SS."""
        if not seconds:
            return "Unknown"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

def main():
    """Start the bot."""
    bot = YouTubeBot()
    
    # Create application with higher timeouts
    app = Application.builder().token(BOT_TOKEN).read_timeout(60).write_timeout(60).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_url))
    app.add_handler(CallbackQueryHandler(bot.button_handler))
    
    # Start bot
    print("🤖 Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    main()
