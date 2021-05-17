#!/usr/bin/env python

import ao
import mad
import readline
import socket
import struct
import sys
import threading
from time import sleep

# The Mad audio library we're using expects to be given a file object, but
# we're not dealing with files, we're reading audio data over the network.  We
# use this object to trick it.  All it really wants from the file object is the
# read() method, so we create this wrapper with a read() method for it to
# call, and it won't know the difference.
# NOTE: You probably don't need to modify this class.
MAX_MESSAGE_SIZE = 4117
EOL = ' END '
EOM = ' END END'
IS_PLAYING = False
ARROW_LOCK = False
NUM_AUDIO_MSGS_RECV = 0

class mywrapper(object):
    def __init__(self):
        self.mf = None
        self.data = ""

    # When it asks to read a specific size, give it that many bytes, and
    # update our remaining data.
    def read(self, size):
        result = self.data[:size]
        self.data = self.data[size:]
        return result

# Receive messages.  If they're responses to info/list, print
# the results for the user to see.  If they contain song data, the
# data needs to be added to the wrapper object.  Be sure to protect
# the wrapper with synchronization, since the other thread is using
# it too!

def recv_thread_func(wrap, cond_filled, sock):
    global ARROW_LOCK
    global NUM_AUDIO_MSGS_RECV
    while True:
        message_data = ""
        while len(message_data) < MAX_MESSAGE_SIZE: #partial recv handling
            message_data += sock.recv(MAX_MESSAGE_SIZE - len(message_data))
            tokenized_data = message_data.split(' ')
            if tokenized_data[-1] == "END" and tokenized_data[-2] == "END":
                break
        if message_data == None:
            continue
        if message_data:
            tokenized_data = message_data.split(' ')
            if 'RESP' == tokenized_data[0]:
                if '100' == tokenized_data[1]: #list
                    song_list = message_data.split(EOL)
                    for song in song_list:
                        if song[0].isdigit():
                            print(song)
                    ARROW_LOCK = False
                elif '200' == tokenized_data[1]: # audio
                    if IS_PLAYING == True:
                        if tokenized_data[-1] == "END" and tokenized_data[-2] == "END":
                            binary_audio = tokenized_data[3: len(tokenized_data) - 2]
                            binary_audio = " ".join(binary_audio)
                            cond_filled.acquire()
                            if wrap.mf is None:
                                wrap.mf = mad.MadFile(wrap)
                            if IS_PLAYING == True:
                                wrap.data += binary_audio
                            cond_filled.release()
                            ARROW_LOCK = False
                            NUM_AUDIO_MSGS_RECV += 1
            elif 'ERRO' == tokenized_data[0]:
                if '404' == tokenized_data[1]:
                    print("Error: Song ID not valid. Please use list to find a correct song ID.")
                    ARROW_LOCK = False


# If there is song data stored in the wrapper object, play it!
# Otherwise, wait until there is.  Be sure to protect your accesses
# to the wrapper with synchronization, since the other thread is
# using it too!
def play_thread_func(wrap, cond_filled, dev):
    global NUM_AUDIO_MSGS_RECV
    while True:
        """
        TODO
        example usage of dev and wrap (see mp3-example.py for a full example):
        buf = wrap.mf.read()
        dev.play(buffer(buf), len(buf))
        """
        if wrap.mf is not None:
            if NUM_AUDIO_MSGS_RECV > 500:
                cond_filled.acquire()
                buf = wrap.mf.read()
                cond_filled.release()
                if buf and IS_PLAYING == True:
                    dev.play(buffer(buf), len(buf))

def main():
    if len(sys.argv) < 3:
        print 'Usage: %s <server name/ip> <server port>' % sys.argv[0]
        sys.exit(1)
    global IS_PLAYING
    global NUM_AUDIO_MSGS_RECV
    # Create a pseudo-file wrapper, condition variable, and socket.  These will
    # be passed to the thread we're about to create.
    wrap = mywrapper()
    # Create a condition variable to synchronize the receiver and player threads.
    # In python, this implicitly creates a mutex lock too.
    # See: https://docs.python.org/2/library/threading.html#condition-objects
    cond_filled = threading.Condition()

    # Create a TCP socket and try connecting to the server.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect((sys.argv[1], int(sys.argv[2])))

    # Create a thread whose job is to receive messages from the server.
    recv_thread = threading.Thread(
        target=recv_thread_func,
        args=(wrap, cond_filled, sock)
    )
    recv_thread.daemon = True
    recv_thread.start()

    # Create a thread whose job is to play audio file data.
    dev = ao.AudioDevice('pulse')
    play_thread = threading.Thread(
        target=play_thread_func,
        args=(wrap, cond_filled, dev)
    )
    play_thread.daemon = True
    play_thread.start()

    # Enter our never-ending user I/O loop.  Because we imported the readline
    # module above, raw_input gives us nice shell-like behavior (up-arrow to
    # go backwards, etc.).
    global ARROW_LOCK
    while True:
        if ARROW_LOCK == False:
            line = raw_input('>> ')
            args = None
            if ' ' in line:
                cmd, args = line.split(' ', 1)
            else:
                cmd = line

            # TODO: Send messages to the server when the user types things.
            if cmd in ['l', 'list']:
                print 'The user asked for list.'
                ARROW_LOCK = True
                message = 'LIST{}'.format(EOM)
                sock.sendall(message)
            if cmd in ['p', 'play']:
                if args is None or not args.isdigit():
                    print("Please type in a valid song ID to play")
                    continue
                print 'The user asked to play:', args
                ARROW_LOCK = True
                message = 'STOP {}{}'.format(args, EOM)
                sock.sendall(message)
                IS_PLAYING = False
                cond_filled.acquire()
                wrap.data = ""
                cond_filled.release()
                sleep(1)
                NUM_AUDIO_MSGS_RECV = 0
                IS_PLAYING = True
                message = 'PLAY {}{}'.format(args, EOM)
                sock.sendall(message)
            if cmd in ['s', 'stop']:
                print 'The user asked for stop.'
                message = 'STOP {}{}'.format(args, EOM)
                sock.sendall(message)
                IS_PLAYING = False
                cond_filled.acquire()
                wrap.data = ""
                cond_filled.release()
                sleep(1)
                NUM_AUDIO_MSGS_RECV = 0
            if cmd in ['quit', 'q', 'exit']:
                cond_filled.acquire()
                wrap.data = ""
                cond_filled.release()
                sleep(2)
                sys.exit(0)

if __name__ == '__main__':
    main()
