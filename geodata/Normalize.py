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
import re
import unidecode

from geodata import GeodataBuild, GeoUtil, Loc, GeoDB

# Todo - simplify and make these all list driven

noise_words= [
    # Noise words - Replacements -  used to calculate match similarity scoring
    (r', ', ','),
    (r"normandy american ", 'normandie american '),
    (r'nouveau brunswick', ' '),
    (r'westphalia', 'westfalen'),
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
    (r' de ', ' '),
    (r' di ', ' '),
    (r' du ', ' '),
    (r' of ', ' '),
    (r' departement', ' '),
    (r'royal borough of windsor and maidenhead', 'berkshire'),
    (r'regional municipality', 'county'),
    ]

phrase_cleanup = [
    # Phrase cleanup - replacements always applied (for database build, lookup, and match scoring)
    ('r\.k\. |r k ', 'rooms katholieke '),
    ('sveti |saints |sainte |sint |saint |sankt |st\. ', 'st '),  # Normalize Saint to St
    (r' co\.', ' county'),  # Normalize County
    (r'united states of america', 'usa'),  # Normalize to USA
    (r'united states', 'usa'),  # Normalize to USA
    (r'town of ', ''),  # - remove town of
    (r'city of ', ''),  # - remove city of
    (r'near ', ' '),  # - remove near
    (r'cimetiere', 'cemetery'),  # cimetière
    ('  +', ' '),  # Strip multiple space
    ('county of ([^,]+)', r'\g<1> county'),  # Normalize 'Township of X' to 'X Township'
    ('township of ([^,]+)', r'\g<1> township'),  # Normalize 'Township of X' to 'X Township'
    ('cathedral of ([^,]+)', r'\g<1> cathedral'),  # Normalize 'Township of X' to 'X Township'
    ('palace of ([^,]+)', r'\g<1> palace'),  # Normalize 'Township of X' to 'X Township'
    ('castle of ([^,]+)', r'\g<1> castle'),  # Normalize 'Township of X' to 'X Township'
    (r',castle', ' castle'),  # -  remove extra comma
    (r',palace', ' palace'),  # -  remove extra comma
    (r',cathedral', ' cathedral'),  # -  remove extra comma
    ]


def normalize_for_scoring(text: str, iso: str) -> str:
    """
        Normalize the title we use to determine how close a match we got. 
        See normalize() for details  
        Also remove noise words such as City Of

    #Args:
        text: text to normalize
        iso: ISO country code

    #Returns:

    """
    text = normalize(text, False)
    text = _remove_noise_words(text)
    return text

