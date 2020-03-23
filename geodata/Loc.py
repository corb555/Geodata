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
"""    Holds the details about a Location: Name,state/province, etc as well as
    the lookup results """
import argparse
import logging
import re
from typing import List, Tuple

from geodata import GeoUtil, Normalize, ArgumentParserNoExit, GeoSearch, GeoDB


# What type of entity is this place?
class PlaceType:
    COUNTRY = 0
    ADMIN1 = 1
    ADMIN2 = 2
    CITY = 3
    PREFIX = 4
    ADVANCED_SEARCH = 5


place_type_name_dict = {
    PlaceType.COUNTRY        : 'Country',
    PlaceType.ADMIN1         : 'STATE/PROVINCE',
    PlaceType.ADMIN2         : 'COUNTY',
    PlaceType.CITY           : ' ',
    PlaceType.ADVANCED_SEARCH: ' '
    }


class Loc:
    """
    Holds the details about a Location: Name, county, state/province, country, lat/long as well as
    the lookup results
    Parses a name into Loc items (county, state, etc)
    """

    def __init__(self):
        """
        Init
        """
        self.logger = logging.getLogger(__name__)
        self.original_entry: str = ""
        self.lat: float = float('NaN')  # Latitude
        self.lon: float = float('NaN')  # Longitude
        self.country_iso: str = ""  # Country ISO code
        self.country_name: str = ''
        self.city: str = ""  # City or entity name
        self.admin1_name: str = ""  # Admin1 (State/province/etc)
        self.admin1_id: str = ""  # Admin1 Geoname ID
        self.admin2_name: str = ""  # Admin2 (county)
        self.admin2_id = ""  # Admin2 Geoname ID
        self.prefix: str = ""  # Prefix (entries prepended before geoname location)
        self.feature: str = ''  # Geoname feature code
        self.place_type: int = PlaceType.COUNTRY  # Is this a Country , Admin1 ,admin2 or city?
        self.geoid: str = ''  # Geoname GEOID
        self.enclosed_by = ''   # The entity that encloses this.  E.g United States encloses Texas
        self.updated_entry = ''
        self.score = 100.0

        # Lookup result info
        self.status: str = ""
        self.status_detail: str = ""
        self.result_type: int = GeoUtil.Result.NO_MATCH  # Result type of lookup
        self.result_type_text: str = ''  # Text version of result type
        self.georow_list: List = []  # List of items that matched this location
        self.event_year: int = 0
        self.geo_db = None

    def clear(self):
        # Place geo info
        self.original_entry: str = ""
        self.lat: float = float('NaN')  # Latitude
        self.lon: float = float('NaN')  # Longitude
        self.country_iso: str = ""  # Country ISO code
        self.country_name: str = ''
        self.city: str = ""  # City or entity name
        self.admin1_name: str = ""  # Admin1 (State/province/etc)
        self.admin2_name: str = ""  # Admin2 (county)
        self.admin1_id: str = ""  # Admin1 Geoname ID
        self.admin2_id = ""  # Admin2 Geoname ID
        self.prefix: str = ""  # Prefix (entries before city)
        self.feature: str = ''  # Geoname feature code
        self.place_type: int = PlaceType.COUNTRY  # Is this a Country , Admin1 ,admin2 or city?
        self.geoid: str = ''  # Geoname GEOID
        self.enclosed_by = ''
        self.updated_entry = ''
        self.score = 100.0

        # Lookup result info
        self.status: str = ""
        self.status_detail: str = ""
        self.result_type: int = GeoUtil.Result.NO_MATCH  # Result type of lookup
        self.result_type_text: str = ''  # Text version of result type
        self.georow_list: List[Tuple] = [()]  # List of items that matched this location

        self.georow_list.clear()

    def parse_place(self, place_name: str, geo_db:GeoDB.GeoDB):
        """
            Given a comma separated place name,   
            parse into its city, admin1, country and type of entity (city, country etc)   
        #Args:   
            place_name: The place name to parse   
            geo_files: GeodataBuild instance   
        #Returns:   
            Fields in Loc (city, adm1, adm2, iso) are updated based on parsing. self.status has Result status code   
        """
        self.geo_db = geo_db
        self.logger.debug(f'PARSE {place_name}\n')
        self.clear()
        self.original_entry = place_name

        # Convert open-brace and open-paren to comma.  close brace/paren will be stripped by normalize()
        name = re.sub(r'\[', ',', place_name)
        name = re.sub(r'\(', ',', name)

        tokens = name.split(",")
        if len(tokens[-1]) == 0:
            # Last item is blank, so remove it
            tokens = tokens[:-1]

        token_count = len(tokens)
        self.place_type = PlaceType.CITY

        # First, try to parse and validate State/Province, and Country from last two tokens  
        # If one other token, parse as city
        # If two other tokens, parse as city, admin2
        # First two tokens are also copied to prefix.
        # Place type is the leftmost item we found - either City, Admin2, Admin2, or Country
        # If '--' in name, then extract advanced search options 

        if '--' in place_name:
            # Advanced Search - Pull out filter flags if present
            self.logger.debug('filter')
            self.get_filter_parameters(place_name)
            return
        
        if token_count > 0:
            #  COUNTRY - right-most token should be country
            self.country_name = Normalize.normalize(tokens[-1], False)

            # Validate country
            #self.logger.debug(f'1) Find COUNTRY [{self.country_name}] *******')
            self.country_iso = geo_db.s.get_country_iso(self.georow_list, self.country_name, self)  # Get Country country_iso
            if self.country_iso != '':
                self.place_type = PlaceType.COUNTRY
            else:
                # Last token is not COUNTRY.
                # Append dummy token  so we now have <tokens>, x
                tokens.append('_')
                token_count = len(tokens)
                self.result_type = GeoUtil.Result.NO_COUNTRY
                self.country_name = ''
        if token_count > 1:
            #  See if 2nd to last token is Admin1
            val = tokens[-2]
            #self.logger.debug(f'ADM1 tkn-2 [{val}]')
            self.admin1_name = Normalize.admin1_normalize(val, self.country_iso)

            if len(self.admin1_name) > 0:
                # Lookup Admin1
                #self.logger.debug(f'2) Find ADMIN1 [{self.admin1_name}] *******')
                row_list = []
                geo_db.s.get_admin1_id(self.admin1_name, self, row_list)
                if self.admin1_id != '':
                    # Found Admin1
                    self.place_type = PlaceType.ADMIN1
                    self.georow_list = row_list
                    self.admin1_name = geo_db.s.get_admin1_name(self.admin1_id, self.country_iso)
                    #self.logger.debug(f'adm1 nm={self.admin1_name}')
                    self.result_type = GeoUtil.Result.PARTIAL_MATCH
                    # Get country if blank
                    row_list = []
                    if self.country_name == '':
                        self.country_name = geo_db.s.get_country_name(self.country_iso, row_list) 
                else:
                    # Last token is not Admin1 - append dummy token so we have <tokens>, admin1, country
                    self.admin1_name = ''
                    # Add dummy token for admin1 position
                    tokens.insert(-1, '_')
                    # token_count = len(tokens)
            else:
                tokens[-2] = '_'

        # Last two tokens are now Admin1, Country (although they may be '_')
        # If >2 tokens:  Put first non-blank token in City and in Prefix
        # If >3 tokens:  Put second non-blank token in Admin2 and also append to Prefix

        # Remove all blank tokens
        tokens = [x for x in tokens if x]
        token_count = len(tokens)

        if token_count >= 3:
            #  Possible Formats: City, Admin1, Country or  Admin2, Admin1, Country
            #  Take first tkn as city
            self.city = Normalize.normalize(tokens[0], False)
            self.place_type = PlaceType.CITY

            # Also place token[0] into Prefix
            if '*' not in tokens[0]:
                self.prefix = str(tokens[0].strip(' '))
                
        if token_count >= 4:
            #  Admin2 is 2nd.  Note -  if Admin2 isnt found, it will look it up as city
            
            if GeoUtil.is_street(tokens[-4].lower()):
                #  Format: Prefix, City, Admin1, Country
                self.city = Normalize.normalize(tokens[-3], False)
            else:
                #  Format: City, Admin2, Admin1, Country
                self.admin2_name = Normalize.normalize(tokens[-3], False)
                self.city = Normalize.normalize(tokens[-4], False)
                
            self.place_type = PlaceType.CITY

            # put token[0] and  token[1] into Prefix
            if '*' not in tokens[1]:
                self.prefix = str(tokens[0].strip(' ')) + ' ' + str(tokens[1].strip(' '))

        self.prefix = Normalize.normalize(self.prefix, False)
        row_list = []
        # fill in country name if still missing - finding Admin1 will find country ISO
        if self.country_name == '' and self.country_iso != '':
            self.country_name = geo_db.s.get_country_name(self.country_iso, row_list)

        self.logger.debug(f"    ======= PARSED: {place_name} \nCity [{self.city}] Adm2 [{self.admin2_name}]"
                          f" Adm1 [{self.admin1_name}] adm1_id [{self.admin1_id}] Cntry [{self.country_name}] Pref=[{self.prefix}]"
                          f" type_id={self.place_type}\n")
        return

    def get_filter_parameters(self, place_name):
        """
            Parse search parameters from place_name and place in appropriate fields.
            Place_name format is:  town, --feature=XXX,--iso=XXX
        # Args:   
            place_name: town, --feature=XXX,--iso=XXX   
        # Returns:   
            Loc fields updated: country_iso, and feature are updated   
        """
        # Separate out arguments
        tokens = place_name.split(",")
        args = []
        for tkn in tokens:
            if '--' in tkn:
                args.append(tkn.strip(' '))

        # Parse options in place name
        parser = ArgumentParserNoExit.ArgumentParserNoExit(description="Parses command.")
        parser.add_argument("-f", "--feature", help=argparse.SUPPRESS)
        parser.add_argument("-i", "--iso", help=argparse.SUPPRESS)
        parser.add_argument("-c", "--country", help=argparse.SUPPRESS)
        self.logger.debug(f'Args {args}' )

        try:
            options = parser.parse_args(args)
            self.city = Normalize.normalize(tokens[0], False)
            self.place_type = PlaceType.ADVANCED_SEARCH
            self.logger.debug(options)

            if options.iso:
                self.country_iso = options.iso.lower()
                self.logger.debug(f'iso {self.country_iso}')
            if options.country:
                self.country_iso = options.country.lower()
            if options.feature:
                self.feature = options.feature.upper()
                self.logger.debug(f'ft {self.feature}')
        except Exception as e:
            self.logger.debug(e)
            
        self.logger.debug(f"    ======= PARSE ADV: {place_name} \nCity [{self.city}] Adm2 [{self.admin2_name}]"
                          f" Adm1 [{self.admin1_name}] adm1_id [{self.admin1_id}] Cntry [{self.country_name}] Pref=[{self.prefix}]"
                          f" type_id={self.place_type} iso={self.country_iso} feat={self.feature}")

    def get_status(self) -> str:
        self.logger.debug(f'status=[{self.status}]')
        return self.status

    def set_types_as_string(self):
        # Ensure all items are string type
        self.city = str(self.city)
        self.admin1_name = str(self.admin1_name)
        self.admin2_name = str(self.admin2_name)
        self.prefix = str(self.prefix)

    def add_commas(self, txt) -> str:
        if txt == '':
                return ''
        else:
            return f'{txt}, '

    @staticmethod
    def lowercase_match_group(matchobj):
        return matchobj.group().lower()

    @staticmethod
    def capwords(nm):
        # Change from lowercase to Title Case but fix the title() apostrophe bug
        if nm is not None:
            # Use title(), then fix the title() apostrophe defect
            nm = nm.title()

            # Fix handling for contractions not handled correctly by title()
            poss_regex = r"(?<=[a-z])[\']([A-Z])"
            nm = re.sub(poss_regex, Loc.lowercase_match_group, nm)

        return nm

    def get_long_name(self, replace_dct) -> str:
        """
        Take the fields in a Place and build full name.  e.g.  city,adm2,adm1,country name   
        Prefix is NOT included.  Text also has replacements from dictionary applied   
        #Args:   
            replace_dct: Dictionary of text replacements.  'Regex':'replacement'   
        #Returns:  
            long name  
        """
        city = self.add_commas(self.city)
        admin2 = self.add_commas(self.admin2_name)
        admin1 = self.add_commas(self.admin1_name)

        if self.place_type == PlaceType.COUNTRY:
            nm = f"{self.country_name}"
        elif self.place_type == PlaceType.ADMIN1:
            nm = f"{admin1}{self.country_name}"
        elif self.place_type == PlaceType.ADMIN2:
            nm = f"{admin2}{admin1}{self.country_name}"
        else:
            nm = f"{city}{admin2}{admin1}{str(self.country_name)}"

        # normalize prefix
        self.prefix = Normalize.normalize(self.prefix, False)

        if len(self.prefix) > 0:
            self.prefix_commas = ', '
        else:
            self.prefix_commas = ''

        nm = Loc.capwords(nm)

        # Perform any text replacements user entered into Output Tab
        if replace_dct:
            for key in replace_dct:
                nm = re.sub(key, replace_dct[key], nm)

        return nm
    
    def get_display_name(self, replace_dct) -> str:
        """
        Take the fields in a Place and build full name.  See if alternate name is available
        e.g.  city,adm2,adm1,country name   
        Prefix is NOT included.  Text also has replacements from dictionary applied   
        #Args:   
            replace_dct: Dictionary of text replacements.  'Regex':'replacement'   
        #Returns:  
            long name  
        """
        
        # See if there is an alternate name for this
        #city, lang = self.geo_db.s.get_alternate_name(self.geoid)
        #if city == '':
        city = self.city
        city = self.add_commas(city)
        admin2 = self.add_commas(self.admin2_name)
        admin1 = self.add_commas(self.admin1_name)

        if self.place_type == PlaceType.COUNTRY:
            nm = f"{self.country_name}"
        elif self.place_type == PlaceType.ADMIN1:
            nm = f"{admin1}{self.country_name}"
        elif self.place_type == PlaceType.ADMIN2:
            nm = f"{admin2}{admin1}{self.country_name}"
        else:
            nm = f"{city}{admin2}{admin1}{str(self.country_name)}"

        # normalize prefix
        self.prefix = Normalize.normalize(self.prefix, False)

        if len(self.prefix) > 0:
            self.prefix_commas = ', '
        else:
            self.prefix_commas = ''

        nm = Loc.capwords(nm)

        # Perform any text replacements user entered into Output Tab
        if replace_dct:
            for key in replace_dct:
                nm = re.sub(key, replace_dct[key], nm)

        return nm

    def get_five_part_title(self):
        # Returns a five part title string and tokenized version:
        #     prefix,city,county,state,country  (prefix plus long name)

        # Normalize country name
        country, modified = Normalize.country_normalize(self.country_name)
        full_title = self.prefix + ' ,' + f"{self.city}, {self.admin2_name}, {self.admin1_name}, {str(country)}"
        return full_title

    def set_type_from_feature(self):
        # Set place type based on DB response feature code
        if self.feature == 'ADM0':
            self.place_type = PlaceType.COUNTRY
        elif self.feature == 'ADM1':
            self.place_type = PlaceType.ADMIN1
        elif self.feature == 'ADM2':
            self.place_type = PlaceType.ADMIN2
        else:
            self.place_type = PlaceType.CITY
        if len(self.prefix) > 0:
            self.place_type = PlaceType.PREFIX
        return self.place_type

    def set_place_type(self):
        # Set place type based on parsing results
        self.place_type = PlaceType.CITY
        if len(str(self.country_name)) > 0:
            self.place_type = PlaceType.COUNTRY
        if len(self.admin1_name) > 0:
            self.place_type = PlaceType.ADMIN1
        if len(self.admin2_name) > 0:
            self.place_type = PlaceType.ADMIN2
        if len(self.city) > 0:
            self.place_type = PlaceType.CITY

    def set_place_type_text(self):
        # Set result_type_text based on place type
        if self.result_type == GeoUtil.Result.NO_COUNTRY:
            self.result_type_text = 'Country'
        elif self.place_type == PlaceType.COUNTRY:
            self.result_type_text = 'Country'
        elif self.place_type == PlaceType.ADMIN1:
            self.result_type_text = self.get_district1_type(self.country_iso)
        elif self.place_type == PlaceType.ADMIN2:
            self.result_type_text = 'County'
        elif self.place_type == PlaceType.CITY:
            self.result_type_text = self.get_type_name(self.feature)
        elif self.place_type == PlaceType.PREFIX:
            self.result_type_text = 'Place'

    def remove_old_fields(self):
        # Remove fields that are unused by this place type
        if self.place_type == PlaceType.COUNTRY:
            # self.prefix = ''
            self.city = ''
            self.admin2_name = ''
            self.admin1_name = ''
        elif self.place_type == PlaceType.ADMIN1:
            # self.prefix = ''
            self.city = ''
            self.admin2_name = ''
        elif self.place_type == PlaceType.ADMIN2:
            # self.prefix = ''
            self.city = ''
        elif self.place_type == PlaceType.CITY:
            # self.prefix = ''
            pass

    @staticmethod
    def sort_words(words: str) -> str:
        word_list: list = words.split(' ')
        word_list.sort()
        return ' '.join(word_list)

    @staticmethod
    def get_soundex_by_word(text: str) -> str:
        result_sdx = ''
        text_words = text.split(' ')
        for word in text_words:
            if len(result_sdx) == 0:
                result_sdx = GeoSearch.get_soundex(Loc.sort_words(word))
            else:
                result_sdx += ' ' + GeoSearch.get_soundex(Loc.sort_words(word))
        return result_sdx

    @staticmethod
    def matchscore_prefix(pref: str, result: str) -> str:
        """
        Remove any items from prefix that are in match result.  Remove *   
        #Args:   
            pref:   
            result:   

        #Returns:  Prefix with words removed   
        """
        new_prfx = pref.lower()
        new_prfx = new_prfx.strip(' ')
        prefix_parts = new_prfx.split(',')

        result = result.lower()
        result_parts = result.split(',')

        # Walk thru each segment in result
        for result_segment_idx, result_segment in enumerate(result_parts):
            result_sdx = ' ' + Loc.get_soundex_by_word(result_segment) + ' '
            result_segment = ' ' + result_segment + ' '
            # Walk thru each segment in prefix
            for prefix_segment_idx, prefix_segment in enumerate(prefix_parts):
                prefix_words = prefix_segment.split(' ')
                # Walk thru each word in prefix segment
                for pref_word_idx, prefix_word in enumerate(prefix_words):
                    prefix_sdx = ' ' + GeoSearch.get_soundex(prefix_word) + ' '
                    if len(prefix_word) < 3:
                        prefix_word += ' '
                    # Remove words in prefix that are in result_segment
                    if (prefix_word in result_segment and prefix_word != '') or (prefix_sdx in
                                                                                 result_sdx and prefix_sdx != ''):
                        result_segment = remove_item(prefix_word.strip(' '), result_segment)
                        new_prfx = remove_item(prefix_word.strip(' '), new_prfx)
                        pass
                    # See if any words in result_segment are in prefix
                    result_words = result_segment.split(' ')
                    if len(prefix_word) > 0:
                        # Walk through each word in result
                        for result_word_idx, result_word in enumerate(result_words):
                            if len(result_word) < 3:
                                result_word = result_word + ' '
                            if result_word in prefix_word and float(len(result_word)) / float(len(prefix_word)) > 0.6:
                                # Remove result_word from result and prefix
                                result_segment = remove_item(result_word, result_segment)
                                new_prfx = remove_item(result_word, new_prfx)

        res = re.sub('[,]', '', new_prfx)
        res = res.strip(' ')
        return res.strip(',')

    @staticmethod
    def prefix_cleanup(pref: str, result: str) -> str:
        """
        Cleanup prefix.  Remove any items from prefix that are in match result.  Remove *   
        #Args:   
            pref:   
            result:   

        #Returns:  Prefix with words removed

        """
        return Loc.matchscore_prefix(pref, result)

    @staticmethod
    def get_district1_type(iso) -> str:
        # Return the local country term for Admin1 district
        if iso in ["al", "no"]:
            return "County"
        elif iso in ["us", "at", "bm", "br", "de"]:
            return "State"
        elif iso in ["ac", "an", 'ao', 'bb', 'bd']:
            return "Parish"
        elif iso in ["ae"]:
            return "Emirate"
        elif iso in ["bc", "bf", "bh", "bl", "bn"]:
            return "District"
        elif iso in ["gb"]:
            return "Country"
        else:
            return "Province"

    @staticmethod
    def get_type_name(feature):
        nm = type_name.get(feature)
        if nm is None:
            nm = ''
        return nm

    def update_names(self,  dct):
        prfx = self.prefix_cleanup(self.prefix, self.get_long_name(dct))
        self.updated_entry = GeoUtil.capwords(prfx) + self.get_long_name(dct)


