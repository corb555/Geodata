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
import sys
import time
from tkinter import messagebox

from geodata import Loc, DB, GeoSearch, MatchScore
from geodata.GeoUtil import Query, Result, Entry
from geodata import Normalize


class GeoDB:
    """
    geoname database routines.  
    """

    def __init__(self, db_path, show_message: bool, exit_on_error: bool, set_speed_pragmas: bool, db_limit: int):
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
        self.show_message = show_message
        self.exit_on_error = exit_on_error
        self.max_query_results = 50
        self.total_time = 0
        self.total_lookups = 0
        self.slow_lookup = 0
        self.match = MatchScore.MatchScore()
        self.norm = Normalize.Normalize()
        
        #self.select_str = 'name, country, admin1_id, admin2_id, lat, lon, feature, geoid, sdx'
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
        self.place_type = ''
        self.s:GeoSearch.GeoSearch = GeoSearch.GeoSearch(geodb=self)
    
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
            self.process_query_list(result_list=row_list, place=None, select_fields=select_str, from_tbl='main.version', query_list=query_list)
            if len(row_list) > 0:
                ver = int(row_list[0][1])
                self.logger.debug(f'Database Version = {ver}')
                return ver

        # No version table, so this is V1
        self.logger.debug('No version table.  Version is 1')
        return 1

    def clear_geoname_data(self):
        """
        Delete geodata table and admin table from database
        """
        for tbl in ['geodata', 'admin']:
            # noinspection SqlWithoutWhere
            self.db.delete_table(tbl)

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
            
        self.s.update_names(place)

        if place.admin2_name is None:
            place.admin2_name = ''
        if place.admin1_name is None:
            place.admin1_name = ''

        place.city = str(place.city)
        if place.city is None:
            place.city = ''

        update = list(row)
        if len(update) < Entry.SCORE + 1:
            update.append(1)
            row = tuple(update)

        try:
            place.score = row[Entry.SCORE]
        except IndexError:
            
            pass

    def process_query_list(self, place, result_list, select_fields, from_tbl: str, query_list: [Query],
                           stop_on_match=False, debug=False):
        """

        Args:
            result_list: will contain matches
            select_fields: fields to select
            from_tbl: table to select from
            query_list: .where is where clause, .args are query arguments

        Returns: Result type. Result.NO_MATCH on failure.  Result_list contains matches

        """
        # Perform each SQL query in the list
        best_score = 9999
        if result_list is None:
            return best_score

        for idx, query in enumerate(query_list):
            start = time.time()

            row_list = self.db.select(select_fields, query.where, from_tbl,
                                      query.args)
            
            if len(row_list) > 0:
                result_type = query.result
                if place:
                    best_score = self._assign_scores(georow_list=row_list, place=place, target_feature=place.feature,
                                                    fast=True, quiet=False)
                result_list.extend(row_list)

                if stop_on_match:
                    break
                    
            if debug:
                self.logger.debug(f'{idx}) SELECT from {from_tbl} where {query.where} val={query.args} ')
                for row in row_list:
                    self.logger.debug(f'   FOUND {row}')


            #else:
            #    self.logger.debug('     NO MATCH')

            elapsed = time.time() - start
            self.total_time += elapsed
            self.total_lookups += 1
            if elapsed > .01:
                self.slow_lookup += elapsed
                self.logger.info(f'Slow lookup. Time={elapsed:.4f}  '
                                  f'len {len(result_list)} from {from_tbl} '
                                  f'where {query.where} val={query.args} ')

            if len(result_list) > self.max_query_results:
                self.logger.debug('MAX QUERIES HIT')
        
        return best_score
    
    def _assign_scores(self, georow_list, place, target_feature, fast=False, quiet=False) -> float:
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
        start = time.time()

        best_score = 9999
        original_prefix = place.prefix

        # If quiet, then only log at INFO level
        lev = logging.getLogger().getEffectiveLevel()
        #if quiet:
        #    logging.getLogger().setLevel(logging.INFO)

        # Add match quality score and prefix to each entry
        for idx, rw in enumerate(georow_list):
            place.prefix = original_prefix
            if len(rw) == 0:
                continue
            # self.logger.debug(rw)
            self.copy_georow_to_place(row=rw, place=result_place, fast=fast)
            result_place.original_entry = result_place.get_long_name(None)
            # self.logger.debug(f'plac feat=[{place.feature}] targ=[{target_feature}]')
            if result_place.feature == target_feature:
                bonus = 10.0
            else:
                bonus = 0

            if len(place.prefix) > 0 and result_place.prefix == '':
                result_place.prefix = ' '
            else:
                result_place.prefix = ''

            score = self.match.match_score(target_place=place, result_place=result_place, fast=fast) - bonus
            best_score = min(best_score, score)

            # Convert row tuple to list and extend so we can assign score
            update = list(rw)
            if len(update) < Entry.SCORE + 1:
                update.append(1)
            update[Entry.SCORE] = score

            result_place.prefix = self.norm.normalize(place.prefix, True)
            update[Entry.PREFIX] = result_place.prefix
            georow_list[idx] = tuple(update)  # Convert back from list to tuple
            # self.logger.debug(f'{update[GeoUtil.Entry.SCORE]:.1f} {update[GeoUtil.Entry.NAME]} [{update[GeoUtil.Entry.PREFIX]}]')

        # if len(georow_list) > 0:
        #    self.logger.debug(f'min={min_score} {georow_list[0]}')
        if best_score < MatchScore.Score.STRONG_CUTOFF:
            place.result_type = Result.STRONG_MATCH

        # Restore logging level
        logging.getLogger().setLevel(lev)

        elapsed = time.time() - start
        self.logger.debug(f'assign_scores min={best_score} elapsed={elapsed:.3f}')
        return best_score

    def get_row_count(self) -> int:
        """
        Get row count of main.geodata
        :return:
        """
        return self.db.get_row_count('main.geodata')

    def close(self):
        """
        Close database.  Set optimize pragma
        """
        self.db.set_optimize_pragma()
        self.logger.info('Closing Database')
        
        self.logger.info(f'Total query time = {self.total_time:.2f}\n                  Slow DB query time = {self.slow_lookup:.2f}')
        self.db.conn.close()

