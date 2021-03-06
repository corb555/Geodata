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

import logging
import os
import time
import unittest

from geodata import GeoUtil, Geodata, Loc

halifax_lat = 44.646
bruce_cty_lat = 44.50009
albanel_lat = 48.91664
st_andrews_lat = 45.55614
halifax_name = "Halifax, Halifax Regional Municipality, Nova Scotia, Canada"
albanel_name = 'Albanel, Saguenay Lac St Jean, Quebec, Canada'

features = ["ADM1", "ADM2", "ADM3", "ADM4", "ADMF", "CH", "CSTL", "CMTY", "EST ", "HSP", "FT",
            "HSTS", "ISL", "MSQE", "MSTY", "MT", "MUS", "PAL", "PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4",
            "PPLC", "PPLG", "PPLH", "PPLL", "PPLQ", "PPLX", "PRK", "PRN", "PRSH", "RUIN", "RLG", "STG", "SQR", "SYG", "VAL"]


class TestGeodata(unittest.TestCase):
    geodata = None
    spell_check = None

    @classmethod
    def tearDownClass(cls):
        TestGeodata.geodata.close()

    @classmethod
    def setUpClass(cls):
        logger = logging.getLogger(__name__)
        fmt = "%(levelname)s %(name)s.%(funcName)s %(lineno)d: %(message)s"
        logging.basicConfig(level=logging.ERROR, format=fmt)

        # Load test data
        #directory = os.path.join(str(Path.home()), "Documents", "geoname_data")
        os.chdir('/Volumes/DISK2')
        directory = os.path.join("geoname_data")
        TestGeodata.geodata = Geodata.Geodata(directory_name=directory, display_progress=None,
                                              show_message=True, exit_on_error=False,
                                              languages_list_dct={'en'},
                                              feature_code_list_dct=features,
                                              supported_countries_dct={'fr', 'gb', 'ca', 'de', 'nl', 'us'},
                                              volume='/Volumes/DISK2')

        # Read in Geoname Gazeteer file - city names, lat/long, etc.
        start_time = time.time()
        error = TestGeodata.geodata.open(repair_database=True, query_limit=50)
        end_time = time.time()

        print(f'Elapsed {end_time - start_time}')
        if error:
            logger.info("Missing geoname Files.")
            logger.info('Requires ca.txt, gb.txt, de.txt from geonames.org in folder username/geoname_test')
            raise ValueError('Missing ca.txt, gb.txt, de.txt from geonames.org')

    def setUp(self) -> None:
        self.place: Loc.Loc = Loc.Loc()

    def run_lookup(self, title: str, entry: str):
        # if title not in ['903']:
        #    return 99.9, 'XX'

        print("*****TEST: {}".format(title))
        match = TestGeodata.geodata.find_best_match(entry, self.place)
        #flags = TestGeodata.geodata.filter_results(self.place)
        # If multiple matches, truncate to first match
        lat = self.place.lat
        if len(self.place.georow_list) > 0:
            lat = self.place.georow_list[0][GeoUtil.Entry.LAT]
            self.place.georow_list = self.place.georow_list[:1]
            #TestGeodata.geodata.process_results(place=self.place, flags=flags)
            self.place.set_place_type()

            nm = f'{self.place.get_long_name(TestGeodata.geodata.geo_build.output_replace_dct)}'
            print(f'Found pre=[{self.place.prefix}{self.place.prefix_commas}] Nam=[{nm}]')
            return float(lat), GeoUtil.capwords(self.place.prefix) + self.place.prefix_commas + nm
        elif match:
            nm = f'{self.place.get_long_name(TestGeodata.geodata.geo_build.output_replace_dct)}'
            print(f'Found pre=[{self.place.prefix}{self.place.prefix_commas}] Nam=[{nm}]')
            return float(lat), GeoUtil.capwords(self.place.prefix) + self.place.prefix_commas + nm
        else:
            return float(lat), 'NO MATCH'
        
    def test_place_name238(self):
        title = "Baden-Württemberg Region, Germany"
        lat, name = self.run_lookup(title, "Baden-Württemberg Region, Germany")
        self.assertEqual("Baden Wurttemberg, Germany", name, title)

    def test_place_name138(self):
        title = "Nogent Le Roi,france"
        lat, name = self.run_lookup(title, "Nogent Le Roi,france")
        self.assertEqual("Nogent Le Roi, Eure Et Loir, Centre Val De Loire, France", name, title)
        
    def test_place_name05(self):
        title = "Halifax"
        lat, name = self.run_lookup(title, "abc,Halifax, ,Nova Scotia, Canada")
        self.assertEqual("Abc, " + halifax_name, name, title)

    def test_place_name06(self):
        title = "City  verify place name"
        lat, name = self.run_lookup(title, "Halifax, , Nova Scotia, Canada")
        self.assertEqual(halifax_name, name, title)

    def test_place_name322(self):
        title = "City "
        lat, name = self.run_lookup(title, "pembro castle, pembrokeshire, wales, united kingdom")
        self.assertEqual("Pembroke Castle, Pembrokeshire, Wales, United Kingdom",
                         name, title)

    def test_place_name22(self):
        title = "City - Evreux, Eure, Normandy, France"
        lat, name = self.run_lookup(title, "Evreux, L'Eure, Normandy, France")
        self.assertEqual("Evreux, Eure, Normandie, France",
                         name, title)

    def test_place_name135(self):
        title = "aisne, picardy, france"
        lat, name = self.run_lookup(title, "l'aisne, Hauts-de-France, france")
        self.assertEqual("Aizenay, Vendee, Pays De La Loire, France", name, title)

    def test_place_name133(self):
        title = "test"
        lat, name = self.run_lookup(title, "st george's, hanover square, london, england")
        self.assertEqual("St George's, Hanover Square, Greater London, England, United Kingdom", name, title)

    def test_place_name11(self):
        title = "City - Lower Grosvenor Street, London, England "
        lat, name = self.run_lookup(title, "Lower Grosvenor Street, London,, England")
        self.assertEqual("Lower Grosvenor Street, London, Greater London, England, United Kingdom", name, title)

    def test_place_name17(self):
        title = "City - Rooms-Katholieke begraafplaats ‘Buitenveldert’, Amsterdam"
        lat, name = self.run_lookup(title, "Rooms-Katholieke begraafplaats ‘Buitenveldert’, Amsterdam, netherlands")
        self.assertEqual("Roman Catholic Cemetery Buitenveldert, Amsterdam, Gemeente Amsterdam, Provincie Noord Holland, Netherlands",
                         name, title)

    # ======= TEST Event Year handling

    def test_eventyear02(self):
        title = "City - good - but before city start"
        self.place.event_year = 1540
        lat, name = self.run_lookup(title, "Albanel,, Quebec, Canada")
        self.assertEqual(GeoUtil.Result.STRONG_MATCH, self.place.result_type, title)

    def test_eventyear03(self):
        title = "name"
        self.place.event_year = 1541
        lat, name = self.run_lookup(title, "Stuttgart,,,Germany")
        self.assertEqual("Stuttgart, Regierungsbezirk Stuttgart, Baden Wurttemberg, Germany", name, title)

    # ====== TEST find first match, find geoid

    def test_findgeoid01(self):
        title = "City - find first"
        entry = "Berlin,,,Germany"

        print("*****TEST: {}".format(title))
        TestGeodata.geodata.find_geoid('6077243', self.place)
        lat = float(self.place.lat)

        self.assertEqual(45.50884, lat, title)

    # ===== TEST RESULT CODES

    def test_res_code01(self):
        title = "City.  Good.  upper lowercase"
        lat, name = self.run_lookup(title, "AlbAnel,, Quebec, CanAda")
        self.assertEqual(GeoUtil.Result.STRONG_MATCH, self.place.result_type, title)

    def test_res_code02(self):
        title = "City - multiple matches"
        lat, name = self.run_lookup(title, "Alberton,, Ontario, Canada")
        self.assertEqual(GeoUtil.Result.MULTIPLE_MATCHES, self.place.result_type, title)

    def test_res_code11(self):
        title = "City and county  Good."
        lat, name = self.run_lookup(title, "baldwin mills,estrie,,canada")
        self.assertEqual(GeoUtil.Result.STRONG_MATCH, self.place.result_type, title)

    def test_res_code04(self):
        title = "city - Good. wrong Province"
        lat, name = self.run_lookup(title, "Halifax, ,Alberta, Canada")
        self.assertEqual(GeoUtil.Result.PARTIAL_MATCH, self.place.result_type, title)

    def test_res_code05(self):
        title = "multiple county - not unique"
        lat, name = self.run_lookup(title, "St Andrews,,,Canada")
        self.assertEqual(GeoUtil.Result.MULTIPLE_MATCHES, self.place.result_type, title)

    def test_res_code07(self):
        title = "City - good. wrong county"
        lat, name = self.run_lookup(title, "Natuashish, Alberta, ,Canada")
        self.assertEqual(GeoUtil.Result.MULTIPLE_MATCHES, self.place.result_type, title)

    def test_res_code08(self):
        title = "City - Bad"
        lat, name = self.run_lookup(title, "Alberton, ,,Germany")
        self.assertEqual(GeoUtil.Result.MULTIPLE_MATCHES, self.place.result_type, title)

    def test_res_code09(self):
        title = "State - Bad"
        lat, name = self.run_lookup(title, "skdfjd,Germany")
        self.assertEqual(GeoUtil.Result.NO_MATCH , self.place.result_type, title)

    def test_res_code10(self):
        title = "Country - blank"
        lat, name = self.run_lookup(title, '')
        self.assertEqual(GeoUtil.Result.NO_MATCH, self.place.result_type, title)

    # Country
    def test_res_code_country01(self):
        title = "Country - bad"
        lat, name = self.run_lookup(title, "squid")
        self.assertEqual(GeoUtil.Result.MULTIPLE_MATCHES, self.place.result_type, title)

    def test_res_code_country02(self):
        title = "No Country - Natuashish"
        lat, name = self.run_lookup(title, "Natuashish,, ")
        self.assertEqual(GeoUtil.Result.STRONG_MATCH, self.place.result_type, title)

    def test_res_code_country03(self):
        title = "No Country - Berlin"
        lat, name = self.run_lookup(title, "Berlin,,, ")
        self.assertEqual(GeoUtil.Result.MULTIPLE_MATCHES, self.place.result_type, title)

    def test_res_code_country04(self):
        title = "Country - not supported"
        lat, name = self.run_lookup(title, "Tokyo,,,Japan")
        self.assertEqual(GeoUtil.Result.NOT_SUPPORTED, self.place.result_type, title)

    def test_res_code_country05(self):
        title = "Country - not supported"
        lat, name = self.run_lookup(title, "Tokyo,Japan")
        self.assertEqual(GeoUtil.Result.NOT_SUPPORTED, self.place.result_type, title)

    # =====  TEST PLACE TYPES
    def test_place_code01(self):
        title = "Country  verify place type"
        lat, name = self.run_lookup(title, "Germany")
        self.assertEqual(Loc.PlaceType.COUNTRY, self.place.place_type, title)

    def test_place_code03(self):
        title = "State - Bad.  verify place type.  with prefix"
        lat, name = self.run_lookup(title, ",,Alberta,Canada")
        self.assertEqual(Loc.PlaceType.ADMIN1, self.place.place_type, title)

    def test_place_code04(self):
        title = "County  prioritize city.  verify place type "
        lat, name = self.run_lookup(title, "Halifax, Nova Scotia, Canada")
        self.assertEqual(Loc.PlaceType.CITY, self.place.place_type, title)

    def test_place_code24(self):
        title = "County .  verify place type "
        lat, name = self.run_lookup(title, "Halifax County, Nova Scotia, Canada")
        self.assertEqual(Loc.PlaceType.ADMIN2, self.place.place_type, title)

    def test_place_code05(self):
        title = "County prioritize city verify place type with prefix "
        lat, name = self.run_lookup(title, "abc,,Halifax, Nova Scotia, Canada")
        self.assertEqual(Loc.PlaceType.CITY, self.place.place_type, title)

    def test_place_code25(self):
        title = "County prioritize city verify place type with prefix "
        lat, name = self.run_lookup(title, "abc,,Halifax County, Nova Scotia, Canada")
        self.assertEqual(Loc.PlaceType.ADMIN2, self.place.place_type, title)

    def test_place_code06(self):
        title = "City  verify place type"
        lat, name = self.run_lookup(title, "Halifax, , Nova Scotia, Canada")
        self.assertEqual(Loc.PlaceType.CITY, self.place.place_type, title)

    def test_place_code07(self):
        title = "City  verify place type with prefix"
        lat, name = self.run_lookup(title, "abc,,Halifax, , Nova Scotia, Canada")
        self.assertEqual(Loc.PlaceType.CITY, self.place.place_type, title)

    # ===== TEST PERMUTATIONS for Exact lookups (non wildcard)

    # Country -------------
    def test_country01(self):
        title = "Country -  good"
        lat, name = self.run_lookup(title, "Canada")
        self.assertEqual('canada', self.place.country_name, title)

    def test_country02(self):
        title = "Country -  bad"
        lat, name = self.run_lookup(title, "abqwzflab")
        self.assertEqual('', self.place.country_iso, title)

    # Province ------------- Verify lookup returns correct place (latitude)


    def test_province04(self):
        title = "Province - bad name"
        lat, name = self.run_lookup(title, "notaplace,Canada")
        self.assertEqual('', self.place.admin1_id, title)

    # City - Verify lookup returns correct place (latitude) -------------------

    # ST ANDREWS
    def test_city03(self):
        title = "City - Good name, Saint"
        lat, name = self.run_lookup(title, "Saint Andrews,,Nova Scotia,Canada")
        self.assertEqual(st_andrews_lat, lat, title)

    def test_city04(self):
        title = "City - Good name, St "
        lat, name = self.run_lookup(title, "St Andrews,,Nova Scotia,Canada")
        self.assertEqual(st_andrews_lat, lat, title)

    def test_city09(self):
        title = "City - Good name, St. "
        lat, name = self.run_lookup(title, "St. Andrews,,Nova Scotia,Canada")
        self.assertEqual(st_andrews_lat, lat, title)

    def test_city07(self):
        title = "City - Good name, gray gull island "
        lat, name = self.run_lookup(title, "gray gull island,,newfoundland and labrador,Canada")
        self.assertEqual(47.5166, lat, title)

    def test_city08(self):
        title = "City - Good name, grey gull island with E "
        lat, name = self.run_lookup(title, "grey gull island,,newfoundland and labrador,Canada")
        self.assertEqual('Gray Gull Island, Newfoundland And Labrador, Canada', name, title)

    def test_city11(self):
        title = "City - Good , Alberton PEI vs Alberton Ontario"
        lat, name = self.run_lookup(title, "Alberton,,Prince Edward Island, Canada")
        self.assertEqual(46.81685, lat, title)

    def test_city12(self):
        title = "City - Good , Alberton Ontario vs Alberton PEI"
        lat, name = self.run_lookup(title, "Alberton,Rainy River District,Ontario, Canada")
        self.assertEqual(48.58318, lat, title)

    def test_city19(self):
        title = "City - good - Halifax ALBERTA Province"
        lat, name = self.run_lookup(title, "Halifax Coulee, Alberta, Canada")
        self.assertEqual(-113.78523, float(self.place.lon))

    def test_city20(self):
        title = "City - Good "
        lat, name = self.run_lookup(title, "Natuashish,,, Canada")
        self.assertEqual(55.91564, lat, title)

    def test_city21(self):
        title = "City - Good "
        lat, name = self.run_lookup(title, "Natuashish")
        self.assertEqual(55.91564, lat, title)

    def test_city22(self):
        title = "City -  wrong county but single match"
        lat, name = self.run_lookup(title, "Agassiz,, british columbia, Canada")
        self.assertEqual(49.23298, lat, title)

    def test_city24(self):
        title = "City - good. city,country"
        lat, name = self.run_lookup(title, "Natuashish,canada")
        self.assertEqual(55.91564, lat, title)

    #def test_city25(self):
    #   title = "City - from AlternateNames"
    #   lat, name = self.run_lookup(title, "Pic du port, canada")
    #   self.assertEqual(52.28333, lat, title)


    # ===== TEST WILDCARDS Verify lookup returns correct place (latitude)

    def test_wildcard02(self):
        title = "Province - wildcard province"
        lat, name = self.run_lookup(title, "Alb*ta, Canada")
        self.assertEqual("Alberta, Canada", name, title)

    def test_wildcard03(self):
        title = "City - good - wildcard city, full county and province"
        lat, name = self.run_lookup(title, "St. Andr,Madawaska ,new brunswick,Canada")
        self.assertEqual("St Andre, Madawaska County, New Brunswick Nouveau Brunswick, Canada", name, title)

    def test_wildcard04(self):
        title = "City - good - wildcard city, no county"
        lat, name = self.run_lookup(title, "Alb*el,, Quebec, CanAda")
        self.assertEqual("Albanel, Saguenay Lac St Jean, Quebec, Canada", name, title)

    def test_wildcard05(self):
        title = "City - good - wildcard city, no county, wild province"
        lat, name = self.run_lookup(title, "Alb*el,, Queb*, CanAda")
        self.assertEqual("Albanel, Saguenay Lac St Jean, Quebec, Canada", name, title)

    # ===== TEST ADMIN ID Verify lookup returns correct place (ID)

    def test_admin_id01(self):
        title = "Admin2 ID - good "
        lat, name = self.run_lookup(title, "Alberton,Rainy River District,Ontario, Canada")
        self.assertEqual('3559', self.place.admin2_id, title)

    def test_admin_id02(self):
        title = "Admin2 ID - good, no province "
        lat, name = self.run_lookup(title, "Alberton,Rainy River District, , Canada")
        self.assertEqual('3559', self.place.admin2_id, title)

    def test_admin_id03(self):
        title = "Admin1 ID - good "
        lat, name = self.run_lookup(title, "Nova Scotia,Canada")
        self.assertEqual('07', self.place.admin1_id, title)

    def test_admin_id04(self):
        title = "Admin1 ID - good -  "
        lat, name = self.run_lookup(title, "Baden wurttemberg, Germany")
        self.assertEqual('01', self.place.admin1_id, title)

    def test_admin_id05(self):
        title = "Admin1 ID - good.  With non-ASCII"
        lat, name = self.run_lookup(title, "Baden-Württemberg Region, Germany")
        self.assertEqual('01', self.place.admin1_id, title)

    def test_admin_id06(self):
        title = "Admin1 ID - good -  "
        lat, name = self.run_lookup(title, "Nova Scotia,Canada")
        self.assertEqual('07', self.place.admin1_id, title)

    def test_admin_id07(self):
        title = "Admin1 ID - good - abbreviated, non-ASCII "
        lat, name = self.run_lookup(title, "Baden-Württemberg, Germany")
        self.assertEqual('01', self.place.admin1_id, title)

    # ===== TEST PARSING Verify lookup returns correct place (name)
    def test_parse00(self):
        title = "***** Test Parse country"
        print(title)
        self.place.parse_place(place_name="aaa,Banff,Alberta's Rockies,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("canada", self.place.country_name, title)
        
    def test_parse01(self):
        title = "***** Test Parse country"
        print(title)
        self.place.parse_place(place_name="Alberta's Rockies,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("canada", self.place.country_name, title)

    def test_parse02(self):
        title = "***** Test Parse country"
        print(title)
        self.place.parse_place(place_name="Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("canada", self.place.country_name, title)
        
    def test_parse03(self):
        title = "***** Test Parse admin1"
        print(title)
        self.place.parse_place(place_name="aaa,Banff,Alberta's Rockies,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("alberta", self.place.admin1_name, title)

    def test_parse04(self):
        title = "***** Test Parse admin2"
        print(title)
        self.place.parse_place(place_name="aaa,Banff,Alberta's Rockies,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("alberta's rockies", self.place.admin2_name, title)
        
    def test_parse05(self):
        title = "***** Test Parse admin2"
        print(title)
        self.place.parse_place(place_name="Banff,Alberta's Rockies,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("alberta's rockies", self.place.admin2_name, title)

    def test_parse06(self):
        title = "***** Test Parse admin2"
        print(title)
        self.place.parse_place(place_name="Alberta's Rockies,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("", self.place.admin2_name, title)

    def test_parse106(self):
        title = "***** Test Parse "
        print(title)
        self.place.parse_place(place_name="Alberta's Rockies,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("alberta's rockies", self.place.city, title)

    def test_parse07(self):
        title = "***** Test Parse "
        print(title)
        self.place.parse_place(place_name="Banff,Alberta's Rockies,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("banff", self.place.city, title)
        
    def test_parse10(self):
        title = "***** Test Parse "
        print(title)
        self.place.parse_place(place_name="Banff,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("banff", self.place.city, title)

    def test_parse08(self):
        title = "***** Test Parse city with punctuation"
        print(title)
        self.place.parse_place(place_name="aaa,Banff!@#^&)_+-=;:<>/?,Alberta's Rockies,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("banff", self.place.city, title)

    def test_parse09(self):
        title = "***** Test Parse prefix"
        print(title)
        self.place.parse_place(place_name="pref,   abcde,Banff,Alberta's Rockies,Alberta,Canada", geo_db=TestGeodata.geodata.geo_build.geodb)
        self.assertEqual("pref abcde", self.place.prefix , title)

    # =====  TEST Verify Name match

    def test_place_name01(self):
        title = "Country  verify place name"
        lat, name = self.run_lookup(title, "Germany")
        self.assertEqual("Germany", name, title)

    def test_place_name03(self):
        title = "Alberta"
        lat, name = self.run_lookup(title, "Alberta,Canada")
        self.assertEqual("Alberta, Canada", name, title)

    def test_place_name04(self):
        title = "Halifax"
        lat, name = self.run_lookup(title, "Halifax, Nova Scotia, Canada")
        self.assertEqual(halifax_name, name, title)

    def test_place_name07(self):
        title = "City  verify place name with prefix"
        lat, name = self.run_lookup(title, "abc,Halifax, , Nova Scotia, Canada")
        self.assertEqual('Abc, '  + halifax_name, name, title)

    def test_place_name08(self):
        title = "province  verify place name with country"
        lat, name = self.run_lookup(title, "Alberta")
        self.assertEqual("Alberta, Canada", name, title)

    def test_place_name09(self):
        title = "City - Edensor, Derbyshire "
        lat, name = self.run_lookup(title, "Edensor, Derbyshire ")
        self.assertEqual("Edensor, Derbyshire, England, United Kingdom", name, title)

    def test_place_name09a(self):
        title = "City - Edensor, Derbyshire "
        lat, name = self.run_lookup(title, "Edensor, ,England, United Kingdom ")
        self.assertEqual("Edensor, Derbyshire, England, United Kingdom", name, title)

    def test_place_name12(self):
        title = "City - Lower Grosvenor Street, London, London, England"
        lat, name = self.run_lookup(title, "Lower Grosvenor Street, London, London, England")
        self.assertEqual("Lower Grosvenor Street, London, Greater London, England, United Kingdom", name, title)

    def test_place_name13(self):
        title = "City - Old Bond Street, London, Middlesex, England"
        lat, name = self.run_lookup(title, "Old Bond Street, London, Middlesex, England")
        self.assertEqual("Old Bond Street, London, Greater London, England, United Kingdom", name, title)

    def test_place_name14(self):
        title = "name"  # ""City - St. Margaret, Westminster, London, England"
        lat, name = self.run_lookup(title, "St. Margaret's church, Greater London,  England")
        self.assertEqual("St Margaret's Church, Greater London, England, United Kingdom", name, title)

    def test_place_name15(self):
        title = "City - Amsterdam, Zuiderkerk"
        lat, name = self.run_lookup(title, "Amsterdam, Zuiderkerk")
        self.assertEqual("Zuiderkerk, Gemeente Amsterdam, Provincie Noord Holland, Netherlands", name, title)

    def test_place_name16(self):
        title = "City - Amsterdam, Spiegelplein 9,,netherlands"
        lat, name = self.run_lookup(title, "Amsterdam, Spiegelplein 9,,netherlands")
        self.assertEqual("Spiegelplein 9, Amsterdam, Gemeente Amsterdam, Provincie Noord Holland, Netherlands", name, title)

    def test_place_name18(self):
        title = "City - Troyes, Aube,  , France"
        lat, name = self.run_lookup(title, "Troyes, L'Aube,  , France")
        self.assertEqual("Troyes, Aube, Grand Est, France",
                         name, title)

    def test_place_name19(self):
        title = "City - Hoxa ,Ronaldsay, orkney, scotland"
        lat, name = self.run_lookup(title, "Hoxa ,Ronaldsay,  scotland")
        self.assertEqual("Hoxa, South Ronaldsay, Orkney Islands, Scotland, United Kingdom",
                         name, title)

    def test_place_name20(self):
        title = "City - Paris, France"
        lat, name = self.run_lookup(title, "Paris, France")
        self.assertEqual("Paris, Paris, Ile De France, France",
                         name, title)

    def test_place_name21(self):
        title = "City - Oak Street, Toronto, Ontario, Canada"
        lat, name = self.run_lookup(title, "Oak Street, Toronto, Ontario, Canada")
        self.assertEqual("Oak Street, Toronto, Ontario, Canada",
                         name, title)

    def test_place_name23(self):
        title = "City - St. Janskathedraal, 's Hertogenbosch"
        lat, name = self.run_lookup(title, "St. Janskathedraal, 's Hertogenbosch,,Netherlands")
        self.assertEqual("St Janskathedraal, 'S Hertogenbosch, Gemeente 'S Hertogenbosch, Provincie Noord Brabant, Netherlands",
                         name, title)

    def test_place_name24(self):
        title = "City - Cambridge, cambridgeshire , England"
        lat, name = self.run_lookup(title, "Cambridge, cambridgeshire , England")
        self.assertEqual("Cambridge, Cambridgeshire, England, United Kingdom",
                         name, title)

    def test_place_name25(self):
        title = "City soundex - Parus, France"
        lat, name = self.run_lookup(title, "Parriss, Ile De France, France")
        self.assertEqual("Paris, Paris, Ile De France, France",
                         name, title)

    def test_place_name26(self):
        title = "City soundex - Toranto, Canada"
        lat, name = self.run_lookup(title, "Toranto, Ontario, Canada")
        self.assertEqual("Toronto, Ontario, Canada",
                         name, title)

    def test_place_name27(self):
        title = "County  verify place name with prefix "
        lat, name = self.run_lookup(title, "abc," + halifax_name)
        self.assertEqual("Abc, " + halifax_name, name, title)

    def test_place_name29(self):
        title = "County  verify not found "
        lat, name = self.run_lookup(title, "khjdfh,Halifax , Nova Scotia, Canada")
        self.assertEqual("Khjdfh, " + halifax_name, name, title)

    def test_place_name28(self):
        title = "Advanced search - albanel,--country=ca"
        lat, name = self.run_lookup(title, "albanel,--country=CA")
        self.assertEqual("Albanel, Saguenay Lac St Jean, Quebec, Canada", name, title)

    def test_place_name291(self):
        title = "Germany"
        lat, name = self.run_lookup(title, "Germany")
        self.assertEqual("Germany", name, title)

    def test_place_name292(self):
        title = "Germany"
        lat, name = self.run_lookup(title, "Germany.")
        self.assertEqual("Germany", name, title)

    def test_place_name129(self):
        title = "County  verify not found "
        lat, name = self.run_lookup(title, "Nova Scotia, Canada")
        self.assertEqual("Nova Scotia, Canada", name, title)

    def test_place_name130(self):
        title = "County  verify not found "
        lat, name = self.run_lookup(title, "newberry, wiltshire, england")
        self.assertEqual("Newbury, Wiltshire, England, United Kingdom", name, title)

    def test_place_name131(self):
        title = "County  verify not found "
        lat, name = self.run_lookup(title, "tretwr, llnfhngl cwm du, breconshire, wales,")
        self.assertEqual("Tretwr Llnfhngl, Llanfihangel Cwm Du, Sir Powys, Wales, United Kingdom", name, title)

    def test_place_name132(self):
        title = "hanover square"
        lat, name = self.run_lookup(title, "hanover square, england")
        self.assertEqual("Hanover Square, Greater London, England, United Kingdom", name, title)

    def test_place_name134(self):
        title = "mispelling winthrope"
        lat, name = self.run_lookup(title, "winthrope, lincolnshire, england")
        self.assertEqual("Winthorpe, Lincolnshire, England, United Kingdom", name, title)

    def test_place_name136(self):
        title = "brains, loire atlantique,pays de la loire, france"
        lat, name = self.run_lookup(title, "braines, loire atlantique,pays de la loire, france")
        self.assertEqual("Brains, Loire Atlantique, Pays De La Loire, France", name, title)

    def test_place_name137(self):
        title = "brains, loire atlantique,pays de la loire, france"
        lat, name = self.run_lookup(title, "rue d'artagnan, braines, loire atlantique,pays de la loire, france")
        self.assertEqual("Rue D'Artagnan, Brains, Loire Atlantique, Pays De La Loire, France", name, title)

    def test_place_name141(self):
        title = "County - good with prefix Bruce County"
        lat, name = self.run_lookup(title, "Bruce County, Ontario, Canada")
        self.assertEqual("Bruce County, Ontario, Canada", name, title)

    def test_place_name142(self):
        title = "County - Spilsby, Lincolnshire, , "
        lat, name = self.run_lookup(title, "Spilsby, Lincolnshire")
        self.assertEqual("Spilsby, Lincolnshire, England, United Kingdom", name, title)

    def test_place_name139(self):
        title = "Chartres,Eure Et Loir, Beauce Centre,  France"
        lat, name = self.run_lookup(title, "Chartres,D'Eure Et Loir,  ,  France")
        self.assertEqual("Chartres, Eure Et Loir, Centre Val De Loire, France", name, title)
        
    def test_place_name143(self):
        title = "cathedral winchester,,england"
        lat, name = self.run_lookup(title, "cathedral winchester,,england")
        self.assertEqual("Winchester Cathedral, Hampshire, England, United Kingdom", name, title)
    
    def test_place_name140(self):
        title = "Quierzy,Departement De L'Aisne,  , France"
        lat, name = self.run_lookup(title, "Quierzy,Departement De L'Aisne,  ,  France")
        self.assertEqual("Quierzy, Aisne, Hauts De France, France", name, title)
    
    
if __name__ == '__main__':
    unittest.main()
