import discord, sqlite3, asyncio
from discord.ext import commands, pages
from cogs.database import *
from cogs.custom_views import *
class Danisen(commands.Cog):
    characters = ["Hyde","Linne","Waldstein","Carmine","Orie","Gordeau","Merkava","Vatista","Seth","Yuzuriha","Hilda","Chaos","Nanase","Byakuya","Phonon","Mika","Wagner","Enkidu","Londrekia","Tsurugi","Kaguya","Kuon","Uzuki","Eltnum","Akatsuki"]
    players = ["player1", "player2"]
    dan_colours = [discord.Colour.from_rgb(255,255,255), discord.Colour.from_rgb(255,255,0), discord.Colour.from_rgb(255,153,0),
                   discord.Colour.from_rgb(39, 78, 19), discord.Colour.from_rgb(97,0,162), discord.Colour.from_rgb(0,0,177), discord.Colour.from_rgb(120,63,4),
                   #SPECIAL RANKS
                   discord.Colour.from_rgb(0,0,255), discord.Colour.from_rgb(120,63,4), discord.Colour.from_rgb(255,0,0), discord.Colour.from_rgb(152,0,0), discord.Colour.from_rgb(0,0,0)
                   ]

    def __init__(self, bot, database, config):
        self.bot = bot
        self._last_member = None

        ###################################################
        #SET ALL CONFIG VALUES 

        self.ACTIVE_MATCHES_CHANNEL_ID = config['ACTIVE_MATCHES_CHANNEL_ID']
        self.total_dans = config['total_dans']
        #cannot rank down if ur dan is <= minimum_derank
        self.minimum_derank = config['minimum_derank']
        #if your rank difference is greater  than maximum rank diff you can no points (e.g. max diff of 2, and rank 4 vs  rank 1)
        self.maximum_rank_difference = config['maximum_rank_difference']
        #if point_rollover is enabled then if we have a dan1 with 2 points, that gains 2 points, they will be (dan 2, 1 point) after
        #without rollover they are only (dan 2, 0 points)
        self.point_rollover = config['point_rollover']
        self.queue_status = config['queue_status']

        ###################################################

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

    @discord.commands.slash_command(description="Close or open the MM queue (admin debug cmd)")
    @discord.commands.default_permissions(manage_roles=True)
    async def set_queue(self, ctx : discord.ApplicationContext,
                        queue_status : discord.Option(bool)):
        self.queue_status = queue_status
        if queue_status == False:
            self.matchmaking_queue = []
            self.dans_in_queue = {dan:[] for dan in range(1,self.total_dans+1)}
            self.max_active_matches = 3
            self.cur_active_matches = 0
            self.in_queue = {}
            self.in_match = {}
            await ctx.respond(f"The matchmaking queue has been disabled")
        else:
            await ctx.respond(f"The matchmaking queue has been enabled")


    def dead_role(self,ctx, player):
        role = None

        print(f'Checking if dan should be removed as well')
        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={player['discord_id']} AND dan={player['dan']}")
        remaining_daniel = res.fetchone()
        if not remaining_daniel:
            print(f'Dan role {player['dan']} will be removed')
            role = (discord.utils.get(ctx.guild.roles, name=f"Dan {player['dan']}"))
            return role

    async def score_update(self, ctx, winner, loser):
        winner_rank = [winner['dan'], winner['points']]
        loser_rank = [loser['dan'], loser['points']]

        rankdown = False
        rankup = False

        #winning if you are more than the maximum_rank_difference you gain nothing
        if winner_rank[0] > loser_rank[0] + self.maximum_rank_difference:
            return winner_rank, loser_rank

        if winner_rank[0] >= loser_rank[0]:
            #higher ranked player gains 1 point at most
            winner_rank[1] += 1
        else:
            #lower ranked player gains 2 points
            winner_rank[1] += 2

        #minimum rank has different rules to clamp the points lost e.g. (min for dan1 is (dan 1, 0 point), min for other dans is -2 pts)
        if loser_rank[0] > self.minimum_derank:
            loser_rank[1] -= 1
        #point loss for dan1 (minimum is 0 points)
        elif loser_rank[0] == 1 and loser_rank[1] > 0:
            loser_rank[1] -= 1
        #point loss for 1 < dan < minimum_derank (minimum is -2 points)
        elif loser_rank[1] > -2:
            loser_rank[1] -= 1

        #rankup logic (normal ranks promote at +3)
        if winner_rank[1] >= 3:
            winner_rank[0] += 1
            if self.point_rollover:
                winner_rank[1] = winner_rank[1] % 3
            else:
                winner_rank[1] = 0
            rankup = True

        #rankdown logic (normal ranks demote at -3)
        if loser_rank[1] <= -3:
            loser_rank[0] -= 1
            loser_rank[1] = 0
            rankdown = True

        print("New Scores")
        print(f"Winner : {winner['player_name']} dan {winner_rank[0]}, points {winner_rank[1]}")
        print(f"Loser : {loser['player_name']} dan {loser_rank[0]}, points {loser_rank[1]}")

        self.database_cur.execute(f"UPDATE players SET dan = {winner_rank[0]}, points = {winner_rank[1]} WHERE player_name='{winner['player_name']}' AND character='{winner['character']}'")
        self.database_cur.execute(f"UPDATE players SET dan = {loser_rank[0]}, points = {loser_rank[1]} WHERE player_name='{loser['player_name']}' AND character='{loser['character']}'")
        self.database_con.commit()

        #Update roles on rankup/down
        if rankup:
            role = discord.utils.get(ctx.guild.roles, name=f"Dan {winner_rank[0]}")
            member = ctx.guild.get_member(winner['discord_id'])
            if role:
                await member.add_roles(role)

            print(f"Dan {winner_rank[0]} added to {member.name}")
            role = self.dead_role(ctx, winner)
            if role:
                await member.remove_roles(role)

        if rankdown:
            member = ctx.guild.get_member(loser['discord_id'])
            role = self.dead_role(ctx, loser)
            if role:
                await member.remove_roles(role)

        return winner_rank, loser_rank

    async def player_autocomplete(self, ctx: discord.AutocompleteContext):
        res = self.database_cur.execute(f"SELECT player_name FROM players")
        name_list=res.fetchall()
        names = set([name[0] for name in name_list])
        return [name for name in names if (name.lower()).startswith(ctx.value.lower())]

    @discord.commands.slash_command(description="set a players rank (admin debug cmd)")
    @discord.commands.default_permissions(manage_roles=True)
    async def set_rank(self, ctx : discord.ApplicationContext,
                        player_name :  discord.Option(str, autocomplete=player_autocomplete),
                        char : discord.Option(str, choices=characters),
                        dan :  discord.Option(int),
                        points : discord.Option(int)):

        self.database_cur.execute(f"UPDATE players SET dan = {dan}, points = {points} WHERE player_name='{player_name}' AND character='{char}'")
        self.database_con.commit()
        await ctx.respond(f"{player_name}'s {char} rank updated to be dan {dan} points {points}")

    @discord.commands.slash_command(description="help msg")
    async def help(self, ctx : discord.ApplicationContext):
        em = discord.Embed(
            title="Help",
            description="list of all commands",
            color=discord.Color.blurple())
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
                    char1 : discord.Option(str, choices=characters),
                    char2 : discord.Option(str, choices=characters, required=False),
                    char3 : discord.Option(str, choices=characters, required=False)):
        char3 = char3 or ""
        char2 = char2 or ""
        player_name = ctx.author.name
        line = [ctx.author.id, player_name, char1, 1, 0]
        insert_new_player(tuple(line),self.database_cur)
        role_list = []
        char_role = discord.utils.get(ctx.guild.roles, name=char1)
        if char_role:
            role_list.append(char_role)

        if char2:
            line[2] = char2
            char_role=discord.utils.get(ctx.guild.roles, name=char2)
            if char_role:
                role_list.append(char_role)
            insert_new_player(tuple(line),self.database_cur)
        if char3:
            line[2] = char3
            char_role=discord.utils.get(ctx.guild.roles, name=char3)
            if char_role:
                role_list.append(char_role)
            insert_new_player(tuple(line),self.database_cur)
        print(f"Adding to db {player_name} {char1} {char2} {char3}")
        self.database_con.commit()

        print(f"Adding Character and Dan roles to user")
        dan_role = discord.utils.get(ctx.guild.roles, name="Dan 1")
        if dan_role:
            role_list.append(dan_role)
        if role_list:
            await ctx.author.add_roles(*role_list)

        await ctx.respond(f"""You are now registered as {player_name} with the following character/s {char1} {char2} {char3}\nif you wish to add more characters you can register multiple times!\n\nWelcome to the Danielsen!""")

    @discord.commands.slash_command(description="unregister to the Danisen database!")
    async def unregister(self, ctx : discord.ApplicationContext, 
                    char1 : discord.Option(str, choices=characters)):
        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={ctx.author.id} AND character='{char1}'")
        daniel = res.fetchone()

        if daniel == None:
            await ctx.respond("You are not registered with that character")
            return

        print(f"Removing {ctx.author.name} {ctx.author.id} {char1} from db")
        self.database_cur.execute(f"DELETE FROM players WHERE discord_id={ctx.author.id} AND character='{char1}'")
        self.database_con.commit()

        role_list = []
        role_list.append(discord.utils.get(ctx.guild.roles, name=char1))
        print(f"Removing role {char1} from member")

        role = self.dead_role(ctx, daniel)
        if role:
            role_list.append(role)
            
        if role_list:
            await ctx.author.remove_roles(*role_list)

        await ctx.respond(f"""You have now unregistered {char1}""")

    #rank command to get discord_name's player rank, (can also ignore 2nd param for own rank)
    @discord.commands.slash_command(description="Get your character rank/Put in a players name to get their character rank!")
    async def rank(self, ctx : discord.ApplicationContext,
                char : discord.Option(str, choices=characters),
                discord_name :  discord.Option(str, autocomplete=player_autocomplete)):
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
        print(f'leave queue called for {name}')
        daniel = None
        for i, member in enumerate(self.matchmaking_queue):
            if member and (member['player_name'] == name):
                print(f'found {name} in MMQ')
                daniel = self.matchmaking_queue.pop(i)
                print(f"removed {name} from MMQ {self.matchmaking_queue}")
        
        if daniel:
            for i, member in enumerate(self.dans_in_queue[daniel['dan']]):
                if member['player_name'] == name:
                    print(f'found {name} in Danq')
                    daniel = self.dans_in_queue[daniel['dan']].pop(i)
                    print(f"removed {name} from DanQ {self.dans_in_queue[daniel['dan']]}")
            
            self.in_queue[daniel['player_name']][0] = False
            await ctx.respond("You have been removed from the queue")
        else:
            await ctx.respond("You are not in queue")
    #joins the matchmaking queue
    @discord.commands.slash_command(description="queue up for danisen games")
    async def join_queue(self, ctx : discord.ApplicationContext,
                    char : discord.Option(str, choices=characters),
                    rejoin_queue : discord.Option(bool)):
        await ctx.defer()

        #check if q open
        if self.queue_status == False:
            await ctx.respond(f"The matchmaking queue is currently closed")
            return

        #Check if valid character
        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={ctx.author.id} AND character='{char}'")
        daniel = res.fetchone()
        if daniel == None:
            await ctx.respond(f"You are not registered with that character")
            return

        daniel = DanisenRow(daniel)
        daniel['requeue'] = rejoin_queue

        #Check if in Queue already
        print(f"join_queue called for {ctx.author.name}")
        if ctx.author.name not in self.in_queue.keys():
            print(f"added {ctx.author.name} to in_queue dict")
            self.in_queue[ctx.author.name] = [True, None]
            print(f"in_queue {self.in_queue}")
        elif self.in_queue[ctx.author.name][0]:
            await ctx.respond(f"You are already in the queue")
            return
        self.in_queue[ctx.author.name][0] = True

        #check if in a match already
        if ctx.author.name not in self.in_match.keys():
            print(f"added {ctx.author.name} to in_match dict")
            self.in_match[ctx.author.name] = False
            print(f"in_match {self.in_match}")
        elif self.in_match[ctx.author.name]:
            await ctx.respond(f"You are in an active match and cannot queue up")
            return

        self.dans_in_queue[daniel['dan']].append(daniel)
        self.matchmaking_queue.append(daniel)
        await ctx.respond(f"You've been added to the matchmaking queue with {char}")

        print("Current MMQ")
        print(self.matchmaking_queue)
        print("Current DanQ")
        print(self.dans_in_queue)
        #matchmake
        if (self.cur_active_matches != self.max_active_matches and
            len(self.matchmaking_queue) >= 2):
            print("matchmake function called")
            await self.matchmake(ctx.interaction)

    def rejoin_queue(self, player):
        if self.queue_status == False:
            print(f"q is closed so no rejoin")
            return

        res = self.database_cur.execute(f"SELECT * FROM players WHERE discord_id={player["discord_id"]} AND character='{player["character"]}'")
        player = res.fetchone()
        player = DanisenRow(player)
        player['requeue'] = True

        self.in_queue[player['player_name']][0] = True
        self.dans_in_queue[player['dan']].append(player)
        self.matchmaking_queue.append(player)
        print(f"{player['player_name']} has rejoined the queue")

        
    async def matchmake(self, ctx : discord.Interaction):
        while (self.cur_active_matches != self.max_active_matches and
                len(self.matchmaking_queue) >= 2):
            daniel1 = self.matchmaking_queue.pop(0)
            if not daniel1:
                continue

            self.in_queue[daniel1['player_name']][0] = False
            print(f"Updated in_queue to set {daniel1} to False")
            print(f"in_queue {self.in_queue}")


            same_daniel = self.dans_in_queue[daniel1['dan']].pop(0)
            #sanity check that this is also the latest daniel in the respective dan queue
            if daniel1 != same_daniel:
                print(f"Somethings gone very wrong... daniel queues are not synchronized {daniel1=} {same_daniel=}")
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
            
            print(f"dan queues to check {check_dan}")
            old_daniel = None
            matchmade = False
            for dan in check_dan:
                if self.dans_in_queue[dan]:
                    daniel2 = self.dans_in_queue[dan].pop(0)
                    if self.in_queue[daniel1['player_name']][1] == daniel2['player_name']:
                        #same match would occur, find different opponent
                        print(f"Same match would occur but prevented {daniel1} vs {daniel2}")
                        old_daniel = daniel2
                        continue
                    
                    self.in_queue[daniel2['player_name']] = [False, daniel1['player_name']]
                    self.in_queue[daniel1['player_name']] = [False, daniel2['player_name']]
                    print(f"Updated in_queue to set last played match")
                    print(f"in_queue {self.in_queue}")

                    #this is so we clean up the main queue later for players that have already been matched
                    for idx in reversed(range(len(self.matchmaking_queue))):
                        player = self.matchmaking_queue[idx]
                        if player and (player['player_name'] == daniel2['player_name']):
                             self.matchmaking_queue[idx] = None
                             print(f"Set {player['player_name']} to none in matchmaking queue")
                             print(self.matchmaking_queue)


                    print(f"match made between {daniel1} and {daniel2}")
                    self.in_match[daniel1['player_name']] = True
                    self.in_match[daniel2['player_name']] = True
                    matchmade = True
                    await self.create_match_interaction(ctx, daniel1, daniel2)
                    break
            if old_daniel:
                #readding old daniel back into the q
                self.dans_in_queue[old_daniel['dan']].insert(0, old_daniel)
                self.in_queue[old_daniel['player_name']][0] = True
                print(f"we readded daniel2 {old_daniel}")
            if not matchmade:
                 self.matchmaking_queue.append(daniel1)
                 self.dans_in_queue[daniel1['dan']].append(daniel1)
                 self.in_queue[daniel1['player_name']][0] = True
                 print(f"we readded daniel1 {daniel1} and are breaking from matchmake")
                 break

    async def create_match_interaction(self, ctx : discord.Interaction,
                                       daniel1, daniel2):
        self.cur_active_matches += 1
        view = MatchView(self, daniel1, daniel2)
        id1 = f'<@{daniel1['discord_id']}>'
        id2 = f'<@{daniel2['discord_id']}>'
        channel = self.bot.get_channel(self.ACTIVE_MATCHES_CHANNEL_ID)
        webhook_msg = await channel.send(id1 +" "+ daniel1['character'] + " vs " + id2 + " " + daniel2['character'] +
                                         "\n Note only players in the match can report it! (and admins)", view=view)

        await webhook_msg.pin()

    #report match score
    @discord.commands.slash_command(description="Report a match score")
    @discord.commands.default_permissions(send_polls=True)
    async def report_match(self, ctx : discord.ApplicationContext,
                        player1_name :  discord.Option(str, autocomplete=player_autocomplete),
                        char1 : discord.Option(str, choices=characters),
                        player2_name :  discord.Option(str, autocomplete=player_autocomplete),
                        char2 : discord.Option(str, choices=characters),
                        winner : discord.Option(str, choices=players)):
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

        print(f"reported match {player1_name} vs {player2_name} as {winner} win")
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

        await interaction.respond(f"Match has been reported as {winner}'s victory over {loser}\n{player1['player_name']}'s {player1['character']} rank is now {winner_rank[0]} dan {winner_rank[1]} points\n{player2['player_name']}'s {player2['character']} rank is now {loser_rank[0]} dan {loser_rank[1]} points")

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
