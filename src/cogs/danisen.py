import discord, sqlite3, asyncio, json, logging, re
from discord.ext import commands, pages
from cogs.database import *
from cogs.custom_views import *
import os
from collections import deque
from constants import *
from random import choice
from datetime import datetime

class Danisen(commands.Cog):
    # Predefined characters and players
    characters = ["Gran", "Djeeta", "Katalina", "Charlotta", "Lancelot", "Percival", "Ladiva", "Metera", "Lowain", "Ferry", "Zeta", "Vaseraga", "Narmaya", "Soriz", "Zooey", "Cagliostro", "Yuel", "Anre", "Eustace", "Seox", "Vira", "Beelzebub", "Belial", "Avatar Belial", "Anila", "Siegfried", "Grimnir", "Nier", "Lucilius", "2B", "Vane", "Beatrix", "Versusia", "Vikala", "Sandalphon", "Galleon", "Wilnas", "Meg", "Lunalu"]
    players = ["player1", "player2"] # These are the presets for specifying which player won in /reportmatch, NOT danisen player names
    dan_colours = [
        discord.Colour.from_rgb(237, 237, 237), discord.Colour.from_rgb(176, 105, 48), discord.Colour.from_rgb(150, 150, 150),
        discord.Colour.from_rgb(227, 197, 45), discord.Colour.from_rgb(23, 209, 66), discord.Colour.from_rgb(105, 215, 240), discord.Colour.from_rgb(178, 75, 219),
        discord.Colour.from_rgb(252, 166, 220), discord.Colour.from_rgb(17, 20, 172), discord.Colour.from_rgb(240, 64, 48),
    ] 
    emoji_mapping = {"Gran": "<:Gran:1438571506681647235>", "Djeeta": "<:Djeeta:1438571497429012662>", "Katalina": "<:Katalina:1438571940683059331>", "Charlotta": "<:Charlotta:1438571495444975678>", "Lancelot": "<:Lancelot:1438571515275645149>", "Percival": "<:Percival:1438571533768327280>", "Ladiva": "<:Ladiva:1438571512142499930>", "Metera": "<:Metera:1438571526126567554>", "Lowain": "<:Lowain:1438571942989791313>", "Ferry": "<:Ferry:1438571501594083439>", "Zeta": "<:Zeta:1438571475958501406>", "Vaseraga": "<:Vaseraga:1438571464038154280>", "Narmaya": "<:Narmaya:1438571944579694765>", "Soriz": "<:Soriz:1438571459533340764>", "Zooey": "<:Zooey:1438571477971763262>", "Cagliostro": "<:Cagliostro:1438571948996038768>", "Yuel": "<:Yuel:1438571474104352860>", "Anre": "<:Anre:1438571481586995301>", "Eustace": "<:Eustace:1438571950828949666>", "Seox": "<:Seox:1438571538919198790>", "Vira": "<:Vira:1438571469792612393>", "Beelzebub": "<:Beelzebub:1438571488679825438>", "Belial": "<:Belial:1438571491858845767>", "Avatar Belial": "<:AvatarBelial:1438910182825525368>", "Anila": "<:Anila:1438571479741632522>", "Siegfried": "<:Siegfried:1438571541833973831>", "Grimnir": "<:Grimnir:1438571508195790959>", "Nier": "<:Nier:1438571530157293710>", "Lucilius": "<:Lucilius:1438571519419748528>", "2B": "<:2B:1438571398682513529>", "Vane": "<:Vane:1438571462351917197>", "Beatrix": "<:Beatrix:1438571485588357140>", "Versusia": "<:Versusia:1438571466051555378>", "Vikala": "<:Vikala:1438571468060622909>", "Sandalphon": "<:Sandalphon:1438571947628822538>", "Galleon": "<:Galleon:1438571953245126676>", "Wilnas": "<:Wilnas:1438571471671787520>", "Meg": "<:Meg:1438571524180414516>", "Lunalu": "<:Lunalu:1439718838034759740>"}

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
                                                                    f"dan INT NOT NULL,"
                                                                    f"points FLOAT NOT NULL,"
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

        # Queue and matchmaking setup
        self.dans_in_queue = {dan: deque() for dan in range(1, self.total_dans + 1)}
        self.matchmaking_queue = deque()
        # self.max_active_matches = 3 # Disabled because of loading this from config below, if this is instantiated it overwrites it for some reason
        
        self.cur_active_matches = 0
        # self.recent_opponents_limit = 2
        self.in_queue = {}  # Format: discord_id@character: [in_queue, deque of last played discord_ids]
        self.in_match = {}  # Format: discord_id: in_match
        self.matchmaking_coro = None  # Task created with asyncio to run start_matchmaking after a set delay

        # Synchronization
        self.queue_lock = asyncio.Lock()

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
        self.ACTIVE_MATCHES_CHANNEL_ID = int(config.get('ACTIVE_MATCHES_CHANNEL_ID', 0))
        self.REPORTED_MATCHES_CHANNEL_ID = int(config.get('REPORTED_MATCHES_CHANNEL_ID', 0))
        self.ONGOING_MATCHES_CHANNEL_ID = int(config.get('ONGOING_MATCHES_CHANNEL_ID', 0))
        self.total_dans = config.get('total_dans', MAX_DAN_RANK)
        self.minimum_derank = config.get('minimum_derank', DEFAULT_DAN)
        self.rank_gap_for_more_points_1 = config.get('rank_gap_for_more_points_1', 2)
        self.rank_gap_for_more_points_2 = config.get("rank_gap_for_more_points_2", 4)
        self.point_rollover = config.get('point_rollover', True)
        self.queue_status = config.get('queue_status', True)
        self.recent_opponents_limit = config.get('recent_opponents_limit', 3)
        self.max_active_matches = config.get('max_active_matches', 7)  # New parameter
        self.special_rank_up_rules = config.get('special_rank_up_rules', False)

    @discord.commands.slash_command(name="setqueue", description="[Admin Command] Open or close the matchmaking queue.")
    @discord.commands.default_permissions(manage_roles=True)
    async def set_queue(self, ctx: discord.ApplicationContext, queue_status: discord.Option(bool, name="enablequeue")):
        # Enable or disable the matchmaking queue
        self.queue_status = queue_status
        if not queue_status:
            self.matchmaking_queue.clear()  # Clear the deque
            self.dans_in_queue = {dan: deque() for dan in range(1, self.total_dans + 1)}  # Reset to empty deques
            self.in_queue = {}
            self.in_match = {}
            await ctx.respond("The matchmaking queue has been disabled.")
        else:
            await ctx.respond("The matchmaking queue has been enabled.")

    def dead_role(self, ctx, player):
        # Check if a player's dan role should be removed
        role = None
        self.logger.info(f'Checking if dan should be removed as well')
        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={player['discord_id']} AND dan={player['dan']}")
        remaining_daniel = res.fetchone()
        if not remaining_daniel:
            self.logger.info(f"Dan role {player['dan']} will be removed")
            role = discord.utils.get(ctx.guild.roles, name=f"Dan {player['dan']}")
        return role


    async def score_update(self, ctx, winner, loser):
        # Update scores for a match
        # Format of [Dan, Points, Rankup?, PointDelta]
        winner_rank = [winner['dan'], winner['points'], False, 0.0]
        loser_rank = [loser['dan'], loser['points'], False, 0,0]
        rankdown = False
        rankup = False

        # Determine rankup points based on rank type
        rankup_points = RANKUP_POINTS_NORMAL # RANKUP_POINTS_SPECIAL if winner_rank[0] >= SPECIAL_RANK_THRESHOLD else RANKUP_POINTS_NORMAL

        # Winning and Losing logic
        if loser_rank[0] >= winner_rank[0] + self.rank_gap_for_more_points_2: # lower ranked player wins with 4 rank gap
            winner_rank[1] += 2.0
            winner_rank[3] += 2.0
            loser_rank[1] -= 1.0
            loser_rank[3] -= 1.0
        elif loser_rank[0] >= winner_rank[0] + self.rank_gap_for_more_points_1: # lower ranked player wins with 2 rank gap
            winner_rank[1] += 1.5
            winner_rank[3] += 1.5
            loser_rank[1] -= 1.0
            loser_rank[3] -= 1.0
        elif winner_rank[0] >= loser_rank[0] + self.rank_gap_for_more_points_2: # higher ranked player wins with 4 rank gap
            winner_rank[1] += 0.1
            winner_rank[3] += 0.1
            loser_rank[1] -= 0.1
            loser_rank[3] -= 0.1
        elif winner_rank[0] >= loser_rank[0] + self.rank_gap_for_more_points_1: # higher ranked player wins with 2 rank gap
            winner_rank[1] += 0.5
            winner_rank[3] += 0.5
            loser_rank[1] -= 0.5
            loser_rank[3] -= 0.5
        else:
            winner_rank[1] += 1.0
            winner_rank[3] += 1.0
            loser_rank[1] -= 1.0
            loser_rank[3] -= 1.0

        if loser_rank[0] == self.minimum_derank and loser_rank[1] < 0: # making sure loser can't go lower than minimum rank
            loser_rank[1] = 0.0
            loser_rank[3] = 0.0
        

        # Rankup logic with special rules
        if winner_rank[1] >= rankup_points:
            can_rankup = True
            
            # Check special rank rules
            if self.special_rank_up_rules and winner_rank[0] >= SPECIAL_RANK_THRESHOLD:
                # Can only rank up by beating another high-ranked player
                can_rankup = loser_rank[0] >= SPECIAL_RANK_THRESHOLD
                if not can_rankup:
                    # Reset points to rankup_points - 1 if can't rank up
                    winner_rank[1] = rankup_points - 1
            
            if can_rankup:
                winner_rank[0] += 1
                winner_rank[2] = True
                winner_rank[1] = winner_rank[1] % rankup_points if self.point_rollover else 0.0
                rankup = True

        # Rankdown logic
        if loser_rank[1] <= RANKDOWN_POINTS:
            loser_rank[0] -= 1
            loser_rank[1] = DEFAULT_POINTS
            loser_rank[2] = True
            rankdown = True

        # Log new scores
        self.logger.info("New Scores")
        self.logger.info(f"Winner : {winner['player_name']} dan {winner_rank[0]}, points {winner_rank[1]}")
        self.logger.info(f"Loser : {loser['player_name']} dan {loser_rank[0]}, points {loser_rank[1]}")

        # Update database
        self.database_cur.execute(f"UPDATE players SET dan = {winner_rank[0]}, points = {winner_rank[1]} WHERE discord_id='{winner['discord_id']}' AND character='{winner['character']}'")
        self.database_cur.execute(f"UPDATE players SET dan = {loser_rank[0]}, points = {loser_rank[1]} WHERE discord_id='{loser['discord_id']}' AND character='{loser['character']}'")
        self.database_con.commit()

        # Update roles on rankup/down
        if rankup:
            self.logger.debug(f"Winning player ranked up, attempting to assign roles")
            dan = self.get_players_highest_dan(winner['player_name'])
            self.logger.debug(f"Winning player's highest character dan is {dan}, rankup dan is {winner_rank[0]}")
            if dan and dan == winner_rank[0]: # it's their highest ranked character that just ranked up, since the table is updated first we check for equality
                role = discord.utils.get(ctx.guild.roles, name=f"Dan {winner_rank[0]}")
                member = ctx.guild.get_member(winner['discord_id'])
                bot_member = ctx.guild.get_member(self.bot.user.id)
                if role and self.can_manage_role(bot_member, role):
                    await member.add_roles(role)
                role = discord.utils.get(ctx.guild.roles, name=f"Dan {winner_rank[0] - 1}") # this could cause issues, but should be fine as long as you can't rank up twice in one game (which cant happen)
                if role and self.can_manage_role(bot_member, role):
                    await member.remove_roles(role)

        if rankdown:
            self.logger.debug(f"Losing player ranked down, attempting to assign roles")
            dan = self.get_players_highest_dan(loser['player_name'])
            self.logger.debug(f"Winning player's highest character dan is {dan}, rankdown dan is {loser_rank[0]}")
            if dan and dan == loser_rank[0]: # same as above, hopefully
                role = discord.utils.get(ctx.guild.roles, name=f"Dan {loser_rank[0]}")
                member = ctx.guild.get_member(loser['discord_id'])
                bot_member = ctx.guild.get_member(self.bot.user.id)
                if role and self.can_manage_role(bot_member, role):
                    await member.add_roles(role)
                role = discord.utils.get(ctx.guild.roles, name=f"Dan {loser_rank[0] + 1}") # this could cause issues, but should be fine as long as you can't rank up twice in one game (which cant happen)
                if role and self.can_manage_role(bot_member, role):
                    await member.remove_roles(role)

        return winner_rank, loser_rank

    # Custom decorator for validation
    def is_valid_char(self, char):
        return char in self.characters

    async def character_autocomplete(self, ctx: discord.AutocompleteContext):
        return [character for character in self.characters if character.lower().startswith(ctx.value.lower())]

    async def player_autocomplete(self, ctx: discord.AutocompleteContext):
        res = self.database_cur.execute(f"SELECT player_name FROM users")
        name_list=res.fetchall()
        names = set([name[0] for name in name_list])
        return [name for name in names if (name.lower()).startswith(ctx.value.lower())]

    @discord.commands.slash_command(name="setrank", description="[Admin Command] Set a player's dan rank and points.")
    @discord.commands.default_permissions(manage_roles=True)
    async def set_rank(self, ctx : discord.ApplicationContext,
                        player_name :  discord.Option(str, autocomplete=player_autocomplete),
                        char : discord.Option(str, name="character", autocomplete=character_autocomplete),
                        dan :  discord.Option(int),
                        points : discord.Option(float)):
        if not self.is_valid_char(char):
            await ctx.respond(f"Invalid char selected {char}. Please choose a valid char.")
            return

        # sync role stuff
        role_removed = False
        discord_id = None
        res = self.database_cur.execute(f"SELECT dan, users.discord_id AS discord_id FROM users JOIN players ON players.discord_id = users.discord_id WHERE player_name='{player_name}' AND character='{char}'").fetchone()
        if res: 
            discord_id = res['discord_id']
            if res['dan'] == self.get_players_highest_dan(player_name) or dan > self.get_players_highest_dan(player_name): # if this is the player's highest ranked character being updated, we need to remove the corresponding dan role
                role = discord.utils.get(ctx.guild.roles, name=f"Dan {self.get_players_highest_dan(player_name)}")
                member = ctx.guild.get_member(res['discord_id'])
                bot_member = ctx.guild.get_member(self.bot.user.id)
                if role and self.can_manage_role(bot_member, role):
                    await member.remove_roles(role)
                    role_removed = True
        else:
            await ctx.respond(f"Database entry for player {player} on character {char} not found.")
        
        self.database_cur.execute(f"UPDATE players SET dan = {dan}, points = {points} WHERE discord_id='{discord_id}' AND character='{char}'")
        self.database_con.commit()

        if role_removed and self.get_players_highest_dan(player_name) is not None:
            role = discord.utils.get(ctx.guild.roles, name=f"Dan {self.get_players_highest_dan(player_name)}")
            member = ctx.guild.get_member(res['discord_id'])
            bot_member = ctx.guild.get_member(self.bot.user.id)
            if role and self.can_manage_role(bot_member, role):
                await member.add_roles(role)

        await ctx.respond(f"{player_name}'s {char} rank updated to be Dan {dan}, {round(points, 1):.1f} points.")

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
        player_nickname = ctx.author.global_name if ctx.author.global_name else ctx.author.name

        player_nickname = re.subn(r"(?P<char>[\*\-\_\~])", r"\\\g<char>", player_nickname)[0]
        self.logger.debug(f"player nickname post regex is {player_nickname}")

        self.logger.info(f"player nickname is {ctx.author.nick}, player global name is {ctx.author.global_name}")

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
        line = (ctx.author.id, char1, DEFAULT_DAN, DEFAULT_POINTS)
        self.database_cur.execute(
            "INSERT INTO players (discord_id, character, dan, points) VALUES (?, ?, ?, ?)", 
            line
        )
        self.database_con.commit()

        # Get Discord roles to add to participant
        role_list = []
        char_role = discord.utils.get(ctx.guild.roles, name=char1)
        if char_role:
            role_list.append(char_role)
        self.logger.info(f"Adding to db {player_name} {char1}")

        highest_dan = self.get_players_highest_dan(player_name)
        self.logger.info(f"Registering player's highest dan is {highest_dan}")
        if not highest_dan or highest_dan == 1:
            dan_role = discord.utils.get(ctx.guild.roles, name="Dan 1")
            if dan_role:
                role_list.append(dan_role)

        participant_role = discord.utils.get(ctx.guild.roles, name="Danisen Participant")
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
                f"You have registered {regged_chars+1}/3 characters to the Danisen. Have fun!"
            )
        else:
            await ctx.respond(
                f"You are now registered as {player_name}{" " + player_nickname if player_nickname else ""} with {char1}!\n"
                "If you wish to add more characters, you can register with up to 3 different characters!\n\n"
                "Welcome to the Danisen!"
            )

    @discord.commands.slash_command(description="Unregister a character from the Danisen database. Note this will reset dan and points.")
    async def unregister(self, ctx : discord.ApplicationContext, 
                    char1 : discord.Option(str, name="character", autocomplete=character_autocomplete)):

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

        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={ctx.author.id} AND character='{char1}'")
        daniel = res.fetchone()

        if daniel == None:
            await ctx.respond("You are not registered with that character")
            return

        self.logger.info(f"Removing {ctx.author.name} {ctx.author.id} {char1} from db")
        self.database_cur.execute(f"DELETE FROM players WHERE discord_id={ctx.author.id} AND character='{char1}'")
        self.database_con.commit()

        # Get roles to remove from participant, if they have them.
        role_list = []
        char_role = discord.utils.get(ctx.guild.roles, name=char1)
        if char_role:
            role_list.append(discord.utils.get(ctx.guild.roles, name=char1))
        self.logger.info(f"Removing role {char1} from member")

        role = self.dead_role(ctx, daniel)
        if role:
            role_list.append(role)

        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id=?", (ctx.author.id,)).fetchone()
        if res is None:
            participant_role = discord.utils.get(ctx.guild.roles, name="Danisen Participant")
            if char_role:
                role_list.append(discord.utils.get(ctx.guild.roles, name="Danisen Participant"))
 
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
        
        if self.get_players_highest_dan(ctx.author.name):
            role = discord.utils.get(ctx.guild.roles, name=f"Dan {self.get_players_highest_dan(ctx.author.name)}")
            member = ctx.author
            bot_member = ctx.guild.get_member(self.bot.user.id)
            if role and self.can_manage_role(bot_member, role):
                await member.add_roles(role)

        message_text += f"You have now unregistered {char1}"
        await ctx.respond(message_text)

    #rank command to get discord_name's player rank, (can also ignore 2nd param for own rank)
    @discord.commands.slash_command(description="Get your character rank/Put in a players name to get their character rank!")
    async def rank(self, ctx : discord.ApplicationContext,
                char : discord.Option(str, name="character", autocomplete=character_autocomplete),
                discord_name :  discord.Option(str, required=False, autocomplete=player_autocomplete)):
        if not self.is_valid_char(char):
            await ctx.respond(f"Invalid char selected {char}. Please choose a valid char.")
            return
    
        if not discord_name:
            discord_name = ctx.author.name

        members = ctx.guild.members
        member = None
        for m in members:
            if discord_name.lower() == m.name.lower():
                member = m
                break
        if discord_name:
            if not member:
                await ctx.respond(f"""{discord_name} isn't a member of this server""")
                return
        else:
            member = ctx.author
        id = member.id

        res = self.database_cur.execute(f"SELECT dan, points, nickname FROM players JOIN users ON players.discord_id = users.discord_id WHERE users.discord_id={id} AND character='{char}'")
        data = res.fetchone()
        if data:
            await ctx.respond(f"""{data['player_name']}'s rank for {char} is Dan {data['dan']}, {round(data['points'], 1):.1f} points""")
        else:
            await ctx.respond(f"""{member.name} is not registered as {char}.""")

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
                    if daniel in self.dans_in_queue[daniel['dan']]:
                        self.dans_in_queue[daniel['dan']].remove(daniel)
                        self.matchmaking_queue.remove(daniel)

                    self.in_queue[str(daniel['discord_id'])+"@"+daniel['character']][0] = False
                await ctx.respond(f"You have been removed from the queue as {char}.")
            elif daniels != []:
                for daniel in daniels:
                    if daniel in self.dans_in_queue[daniel['dan']]:
                        self.dans_in_queue[daniel['dan']].remove(daniel)
                        self.matchmaking_queue.remove(daniel)

                    self.in_queue[str(daniel['discord_id'])+"@"+daniel['character']][0] = False
                await ctx.respond("You have been removed from the queue on all characters.")
            else:
                await ctx.respond("You are not in queue.")

    #joins the matchmaking queue
    @discord.commands.slash_command(name="joinqueue", description="queue up for danisen games")
    async def join_queue(self, ctx : discord.ApplicationContext,
                    char: discord.Option(str, autocomplete=character_autocomplete)):
        await ctx.defer()
        discord_id = ctx.author.id
        rejoin_queue = False

        if not self.is_valid_char(char):
            await ctx.respond(f"Invalid char selected {char}. Please choose a valid char.")
            return

        #check if q open
        if self.queue_status == False:
            await ctx.respond(f"The matchmaking queue is currently closed")
            return

        #Check if valid character
        res = self.database_cur.execute(f"SELECT users.discord_id AS discord_id, player_name, nickname, keyword, character, dan, points FROM players JOIN users ON players.discord_id = users.discord_id WHERE users.discord_id={discord_id} AND character='{char}'")
        daniel = res.fetchone()
        if daniel == None:
            await ctx.respond(f"You are not registered with that character")
            return


        # Update player nickname, could be refactored to another function but idk where else to put it
        player_nickname = ctx.author.global_name if ctx.author.global_name else ctx.author.name
        player_nickname = re.subn(r"(?P<char>[\*\-\_\~])", r"\\\g<char>", player_nickname)[0]
        self.logger.debug(f"player nickname post regex is {player_nickname}")
        if player_nickname != daniel['nickname']:
            self.database_cur.execute(f"UPDATE users SET nickname = '{player_nickname}' WHERE discord_id='{ctx.author.id}'")

        daniel = DanisenRow(daniel)
        daniel['requeue'] = rejoin_queue
        daniel['nickname'] = player_nickname

        self.logger.debug(f"join_queue for player {daniel['player_name']} awaiting lock")
        queue_add_success = False
        async with self.queue_lock:
            self.logger.debug(f"join_queue for player {daniel['player_name']} acquired lock")
            #Check if in Queue already
            self.logger.debug(f"checking that {str(discord_id)+"@"+char} is in {self.in_queue}: {str(discord_id)+"@"+char in self.in_queue} and {(str(discord_id)+"@"+char in self.in_queue) and self.in_queue[str(discord_id)+"@"+char][0]}")
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

            self.dans_in_queue[daniel['dan']].append(daniel)
            self.matchmaking_queue.append(daniel)
            queue_add_success = True
        
        if queue_add_success:
            await ctx.respond(f"You've been added to the matchmaking queue with {char}")
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

        res = self.database_cur.execute(f"SELECT users.discord_id AS discord_id, player_name, nickname, keyword, character, dan, points FROM players JOIN users ON players.discord_id = users.discord_id WHERE users.discord_id={player['discord_id']} AND character='{player['character']}'")
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
            self.dans_in_queue[player['dan']].append(player)  # Append the transformed player
            self.matchmaking_queue.append(player)

        await self.begin_matchmaking_timer(interaction, 30) # Attempt to restart the timer, if it's stopped

    @discord.commands.slash_command(name="viewqueue", description="view players in the queue")
    async def view_queue(self, ctx : discord.ApplicationContext):
        em = discord.Embed(
            title="Current Danisen Queue",
            color=discord.Color.blurple())

        self.logger.debug(f"current queue is {self.matchmaking_queue}")
        for player in self.matchmaking_queue:
            if player:
                em.add_field(name=f"{player['nickname']} ({player['character']})", 
                        value=f"Dan {player['dan']}, {round(player['points'], 1):.1f} points", 
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
            self.logger.debug(f"Current dans_in_queue: { {dan: list(queue) for dan, queue in self.dans_in_queue.items()} }")

            daniel1 = self.matchmaking_queue.popleft()  # Pop from the left of the deque
            self.logger.debug(f"Dequeued daniel1 from matchmaking_queue: {daniel1}")

            if not daniel1:
                self.logger.warning("Dequeued daniel1 is None. Skipping iteration.")
                continue

            self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][0] = False

            same_daniel = self.dans_in_queue[daniel1['dan']].popleft()  # Pop from the left of the deque
            self.logger.debug(f"Dequeued same_daniel from dans_in_queue[{daniel1['dan']}]: {same_daniel}")

            # Sanity check that this is also the latest daniel in the respective dan queue
            if daniel1 != same_daniel:
                self.logger.error(f"Queue desynchronization detected: daniel1={daniel1} same_daniel={same_daniel}")
                self.logger.debug(f"Remaining matchmaking_queue: {list(self.matchmaking_queue)}")
                self.logger.debug(f"Remaining dans_in_queue[{daniel1['dan']}]: {list(self.dans_in_queue[daniel1['dan']])}")
                return

            check_dan = [daniel1['dan']]
            for dan_offset in range(1, self.total_dans):
                cur_dan = check_dan[0] + dan_offset
                if DEFAULT_DAN <= cur_dan <= self.total_dans:
                    check_dan.append(cur_dan)
                cur_dan = check_dan[0] - dan_offset
                if DEFAULT_DAN <= cur_dan <= self.total_dans:
                    check_dan.append(cur_dan)

            old_daniels = []  # List to track multiple old_daniel instances
            matchmade = False
            for dan in check_dan:
                self.logger.debug(f"Checking dan queue for dan {dan}: {list(self.dans_in_queue[dan])}")
                while self.dans_in_queue[dan]:  # Continue checking the same dan queue
                    daniel2 = self.dans_in_queue[dan].popleft()
                    self.logger.debug(f"Dequeued daniel2 from dans_in_queue[{dan}]: {daniel2}")

                    self.logger.debug(f"player identifier: {str(daniel2['discord_id'])+"@"+daniel2['character']}, daniel1 recent: {self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][1]}")
                    if str(daniel2['discord_id'])+"@"+daniel2['character'] in self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][1]:
                        self.logger.debug(f"Skipping daniel2 {daniel2} as they are in daniel1's recent opponents.")
                        old_daniels.append(daniel2)
                        continue
                    
                    if daniel2['discord_id'] == daniel1['discord_id']:
                        self.logger.debug(f"Skipping daniel2 {daniel2} as they are the same user on different characters.")
                        old_daniels.append(daniel2)
                        continue

                    if daniel2['discord_id'] in self.in_match and self.in_match[daniel2['discord_id']]:
                        self.logger.debug(f"Skipping daniel2 {daniel2} as they are currently in a match as a different character.")
                        old_daniels.append(daniel2)
                        continue

                    if daniel1['discord_id'] in self.in_match and self.in_match[daniel1['discord_id']]:
                        self.logger.debug(f"Skipping daniel1 chosen from queue {daniel1} as they are currently in a match as a different character.")
                        old_daniels.append(daniel2)
                        continue

                    # This is an old implementation but I'm keeping it here in case the new one breaks
                    # self.in_queue[str(daniel2['discord_id'])+"@"+daniel2['character']] = [False, deque([str(daniel1['discord_id'])+"@"+daniel1['character']], maxlen=self.recent_opponents_limit)] # why does this do this instead of just mutate
                    # self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][1].append(str(daniel2['discord_id'])+"@"+daniel2['character'])

                    if str(daniel2['discord_id'])+"@"+daniel2['character'] in self.in_queue:
                        self.in_queue[str(daniel2['discord_id'])+"@"+daniel2['character']][0] = False
                        self.in_queue[str(daniel2['discord_id'])+"@"+daniel2['character']][1].append(str(daniel1['discord_id'])+"@"+daniel1['character'])
                    else:
                        self.in_queue[str(daniel2['discord_id'])+"@"+daniel2['character']] = [False, deque([str(daniel1['discord_id'])+"@"+daniel1['character']], maxlen=self.recent_opponents_limit)]

                    self.in_queue[str(daniel1['discord_id'])+"@"+daniel1['character']][1].append(str(daniel2['discord_id'])+"@"+daniel2['character'])

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

                if matchmade:
                    break

            # Re-add all skipped old_daniels back into the queue
            self.logger.debug(f"Current matchmaking round finished, adding old_daniels {old_daniels} back into their dan queues")
            for old_daniel in reversed(old_daniels):
                self.logger.debug(f"Re-adding skipped daniel {old_daniel} back to dans_in_queue[{old_daniel['dan']}].")
                self.dans_in_queue[old_daniel['dan']].appendleft(old_daniel)
                self.in_queue[str(old_daniel['discord_id'])+"@"+old_daniel['character']][0] = True

            if not matchmade:
                self.logger.debug(f"No match found for daniel1 {daniel1}. Re-adding to queues.")
                self.matchmaking_queue.append(daniel1)  # Append back to the deque
                self.dans_in_queue[daniel1['dan']].append(daniel1)  # Append back to the deque
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
            active_match_msg = await channel.send(f"[{datetime.now().time().replace(microsecond=0)}] {daniel1['nickname']}'s {daniel1['character']} {self.emoji_mapping[daniel1['character']]}{p1_alert} (Dan {daniel1['dan']}, {round(daniel1['points'], 1)} points) vs {daniel2['nickname']}'s {daniel2['character']} {self.emoji_mapping[daniel2['character']]}{p2_alert} (Dan {daniel2['dan']}, {round(daniel2['points'], 1)} points)")
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
                content=f"\n## New Match Created\n### Player 1: {id1} {daniel1['character']} (Dan {daniel1['dan']}, {round(daniel1['points'], 1):.1f} points) {self.emoji_mapping[daniel1['character']]}\n\n### Player 2: {id2} {daniel2['character']} (Dan {daniel2['dan']}, {round(daniel2['points'], 1):.1f} points) {self.emoji_mapping[daniel2['character']]}" +\
                (f"\n\nThe room host will be {[id1, id2][room_keyword[1]]}, pw `{room_keyword[0]}`." if room_keyword[0] else f"\n\nNeither player has a default room password set, please coordinate the room in <#1433545145554309233>") +\
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
            winner_char = player1['character']
            winner_old_dan = player1['dan']
            winner_old_points = player1['points']
            loser = player2['nickname']
            loser_char = player2['character']
            loser_old_dan = player2['dan']
            loser_old_points = player2['points']
        else:
            winner_rank, loser_rank = await self.score_update(ctx, player2, player1)
            winner = player2['nickname']
            winner_char = player2['character']
            winner_old_dan = player2['dan']
            winner_old_points = player2['points']
            loser = player1['nickname']
            loser_char = player1['character']
            loser_old_dan = player1['dan']
            loser_old_points = player1['points']

        await ctx.respond(
            f"### The match has been reported as {winner}'s victory over {loser}!\n"
            f"{winner}'s {winner_char} {self.emoji_mapping[winner_char]}: Dan {winner_old_dan}, {round(winner_old_points, 1):.1f} points → **Dan {winner_rank[0]}, {round(winner_rank[1], 1):.1f} points** (+{winner_rank[3]} point(s){", Rank up!" if winner_rank[2] else ""})\n"
            f"{loser}'s {loser_char} {self.emoji_mapping[loser_char]}: Dan {loser_old_dan}, {round(loser_old_points, 1):.1f} points → **Dan {loser_rank[0]}, {round(loser_rank[1], 1):.1f} points** ({loser_rank[3]} point(s){", Rank down..." if loser_rank[2] else ""})"
        )

    #report match score for the queue
    async def report_match_queue(self, interaction: discord.Interaction, player1, player2, winner):
        if (winner == "player1") :
            winner_rank, loser_rank = await self.score_update(interaction, player1,player2)
            winner = player1['nickname']
            winner_char = player1['character']
            winner_old_dan = player1['dan']
            winner_old_points = player1['points']
            loser = player2['nickname']
            loser_char = player2['character']
            loser_old_dan = player2['dan']
            loser_old_points = player2['points']
        else:
            winner_rank, loser_rank = await self.score_update(interaction, player2,player1)
            winner = player2['nickname']
            winner_char = player2['character']
            winner_old_dan = player2['dan']
            winner_old_points = player2['points']
            loser = player1['nickname']
            loser_char = player1['character']
            loser_old_dan = player1['dan']
            loser_old_points = player1['points']

        view = RequeueView(self, player1, player2)

        channel = self.bot.get_channel(self.REPORTED_MATCHES_CHANNEL_ID)
        if channel:
            await channel.send(
                content=f"### The match has been reported as {winner}'s victory over {loser}!\n"
                f"{winner}'s {winner_char} {self.emoji_mapping[winner_char]}: Dan {winner_old_dan}, {round(winner_old_points, 1):.1f} points → **Dan {winner_rank[0]}, {round(winner_rank[1], 1):.1f} points** (+{winner_rank[3]} point(s){", Rank up!" if winner_rank[2] else ""})\n"
                f"{loser}'s {loser_char} {self.emoji_mapping[loser_char]}: Dan {loser_old_dan}, {round(loser_old_points, 1):.1f} points → **Dan {loser_rank[0]}, {round(loser_rank[1], 1):.1f} points** ({loser_rank[3]} point(s){", Rank down..." if loser_rank[2] else ""})",
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
        total_pages = (len(data) // fields_per_page) + 1
        items_per_page = len(data) // total_pages
        for page in range(total_pages):
            em = discord.Embed(title=f"{title} ({page + 1}/{total_pages})", colour=colour)
            page_list.append(em)
            for idx in range(page * items_per_page, min((page + 1) * items_per_page, len(data))):
                em.add_field(name=f"#{idx+1}: {data[idx]['name']}", value=f"Current Rank: {data[idx]['value']}", inline=False)
        return page_list

    # Refactor danisen_stats to use the helper function
    # @discord.commands.slash_command(name="danisenstats", description="See various statistics about the danisen")
    # async def danisen_stats(self, ctx: discord.ApplicationContext):
    #     char_count = self.database_cur.execute(
    #         "SELECT character AS name, COUNT(*) AS value FROM players GROUP BY character ORDER BY character"
    #     ).fetchall()
    #     dan_count = self.database_cur.execute(
    #         "SELECT dan AS name, COUNT(*) AS value FROM players GROUP BY dan ORDER BY dan"
    #     ).fetchall()

    #     # reformat dan count as their names are just numbers
    #     dan_count = [{"name": f"Dan {dan['name']}", "value": dan['value']} for dan in dan_count]
    #     char_pages = self.create_paginated_embeds("Character Stats", char_count, MAX_FIELDS_PER_EMBED)
    #     dan_pages = self.create_paginated_embeds("Dan Stats", dan_count, MAX_FIELDS_PER_EMBED, colour=discord.Color.blurple())

    #     paginator = pages.Paginator(pages=char_pages + dan_pages)
    #     await paginator.respond(ctx.interaction, ephemeral=False)

    # I've currently commented this out, I intend to reimplement it using a different sqlite table and more extensive stats tracking

    # Refactor leaderboard to use the helper function
    @discord.commands.slash_command(description="See the top players")
    async def leaderboard(self, ctx: discord.ApplicationContext):
        daniels = self.database_cur.execute(
            "SELECT nickname || '''s ' || character AS name, 'Dan ' || dan || ', ' || ROUND(points, 1) || ' points' AS value "
            "FROM players JOIN users ON players.discord_id = users.discord_id ORDER BY dan DESC, points DESC"
        ).fetchall()

        leaderboard_pages = self.create_paginated_embeds("Top Danisen Characters", daniels, MAX_FIELDS_PER_EMBED)
        paginator = pages.Paginator(pages=leaderboard_pages)
        await paginator.respond(ctx.interaction, ephemeral=True)

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
            "SELECT users.discord_id AS discord_id, player_name, nickname, keyword, character, dan, points FROM players JOIN users ON players.discord_id = users.discord_id WHERE player_name=? AND character=?", 
            (player_name, character)
        )
        return res.fetchone()

    def get_players_by_dan(self, dan):
        res = self.database_cur.execute(
            "SELECT users.discord_id AS discord_id, player_name, nickname, keyword, character, dan, points FROM players JOIN users ON players.discord_id = users.discord_id WHERE dan=?", 
            (dan,)
        )
        return res.fetchall()

    @discord.commands.slash_command(description="View your or another player's profile")
    async def profile(self, ctx: discord.ApplicationContext, 
                      discord_name: discord.Option(str, name="discordname", autocomplete=player_autocomplete, required=False, default=None)):
        """Lists all registered characters for a player along with their ranks and points."""
        # Determine the target player
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
            "SELECT character, dan, points FROM players WHERE discord_id = ?", 
            (member.id,)
        ).fetchall()

        if not res:
            await ctx.respond(f"{member.name} has no registered characters.")
            return

        user_res = self.database_cur.execute( # implicitly required to exist based on registered characters
            "SELECT * FROM users WHERE discord_id = ?",
            (member.id,)
        ).fetchone()

        player_highest_dan = self.get_players_highest_dan(member.name)

        # Create an embed to display the profile
        em = discord.Embed(
            title=f"{user_res['nickname']}'s Profile",
            color=self.dan_colours[player_highest_dan-1]
        )
        if member.avatar:
            em.set_thumbnail(url=member.avatar.url)

        if user_res["keyword"]:
            em.add_field(
                name=f"Room Password:",
                value=f"`{user_res["keyword"]}`",
                inline=True
            )
        else:
            em.add_field(
                name=f"Room Password:",
                value=f"None (set one with /setroompassword)",
                inline=True
            )

        em.add_field(
            name=f"Characters:",
            value=f"",
            inline=False
        )

        for row in res:
            em.add_field(
                name=f"{row["character"]} {self.emoji_mapping[row['character']]}", 
                value=f"Dan {row['dan']}, {round(row['points'], 1):.1f} points", 
                inline=False
            )

        await ctx.respond(embed=em)

    # Helper function
    # Returns the highest Dan rank on any character registered by this player. If the player has no characters registered, return None
    def get_players_highest_dan(self, player_name: str):
        res = self.database_cur.execute(f"SELECT MAX(dan) as max_dan FROM players JOIN users ON players.discord_id = users.discord_id WHERE player_name='{player_name}'").fetchone()
        if res:
            return res['max_dan']
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

    @discord.commands.slash_command(name="setroompassword", description="Assign a default room password to your profile")
    async def set_room_password(self, ctx: discord.ApplicationContext, pw: discord.Option(str, name="password", required=True)):
        if not pw.isalnum() or len(pw) > 8:
            await ctx.respond(f"Invalid room password `{kw}`. Please assure the password is alphanumeric, is 8 or less characters, and has no spaces (so that it works in GBVSR).")
            return
        self.database_cur.execute(f"UPDATE users SET keyword = '{pw}' WHERE discord_id='{ctx.author.id}'")
        self.database_con.commit()
        await ctx.respond(f"Default room password updated.")

    @discord.commands.slash_command(name="removeroompassword", description="Remove the room password from your profile, if one is assigned")
    async def remove_room_password(self, ctx: discord.ApplicationContext):
        self.database_cur.execute(f"UPDATE users SET keyword = NULL WHERE discord_id='{ctx.author.id}'")
        self.database_con.commit()
        await ctx.respond(f"Default room password removed.")

    async def check_rankup_potential(self, player1, player2):
        # Determine rankup points based on rank type
        rankup_points = RANKUP_POINTS_NORMAL # RANKUP_POINTS_SPECIAL if winner_rank[0] >= SPECIAL_RANK_THRESHOLD else RANKUP_POINTS_NORMAL

        # The return array, index 0 is p1 index 1 is p2, value of 0 means nothing, 1 means rankup chance, -1 means rankdown chance
        ret = [0, 0]

        p1_current_points = player1['points']
        p2_current_points = player2['points']

        p1_point_potential = [1.0, -1.0] #default
        p2_point_potential = [1.0, -1.0]

        if player1['dan'] >= player2['dan'] + self.rank_gap_for_more_points_2: # player1 four or more above player2
            p1_potential = [0.1, -1]
            p2_potential = [2, -0.1]
        elif player1['dan'] >= player2['dan'] + self.rank_gap_for_more_points_1: # player1 two or three above player2
            p1_potential = [0.5, -1]
            p2_potential = [1.5, -0.5]
        elif player2['dan'] >= player1['dan']  + self.rank_gap_for_more_points_2: # player2 four or more above player1
            p1_potential = [2, -0.1]
            p2_potential = [0.1, -1]
        elif player2['dan'] >= player1['dan'] + self.rank_gap_for_more_points_1: # player2 two or three above player1
            p1_potential = [1.5, -0.1]
            p2_potential = [0.1, -1]
        

        # Rankup logic with special rules and Rankdown logic
        if p1_current_points + p1_point_potential[0] >= rankup_points and (not self.special_rank_up_rules or (self.special_rank_up_rules and player1['dan'] >= SPECIAL_RANK_THRESHOLD and player2['dan'] >= SPECIAL_RANK_THRESHOLD)):
            ret[0] = 1
        elif p1_current_points + p1_point_potential[1] <= RANKDOWN_POINTS: # adds negative value
            ret[0] = -1
        if p2_current_points + p2_point_potential[0] >= rankup_points and (not self.special_rank_up_rules or (self.special_rank_up_rules and player1['dan'] >= SPECIAL_RANK_THRESHOLD and player2['dan'] >= SPECIAL_RANK_THRESHOLD)):
            ret[1] = 1
        elif p2_current_points + p2_point_potential[1] <= RANKDOWN_POINTS: # adds negative value
            ret[0] = -1

        return ret 
