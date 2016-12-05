import http
from http.client import error

import urllib
from urllib import request, error

from constants import AUDIO_TYPES, PL_TYPES, HLS_TYPES

from plparser import PlaylistParser
from plselect import playlist_selecter

FOLLOW_LINK_LIMIT = 5


def get_next_url(window, url):
    r = urllib.request.urlopen(url)
    mime = r.info().get_content_type()

    if (mime in AUDIO_TYPES) or (mime in HLS_TYPES):
        r.close()
        return url
    elif mime in PL_TYPES:
        data = str(r.read(), "utf-8")
        r.close()
        match = PlaylistParser().parse(data, mime)
        if len(match) > 1:
            result = playlist_selecter(window, match)
            if result == "cancel":
                return
            elif result == "keep":
                return url
            elif type(result) is tuple:
                res = []
                for row in result[1]:
                    res.append(row)
                return result[0], res

        elif len(match) == 1:
            return match[0][1]


def get_audio_url(window, url):
    new_url = "fresh"
    i = 0
    content_type = None
    while content_type not in AUDIO_TYPES and i < FOLLOW_LINK_LIMIT:

        if new_url != "fresh":
            url = new_url

        try:
            response = urllib.request.urlopen(url)
            info = response.info()
            content_type = info.get_content_type()
            print(content_type)
        except urllib.error.HTTPError as err:
            window.httperror_popup(err)
            return "error"
        except http.client.BadStatusLine as err:
            if err.line == "ICY 200 OK\r\n":
                print("ICY 200 OK")
                return url

        if content_type in PL_TYPES:
            data = str(response.read(), "utf-8")
            response.close()
            match = PlaylistParser().parse(data, content_type)
            new_url = match[0][1]
            if new_url is None:
                return "error: Couldn't find an URL"

        if content_type in AUDIO_TYPES:
            break

        if content_type in HLS_TYPES:
            return "error: HLS"

        if new_url == "fresh":
            # No new url
            return "error: No new URL"

        i += 1

    if i == 5:
        return "error"

    return url
