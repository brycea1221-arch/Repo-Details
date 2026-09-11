import os
import sqlite3
import datetime
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Dummy web server to keep Render happy on port 10000
class SimpleHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot is running!")

def run_server():
    server = HTTPServer(('0.0.0.0', 10000), SimpleHandler)
    server.serve_forever()

# Start the dummy server in a background thread
threading.Thread(target=run_server, daemon=True).start()

# Load environment variables from .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Set up database connection
db = sqlite3.connect("sportsbook.db")
cursor = db.cursor()

# 1. Create Tables if they don't exist
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 1000.0,
        last_daily TEXT
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        team1 TEXT,
        team2 TEXT,
        odds_team1 INTEGER,
        odds_team2 INTEGER,
        spread REAL DEFAULT 0.0,
        total_line REAL DEFAULT 0.0,
        status TEXT DEFAULT 'open'
    )
''')

cursor.execute('''
    CREATE TABLE IF NOT EXISTS bets (
        bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        game_id INTEGER,
        chosen_team TEXT,
        amount REAL
    )
''')
db.commit()

# Set up bot intents and instance
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Helper function to convert American odds (+150, -110) into multipliers
def american_to_multiplier(odds: int) -> float:
    if odds > 0:
        return 1.0 + (odds / 100.0)
    else:
        return 1.0 + (100.0 / abs(odds))

@bot.event
async def on_ready():
    print(f"Sportsbook bot is online and logged in as {bot.user}")

# --- PING TEST ---
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong! 🏓 Bot is online and listening.")

# --- BALANCE ---
@bot.command(name="balance")
async def balance(ctx):
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    user_id = ctx.author.id
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row is None:
        user_balance = 1000.0
    else:
        user_balance = row[0]

    await ctx.send(f"{ctx.author.mention}, your current balance is ${user_balance:.2f}!")

# --- DAILY BONUS ---
@bot.command(name="daily")
async def daily(ctx):
    user_id = ctx.author.id
    today = str(datetime.date.today())

    cursor.execute("SELECT balance, last_daily FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if user and user[1] == today:
        await ctx.send(f"❌ {ctx.author.mention}, you have already claimed your daily bonus today! Come back tomorrow.")
        return

    current_balance = user[0] if user else 1000.0
    new_balance = current_balance + 250.0

    cursor.execute("INSERT OR REPLACE INTO users (user_id, balance, last_daily) VALUES (?, ?, ?)", (user_id, new_balance, today))
    db.commit()

    await ctx.send(f"💰 {ctx.author.mention} claimed your daily bonus of **$250.00**! Your new balance is ${new_balance:.2f}.")

# --- CREATE GAME (Admin only) ---
@bot.command(name="creategame")
@commands.has_permissions(administrator=True)
async def creategame(ctx, *, arg: str):
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    # Expected format: Ohio State 100 vs Texas -118
    lower_arg = arg.lower()
    if " vs " not in lower_arg:
        await ctx.send("❌ Please use 'vs' between teams. Example: `!creategame Ohio State 100 vs Texas -118`", delete_after=10)
        return

    # Split the message cleanly at " vs "
    idx = lower_arg.find(" vs ")
    side1 = arg[:idx].strip()
    side2 = arg[idx + 4:].strip()

    # Parse Team 1 and its odds (last word of side 1)
    s1_words = side1.split()
    try:
        odds1 = int(s1_words[-1])
        team1 = " ".join(s1_words[:-1])
    except ValueError:
        await ctx.send("❌ Error parsing Team 1 odds. Format should be: `Team Name [odds]`", delete_after=10)
        return

    # Parse Team 2 and its odds (last word of side 2)
    s2_words = side2.split()
    try:
        odds2 = int(s2_words[-1])
        team2 = " ".join(s2_words[:-1])
    except ValueError:
        await ctx.send("❌ Error parsing Team 2 odds. Format should be: `Team Name [odds]`", delete_after=10)
        return

    cursor.execute(
        "INSERT INTO games (team1, team2, odds_team1, odds_team2, status) VALUES (?, ?, ?, ?, 'open')",
        (team1, team2, odds1, odds2)
    )
    db.commit()
    game_id = cursor.lastrowid

    await ctx.send(
        f"🎮 **New Game Open!** (Game #{game_id})\n"
        f"🏟️ **{team1}** ({odds1:+d}) vs **{team2}** ({odds2:+d})\n"
        f"Use `!bet {game_id} <team> <amount>` to place your wager!"
    )

# --- PLACE BET ---
@bot.command(name="bet")
async def bet(ctx, game_id: int, choice: str, amount: float):
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass

    user_id = ctx.author.id

    if amount <= 0:
        await ctx.send(f"❌ {ctx.author.mention}, bet amount must be greater than zero.", delete_after=5)
        return

    cursor.execute("SELECT team1, team2, odds_team1, odds_team2, status FROM games WHERE game_id = ?", (game_id,))
    game = cursor.fetchone()

    if not game:
        await ctx.send(f"❌ {ctx.author.mention}, Game #{game_id} not found.", delete_after=5)
        return

    team1, team2, odds1, odds2, status = game

    if status != 'open':
        await ctx.send(f"❌ {ctx.author.mention}, betting is closed for this game.", delete_after=5)
        return

    if choice.lower() not in [team1.lower(), team2.lower()]:
        await ctx.send(f"❌ {ctx.author.mention}, invalid choice. Pick either **{team1}** or **{team2}**.", delete_after=5)
        return

    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    current_balance = user[0] if user else 1000.0

    if current_balance < amount:
        await ctx.send(f"❌ {ctx.author.mention}, you don't have enough funds! Balance: ${current_balance:.2f}", delete_after=5)
        return

    new_balance = current_balance - amount
    cursor.execute("INSERT OR REPLACE INTO users (user_id, balance) VALUES (?, ?)", (user_id, new_balance))
    
    chosen_team = team1 if choice.lower() == team1.lower() else team2
    cursor.execute(
        "INSERT INTO bets (user_id, game_id, chosen_team, amount) VALUES (?, ?, ?, ?)",
        (user_id, game_id, chosen_team, amount)
    )
    db.commit()

    odds_used = odds1 if chosen_team.lower() == team1.lower() else odds2
    await ctx.send(f"✅ {ctx.author.mention} successfully wagered ${amount:.2f} on **{chosen_team}** ({odds_used:+d}) for Game #{game_id}!")

# --- RESOLVE GAME (Admin only) ---
@bot.command(name="resolve_game")
@commands.has_permissions(administrator=True)
async def resolve_game(ctx, game_id: int, winning_team: str):
    cursor.execute("SELECT team1, team2, odds_team1, odds_team2, status FROM games WHERE game_id = ?", (game_id,))
    game = cursor.fetchone()

    if not game:
        await ctx.send("❌ Game not found.")
        return

    team1, team2, odds1, odds2, status = game

    if status == 'closed':
        await ctx.send("❌ This game has already been resolved.")
        return

    if winning_team.lower() not in [team1.lower(), team2.lower()]:
        await ctx.send(f"❌ Invalid winning team. Choose either **{team1}** or **{team2}**.")
        return

    winning_odds = odds1 if winning_team.lower() == team1.lower() else odds2
    multiplier = american_to_multiplier(winning_odds)

    cursor.execute("UPDATE games SET status = 'closed' WHERE game_id = ?", (game_id,))

    cursor.execute("SELECT user_id, chosen_team, amount FROM bets WHERE game_id = ?", (game_id,))
    all_bets = cursor.fetchall()

    payouts = {}
    for user_id, chosen_team, amount in all_bets:
        if chosen_team.lower() == winning_team.lower():
            winnings = amount * multiplier
            payouts[user_id] = payouts.get(user_id, 0) + winnings

    for user_id, total_winnings in payouts.items():
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        current_bal = row[0] if row else 1000.0
        new_bal = current_bal + total_winnings
        cursor.execute("INSERT OR REPLACE INTO users (user_id, balance) VALUES (?, ?)", (user_id, new_bal))

    db.commit()
    await ctx.send(f"🏆 Game #{game_id} resolved! Winner: **{winning_team}** ({winning_odds:+d}). Payouts distributed!")

# --- TOP LEADERBOARD ---
@bot.command(name="top")
async def top(ctx):
    cursor.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT 5")
    top_users = cursor.fetchall()

    if not top_users:
        await ctx.send("📊 No users on the leaderboard yet.")
        return

    msg = "🏆 **Sportsbook Leaderboard - Top Bettors** 🏆\n"
    for i, (user_id, balance) in enumerate(top_users, 1):
        member = ctx.guild.get_member(user_id)
        name = member.name if member else f"User {user_id}"
        msg += f"{i}. **{name}** — ${balance:.2f}\n"

    await ctx.send(msg)

@bot.command(name="games")
async def games(ctx):
    cursor.execute("SELECT id, team1, team2, odds_team1, odds_team2 FROM games WHERE status='open'")
    active_games = cursor.fetchall()
    
    if not active_games:
        await ctx.send("❌ There are no open games right now.")
        return
        
    msg = "🎮 **Open Games:**\n"
    for g in active_games:
        gid, t1, t2, o1, o2 = g
        o1_str = f"+{o1}" if o1 > 0 else str(o1)
        o2_str = f"+{o2}" if o2 > 0 else str(o2)
        msg += f"**Game #{gid}**: {t1} ({o1_str}) vs {t2} ({o2_str})\n"
        
    await ctx.send(msg)

# --- RUN BOT ---
if TOKEN:
    bot.run(TOKEN)
else:
    print("Error: DISCORD_TOKEN not found in environment variables.")