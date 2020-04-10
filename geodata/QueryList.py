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

""" Build SQL where clause and arg list """
import re


class QueryItem:
    def __init__(self):
        self.where = ''
        self.args = tuple()
        self.table = 'main.geodata'

    def clear(self):
        self.where = ''
        self.args = tuple()

    def add_clauses(self, where_clauses: [str], terms: [], table=''):
        """
        Create a Where clause (and args list) by appending each item in clause with AND as separator
        Use equal, unless there is an '*', then use LIKE type clause
        Args:
            where_clauses: list of column names
            terms: list of values
            table to use
        Returns: None
        """
        if table != '':
            self.table = table

        for idx, where_clause in enumerate(where_clauses):
            # Walk thru the where clauses specified and add each to our query and list of args
            term = terms[idx]
            # If where clause is for feature column and term is ADM0 or ADM1, then we need to look into admin table
            if where_clause == 'feature' and table == '':
                if 'ADM0' in term or 'ADM1' in term:
                    self.table = 'main.admin'

            if len(term) > 0:
                if len(self.where) > 0:
                    # There is already text in Where, so add AND
                    self.where += ' AND '

                if term[-1] == '*':
                    # TODO handle case with multiple wildcards with one at end
                    # Wildcard search at end of text - Use >= and < (usually gives better performanc than LIKE)
                    term = self.create_wildcard(term, remove=True)
                    self.where += f' ({where_clause} >= ? and {where_clause} < ?) '
                    self.args += (term, inc_key(term),)
                elif '*' in term:
                    # Wildcard search in middle or start of search - Use LIKE
                    term = self.create_wildcard(term, remove=False)
                    self.where += f' ({where_clause} like ?) '
                    self.args += (term,)
                else:
                    self.where += f' {where_clause} = ?'
                    self.args += (term,)

    @staticmethod
    def create_wildcard(pattern: str, remove: bool):
        """
        Convert lookup pattern into a SQL lookup (convert * to %)
        Args:
            pattern: 
            remove: If True, remove  wildcards

        Returns:

        """
        
        # Create SQL wildcard pattern (convert * to %).  Add % on end
        if remove:
            return re.sub(r"\*", "", pattern)
        else:
            return re.sub(r"\*", "%", pattern)


def inc_key(text):
    """ increment the last letter of text by one.  Used to replace key in SQL LIKE case with less than """
    return text[0:-1] + chr(ord(text[-1]) + 1)
