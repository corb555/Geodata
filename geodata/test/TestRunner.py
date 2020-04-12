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

CS_CASE = 0
CS_EXPECTED = 1


class TestRunner(unittest.TestCase):
    """
    Runs all the test cases specified in cases[] and compares them with expected result
    """
    # [(Target, Expected_Result)]
    cases = []

    def test_score(self):
        # Run all tests
        print (TestRunner.cases)
        for i in range(0, len(TestRunner.cases)):
            with self.subTest(i=i):
                res = self.run_test(TestRunner.cases[i][CS_CASE])
                print(f'{i})\t{res}\t{TestRunner.cases[i][CS_CASE]}\t'
                      f'{TestRunner.cases[i][CS_EXPECTED]}')
                self.assertEqual(res, TestRunner.cases[i][CS_EXPECTED], msg=f' \nTest #{i}  [{TestRunner.cases[i][CS_CASE]}] '
                f'Got: [{res}] Exp: [{TestRunner.cases[i][CS_EXPECTED]}]')

    @classmethod
    def setUpClass(cls):
        TestRunner.logger = logging.getLogger(__name__)
        fmt = "%(levelname)s %(name)s.%(funcName)s %(lineno)d: %(message)s"
        logging.basicConfig(level=logging.INFO, format=fmt)

    @staticmethod
    def run_test(test_case):
        """
        User must create this. It is called with each test case and must return result
        Args:
            test_case: 

        Returns:  Must return result of test

        """

        return ''

    def setUp(self) -> None:
        pass

    def tearDown(self) -> None:
        pass
