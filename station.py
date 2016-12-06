import http
from http.client import error

import urllib
from urllib import request, error

import mimetypes

from plparser import PlaylistParser
from constants import AUDIO_TYPES, PL_TYPES
from tools import get_metadata, get_audio_url
from plselect import playlist_selecter


class Station:
    def __init__(self, app, location, parent, file=False):
        self.app = app
        self.row = None

        self._add_station(location, parent, file)

    def _add_station(self, location, parent=None, file=False):

        if file:
            mime = mimetypes.guess_type(location)
            if mime[0] in AUDIO_TYPES:
                self.app.popup("Can't be added from a local file\n\nPlease copy/paste the link")
                return

            file = open(location, "r")
            data = file.read()
            file.close()
            self._add_playlist(location, data, mime[0], None, True)

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
                    self._add_url(location, parent)
                    return

            if content_type in PL_TYPES:
                data = str(response.read(), "utf-8")
                response.close()
                self._add_playlist(location, data, content_type, parent, False)

            elif content_type in AUDIO_TYPES:
                response.close()
                self._add_url(location, parent)

            else:
                response.close()
                self.app.popup("Unknown content type: {}".format(content_type))

    def _add_url(self, url, parent=None):
        infos = get_metadata(get_audio_url(url))
        infos.append(False)
        infos.append(400)
        infos[1] = url
        self.app.db.add_row(parent, infos)
        return

    def _add_playlist(self, location, data, mime, parent=None, file=False):
        match = PlaylistParser().parse(data, mime)

        if len(match) > 1:
            response = playlist_selecter(self.app.window, match, file)
            if type(response) is tuple:
                if response[0] is not None:
                    par = self.app.db.add_folder(response[0])
                else:
                    par = None
                for row in response[1]:
                    self._add_station(row, par)

            elif response == "cancel":
                return

            elif response == "keep":
                self._add_url(location, parent)

        elif len(match) == 1 and not file:
            self._add_url(location, parent)

        elif len(match) == 1 and file:
            self._add_url(match[0][1], parent)

        elif match is None or len(match) == 0:
            raise RuntimeError("Empty playlist")

        return

