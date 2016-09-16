from .database import get_database, Database
from pydub import AudioSegment
import decoder as decoder
import fingerprint
import multiprocessing
import os
import traceback
import sys
import time


class Dejavu(object):

    SONG_ID = "song_id"
    SONG_NAME = 'song_name'
    CONFIDENCE = 'confidence'
    MATCH_TIME = 'match_time'
    SONG_END_TIME = 'end_time'
    OFFSET = 'offset'
    SONG_START_TIME = "start_time"
    OFFSET_SECS = 'offset_seconds',
    ABS_START_TIME = 'abs_start_time',
    ABS_END_TIME = 'abs_end_time'



    def __init__(self, config):
        super(Dejavu, self).__init__()

        self.config = config

        # initialize db

        db_cls = get_database(config.get("database_type", None))
        # print db_cls
        # sys.exit()

        self.db = db_cls(**config.get("database", {}))

        # if we should limit seconds fingerprinted,
        # None|-1 means use entire track
        self.limit = self.config.get("fingerprint_limit", None)

        if self.limit == -1:  # for JSON compatibility
            self.limit = None
        self.get_fingerprinted_songs()

    def get_fingerprinted_songs(self):
        # get songs previously indexed
        self.songs = self.db.get_songs()
        self.songhashes_set = set()  # to know which ones we've computed before
        for song in self.songs:
            song_hash = song[2]
            self.songhashes_set.add(song_hash)

    def fingerprint_directory(self, path, extensions, nprocesses=None):
        # Try to use the maximum amount of processes if not given.
        try:
            nprocesses = nprocesses or multiprocessing.cpu_count()
        except NotImplementedError:
            nprocesses = 1
        else:
            nprocesses = 1 if nprocesses <= 0 else nprocesses

        pool = multiprocessing.Pool(nprocesses)
        filenames_to_fingerprint = []
        for filename, _ in decoder.find_files(path, extensions):

            # don't refingerprint already fingerprinted files
            if decoder.unique_hash(filename) in self.songhashes_set:
                print "%s already fingerprinted, continuing..." % filename
                continue

            filenames_to_fingerprint.append(filename)


        # Prepare _fingerprint_worker input
        worker_input = zip(filenames_to_fingerprint,
                           [self.limit] * len(filenames_to_fingerprint))


        # Send off our tasks
        iterator = pool.imap_unordered(_fingerprint_worker,worker_input)

        # Loop till we have all of them
        while True:
            try:
                song_name, hashes, file_hash = iterator.next()
            except multiprocessing.TimeoutError:
                continue


            except StopIteration:
                break
            except:
                print("Failed fingerprinting")
                # Print traceback because we can't reraise it here
                traceback.print_exc(file=sys.stdout)
            else:


                sorted_hash = sorted(hashes,key= lambda x:x[1],reverse=True)
                duration = round(float(sorted_hash[0][1]) / fingerprint.DEFAULT_FS *
                         fingerprint.DEFAULT_WINDOW_SIZE *
                         fingerprint.DEFAULT_OVERLAP_RATIO, 5)


                sid = self.db.insert_song(song_name, file_hash,duration)

                self.db.insert_hashes(sid, hashes)
                self.db.set_song_fingerprinted(sid)
                self.get_fingerprinted_songs()

        pool.close()
        pool.join()

    def fingerprint_file(self, filepath, song_name=None):
        songname = decoder.path_to_songname(filepath)
        song_hash = decoder.unique_hash(filepath)
        song_name = song_name or songname
        # don't refingerprint already fingerprinted files
        if song_hash in self.songhashes_set:
            print "%s already fingerprinted, continuing..." % song_name
        else:

            song_name, hashes, file_hash = _fingerprint_worker(
                filepath,
                self.limit,
                song_name=song_name
            )
            sorted_hash = sorted(hashes,key= lambda x:x[1],reverse=True)
            duration = round(float(sorted_hash[0][1]) / fingerprint.DEFAULT_FS *
                         fingerprint.DEFAULT_WINDOW_SIZE *
                         fingerprint.DEFAULT_OVERLAP_RATIO, 5)
            sid = self.db.insert_song(song_name, file_hash,duration)
            print "inserted song id"
            print sid
            self.db.insert_hashes(sid, hashes)
            self.db.set_song_fingerprinted(sid)
            self.get_fingerprinted_songs()

    def find_matches(self, samples, Fs=fingerprint.DEFAULT_FS):

        hashes = fingerprint.fingerprint(samples, Fs=Fs)
        # this hash gives (hash, offset)
        return self.db.return_matches(hashes)


    def align_matches(self, matches,samples,sample_rate):

        print 'samples'
        print samples
        print 'sample rate'
        print sample_rate
        # confidence_freq = self.config.get("confidence_freq")
        # # local_maxima_freq = self.config.get("confidence_freq")
        # confidence = (samples/float(sample_rate)) * confidence_freq
        cnf = 10
        print 'standard_confidence'
        print cnf
        print "in align_matches:"
        # sys.exit()
        # traceback.print_stack()
        # traceback.print_exc(file=sys.stdout)
        # print matches
        """
            Finds hash matches that align in time with other matches and finds
            consensus about which hashes are "true" signal from the audio.

            Returns a dictionary with match information.
        """
    
        songs_count = {}
        for match_song_id, offset_delta, offset_db, offset_clip in matches:
            if match_song_id not in songs_count:
                songs_count[match_song_id] = 0
            songs_count[match_song_id] += 1
        print songs_count

        # no of confidence of each song that has match the hash value
        check = {}
        j = {}

        for match_song_id, offset_delta, offset_db, offset_clip in matches:
            if match_song_id not in check:
                j[match_song_id] = 0
                check[match_song_id] = {}
            if offset_delta not in check[match_song_id]:
                check[match_song_id][offset_delta] = 0
            check[match_song_id][offset_delta] += 1
            if check[match_song_id][offset_delta] > j[match_song_id]:
                j[match_song_id] = check[match_song_id][offset_delta]
        print j

        confidence_match = {}
        for song_id, diff, d_off, o_off in matches:
            if song_id not in confidence_match:
                confidence_match[song_id] = {}
            if diff not in confidence_match[song_id]:
                confidence_match[song_id][diff] = 0
            confidence_match[song_id][diff] += 1
        # print "confidence match"
        # print confidence_match

        fil_confidence_match = {}
        for song in confidence_match:
            # fil_confidence_match[song] = {}
            filtered = {k: v for k, v in confidence_match[song].items() if v > cnf}
            if bool(filtered):
                fil_confidence_match[song] = filtered

        print 'confidence match'
        print fil_confidence_match
        result_matches = []
        for song_id in fil_confidence_match:
            for confidence, count in fil_confidence_match[song_id].items():
                highest = 0
                lowest = 100000
                for i, j, k, l in matches:
                    if i == song_id and j == confidence:
                        if (k < lowest):
                            lowest = k
                            abs_low = l

                            low_params = (i, j, k, l)
                        if (k > highest):
                            highest = k
                            abs_hig = l
                            high_params = (i, j, k, l)

                hseconds = round(float(highest) / fingerprint.DEFAULT_FS *
                                 fingerprint.DEFAULT_WINDOW_SIZE *
                                 fingerprint.DEFAULT_OVERLAP_RATIO, 5)

                sseconds = round(float(lowest) / fingerprint.DEFAULT_FS *
                                 fingerprint.DEFAULT_WINDOW_SIZE *
                                 fingerprint.DEFAULT_OVERLAP_RATIO, 5)

                absolute_hseconds = round(float(abs_hig) / fingerprint.DEFAULT_FS *
                                          fingerprint.DEFAULT_WINDOW_SIZE *
                                          fingerprint.DEFAULT_OVERLAP_RATIO, 5)

                absolute_seconds = round(float(abs_low) / fingerprint.DEFAULT_FS *
                                         fingerprint.DEFAULT_WINDOW_SIZE *
                                         fingerprint.DEFAULT_OVERLAP_RATIO, 5)

                result_matches.append({'song_id': song_id, 'match_length': hseconds - sseconds, 'start_time': sseconds,
                                       'end_time': hseconds, 'abs_start_time': absolute_seconds,
                                       'abs_end_time': absolute_hseconds})
                # self.db.insert_matches(song_id, hseconds - sseconds, sseconds, hseconds)

        rejected_matches = []
        for activeindex, val1 in enumerate(result_matches):
            for index, val2 in enumerate(result_matches):
                if activeindex != index:
                    if val1['abs_start_time'] >= val2['abs_start_time'] and val1['abs_end_time'] <= val2[
                        'abs_end_time']:
                        # these are the one to be skipped
                        # print activeindex
                        if activeindex not in rejected_matches:
                            rejected_matches.append(activeindex)

        # filtered_result_matches = [i for j, i in enumerate(result_matches) if j not in rejected_matches]
        filtered_result_matches = []
        for index, val in enumerate(result_matches):
            if index not in rejected_matches:
                self.db.insert_matches(val['song_id'],val['match_length'], val['start_time'], val['end_time'],time.time())
                filtered_result_matches.append(val)

        print 'final'
        print filtered_result_matches


    def recognize(self, recognizer, *options, **kwoptions):
        r = recognizer(self)
        return r.recognize(*options, **kwoptions)

    def clear_data(self):

        """
            Clear the database of all contents
        """

        self.db.empty()

    def create_tables(self):

        self.db.setup()

    def ok_test(self):
        s11,s12,s13 = self.db.my_test()
        print "with 48000"
        print len(s11)
        print "with 44100"
        print len(s12)
        print "with 22050"
        print len(s13)
        print len(s11 & s12 & s13)

