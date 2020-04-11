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
geoname database support routines.  Add locations to geoname DB, create geoname tables and indices.   
Provides a number of methods to lookup locations by name, feature, admin ID, etc.
"""
import functools
import logging
import re

import phonetics

from geodata import Loc, Country, MatchScore, Normalize, QueryList
from geodata.GeoUtil import Query, Result, Entry, get_feature_group

FUZZY_LOOKUP = [Result.WILDCARD_MATCH, Result.WORD_MATCH, Result.SOUNDEX_MATCH]
CACHE_SIZE = 32768
COUNTRY_CACHE = 2048


class GeoSearch:
    """
    geoname database search routines.  look up items in geoname DB
    """

    def __init__(self, geodb):
        self.logger = logging.getLogger(__name__)
        self.detailed_debug = True
        self.start = 0
        self.use_wildcards = True
        self.total_lookups = 0
        self.cache = {}
        self.place_type = ''
        self.select_str = 'name, country, admin1_id, admin2_id, lat, lon, feature, geoid, sdx'
        self.geodb = geodb
        self.match = MatchScore.MatchScore()
        self.norm = Normalize.Normalize()
        self.place = Loc.Loc()

    def lookup_place(self, place: Loc) -> []:
        """
            **Lookup a place in geoname.org db**     
            Lookup is based on place.place_type as follows:  
                Loc.PlaceType.COUNTRY: does self.search_country(place)  
                Loc.PlaceType.ADVANCED_SEARCH: does self.feature_search(place)  
                Otherwise: do self.search_city(place)  
        # Args:   
            place: Loc instance.  Call Loc.parse_place() before calling lookup_place()   

        # Returns:   
            Best score found  
            place.georow_list contains a list of matching entries.  
            Each entry has: Lat, Long, districtID (County or State or Province ID), and a match quality score  

        """
        place.result_type = Result.STRONG_MATCH
        best_score = MatchScore.Score.VERY_POOR

        if place.place_type == Loc.PlaceType.COUNTRY:
            # Country
            if place.georow_list:
                place.country_name = self.get_country_name(place.country_name)
                best_score = MatchScore.Score.VERY_GOOD
        else:
            # General search 
            if place.place_type == Loc.PlaceType.ADMIN1:
                place.feature = "ADM1"
            place.georow_list.clear()
            best_score = self._search(place=place, georow_list=place.georow_list, name=place.city, admin1_id=place.admin1_id,
                                      admin2_id=place.admin2_id, iso=place.country_iso, feature=place.feature, sdx=get_soundex(place.city))
        self.logger.debug(f'**LOOKUP PLACE  score={best_score}')
        return best_score

    def deep_lookup(self, place: Loc) -> []:
        """
        Do a lookup based on soundex and combinations of words
        Args:
            place: 

        Returns: best score found

        """
        # Get more results unless we have a high score
        row_list = []
        best_score = self.search_for_combinations(row_list, place.city, place, 'main.geodata')
        if len(row_list) > 0:
            place.georow_list.extend(row_list)
        if best_score > MatchScore.Score.VERY_POOR - 10:
            # Search for each term in name
            row_list = []
            best_score = self.search_each_term(row_list, place.city, place, 'main.geodata')
            if len(row_list) > 0:
                place.georow_list.extend(row_list)
        return best_score

    def get_admin2_name(self, admin1_id, admin2_id, iso) -> str:
        """
        Search for Admin2 name using admin2_id and admin1_id 

        # Args:   
            admin1_id: Admin1 ID   
            admin2_id: Admin2 ID   
            iso: country ISO     

        # Returns:
            Admin2 name
        """
        return self._get_name(admin1_id=admin1_id, admin2_id=admin2_id, iso=iso, feature='ADM2')

    def get_admin1_name(self, admin1_id, iso) -> str:
        """
        Search for Admin1 name using admin1_id (rather than place instance)

        # Args:   
            admin1_id: Admin1 ID   
            iso: country ISO     

        # Returns:
            Admin1 name.   
        """
        return self._get_name(admin1_id=admin1_id, admin2_id='', iso=iso, feature='ADM1')

    def get_country_name(self, iso: str) -> str:
        """
             return country name for specified ISO code 
        # Args:   
            iso:   Country ISO code
        # Returns:
            Country name or ''
        """
        return self._get_name(admin1_id='', admin2_id='', iso=iso, feature='ADM0')

    @functools.lru_cache(maxsize=CACHE_SIZE)
    def _get_name(self, admin1_id, admin2_id, iso, feature, sdx='') -> str:
        """
             return  name for specified ID

        # Args:   
            iso:   Country ISO code

        # Returns:
             name or ''
        """
        row_list = []
        key = f'{admin1_id}_{admin2_id}_{iso}_{feature}'
        if len(admin1_id + admin2_id + iso) == 0:
            return ''

        self._search(georow_list=row_list, place=None, name='', admin1_id=admin1_id, admin2_id=admin2_id, iso=iso, feature=feature, sdx=sdx)

        if len(row_list) > 0:
            self.cache[key] = row_list[0][Entry.NAME]
            return row_list[0][Entry.NAME]
        else:
            return ''

    def get_admin1_alternate_name(self, admin1_id, place: Loc) -> (str, str):
        """
             Get Admin1 name from alternate name table 

        # Args:   
            place:   place instance.  place.admin1_id is used for lookup

        # Returns:
            (admin1 name, lang)  place.admin2_id is updated with best match 
        """
        # self.logger.debug('GET ADMIN1 ALT NAME')
        if len(admin1_id) == 0:
            return '', ''

        # Find GEOID for admin1_id and then get alternate name for GEOID
        row_list = []
        self._search(georow_list=row_list, place=None, name='', admin1_id=admin1_id, admin2_id='', iso=place.country_iso, feature='ADM1')
        if len(row_list) > 0:
            row = row_list[0]
            # Get alternate name for this GEOID
            admin1_name, lang = self.get_alternate_name(row[Entry.ID])
            return admin1_name, lang
        else:
            return '', ''

    def get_alternate_name(self, geoid) -> (str, str):
        """
        Retrieve alternate name for specified GEOID   

        #Args:    
            geoid: Geoid to get alternate names for   

        #Returns: 
            (name, lang)   

        """
        # todo - make rowlist a param
        query_list = [
            Query(where="geoid = ?",
                  args=(geoid,),
                  result=Result.STRONG_MATCH)]
        select = 'name, lang'
        row_list = []
        self.geodb.process_query_list(result_list=row_list, place=None, select_fields=select, from_tbl='main.altname', query_list=query_list)
        if len(row_list) > 0:
            return row_list[0][0], row_list[0][1]
        else:
            return '', ''

    @functools.lru_cache(maxsize=COUNTRY_CACHE)
    def get_iso_from_admin1_id(self, admin1_id, country_iso) -> str:
        """
                Search for country iso using admin1_name

                # Args:   
                    admin1_name:
                    place:   

                # Returns:
                    admin1_id
                """
        row_list = []
        self.logger.debug(f'GET ISO ID for adm1 id [{admin1_id}]')
        self._search(georow_list=row_list, place=None, name='', admin1_id=admin1_id, admin2_id='', iso=country_iso, feature='ADM1', sdx='')
        if len(row_list) > 0:
            country_iso = row_list[0][Entry.ISO]
        else:
            country_iso = ''
        return country_iso

    @functools.lru_cache(maxsize=CACHE_SIZE)
    def get_admin1_id(self, admin1_name, country_iso) -> str:
        """
        Search for Admin1 ID using admin1_name

        # Args:   
            admin1_name:
            place:   

        # Returns:
            admin1_id
        """
        row_list = []
        self.place.clear()
        self.place.admin1_name = admin1_name
        self.place.country_iso = country_iso
        admin1_name = self.norm.admin1_normalize(admin1_name, country_iso)
        self.logger.debug(f'GET ADMIN1 ID from [{admin1_name}]')
        self._search(georow_list=row_list, place=None, name=admin1_name, admin1_id='', admin2_id='', iso=country_iso, feature='ADM1', sdx='')

        if len(row_list) == 0:
            # Nothing found.  Try deeper search
            self.logger.debug(f'not found - search for combo [{admin1_name}]')
            self.search_for_combinations(row_list=row_list, target=admin1_name, place=self.place, table='main.admin')
        else:
            self.logger.debug(f'found {row_list}')
            pass

        if len(row_list) > 0:
            admin1_id = row_list[0][Entry.ADM1]
        else:
            admin1_id = ''
        return admin1_id

    @functools.lru_cache(maxsize=COUNTRY_CACHE)
    def get_country_iso(self, country_name) -> str:
        """
             return country ISO code for place.country_name   

        # Args:   
            place:   place instance.  looks up by place.country_name   

        # Returns:   
            Country ISO or ''.     
        """
        row_list = []
        self.place.clear()
        self.place.country_name = country_name

        country_name, modified = self.norm.country_normalize(country_name)
        if len(country_name) == 0:
            return ''
        sdx = get_soundex(country_name) + '*'

        best = self._search(georow_list=row_list, place=self.place, name=country_name, admin1_id='', admin2_id='', iso='', feature='ADM0', sdx='')

        if self.place.result_type == Result.STRONG_MATCH:
            iso = row_list[0][Entry.ISO]
            self.place.country_name = row_list[0][Entry.NAME]
        else:
            # Lookup by soundex
            best = self._search(georow_list=row_list, place=self.place, name='', admin1_id='', admin2_id='', iso='', feature='ADM0',
                                sdx=sdx)
            if self.place.result_type == Result.STRONG_MATCH:
                iso = row_list[0][Entry.ISO]
                self.place.country_name = row_list[0][Entry.NAME]
            else:
                iso = ''
        return iso

    def update_names(self, place):
        # Use ID fields to fill in  missing names for admin1, admin2, and country
        if place.admin1_id != '':
            if place.admin1_name == '':
                place.admin1_name = self.get_admin1_name(place.admin1_id, place.country_iso)
            if place.admin2_name == '':
                place.admin2_name = self.get_admin2_name(place.admin1_id, place.admin2_id, place.country_iso)
        place.country_name = str(self.get_country_name(place.country_iso))

    def _search(self, georow_list, place, name, admin1_id, admin2_id, iso, feature, sdx=''):
        """

        Args:
            georow_list: Returns list of matching georows
            name: name of location to lookup
            admin1_id: admin1_id of location (if available, otherwise '')
            admin2_id: 
            iso: country iso of location (if available,  otherwise '')
            feature: feature code of location (if available, otherwise '')

        Returns: result_type

        """
        query_list = []

        # Put together where clauses with all non-blank fields 
        if len(name + admin2_id + admin2_id + admin1_id + iso) == 0:
            return Result.NO_MATCH
        ql = QueryList.QueryItem()

        where_clauses = ["name", "country", "admin1_id", "admin2_id", "feature"]
        terms = [name, iso, admin1_id, admin2_id, feature]
        ql.add_clauses(where_clauses=where_clauses, terms=terms)  # add 
        query_list.append(Query(where=ql.where, args=ql.args, result=Result.PARTIAL_MATCH))

        ql.clear()
        if len(sdx) > 0:
            where_clauses = ["country", "feature", "sdx"]
            terms = [iso, feature, sdx]
            ql.add_clauses(where_clauses=where_clauses, terms=terms)  # add 
            query_list.append(Query(where=ql.where, args=ql.args, result=Result.PARTIAL_MATCH))

        # See if we can determine feature type from name and lookup by that
        self.add_feature_query(query_list, name, iso)

        best = self.geodb.process_query_list(result_list=georow_list, place=place, select_fields=self.select_str, from_tbl=ql.table,
                                             query_list=query_list, debug=True)
        return best

    def search_each_term(self, row_list, target, place, table):
        """
        Search for soundex of combinations of words in target
        Words are sorted and then Soundex searched with every combination of one word missing
        Args:
            row_list: 
            target: 
            place: 
            table: 

        Returns:

        """
        query_list = []
        best = 999

        sdx = get_soundex(target)
        if len(sdx) > 3:
            sdx_word_list = sdx.split(' ')
        else:
            sdx_word_list = ['']

        if len(sdx_word_list) > 1 and len(place.country_iso) > 0:
            #  Try each word 
            self.logger.debug(f'Search EACH {sdx_word_list}')
            for idx, word in enumerate(sdx_word_list):
                if len(word) == 0:
                    continue
                pattern = word[0:4]
                self.logger.debug(f' {pattern}')
                if place.feature:
                    search, pattern, pattern2 = convert_like(column_name='sdx', pattern=pattern)
                    where = f'{search} AND  country = ? AND feature = ?'
                    if pattern2:
                        args = (pattern, pattern2, place.country_iso, place.feature,)
                    else:
                        args = (pattern, place.country_iso, place.feature,)
                    query_list.append(Query(where=where, args=args, result=Result.SOUNDEX_MATCH))
                else:
                    search, pattern, pattern2 = convert_like(column_name='sdx', pattern=pattern)
                    where = f'{search} AND  country = ? '
                    if pattern2:
                        args = (pattern, pattern2, place.country_iso,)
                    else:
                        args = (pattern, place.country_iso,)
                    query_list.append(Query(where=where, args=args, result=Result.SOUNDEX_MATCH))

            best = self.geodb.process_query_list(result_list=row_list, place=place, select_fields=self.select_str,
                                                 from_tbl=table, query_list=query_list, debug=True)
        return best

    def search_for_combinations(self, row_list, target, place, table):
        """
        Search for soundex of combinations of words in target
        Words are sorted and then Soundex searched of every combination with one word missing
        Args:
            row_list: 
            target: 
            place: 
            table: 

        Returns: None

        """
        query_list = []
        best = 999

        sdx = get_soundex(target)

        if len(sdx) > 3 and len(place.country_iso) > 0:
            sdx_word_list = sdx.split(' ')
            self.logger.debug(f'COMBO SEARCH {sdx_word_list}')

            if len(sdx_word_list) == 1:
                if place.feature:
                    query_list.append(Query(where="(sdx >= ? and sdx < ?) AND country = ? AND feature = ?",
                                            args=(sdx, inc_key(sdx), place.country_iso, place.feature,),
                                            result=Result.SOUNDEX_MATCH))
                else:
                    query_list.append(Query(where="(sdx >= ? and sdx < ?) AND country = ?",
                                            args=(sdx, inc_key(sdx), place.country_iso,),
                                            result=Result.SOUNDEX_MATCH))
            else:
                # Multiple words - Try every combination with a single word removed
                for ignore_word_idx in range(0, len(sdx_word_list)):
                    pattern = ''
                    for idx, word in enumerate(sdx_word_list):
                        if idx != ignore_word_idx:
                            if len(pattern) == 0:
                                pattern += word
                            else:
                                pattern += ' ' + word
                    # pattern += '%'
                    self.logger.debug(f'{ignore_word_idx}) {pattern}')
                    if place.feature:
                        query_list.append(Query(where="(sdx >= ? and sdx < ?) AND country = ? AND feature = ?",
                                                args=(pattern, inc_key(pattern), place.country_iso, place.feature,),
                                                result=Result.SOUNDEX_MATCH))
                    else:
                        query_list.append(Query(where="(sdx >= ? and sdx < ?) AND country = ?",
                                                args=(pattern, inc_key(pattern), place.country_iso,),
                                                result=Result.SOUNDEX_MATCH))

            best = self.geodb.process_query_list(result_list=row_list, place=place, select_fields=self.select_str,
                                                 from_tbl=table, query_list=query_list, debug=True)

            self.logger.debug(f'search_for_combos ')
        return best

    def lookup_geoid(self, georow_list, geoid, place: Loc, admin=False) -> None:
        """
        Search by GEOID 
        Args:
            georow_list: 
            geoid: 
            place: 
            admin: If True, look up in admin table, otherwise look in geodata table

        Returns: None.  georow_list contains list of matches
        """
        if admin:
            table = 'main.admin'
        else:
            table = 'main.geodata'
        query_list = [
            Query(where="geoid = ? ",
                  args=(geoid,),
                  result=Result.STRONG_MATCH)
            ]
        self.geodb.process_query_list(result_list=georow_list, place=None, select_fields=self.select_str,
                                      from_tbl=table, query_list=query_list)

    def lookup_dbid(self, georow_list, dbid, place: Loc, admin=False) -> None:
        """
        Search by Database ID 
        Args:
            georow_list: 
            dbid: 
            place: 
            admin: If True, look up in admin table, otherwise look in geodata table

        Returns: None.  georow_list contains list of matches
        """
        if admin:
            table = 'main.admin'
        else:
            table = 'main.geodata'
        query_list = [
            Query(where="id = ? ",
                  args=(dbid,),
                  result=Result.STRONG_MATCH)
            ]
        self.geodb.process_query_list(result_list=georow_list, place=None, select_fields=self.select_str,
                                      from_tbl=table, query_list=query_list)
        if georow_list:
            # self.logger.debug(georow_list[0])
            self.copy_georow_to_place(georow_list[0], place, fast=True)
        else:
            self.logger.debug('no match')

    def copy_georow_to_place(self, row, place: Loc, fast: bool):
        """
        Copy data from DB row into place instance   
        Country, admin1_id, admin2_id, city, lat/lon, feature, geoid are updated if available   
        #Args:   
            row: georow from geoname database   
            place: Loc instance   
            fast: Currently ignored
        #Returns:   
            None.  Place instance is updated with data from georow   
        """
        place.admin1_id = ''
        place.admin2_id = ''
        place.admin1_name = ''
        place.admin2_name = ''
        place.city = ''

        place.country_iso = str(row[Entry.ISO])
        place.lat = row[Entry.LAT]
        place.lon = row[Entry.LON]
        place.feature = str(row[Entry.FEAT])
        # self.logger.debug(f'feat={place.feature}')
        place.geoid = str(row[Entry.ID])
        place.prefix = row[Entry.PREFIX]
        place.place_type = Loc.PlaceType.CITY

        if place.feature == 'ADM0':
            place.place_type = Loc.PlaceType.COUNTRY
            pass
        elif place.feature == 'ADM1':
            place.admin1_id = row[Entry.ADM1]
            place.place_type = Loc.PlaceType.ADMIN1
        elif place.feature == 'ADM2':
            place.admin1_id = row[Entry.ADM1]
            place.admin2_id = row[Entry.ADM2]
            place.place_type = Loc.PlaceType.ADMIN2
        else:
            place.admin1_id = row[Entry.ADM1]
            place.admin2_id = row[Entry.ADM2]
            place.city = row[Entry.NAME]

        if place.admin1_id != '':
            if place.admin1_name == '':
                place.admin1_name = self.get_admin1_name(place.admin1_id, place.country_iso)
            if place.admin2_name == '':
                place.admin2_name = self.get_admin2_name(place.admin1_id, place.admin2_id, place.country_iso)
        place.country_name = str(self.get_country_name(row[Entry.ISO]))

        if place.admin2_name is None:
            place.admin2_name = ''
        if place.admin1_name is None:
            place.admin1_name = ''

        place.city = str(place.city)
        if place.city is None:
            place.city = ''

        try:
            place.score = row[Entry.SCORE]
        except IndexError:
            pass

    @staticmethod
    def create_wildcard(pattern):
        """
        Create wildcard pattern.  Convert * to %.  Add % on end   
        #Args:   
            pattern:   

        #Returns: wildcard pattern   

        """
        if '*' in pattern:
            return re.sub(r"\*", "%", pattern)
        else:
            return f'%{pattern}%'

    @staticmethod
    def create_admin1_wildcard(pattern):
        """
        Create wildcard pattern.  Convert * to %.  Add % on end.  Currently this  
        is the same at create_wildcard   
        #Args:   
            pattern:    

        #Returns: wildcard pattern   

        """
        if '*' in pattern:
            return re.sub(r"\*", "%", pattern)
        else:
            return f'{pattern}%'

    @staticmethod
    def create_county_wildcard(pattern):
        """
        create wildcard for county lookup  
        #Args:   
            pattern:    

        #Returns:  

        """
        # Try pattern with 'shire' removed
        pattern = re.sub(r"shire", "", pattern)
        # Create SQL wildcard pattern (convert * to %).  Add % on end
        if '*' in pattern:
            return re.sub(r"\*", "%", pattern)
        else:
            return f'{pattern}'

    def set_display_names(self, temp_place):
        """
            See if there is an alternate name entry for this place   

        #Args:   
            temp_place: place instance   

        #Returns: None   

        """
        place_lang = Country.Country.get_lang(temp_place.country_iso)
        res, lang = self.get_alternate_name(temp_place.geoid)
        if res != '':  # and (lang == place_lang or lang == 'ut8'):
            temp_place.city = res

        res, lang = self.get_admin1_alternate_name(temp_place.city, temp_place)
        if res != '':  # and (lang == place_lang or lang == 'ut8'):
            temp_place.admin1_name = res

    def debugZZZ(self, text):
        if self.detailed_debug:
            self.logger.debug(text)

    def add_feature_query(self, query_list, target, iso):
        # todo use ql.add instead
        # Scan target to see if we can determine what feature type it is
        word, group = get_feature_group(target)
        if word != '':
            if 'st ' not in word:
                targ = re.sub(word, '', target).strip(' ')
            else:
                targ = target
            query_list.append(Query(where="(name >= ? and name < ?) AND country = ? AND feature = ?",
                                    args=(targ, inc_key(targ), iso, group),
                                    result=Result.WORD_MATCH))
            self.logger.debug(f'Add Feature query [{targ}] {group}')


def get_soundex(text) -> str:
    """
    Returns: Phonetics Double Metaphone Soundex code for sorted words in text  
    Words are alpha sorted but stop words are forced to end
    First two actual letters of word are prepended
    """
    sdx = []
    word_list = Normalize.sorted_normalize(text)

    for word in word_list:
        sdx.append(get_word_soundex(word))

    res = ' '.join(sdx)
    if len(res) == 0:
        res = text
    return res.lower()


@functools.lru_cache(maxsize=CACHE_SIZE)
def get_word_soundex(word):
    if len(word) > 1:
        return word[0:2] + phonetics.dmetaphone(word)[0]
    else:
        return phonetics.dmetaphone(word)[0]


def convert_like(pattern, column_name):
    """
    Convert SQL LIKE search to comparison if has % at end.  

    Args:
        pattern: 
        column_name: the column name for the search
    Returns: (txt, pattern, pattern2)
        1)  if % is not at end returns:
            txt is term like ?
            pattern1 is pattern
            pattern2 is ''
        or
        2) an equivalent SQL comparison if % at end:  
            txt is term >= ? and term < ?
            pattern1 is pattern
            pattern2 is term with last letter incremented
    """
    pattern2 = ''
    if pattern[-1] == '%':
        # Wildcard at end - Use  xx>= and yy< instead of LIKE to ensure Index can be used
        txt = f'({column_name} >= ? and {column_name} < ?)'
        pattern2 = inc_key(pattern)
    elif '%' in pattern:
        # Wildcard in middle - use LIKE
        txt = f'{column_name} LIKE ?'
    else:
        txt = f'{column_name} = ?'

    # print(f'[{txt}] ')
    return txt, pattern, pattern2


def inc_key(text):
    """ increment the last letter of text by one.  Used to replace key in SQL LIKE case with less than """
    if len(text) > 0:
        return text[0:-1] + chr(ord(text[-1]) + 1)
    else:
        return text
