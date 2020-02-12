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
import logging
import os
import re
import sys
import time
from collections import Counter
from datetime import timedelta
from operator import itemgetter
from tkinter import messagebox

from geodata import GeoUtil, Loc, Country, MatchScore, Normalize, DB, QueryList
from geodata.GeoUtil import Query, Result, Entry, get_soundex

FUZZY_LOOKUP = [Result.WILDCARD_MATCH, Result.WORD_MATCH, Result.SOUNDEX_MATCH]

class GeoDB:
    """
    geoname database routines.  Add items to geoname DB, look up items, create tables, indices
    """

    def __init__(self, db_path, 
                 show_message: bool, exit_on_error: bool, set_speed_pragmas: bool, db_limit: int):
        """
            geoname data database init. Open database if present otherwise raise error
        # Args:
            db_path: full path to database file
            show_message: If True, show messagebox to user on error
            exit_on_error: If True, exit if significant error occurs
            set_speed_pragmas: If True, set DB pragmas for maximum performance. 
            db_limit: SQL LIMIT parameter
        # Raises:
            ValueError('Cannot open database'), ValueError('Database empty or corrupt')
        """
        self.logger = logging.getLogger(__name__)
        self.detailed_debug = False
        self.start = 0
        self.match = MatchScore.MatchScore()
        self.select_str = 'name, country, admin1_id, admin2_id, lat, lon, f_code, geoid, sdx'

        self.use_wildcards = True
        self.total_time = 0
        self.total_lookups = 0
        self.max_query_results = 50

        self.db_path = db_path
        # See if DB exists 
        if os.path.exists(db_path):
            db_existed = True
        else:
            db_existed = False

        self.db = DB.DB(db_filename=db_path, show_message=show_message, exit_on_error=exit_on_error)
        if self.db.err != '':
            self.logger.error(f"Error! cannot open database {db_path}.")
            raise ValueError('Cannot open database')

        # If DB was initially found 
        if db_existed:
            # Run sanity test on DB
            err = self.db.test_database('name', 'main.geodata', where='name = ? AND country = ?', args=('ba', 'fr'))

            if err:
                # DB failed sanity test
                self.logger.warning(f'DB error for {db_path}')

                if show_message:
                    if messagebox.askyesno('Error',
                                           f'Geoname database is empty or corrupt:\n\n {db_path} \n\nDo you want to delete it and rebuild?'):
                        messagebox.showinfo('', 'Deleting Geoname database')
                        self.db.conn.close()
                        os.remove(db_path)
                if exit_on_error:
                    sys.exit()
                else:
                    raise ValueError('Database empty or corrupt')

        if set_speed_pragmas:
            self.db.set_speed_pragmas()
        self.db_limit = db_limit
        self.db.order_string = ''
        self.db.limit_string = f'LIMIT {self.db_limit}'
        self.geoid_main_dict = {}  # Key is GEOID, Value is DB ID for entry
        self.geoid_admin_dict = {}  # Key is GEOID, Value is DB ID for entry
        self.place_type = ''

    def lookup_place(self, place: Loc) -> []:
        """
            **Lookup a place in geoname.org db**     
            Lookup is based on place.place_type as follows:  
                Loc.PlaceType.ADMIN1: does self.wide_search_admin1(place)  
                Loc.PlaceType.ADMIN2: does self.wide_search_admin2(place)  
                Loc.PlaceType.COUNTRY: does self.wide_search_country(place)  
                Loc.PlaceType.ADVANCED_SEARCH: does self.feature_search(place)  
                Otherwise: do self.wide_search_city(place)  
        # Args:   
            place: Loc instance.  Call Loc.parse_place() before calling lookup_place()   
  
        # Returns:   
            None.  
            Place.georow_list contains a list of matching entries.  
            Each entry has: Lat, Long, districtID (County or State or Province ID), and a match quality score  

        """
        self.start = time.time()
        place.result_type = Result.STRONG_MATCH

        if place.country_iso != '' and place.country_name == '':
            place.country_name = self.get_country_name(place.country_iso)

        target_feature = place.place_type

        # Lookup Place based on Place Type
        if place.place_type == Loc.PlaceType.ADMIN1:
            lookup_type = 'ADMIN1'
            self.wide_search_admin1(place)
        elif place.place_type == Loc.PlaceType.ADMIN2:
            lookup_type = 'ADMIN2'
            if place.admin1_id == '':
                self.wide_search_admin1_id(place=place)
            self.wide_search_admin2(place)
        elif place.place_type == Loc.PlaceType.COUNTRY:
            lookup_type = 'COUNTRY'
            self.wide_search_country(place)
        elif place.place_type == Loc.PlaceType.ADVANCED_SEARCH:
            self.feature_search(place)
            lookup_type = 'ADVANCED'
        else:
            # Lookup as City
            lookup_type = 'CITY'
            self.wide_search_city(place)

        if place.georow_list:
            self.logger.debug(f'LOOKED UP: {len(place.georow_list)} matches for type={lookup_type}  '
                              f'targ={place.target} nm=[{place.get_five_part_title()}]\n')
            #self.logger.debug(place.georow_list)
            self.assign_scores(place, target_feature, fast=False, quiet=False)
        else:
            self.debug(f'LOOKUP. No match:for {lookup_type}  targ={place.target} nm=[{place.get_five_part_title()}]\n')
            place.georow_list = []

    def wide_search_city(self, place: Loc):
        """
        Search for city using place.target
        # Args:   
            place: Loc instance   
        # Returns:   
            None.  place.georow_list is updated with list of matches   
        """
        self.debug(f'WIDE SEARCH CITY: [{place.target}]')

        lookup_target = place.target
        if len(place.target) == 0:
            return

        pattern = self.create_wildcard(lookup_target)

        sdx = get_soundex(lookup_target)
        self.logger.debug(f'CITY lkp targ=[{lookup_target}] adm1 id=[{place.admin1_id}]'
                          f' adm2 id=[{place.admin2_id}] iso=[{place.country_iso}] patt =[{pattern}] sdx={sdx} pref={place.prefix}')

        query_list = []
        
        #QueryList.QueryList.build_query_list(typ=QueryList.Typ.CITY, query_list=query_list, place=place)

        if len(place.country_iso) == 0:
            # NO COUNTRY - do lookup just by name 
            if lookup_target in pattern:
                query_list.append(Query(where="name = ?",
                                        args=(lookup_target,),
                                        result=Result.PARTIAL_MATCH))
            # lookup by wildcard name
            if '*' in lookup_target:
                query_list.clear()
                query_list.append(Query(where="name LIKE ?",
                                        args=(pattern,),
                                        result=Result.WILDCARD_MATCH))
            else:
                query_list.append(Query(where="name LIKE ?",
                                        args=(pattern,),
                                        result=Result.WORD_MATCH))

            # lookup by soundex
            query_list.append(Query(where="sdx = ?",
                                    args=(sdx,),
                                    result=Result.SOUNDEX_MATCH))
            
            place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str,
                                                                           from_tbl='main.geodata',
                                                                           query_list=query_list)
            # self.debug(place.georow_list)
            return

        if len(place.admin1_name) > 0:
            # lookup by name, ADMIN1, country
            if lookup_target in pattern:
                query_list.append(Query(
                    where="name = ? AND country = ? AND admin1_id = ?",
                    args=(lookup_target, place.country_iso, place.admin1_id),
                    result=Result.STRONG_MATCH))

            # lookup by wildcard name, ADMIN1, country
            if '*' in lookup_target:
                query_list.clear()

                query_list.append(Query(
                    where="name LIKE ? AND country = ? AND admin1_id = ?",
                    args=(pattern, place.country_iso, place.admin1_id),
                    result=Result.WILDCARD_MATCH))
            else:
                query_list.append(Query(
                    where="name LIKE ? AND country = ? AND admin1_id = ?",
                    args=(pattern, place.country_iso, place.admin1_id),
                    result=Result.WORD_MATCH))
            # lookup by Soundex , country
            query_list.append(Query(where="sdx = ? AND country = ?",
                                    args=(sdx, place.country_iso),
                                   result=Result.SOUNDEX_MATCH))
        else:
            # No admin1 - lookup by name, country
            query_list.clear()

            if '*' in lookup_target:

                query_list.append(Query(where="name LIKE ? AND country = ?",
                                        args=(pattern, place.country_iso),
                                        result=Result.WILDCARD_MATCH))
            else:
                query_list.append(Query(where="name LIKE ? AND country = ?",
                                        args=(pattern, place.country_iso),
                                        result=Result.WORD_MATCH))

        # lookup by Soundex , country
        query_list.append(Query(where="sdx = ? AND country = ?",
                                args=(sdx, place.country_iso),
                                result=Result.SOUNDEX_MATCH))
        
        # Try to find feature type and lookup by that
        self.add_feature_query(query_list, lookup_target, place.country_iso)

        # Try each query in list
        place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str, from_tbl='main.geodata',
                                                                       query_list=query_list)
        self.logger.debug(place.georow_list)

    def wide_search_admin2(self, place: Loc):
        """
        Search for Admin2 using place.admin2_name

        # Args:   
            place:   

        # Returns:
            None.  place.georow_list is updated with list of matches   
        """
        self.debug('WIDE SEARCH ADMIN2')

        save_target = place.target

        place.target = place.admin2_name
        if len(place.target) == 0:
            return

        query_list = []
        QueryList.QueryList.build_query_list(typ=QueryList.Typ.ADMIN2, query_list=query_list, place=place)

        self.debug(f'Admin2 lookup=[{place.target}] country=[{place.country_iso}]')
        place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str, from_tbl='main.geodata', 
                                                    query_list=query_list)

        if len(place.georow_list) == 0:
            # Try city rather than County match.
            save_admin2 = place.admin2_name
            place.city1 = place.admin2_name
            place.admin2_name = ''
            self.debug(f'Try admin2 as city: [{place.target}]')
            if len(place.georow_list) == 0:
                #  not found.  restore admin
                place.admin2_name = save_admin2
                place.city1 = ''
            else:
                # Found match as a City
                place.place_type = Loc.PlaceType.CITY
                match_adm1 = self.get_admin1_name_direct(admin1_id=place.georow_list[0][Entry.ADM1], iso=place.country_iso)
                # self.debug(f'pl_iso [{place.country_iso}] pl_adm1 {place.admin1_name} match_adm1=[{match_adm1}] ')
                if place.admin1_name != match_adm1 and '*' not in place.admin1_name.title():
                    # place.prefix = place.admin1_name.title()
                    place.admin1_name = ''
                return

        place.target = save_target

    def wide_search_admin1(self, place: Loc):
        """
        Search for Admin1 using place.admin1_name

        # Args:   
            place:   

        # Returns:
            None.  place.georow_list is updated with list of matches   
        """
        self.debug('WIDE SEARCH ADMIN1')
        save_target = place.target
        place.target = place.admin1_name
        if len(place.target) == 0:
            return

        query_list = []
        QueryList.QueryList.build_query_list(typ=QueryList.Typ.ADMIN1, query_list=query_list, place=place)
        place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        # Sort places in match_score order
        if len(place.georow_list) > 0:
            self.assign_scores(place, 'ADM1', fast=True, quiet=True)
            sorted_list = sorted(place.georow_list, key=itemgetter(GeoUtil.Entry.SCORE))
            place.admin1_id = sorted_list[0][Entry.ADM1]
            # self.debug(f'Found adm1 id = {place.admin1_id}')

        place.target = save_target

    def wide_search_country(self, place: Loc):
        """
        Search for Country using country_iso

        # Args:   
            place:   

        # Returns:
            None.  place.georow_list is updated with list of matches   
        """
        self.debug('WIDE SEARCH COUNTRY')

        lookup_target = place.country_iso
        if len(lookup_target) == 0:
            return
        sdx = get_soundex(lookup_target)

        # Try each query until we find a match - each query gets less exact
        query_list = [
            Query(where="country = ? AND f_code = ? ",
                  args=(place.country_iso, 'ADM0'),
                  result=Result.STRONG_MATCH),
            Query(where="sdx = ?  AND f_code=?",
                  args=(sdx, 'ADM0'),
                  result=Result.SOUNDEX_MATCH)
            ]

        place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

    def wide_search_admin1_id(self, place: Loc):
        """
        Search for Admin1 ID using place.admin1_name

        # Args:   
            place:   

        # Returns:
            None.  place.admin1_id and place.country_iso are updated with best match 
        """
        self.debug('WIDE SEARCH ADMIN1 ID')

        lookup_target = place.admin1_name
        pattern = self.create_admin1_wildcard(lookup_target)
        sdx = get_soundex(lookup_target)

        if len(lookup_target) == 0:
            return
        save_prefix = place.prefix

        query_list = []

        # Try each query then calculate best match - each query gets less exact
        if place.country_iso == '':

            query_list.append(Query(where="name = ? AND f_code = ?",
                                    args=(lookup_target, 'ADM1'),
                                    result=Result.WILDCARD_MATCH))
        else:
            query_list.append(Query(where="name LIKE ? AND country = ?  AND f_code = ?",
                                    args=(pattern, place.country_iso, 'ADM1'),
                                    result=Result.WILDCARD_MATCH))

        query_list.append(Query(where="sdx = ?  AND f_code = ?",
                                args=(sdx, 'ADM1'),
                                result=Result.SOUNDEX_MATCH))

        place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        self.assign_scores(place, 'ADM1', fast=True, quiet=True)
        
        # Sort places in match_score order
        if len(place.georow_list) > 0:
            sorted_list = sorted(place.georow_list, key=itemgetter(GeoUtil.Entry.SCORE))
            score = sorted_list[0][Entry.SCORE]
            place.admin1_id = sorted_list[0][Entry.ADM1]

            self.debug(f'WIDE SEARCH Found adm1 id = {place.admin1_id}  score={score:.1f}')
            # Fill in Country ISO
            if place.country_iso == '':
                place.country_iso = sorted_list[0][Entry.ISO]
        place.prefix = save_prefix

    def wide_search_admin2_id(self, place: Loc):
        """
             Search for Admin2 ID using place.admin2_name

        # Args:   
            place:   

        # Returns:
            None.  place.admin2_id is updated with best match 
        """
        self.debug('WIDE SEARCH ADMIN2 ID')

        lookup_target = place.admin2_name
        save_prefix = place.prefix
        # pattern = self.create_county_wildcard(lookup_target)
        if len(lookup_target) == 0:
            return

        # Try each query until we find a match - each query gets less exact
        query_list = []
        if len(place.admin1_id) > 0:
            query_list.append(Query(where="name = ? AND country = ? AND admin1_id=? AND f_code=?",
                                    args=(lookup_target, place.country_iso, place.admin1_id, 'ADM2'),
                                    result=Result.STRONG_MATCH))
            query_list.append(Query(where="name LIKE ? AND country = ? and admin1_id = ? AND f_code=?",
                                    args=(lookup_target, place.country_iso, place.admin1_id, 'ADM2'),
                                    result=Result.WILDCARD_MATCH))
            query_list.append(Query(where="name LIKE ? AND country = ? and admin1_id = ? AND f_code=?",
                                    args=(self.create_county_wildcard(lookup_target), place.country_iso, place.admin1_id, 'ADM2'),
                                    result=Result.WILDCARD_MATCH))
        else:
            query_list.append(Query(where="name = ? AND country = ? AND f_code=?",
                                    args=(lookup_target, place.country_iso, 'ADM2'),
                                    result=Result.STRONG_MATCH))
            query_list.append(Query(where="name LIKE ? AND country = ? AND f_code=?",
                                    args=(lookup_target, place.country_iso, 'ADM2'),
                                    result=Result.WILDCARD_MATCH))
            query_list.append(Query(where="name LIKE ? AND country = ? AND f_code=?",
                                    args=(self.create_county_wildcard(lookup_target), place.country_iso, 'ADM2'),
                                    result=Result.WILDCARD_MATCH))

        place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str, from_tbl='main.geodata', 
                                                    query_list=query_list)

        self.assign_scores(place, 'ADM2', fast=False,quiet=True)

        if place.result_type == Result.STRONG_MATCH:
            row = place.georow_list[0]
            place.admin2_id = row[Entry.ADM2]
        place.prefix = save_prefix

    def get_admin1_alt_name(self, place: Loc) -> (str, str):
        """
             Get Admin1 name from alternate name table 

        # Args:   
            place:   place instance.  place.admin1_id is used for lookup

        # Returns:
            None.  place.admin2_id is updated with best match 
        """
        self.debug('GET ADMIN1 ALT NAME')

        lookup_target = place.admin1_id
        if len(lookup_target) == 0:
            return '', ''

        # Try each query until we find a match - each query gets less exact
        query_list = [
            Query(where="admin1_id = ? AND country = ?  AND f_code = ? ",
                  args=(lookup_target, place.country_iso, 'ADM1'),
                  result=Result.STRONG_MATCH)
            ]
        row_list = []
        self.process_query_list(result_list=row_list, select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        if len(row_list) > 0:
            row = row_list[0]
            admin1_name, lang = self.get_alt_name(row[Entry.ID])
            return admin1_name, lang
        else:
            return '', ''

    def get_admin1_name_direct(self, admin1_id, iso) -> str:
        """
        Search for Admin1 name using admin1_id (rather than place instance)

        # Args:   
            admin1_id: Admin1 ID   
            iso: country ISO     

        # Returns:
            None.  place.admin1_id and place.country_iso are updated with best match 
        """
        self.debug('GET ADMIN1 NAME DIRECT')

        if len(admin1_id) == 0:
            return ''

        # Try each query until we find a match - each query gets less exact
        query_list = [
            Query(where="admin1_id = ? AND country = ?  AND f_code = ? ",
                  args=(admin1_id, iso, 'ADM1'),
                  result=Result.STRONG_MATCH)
            ]
        row_list = []
        self.process_query_list(result_list=row_list, select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        if len(row_list) > 0:
            row = row_list[0]
            return row[Entry.NAME]
        else:
            return ''
        
    def get_admin1_name(self, place: Loc) -> str:
        """
             Get admin1 name using place.admin1_id

        # Args:   
            place:   place instance.  Uses  place.admin1_id for lookup

        # Returns:
            Admin1 name.  Place instance admin1_name is updated with DB result
        """
        place.admin1_name = self.get_admin1_name_direct(place.admin1_id, place.country_iso)
        return place.admin1_name

    def get_admin2_name_direct(self, admin1_id, admin2_id, iso) -> str:
        """
        Search for Admin2 name using admin2_id and admin1_id (rather than place instance)

        # Args:   
            admin1_id: Admin1 ID   
            admin2_id: Admin2 ID   
            iso: country ISO     

        # Returns:
            None.  place.admin1_id and place.country_iso are updated with best match 
        """
        #self.logger.debug('GET ADMIN2 NAME DIRECT')

        if len(admin2_id) == 0:
            return ''

        # Try each query until we find a match - each query gets less exact
        query_list = []
        if admin1_id != '':
            query_list.append(Query(where="admin2_id = ? AND country = ? AND admin1_id = ? AND f_code = 'ADM2'",
                  args=(admin2_id, iso, admin1_id),
                  result=Result.STRONG_MATCH))
        else:
            query_list.append(Query(where="admin2_id = ? AND country = ? AND f_code = 'ADM2'",
                  args=(admin2_id, iso),
                  result=Result.PARTIAL_MATCH))

        row_list = []
        self.process_query_list(result_list=row_list, select_string=self.select_str, from_tbl='main.geodata', query_list=query_list)

        if len(row_list) > 0:
            row = row_list[0]
            #self.logger.debug(f'FOUND ADMIN2 NAME {row[Entry.NAME]}')

            return row[Entry.NAME]
        else:
            return ''

    def get_admin2_name(self, place: Loc) -> str:
        """
             Get admin2 name using place.admin1_id and place.admin2_id

        # Args:   
            place:   place instance.  Uses  place.admin1_id and place.admin2_id for lookup

        # Returns:
            Admin2 name.  Place instance admin2_name is updated with DB result
        """
        place.admin2_name = self.get_admin2_name_direct(place.admin1_id, place.admin2_id, place.country_iso)
        return place.admin2_name
    
    def get_geoid(self, place: Loc) -> None:
        """
             Search for location using Geoid in place.target

        # Args:   
            place:   place instance.  Uses  Geoid in place.target for lookup

        # Returns:
            None.   Place instance is updated with DB results
        """
        self.debug('GET GEOID')

        result_place: Loc = Loc.Loc()

        query_list = [
            Query(where="geoid = ? ",
                  args=(place.target,),
                  result=Result.STRONG_MATCH)
            ]
        place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str,
                                                                       from_tbl='main.geodata', query_list=query_list)
        if len(place.georow_list) == 0:
            place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str,
                                                                           from_tbl='main.admin', query_list=query_list)
        else:
            place.georow_list = place.georow_list[:1]
            place.result_type = GeoUtil.Result.STRONG_MATCH

        # Add search quality score to each entry
        for idx, rw in enumerate(place.georow_list):
            self.copy_georow_to_place(row=rw, place=result_place, fast=True)
            update = list(rw)
            update.append(1)  # Extend list row and assign score
            result_place.prefix = ''
            result_name = result_place.get_long_name(None)
            score = 0.0

            # Remove any words from Prefix that are in result name
            place.prefix = Loc.Loc.prefix_cleanup(place.prefix, result_name)

            update[GeoUtil.Entry.SCORE] = int(score * 100)
            place.georow_list[idx] = tuple(update)

    def get_country_name(self, iso: str) -> str:
        """
             return country name for specified ISO code 

        # Args:   
            iso:   Country ISO code

        # Returns:
            Country name or ''
        """
        self.debug('GET COUNTRY NAME')

        if len(iso) == 0:
            return ''

        # Try each query until we find a match - each query gets less exact
        query_list = [
            Query(where="country = ? AND f_code = ? ",
                  args=(iso, 'ADM0'),
                  result=Result.STRONG_MATCH)]

        row_list = []
        self.process_query_list(result_list=row_list, select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        if len(row_list) > 0:
            res = row_list[0][Entry.NAME]
            if iso == 'us':
                res = 'United States'
        else:
            res = ''
        return res

    def get_country_iso(self, place: Loc) -> str:
        """
             return country ISO code for place.country_name   

        # Args:   
            place:   place instance.  looks up by place.country_name   

        # Returns:   
            Country ISO or ''.  If found, update place.country_name with DB country name   
        """
        self.debug('GET COUNTRY ISO')

        lookup_target, modified = Normalize.country_normalize(place.country_name)
        if len(lookup_target) == 0:
            return ''
        query_list = [Query(where="name = ? AND f_code = ? ",
                            args=(lookup_target, 'ADM0'),
                            result=Result.STRONG_MATCH)]

        # Add queries - each query gets less exact

        place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        self.assign_scores(place, 'ADM0', fast=True, quiet=True)

        if place.result_type == Result.STRONG_MATCH:
            iso = place.georow_list[0][Entry.ISO]
            place.country_name = place.georow_list[0][Entry.NAME]
        else:
            iso = ''

        return iso

    def feature_search(self, place: Loc):
        """
                Feature search - lookup by name, ISO Country and Feature class   
                e.g. place.target='d*'   
                    place.country_iso='gb'   
                    place.feature='CSTL'   
        # Args:   
            place: Uses place.target as lookup target, place.feature as feature target,   
                place.country_iso as country code target.   

        # Returns: 
            None.  place.georow_list has list of matching georows   

        """
        self.debug('FEATURE SEARCH')

        lookup_target = place.target
        if len(lookup_target) == 0:
            return
        pattern = self.create_wildcard(lookup_target)
        feature_pattern = self.create_wildcard(place.feature)
        self.debug(f'Advanced Search. Targ=[{pattern}] feature=[{feature_pattern}]'
                          f'  iso=[{place.country_iso}] ')

        if len(place.feature) > 0:
            query_list = [
                Query(where="name LIKE ? AND country LIKE ? AND f_code LIKE ?",
                      args=(pattern, place.country_iso, feature_pattern),
                      result=Result.PARTIAL_MATCH)]
        else:
            query_list = [
                Query(where="name LIKE ? AND country LIKE ?",
                      args=(pattern, place.country_iso),
                      result=Result.PARTIAL_MATCH)]

        # Search main DB
        place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str,
                                                                       from_tbl='main.geodata',
                                                                       query_list=query_list)

        # self.debug(f'main Result {place.georow_list}')

        # Search admin DB
        admin_list = []
        if len(place.georow_list) == 0:
            place.result_type = self.process_query_list(result_list=admin_list,select_string=self.select_str, from_tbl='main.admin', 
                                                                    query_list=query_list)
            place.georow_list.extend(admin_list)
            # self.debug(f'admin Result {place.georow_list}')
            
    def lookup_main_dbid(self, place: Loc) -> None:
        """Search for DB ID in main table"""
        query_list = [
            Query(where="id = ? ",
                  args=(place.target,),
                  result=Result.STRONG_MATCH)
            ]
        place.result_type = self.process_query_list(result_list=place.georow_list, select_string=self.select_str,
                                                                       from_tbl='main.geodata', query_list=query_list)

    def copy_georow_to_place(self, row, place: Loc, fast:bool):
        """
        Copy data from DB row into place instance   
        Country, admin1_id, admin2_id, city, lat/lon, feature, geoid are updated if available   
        #Args:   
            row: georow from geoname database   
            place: Loc instance   

        #Returns:   
            None.  Place instance is updated with data from georow   
        """
        self.debug(f'COPY GEOROW >>>> {row[Entry.NAME]} ')

        place.admin1_id = ''
        place.admin2_id = ''
        place.city1 = ''

        place.country_iso = str(row[Entry.ISO])
        place.country_name = str(self.get_country_name(row[Entry.ISO]))
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
            place.city1 = row[Entry.NAME]

        if not fast:
            place.admin1_name = str(self.get_admin1_name(place))
            place.admin2_name = str(self.get_admin2_name(place))
        if place.admin2_name is None:
            place.admin2_name = ''
        if place.admin1_name is None:
            place.admin1_name = ''

        place.city1 = str(place.city1)
        if place.city1 is None:
            place.city1 = ''

        try:
            place.score = row[Entry.SCORE]
        except IndexError :
            pass

    def clear_geoname_data(self):
        """
        Delete geodata table and admin table from database
        """
        for tbl in ['geodata', 'admin']:
            # noinspection SqlWithoutWhere
            self.db.delete_table(tbl)

    @staticmethod
    def make_georow(name: str, iso: str, adm1: str, adm2: str, lat: float, lon: float, feat: str, geoid: str, sdx: str) -> ():
        """
        Create a georow based on arguments
        # Args:
            name:   
            iso:   
            adm1: admin1 id   
            adm2: admin2_id   
            lat:   
            lon: 
            feat:     
            geoid:   
            sdx:   

        # Returns:    
            georow

        """
        res = (name, iso, adm1, adm2, lat, lon, feat, geoid, sdx)
        return res

    def get_row_count(self) -> int:
        """
        Get row count of main.geodata
        :return:
        """
        return self.db.get_row_count('main.geodata')

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

    def close(self):
        """
        Close database.  Set optimize pragma
        """
        self.db.set_optimize_pragma()
        self.logger.info(f'TOTAL DATABASE LOOKUP TIME: {str(timedelta(seconds=self.total_time))}')
        if self.total_time > 0:
            self.logger.info(f'Lookups per second {self.total_lookups / self.total_time:.0f}')
        self.logger.info('Closing Database')
        self.db.conn.close()

    def set_display_names(self, temp_place):
        """
            See if there is an alternate name entry for this place   

        #Args:   
            temp_place: place instance   

        #Returns: None   

        """
        place_lang = Country.Country.get_lang(temp_place.country_iso)
        res, lang = self.get_alt_name(temp_place.geoid)
        if res != '' and (lang == place_lang or lang == 'ut8'):
            temp_place.city1 = res

        res, lang = self.get_admin1_alt_name(temp_place)
        if res != '' and (lang == place_lang or lang == 'ut8'):
            temp_place.admin1_name = res

    def get_alt_name(self, geoid) -> (str, str):
        """
        Retrieve alternate names for specified GEOID   

        #Args:    
            geoid: Geoid to get alternate names for   

        #Returns: 
            row_list from DB matches   

        """
        query_list = [
            Query(where="geoid = ?",
                  args=(geoid,),
                  result=Result.STRONG_MATCH)]
        select = 'name, lang'
        row_list = []
        self.process_query_list(result_list=row_list, select_string=select, from_tbl='main.altname', query_list=query_list)
        if len(row_list) > 0:
            return row_list[0][0], row_list[0][1]
        else:
            return '', ''

    def insert(self, geo_row: (), feat_code: str):
        """
        Insert a geo_row into geonames database   
        #Args:   
            geo_row: row to insert   
            feat_code: Geonames feature code of item   
        #Returns:   
            row_id for inserted row   
        """
        # We split the data into 2  tables, 1) admin: ADM0/ADM1,  and 2) geodata:  all other place types (city, county, ADM2, etc)
        if feat_code == 'ADM1' or feat_code == 'ADM0':
            sql = ''' INSERT OR IGNORE INTO admin(name,country, admin1_id,admin2_id,lat,lon,f_code, geoid, sdx)
                      VALUES(?,?,?,?,?,?,?,?,?) '''
            row_id = self.db.execute(sql, geo_row)
            # Add name to dictionary.  Used by AlternateNames for fast lookup during DB build
            self.geoid_admin_dict[geo_row[Entry.ID]] = row_id
        else:
            sql = ''' INSERT OR IGNORE INTO geodata(name, country, admin1_id, admin2_id, lat, lon, f_code, geoid, sdx)
                      VALUES(?,?,?,?,?,?,?,?,?) '''
            row_id = self.db.execute(sql, geo_row)
            # Add name to dictionary.  Used by AlternateNames for fast lookup during DB build
            self.geoid_main_dict[geo_row[Entry.ID]] = row_id

        return row_id

    def insert_alternate_name(self, alternate_name: str, geoid: str, lang: str):
        """
        Add alternate name to altname table
        #Args:   
            alternate_name: alternate name to add for this geoid   
            geoid: geonames.org geoid   
            lang: ISO lang code for this entry   

        #Returns: None   

        """
        row = (alternate_name, lang, geoid)
        sql = ''' INSERT OR IGNORE INTO altname(name,lang, geoid)
                  VALUES(?,?,?) '''
        self.db.execute(sql, row)

    def insert_version(self, db_version: int):
        """
        Insert DB version into Database.  This is used to track when DB schema changes   
        #Args:   
            db_version: Version of this DB schema   

        #Returns: None   

        """
        self.db.begin()
        
        # Delete previous version from table
        # noinspection SqlWithoutWhere
        sql ='''DELETE FROM version;'''
        args = None
        self.db.execute(sql, args)

        sql = ''' INSERT OR IGNORE INTO version(version)
                  VALUES(?) '''
        args = (db_version,)
        self.db.execute(sql, args)
        self.db.commit()

    def get_db_version(self) -> int:
        """
        Get schema version of database   
        #Returns: 
            schema version of database   

        """
        # If version table does not exist, this is V1
        if self.db.table_exists('version'):
            # query version ID
            query_list = [
                Query(where="version like ?",
                      args=('%',),
                      result=Result.STRONG_MATCH)]
            select_str = '*'
            row_list = []
            self.process_query_list(result_list=row_list, select_string=select_str, from_tbl='main.version', query_list=query_list)
            if len(row_list) > 0:
                ver = int(row_list[0][1])
                self.logger.debug(f'Database Version = {ver}')
                return ver

        # No version table, so this is V1
        self.logger.debug('No version table.  Version is 1')
        return 1
    
    def process_query_list(self, result_list, select_string, from_tbl: str, query_list: [Query]):
        """
        
        Args:
            result_list: 
            select_string: 
            from_tbl: 
            query_list: 

        Returns: Result type.  Result list contains matches

        """
        result_type =  self._process_queries(select_string, from_tbl, query_list, False, result_list)
        result_type1 =  self._process_queries(select_string, from_tbl, query_list, True, result_list)
        
        for row in result_list:
            self.debug(f"     Found {row[Entry.NAME]}")

        if result_type in GeoUtil.successful_match:
            return result_type
        else:
            return result_type1

    def _process_queries(self, select_string, from_tbl: str, query_list: [Query], use_wildcards, row_list):
        """
        Do a lookup for each query in the query_list.  Stop when self.max_query_results is reached    
        #Args:   
            select_string: SQL select string   
            from_tbl: Table to query   
            query_list: A list of SQL queries   

        #Returns: 
            tuple of row_list and result_type   

        """
        # Perform each SQL query in the list

        result_type = Result.NO_MATCH
        #self.debug(f'=======PROCESS QUERY {from_tbl}')
        
        for idx,query in enumerate(query_list):
            # Skip query if it's a wildcard and wildcards are disabled
            if use_wildcards is False and query.result in FUZZY_LOOKUP:
                continue
            if use_wildcards is True and query.result not in FUZZY_LOOKUP:
                continue
            start = time.time()

            if query.result == Result.WORD_MATCH :
                self.debug(f'WORD MATCH from {from_tbl} where {query.where} val={query.args} ')

                result_list2 = self.word_match(select_string, query.where, from_tbl,
                                               query.args)
                row_list.extend(result_list2)
            else:
                self.debug(f'SELECT from {from_tbl} where {query.where} val={query.args} ')
                result_list = self.db.select(select_string, query.where, from_tbl,
                                             query.args)
                #self.logger.debug(result_list)
                row_list.extend(result_list)
                
            if len(row_list) > 0:
                result_type = query.result

            elapsed = time.time() - start
            self.total_time += elapsed
            self.total_lookups += 1
            if elapsed > .4:
                if query.result == Result.WORD_MATCH:
                    self.logger.debug(f'Slow word lookup. Time={elapsed:.4f}  '
                                      f'len {len(row_list)} from {from_tbl} '
                                      f'where {query.where} val={query.args} ')
                else:
                    self.logger.debug(f'Slow lookup. Time={elapsed:.4f}  '
                                      f'len {len(row_list)} from {from_tbl} '
                                      f'where {query.where} val={query.args} ')
                    
            if len(row_list) > self.max_query_results:
                break
                
        return result_type
    
    def debug(self, text):
        if self.detailed_debug:
            self.logger.debug(text)

    def word_match(self, select_string, where, from_tbl, args)->[]:
        """
        Perform a wildcard match on each word in args[0], and then   
        merges the results into a single result.  During the merge, we note if   
        a duplicate occurs, and mark that as a higher priority result.  We  
        also note if an individual word has too many results, as we will drop   
        those results from the final list after doing the priority checks.   
        This should kill off common words from the results, while still   
        preserving combinations.   

        For example, searching for "Village of Bay", will find all three words   
        to have very many results, but the combinations of "Village" and "Bay"   
        or "Village" and "of" or "Bay" and "of" will show up in the results.   

        The order of the words will also not matter, so results should contain   
        "City of Bay Village", "Bay Village" etc.   
        
        #Args:   
            select_string:    
            where:  
            from_tbl:  
            args: args[0] has the words to search for   

        #Returns:   List of matches   

        """
        self.debug(f'WORD MATCH from {from_tbl} where {where} val={args} ')
        count = Counter()
        dct = {}
        max_matches = 0
        words = args[0].split()

        if len(words) == 0:
            return []
        
        for word in words:
            # redo tuple for each word; select_string still has LIKE
            word = re.sub(r'%','',word)
            if len(word) < 4:
                continue
            n_args = (f'%{word.strip(" ")}%', *args[1:])
            db_results = self.db.select(select_string, where, from_tbl, n_args)
            if len(db_results) < 50:
                for db_row in db_results:
                    # Add item to Dict and to Counter
                    dbid = db_row[Entry.ID]
                    ct = count[dbid]
                    if ct == 0:
                        dct[dbid] = db_row
                        count[dbid] = 1
                    else:
                        count[dbid] = 2
                    if count[dbid] > max_matches:
                        max_matches = count[dbid] 
    
        # Return list with items 
        return [dct[dbid] for dbid in count]

    def add_feature_query(self, query_list, lookup_target, iso):
        # Scan target to see if we can determine what feature type it is
        word, group = GeoUtil.get_feature_group(lookup_target)
        if word != '':
            targ = '%' + re.sub(word, '', lookup_target).strip(' ') + '%' 
            query_list.append(Query(where="name LIKE ? AND country = ? AND f_code = ?",
                                    args=(targ, iso, group),
                                    result=Result.WORD_MATCH))
            self.logger.debug(f'Added Feature query name={targ} group={group}')

    def assign_scores(self, place, target_feature, fast, quiet):
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

        lev = logging.getLogger().getEffectiveLevel()
        if quiet:
            logging.getLogger().setLevel(logging.INFO)

        # Add search quality score and prefix to each entry
        for idx, rw in enumerate(place.georow_list):
            place.prefix = original_prefix
            self.copy_georow_to_place(row=rw, place=result_place, fast=fast)
            result_place.original_entry = result_place.get_long_name(None)

            if len(place.prefix) > 0 and result_place.prefix == '':
                result_place.prefix = ' '
                result_place.prefix_commas = ','
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
            place.georow_list[idx] = tuple(update)  # Convert back from list to tuple
            #self.logger.debug(f'{update[GeoUtil.Entry.SCORE]:.1f} {update[GeoUtil.Entry.NAME]} [{update[GeoUtil.Entry.PREFIX]}]')

        if min_score < MatchScore.Score.VERY_GOOD + 2:
            place.result_type = GeoUtil.Result.STRONG_MATCH

        # Restore logging level
        logging.getLogger().setLevel(lev)
