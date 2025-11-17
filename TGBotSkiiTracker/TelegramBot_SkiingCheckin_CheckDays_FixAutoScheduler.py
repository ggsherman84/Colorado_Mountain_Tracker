import os
import csv
import logging
import requests
import random
from datetime import datetime, time, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
import pytz

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# CSV file for database
CSV_FILE = 'users_database.csv'
CSV_HEADERS = ['user_id', 'username', 'passHolder', 'skillLevel', 'typeRider', 'activeMountain', 'checkin_timestamp', 'checkin_history']

# Weather CSV file
WEATHER_CSV_FILE = 'weather_database.csv'
WEATHER_CSV_HEADERS = ['mountain_name', 'temp_low', 'temp_high', 'temp_current', 'description', 'snowfall_12hr', 'is_snowing', 'last_updated']

# MOTD file
MOTD_FILE = 'motd_data.txt'

# Active Riders announcement toggle file
ANNOUNCE_TOGGLE_FILE = 'announce_toggle.txt'

# Check-in history file
CHECKIN_HISTORY_FILE = 'checkin_history.csv'
CHECKIN_HISTORY_HEADERS = ['user_id', 'date', 'mountain', 'checkin_time']

# Daily snapshot file - records longest check-in per day
DAILY_SNAPSHOT_FILE = 'daily_snapshot.csv'
DAILY_SNAPSHOT_HEADERS = ['user_id', 'date', 'mountain', 'username']

# Mountain lists with coordinates for weather API
EPM_MOUNTAINS = ['Vail', 'Beaver Creek', 'Breckenridge', 'Keystone', 'Crested Butte', 'Telluride']
IPM_MOUNTAINS = ['Aspen', 'Snowmass', 'Steamboat', 'Winter Park', 'Copper Mountain', 'Arapahoe Basin', 'Eldora']
LOVELAND_MOUNTAINS = ['Loveland']

# Mountain coordinates (latitude, longitude) for weather lookups
MOUNTAIN_COORDS = {
    'Vail': (39.6403, -106.3742),
    'Beaver Creek': (39.6042, -106.5165),
    'Breckenridge': (39.4817, -106.0384),
    'Keystone': (39.5791, -105.9347),
    'Crested Butte': (38.8697, -106.9878),
    'Telluride': (37.9375, -107.8123),
    'Aspen': (39.1911, -106.8175),
    'Snowmass': (39.2130, -106.9378),
    'Steamboat': (40.4850, -106.8317),
    'Winter Park': (39.8868, -105.7625),
    'Copper Mountain': (39.5022, -106.1506),
    'Arapahoe Basin': (39.6428, -105.8717),
    'Eldora': (39.9372, -105.5828),
    'Loveland': (39.6794, -105.8978)
}

# Conversation states
PASS_SELECT, SKILL_SELECT, RIDER_SELECT = range(3)
MOUNTAIN_PASS_SELECT, MOUNTAIN_SELECT, BUDDY_CHECKIN_CONFIRM, BUDDY_SELECT = range(3, 7)
EDIT_PASS_SELECT, EDIT_SKILL_SELECT, EDIT_RIDER_SELECT = range(7, 10)
MOTD_AUTH, MOTD_INPUT = range(10, 12)
ERASEALL_AUTH, ERASEALL_CONFIRM = range(12, 14)
VIEW_MOUNTAIN_PASS_SELECT, VIEW_MOUNTAIN_SELECT, VIEW_MOUNTAIN_CHECKIN = range(14, 17)
TOGGLE_ANNOUNCE_AUTH = 17

# Timeout duration in seconds (3 minutes)
CONVERSATION_TIMEOUT = 180

# Initialize CSV and MOTD files
def init_files():
    files_to_init = [
        (CSV_FILE, CSV_HEADERS),
        (WEATHER_CSV_FILE, WEATHER_CSV_HEADERS),
        (CHECKIN_HISTORY_FILE, CHECKIN_HISTORY_HEADERS),
        (DAILY_SNAPSHOT_FILE, DAILY_SNAPSHOT_HEADERS)
    ]
    
    for file_path, headers in files_to_init:
        if not os.path.exists(file_path):
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
    
    if not os.path.exists(MOTD_FILE):
        with open(MOTD_FILE, 'w', encoding='utf-8') as f:
            f.write("Welcome to the slopes! Have an amazing day!")
    
    # Initialize announce toggle file (default: ON)
    if not os.path.exists(ANNOUNCE_TOGGLE_FILE):
        with open(ANNOUNCE_TOGGLE_FILE, 'w', encoding='utf-8') as f:
            f.write("ON")

