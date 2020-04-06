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
"""
Provide functions to normalize text strings by converting to lowercase, removing noisewords.   
This is used by the lookup functions and the database build functions and match scoring  
 
noise_words is a list of replacements only used for match scoring   
phrase_cleanup is a list of replacements for db build, lookup and match scoring   
"""
import functools
from re import sub
import sys

import unidecode

from geodata import GeodataBuild, Loc, GeoUtil

# Todo -  make all of these list driven

CACHE_SIZE = 16384


stop_words = {
    # list of stop words
    # These are forced to sort at end of Soundex name so that search for 'north pinewood' can be done as 'pinewood%' and
    # will find 'pinewood north'
    'east',
    'west',
    'north',
    'south',
    'the',
    'of',
    'town',
    'city',
    'county',
    'and',
    'on',
    'by',
    'new',
    'old',
    'big',
    'little',
    'royal',
    'borough',
    'department',
    'region',
    }

scoring_noise_words = [
    # apply this list of substitutions before match scoring
    # list of (Regex, Replacement) - sub applied 
    (r', ', ','),
    (r"normandy american ", 'normandie american '),
    (r'nouveau brunswick', ' '),
    (r'westphalia', 'westfalen'),
    (r' departement', ' department'),
    (r'royal borough of windsor and maidenhead', 'berkshire'),
    (r'regional municipality', 'county'),
    (r'kathedrale', 'cathedral'),
    (r"l'", ''),
    (r'citta metropolitana di ', ' '),
    (r'kommune', ''),
    (r"politischer bezirk ", ' '),
    (r'erry', 'ury'),
    (r'ery', 'ury'),
    (r'borg', 'burg'),
    (r'bourg', 'burg'),
    (r'urgh', 'urg'),
    (r'mound', 'mund'),
    (r'ourne', 'orn'),
    (r'ney', 'ny'),
    (r'region', ' '),
    (r'abbey', 'abbey'),
    (r'priory', 'abbey'),
    (r' de ', ' '),
    (r' di ', ' '),
    (r' du ', ' '),
    (r' of ', ' '),
    ]


phrase_cleanup = [
    # Phrase cleanup - apply these replacements for database build, lookup, and match score 
    # list of (Regex, Replacement) - sub applied 
    (r'  +', ' '),  # Strip multiple space to single space
    (r'^mt ', 'mount '),
    (r'r\.k\. |r k ', 'roman catholic '),
    (r'rooms katholieke ', 'roman catholic '),
    (r'sveti |saints |sainte |sint |saint |sankt |st\. ', 'st '),  # Normalize Saint to St
    (r' co\.', ' county'),  # Normalize County
    (r'united states of america', 'usa'),  # Normalize to USA   begraafplaats
    (r'united states', 'usa'),  # Normalize to USA
    (r'cimetiere', 'cemetery'),  # cimetière
    (r'begraafplaats', 'cemetery'),  # 
    (r'town of ', ''),  # - remove town of
    (r'city of ', ''),  # - remove city of
    (r'county of ([^,]+)', r'\g<1> county'),  # Normalize 'Township of X' to 'X Township'
    (r'township of ([^,]+)', r'\g<1> township'),  # Normalize 'Township of X' to 'X Township'
    (r'cathedral of ([^,]+)', r'\g<1> cathedral'),  # Normalize 'Township of X' to 'X Township'
    (r'palace of ([^,]+)', r'\g<1> palace'),  # Normalize 'Township of X' to 'X Township'
    (r'castle of ([^,]+)', r'\g<1> castle'),  # Normalize 'Township of X' to 'X Township'
    (r',castle', ' castle'),  # -  remove extra comma
    (r',palace', ' palace'),  # -  remove extra comma
    (r"'(\w{2,})'", r"\g<1>"),  # remove single quotes around word, but leave apostrophe
    ]


local_country_names = {
    # Dictionary of key=local name, val = english name for country
    'norge'       : 'norway',
    'sverige'     : 'sweden',
    'osterreich'  : 'austria',
    'belgie'      : 'belgium',
    'brasil'      : 'brazil',
    'danmark'     : 'denmark',
    'eire'        : 'ireland',
    'magyarorszag': 'hungary',
    'italia'      : 'italy',
    'espana'      : 'spain',
    'deutschland' : 'germany',
    'prussia'     : 'germany',
    'suisse'      : 'switzerland',
    'schweiz'     : 'switzerland',
    }

ALIAS_FEAT = 2
ALIAS_ISO = 1
ALIAS_NAME = 0