def _fingerprint_worker(filename, limit=None, song_name=None):
    # Pool.imap sends arguments as tuples so we have to unpack
    # them ourself.

    try:
        filename, limit = filename
    except ValueError:
        pass

    songname, extension = os.path.splitext(os.path.basename(filename))
    song_name = song_name or songname
    print song_name
    channels, Fs, file_hash = decoder.read(filename, limit)
    print ' i am here'
    print 'sampling Rate'
    print Fs
    result = set()
    channel_amount = len(channels)
    print channels
    for channeln, channel in enumerate(channels):
        #creating hash acc to the channel
        # TODO: Remove prints or change them into optional logging.n
        print("Fingerprinting channel %d/%d for %s" % (channeln + 1,
                                                       channel_amount,
                                                       filename))
        hashes = fingerprint.fingerprint(channel, Fs=Fs)
        print("Finished channel %d/%d for %s" % (channeln + 1, channel_amount,
                                                 filename))

        result |= set(hashes)
        # print result

    return song_name, result, file_hash

    def check_fs(self, filename):
        audiofile = AudioSegment.from_file(filename)
        fs = audiofile.frame_rate
        return fs


def chunkify(lst, n):
    """
    Splits a list into roughly n equal parts.
    http://stackoverflow.com/questions/2130016/splitting-a-list-of-arbitrary-size-into-only-roughly-n-equal-parts
    """
    return [lst[i::n] for i in xrange(n)]
