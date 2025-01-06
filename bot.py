import discord
import sqlite3
from cogs.danisen import *
import json
import os

def create_bot():
    try:
        if os.path.exists("config.json"):
            with open("config.json", 'r') as f:
                config = json.load(f)
    except Exception as e:
        print("Warning", f"Failed to load configuration: {str(e)}")

    intents = discord.Intents.default()
    intents.members = True

    bot = discord.Bot(intents=intents)
    con = sqlite3.connect("danisen.db")

    bot.add_cog(Danisen(bot,con,config))

    @bot.event
    async def on_ready():
        print(f'We have logged in as {bot.user}')
    
    return bot
