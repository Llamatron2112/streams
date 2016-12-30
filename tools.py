import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GstPbutils", "1.0")
from gi.repository import GstPbutils

import http
from http.client import error

import urllib
from urllib import request

import re

from plparser import PlaylistParser
from plselect import playlist_selecter
from constants import AUDIO_TYPES, PL_TYPES


FOLLOW_LINK_LIMIT = 5


def get_next_url(app, url):
    r = urllib.request.urlopen(url)
    mime = r.info().get_content_type()

    if mime in AUDIO_TYPES:
        r.close()
        return url
    elif mime in PL_TYPES:
        data = str(r.read(), "utf-8")
        r.close()
        match = PlaylistParser().parse(data, mime)
        if len(match) > 1:
            result = playlist_selecter(app, match)
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


def get_audio_url(url):
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
                raise RuntimeError("Couldn't find an URL")

        if content_type in AUDIO_TYPES:
            break

        if new_url == "fresh":
            raise RuntimeError("No new URL")

        i += 1

    if i == 5:
        raise RuntimeError("Reached max iterations amount while getting audio url")

    return url


def get_metadata(url):
    audio_url = get_audio_url(url)
    info = GstPbutils.Discoverer().discover_uri(audio_url)

    name = ""
    genres = ""
    web = ""

    tags = info.get_tags()
    n = tags.n_tags()
    for i in range(0, n):
        tag = tags.nth_tag_name(i)
        value = tags.get_string(tag)[1]
        print(i, ":", tag, "→", value)
        if tag == "organization":
            name = value
        elif tag == "genre":
            genres = value
        elif tag == "location":
            web = value

    stream_list = info.get_stream_list()
    audio_stream = stream_list[0]
    bitrate = str(int(audio_stream.get_bitrate() / 1000))
    sample = str(audio_stream.get_sample_rate())

    caps = audio_stream.get_caps()
    codec = GstPbutils.pb_utils_get_codec_description(caps)

    if bitrate == "0" or name == "" or genres == "" or web == "":
        try:
            req = urllib.request.urlopen(audio_url)
            head = req.info()
            req.close()
        except http.client.BadStatusLine:
            pass
        else:
            for tag in head.items():
                match = re.match(r"ic[ey]-([a-z]+)", tag[0])
                if match:
                    print(match.group(1) + ": " + tag[1])
                    tagname = match.group(1)
                    tagvalue = tag[1]
                    if tagname == "br" or tagname == "bitrate":
                        bitrate = tagvalue
                    elif tagname == "name":
                        name = tagvalue
                    elif tagname == "genre":
                        genres = tagvalue
                    elif tagname == "url":
                        web = tagvalue

    if bitrate == "0":
        bitrate = "N/A"

    if name == "":
        name = url

    dat = [name, url, genres, web, codec, bitrate, sample]

    return dat

