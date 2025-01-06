This bot uses Pycord and not Discord.py to clarify (these packages have the same name but have slightly different functionality)
(https://docs.pycord.dev/en/stable/index.html)

(Note if you already have discord.py installed you will need to uninstall it in order for pycord to work)

# Installation
git clone https://github.com/dlotfi2/DanisenBot


# DanisenBot setup
In order to make the bot functional for yourself you need to add your bot token and ACTIVE_MATCHES_CHANNEL_ID to the config.json file

This can be done in the gui, or by editing the file manually

# Running the bot

Enter the following command into your terminal

python gui.py

# Notes

Regarding matchmaking, the matchmaking queue will attempt to match players closest in dan, while also not matching them with the same person they previously played

And for point gains we have that if there  is a 2 dan or larger gap (e.g dan 1 vs dan 3) if the higher dan player wins, no points are gained/lost, but if the lower dan wins everything works as normal (this is in order to discourage farming low ranks while also not discouraging lower ranked players from playing against higher ranked players)


There is a maximum amount of matches that the bot makes concurrently (default is set to 3)
you can update this amount using the /update_max_matches command

The queue can be closed/opened using 
