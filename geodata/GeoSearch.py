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
import copy
import logging
import re
import time
from operator import itemgetter

import phonetics

from geodata import GeoUtil, Loc, Country, MatchScore, Normalize, QueryList
from geodata.GeoUtil import Query, Result, Entry

FUZZY_LOOKUP = [Result.WILDCARD_MATCH, Result.WORD_MATCH, Result.SOUNDEX_MATCH]


class GeoSearch:
    """
    geoname database search routines.  look up items in geoname DB
    """

    def __init__(self, geodb):
        self.logger = logging.getLogger(__name__)
        self.detailed_debug = True
        self.start = 0
        self.match = MatchScore.MatchScore()
        self.use_wildcards = True
        self.total_lookups = 0
        self.cache = {}
        self.place_type = ''
        self.select_str = 'name, country, admin1_id, admin2_id, lat, lon, feature, geoid, sdx'
        self.geodb = geodb

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
            None.  
            place.georow_list contains a list of matching entries.  
            Each entry has: Lat, Long, districtID (County or State or Province ID), and a match quality score  

        """
        self.start = time.time()
        place.result_type = Result.STRONG_MATCH
        # target_feature = place.place_type

        # Lookup Place based on Place Type
        # if place.admin1_id:
        # admin1 was already looked up 
        # self.logger.debug('admin1  already looked up')
        # return
        if place.place_type == Loc.PlaceType.COUNTRY:
            self.logger.debug('country look up')

            if place.georow_list:
                place.country_name = self.get_country_name(place.country_name, place.georow_list)
        elif place.place_type == Loc.PlaceType.ADMIN1:
            self.logger.debug('admin1 look up')
            pass
        else:
            # General search 
            # self.logger.debug('general look up')
            place.georow_list.clear()

            place.result_type = self._search(georow_list=place.georow_list, name=place.city, admin1_id=place.admin1_id,
                                             admin2_id=place.admin2_id, iso=place.country_iso, feature=place.feature, sdx=get_soundex(place.city))
            # self.logger.debug(f'lookup result {place.georow_list}')
            if len(place.georow_list) < 10:
                # Not enough matches found.  Try soundex search
                if (len(place.georow_list) > 0 and place.feature not in ['ADM0', 'ADM1']) or len(place.georow_list) == 0:
                    # self.logger.debug('soundex/combination look up')
                    row_list = []
                    self.search_for_combinations(row_list, place.city, place, 'main.geodata')
                    if len(row_list) > 0:
                        place.georow_list.extend(row_list)
                    # self.logger.debug(f'lookup result place:[{place.georow_list}] rowlist:[{row_list}]')

        if len(place.georow_list) > 0:
            self.assign_scores(georow_list=place.georow_list, place=place, target_feature=place.feature,
                               fast=False, quiet=False)
            # self.logger.debug(f'Found: {len(place.georow_list)} matches  '
            #                  f' [{place.georow_list}]\n')
        else:
            # self.logger.debug(f'LOOKUP. No match:for  nm=[{place.get_five_part_title()}]\n')
            pass

    def _search(self, georow_list, name, admin1_id, admin2_id, iso, feature, sdx=''):
        """
        
        Args:
            georow_list: List of matching georows
            name: name of location to lookup
            admin1_id: admin1_id of location (if available, otherwise '')
            admin2_id: 
            iso: country iso of location (if available,  otherwise '')
            feature: feature code of location (if available, otherwise '')

        Returns: result_type

        """
        query_list = []
        # self.logger.debug(f'** SEARCH  name=[{name}] adm1 id=[{admin1_id}]'
        #                  f' adm2 id=[{admin2_id}] iso=[{iso}] feat=[{feature}] sdx=[{sdx}]')

        # Put together where clauses with all non-blank fields 
        if len(name + admin2_id + admin2_id + iso) == 0:
            return GeoUtil.Result.NO_MATCH

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

        return self.geodb.process_query_list(result_list=georow_list, select_fields=self.select_str, from_tbl=ql.table,
                                             query_list=query_list)

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
        if len(admin2_id) > 0:
            return self._get_name(admin1_id=admin1_id, admin2_id=admin2_id, iso=iso, feature='ADM2')
        else:
            return ''

    def get_admin1_name(self, admin1_id, iso) -> str:
        """
        Search for Admin1 name using admin1_id (rather than place instance)

        # Args:   
            admin1_id: Admin1 ID   
            iso: country ISO     

        # Returns:
            Admin1 name.   
        """
        if len(admin1_id) > 0:
            return self._get_name(admin1_id=admin1_id, admin2_id='', iso=iso, feature='ADM1')
        else:
            return ''

    def get_country_name(self, iso: str, row_list) -> str:
        """
             return country name for specified ISO code 
        # Args:   
            iso:   Country ISO code
        # Returns:
            Country name or ''
        """
        return self._get_name(admin1_id='', admin2_id='', iso=iso, feature='ADM0')

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

        name = self.cache.get(key)
        if name:
            # self.logger.debug('CACHE MATCH')
            return name

        self._search(georow_list=row_list, name='', admin1_id=admin1_id, admin2_id=admin2_id, iso=iso, feature=feature, sdx=sdx)

        if len(row_list) > 0:
            # self.logger.debug(f'GET NAME for {feature} ID: 1[{admin1_id}] 2[{admin2_id}] iso[{iso}] RES=[{row_list[0][Entry.NAME]}]')
            self.cache[key] = row_list[0][Entry.NAME]
            return row_list[0][Entry.NAME]
        else:
            # self.logger.debug(f'GET NAME for ID 1[{admin1_id}] 2[{admin2_id}] iso[{iso}] RES=[NO MATCH]')
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

        # target = place.admin1_id
        if len(admin1_id) == 0:
            return '', ''

        # Find GEOID for admin1_id and then get alternate name for GEOID
        row_list = []
        self._search(georow_list=row_list, name='', admin1_id=admin1_id, admin2_id='', iso=place.country_iso, feature='ADM1')
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
        self.geodb.process_query_list(result_list=row_list, select_fields=select, from_tbl='main.altname', query_list=query_list)
        if len(row_list) > 0:
            return row_list[0][0], row_list[0][1]
        else:
            return '', ''

    def update_names(self, place):
        # Use ID fields to fill in  missing names for admin1, admin2, and country
        row_list = []

        if place.admin1_id != '':
            if place.admin1_name == '':
                place.admin1_name = self.get_admin1_name(place.admin1_id, place.country_iso)
            if place.admin2_name == '':
                place.admin2_name = self.get_admin2_name(place.admin1_id, place.admin2_id, place.country_iso)
        place.country_name = str(self.get_country_name(place.country_iso, row_list))

    def get_admin1_id(self, admin1_name, place: Loc, row_list):
        """
        Search for Admin1 ID using admin1_name

        # Args:   
            admin1_name:
            place:   

        # Returns:
            None.  place.admin1_id and place.country_iso are updated with best match 
        """

        # TODO get rid of utilization of place, return id
        # if len(admin1_name) == 0:
        #    return
        admin1_name = Normalize.admin1_normalize(admin1_name, place.country_iso)
        # self.logger.debug(f'GET ADMIN1 ID from [{admin1_name}]')

        result_place = copy.copy(place)
        sdx = get_soundex(admin1_name)

        self._search(georow_list=row_list, name=admin1_name, admin1_id='', admin2_id='', iso=place.country_iso, feature='ADM1', sdx=sdx)

        # Sort places in match_score order
        if len(row_list) == 0:
            self.logger.debug(f'search for combo {admin1_name}')
            self.search_for_combinations(row_list=row_list, target=admin1_name, place=place, table='main.admin')
        else:
            # self.logger.debug(f'found {row_list}')
            pass

        if len(row_list) > 0:
            self.assign_scores(row_list, result_place, 'ADM1', fast=False, quiet=False)
            sorted_list = sorted(row_list, key=itemgetter(GeoUtil.Entry.SCORE))
            place.admin1_id = sorted_list[0][Entry.ADM1]

            # self.logger.debug(f'SEARCH for ADMIN1 ID DONE -- Found adm1 id = [{place.admin1_id}] row={sorted_list[0]} ')
            # Fill in Country ISO
            if place.country_iso == '':
                place.country_iso = sorted_list[0][Entry.ISO]
        else:
            self.logger.debug(f'SEARCH ADMIN1 ID DONE -- NO MATCH SEARCH  adm1 name = {admin1_name}  ')

    def get_country_iso(self, georow_list, country_name, place: Loc) -> str:
        """
             return country ISO code for place.country_name   

        # Args:   
            place:   place instance.  looks up by place.country_name   

        # Returns:   
            Country ISO or ''.  If found, update place.country_name with DB country name   
        """
        # self.logger.debug(f'GET COUNTRY ISO for [{country_name}]')

        country_name, modified = Normalize.country_normalize(country_name)
        if len(country_name) == 0:
            return ''
        sdx = get_soundex(country_name) + '*'

        place.result_type = self._search(georow_list=georow_list, name=country_name, admin1_id='', admin2_id='', iso='', feature='ADM0', sdx='')
        self.assign_scores(georow_list, place, 'ADM0', fast=False, quiet=True)
        # self.logger.debug(georow_list[0])

        if place.result_type == Result.STRONG_MATCH:
            iso = georow_list[0][Entry.ISO]
            place.country_name = georow_list[0][Entry.NAME]
        else:
            place.result_type = self._search(georow_list=georow_list, name='', admin1_id='', admin2_id='', iso='', feature='ADM0',
                                             sdx=sdx)
            self.assign_scores(georow_list, place, 'ADM0', fast=False, quiet=True)
            if place.result_type == Result.STRONG_MATCH:
                iso = georow_list[0][Entry.ISO]
                place.country_name = georow_list[0][Entry.NAME]
            else:
                iso = ''

        # self.logger.debug(f'found iso [{iso}]')

        return iso

    def search_for_combinations(self, row_list, target, place, table):
        """
        Search for soundex of combinations of words in target
        Words are sorted and then searched with every combination of one word missing
        Args:
            row_list: 
            target: 
            place: 
            table: 

        Returns:

        """
        query_list = []
        sdx = get_soundex(target)

        if len(sdx) > 3 and len(place.country_iso) > 0:
            # append wildcard
            sdx += '%'

            word_list = sdx.split(' ')

            if len(word_list) == 1:
                if place.feature:
                    query_list.append(Query(where="sdx like ? AND country = ? AND feature = ?",
                                            args=(sdx, place.country_iso, place.feature,),
                                            result=Result.SOUNDEX_MATCH))
                else:
                    query_list.append(Query(where="sdx like ? AND country = ?",
                                            args=(sdx, place.country_iso,),
                                            result=Result.SOUNDEX_MATCH))
            else:
                # Try every combination with a single word removed
                for ignore_word_idx in range(0, len(word_list)):
                    pattern = ''
                    for idx, word in enumerate(word_list):
                        if idx != ignore_word_idx:
                            if len(pattern) == 0:
                                pattern += word
                            else:
                                pattern += ' ' + word
                    # self.logger.debug(f'{ignore_word_idx}) {pattern}')
                    if place.feature:
                        query_list.append(Query(where="sdx like ? AND country = ? AND feature = ?",
                                                args=(pattern, place.country_iso, place.feature,),
                                                result=Result.SOUNDEX_MATCH))
                    else:
                        query_list.append(Query(where="sdx like ? AND country = ?",
                                                args=(pattern, place.country_iso,),
                                                result=Result.SOUNDEX_MATCH))

            place.result_type = self.geodb.process_query_list(result_list=row_list, select_fields=self.select_str,
                                                              from_tbl=table, query_list=query_list)

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
        self.geodb.process_query_list(result_list=georow_list, select_fields=self.select_str,
                                      from_tbl=table, query_list=query_list)
        if georow_list:
            #self.logger.debug(georow_list[0])
            self.assign_scores(georow_list=place.georow_list, place=place, target_feature=place.feature,
                               fast=False, quiet=False)
            #self.copy_georow_to_place(georow_list[0], place, fast=True)
        else:
            self.logger.debug('no match')

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
        self.geodb.process_query_list(result_list=georow_list, select_fields=self.select_str,
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
        # self.logger.debug(f'>>>>  COPY GEOROW {row} ')
        place.admin1_id = ''
        place.admin2_id = ''
        place.admin1_name = ''
        place.admin2_name = ''
        place.city = ''

        place.country_iso = str(row[Entry.ISO])
        row_list = []
        place.lat = row[Entry.LAT]
        place.lon = row[Entry.LON]
        place.feature = str(row[Entry.FEAT])
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
        place.country_name = str(self.get_country_name(row[Entry.ISO], row_list))

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

        # self.logger.debug(f'<<<<< COPY DONE:  A1 [{place.admin1_name}] A2 [{place.admin2_name}] count [{place.country_name}]')

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
        if res != '': # and (lang == place_lang or lang == 'ut8'):
            temp_place.city = res

        res, lang = self.get_admin1_alternate_name(temp_place.city, temp_place)
        if res != '': # and (lang == place_lang or lang == 'ut8'):
            temp_place.admin1_name = res

    def debugZZZ(self, text):
        if self.detailed_debug:
            self.logger.debug(text)

    def add_feature_query(self, query_list, target, iso):
        # Scan target to see if we can determine what feature type it is
        word, group = GeoUtil.get_feature_group(target)
        if word != '':
            if 'st ' not in word:
                targ = '%' + re.sub(word, '', target).strip(' ') + '%'
            else:
                targ = target
            query_list.append(Query(where="name LIKE ? AND country = ? AND feature like ?",
                                    args=(targ, iso, group),
                                    result=Result.WORD_MATCH))
            self.logger.debug(f'Add Feature query [{targ}] {group}')

    def assign_scores(self, georow_list, place, target_feature, fast, quiet):
        """
                    Assign match score to each result in list   
        Args:
            place: 
            target_feature: 
            fast: 
            quiet: if True, set logging to INFO

        Returns:

        """
        result_place: Loc = Loc.Loc()

        min_score = 9999
        original_prefix = place.prefix

        # If quiet, then only log at INFO level
        lev = logging.getLogger().getEffectiveLevel()
        if quiet:
            logging.getLogger().setLevel(logging.INFO)

        # Add match quality score and prefix to each entry
        for idx, rw in enumerate(georow_list):
            place.prefix = original_prefix
            if len(rw) == 0:
                continue
            # self.logger.debug(rw)
            self.copy_georow_to_place(row=rw, place=result_place, fast=fast)
            result_place.original_entry = result_place.get_long_name(None)

            if len(place.prefix) > 0 and result_place.prefix == '':
                result_place.prefix = ' '
                # result_place.prefix_commas = ','
            else:
                result_place.prefix = ''

            # Remove items in prefix that are in result
            if place.place_type != Loc.PlaceType.ADVANCED_SEARCH:
                result_name = result_place.get_long_name(None)
                place.prefix = Loc.Loc.prefix_cleanup(place.prefix, result_name)
            else:
                place.updated_entry = place.get_long_name(None)

            score = self.match.match_score(target_place=place, result_place=result_place)
            min_score = min(min_score, score)

            # Convert row tuple to list and extend so we can assign score
            update = list(rw)
            if len(update) < GeoUtil.Entry.SCORE + 1:
                update.append(1)
            update[GeoUtil.Entry.SCORE] = score

            result_place.prefix = Normalize.normalize(place.prefix, True)
            update[GeoUtil.Entry.PREFIX] = result_place.prefix
            georow_list[idx] = tuple(update)  # Convert back from list to tuple
            # self.logger.debug(f'{update[GeoUtil.Entry.SCORE]:.1f} {update[GeoUtil.Entry.NAME]} [{update[GeoUtil.Entry.PREFIX]}]')

        if min_score < MatchScore.Score.VERY_GOOD + 2:
            place.result_type = GeoUtil.Result.STRONG_MATCH

        # Restore logging level
        logging.getLogger().setLevel(lev)


def special_terms_last(item):
    """  key function - return key with special terms forced to sort last"""
    special = {'east': 1, 'west': 1, 'north': 1, 'south': 1}
    if special.get(item):
        # Force special term to sort last.  { will sort last
        return '{' + item
    return item


def get_soundex(text) -> str:
    """
    Returns: Phonetics Double Metaphone Soundex code for sorted words in text  
    First two actual letters of word are prepended
    """
    sdx = []
    # Remove l' and d' from soundex 
    text = re.sub(r"l\'", "", text)
    text = re.sub(r"d\'", "", text)

    # Force special terms to sort at end of list so wildcard will find phrases without them  (East, West, North, South)
    # North Haden becomes Haden North and Haden% will match it.
    word_list = sorted(text.split(' '), key=special_terms_last)

    for word in word_list:
        if len(word) > 1:
            sdx.append(word[0:2] + phonetics.dmetaphone(word)[0])
        else:
            sdx.append(phonetics.dmetaphone(word)[0])
    res = ' '.join(sdx)
    if len(res) == 0:
        res = text
    return res
