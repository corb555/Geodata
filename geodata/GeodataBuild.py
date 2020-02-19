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
""" Build database for geonames.org data """
import csv
import logging
import os
import sys
import time
from collections import namedtuple
from tkinter import messagebox
from typing import Dict

from geodata import GeoUtil, Loc, Country, GeoDB, Normalize, CachedDictionary, LoadAlternateNames

DB_MINIMUM_RECORDS = 1000


class GeodataBuild:
    """
    Read in geonames.org geo data files, filter them and place the entries in a sqlite db.

    The files must be downloaded from geonames.org and used according to their usage rules.
    
    geoname files: allCountries.txt,  alternateNamesV2.txt

    The geoname file is filtered to only include the countries and feature codes specified in: 1) the country_list,
      2) the feature_list, and 3) the language list.  The import also creates new Feature codes: PP1M, P1HK, and P10K using   
     geoname population data (Pop > 1M, Pop > 100K, Pop > 10K).   

    """

    def __init__(self, directory: str, display_progress,
                 show_message, exit_on_error, languages_list_dct, feature_code_list_dct, supported_countries_dct):
        """
        Read in datafiles needed for geodata, filter them and create a sql db.
        Filter dictionary examples:   
            languages_list_dct={'fr','de'}
            feature_code_list_dct={'PPL', 'ADM1', 'CSTL'}
            supported_countries_dct = {'us','gb','at'}
        # Args:
            directory: base directory
            display_progress: None or Handler called with percent_done:int, msg:str
            show_message: True to show message boxes to user on errors
            exit_on_error:  True to exit on serious errors
            languages_list_dct: dictionary containing the ISO-2 languages we want to load from alternateNames
            feature_code_list_dct: dictionary containing the Geonames.org feature codes we want to load
            supported_countries_dct: dictionary containing the ISO-2 countries we want to load
        """
        self.logger = logging.getLogger(__name__)
        self.geodb = None
        self.show_message = show_message
            
        self.exit_on_error = exit_on_error
        self.required_db_version = 3
        # Message to user upgrading from earlier DB version  
        self.db_upgrade_text = 'Moved county data from admin table to geodata table to improve performance'
        self.directory: str = directory
        self.progress_bar = display_progress
        self.line_num = 0
        self.cache_changed: bool = False
        sub_dir = GeoUtil.get_cache_directory(self.directory)
        self.country = None
        self.languages_list_dct = languages_list_dct
        self.feature_code_list_dct = feature_code_list_dct
        self.supported_countries_dct = supported_countries_dct
        self.lang_list = []

        for item in self.languages_list_dct:
            self.lang_list.append(item)

        if not os.path.exists(sub_dir):
            self.logger.warning(f'Directory] {sub_dir} NOT FOUND')
            if self.show_message:
                messagebox.showwarning('Folder not found', f'Directory\n\n {sub_dir}\n\n NOT FOUND')
            if exit_on_error:
                sys.exit()

        # Read in Text Replacement dictionary pickle - this has output text replacements
        self.output_replace_cd = CachedDictionary.CachedDictionary(sub_dir, "output_list.pkl")
        self.output_replace_cd.read()
        self.output_replace_dct: Dict[str, str] = self.output_replace_cd.dict
        self.output_replace_list = []

        for item in self.output_replace_dct:
            self.output_replace_list.append(item)
            #self.logger.debug(f'Output replace [{item}] to [{self.output_replace_dct[item]}]')

        self.entry_place = Loc.Loc()

        # Support for Geonames AlternateNames file.  Adds alternate names for entries
        self.alternate_names = LoadAlternateNames.AlternateNames(directory=self.directory, geo_files=self,
                                                                 progress_bar=self.progress_bar, filename='alternateNamesV2.txt',
                                                                 lang_list=self.lang_list)

    def open_geodb(self, repair_database: bool, query_limit:int) -> bool:
        """
         Open Geoname DB file - this is the db of geoname.org city files and is stored in cache directory under geonames_data.
         The db only contains important fields and only for supported countries.
         If the db doesn't exist and repair flag is True, read the geonames.org files and build DB.   
         The DB has a version table for the schema version.  If the schema changes, the version should be updated.   
         This will check DB schema version and rebuild DB if version is out of date.   
        # Args:   
            repair_database: If True, rebuild database if error or missing   
        Returns:   
            True if error   
        """

        # Use db if it exists and has data and is correct version
        cache_dir = GeoUtil.get_cache_directory(self.directory)
        db_path = os.path.join(cache_dir, 'geodata.db')

        self.logger.debug(f'path for geodata.db: {db_path}')
        err_msg = ''

        # Validate Database setup
        if os.path.exists(db_path):
            # DB was Found
            self.logger.debug(f'DB found at {db_path}')
            self.geodb = GeoDB.GeoDB(db_path=db_path, 
                                     show_message=self.show_message, exit_on_error=self.exit_on_error,
                                     set_speed_pragmas=True, db_limit=query_limit)

            # Make sure DB is correct version
            ver = self.geodb.get_db_version()
            if ver != self.required_db_version:
                # Wrong version
                err_msg = f'Database version will be upgraded:\n\n{self.db_upgrade_text}\n\n' \
                    f'Upgrading database from V {ver} to V {self.required_db_version}.'
                self.geodb.close()
                os.remove(db_path)
                self.logger.info('DB version is out of date.  Database deleted')
                if self.show_message:
                    messagebox.showinfo('Database Deleted. Will rebuild on start up', err_msg)
                sys.exit()
            else:
                # Correct Version.  Make sure DB has reasonable number of records
                count = self.geodb.get_row_count()
                self.logger.info(f'Geoname entries = {count:,}')
                if count < DB_MINIMUM_RECORDS:
                    # Error if DB has under 1000 records
                    err_msg = f'Geoname Database is too small.\n\n {db_path}\n\nRebuilding DB '
        else:
            err_msg = f'Database not found at\n\n{db_path}.\n\nBuilding DB'

        self.logger.debug(f'{err_msg}')
        if err_msg == '':
            # No DB errors detected
            pass
        else:
            # DB error detected - rebuild database if flag set
            if self.show_message:
                messagebox.showinfo('Database Error', err_msg)

            self.logger.debug(err_msg)

            if repair_database:
                if os.path.exists(db_path):
                    self.geodb.close()
                    os.remove(db_path)
                    self.logger.info('Database deleted')
                    if self.show_message:
                        messagebox.showinfo('Database Deleted. Will rebuild on start up', err_msg)

                self.geodb = GeoDB.GeoDB(db_path=db_path, 
                                         show_message=self.show_message, exit_on_error=self.exit_on_error,
                                         set_speed_pragmas=True, db_limit=query_limit)
                self.create_geonames_database()

        return False

    def create_geonames_database(self)->bool:
        """
        Create geonames database from geonames.org files.
        You must call self.geodb = GeoDB.GeoDB(...) before this
        # Returns:
            True if error
        """
        # todo determine why some entries are duplicates
        # DB didnt exist.  Create tables.
        if self.geodb is None:
            self.logger.error('Cannot create DB: geodb is None')
            return True

        self.create_tables()
        self.geodb.insert_version(self.required_db_version)

        self.country = Country.Country(progress=self.progress_bar, geo_files=self, lang_list=self.lang_list)

        file_count = 0

        # Set DB version to -1 as invalid until build is completed
        self.geodb.insert_version(-1)

        # Put in country names
        self.country.add_country_names_to_db(geodb=self.geodb)

        # Put in historic names
        self.country.add_historic_names_to_db(self.geodb)

        start_time = time.time()

        # Put in data from geonames.org files
        for fname in ['allCountries.txt', 'ca.txt', 'gb.txt', 'de.txt', 'fr.txt', 'nl.txt']:
            # Read  geoname files
            error = self._add_geoname_file_to_db(fname)  # Read in info (lat/long) for all places from

            if error:
                self.logger.error(f'Error reading geoname file {fname}')
            else:
                file_count += 1

        if file_count == 0:
            self.logger.error(f'No geonames files found in {os.path.join(self.directory, "*.txt")}')
            return True

        self.logger.info(f'Geonames.org files done.  Elapsed ={time.time() - start_time}')

        # Put in geonames.org alternate names
        start_time = time.time()
        err = self.alternate_names.add_alternate_names_to_db()
        if err:
            self.logger.warning(f'Error reading Alternate names.')
        else:
            self.logger.info(f'Alternate names done.  Elapsed ={time.time() - start_time}')
        self.logger.info(f'Geonames entries = {self.geodb.get_row_count():,}')

        # Add aliases
        Normalize.add_aliases_to_database(self)

        # Create Indices
        start_time = time.time()
        self.progress("3) Final Step: Creating Indices for Database...", 95)
        self.create_geoid_index()
        self.create_indices()
        self.logger.debug(f'Indices done.  Elapsed ={time.time() - start_time}')

        # Set Database Version
        self.geodb.insert_version(self.required_db_version)
        return err

    def _add_geoname_file_to_db(self, file) -> bool:
        """
            Read in geonames files and build lookup structure

            Read a geoname.org places file and create a db of all the places.
            1. The db contains: Name, Lat, Long, district1ID (State or Province ID),
            district2_id, feat_code

            2. Since Geonames supports over 25M entries, the db is filtered to only the countries and feature types we want
        # Args:
            file: filename (not path) for DB file.  Will be placed in directory from init call

        Returns:
            True if error
        """
        Geofile_row = namedtuple('Geofile_row',
                                 'id name name_asc alt lat lon feat_class feat_code iso iso2 admin1_id'
                                 ' admin2_id admin3_id admin4_id pop elev dem timezone mod')
        self.line_num = 0
        self.progress("Reading {}...".format(file), 0)
        path = os.path.join(self.directory, file)

        if os.path.exists(path):
            fsize = os.path.getsize(path)
            bytes_per_line = 128  # Approximate bytes per line for progress indicator
            with open(path, 'r', newline="", encoding='utf-8', errors='replace') as geofile:
                self.progress("Building Database from {}".format(file), 2)  # initialize progress bar
                reader = csv.reader(geofile, delimiter='\t')
                self.geodb.db.begin()

                # Map line from csv reader into GeonameData namedtuple
                for line in reader:
                    self.line_num += 1
                    if self.line_num % 20000 == 0:
                        # Periodically update progress
                        prog = self.line_num * bytes_per_line * 100 / fsize
                        self.progress(msg=f"1) Building Database from {file}            {prog:.1f}%", val=prog)
                    try:
                        geoname_row = Geofile_row._make(line)
                    except TypeError:
                        self.logger.error(f'Unable to parse geoname location info in {file}  line {self.line_num}')
                        continue

                    # Only handle line if it's  for a country we follow and its
                    # for a Feature tag we're interested in
                    if geoname_row.iso.lower() in self.supported_countries_dct and \
                            geoname_row.feat_code in self.feature_code_list_dct:
                        self.insert_georow(geoname_row)
                        if geoname_row.name.lower() != Normalize.normalize(geoname_row.name, remove_commas=True):
                            self.geodb.insert_alternate_name(geoname_row.name,
                                                             geoname_row.id, 'ut8')

            self.progress("Write Database", 90)
            self.geodb.db.commit()
            self.progress("Database created", 100)
            return False
        else:
            return True

    @staticmethod
    def update_geo_row_name(geo_row, name):
        """
            Update the name entry and soundex entry with a new location name
        #Args:
            geo_row: 
            name: location name
        """
        geo_row[GeoDB.Entry.NAME] = Normalize.normalize(name, remove_commas=True)
        geo_row[GeoDB.Entry.SDX] = GeoUtil.get_soundex(geo_row[GeoDB.Entry.NAME])

    def insert_georow(self, geoname_row):
        """
            Create a Geo_row and insert it into DB
            This also creates new Feature codes PP1M, P1HK, and P10K using population data
        Args:
            geoname_row: ('paris', 'fr', '07', '012', 12.345, 45.123, 'PPL', '34124')

        Returns:
            None
        """
        geo_row = [None] * GeoDB.Entry.MAX
        self.update_geo_row_name(geo_row=geo_row, name=geoname_row.name)

        geo_row[GeoDB.Entry.ISO] = geoname_row.iso.lower()
        geo_row[GeoDB.Entry.ADM1] = geoname_row.admin1_id
        geo_row[GeoDB.Entry.ADM2] = geoname_row.admin2_id
        geo_row[GeoDB.Entry.LAT] = geoname_row.lat
        geo_row[GeoDB.Entry.LON] = geoname_row.lon
        geo_row[GeoDB.Entry.FEAT] = geoname_row.feat_code
        geo_row[GeoDB.Entry.ID] = geoname_row.id

        # Create new Feature codes based on city population
        if int(geoname_row.pop) > 1000000 and 'PP' in geoname_row.feat_code:
            geo_row[GeoDB.Entry.FEAT] = 'PP1M'
        elif int(geoname_row.pop) > 100000 and 'PP' in geoname_row.feat_code:
            geo_row[GeoDB.Entry.FEAT] = 'P1HK'
        elif int(geoname_row.pop) > 10000 and 'PP' in geoname_row.feat_code:
            geo_row[GeoDB.Entry.FEAT] = 'P10K'

        self.geodb.insert(geo_row=geo_row, feat_code=geoname_row.feat_code)

        # Also add abbreviations for USA states
        if geo_row[GeoDB.Entry.ISO] == 'us' and geoname_row.feat_code == 'ADM1':
            # geo_row[GeoDB.Entry.NAME] = geo_row[GeoDB.Entry.ADM1].lower()
            self.update_geo_row_name(geo_row=geo_row, name=geo_row[GeoDB.Entry.ADM1])
            self.geodb.insert(geo_row=geo_row, feat_code=geoname_row.feat_code)

    def get_supported_countries(self) -> [str, int]:
        """ Convert list of supported countries into sorted string """
        nm_msg = ""
        for ky in self.supported_countries_dct:
            nm_msg += ky.upper() + ', '
        return nm_msg, len(self.supported_countries_dct)

    def progress(self, msg, val):
        """ Update progress bar if there is one """
        if self.progress_bar is not None:
            self.progress_bar(val, msg)

        # If we're past 80% log item as info, otherwise log as debug
        if val > 80:
            self.logger.info(f'{val:.1f}%  {msg}')
        else:
            self.logger.debug(f'{val:.1f}%  {msg}')

    def close(self):
        if self.geodb:
            self.geodb.close()

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
            self.geodb.db.create_table(tbl)

    def create_geoid_index(self):
        """
        Create database indices for GEOID
        """
        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS geoid_idx ON geodata(geoid)')
        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS admgeoid_idx ON admin(geoid)')
        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS altnamegeoid_idx ON altname(geoid)')

    def create_indices(self):
        """
        Create indices for geoname database
        """
        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS name_idx ON geodata(name, country )')
        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS admin1_idx ON geodata(admin1_id )')
        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS sdx_idx ON geodata(sdx )')
        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS adm_admin2_idx ON geodata(admin1_id, admin2_id, f_code)')

        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS adm_name_idx ON admin(name, country )')
        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS adm_admin1_idx ON admin(admin1_id, f_code)')
        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS adm_country_idx ON admin(country, f_code)')
        self.geodb.db.create_index(create_index_sql='CREATE INDEX IF NOT EXISTS adm_sdx_idx ON admin(sdx )')
