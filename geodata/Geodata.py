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
Provides a place lookup gazeteer based on files from geonames.org.   
  Provides the location lookup methods for the geodata package.  
           
+ Creates a local sqlite3 place database of geonames.org data  
+ Parses lookup text and returns multiple matches ranked by closeness to lookup term  
+ Provides latitude/longitude  
+ Supports Wildcard search, Phonetic/Soundex search, and Word search of place database names  
+ Search by feature type (e.g. mountain, cemetery, palace, etc)  
+ Database can be filtered to only include specified countries, languages, and feature types   
   
   Main routines for Geodata package:   
    example.py - a sample demonstrating place lookups using geodata   
    geodata.open - open database.  create DB if missing   
    geodata.find_best_match - parse location and provide the best match   
    geodata.find_matches - parse location and provide a ranked list of matches   
    geodata.find_feature - lookup location by feature type and provide a ranked list of matches   
    normalize.py - Normalize text for lookup
  """
import collections
import copy
import logging
from operator import itemgetter

from geodata import GeoUtil, GeodataBuild, Loc, MatchScore, GeoSearch


class Geodata:
    """
Provide a place lookup gazeteer based on files from geonames.org  
   
    """

    def __init__(self, directory_name: str, display_progress,
                 show_message: bool, exit_on_error: bool, languages_list_dct, feature_code_list_dct,
                 supported_countries_dct):
        """
            Init

        #Args:
            directory_name: directory where geoname.org files are.  DB will be in 'cache' folder under this   
            display_progress: None or function to display progress(percent_done:int, msg:str)  
            show_message: If True - show TKInter message dialog on error   
            exit_on_error: If True - exit on significant error   
            languages_list_dct: Dictionary of ISO-2 languages to import from AlternateNamesV2.txt   
            feature_code_list_dct: Dictionary of Geoname Feature codes to import into DB   
            supported_countries_dct: Dictionary of ISO-2 Country codes to import into DB   
        """
        self.logger = logging.getLogger(__name__)
        self.display_progress = display_progress
        self.save_place: Loc = Loc.Loc()
        self.miss_diag_file = None
        self.distance_cutoff = 0.6  # Value to determine if two lat/longs are similar based on Rectilinear Distance
        self.geo_build = GeodataBuild.GeodataBuild(str(directory_name), display_progress=self.display_progress,
                                                   show_message=show_message, exit_on_error=exit_on_error,
                                                   languages_list_dct=languages_list_dct,
                                                   feature_code_list_dct=feature_code_list_dct,
                                                   supported_countries_dct=supported_countries_dct)

    def find_matches(self, location: str, place: Loc, plain_search) -> GeoUtil.Result:
        """
            Find a location in the geoname database.  On successful match, place.georow_list will contain   
            a list of georows that matched the name.  Each georow can be copied to a Loc structure by   
            calling process_result   

        #Args:   
            location: comma separated name of location to find, e.g. 'Los Angeles, California, USA'   
            place: Loc structure   
            plain_search: If True then don't do wildcard searches   
        #Returns:   
            GeoUtil.Result code   
        """
        place.parse_place(place_name=location, geo_db=self.geo_build.geodb)

        self.is_country_valid(place)
        if place.result_type == GeoUtil.Result.NOT_SUPPORTED:
            return place.result_type

        # Create full entry text
        place.update_names(self.geo_build.output_replace_dct)
        
        flags = ResultFlags(limited=False, filtered=False)
        result_list = []  # We will do different search types and append all results into result_list

        # self.logger.debug(f'== FIND LOCATION City=[{place.city}] Adm2=[{place.admin2_name}]\
        # Adm1=[{place.admin1_name}] Pref=[{place.prefix}] Cntry=[{place.country_name}] iso=[{place.country_iso}]  Type={place.place_type} ')

        # Save a shallow copy of place so we can restore fields
        self.save_place = copy.copy(place)

        # After parsing, last token is either country or underscore. 
        # Second to last is either Admin1 or underscore
        # If >2 tokens:  token[0] is placed in City and in Prefix
        # If >3 tokens:  token[1] is placed in Admin2 and appended to Prefix

        # 1) Try lookup based on standard parsing: lookup city, county, state/province, or country as parsed
        self.logger.debug(f'  1) Standard, based on parsing.  pref [{place.prefix}] city [{place.city}]'
                          f' sdx={GeoSearch.get_soundex(place.city)} '
                          f'feat={place.feature}')
        
        if place.place_type != Loc.PlaceType.COUNTRY and place.place_type != Loc.PlaceType.ADMIN2:
            self.geo_build.geodb.s.lookup_place(place=place)
            #self.logger.debug(place.georow_list)
            if place.georow_list:
                result_list.extend(place.georow_list)
            #self.logger.debug(result_list)

            # Restore fields
            self._restore_fields(place, self.save_place)
    
            # 2) Try second token (Admin2) as a city 
            if place.admin2_name != '': # and len(result_list) < 9:
                place.georow_list.clear()
                self._find_type_as_city(place, Loc.PlaceType.ADMIN2)
                #self.logger.debug(place.georow_list)
    
                if place.georow_list:
                    result_list.extend(place.georow_list)
                    #self.logger.debug(result_list)
                self._restore_fields(place, self.save_place)
    
            #  Move result_list into place georow list
            place.georow_list.clear()
            place.georow_list.extend(result_list)
            #self.logger.debug(place.georow_list)
        else:
            #self.logger.debug('ignore country, admin2')
            pass

        if len(place.georow_list) > 0:
            #self.logger.debug('process results')
            self.process_results(place=place, flags=flags)
            flags = self.filter_results(place)
        #self.logger.debug(place.georow_list)

        if len(place.georow_list) == 0:
            # NO MATCH
            self.logger.debug(f'Not found.')
            if place.result_type != GeoUtil.Result.NO_COUNTRY and place.result_type != GeoUtil.Result.NOT_SUPPORTED:
                place.result_type = GeoUtil.Result.NO_MATCH
        elif len(place.georow_list) > 1:
            self.logger.debug(f'Success!  {len(place.georow_list)} matches')
            place.result_type = GeoUtil.Result.MULTIPLE_MATCHES

        # Process the results
        self.process_results(place=place, flags=flags)
        # self.logger.debug(f'Status={place.status}')
        return place.result_type

    def find_best_match(self, location: str, place: Loc) -> bool:
        """
            Find the best scoring match for this location in the geoname dictionary.  
        #Args:  
            location:  location name, e.g. Los Angeles, California, USA   
            place:  Loc instance   
        #Returns: True if a match was found     
            place is updated with -- lat, lon, district, city, country_iso, result code  
        """
        #  First parse the location into <prefix>, city, <district2>, district1, country.
        #  Then look it up in the place db

        self.find_matches(location, place, plain_search=False)

        # Clear to just best entry
        flags = self.filter_results(place)
        # If multiple matches, truncate to first match
        if len(place.georow_list) > 0:
            place.georow_list = place.georow_list[:1]
            self.process_results(place=place, flags=flags)
            place.set_place_type()

            nm = f'{place.get_long_name(self.geo_build.output_replace_dct)}'
            print(f'Found pre=[{place.prefix}{place.prefix_commas}] Nam=[{nm}]')
            return True
        else:
            return False

    def find_geoid(self, geoid: str, place: Loc):
        """
        Lookup by geoid   
        #Args:   
            geoid:  Geonames.org geoid
            place:  Location fields in place are updated

        #Returns: None. Location fields in Loc are updated

        """
        place.geoid = geoid
        place.georow_list.clear()
        self.geo_build.geodb.s.lookup_geoid(georow_list=place.georow_list, geoid=place.geoid, place=place)
        if len(place.georow_list) > 0:
            # Copy geo row to Place
            #self.geo_build.geodb.copy_georow_to_place(row=place.georow_list[0], place=place, fast=True)
            flags = self.filter_results(place)
            self.process_results(place=place, flags=flags)
            # place.original_entry = place.get_long_name(None)
            place.result_type = GeoUtil.Result.STRONG_MATCH
        else:
            place.result_type = GeoUtil.Result.NO_MATCH

    def _find_type_as_city(self, place: Loc, typ):
        """
            Do a lookup using the field specifed by typ as a city name.  E.g. if typ is PlaceType.ADMIN1 then   
            use the place.admin1_name field to do the city lookup   
        #Args:   
            place: Loc instance   
            typ: Loc.PlaceType - Specifies which field to use as target for lookup   

        #Returns:  None   
            place.georow_list is updated with matches   
        """
        # place.standard_parse = False
        typ_name = ''
        if typ == Loc.PlaceType.CITY:
            # Try City as city (do as-is)
            typ_name = 'City'
            pass
        elif typ == Loc.PlaceType.ADMIN2:
            # Try ADMIN2 as city
            if place.admin2_name != '':
                # if '*' not in place.city:
                #    place.prefix += ' ' + place.city
                place.city = place.admin2_name
                place.admin2_name = ''
                typ_name = 'Admin2'
        elif typ == Loc.PlaceType.PREFIX:
            # Try Prefix as City
            if place.prefix != '':
                place.city = place.prefix
                # if '*' not in tmp:
                #    place.prefix = tmp
                typ_name = 'Prefix'
        elif typ == Loc.PlaceType.ADVANCED_SEARCH:
            # Advanced Search
            self.geo_build.geodb.lookup_place(place=place)
            return
        else:
            self.logger.warning(f'Unknown TYPE {typ}')

        if typ_name != '':
            self.logger.debug(f'2) Try {typ_name} as City.  Target={place.city}  pref [{place.prefix}] ')

            place.place_type = Loc.PlaceType.CITY
            self.geo_build.geodb.s.lookup_place(place=place)


    def _lookup_city_as_admin2(self, place: Loc, result_list):
        """
        Lookup place.city as admin2 name   
        #Args:   
            place:     
            result_list:   

        #Returns:   

        """
        # Try City as ADMIN2
        # place.standard_parse = False
        place.admin2_name = place.city
        place.city = ''
        place.place_type = Loc.PlaceType.ADMIN2
        self.logger.debug(f'  Try admin2  [{place.admin2_name}] as city [{place.get_five_part_title()}]')
        self.geo_build.geodb.lookup_place(place=place)
        result_list.extend(place.georow_list)

    def find_feature(self, place):
        """
        Lookup location with - name, country, and feature  

        #Args:   
            place: place.name, place.country, and place.feature are used for lookup  
        #Returns:   
            None.  place.georow_list contains matches   

        """
        self.logger.debug('Feature Search')
        self._find_type_as_city(place, place.place_type)

        #if len(place.georow_list) > 0:
            # Build list - sort and remove duplicates
            # self.logger.debug(f'Match {place.georow_list}')
            #flags = ResultFlags(limited=False, filtered=False)
            #self.process_results(place=place, flags=flags)
            #self.filter_results(place)

    def process_results(self, place: Loc, flags) -> None:
        """
            Update fields in place record using first entry in place.georow_list   
            Updates fields with available data: city, admin1, admin2, country, lat/long, feature, etc.   
        #Args:    
            place: Loc instance   
            flags: Flags tuple as returned by sort_results   

        #Returns:    
            None.  place instance fields are updated   
        """
        # self.logger.debug(f'**PROCESS RESULT:  Res={place.result_type}   Georow_list={place.georow_list}')
        if place.result_type == GeoUtil.Result.NOT_SUPPORTED:
            place.place_type = Loc.PlaceType.COUNTRY

        if place.result_type in GeoUtil.successful_match and len(place.georow_list) > 0:
            self.geo_build.geodb.copy_georow_to_place(row=place.georow_list[0], place=place, fast=False)
        elif len(place.georow_list) > 0 and place.result_type != GeoUtil.Result.NOT_SUPPORTED:
            # self.logger.debug(f'***RESULT={place.result_type} Setting to Partial')
            place.result_type = GeoUtil.Result.PARTIAL_MATCH

        place.set_place_type_text()

    @staticmethod
    def distance(lat_a: float, lon_a: float, lat_b: float, lon_b: float):
        """
        Returns rectilinear distance in degrees between two lat/longs   
        Args:   
            lat_a: latitude of point A   
            lon_a: longitude of point A   
            lat_b: latitude of point B   
            lon_b: longitude of point B   
        Returns: Rectilinear distance between two points   

        """
        return abs(lat_a - lat_b) + abs(lon_a - lon_b)

    def remove_duplicates(self, place):
        # sort list by LON/LAT and score so we can remove dups
        #for row in place.georow_list:
        #    self.logger.debug(row)
        if len(place.georow_list) == 0:
            self.logger.debug('empty')
            return
        rows_sorted_by_latlon = sorted(place.georow_list, key=itemgetter(GeoUtil.Entry.LON, GeoUtil.Entry.LAT, GeoUtil.Entry.SCORE))
        place.georow_list.clear()

        # Create a dummy 'previous' row so the comparison to previous entry works on the first item
        prev_geo_row = self.geo_build.make_georow(name='q', iso='q', adm1='q', adm2='q', lat=900, lon=900, feat='q', geoid='q', sdx='q')
        georow_idx = 0

        # Keep track of list by GEOID to ensure no duplicates in GEOID
        geoid_dict = {}  # Key is GEOID.  Value is List index

        # Find and remove if two entries are duplicates - defined as two items with:
        #  1) same GEOID or 2) same name and lat/lon is within Box Distance of 0.6 degrees
        for geo_row in rows_sorted_by_latlon:
            # self.logger.debug(f'{geo_row[GeoUtil.Entry.NAME]},{geo_row[GeoUtil.Entry.FEAT]} '
            #                  f'{geo_row[GeoUtil.Entry.SCORE]:.1f} {geo_row[GeoUtil.Entry.ADM2]}, '
            #                  f'{geo_row[GeoUtil.Entry.ADM1]} {geo_row[GeoUtil.Entry.ISO]}')
            if self._valid_year_for_location(place.event_year, geo_row[GeoUtil.Entry.ISO], geo_row[GeoUtil.Entry.ADM1], 60) is False:
                # Skip location if location name  didnt exist at the time of event WITH 60 years padding
                continue

            if self._valid_year_for_location(place.event_year, geo_row[GeoUtil.Entry.ISO], geo_row[GeoUtil.Entry.ADM1], 0) is False:
                # Flag if location name  didnt exist at the time of event
                date_filtered = True

            old_row = list(geo_row)
            geo_row = tuple(old_row)

            if geo_row[GeoUtil.Entry.NAME] != prev_geo_row[GeoUtil.Entry.NAME]:
                # Add this item to georow list since it has a different name.  Also add its idx to geoid dict
                place.georow_list.append(geo_row)
                geoid_dict[geo_row[GeoUtil.Entry.ID]] = georow_idx
                georow_idx += 1
            elif geoid_dict.get(geo_row[GeoUtil.Entry.ID]):
                # We already have an entry for this geoid.  Replace it if this one has better score
                row_idx = geoid_dict.get(geo_row[GeoUtil.Entry.ID])
                old_row = place.georow_list[row_idx]
                if geo_row[GeoUtil.Entry.SCORE] < old_row[GeoUtil.Entry.SCORE]:
                    # Same GEOID but this has better score so replace other entry.  
                    place.georow_list[row_idx] = geo_row
                    self.logger.debug(f'Better score {geo_row[GeoUtil.Entry.SCORE]} < '
                                      f'{old_row[GeoUtil.Entry.SCORE]} {geo_row[GeoUtil.Entry.NAME]}')
            elif self.distance(float(prev_geo_row[GeoUtil.Entry.LAT]), float(prev_geo_row[GeoUtil.Entry.LON]),
                               float(geo_row[GeoUtil.Entry.LAT]), float(geo_row[GeoUtil.Entry.LON])) > self.distance_cutoff:
                # Add this item to georow list since Lat/lon is different from previous item.  Also add its idx to geoid dict 
                place.georow_list.append(geo_row)
                geoid_dict[geo_row[GeoUtil.Entry.ID]] = georow_idx
                georow_idx += 1
            elif geo_row[GeoUtil.Entry.SCORE] < prev_geo_row[GeoUtil.Entry.SCORE]:
                # Same Lat/lon but this has better score so replace previous entry.  
                place.georow_list[georow_idx - 1] = geo_row
                geoid_dict[geo_row[GeoUtil.Entry.ID]] = georow_idx - 1
                # self.logger.debug(f'Use. {geo_row[GeoUtil.Entry.SCORE]}  < {prev_geo_row[GeoUtil.Entry.SCORE]} {geo_row[GeoUtil.Entry.NAME]}')

            prev_geo_row = geo_row

    def filter_results(self, place: Loc):
        """
            Sort place.georow_list by match score and eliminate duplicates   
        
        In case of duplicate, keep the one with best match score.   
        See MatchScore.match_score() for details on score calculation    
        Discard names that didnt exist at time of event (update result flag if this occurs)  
        Duplicates are defined as two items with:  
        1) same GEOID or 2) same name and similar lat/lon (within Rectilinear Distance of distance_cutoff degrees)  
        
        Add flag if we hit the lookup limit  
        #Args:   
            place:   
        
        #Returns:   
            ResultFlags(limited=limited_flag, filtered=date_filtered)   
        """

        date_filtered = False  # Flag to indicate whether we dropped locations due to event date
        # event_year = place.event_year

        if len(place.georow_list) > 100:
            limited_flag = True
        else:
            limited_flag = False

        if len(place.georow_list) == 0:
            self.logger.debug('EMPTY')
            return ResultFlags(limited=limited_flag, filtered=date_filtered)

        # Remove duplicate locations in list (have same name and lat/lon)
        self.remove_duplicates(place)

        gap_threshold = 0
        score = 0

        # Sort places in match_score order
        new_list = sorted(place.georow_list, key=itemgetter(GeoUtil.Entry.SCORE, GeoUtil.Entry.ADM1))
        #self.logger.debug(new_list[0])
        min_score = new_list[0][GeoUtil.Entry.SCORE]
        place.georow_list.clear()

        # Go through sorted list and only add items to georow_list that are close to the best score
        for rw, geo_row in enumerate(new_list):
            score = geo_row[GeoUtil.Entry.SCORE]
            # admin1_name = self.geo_build.geodb.get_admin1_name_direct(geo_row[GeoUtil.Entry.ADM1], geo_row[GeoUtil.Entry.ISO])
            # admin2_name = self.geo_build.geodb.get_admin2_name_direct(geo_row[GeoUtil.Entry.ADM1],
            #                                                          geo_row[GeoUtil.Entry.ADM2], geo_row[GeoUtil.Entry.ISO])

            base = MatchScore.Score.VERY_GOOD + (MatchScore.Score.GOOD / 3)
            gap_threshold = base + abs(min_score) * .6

            # Range to display when there is a strong match
            #if (min_score <= base and score > min_score + gap_threshold) or score > MatchScore.Score.VERY_POOR * 1.5:
            if score > min_score + gap_threshold:

                self.logger.debug(f'SKIP Score={score:.1f} Min={min_score:.1f} Gap={gap_threshold:.1f} [{geo_row[GeoUtil.Entry.PREFIX]}]'
                                  f' {geo_row[GeoUtil.Entry.NAME]},'
                                  f' {geo_row[GeoUtil.Entry.ADM2]},'
                                  f' {geo_row[GeoUtil.Entry.ADM1]} ')
            else:
                place.georow_list.append(geo_row)
                self.logger.debug(f'Score {score:.1f} [{geo_row[GeoUtil.Entry.PREFIX]}] {geo_row[GeoUtil.Entry.NAME]}, '
                                  f'AD2={geo_row[GeoUtil.Entry.ADM2]},'
                                  f' AD1={geo_row[GeoUtil.Entry.ADM1]} {geo_row[GeoUtil.Entry.ISO]}')

        #self.logger.debug(f'min={min_score:.1f}, gap2={gap_threshold:.1f} strong cutoff={min_score + gap_threshold:.1f}')

        if min_score <= MatchScore.Score.VERY_GOOD and len(place.georow_list) == 1 and place.result_type != GeoUtil.Result.NOT_SUPPORTED:
            place.result_type = GeoUtil.Result.STRONG_MATCH
        else:
            # Log item that we couldnt match
            if self.miss_diag_file:
                self.miss_diag_file.write(
                    f'Lookup {place.original_entry} thresh={gap_threshold} gap={score - min_score}\n\n')

        return ResultFlags(limited=limited_flag, filtered=date_filtered)

    def open(self, repair_database: bool, query_limit: int):
        """
        Open geodb.  Create DB if needed   
        #Args:  
            repair_database: If True, create DB if missing or damaged. 
            query_limit:  SQL query limit 
        #Returns:  
            True if error  
        """
        self._progress("Reading Geoname files...", 70)
        return self.geo_build.open_geodb(repair_database=repair_database, query_limit=query_limit)

    def _progress(self, msg: str, percent: int):
        if self.display_progress is not None:
            self.display_progress(percent, msg)
        else:
            self.logger.debug(msg)

    def is_country_valid(self, place: Loc) -> bool:
        """
        See if COUNTRY is present and is in the supported country list   

        #Args:   
            place:  

        #Returns:   
            True if country is valid   
        """
        if place.country_iso == '':
            place.result_type = GeoUtil.Result.NO_COUNTRY
            is_valid = False
        elif place.country_iso not in self.geo_build.supported_countries_dct:
            self.logger.debug(f'[{place.country_iso}] not supported')
            place.result_type = GeoUtil.Result.NOT_SUPPORTED
            place.place_type = Loc.PlaceType.COUNTRY
            is_valid = False
        else:
            is_valid = True

        return is_valid

    @staticmethod
    def _valid_year_for_location(event_year: int, country_iso: str, admin1: str, pad_years: int) -> bool:
        """
        See if this state/province had modern names at the time of the event. Only US and Canada currently supported.   
        For example, looking up New York for year 1410 would be invalid since it did not have an English name at that time.   
        Data is based on https://en.wikipedia.org/wiki/List_of_North_American_settlements_by_year_of_foundation   
        Geonames has support for date ranges on names but that data is sparsely populated and not used here yet.   

        #Args:   
            event_year: Year to check   
            country_iso: ISO-2 country code   
            admin1: State/Province name   
            pad_years: Number of years to pad for inaccuracy   

        #Returns: 
            True if valid   

        """
        if not event_year:
            return True

        # Try looking up start year by state/province
        place_year = admin1_name_start_year.get(f'{country_iso}.{admin1.lower()}')
        if place_year is None:
            # Try looking up start year by country
            place_year = country_name_start_year.get(country_iso)
        if place_year is None:
            place_year = -1

        if event_year + pad_years < place_year:
            # self.logger.debug(f'Invalid year:  incorporation={place_year}  event={event_year} loc={admin1},{iso} pad={padding}')
            return False
        else:
            return True

    @staticmethod
    def _feature_priority(feature: str):
        """
        Returns 0-100 for feature priority.  PP1M - city with 1 million people is zero 

        #Args:   
            feature:   

        #Returns:   
            0-100 for feature priority   

        """
        res = feature_priority.get(feature)
        if res:
            return 100.0 - res
        else:
            return 100.0 - feature_priority.get('DEFAULT')

    def open_diag_file(self, miss_diag_fname: str):
        """
        Open diagnostic file   

        #Args:
            miss_diag_fname:  

        #Returns:   

        """
        self.miss_diag_file = open(miss_diag_fname, 'wt')

    def close_diag_file(self):
        """
        Close diagnostic file   

        Returns:   
        """
        if self.miss_diag_file:
            self.miss_diag_file.close()

    @staticmethod
    def _restore_fields(place, save_place):
        # Restore fields that were overwritten
        place.city = save_place.city
        place.admin2_name = save_place.admin2_name
        place.prefix = save_place.prefix

    def close(self):
        """
        Close files and database   

        Returns: None   

        """
        if self.geo_build:
            self.geo_build.geodb.close()

    def log_results(self, geo_row_list):
        for geo_row in geo_row_list:
            self.logger.debug(f'    {geo_row[GeoUtil.Entry.NAME]}')


# Entries are only loaded from geonames.org files if their feature is in this list
# Highest value is for large city or capital
# Also, If there are 2 identical entries, we only add the one with higher feature priority.  
# These scores are also used for match ranking score
# Note: PP1M, P1HK, P10K do not exist in Geonames and are created by geodata.geodataBuild
feature_priority = {
    'PP1M': 100, 'ADM1': 96, 'PPLA': 96, 'PPLC': 96, 'PPLH': 96, 'ADM0': 93, 'PPLA2': 93, 'P1HK': 93,
    'P10K': 89, 'PPLX': 82, 'PP1K': 82, 'PRN': 71, 'PRSH': 71, 'RLG': 71, 'RUIN': 71, 'STG': 71,
    'PPLG': 75, 'RGN': 71, 'AREA': 71, 'NVB': 71, 'PPLA3': 71, 'ADMF': 71, 'PPLA4': 69, 'PPLF': 69, 'ADMX': 66,
    'PPLQ': 60, 'PPLR': 60, 'PPLS': 55, 'PPLL': 55, 'PPLW': 55, 'PPL': 55, 'SQR': 50, 'ISL': 50,
    'ADM2': 45, 'CH': 44, 'MSQE': 44, 'MSTY': 44, 'SYG': 44, 'MUS': 44, 'CMTY': 44, 'CSTL': 44, 'EST': 44,
    'MILB': 44, 'MNMT': 44, 'PAL': 44, 'HSTS': 42, 'PRK': 42, 'ADM3': 32,
    'BTL' : 22, 'HSP': 0, 'VAL': 0, 'MT': 0, 'ADM4': 0, 'DEFAULT': 0,
    }

ResultFlags = collections.namedtuple('ResultFlags', 'limited filtered')

# Starting year this country name was valid
country_name_start_year = {
    'cu': -1,
    }

# Starting year when modern names were valid for this state/province 
# https://en.wikipedia.org/wiki/List_of_North_American_settlements_by_year_of_foundation
admin1_name_start_year = {
    'us.al': 1711,
    'us.ak': 1774,
    'us.az': 1775,
    'us.ar': 1686,
    'us.ca': 1769,
    'us.co': 1871,
    'us.ct': 1633,
    'us.de': 1638,
    'us.dc': 1650,
    'us.fl': 1565,
    'us.ga': 1566,
    'us.hi': -1,
    'us.id': 1862,
    'us.il': 1703,
    'us.in': 1715,
    'us.ia': 1785,
    'us.ks': 1870,
    'us.ky': 1775,
    'us.la': 1699,
    'us.me': 1604,
    'us.md': 1633,
    'us.ma': 1620,
    'us.mi': 1784,
    'us.mn': 1820,
    'us.ms': 1699,
    'us.mo': 1765,
    'us.mt': 1877,
    'us.ne': 1854,
    'us.nv': 1905,
    'us.nh': 1638,
    'us.nj': 1624,
    'us.nm': 1598,
    'us.ny': 1614,
    'us.nc': 1653,
    'us.nd': 1871,
    'us.oh': 1785,
    'us.ok': 1889,
    'us.or': 1811,
    'us.pa': 1682,
    'us.ri': 1636,
    'us.sc': 1663,
    'us.sd': 1865,
    'us.tn': 1739,
    'us.tx': 1685,
    'us.ut': 1847,
    'us.vt': 1650,
    'us.va': 1607,
    'us.wa': 1825,
    'us.wv': 1788,
    'us.wi': 1685,
    'us.wy': 1867,
    'ca.01': 1795,
    'ca.02': 1789,
    'ca.03': 1733,
    'ca.04': 1766,
    'ca.05': 1583,
    'ca.07': 1604,
    'ca.08': 1673,
    'ca.09': 1764,
    'ca.10': 1541,
    'ca.11': 1862,
    'ca.12': 1700,
    'ca.13': 1700,
    'ca.14': 1700
    }
