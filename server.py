# !/usr/bin/env python

import os
import socket
import struct
import sys
from threading import Lock, Thread
from signal import signal, SIGPIPE, SIG_IGN
import errno

QUEUE_LENGTH = 10
SEND_BUFFER = 4096
EOL = ' END '
EOM = 'END'
URL = '127.0.0.1'
# URL = '0.0.0.0'

# per-client struct
class Client:
    def __init__(self, song_list, music_dir, conn):
        self.lock = Lock()
        self.conn = conn
        self.message_queue = []
        self.song_list = song_list
        self.music_dir = music_dir
        self.song_name = None
        self.keep_playing = False
        self.list_req_while_playing = False

# TODO: Thread that sends music and lists to the client.  All send() calls
# should be contained in this function.  Control signals from client_read could
# be passed to this thread through the associated Client object.  Make sure you
# use locks or similar synchronization tools to ensure that the two threads play
# nice with one another!

def list_songs(song_list, conn):
    formatted_list = []
    i = 0
    for song in song_list:
        formatted_list.append("{}. {}{}".format(i + 1, song[:-4], EOL))
        i += 1
    curr_buff_size = 0
    songs_counted = 0
    formatted_list_size = len(formatted_list)
    packaged_songs = ""
    just_sent = False
    for song in formatted_list:
        song_size = len(song)
        if curr_buff_size + song_size <= SEND_BUFFER:
            packaged_songs += song
            curr_buff_size += song_size
            just_sent = False
            songs_counted += 1
        else:
            outgoing_message = "RESP 100{}".format(EOL) + packaged_songs + EOM
            try:
                conn.sendall(outgoing_message)
            except client.conn.error, e:
                if e.errno == errno.EPIPE:
                    print("Error: Client has disconnected.")
                else:
                    print("Error: {}".format(e))
                break
            packaged_songs = ""
            curr_buff_size = 0
            just_sent = True
        if songs_counted == len(formatted_list) and just_sent == False:
            outgoing_message = "RESP 100{}".format(EOL) + packaged_songs + EOM
            try:
                conn.sendall(outgoing_message)
            except client.conn.error, e:
                if e.errno == errno.EPIPE:
                    print("Error: Client has disconnected.")
                else:
                    print("Error: {}".format(e))
                break

    return False

def client_write(client):
    while True:
        while client.message_queue:
            client.lock.acquire()
            command = client.message_queue.pop(0)
            client.lock.release()
            if command == "list":
                client.list_req_while_playing = list_songs(client.song_list, client.conn)
            elif command == "play":
                if client.song_name:
                    with open(client.music_dir + client.song_name, "r") as song_file:
                        data = song_file.read(SEND_BUFFER)
                        while data and client.keep_playing == True:
                            if client.list_req_while_playing == True:
                                client.list_req_while_playing = list_songs(client.song_list, client.conn)
                            outgoing_message = "RESP 200{}".format(EOL) + data + EOL + EOM
                            try:
                                client.conn.sendall(outgoing_message)
                            except client.conn.error, e:
                                if e.errno == errno.EPIPE:
                                    print("Error: Client has disconnected.")
                                else:
                                    print("Error: {}".format(e))
                                break
                            data = song_file.read(SEND_BUFFER)

# TODO: Thread that receives commands from the client.  All recv() calls should
# be contained in this function.
def client_read(client):
    received_data = client.conn.recv(SEND_BUFFER)
    while received_data:
        client.lock.acquire()
        if 'LIST' == received_data[0:4]:
            client.message_queue.append("list")
            client.list_req_while_playing = True
        elif 'PLAY' == received_data[0:4]:
            client.message_queue.append("play")
            client.keep_playing = True
            if received_data.split(" ")[1].isdigit():
                mySongID = int(received_data.split(" ")[1])
                if mySongID <= len(client.song_list) and mySongID > 0:
                    client.song_name = client.song_list[mySongID-1]
                else:
                    client.song_name = None
                    err_message = "ERRO 404{}{}".format(EOL,EOM)
                    try:
                        client.conn.sendall(err_message)
                    except client.conn.error, e:
                        if e.errno == errno.EPIPE:
                            print("Error: Client has disconnected.")
                        else:
                            print("Error: {}".format(e))
                        break
        elif 'STOP' == received_data[0:4]:
            client.keep_playing = False
        client.lock.release()
        received_data = client.conn.recv(SEND_BUFFER)

def get_mp3s(musicdir):
    print("Reading music files...")
    songs = []
    for filename in os.listdir(musicdir):
        if filename.endswith(".mp3"):
        # TODO: Store song metadata for future use.  You may also want to build
        # the song list once and send to any clients that need it.
            songs.append(filename)
    print("Found {0} song(s)!".format(len(songs)))
    return songs

def main():
    if len(sys.argv) != 3:
        sys.exit("Usage: python server.py [port] [musicdir]")
    if not os.path.isdir(sys.argv[2]):
        sys.exit("Directory '{0}' does not exist".format(sys.argv[2]))

    port = int(sys.argv[1])
    music_dir = sys.argv[2]
    if not music_dir.endswith("/"):
        music_dir = music_dir + "/"
    song_list = get_mp3s(sys.argv[2])
    threads = []

    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SEND_BUFFER)
    s.bind((URL, port))
    s.listen(QUEUE_LENGTH)
    # TODO: create a socket and accept incoming connections
    while True:
        conn, addr = s.accept()
        client = Client(song_list, music_dir, conn)
        t = Thread(target=client_read, args=(client,))
        threads.append(t)
        t.start()
        t = Thread(target=client_write, args=(client,))
        threads.append(t)
        t.start()
    s.close()


if __name__ == "__main__":
    main()
