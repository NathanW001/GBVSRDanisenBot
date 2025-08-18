import discord
import sqlite3
from cogs.danisen import *
import json
import os
import logging
from constants import CONFIG_PATH


def create_bot(con):
    intents = discord.Intents.default()
    intents.members = True

    bot = discord.Bot(intents=intents)

    bot.add_cog(Danisen(bot,con,CONFIG_PATH))

    # Create and configure logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)

    @bot.event
    async def on_ready():
        logger.info(f'We have logged in as {bot.user}')
    
    return bot

def update_bot_config(bot):
    danisen = bot.get_cog("Danisen")
    danisen.update_config()