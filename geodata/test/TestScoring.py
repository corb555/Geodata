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
from pathlib import Path

from geodata import GeoUtil, Geodata, Loc, MatchScore

features = ["ADM1", "ADM2", "ADM3", "ADM4", "ADMF", "CH", "CSTL", "CMTY", "EST ", "HSP", "FT",
            "HSTS", "ISL", "MSQE", "MSTY", "MT", "MUS", "PAL", "PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4",
            "PPLC", "PPLG", "PPLH", "PPLL", "PPLQ", "PPLX", "PRK", "PRN", "PRSH", "RUIN", "RLG", "STG", "SQR", "SYG", "VAL"]


class TestScoring(unittest.TestCase):
    scoring = None
    logger = None
    geodata = None
    test_idx = -1
    delta = 22

    # ===== TEST SCORING
    test_values = [
        # 0Target, 1Result, 2Feature, 3Expected Score
        ("Spilsby, Lincolnshire, , ", "Lincolnshire, Erie County, Ohio, United States", 'P10K', MatchScore.Score.POOR, 35),  # 0
        ("toronto,ontario,canada", "toronto,ontario,canada", 'PP1M', MatchScore.Score.VERY_GOOD, 0.0),  # 1

        ("toronto, canada", "toronto, canada", 'PPL', MatchScore.Score.VERY_GOOD, 3.5),  # 2

        ("chelsea,,england", "winchelsea, east sussex, england, united kingdom", 'PP1M', MatchScore.Score.GOOD, 29.25),  # 3
        ("chelsea,,england", "chelsea, greater london, england, united kingdom", 'PP1M', MatchScore.Score.VERY_GOOD, 29.25),  # 4

        ("sonderburg,denmark", "sonderborg kommune,region syddanmark, denmark", 'PP1M', MatchScore.Score.VERY_GOOD, 45.13636363636364),  # 5

        ("Paris, France", "Paris,, France", 'PP1M', MatchScore.Score.VERY_GOOD, 4.5),  # 6
        ("Paris, France.", "Paris,, France", 'PP1M', MatchScore.Score.VERY_GOOD, 4.5),  # 7

        ("London, England", "London, England, United Kingdom", 'PP1M', MatchScore.Score.VERY_GOOD, 0.0),  # 8
        ("London, England, United Kingdom", "London, England, United Kingdom", 'PP1M', MatchScore.Score.VERY_GOOD, 0.0),  # 9
        ("London, England, United Kingdom", "London, England, United Kingdom", 'HSP', MatchScore.Score.GOOD, 0.0),  # 10

        ("Domfront, Normandy", "Domfront-En-Champagne, Sarthe, Pays De La Loire, France", 'PP1M', MatchScore.Score.POOR, 63.00000000000001),  # 11
        ("Domfront, Normandy", "Domfront, Department De L'Orne, Normandie, France", 'PP1M', MatchScore.Score.GOOD, 1),  # 12

        ("St Quentin, Aisne, Picardy, France", "St Quentin, Departement De L'Aisne, Hauts De France, France", 'PP1M', MatchScore.Score.GOOD, 1),
        # 13

        ("Old Bond Street, London, Middlesex, England", " , London, Greater London, England, United Kingdom", 'PP1M', MatchScore.Score.GOOD, 1),  # 14
        ("Old Bond Street, London, Middlesex, England", " , Museum Of London, Greater London, England, United Kingdom", 'PPL',
         MatchScore.Score.POOR, 1),  # 15

        ("zxq, xyzzy", " , London, Greater London, England, United Kingdom", ' ', MatchScore.Score.VERY_POOR, 1),  # 16

        ("St. Margaret, Westminster, London, England", "London,England,United Kingdom", 'PPL', MatchScore.Score.POOR, 1),  # 17
        ("St. Margaret, Westminster, London, England", "Westminster Cathedral, Greater London, England", 'PPL', MatchScore.Score.POOR, 1),  # 18

        ("Canada", "Canada", 'ADM0', MatchScore.Score.VERY_GOOD, 1),  # 19
        ("France", ",France", 'ADM0', MatchScore.Score.VERY_GOOD, 1),  # 20

        ("barton, lancashire, england, united kingdom", "barton, lancashire, england, united kingdom", 'PPLL', MatchScore.Score.VERY_GOOD, 1),  # 21
        ("barton, lancashire, england, united kingdom", "barton, cambridgeshire, england, united kingdom", 'PPLL', MatchScore.Score.VERY_GOOD, 1),
        # 22

        ("testerton, norfolk, , england", "norfolk,england, united kingdom", "ADM2", MatchScore.Score.GOOD, 1),  # 23
        ("testerton, norfolk, , england", "testerton, norfolk, england,united kingdom", "PPLL", MatchScore.Score.GOOD, 1),  # 24

        ("Holborn, Middlesex, England", "Holborn, Greater London, England, United Kingdom", 'PP1M', MatchScore.Score.VERY_GOOD, 1),  # 25
        ("aisne, picardy, france", "aisne, picardy, france", 'PP1M', MatchScore.Score.VERY_GOOD, 1),  # 26
        ("braines, loire atlantique, france", "brains, loire atlantique, pays de la loire, france", 'PPL', MatchScore.Score.GOOD, 1),  # 27

        ("Berlin, , deutschland", "Berlin, Germany", 'PP1M', MatchScore.Score.VERY_GOOD, 1),  # 28
        ("Berl*n, , deutschland", "Berlin, Germany", 'PP1M', MatchScore.Score.VERY_GOOD, 1),  # 29
        ("toronto,nova scotia, canada", "toronto,ontario,canada", 'PPL', MatchScore.Score.POOR, 35),  # 30

        ]

    @classmethod
    def setUpClass(cls):
        TestScoring.logger = logging.getLogger(__name__)
        fmt = "%(levelname)s %(name)s.%(funcName)s %(lineno)d: %(message)s"
        logging.basicConfig(level=logging.DEBUG, format=fmt)
        TestScoring.logger.debug('Scoring')
        TestScoring.scoring = MatchScore.MatchScore()

        # Load test data
        directory = os.path.join(str(Path.home()), "geoname_test")
        TestScoring.geodata = Geodata.Geodata(directory_name=directory, progress_bar=None, enable_spell_checker=False,
                                              show_message=True, exit_on_error=False,
                                              languages_list_dct={'en'},
                                              feature_code_list_dct=features,
                                              supported_countries_dct={'fr', 'gb', 'ca', 'de', 'nl'})

        # Read in Geoname Gazeteer file - city names, lat/long, etc.
        start_time = time.time()
        error = TestScoring.geodata.open(repair_database=False, query_limit=105)
        end_time = time.time()

    def setUp(self) -> None:
        TestScoring.in_place: Loc.Loc = Loc.Loc()
        TestScoring.out_place: Loc.Loc = Loc.Loc()

    @staticmethod
    def run_test1(title: str, inp, out):
        print("*****TEST: WORD {}".format(title))
        out, inp = GeoUtil.remove_matching_sequences(out, inp, 2)
        return out, inp

    @staticmethod
    def run_test2(title: str, inp, out):
        print("*****TEST: CHAR {}".format(title))
        out, inp = GeoUtil.remove_matching_sequences(out, inp, 2)
        return out, inp
    
    @staticmethod
    def prepare_test(idx, in_place, res_place):
        TestScoring.test_idx = idx
        title = TestScoring.test_values[idx][0]
        inp = TestScoring.test_values[idx][0]
        res = TestScoring.test_values[idx][1]
        feat = TestScoring.test_values[idx][2]

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
    def run_test_score( idx) -> int:
        in_place = Loc.Loc()
        res_place = Loc.Loc()

        TestScoring.prepare_test(idx, in_place, res_place)
        score = TestScoring.scoring.match_score(in_place, res_place)

        print(f'#{idx} {score:.1f} [{in_place.original_entry.title().lower()}] [{res_place.get_five_part_title()}]')
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

        print(f'#{idx} {score:.1f} Out={sc:.1f}[{in_place.original_entry.title().lower()}] [{res_place.get_five_part_title()}]')
        return sc

    def test_one(self):
        self.run_test_score(0)
    
    
    #def test_output(self):
    #    for i in range(0, len(TestScoring.test_values)-1):
    #        with self.subTest(i=i):
    #            score = self.run_test_outscore(i)
    #            self.assertEqual(TestScoring.test_values[i][4], score,
    #                             msg=TestScoring.test_values[i][0])

    def test_score(self):
        for i in range(0, len(TestScoring.test_values)-1):
            with self.subTest(i=i):
                score = self.run_test_score(i)
                self.assertLess(score, TestScoring.test_values[i][3],
                                msg=TestScoring.test_values[i][0])
                self.assertGreaterEqual(score, TestScoring.test_values[i][3] - TestScoring.delta,
                                        msg=TestScoring.test_values[i][0])
    
    """
    # ===== TEST INPUT WORD REMOVAL

    def test_in01(self):
        title = "Input word1"
        out, inp = self.run_test1(title, "France", "Paris, France")
        self.assertEqual('', inp, title)

    def test_in02(self):
        title = "Input word2"
        out, inp = self.run_test1(title, "Westchester County, New York, USA", "Westchester, New York, USA")
        self.assertEqual('County,,', inp, title)

    def test_in03(self):
        title = "Input word1"
        out, inp = self.run_test1(title, "Frunce", "Paris, France")
        self.assertEqual('u', inp, title)

    def test_in04(self):
        title = "Input word1"
        out, inp = self.run_test1(title, "London,England,", "London,England,United Kingdom")
        self.assertEqual(',,', inp, title)

    def test_in05(self):
        title = "Input word1"
        out, inp = self.run_test1(title, "St. Margaret, Westminster, London, England", "London,England,United Kingdom")
        self.assertEqual('St. Margaret, Westmsr, ,', inp, title)

    def test_in06(self):
        title = "Input word1"
        out, inp = self.run_test1(title, "St. Margaret, Westminster, London, England", "Westminster Cathedral, Greater London, England")
        self.assertEqual('St. Marg, ,,', inp, title)

    # ===== TEST OUTPUT WORD REMOVAL

    def test_outrem01(self):
        title = "output word1"
        out, inp = self.run_test1(title, "France", "Paris, France")
        self.assertEqual('Paris,', out, title)

    def test_outrem02(self):
        title = "output word2"
        out, inp = self.run_test1(title, "Westchester County, New York, USA", "Westchester, New York, USA")
        self.assertEqual(',,', out, title)

    def test_outrem03(self):
        title = "output word1"
        out, inp = self.run_test1(title, "Frunce", "Paris, France")
        self.assertEqual('Paris, a', out, title)

    # ===== TEST total REMOVAL
    def test_tot01(self):
        title = "total word1"
        out, inp = self.run_test1(title, "France", "Paris, France")
        out, inp = self.run_test2(title, inp, out)
        self.assertEqual('', inp, title)

    def test_tot02(self):
        title = "total word1"
        out, inp = self.run_test1(title, "Frunce", "Paris, France")
        out, inp = self.run_test2(title, inp, out)
        self.assertEqual('u', inp, title)

    def test_tot03(self):
        title = "total word2"
        out, inp = self.run_test1(title, "Westchester County, New York, USA", "Westchester, New York, USA")
        out, inp = self.run_test2(title, inp, out)
        self.assertEqual('County,,', inp, title)

    # ===== TEST INPUT CHAR REMOVAL
    def test_char01(self):
        title = "Input word1"
        out, inp = self.run_test2(title, "France", "Paris, France")
        self.assertEqual('', inp, title)

    def test_char02(self):
        title = "Input word2"
        out, inp = self.run_test2(title, "Westchester County, New York, USA", "Westchester, New York, USA")
        self.assertEqual('County,,', inp, title)

    def test_char03(self):
        title = "Input word3"
        out, inp = self.run_test2(title, "Frunce", "Paris, France")
        self.assertEqual('u', inp, title)
    """

if __name__ == '__main__':
    unittest.main()
