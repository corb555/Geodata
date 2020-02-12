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

from geodata import Geodata, Loc


class Example:
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
        self.geodata = Geodata.Geodata(directory_name=directory, display_progress=None,
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
            nm = f'{place.get_long_name(None)}'
            print(f'   Best match for {location_name}:\n {nm}  Prefix=[{place.prefix}{place.prefix_commas}] Score= {place.score:.1f}\n')
        else:
            if place.result_type == Geodata.GeoUtil.Result.NOT_SUPPORTED:
                print(f'   NO match for {location_name}:\n Country {place.country_name} not in supported country list')
            else:
                print(f'   NO match for {location_name}:\n')


# Geoname feature types to add to database.  Other feature types will be ignored.
features = {"ADM1", "ADM2", "ADM3", "ADM4", "ADMF", "CH", "CSTL", "CMTY", "EST ", "HSP", "FT",
            "HSTS", "ISL", "MSQE", "MSTY", "MT", "MUS", "PAL", "PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4",
            "PPLC", "PPLG", "PPLH", "PPLL", "PPLQ", "PPLX", "PRK", "PRN", "PRSH", "RUIN", "RLG", "STG", "SQR", "SYG", "VAL"}

if __name__ == "__main__":
    # Initialize
    ex = Example()

    # Try a few different locations
    locations = [
        '12 baker st, Manchester, , England',  # Street as prefix
        'eddinburg castle,,scotland',  # misspelled
        'cant* cath*,england',  # wildcards
        'd*,--feature=CSTL,--iso=GB',  # search by feature type= castle
        'cardiff, wales',  # good location
        'cardiff kommune, wales',  # good location
        'carddif, wales',  # misspelled 
        'lindering, wales',  # poor match quality        'eddinburg castle,,scotland',  # misspelled

        'phoenix, england',  # doesnt exist
        'Saint-Denis-le-Ferment,,normandie,france',
        'cairo,egypt',
        'tiverton',
        'Thetford Abbey, , england',
        'tretwr, llnfhngl cwm du, breconshire, england,',
        'kathedrale winchester,england',
        'bemposta palace,paris,france',
        "'Buitenveldert' Amsterdam, Rooms Katholieke Begraafplaats,  Apeldoorn,  Gelderland, Netherland",
        'cathedral winchester,,england',
        'Chartres,Eure Et Loir,  ,  France',
        'Lathom,Lancashire,england',
        'St Filbert,Manchester,,england'
        ]

    locations2 = [
        'Saint-Denis-le-Ferment,,normandie,france',
        'St Filbert,Manchester,,england'
        ]

    for name in locations2:
        ex.lookup_place(name)
