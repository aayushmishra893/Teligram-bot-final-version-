import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import sqlite3
import os
import random
import asyncio

# Logging setup
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "8549652169:AAGKUZALL5V8VFUGrxobkaFxILDqynhDO3M"
OWNER_ID = 6020796284
PROMOTION_CHANNEL = "@your_channel_username"

# Database Setup
DB_FILE = "bot_data.db"

def init_database():
    """Initialize database - Keep all data"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Media table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS media (
            media_id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id TEXT UNIQUE,
            file_type TEXT,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Settings table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # User viewing history
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            media_id INTEGER,
            viewed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Initialize default settings
    cursor.execute('INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)',
                   ('force_join_enabled', '1'))
    cursor.execute('INSERT OR IGNORE INTO settings (setting_key, setting_value) VALUES (?, ?)',
                   ('promotion_channel', PROMOTION_CHANNEL))
    
    conn.commit()
    conn.close()
    print("Database: Connected!")

def get_db_connection():
    """Get database connection"""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def get_setting(key):
    """Get setting value"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT setting_value FROM settings WHERE setting_key = ?', (key,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else None

def set_setting(key, value):
    """Set setting value"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT OR REPLACE INTO settings (setting_key, setting_value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
    ''', (key, value))
    conn.commit()
    conn.close()

def add_media(file_id, file_type):
    """Add media/file to database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO media (file_id, file_type)
            VALUES (?, ?)
        ''', (file_id, file_type))
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()

def get_random_media(user_id):
    """Get random media for user without repeat"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Total media count
    cursor.execute('SELECT COUNT(*) as count FROM media')
    total_media = cursor.fetchone()['count']
    
    if total_media == 0:
        conn.close()
        return None
    
    # Media viewed by user
    cursor.execute('''
        SELECT DISTINCT media_id FROM user_views WHERE user_id = ?
    ''', (user_id,))
    viewed_ids = [row['media_id'] for row in cursor.fetchall()]
    
    # Get all unviewed media
    if len(viewed_ids) < total_media:
        placeholders = ','.join('?' * len(viewed_ids)) if viewed_ids else ''
        if viewed_ids:
            cursor.execute(f'''
                SELECT media_id, file_id, file_type FROM media WHERE media_id NOT IN ({placeholders})
            ''', viewed_ids)
        else:
            cursor.execute('SELECT media_id, file_id, file_type FROM media')
        unviewed = cursor.fetchall()
    else:
        # All viewed, reset all
        cursor.execute('DELETE FROM user_views WHERE user_id = ?', (user_id,))
        conn.commit()
        cursor.execute('SELECT media_id, file_id, file_type FROM media')
        unviewed = cursor.fetchall()
    
    if not unviewed:
        conn.close()
        return None
    
    selected = random.choice(unviewed)
    
    # Add view record
    cursor.execute('''
        INSERT INTO user_views (user_id, media_id) VALUES (?, ?)
    ''', (user_id, selected['media_id']))
    conn.commit()
    conn.close()
    
    return selected

def get_total_media_count():
    """Count total media"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as count FROM media')
    count = cursor.fetchone()['count']
    conn.close()
    return count

# ========================= USER HANDLERS =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command - /start"""
    user = update.effective_user
    
    force_join_enabled = get_setting('force_join_enabled') == '1'
    promotion_channel = get_setting('promotion_channel')
    
    if force_join_enabled:
        # Force Join System
        keyboard = [
            [InlineKeyboardButton("Link: Join Channel", url=f"https://t.me/{promotion_channel.replace('@', '')}")],
            [InlineKeyboardButton("Check: Try Again", callback_data="check_join")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"Welcome {user.first_name}!\n\n"
            f"Please join our channel to view media.\n\n"
            f"Channel: {promotion_channel}",
            reply_markup=reply_markup
        )
    else:
        await show_main_menu(update, context)

async def check_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check if user joined channel"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    promotion_channel = get_setting('promotion_channel')
    
    try:
        channel = promotion_channel
        if channel.startswith('@'):
            channel = channel[1:]
        
        chat_member = await context.bot.get_chat_member(
            chat_id=f"@{channel}",
            user_id=user_id
        )
        
        if chat_member.status in ['member', 'administrator', 'creator']:
            await query.edit_message_text("Success! You can now view content.")
            await asyncio.sleep(1)
            await show_main_menu(update, context)
        else:
            await query.answer("Error: Please join the channel first!", show_alert=True)
    except Exception as e:
        logger.error(f"Error checking join: {e}")
        await query.answer("Error occurred. Please try again.", show_alert=True)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show main menu"""
    keyboard = [
        [InlineKeyboardButton("Video: Watch", callback_data="watch")],
        [InlineKeyboardButton("Menu: Options", callback_data="menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            "Welcome to Media Bot!\n\nWhat would you like to do?",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            "Welcome to Media Bot!\n\nWhat would you like to do?",
            reply_markup=reply_markup
        )

async def watch_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show random media"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    media = get_random_media(user_id)
    
    if not media:
        await query.edit_message_text(
            "Error: No media found. Please contact admin."
        )
        return
    
    keyboard = [
        [InlineKeyboardButton("Next: Skip", callback_data="next_media"),
         InlineKeyboardButton("Back: Menu", callback_data="back_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        # Delete old message
        try:
            await query.delete_message()
        except:
            pass
        
        # Send media with protection
        if media['file_type'] == 'photo':
            await context.bot.send_photo(
                chat_id=query.from_user.id,
                photo=media['file_id'],
                reply_markup=reply_markup,
                protect_content=True
            )
        elif media['file_type'] == 'video':
            await context.bot.send_video(
                chat_id=query.from_user.id,
                video=media['file_id'],
                reply_markup=reply_markup,
                protect_content=True
            )
    except Exception as e:
        logger.error(f"Error sending media: {e}")
        await query.edit_message_text(f"Error: {str(e)}")

async def next_media(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show next media"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    
    try:
        await query.delete_message()
    except:
        pass
    
    media = get_random_media(user_id)
    
    if not media:
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text="Success! All media viewed. Go back to menu.",
            protect_content=True
        )
        await show_main_menu(update, context)
        return
    
    keyboard = [
        [InlineKeyboardButton("Next: Skip", callback_data="next_media"),
         InlineKeyboardButton("Back: Menu", callback_data="back_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        if media['file_type'] == 'photo':
            await context.bot.send_photo(
                chat_id=query.from_user.id,
                photo=media['file_id'],
                reply_markup=reply_markup,
                protect_content=True
            )
        elif media['file_type'] == 'video':
            await context.bot.send_video(
                chat_id=query.from_user.id,
                video=media['file_id'],
                reply_markup=reply_markup,
                protect_content=True
            )
    except Exception as e:
        logger.error(f"Error sending next media: {e}")

async def back_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to main menu"""
    query = update.callback_query
    await query.answer()
    
    try:
        await query.delete_message()
    except:
        pass
    
    await show_main_menu(update, context)

# ========================= ADMIN HANDLERS =========================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/admin command - Admin panel"""
    user = update.effective_user
    
    if user.id != OWNER_ID:
        await update.message.reply_text("Error: You do not have admin access.")
        return
    
    keyboard = [
        [InlineKeyboardButton("Files: Add Media", callback_data="add_files")],
        [InlineKeyboardButton("Promotion: Settings", callback_data="promotion")],
        [InlineKeyboardButton("Bot: Details", callback_data="bot_details")],
        [InlineKeyboardButton("Back: Menu", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Admin Panel - Locked Access\n\nWhat would you like to do?",
        reply_markup=reply_markup
    )

async def add_files_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Files add prompt"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Files: Send Photo/Video one by one\n\n"
        "Type /done when finished adding all files."
    )
    context.user_data['adding_files'] = True

async def handle_media_upload(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle media files"""
    if not context.user_data.get('adding_files'):
        return
    
    if update.message.photo:
        file_id = update.message.photo[-1].file_id
        media_id = add_media(file_id, 'photo')
        if media_id:
            await update.message.reply_text("Success! Photo added!")
        else:
            await update.message.reply_text("Warning: This photo already exists.")
    
    elif update.message.video:
        file_id = update.message.video.file_id
        media_id = add_media(file_id, 'video')
        if media_id:
            await update.message.reply_text("Success! Video added!")
        else:
            await update.message.reply_text("Warning: This video already exists.")

async def done_adding_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/done command"""
    if not context.user_data.get('adding_files'):
        return
    
    context.user_data['adding_files'] = False
    total = get_total_media_count()
    await update.message.reply_text(f"Success! Total {total} media files added.")
    await admin_panel(update, context)

async def promotion_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Promotion settings"""
    query = update.callback_query
    await query.answer()
    
    force_join_enabled = get_setting('force_join_enabled') == '1'
    promotion_channel = get_setting('promotion_channel')
    status = "On" if force_join_enabled else "Off"
    
    keyboard = [
        [InlineKeyboardButton("Channel: Change", callback_data="change_channel")],
        [InlineKeyboardButton(f"Force Join: {status}", callback_data="toggle_force_join")],
        [InlineKeyboardButton("Back: Menu", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Promotion Settings\n\n"
        f"Current Channel: {promotion_channel}",
        reply_markup=reply_markup
    )

async def change_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change channel handler"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Channel: Change\n\n"
        "Send new channel username (like @mychannel or mychannel)\n\n"
        "Type /cancel to go back."
    )
    context.user_data['waiting_channel'] = True

async def handle_channel_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle channel input"""
    if not context.user_data.get('waiting_channel'):
        return
    
    channel_name = update.message.text.strip()
    
    if not channel_name.startswith('@'):
        channel_name = '@' + channel_name
    
    set_setting('promotion_channel', channel_name)
    context.user_data['waiting_channel'] = False
    
    await update.message.reply_text(
        f"Success! Channel changed to: {channel_name}\n\n"
        "Users will see this channel on next /start"
    )

async def toggle_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Toggle force join"""
    query = update.callback_query
    await query.answer()
    
    current = get_setting('force_join_enabled')
    new_value = '0' if current == '1' else '1'
    set_setting('force_join_enabled', new_value)
    
    status = "Enabled" if new_value == '1' else "Disabled"
    await query.answer(f"Force Join {status}!", show_alert=True)
    await promotion_handler(update, context)

async def bot_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show bot details"""
    query = update.callback_query
    await query.answer()
    
    total_media = get_total_media_count()
    force_join_status = "On" if get_setting('force_join_enabled') == '1' else "Off"
    promotion_channel = get_setting('promotion_channel')
    
    keyboard = [
        [InlineKeyboardButton("Back: Menu", callback_data="admin_back")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    details = (
        f"Bot Details - Protected\n\n"
        f"Media: {total_media}\n"
        f"Force Join: {force_join_status}\n"
        f"Channel: {promotion_channel}\n"
        f"Started: 2026-03-01"
    )
    
    await query.edit_message_text(details, reply_markup=reply_markup)

async def admin_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Back to admin panel"""
    query = update.callback_query
    await query.answer()
    
    context.user_data['waiting_channel'] = False
    
    try:
        await query.delete_message()
    except:
        pass
    
    await admin_panel(update.callback_query, context)

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/cancel command"""
    context.user_data['waiting_channel'] = False
    context.user_data['adding_files'] = False
    
    await update.message.reply_text("Operation cancelled.")

# ========================= MAIN =========================

def main():
    """Start bot"""
    init_database()
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CommandHandler("done", done_adding_files))
    application.add_handler(CommandHandler("cancel", cancel_command))
    
    # Callbacks
    application.add_handler(CallbackQueryHandler(check_join, pattern="check_join"))
    application.add_handler(CallbackQueryHandler(watch_media, pattern="watch"))
    application.add_handler(CallbackQueryHandler(next_media, pattern="next_media"))
    application.add_handler(CallbackQueryHandler(back_menu, pattern="back_menu"))
    application.add_handler(CallbackQueryHandler(add_files_handler, pattern="add_files"))
    application.add_handler(CallbackQueryHandler(promotion_handler, pattern="promotion"))
    application.add_handler(CallbackQueryHandler(change_channel, pattern="change_channel"))
    application.add_handler(CallbackQueryHandler(toggle_force_join, pattern="toggle_force_join"))
    application.add_handler(CallbackQueryHandler(bot_details, pattern="bot_details"))
    application.add_handler(CallbackQueryHandler(admin_back, pattern="admin_back"))
    
    # Messages
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_channel_input))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO, handle_media_upload))
    
    print("Bot: Started and Running!")
    application.run_polling()

if __name__ == "__main__":
    main()