def remove_item(pattern, text) -> str:
    if len(pattern) < 1:
        return text
    # Find pattern in word in text and remove entire word
    segment_list = text.split(',')
    # Walk thru segments
    for seg_idx, segment in enumerate(segment_list):
        # Walk thru words
        word_list = segment.split(' ')
        for idx, word in enumerate(word_list):
            if pattern in word:
                # Remove entire word, not just pattern
                word_list[idx] = ''
        segment_list[seg_idx] = ' '.join(word_list)
    text = ','.join(segment_list)
    return text


type_name = {
    "ADM0": 'Country', "ADM1": 'City', "ADM2": 'City', "ADM3": 'City', "ADM4": 'City', "ADMF": 'City',
    "CH"  : 'Church', "CSTL": 'Castle', "CMTY": 'Cemetery', "EST": 'Estate', "HSP": 'Hospital',
    "HSTS": 'Historic', "ISL": 'Island', "MSQE": 'Mosque', "MSTY": 'Monastery', "MT": 'Mountain', "MUS": 'Museum', "PAL": 'Palace',
    "PPL" : 'City', "PPLA": 'City', "PPLA2": 'City', "PPLA3": 'City', "PPLA4": 'City',
    "PPLC": 'City', "PPLG": 'City', "PPLH": 'City', "PPLL": 'Village', "PPLQ": 'City', "PPLX": 'City',
    "PRK" : 'Park', "PRN": 'Prison', "PRSH": 'Parish', "RUIN": 'Ruin',
    "RLG" : 'Religious', "STG": '', "SQR": 'Square', "SYG": 'Synagogue', "VAL": 'Valley', "PP1M": 'City', "PP1K": 'City'
    }
