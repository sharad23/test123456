from . import fingerprint
from . import decoder
import numpy as np
import pyaudio
import time
import sounddevice as sd
import sys
from os import path,makedirs,remove,rename

from  multiprocessing import Process,Queue

import json

import wave

class BaseRecognizer(object):

    def __init__(self, dejavu):
        self.dejavu = dejavu
        self.Fs = fingerprint.DEFAULT_FS


    def _recognize(self, *data):
        # print data
        # sys.exit()
        matches = []
        # np.set_printoptions(threshold=np.nan)
        for d in data:
            matches.extend(self.dejavu.find_matches(d, Fs=self.Fs))
        return self.dejavu.align_matches(matches,len(d),self.Fs)

    def recognize(self):
        pass  # base class does nothing

class FileRecognizer(BaseRecognizer):
    def __init__(self, dejavu):
        super(FileRecognizer, self).__init__(dejavu)

    def recognize_file(self, filename):
        # np.set_printoptions(threshold=np.nan)
        frames, self.Fs, file_hash = decoder.read(filename, self.dejavu.limit)
        print 'sampling rate'
        print self.Fs
        # self.Fs =  44100
        # print 'new sampling rate'
        t = time.time()
        # print t

        # sys.exit()
        match = self._recognize(*frames)
        # t = time.time() - t
        # if match:
        #     match['match_time'] = t

        return match

    def recognize(self, filename):
        return self.recognize_file(filename)

class MicrophoneRecognizer(BaseRecognizer):
    default_chunksize   = 8192
    default_format      = pyaudio.paInt16
    default_channels    = 2
    default_samplerate  = 44100

    def __init__(self, dejavu):
        super(MicrophoneRecognizer, self).__init__(dejavu)
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.data = []
        self.channels = MicrophoneRecognizer.default_channels
        self.chunksize = MicrophoneRecognizer.default_chunksize
        self.samplerate = MicrophoneRecognizer.default_samplerate
        self.recorded = False

    def start_recording(self, channels=default_channels,
                        samplerate=default_samplerate,
                        chunksize=default_chunksize):
        self.chunksize = chunksize
        self.channels = channels
        self.recorded = False
        self.samplerate = samplerate

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()

        self.stream = self.audio.open(
            format=self.default_format,
            channels=channels,
            rate=samplerate,
            input=True,
            frames_per_buffer=chunksize,
        )

        self.data = [[] for i in range(channels)]

    def process_recording(self):
        data = self.stream.read(self.chunksize)

        # print data.size
        print type(data)
        # print data
        nums = np.fromstring(data, np.int16)
        # print dir(nums)
        print nums.size
        print nums.ndim
        print nums
        # print self.channels
        for c in range(self.channels):
            self.data[c].extend(nums[c::self.channels])
        # print self.data
        # print nums
        # print 'start',nums[c::self.channels],'stop'

    def stop_recording(self):
        self.stream.stop_stream()
        self.stream.close()
        self.stream = None
        self.recorded = True

    def recognize_recording(self):
        if not self.recorded:
            raise NoRecordingError("Recording was not complete/begun")
        # print self.data
        # print type(self.data)
        # print type(*self.data)

        # with open('data.txt', 'w') as outfile:
        #     # json.dump(self.data, outfile)
        #     outfile.write(json.dumps(self.data))
        #


        return self._recognize(*self.data)

    def get_recorded_time(self):
        return len(self.data[0]) / self.rate

    def recognize(self, seconds=10):
        self.start_recording()
        for i in range(0, int(self.samplerate / self.chunksize
                              * seconds)):
            self.process_recording()
        self.stop_recording()
        return self.recognize_recording()

class NoRecordingError(Exception):
    pass

