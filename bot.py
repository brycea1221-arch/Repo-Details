import os
import sqlite3
import discord
from discord.ext import commands
from dotenv import load_dotenv
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler

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
import sqlite3
import discord
from discord.ext import commands

# 1. Connect to the SQLite database file
db = sqlite3.connect("sportsbook.db")
cursor = db.cursor()

# 2. RUN STEP 1 HERE: Create the tables if they don't already exist
# Users table (tracks money and daily bonus claims)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance REAL DEFAULT 1000.0,
        last_daily TEXT
    )
''')

# Games table (tracks matchups like Chiefs vs 49ers)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        team_a TEXT,
        team_b TEXT,
        status TEXT DEFAULT 'open'
    )
''')

# Bets table (tracks who bet on which team and how much)
cursor.execute('''
    CREATE TABLE IF NOT EXISTS bets (
        bet_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        game_id INTEGER,
        chosen_team TEXT,
        amount REAL
    )
''')

# Save (commit) these changes to the database file
db.commit()
import datetime
from discord.ext import commands
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# 1. Create a Game (Admin only)
@bot.command(name="create_game")
@commands.has_permissions(administrator=True)
async def create_game(ctx, team_a: str, team_b: str):
    cursor.execute("INSERT INTO games (team_a, team_b, status) VALUES (?, ?, 'open')", (team_a, team_b))
    db.commit()
    game_id = cursor.lastrowid
    await ctx.send(f"🎮 Game #{game_id} created successfully!\n**{team_a} vs {team_b}**\nUse `!bet {game_id} <team> <amount>` to place your wager.")

# 2. Place a Bet (Everyone can use)
@bot.command(name="bet")
async def bet(ctx, game_id: int, team: str, amount: float):
    user_id = ctx.author.id
    
    if amount <= 0:
        await ctx.send("❌ Bet amount must be greater than zero.")
        return

    # Check if game exists and is open
    cursor.execute("SELECT team_a, team_b, status FROM games WHERE game_id = ?", (game_id,))
    game = cursor.fetchone()
    if not game:
        await ctx.send("❌ Game not found.")
        return
    if game[2] != 'open':
        await ctx.send("❌ Betting is closed for this game.")
        return
    
    team_a, team_b = game[0], game[1]
    if team.lower() not in [team_a.lower(), team_b.lower()]:
        await ctx.send(f"❌ Invalid team name. Choose either **{team_a}** or **{team_b}**.")
        return

    # Check user balance
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    current_balance = user[0] if user else 1000.0 # Default starting balance

    if current_balance < amount:
        await ctx.send(f"❌ You don't have enough funds! Your balance is ${current_balance:.2f}.")
        return

    # Deduct balance and record bet
    new_balance = current_balance - amount
    cursor.execute("INSERT OR REPLACE INTO users (user_id, balance) VALUES (?, ?)", (user_id, new_balance))
    cursor.execute("INSERT INTO bets (user_id, game_id, chosen_team, amount) VALUES (?, ?, ?, ?)", (user_id, game_id, team, amount))
    db.commit()

    await ctx.send(f"✅ Bet placed successfully! Wagered ${amount:.2f} on {team} for Game #{game_id}.")

# 3. Resolve Game and Payout Winners (Admin only)
@bot.command(name="resolve_game")
@commands.has_permissions(administrator=True)
async def resolve_game(ctx, game_id: int, winning_team: str):
    cursor.execute("SELECT team_a, team_b, status FROM games WHERE game_id = ?", (game_id,))
    game = cursor.fetchone()
    if not game:
        await ctx.send("❌ Game not found.")
        return
    if game[2] == 'closed':
        await ctx.send("❌ This game has already been resolved.")
        return

    # Mark game as closed
    cursor.execute("UPDATE games SET status = 'closed' WHERE game_id = ?", (game_id,))
    
    # Get all bets for this game
    cursor.execute("SELECT user_id, chosen_team, amount FROM bets WHERE game_id = ?", (game_id,))
    all_bets = cursor.fetchall()

    payouts = {}
    for user_id, chosen_team, amount in all_bets:
        if chosen_team.lower() == winning_team.lower():
            winnings = amount * 2  # Simple 2x payout model
            payouts[user_id] = payouts.get(user_id, 0) + winnings

    # Update balances for winners
    for user_id, total_winnings in payouts.items():
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
        bal_row = cursor.fetchone()
        current_bal = bal_row[0] if bal_row else 1000.0
        new_bal = current_bal + total_winnings
        cursor.execute("INSERT OR REPLACE INTO users (user_id, balance) VALUES (?, ?)", (user_id, new_bal))

    db.commit()
    await ctx.send(f"🏆 Game #{game_id} resolved! Winner: **{winning_team}**. Payouts have been distributed to winning tickets.")

