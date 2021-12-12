import sqlite3
import logging
import traceback
import time

from enum import Enum


class Wakeword(Enum):
    Здравствуйте = 0


class TableAlreadyExistsException(Exception):
    pass

class BadgeNotFoundException(Exception):
    pass

def retriable_query(function):
    def wrapper(*args, **kwargs):
        while True:
            try:
                return function(*args, **kwargs)
                break
            except sqlite3.OperationalError as e:
                if e.args[0].find("database is locked") == -1:
                    traceback.print_exc()
                    raise e

    return wrapper


class BadgesDB():
    def __init__(self, db_file="tables.db"):
        try:
            self.conn = sqlite3.connect(db_file)
            self.conn.execute("PRAGMA foreign_keys = 1")
            self.cursor = self.conn.cursor()
            logging.info("Successfully connected to the database!")
        except Exception as e:
            tb_str = traceback.format_exc()
            logging.critical(f"{e.__class__} occurred while connecting to the database, traceback:")
            logging.critical(tb_str)
            logging.critical("Terminating...")
            raise e


    def init_db(self,force_recreate=False):
        logging.info("Initializing tables...")
        if force_recreate:
            logging.info("force flag is on, tables are gonna be recreated")
            self._drop_tables()
        self._create_tables()
        logging.info("Done")

    @retriable_query
    def _drop_tables(self):
        with open("drop_queries.sql", "r") as f:
            drop_queries_text = "".join(l[:-1] for l in f.readlines())
        drop_queries = drop_queries_text.split(";")

        for drop_query in drop_queries:
            self.cursor.execute(drop_query)

    @retriable_query
    def _create_tables(self):
        with open("create_queries.sql", "r") as f:
            queries_text = "".join(l[:-1] for l in f.readlines())
        queries = queries_text.split(";")
        for query in queries:
            self.cursor.execute(query)
        for w in Wakeword:
            self.cursor.execute("INSERT OR IGNORE INTO Wakewords VALUES (?,?)", (w.value, w.name))
            self.conn.commit()
            logging.info(f"Added '{w.name}' wakeword to the table")

    @retriable_query
    def register_badge(self, badge_id: str):
        self.cursor.execute("INSERT INTO Badges VALUES (?,?,0,0)", (badge_id, int(time.time())))
        self.conn.commit()
        logging.debug(f"Registered new badge '{badge_id}' to the database")

    @retriable_query
    def register_activation(self, badge_id: str, wakeword: Wakeword, duration: float):
        self.cursor.execute("INSERT INTO Activations VALUES (?,?,?,?)",
                            (badge_id, int(time.time()), wakeword.value, duration))
        self.conn.commit()
        logging.debug(
            f"Registered an activation on badge {badge_id}, wakeword: {eval(f'Wakeword.{wakeword}')}, duration of speech {duration}")

    @retriable_query
    def enable_badge(self, badge_id: str):
        badge_exists = self.cursor.execute("SELECT BadgeID FROM Badges WHERE BadgeID = ?",(badge_id,)).fetchall()
        if badge_exists:
            self.cursor.execute("UPDATE Badges SET Enabled = 1 WHERE BadgeID = ?", (badge_id,))
            self.conn.commit()
        else:
            raise BadgeNotFoundException(f"Badge {badge_id} does not exist")

    @retriable_query
    def disable_badge(self, badge_id: str):
        self.cursor.execute("UPDATE Badges SET Enabled = 0 WHERE BadgeID = ?", (badge_id,))
        self.conn.commit()
        logging.debug(f"Registered disabled state on badge {badge_id} in the database")
