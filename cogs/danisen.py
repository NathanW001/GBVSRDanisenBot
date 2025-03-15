import discord, sqlite3, asyncio
from discord.ext import commands, pages
from cogs.database import *
from cogs.custom_views import *
import os
class Danisen(commands.Cog):
    characters = ["Hyde","Linne","Waldstein","Carmine","Orie","Gordeau","Merkava","Vatista","Seth","Yuzuriha","Hilda","Chaos","Nanase","Byakuya","Phonon","Mika","Wagner","Enkidu","Londrekia","Tsurugi","Kaguya","Kuon","Uzuki","Eltnum","Akatsuki","Ogre"]
    players = ["player1", "player2"]
    dan_colours = [discord.Colour.from_rgb(255,255,255), discord.Colour.from_rgb(255,255,0), discord.Colour.from_rgb(255,153,0),
                   discord.Colour.from_rgb(39, 78, 19), discord.Colour.from_rgb(97,0,162), discord.Colour.from_rgb(0,0,177), discord.Colour.from_rgb(120,63,4),
                   #SPECIAL RANKS
                   discord.Colour.from_rgb(0,0,255), discord.Colour.from_rgb(120,63,4), discord.Colour.from_rgb(255,0,0), discord.Colour.from_rgb(152,0,0), discord.Colour.from_rgb(0,0,0)
                   ]

    def __init__(self, bot, database, config_path):
        # Set up the logger
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)

        self.bot = bot
        self._last_member = None

        self.config_path = config_path
        self.update_config()

        self.database_con = database
        self.database_con.row_factory = sqlite3.Row
        self.database_cur = self.database_con.cursor()
        self.database_cur.execute("CREATE TABLE IF NOT EXISTS players(discord_id, player_name, character, dan, points,   PRIMARY KEY (discord_id, character) )")

        self.dans_in_queue = {dan:[] for dan in range(1,self.total_dans+1)}
        self.matchmaking_queue = []
        self.max_active_matches = 3
        self.cur_active_matches = 0

        #dict with following format player_name:[in_queue, last_played_player_name]
        self.in_queue = {}
        #dict with following format player_name:in_match
        self.in_match = {}

    def can_manage_role(self, bot_member, role):
        # Check if bot's highest role is higher than the role to be added
        return (
            bot_member.top_role.position > role.position and 
            bot_member.guild_permissions.manage_roles
        )
    def update_config(self):

        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
        except Exception as e:
            self.logger.warning("Warning", f"Failed to load configuration: {str(e)}")

        ###################################################
        #SET ALL CONFIG VALUES 

        
        self.ACTIVE_MATCHES_CHANNEL_ID = int(config['ACTIVE_MATCHES_CHANNEL_ID']) if (config['ACTIVE_MATCHES_CHANNEL_ID']) else 0
        self.REPORTED_MATCHES_CHANNEL_ID = int(config['REPORTED_MATCHES_CHANNEL_ID']) if 'REPORTED_MATCHES_CHANNEL_ID' in config and config['REPORTED_MATCHES_CHANNEL_ID'] else 0

        self.total_dans = config['total_dans']
        #cannot rank down if ur dan is <= minimum_derank
        self.minimum_derank = config['minimum_derank']
        #if your rank difference is greater  than maximum rank diff you can no points (e.g. max diff of 2, and rank 4 vs  rank 1)
        self.maximum_rank_difference = config['maximum_rank_difference']

        #The minimal gap required for the lower ranked player to gain 2 points on a win
        self.rank_gap_for_more_points = config['rank_gap_for_more_points'] if 'rank_gap_for_more_points' in config else 1

        #if point_rollover is enabled then if we have a dan1 with 2 points, that gains 2 points, they will be (dan 2, 1 point) after
        #without rollover they are only (dan 2, 0 points)
        self.point_rollover = config['point_rollover']
        self.queue_status = config['queue_status']

        ###################################################

    @discord.commands.slash_command(description="Close or open the MM queue (admin debug cmd)")
    @discord.commands.default_permissions(manage_roles=True)
    async def set_queue(self, ctx : discord.ApplicationContext,
                        queue_status : discord.Option(bool)):
        self.queue_status = queue_status
        if queue_status == False:
            self.matchmaking_queue = []
            self.dans_in_queue = {dan:[] for dan in range(1,self.total_dans+1)}
            self.in_queue = {}
            self.in_match = {}
            await ctx.respond(f"The matchmaking queue has been disabled")
        else:
            await ctx.respond(f"The matchmaking queue has been enabled")


    def dead_role(self,ctx, player):
        role = None

        self.logger.info(f'Checking if dan should be removed as well')
        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={player['discord_id']} AND dan={player['dan']}")
        remaining_daniel = res.fetchone()
        if not remaining_daniel:
            self.logger.info(f'Dan role {player['dan']} will be removed')
            role = (discord.utils.get(ctx.guild.roles, name=f"Dan {player['dan']}"))
            return role

    async def score_update(self, ctx, winner, loser):
        winner_rank = [winner['dan'], winner['points']]
        loser_rank = [loser['dan'], loser['points']]

        rankdown = False
        rankup = False
        
        rankup_points = 3 if winner_rank[0] <= 7 else 5

        #winning if you are more than the maximum_rank_difference you gain nothing
        if winner_rank[0] > loser_rank[0] + self.maximum_rank_difference:
            return winner_rank, loser_rank

        if loser_rank[0] >= winner_rank[0] + self.rank_gap_for_more_points:
            #lower ranked player gains 2 point at most if rank gap is big enough
            winner_rank[1] += 2
        else:
            #higher ranked player gains 1 points
            winner_rank[1] += 1

        #minimum rank has different rules to clamp the points lost e.g. (min for dan1 is (dan 1, 0 point), min for other dans is -2 pts)
        if loser_rank[0] > self.minimum_derank:
            loser_rank[1] -= 1
        #point loss for minimum dans is capped at 0 min (minimum is 0 points)
        elif loser_rank[1] > 0:
            loser_rank[1] -= 1

        #rankup logic (normal ranks promote at +3) (special at +5)
        if winner_rank[1] >= rankup_points:
            winner_rank[0] += 1
            if self.point_rollover:
                winner_rank[1] = winner_rank[1] % rankup_points
            else:
                winner_rank[1] = 0
            rankup = True

        #rankdown logic (ranks demote at -3)
        if loser_rank[1] <= -3:
            loser_rank[0] -= 1
            loser_rank[1] = 0
            rankdown = True

        self.logger.info("New Scores")
        self.logger.info(f"Winner : {winner['player_name']} dan {winner_rank[0]}, points {winner_rank[1]}")
        self.logger.info(f"Loser : {loser['player_name']} dan {loser_rank[0]}, points {loser_rank[1]}")

        self.database_cur.execute(f"UPDATE players SET dan = {winner_rank[0]}, points = {winner_rank[1]} WHERE player_name='{winner['player_name']}' AND character='{winner['character']}'")
        self.database_cur.execute(f"UPDATE players SET dan = {loser_rank[0]}, points = {loser_rank[1]} WHERE player_name='{loser['player_name']}' AND character='{loser['character']}'")
        self.database_con.commit()

        #Update roles on rankup/down
        if rankup:
            role = discord.utils.get(ctx.guild.roles, name=f"Dan {winner_rank[0]}")
            member = ctx.guild.get_member(winner['discord_id'])
            bot_member = ctx.guild.get_member(self.bot.user.id)
            if role:
                if self.can_manage_role(bot_member,role):
                    await member.add_roles(role)
                else:
                    self.logger.warning(f"Could not add {role} to {member.name} due to bot's role being too low")

            self.logger.info(f"Dan {winner_rank[0]} added to {member.name}")
            role = self.dead_role(ctx, winner)
            if role:
                if self.can_manage_role(bot_member,role):
                    await member.remove_roles(role)
                else:
                    self.logger.warning(f"Could not remove {role} to {member.name} due to bot's role being too low")

        if rankdown:
            member = ctx.guild.get_member(loser['discord_id'])
            role = self.dead_role(ctx, loser)
            if role:
                await member.remove_roles(role)

        return winner_rank, loser_rank
    # Custom decorator for validation
    def is_valid_char(self, char):
        return char in self.characters

    async def character_autocomplete(self, ctx: discord.AutocompleteContext):
        return [character for character in self.characters if character.lower().startswith(ctx.value.lower())]

    async def player_autocomplete(self, ctx: discord.AutocompleteContext):
        res = self.database_cur.execute(f"SELECT player_name FROM players")
        name_list=res.fetchall()
        names = set([name[0] for name in name_list])
        return [name for name in names if (name.lower()).startswith(ctx.value.lower())]

    @discord.commands.slash_command(description="set a players rank (admin debug cmd)")
    @discord.commands.default_permissions(manage_roles=True)
    async def set_rank(self, ctx : discord.ApplicationContext,
                        player_name :  discord.Option(str, autocomplete=player_autocomplete),
                        char : discord.Option(str, autocomplete=character_autocomplete),
                        dan :  discord.Option(int),
                        points : discord.Option(int)):
        if not self.is_valid_char(char):
            await ctx.respond(f"Invalid char selected {char}. Please choose a valid char.")
            return
        self.database_cur.execute(f"UPDATE players SET dan = {dan}, points = {points} WHERE player_name='{player_name}' AND character='{char}'")
        self.database_con.commit()
        await ctx.respond(f"{player_name}'s {char} rank updated to be dan {dan} points {points}")

    @discord.commands.slash_command(description="help msg")
    async def help(self, ctx : discord.ApplicationContext):
        em = discord.Embed(
            title="Help",
            description="list of all commands",
            color=discord.Color.blurple())
        if self.bot.user.avatar.url:
            em.set_thumbnail(
                url=self.bot.user.avatar.url)

        for slash_command in self.walk_commands():
            em.add_field(name=slash_command.name, 
                        value=slash_command.description if slash_command.description else slash_command.name, 
                        inline=False) 
                        # fallbacks to the command name incase command description is not defined

        await ctx.send_response(embed=em)
    #registers player+char to db
    @discord.commands.slash_command(description="Register to the Danisen database!")
    async def register(self, ctx : discord.ApplicationContext, 
                    char1 : discord.Option(str, autocomplete=character_autocomplete)):
        player_name = ctx.author.name

        if not self.is_valid_char(char1):
            await ctx.respond(f"Invalid char selected {char1}. Please choose a valid char.")
            return

        line = [ctx.author.id, player_name, char1, 1, 0]
        insert_new_player(tuple(line),self.database_cur)
        role_list = []
        char_role = discord.utils.get(ctx.guild.roles, name=char1)
        if char_role:
            role_list.append(char_role)
        self.logger.info(f"Adding to db {player_name} {char1}")
        self.database_con.commit()

        self.logger.info(f"Adding Character and Dan roles to user")
        dan_role = discord.utils.get(ctx.guild.roles, name="Dan 1")
        if dan_role:
            role_list.append(dan_role)

        bot_member = ctx.guild.get_member(self.bot.user.id)
        can_add_roles = True
        message_text = ""
        if role_list:
            for role in role_list:
                can_add_roles = can_add_roles and self.can_manage_role(bot_member,role)
            if can_add_roles:
                await ctx.author.add_roles(*role_list)
            else:
                message_text += "Could not add Dan 1 role or Character roles due to bot's role being too low\n\n"
                self.logger.warning(f"Could not add Dan 1 role or Character roles due to bot's role being too low")
        
        message_text += (f"You are now registered as {player_name} with the following character/s {char1}\n"
                         "if you wish to add more characters you can register multiple times!\n\n"
                         "Welcome to the Danielsen!")

        

        await ctx.respond(message_text)

    @discord.commands.slash_command(description="unregister to the Danisen database!")
    async def unregister(self, ctx : discord.ApplicationContext, 
                    char1 : discord.Option(str, autocomplete=character_autocomplete)):

        if not self.is_valid_char(char1):
            await ctx.respond(f"Invalid char selected {char1}. Please choose a valid char.")
            return

        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={ctx.author.id} AND character='{char1}'")
        daniel = res.fetchone()

        if daniel == None:
            await ctx.respond("You are not registered with that character")
            return

        self.logger.info(f"Removing {ctx.author.name} {ctx.author.id} {char1} from db")
        self.database_cur.execute(f"DELETE FROM players WHERE discord_id={ctx.author.id} AND character='{char1}'")
        self.database_con.commit()

        role_list = []
        char_role = discord.utils.get(ctx.guild.roles, name=char1)
        if char_role:
            role_list.append(discord.utils.get(ctx.guild.roles, name=char1))
        self.logger.info(f"Removing role {char1} from member")

        role = self.dead_role(ctx, daniel)
        if role:
            role_list.append(role)

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
        message_text += f"You have now unregistered {char1}"
        await ctx.respond(message_text)

    #rank command to get discord_name's player rank, (can also ignore 2nd param for own rank)
    @discord.commands.slash_command(description="Get your character rank/Put in a players name to get their character rank!")
    async def rank(self, ctx : discord.ApplicationContext,
                char : discord.Option(str, autocomplete=character_autocomplete),
                discord_name :  discord.Option(str, autocomplete=player_autocomplete)):
        if not self.is_valid_char(char):
            await ctx.respond(f"Invalid char selected {char}. Please choose a valid char.")
            return

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

        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={id} AND character='{char}'")
        data = res.fetchone()
        if data:
            await ctx.respond(f"""{data['player_name']}'s rank for {char} is {data['dan']} dan {data['points']} points""")
        else:
            await ctx.respond(f"""{member.name} is not registered as {char} so you have no rank...""")

    #leaves the matchmaking queue
    @discord.commands.slash_command(description="leave the danisen queue")
    async def leave_queue(self, ctx : discord.ApplicationContext):
        name = ctx.author.name
        self.logger.info(f'leave queue called for {name}')
        daniel = None
        for i, member in enumerate(self.matchmaking_queue):
            if member and (member['player_name'] == name):
                self.logger.info(f'found {name} in MMQ')
                daniel = self.matchmaking_queue.pop(i)
                self.logger.info(f"removed {name} from MMQ {self.matchmaking_queue}")
        
        if daniel:
            for i, member in enumerate(self.dans_in_queue[daniel['dan']]):
                if member['player_name'] == name:
                    self.logger.info(f'found {name} in Danq')
                    daniel = self.dans_in_queue[daniel['dan']].pop(i)
                    self.logger.info(f"removed {name} from DanQ {self.dans_in_queue[daniel['dan']]}")
            
            self.in_queue[daniel['player_name']][0] = False
            await ctx.respond("You have been removed from the queue")
        else:
            await ctx.respond("You are not in queue")
    #joins the matchmaking queue
    @discord.commands.slash_command(description="queue up for danisen games")
    async def join_queue(self, ctx : discord.ApplicationContext,
                    char : discord.Option(str, autocomplete=character_autocomplete),
                    rejoin_queue : discord.Option(bool)):
        if not self.is_valid_char(char):
            await ctx.respond(f"Invalid char selected {char}. Please choose a valid char.")
            return
        await ctx.defer()

        #check if q open
        if self.queue_status == False:
            self.logger.info("Queue is closed ending join function")
            await ctx.respond(f"The matchmaking queue is currently closed")
            return

        #Check if valid character
        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={ctx.author.id} AND character='{char}'")
        daniel = res.fetchone()
        if daniel == None:
            self.logger.info(f"{ctx.author.name} not registered with {char}")
            await ctx.respond(f"You are not registered with that character")
            return

        daniel = DanisenRow(daniel)
        daniel['requeue'] = rejoin_queue

        #Check if in Queue already
        self.logger.info(f"join_queue called for {ctx.author.name}")
        if ctx.author.name not in self.in_queue.keys():
            self.logger.info(f"added {ctx.author.name} to in_queue dict")
            self.in_queue[ctx.author.name] = [True, None]
            self.logger.info(f"in_queue {self.in_queue}")
        elif self.in_queue[ctx.author.name][0]:
            self.logger.info(f"{ctx.author.name} in the queue")
            await ctx.respond(f"You are already in the queue")
            return

        #check if in a match already
        if ctx.author.name not in self.in_match.keys():
            self.logger.info(f"added {ctx.author.name} to in_match dict")
            self.in_match[ctx.author.name] = False
            self.logger.info(f"in_match {self.in_match}")
        elif self.in_match[ctx.author.name]:
            self.logger.info(f"{ctx.author.name} is in an active match and cannot queue up")
            await ctx.respond(f"You are in an active match and cannot queue up")
            return

        self.in_queue[ctx.author.name][0] = True

        self.dans_in_queue[daniel['dan']].append(daniel)
        self.matchmaking_queue.append(daniel)
        await ctx.respond(f"You've been added to the matchmaking queue with {char}")

        self.logger.info("Current MMQ")
        self.logger.info(self.matchmaking_queue)
        self.logger.info("Current DanQ")
        self.logger.info(self.dans_in_queue)
        #matchmake
        if (self.cur_active_matches < self.max_active_matches and
            len(self.matchmaking_queue) >= 2):
            self.logger.info("matchmake function called")
            await self.matchmake(ctx.interaction)

    def rejoin_queue(self, player):
        if self.queue_status == False:
            self.logger.info(f"q is closed so no rejoin")
            return

        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={player["discord_id"]} AND character='{player["character"]}'")
        player = res.fetchone()
        player = DanisenRow(player)
        player['requeue'] = True

        self.in_queue[player['player_name']][0] = True
        self.dans_in_queue[player['dan']].append(player)
        self.matchmaking_queue.append(player)
        self.logger.info(f"{player['player_name']} has rejoined the queue")

    @discord.commands.slash_command(description="view players in the queue")
    async def view_queue(self, ctx : discord.ApplicationContext):
        self.matchmaking_queue = [player for player in self.matchmaking_queue if player]
        self.logger.info("view_queue called")
        self.logger.info("Current MMQ")
        self.logger.info(self.matchmaking_queue)
        self.logger.info("Current DanQ")
        self.logger.info(self.dans_in_queue)
        await ctx.respond(f"Current full MMQ {self.matchmaking_queue}\nCurrent full DanQ {self.dans_in_queue}")

    async def matchmake(self, ctx : discord.Interaction):
        while (self.cur_active_matches < self.max_active_matches and
                len(self.matchmaking_queue) >= 2):
            daniel1 = self.matchmaking_queue.pop(0)
            if not daniel1:
                continue

            self.in_queue[daniel1['player_name']][0] = False
            self.logger.info(f"Updated in_queue to set {daniel1} to False")
            self.logger.info(f"in_queue {self.in_queue}")


            same_daniel = self.dans_in_queue[daniel1['dan']].pop(0)
            #sanity check that this is also the latest daniel in the respective dan queue
            if daniel1 != same_daniel:
                self.logger.error(f"Somethings gone very wrong... daniel queues are not synchronized {daniel1=} {same_daniel=}")
                return
            
            #iterate through daniel queues to find suitable opponent
            #will search through queues for an opponent closest in dan prioritizing higher dan
            #x, x+1, x-1, x+2, x-2 etc.
            #e.g. for a dan 3 player we will search the queues as follows
            #3, 4, 2, 5, 1, 6, 7
            #(defaults to ascending order or descending order once out of dans lower or higher resp.)

            #creating daniel iterator (the search pattern defined above)
            check_dan = [daniel1['dan']]
            for dan_offset in range(1, max(self.total_dans-check_dan[0], check_dan[0]-1)):
                cur_dan = check_dan[0] + dan_offset
                if  1 <= cur_dan <= 7:
                    check_dan.append(cur_dan)
                cur_dan = check_dan[0] - dan_offset
                if  1 <= cur_dan <= 7:
                    check_dan.append(cur_dan)
            
            self.logger.info(f"dan queues to check {check_dan}")
            old_daniel = None
            matchmade = False
            for dan in check_dan:
                if self.dans_in_queue[dan]:
                    daniel2 = self.dans_in_queue[dan].pop(0)
                    if self.in_queue[daniel1['player_name']][1] == daniel2['player_name']:
                        #same match would occur, find different opponent
                        self.logger.info(f"Same match would occur but prevented {daniel1} vs {daniel2}")
                        old_daniel = daniel2
                        continue
                    
                    self.in_queue[daniel2['player_name']] = [False, daniel1['player_name']]
                    self.in_queue[daniel1['player_name']] = [False, daniel2['player_name']]
                    self.logger.info(f"Updated in_queue to set last played match")
                    self.logger.info(f"in_queue {self.in_queue}")

                    #this is so we clean up the main queue later for players that have already been matched
                    for idx in reversed(range(len(self.matchmaking_queue))):
                        player = self.matchmaking_queue[idx]
                        if player and (player['player_name'] == daniel2['player_name']):
                             self.matchmaking_queue[idx] = None
                             self.logger.info(f"Set {player['player_name']} to none in matchmaking queue")
                             self.logger.info(self.matchmaking_queue)


                    self.logger.info(f"match made between {daniel1} and {daniel2}")
                    self.in_match[daniel1['player_name']] = True
                    self.in_match[daniel2['player_name']] = True
                    matchmade = True
                    await self.create_match_interaction(ctx, daniel1, daniel2)
                    break
            if old_daniel:
                #readding old daniel back into the q
                self.dans_in_queue[old_daniel['dan']].insert(0, old_daniel)
                self.in_queue[old_daniel['player_name']][0] = True
                self.logger.info(f"we readded daniel2 {old_daniel}")
            if not matchmade:
                 self.matchmaking_queue.append(daniel1)
                 self.dans_in_queue[daniel1['dan']].append(daniel1)
                 self.in_queue[daniel1['player_name']][0] = True
                 self.logger.info(f"we readded daniel1 {daniel1} and are breaking from matchmake")
                 break

    async def create_match_interaction(self, ctx : discord.Interaction,
                                       daniel1, daniel2):
        self.cur_active_matches += 1
        view = MatchView(self, daniel1, daniel2)
        id1 = f'<@{daniel1['discord_id']}>'
        id2 = f'<@{daniel2['discord_id']}>'
        channel = self.bot.get_channel(self.ACTIVE_MATCHES_CHANNEL_ID)
        if channel:
            webhook_msg = await channel.send(f"{id1} {daniel1['character']} dan {daniel1['dan']} points {daniel1['points']} vs {id2} {daniel2['character']} dan {daniel2['dan']} points {daniel2['points']} "+
                                         "\n Note only players in the match can report it! (and admins)", view=view)
            await webhook_msg.pin()

            #deleting the pin added system message (checking last 5 messages incase some other stuff was posted in the channel in the meantime)
            async for message in channel.history(limit=5):
                if message.type == discord.MessageType.pins_add:
                    await message.delete()
        else:
            await ctx.respond(f"""Could not find channel to send match message to (could be an issue with channel id {self.ACTIVE_MATCHES_CHANNEL_ID} or bot permissions)""")


    #report match score
    @discord.commands.slash_command(description="Report a match score")
    @discord.commands.default_permissions(send_polls=True)
    async def report_match(self, ctx : discord.ApplicationContext,
                        player1_name :  discord.Option(str, autocomplete=player_autocomplete),
                        char1 : discord.Option(str, autocomplete=character_autocomplete),
                        player2_name :  discord.Option(str, autocomplete=player_autocomplete),
                        char2 : discord.Option(str, autocomplete=character_autocomplete),
                        winner : discord.Option(str, choices=players)):
        if not self.is_valid_char(char1):
            await ctx.respond(f"Invalid char1 selected {char1}. Please choose a valid char1.")
            return
        if not self.is_valid_char(char2):
            await ctx.respond(f"Invalid char2 selected {char2}. Please choose a valid char2.")
            return
        res = self.database_cur.execute(f"SELECT * FROM players WHERE player_name='{player1_name}' AND character='{char1}'")
        player1 = res.fetchone()
        res = self.database_cur.execute(f"SELECT * FROM players WHERE player_name='{player2_name}' AND character='{char2}'")
        player2 = res.fetchone()

        if not player1:
            await ctx.respond(f"""No player named {player1_name} with character {char1}""")
            return
        if not player2:
            await ctx.respond(f"""No player named {player2_name} with character {char2}""")
            return

        self.logger.info(f"reported match {player1_name} vs {player2_name} as {winner} win")
        if (winner == "player1") :
            winner_rank, loser_rank = await self.score_update(ctx, player1, player2)
            winner = player1_name
            loser = player2_name
        else:
            loser_rank, winner_rank = await self.score_update(ctx, player2, player1)
            winner = player2_name
            loser = player1_name

        await ctx.respond(f"Match has been reported as {winner}'s victory over {loser}\n{player1_name}'s {char1} rank is now {winner_rank[0]} dan {winner_rank[1]} points\n{player2_name}'s {char2} rank is now {loser_rank[0]} dan {loser_rank[1]} points")

    #report match score for the queue
    async def report_match_queue(self, interaction: discord.Interaction, player1, player2, winner):
        if (winner == "player1") :
            winner_rank, loser_rank = await self.score_update(interaction, player1,player2)
            winner = player1['player_name']
            loser = player2['player_name']
        else:
            loser_rank, winner_rank = await self.score_update(interaction, player2,player1)
            winner = player2['player_name']
            loser = player1['player_name']

        channel = self.bot.get_channel(self.REPORTED_MATCHES_CHANNEL_ID)
        if channel:
            await channel.send(f"Match has been reported as {winner}'s victory over {loser}\n{player1['player_name']}'s {player1['character']} rank is now {winner_rank[0]} dan {winner_rank[1]} points\n{player2['player_name']}'s {player2['character']} rank is now {loser_rank[0]} dan {loser_rank[1]} points")
        else:
            self.logger.warning("No Report Matches Channel")

    @discord.commands.slash_command(description="See players in a specific dan")
    async def dan(self, ctx : discord.ApplicationContext,
                  dan : discord.Option(int, min_value=1, max_value=12)):
        res = self.database_cur.execute(f"SELECT * FROM players WHERE dan={dan}")
        daniels = res.fetchall()
        page_list = []
        em = discord.Embed(title=f"Dan {dan}",colour=self.dan_colours[dan-1])
        page_list.append(em)
        page_size = 0
        for daniel in daniels:
            page_size += 1
            page_list[-1].add_field(name=f"{daniel['player_name']} {daniel['character']}", value=f"Dan : {daniel['dan']} Points: {daniel['points']}")
            if page_size == 10:
                em = discord.Embed(title=f"Dan {dan}",colour=self.dan_colours[dan-1])
                page_list.append(em)
                page_size = 0
        paginator = pages.Paginator(pages=page_list)
        await paginator.respond(ctx.interaction, ephemeral=False)

    @discord.commands.slash_command(description="See various statistics about the danisen")
    async def danisen_stats(self, ctx : discord.ApplicationContext):
        res = self.database_cur.execute(("SELECT character, COUNT(*) as count "
                                        "FROM players "
                                        "GROUP BY character "
                                        "ORDER BY character;"))
        char_count = res.fetchall()
        res = self.database_cur.execute(("SELECT dan, COUNT(*) as count "
                                        "FROM players "
                                        "GROUP BY dan "
                                        "ORDER BY dan;"))
        dan_count = res.fetchall()
        page_list = []
        em = discord.Embed(title=f"Character Stats 1/2")
        page_list.append(em)
        for char in char_count[:13]:
            em.add_field(name=f"{char['character']}", value=f"Count : {char['count']}")
        em = discord.Embed(title=f"Character Stats 2/2")
        page_list.append(em)
        for char in char_count[13:]:
            em.add_field(name=f"{char['character']}", value=f"Count : {char['count']}")
        em = discord.Embed(title=f"Dan Stats")
        page_list.append(em)
        for dan in dan_count:
            em.add_field(name=f"Dan {dan['dan']}", value=f"Count : {dan['count']}")
        paginator = pages.Paginator(pages=page_list)
        await paginator.respond(ctx.interaction, ephemeral=False)


    @discord.commands.slash_command(description="See the top players")
    async def leaderboard(self, ctx : discord.ApplicationContext):
        res = self.database_cur.execute(f"SELECT * FROM players ORDER BY dan DESC, points DESC")
        daniels = res.fetchall()
        page_list = []
        page_num = 1
        em = discord.Embed(title=f"Top Daniels {page_num}")
        page_list.append(em)
        page_size = 0
        for daniel in daniels:
            page_size += 1
            page_list[-1].add_field(name=f"{daniel['player_name']} {daniel['character']}", value=f"Dan : {daniel['dan']} Points: {daniel['points']}")
            if page_size == 10:
                page_num += 1
                em = discord.Embed(title=f"Top Daniels {page_num}")
                page_list.append(em)
                page_size = 0
        paginator = pages.Paginator(pages=page_list)
        await paginator.respond(ctx.interaction, ephemeral=False)

    @discord.commands.slash_command(description="Update max matches for the queue system (Admin Cmd)")
    @discord.commands.default_permissions(manage_messages=True)
    async def update_max_matches(self, ctx : discord.ApplicationContext,
                                 max : discord.Option(int, min_value=1)):
        self.max_active_matches = max
        await ctx.respond(f"Max matches updated to {max}")
