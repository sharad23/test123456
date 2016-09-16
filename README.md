Audio processing wit time
==========

Audio fingerprinting and recognition algorithm implemented in Python, see the explanation here:  
[How it works](http://willdrevo.com/fingerprinting-and-audio-recognition-with-python.html)

Dejavu can memorize audio by listening to it once and fingerprinting it. Then by playing a song and recording microphone input, Dejavu attempts to match the audio against the fingerprints held in the database, returning the song being played. 

Note that for voice recognition, Dejavu is not the right tool! Dejavu excels at recognition of exact signals with reasonable amounts of noise.

## Installation and Dependencies:

Read [INSTALLATION.md](INSTALLATION.md)

## Setup

First, install the above dependencies. 

Second, you'll need to create a MySQL database where Dejavu can store fingerprints. For example, on your local setup:
	
	$ mysql -u root -p
	Enter password: **********
	mysql> CREATE DATABASE IF NOT EXISTS dejavu;

Now you're ready to start fingerprinting your audio collection! 

## Quickstart

```bash
$ git clone https://github.com/worldveil/dejavu.git ./dejavu
$ cd dejavu
$ python example.py
```

## Fingerprinting

Let's say we want to fingerprint all of July 2013's VA US Top 40 hits. 

Start by creating a Dejavu object with your configurations settings (Dejavu takes an ordinary Python dictionary for the settings).

```python
>>> from dejavu import Dejavu
>>> config = {
...     "database": {
...         "host": "127.0.0.1",
...         "user": "root",
...         "passwd": <password above>, 
...         "db": <name of the database you created above>,
...     }
... }
>>> djv = Dejavu(config)
```

Next, give the `fingerprint_directory` method three arguments:
* input directory to look for audio files
* audio extensions to look for in the input directory
* number of processes (optional)

```python
>>> djv.fingerprint_directory("va_us_top_40/mp3", [".mp3"], 3)
```

For a large amount of files, this will take a while. However, Dejavu is robust enough you can kill and restart without affecting progress: Dejavu remembers which songs it fingerprinted and converted and which it didn't, and so won't repeat itself. 

You'll have a lot of fingerprints once it completes a large folder of mp3s:
```python
>>> print djv.db.get_num_fingerprints()
5442376
```

Also, any subsequent calls to `fingerprint_file` or `fingerprint_directory` will fingerprint and add those songs to the database as well. It's meant to simulate a system where as new songs are released, they are fingerprinted and added to the database seemlessly without stopping the system. 

## Configuration options

The configuration object to the Dejavu constructor must be a dictionary. 

The following keys are mandatory:

* `database`, with a value as a dictionary with keys that the database you are using will accept. For example with MySQL, the keys must can be anything that the [`MySQLdb.connect()`](http://mysql-python.sourceforge.net/MySQLdb.html) function will accept. 

The following keys are optional:

* `fingerprint_limit`: allows you to control how many seconds of each audio file to fingerprint. Leaving out this key, or alternatively using `-1` and `None` will cause Dejavu to fingerprint the entire audio file. Default value is `None`.
* `database_type`: as of now, only `mysql` (the default value) is supported. If you'd like to subclass `Database` and add another, please fork and send a pull request!

An example configuration is as follows:

```python
>>> from dejavu import Dejavu
>>> config = {
...     "database": {
...         "host": "127.0.0.1",
...         "user": "root",
...         "passwd": "Password123", 
...         "db": "dejavu_db",
...     },
...     "database_type" : "mysql",
...     "fingerprint_limit" : 10
... }
>>> djv = Dejavu(config)
```



### Recognizing: On Disk

Through the terminal:

```bash
$ python dejavu.py --recognize file sometrack.wav 
{'song_id': 1, 'song_name': 'Taylor Swift - Shake It Off', 'confidence': 3948, 'offset_seconds': 30.00018, 'match_time': 0.7159781455993652, 'offset': 646L}
```

or in scripting, assuming you've already instantiated a Dejavu object: 

```python
>>> from dejavu.recognize import FileRecognizer
>>> song = djv.recognize(FileRecognizer, "va_us_top_40/wav/Mirrors - Justin Timberlake.wav")
```



