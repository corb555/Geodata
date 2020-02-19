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

""" Build database queries for various lookups """
import re

from geodata import Loc
from geodata.GeoUtil import Query, Result, get_soundex


class Typ:
    CITY = 0
    ADMIN2 = 1
    ADMIN1 = 2
    COUNTRY = 3
    ADMIN1_ID = 4
    ADMIN2_ID = 5
    ADMIN1_ALT_NAME = 6
    GEOID = 7


class QueryList:
    @staticmethod
    def build_query_list(typ: int, query_list, place: Loc):
        """
        
        Args:
            typ: 
            query_list: 
            place: 

        Returns:

        """
        if typ == Typ.CITY:
            QueryList.query_list_city(query_list, place)
        elif typ == Typ.ADMIN2:
            QueryList.query_list_admin2(query_list, place)
        elif typ == Typ.ADMIN1:
            QueryList.query_list_admin1(query_list, place)
        elif typ == Typ.COUNTRY:
            QueryList.query_list_country(query_list, place)
        elif typ == Typ.ADMIN1_ID:
            QueryList.query_list_admin1_id(query_list, place)
        elif typ == Typ.ADMIN2_ID:
            QueryList.query_list_admin2_id(query_list, place)
        elif typ == Typ.ADMIN1_ALT_NAME:
            QueryList.query_list_admin1_alt_name(query_list, place)
        elif typ == Typ.GEOID:
            QueryList.query_list_geoid(query_list, place)

    @staticmethod
    def query_list_city(query_list, place: Loc):
        """
        Search for  city - try the most exact match, then less exact matches
        """
        lookup_target = place.city1
        sdx = get_soundex(lookup_target)
        pattern = QueryList.create_wildcard(lookup_target)
        if len(place.country_iso) == 0:
            # NO COUNTRY - try lookup by name.
            if lookup_target in pattern:
                query_list.append(Query(where="name = ?",
                                        args=(lookup_target,),
                                        result=Result.PARTIAL_MATCH))
            # lookup by wildcard name
            if '*' in lookup_target:
                query_list.clear()
                query_list.append(Query(where="name LIKE ?",
                                        args=(pattern,),
                                        result=Result.WILDCARD_MATCH))
            else:
                query_list.append(Query(where="name LIKE ?",
                                        args=(pattern,),
                                        result=Result.WORD_MATCH))

            # lookup by soundex
            query_list.append(Query(where="sdx = ?",
                                    args=(sdx,),
                                    result=Result.SOUNDEX_MATCH))
            return

        if len(place.admin1_name) > 0:
            # lookup by name, ADMIN1, country
            if lookup_target in pattern:
                query_list.append(Query(
                    where="name = ? AND country = ? AND admin1_id = ?",
                    args=(lookup_target, place.country_iso, place.admin1_id),
                    result=Result.STRONG_MATCH))

            # add lookup by wildcard name, ADMIN1, country
            if '*' in lookup_target:
                query_list.clear()

                query_list.append(Query(
                    where="name LIKE ? AND country = ? AND admin1_id = ?",
                    args=(pattern, place.country_iso, place.admin1_id),
                    result=Result.WILDCARD_MATCH))
            else:
                query_list.append(Query(
                    where="name LIKE ? AND country = ? AND admin1_id = ?",
                    args=(pattern, place.country_iso, place.admin1_id),
                    result=Result.WORD_MATCH))
        else:
            # add lookup by wildcard  name, country
            if '*' in lookup_target:
                query_list.clear()

                query_list.append(Query(where="name LIKE ? AND country = ?",
                                        args=(pattern, place.country_iso),
                                        result=Result.WILDCARD_MATCH))
            else:
                query_list.append(Query(where="name LIKE ? AND country = ?",
                                        args=(pattern, place.country_iso),
                                        result=Result.WORD_MATCH))

        # add lookup by Soundex , country
        query_list.append(Query(where="sdx = ? AND country = ?",
                                args=(sdx, place.country_iso),
                                result=Result.SOUNDEX_MATCH))

    @staticmethod
    def query_list_admin2(query_list, place: Loc):
        # Try Admin queries and find best match
        # sdx = get_soundex(lookup_target)
        lookup_target = place.admin2_name
        pattern = QueryList.create_wildcard(lookup_target)

        if len(place.country_iso) == 0:
            query_list.append(Query(where="name = ?  ",
                                    args=lookup_target,
                                    result=Result.PARTIAL_MATCH))
        else:
            query_list.append(Query(where="name = ? AND country = ? ",
                                    args=(lookup_target, place.country_iso),
                                    result=Result.PARTIAL_MATCH))

        query_list.append(Query(where="name LIKE ? AND country = ? ",
                                args=(lookup_target, place.country_iso),
                                result=Result.PARTIAL_MATCH))

        if '*' in lookup_target:
            query_list.clear()
            query_list.append(Query(where="name LIKE ? AND country = ? ",
                                    args=(pattern, place.country_iso),
                                    result=Result.WILDCARD_MATCH))
        else:
            query_list.append(Query(
                where="name LIKE ? AND country = ? AND admin1_id = ?",
                args=(pattern, place.country_iso, place.admin1_id),
                result=Result.WORD_MATCH))

    @staticmethod
    def query_list_admin1(query_list, place: Loc):
        """Search for Admin1 entry"""
        lookup_target = place.admin1_name
        sdx = get_soundex(lookup_target)
        pattern = QueryList.create_wildcard(lookup_target)
        #query_list.append(Query(where="name = ? AND country = ? AND f_code = ? ",
        #                        args=(lookup_target, place.country_iso, 'ADM1'),
        #                        result=Result.STRONG_MATCH))
        if '*' in lookup_target:
            query_list.clear()

            query_list.append(Query(where="name LIKE ? AND country = ?  AND f_code = ?",
                                    args=(pattern, place.country_iso, 'ADM1'),
                                    result=Result.WILDCARD_MATCH))
        else:
            query_list.append(Query(where="name LIKE ? AND country = ?  AND f_code = ?",
                                    args=(pattern, place.country_iso, 'ADM1'),
                                    result=Result.WORD_MATCH))

        query_list.append(Query(where="sdx = ? AND country = ? AND f_code=?",
                                args=(sdx, place.country_iso, 'ADM1'),
                                result=Result.SOUNDEX_MATCH))

    @staticmethod
    def query_list_country(query_list, place: Loc):
        """Search for Admin1 entry"""
        lookup_target = place.country_name
        sdx = get_soundex(lookup_target)
        # pattern = QueryList.create_wildcard(lookup_target)

        query_list.append(where="country = ? AND f_code = ? ",
                          args=(place.country_iso, 'ADM0'),
                          result=Result.STRONG_MATCH)

        query_list.append(where="sdx = ?  AND f_code=?",
                          args=(sdx, 'ADM0'),
                          result=Result.SOUNDEX_MATCH)

    @staticmethod
    def query_list_admin1_id(query_list, place: Loc):
        """Search for Admin1 entry"""
        # sdx = get_soundex(lookup_target)
        lookup_target = place.admin1_id
        pattern = QueryList.create_wildcard(lookup_target)

        if place.country_iso == '':
            query_list.append(Query(where="name = ?  AND f_code = ? ",
                                    args=(lookup_target, 'ADM1'),
                                    result=Result.STRONG_MATCH))

            query_list.append(Query(where="name LIKE ? AND f_code = ?",
                                    args=(pattern, 'ADM1'),
                                    result=Result.WILDCARD_MATCH))
        else:
            query_list.append(Query(where="name = ? AND country = ? AND f_code = ? ",
                                    args=(lookup_target, place.country_iso, 'ADM1'),
                                    result=Result.STRONG_MATCH))
            query_list.append(Query(where="name LIKE ? AND country = ?  AND f_code = ?",
                                    args=(pattern, place.country_iso, 'ADM1'),
                                    result=Result.WILDCARD_MATCH))

        query_list.append(Query(where="name = ?  AND f_code = ?",
                                args=(lookup_target, 'ADM1'),
                                result=Result.SOUNDEX_MATCH))

    @staticmethod
    def query_list_admin2_id(query_list, place: Loc):
        """Search for Admin2 entry"""
        # sdx = get_soundex(lookup_target)
        lookup_target = place.admin2_id
        pattern = QueryList.create_wildcard(lookup_target)

        if len(place.admin1_id) > 0:
            query_list.append(Query(where="name = ? AND country = ? AND admin1_id=? AND f_code=?",
                                    args=(lookup_target, place.country_iso, place.admin1_id, 'ADM2'),
                                    result=Result.STRONG_MATCH))
            query_list.append(Query(where="name LIKE ? AND country = ? and admin1_id = ? AND f_code=?",
                                    args=(lookup_target, place.country_iso, place.admin1_id, 'ADM2'),
                                    result=Result.WILDCARD_MATCH))
            query_list.append(Query(where="name LIKE ? AND country = ? and admin1_id = ? AND f_code=?",
                                    args=(pattern, place.country_iso, place.admin1_id, 'ADM2'),
                                    result=Result.WILDCARD_MATCH))
        else:
            query_list.append(Query(where="name = ? AND country = ? AND f_code=?",
                                    args=(lookup_target, place.country_iso, 'ADM2'),
                                    result=Result.STRONG_MATCH))
            query_list.append(Query(where="name LIKE ? AND country = ? AND f_code=?",
                                    args=(lookup_target, place.country_iso, 'ADM2'),
                                    result=Result.WILDCARD_MATCH))
            query_list.append(Query(where="name LIKE ? AND country = ? AND f_code=?",
                                    args=(pattern, place.country_iso, 'ADM2'),
                                    result=Result.WILDCARD_MATCH))

    @staticmethod
    def query_list_admin1_alt_name(query_list, place: Loc):
        """Search for Admin1 entry"""
        lookup_target = place.admin1_id
        query_list.append(where="admin1_id = ? AND country = ?  AND f_code = ? ",
                          args=(lookup_target, place.country_iso, 'ADM1'),
                          result=Result.STRONG_MATCH)

    @staticmethod
    def query_list_geoid(query_list, place: Loc) -> None:
        """Search for GEOID"""
        lookup_target = place.geoid
        query_list.append(where="geoid = ? ",
                          args=(lookup_target,),
                          result=Result.STRONG_MATCH)

    @staticmethod
    def query_list_admin1_name_direct(query_list, lookup_target, iso):
        """Search for Admin1 entry"""
        query_list.append(where="admin1_id = ? AND country = ?  AND f_code = ? ",
                          args=(lookup_target, iso, 'ADM1'),
                          result=Result.STRONG_MATCH)

    @staticmethod
    def query_list_admin2_name_direct(query_list, lookup_target, iso, admin1_id):
        """Search for Admin2 entry"""
        query_list.append(where="admin2_id = ? AND country = ? AND admin1_id = ?",
                          args=(lookup_target, iso, admin1_id),
                          result=Result.STRONG_MATCH)

        query_list.append(where="admin2_id = ? AND country = ?",
                          args=(lookup_target, iso),
                          result=Result.PARTIAL_MATCH)

    @staticmethod
    def create_wildcard(pattern):
        """

        :param pattern:
        :return:
        """
        # Create SQL wildcard pattern (convert * to %).  Add % on end
        if '*' in pattern:
            return re.sub(r"\*", "%", pattern)
        else:
            return f'%{pattern}%'