class AudioInStreamRecognizer(BaseRecognizer):

    default_format = pyaudio.paInt16


    def __init__(self, dejavu):
        super(AudioInStreamRecognizer, self).__init__(dejavu)
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.data = []
        self.channels = 1
        self.chunk_size = 8192
        self.sample_rate = 44100
        self.recorded = False
        # self.buffersize = format=self.default_format#1024
        # self.buffersize = 2**12
        self.buffersize = 1024
        self.reset_data()

        self.matches = []

        """
        Setting up the array that will handle the timeseries of audio data from our input
        """
        self.audio_empty = np.empty((self.buffersize), dtype="int16")
        print self.audio_empty
        # stack to store the incoming audio data
        self.audio_in_queue = Queue()

        self.device_index = 8

        self.p1 = Process(target=self.add_to_queue, args=(self.audio_in_queue,))
        self.p2 = Process(target=self.process_queue, args=(self.audio_in_queue,))

    def reset_data(self):
        # self.data = []
        self.data = [[] for i in range(self.channels)]

    def is_potential_input_device(self,device_name):
        device_name = device_name.lower()
        # and device_name.find('hw:0,0') ==-1
        if (device_name.find('usb') > -1 and device_name.find('hw:0,0') == -1):
            return True
        return False

    def manual_device_choice(self):
        index = raw_input('Enter the index of the device. -1 for none')
        return int(index)

    def detect_device(self,list_devices=1):
        # list all the input audio devices
        p = pyaudio.PyAudio()
        n = p.get_device_count()
        i = 0
        potential_devices = []
        while i < n:
            dev = p.get_device_info_by_index(i)
            print str(i) + '. ' + dev['name']
            if dev['maxInputChannels'] > 0:
                # if(list_devices == 1):
                if (self.is_potential_input_device(dev['name'])):
                    potential_devices.append(i)
            i += 1
        pot_dev_count = len(potential_devices)
        if (pot_dev_count == 1):
            device_index = potential_devices.pop()
        else:
            print str(pot_dev_count) + ' potential devices found'
            device_index = self.manual_device_choice()

        theDevice = p.get_device_info_by_index(device_index)
        fs = int(theDevice['defaultSampleRate'])
        print 'Using Input device: [' + str(device_index) + '] ' + theDevice['name']
        return (device_index, fs)

    def recorded_stream_callback(self, in_data, frame_count, time_info, status):
        # must return a tuple containing frame_count frames of audio data and a flag
        # signifying whether there are more frames to play/record.
        # print 'c %s' % time.time()
        # return (in_data)
        # audio_data =  np.fromstring(in_data)
        # print type(in_data)
        nums = np.fromstring(in_data, np.int16)
        # print nums.size
        print nums
        # print self.channels
        for c in range(self.channels):
            self.data[c].extend(nums[c::self.channels])
            # self.data[c].extend(nums)
        # print len(self.data)
        # self.data.extend(nums)

        # print len(self.data[0])

        compare = 100000

        if   len(self.data[0]) > compare   :
            self.audio_in_queue.put(self.data)
            # print self.data
            self.reset_data()

        # return (in_data, pyaudio.paContinue)
        # self.audio_in_queue.put(audio_data)
        # print self.audio_in_queue.qsize()

        return ("ok", pyaudio.paContinue)

    def process_queue(self,audio_queue):
        while True:
            data = audio_queue.get()
            # if t in None:
            # return \
            self._recognize(*data)
            # np.set_printoptions(threshold=np.nan)

            # self.matches.extend(self.dejavu.find_matches(data, Fs=self.Fs))

            # return self.dejavu.align_matches(self.matches)


            # print 'processing queue'
            # print t

    def add_to_queue(self,audio_queue):
        print 'a'
        # WIDTH = 2
        # CHANNELS = 2
        # RATE = 44100
        DEVICE_INDEX, RATE = self.detect_device(0)
        # DEVICE_INDEX=2
        # RATE=44100
        print 'listening audio index %s with sample rate %s' % (DEVICE_INDEX, RATE)
        p = pyaudio.PyAudio()
        chunk_size = 2 ** 16

        stream = p.open(
            format=pyaudio.paInt16,
            # format=p.get_format_from_width(WIDTH),
            channels=self.channels,
            rate=RATE,
            input=True,
            frames_per_buffer=chunk_size,
            # output=True,
            input_device_index=DEVICE_INDEX,
            stream_callback=self.recorded_stream_callback
        )



        default_chunksize = 1024
        default_format = pyaudio.paInt16
        default_channels = 2
        default_samplerate = 44100

        data = []

        stream.stop_stream()
        stream.start_stream()

        while stream.is_active():
            time.sleep(0.01)

    def recognize(self,device_index=None):
        print 'recognizing'
        self.p1.start()
        self.p2.start()
        self.p1.join()
        self.p2.join()