alias_list = {
    # Dictionary of key=local name, val = (english name, iso, feature) for country, province, county
    'norge'               : ('norway', '', 'ADM0'),
    'sverige'             : ('sweden', '', 'ADM0'),
    'osterreich'          : ('austria', '', 'ADM0'),
    'belgie'              : ('belgium', '', 'ADM0'),
    'brasil'              : ('brazil', '', 'ADM0'),
    'danmark'             : ('denmark', '', 'ADM0'),
    'eire'                : ('ireland', '', 'ADM0'),
    'magyarorszag'        : ('hungary', '', 'ADM0'),
    'italia'              : ('italy', '', 'ADM0'),
    'espana'              : ('spain', '', 'ADM0'),
    'deutschland'         : ('germany', '', 'ADM0'),
    'prussia'             : ('germany', '', 'ADM0'),
    'suisse'              : ('switzerland', '', 'ADM0'),
    'schweiz'             : ('switzerland', '', 'ADM0'),

    'bayern'              : ('bavaria', 'de', 'ADM1'),
    'westphalia'          : ('westfalen', 'de', 'ADM1'),

    'normandy'            : ('normandie', 'fr', 'ADM1'),
    'brittany'            : ('bretagne', 'fr', 'ADM1'),
    'burgundy'            : ('bourgogne franche comte', 'fr', 'ADM1'),
    'franche comte'       : ('bourgogne franche comte', 'fr', 'ADM1'),
    'aquitaine'           : ('nouvelle aquitaine', 'fr', 'ADM1'),
    'limousin'            : ('nouvelle aquitaine', 'fr', 'ADM1'),
    'poitou charentes'    : ('nouvelle aquitaine', 'fr', 'ADM1'),
    'alsace'              : ('grand est', 'fr', 'ADM1'),
    'champagne ardenne'   : ('grand est', 'fr', 'ADM1'),
    'lorraine'            : ('grand est', 'fr', 'ADM1'),
    'languedoc roussillon': ('occitanie', 'fr', 'ADM1'),
    'nord pas de calais'  : ('hauts de france', 'fr', 'ADM1'),
    'picardy'             : ('hauts de france', 'fr', 'ADM1'),
    'auvergne'            : ('auvergne rhone alpes', 'fr', 'ADM1'),
    'rhone alpes'         : ('auvergne rhone alpes', 'fr', 'ADM1'),

    'breconshire'         : ('sir powys', 'gb', 'ADM2'),
    }


@functools.lru_cache(maxsize=CACHE_SIZE)
def normalize(text: str, remove_commas: bool) -> str:
    """
    Normalize text - Convert to lowercase ascii, remove most punctuation, apply replacements in phrase_cleanup list
    Remove commas if parameter set.   
    Remove all non alphanumeric except $ and *  
    Then call _phrase_normalize() which normalizes common phrases with multiple spellings, such as saint to st   
    #Args:   
        text:  Text to normalize   
        remove_commas:   True if commas should be removed   

    #Returns:   
        Normalized text

    """
    # Convert UT8 to ascii
    text = unidecode.unidecode(text)
    text = str(text).lower()

    # remove all non alphanumeric except $ and * and comma(if flag set)
    if remove_commas:
        text = sub(r"[^a-z0-9 $*']+", " ", text)
    else:
        text = sub(r"[^a-z0-9 $*,']+", " ", text)

    text = _phrase_normalize(text)
    return text.strip()


@functools.lru_cache(maxsize=CACHE_SIZE)
def normalize_for_scoring(text: str) -> str:
    """
        Normalize the text for closeness scoring.  Apply normal normalization and then replacements for scoring_noise_words

    #Args:
        text: text to normalize
    #Returns:

    """
    text = normalize(text=text, remove_commas=False)
    text = _remove_noise_words(text)
    return text


def _phrase_normalize(text: str) -> str:
    """ Strip spaces and normalize spelling for items such as Saint and County """
    # Replacement patterns to clean up entries

    for pattern, replace in phrase_cleanup:
        text = sub(pattern, replace, text)

    return text


def admin1_normalize(admin1_name: str, iso):
    """ Normalize historic or colloquial Admin1 names to current geoname standard """
    admin1_name = normalize(admin1_name, False)
    if iso == 'de':
        admin1_name = sub(r'bayern', 'bavaria', admin1_name)
        admin1_name = sub(r'westphalia', 'westfalen', admin1_name)
    elif iso == 'fr':
        admin1_name = sub(r'normandy', 'normandie', admin1_name)
        admin1_name = sub(r'brittany', 'bretagne', admin1_name)
        admin1_name = sub(r'burgundy', 'bourgogne franche comte', admin1_name)
        admin1_name = sub(r'franche comte', 'bourgogne franche comte', admin1_name)
        admin1_name = sub(r'aquitaine', 'nouvelle aquitaine', admin1_name)
        admin1_name = sub(r'limousin', 'nouvelle aquitaine', admin1_name)
        admin1_name = sub(r'poitou charentes', 'nouvelle aquitaine', admin1_name)
        admin1_name = sub(r'alsace', 'grand est', admin1_name)
        admin1_name = sub(r'champagne ardenne', 'grand est', admin1_name)
        admin1_name = sub(r'lorraine', 'grand est', admin1_name)
        admin1_name = sub(r'languedoc roussillon', 'occitanie', admin1_name)
        admin1_name = sub(r'midi pyrenees', 'occitanie', admin1_name)
        admin1_name = sub(r'nord pas de calais', 'hauts de france', admin1_name)
        admin1_name = sub(r'picardy', 'hauts de france', admin1_name)
        admin1_name = sub(r'auvergne', 'auvergne rhone alpes', admin1_name)
        admin1_name = sub(r'rhone alpes', 'auvergne rhone alpes', admin1_name)
    elif iso == 'ca':
        admin1_name = sub(r'brunswick', 'brunswick*', admin1_name)

    return admin1_name


