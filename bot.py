import os
import sqlite3
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Set up database connection
db = sqlite3.connect("sportsbook.db")
cursor = db.cursor()

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
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

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

# Run the bot
if TOKEN:
    bot.run(TOKEN)
else:
    print("Error: DISCORD_TOKEN not found in environment variables.")