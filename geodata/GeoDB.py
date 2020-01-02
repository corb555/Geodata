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
from datetime import timedelta
from operator import itemgetter
from tkinter import messagebox

from geodata import GeoUtil, Loc, Country, MatchScore, Normalize, DB, QueryList
from geodata.GeoUtil import Query, Result, Entry, get_soundex


# from util import SpellCheck


class GeoDB:
    """
    geoname database routines.  Add items to geoname DB, look up items, create tables, indices
    """

    def __init__(self, db_path, spellcheck,
                 show_message: bool, exit_on_error: bool, set_speed_pragmas: bool, db_limit: int):
        """
            geoname data database init. Open database if present otherwise raise error
        # Args:
            db_path: full path to database file
            spellcheck: True if Spellcheck should be enabled.  NOT CURRENTLY SUPPORTED.  Must be False
            show_message: If True, show messagebox to user on error
            exit_on_error: If True, exit if significant error occurs
            set_speed_pragmas: If True, set DB pragmas for maximum performance. 
            db_limit: SQL LIMIT parameter
        # Raises:
            ValueError('Cannot open database'), ValueError('Database empty or corrupt')
        """
        self.logger = logging.getLogger(__name__)
        self.start = 0
        self.match = MatchScore.MatchScore()
        self.select_str = 'name, country, admin1_id, admin2_id, lat, lon, f_code, geoid, sdx'
        if spellcheck:
            raise ValueError('Spellcheck is not currently supported')

        self.spellcheck = spellcheck
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
            if place.admin2_id == '':
                self.wide_search_admin2_id(place=place)
            self.wide_search_city(place)

        if place.georow_list:
            self.assign_scores(place, target_feature)
            self.logger.debug(f'LOOKUP: {len(place.georow_list)} matches for type={lookup_type}  '
                              f'targ={place.target} nm=[{place.get_five_part_title()}]\n')
        else:
            # self.logger.debug(f'LOOKUP. No match:for {lookup_type}  targ={place.target} nm=[{place.get_five_part_title()}]\n')
            place.georow_list = []

    def wide_search_city(self, place: Loc):
        """
        Search for city using place.target
        # Args:   
            place: Loc instance   
        # Returns:   
            None.  place.georow_list is updated with list of matches   
        """
        lookup_target = place.target
        if len(place.target) == 0:
            return

        if self.spellcheck:
            pattern = self.spellcheck.fix_spelling(lookup_target)
        else:
            pattern = lookup_target
        pattern = self.create_wildcard(pattern)

        sdx = get_soundex(lookup_target)
        # self.logger.debug(f'CITY lkp targ=[{lookup_target}] adm1 id=[{place.admin1_id}]'
        #                  f' adm2 id=[{place.admin2_id}] iso=[{place.country_iso}] patt =[{pattern}] sdx={sdx} pref={place.prefix}')

        query_list = []
        QueryList.QueryList.build_query_list(typ=QueryList.Typ.CITY, query_list=query_list, place=place)

        if len(place.country_iso) == 0:
            # NO COUNTRY - try lookup by name.
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

            place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str,
                                                                           from_tbl='main.geodata',
                                                                           query_list=query_list)
            # self.logger.debug(place.georow_list)
            return

        # Build query list
        # Start with the most exact match depending on the data provided.
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
        else:
            # lookup by wildcard  name, country
            if '*' in lookup_target:
                query_list.clear()

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

        # Try each query in list
        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str, from_tbl='main.geodata',
                                                                       query_list=query_list)

    def wide_search_admin2(self, place: Loc):
        """
        Search for Admin2 using place.admin2_name

        # Args:   
            place:   

        # Returns:
            None.  place.georow_list is updated with list of matches   
        """
        save_target = place.target

        place.target = place.admin2_name
        if len(place.target) == 0:
            return

        query_list = []
        QueryList.QueryList.build_query_list(typ=QueryList.Typ.ADMIN2, query_list=query_list, place=place)

        # self.logger.debug(f'Admin2 lookup=[{lookup_target}] country=[{place.country_iso}]')
        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        if len(place.georow_list) == 0:
            # Try city rather than County match.
            save_admin2 = place.admin2_name
            place.city1 = place.admin2_name
            place.admin2_name = ''
            # self.logger.debug(f'Try admin2 as city: [{place.target}]')

            self.wide_search_city(place)

            if len(place.georow_list) == 0:
                #  not found.  restore admin
                place.admin2_name = save_admin2
                place.city1 = ''
            else:
                # Found match as a City
                place.place_type = Loc.PlaceType.CITY
                match_adm1 = self.get_admin1_name_direct(admin1_id=place.georow_list[0][Entry.ADM1], iso=place.country_iso)
                # self.logger.debug(f'pl_iso [{place.country_iso}] pl_adm1 {place.admin1_name} match_adm1=[{match_adm1}] ')
                if place.admin1_name != match_adm1:
                    place.prefix = place.admin1_name.title()
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
        save_target = place.target
        place.target = place.admin1_name
        if len(place.target) == 0:
            return

        query_list = []
        QueryList.QueryList.build_query_list(typ=QueryList.Typ.ADMIN1, query_list=query_list, place=place)
        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        # Sort places in match_score order
        if len(place.georow_list) > 0:
            self.assign_scores(place, 'ADM1')
            sorted_list = sorted(place.georow_list, key=itemgetter(GeoUtil.Entry.SCORE))
            place.admin1_id = sorted_list[0][Entry.ADM1]
            # self.logger.debug(f'Found adm1 id = {place.admin1_id}')

        place.target = save_target

    def wide_search_country(self, place: Loc):
        """
        Search for Country using country_iso

        # Args:   
            place:   

        # Returns:
            None.  place.georow_list is updated with list of matches   
        """
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

        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

    def wide_search_admin1_id(self, place: Loc):
        """
        Search for Admin1 ID using place.admin1_name

        # Args:   
            place:   

        # Returns:
            None.  place.admin1_id and place.country_iso are updated with best match 
        """
        lookup_target = place.admin1_name
        pattern = self.create_admin1_wildcard(lookup_target)
        if len(lookup_target) == 0:
            return

        query_list = []

        # Try each query then calculate best match - each query gets less exact
        if place.country_iso == '':
            query_list.append(Query(where="name = ?  AND f_code = ? ",
                                    args=(lookup_target, 'ADM1'),
                                    result=Result.STRONG_MATCH))

            query_list.append(Query(where="name LIKE ? AND f_code = ?",
                                    args=(pattern, 'ADM1'),
                                    result=Result.WILDCARD_MATCH))
        else:
            query_list.append(Query(where="name = ? AND country = ? AND f_code = ? ",
                                    args=(lookup_target, place.country_iso, 'ADM1'),
                                    result=Result.STRONG_MATCH))
            query_list.append(Query(where="name LIKE ? AND country = ?  AND f_code = ?",
                                    args=(pattern, place.country_iso, 'ADM1'),
                                    result=Result.WILDCARD_MATCH))

        query_list.append(Query(where="name = ?  AND f_code = ?",
                                args=(lookup_target, 'ADM1'),
                                result=Result.SOUNDEX_MATCH))

        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        self.assign_scores(place, 'ADM1')
        # Sort places in match_score order
        if len(place.georow_list) > 0:
            sorted_list = sorted(place.georow_list, key=itemgetter(GeoUtil.Entry.SCORE))
            score = sorted_list[0][Entry.SCORE]
            self.logger.debug(f'score={score}')
            place.admin1_id = sorted_list[0][Entry.ADM1]

            self.logger.debug(f'Found adm1 id = {place.admin1_id}')
            # Fill in Country ISO
            if place.country_iso == '':
                place.country_iso = sorted_list[0][Entry.ISO]

    def wide_search_admin2_id(self, place: Loc):
        """
             Search for Admin2 ID using place.admin2_name

        # Args:   
            place:   

        # Returns:
            None.  place.admin2_id is updated with best match 
        """
        lookup_target = place.admin2_name
        #pattern = self.create_county_wildcard(lookup_target)
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

        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        self.assign_scores(place, 'ADM2')

        if place.result_type == Result.STRONG_MATCH:
            row = place.georow_list[0]
            place.admin2_id = row[Entry.ADM2]

    def get_admin1_alt_name(self, place: Loc) -> (str, str):
        """
             Get Admin1 name from alternate name table 

        # Args:   
            place:   place instance.  place.admin1_id is used for lookup

        # Returns:
            None.  place.admin2_id is updated with best match 
        """

        lookup_target = place.admin1_id
        if len(lookup_target) == 0:
            return '', ''

        # Try each query until we find a match - each query gets less exact
        query_list = [
            Query(where="admin1_id = ? AND country = ?  AND f_code = ? ",
                  args=(lookup_target, place.country_iso, 'ADM1'),
                  result=Result.STRONG_MATCH)
            ]
        row_list, res = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

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
        if len(admin1_id) == 0:
            return ''

        # Try each query until we find a match - each query gets less exact
        query_list = [
            Query(where="admin1_id = ? AND country = ?  AND f_code = ? ",
                  args=(admin1_id, iso, 'ADM1'),
                  result=Result.STRONG_MATCH)
            ]
        row_list, res = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        if len(row_list) > 0:
            row = row_list[0]
            return row[Entry.NAME]
        else:
            return ''

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
        if len(admin2_id) == 0:
            return ''

        # Try each query until we find a match - each query gets less exact
        query_list = [
            Query(where="admin2_id = ? AND country = ? AND admin1_id = ?",
                  args=(admin2_id, iso, admin1_id),
                  result=Result.STRONG_MATCH),
            Query(where="admin2_id = ? AND country = ?",
                  args=(admin2_id, iso),
                  result=Result.PARTIAL_MATCH)]

        row_list, res = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        if len(row_list) > 0:
            row = row_list[0]
            return row[Entry.NAME]
        else:
            return ''

    def get_geoid(self, place: Loc) -> None:
        """
             Search for location using Geoid in place.target

        # Args:   
            place:   place instance.  Uses  Geoid in place.target for lookup

        # Returns:
            None.   Place instance is updated with DB results
        """
        result_place: Loc = Loc.Loc()

        query_list = [
            Query(where="geoid = ? ",
                  args=(place.target,),
                  result=Result.STRONG_MATCH)
            ]
        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str,
                                                                       from_tbl='main.geodata', query_list=query_list)
        if len(place.georow_list) == 0:
            place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str,
                                                                           from_tbl='main.admin', query_list=query_list)
        else:
            place.georow_list = place.georow_list[:1]
            place.result_type = GeoUtil.Result.STRONG_MATCH

        # Add search quality score to each entry
        for idx, rw in enumerate(place.georow_list):
            self.copy_georow_to_place(row=rw, place=result_place)
            update = list(rw)
            update.append(1)  # Extend list row and assign score
            result_place.prefix = ''
            result_name = result_place.get_long_name(None)
            score = 0.0

            # Remove any words from Prefix that are in result name
            place.prefix = self.prefix_cleanup(place.prefix, result_name)

            update[GeoUtil.Entry.SCORE] = int(score * 100)
            place.georow_list[idx] = tuple(update)

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

    def lookup_main_dbid(self, place: Loc) -> None:
        """Search for DB ID in main table"""
        query_list = [
            Query(where="id = ? ",
                  args=(place.target,),
                  result=Result.STRONG_MATCH)
            ]
        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str,
                                                                       from_tbl='main.geodata', query_list=query_list)

    def lookup_admin_dbid(self, place: Loc) -> None:
        """Search for DB ID in admin table"""
        query_list = [
            Query(where="id = ? ",
                  args=(place.target,),
                  result=Result.STRONG_MATCH)
            ]
        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

    def get_country_name(self, iso: str) -> str:
        """
             return country name for specified ISO code 

        # Args:   
            iso:   Country ISO code

        # Returns:
            Country name or ''
        """
        if len(iso) == 0:
            return ''

        # Try each query until we find a match - each query gets less exact
        query_list = [
            Query(where="country = ? AND f_code = ? ",
                  args=(iso, 'ADM0'),
                  result=Result.STRONG_MATCH)]

        row_list, res = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

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
            Country ISO or ''   
        """
        lookup_target, modified = Normalize.country_normalize(place.country_name)
        if len(lookup_target) == 0:
            return ''
        query_list = []

        # Add queries - each query gets less exact
        query_list.append(Query(where="name = ? AND f_code = ? ",
                                args=(lookup_target, 'ADM0'),
                                result=Result.STRONG_MATCH))

        if self.spellcheck:
            pattern = self.spellcheck.fix_spelling(lookup_target)
            query_list.append(Query(where="name LIKE ?  AND f_code = ? ",
                                    args=(pattern, 'ADM0'),
                                    result=Result.WILDCARD_MATCH))

        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)

        self.assign_scores(place, 'ADM0')

        if place.result_type == Result.STRONG_MATCH:
            res = place.georow_list[0][Entry.ISO]
            # if len(row_list) == 1:
            place.country_name = place.georow_list[0][Entry.NAME]
        else:
            res = ''

        return res

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

        lookup_target = place.target
        if len(lookup_target) == 0:
            return
        pattern = self.create_wildcard(lookup_target)
        feature_pattern = self.create_wildcard(place.feature)
        self.logger.debug(f'Advanced Search. Targ=[{pattern}] feature=[{feature_pattern}]'
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
        place.georow_list, place.result_type = self.process_query_list(select_string=self.select_str,
                                                                       from_tbl='main.geodata',
                                                                       query_list=query_list)

        # self.logger.debug(f'main Result {place.georow_list}')

        # Search admin DB
        admin_list, place.result_type = self.process_query_list(select_string=self.select_str, from_tbl='main.admin', query_list=query_list)
        place.georow_list.extend(admin_list)
        # self.logger.debug(f'admin Result {place.georow_list}')

    def copy_georow_to_place(self, row, place: Loc):
        """
        Copy data from DB row into place instance   
        Country, admin1_id, admin2_id, city, lat/lon, feature, geoid are updated if available   
        #Args:   
            row: georow from geoname database   
            place: Loc instance   

        #Returns:   
            None.  Place instance is updated with data from georow   
        """
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

        if place.feature == 'ADM0':
            self.place_type = Loc.PlaceType.COUNTRY
            pass
        elif place.feature == 'ADM1':
            place.admin1_id = row[Entry.ADM1]
            self.place_type = Loc.PlaceType.ADMIN1
        elif place.feature == 'ADM2':
            place.admin1_id = row[Entry.ADM1]
            place.admin2_id = row[Entry.ADM2]
            self.place_type = Loc.PlaceType.ADMIN2
        else:
            place.admin1_id = row[Entry.ADM1]
            place.admin2_id = row[Entry.ADM2]
            place.city1 = row[Entry.NAME]
            self.place_type = Loc.PlaceType.CITY

        place.admin1_name = str(self.get_admin1_name(place))
        place.admin2_name = str(self.get_admin2_name(place))
        if place.admin2_name is None:
            place.admin2_name = ''
        if place.admin1_name is None:
            place.admin1_name = ''

        place.city1 = str(place.city1)
        if place.city1 is None:
            place.city1 = ''

    def clear_geoname_data(self):
        """
        Delete geodata table and admin table from database
        """
        for tbl in ['geodata', 'admin']:
            # noinspection SqlWithoutWhere
            self.db.delete_table(tbl)

    def create_geoid_index(self):
        """
        Create database indices for GEOID
        """
        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS geoid_idx ON geodata(geoid)')
        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS admgeoid_idx ON admin(geoid)')
        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS altnamegeoid_idx ON altname(geoid)')

    def create_indices(self):
        """
        Create indices for geoname database
        """
        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS name_idx ON geodata(name, country )')
        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS admin1_idx ON geodata(admin1_id )')
        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS sdx_idx ON geodata(sdx )')

        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS adm_name_idx ON admin(name, country )')
        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS adm_admin1_idx ON admin(admin1_id, f_code)')
        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS adm_admin2_idx ON admin(admin1_id, admin2_id)')
        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS adm_country_idx ON admin(country, f_code)')
        self.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS adm_sdx_idx ON admin(sdx )')

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
        row_list, res = self.process_query_list(select_string=select, from_tbl='main.altname', query_list=query_list)
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
        # We split the data into 2  tables, 1) Admin: ADM0/ADM1/ADM2,  and 2) city data
        if feat_code == 'ADM1' or feat_code == 'ADM0' or feat_code == 'ADM2':
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

        # Add item to Spell Check dictionary
        if self.spellcheck:
            self.spellcheck.insert(geo_row[Entry.NAME], geo_row[Entry.ISO])

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
            row_list, res = self.process_query_list(select_string=select_str, from_tbl='main.version', query_list=query_list)
            if len(row_list) > 0:
                ver = int(row_list[0][1])
                self.logger.debug(f'Database Version = {ver}')
                return ver

        # No version table, so this is V1
        self.logger.debug('No version table.  Version is 1')
        return 1

    def process_query_list(self, select_string, from_tbl: str, query_list: [Query]):
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
        row_list = []
        result_type = Result.NO_MATCH
        for query in query_list:
            # Skip query if it's a wildcard and wildcards are disabled
            if self.use_wildcards is False and (query.result == Result.WILDCARD_MATCH or query.result == Result.SOUNDEX_MATCH):
                continue
            start = time.time()
            if query.result == Result.WORD_MATCH:
                result_list = self.word_match(select_string, query.where, from_tbl,
                                              query.args)
            else:
                result_list = self.db.select(select_string, query.where, from_tbl,
                                             query.args)
            if row_list:
                row_list.extend(result_list)
            else:
                row_list = result_list

            if len(row_list) > 0:
                result_type = query.result

            elapsed = time.time() - start
            self.total_time += elapsed
            self.total_lookups += 1
            if elapsed > .005:
                self.logger.debug(f'Time={elapsed:.6f} TOT={self.total_time:.1f} '
                                  f'len {len(row_list)} from {from_tbl} '
                                  f'where {query.where} val={query.args} ')
            if len(row_list) > self.max_query_results:
                break

        return row_list, result_type

    def word_match(self, select_string, where, from_tbl, args):
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

        #Returns:   

        """
        words = args[0].split()
        results = []  # the entire merged list of result rows
        res_flags = []  # list of flags, matching results list, 'True' to keep
        for word in words:
            # redo tuple for each word; select_string still has LIKE
            n_args = (f'%{word.strip()}%', *args[1:])
            result = self.db.select(select_string, where, from_tbl, n_args)
            for row in result:
                # check if already in overall list
                for indx, r_row in enumerate(results):
                    if row[Entry.ID] == r_row[Entry.ID]:
                        # if has same ID as in overall list, mark to keep
                        res_flags[indx] = True
                        break
                else:  # this result row did not match anything
                    # Remove "word" from prefix
                    results.append(row)  # add it to overall list
                    # if reasonable number of results for this word, flag to
                    # keep the result
                    res_flags.append(len(result) < 20)
        # strip out any results not flagged (too many to be interesting)
        result = [results[indx] for indx in range(len(results)) if
                  res_flags[indx]]
        return result

    @staticmethod
    def prefix_cleanup(pref: str, result: str) -> str:
        """
        Cleanup prefix.  Remove any words from prefix that are in match result.  Remove *   
        #Args:   
            pref:   
            result:   

        #Returns:   

        """
        new_prfx = pref.lower()

        # Remove words from prefix that are in result
        for item in re.split(r'\W+', result.lower()):
            if len(item) > 1:
                new_prfx = re.sub(item, '', new_prfx, count=1)

        # Remove wildcard char from prefix
        new_prfx = re.sub(r'\*', '', new_prfx)

        new_prfx = new_prfx.strip(' ')

        return new_prfx

    def assign_scores(self, place, target_feature):
        """
            Assign match score to each result in list   
        # Args:   
            place:   
            target_feature:  The feature type we were searching for   
        """
        result_place: Loc = Loc.Loc()

        min_score = 9999
        original_prefix = place.prefix + ' ' + place.extra + ' ' + place.target

        # Remove redundant terms in prefix by converting it to dictionary (then back to list)
        # prefix_list = list(dict.fromkeys(original_prefix.split(' ')))
        # original_prefix = ' '.join(list(prefix_list))

        # Add search quality score and prefix to each entry
        for idx, rw in enumerate(place.georow_list):
            self.copy_georow_to_place(row=rw, place=result_place)
            result_place.set_place_type()
            result_place.original_entry = result_place.get_long_name(None)

            if len(place.prefix) > 0 and result_place.prefix == '':
                result_place.prefix = ' '
                result_place.prefix_commas = ','
            else:
                result_place.prefix = ''

            # Remove items in prefix that are in result
            if place.place_type != Loc.PlaceType.ADVANCED_SEARCH:
                nm = place.get_long_name(None)
                place.prefix = self.prefix_cleanup(original_prefix, nm)
                new_prfx = place.prefix

                if len(new_prfx) > 0:
                    new_prfx += ', '
            else:
                place.updated_entry = place.get_long_name(None)

            score = self.match.match_score(target_place=place, result_place=result_place)
            if result_place.feature == target_feature:
                score -= 10

            min_score = min(min_score, score)

            # Convert row tuple to list and extend so we can assign score
            update = list(rw)
            update.append(1)
            update[GeoUtil.Entry.SCORE] = score

            result_place.prefix = Normalize.normalize(place.prefix, True)
            result_place.clean_prefix()
            update[GeoUtil.Entry.PREFIX] = result_place.prefix
            place.georow_list[idx] = tuple(update)  # Convert back from list to tuple

        if min_score < MatchScore.Score.VERY_GOOD + 2:
            place.result_type = GeoUtil.Result.STRONG_MATCH

    def create_tables(self):
        """
        Create all the tables needed for the geoname database
        """
        # name, country, admin1_id, admin2_id, lat, lon, f_code, geoid
        sql_geodata_table = """CREATE TABLE IF NOT EXISTS geodata    (
                id           integer primary key autoincrement not null,
                name     text,
                country     text,
                admin1_id     text,
                admin2_id text,
                lat      text,
                lon       text,
                f_code      text,
                geoid      text,
                sdx     text
                                    );"""

        # name, country, admin1_id, admin2_id, lat, lon, f_code, geoid
        sql_admin_table = """CREATE TABLE IF NOT EXISTS admin    (
                id           integer primary key autoincrement not null,
                name     text,
                country     text,
                admin1_id     text,
                admin2_id text,
                lat      text,
                lon       text,
                f_code      text,
                geoid      text,
                sdx     text
                                    );"""

        # name, country, admin1_id, admin2_id, lat, lon, f_code, geoid
        sql_alt_name_table = """CREATE TABLE IF NOT EXISTS altname    (
                id           integer primary key autoincrement not null,
                name     text,
                lang     text,
                geoid      text
                                    );"""

        # name, country, admin1_id, admin2_id, lat, lon, f_code, geoid
        sql_version_table = """CREATE TABLE IF NOT EXISTS version    (
                id           integer primary key autoincrement not null,
                version     integer
                                    );"""

        for tbl in [sql_geodata_table, sql_admin_table, sql_version_table, sql_alt_name_table]:
            self.db.create_table(tbl)