class AudioInStreamRecognizerNoFile(BaseRecognizer):

    default_format = pyaudio.paInt16

    def __init__(self, dejavu):
        super(AudioInStreamRecognizer, self).__init__(dejavu)
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.data = []
        self.channels = 2
        self.chunk_size = 8192
        self.sample_rate = 44100
        self.recorded = False
        # self.buffersize = format=self.default_format#1024
        self.buffersize = 2**12
        self.reset_data()

        self.device_index = None

        self.vandar = []

        """
        Setting up the array that will handle the timeseries of audio data from our input
        """
        self.audio_empty = np.empty((self.buffersize), dtype="int16")
        print self.audio_empty
        # stack to store the incoming audio data
        self.audio_in_queue = Queue()

        self.device_index = 8

        self.p1 = Process(target=self.add_to_queue, args=(self.audio_in_queue,))
        self.p2 = Process(target=self.process_queue, args=(self.audio_in_queue,))

    def reset_data(self):
        self.data = [[] for i in range(self.channels)]
        self.vandar = []

    def is_potential_input_device(self,device_name):
        device_name = device_name.lower()
        # and device_name.find('hw:0,0') ==-1
        if (device_name.find('usb') > -1 and device_name.find('hw:0,0') == -1):
            return True
        return False

    def manual_device_choice(self):
        index = raw_input('Enter the index of the device. -1 for none')
        return int(index)

    def detect_device(self,list_devices=1):
        # list all the input audio devices
        p = pyaudio.PyAudio()
        n = p.get_device_count()
        i = 0
        potential_devices = []
        while i < n:
            dev = p.get_device_info_by_index(i)
            print str(i) + '. ' + dev['name']
            if dev['maxInputChannels'] > 0:
                # if(list_devices == 1):
                if (self.is_potential_input_device(dev['name'])):
                    potential_devices.append(i)
            i += 1
        pot_dev_count = len(potential_devices)
        if (pot_dev_count == 1):
            device_index = potential_devices.pop()
        else:
            print str(pot_dev_count) + ' potential devices found'
            device_index = self.manual_device_choice()

        theDevice = p.get_device_info_by_index(device_index)
        fs = int(theDevice['defaultSampleRate'])
        print 'Using Input device: [' + str(device_index) + '] ' + theDevice['name']
        return (device_index, fs)

    def recorded_stream_callback(self, indata, frames, time_, status):
        # must return a tuple containing frame_count frames of audio data and a flag
        # signifying whether there are more frames to play/record.
        # print 'c %s' % time.time()
        # return (in_data)
        # audio_data =  np.fromstring(in_data)
        # print indata

        if status:
            print status


        # outdata [::1] = indata
        # print 'wtf'
        # print frames
        # print bool(status)
        nums = np.fromstring(indata, np.int16)
        # nums = indata
        # print indata[::args.downsample, mapping];
        # print self.channels

        # print self.data
        '''
        self.vandar.extend(nums)

        if len(self.vandar) > 500000:
            self.audio_in_queue.put(self.vandar)
            # print self.data
            self.reset_data()

        return (indata, pyaudio.paContinue)
        '''
        for c in range(self.channels):
            self.data[c].extend(nums[c::self.channels])
        print len(self.data[0])
        print len(self.data[1])

        sys.stdout.write('.')
        # print len(self.data[0])

        if len(self.data[0]) > 500000:
            self.audio_in_queue.put(self.data)
            # self.audio_in_queue.put(self.data[1])
            # print self.data
            self.reset_data()

        return (indata, pyaudio.paContinue)
        # self.audio_in_queue.put(audio_data)
        # print self.audio_in_queue.qsize()

        return ("ok", pyaudio.paContinue)

    def process_queue(self,audio_queue):
        while True:
            data = audio_queue.get()

            # print type(data)
            # for t in data:
            #     print type(t)
            # if t in None:
            # return \
            # print data
            self._recognize(*data)
            # print 'processing queue'
            # print t

    def add_to_queue(self,audio_queue):
        print 'a'

        WIDTH = 2
        CHANNELS = 2
        # RATE = 44100

        if self.device_index is None:
            self.device_index,self.sample_rate=  self.detect_device(0)

        # DEVICE_INDEX=8
        # RATE=44100
        print 'listening audio index %s with sample rate %s' % (self.device_index, self.sample_rate)
        # p = pyaudio.PyAudio()
        chunk_size = 2 ** 13

        stream = sd.InputStream(
            device=self.device_index,
            channels=self.channels,
            # dtype=pyaudio.paInt16,
            blocksize=chunk_size,
            samplerate=self.sample_rate,
            callback=self.recorded_stream_callback
        )




        with stream:
            while True:
                pass


    def recognize(self,device_index=None):
        if device_index is not None:
            self.device_index = device_index
        print 'recognizing'
        self.p1.start()
        self.p2.start()
        self.p1.join()
        self.p2.join()

