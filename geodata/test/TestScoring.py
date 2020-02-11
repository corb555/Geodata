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

CS_TARGET = 0
CS_RESULT = 1
CS_FEATURE = 2
CS_SCORE = 3
CS_IN_SCORE = 4


class TestScoring(unittest.TestCase):
    scoring = None
    logger = None
    geodata = None
    test_idx = -1
    delta = 22

    # TEXT INPUT REMOVAL TEST CASES
    in_removal_test_cases = [
        # Output, Input, Expected
        ("France", "Paris, France", 'Paris,'),  # 0
        ("Westchester County, New York, USA", "Westchester, New York, USA", ',,'),  # 1
        ("Frunce", "Paris, France", 'Paris, a'),  # 2
        ("output, austria", "input, aus", 'in,'),  # 3
        ("Blore  , Staffordshire,england, united kingdom", " Blore Heath, Staffordshire,england, united kingdom", 'Heath,,,')  # 4
        ]

    # TEXT OUTPUT REMOVAL TEST CASES
    out_removal_test_cases = [
        # Output, Input, Expected
        ("France", "Paris, France", ""),
        ("Frunce", "Paris, France", 'u'),
        ("Westchester County, New York, USA", "Westchester, New York, USA", 'County,,'),
        ("London,England,", "London,England,United Kingdom", ',,'),
        ("St. Margaret, Westminster, London, England", "London,England,United Kingdom", 'St. Margaret, Westmsr, ,'),
        ("St. Margaret, Westminster, London, England", "Westminster Cathedral, Greater London, England", 'St. Marg, ,,'),
        ("output, texas", "input, tex", 'out,as'),
        ("Blore  , Staffordshire,england, united kingdom", " Blore Heath, Staffordshire,england, united kingdom", ',,,')
        ]

    # MATCH SCORING TEST CASES

    score_test_cases = [
        # 0 Target, 1 Result, 2 Feature, 3 Overall Score, 4 Input score,
        ("Spilsby, Lincolnshire", "Lincolnshire, Erie County, Ohio, United States", 'P10K', 67, 64),  # 0

        ("toronto,ontario,canada", "toronto,ontario,canada", 'PP1M', -8, 0),  # 1
        ("toronto, canada", "toronto, canada", 'PPL', -6, 0),  # 2

        ("chelsea,,england", "a,winchelsea, east sussex, england, united kingdom", 'PP1M', 13, 12),  # 3
        ("chelsea,,england", "a,chelsea, greater london, england, united kingdom", 'PP1M', 0, 0),  # 4

        ("sonderburg,denmark", "sonderborg kommune,region syddanmark, denmark", 'PP1M', -2, 0),  # 5

        ("Paris, France", "Paris,, France", 'PP1M', -8, 0),  # 6
        ("Paris, France.", "Paris,, France", 'PP1M', -8, 0),  # 7

        ("London, England", "London, England, United Kingdom", 'PP1M', -8, 0),  # 8
        ("London, England, United Kingdom", "London, England, United Kingdom", 'PP1M', -8, 0),  # 9
        ("London, England, United Kingdom", "London, England, United Kingdom", 'HSP', -3, 0),  # 10

        ("Domfront, Normandy", "Domfront-En-Champagne, Sarthe, Pays De La Loire, France", 'PPL', 36, 37),  # 11
        ("Domfront, Normandy", "Domfront, Department De L'Orne, Normandie, France", 'PP1M', 0, 0),  # 12

        ("St Quentin, Aisne, Picardy, France", "St Quentin, Departement De L'Aisne, Hauts De France, France",
         'PP1M', -5, 9),  # 13

        ("Old Bond Street, London,  , England,United Kingdom", " , London, Greater London, England, United Kingdom", 'PP1M', 18, 0),  # 14
        ("Old Bond Street, London, Middlesex, England,United Kingdom", " , Museum Of London, Greater London, England, United Kingdom",
         'PPL', 35, 24),  # 15

        ("zxq, xyzzy", " , London, Greater London, England, United Kingdom", ' ', 91, 90),  # 16

        ("St. Margaret, Westminster, London, England,", "London,England,United Kingdom", 'PPL', 78, 73),  # 17
        ("St. Margaret, Westminster, London, England,", "Westminster Cathedral, Greater London, England", 'PPL', 40, 26),  # 18

        ("Canada", "Canada", 'ADM0', -10, 0),  # 19
        ("France", ",France", 'ADM0', -10, 0),  # 20

        ("barton, lancashire, england, united kingdom", "barton, lancashire, england, united kingdom", 'PPLL', -6, 0),  # 21
        ("barton, lancashire, england, united kingdom", "barton, cambridgeshire, england, united kingdom", 'PPLL', -3, 4),
        # 22

        ("testerton, norfolk, england", "norfolk,england, united kingdom", "ADM2", 48, 66),  # 23
        ("testerton, norfolk, england", "testerton, norfolk, england,united kingdom", "PPLL", -6, 0),  # 24

        ("Holborn, Middlesex, England", "Holborn, Greater London, England, United Kingdom", 'PP1M', -8, 0),  # 25
        ("aisne, picardy, france", "aisne, picardy, france", 'PP1M', -8, 0),  # 26
        ("braines, loire atlantique, france", "brains, loire atlantique, pays de la loire, france", 'PPL', 8, 7),  # 27

        ("Berlin, , deutschland", "Berlin, Germany", 'PP1M', -8, 0),  # 28
        ("Berl*n, , deutschland", "Berlin, Germany", 'PP1M', -11, 11),  # 29
        ("toronto,nova scotia, canada", "toronto,ontario,canada", 'PPL', 3, 8),  # 30
        ("Blore Heath , Staffordshire,england", " Blore Heath, Staffordshire,england, united kingdom", "XXX", -3, 0),  # 31
        ("Blore Heath , Staffordshire,england", " Blore , Staffordshire,england, united kingdom", "XXX", 16, 24),  # 32
        ("Blore Heath , Staffordshire,england", " Staffordshire,england, united kingdom", "XXX", 48, 60),  # 33
        ("Abc, Halifax, , Nova Scotia, Canada", "Army Museum Halifax Citadel, , Nova Scotia, Canada", "XXX", 48, 38),  # 34
        ("Abc, Halifax, , Nova Scotia, Canada", "Abc, Halifax, , Nova Scotia, Canada", "XXX", 11, 0),  # 35
        ("Nogent Le Roi,france", "Nogent Le Roi, Departement D'Eure Et Loir, Centre Val De Loire, France", "XXX", 15, 0),  # 36
        ("Nogent Le Roi,france", "Le Roi, Nogent Sur Eure, Eure Et Loir, Centre Val De Loire, France", "XXX", 36, 23),  # 37
        # Tiverton, Devon, England, United Kingdom
        ("Tiverton,,,", "Tiverton, Devon, England, United Kingdom", 'PPL', 25, 10),  # 38
        ("Spilsby, Lincolnshire", "Lincolnshire, Erie County, Ohio, United States", 'P10K', 67, 64),  # 39
        ("Spilsby, Lincolnshire", "Spilsby, Lincolnshire, England, United Kingdom", 'P10K', 17, 64),  # 40

        ]

    # 0 Target, 1 Result, 2 Feature, 3 Overall Score, 4 Input score,
    def test_score(self):
        # Run match scoring tests
        i = 4
        #if True:
        for i in range(0, len(TestScoring.score_test_cases)):
            with self.subTest(i=i):
                res = self.run_test_score(i)
                targ = TestScoring.score_test_cases[i][CS_SCORE]
                delta = abs(res - targ)
                self.assertLess(delta, 3, msg=f' SCORE={res:.1f} TARGET={targ:.1f}')
    """
    def test_input_score(self):
        # Run match scoring tests
        for i in range(0, len(TestScoring.score_test_cases)):
            with self.subTest(i=i):
                res = self.run_test_inscore(i)
                targ = TestScoring.score_test_cases[i][CS_IN_SCORE]
                delta = abs(res - targ)
                print(f'DELTA={delta:.1f} SCORE={res:.1f} TARGET={targ:.1f}')
                self.assertLess(delta, 3, msg=f'INPUT SCORE={res:.1f} TARGET={targ:.1f}')

    def test_one(self):
        # Just run a single match score test for debugging (not test suite)
        self.run_test_score(31)

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
                
    """
    @classmethod
    def setUpClass(cls):
        TestScoring.logger = logging.getLogger(__name__)
        fmt = "%(levelname)s %(name)s.%(funcName)s %(lineno)d: %(message)s"
        logging.basicConfig(level=logging.DEBUG, format=fmt)
        TestScoring.logger.debug('Scoring')
        TestScoring.scoring = MatchScore.MatchScore()

        # Load test data
        directory = os.path.join(str(Path.home()), 'Documents', "geoname_data")
        TestScoring.geodata = Geodata.Geodata(directory_name=directory, display_progress=None,
                                              show_message=True, exit_on_error=False,
                                              languages_list_dct={'en'},
                                              feature_code_list_dct=features,
                                              supported_countries_dct={'fr', 'gb', 'ca', 'de', 'nl', 'us'})

        # Read in Geoname Gazeteer file - city names, lat/long, etc.
        TestScoring.geodata.open(repair_database=False, query_limit=105)

    def setUp(self) -> None:
        TestScoring.in_place: Loc.Loc = Loc.Loc()
        TestScoring.out_place: Loc.Loc = Loc.Loc()

    @staticmethod
    def prepare_test(idx, in_place, res_place):
        TestScoring.test_idx = idx
        inp = TestScoring.score_test_cases[idx][CS_TARGET]
        res = TestScoring.score_test_cases[idx][CS_RESULT]
        feat = TestScoring.score_test_cases[idx][CS_FEATURE]

        TestScoring.logger.debug(f'======================= Prepare TEST {idx}: {inp}')

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
    def remove_matches(out, inp):
        out, inp = GeoUtil.remove_matching_sequences(text1=out, text2=inp, min_len=2)
        return out, inp

    @staticmethod
    def run_test_score(idx) -> int:
        in_place = Loc.Loc()
        res_place = Loc.Loc()

        TestScoring.prepare_test(idx, in_place, res_place)
        score = TestScoring.scoring.match_score(in_place, res_place)

        TestScoring.logger.debug(f'     {idx}) {score:.1f} In=[{in_place.original_entry.title().lower()}] Out=[{res_place.get_five_part_title()}]')
        return score

    @staticmethod
    def run_test_inscore(idx) -> int:
        target_place = Loc.Loc()
        result_place = Loc.Loc()

        TestScoring.logger.debug(f'TEST INPUT SCORE:')

        TestScoring.prepare_test(idx, target_place, result_place)
        TestScoring.logger.debug(f'prepare_test: INP={target_place.city1},{target_place.admin2_name},'
                                 f'{target_place.admin1_name},{target_place.country_name}'
                                 f' RES={result_place.city1},{result_place.admin2_name},'
                                 f'{result_place.admin1_name},{result_place.country_name}')

        # Create full, normalized titles (prefix,city,county,state,country)
        result_title, result_tokens, target_title, target_tokens = MatchScore._prepare_input(target_place, result_place)

        # Calculate score for  percent of input target text that matched result
        sc = TestScoring.scoring._calculate_weighted_score(target_tokens, result_tokens)

        print(f'#{idx} SCORE={sc:.1f} In={sc:.1f}[{target_place.original_entry.title().lower()}] [{result_place.get_five_part_title()}]')
        return sc
    
    
if __name__ == '__main__':
    unittest.main()
