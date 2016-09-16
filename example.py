import warnings
import json
import time
import sys
warnings.filterwarnings("ignore")

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer, MicrophoneRecognizer

# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavuPgsql.cnf") as f:
    config = json.load(f)

if __name__ == '__main__':

	# create a Dejavu instance
    djv = Dejavu(config)

    print 'test'
    # print djv.songhashes_set
    # Fingerprint all the mp3's in the directory we give it
    # djv.fingerprint_directory("mp3", [".mp3"])
    # this one
    # djv.fingerprint_file("chunks/ja.wav")
    # djv.ok_test()

    # Recognize audio from a file
    # this one
    # fromtime = time.time()
    try:
        song = djv.recognize(FileRecognizer,"chunks/ja.wav")
        print song
    except Exception, e:
        print "in example"
        print e
    # print  time.time() - fromtime



    # recognizer = FileRecognizer(djv)
    # song = recognizer.recognize_file("mp3/Josh-Woodward--I-Want-To-Destroy-Something-Beautiful.mp3")
    # print "No shortcut, we recognized: %s\n" % song
    # # Or recognize audio from your microphone for `secs` secondse
	# secs = 5
	# song = djv.recognize(MicrophoneRecognizer, seconds=secs)
	# if song is None:
	# 	print "Nothing recognized -- did you
    # play the song out loud so your mic could hear it? :)"
	# else:
	# 	print "From mic with %d seconds we recognized: %s\n" % (secs, song)
    # # Or use a recognizer without the shortcut, in anyway you would like
	# recognizer = FileRecognizer(djv)
	# song = recognizer.recognize_file("mp3/Josh-Woodward--I-Want-To-Destroy-Something-Beautiful.mp3")
	# print "No shortcut, we recognized: %s\n" % song