def admin2_normalize(admin2_name: str, iso) -> (str, bool):
    """
        Normalize historic or colloquial Admin2 names to standard

    Args:
        admin2_name: 
        iso: 

    Returns: TUPLE (result, modified) - result is new string, modified - True if modified

    """
    admin2_name = normalize(admin2_name, False)

    mod = False

    if iso == 'gb':
        admin2_name = sub(r'breconshire', 'sir powys', admin2_name)
        mod = True

    return admin2_name, mod


def country_normalize(country_name) -> (str, bool):
    """
    normalize local language Country name to standardized English country name for lookups
    :param country_name:
    :return: (result, modified)
    result - new string
    modified - True if modified
    """
    country_name = sub(r'\.', '', country_name)  # remove .

    if local_country_names.get(country_name):
        country_name = local_country_names.get(country_name)
        return country_name.strip(' '), True
    else:
        return country_name.strip(' '), False


def feature_normalize(feature, name, pop: int):
    # Set city feature based on population and cleanup features for RUIN and HSTS
    feat = feature
    if 'PP' == feat[0:2] or feat in {'HSTS', 'RUIN', 'AREA'}:
        # Create new Feature codes based on city population
        if pop > 1000000 and 'PP' == feat[0:2]:
            feat = 'PP1M'
        elif pop > 100000 and 'PP' == feat[0:2]:
            feat = 'P1HK'
        elif pop > 10000 and 'PP' == feat[0:2]:
            feat = 'P10K'
    
        if feat == 'AREA':
            if 'island' in name:
                feat = 'ISL'
    
        # Set feature type for Abbey/Priory, Castle, and Church if feature is RUIN or HSTS and name matches
        if feat == 'HSTS' or feat == 'RUIN':
            if 'abbey' in name :
                feat = 'MSTY' 
            elif 'priory' in name:
                feat = 'MSTY' 
            elif 'castle' in name:
                feat = 'CSTL'
            elif 'church' in name:
                feat = 'CH' 
                
    return feat


def stop_words_last(item):
    """
    key function for sorting - return key but force stop words to sort last
    Stop words come from Normalize.stop_words
    Args:
        item: 

    Returns:
        key for item, with stop words forced last
    """
    if item in stop_words:
        # Force stop words to sort last.  { will sort last
        return '{' + item
    return item

def sorted_normalize(text):
    # Remove l' and d'  
    text = sub(r"l\'", "", text)
    text = sub(r"d\'", "", text)

    # Modify phrase X of Y to be Y X.  County of Whitley becomes Whitley County
    text = sub('([^,]+) of ([^,]+)', r'\g<2> \g<1>', text)

    # Force stop words to sort at end of list so wildcard will find phrases without them  (East, West, North, South)
    # North Haden becomes Haden North and Haden% will match it.
    word_list = sorted(text.split(' '), key=stop_words_last)
    return word_list


def _remove_noise_words(text: str):
    # Calculate score with noise words removed    
    for pattern, replace in scoring_noise_words:
        text = sub(pattern, replace, text)
    return text


def remove_aliase(input_words, res_words) -> (str, str):
    if "middlesex" in input_words and "greater london" in res_words:
        input_words = sub('middlesex', 'greater london', input_words)
    return input_words, res_words


def add_aliases_to_db(geo_build: GeodataBuild):
    #  Add alias names to DB
    for ky in alias_list:
        add_alias_to_db(ky, geo_build)


def add_alias_to_db(ky: str, geo_build: GeodataBuild):
    alias_row = alias_list.get(ky)
    place = Loc.Loc()
    place.country_iso = alias_row[ALIAS_ISO].lower()
    place.city = alias_row[ALIAS_NAME]
    place.feature = alias_row[ALIAS_FEAT]
    place.place_type = Loc.PlaceType.CITY

    # Lookup main entry and get GEOID
    geo_build.geodb.s.lookup_place(place)
    if len(place.georow_list) > 0:
        if len(place.georow_list[0]) > 0:
            geo_row = list(place.georow_list[0][0:GeoUtil.Entry.SDX + 1])
            geo_build.update_geo_row_name(geo_row=geo_row, name=ky)
            geo_tuple = tuple(geo_row)
            geo_build.insert(geo_tuple=geo_tuple, feat_code=alias_row[ALIAS_FEAT])

def deb(msg=None):
    # Display debug message with line number
    print(f"Debug {sys._getframe().f_back.f_lineno}: {msg if msg is not None else ''}")