class AudioInStreamRecognizerSd(BaseRecognizer):

    default_format = pyaudio.paInt16

    def __init__(self, dejavu):
        super(AudioInStreamRecognizer, self).__init__(dejavu)
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.data = []
        self.channels = 1
        self.chunk_size = 8192
        self.sample_rate = 44100
        self.recorded = False
        # self.buffersize = format=self.default_format#1024
        self.buffersize = 2**12
        self.reset_data()

        self.device_index = None

        self.vandar = []

        """
        Setting up the array that will handle the timeseries of audio data from our input
        """
        self.audio_empty = np.empty((self.buffersize), dtype="int16")
        print self.audio_empty
        # stack to store the incoming audio data
        self.audio_in_queue = Queue()

        self.device_index = 8

        self.p1 = Process(target=self.add_to_queue, args=(self.audio_in_queue,))
        self.p2 = Process(target=self.process_queue, args=(self.audio_in_queue,))

    def reset_data(self):
        self.data = [[] for i in range(self.channels)]
        self.vandar = []

    def is_potential_input_device(self,device_name):
        device_name = device_name.lower()
        # and device_name.find('hw:0,0') ==-1
        if (device_name.find('usb') > -1 and device_name.find('hw:0,0') == -1):
            return True
        return False

    def manual_device_choice(self):
        index = raw_input('Enter the index of the device. -1 for none')
        return int(index)

    def detect_device(self, list_devices=1):
        # list all the input audio devices
        p = pyaudio.PyAudio()
        n = p.get_device_count()
        i = 0
        potential_devices = []
        while i < n:
            dev = p.get_device_info_by_index(i)
            print str(i) + '. ' + dev['name']
            if dev['maxInputChannels'] > 0:
                # if(list_devices == 1):
                if (self.is_potential_input_device(dev['name'])):
                    potential_devices.append(i)
            i += 1
        pot_dev_count = len(potential_devices)
        if (pot_dev_count == 1):
            device_index = potential_devices.pop()
        else:
            print str(pot_dev_count) + ' potential devices found'
            device_index = self.manual_device_choice()

        theDevice = p.get_device_info_by_index(device_index)
        fs = int(theDevice['defaultSampleRate'])
        print 'Using Input device: [' + str(device_index) + '] ' + theDevice['name']
        return (device_index, fs)

    def recorded_stream_callback(self, indata, frames, time_, status):
        # must return a tuple containing frame_count frames of audio data and a flag
        # signifying whether there are more frames to play/record.
        # print 'c %s' % time.time()
        # return (in_data)
        # audio_data =  np.fromstring(in_data)
        # print indata

        # print type(indata)
        # if time_ < 2:
        #     print dir(indata)
        if status:
            print status

        sys.stdout.write('.')
        self.audio_in_queue.put(indata)


        return ("ok", pyaudio.paContinue)
        # print dir(time_)
        # print int(time_.currentTime)

        # outdata [::1] = indata
        # print 'wtf'
        # print frames
        # print bool(status)
        nums = np.fromstring(indata, np.int16)
        # nums = indata
        # print indata[::args.downsample, mapping];
        # print self.channels

        # print self.data
        '''
        self.vandar.extend(nums)

        if len(self.vandar) > 500000:
            self.audio_in_queue.put(self.vandar)
            # print self.data
            self.reset_data()

        return (indata, pyaudio.paContinue)
        '''
        for c in range(self.channels):
            self.data[c].extend(nums[c::self.channels])

        # print len(self.data[0])
        # print len(self.data[1])

        sys.stdout.write('.')
        # print len(self.data[0])

        if len(self.data[0]) > 50000:
            self.audio_in_queue.put(self.data)
            # self.audio_in_queue.put(self.data[1])
            # print self.data
            self.reset_data()

        return (indata, pyaudio.paContinue)
        # self.audio_in_queue.put(audio_data)
        # print self.audio_in_queue.qsize()

        return ("ok", pyaudio.paContinue)

    def process_queue(self, audio_queue):
        # ploting script
        downsample = 1
        length = np.ceil(200 * self.sample_rate / (1000 * downsample))
        plotdata = np.zeros((length, self.channels))

        fig, ax = plt.subplots()
        global lines
        lines = ax.plot(plotdata)
        if self.channels > 1:
            ax.legend(['channel {}'.format(c) for c in self.channels],
                      loc='lower left', ncol=self.channels)
        ax.axis((0, len(plotdata), -1, 1))
        ax.set_yticks([0])
        ax.yaxis.grid(True)
        ax.tick_params(bottom='off', top='off', labelbottom='off',
                       right='off', left='off', labelleft='off')
        fig.tight_layout(pad=0)

        while True:
            raw_data = audio_queue.get()
            print raw_data

            for c in range(self.channels):
                # self.data[c].extend(raw_data[c::self.channels])
                self.data[c].extend(raw_data[c])

            # print type(raw_data)
            # data = np.fromstring(raw_data, np.int16)
            # print data.ndim
            # print '--'
            # print type(data)
            # print raw_data

            # data = [raw_data]

            # print raw_data.ndim
            # print self.data

            # print type(raw_data)
            # print dir(raw_data)

            # self._recognize(*raw_data)

            # self.data[0].extend(data)
            #
            if len(self.data[0]) > 10:
                print self.data
                self._recognize(*self.data)
                self.reset_data()



            # print data.size
            # self._recognize(data)
            # print type(data)
            # for t in data:
            #     print type(t)
            # if t in None:
            # return \
            # print data
            # self._recognize(*data)
            # print 'processing queue'
            # print t


    def add_to_queue(self, audio_queue):
        print 'a'

        WIDTH = 2
        CHANNELS = 2
        # RATE = 44100

        # if self.device_index is None:

        self.device_index,self.sample_rate=  self.detect_device(0)

        # DEVICE_INDEX=8
        # RATE=44100
        print 'listening audio index %s with sample rate %s' % (self.device_index, self.sample_rate)
        # p = pyaudio.PyAudio()
        chunk_size = 2 ** 12

        stream = sd.InputStream(
            device=self.device_index,
            channels=self.channels,
            # dtype=pyaudio.paIsnt16,
            blocksize=chunk_size,
            samplerate=self.sample_rate,
            # never_drop_input=True,
            callback=self.recorded_stream_callback
        )

        # ani = FuncAnimation(fig, update_plot, interval=30, blit=True)

        with stream:
            plt.show()
            while True:
                pass

    def recognize(self, device_index=None):
        if device_index is not None:
            self.device_index = device_index
        print 'recognizing'
        self.p1.start()
        self.p2.start()
        self.p1.join()
        self.p2.join()

