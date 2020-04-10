#!/usr/bin/env python3
# -*- coding: utf-8 -*-

#  Copyright (c) 2019.       Mike Herbert
#
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
#   You should have received a copy of the GNU General Public License
#   along with this program; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301  USA
""" Utilities """
import collections
import logging
import os
import re
import sys
import time
from difflib import SequenceMatcher
from functools import wraps

import unidecode

street_patterns = [r'\d', ' street', ' avenue', ' road', 'rue ']


class Entry:
    # Database geodata table and admin table entries
    NAME = 0
    ISO = 1
    ADM1 = 2
    ADM2 = 3
    LAT = 4
    LON = 5
    FEAT = 6
    ID = 7
    SDX = 8
    PREFIX = 8  # Note - item 8 is overloaded:  Soundex in DB and Prefix in result
    SCORE = 9
    MAX = 9


class Result:
    # Result codes for lookup
    STRONG_MATCH = 9
    MULTIPLE_MATCHES = 8
    PARTIAL_MATCH = 7
    WORD_MATCH = 6
    WILDCARD_MATCH = 5
    SOUNDEX_MATCH = 4
    DELETE = 3
    NO_COUNTRY = 2
    NO_MATCH = 1
    NOT_SUPPORTED = 0


# Result types that are successful matches
successful_match = [Result.STRONG_MATCH, Result.PARTIAL_MATCH, Result.WILDCARD_MATCH, Result.WORD_MATCH,
                    Result.SOUNDEX_MATCH, Result.MULTIPLE_MATCHES]

Query = collections.namedtuple('Query', 'where args result')


class MultiRegex():
    """
    list of Regex statements.  MultiRegex.sub(text) will apply all regex substitutions
    """

    def __init__(self, regex):
        self.rgx = regex
        expression = []
        # Walk thru list and add each pattern as a Regex OR group
        for idx, item in enumerate(self.rgx):
            expression.append(f'(?P<G{idx}>{item[0]})')
        patt = '|'.join(expression)
        # print(f'patt = {patt}')
        self.patt = re.compile(f"{patt}")

    def sub(self, text: str, lower=True, set_ascii=True):
        """
        Apply regex substitutions in list
        Args:
            text: text to be modified
            lower: If True,  convert to lowercase before Regex
            set_ascii: If True, Convert unicode characters to ascii
        Returns:
            text as modified by Regex in dictionary
        """
        if set_ascii:
            text = unidecode.unidecode(text)

        if lower:
            text = text.lower()

        for m in self.patt.finditer(text):
            # print(m)
            if m.groupdict():
                for g in m.groupdict():
                    if m.group(g):
                        idx = int(g[1:])
                        # print(f'{self.rgx[idx]} {m.group(g)}')
                        # Re found a match, perform the substitution
                        text = re.sub(self.rgx[idx][0], self.rgx[idx][1], text)
            # print(m.groupdict())
        return text


def get_directory_name() -> str:
    """
    Returns: Name of geodata data directory where geonames.org files are
    """
    return "geoname_data"


def get_cache_directory(basepath):
    """ 
    Returns:  directory for geodata cache files including DB
    """
    return os.path.join(basepath, "cache")


def is_street(text) -> bool:
    # See if text looks like a street name
    for pattern in street_patterns:
        if bool(re.search(pattern, text)):
            return True
    return False


def set_debug_logging(msg):
    """
         Set up logging configuration for debug level 
    # Args:
        msg: Initial message to log
    """
    logger = logging.getLogger(__name__)
    fmt = "%(levelname)s %(name)s.%(funcName)s %(lineno)d: %(message)s"
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout, format=fmt)
    logger.info(msg)
    return logger


def set_info_logging(msg):
    """
         Set up logging configuration for info level 
    # Args:
        msg: Initial message to log
    """
    logger = logging.getLogger(__name__)
    fmt = "%(levelname)s %(name)s.%(funcName)s %(lineno)d: %(message)s"
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format=fmt)
    logger.info(msg)
    return logger


def _remove_matching_seq(text1: str, text2: str, attempts: int, min_len: int) -> (str, str):
    """
    Find largest matching sequence.  Remove it in text1 and text2.
            called by remove_matching_sequences which provides a wrapper
    Call recursively until attempts hits zero or there are no matches longer than 1 char
    :param text1:
    :param text2:
    :param attempts: Number of times to remove largest text sequence
    :return:
    """
    s = SequenceMatcher(None, text1, text2)
    match = s.find_longest_match(0, len(text1), 0, len(text2))
    if match.size >= min_len:
        # Remove matched sequence from inp and out
        item = text1[match.a:match.a + match.size]
        text2 = re.sub(item, '', text2, count=4)
        text1 = re.sub(item, '', text1, count=4)
        if attempts > 0:
            # Call recursively - get next largest match and remove it
            text1, text2 = _remove_matching_seq(text1, text2, attempts - 1, min_len)
    return text1, text2


def remove_matching_sequences(text1: str, text2: str, min_len: int) -> (str, str):
    """
    Find largest sequences that match between text1 and 2.  Remove them from text1 and text2.
    Matches will NOT include commas
    # Args:
        text1:
        text2:
        min_len: minimum length of match that will be removed
    Returns: text 1 and 2 with the largest text sequences in both removed
    """
    # Prepare strings for input to remove_matching_seq
    # Swap all commas in text2 string to '@'.  This way they will never match comma in text1 string
    # Ensures we don;t remove commas and don't match across tokens
    text2 = re.sub(',', '@', text2)
    text1, text2 = _remove_matching_seq(text1=text1, text2=text2, attempts=1, min_len=min_len)
    # Restore commas in text2
    text2 = re.sub('@', ',', text2)
    return text1.strip(' '), text2.strip(' ')


