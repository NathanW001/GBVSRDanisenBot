import sqlite3
import pandas
import math

class DanisenRow(dict):
    def __repr__(self):
        return self.__getitem__('player_name')
    def __str__(self):
        return self.__getitem__('player_name')

def insert_new_player(player_tuple, db):
    res = True
    try:
        db.execute("INSERT INTO players VALUES " + str(player_tuple))
    except sqlite3.IntegrityError:
        res = sqlite3.IntegrityError
        print("Attempted inserting duplicate data (discord_id, character) pair already exists")
    return res

def sheetdata_to_db(line, db):
    data = [line["Discord Id"], line["Player Name"], line["Character 1"], 1, 0]
    insert_new_player(tuple(data), db)
    if not pandas.isna(line["Character 2"]):
        data[2] = line["Character 2"]
        insert_new_player(tuple(data), db)
    if not pandas.isna(line["Character 3"]):
        data[2] = line["Character 3"]
        insert_new_player(tuple(data), db)