# Read and write MOTD
def read_motd():
    if os.path.exists(MOTD_FILE):
        with open(MOTD_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()
    return "Welcome to the slopes! Have an amazing day!"

def write_motd(message):
    with open(MOTD_FILE, 'w', encoding='utf-8') as f:
        f.write(message)

# Read and write announce toggle
def read_announce_toggle():
    """Read announcement toggle status (ON/OFF)"""
    if os.path.exists(ANNOUNCE_TOGGLE_FILE):
        with open(ANNOUNCE_TOGGLE_FILE, 'r', encoding='utf-8') as f:
            status = f.read().strip().upper()
            return status == "ON"
    return True  # Default to ON

def write_announce_toggle(enabled):
    """Write announcement toggle status"""
    with open(ANNOUNCE_TOGGLE_FILE, 'w', encoding='utf-8') as f:
        f.write("ON" if enabled else "OFF")

# Generic CSV read/write functions
def read_csv_file(file_path):
    """Generic CSV reader"""
    data = []
    if os.path.exists(file_path):
        with open(file_path, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = list(reader)
    return data

def write_csv_file(file_path, headers, data):
    """Generic CSV writer"""
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for record in data:
            writer.writerow(record)

# Daily snapshot functions
def read_daily_snapshots():
    return read_csv_file(DAILY_SNAPSHOT_FILE)

def write_daily_snapshots(snapshots):
    write_csv_file(DAILY_SNAPSHOT_FILE, DAILY_SNAPSHOT_HEADERS, snapshots)

def add_daily_snapshot(user_id, mountain, username):
    """Add a daily snapshot record for today"""
    snapshots = read_daily_snapshots()
    today = datetime.now(pytz.timezone('America/Denver')).strftime('%Y-%m-%d')
    
    # Remove any existing snapshot for this user today
    snapshots = [s for s in snapshots if not (s['user_id'] == str(user_id) and s['date'] == today)]
    
    # Add new snapshot
    snapshots.append({
        'user_id': str(user_id),
        'date': today,
        'mountain': mountain,
        'username': username
    })
    
    write_daily_snapshots(snapshots)
    logger.info(f"Daily snapshot recorded: User {user_id} ({username}) at {mountain} on {today}")

def get_user_daily_stats(user_id):
    """Get daily snapshot statistics for a user"""
    snapshots = read_daily_snapshots()
    user_snapshots = [s for s in snapshots if s['user_id'] == str(user_id)]
    
    if not user_snapshots:
        return None
    
    # Count by mountain
    mountain_counts = {}
    for snapshot in user_snapshots:
        mountain = snapshot['mountain']
        mountain_counts[mountain] = mountain_counts.get(mountain, 0) + 1
    
    return {
        'total_days': len(user_snapshots),
        'mountain_counts': mountain_counts,
        'snapshots': user_snapshots
    }

# Check-in history functions
def read_checkin_history():
    return read_csv_file(CHECKIN_HISTORY_FILE)

def write_checkin_history(history):
    write_csv_file(CHECKIN_HISTORY_FILE, CHECKIN_HISTORY_HEADERS, history)

def add_checkin_record(user_id, mountain):
    """Add a check-in record with timestamp"""
    history = read_checkin_history()
    mountain_tz = pytz.timezone('America/Denver')
    now = datetime.now(mountain_tz)
    today = now.strftime('%Y-%m-%d')
    checkin_time = now.strftime('%Y-%m-%d %H:%M:%S')
    
    # Remove any existing check-in for this user today
    history = [h for h in history if not (h['user_id'] == str(user_id) and h['date'] == today)]
    
    # Add new check-in with timestamp
    history.append({
        'user_id': str(user_id),
        'date': today,
        'mountain': mountain,
        'checkin_time': checkin_time
    })
    
    write_checkin_history(history)

def get_user_checkin_stats(user_id):
    """Get check-in statistics for a user"""
    history = read_checkin_history()
    user_checkins = [h for h in history if h['user_id'] == str(user_id)]
    
    if not user_checkins:
        return None
    
    # Count by mountain
    mountain_counts = {}
    for checkin in user_checkins:
        mountain = checkin['mountain']
        mountain_counts[mountain] = mountain_counts.get(mountain, 0) + 1
    
    return {
        'total_days': len(user_checkins),
        'mountain_counts': mountain_counts,
        'checkins': user_checkins
    }

# User database functions
def read_users():
    users = {}
    if os.path.exists(CSV_FILE):
        with open(CSV_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Ensure checkin_timestamp field exists for backward compatibility
                if 'checkin_timestamp' not in row:
                    row['checkin_timestamp'] = ''
                users[row['user_id']] = row
    return users

def write_users(users):
    with open(CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
        for user_data in users.values():
            writer.writerow(user_data)

def get_user(user_id):
    users = read_users()
    return users.get(str(user_id))

def save_user(user_id, username, pass_holder, skill_level, type_rider, active_mountain='', checkin_timestamp=''):
    users = read_users()
    users[str(user_id)] = {
        'user_id': str(user_id),
        'username': username,
        'passHolder': pass_holder,
        'skillLevel': skill_level,
        'typeRider': type_rider,
        'activeMountain': active_mountain,
        'checkin_timestamp': checkin_timestamp,
        'checkin_history': ''
    }
    write_users(users)

def update_user_profile(user_id, pass_holder=None, skill_level=None, type_rider=None):
    users = read_users()
    user_key = str(user_id)
    if user_key in users:
        if pass_holder is not None:
            users[user_key]['passHolder'] = pass_holder
        if skill_level is not None:
            users[user_key]['skillLevel'] = skill_level
        if type_rider is not None:
            users[user_key]['typeRider'] = type_rider
        write_users(users)

def update_active_mountain(user_id, mountain):
    users = read_users()
    mountain_tz = pytz.timezone('America/Denver')
    if str(user_id) in users:
        users[str(user_id)]['activeMountain'] = mountain
        # Set timestamp when checking in, clear when checking out
        if mountain:
            users[str(user_id)]['checkin_timestamp'] = datetime.now(mountain_tz).strftime('%Y-%m-%d %H:%M:%S')
        else:
            users[str(user_id)]['checkin_timestamp'] = ''
        write_users(users)

def delete_user(user_id):
    users = read_users()
    if str(user_id) in users:
        del users[str(user_id)]
        write_users(users)

# Weather functions
def read_weather():
    weather_data = {}
    if os.path.exists(WEATHER_CSV_FILE):
        with open(WEATHER_CSV_FILE, 'r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                weather_data[row['mountain_name']] = row
    return weather_data

def write_weather(weather_data):
    with open(WEATHER_CSV_FILE, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=WEATHER_CSV_HEADERS)
        writer.writeheader()
        for data in weather_data.values():
            writer.writerow(data)

def fetch_mountain_weather(mountain_name, lat, lon):
    """Fetch weather data from Open-Meteo API"""
    try:
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            'latitude': lat,
            'longitude': lon,
            'current': 'temperature_2m,precipitation,snowfall,weather_code',
            'daily': 'temperature_2m_max,temperature_2m_min,snowfall_sum',
            'temperature_unit': 'fahrenheit',
            'timezone': 'America/Denver',
            'forecast_days': 1
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        current = data.get('current', {})
        daily = data.get('daily', {})
        
        temp_current = current.get('temperature_2m', 'N/A')
        temp_low = daily.get('temperature_2m_min', [None])[0] or 'N/A'
        temp_high = daily.get('temperature_2m_max', [None])[0] or 'N/A'
        snowfall_12hr = current.get('snowfall', 0)
        weather_code = current.get('weather_code', 0)
        
        # Determine if it's snowing based on weather code
        snowing_codes = [71, 73, 75, 77, 85, 86]
        is_snowing = 'Yes' if weather_code in snowing_codes else 'No'
        
        # Weather description based on code
        weather_descriptions = {
            0: 'Clear sky', 1: 'Mainly clear', 2: 'Partly cloudy', 3: 'Overcast',
            45: 'Foggy', 48: 'Rime fog', 51: 'Light drizzle', 53: 'Moderate drizzle',
            55: 'Dense drizzle', 56: 'Freezing drizzle', 57: 'Freezing drizzle',
            61: 'Slight rain', 63: 'Moderate rain', 65: 'Heavy rain',
            66: 'Freezing rain', 67: 'Freezing rain', 71: 'Slight snow',
            73: 'Moderate snow', 75: 'Heavy snow', 77: 'Snow grains',
            80: 'Slight rain showers', 81: 'Moderate showers', 82: 'Violent showers',
            85: 'Slight snow showers', 86: 'Heavy snow showers',
            95: 'Thunderstorm', 96: 'Thunderstorm with hail', 99: 'Thunderstorm with hail'
        }
        description = weather_descriptions.get(weather_code, 'Unknown')
        
        # Format snowfall
        if isinstance(snowfall_12hr, (int, float)):
            snowfall_display = f"{snowfall_12hr:.1f}"
        else:
            snowfall_display = "N/A"
        
        return {
            'mountain_name': mountain_name,
            'temp_low': str(temp_low),
            'temp_high': str(temp_high),
            'temp_current': str(temp_current),
            'description': description,
            'snowfall_12hr': snowfall_display,
            'is_snowing': is_snowing,
            'last_updated': datetime.now(pytz.timezone('America/Denver')).strftime('%Y-%m-%d %H:%M:%S')
        }
    
    except Exception as e:
        logger.error(f"Error fetching weather for {mountain_name}: {e}")
        return {
            'mountain_name': mountain_name,
            'temp_low': 'N/A',
            'temp_high': 'N/A',
            'temp_current': 'N/A',
            'description': 'Error fetching weather',
            'snowfall_12hr': 'N/A',
            'is_snowing': 'No',
            'last_updated': datetime.now(pytz.timezone('America/Denver')).strftime('%Y-%m-%d %H:%M:%S')
        }

def get_skill_emoji(skill_level):
    """Return emoji for skill level"""
    emoji_map = {
        'Beginner': '🟢',
        'Intermediate': '🔵',
        'Advanced': '⚫',
        'Expert': '💎'
    }
    return emoji_map.get(skill_level, '❓')

# Helper function to categorize mountains
def categorize_users_by_mountain(users, active_only=False):
    """Categorize users by mountain type (Epic/Ikon/Loveland)"""
    epic_list = []
    ikon_list = []
    loveland_list = []
    
    for user_data in users.values():
        mountain = user_data.get('activeMountain', '')
        
        if active_only and not mountain:
            continue
        
        if mountain and mountain != 'None':
            skill_emoji = get_skill_emoji(user_data['skillLevel'])
            user_info = f"👤 {user_data['username']} | {skill_emoji} | {user_data['typeRider']} | 🏔{mountain}"
            
            if mountain in EPM_MOUNTAINS:
                epic_list.append(user_info)
            elif mountain in IPM_MOUNTAINS:
                ikon_list.append(user_info)
            elif mountain in LOVELAND_MOUNTAINS:
                loveland_list.append(user_info)
    
    return epic_list, ikon_list, loveland_list

# Helper function to build mountain message
def build_mountain_message(epic_list, ikon_list, loveland_list, title, empty_message="No riders are currently at any mountains."):
    """Build a formatted message for mountain listings"""
    if not epic_list and not ikon_list and not loveland_list:
        return empty_message
    
    message = f"{title}\n\n"
    
    if epic_list:
        message += "⛷️ **EPIC MOUNTAINS:**\n" + "\n".join(epic_list) + "\n\n"
    
    if ikon_list:
        message += "🎿 **IKON MOUNTAINS:**\n" + "\n".join(ikon_list) + "\n\n"
    
    if loveland_list:
        message += "❤️ **LOVELAND:**\n" + "\n".join(loveland_list) + "\n"
    
    return message.strip()

async def update_pass_keyboard(selected_passes, callback_prefix, continue_callback):
    """Generate keyboard for pass selection"""
    pass_options = ['Epic', 'Ikon', 'Loveland', 'None']
    keyboard = []
    
    for pass_option in pass_options:
        if pass_option in selected_passes:
            button_text = f"✅ {pass_option}"
        else:
            button_text = f"⬜ {pass_option}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f'{callback_prefix}{pass_option}')])
    
    keyboard.append([InlineKeyboardButton('➡️ Continue', callback_data=continue_callback)])
    return InlineKeyboardMarkup(keyboard)

async def send_private_message(update: Update, context: ContextTypes.DEFAULT_TYPE, message: str, reply_markup=None):
    """Send message only in private chat"""
    if update.message:
        chat_type = update.message.chat.type
        if chat_type == 'private':
            if reply_markup:
                await update.message.reply_text(message, reply_markup=reply_markup)
            else:
                await update.message.reply_text(message)
        else:
            try:
                if reply_markup:
                    await context.bot.send_message(chat_id=update.effective_user.id, text=message, reply_markup=reply_markup)
                else:
                    await context.bot.send_message(chat_id=update.effective_user.id, text=message)
                await update.message.reply_text("I've sent you a private message!")
            except Exception as e:
                await update.message.reply_text("Please start a private chat with me first by clicking my name and pressing 'Start'.")
                logger.error(f"Could not send PM: {e}")
    elif update.callback_query:
        if reply_markup:
            await update.callback_query.message.reply_text(message, reply_markup=reply_markup)
        else:
            await update.callback_query.message.reply_text(message)

async def timeout_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle conversation timeout"""
    if update.message:
        await update.message.reply_text(
            "⏰ This conversation has timed out due to inactivity.\n"
            "Please start again with the appropriate command."
        )
    return ConversationHandler.END

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        '🎿 Welcome to the Ski Bot! 🏔️\n\n'
        'Use /addProfile to get started or /commands to see all available commands.'
    )

async def add_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    existing_user = get_user(user_id)
    
    if existing_user:
        message = (
            "⚠️ You already have a profile!\n\n"
            "Use /editProfile to update your information."
        )
        await send_private_message(update, context, message)
        return ConversationHandler.END
    
    context.user_data['selected_passes'] = set()
    keyboard = await update_pass_keyboard(set(), 'pass_', 'pass_continue')
    
    message = (
        "🎿 **PROFILE CREATION** 🎿\n\n"
        "Select your season pass(es):\n"
        "(You can select multiple passes)"
    )
    
    await send_private_message(update, context, message, keyboard)
    return PASS_SELECT

async def edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data:
        message = (
            "❌ You don't have a profile yet!\n\n"
            "Use /addProfile to create one first."
        )
        await send_private_message(update, context, message)
        return ConversationHandler.END
    
    current_passes = user_data['passHolder'].split(', ')
    context.user_data['selected_passes'] = set(current_passes)
    context.user_data['edit_mode'] = True
    
    keyboard = await update_pass_keyboard(context.user_data['selected_passes'], 'edit_pass_', 'edit_pass_continue')
    
    message = (
        "✏️ **EDIT YOUR PROFILE** ✏️\n\n"
        f"**Current Pass(es):** {user_data['passHolder']}\n"
        f"**Current Skill:** {user_data['skillLevel']}\n"
        f"**Current Type:** {user_data['typeRider']}\n\n"
        "Select your season pass(es):"
    )
    
    await send_private_message(update, context, message, keyboard)
    return EDIT_PASS_SELECT

async def edit_pass_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    pass_type = query.data.replace('edit_pass_', '')
    
    if pass_type == 'continue':
        if not context.user_data.get('selected_passes'):
            await query.edit_message_text(
                "⚠️ Please select at least one pass option before continuing."
            )
            return EDIT_PASS_SELECT
        
        passes_str = ', '.join(sorted(context.user_data['selected_passes']))
        
        keyboard = [
            [InlineKeyboardButton('🟢 Beginner', callback_data='edit_skill_Beginner')],
            [InlineKeyboardButton('🔵 Intermediate', callback_data='edit_skill_Intermediate')],
            [InlineKeyboardButton('⚫ Advanced', callback_data='edit_skill_Advanced')],
            [InlineKeyboardButton('💎 Expert', callback_data='edit_skill_Expert')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Selected Pass(es): {passes_str}\n\n"
            "What's your skill level?",
            reply_markup=reply_markup
        )
        return EDIT_SKILL_SELECT
    
    # Toggle pass selection
    if pass_type == 'None':
        context.user_data['selected_passes'] = {'None'}
    elif pass_type in context.user_data['selected_passes']:
        context.user_data['selected_passes'].discard(pass_type)
    else:
        context.user_data['selected_passes'].discard('None')
        context.user_data['selected_passes'].add(pass_type)
    
    keyboard = await update_pass_keyboard(context.user_data['selected_passes'], 'edit_pass_', 'edit_pass_continue')
    await query.edit_message_reply_markup(reply_markup=keyboard)
    return EDIT_PASS_SELECT

async def edit_skill_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    skill = query.data.replace('edit_skill_', '')
    context.user_data['skill_level'] = skill
    
    keyboard = [
        [InlineKeyboardButton('⛷️ Skier', callback_data='edit_rider_Skier')],
        [InlineKeyboardButton('🏂 Snowboarder', callback_data='edit_rider_Snowboarder')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Skill Level: {skill}\n\n"
        "Are you a skier or snowboarder?",
        reply_markup=reply_markup
    )
    return EDIT_RIDER_SELECT

async def edit_rider_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    rider_type = query.data.replace('edit_rider_', '')
    user_id = update.effective_user.id
    
    passes_str = ', '.join(sorted(context.user_data['selected_passes']))
    skill = context.user_data['skill_level']
    
    update_user_profile(user_id, passes_str, skill, rider_type)
    
    await query.edit_message_text(
        f'✅ **Profile Updated!**\n\n'
        f'Pass(es): {passes_str}\n'
        f'Skill: {skill}\n'
        f'Type: {rider_type}\n\n'
        f'Use /skiing or /boarding to check in to a mountain!'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def pass_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    pass_type = query.data.replace('pass_', '')
    
    if pass_type == 'continue':
        if not context.user_data.get('selected_passes'):
            await query.edit_message_text(
                "⚠️ Please select at least one pass option before continuing."
            )
            return PASS_SELECT
        
        passes_str = ', '.join(sorted(context.user_data['selected_passes']))
        context.user_data['pass_holder'] = passes_str
        
        keyboard = [
            [InlineKeyboardButton('🟢 Beginner', callback_data='skill_Beginner')],
            [InlineKeyboardButton('🔵 Intermediate', callback_data='skill_Intermediate')],
            [InlineKeyboardButton('⚫ Advanced', callback_data='skill_Advanced')],
            [InlineKeyboardButton('💎 Expert', callback_data='skill_Expert')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Selected Pass(es): {passes_str}\n\n"
            "What's your skill level?",
            reply_markup=reply_markup
        )
        return SKILL_SELECT
    
    # Toggle pass selection
    if pass_type == 'None':
        context.user_data['selected_passes'] = {'None'}
    elif pass_type in context.user_data['selected_passes']:
        context.user_data['selected_passes'].discard(pass_type)
    else:
        context.user_data['selected_passes'].discard('None')
        context.user_data['selected_passes'].add(pass_type)
    
    keyboard = await update_pass_keyboard(context.user_data['selected_passes'], 'pass_', 'pass_continue')
    await query.edit_message_reply_markup(reply_markup=keyboard)
    return PASS_SELECT

async def skill_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    skill = query.data.replace('skill_', '')
    context.user_data['skill_level'] = skill
    
    keyboard = [
        [InlineKeyboardButton('⛷️ Skier', callback_data='rider_Skier')],
        [InlineKeyboardButton('🏂 Snowboarder', callback_data='rider_Snowboarder')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"Skill Level: {skill}\n\n"
        "Are you a skier or snowboarder?",
        reply_markup=reply_markup
    )
    return RIDER_SELECT

async def rider_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    rider_type = query.data.replace('rider_', '')
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    pass_holder = context.user_data['pass_holder']
    skill = context.user_data['skill_level']
    
    save_user(user_id, username, pass_holder, skill, rider_type)
    
    await query.edit_message_text(
        f'✅ **Profile Created!**\n\n'
        f'Username: {username}\n'
        f'Pass(es): {pass_holder}\n'
        f'Skill: {skill}\n'
        f'Type: {rider_type}\n\n'
        f'Use /skiing or /boarding to check in to a mountain!'
    )
    
    context.user_data.clear()
    return ConversationHandler.END

async def temp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display current temperatures for all mountains"""
    weather_data = read_weather()
    
    if not weather_data:
        await update.message.reply_text(
            "⚠️ No weather data available.\n"
            "Use /weatherUpdate to fetch the latest data."
        )
        return
    
    message = "🌡️ **CURRENT TEMPERATURES** 🌡️\n\n"
    
    # Group mountains by pass type
    mountain_groups = [
        ("⛷️ **EPIC RESORTS:**\n", EPM_MOUNTAINS),
        ("🎿 **IKON RESORTS:**\n", IPM_MOUNTAINS),
        ("❤️ **LOVELAND:**\n", LOVELAND_MOUNTAINS)
    ]
    
    for header, mountains in mountain_groups:
        message += header
        for mountain in mountains:
            if mountain in weather_data:
                w = weather_data[mountain]
                message += f"  🏔️ {mountain}: {w['temp_current']}°F\n"
        message += "\n"
    
    await update.message.reply_text(message)

async def view_mountain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View who's at specific mountains with check-in option"""
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data:
        message = (
            "❌ You need a profile first!\n\n"
            "Use /addProfile to create your profile."
        )
        await send_private_message(update, context, message)
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton('⛷️ Epic Mountains', callback_data='view_mount_Epic')],
        [InlineKeyboardButton('🎿 Ikon Mountains', callback_data='view_mount_Ikon')],
        [InlineKeyboardButton('❤️ Loveland', callback_data='view_mount_Loveland')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_private_message(
        update,
        context,
        "🏔️ **VIEW MOUNTAIN RIDERS** 🏔️\n\n"
        "Which mountain pass would you like to view?",
        reply_markup
    )
    return VIEW_MOUNTAIN_PASS_SELECT

async def view_mountain_pass_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    pass_type = query.data.replace('view_mount_', '')
    context.user_data['view_pass_type'] = pass_type
    
    # Select mountains based on pass
    if pass_type == 'Epic':
        mountains = EPM_MOUNTAINS
        emoji = '⛷️'
    elif pass_type == 'Ikon':
        mountains = IPM_MOUNTAINS
        emoji = '🎿'
    else:  # Loveland
        mountains = LOVELAND_MOUNTAINS
        emoji = '❤️'
    
    # Build keyboard with mountain options
    keyboard = []
    for mountain in mountains:
        keyboard.append([InlineKeyboardButton(f'{emoji} {mountain}', callback_data=f'view_mountain_{mountain}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"{emoji} **{pass_type.upper()} MOUNTAINS** {emoji}\n\n"
        "Select a mountain to view riders:",
        reply_markup=reply_markup
    )
    return VIEW_MOUNTAIN_SELECT

async def view_mountain_checkin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    action = query.data.replace('view_checkin_', '')
    
    if action == 'yes':
        user_id = update.effective_user.id
        mountain = context.user_data.get('selected_mountain')
        username = update.effective_user.username or update.effective_user.first_name
        
        update_active_mountain(user_id, mountain)
        add_checkin_record(user_id, mountain)
        
        await query.edit_message_text(
            f"✅ **Checked in to {mountain}!**\n\n"
            f"Have an amazing day on the slopes! 🎿"
        )
    else:
        await query.edit_message_text(
            "👍 No problem! Enjoy browsing who's riding."
        )
    
    context.user_data.clear()
    return ConversationHandler.END

async def view_mountain_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    mountain = query.data.replace('view_mountain_', '')
    users = read_users()
    
    riders_at_mountain = []
    for user_data in users.values():
        if user_data.get('activeMountain') == mountain:
            skill_emoji = get_skill_emoji(user_data['skillLevel'])
            riders_at_mountain.append(
                f"👤 {user_data['username']} | {skill_emoji} {user_data['skillLevel']} | {user_data['typeRider']}"
            )
    
    if riders_at_mountain:
        message = f"🏔️ **RIDERS AT {mountain.upper()}** 🏔️\n\n"
        message += "\n".join(riders_at_mountain)
    else:
        message = f"🏔️ **{mountain.upper()}** 🏔️\n\nNo riders currently checked in."
    
    # Ask if user wants to check in
    keyboard = [
        [InlineKeyboardButton('✅ Check In Here', callback_data='view_checkin_yes')],
        [InlineKeyboardButton('❌ Just Viewing', callback_data='view_checkin_no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    context.user_data['selected_mountain'] = mountain
    
    message += "\n\nWould you like to check in to this mountain?"
    
    await query.edit_message_text(message, reply_markup=reply_markup)
    return VIEW_MOUNTAIN_CHECKIN

async def set_mountain(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data:
        message = (
            "❌ You need to create a profile first!\n\n"
            "Use /addProfile to get started."
        )
        await send_private_message(update, context, message)
        return ConversationHandler.END
    
    keyboard = [
        [InlineKeyboardButton('⛷️ Epic Mountains', callback_data='mount_Epic')],
        [InlineKeyboardButton('🎿 Ikon Mountains', callback_data='mount_Ikon')],
        [InlineKeyboardButton('❤️ Loveland', callback_data='mount_Loveland')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await send_private_message(
        update,
        context,
        "🏔️ **CHECK IN TO A MOUNTAIN** 🏔️\n\n"
        "Which mountain pass?",
        reply_markup
    )
    return MOUNTAIN_PASS_SELECT

async def mountain_pass_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    pass_type = query.data.replace('mount_', '')
    await show_mountain_selection(update, context, pass_type, query)
    return MOUNTAIN_SELECT

async def show_mountain_selection(update, context, pass_type, query=None):
    """Display mountain selection based on pass type"""
    if pass_type == 'Epic':
        mountains = EPM_MOUNTAINS
        emoji = '⛷️'
    elif pass_type == 'Ikon':
        mountains = IPM_MOUNTAINS
        emoji = '🎿'
    else:  # Loveland
        mountains = LOVELAND_MOUNTAINS
        emoji = '❤️'
    
    keyboard = []
    for mountain in mountains:
        keyboard.append([InlineKeyboardButton(f'{emoji} {mountain}', callback_data=f'mountain_{mountain}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(
            f"{emoji} **SELECT YOUR MOUNTAIN** {emoji}",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"{emoji} **SELECT YOUR MOUNTAIN** {emoji}",
            reply_markup=reply_markup
        )

async def mountain_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    mountain = query.data.replace('mountain_', '')
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    update_active_mountain(user_id, mountain)
    add_checkin_record(user_id, mountain)
    
    context.user_data['current_mountain'] = mountain
    context.user_data['checked_in_user'] = username
    
    keyboard = [
        [InlineKeyboardButton('✅ Yes, check them in', callback_data='buddy_confirm_yes')],
        [InlineKeyboardButton('❌ No, just me', callback_data='buddy_confirm_no')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"✅ **Checked in to {mountain}!**\n\n"
        f"Have fun out there! 🎿\n\n"
        f"Are there any buddies with you that you'd like to check in?",
        reply_markup=reply_markup
    )
    return BUDDY_CHECKIN_CONFIRM

async def buddy_checkin_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    choice = query.data.replace('buddy_confirm_', '')
    
    if choice == 'no':
        await query.edit_message_text(
            "👍 All set! Have an amazing day on the mountain! 🏔️"
        )
        context.user_data.clear()
        return ConversationHandler.END
    
    # Show buddy selection
    await show_buddy_selection(query, context)
    return BUDDY_SELECT

async def show_buddy_selection(query, context, available_users=None):
    """Show list of users to check in as buddies"""
    if available_users is None:
        users = read_users()
        current_user_id = query.from_user.id
        current_mountain = context.user_data.get('current_mountain')
        
        available_users = []
        for user_id, user_data in users.items():
            if user_id != str(current_user_id):
                is_selected = user_id in context.user_data.get('selected_buddies', set())
                available_users.append({
                    'user_id': user_id,
                    'username': user_data['username'],
                    'is_selected': is_selected
                })
    
    keyboard = []
    for user in available_users:
        checkbox = '✅' if user['is_selected'] else '⬜'
        keyboard.append([
            InlineKeyboardButton(
                f"{checkbox} {user['username']}",
                callback_data=f"buddy_toggle_{user['user_id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton('✅ Check In Selected', callback_data='buddy_checkin_selected')])
    keyboard.append([InlineKeyboardButton('❌ Cancel', callback_data='buddy_cancel')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message = "👥 **SELECT BUDDIES TO CHECK IN**\n\n"
    message += f"Mountain: {context.user_data.get('current_mountain')}\n\n"
    message += "Select all buddies who are with you:"
    
    await query.edit_message_text(message, reply_markup=reply_markup)

async def buddy_select_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == 'buddy_cancel':
        await query.edit_message_text("👍 Buddy check-in cancelled.")
        context.user_data.clear()
        return ConversationHandler.END
    
    if data == 'buddy_checkin_selected':
        selected_buddies = context.user_data.get('selected_buddies', set())
        
        if not selected_buddies:
            await query.answer("Please select at least one buddy!", show_alert=True)
            return BUDDY_SELECT
        
        mountain = context.user_data.get('current_mountain')
        checked_in_names = []
        
        for buddy_id in selected_buddies:
            update_active_mountain(int(buddy_id), mountain)
            add_checkin_record(int(buddy_id), mountain)
            user_data = get_user(int(buddy_id))
            if user_data:
                checked_in_names.append(user_data['username'])
        
        await query.edit_message_text(
            f"✅ **Buddies Checked In!**\n\n"
            f"The following riders have been checked in to {mountain}:\n"
            f"• " + "\n• ".join(checked_in_names) + "\n\n"
            f"Have an amazing day together! 🎿🏂"
        )
        
        context.user_data.clear()
        return ConversationHandler.END
    
    # Toggle buddy selection
    if data.startswith('buddy_toggle_'):
        buddy_id = data.replace('buddy_toggle_', '')
        
        if 'selected_buddies' not in context.user_data:
            context.user_data['selected_buddies'] = set()
        
        if buddy_id in context.user_data['selected_buddies']:
            context.user_data['selected_buddies'].remove(buddy_id)
        else:
            context.user_data['selected_buddies'].add(buddy_id)
        
        await show_buddy_selection(query, context)
        return BUDDY_SELECT

# Consolidated list function for mountain types
async def list_by_mountain_type(update: Update, context: ContextTypes.DEFAULT_TYPE, mountain_list, mountain_name, emoji):
    """Generic function to list riders at specific mountain type"""
    users = read_users()
    active_riders = []
    
    for user_data in users.values():
        mountain = user_data.get('activeMountain', '')
        if mountain and mountain in mountain_list:
            skill_emoji = get_skill_emoji(user_data['skillLevel'])
            user_info = f"👤 {user_data['username']} | {skill_emoji} | {user_data['typeRider']} | 🏔{mountain}"
            active_riders.append(user_info)
    
    if not active_riders:
        await update.message.reply_text(f'No riders currently checked in at {mountain_name}.')
        return
    
    message = f"{emoji} **RIDERS AT {mountain_name.upper()}:**\n\n"
    message += "\n".join(active_riders)
    
    await update.message.reply_text(message)

async def list_active(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List only users who are actively on a mountain"""
    users = read_users()
    
    if not users:
        await update.message.reply_text('No users registered yet.')
        return
    
    epic_list, ikon_list, loveland_list = categorize_users_by_mountain(users, active_only=True)
    
    if not epic_list and not ikon_list and not loveland_list:
        await update.message.reply_text('No riders are currently at any mountains.')
        return
    
    message = build_mountain_message(epic_list, ikon_list, loveland_list, "🏔️ **ACTIVE RIDERS ON MOUNTAINS**")
    await update.message.reply_text(message)

async def list_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = read_users()
    
    if not users:
        await send_private_message(update, context, 'No users registered yet.')
        return
    
    epic_users = []
    ikon_users = []
    loveland_users = []
    
    for user_data in users.values():
        mountain = user_data['activeMountain'] or 'None'
        skill_emoji = get_skill_emoji(user_data['skillLevel'])
        user_info = f"👤 {user_data['username']} | {skill_emoji} | {user_data['typeRider']} | 🏔{mountain}"
        
        if mountain in EPM_MOUNTAINS:
            epic_users.append(user_info)
        elif mountain in IPM_MOUNTAINS:
            ikon_users.append(user_info)
        elif mountain in LOVELAND_MOUNTAINS:
            loveland_users.append(user_info)
        else:
            # Categorize by pass holder
            pass_holder = user_data['passHolder']
            passes = [p.strip() for p in pass_holder.split(',')]
            
            for p in passes:
                p_lower = p.lower()
                if 'epic' in p_lower and user_info not in epic_users:
                    epic_users.append(user_info)
                if 'ikon' in p_lower and user_info not in ikon_users:
                    ikon_users.append(user_info)
                if 'loveland' in p_lower and user_info not in loveland_users:
                    loveland_users.append(user_info)
    
    message = build_mountain_message(epic_users, ikon_users, loveland_users, "📋 **ALL REGISTERED USERS**")
    await send_private_message(update, context, message)

async def list_ikon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all people currently checked into Ikon mountains"""
    await list_by_mountain_type(update, context, IPM_MOUNTAINS, "Ikon Mountains", "🎿")

async def list_epic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all people currently checked into Epic mountains"""
    await list_by_mountain_type(update, context, EPM_MOUNTAINS, "Epic Mountains", "⛷️")

async def list_loveland(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all people currently checked into Loveland"""
    await list_by_mountain_type(update, context, LOVELAND_MOUNTAINS, "Loveland", "❤️")

async def announcement(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = read_users()
    
    if not users:
        await update.message.reply_text('No users registered.')
        return
    
    epic_active = []
    ikon_active = []
    loveland_active = []
    
    for user_data in users.values():
        mountain = user_data['activeMountain']
        
        if mountain:
            user_info = (
                f"👤 {user_data['username']}\n"
                f"  Mountain: {mountain}\n"
                f"  Skill: {user_data['skillLevel']}\n"
            )
            
            if mountain in EPM_MOUNTAINS:
                epic_active.append(user_info)
            elif mountain in IPM_MOUNTAINS:
                ikon_active.append(user_info)
            elif mountain in LOVELAND_MOUNTAINS:
                loveland_active.append(user_info)
    
    message = "🏔️ **RIDERS ON MOUNTAINS TODAY** 🏔️\n\n"
    
    if epic_active:
        message += "⛷️ **EPIC MOUNTAINS:**\n" + "\n".join(epic_active) + "\n\n"
    
    if ikon_active:
        message += "🎿 **IKON MOUNTAINS:**\n" + "\n".join(ikon_active) + "\n\n"
    
    if loveland_active:
        message += "❤️ **LOVELAND:**\n" + "\n".join(loveland_active) + "\n"
    
    if not epic_active and not ikon_active and not loveland_active:
        message += "No riders are currently at any mountains."
    
    await update.message.reply_text(message)

async def weather_update(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Manually update weather data with current temperatures"""
    await update.message.reply_text("🔄 Updating weather data... Please wait...")
    
    weather_data = {}
    all_mountains = EPM_MOUNTAINS + IPM_MOUNTAINS + LOVELAND_MOUNTAINS
    
    for mountain in all_mountains:
        if mountain in MOUNTAIN_COORDS:
            lat, lon = MOUNTAIN_COORDS[mountain]
            weather_info = fetch_mountain_weather(mountain, lat, lon)
            weather_data[mountain] = weather_info
            logger.info(f"Fetched weather for {mountain}")
    
    write_weather(weather_data)
    
    message = "✅ **Weather Updated Successfully!**\n\n"
    
    # Display weather for all mountain groups
    mountain_groups = [
        ("⛷️ **EPIC RESORTS:**\n\n", EPM_MOUNTAINS),
        ("🎿 **IKON RESORTS:**\n\n", IPM_MOUNTAINS),
        ("❤️ **LOVELAND:**\n\n", LOVELAND_MOUNTAINS)
    ]
    
    for header, mountains in mountain_groups:
        message += header
        for mountain in mountains:
            if mountain in weather_data:
                w = weather_data[mountain]
                snowfall = w['snowfall_12hr']
                
                if snowfall != 'N/A' and float(snowfall) >= 3.0:
                    snow_display = f"🔥 **{snowfall} in** 🔥"
                else:
                    snow_display = f"{snowfall} in"
                
                snow_indicator = "❄️ SNOWING!" if w['is_snowing'] == 'Yes' else ""
                
                message += (
                    f"🏔️ **{mountain}**\n"
                    f"  🌡️ Current: {w['temp_current']}°F {snow_indicator}\n"
                    f"  🌡️ Range: {w['temp_low']}°F - {w['temp_high']}°F\n"
                    f"  ❄️ Snow (12hr): {snow_display}\n"
                    f"  📍 {w['description']}\n\n"
                )
    
    await update.message.reply_text(message)

async def weather(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Display current weather conditions for all mountains"""
    weather_data = read_weather()
    
    if not weather_data:
        await update.message.reply_text(
            "⚠️ No weather data available.\n"
            "Use /weatherUpdate to fetch the latest data."
        )
        return
    
    message = "🌨️ **CURRENT WEATHER CONDITIONS** 🌨️\n\n"
    
    # Display weather for all mountain groups
    mountain_groups = [
        ("⛷️ **EPIC RESORTS:**\n\n", EPM_MOUNTAINS),
        ("🎿 **IKON RESORTS:**\n\n", IPM_MOUNTAINS),
        ("❤️ **LOVELAND:**\n\n", LOVELAND_MOUNTAINS)
    ]
    
    for header, mountains in mountain_groups:
        message += header
        for mountain in mountains:
            if mountain in weather_data:
                w = weather_data[mountain]
                snowfall = w['snowfall_12hr']
                
                if snowfall != 'N/A' and float(snowfall) >= 3.0:
                    snow_display = f"🔥 **{snowfall} in** 🔥"
                else:
                    snow_display = f"{snowfall} in"
                
                snow_indicator = "❄️ SNOWING!" if w['is_snowing'] == 'Yes' else ""
                
                message += (
                    f"🏔️ **{mountain}**\n"
                    f"  🌡️ Current: {w['temp_current']}°F {snow_indicator}\n"
                    f"  🌡️ Range: {w['temp_low']}°F - {w['temp_high']}°F\n"
                    f"  ❄️ Snow (12hr): {snow_display}\n"
                    f"  📍 {w['description']}\n\n"
                )
    
    await update.message.reply_text(message)

async def leaving(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check out from current mountain"""
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data:
        await update.message.reply_text("❌ You don't have a profile! Use /addProfile to create one.")
        return
    
    current_mountain = user_data.get('activeMountain')
    if not current_mountain:
        await update.message.reply_text("You're not currently checked in to any mountain.")
        return
    
    update_active_mountain(user_id, '')
    await update.message.reply_text(f"👋 Checked out from {current_mountain}. Drive safe!")

async def erase_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete user's own profile"""
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data:
        await update.message.reply_text("You don't have a profile to delete.")
        return
    
    delete_user(user_id)
    await update.message.reply_text("✅ Your profile has been deleted.")

async def erase_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to delete all user profiles"""
    if update.message.chat.type != 'private':
        return ConversationHandler.END
    
    correct_answer = 13
    wrong_answers = []
    while len(wrong_answers) < 3:
        num = random.randint(1, 50)
        if num != correct_answer and num not in wrong_answers:
            wrong_answers.append(num)
    
    all_answers = wrong_answers + [correct_answer]
    random.shuffle(all_answers)
    
    keyboard = []
    for answer in all_answers:
        keyboard.append([InlineKeyboardButton(str(answer), callback_data=f'eraseall_auth_{answer}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔒 **Authentication Required**\n\n"
        "How many O's are in Rrruff's name?",
        reply_markup=reply_markup
    )
    return ERASEALL_AUTH

async def eraseall_auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle auth response for eraseAll"""
    query = update.callback_query
    await query.answer()
    
    answer = query.data.replace('eraseall_auth_', '')
    
    if answer == '13':
        users = read_users()
        user_count = len(users)
        
        if user_count == 0:
            await query.edit_message_text('⚠️ No users to delete.')
            return ConversationHandler.END
        
        context.user_data['user_count'] = user_count
        
        keyboard = [
            [InlineKeyboardButton("✅ Yes, DELETE ALL", callback_data='eraseall_confirm_yes')],
            [InlineKeyboardButton("❌ No, Cancel", callback_data='eraseall_confirm_no')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ Authentication successful!\n\n"
            f"⚠️ **WARNING: You are about to delete {user_count} user profile(s)!**\n\n"
            "This action CANNOT be undone.\n"
            "All users will need to use /addProfile again.\n\n"
            "Are you sure?",
            reply_markup=reply_markup
        )
        return ERASEALL_CONFIRM
    else:
        await query.edit_message_text("❌ Incorrect answer. Access denied.")
        return ConversationHandler.END

async def eraseall_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle final confirmation for eraseAll"""
    query = update.callback_query
    await query.answer()
    
    choice = query.data.replace('eraseall_confirm_', '')
    
    if choice == 'no':
        await query.edit_message_text("✅ Cancelled. No profiles were deleted.")
        context.user_data.clear()
        return ConversationHandler.END
    
    user_count = context.user_data.get('user_count', 0)
    user_id = update.effective_user.id
    
    write_users({})
    
    await query.edit_message_text(
        f'🗑️ **ALL PROFILES DELETED**\n\n'
        f'Removed {user_count} user profile(s).\n'
        f'All users will need to use /addProfile to register again.'
    )
    
    logger.info(f"User {user_id} executed /eraseAll - deleted {user_count} profiles")
    
    context.user_data.clear()
    return ConversationHandler.END

async def commands_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    commands_text = (
        "📋 **AVAILABLE COMMANDS:**\n\n"
        "/addProfile - Create your profile\n"
        "/editProfile - Update your profile\n"
        "/skiing or /boarding - Check in to a mountain\n"
        "/mountain - View who's at mountains (with check-in)\n"
        "/leaving - Check out from current mountain\n"
        "/temp - View current temperatures\n"
        "/weather - View weather conditions\n"
        "/weatherUpdate - Update weather data\n"
        "/listAll - List all registered users\n"
        "/listActive - List users on mountains\n"
        "/Epic - List riders at Epic mountains\n"
        "/Ikon - List riders at Ikon mountains\n"
        "/Loveland - List riders at Loveland\n"
        "/announcement - Show active riders\n"
        "/holders - List all registered users by pass type\n"
        "/days - View your mountain day history\n"
        "/eraseMe - Delete your profile\n"
        "/commands - Show this list"
    )
    
    await send_private_message(update, context, commands_text)

async def holders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all registered users and their pass selections, organized by pass type"""
    users = read_users()
    
    if not users:
        await send_private_message(update, context, "No registered users found.")
        return
    
    # Lists to hold user info by pass type
    ikon_holders = []
    epic_holders = []
    loveland_holders = []
    none_holders = []
    
    for user_data in users.values():
        username = user_data['username']
        pass_type = user_data['passHolder']
        skill = user_data.get('skillLevel', 'N/A')
        rider_type = user_data.get('typeRider', 'N/A')
        
        user_info = {
            'username': username,
            'pass': pass_type,
            'skill': skill,
            'rider': rider_type
        }
        
        passes = [p.strip() for p in pass_type.split(',')]
        
        if 'None' in passes or pass_type.lower() == 'none':
            none_holders.append(user_info)
        else:
            for p in passes:
                p_lower = p.lower()
                if 'ikon' in p_lower and user_info not in ikon_holders:
                    ikon_holders.append(user_info)
                if 'epic' in p_lower and user_info not in epic_holders:
                    epic_holders.append(user_info)
                if 'loveland' in p_lower and user_info not in loveland_holders:
                    loveland_holders.append(user_info)
    
    message = "📊 **ALL REGISTERED PASS HOLDERS**\n"
    message += "(Regardless of check-in status)\n\n"
    
    # Display in order: Ikon, Epic, Loveland
    holder_groups = [
        (ikon_holders, "🎿 **IKON PASS", "IKON PASS"),
        (epic_holders, "⛷️ **EPIC PASS", "EPIC PASS"),
        (loveland_holders, "❤️ **LOVELAND", "LOVELAND"),
        (none_holders, "❌ **NO PASS", "NO PASS")
    ]
    
    for holders, header, name in holder_groups:
        if holders:
            message += f"{header} ({len(holders)}):**\n"
            for holder in sorted(holders, key=lambda x: x['username']):
                message += f"  • {holder['username']} - {holder['skill']} {holder['rider']}\n"
            message += "\n"
    
    message += f"📋 **Total Registered Users:** {len(users)}"
    
    await send_private_message(update, context, message)

async def days_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's mountain day statistics from daily snapshots"""
    user_id = update.effective_user.id
    user_data = get_user(user_id)
    
    if not user_data:
        message = (
            "❌ You don't have a profile yet!\n\n"
            "Please use /addProfile to create one first, then get out there and shred! 🎿"
        )
        await send_private_message(update, context, message)
        return
    
    stats = get_user_daily_stats(user_id)
    
    if not stats:
        message = (
            "🏔️ **YOUR MOUNTAIN DAYS** 🏔️\n\n"
            "You haven't been recorded at any mountains yet!\n\n"
            "Get out there and shred! 🎿⛷️\n"
            "Don't forget to use /skiing or /boarding to check in when you hit the slopes!\n\n"
            "_Note: The bot records your mountain at 4:45 PM MT each day._"
        )
        await send_private_message(update, context, message)
        return
    
    message = f"🏔️ **YOUR MOUNTAIN DAYS** 🏔️\n\n"
    message += f"📊 **Total Days on Mountain:** {stats['total_days']}\n\n"
    message += "**Days by Mountain:**\n"
    
    sorted_mountains = sorted(stats['mountain_counts'].items(), key=lambda x: x[1], reverse=True)
    
    for mountain, count in sorted_mountains:
        message += f"  🏔️ {mountain}: {count} day{'s' if count != 1 else ''}\n"
    
    message += "\n**Recent Days:**\n"
    
    recent_snapshots = sorted(stats['snapshots'], key=lambda x: x['date'], reverse=True)[:10]
    
    for snapshot in recent_snapshots:
        date_obj = datetime.strptime(snapshot['date'], '%Y-%m-%d')
        formatted_date = date_obj.strftime('%b %d, %Y')
        message += f"  📅 {formatted_date} - {snapshot['mountain']}\n"
    
    if stats['total_days'] > 10:
        message += f"\n_Showing 10 most recent of {stats['total_days']} total days_"
    
    message += "\n\n_The bot records your longest check-in each day at 4:45 PM MT._"
    
    await send_private_message(update, context, message)

async def admin_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show all admin commands (hidden from regular users)"""
    
    # Get current toggle status
    announce_status = "ON" if read_announce_toggle() else "OFF"
    
    admin_commands_text = (
        "🔐 **ADMIN COMMANDS:**\n\n"
        "**User Management:**\n"
        "/eraseAll - Delete all user profiles\n"
        "/eraseMe - Delete your own profile\n\n"
        "**Check-in Management:**\n"
        "/massCheckout - Force checkout all users from mountains\n\n"
        "**Scheduler Management:**\n"
        f"/toggleAnnounce - Toggle Active Riders only (Currently: {announce_status})\n"
        "_Note: MOTD & Weather at 4:00 AM always run_\n\n"
        "**Content Management:**\n"
        "/updateMOTD - Update message of the day\n"
        "/weatherUpdate - Update weather data\n\n"
        "**Information:**\n"
        "/adminCommands - Show this list\n"
        "/listAll - List all registered users\n"
        "/holders - List all registered users by pass type"
    )
    
    await send_private_message(update, context, admin_commands_text)

async def mass_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Force all users to check out from mountains (admin command)"""
    # Only allow in private messages
    if update.message.chat.type != 'private':
        return
    
    users = read_users()
    
    if not users:
        await send_private_message(update, context, "No users found in database.")
        return
    
    # Count how many users are currently checked in
    checked_in_users = [
        {'username': user_data['username'], 'mountain': user_data['activeMountain']}
        for user_data in users.values()
        if user_data.get('activeMountain')
    ]
    
    if not checked_in_users:
        await send_private_message(
            update, 
            context, 
            "✅ No users are currently checked in to any mountains."
        )
        return
    
    # Force checkout all users
    for user_id, user_data in users.items():
        if user_data.get('activeMountain'):
            user_data['activeMountain'] = None
    
    write_users(users)
    
    # Create detailed message
    message = f"✅ **MASS CHECKOUT COMPLETE**\n\n"
    message += f"Checked out {len(checked_in_users)} user(s) from mountains:\n\n"
    
    for user in checked_in_users:
        message += f"  • {user['username']} (was at {user['mountain']})\n"
    
    message += f"\nAll users have been forced to check out."
    
    await send_private_message(update, context, message)
    
    logger.info(f"Admin {update.effective_user.id} executed /massCheckout - checked out {len(checked_in_users)} users")

async def toggle_announce(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to toggle Active Riders announcements"""
    if update.message.chat.type != 'private':
        return ConversationHandler.END
    
    correct_answer = 13
    wrong_answers = []
    while len(wrong_answers) < 3:
        num = random.randint(1, 50)
        if num != correct_answer and num not in wrong_answers:
            wrong_answers.append(num)
    
    all_answers = wrong_answers + [correct_answer]
    random.shuffle(all_answers)
    
    keyboard = []
    for answer in all_answers:
        keyboard.append([InlineKeyboardButton(str(answer), callback_data=f'toggle_auth_{answer}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔒 **Authentication Required**\n\n"
        "How many O's are in Rrruff's name?",
        reply_markup=reply_markup
    )
    return TOGGLE_ANNOUNCE_AUTH

async def toggle_announce_auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle auth response for toggleAnnounce"""
    query = update.callback_query
    await query.answer()
    
    answer = query.data.replace('toggle_auth_', '')
    
    if answer == '13':
        # Get current status
        current_status = read_announce_toggle()
        new_status = not current_status
        
        # Toggle the status
        write_announce_toggle(new_status)
        
        status_text = "ENABLED ✅" if new_status else "DISABLED ❌"
        emoji = "🟢" if new_status else "🔴"
        
        await query.edit_message_text(
            f"✅ **Authentication successful!**\n\n"
            f"{emoji} **Active Riders Announcements:**\n"
            f"Status: {status_text}\n\n"
            f"{'Active Riders will post at scheduled times (4:30 AM - 4:30 PM).' if new_status else 'Active Riders posts are paused.'}\n\n"
            f"_Note: MOTD and Weather at 4:00 AM always run regardless of this toggle._"
        )
        
        logger.info(f"Admin {update.effective_user.id} toggled announcements: {status_text}")
        return ConversationHandler.END
    else:
        await query.edit_message_text("❌ Incorrect answer. Access denied.")
        return ConversationHandler.END

async def update_motd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat.type != 'private':
        return
    
    correct_answer = 13
    wrong_answers = []
    while len(wrong_answers) < 3:
        num = random.randint(1, 50)
        if num != correct_answer and num not in wrong_answers:
            wrong_answers.append(num)
    
    all_answers = wrong_answers + [correct_answer]
    random.shuffle(all_answers)
    
    keyboard = []
    for answer in all_answers:
        keyboard.append([InlineKeyboardButton(str(answer), callback_data=f'motd_auth_{answer}')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "🔒 **Authentication Required**\n\n"
        "How many O's are in Rrruff's name?",
        reply_markup=reply_markup
    )
    return MOTD_AUTH

async def motd_auth_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    answer = query.data.replace('motd_auth_', '')
    
    if answer == '13':
        await query.edit_message_text(
            "✅ Authentication successful!\n\n"
            "What would you like the MOTD to be?"
        )
        return MOTD_INPUT
    else:
        await query.edit_message_text("❌ Incorrect answer. Access denied.")
        return ConversationHandler.END

async def motd_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_motd = update.message.text
    write_motd(new_motd)
    
    await update.message.reply_text(
        f"✅ **MOTD Updated!**\n\n"
        f"New message:\n{new_motd}\n\n"
        f"_It will be posted at 4:00 AM MT tomorrow._"
    )
    
    logger.info(f"MOTD updated by user {update.effective_user.id}")
    
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END

async def daily_reset(context: ContextTypes.DEFAULT_TYPE):
    """Reset all active mountains at 11:59 PM MT"""
    users = read_users()
    for user_id in users:
        update_active_mountain(user_id, '')
    logger.info("Daily reset completed - all active mountains cleared")

async def daily_snapshot_capture(context: ContextTypes.DEFAULT_TYPE):
    """Capture daily snapshot at 4:45 PM MT - records the longest check-in of the day"""
    users = read_users()
    
    for user_id, user_data in users.items():
        mountain = user_data.get('activeMountain', '')
        if mountain:
            username = user_data.get('username', 'Unknown')
            add_daily_snapshot(user_id, mountain, username)
    
    logger.info("Daily snapshot captured at 4:45 PM MT")

async def message_of_the_day(context: ContextTypes.DEFAULT_TYPE):
    """Post MOTD at 4:00 AM MT - runs regardless of announcement toggle"""
    motd_text = read_motd()
    
    emoji_sets = [
        ("🎿", "⛷️", "🏂"),
        ("❄️", "🌨️", "☃️"),
        ("🏔️", "⛰️", "🗻"),
        ("🚡", "🚠", "🎿")
    ]
    
    emojis = random.choice(emoji_sets)
    
    message = (
        f"{emojis[0]} {emojis[1]} {emojis[2]} **MESSAGE OF THE DAY** {emojis[2]} {emojis[1]} {emojis[0]}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"💫 {motd_text}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏔️ Don't forget to use /skiing or /boarding to register yourself to a mountain!\n"
        f"🌡️ Check out current temps by using /temp or /weatherUpdate\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )
    
    chat_id = context.job.data
    await context.bot.send_message(chat_id=chat_id, text=message)
    logger.info("MOTD posted")

async def daily_weather_update(context: ContextTypes.DEFAULT_TYPE):
    """Fetch weather and post to group at 4:00 AM MT - runs regardless of announcement toggle"""
    weather_data = {}
    all_mountains = EPM_MOUNTAINS + IPM_MOUNTAINS + LOVELAND_MOUNTAINS
    
    for mountain in all_mountains:
        if mountain in MOUNTAIN_COORDS:
            lat, lon = MOUNTAIN_COORDS[mountain]
            weather_info = fetch_mountain_weather(mountain, lat, lon)
            weather_data[mountain] = weather_info
            logger.info(f"Fetched weather for {mountain}")
    
    write_weather(weather_data)
    logger.info("Weather data updated at 4am MT")
    
    message = "🌨️ **DAILY WEATHER UPDATE - 4:00 AM MT** 🌨️\n\n"
    
    # Build weather message for all mountain groups
    mountain_groups = [
        ("⛷️ **EPIC RESORTS:**\n\n", EPM_MOUNTAINS),
        ("🎿 **IKON RESORTS:**\n\n", IPM_MOUNTAINS),
        ("❤️ **LOVELAND:**\n\n", LOVELAND_MOUNTAINS)
    ]
    
    for header, mountains in mountain_groups:
        message += header
        for mountain in mountains:
            if mountain in weather_data:
                w = weather_data[mountain]
                snowfall = w['snowfall_12hr']
                
                if snowfall != 'N/A' and float(snowfall) >= 3.0:
                    snow_display = f"🔥 **{snowfall} in** 🔥"
                else:
                    snow_display = f"{snowfall} in"
                
                snow_indicator = "❄️ SNOWING!" if w['is_snowing'] == 'Yes' else ""
                
                message += (
                    f"🏔️ **{mountain}**\n"
                    f"  🌡️ Current: {w['temp_current']}°F {snow_indicator}\n"
                    f"  🌡️ Range: {w['temp_low']}°F - {w['temp_high']}°F\n"
                    f"  ❄️ Snow (12hr): {snow_display}\n"
                    f"  📍 {w['description']}\n\n"
                )
    
    chat_id = context.job.data
    await context.bot.send_message(chat_id=chat_id, text=message)

async def hourly_auto_checkout(context: ContextTypes.DEFAULT_TYPE):
    """Check every hour for users checked in from previous day and auto-checkout"""
    users = read_users()
    mountain_tz = pytz.timezone('America/Denver')
    now = datetime.now(mountain_tz)
    today = now.strftime('%Y-%m-%d')
    
    checked_out_users = []
    
    for user_id, user_data in users.items():
        checkin_timestamp = user_data.get('checkin_timestamp', '')
        
        # If user has a check-in timestamp and is currently at a mountain
        if checkin_timestamp and user_data.get('activeMountain'):
            try:
                # Parse the check-in timestamp
                checkin_dt = datetime.strptime(checkin_timestamp, '%Y-%m-%d %H:%M:%S')
                checkin_dt = mountain_tz.localize(checkin_dt)
                checkin_date = checkin_dt.strftime('%Y-%m-%d')
                
                # If check-in was from a previous day, auto-checkout
                if checkin_date < today:
                    mountain = user_data['activeMountain']
                    username = user_data['username']
                    
                    # Checkout the user
                    update_active_mountain(user_id, '')
                    
                    checked_out_users.append({
                        'username': username,
                        'mountain': mountain,
                        'checkin_time': checkin_timestamp
                    })
                    
                    logger.info(f"Auto-checkout: {username} from {mountain} (checked in {checkin_timestamp})")
            
            except Exception as e:
                logger.error(f"Error processing auto-checkout for user {user_id}: {e}")
    
    if checked_out_users:
        logger.info(f"Hourly auto-checkout completed: {len(checked_out_users)} users checked out")

async def auto_announce(context: ContextTypes.DEFAULT_TYPE):
    """Post Active Riders Update - respects announcement toggle (can be disabled)"""
    # Check if announcements are enabled
    if not read_announce_toggle():
        logger.info("Active Riders announcements are disabled - skipping")
        return
    
    users = read_users()
    
    if not users:
        return
    
    epic_active = []
    ikon_active = []
    loveland_active = []
    
    for user_data in users.values():
        active = user_data['activeMountain']
        
        if active:
            user_info = (
                f"👤 {user_data['username']}\n"
                f"  Skill: {user_data['skillLevel']}\n"
                f"  Mountain: {active}\n"
            )
            
            if active in EPM_MOUNTAINS:
                epic_active.append(user_info)
            elif active in IPM_MOUNTAINS:
                ikon_active.append(user_info)
            elif active in LOVELAND_MOUNTAINS:
                loveland_active.append(user_info)
    
    # Only send message if there are active riders
    if not epic_active and not ikon_active and not loveland_active:
        return  # Don't post if no one is on mountains
    
    message = "🏔️ **ACTIVE RIDERS UPDATE** 🏔️\n\n"
    
    if epic_active:
        message += "⛷️ **EPIC MOUNTAINS:**\n" + "\n".join(epic_active) + "\n"
    
    if ikon_active:
        message += "🎿 **IKON MOUNTAINS:**\n" + "\n".join(ikon_active) + "\n"
    
    if loveland_active:
        message += "❤️ **LOVELAND:**\n" + "\n".join(loveland_active) + "\n"
    
    chat_id = context.job.data
    await context.bot.send_message(chat_id=chat_id, text=message)

def main():
    init_files()
    
    application = Application.builder().token("8589219296:AAES6K4nXHNJZBaPU1igvGx9WIwSbsAyGpg").build()
    
    add_profile_handler = ConversationHandler(
        entry_points=[CommandHandler('addProfile', add_profile)],
        states={
            PASS_SELECT: [CallbackQueryHandler(pass_callback, pattern='^pass_')],
            SKILL_SELECT: [CallbackQueryHandler(skill_callback, pattern='^skill_')],
            RIDER_SELECT: [CallbackQueryHandler(rider_callback, pattern='^rider_')],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
        per_message=False,
        per_chat=False,
        per_user=True,
    )
    
    edit_profile_handler = ConversationHandler(
        entry_points=[CommandHandler('editProfile', edit_profile)],
        states={
            EDIT_PASS_SELECT: [CallbackQueryHandler(edit_pass_callback, pattern='^edit_pass_')],
            EDIT_SKILL_SELECT: [CallbackQueryHandler(edit_skill_callback, pattern='^edit_skill_')],
            EDIT_RIDER_SELECT: [CallbackQueryHandler(edit_rider_callback, pattern='^edit_rider_')],
            ConversationHandler.TIMEOUT: [MessageHandler(filters.ALL, timeout_handler)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        conversation_timeout=CONVERSATION_TIMEOUT,
        per_message=False,
        per_chat=False,
        per_user=True,
    )
    
    set_mountain_handler = ConversationHandler(
        entry_points=[
            CommandHandler('skiing', set_mountain),
            CommandHandler('boarding', set_mountain)
        ],
        states={
            MOUNTAIN_PASS_SELECT: [CallbackQueryHandler(mountain_pass_callback, pattern='^mount_')],
            MOUNTAIN_SELECT: [CallbackQueryHandler(mountain_select_callback, pattern='^mountain_')],
            BUDDY_CHECKIN_CONFIRM: [CallbackQueryHandler(buddy_checkin_confirm_callback, pattern='^buddy_confirm_')],
            BUDDY_SELECT: [CallbackQueryHandler(buddy_select_callback, pattern='^(buddy_toggle_|buddy_checkin_selected|buddy_cancel)')],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False,
        per_chat=False,
        per_user=True,
    )
    
    view_mountain_handler = ConversationHandler(
        entry_points=[CommandHandler('mountain', view_mountain)],
        states={
            VIEW_MOUNTAIN_PASS_SELECT: [CallbackQueryHandler(view_mountain_pass_callback, pattern='^view_mount_')],
            VIEW_MOUNTAIN_CHECKIN: [CallbackQueryHandler(view_mountain_checkin_callback, pattern='^view_checkin_')],
            VIEW_MOUNTAIN_SELECT: [CallbackQueryHandler(view_mountain_select_callback, pattern='^view_mountain_')],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False,
        per_chat=False,
        per_user=True,
    )
    
    update_motd_handler = ConversationHandler(
        entry_points=[CommandHandler('updateMOTD', update_motd)],
        states={
            MOTD_AUTH: [CallbackQueryHandler(motd_auth_callback, pattern='^motd_auth_')],
            MOTD_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, motd_input)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False,
        per_chat=False,
        per_user=True,
    )
    
    erase_all_handler = ConversationHandler(
        entry_points=[CommandHandler('eraseAll', erase_all)],
        states={
            ERASEALL_AUTH: [CallbackQueryHandler(eraseall_auth_callback, pattern='^eraseall_auth_')],
            ERASEALL_CONFIRM: [CallbackQueryHandler(eraseall_confirm_callback, pattern='^eraseall_confirm_')],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False,
        per_chat=False,
        per_user=True,
    )
    
    toggle_announce_handler = ConversationHandler(
        entry_points=[CommandHandler('toggleAnnounce', toggle_announce)],
        states={
            TOGGLE_ANNOUNCE_AUTH: [CallbackQueryHandler(toggle_announce_auth_callback, pattern='^toggle_auth_')],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
        per_message=False,
        per_chat=False,
        per_user=True,
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(add_profile_handler)
    application.add_handler(edit_profile_handler)
    application.add_handler(set_mountain_handler)
    application.add_handler(view_mountain_handler)
    application.add_handler(update_motd_handler)
    application.add_handler(erase_all_handler)
    application.add_handler(toggle_announce_handler)
    application.add_handler(CommandHandler('listAll', list_all))
    application.add_handler(CommandHandler('listActive', list_active))
    application.add_handler(CommandHandler('listIkon', list_ikon))
    application.add_handler(CommandHandler('Ikon', list_ikon))
    application.add_handler(CommandHandler('listEpic', list_epic))
    application.add_handler(CommandHandler('Epic', list_epic))
    application.add_handler(CommandHandler('listLoveland', list_loveland))
    application.add_handler(CommandHandler('Loveland', list_loveland))
    application.add_handler(CommandHandler('announcement', announcement))
    application.add_handler(CommandHandler('weatherUpdate', weather_update))
    application.add_handler(CommandHandler('weather', weather))
    application.add_handler(CommandHandler('temp', temp))
    application.add_handler(CommandHandler('leaving', leaving))
    application.add_handler(CommandHandler('eraseMe', erase_me))
    application.add_handler(CommandHandler('commands', commands_list))
    application.add_handler(CommandHandler('holders', holders))
    application.add_handler(CommandHandler('days', days_command))
    application.add_handler(CommandHandler('adminCommands', admin_commands))
    application.add_handler(CommandHandler('massCheckout', mass_checkout))
    
    job_queue = application.job_queue
    if job_queue:
        mountain_tz = pytz.timezone('America/Denver')
        reset_time = time(hour=23, minute=59, tzinfo=mountain_tz)
        snapshot_time = time(hour=16, minute=45, tzinfo=mountain_tz)
        motd_time = time(hour=4, minute=0, tzinfo=mountain_tz)
        announce_time = time(hour=4, minute=30, tzinfo=mountain_tz)
        
        job_queue.run_daily(daily_reset, reset_time)
        logger.info("Daily reset scheduled for 11:59 PM MT")
        
        job_queue.run_daily(
            daily_snapshot_capture,
            snapshot_time,
            name="daily_snapshot"
        )
        logger.info("Daily snapshot scheduled for 4:45 PM MT")
        
        GROUP_CHAT_ID = -GROUPIDHERE
        job_queue.run_daily(
            daily_weather_update,
            reset_time,
            data=GROUP_CHAT_ID,
            name="daily_weather_update"
        )
        logger.info("Daily weather update scheduled for 4:00 AM MT")
        
        # Auto-announcements: Every hour from 4:30 AM to 4:30 PM MT
        # Schedule for specific times: 4:30, 5:30, 6:30, 7:30, 8:30, 9:30, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30, 16:30
        announce_hours = [4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16]
        for hour in announce_hours:
            announce_time_specific = time(hour=hour, minute=30, tzinfo=mountain_tz)
            job_queue.run_daily(
                auto_announce,
                announce_time_specific,
                data=GROUP_CHAT_ID,
                name=f"auto_announce_{hour:02d}30"
            )
        logger.info(f"Auto-announcements scheduled every hour from 4:30 AM to 4:30 PM MT (13 times per day)")
        
        # MOTD: Only at 4:00 AM daily
        job_queue.run_daily(
            message_of_the_day,
            motd_time,
            data=GROUP_CHAT_ID,
            name="motd_daily"
        )
        logger.info("MOTD scheduled for 4:00 AM MT daily")
        
        # Hourly auto-checkout for users checked in from previous day
        job_queue.run_repeating(
            hourly_auto_checkout,
            interval=3600,
            first=60,
            name="hourly_auto_checkout"
        )
        logger.info("Hourly auto-checkout scheduled every hour")
    else:
        logger.warning("JobQueue not available. Install with: pip install python-telegram-bot[job-queue]")
    
    logger.info("Bot started - Ready for PM and group chat commands")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()