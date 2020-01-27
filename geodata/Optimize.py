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
"""    Example program for Geodata gazeteer.  
"""
import logging
import os
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

from geodata import Geodata, Loc


class Optimize:
    """
    Example program for Geodata gazeteer.  
    0. pip3 install geodata
    1. Create folder in home directory:  example/cache  
    2. Download gb.txt from geonames.org and place in example/cache.  (This just has Great Britain data)  
    3. Run example.py  
    """

    def __init__(self):
        # Set up standard logging.  
        logging.getLogger(__name__)
        fmt = "%(levelname)s %(name)s.%(funcName)s %(lineno)d: %(message)s"
        logging.basicConfig(level=logging.INFO, stream=sys.stdout, format=fmt)  # Change this to logging.DEBUG for more detail

        # Initialize
        directory = os.path.join(str(Path.home()), "Documents", "geoname_data")
        self.geodata = Geodata.Geodata(directory_name=directory, progress_bar=None, enable_spell_checker=False,
                                       show_message=True, exit_on_error=True,
                                       languages_list_dct={'en'},
                                       feature_code_list_dct=features,
                                       supported_countries_dct={'fr', 'gb', 'ca'})

        # Open Geoname database - city names, lat/long, etc.  Create database if not found
        error = self.geodata.open(repair_database=True, query_limit=105)
        if error:
            print(f"Missing geoname Files in {directory}: download gb.txt or allcountries.txt from geonames.org")
            raise ValueError('Missing files from geonames.org')

    def lookup_place(self, location_name):
        # Create Location instance.  This will hold search parameters and result
        place: Loc.Loc = Loc.Loc()

        # Find best match
        match = self.geodata.find_best_match(location=location_name, place=place)

        if match:
            # Create full name for result
            name = f'{place.get_long_name(None)}'
            print(f'\n   Best match for {location_name}: {name}  Prefix=[{place.prefix}{place.prefix_commas}] Score= {place.score:.1f}')
            return place.score
        else:
            if place.result_type == Geodata.GeoUtil.Result.NOT_SUPPORTED:
                print(f'   NO match for {location_name}:\n Country {place.country_name} not in supported country list')
            else:
                print(f'   NO match for {location_name}:\n')
            return 100.0

    def calculate(self, args):
        # Initialize
        score = 0
        tk = args[0:5]
        
        # Weighting for each input term match - prefix, city, adm2, adm1, country
        self.geodata.geo_build.geodb.match.set_weighting(token_weight=tk, prefix_weight=args[5], feature_weight=args[6], 
                                                 result_weight=args[7])

        for idx, name in enumerate(locations):
            delta = abs(ex.lookup_place(locations[idx])-scores[idx])
            score += delta
            
        return score
    
# Try a few different locations
locations = [
    '12 baker st, edinburgh ,edinburgh,scotland',  # Street as prefix
    'eddinburg ,,scotland',  # misspelled
    'edinburgh ,,scotland',  # misspelled
    '12 baker st,edinburgh,ile de france,scotland,united kingdom',  # misspelled
    'edinbur,ile de france,wales, united kingdom',
    
    ]

scores = [
    28.0,
    16.0,
    -10.0,
    32.5,
    100.0,
    ]


# Geoname feature types to add to database.  Other feature types will be ignored.
features = {"ADM1", "ADM2", "ADM3", "ADM4", "ADMF", "CH", "CSTL", "CMTY", "EST ", "HSP", "FT",
            "HSTS", "ISL", "MSQE", "MSTY", "MT", "MUS", "PAL", "PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4",
            "PPLC", "PPLG", "PPLH", "PPLL", "PPLQ", "PPLX", "PRK", "PRN", "PRSH", "RUIN", "RLG", "STG", "SQR", "SYG", "VAL"}

if __name__ == "__main__":
    # Initialize
    ex = Optimize()
    
    """ 
    #                   pre, cit, cty, prov, co  pref        result
    res = ex.calculate([0.0, 1.0, 0.6, 0.7, 0.7, 2.0, 0.10,  0.19])
    print(f'==== Calc1 = {res:.1f}') 
    
    res = ex.calculate([0.0, 1.4, 0.6, 0.7, 0.7, 1.0, 0.60,  0.19])
    print(f'==== Calc2 = {res:.1f}') 
    """
    
    x0 = np.array([0.0, 1.0, 0.6, 0.7, 0.7, 2.0, 0.10,  0.19])
    res = minimize(ex.calculate, x0, method='nelder-mead')
    
    print(res.x)
