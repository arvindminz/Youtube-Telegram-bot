import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import tempfile
import subprocess

# Enable logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Get bot token from environment variable (Railway sets this)
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
            "• Download videos (MP4)\n"
            "• Download audio (MP3)\n"
            "• Multiple quality options",
            parse_mode='Markdown'
        )
    
    async def handle_url(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle YouTube URLs."""
        url = update.message.text.strip()
        
        # Send typing indicator
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        
        # Initial message
        status_msg = await update.message.reply_text("🔍 Fetching video information...")
        
        try:
            # Get video info
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False
            }
            
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
                f"**What would you like to download?**",
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
                [InlineKeyboardButton("360p", callback_data='video_360')],
                [InlineKeyboardButton("720p", callback_data='video_720')],
                [InlineKeyboardButton("1080p", callback_data='video_1080')],
                [InlineKeyboardButton("Best Available", callback_data='video_best')],
                [InlineKeyboardButton("🔙 Back", callback_data='back')]
            ]
            await query.edit_message_text(
                "🎬 **Select video quality:**\n\n"
                "Note: Higher quality = larger file size",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif query.data == 'type_audio':
            # Audio quality options
            keyboard = [
                [InlineKeyboardButton("128 kbps", callback_data='audio_128')],
                [InlineKeyboardButton("192 kbps", callback_data='audio_192')],
                [InlineKeyboardButton("320 kbps", callback_data='audio_320')],
                [InlineKeyboardButton("🔙 Back", callback_data='back')]
            ]
            await query.edit_message_text(
                "🎵 **Select audio quality:**\n\n"
                "Higher quality = Better sound + Larger file",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        elif query.data.startswith('video_') or query.data.startswith('audio_'):
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
    
    async def download_and_send(self, update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str):
        """Download and send the file."""
        query = update.callback_query
        url = context.user_data.get('url')
        
        if not url:
            await query.edit_message_text("❌ Session expired. Please send the URL again.")
            return
        
        # Update status
        await query.edit_message_text("⏬ **Downloading...** Please wait (this may take a minute)", parse_mode='Markdown')
        
        # Create temp directory for download
        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Configure yt-dlp options
                ydl_opts = {
                    'outtmpl': f'{temp_dir}/%(title)s.%(ext)s',
                    'quiet': True,
                    'no_warnings': True,
                }
                
                if choice.startswith('audio_'):
                    # Audio download
                    quality = choice.replace('audio_', '')
                    ydl_opts['format'] = 'bestaudio/best'
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': quality,
                    }]
                    file_ext = 'mp3'
                else:
                    # Video download
                    quality = choice.replace('video_', '')
                    if quality == 'best':
                        ydl_opts['format'] = 'best[height<=1080]+bestaudio/best'
                    else:
                        ydl_opts['format'] = f'best[height<={quality}]+bestaudio/best'
                    ydl_opts['merge_output_format'] = 'mp4'
                    file_ext = 'mp4'
                
                # Download
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                # Find downloaded file
                import glob
                files = glob.glob(f'{temp_dir}/*.{file_ext}')
                if not files:
                    files = glob.glob(f'{temp_dir}/*')
                
                if files:
                    downloaded_file = files[0]
                    file_size = os.path.getsize(downloaded_file) / (1024 * 1024)  # Size in MB
                    
                    # Check if file is too large for Telegram (50MB limit)
                    if file_size > 45:  # Leave some margin
                        await query.edit_message_text(
                            f"❌ File too large for Telegram ({file_size:.1f}MB > 45MB limit)\n"
                            f"Try a lower quality."
                        )
                        return
                    
                    # Upload to Telegram
                    await query.edit_message_text("📤 **Uploading to Telegram...**", parse_mode='Markdown')
                    
                    with open(downloaded_file, 'rb') as f:
                        if choice.startswith('audio_'):
                            await context.bot.send_audio(
                                chat_id=update.effective_chat.id,
                                audio=f,
                                title=context.user_data.get('title', 'Audio'),
                                performer=context.user_data.get('uploader', 'YouTube'),
                                caption=f"✅ Downloaded via @{context.bot.username}"
                            )
                        else:
                            await context.bot.send_video(
                                chat_id=update.effective_chat.id,
                                video=f,
                                caption=f"✅ Downloaded via @{context.bot.username}",
                                supports_streaming=True
                            )
                    
                    await query.delete_message()
                else:
                    await query.edit_message_text("❌ Could not find downloaded file")
                    
            except Exception as e:
                await query.edit_message_text(f"❌ Download error: {str(e)}")
            
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
    
    # Create application
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", bot.start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, bot.handle_url))
    app.add_handler(CallbackQueryHandler(bot.button_handler))
    
    # Start bot
    print("🤖 Bot is running...")
    app.run_polling()

if __name__ == '__main__':
    main()