# 4. Daily Bonus Command
@bot.command(name="daily")
async def daily(ctx):
    user_id = ctx.author.id
    today = str(datetime.date.today())

    cursor.execute("SELECT balance, last_daily FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if user and user[1] == today:
        await ctx.send("⏳ You have already claimed your daily bonus today! Come back tomorrow.")
        return

    current_balance = user[0] if user else 1000.0
    new_balance = current_balance + 250.0 # $250 daily bonus

    cursor.execute("INSERT OR REPLACE INTO users (user_id, balance, last_daily) VALUES (?, ?, ?)", (user_id, new_balance, today))
    db.commit()

    await ctx.send(f"🎁 You claimed your daily bonus of **$250.00**! Your new balance is ${new_balance:.2f}.")

# 5. Leaderboard Command
@bot.command(name="top") # Changed from leaderboard to top
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
# Create tables for users and games if they don't exist
cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 1000
    )
""")
cursor.execute("""
    CREATE TABLE IF NOT EXISTS games (
        game_id INTEGER PRIMARY KEY AUTOINCREMENT,
        team1 TEXT,
        team2 TEXT,
        status TEXT DEFAULT 'open'
    )
""")
db.commit()

# Set up bot intents

@bot.event
async def on_ready():
    print(f"Sportsbook bot is online and logged in as {bot.user}")

@bot.command(name="balance")
async def balance(ctx):
    # Automatically delete the user's command message so it's hidden
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass  # Ignores if bot lacks permission, but will delete if permitted
    
    user_id = ctx.author.id
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    
    if row is None:
        cursor.execute("INSERT INTO users (user_id, balance) VALUES (?, 1000)", (user_id,))
        db.commit()
        user_balance = 1000
    else:
        user_balance = row[0]
        
    # Send the public response for everyone to see
    await ctx.send(f"{ctx.author.mention}, your current balance is ${user_balance}!")

@bot.command(name="creategame")
async def creategame(ctx, team1: str, team2: str):
    # Automatically delete the user's command message
    try:
        await ctx.message.delete()
    except discord.Forbidden:
        pass
        
    cursor.execute("INSERT INTO games (team1, team2) VALUES (?, ?)", (team1, team2))
    db.commit()
    
    # Send the public response for everyone
    await ctx.send(f"🎮 **New Game Open!** **{team1} vs {team2}** is now open for betting!")
# List all open games
@bot.command(name="games")
async def games(ctx):
    cursor.execute("SELECT game_id, team1, team2 FROM games WHERE status = 'open'")
    open_games = cursor.fetchall()

    if not open_games:
        await ctx.send("❌ There are currently no open games to bet on.")
        return

    msg = "🎮 **Active Games for Betting** 🎮\n"
    for game_id, team1, team2 in open_games:
        msg += f"Game #{game_id}: **{team1} vs {team2}**\n"
    
    msg += "\nUse `!bet <game_id> <team> <amount>` to place your wager!"
    await ctx.send(msg)
@bot.command(name="ping")
async def ping(ctx):
    await ctx.send("Pong! 🏓 Bot is online and listening.")
# Run the bot
if TOKEN:
    bot.run(TOKEN)
else:
    print("Error: DISCORD_TOKEN not found in environment variables.")