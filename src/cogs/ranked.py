import discord, sqlite3, asyncio, json, logging, re, math
from discord.ext import commands, pages
from cogs.database import *
from cogs.custom_views import *
import os
from collections import deque
from constants import *
from random import choice
from datetime import datetime
from time import time

class Ranked(commands.Cog):
    # Predefined constants
    players = ["player1", "player2"] # These are the presets for specifying which player won in /reportmatch, NOT danisen player names

    def __init__(self, bot, database, config_path):
        # Initialize the cog
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        self.bot = bot
        self.config_path = config_path
        self.update_config()

        # Database setup
        self.database_con = database
        self.database_con.row_factory = sqlite3.Row
        self.database_cur = self.database_con.cursor()

        # Table for a discord user and profile config
        self.database_cur.execute(f"CREATE TABLE IF NOT EXISTS users("
                                                                    f"discord_id INT PRIMARY KEY,"
                                                                    f"player_name TEXT NOT NULL,"
                                                                    f"nickname TEXT,"
                                                                    f"keyword TEXT"
                                                                    f")")

        # Table for characters registered by a discord user
        self.database_cur.execute(f"CREATE TABLE IF NOT EXISTS players("
                                                                    f"discord_id INT NOT NULL,"
                                                                    f"character TEXT NOT NULL,"
                                                                    f"glicko_rating FLOAT NOT NULL,"
                                                                    f"glicko_rd FLOAT NOT NULL,"
                                                                    f"glicko_volatility FLOAT NOT NULL,"
                                                                    f"last_rating_timestamp INTEGER NOT NULL," #unix timestamp
                                                                    f"FOREIGN KEY (discord_id) REFERENCES users ON UPDATE CASCADE ON DELETE CASCADE,"
                                                                    f"PRIMARY KEY (discord_id, character)"
                                                                    f")")

        # Table for match history
        self.database_cur.execute(f"CREATE TABLE IF NOT EXISTS matches("
                                                                    f"id INTEGER PRIMARY KEY,"
                                                                    f"winner_discord_id INT,"
                                                                    f"winner_character TEXT,"
                                                                    f"loser_discord_id INT,"
                                                                    f"loser_character TEXT,"
                                                                    f"FOREIGN KEY (winner_discord_id, winner_character) REFERENCES players(discord_id, character) ON UPDATE CASCADE ON DELETE SET NULL,"
                                                                    f"FOREIGN KEY (loser_discord_id, loser_character) REFERENCES players(discord_id, character) ON UPDATE CASCADE ON DELETE SET NULL"
                                                                    f")")

        self.database_cur.execute(f"CREATE TABLE IF NOT EXISTS rating_period("
                                                                            f"timestamp INTEGER NOT NULL" #uses unix time
                                                                            f")")

        # self.database_cur.execute(f"CREATE TABLE IF NOT EXISTS invites("
        #                                                             f"discord_id INT NOT NULL,"
        #                                                             f"invite_link TEXT,"
        #                                                             f"timestamp INTEGER," # uses unix time
        #                                                             f"FOREIGN KEY (discord_id) REFERENCES users (discord_id) ON UPDATE CASCADE ON DELETE CASCADE,"
        #                                                             f"PRIMARY KEY (discord_id)"
        #                                                             f")")

        # Queue and matchmaking setup
        self.matchmaking_queue = deque()   
        self.cur_active_matches = 0
        self.in_queue = {}  # Format: discord_id@character: [in_queue, deque of last played discord_ids]
        self.in_match = {}  # Format: discord_id: in_match
        self.matchmaking_coro = None  # Task created with asyncio to run start_matchmaking after a set delay
        self.rating_period_coro = None

        # Synchronization
        self.queue_lock = asyncio.Lock()

        # Confige glicko rating period
        self.setup_rating_period()

    def can_manage_role(self, bot_member, role):
        # Check if the bot can manage a specific role
        return bot_member.top_role.position > role.position and bot_member.guild_permissions.manage_roles

    def update_config(self):
        # Load configuration from the config file
        config = {}  # Initialize config as an empty dictionary
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
        except Exception as e:
            self.logger.warning(f"Failed to load configuration: {str(e)}")  # Fix logging issue

        # Set all configuration values

        # DISCORD CHANNEL ID CONFIG
        self.ACTIVE_MATCHES_CHANNEL_ID = int(config.get('ACTIVE_MATCHES_CHANNEL_ID', 0))
        self.REPORTED_MATCHES_CHANNEL_ID = int(config.get('REPORTED_MATCHES_CHANNEL_ID', 0))
        self.ONGOING_MATCHES_CHANNEL_ID = int(config.get('ONGOING_MATCHES_CHANNEL_ID', 0))
        self.WELCOME_CHANNEL_ID = int(config.get('WELCOME_CHANNEL_ID', 0))

        # CHARACTER SETTINGS CONFIG
        self.characters = config.get('characters', [])
        self.emoji_mapping = config.get('emoji_mapping', {char: "" for char in self.characters})
        self.character_aliases = config.get('character_aliases', {})
        for char in self.characters: # Each character must exist in emoji mapping
            if char not in self.emoji_mapping:
                self.emoji_mapping[char] = ""

        # MATCHMAKING QUEUE CONFIG
        self.queue_status = config.get('queue_status', True)
        self.recent_opponents_limit = config.get('recent_opponents_limit', 3)
        self.max_active_matches = config.get('max_active_matches', 7)  # New parameter

        # GLICKO-2 CONSTANTS
        self.tau = config.get('glicko_tau', 0.3)
        self.default_rating = config.get('glicko_default_rating', 1500)
        self.default_rd = config.get('glicko_default_rd', 350)
        self.default_volatility = config.get('glicko_default_volatility', 0.06)
        self.rating_period_length = config.get('glicko_rating_period_length', 1) # measured in days


    @discord.commands.slash_command(name="setqueue", description="[Admin Command] Open or close the matchmaking queue.")
    @discord.commands.default_permissions(manage_roles=True)
    async def set_queue(self, ctx: discord.ApplicationContext, queue_status: discord.Option(bool, name="enablequeue")):
        # Enable or disable the matchmaking queue
        self.queue_status = queue_status
        if not queue_status:
            self.matchmaking_queue.clear()  # Clear the deque
            self.in_queue = {}
            self.in_match = {}
            await ctx.respond("The matchmaking queue has been disabled.")
        else:
            await ctx.respond("The matchmaking queue has been enabled.")

    # def dead_role(self, ctx, player):
    #     # Check if a player's dan role should be removed
    #     role = None
    #     self.logger.info(f'Checking if dan should be removed as well')
    #     res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={player['discord_id']} AND dan={player['dan']}")
    #     remaining_daniel = res.fetchone()
    #     if not remaining_daniel:
    #         self.logger.info(f"Dan role {player['dan']} will be removed")
    #         role = discord.utils.get(ctx.guild.roles, name=f"Dan {player['dan']}")
    #     return role

    async def score_update(self, ctx, winner, loser):
        # Update scores for a match
        # Format of [Rating, RD, Rankup?, PointDelta]
        winner_rank = [0.0, 0.0, False, 0.0]
        loser_rank = [0.0, 0.0, False, 0.0]
        rankdown = False
        rankup = False

        # glicko-2 calculations
        winner_rating, winner_rd, winner_volatility = winner['glicko_rating'], winner['glicko_rd'], winner['glicko_volatility']
        loser_rating, loser_rd, loser_volatility = loser['glicko_rating'], loser['glicko_rd'], loser['glicko_volatility']
        p1_elapsed_rating_periods = 1.0 # TODO: set to proper period by adding timestamps to db
        p2_elapsed_rating_periods = 1.0

        winner_new_rating, winner_new_rd, winner_new_volatility = self.glicko_update_rating(winner_rating, winner_rd, winner_volatility, [loser_rating], [loser_rd], [1], p1_elapsed_rating_periods)
        loser_new_rating, loser_new_rd, loser_new_volatility = self.glicko_update_rating(loser_rating, loser_rd, loser_volatility, [winner_rating], [winner_rd], [0], p2_elapsed_rating_periods)
        
        # TODO: add a config option to disable this
        loser_new_rating = max(loser_new_rating, self.default_rating)

        winner_rank[0] = winner_new_rating
        winner_rank[1] = winner_new_rd
        winner_rank[3] = winner_new_rating - winner_rating

        loser_rank[0] = loser_new_rating
        loser_rank[1] = loser_new_rd
        loser_rank[3] = loser_new_rating - loser_rating

        # Rank thresholds are hard coded for now
        # Rankup logic
        winner_new_role = False
        winner_old_role_name = self.get_role_name_by_rating(winner_rating)
        winner_new_role_name = self.get_role_name_by_rating(winner_new_rating)
        if winner_old_role_name != winner_new_role_name:
            winner_new_role = True
            winner_rank[2] = True

        # Rankdown logic
        loser_new_role = False
        loser_old_role_name = self.get_role_name_by_rating(loser_rating)
        loser_new_role_name = self.get_role_name_by_rating(loser_new_rating)
        if loser_old_role_name != loser_new_role_name:
            loser_new_role = True
            loser_rank[2] = True

        # Log new scores
        self.logger.info("New Ratings")
        self.logger.info(f"Winner : {winner['player_name']}, {winner_new_rating}±{winner_new_rd}")
        self.logger.info(f"Loser : {loser['player_name']}, {loser_new_rating}±{loser_new_rd}")

        # Update database
        self.database_cur.execute("UPDATE players SET glicko_rating = ?, glicko_rd = ?, glicko_volatility = ? WHERE discord_id=? AND character=?", (winner_new_rating, winner_new_rd, winner_new_volatility, winner['discord_id'], winner['character']))
        self.database_cur.execute("UPDATE players SET glicko_rating = ?, glicko_rd = ?, glicko_volatility = ? WHERE discord_id=? AND character=?", (loser_new_rating, loser_new_rd, loser_new_volatility, loser['discord_id'], loser['character']))
        self.database_con.commit()

        # Update roles on rankup/down
        if winner_new_role:
            self.logger.debug(f"Winning player ranked up, attempting to assign roles")
            highest_rating = self.get_players_highest_rating(winner['player_name'])
            if highest_rating and highest_rating == winner_new_rating: # highest rating they have, role may be duplicate though
                role = discord.utils.get(ctx.guild.roles, name=winner_new_role_name)
                old_role = discord.utils.get(ctx.guild.roles, name=winner_old_role_name)
                member = ctx.guild.get_member(winner['discord_id'])
                bot_member = ctx.guild.get_member(self.bot.user.id)

                if role and old_role and role != old_role and self.can_manage_role(bot_member, role):
                    await member.add_roles(role)
                    await member.remove_roles(old_role)

        if loser_new_role:
            self.logger.debug(f"Losing player ranked down, attempting to assign roles")
            highest_rating = self.get_players_highest_rating(loser['player_name'])
            if highest_rating and (highest_rating == loser_new_rating or loser_new_role_name == self.get_role_name_by_rating(highest_rating)): # have to deal with the case where new rating is less than higest rating, but still goes below the threshold of a rating bracket
                role = discord.utils.get(ctx.guild.roles, name=loser_new_role_name)
                old_role = discord.utils.get(ctx.guild.roles, name=loser_old_role_name)
                member = ctx.guild.get_member(loser['discord_id'])
                bot_member = ctx.guild.get_member(self.bot.user.id)

                if role and old_role and role != old_role and self.can_manage_role(bot_member, role):
                    await member.add_roles(role)
                    await member.remove_roles(old_role)

        return winner_rank, loser_rank

    # Custom decorator for validation
    def is_valid_char(self, char):
        return char in self.characters

    async def character_autocomplete(self, ctx: discord.AutocompleteContext):
        return [character for character in self.characters if character.lower().startswith(ctx.value.lower())]

    async def player_autocomplete(self, ctx: discord.AutocompleteContext):
        res = self.database_cur.execute("SELECT player_name FROM users")
        name_list=res.fetchall()
        names = set([name[0] for name in name_list])
        return [name for name in names if (name.lower()).startswith(ctx.value.lower())]

    @discord.commands.slash_command(name="setrank", description="[Admin Command] Set a player's dan rank and points.")
    @discord.commands.default_permissions(manage_roles=True)
    async def set_rank(self, ctx : discord.ApplicationContext,
                        player_name :  discord.Option(str, autocomplete=player_autocomplete),
                        char : discord.Option(str, name="character", autocomplete=character_autocomplete),
                        glicko_rating :  discord.Option(int),
                        glicko_rd : discord.Option(float, required=False),
                        glicko_volatility : discord.Option(float, required=False)):

        char = self.convert_character_alias(char)
        if not self.is_valid_char(char):
            await ctx.respond(f"Invalid char selected {char}. Please choose a valid char.")
            return

        # sync role stuff
        role_removed = False
        discord_id = None
        res = self.database_cur.execute("SELECT glicko_rating, users.discord_id AS discord_id FROM users JOIN players ON players.discord_id = users.discord_id WHERE player_name=? AND character=?", (player_name, char)).fetchone()
        old_highest_rating = self.get_players_highest_rating(player_name)
        if res:
            discord_id = res['discord_id']
        else:
            await ctx.respond(f"Database entry for player {player_name} on character {char} not found.")

        self.database_cur.execute("UPDATE players SET glicko_rating = ? WHERE discord_id=? AND character=?", (glicko_rating, discord_id, char))
        if glicko_rd is not None:
            self.database_cur.execute("UPDATE players SET glicko_rd = ? WHERE discord_id=? AND character=?", (glicko_rd, discord_id, char))
        if glicko_volatility is not None:
            self.database_cur.execute("UPDATE players SET glicko_variance = ? WHERE discord_id=? AND character=?", (glicko_variance, discord_id, char))    
        self.database_con.commit()
        self.logger.debug(f"Checking for role removal in setrank")
        if old_highest_rating != self.get_players_highest_rating(player_name) and self.get_role_name_by_rating(self.get_players_highest_rating(player_name)) != self.get_role_name_by_rating(old_highest_rating): 
            discord_id = res['discord_id']
            old_role = discord.utils.get(ctx.guild.roles, name=self.get_role_name_by_rating(old_highest_rating))
            new_role = discord.utils.get(ctx.guild.roles, name=self.get_role_name_by_rating(self.get_players_highest_rating(player_name)))
            member = ctx.guild.get_member(res['discord_id'])
            bot_member = ctx.guild.get_member(self.bot.user.id)
            if old_role and self.can_manage_role(bot_member, old_role):
                await member.remove_roles(old_role)
            if new_role and self.can_manage_role(bot_member, new_role):
                await member.add_roles(new_role)


        await ctx.respond(f"{player_name}'s {char} rank updated to be {glicko_rating}{f"±{glicko_rd}" if glicko_rd is not None else ""}{f", volatility={glicko_volatility}" if glicko_volatility is not None else ""}.")

    @discord.commands.slash_command(description="Displays a help message and a list of commands.")
    async def help(self, ctx : discord.ApplicationContext):
        em = discord.Embed(
            title="GBVSR Danisen Bot Command List",
            description="Below is a list of all commands for the GBVSR Danisen Bot. For more information about Danisen, visit <#1433543613404414112>.",
            color=discord.Color.blurple())
        # if self.bot.user.avatar.url: # I dont really like the way the thumbnail looks lol
        #     em.set_thumbnail(
        #         url=self.bot.user.avatar.url)
        self.logger.debug(f"author is {ctx.author}, perms are {ctx.author.guild_permissions}, role specific perm is {ctx.author.guild_permissions.manage_roles}")
        for slash_command in self.walk_commands():
            if not slash_command.default_member_permissions:
                em.add_field(name="/" + slash_command.name, 
                            value=slash_command.description if slash_command.description else slash_command.name, 
                            inline=False) 
                            # fallbacks to the command name incase command description is not defined
            elif slash_command.default_member_permissions < ctx.author.guild_permissions: # check if required perms are a subset of users perms, to see if they can use command
                em.add_field(name="/" + slash_command.name, 
                            value=slash_command.description if slash_command.description else slash_command.name, 
                            inline=False) 
                            # fallbacks to the command name incase command description is not defined

        await ctx.send_response(embed=em)

    #registers player+char to db
    @discord.commands.slash_command(description="Register to the Danisen database!")
    async def register(self, ctx: discord.ApplicationContext,
                       char1: discord.Option(str, name="character", autocomplete=character_autocomplete)):
        player_name = ctx.author.name
        player_discord_id = ctx.author.id
        player_nickname = ctx.author.nick if ctx.author.nick else ctx.author.global_name if ctx.author.global_name else ctx.author.name

        player_nickname = re.subn(r"(?P<char>[\*\-\_\~])", r"\\\g<char>", player_nickname)[0]
        self.logger.debug(f"player nickname post regex is {player_nickname}")

        self.logger.info(f"player nickname is {ctx.author.nick}, player global name is {ctx.author.global_name}")

        char1 = self.convert_character_alias(char1)
        if not self.is_valid_char(char1):
            await ctx.respond(f"Invalid char selected {char1}. Please choose a valid char.")
            return

        # Check if the player is already registered with the character
        res = self.database_cur.execute(
            "SELECT * FROM players WHERE discord_id = ? AND character = ?",
            (player_discord_id, char1)
        ).fetchone()

        if res:
            await ctx.respond(f"You are already registered with the character {char1}.")
            return

        # Check if the player has three characters already registered
        res = self.database_cur.execute(
            "SELECT COUNT(*) AS char_count FROM players WHERE discord_id = ?",
            (player_discord_id,)
        ).fetchone()

        self.logger.info(f"Player has {res["char_count"]} characters.")

        regged_chars = 0
        if res:
            regged_chars = res["char_count"]
            if res["char_count"] >= 3:
                await ctx.respond(f"You are already registered with 3 characters. Please unregister one of your characters before registering a new character.")
                return        

        # If user is not in the users table, insert them into that table first
        res = self.database_cur.execute(
            "SELECT * FROM users WHERE discord_id = ?",
            (player_discord_id,)
        ).fetchone()

        if res:
            self.logger.debug(f"User {player_name} already exists in users table")
        else:
            self.logger.info(f"Adding user {player_name} into users table")
            self.database_cur.execute(
                "INSERT INTO users (discord_id, player_name, nickname, keyword) VALUES (?, ?, ?, ?)", 
                (player_discord_id, player_name, player_nickname, None)
            )
            self.database_con.commit()


        # Insert the new player record
        line = (ctx.author.id, char1, self.default_rating, self.default_rd, self.default_volatility, int(time()))
        self.database_cur.execute(
            "INSERT INTO players (discord_id, character, glicko_rating, glicko_rd, glicko_volatility, last_rating_timestamp) VALUES (?, ?, ?, ?, ?, ?)", 
            line
        )
        self.database_con.commit()

        # Get Discord roles to add to participant
        role_list = []
        char_role = discord.utils.get(ctx.guild.roles, name=char1)
        if char_role:
            role_list.append(char_role)
        self.logger.info(f"Adding to db {player_name} {char1}")

        highest_rating = self.get_players_highest_rating(player_name)
        self.logger.info(f"Registering player's highest dan is {highest_rating}")
        if highest_rating and highest_rating == self.default_rating:
            dan_role = discord.utils.get(ctx.guild.roles, name="新人") # TODO: refactor for configable roles
            if dan_role:
                role_list.append(dan_role)

        participant_role = discord.utils.get(ctx.guild.roles, name="Ranked Bot Participant")
        if participant_role:
            role_list.append(participant_role)

        bot_member = ctx.guild.get_member(self.bot.user.id)
        can_add_roles = all(self.can_manage_role(bot_member, role) for role in role_list)
        if can_add_roles:
            await ctx.author.add_roles(*role_list)
        else:
            self.logger.warning("Could not add roles due to bot's role being too low")

        if regged_chars > 0:
            await ctx.respond(
                f"You are now registered as {player_name}{" " + player_nickname if player_nickname else ""} with {char1}!\n"
                f"You have registered {regged_chars+1}/3 characters. Have fun!"
            )
        else:
            await ctx.respond(
                f"You are now registered as {player_name}{" " + player_nickname if player_nickname else ""} with {char1}!\n"
                "If you wish to add more characters, you can register with up to 3 different characters!\n\n"
                "Welcome to the BBCF ranked ladder!"
            )

    @discord.commands.slash_command(description="Unregister a character from the Danisen database. Note this will reset dan and points.")
    async def unregister(self, ctx : discord.ApplicationContext, 
                    char1 : discord.Option(str, name="character", autocomplete=character_autocomplete)):

        char1 = self.convert_character_alias(char1)
        if not self.is_valid_char(char1):
            await ctx.respond(f"Invalid char selected {char1}. Please choose a valid char.")
            return

        # Check if the player is in a match
        if ctx.author.name in self.in_match and self.in_match[ctx.author.name]:
            await ctx.respond("You cannot unregister while in an active match.")
            return

        # Check if the player is in the queue
        if ctx.author.name in self.in_queue and self.in_queue[ctx.author.name][0]:
            await ctx.respond("You cannot unregister while in the queue. Please leave the queue first.")
            return

        res = self.database_cur.execute("SELECT * FROM players WHERE discord_id=? AND character=?", (ctx.author.id, char1))
        daniel = res.fetchone()

        if daniel == None:
            await ctx.respond("You are not registered with that character")
            return

        self.logger.info(f"Removing {ctx.author.name} {ctx.author.id} {char1} from db")
        self.database_cur.execute("DELETE FROM players WHERE discord_id=? AND character=?", (ctx.author.id, char1))
        self.database_con.commit()

        # Get roles to remove from participant, if they have them.
        role_list = []
        char_role = discord.utils.get(ctx.guild.roles, name=char1)
        if char_role:
            role_list.append(discord.utils.get(ctx.guild.roles, name=char1))
        self.logger.info(f"Removing role {char1} from member")

        unregged_character_role_name = self.get_role_name_by_rating(daniel['glicko_rating'])
        best_chararcter_role_name = None
        if self.get_players_highest_rating(ctx.author.name):
            best_character_role_name = self.get_role_name_by_rating(self.get_players_highest_rating(ctx.author.name))
        role = None
        if unregged_character_role_name != best_chararcter_role_name and (not self.get_players_highest_rating(ctx.author.name) or (self.get_players_highest_rating(ctx.author.name) and daniel['glicko_rating'] > self.get_players_highest_rating(ctx.author.name))):
            role = discord.utils.get(ctx.guild.roles, name=unregged_character_role_name)
        if role:
            role_list.append(role)

        res = self.database_cur.execute("SELECT * FROM players WHERE discord_id=?", (ctx.author.id,)).fetchone()
        if res is None:
            participant_role = discord.utils.get(ctx.guild.roles, name="Ranked Bot Participant")
            if participant_role:
                role_list.append(participant_role)
 
        bot_member = ctx.guild.get_member(self.bot.user.id)
        can_remove_roles = True
        message_text = ""
        if role_list:
            self.logger.info(f"{role_list}")
            for role in role_list:
                can_remove_roles = can_remove_roles and self.can_manage_role(bot_member,role)
            if can_remove_roles:
                await ctx.author.remove_roles(*role_list)
            else:
                message_text += f"Could not remove roles due to bot's role being too low\n\n"
                self.logger.warning(f"Could not remove roles due to bot's role being too low")
        
        if self.get_players_highest_rating(ctx.author.name):
            role = discord.utils.get(ctx.guild.roles, name=self.get_role_name_by_rating(self.get_players_highest_rating(ctx.author.name)))
            member = ctx.author
            bot_member = ctx.guild.get_member(self.bot.user.id)
            if role and self.can_manage_role(bot_member, role):
                await member.add_roles(role)

        message_text += f"You have now unregistered {char1}"
        await ctx.respond(message_text)

    # Commented out for now, no need to do /rank when you can do /profile for someone
    # #rank command to get discord_name's player rank, (can also ignore 2nd param for own rank)
    # @discord.commands.slash_command(description="Get your character rank/Put in a players name to get their character rank!")
    # async def rank(self, ctx : discord.ApplicationContext,
    #             char : discord.Option(str, name="character", autocomplete=character_autocomplete),
    #             discord_name :  discord.Option(str, required=False, autocomplete=player_autocomplete)):

    #     char = self.convert_character_alias(char)
    #     if not self.is_valid_char(char):
    #         await ctx.respond(f"Invalid char selected {char}. Please choose a valid char.")
    #         return
    
    #     if not discord_name:
    #         discord_name = ctx.author.name

    #     members = ctx.guild.members
    #     member = None
    #     for m in members:
    #         if discord_name.lower() == m.name.lower():
    #             member = m
    #             break
    #     if discord_name:
    #         if not member:
    #             await ctx.respond(f"""{discord_name} isn't a member of this server""")
    #             return
    #     else:
    #         member = ctx.author
    #     id = member.id

    #     res = self.database_cur.execute(f"SELECT dan, points, nickname FROM players JOIN users ON players.discord_id = users.discord_id WHERE users.discord_id={id} AND character='{char}'")
    #     data = res.fetchone()
    #     if data:
    #         await ctx.respond(f"""{data['player_name']}'s rank for {char} is Dan {data['dan']}, {round(data['points'], 1):.1f} points""")
    #     else:
    #         await ctx.respond(f"""{member.name} is not registered as {char}.""")

    #leaves the matchmaking queue
    @discord.commands.slash_command(name="leavequeue", description="leave the danisen queue")
    async def leave_queue(self, ctx : discord.ApplicationContext,
                                char : discord.Option(str, name="character", required=False, autocomplete=character_autocomplete)):
        discord_id = ctx.author.id
        self.logger.info(f"{ctx.author.name} requested to leave the queue")
        daniels = [] 

        self.logger.debug(f"leave_queue for player {ctx.author.name} awaiting lock")
        async with self.queue_lock:
            self.logger.debug(f"leave_queue for player {ctx.author.name} acquired lock")
            self.logger.debug(f"current mmq is {self.matchmaking_queue}")
            for member in self.matchmaking_queue:
                self.logger.debug(f"Checking if player {member} should leave queue.")
                if member and (member['discord_id'] == discord_id) and (char is None or (char is not None and member['character'] == char)):
                    self.logger.debug(f"Player {member['player_name']} on character {member['character']} should leave queue.")
                    daniels.append(member)

            if char is not None and daniels != []:
                for daniel in daniels:
                    if daniel in self.matchmaking_queue:
                        self.matchmaking_queue.remove(daniel)

                    self.in_queue[str(daniel['discord_id'])+"@"+daniel['character']][0] = False
                await ctx.respond(f"You have been removed from the queue as {char}.")
            elif daniels != []:
                for daniel in daniels:
                    if daniel in self.matchmaking_queue:
                        self.matchmaking_queue.remove(daniel)

                    self.in_queue[str(daniel['discord_id'])+"@"+daniel['character']][0] = False
                await ctx.respond("You have been removed from the queue on all characters.")
            else:
                await ctx.respond("You are not in queue.")

    #joins the matchmaking queue
    @discord.commands.slash_command(name="joinqueue", description="queue up for rated games")
    async def join_queue(self, ctx : discord.ApplicationContext,
                    char: discord.Option(str, autocomplete=character_autocomplete)):
        await ctx.defer()
        discord_id = ctx.author.id
        rejoin_queue = False

        char = self.convert_character_alias(char)
        if not self.is_valid_char(char):
            await ctx.respond(f"Invalid char selected {char}. Please choose a valid char.")
            return

        #check if q open
        if self.queue_status == False:
            await ctx.respond(f"The matchmaking queue is currently closed")
            return

        #Check if valid character
        res = self.database_cur.execute("SELECT users.discord_id AS discord_id, player_name, nickname, keyword, character, glicko_rating, glicko_rd, glicko_volatility, last_rating_timestamp FROM players JOIN users ON players.discord_id = users.discord_id WHERE users.discord_id=? AND character=?", (discord_id, char))
        daniel = res.fetchone()
        if daniel == None:
            await ctx.respond(f"You are not registered with that character")
            return


        # Update player nickname, could be refactored to another function but idk where else to put it
        player_nickname = ctx.author.nick if ctx.author.nick else ctx.author.global_name if ctx.author.global_name else ctx.author.name
        player_nickname = re.subn(r"(?P<char>[\*\-\_\~])", r"\\\g<char>", player_nickname)[0]
        self.logger.debug(f"player nickname post regex is {player_nickname}")
        if player_nickname != daniel['nickname']:
            self.database_cur.execute("UPDATE users SET nickname = ? WHERE discord_id=?", (player_nickname, ctx.author.id))

        daniel = DanisenRow(daniel)
        daniel['requeue'] = rejoin_queue
        daniel['nickname'] = player_nickname

        self.logger.debug(f"join_queue for player {daniel['player_name']} awaiting lock")
        queue_add_success = False
        async with self.queue_lock:
            self.logger.debug(f"join_queue for player {daniel['player_name']} acquired lock")
            #Check if in Queue already
            # self.logger.debug(f"checking that {str(discord_id)+"@"+char} is in {self.in_queue}: {str(discord_id)+"@"+char in self.in_queue} and {(str(discord_id)+"@"+char in self.in_queue) and self.in_queue[str(discord_id)+"@"+char][0]}")
            if str(discord_id)+"@"+char in self.in_queue and self.in_queue[str(discord_id)+"@"+char][0]:
                await ctx.respond(f"You are already in the queue as that character")
                return

            #check if in a match already
            if discord_id in self.in_match and self.in_match[discord_id]:
                await ctx.respond(f"You are in an active match and cannot queue up")
                return

            if self.in_queue.setdefault(str(discord_id)+"@"+char, [True, deque(maxlen=self.recent_opponents_limit)]):
                self.in_queue[str(discord_id)+"@"+char][0] = True
            self.in_match.setdefault(str(discord_id)+"@"+char, False)

            self.matchmaking_queue.append(daniel)
            queue_add_success = True
        
        if queue_add_success:
            await ctx.respond(f"You've been added to the matchmaking queue with {char}. Current queue length: {len([True for player in self.matchmaking_queue if player])}")
            await self.begin_matchmaking_timer(ctx.interaction, 30)
        else:
            await ctx.respond(f"An error with the queue mutex or code within has occured, please contact and admin.")

        #matchmake
        # if (self.cur_active_matches < self.max_active_matches and  # Taking out automatic matchmaking
        #     len(self.matchmaking_queue) >= 2):
        #     await self.matchmake(ctx.interaction)

    async def rejoin_queue(self, interaction, player):
        if self.queue_status == False:
            return

        res = self.database_cur.execute("SELECT users.discord_id AS discord_id, player_name, nickname, keyword, character, glicko_rating, glicko_rd, glicko_volatility, last_rating_timestamp FROM players JOIN users ON players.discord_id = users.discord_id WHERE users.discord_id=? AND character=?", (player['discord_id'], player['character']))
        db_player = res.fetchone()
        if not db_player:
            return  # Exit if the player is not found in the database

        player = DanisenRow(db_player)  # Transform the database row into a DanisenRow
        player['requeue'] = True

        self.logger.debug(f"rejoin_queue for player {player['player_name']} awaiting lock")
        async with self.queue_lock:
            self.logger.debug(f"rejoin_queue for player {player['player_name']} acquired lock")
            # Ensure the player is initialized in self.in_queue
            if str(player['discord_id'])+"@"+player['character'] not in self.in_queue:
                self.in_queue[str(player['discord_id'])+"@"+player['character']] = [False, deque(maxlen=self.recent_opponents_limit)]

            self.in_queue[str(player['discord_id'])+"@"+player['character']][0] = True
            self.matchmaking_queue.append(player)

        await self.begin_matchmaking_timer(interaction, 30) # Attempt to restart the timer, if it's stopped

    @discord.commands.slash_command(name="viewqueue", description="view players in the queue")
    async def view_queue(self, ctx : discord.ApplicationContext):
        em = discord.Embed(
            title="Current Queue",
            color=discord.Color.blurple())

        self.logger.debug(f"current queue is {self.matchmaking_queue}")
        for player in self.matchmaking_queue:
            if player:
                em.add_field(name=f"{player['nickname']} ({player['character']})", 
                        value=f"{player['glicko_rating']:.0f}±{player['glicko_rd']:.0f} rating", 
                        inline=False) 
        
        await ctx.send_response(embed=em)

    @discord.commands.slash_command(name="startmatchmaking", description="Start matchmaking.")
    async def start_matchmaking(self, ctx: discord.ApplicationContext):
        self.logger.debug(f"matchmake command from start_matchmaking awaiting lock")
        async with self.queue_lock:
            self.logger.debug(f"matchmake command from start_matchmaking acquired lock")
            await self.matchmake(ctx.interaction)
        await ctx.respond("Finished matchmaking")

    async def matchmake(self, ctx: discord.Interaction):
        match_attempts = 0
        #  This is to deal with the case where there is one None in the queue
        if len(self.matchmaking_queue) == 1 and self.matchmaking_queue[0] is None:
            self.matchmaking_queue.popleft()
            return
            
        while (self.cur_active_matches < self.max_active_matches and
               len(self.matchmaking_queue) >= 2):
            self.logger.debug(f"Starting matchmaking loop. Current matchmaking_queue: {list(self.matchmaking_queue)}")

            daniel1 = self.matchmaking_queue.popleft()  # Pop from the left of the deque
            self.logger.debug(f"Dequeued daniel1 from matchmaking_queue: {daniel1}")

            if not daniel1:
                self.logger.warning("Dequeued daniel1 is None. Skipping iteration.")
                continue

            self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][0] = False

            check_queue_member = [player for player in self.matchmaking_queue]
            check_queue_member.sort(key=lambda x: abs(x['glicko_rating'] - daniel1['glicko_rating'])) # sort players by difference in rating
            check_queue_member = deque(check_queue_member) # need to convert to deque for popleft
            self.logger.debug(f"queue to check is {check_queue_member}")

            old_daniels = []  # List to track multiple old_daniel instances
            matchmade = False
            while check_queue_member:  # Continue checking the same dan queue
                daniel2 = check_queue_member.popleft()
                self.logger.debug(f"Dequeued daniel2 from check_queue_member: {daniel2}")

                self.logger.debug(f"player identifier: {str(daniel2['discord_id'])+"@"+daniel2['character']}, daniel1 recent: {self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][1]}")
                if daniel2['discord_id'] in self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][1] or daniel1['discord_id'] in self.in_queue[str(daniel2['discord_id'])+"@"+daniel2['character']][1]:
                    self.logger.debug(f"Skipping daniel2 {daniel2} as they are in daniel1's recent opponents, or vice versa.")
                    continue
                
                if daniel2['discord_id'] == daniel1['discord_id']:
                    self.logger.debug(f"Skipping daniel2 {daniel2} as they are the same user on different characters.")
                    continue

                if daniel2['discord_id'] in self.in_match and self.in_match[daniel2['discord_id']]:
                    self.logger.debug(f"Skipping daniel2 {daniel2} as they are currently in a match as a different character.")
                    continue

                if daniel1['discord_id'] in self.in_match and self.in_match[daniel1['discord_id']]:
                    self.logger.debug(f"Skipping daniel1 chosen from queue {daniel1} as they are currently in a match as a different character.")
                    continue

                # This is an old implementation but I'm keeping it here in case the new one breaks
                # self.in_queue[str(daniel2['discord_id'])+"@"+daniel2['character']] = [False, deque([str(daniel1['discord_id'])+"@"+daniel1['character']], maxlen=self.recent_opponents_limit)] # why does this do this instead of just mutate
                # self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][1].append(str(daniel2['discord_id'])+"@"+daniel2['character'])

                if str(daniel2['discord_id'])+"@"+daniel2['character'] in self.in_queue:
                    self.in_queue[str(daniel2['discord_id'])+"@"+daniel2['character']][0] = False
                    self.in_queue[str(daniel2['discord_id'])+"@"+daniel2['character']][1].append(daniel1['discord_id'])
                else:
                    self.in_queue[str(daniel2['discord_id'])+"@"+daniel2['character']] = [False, deque([daniel1['discord_id']], maxlen=self.recent_opponents_limit)]

                self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][1].append(daniel2['discord_id'])

                # Clean up the main queue for players that have already been matched
                for idx in reversed(range(len(self.matchmaking_queue))):
                    player = self.matchmaking_queue[idx]
                    if player and (player['discord_id'] == daniel2['discord_id']) and (player['character'] == daniel2['character']):
                        self.logger.debug(f"Removing matched player {player} from matchmaking_queue.")
                        self.matchmaking_queue[idx] = None

                self.in_match[daniel1['discord_id']] = True
                self.in_match[daniel2['discord_id']] = True
                matchmade = True
                await self.create_match_interaction(ctx, daniel1, daniel2)
                break

            if not matchmade:
                self.logger.debug(f"No match found for daniel1 {daniel1}. Re-adding to queues.")
                self.matchmaking_queue.append(daniel1)  # Append back to the deque
                self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][0] = True
                match_attempts += 1  # Since we can have multiple players on different chars, we have to check at least half(?) the queue
                if match_attempts > (len(self.in_queue) // 2):
                    self.logger.debug(f"No possible matches for any player in queue.")
                    # shuffle(self.matchmaking_queue)
                    break

    async def create_match_interaction(self, ctx: discord.Interaction, daniel1, daniel2):
        self.cur_active_matches += 1

        # Calucalte if a player can rank up or down from this match
        rankup_potential = await self.check_rankup_potential(daniel1, daniel2)
        self.logger.debug(f"Player rankup potential is {rankup_potential}")

        promotion_alert = " :rotating_light: **PROMOTION MATCH** :rotating_light:"
        demotion_alert = " :rotating_light: **IN DANGER OF DEMOTION** :rotating_light:"

        p1_alert = promotion_alert if rankup_potential[0] == 1 else (demotion_alert if rankup_potential[0] == -1 else "")
        p2_alert = promotion_alert if rankup_potential[1] == 1 else (demotion_alert if rankup_potential[1] == -1 else "")

        self.logger.debug(f"p1_alert is {p1_alert}, p2_alert is {p2_alert}")

        # Randomize room host, if applicable
        room_keyword = (None, 0)
        if daniel1['keyword'] and daniel2['keyword']:
            room_keyword = choice(((daniel1['keyword'], 0), (daniel2['keyword'], 1)))
        elif daniel1['keyword'] or daniel2['keyword']:
            room_keyword = (daniel1['keyword'], 0) if daniel1['keyword'] else (daniel2['keyword'], 1)

        # Send a message in the #active-matches channel
        channel = self.bot.get_channel(self.ONGOING_MATCHES_CHANNEL_ID)
        active_match_msg = None
        if channel:
            active_match_msg = await channel.send(f"[{datetime.now().time().replace(microsecond=0)}] {daniel1['nickname']}'s {daniel1['character']}{self.emoji_mapping[daniel1['character']]}{p1_alert} ({daniel1['glicko_rating']:.0f}±{daniel1['glicko_rd']:.0f} rating) vs {daniel2['nickname']}'s {daniel2['character']}{self.emoji_mapping[daniel2['character']]}{p2_alert} ({daniel2['glicko_rating']:.0f}±{daniel2['glicko_rd']:.0f} rating).{" Room link is " + room_keyword[0] + "." if room_keyword[0] else ""}")
        else:
            await ctx.respond(
                f"Could not find channel to add to current ongoing matches (could be an issue with channel id {self.ONGOING_MATCHES_CHANNEL_ID} or bot permissions)"
            )

        # Create view for dropdown reporting
        view = MatchView(self, daniel1, daniel2, active_match_msg) # Report Match Dropdown
        id1 = f"<@{daniel1['discord_id']}>"
        id2 = f"<@{daniel2['discord_id']}>"        

        # Send the message with the view in the #dani-matches
        channel = self.bot.get_channel(self.ACTIVE_MATCHES_CHANNEL_ID)
        if channel:
            webhook_msg = await channel.send(
                content=f"\n## New Match Created\n### Player 1: {id1} {daniel1['character']} ({daniel1['glicko_rating']:.0f}±{daniel1['glicko_rd']:.0f} rating) {self.emoji_mapping[daniel1['character']]}\n\n### Player 2: {id2} {daniel2['character']} ({daniel2['glicko_rating']:.f}±{daniel2['glicko_rd']:.0f} rating) {self.emoji_mapping[daniel2['character']]}" +\
                (f"\n\nThe room host will be {[id1, id2][room_keyword[1]]}, url {room_keyword[0]} " if room_keyword[0] else f"\n\nNeither player has a Steam ID set, please coordinate the room a text channel.") +\
                "\n\nAll sets are FT3, do not swap characters off of the character you matched as.\nPlease report the set result in the drop down menu after the set! (only players in the match and admins can report it)",
                view=view,
            )
            await webhook_msg.pin()

            # deleting the pin added system message (checking last 5 messages incase some other stuff was posted in the channel in the meantime)
            async for message in channel.history(limit=5):
                if message.type == discord.MessageType.pins_add:
                    await message.delete()
        else:
            await ctx.respond(
                f"Could not find channel to send match message to (could be an issue with channel id {self.ACTIVE_MATCHES_CHANNEL_ID} or bot permissions)"
            )

    #report match score
    @discord.commands.slash_command(name="reportmatch", description="Report a match score")
    @discord.commands.default_permissions(send_polls=True)
    async def report_match(self, ctx: discord.ApplicationContext,
                           player1_name: discord.Option(str, autocomplete=player_autocomplete),
                           char1: discord.Option(str, autocomplete=character_autocomplete),
                           player2_name: discord.Option(str, autocomplete=player_autocomplete),
                           char2: discord.Option(str, autocomplete=character_autocomplete),
                           winner: discord.Option(str, choices=players)):
        char1 = self.convert_character_alias(char1)
        char2 = self.convert_character_alias(char2)
        if not self.is_valid_char(char1):
            await ctx.respond(f"Invalid char1 selected {char1}. Please choose a valid char1.")
            return
        if not self.is_valid_char(char2):
            await ctx.respond(f"Invalid char2 selected {char2}. Please choose a valid char2.")
            return

        player1 = self.get_player(player1_name, char1)
        player2 = self.get_player(player2_name, char2)

        if not player1:
            await ctx.respond(f"No player named {player1_name} with character {char1}")
            return
        if not player2:
            await ctx.respond(f"No player named {player2_name} with character {char2}")
            return

        self.logger.info(f"Reported match {player1_name} vs {player2_name} as {winner} win")
        if winner == "player1":
            winner_rank, loser_rank = await self.score_update(ctx, player1,player2)
            winner = player1['nickname']
            winner_id = player1['discord_id']
            winner_char = player1['character']
            winner_old_rating = player1['glicko_rating']
            winner_old_rd = player1['glicko_rd']
            loser = player2['nickname']
            loser_id = player2['discord_id']
            loser_char = player2['character']
            loser_old_rating = player2['glicko_rating']
            loser_old_rd = player2['glicko_rd']
        else:
            winner_rank, loser_rank = await self.score_update(ctx, player2, player1)
            winner = player2['nickname']
            winner_id = player2['discord_id']
            winner_char = player2['character']
            winner_old_rating = player2['glicko_rating']
            winner_old_rd = player2['glicko_rd']
            loser = player1['nickname']
            loser_id = player1['discord_id']
            loser_char = player1['character']
            loser_old_rating = player1['glicko_rating']
            loser_old_rd = player1['glicko_rd']

        self.logger.info(f"Adding match of {player1['player_name']} vs {player2['player_name']} into matches table")
        self.database_cur.execute(
            "INSERT INTO matches (winner_discord_id, winner_character, loser_discord_id, loser_character) VALUES (?, ?, ?, ?)", 
            (winner_id, winner_char, loser_id, loser_char)
        )
        self.database_con.commit()

        rankup_message = ", Rank bracket up!" if winner_rank[2] else ""
        rankdown_message = ", Rank bracket down..." if loser_rank[2] else ""

        await ctx.respond(
            f"### The match has been reported as <@{winner_id}>'s victory over <@{loser_id}>!\n"
            f"{winner}'s {winner_char} {self.emoji_mapping[winner_char]}: {winner_old_rating:.0f}±{winner_old_rd:.0f} → **{winner_rank[0]:.0f}±{winner_rank[1]:.0f}** (+{winner_rank[3]:.0f} rating){rankup_message})\n"
            f"{loser}'s {loser_char} {self.emoji_mapping[loser_char]}: {loser_old_rating:.0f}±{loser_old_rd:.0f} → **{loser_rank[0]:.0f}±{loser_rank[1]:.0f}** ({loser_rank[3]:.0f} rating){rankdown_message})"
        )

    #report match score for the queue
    async def report_match_queue(self, interaction: discord.Interaction, player1, player2, winner):
        if (winner == "player1") :
            winner_rank, loser_rank = await self.score_update(interaction, player1,player2)
            winner = player1['nickname']
            winner_id = player1['discord_id']
            winner_char = player1['character']
            winner_old_rating = player1['glicko_rating']
            winner_old_rd = player1['glicko_rd']
            loser = player2['nickname']
            loser_id = player2['discord_id']
            loser_char = player2['character']
            loser_old_rating = player2['glicko_rating']
            loser_old_rd = player2['glicko_rd']
        else:
            winner_rank, loser_rank = await self.score_update(interaction, player2,player1)
            winner = player2['nickname']
            winner_id = player2['discord_id']
            winner_char = player2['character']
            winner_old_rating = player2['glicko_rating']
            winner_old_rd = player2['glicko_rd']
            loser = player1['nickname']
            loser_id = player1['discord_id']
            loser_char = player1['character']
            loser_old_rating = player1['glicko_rating']
            loser_old_rd = player1['glicko_rd']

        self.logger.info(f"Adding match of {player1['player_name']} vs {player2['player_name']} into matches table")
        self.database_cur.execute(
            "INSERT INTO matches (winner_discord_id, winner_character, loser_discord_id, loser_character) VALUES (?, ?, ?, ?)", 
            (winner_id, winner_char, loser_id, loser_char)
        )
        self.database_con.commit()

        view = RequeueView(self, player1, player2)
        rankup_message = ", Rank bracket up!" if winner_rank[2] else ""
        rankdown_message = ", Rank bracket down..." if loser_rank[2] else ""

        channel = self.bot.get_channel(self.REPORTED_MATCHES_CHANNEL_ID)
        if channel:
            await channel.send(
                content=f"### The match has been reported as <@{winner_id}>'s victory over <@{loser_id}>!\n"
                f"{winner}'s {winner_char} {self.emoji_mapping[winner_char]}: {winner_old_rating:.0f}±{winner_old_rd:.0f} → **{winner_rank[0]:.0f}±{winner_rank[1]:.0f}** (+{winner_rank[3]:.0f} rating){rankup_message})\n"
                f"{loser}'s {loser_char} {self.emoji_mapping[loser_char]}: {loser_old_rating:.0f}±{loser_old_rd:.0f} → **{loser_rank[0]:.0f}±{loser_rank[1]:.0f}** ({loser_rank[3]:.0f} rating){rankdown_message})",
                view=view
                )
        else:
            self.logger.warning("No Report Matches Channel")

    # Temporarily disabled, no need to see players of a specific dan
    # @discord.commands.slash_command(description="See players in a specific dan")
    # async def dan(self, ctx: discord.ApplicationContext,
    #               dan: discord.Option(int, min_value=DEFAULT_DAN, max_value=MAX_DAN_RANK)):
    #     daniels = self.get_players_by_dan(dan)
    #     data = [
    #         {
    #             "name": f"{daniel['player_name']} {daniel['character']}",
    #             "value": f"Dan {daniel['dan']}, {round(daniel['points'], 1)} points"
    #         }
    #         for daniel in daniels
    #     ]
    #     embeds = self.create_paginated_embeds(f"Dan {dan}", data, MAX_FIELDS_PER_EMBED, colour=self.dan_colours[dan - 1])
    #     paginator = pages.Paginator(pages=embeds)

    #     await paginator.respond(ctx.interaction, ephemeral=False)

    # Add a helper function for paginated embeds
    def create_paginated_embeds(self, title, data, fields_per_page, colour=None):
        """Helper function to create paginated embeds."""
        page_list = []
        fields_per_page += 1 # Includes Title
        total_pages = (len(data) // fields_per_page) + 1
        items_per_page = len(data) // total_pages
        for page in range(total_pages):
            em = discord.Embed(title=f"{title} ({page + 1}/{total_pages})", colour=colour)
            page_list.append(em)
            for idx in range(page * items_per_page, min((page + 1) * items_per_page, len(data))):
                em.add_field(name=f"#{idx+1}: {data[idx]['name']}", value=f"Current Rank: {data[idx]['value']}", inline=False)
        return page_list

    def create_paginated_character_embeds(self, title, data, fields_per_page, colour=None):
        """Helper function to create paginated embeds."""
        page_list = []
        fields_per_page += 1 # Includes Title
        total_pages = (len(data) // fields_per_page) + 1
        items_per_page = len(data) // total_pages
        for page in range(total_pages):
            em = discord.Embed(title=f"{title} ({page + 1}/{total_pages})", colour=colour)
            page_list.append(em)
            for idx in range(page * items_per_page, min((page + 1) * items_per_page, len(data))):
                em.add_field(name=f"{data[idx]['name']}: {data[idx]['character_count']} registered player(s)", value=f"Total Wins: {data[idx]['wins']}, Total Losses: {data[idx]['losses']}, Winrate: {data[idx]['winrate']:.1f}%", inline=False)
        return page_list

    def create_paginated_dan_embeds(self, title, data, fields_per_page, colour=None):
        """Helper function to create paginated embeds."""
        page_list = []
        fields_per_page += 1 # Includes Title
        total_pages = (len(data) // fields_per_page) + 1
        items_per_page = len(data) // total_pages
        for page in range(total_pages):
            em = discord.Embed(title=f"{title} ({page + 1}/{total_pages})", colour=colour)
            page_list.append(em)
            for idx in range(page * items_per_page, min((page + 1) * items_per_page, len(data))):
                em.add_field(name=f"{data[idx]['name']}:", value=f"Current Players: {data[idx]['value']}", inline=False)
        return page_list

    def create_danisen_stat_embed(self, title, data, fields_per_page, colour=None):
        """Helper function to create paginated embeds."""
        page_list = []
        em = discord.Embed(title=f"{title}", colour=colour)
        page_list.append(em)
        em.add_field(name=f"Current Unique Players", value=f"{data['accounts']} people registered", inline=False)
        em.add_field(name=f"Total Characters Registered", value=f"{data['characters']} characters registered", inline=False)
        em.add_field(name=f"Total Matches Played", value=f"{data['total_games']} sets", inline=False)

        return page_list

    # Refactor danisen_stats to use the helper function
    @discord.commands.slash_command(name="serverstats", description="See various statistics about the danisen")
    async def danisen_stats(self, ctx: discord.ApplicationContext):
        danisen_info = self.database_cur.execute(
            "SELECT accounts, characters, total_games FROM (SELECT COUNT(*) AS accounts FROM users) AS AccountsTable JOIN (SELECT COUNT(*) AS characters FROM players) AS CharactersTable JOIN (SELECT COUNT(*) AS total_games FROM matches) AS MatchesTable"
        ).fetchone()
        char_info = self.database_cur.execute(
            "SELECT CharCountTable.character AS name, character_count, wins, losses, ROUND(100.0 * wins / (wins + losses), 1) AS winrate FROM (SELECT character, COUNT(*) AS character_count FROM players GROUP BY character) AS CharCountTable JOIN (SELECT winner_character AS character, COUNT(*) AS wins FROM matches GROUP BY winner_character) AS CharWinTable ON CharCountTable.character = CharWinTable.character JOIN (SELECT loser_character AS character, COUNT(*) AS losses FROM matches GROUP BY loser_character) AS CharLossTable ON CharCountTable.character = CharLossTable.character GROUP BY CharCountTable.character ORDER BY character_count DESC"
        ).fetchall()
        # dan_count = self.database_cur.execute(
        #     "SELECT dan AS name, COUNT(*) AS value FROM players GROUP BY dan ORDER BY dan"
        # ).fetchall()

        # reformat dan count as their names are just numbers
        # dan_count = [{"name": f"Dan {dan['name']}", "value": dan['value']} for dan in dan_count]
        danisen_pages = self.create_danisen_stat_embed("General Danisen Stats", danisen_info, MAX_FIELDS_PER_EMBED)
        char_pages = self.create_paginated_character_embeds("Character Usage Stats", char_info, MAX_FIELDS_PER_EMBED)
        # dan_pages = self.create_paginated_dan_embeds("Dan Stats", dan_count, MAX_FIELDS_PER_EMBED, colour=discord.Color.blurple())
        dan_pages = [] # TEMP

        paginator = pages.Paginator(pages=danisen_pages + char_pages + dan_pages)
        await paginator.respond(ctx.interaction, ephemeral=False)

    # I've currently commented this out, I intend to reimplement it using a different sqlite table and more extensive stats tracking

    # Refactor leaderboard to use the helper function
    @discord.commands.slash_command(description="See the top players")
    async def leaderboard(self, ctx: discord.ApplicationContext):
        daniels = self.database_cur.execute(
            "SELECT nickname || '''s ' || character AS name, CAST(ROUND(glicko_rating, 0) AS INT) || '±' || CAST(ROUND(glicko_rd, 0) AS INT) || ' rating' AS value "
            "FROM players JOIN users ON players.discord_id = users.discord_id ORDER BY glicko_rating DESC, glicko_rd ASC"
        ).fetchall()

        leaderboard_pages = self.create_paginated_embeds("Top Characters", daniels, MAX_FIELDS_PER_EMBED)
        paginator = pages.Paginator(pages=leaderboard_pages)
        await paginator.respond(ctx.interaction, ephemeral=False)

    @discord.commands.slash_command(name="updatemaxmatches", description="[Admin Command] Update max matches for the queue system")
    @discord.commands.default_permissions(manage_messages=True)
    async def update_max_matches(self, ctx : discord.ApplicationContext,
                                 max : discord.Option(int, min_value=1)):
        self.max_active_matches = max
        await ctx.respond(f"Max matches updated to {max}")
        # if (self.cur_active_matches < self.max_active_matches and  # Taking out automatic matchmaking
        # len(self.matchmaking_queue) >= 2):
        #     await self.matchmake(ctx.interaction)

    @discord.commands.slash_command(name="viewconfig", description="[Admin Command] View current bot configuration.")
    @discord.commands.default_permissions(manage_guild=True)
    async def view_config(self, ctx: discord.ApplicationContext):
        """Displays the current configuration loaded from the config file."""
        # Try to load the raw config file so user can see exactly what's persisted
        config = {}
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
        except Exception as e:
            self.logger.warning(f"Failed to load configuration for view: {e}")

        # Fallback to runtime attributes if some keys are missing
        merged = dict(DEFAULT_CONFIG)
        merged.update(config)
        # Also include some runtime-derived values
        merged['max_active_matches'] = self.max_active_matches
        merged['queue_status'] = self.queue_status
        merged['total_dans'] = self.total_dans

        em = discord.Embed(title="Current Configuration", color=discord.Color.blurple())
        for k, v in merged.items():
            em.add_field(name=str(k), value=str(v), inline=False)

        await ctx.respond(embed=em, ephemeral=True)

    @discord.commands.slash_command(name="setconfig", description="[Admin Command] Set a configuration key.")
    @discord.commands.default_permissions(manage_guild=True)
    async def set_config(self, ctx: discord.ApplicationContext,
                         key: discord.Option(str, choices=[
                             "ACTIVE_MATCHES_CHANNEL_ID", "REPORTED_MATCHES_CHANNEL_ID", "ONGOING_MATCHES_CHANNEL_ID",
                             "total_dans", "minimum_derank", "maximum_rank_difference",
                             "rank_gap_for_more_points_1", "rank_gap_for_more_points_2" "point_rollover", "queue_status",
                             "recent_opponents_limit", "max_active_matches", "special_rank_up_rules"
                         ]),
                         value: discord.Option(str)):
        """Update a single configuration key and persist it to disk."""
        # Load existing config
        cfg = dict(DEFAULT_CONFIG)
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    loaded = json.load(f)
                    cfg.update(loaded)
        except Exception as e:
            self.logger.warning(f"Failed to load existing config while setting key: {e}")

        # Determine expected type from DEFAULT_CONFIG when possible
        expected = DEFAULT_CONFIG.get(key, None)

        def parse_to_expected(val_str, expected_default):
            # If DEFAULT_CONFIG provides a default, use its type
            if expected_default is not None:
                target_type = type(expected_default)
            else:
                # Fallback heuristics
                if key.upper().endswith('CHANNEL_ID') or 'CHANNEL' in key.upper():
                    target_type = str
                elif key in ('point_rollover', 'queue_status', 'special_rank_up_rules'):
                    target_type = bool
                else:
                    # default to int for most numeric-like config options
                    target_type = int

            s = val_str.strip()
            # Booleans
            if target_type is bool:
                low = s.lower()
                if low in ('true', '1', 'yes', 'on'):
                    return True
                if low in ('false', '0', 'no', 'off'):
                    return False
                # try JSON parse
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, bool):
                        return parsed
                except Exception:
                    pass
                # fallback: non-empty string => True
                return bool(s)

            # Integers
            if target_type is int:
                try:
                    return int(s)
                except Exception:
                    try:
                        parsed = json.loads(s)
                        if isinstance(parsed, (int, float)):
                            return int(parsed)
                    except Exception:
                        pass
                    # final fallback: 0
                    return 0

            # Strings
            if target_type is str:
                return s

            # Fallback: try json then return raw string
            try:
                return json.loads(s)
            except Exception:
                return s

        parsed_value = parse_to_expected(value, expected)

        # Store the parsed value
        cfg[key] = parsed_value

        # Ensure the config dir exists and write back
        try:
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            with open(self.config_path, 'w') as f:
                json.dump(cfg, f, indent=4)
        except Exception as e:
            self.logger.error(f"Failed to persist configuration: {e}")
            await ctx.respond(f"Failed to persist configuration: {e}")
            return

        # Reload runtime config
        try:
            self.update_config()
        except Exception as e:
            self.logger.warning(f"update_config failed after setting config: {e}")

        await ctx.respond(f"Configuration key `{key}` updated to `{parsed_value}`", ephemeral=True)

    def get_player(self, player_name, character):
        res = self.database_cur.execute(
            "SELECT users.discord_id AS discord_id, player_name, nickname, keyword, character, glicko_rating, glicko_rd, glicko_volatility FROM players JOIN users ON players.discord_id = users.discord_id WHERE player_name=? AND character=?", 
            (player_name, character)
        )
        return res.fetchone()

    @discord.commands.slash_command(description="View your or another player's profile")
    async def profile(self, ctx: discord.ApplicationContext, 
                      discord_name: discord.Option(str, name="discordname", autocomplete=player_autocomplete, required=False, default=None)):
        """Lists all registered characters for a player along with their ranks and points."""
        # Determine the target player
        # await ctx.response.defer()

        if discord_name:
            members = ctx.guild.members
            member = next((m for m in members if discord_name.lower() == m.name.lower()), None)
            if not member:
                await ctx.respond(f"{discord_name} isn't a member of this server.")
                return
        else:
            member = ctx.author

        # Fetch all characters for the player
        res = self.database_cur.execute(
            "SELECT character, glicko_rating, glicko_rd, glicko_volatility FROM players WHERE discord_id = ?", 
            (member.id,)
        ).fetchall()

        if not res:
            await ctx.respond(f"{member.name} has no registered characters.")
            return

        user_res = self.database_cur.execute( # implicitly required to exist based on registered characters
            "SELECT * FROM users WHERE discord_id = ?",
            (member.id,)
        ).fetchone()

        player_highest_rating = self.get_players_highest_rating(member.name)
        dan_colour = discord.utils.get(ctx.guild.roles, name=self.get_role_name_by_rating(player_highest_rating)).color

        # Create an embed to display the profile
        em = discord.Embed(
            title=f"{user_res['nickname']}'s Profile",
            color=dan_colour
        )
        if member.avatar:
            em.set_thumbnail(url=member.avatar.url)

        em.add_field(
            name=f"Player Information:",
            value=f"",
            inline=False
        )

        winrate_info = self.get_winrate_by_id(user_res['discord_id'])

        em.add_field(
            name=f"Set Winrate:",
            value=f"{winrate_info[0]:.2f}%, ({winrate_info[1]}W, {winrate_info[2]}L)",
            inline=False
        )

        if user_res["keyword"]:
            em.add_field(
                name=f"Room Password:",
                value=f"`{user_res["keyword"]}`",
                inline=True
            )
        else:
            em.add_field(
                name=f"Room Link:",
                value=f"None (set one with /setsteamid)",
                inline=True
            )

        em.add_field(
            name=f"Characters:",
            value=f"",
            inline=False
        )

        char_winrates = self.get_all_char_winrate_by_id(user_res['discord_id'])

        for row in res:
            if row['character'] in char_winrates:
                em.add_field(
                    name=f"{row["character"]} {self.emoji_mapping[row['character']]}", 
                    value=f"{row['glicko_rating']:.0f}±{row['glicko_rd']:.0f} rating. {char_winrates[row['character']][2]:.0f}% Winrate ({char_winrates[row['character']][0]}W, {char_winrates[row['character']][1]}L)", 
                    inline=False
                )
            else:
                em.add_field(
                    name=f"{row["character"]} {self.emoji_mapping[row['character']]}", 
                    value=f"{row['glicko_rating']:.0f}±{row['glicko_rd']:.0f} rating. 0.00% Winrate (0W, 0L)", 
                    inline=False
                )

        await ctx.respond(embed=em)

    # Helper function
    # Returns the highest Dan rank on any character registered by this player. If the player has no characters registered, return None
    def get_players_highest_rating(self, player_name: str):
        res = self.database_cur.execute("SELECT MAX(glicko_rating) as max_rating FROM players JOIN users ON players.discord_id = users.discord_id WHERE player_name=?", (player_name,)).fetchone()
        if res:
            return res['max_rating']
        else:
            return res

    # Command Aliases for common commands
    @discord.commands.slash_command(name="jq", description="short for /joinqueue")
    async def join_queue_alias(self, ctx : discord.ApplicationContext,
                    char: discord.Option(str, autocomplete=character_autocomplete)):
        await self.join_queue(ctx, char)
        
    @discord.commands.slash_command(name="lq", description="short for /leavequeue")
    async def leave_queue_alias(self, ctx : discord.ApplicationContext,
                                char : discord.Option(str, name="character", required=False, autocomplete=character_autocomplete)):
        await self.leave_queue(ctx, char)

    @discord.commands.slash_command(name="vq", description="short for /viewqueue")
    async def view_queue_alias(self, ctx : discord.ApplicationContext):
        await self.view_queue(ctx)

    # This function is used to create an asynchronous task for the matchmaking timer if there is not one running
    async def begin_matchmaking_timer(self, interaction: discord.Interaction, delay: int):
        self.logger.debug(f"Attempting to start matchmaking timer")
        if self.matchmaking_coro is None or self.matchmaking_coro.done():
            self.matchmaking_coro = asyncio.create_task(self.matchmaking_timer(interaction, delay))
            self.logger.debug(f"Matchmaking timer started with {delay} seconds")

    async def matchmaking_timer(self, interaction: discord.Interaction, delay: int):
        await asyncio.sleep(delay)
        self.logger.debug(f"Timer ended, attempting matchmaking")
        self.logger.debug(f"matchmake command from matchmaking_timer awaiting lock")
        async with self.queue_lock:
            self.logger.debug(f"matchmake command from matchmaking_timer acquired lock")
            await self.matchmake(interaction)

        while len(self.matchmaking_queue) > 0:
            self.logger.debug(f"players still detected in queue, restarting timer")
            await asyncio.sleep(delay)
            self.logger.debug(f"Timer ended, attempting matchmaking")
            self.logger.debug(f"matchmake command from matchmaking_timer awaiting lock")
            async with self.queue_lock:
                self.logger.debug(f"matchmake command from matchmaking_timer acquired lock")
                await self.matchmake(interaction)

        self.logger.debug(f"Not restarting timer, no players in queue")

    @discord.commands.slash_command(name="setsteamid", description="Assign a default room password to your profile")
    async def set_room_password(self, ctx: discord.ApplicationContext, pw: discord.Option(str, name="id", required=True)):
        if not pw.isalnum():
            await ctx.respond(f"Invalid room password `{pw}`. Please assure the password is alphanumeric.")
            return
        full_pw_url = "https://steamjoin.com/" + pw
        self.database_cur.execute("UPDATE users SET keyword = ? WHERE discord_id=?", (full_pw_url, ctx.author.id))
        self.database_con.commit()
        await ctx.respond(f"Default room password updated.")

    @discord.commands.slash_command(name="removesteamid", description="Remove the room password from your profile, if one is assigned")
    async def remove_room_password(self, ctx: discord.ApplicationContext):
        self.database_cur.execute("UPDATE users SET keyword = NULL WHERE discord_id=?", (ctx.author.id,))
        self.database_con.commit()
        await ctx.respond(f"Default room password removed.")

    async def check_rankup_potential(self, player1, player2):
        return [0,0]
        # TODO: fix for configurable ranks
        # # Determine rankup points based on rank type
        # rankup_points_p1 = RANKUP_POINTS_SPECIAL if player1['dan'] >= SPECIAL_RANK_THRESHOLD else RANKUP_POINTS_NORMAL
        # rankup_points_p2 = RANKUP_POINTS_SPECIAL if player2['dan'] >= SPECIAL_RANK_THRESHOLD else RANKUP_POINTS_NORMAL

        # # The return array, index 0 is p1 index 1 is p2, value of 0 means nothing, 1 means rankup chance, -1 means rankdown chance
        # ret = [0, 0]

        # p1_current_points = player1['points']
        # p2_current_points = player2['points']

        # p1_point_potential = [1.0, -1.0] #default
        # p2_point_potential = [1.0, -1.0]

        # if player1['dan'] >= player2['dan'] + self.rank_gap_for_more_points_2: # player1 four or more above player2
        #     p1_point_potential = [0.3, -1]
        #     p2_point_potential = [3, -0.3]
        # elif player1['dan'] >= player2['dan'] + self.rank_gap_for_more_points_1: # player1 two or three above player2
        #     p1_point_potential = [0.5, -1]
        #     p2_point_potential = [2, -0.5]
        # elif player2['dan'] >= player1['dan']  + self.rank_gap_for_more_points_2: # player2 four or more above player1
        #     p1_point_potential = [3, -0.3]
        #     p2_point_potential = [0.3, -1]
        # elif player2['dan'] >= player1['dan'] + self.rank_gap_for_more_points_1: # player2 two or three above player1
        #     p1_point_potential = [2, -0.5]
        #     p2_point_potential = [0.5, -1]
        

        # # Rankup logic with special rules and Rankdown logic
        # if p1_current_points + p1_point_potential[0] >= rankup_points_p1 and (not self.special_rank_up_rules or (self.special_rank_up_rules and player1['dan'] >= SPECIAL_RANK_THRESHOLD and player2['dan'] >= SPECIAL_RANK_THRESHOLD)):
        #     ret[0] = 1
        # elif p1_current_points + p1_point_potential[1] <= RANKDOWN_POINTS: # adds negative value
        #     ret[0] = -1
        # if p2_current_points + p2_point_potential[0] >= rankup_points_p2 and (not self.special_rank_up_rules or (self.special_rank_up_rules and player1['dan'] >= SPECIAL_RANK_THRESHOLD and player2['dan'] >= SPECIAL_RANK_THRESHOLD)):
        #     ret[1] = 1
        # elif p2_current_points + p2_point_potential[1] <= RANKDOWN_POINTS: # adds negative value
        #     ret[1] = -1

        # return ret 

    # Returns in format (percentage, wins, losses)
    def get_winrate_by_id(self, discord_id: int):
        winning_sets = 0
        losing_sets = 0

        res = self.database_cur.execute("SELECT COUNT(*) AS wins FROM matches WHERE winner_discord_id=?", (discord_id,)).fetchone()
        if res:
            winning_sets = res['wins']

        res = self.database_cur.execute("SELECT COUNT(*) AS losses FROM matches WHERE loser_discord_id=?", (discord_id,)).fetchone()
        if res:
            losing_sets = res['losses']

        if winning_sets == 0 and losing_sets == 0:
            return (0,0,0)
        else:
            return (100 * (winning_sets / (winning_sets + losing_sets)), winning_sets, losing_sets)

    def get_all_char_winrate_by_id(self, discord_id: int):
        ret = {} # in the form {character: [wins, losses, winrate]}
        res = self.database_cur.execute("SELECT winner_character AS character, COUNT(*) AS wins FROM matches WHERE winner_discord_id=? GROUP BY winner_character", (discord_id,)).fetchall()
        for char_res in res:
            if char_res['character'] not in ret:
                ret[char_res['character']] = [char_res['wins'], 0, 100.0]
            else:
                ret[char_res['character']][0] = char_res['wins']

        res = self.database_cur.execute("SELECT loser_character AS character, COUNT(*) AS losses FROM matches WHERE loser_discord_id=? GROUP BY loser_character", (discord_id,)).fetchall()
        for char_res in res:
            if char_res['character'] not in ret:
                ret[char_res['character']] = [0, char_res['losses'], 0.0]
            else:
                ret[char_res['character']][1] = char_res['losses']

        self.logger.debug(f"all_char_winrate is {ret}")
        for char in ret:
            if ret[char][0] > 0 or ret[char][1] > 0:
                ret[char][2] = 100 * ret[char][0] / (ret[char][0] + ret[char][1])
            else:
                ret[char][2] = 0.0

        self.logger.debug(f"all_char_winrate after winrate calc is {ret}")
        return ret


    def get_total_matches_by_id(self, discord_id: int):
        total_sets = 0
        res = self.database_cur.execute("SELECT COUNT(*) AS sets FROM matches WHERE winner_discord_id=? OR loser_discord_id=?", (discord_id, discord_id)).fetchone()
        if res:
            total_sets = res['sets']
        
        return total_sets

    
    @discord.commands.slash_command(name="removelastmatchinstance", description="[Admin Command] Remove the last match instance of p1 vs p2, no ordering")
    @discord.commands.default_permissions(manage_guild=True)
    async def remove_last_match_instance(self, ctx: discord.ApplicationContext,
                                               player1: discord.Option(str, name="player1", required=True, autocomplete=player_autocomplete),
                                               player2: discord.Option(str, name="player2", required=True, autocomplete=player_autocomplete)):
        p1_id = 0
        p2_id = 0

        self.logger.debug(f"Attempting to find match to remove between {player1}" and {player2})
        res = self.database_cur.execute("SELECT discord_id FROM users WHERE player_name=?", (player1,)).fetchone()
        if res:
            p1_id = res['discord_id']
        else:
            await ctx.respond(f"Player 1 ({player1}) is not registered to the Danisen database.")
            return

        res = self.database_cur.execute("SELECT discord_id FROM users WHERE player_name=?", (player2,)).fetchone()
        if res:
            p2_id = res['discord_id']
        else:
            await ctx.respond(f"Player 2 ({player2}) is not registered to the Danisen database.")
            return

        res = self.database_cur.execute("SELECT MAX(id) AS id FROM matches WHERE (winner_discord_id=? AND loser_discord_id=?) OR (winner_discord_id=? AND loser_discord_id=?)", (p1_id, p2_id, p2_id, p1_id)).fetchone()
        if res and res['id']:
            self.logger.debug(f"Match between players found, removing from db")
            self.database_cur.execute("DELETE FROM matches WHERE id=?", (res['id'],))
            self.database_con.commit()
            await ctx.respond(f"Latest match successfully removed (id = {res['id']})")
            return
        else:
            await ctx.respond(f"No match found between")
            return

    # Generates an invite link to the 
    # @discord.commands.slash_command(name="getinvite", description=f"Get a 1 use invite link once a week, usable only by higher dans")
    # async def get_invite_link(self, ctx: discord.ApplicationContext):
    #     bot_member = ctx.guild.get_member(self.bot.user.id)
    #     if not bot_member.guild_permissions.create_instant_invite:
    #         await ctx.respond("The bot does not have the permissions to create invites")
    #         return

    #     max_dan = self.get_players_highest_dan(ctx.author.name)
    #     res = self.database_cur.execute(f"SELECT (UNIXEPOCH('now') - timestamp) AS timediff, UNIXEPOCH('now') AS timenow, invite_link FROM invites WHERE discord_id={ctx.author.id}").fetchone()
    #     if max_dan and max_dan >= self.minimum_invite_dan:
    #         if not res:
    #             self.logger.debug(f"User {ctx.author.name} not in invites table, generating link and adding")
    #             welcome_channel = self.bot.get_channel(self.WELCOME_CHANNEL_ID)
    #             created_invite = await welcome_channel.create_invite(max_age=604800, max_uses=1, unique=True, reason=f"Created by user {ctx.author.name} with /getinvite")
    #             self.database_cur.execute(f"INSERT INTO invites (discord_id, invite_link, timestamp) VALUES (?, ?, UNIXEPOCH('now'))", (ctx.author.id, created_invite.url))
    #             self.database_con.commit()
    #             await ctx.respond(f"New invite link generated: {created_invite.url}. You will be able to recieve another link <t:{int(time()) + 604800}:R>, the original link will also expire at that time. You can use this command at any time to check the generated link.", ephemeral=True)
    #             return
    #         elif (res and res['timediff'] >= 604800): 
    #             self.logger.debug(f"User {ctx.author.name} found in invites table, generating link and updating.")
    #             welcome_channel = self.bot.get_channel(self.WELCOME_CHANNEL_ID)
    #             created_invite = await welcome_channel.create_invite(max_age=604800, max_uses=1, unique=True, reason=f"Created by user {ctx.author.name} with /getinvite")
    #             self.database_cur.execute(f"UPDATE invites SET invite_link='{created_invite.url}', timestamp=UNIXEPOCH('now') WHERE discord_id={ctx.author.id}")
    #             self.database_con.commit()
    #             await ctx.respond(f"New invite link generated: {created_invite.url}. You will be able to recieve another link <t:{(604800 - res['timediff']) + res['timenow']}:R>, the original link will also expire at that time. You can use this command at any time to check the generated link.", ephemeral=True)
    #             return
    #         elif res:
    #             await ctx.respond(f"You will be able to recieve another link <t:{(604800 - res['timediff']) + res['timenow']}:R>. Your last invite link was: {res['invite_link']}.", ephemeral=True)
    #             return
    #     elif (res and res['timediff'] < 604800):
    #         await ctx.respond(f"You will be able to recieve another link <t:{(604800 - res['timediff']) + res['timenow']}:R>. Your last invite link was: {res['invite_link']}.", ephemeral=True)
    #         return
    #     elif res:
    #         await ctx.respond(f"Your last invite link has expired, and you are no longer a high enough Dan (Dan {self.minimum_invite_dan}+) to generate a new invite link.", ephemeral=True)
    #         return
    #     else:
    #         await ctx.respond(f"This command is only available for players Dan {self.minimum_invite_dan} and above.", ephemeral=True)
    #         return

    # Returns the character if an alias is found, otherwise returns the input
    def convert_character_alias(self, character: str):
        lower_char = character.lower()
        ret = character
        if lower_char in self.character_aliases:
            ret = self.character_aliases[lower_char]
        return ret

    @discord.commands.slash_command(name="updaterecentmatchlimit", description=f"[Admin Command]")
    @discord.commands.default_permissions(manage_guild=True)
    async def update_recent_opponents_limit(self, ctx: discord.ApplicationContext,
                                                  limit: discord.Option(int)):
        self.recent_opponents_limit = limit
        for player in self.in_queue.keys():
            new_deque = deque(list(self.in_queue[player][1]), maxlen=limit)
            self.in_queue[player][1] = new_deque

        await ctx.respond(f"recent_opponents_limit updated to {limit}!")
        return

    ### GLICKO-2 ALGORITHM IMPLEMENTATION WITH FRACTIONAL RATINGS

    # Step 2 of the Glicko 2 algorithm
    def convert_to_glicko_scale(self, rating: float, rd: float):
        new_rating = (rating - self.default_rating) / 173.7178
        new_rd = rd / 173.7178

        return new_rating, new_rd

    # Step 8, but also here for organization
    def convert_from_glicko_scale(self, glicko_rating: float, glicko_rd: float):
        new_rating = (173.7178 * glicko_rating) + self.default_rating
        new_rd = 173.7178 * glicko_rd

        return new_rating, new_rd

    # Step 3
    def glicko_v(self, mu: float, opponent_mus: list[float], opponent_phis: list[float]):
        ret_frac = 0
        for i in range(len(opponent_mus)):
            E_res = self.glicko_E(mu, opponent_mus[i], opponent_phis[i])
            g_res = self.glicko_g(opponent_phis[i])
            ret_frac += math.pow(g_res, 2) * E_res * (1 - E_res)

        return 1 / ret_frac

    def glicko_g(self, phi: float):
        return 1 / math.sqrt(1 + 3 * math.pow(phi, 2) / math.pow(math.pi, 2))

    def glicko_E(self, mu: float, opponent_mu: float, opponent_phi: float):
        return 1 / (1 + math.exp(-1 * self.glicko_g(opponent_phi) * (mu - opponent_mu)))

    # Step 4
    def glicko_delta(self, v: float, mu: float, opponent_mus: list[float], opponent_phis: list[float], game_outcomes: list[float]):
        ret = 0
        for i in range(len(opponent_mus)):
            E_res = self.glicko_E(mu, opponent_mus[i], opponent_phis[i])
            g_res = self.glicko_g(opponent_phis[i])
            ret += g_res * (game_outcomes[i] - E_res)
        
        return ret * v

    # Step 5, returns sigma prime value
    def glicko_new_volatility(self, phi: float, sigma: float, delta: float, v: float):
        convergence_epsilon = 0.000001
        a = math.log(math.pow(sigma, 2))
        big_a = a
        # print(f"delta^2 is {math.pow(delta, 2)}, phi^2 is {math.pow(phi, 2)}, v is {v}, phi^2-v is {math.pow(phi, 2) - v}, total is {math.pow(delta, 2) - math.pow(phi, 2) - v}, bool is {math.pow(delta, 2) > math.pow(phi, 2) - v}")
        if math.pow(delta, 2) > math.pow(phi, 2) + v:
            big_b = math.log(math.pow(delta, 2) - math.pow(phi, 2) - v)
        elif math.pow(delta, 2) <= math.pow(phi, 2) + v:
            k = 1
            k_func_res = self.glicko_volatility_f_helper(a - (k * self.tau), a, phi, delta, v)
            while k_func_res < 0:
                k += 1
                k_func_res = self.glicko_volatility_f_helper(a - (k * self.tau), a, phi, delta, v)
            big_b = a - (k * self.tau)
        
        big_a_func_res = self.glicko_volatility_f_helper(big_a, a, phi, delta, v)
        big_b_func_res = self.glicko_volatility_f_helper(big_b, a, phi, delta, v)
        while abs(big_a - big_b) > convergence_epsilon:
            big_c = big_a + ((big_a - big_b) * big_a_func_res) / (big_b_func_res - big_a_func_res)
            big_c_func_res = self.glicko_volatility_f_helper(big_c, a, phi, delta, v)
            if big_c_func_res * big_b_func_res <= 0:
                big_a = big_b
                big_a_func_res = big_b_func_res
            else:
                big_a_func_res /= 2
            big_b = big_c
            big_b_func_res = big_c_func_res

        return math.pow(math.e, (big_a / 2))

    def glicko_volatility_f_helper(self, x: float, a: float, phi: float, delta: float, v: float):
        return ((math.pow(math.e, x) * (math.pow(delta, 2) - math.pow(phi, 2) - v - math.pow(math.e, x))) / (2 * math.pow((math.pow(phi, 2) + v + math.pow(math.e, x)), 2))) - ((x - a) / math.pow(self.tau, 2))

    # Step 6, with fractional rating implementation from Lichess
    # also, this is the only function that is applied when a player has no played games in a given rating period
    def glicko_new_rd_star(self, phi: float, sigma_prime: float, elapsed_rating_periods: float):
        return math.sqrt(math.pow(phi, 2) + elapsed_rating_periods * math.pow(sigma_prime, 2))

    # Step 7, returns phi_prime, mu_prime
    def glicko_new_rating_and_rd(self, phi_star: float, v: float, mu: float, opponent_mus: list[float], opponent_phis: list[float], game_outcomes: list[float]):
        phi_prime = 1 / math.sqrt((1/math.pow(phi_star, 2)) + (1 / v))
        mu_sum = 0
        for i in range(len(opponent_mus)):
            E_res = self.glicko_E(mu, opponent_mus[i], opponent_phis[i])
            g_res = self.glicko_g(opponent_phis[i])
            mu_sum += g_res * (game_outcomes[i] - E_res)
        mu_prime = mu + math.pow(phi_prime, 2) * mu_sum
        return phi_prime, mu_prime

    # Wrapper for the entire glicko-2 calculation
    # game outcomes must be either 0, 1, or 0.5 for loss, win and tie respectively
    # returns rating, rd, volatility
    def glicko_update_rating(self, player_rating: float, player_rd: float, player_volatility: float, opponent_ratings: list[float], opponent_rds: list[float], game_outcomes: list[float], elapsed_rating_periods: float):
        player_mu, player_phi = self.convert_to_glicko_scale(player_rating, player_rd)
        player_sigma = player_volatility
        opponent_mus = [(rating - self.default_rating) / 173.7178 for rating in opponent_ratings]
        opponent_phis = [rating / 173.7178 for rating in opponent_rds]
        player_v = self.glicko_v(player_mu, opponent_mus, opponent_phis)
        player_delta = self.glicko_delta(player_v, player_mu, opponent_mus, opponent_phis, game_outcomes)
        player_sigma_prime = self.glicko_new_volatility(player_phi, player_sigma, player_delta, player_v)
        player_phi_star = self.glicko_new_rd_star(player_phi, player_sigma_prime, elapsed_rating_periods)
        player_phi_prime, player_mu_prime = self.glicko_new_rating_and_rd(player_phi_star, player_v, player_mu, opponent_mus, opponent_phis, game_outcomes)
        player_new_rating, player_new_rd = self.convert_from_glicko_scale(player_mu_prime, player_phi_prime)
        
        return player_new_rating, player_new_rd, player_sigma_prime

    def glicko_update_rating_no_games(self, player_rating: float, player_rd: float, player_volatility: float, elapsed_rating_periods: float):
        player_mu, player_phi = self.convert_to_glicko_scale(player_rating, player_rd)
        player_sigma = player_volatility
        player_phi_star = self.glicko_new_rd_star(player_phi, player_sigma, elapsed_rating_periods)
        player_new_rating, player_new_rd = self.convert_from_glicko_scale(player_mu, player_phi_star)

        return player_new_rd

    # Closes the current rating period, 
    def glicko_close_rating_period(self, new_timestamp: int):
        players_res = self.database_cur.execute(
            "SELECT discord_id, character, glicko_rating, glicko_rd, glicko_volatility, last_rating_timestamp FROM players"
        ).fetchall()

        for player in players_res:
            player_elapsed_rating_period = (new_timestamp - int(player['last_rating_timestamp'])) / 86400
            player_new_rd = self.glicko_update_rating_no_games(player['glicko_rating'], player['glicko_rd'], player['glicko_volatility'], player_elapsed_rating_period)
            self.database_cur.execute("UPDATE players SET glicko_rd = ?, last_rating_timestamp = ? WHERE discord_id=? and character=?", (player_new_rd, new_timestamp, player['discord_id'], player['character']))

        self.database_con.commit()



    # 0 ~ 1099 -> Rookie (新人/Shinjin)
    # 1100 ~ 1249 -> Advanced (先進/Senshin) 
    # 1250 ~ 1399 -> Expert (玄人/Kurouto) 
    # 1400 ~ 1599 -> Ultimate (究極/Kyuukyoku)
    # 1600+ -> Unrivaled (無敵/Muteki) 
    def get_role_name_by_rating(self, rating: float):
        if rating <= 1099: 
            return "新人"
        elif rating <= 1249:
            return "先進"
        elif rating <= 1399:
            return "玄人"
        elif rating <= 1599:
            return "究極"
        elif rating >= 1600:
            return "無敵"

    # Starts a new glicko-2 rating period if there is not one already started. If one has ended, it will apply the RD increase to every player
    def setup_rating_period(self):
        res = self.database_cur.execute("SELECT timestamp FROM rating_period").fetchone()
        if not res:
            self.logger.debug(f"No previous rating period found, starting a new one")
            self.database_cur.execute(
                "INSERT INTO rating_period (timestamp) VALUES (?)", 
                (int(time()),)
            )
        else:
            time_since_last_period = int(res['timestamp'])
            self.logger.debug(f"Previous rating period found (started {(time_since_last_period / 86400):.1f} days ago), attempting to update")
            period_length = self.rating_period_length * 86400
            periods_since_last_update = (int(time()) - time_since_last_period) / period_length
            if periods_since_last_update >= 1:
                new_timestamp = int(time())
                self.glicko_close_rating_period(new_timestamp)
                self.database_cur.execute("UPDATE rating_period SET timestamp = ?", (new_timestamp,))

        if self.rating_period_coro is None:
            res = self.database_cur.execute("SELECT timestamp FROM rating_period").fetchone()
            delay = self.rating_period_length * 86400
            if res:
                delay -= (int(time()) - int(res['timestamp']))

            self.rating_period_coro = asyncio.create_task(self.rating_period_timer(delay))
            self.logger.debug(f"Matchmaking timer started with {delay} seconds")


    async def rating_period_timer(self, delay):
        await asyncio.sleep(delay)
        self.logger.info(f"Closing current rating period and updating")
        new_timestamp = int(time())
        self.glicko_close_rating_period(new_timestamp)
        self.database_cur.execute("UPDATE rating_period SET timestamp = ?", (new_timestamp,))

        while True:
            await asyncio.sleep(self.rating_period_length * 86400)
            self.logger.info(f"Closing current rating period and updating")
            new_timestamp = int(time())
            self.glicko_close_rating_period(new_timestamp)
            self.database_cur.execute("UPDATE rating_period SET timestamp = ?", (new_timestamp,))

    @discord.commands.slash_command(name="viewratingperiod", description="[Admin Command] View the start date of the current rating period, mainly debug")
    @discord.commands.default_permissions(manage_guild=True)
    async def view_rating_period(self, ctx: discord.ApplicationContext):
        res = self.database_cur.execute(f"SELECT timestamp FROM rating_period").fetchone()
        if not res:
            await ctx.respond(f"No rating period has started (this is probably an error, lmao)")
            return
        else:
            await ctx.respond(f"The last rating period was started on <t:{res['timestamp']}:D>.")
            return

    # @discord.commands.slash_command(name="updateratingperiod", description="[Admin Command] Set the start date of the current rating period, mainly debug. Uses Unix time.")
    # @discord.commands.default_permissions(manage_guild=True)
    # async def update_rating_period(self, ctx: discord.ApplicationContext, new_timestamp: discord.Option(int, required=True)):
    #     self.database_cur.execute("UPDATE rating_period SET timestamp = ?", (new_timestamp,))
    #     self.database_con.commit()
    #     await ctx.respond(f"Rating period start time updated to <t:{new_timestamp}:D>.")

    
    # @discord.commands.slash_command(name="endratingperiod", description="[Admin Command] Forcefully end the current rating period")
    # @discord.commands.default_permissions(manage_guild=True)
    # async def end_rating_period(self, ctx: discord.ApplicationContext):
    #     new_timestamp = int(time())
    #     self.glicko_close_rating_period(new_timestamp)
    #     self.database_cur.execute("UPDATE rating_period SET timestamp = ?", (new_timestamp,))
    #     self.database_con.commit()
    #     await ctx.respond(f"Rating period start time updated to <t:{new_timestamp}:D>.")


    # @discord.commands.slash_command(name="setplayerlastplayedtime", description="[Admin Command] Debug function, sets the last time a player played")
    # @discord.commands.default_permissions(manage_guild=True)
    # async def set_player_last_played_time(self, ctx: discord.ApplicationContext, discord_id: discord.Option(str), new_timestamp: discord.Option(int)):
    #     self.database_cur.execute("UPDATE players SET last_rating_timestamp = ? where discord_id = ?", (new_timestamp, discord_id))
    #     self.database_con.commit()
    #     await ctx.respond(f"Rating period start time updated to <t:{new_timestamp}:D>.")
    






    
