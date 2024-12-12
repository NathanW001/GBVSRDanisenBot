import discord
import configparser
import sqlite3
from functools import cache
from cogs.danisen import *

config = configparser.RawConfigParser()
config.read('bot.cfg')

id_dict = dict(config.items('TOKENS'))
token = id_dict['token']

intents = discord.Intents.default()
intents.members = True

bot = discord.Bot(intents=intents)
con = sqlite3.connect("danisen.db")

bot.add_cog(Danisen(bot,con))

@bot.event
async def on_ready():
    print(f'We have logged in as {bot.user}')

bot.run(token)