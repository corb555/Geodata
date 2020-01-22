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
import unittest

from geodata import Loc

features = ["ADM1", "ADM2", "ADM3", "ADM4", "ADMF", "CH", "CSTL", "CMTY", "EST ", "HSP", "FT",
            "HSTS", "ISL", "MSQE", "MSTY", "MT", "MUS", "PAL", "PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4",
            "PPLC", "PPLG", "PPLH", "PPLL", "PPLQ", "PPLX", "PRK", "PRN", "PRSH", "RUIN", "RLG", "STG", "SQR", "SYG", "VAL"]


class TestClearPrefix(unittest.TestCase):
    geodata = None
    spell_check = None

    @classmethod
    def tearDownClass(cls):
        pass

    @classmethod
    def setUpClass(cls):
        TestClearPrefix.logger = logging.getLogger(__name__)
        fmt = "%(levelname)s %(name)s.%(funcName)s %(lineno)d: %(message)s"
        logging.basicConfig(level=logging.DEBUG, format=fmt)

    def setUp(self) -> None:
        #self.place: Loc.Loc = Loc.Loc()
        pass

    def run_test(self, title: str, pref: str, result:str)->str:
        print("*****TEST: {}".format(title))
        return Loc.Loc.matchscore_prefix(pref, result)

    def test_place_name01(self):
        title = "rue d'artagnan"
        name = self.run_test(title, "rue d'artagnan, braines",
                             'braines, loire atlantique,pays de la loire, france')
        self.assertEqual("rue d'artagnan", name, title)

    def test_place_name02(self):
        title = "Country  verify place name"
        name = self.run_test(title, "Chartres,D'Eure Et Loir",
                             "Chartres, Departement D'Eure Et Loir, Centre Val De Loire, France")
        self.assertEqual("", name, title)

    def test_place_name03(self):
        title = "Country  verify place name"
        name = self.run_test(title, "Newberry, Wiltshire",
                             "Newbury, Wiltshire, England, United Kingdom")
        self.assertEqual("", name, title)


if __name__ == '__main__':
    unittest.main()


"""


"""