def _lowercase_match_group(matchobj):
    return matchobj.group().lower()


def capwords(text):
    """
    Change text to Title Case. Fixes the apostrophe handling problem with title() 
    """
    if text is not None:
        # Fix handling for contractions not handled correctly by title()
        poss_regex = r"(?<=[a-z])[\']([A-Z])"
        text = re.sub(poss_regex, _lowercase_match_group, text.title())

    return text


def get_feature_group(location: str):
    """
        Scan location name to see if it refers to a generic feature like cemetery or church,etc.
        This allows a database search by geonames.org feature type
        If any word in location is in feature list, return the word found and the feature group 
    Args:
        location: 

    Returns: (word, group) - feature word found, geonames.org feature group it is in

    """
    for word in location.split(' '):
        group = feature_mapping.get(word)
        if group:
            return word, group

    return '', ''


def timeit_wrapper(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()  # Alternatively, you can use time.process_time()
        func_return_val = func(*args, **kwargs)
        end = time.perf_counter()
        print('{0:<10}.{1:<8} : {2:<8}'.format(func.__module__, func.__name__, end - start))
        return func_return_val

    return wrapper


feature_list = ["ADM1", "ADM2", "ADM3", "ADM4", "ADMF", "AREA", "CH", "CSTL", "CMTY", "EST ", "HSP", "FT",
                "HSTS", "ISL", "MSQE", "MSTY", "MT", "MUS", "PAL", "PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4",
                "PPLC", "PPLG", "PPLH", "PPLL", "PPLQ", "PPLX", "PRK", "PRN", "PRSH", "RUIN", "RGN", "RLG", "STG",
                "SQR", "SYG", "VAL", "MNMT"]

feature_mapping = {
    # If location has item below, then derive its feature type
    'st'                            : 'RLG',
    'kapelle'                       : 'RLG',
    'chapel'                        : 'RLG',
    'kirche'                        : 'RLG',
    'kirke'                         : 'RLG',
    'church'                        : 'RLG',
    'eglise'                        : 'RLG',
    'cathedral'                     : 'RLG',
    'cathedrale'                    : 'RLG',
    'kathedrale'                    : 'RLG',
    'kanisat'                       : 'RLG',
    'iglesia'                       : 'RLG',
    'catedral'                      : 'RLG',
    'parroquia'                     : 'RLG',
    'chapelle'                      : 'RLG',
    'chiesa'                        : 'RLG',
    'cappella'                      : 'RLG',
    'basilica'                      : 'RLG',
    'cattedrale'                    : 'RLG',
    'mosque'                        : "RLG",
    'monastery'                     : "RLG",
    'synagogue'                     : "RLG",
    'abbey'                         : "RLG",
    'priory'                        : "RLG",

    'castle'                        : 'CSTL',
    'schloss'                       : 'CSTL',
    'chateau'                       : 'CSTL',
    'castell'                       : 'CSTL',
    'castillo'                      : 'CSTL',
    'castello'                      : 'CSTL',
    'kasteel'                       : 'CSTL',
    'zamek'                         : 'CSTL',
    'slott'                         : 'CSTL',

    'cemetery'                      : 'CMTY',
    'cimetiere'                     : 'CMTY',
    'cementerio'                    : 'CMTY',
    'cimitero'                      : 'CMTY',
    'rooms katholieke begraafplaats': 'CMTY',
    'begraafplaats'                 : 'CMTY',
    'gravlund'                      : 'CMTY',
    'kirkegard'                     : 'CMTY',
    'friedhof'                      : 'CMTY',

    'hospital'                      : 'HSP',
    'hopital'                       : 'HSP',
    'krankenhaus'                   : 'HSP',
    'ospedale'                      : 'HSP',

    'palace'                        : 'PAL',
    'palais'                        : 'PAL',

    'county'                        : 'ADM2',

    'island'                        : 'ISL',
    'isle'                          : 'ISL',
    'ile'                           : 'ISL',
    'ostrov'                        : 'ISL',
    'islet'                         : 'ISL',

    'mountain'                      : "MT",
    'museum'                        : "MUS",
    'park'                          : "PRK",
    'prison'                        : "PRN",
    'square'                        : "SQR",

    }

feature_names = {
    "AREA" : 'Area',
    "CH"   : 'Church',
    "CSTL" : 'Castle',
    "CMTY" : 'Cemetery',
    "EST"  : 'Estate',
    "HSP"  : 'Hospital',
    "HSTS" : 'Historical',
    "ISL"  : 'Island',
    "MT"   : 'Mountain',
    "MUS"  : 'Museum',
    "MSQE" : 'Mosque',
    "MSTY" : 'Monastery',
    "PAL"  : 'Palace',
    "PRK"  : 'Park',
    "PRN"  : 'Prison',
    "RUIN" : 'Ruin',
    "SQR"  : 'Square',
    "VAL"  : 'Valley',
    "ADM1" : 'State',
    "ADM2" : 'County',
    "ADM3" : 'Township',
    "ADM4" : 'Township',
    "PPL"  : 'City',
    "PPLA" : 'City',
    "PPLA2": 'City',
    "PPLA3": 'City',
    "PPLA4": 'City',
    "PPLC" : 'City',
    "PPLG" : 'City',
    "PPLH" : 'City',
    "PPLL" : 'Village',
    "PPLQ" : 'Historical',
    "PPLX" : 'Neighborhood',
    "SYG"  : 'Synagogue'
    }
