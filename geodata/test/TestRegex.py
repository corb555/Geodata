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
import unittest

from geodata import GeoUtil
from geodata.test.TestRunner import TestRunner

noise_words = [
    # apply this list of regex substitutions for match scoring
    (r'normandy american ', 'normandie american ', 5),
    (r'nouveau brunswick', ' ', 5),
    (r'westphalia', 'westfalen', 5),
    (r'departement', 'department', 5),
    (r'royal borough of windsor and maidenhead', 'berkshire', 2),
    (r'regional municipality', 'county', 5),
    (r'kathedrale', 'cathedral', 2),
    (r'citta metropolitana di ', ' ', 5),
    (r'kommune', '', 5),
    (r"politischer bezirk ", ' ', 5),
    (r'regional', ' ', 5),
    (r'region', ' ', 5),
    (r'abbey', 'abbey', 5),
    (r'priory', 'abbey', 5),
    (r'greater', ' ', 5),
    (r'\bde\b', ' ', 99),
    (r'\bdi\b', ' ', 99),
    (r'\bdu\b', ' ', 99),
    (r'\bof\b', ' ', 99),

    (r"\bl'", '', 5),

    (r'erry', 'ury', 5),
    (r'ery', 'ury', 5),
    (r'borg', 'burg', 5),
    (r'bourg', 'burg', 5),
    (r'urgh', 'urg', 5),
    (r'mound', 'mund', 5),
    (r'ourne', 'orn', 5),
    (r'ney', 'ny', 5),
    ]

phrase_cleanup = [
    # always apply this list of regex substitutions 
    (r'  +', ' ', 2),  # Strip multiple space to single space
    (r'  +', ' ', 99),  # Strip multiple space to single space
    (r'\bmt\b', 'mount ', 5),
    (r'\br\.k\. |\br k ', 'roman catholic ', 5),
    (r'\brooms katholieke\b', 'roman catholic', 5),

    (r'sveti |saints |sainte |sint |saint |sankt |st\. ', 'st ', 2),  # Normalize Saint to St
    (r' co\.', ' county', 5),  # Normalize County
    (r'united states of america', 'usa', 5),  # Normalize to USA   begraafplaats
    (r'united states', 'usa', 5),  # Normalize to USA

    (r'cimetiere', 'cemetery', 5),  # 
    (r'begraafplaats', 'cemetery', 5),  # 

    (r'town of ', '', 5),  # - remove town of
    (r'city of ', '', 5),  # - remove city of
    (r'county of ([^,]+)', r'\g<1> county', 5),  # Normalize 'Township of X' to 'X Township'
    (r'township of ([^,]+)', r'\g<1> township', 5),  # Normalize 'Township of X' to 'X Township'
    (r'cathedral of ([^,]+)', r'\g<1> cathedral', 5),  # Normalize 'Township of X' to 'X Township'
    (r'palace of ([^,]+)', r'\g<1> palace', 5),  # Normalize 'Township of X' to 'X Township'
    (r'castle of ([^,]+)', r'\g<1> castle', 5),  # Normalize 'Township of X' to 'X Township'

    (r"'(\w{2,})'", r"\g<1>", 98),  # remove single quotes around word, but leave apostrophes
    ]

no_punc_remove_commas = [
    # Regex to remove most punctuation including commas
    (r"[^a-z0-9 $*']+", " ",1)
    ]

no_punc_keep_commas = [
    # Regex to remove most punctuation but keep commas
    (r"[^a-z0-9 $*,']+", " ",1)
    ]

class TestRegex(TestRunner):
    # [(Target, Expected_Result)]
    cases2 = [
        ('kathedrale of westphalia kommune ', 'westfalen cathedral'),  # kathedrale, westfalen, kommune
        ]
    
    cases = [
        ('12 baker st, Man!@#%^&(chester, , England', '12 baker st, man chester, , england'),  # punctuation
        ('kathedrale of westphalia kommune ', 'westfalen cathedral'),  # kathedrale, westfalen, kommune
        ('town of augustin', 'augustin'), #town of
        ('county of ferand', 'ferand county'),  # xx of
        ('Le Mont Saint Michel', 'le mont st michel'),  #  Saint
        ]

                
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        TestRunner.cases = TestRegex.cases
        TestRegex.phrase_rgx_keep_commas = GeoUtil.RegexList(no_punc_keep_commas + phrase_cleanup + noise_words)
        TestRegex.phrase_rgx_remove_commas = GeoUtil.RegexList(no_punc_remove_commas + phrase_cleanup + noise_words)
        
    @staticmethod
    def run_test(case):
        res = TestRegex.phrase_rgx_keep_commas.sub(case)
        return res

if __name__ == '__main__':
    unittest.main()
