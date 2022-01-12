import psycopg2
import logging
import traceback
import datetime
import os

from enum import Enum

from config import Config

class Wakeword(Enum):
    Здравствуйте = 0


class TableAlreadyExistsException(Exception):
    pass

class BadgeNotFoundException(Exception):
    pass

class BadgeAlreadyEnabled(Exception):
    pass

class BadgeAlreadyDisabled(Exception):
    pass

# def retriable_query(function):
#     def wrapper(*args, **kwargs):
#         while True:
#             try:
#                 return function(*args, **kwargs)
#                 break
#             except sqlite3.OperationalError as e:
#                 if e.args[0].find("database is locked") == -1:
#                     traceback.print_exc()
#                     raise e
#
#     return wrapper

db = None

class Singleton(object):
    _instance = None
    def __new__(class_, *args, **kwargs):
        if not isinstance(class_._instance, class_):
            class_._instance = object.__new__(class_)
        return class_._instance

class BadgesDB(Singleton):
    _instance = None

    def __init__(self, user:str,password:str, host:str, port:int):
        try:
            self.conn = psycopg2.connect(dbname="vad",user=user,password=password,host=host,port=port)
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


    def _drop_tables(self):
        with open("drop_queries.sql", "r") as f:
            drop_queries_text = "".join(l[:-1] for l in f.readlines())
        drop_queries = drop_queries_text.split(";")

        for drop_query in drop_queries:
            self.cursor.execute(drop_query)


    def _create_tables(self):
        with open("create_queries.sql", "r") as f:
            queries_text = "".join(l[:-1] for l in f.readlines())
        queries = queries_text.split(";")
        for query in queries:
            self.cursor.execute(query)
        for w in Wakeword:
            self.cursor.execute("INSERT INTO Wakewords VALUES (%s,%s) ON CONFLICT (ID) DO NOTHING", (w.value, w.name))
            self.conn.commit()
            logging.info(f"Added '{w.name}' wakeword to the table")


    def register_badge(self, badge_id: str):
        self.cursor.execute("INSERT INTO Badges VALUES (%s,%s,0,FALSE)", (badge_id, datetime.datetime.now()))
        self.conn.commit()
        logging.debug(f"Registered new badge '{badge_id}' to the database")


    def register_activation(self, badge_id: str, wakeword: Wakeword, duration: float):
        self.cursor.execute("INSERT INTO Activations VALUES (%s,%s,%s,%s)",
                            (badge_id, datetime.datetime.now(), wakeword.value, duration))
        self.conn.commit()



    def enable_badge(self, badge_id: str):
        if self.badge_exists(badge_id):
            if not self.badge_enabled(badge_id):
                self.cursor.execute("UPDATE Badges SET Enabled = TRUE WHERE BadgeID = %s", (badge_id,))
                self.conn.commit()
            else:
                raise BadgeAlreadyEnabled(f"Badge {badge_id} already enabled!")
        else:
            raise BadgeNotFoundException(f"Badge {badge_id} does not exist")


    def disable_badge(self, badge_id: str):
        if self.badge_exists(badge_id):
            if self.badge_enabled(badge_id):
                self.cursor.execute("UPDATE Badges SET Enabled = FALSE WHERE BadgeID = %s", (badge_id,))
                self.conn.commit()
            else:
                raise BadgeAlreadyDisabled(f"Badge {badge_id} already disabled!")
        else:
            raise BadgeNotFoundException(f"Badge {badge_id} does not exist")


    def badge_enabled(self,badge_id: str):
        if self.badge_exists(badge_id):
            self.cursor.execute("SELECT Enabled FROM Badges WHERE BadgeID = %s",(badge_id,))
            res = self.cursor.fetchone()
            return res[0]
        else:
            raise BadgeNotFoundException(f"Badge {badge_id} does not exist")


    def badge_exists(self, badge_id: str):
        self.cursor.execute("SELECT BadgeID FROM Badges WHERE BadgeID = %s",(badge_id,))
        badge_exists = self.cursor.fetchall()
        if badge_exists:
            return True
        else:
            return False


    def get_active_badges(self):
        self.cursor.execute("SELECT BadgeID FROM Badges WHERE Enabled = TRUE")
        res = self.cursor.fetchall()
        return [x[0] for x in res]


    def __del__(self):
        self.conn.close()

def init_db(config: Config):
    user = os.environ.get("DB_USER")
    password = os.environ.get("DB_PASS")
    if user and password:
        db = BadgesDB(user,password,config.db_host,config.db_port)
        db.init_db()
        return db
    raise ValueError("Something went wrong with loading database credentials...")