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
import unittest
from pathlib import Path

from geodata import GeoUtil, Geodata, Loc, MatchScore

features = ["ADM1", "ADM2", "ADM3", "ADM4", "ADMF", "CH", "CSTL", "CMTY", "EST ", "HSP", "FT",
            "HSTS", "ISL", "MSQE", "MSTY", "MT", "MUS", "PAL", "PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4",
            "PPLC", "PPLG", "PPLH", "PPLL", "PPLQ", "PPLX", "PRK", "PRN", "PRSH", "RUIN", "RLG", "STG", "SQR", "SYG", "VAL"]

RW_OUT = 0
RW_IN = 1
RW_EXPECT = 2


class TestScoring(unittest.TestCase):
    scoring = None
    logger = None
    geodata = None
    test_idx = -1
    delta = 22

    # TEXT INPUT REMOVAL TEST CASES
    in_removal_test_cases = [
        # Output, Input, Expected
        ("France", "Paris, France", 'Paris,'),
        ("Westchester County, New York, USA", "Westchester, New York, USA", ',,'),
        ("Frunce", "Paris, France", 'Paris, a'),
        ("output, austria", "input, aus", 'in,'),
        ]

    # TEXT OUPUT REMOVAL TEST CASES
    out_removal_test_cases = [
        # Output, Input, Expected
        ("France", "Paris, France", ""),
        ("Frunce", "Paris, France", 'u'),
        ("Westchester County, New York, USA", "Westchester, New York, USA", 'County,,'),
        ("London,England,", "London,England,United Kingdom", ',,'),
        ("St. Margaret, Westminster, London, England", "London,England,United Kingdom", 'St. Margaret, Westmsr, ,'),
        ("St. Margaret, Westminster, London, England", "Westminster Cathedral, Greater London, England", 'St. Marg, ,,'),
        ("output, texas", "input, tex", 'out,as'),
        ]

    # MATCH SCORING TEST CASES
    score_test_cases = [
        # 0Target, 1Result, 2Feature, 3Expected Score, 4 xxx
        ("Spilsby, Lincolnshire, , ", "Lincolnshire, Erie County, Ohio, United States", 'P10K', 47),  # 0
        ("toronto,ontario,canada", "toronto,ontario,canada", 'PP1M', 0),  # 1

        ("toronto, canada", "toronto, canada", 'PPL', 5),  # 2

        ("chelsea,,england", "winchelsea, east sussex, england, united kingdom", 'PP1M', 35),  # 3
        ("chelsea,,england", "chelsea, greater london, england, united kingdom", 'PP1M', 6),  # 4

        ("sonderburg,denmark", "sonderborg kommune,region syddanmark, denmark", 'PP1M', 19),  # 5

        ("Paris, France", "Paris,, France", 'PP1M', 0),  # 6
        ("Paris, France.", "Paris,, France", 'PP1M', 0),  # 7

        ("London, England", "London, England, United Kingdom", 'PP1M', 0),  # 8
        ("London, England, United Kingdom", "London, England, United Kingdom", 'PP1M', 0),  # 9
        ("London, England, United Kingdom", "London, England, United Kingdom", 'HSP', 10),  # 10

        ("Domfront, Normandy", "Domfront-En-Champagne, Sarthe, Pays De La Loire, France",'PPL', 40),  # 11
        ("Domfront, Normandy", "Domfront, Department De L'Orne, Normandie, France", 'PP1M',15),  # 12

        ("St Quentin, Aisne, Picardy, France", "St Quentin, Departement De L'Aisne, Hauts De France, France", 'PP1M', 12),
        # 13

        ("Old Bond Street, London,  , England,United Kingdom", " , London, Greater London, England, United Kingdom", 'PP1M', 45),  # 14
        ("Old Bond Street, London, Middlesex, England,United Kingdom", " , Museum Of London, Greater London, England, United Kingdom", 'PPL',
          55),  # 15

        ("zxq, xyzzy", " , London, Greater London, England, United Kingdom", ' ', 120),  # 16

        ("St. Margaret, Westminster, London, England", "London,England,United Kingdom", 'PPL', 100),  # 17
        ("St. Margaret, Westminster, London, England", "Westminster Cathedral, Greater London, England", 'PPL',49),  # 18

        ("Canada", "Canada", 'ADM0', 9),  # 19
        ("France", ",France", 'ADM0', 9),  # 20

        ("barton, lancashire, england, united kingdom", "barton, lancashire, england, united kingdom", 'PPLL', 11),  # 21
        ("barton, lancashire, england, united kingdom", "barton, cambridgeshire, england, united kingdom", 'PPLL', 25),
        # 22

        ("testerton, norfolk, , england", "norfolk,england, united kingdom", "ADM2", 35),  # 23
        ("testerton, norfolk, , england", "testerton, norfolk, england,united kingdom", "PPLL", 11),  # 24

        ("Holborn, Middlesex, England", "Holborn, Greater London, England, United Kingdom", 'PP1M', 5),  # 25
        ("aisne, picardy, france", "aisne, picardy, france", 'PP1M', 5),  # 26
        ("braines, loire atlantique, france", "brains, loire atlantique, pays de la loire, france", 'PPL', 24),  # 27

        ("Berlin, , deutschland", "Berlin, Germany", 'PP1M', 6),  # 28
        ("Berl*n, , deutschland", "Berlin, Germany", 'PP1M', 12),  # 29
        ("toronto,nova scotia, canada", "toronto,ontario,canada", 'PPL', 24),  # 30

        ]

    @classmethod
    def setUpClass(cls):
        TestScoring.logger = logging.getLogger(__name__)
        fmt = "%(levelname)s %(name)s.%(funcName)s %(lineno)d: %(message)s"
        logging.basicConfig(level=logging.INFO, format=fmt)
        TestScoring.logger.debug('Scoring')
        TestScoring.scoring = MatchScore.MatchScore()

        # Load test data
        directory = os.path.join(str(Path.home()), "geoname_test")
        TestScoring.geodata = Geodata.Geodata(directory_name=directory, display_progress=None,
                                              show_message=True, exit_on_error=False,
                                              languages_list_dct={'en'},
                                              feature_code_list_dct=features,
                                              supported_countries_dct={'fr', 'gb', 'ca', 'de', 'nl'})

        # Read in Geoname Gazeteer file - city names, lat/long, etc.
        TestScoring.geodata.open(repair_database=False, query_limit=105)

    def setUp(self) -> None:
        TestScoring.in_place: Loc.Loc = Loc.Loc()
        TestScoring.out_place: Loc.Loc = Loc.Loc()

    @staticmethod
    def prepare_test(idx, in_place, res_place):
        TestScoring.test_idx = idx
        title = TestScoring.score_test_cases[idx][0]
        inp = TestScoring.score_test_cases[idx][0]
        res = TestScoring.score_test_cases[idx][1]
        feat = TestScoring.score_test_cases[idx][2]

        in_place.original_entry = inp
        in_place.parse_place(place_name=inp, geo_files=TestScoring.geodata.geo_build)
        if in_place.country_name == '' and in_place.country_iso != '':
            in_place.country_name = TestScoring.geodata.geo_files.geodb.get_country_name(in_place.country_iso)

        res_place.original_entry = res
        res_place.parse_place(place_name=res, geo_files=TestScoring.geodata.geo_build)
        res_place.feature = feat
        if res_place.country_name == '' and res_place.country_iso != '':
            res_place.country_name = TestScoring.geodata.geo_files.geodb.get_country_name(res_place.country_iso)

    @staticmethod
    def run_test_score(idx) -> int:
        in_place = Loc.Loc()
        res_place = Loc.Loc()

        TestScoring.prepare_test(idx, in_place, res_place)
        score = TestScoring.scoring.match_score(in_place, res_place)

        print(f'     {idx}) {score:.1f} In=[{in_place.original_entry.title().lower()}] Out=[{res_place.get_five_part_title()}]')
        return score

    @staticmethod
    def run_test_inscore(idx) -> int:
        in_place = Loc.Loc()
        res_place = Loc.Loc()

        TestScoring.prepare_test(idx, in_place, res_place)
        score = TestScoring.scoring.match_score(in_place, res_place)
        sc = TestScoring.scoring.in_score

        print(f'#{idx} {score:.1f} In={sc:.1f}[{in_place.original_entry.title().lower()}] [{res_place.get_five_part_title()}]')
        return sc

    @staticmethod
    def run_test_outscore(idx) -> int:
        in_place = Loc.Loc()
        res_place = Loc.Loc()

        TestScoring.prepare_test(idx, in_place, res_place)
        score = TestScoring.scoring.match_score(in_place, res_place)

        sc = TestScoring.scoring.out_score

        print(f'{idx}) {score:.1f} Out={sc:.1f}[{in_place.original_entry.title().lower()}] [{res_place.get_five_part_title()}]')
        return sc

    @staticmethod
    def remove_matches(out, inp):
        out, inp = GeoUtil.remove_matching_sequences(out, inp, 2)
        return out, inp

    def test_one(self):
        # Just run match score test zero
        self.run_test_score(0)

    def test_score(self):
        # Run match scoring tests
        for i in range(0, len(TestScoring.score_test_cases) ):
            with self.subTest(i=i):
                res = self.run_test_score(i)
                targ = TestScoring.score_test_cases[i][3]
                delta = abs(res - targ) 
                print(f'DELTA={delta:.1f} res={res:.1f} target={targ:.1f}')
                self.assertLess(delta, 10, msg=TestScoring.score_test_cases[i][0])
    
    def test_out_removal(self):
        # Test removal of characters in output result
        print(f'OUTPUT Len={len(TestScoring.out_removal_test_cases)}')
        for i in range(0, len(TestScoring.out_removal_test_cases)):
            with self.subTest(i=i):
                print("*****TEST: OUTPUT removal ")
                row = TestScoring.out_removal_test_cases[i]
                out, inp = self.remove_matches(out=row[RW_OUT], inp=row[RW_IN])
                print(f'{i}) out=[{row[RW_OUT]}] in=[{row[RW_IN]}] in result=[{inp}]=[{row[RW_EXPECT]}]')

                self.assertEqual(row[RW_EXPECT], out, 'output')

    def test_input_removal(self):
        # Test removal of characters in user input 
        print(f'INPUT Len={len(TestScoring.in_removal_test_cases)}')

        for i in range(0, len(TestScoring.in_removal_test_cases)):
            with self.subTest(i=i):
                print("*****TEST: INPUT removal ")
                row = TestScoring.in_removal_test_cases[i]
                out, inp = self.remove_matches(out=row[RW_OUT], inp=row[RW_IN])
                print(f'{i}) out=[{row[RW_OUT]}] in=[{row[RW_IN]}] in result=[{inp}]=[{row[RW_EXPECT]}]')

                self.assertEqual(row[RW_EXPECT], inp, 'input')
    

if __name__ == '__main__':
    unittest.main()
