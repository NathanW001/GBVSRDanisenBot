import unittest
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
        # Mock bot, database, and config path
        self.bot = MagicMock()
        self.database = MagicMock()
        self.database_cur = MagicMock()  # Mock the database cursor
        self.database.cursor.return_value = self.database_cur  # Mock cursor return
        self.config_path = "config.json"

        # Initialize the Danisen cog
        self.danisen = Danisen(self.bot, self.database, self.config_path)

        # Mock database cursor methods
        self.database_cur.execute = MagicMock(return_value=self.database_cur)  # Ensure execute returns self.database_cur
        self.database_cur.fetchone = MagicMock()
        self.database_cur.fetchall = MagicMock()

        # Mock ctx and ctx.author
        self.ctx = MagicMock()
        self.ctx.author = MagicMock()
        self.ctx.author.add_roles = AsyncMock()  # Use AsyncMock for add_roles
        self.ctx.author.remove_roles = AsyncMock()  # Use AsyncMock for remove_roles
        self.ctx.respond = AsyncMock()  # Use AsyncMock for ctx.respond
        self.ctx.defer = AsyncMock()  # Use AsyncMock for ctx.defer

    async def test_register_new_player(self):
        # Mock context and inputs
        self.ctx.author.id = 12345
        self.ctx.author.name = "TestPlayer"
        char1 = "Hyde"

        # Simulate no existing record in the database
        self.database_cur.fetchone.return_value = None

        # Call the function
        await self.danisen.register(self.ctx, char1)

        # Verify database insertion
        self.database_cur.execute.assert_called_with(
            "INSERT INTO players (discord_id, player_name, character, dan, points) VALUES (?, ?, ?, ?, ?)",
            (12345, "TestPlayer", "Hyde", 1, 0)
        )
        self.ctx.respond.assert_called_with(
            "You are now registered as TestPlayer with the following character/s Hyde\n"
            "If you wish to add more characters, you can register multiple times!\n\n"
            "Welcome to the Danisen!"
        )

    async def test_register_existing_player(self):
        # Mock context and inputs
        self.ctx.author.id = 12345
        self.ctx.author.name = "TestPlayer"
        char1 = "Hyde"

        # Simulate existing record in the database
        self.database_cur.fetchone.return_value = {"discord_id": 12345, "character": "Hyde",  "dan": 1, "points": 0}

        # Call the function
        await self.danisen.register(self.ctx, char1)

        # Verify the SELECT query was executed
        self.database_cur.execute.assert_any_call(
            "SELECT * FROM players WHERE discord_id = ? AND character = ?",
            (12345, "Hyde")
        )

        # Verify the INSERT query was not executed
        calls = [
            call[0] for call in self.database_cur.execute.call_args_list
        ]
        self.assertNotIn(
            "INSERT INTO players (discord_id, player_name, character, dan, points) VALUES (?, ?, ?, ?, ?)",
            calls
        )

        # Verify the correct response was sent
        self.ctx.respond.assert_called_with("You are already registered with the character Hyde.")

    async def test_unregister_player_not_in_queue_or_match(self):
        # Mock context and inputs
        self.ctx.author.id = 12345
        self.ctx.author.name = "TestPlayer"
        char1 = "Hyde"

        # Simulate player in database with required keys
        self.database_cur.fetchone.side_effect = [
            {"discord_id": 12345, "character": "Hyde", "dan": 1, "points": 0},  # First fetchone for the player
            None  # Second fetchone for the dead_role check
        ]

        # Call the function
        await self.danisen.unregister(self.ctx, char1)

        # Verify the SELECT query for dead_role
        self.database_cur.execute.assert_any_call(
            "SELECT * FROM players WHERE discord_id=12345 AND dan=1"
        )

        # Verify the DELETE query
        self.database_cur.execute.assert_any_call(
            "DELETE FROM players WHERE discord_id=12345 AND character='Hyde'"
        )

        # Verify the correct response was sent
        self.ctx.respond.assert_called_with("You have now unregistered Hyde")

    async def test_unregister_player_in_match(self):
        # Mock context and inputs
        self.ctx.author.name = "TestPlayer"
        char1 = "Hyde"

        # Simulate player in an active match
        self.danisen.in_match["TestPlayer"] = True

        # Call the function
        await self.danisen.unregister(self.ctx, char1)

        # Verify no database deletion
        self.database_cur.execute.assert_not_called()
        self.ctx.respond.assert_called_with("You cannot unregister while in an active match.")

    async def test_join_queue(self):
        # Mock context and inputs
        self.ctx.author.id = 12345
        self.ctx.author.name = "TestPlayer"
        char = "Hyde"
        rejoin_queue = False

        # Simulate player in database
        self.database_cur.fetchone.return_value = {"discord_id": 12345, "character": "Hyde", "dan": 1, "points": 0}

        # Call the function
        await self.danisen.join_queue(self.ctx, char, rejoin_queue)

        # Verify player added to queue
        self.assertIn("TestPlayer", self.danisen.in_queue)
        self.ctx.respond.assert_called_with("You've been added to the matchmaking queue with Hyde")

    async def test_join_queue_already_in_queue(self):
        # Mock context and inputs
        self.ctx.author.name = "TestPlayer"
        char = "Hyde"
        rejoin_queue = False

        # Simulate player already in queue
        self.danisen.in_queue["TestPlayer"] = [True, deque()]

        # Call the function
        await self.danisen.join_queue(self.ctx, char, rejoin_queue)

        # Verify no duplicate addition
        self.ctx.respond.assert_called_with("You are already in the queue")

    async def test_leave_queue(self):
        # Mock context and inputs
        self.ctx.author.name = "TestPlayer"
        self.danisen.matchmaking_queue.append({"player_name": "TestPlayer", "dan": 1})
        self.danisen.dans_in_queue[1].append({"player_name": "TestPlayer", "dan": 1})
        self.danisen.in_queue["TestPlayer"] = [True, deque()]

        # Call the function
        await self.danisen.leave_queue(self.ctx)

        # Verify player is still in the dictionary but marked as not in queue
        self.assertIn("TestPlayer", self.danisen.in_queue)
        self.assertFalse(self.danisen.in_queue["TestPlayer"][0])  # Ensure in_queue status is False
        self.ctx.respond.assert_called_with("You have been removed from the queue")

    async def test_score_update(self):
        # Mock context and inputs
        self.ctx.guild = MagicMock()
        self.ctx.guild.get_member = MagicMock(return_value=self.ctx.author)
        self.ctx.guild.roles = [MagicMock(name="Dan 1"), MagicMock(name="Dan 2")]

        winner = {"player_name": "Winner", "discord_id": 12345, "dan": 1, "points": 2, "character": "Hyde"}
        loser = {"player_name": "Loser", "discord_id": 67890, "dan": 1, "points": 0, "character": "Linne"}

        # Call the function
        winner_rank, loser_rank = await self.danisen.score_update(self.ctx, winner, loser)

        # Verify rank and points update
        self.assertEqual(winner_rank, [2, 0])  # Winner ranks up to Dan 2
        self.assertEqual(loser_rank, [1, 0])  # Loser remains at Dan 1 with 0 points

        # Verify database updates
        self.database_cur.execute.assert_any_call(
            "UPDATE players SET dan = 2, points = 0 WHERE player_name='Winner' AND character='Hyde'"
        )
        self.database_cur.execute.assert_any_call(
            "UPDATE players SET dan = 1, points = 0 WHERE player_name='Loser' AND character='Linne'"
        )

    async def test_set_queue(self):
        # Mock context and inputs
        queue_status = False

        # Call the function
        await self.danisen.set_queue(self.ctx, queue_status)

        # Verify queue status and response
        self.assertFalse(self.danisen.queue_status)
        self.ctx.respond.assert_called_with("The matchmaking queue has been disabled")

        # Test enabling the queue
        queue_status = True
        await self.danisen.set_queue(self.ctx, queue_status)
        self.assertTrue(self.danisen.queue_status)
        self.ctx.respond.assert_called_with("The matchmaking queue has been enabled")

    async def test_matchmake(self):
        # Mock context and inputs
        self.ctx.interaction = MagicMock()
        player1 = {"player_name": "Player1", "dan": 1, "discord_id": 12345, "character": "Hyde", "points": 0}
        player2 = {"player_name": "Player2", "dan": 1, "discord_id": 67890, "character": "Linne", "points": 0}

        # Populate matchmaking queue and dans_in_queue
        self.danisen.matchmaking_queue.extend([player1, player2])
        self.danisen.dans_in_queue[1].extend([player1, player2])
        self.danisen.in_queue = {
            "Player1": [True, deque()],
            "Player2": [True, deque()]
        }

        # Mock the channel and its send method
        mock_channel = MagicMock()
        mock_channel.send = AsyncMock()  # Use AsyncMock for send
        self.bot.get_channel = MagicMock(return_value=mock_channel)

        # Call the function
        await self.danisen.matchmake(self.ctx.interaction)

        # Verify players are matched and removed from the queue
        self.assertFalse(self.danisen.in_queue["Player1"][0])
        self.assertFalse(self.danisen.in_queue["Player2"][0])
        self.assertTrue(self.danisen.in_match["Player1"])
        self.assertTrue(self.danisen.in_match["Player2"])

        # Verify the match interaction message was sent
        mock_channel.send.assert_called_once()

    async def test_report_match(self):
        # Mock context and inputs
        self.ctx.guild = MagicMock()
        self.ctx.guild.get_member = MagicMock(return_value=self.ctx.author)
        self.ctx.guild.roles = [MagicMock(name="Dan 1"), MagicMock(name="Dan 2")]

        # Mock database responses for fetchone
        self.database_cur.fetchone.side_effect = [
            {"player_name": "Player1", "discord_id": 12345, "dan": 1, "points": 2, "character": "Hyde"},  # Player1 data
            {"player_name": "Player2", "discord_id": 67890, "dan": 1, "points": 0, "character": "Linne"},  # Player2 data
            None,  # For dead_role check on winner
            None   # For dead_role check on loser
        ]

        # Call the function
        await self.danisen.report_match(
            self.ctx,
            player1_name="Player1",
            char1="Hyde",
            player2_name="Player2",
            char2="Linne",
            winner="player1"
        )

        # Verify database updates
        self.database_cur.execute.assert_any_call(
            "UPDATE players SET dan = 2, points = 0 WHERE player_name='Player1' AND character='Hyde'"
        )
        self.database_cur.execute.assert_any_call(
            "UPDATE players SET dan = 1, points = 0 WHERE player_name='Player2' AND character='Linne'"
        )

        # Verify response
        self.ctx.respond.assert_called_with(
            "Match has been reported as Player1's victory over Player2\n"
            "Player1's Hyde rank is now 2 dan 0 points\n"
            "Player2's Linne rank is now 1 dan 0 points"
        )

if __name__ == "__main__":
    unittest.main()
