import json
import os
import time
import discord
from discord.ext import commands
from dotenv import load_dotenv
from keep_alive import keep_alive

# Load secret token from .env file
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# Setup bot intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# Reward tiers mapping streak length to reward amount
STREAK_REWARDS = [
    5, 10, 20, 50, 100, 150, 200, 250, 500, 750,
    1000, 1500, 2000, 3000, 4000, 5000, 7500, 10000,
    15000, 20000, 25000, 30000, 40000, 50000, 75000, 100000
]

def load_data():
    """Load user data from json file."""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_data(data):
    """Save user data to json file."""
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

@bot.command()
async def daily(ctx):
    user_id = str(ctx.author.id)  # JSON keys must be strings
    current_time = time.time()
    user_data = load_data()

    # Initialize profile if new user
    if user_id not in user_data:
        user_data[user_id] = {"tokens": 0, "streak": 0, "last_daily": 0}

    stats = user_data[user_id]
    time_passed = current_time - stats["last_daily"]

    # Minimum wait time: 24 hours (86,400 seconds)
    if time_passed < 86400 and stats["last_daily"] != 0:
        time_remaining = int((86400 - time_passed) / 3600)
        await ctx.send(f"{ctx.author.mention}, you already claimed your daily reward! Please wait ~{time_remaining} hours.")
        return

    # Maximum window: 48 hours (172,800 seconds) before streak resets
    if time_passed > 172800 and stats["last_daily"] != 0:
        stats["streak"] = 1
    else:
        stats["streak"] += 1

    # Determine reward based on current streak index
    reward_index = min(stats["streak"] - 1, len(STREAK_REWARDS) - 1)
    earned = STREAK_REWARDS[reward_index]

    # Update balance and timestamp
    stats["tokens"] += earned
    stats["last_daily"] = current_time

    # Save to file
    save_data(user_data)

    # Bot response
    await ctx.send(f"{ctx.author.mention} Now has **${stats['tokens']:,}** and a streak of **x{stats['streak']}**")

if __name__ == "__main__":
    keep_alive()  # Starts the Flask web server for Render keep-alive
    bot.run(TOKEN)