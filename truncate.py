import warnings
import json
warnings.filterwarnings("ignore")

from dejavu import Dejavu
from dejavu.recognize import FileRecognizer, MicrophoneRecognizer

# load config from a JSON file (or anything outputting a python dictionary)
with open("dejavuPgsql.cnf") as f:
# with open("dejavuMysql.cnf") as f:
    config = json.load(f)

if __name__ == '__main__':

	# create a Dejavu instance
    djv = Dejavu(config)

    #drop all the data
    djv.clear_data()

    #create all the tables
    djv.create_tables()