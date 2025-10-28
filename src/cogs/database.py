import sqlite3

class DanisenRow(dict):
    def __repr__(self):
        return self.__getitem__('player_name') + "@" + self.__getitem__('character')
    def __str__(self):
        return self.__getitem__('player_name') + "@" + self.__getitem__('character')

def insert_new_player(player_tuple, db):
    res = True
    try:
        db.execute("INSERT INTO players VALUES " + str(player_tuple))
    except sqlite3.IntegrityError:
        res = sqlite3.IntegrityError
        print("Attempted inserting duplicate data (discord_id, character) pair already exists")
    return res