This bot uses Pycord and not Discord.py to clarify (these packages have the same name but have slightly different functionality)
(https://docs.pycord.dev/en/stable/index.html)

(Note if you already have discord.py installed you will need to uninstall it in order for pycord to work)

# DanisenBot setup
In order to make the bot functional for yourself you need to add your bot token to the bot.cfg file

where you replace "DISCORD_BOT_TOKEN_HERE" with your respective token in order to host the bot.

(I will potentially be adding functionality for daniel to run on other servers but this is TBD)


Also need to replace ACTIVE_MATCHES_CHANNEL_ID inside danisen.py with the respective discord channel id you want match interactions to show up in (this will be a message from the bot when a match is made between 2 players)

# Running the bot

Enter the following command into your terminal

python bot.py

# Notes

Regarding matchmaking, the matchmaking queue will attempt to match players closest in dan, while also not matching them with the same person they previously played

And for point gains we have that if there  is a 2 dan or larger gap (e.g dan 1 vs dan 3) if the higher dan player wins, no points are gained/lost, but if the lower dan wins everything works as normal (this is in order to discourage farming low ranks while also not discouraging lower ranked players from playing against higher ranked players)