def normalize(text: str, remove_commas: bool) -> str:
    """
    Normalize text - Convert from UTF-8 to lowercase ascii.  
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
        text = re.sub(r"[^a-z0-9 $*']+", " ", text)
    else:
        text = re.sub(r"[^a-z0-9 $*,']+", " ", text)

    text = _phrase_normalize(text)
    return text.strip(' ')


def _phrase_normalize(text: str) -> str:
    """ Strip spaces and normalize spelling for items such as Saint and County """
    # Replacement patterns to clean up entries
    
    if 'amt' not in text:
        text = re.sub(r'^mt ', 'mount ', text)
        
    for pattern, replace in phrase_cleanup:
        text = re.sub(pattern, replace, text)

    return text

def _remove_noise_words(text: str):
    # Calculate score with noise words removed    
    for pattern, replace in noise_words:
        text = re.sub(pattern, replace, text)
    return text

def remove_aliase(input_words, res_words) -> (str, str):
    if "middlesex" in input_words and "greater london" in res_words:
        input_words = re.sub('middlesex', '', input_words)
        res_words = re.sub('greater london', '', res_words)
    return input_words, res_words


alias_list = {
    'norge': ('norway', '', 'ADM0'),
    'sverige': ('sweden', '', 'ADM0'),
    'osterreich': ('austria', '', 'ADM0'),
    'belgie': ('belgium', '', 'ADM0'),
    'brasil': ('brazil', '', 'ADM0'),
    'danmark': ('denmark', '', 'ADM0'),
    'eire': ('ireland', '', 'ADM0'),
    'magyarorszag': ('hungary', '', 'ADM0'),
    'italia': ('italy', '', 'ADM0'),
    'espana': ('spain', '', 'ADM0'),
    'deutschland': ('germany', '', 'ADM0'),
    'prussia': ('germany', '', 'ADM0'),
    'suisse': ('switzerland', '', 'ADM0'),
    'schweiz': ('switzerland', '', 'ADM0'),

    'bayern': ('bavaria', 'de', 'ADM1'),
    'westphalia': ('westfalen', 'de', 'ADM1'),

    'normandy': ('normandie', 'fr', 'ADM1'),
    'brittany': ('bretagne', 'fr', 'ADM1'),
    'burgundy': ('bourgogne franche comte', 'fr', 'ADM1'),
    'franche comte': ('bourgogne franche comte', 'fr', 'ADM1'),
    'aquitaine': ('nouvelle aquitaine', 'fr', 'ADM1'),
    'limousin': ('nouvelle aquitaine', 'fr', 'ADM1'),
    'poitou charentes': ('nouvelle aquitaine', 'fr', 'ADM1'),
    'alsace': ('grand est', 'fr', 'ADM1'),
    'champagne ardenne': ('grand est', 'fr', 'ADM1'),
    'lorraine': ('grand est', 'fr', 'ADM1'),
    'languedoc roussillon': ('occitanie', 'fr', 'ADM1'),
    'nord pas de calais': ('hauts de france', 'fr', 'ADM1'),
    'picardy': ('hauts de france', 'fr', 'ADM1'),
    'auvergne': ('auvergne rhone alpes', 'fr', 'ADM1'),
    'rhone alpes': ('auvergne rhone alpes', 'fr', 'ADM1'),

    'breconshire': ('sir powys', 'gb', 'ADM2'),
    }


def add_aliases_to_database(geo_files: GeodataBuild):
    #  Add alias names to DB
    place = Loc.Loc()
    for ky in alias_list:
        row = alias_list.get(ky)
        place.clear()

        # Create Geo_row
        # ('paris', 'fr', '07', '012', '12.345', '45.123', 'PPL')
        geo_row = [None] * GeoDB.Entry.MAX
        geo_row[GeoDB.Entry.FEAT] = row[2]
        geo_row[GeoDB.Entry.ISO] = row[1].lower()
        geo_row[GeoDB.Entry.LAT] = '99.9'
        geo_row[GeoDB.Entry.LON] = '99.9'
        geo_row[GeoDB.Entry.ADM1] = ''
        geo_row[GeoDB.Entry.ADM2] = ''

        geo_files.update_geo_row_name(geo_row=geo_row, name=ky)
        if row[2] == 'ADM1':
            geo_row[GeoDB.Entry.ADM1] = ky
            place.place_type = Loc.PlaceType.ADMIN1
        elif row[2] == 'ADM2':
            geo_row[GeoDB.Entry.ADM2] = ky
            place.place_type = Loc.PlaceType.ADMIN2
        else:
            place.place_type = Loc.PlaceType.COUNTRY
            place.country_name = ky

        place.country_iso = row[1]
        place.admin1_name = geo_row[GeoDB.Entry.ADM1]
        place.admin2_name = geo_row[GeoDB.Entry.ADM2]

        # Lookup main entry and get GEOID
        geo_files.geodb.lookup_place(place)
        if place.result_type in GeoUtil.successful_match and len(place.georow_list) > 0:
            geo_files.geodb.copy_georow_to_place(row=place.georow_list[0], place=place, fast=True)
            # place.format_full_nm(geodata.geo_files.output_replace_dct)

        geo_row[GeoDB.Entry.ID] = place.geoid

        geo_files.geodb.insert(geo_row=geo_row, feat_code=row[2])


def admin1_normalize(admin1_name: str, iso):
    """ Normalize historic or colloquial Admin1 names to current geoname standard """
    admin1_name = normalize(admin1_name, False)
    if iso == 'de':
        admin1_name = re.sub(r'bayern', 'bavaria', admin1_name)
        admin1_name = re.sub(r'westphalia', 'westfalen', admin1_name)

    if iso == 'fr':
        admin1_name = re.sub(r'normandy', 'normandie', admin1_name)
        admin1_name = re.sub(r'brittany', 'bretagne', admin1_name)
        admin1_name = re.sub(r'burgundy', 'bourgogne franche comte', admin1_name)
        admin1_name = re.sub(r'franche comte', 'bourgogne franche comte', admin1_name)
        admin1_name = re.sub(r'aquitaine', 'nouvelle aquitaine', admin1_name)
        admin1_name = re.sub(r'limousin', 'nouvelle aquitaine', admin1_name)
        admin1_name = re.sub(r'poitou charentes', 'nouvelle aquitaine', admin1_name)
        admin1_name = re.sub(r'alsace', 'grand est', admin1_name)
        admin1_name = re.sub(r'champagne ardenne', 'grand est', admin1_name)
        admin1_name = re.sub(r'lorraine', 'grand est', admin1_name)
        admin1_name = re.sub(r'languedoc roussillon', 'occitanie', admin1_name)
        admin1_name = re.sub(r'midi pyrenees', 'occitanie', admin1_name)
        admin1_name = re.sub(r'nord pas de calais', 'hauts de france', admin1_name)
        admin1_name = re.sub(r'picardy', 'hauts de france', admin1_name)
        admin1_name = re.sub(r'auvergne', 'auvergne rhone alpes', admin1_name)
        admin1_name = re.sub(r'rhone alpes', 'auvergne rhone alpes', admin1_name)

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
        admin2_name = re.sub(r'breconshire', 'sir powys', admin2_name)
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
    country_name = re.sub(r'\.', '', country_name)  # remove .

    natural_names = {
        'norge': 'norway',
        'sverige': 'sweden',
        'osterreich': 'austria',
        'belgie': 'belgium',
        'brasil': 'brazil',
        'danmark': 'denmark',
        'eire': 'ireland',
        'magyarorszag': 'hungary',
        'italia': 'italy',
        'espana': 'spain',
        'deutschland': 'germany',
        'prussia': 'germany',
        'suisse': 'switzerland',
        'schweiz': 'switzerland',

        }
    if natural_names.get(country_name):
        country_name = natural_names.get(country_name)
        return country_name.strip(' '), True
    else:
        return country_name.strip(' '), False