class AudioInStreamRecognizerFileBased(BaseRecognizer):

    default_format = pyaudio.paInt16


    def __init__(self, dejavu):
        super(AudioInStreamRecognizerFileBased, self).__init__(dejavu)
        self.audio = pyaudio.PyAudio()

        self.data = []
        self.channels = 1

        self.sample_rate = 48000
        self.buffer_size = 2**8
        self.reset_data()

        self.device_index = None
        self.matches = []

        # make the file directory if not exists
        self.chunk_directory = './ad_chunks2/'

        if not path.exists( self.chunk_directory):
            makedirs(self.chunk_directory)

        self.file_counter = 0

        # stack to store the incoming audio data
        self.audio_in_queue = Queue()
        self.files_in_queue = Queue()

        self.p1 = Process(target=self.add_to_queue, args=(self.audio_in_queue,))
        self.p2 = Process(target=self.process_queue, args=(self.audio_in_queue,self.files_in_queue,))
        self.p3 = Process(target=self.process_files, args=(self.files_in_queue,))

    def reset_data(self):
        self.data = []
        # self.data = [[] for i in range(self.channels)]

    def is_potential_input_device(self,device_name):
        device_name = device_name.lower()
        # and device_name.find('hw:0,0') ==-1
        if (device_name.find('usb') > -1 and device_name.find('hw:0,0') == -1):
            return True
        return False

    def manual_device_choice(self):
        index = raw_input('Enter the index of the device. -1 for none')
        return int(index)

    def detect_device(self,list_devices=1):
        # list all the input audio devices
        p = pyaudio.PyAudio()
        n = p.get_device_count()
        i = 0
        potential_devices = []
        while i < n:
            dev = p.get_device_info_by_index(i)
            print str(i) + '. ' + dev['name']
            if dev['maxInputChannels'] > 0:
                # if(list_devices == 1):
                if (self.is_potential_input_device(dev['name'])):
                    potential_devices.append(i)
            i += 1
        pot_dev_count = len(potential_devices)
        if (pot_dev_count == 1):
            device_index = potential_devices.pop()
        else:
            print str(pot_dev_count) + ' potential devices found'
            device_index = self.manual_device_choice()

        theDevice = p.get_device_info_by_index(device_index)
        fs = int(theDevice['defaultSampleRate'])
        print 'Using Input device: [' + str(device_index) + '] ' + theDevice['name']
        return (device_index, fs)

    def recorded_stream_callback(self, in_data, frame_count, time_info, status):
        # must return a tuple containing frame_count frames of audio data and a flag
        # signifying whether there are more frames to play/record.

        self.audio_in_queue.put(in_data)

        return ("ok", pyaudio.paContinue)

    def _prepare_file(self,fname,mode='wb'):
        wavefile = wave.open(self.chunk_directory + fname, 'wb')
        wavefile.setnchannels(self.channels)
        wavefile.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
        wavefile.setframerate(self.sample_rate)
        return wavefile

    def process_queue(self, audio_queue, file_queue):

        block_size = 1024
        seconds_to_record = 30

        limit = 10

        samples_per_second = self.sample_rate/self.buffer_size

        samples_to_record = samples_per_second * seconds_to_record


        # duration = 5
        # frames_count = duration * frame_size

        # fname = "chunk_%s_%s" % (self.file_counter, start)


        while True:

            queue_items_count = audio_queue.qsize()

            if not queue_items_count:
                continue

            # start = time.time()
            print "@@@@@@@@@@@@@@@@@@@@@@@@ there is file to store @@@@@@@@@@@@@@@@"
            fname = "chunk_%s.wav" % (self.file_counter)
            print fname
            # f = open(self.chunk_directory + fname, 'wb')

            self.wavefile = self._prepare_file(fname)

            # while time.time() - start < limit:


            frames_count = 0
            print '%d frames going to be recorded in %s for %d sec' % (samples_to_record,fname,seconds_to_record)
            # while time.time() - start <  < limit:
            while frames_count < samples_to_record:
                try:
                    audio_data = audio_queue.get()
                    if not audio_data:
                        break

                    # f.write(audio_data)

                    self.wavefile.writeframes(audio_data)
                    frames_count = frames_count + 1
                    sys.stdout.write('.')
                except Exception as e:
                    print ("Error " + str(e))
            sys.stdout.flush()
            self.wavefile.close()
            print '%d frames recorded in %s for %d sec' % (samples_to_record,fname,seconds_to_record)
            file_queue.put(fname)
            self.file_counter = self.file_counter +1
            sys.stdout.flush()
            # if t in None:
            # return \
            # np.set_printoptions(threshold=np.nan)

            # self.matches.extend(self.dejavu.find_matches(data, Fs=self.Fs))

            # return self.dejavu.align_matches(self.matches)

            # print 'processing queue'
            # print t

    def change_to_standard(self,file_queue):
        chunk_filename = file_queue.get()
        if dejavu.check_fs(chunk_filename) != fingerprint.DEFAULT_FS:
            filelist = chunk_filename.split('/')
            filename = filelist[-1]
            filename = '_' + filename
            filelist[-1] = filename
            filtered_chunk_filename = "/".join(filelist)
            ff = ffmpy.FFmpeg(
                inputs={chunk_filename: None},
                outputs={filtered_chunk_filename: '-ar '+str(fingerprint.DEFAULT_FS)}
            )
            ff.run()
        else:
            filtered_chunk_filename = chunk_filename


    def process_files(self, file_queue ):
        print 'processing files started'
        while True:

            files_count = file_queue.qsize()

            if not files_count:
                # sys.stdout.write('.')
                continue
            print '%d files found in queue' % files_count
            chunk_filename = file_queue.get()
            the_file = self.chunk_directory + chunk_filename

            print '...processing file %s' % the_file
            # time.sleep(20)
            # print "About to process........."
            # print the_file

            # self.dejavu.recognize(FileRecognizer,the_file)
            matches = self.dejavu.recognize(FileRecognizer, the_file)
            print matches
            # if not matches:
            #     remove(the_file)
            # else:
            #     pass
                # rename the file name to sth unique
                # rename(the_file,'match_')
                # for m in matches:
                #     pass
                #     #insert in new table for



    def add_to_queue(self,audio_queue):
        print 'a'
        WIDTH = 2
        # CHANNELS = 1
        # DEVICE_INDEX, RATE = self.detect_device(0)
        # DEVICE_INDEX=2
        # RATE=44100
        print 'listening audio index %s with sample rate %s' % (self.device_index, self.sample_rate)
        p = pyaudio.PyAudio()
        print 'channels '
        print self.channels

        stream = p.open(
            format=pyaudio.paInt16,
            # format=p.get_format_from_width(WIDTH),
            channels=self.channels,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.buffer_size,
            # output=True,
            input_device_index=self.device_index,
            stream_callback=self.recorded_stream_callback
        )

        data = []

        stream.stop_stream()
        stream.start_stream()

        # while stream.is_active():
        #     time.sleep(0.01)
        # with stream:
            # while True:
            #     pass

        while stream.is_active():
            while True:
                pass



    def recognize(self,device_index=None,channels=2):
        print 'recognizing'
        self.channels=channels
        if device_index is not None:
            self.device_index = device_index
        self.p1.start()
        self.p2.start()
        self.p3.start()

        self.p1.join()
        self.p2.join()
        self.p3.join()

def __exit__(self, exception, value, traceback):
        print '__exit__ has been called'

        self.p1.terminate()
        self.p2.terminate()
        self.p3.terminate()
