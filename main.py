import json
import os
import time
import random
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
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
ADMIN_ROLE_ID = 1540450634988519665
GAMBLE_CHANNEL_ID = 1540451527280300122
LEADERBOARD_CHANNEL_ID = 1540455291907350670

# Reward tiers mapping streak length to reward amount
STREAK_REWARDS = [
    5, 10, 20, 50, 100, 150, 200, 250, 500, 750,
    1000, 1500, 2000, 3000, 4000, 5000, 7500, 10000,
    15000, 20000, 25000, 30000, 40000, 50000, 75000, 100000
]

# --- DATA MANAGEMENT ---
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- BLACKJACK LOGIC ---
def get_card():
    cards = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
    return random.choice(cards)

def calculate_score(hand):
    score = 0
    aces = 0
    for card in hand:
        if card in ['J', 'Q', 'K']: score += 10
        elif card == 'A': aces += 1
        else: score += int(card)
    
    for _ in range(aces):
        if score + 11 > 21: score += 1 # Ace as 1
        else: score += 11 # Ace as 11 (simplified logic)
    # Correcting Ace logic for simplicity in blackjack
    # If score > 21 and we have an ace that was counted as 11, subtract 10
    return score

class BlackjackView(discord.ui.View):
    def __init__(self, ctx, bet, multiplier):
        super().__init__(timeout=60)
        self.ctx = ctx
        self.bet = bet
        self.multiplier = multiplier
        self.user_hand = [get_card(), get_card()]
        self.dealer_hand = [get_card(), get_card()]
        self.game_over = False

    def render_embed(self):
        user_score = calculate_score(self.user_hand)
        dealer_score = calculate_score(self.dealer_hand)
        
        embed = discord.Embed(title="♠️ Blackjack Table ♣️", color=discord.Color.dark_green())
        embed.set_author(name=f"Multiplier: {self.multiplier:.2f}x")
        embed.description = f"Your Hand: {self.user_hand} ({user_score})\nDealer's Hand: [{self.dealer_hand[0]}, ?] ({dealer_score})"
        embed.add_field(name="Table", value="```\n   ___   ___\n  |   | |   |\n  |___| |___|\n    [  ] [  ]\n  __________\n  |  BET    |\n  |________|\n```", inline=False)
        return embed

    async def handle_game_over(self, result_text, final_multiplier):
        user_data = load_data()
        user_id = str(self.ctx.author.id)
        
        # Calculate payout
        if "Win" in result_text:
            win_amount = int(self.bet * final_multiplier)
            user_data[user_id]["tokens"] += win_amount
            # Multiplier goes down on win
            current_mult = user_data.get("multiplier", 2.0)
            user_data["multiplier"] = max(0.5, current_mult - random.uniform(0.1, 0.5))
        else:
            # Multiplier goes up on loss
            current_mult = user_data.get("multiplier", 2.0)
            user_data["multiplier"] = min(5.0, current_mult + random.uniform(0.1, 0.5))

        save_data(user_data)
        
        embed = self.render_embed()
        embed.add_field(name="Result", value=result_text)
        await self.ctx.send(embed=embed, view=None)
        self.stop()

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.blur)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.defer()
        
        self.user_hand.append(get_card())
        score = calculate_score(self.user_hand)
        
        if score > 21:
            await self.handle_game_over("❌ Bust! You lost.", self.multiplier)
            await interaction.response.edit_message(embed=self.render_embed())
        else:
            await interaction.response.edit_message(embed=self.render_embed(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.green)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author: return await interaction.response.defer()
        
        # Dealer plays
        dealer_score = calculate_score(self.dealer_hand)
        while dealer_score < 17:
            self.dealer_hand.append(get_card())
            dealer_score = calculate_score(self.dealer_hand)
        
        user_score = calculate_score(self.user_hand)
        
        if dealer_score > 21 or user_score > dealer_score:
            await self.handle_game_over("🎉 You Win!", self.multiplier)
        elif user_score < dealer_score:
            await self.handle_game_over("💀 Dealer Wins!", self.multiplier)
        else:
            await self.handle_game_over("🤝 Push (Tie)!", 1.0)
            
        await interaction.response.edit_message(embed=self.render_embed(), view=None)

# --- LEADERBOARD TASK ---
@tasks.loop(seconds=10)
async def update_leaderboard():
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID)
    if not channel: return
    
    data = load_data()
    # Sort users by tokens
    sorted_users = sorted(data.items(), key=lambda x: x[1].get("tokens", 0), reverse=True)[:10]
    
    lb_text = "**🏆 Top 10 Richest Users**\n"
    for i, (uid, stats) in enumerate(sorted_users, 1):
        lb_text += f`{i}. <@{uid}> - {stats['tokens']:,} Quack Tokens` + "\n"
    
    # Find the existing leaderboard message to edit, or send new one
    async for message in channel.history(limit=10):
        if message.author == bot.user and "Top 10 Richest" in (message.content or ""):
            await message.edit(content=lb_set_text := lb_text)
            return
            
    await channel.send(lb_text)

