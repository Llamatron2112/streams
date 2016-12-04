import http
from http.client import error

import urllib
from urllib import request, error

import re

import mimetypes

from plparser import PlaylistParser
from constants import AUDIO_TYPES, PL_TYPES, HLS_TYPES
from dig import dig
from metadata import fetch_gst, fetch_ffmpeg
from plselect import playlist_selecter

FFMPEG = False


class Station:
    def __init__(self, app, location, db, parent, file=False):
        self.db = db
        self.app = app
        self.add_station(location, parent, file)

    def add_station(self, location, parent=None, file=False):

        if file:
            mime = mimetypes.guess_type(location)
            if mime[0] in HLS_TYPES:
                self.app.popup("HLS streams can't be added from a file\n\nPlease copy/paste the link")
                return

            file = open(location, "r")
            data = file.read()
            file.close()
            self.add_playlist(location, data, mime[0], None, True)

        else:
            content_type = None
            response = None
            try:
                response = urllib.request.urlopen(location)
                info = response.info()
                content_type = info.get_content_type()

            except urllib.error.HTTPError as err:
                self.app.httperror_popup(err)
                return

            except http.client.BadStatusLine as err:
                if err.line == 'ICY 200 OK\r\n':
                    self.add_url(location, parent)
                    return

            if content_type in PL_TYPES:
                data = str(response.read(), "utf-8")
                response.close()
                self.add_playlist(location, data, content_type, parent, False)

            elif content_type in AUDIO_TYPES:
                response.close()
                self.add_url(location, parent)

            elif content_type in HLS_TYPES:
                response.close()
                self.add_hls(location, parent)

            else:
                response.close()
                self.app.popup("Unknown content type: {}".format(content_type))

    def add_url(self, url, parent=None):
        infos = Station.fetch_infos(self, url)
        infos.append(False)
        infos.append(400)
        infos[1] = url
        self.db.append(parent, infos)
        return

    def add_hls(self, url, parent=None):
        infos = str(urllib.request.urlopen(url).read(), "utf-8")
        br = re.findall(r"BANDWIDTH=(\d*)", infos)
        bitrate = int(br[0]) / 1000
        cod = re.findall(r"CODECS=\"(.*)\"", infos)
        codec = cod[0]
        row = (url, url, "", "", codec, bitrate, "", False, 400)
        self.db.append(parent, row)
        return

    def add_playlist(self, location, data, mime, parent=None, file=False):
        match = PlaylistParser().parse(data, mime)

        if len(match) > 1:
            response = playlist_selecter(self.app.window, match, file)
            if type(response) is tuple:
                if response[0] is not None:
                    par_row = [response[0], "", "", "", "", "", "", True, 700]
                    par = self.db.append(None, par_row)
                else:
                    par = None
                for row in response[1]:
                    self.add_station(row, par)

            elif response == "cancel":
                return

            elif response == "keep":
                self.add_url(location, parent)

        elif len(match) == 1 and not file:
            self.add_url(location, parent)

        elif len(match) == 1 and file:
            self.add_url(match[0][1], parent)

        return

    def fetch_infos(self, url):
        server_url = dig(self, url, True)
        if re.match("error: .*", server_url):
            self.app.popup(server_url)
            return

        if FFMPEG:
            data = fetch_ffmpeg(server_url)
        else:
            data = fetch_gst(server_url)

        data[1] = url
        return data
