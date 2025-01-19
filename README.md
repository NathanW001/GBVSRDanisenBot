This bot uses Pycord and not Discord.py to clarify (these packages have the same name but have slightly different functionality)
(https://docs.pycord.dev/en/stable/index.html)

(Note if you already have discord.py installed you will need to uninstall it in order for pycord to work)

# RUNNING BOT THROUGH PY FILE
# Installation
git clone https://github.com/dlotfi2/DanisenBot

# DanisenBot setup
In order to make the bot functional for yourself you need to add your bot token and ACTIVE_MATCHES_CHANNEL_ID to the config.json file

This can be done in the gui, or by editing the file manually

# Running the bot

Enter the following command into your terminal

python gui.py


# RUNNING THROUGH GUI
Basic functional release of the bot as an exe,


First Create Your Bot:
- Create a Bot using the discord dev portal https://discord.com/developers/applications
- Save your bot token somewhere
- Invite your bot to your server with the following permissions
![firefox_HsUjlQfpO2](https://github.com/user-attachments/assets/de93b627-a109-4361-b528-cc26361ad703)
![firefox_DAfBkhvL0G](https://github.com/user-attachments/assets/0eede925-cf92-4458-bf8c-c340721d4948)
![firefox_8JicCP8Vkp](https://github.com/user-attachments/assets/1c1a694d-5f50-42d0-a04d-e36e827bdb4a)
![firefox_XQiyPiNnCw](https://github.com/user-attachments/assets/bb1c6779-dc93-42c9-800b-583ce16ce298)

Pick a channel id in your server where you want the bot to post messages
![Discord_1uMsu0beLJ](https://github.com/user-attachments/assets/3bed0f6a-97ae-48e6-8a8c-dcddd648eda7)

Running the bot:
- Place DanisenBot.exe inside its own folder
- Run the exe file
- Go to the Config Tab and put in the relevant fields (DISCORD BOT TOKEN AND CHANNEL ID!!!) (VERY IMPORTANT)
- Save the configuration

After you've done the above you can press the start button!


# Notes


Regarding matchmaking, the matchmaking queue will attempt to match players closest in dan, while also not matching them with the same person they previously played

And for point gains we have that if there  is a 2 dan or larger gap (e.g dan 1 vs dan 3) if the higher dan player wins, no points are gained/lost, but if the lower dan wins everything works as normal (this is in order to discourage farming low ranks while also not discouraging lower ranked players from playing against higher ranked players)


There is a maximum amount of matches that the bot makes concurrently (default is set to 3)
you can update this amount using the /update_max_matches command

The queue can be closed/opened using the relevant bot commands


The bot supports having dan roles/character roles just ensure that the bots role is higher than either of the 2