# --- COMMANDS ---

@bot.command()
async def daily(ctx):
    user_id = str(ctx.author.id)
    current_time = time.time()
    user_data = load_data()

    if user_id not in user_data:
        user_data[user_id] = {"tokens": 0, "streak": 0, "last_daily": 0}

    stats = user_data[user_id]
    time_passed = current_time - stats["last_daily"]

    if time_passed < 86400 and stats["last_daily"] != 0:
        time_remaining = int((86400 - time_passed) / 3600)
        await ctx.send(f"{ctx.author.mention}, you already claimed your daily reward! Please wait ~{time_remaining} hours.")
        return

    if time_passed > 172800 and stats["last_daily"] != 0:
        stats["streak"] = 1
    else:
        stats["streak"] += 1

    reward_index = min(stats["streak"] - 1, len(STREAK_REWARDS) - 1)
    earned = STREAK_REWARDS[reward_index]

    stats["tokens"] += earned
    stats["last_daily"] = current_time
    save_data(user_data)

    await ctx.send(f"{ctx.mention} Now has {stats['tokens']:,} Quack Tokens and has a streak of **x{stats['streak']} days**")

@bot.command()
async def blackjack(ctx, amount: int):
    if ctx.channel.id != GAMBLE_CHANNEL_ID:
        await ctx.send("Gambling commands can only be used in the designated channel!", delete_after=5)
        return

    user_id = str(ctx.author.id)
    user_data = load_data()
    
    if user_id not in user_data or user_data[user_id]["tokens"] < amount:
        await ctx.send("You don't have enough Quack Tokens!")
        return

    # Deduct bet
    user_data[user_id]["tokens"] -= amount
    save_data(user_data)
    
    multiplier = user_data.get("multiplier", 2.0)
    view = BlackjackView(ctx, amount, multiplier)
    await ctx.send(embed=view.render_embed(), view=view)

@bot.command()
async def addtokens(ctx, user: discord.Member, amount: int):
    if not any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
        await ctx.send("**You do not have the correct role for this.**", delete_after=5)
        return

    user_data = load_data()
    uid = str(user.id)
    if uid not in user_data: user_data[uid] = {"tokens": 0, "streak": 0, "last_daily": 0}
    
    user_data[uid]["tokens"] += amount
    save_data(user_data)
    await ctx.send(f"Added {amount} Quack Tokens to {user.mention}")

@bot.command()
async def removetokens(ctx, user: discord.Member, amount: int):
    if not any(role.id == ADMIN_ROLE_ID for role in ctx.author.roles):
        await ctx.send("**You do not have the correct role for this.**", delete_after=5)
        return

    user_data = load_data()
    uid = str(user.id)
    if uid not in user_data: user_data[uid] = {"tokens": 0, "streak": 0, "last_daily": 0}
    
    user_data[uid]["tokens"] -= amount
    save_data(user_data)
    await ctx.send(f"Removed {amount} Quack Tokens from {user.mention}")

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")
    update_leaderboard.start()

if __name__ == "__main__":
    keep_alive()
    bot.run(TOKEN)
