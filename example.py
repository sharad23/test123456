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
    ######################
    # To Store our music uncomment this section with your music#
    ######################
    
    # djv.fingerprint_file("chunks/ja.wav")
    
    
    #####################################
    # to recognize uncomment this section
    ###########################################
    #try:
    #    song = djv.recognize(FileRecognizer,"chunks/ja.wav")
    #    print song
    #except Exception, e:
    #    print "in example"
    #    print e
    # print  time.time() - fromtime



    
