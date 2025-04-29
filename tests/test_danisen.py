import unittest
import coverage
import json
from unittest.mock import AsyncMock, MagicMock, patch
from collections import deque

# Mock the discord.commands.slash_command decorator
def mock_slash_command(*args, **kwargs):
    def decorator(func):
        return func
    return decorator

# Apply the patch before importing Danisen
patch("discord.commands.slash_command", mock_slash_command).start()

from cogs.danisen import Danisen  # Import after patching
import discord

class TestDanisen(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # Set up mocks for bot, database, and context
        self.bot = MagicMock()
        self.database = MagicMock()
        self.database_con = MagicMock()
        self.database_cur = MagicMock()
        self.database.cursor.return_value = self.database_cur
        self.database_con.cursor.return_value = self.database_cur
        self.database_con.commit = MagicMock()
        self.config_path = "config.json"

        # Initialize the Danisen cog
        self.danisen = Danisen(self.bot, self.database_con, self.config_path)

        # Mock database cursor methods
        self.database_cur.execute = MagicMock(return_value=self.database_cur)
        self.database_cur.fetchone = MagicMock()
        self.database_cur.fetchall = MagicMock()

        # Mock context and author
        self.ctx = AsyncMock()
        self.ctx.author = AsyncMock()
        self.ctx.author.add_roles = AsyncMock()
        self.ctx.author.remove_roles = AsyncMock()
        self.ctx.respond = AsyncMock()
        self.ctx.defer = AsyncMock()

    def mock_database_response(self, fetchone=None, fetchall=None):
        """Helper to mock database responses for fetchone and fetchall."""
        self.database_cur.fetchone.return_value = fetchone
        self.database_cur.fetchall.return_value = fetchall

    def mock_interaction(self):
        """Helper to mock ctx.interaction as a valid discord.Interaction."""
        self.ctx.interaction = MagicMock(spec=discord.Interaction)
        self.ctx.interaction.followup.send = AsyncMock()

    def mock_guild(self):
        """Helper to mock ctx.guild and its methods."""
        self.ctx.guild = MagicMock()
        self.ctx.guild.get_member = MagicMock(return_value=self.ctx.author)

    async def call_and_verify(self, coro, *args, db_calls=None, response=None):
        """Helper to call a coroutine and verify database calls and responses."""
        await coro(*args)
        if db_calls:
            for call in db_calls:
                self.database_cur.execute.assert_any_call(*call)
        if response:
            self.ctx.respond.assert_called_with(response)

    async def test_register_new_player(self):
        """Test registering a new player with a character."""
        self.ctx.author.id = 12345
        self.ctx.author.name = "TestPlayer"
        char1 = "Hyde"

        self.mock_database_response(fetchone=None)
        self.mock_guild()

        await self.call_and_verify(
            self.danisen.register,
            self.ctx, char1,
            db_calls=[
                ("INSERT INTO players (discord_id, player_name, character, dan, points) VALUES (?, ?, ?, ?, ?)",
                 (12345, "TestPlayer", "Hyde", 1, 0))
            ],
            response=(
                "You are now registered as TestPlayer with the following character/s Hyde\n"
                "If you wish to add more characters, you can register multiple times!\n\n"
                "Welcome to the Danisen!"
            )
        )

    async def test_unregister_player_not_in_queue_or_match(self):
        """Test unregistering a player who is not in a queue or match."""
        self.ctx.author.id = 12345
        self.ctx.author.name = "TestPlayer"
        char1 = "Hyde"

        self.database_cur.fetchone.side_effect = [
            {"discord_id": 12345, "character": "Hyde", "dan": 1, "points": 0},
            None
        ]
        self.mock_guild()

        await self.call_and_verify(
            self.danisen.unregister,
            self.ctx, char1,
            db_calls=[
                ("SELECT * FROM players WHERE discord_id=12345 AND dan=1",),
                ("DELETE FROM players WHERE discord_id=12345 AND character='Hyde'",)
            ],
            response="You have now unregistered Hyde"
        )

    async def test_join_queue(self):
        """Test joining the matchmaking queue."""
        self.ctx.author.id = 12345
        self.ctx.author.name = "TestPlayer"
        char = "Hyde"

        # Simulate player in the database
        self.mock_database_response(fetchone={"discord_id": 12345, "character": "Hyde", "dan": 1, "points": 0})

        # Call the join_queue function with rejoin_queue as part of args
        await self.call_and_verify(
            self.danisen.join_queue,
            self.ctx, char, False,  # Pass rejoin_queue as positional argument
            response="You've been added to the matchmaking queue with Hyde"
        )

    async def test_leave_queue(self):
        """Test leaving the matchmaking queue."""
        self.ctx.author.name = "TestPlayer"
        self.danisen.matchmaking_queue.append({"player_name": "TestPlayer", "dan": 1})
        self.danisen.dans_in_queue[1].append({"player_name": "TestPlayer", "dan": 1})
        self.danisen.in_queue["TestPlayer"] = [True, deque()]

        await self.call_and_verify(
            self.danisen.leave_queue,
            self.ctx,
            response="You have been removed from the queue"
        )

    async def test_view_queue(self):
        """Test viewing the matchmaking queue."""
        self.danisen.matchmaking_queue.extend([
            {"player_name": "Player1", "dan": 1},
            {"player_name": "Player2", "dan": 2}
        ])
        self.danisen.dans_in_queue[1].append({"player_name": "Player1", "dan": 1})
        self.danisen.dans_in_queue[2].append({"player_name": "Player2", "dan": 2})

        await self.call_and_verify(
            self.danisen.view_queue,
            self.ctx,
            response=(
                f"Current full MMQ {repr(self.danisen.matchmaking_queue)}\n"
                f"Current full DanQ {repr(self.danisen.dans_in_queue)}"
            )
        )

    async def test_dan(self):
        """Test viewing players in a specific dan."""
        self.mock_database_response(fetchall=[
            {"player_name": "Player1", "character": "Hyde", "dan": 1, "points": 0},
            {"player_name": "Player2", "character": "Linne", "dan": 1, "points": 2}
        ])
        self.mock_interaction()

        await self.danisen.dan(self.ctx, dan=1)
        self.ctx.interaction.followup.send.assert_called_once()

    async def test_leaderboard(self):
        """Test viewing the leaderboard."""
        self.mock_database_response(fetchall=[
            {"name": "Player1 Hyde", "value": "Dan: 2 Points: 3"},
            {"name": "Player2 Linne", "value": "Dan: 1 Points: 1"}
        ])
        self.mock_interaction()

        await self.danisen.leaderboard(self.ctx)
        self.ctx.interaction.followup.send.assert_called_once()

    async def test_update_max_matches(self):
        """Test updating the maximum number of active matches."""
        max_matches = 5

        await self.danisen.update_max_matches(self.ctx, max_matches)

        self.assertEqual(self.danisen.max_active_matches, 5)
        self.ctx.respond.assert_called_with("Max matches updated to 5")

    async def test_unregister_player_in_match(self):
        """Test unregistering a player who is in an active match."""
        self.ctx.author.name = "TestPlayer"
        char1 = "Hyde"

        self.danisen.in_match["TestPlayer"] = True

        await self.danisen.unregister(self.ctx, char1)

        self.database_cur.execute.assert_not_called()
        self.ctx.respond.assert_called_with("You cannot unregister while in an active match.")

    async def test_join_queue_already_in_queue(self):
        """Test joining the queue when already in the queue."""
        self.ctx.author.name = "TestPlayer"
        char = "Hyde"

        self.danisen.in_queue["TestPlayer"] = [True, deque()]

        await self.danisen.join_queue(self.ctx, char, rejoin_queue=False)

        self.ctx.respond.assert_called_with("You are already in the queue")

    async def test_score_update(self):
        """Test updating the score after a match."""
        self.ctx.guild = MagicMock()
        self.ctx.guild.get_member = MagicMock(return_value=self.ctx.author)
        self.ctx.guild.roles = [MagicMock(name="Dan 1"), MagicMock(name="Dan 2")]

        winner = {"player_name": "Winner", "discord_id": 12345, "dan": 1, "points": 2, "character": "Hyde"}
        loser = {"player_name": "Loser", "discord_id": 67890, "dan": 1, "points": 0, "character": "Linne"}

        winner_rank, loser_rank = await self.danisen.score_update(self.ctx, winner, loser)

        self.assertEqual(winner_rank, [2, 0])
        self.assertEqual(loser_rank, [1, 0])
        self.database_cur.execute.assert_any_call(
            "UPDATE players SET dan = 2, points = 0 WHERE player_name='Winner' AND character='Hyde'"
        )
        self.database_cur.execute.assert_any_call(
            "UPDATE players SET dan = 1, points = 0 WHERE player_name='Loser' AND character='Linne'"
        )

    async def test_set_queue(self):
        """Test enabling and disabling the matchmaking queue."""
        queue_status = False

        await self.danisen.set_queue(self.ctx, queue_status)

        self.assertFalse(self.danisen.queue_status)
        self.ctx.respond.assert_called_with("The matchmaking queue has been disabled")

        queue_status = True

        await self.danisen.set_queue(self.ctx, queue_status)

        self.assertTrue(self.danisen.queue_status)
        self.ctx.respond.assert_called_with("The matchmaking queue has been enabled")

    async def test_matchmake(self):
        """Test matchmaking between players."""
        self.ctx.interaction = AsyncMock()
        player1 = {"player_name": "Player1", "dan": 1, "discord_id": 12345, "character": "Hyde", "points": 0}
        player2 = {"player_name": "Player2", "dan": 1, "discord_id": 67890, "character": "Linne", "points": 0}

        self.danisen.matchmaking_queue.extend([player1, player2])
        self.danisen.dans_in_queue[1].extend([player1, player2])
        self.danisen.in_queue = {
            "Player1": [True, deque()],
            "Player2": [True, deque()]
        }

        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        self.bot.get_channel = MagicMock(return_value=mock_channel)

        await self.danisen.matchmake(self.ctx.interaction)

        self.assertFalse(self.danisen.in_queue["Player1"][0])
        self.assertFalse(self.danisen.in_queue["Player2"][0])
        self.assertTrue(self.danisen.in_match["Player1"])
        self.assertTrue(self.danisen.in_match["Player2"])

        mock_channel.send.assert_called_once()

    async def test_matchmake_dan1_and_dan12(self):
        """Test matchmaking between a dan1 and a dan12 player."""
        self.ctx.interaction = AsyncMock()

        # Player1 (dan1)
        player1 = {
            "player_name": "Player1",
            "discord_id": 12345,
            "character": "Hyde",
            "dan": 1,
            "points": 0
        }
        # Player2 (dan12)
        player2 = {
            "player_name": "Player2",
            "discord_id": 67890,
            "character": "Linne",
            "dan": 12,
            "points": 0
        }

        # Add players to the matchmaking queue and dans_in_queue
        self.danisen.matchmaking_queue.extend([player1, player2])
        self.danisen.dans_in_queue[1].append(player1)
        self.danisen.dans_in_queue[12].append(player2)
        self.danisen.in_queue = {
            "Player1": [True, deque()],
            "Player2": [True, deque()]
        }

        # Mock create_match_interaction
        self.danisen.create_match_interaction = AsyncMock()

        # Run matchmaking
        await self.danisen.matchmake(self.ctx.interaction)

        # Assertions
        self.danisen.create_match_interaction.assert_called_once_with(self.ctx.interaction, player1, player2)
        self.assertFalse(self.danisen.in_queue["Player1"][0])  # Player1 is no longer in queue
        self.assertFalse(self.danisen.in_queue["Player2"][0])  # Player2 is no longer in queue
        self.assertTrue(self.danisen.in_match["Player1"])  # Player1 is in a match
        self.assertTrue(self.danisen.in_match["Player2"])  # Player2 is in a match

    async def test_report_match(self):
        """Test reporting the result of a match."""
        self.ctx.guild = MagicMock()
        self.ctx.guild.get_member = MagicMock(return_value=self.ctx.author)
        self.ctx.guild.roles = [MagicMock(name="Dan 1"), MagicMock(name="Dan 2")]

        self.database_cur.fetchone.side_effect = [
            {"player_name": "Player1", "discord_id": 12345, "dan": 1, "points": 2, "character": "Hyde"},
            {"player_name": "Player2", "discord_id": 67890, "dan": 1, "points": 0, "character": "Linne"},
            None,
            None
        ]

        await self.danisen.report_match(
            self.ctx,
            player1_name="Player1",
            char1="Hyde",
            player2_name="Player2",
            char2="Linne",
            winner="player1"
        )

        self.database_cur.execute.assert_any_call(
            "UPDATE players SET dan = 2, points = 0 WHERE player_name='Player1' AND character='Hyde'"
        )
        self.database_cur.execute.assert_any_call(
            "UPDATE players SET dan = 1, points = 0 WHERE player_name='Player2' AND character='Linne'"
        )
        self.ctx.respond.assert_called_with(
            "Match has been reported as Player1's victory over Player2\n"
            "Player1's Hyde rank is now 2 dan 0 points\n"
            "Player2's Linne rank is now 1 dan 0 points"
        )

    async def test_can_manage_role(self):
        """Test if the bot can manage a specific role."""
        bot_member = MagicMock()
        bot_member.top_role.position = 10
        bot_member.guild_permissions.manage_roles = True

        role = MagicMock()
        role.position = 5

        result = self.danisen.can_manage_role(bot_member, role)

        self.assertTrue(result)

    async def test_update_config(self):
        """Test updating the configuration from the config file."""
        mock_config = {
            "ACTIVE_MATCHES_CHANNEL_ID": 123,
            "REPORTED_MATCHES_CHANNEL_ID": 456,
            "total_dans": 10,
            "minimum_derank": 1,
            "maximum_rank_difference": 2,
            "rank_gap_for_more_points": 1,
            "point_rollover": False,
            "queue_status": False,
            "recent_opponents_limit": 5
        }

        with patch("builtins.open", unittest.mock.mock_open(read_data=json.dumps(mock_config))):
            with patch("os.path.exists", return_value=True):
                self.danisen.update_config()

        self.assertEqual(self.danisen.ACTIVE_MATCHES_CHANNEL_ID, 123)
        self.assertEqual(self.danisen.REPORTED_MATCHES_CHANNEL_ID, 456)
        self.assertEqual(self.danisen.total_dans, 10)
        self.assertEqual(self.danisen.minimum_derank, 1)
        self.assertEqual(self.danisen.maximum_rank_difference, 2)
        self.assertEqual(self.danisen.rank_gap_for_more_points, 1)
        self.assertFalse(self.danisen.point_rollover)
        self.assertFalse(self.danisen.queue_status)
        self.assertEqual(self.danisen.recent_opponents_limit, 5)

    async def test_set_rank(self):
        """Test setting the rank and points for a player."""
        player_name = "TestPlayer"
        char = "Hyde"
        dan = 3
        points = 2

        await self.danisen.set_rank(self.ctx, player_name, char, dan, points)

        self.database_cur.execute.assert_called_with(
            "UPDATE players SET dan = 3, points = 2 WHERE player_name='TestPlayer' AND character='Hyde'"
        )
        self.database_con.commit.assert_called_once()
        self.ctx.respond.assert_called_with("TestPlayer's Hyde rank updated to be dan 3 points 2")

    async def test_can_manage_role_insufficient_permissions(self):
        """Test if the bot cannot manage a role due to insufficient permissions."""
        bot_member = MagicMock()
        bot_member.top_role.position = 5
        bot_member.guild_permissions.manage_roles = False

        role = MagicMock()
        role.position = 10

        result = self.danisen.can_manage_role(bot_member, role)

        self.assertFalse(result)

    async def test_update_config_file_not_found(self):
        """Test behavior when the configuration file does not exist."""
        with patch("os.path.exists", return_value=False):
            self.danisen.update_config()

        self.assertEqual(self.danisen.total_dans, 12)
        self.assertTrue(self.danisen.queue_status)

    async def test_update_config_invalid_json(self):
        """Test behavior when the configuration file contains invalid JSON."""
        with patch("builtins.open", unittest.mock.mock_open(read_data="invalid_json")):
            with patch("os.path.exists", return_value=True):
                self.danisen.update_config()

        self.assertEqual(self.danisen.total_dans, 12)
        self.assertTrue(self.danisen.queue_status)

    async def test_dead_role_role_removal(self):
        """Test if the correct role is returned for removal."""
        self.database_cur.fetchone.return_value = None  # Simulate no remaining players in the dan
        
        mock_role = MagicMock()
        mock_role.name = "Dan 1"
        ctx = MagicMock()
        ctx.guild.roles = [mock_role]

        player = {"discord_id": 12345, "dan": 1}
        role = self.danisen.dead_role(ctx, player)

        self.assertEqual(role.name, "Dan 1")

    async def test_dead_role_no_removal(self):
        """Test if no role is returned when the player is not the last in the dan."""
        self.database_cur.fetchone.return_value = {"discord_id": 12345, "dan": 1}  # Simulate remaining players
        ctx = MagicMock()

        player = {"discord_id": 12345, "dan": 1}
        role = self.danisen.dead_role(ctx, player)

        self.assertIsNone(role)

    async def test_score_update_rankup(self):
        """Test rank-up behavior when a player reaches the required points."""
        self.ctx.guild = MagicMock()
        self.ctx.guild.get_member = MagicMock(return_value=self.ctx.author)
        self.ctx.guild.roles = [MagicMock(name="Dan 1"), MagicMock(name="Dan 2")]

        winner = {"player_name": "Winner", "discord_id": 12345, "dan": 1, "points": 2, "character": "Hyde"}
        loser = {"player_name": "Loser", "discord_id": 67890, "dan": 1, "points": 0, "character": "Linne"}

        winner_rank, loser_rank = await self.danisen.score_update(self.ctx, winner, loser)

        self.assertEqual(winner_rank, [2, 0])  # Winner ranks up to Dan 2
        self.assertEqual(loser_rank, [1, 0])  # Loser remains at Dan 1

    async def test_score_update_rankdown(self):
        """Test rank-down behavior when a player loses enough points."""
        self.ctx.guild = MagicMock()
        self.ctx.guild.get_member = MagicMock(return_value=self.ctx.author)
        self.ctx.guild.roles = [MagicMock(name="Dan 1"), MagicMock(name="Dan 2")]

        winner = {"player_name": "Winner", "discord_id": 12345, "dan": 1, "points": 0, "character": "Hyde"}
        loser = {"player_name": "Loser", "discord_id": 67890, "dan": 2, "points": -3, "character": "Linne"}

        winner_rank, loser_rank = await self.danisen.score_update(self.ctx, winner, loser)

        self.assertEqual(winner_rank, [1, 2])  # Winner gains 2 points due to rank gap
        self.assertEqual(loser_rank, [1, 0])  # Loser ranks down to Dan 1

    async def test_set_rank_invalid_player(self):
        """Test setting rank for a player who does not exist."""
        self.database_cur.execute.return_value = None  # Simulate no matching player

        await self.danisen.set_rank(self.ctx, "NonExistentPlayer", "Hyde", 3, 2)

        self.ctx.respond.assert_called_with("NonExistentPlayer's Hyde rank updated to be dan 3 points 2")

    async def test_join_queue_queue_closed(self):
        """Test joining the queue when the queue is closed."""
        self.danisen.queue_status = False  # Close the queue

        await self.danisen.join_queue(self.ctx, "Hyde", rejoin_queue=False)

        self.ctx.respond.assert_called_with("The matchmaking queue is currently closed")

    async def test_view_queue_empty(self):
        """Test viewing the queue when it is empty."""
        self.danisen.matchmaking_queue.clear()
        self.danisen.dans_in_queue = {dan: deque() for dan in range(1, self.danisen.total_dans + 1)}

        await self.danisen.view_queue(self.ctx)

        expected_mmq = repr(self.danisen.matchmaking_queue)
        expected_danq = repr(self.danisen.dans_in_queue)
        self.ctx.respond.assert_called_with(f"Current full MMQ {expected_mmq}\nCurrent full DanQ {expected_danq}")

    async def test_matchmake_insufficient_players(self):
        """Test matchmaking when there are fewer than two players in the queue."""
        self.danisen.matchmaking_queue.append({"player_name": "Player1", "dan": 1})

        await self.danisen.matchmake(self.ctx.interaction)

        self.assertEqual(len(self.danisen.matchmaking_queue), 1)

    async def test_report_match_invalid_player(self):
        """Test reporting a match when one or both players do not exist."""
        self.database_cur.fetchone.side_effect = [None, None]  # Simulate no players found

        await self.danisen.report_match(
            self.ctx,
            player1_name="NonExistentPlayer1",
            char1="Hyde",
            player2_name="NonExistentPlayer2",
            char2="Linne",
            winner="player1"
        )

        self.ctx.respond.assert_called_with("No player named NonExistentPlayer1 with character Hyde")

    async def test_rank(self):
        """Test retrieving a player's rank for a specific character."""
        self.ctx.author.id = 12345
        self.ctx.author.name = "TestPlayer"
        char = "Hyde"

        mock_member = MagicMock()
        mock_member.name = "TestPlayer"
        mock_member.id = 12345
        self.ctx.guild.members = [mock_member]

        self.mock_database_response(fetchone={"player_name": "TestPlayer", "dan": 2, "points": 3, "character": "Hyde"})

        await self.danisen.rank(self.ctx, char, discord_name="TestPlayer")

        self.ctx.respond.assert_called_with("TestPlayer's rank for Hyde is 2 dan 3 points")

    async def test_rejoin_queue(self):
        """Test rejoining the matchmaking queue."""
        player = {"discord_id": 12345, "player_name": "TestPlayer", "dan": 1, "character": "Hyde"}

        self.mock_database_response(fetchone={"discord_id": 12345, "player_name": "TestPlayer", "dan": 1, "character": "Hyde", "points": 0})

        self.danisen.rejoin_queue(player)

        self.assertTrue(self.danisen.in_queue["TestPlayer"][0])
        self.assertEqual(self.danisen.dans_in_queue[1][0]['player_name'], "TestPlayer")
        self.assertEqual(self.danisen.matchmaking_queue[0]['player_name'], "TestPlayer")

    async def test_report_match_queue(self):
        """Test reporting a match result from the queue."""
        self.ctx.guild = MagicMock()
        self.ctx.guild.get_member = MagicMock(return_value=self.ctx.author)
        self.ctx.guild.roles = [MagicMock(name="Dan 1"), MagicMock(name="Dan 2")]

        player1 = {"player_name": "Player1", "discord_id": 12345, "dan": 1, "points": 2, "character": "Hyde"}
        player2 = {"player_name": "Player2", "discord_id": 67890, "dan": 1, "points": 0, "character": "Linne"}

        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()
        self.bot.get_channel = MagicMock(return_value=mock_channel)

        await self.danisen.report_match_queue(self.ctx, player1, player2, winner="player1")

        self.database_cur.execute.assert_any_call(
            "UPDATE players SET dan = 2, points = 0 WHERE player_name='Player1' AND character='Hyde'"
        )
        self.database_cur.execute.assert_any_call(
            "UPDATE players SET dan = 1, points = 0 WHERE player_name='Player2' AND character='Linne'"
        )
        mock_channel.send.assert_called_once_with(
            "Match has been reported as Player1's victory over Player2\n"
            "Player1's Hyde rank is now 2 dan 0 points\n"
            "Player2's Linne rank is now 1 dan 0 points"
        )

    async def test_danisen_stats(self):
        """Test viewing various statistics about the Danisen system."""
        self.database_cur.execute.side_effect = [
            MagicMock(fetchall=MagicMock(return_value=[
                {"name": "Hyde", "value": 5},
                {"name": "Linne", "value": 3}
            ])),
            MagicMock(fetchall=MagicMock(return_value=[
                {"name": 1, "value": 4},
                {"name": 2, "value": 4}
            ]))
        ]
        self.mock_interaction()

        await self.danisen.danisen_stats(self.ctx)

        self.ctx.interaction.followup.send.assert_called_once()
        
if __name__ == "__main__":
    unittest.main()
