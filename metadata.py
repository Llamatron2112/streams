import gi
gi.require_version("GstPbutils", "1.0")
from gi.repository import GstPbutils

import http
from http.client import error

import urllib
from urllib import request

import re


def get_metadata(url):
    info = GstPbutils.Discoverer().discover_uri(url)

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
            req = urllib.request.urlopen(url)
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

