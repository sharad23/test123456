from __future__ import absolute_import
from itertools import izip_longest
import sys
import time
import psycopg2
# from dejavu.database import Database
from .database import Database

class PGSQLDatabase(Database):
    """
    Queries:

    1) Find duplicates (shouldn't be any, though):

        select `hash`, `song_id`, `offset`, count(*) cnt
        from fingerprints
        group by `hash`, `song_id`, `offset`
        having cnt > 1
        order by cnt asc;

    2) Get number of hashes by song:

        select song_id, song_name, count(song_id) as num
        from fingerprints
        natural join songs
        group by song_id
        order by count(song_id) desc;

    3) get hashes with highest number of collisions

        select
            hash,
            count(distinct song_id) as n
        from fingerprints
        group by `hash`
        order by n DESC;

    => 26 different songs with same fingerprint (392 times):

        select songs.song_name, fingerprints.offset
        from fingerprints natural join songs
        where fingerprints.hash = "08d3c833b71c60a7b620322ac0c0aba7bf5a3e73";
    """

    type = "pgsql"

    # tables
    FINGERPRINTS_TABLENAME = "fingerprints"
    SONGS_TABLENAME = "songs"
    MATCHES_TABLENAME = "matches"


    # fields
    FIELD_FINGERPRINTED = "fingerprinted"

    # creates
    CREATE_FINGERPRINTS_TABLE = """
       CREATE TABLE IF NOT EXISTS %s (
             %s bytea not null,
             %s int not null,
             %s int not null
       );
       """ % (
        FINGERPRINTS_TABLENAME, Database.FIELD_HASH,
        Database.FIELD_SONG_ID, Database.FIELD_OFFSET

    )
    CREATE_INDEX_FINGERPRINTS = """
         CREATE INDEX fingerprint_index
         ON %s (%s);
        """ % (
        FINGERPRINTS_TABLENAME, Database.FIELD_HASH
    )

    CREATE_FINGERPRINTS_RULE = """
       CREATE OR REPLACE RULE ignore_duplicate_inserts AS
       ON INSERT TO %s
       WHERE (EXISTS ( SELECT *
               FROM %s
              WHERE %s.%s = NEW.%s and %s.%s = NEW.%s and %s.%s = NEW.%s )) DO INSTEAD NOTHING;
        """ % (
        FINGERPRINTS_TABLENAME, FINGERPRINTS_TABLENAME, FINGERPRINTS_TABLENAME, Database.FIELD_HASH,
        Database.FIELD_HASH,
        FINGERPRINTS_TABLENAME, Database.FIELD_SONG_ID, Database.FIELD_SONG_ID,
        FINGERPRINTS_TABLENAME, Database.FIELD_OFFSET, Database.FIELD_OFFSET
    )

    CREATE_SONGS_TABLE = """

        CREATE TABLE IF NOT EXISTS %s (
            %s serial not null,
            %s varchar(250) not null,
            %s varchar(250),
            %s smallint default 0,
            %s bytea not null,
        PRIMARY KEY (%s)
    );""" % (
        SONGS_TABLENAME, Database.FIELD_SONG_ID, Database.FIELD_SONGNAME, Database.FIELD_DURATION, FIELD_FINGERPRINTED,
        Database.FIELD_FILE_SHA1,
        Database.FIELD_SONG_ID
    )

    CREATE_MATCHES_TABLE = """

        CREATE TABLE IF NOT EXISTS %s (
            %s serial not null,
            %s int,
            %s varchar(250),
            %s varchar(250),
            %s varchar(250),
            %s varchar(250),
         PRIMARY KEY (%s)
        );""" % (
        MATCHES_TABLENAME, Database.FIELD_MATCHES_ID, Database.FIELD_SONG_ID, Database.FIELD_DURATION,
        Database.FIELD_REAL_TIME, Database.FIELD_FROM_SONG_TIME, Database.FIELD_TO_SONG_TIME,
        Database.FIELD_MATCHES_ID
    )
    # inserts (ignores duplicates)
    INSERT_FINGERPRINT = """
        INSERT INTO %s (%s, %s, %s) values
        (decode(%%s,'hex'), %%s, %%s)
        """ % (FINGERPRINTS_TABLENAME, Database.FIELD_HASH, Database.FIELD_SONG_ID, Database.FIELD_OFFSET)

    INSERT_SONG = "INSERT INTO %s (%s, %s, %s) values (%%s, decode(%%s,'hex'),%%s) RETURNING song_id;" % (
        SONGS_TABLENAME, Database.FIELD_SONGNAME, Database.FIELD_FILE_SHA1, Database.FIELD_DURATION)

    INSERT_MATCHES = "INSERT INTO %s (%s, %s, %s, %s, %s) values (%%s, %%s ,%%s, %%s, %%s);" % (
        MATCHES_TABLENAME, Database.FIELD_SONG_ID, Database.FIELD_DURATION, Database.FIELD_REAL_TIME,
        Database.FIELD_FROM_SONG_TIME, Database.FIELD_TO_SONG_TIME)

    # selects
    SELECT = """
        SELECT %s, %s FROM %s WHERE %s = decode(%%s,'hex');
    """ % (Database.FIELD_SONG_ID, Database.FIELD_OFFSET, FINGERPRINTS_TABLENAME, Database.FIELD_HASH)

    SELECT_MULTIPLE = """
        SELECT encode(%s,'hex'), %s, %s FROM %s WHERE %s IN (%%s);
    """ % (Database.FIELD_HASH, Database.FIELD_SONG_ID, Database.FIELD_OFFSET,
           FINGERPRINTS_TABLENAME, Database.FIELD_HASH)

    SELECT_ALL = """
        SELECT %s, %s FROM %s;
    """ % (Database.FIELD_SONG_ID, Database.FIELD_OFFSET, FINGERPRINTS_TABLENAME)

    SELECT_SONG = """
        SELECT %s, encode(%s,'hex') as %s FROM %s WHERE %s = %%s;
    """ % (Database.FIELD_SONGNAME, Database.FIELD_FILE_SHA1, Database.FIELD_FILE_SHA1, SONGS_TABLENAME, Database.FIELD_SONG_ID)

    SELECT_NUM_FINGERPRINTS = """
        SELECT COUNT(*) as n FROM %s
    """ % (FINGERPRINTS_TABLENAME)

    SELECT_UNIQUE_SONG_IDS = """
        SELECT COUNT(DISTINCT %s) as n FROM %s WHERE %s = 1;
    """ % (Database.FIELD_SONG_ID, SONGS_TABLENAME, FIELD_FINGERPRINTED)

    SELECT_SONGS = """
        SELECT %s, %s, encode(%s,'hex') as %s FROM %s WHERE %s = 1;
    """ % (Database.FIELD_SONG_ID, Database.FIELD_SONGNAME, Database.FIELD_FILE_SHA1, Database.FIELD_FILE_SHA1,
           SONGS_TABLENAME, FIELD_FINGERPRINTED)

    # drops

    DROP_FINGERPRINTS_INDEX = "DROP INDEX fingerprint_index;"
    DROP_FINGERPRINTS = "DROP TABLE IF EXISTS %s;" % FINGERPRINTS_TABLENAME
    DROP_SONGS = " DROP TABLE IF EXISTS %s;" % SONGS_TABLENAME
    DROP_MATCHES_TABLE = "DROP TABLE IF EXISTS %s;" % MATCHES_TABLENAME
    DROP_FINGERPRINTS_RULE = "DROP RULE ignore_duplicate_inserts ON %s;" % FINGERPRINTS_TABLENAME

    # update
    UPDATE_SONG_FINGERPRINTED = """
        UPDATE %s SET %s = 1 WHERE %s = %%s
    """ % (SONGS_TABLENAME, FIELD_FINGERPRINTED, Database.FIELD_SONG_ID)

    # delete
    DELETE_UNFINGERPRINTED = """
        DELETE FROM %s WHERE %s = 0;
    """ % (SONGS_TABLENAME, FIELD_FINGERPRINTED)

    def __init__(self, **options):
        super(PGSQLDatabase, self).__init__()
        print "this is pgsql database"
        self.conn = psycopg2.connect(database=options['db'], user=options['user'], password=options['passwd'], host=options['host'], port="5432")
        # sys.exit()
        self.cursor = self.conn.cursor()




    def setup(self):
        """
        Creates any non-existing tables required for dejavu to function.

        This also removes all songs that have been added but have no
        fingerprints associated with them.
        """
        self.cursor.execute(self.CREATE_SONGS_TABLE)
        self.cursor.execute(self.CREATE_FINGERPRINTS_TABLE)
        self.cursor.execute(self.CREATE_INDEX_FINGERPRINTS)
        self.cursor.execute(self.DELETE_UNFINGERPRINTED)
        self.cursor.execute(self.CREATE_MATCHES_TABLE)
        self.cursor.execute(self.CREATE_FINGERPRINTS_RULE)
        self.conn.commit()
        print "ok Tables created"



    def empty(self):
        """
        Drops tables created by dejavu and then creates them again
        by calling `SQLDatabase.setup`.

        .. warning:
            This will result in a loss of data
        """
        self.cursor.execute(self.DROP_FINGERPRINTS_INDEX)
        self.cursor.execute(self.DROP_FINGERPRINTS_RULE)
        self.cursor.execute(self.DROP_FINGERPRINTS)
        self.cursor.execute(self.DROP_SONGS)
        self.cursor.execute(self.DROP_MATCHES_TABLE)
        self.conn.commit()
        print "Tables Droped"


    def delete_unfingerprinted_songs(self):
        """
        Called to remove any song entries that do not have any fingerprints
        associated with them.
        """
        pass


    def get_num_songs(self):
        """
        Returns the amount of songs in the database.
        """
        pass


    def get_num_fingerprints(self):
        """
        Returns the number of fingerprints in the database.
        """
        pass


    def set_song_fingerprinted(self, sid):
        """
        Sets a specific song as having all fingerprints in the database.

        sid: Song identifier
        """
        self.cursor.execute(self.UPDATE_SONG_FINGERPRINTED, (sid,))
        self.conn.commit()


    def get_songs(self):
        """
        Returns all fully fingerprinted songs in the database.
        """
        self.cursor.execute(self.SELECT_SONGS)
        for row in self.cursor:
            yield row


    def get_song_by_id(self, sid):
        """
        Return a song by its identifier

        sid: Song identifier
        """
        self.cursor.execute(self.SELECT_SONG, (sid,))
        self.conn.commit()
        return self.cursor.fetchone()

    def insert_matches(self,song_id,duration,start,end,realtime):

        """
            Inserts matches in the database and returns the ID of the inserted record.
        """
        # print "from the database"
        # print matches
        # return
        self.cursor.execute(self.INSERT_MATCHES, (song_id,duration,realtime,start,end))
        self.conn.commit()



    def insert(self, hash, sid, offset):
        """
        Inserts a single fingerprint into the database.

          hash: Part of a sha1 hash, in hexadecimal format
           sid: Song identifier this fingerprint is off
        offset: The offset this hash is from
        """
        self.cursor.execute(self.INSERT_FINGERPRINT, (hash, sid, offset))
        self.conn.commit()


    def insert_song(self, songname, file_hash,duration):
        """
        Inserts a song name into the database, returns the new
        identifier of the song.

        song_name: The name of the song.
        """
        self.cursor.execute(self.INSERT_SONG, (songname, file_hash, duration))
        last_id = self.cursor.fetchone()[0]
        self.conn.commit()
        return last_id


    def query(self, hash):
        """
        Returns all matching fingerprint entries associated with
        the given hash as parameter.

        hash: Part of a sha1 hash, in hexadecimal format
        """
        pass


    def get_iterable_kv_pairs(self):
        """
        Returns all fingerprints in the database.
        """
        pass


    def insert_hashes(self, sid, hashes):
        """
        Insert a multitude of fingerprints.

           sid: Song identifier the fingerprints belong to
        hashes: A sequence of tuples in the format (hash, offset)
        -   hash: Part of a sha1 hash, in hexadecimal format
        - offset: Offset this hash was created from/at.
        """
        values = []
        for hash, offset in hashes:
            values.append((hash, sid, offset))

        for split_values in grouper(values, 1000):
            self.cursor.executemany(self.INSERT_FINGERPRINT, split_values)
        self.conn.commit()


    def return_matches(self, hashes):
        """
        Searches the database for pairs of (hash, offset) values.

        hashes: A sequence of tuples in the format (hash, offset)
        -   hash: Part of a sha1 hash, in hexadecimal format
        - offset: Offset this hash was created from/at.

        Returns a sequence of (sid, offset_difference) tuples.

                      sid: Song identifier
        offset_difference: (offset - database_offset)
        """
        mapper = {}
        finale = []
        for hash, offset in hashes:
            mapper[hash.upper()] = offset

        # print mapper
        # sys.exit()
        # Get an iteratable of all the hashes we need
        values = mapper.keys()
        for split_values in grouper(values, 1000):
                # Create our IN part of the query
                query = self.SELECT_MULTIPLE
                query = query % ','.join(["decode(%s,'hex')"] * len(split_values))
                self.cursor.execute(query, split_values)
                for hash, sid, offset in self.cursor.fetchall():
                    # (sid, db_offset - song_sampled_offset)
                    yield (sid, offset - mapper[hash.upper()], offset, mapper[hash.upper()])

    def my_test(self):
        s11 = set()
        self.cursor.execute("Select hash,ofset from fingerprints where song_id = 15")
        for row in self.cursor:
             s11.add(row)

        s12 =  set()
        self.cursor.execute("Select hash,ofset from fingerprints where song_id = 16")
        for row in self.cursor:
             s12.add(row)

        s13 = set()
        self.cursor.execute("Select hash,ofset from fingerprints where song_id = 17")
        for row in self.cursor:
            s13.add(row)

        return s11,s12,s13

def grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return (filter(None, values) for values
            in izip_longest(fillvalue=fillvalue, *args))






