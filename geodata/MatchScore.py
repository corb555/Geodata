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
"""Calculate a heuristic score for how well a result place name matches a target place name."""
import copy
import logging
import re

# import python-Levenshtein 
from fuzzywuzzy import fuzz

from geodata import Loc, Normalize, Geodata, GeoUtil


class Score:
    VERY_GOOD = 30
    VERY_POOR = 100
    GOOD = VERY_GOOD + (VERY_POOR - VERY_GOOD) * 0.33
    POOR = VERY_GOOD + (VERY_POOR - VERY_GOOD) * 0.66
    

class MatchScore:
    """
    Calculate a heuristic score for how well a result place name matches a target place name. The score is based on percent
    of characters that didnt match plus other items - described in match_score()
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.score_diags = ''  # Diagnostic text for scoring
        self.token_weight = []
        self.prefix_weight = 0.0
        self.feature_weight = 0.0
        self.input_weight = 0.0

        # Weighting for each input term match -  adm2, adm1, country
        token_weights = [.1, .2, .2]
        self.set_weighting(token_weight=token_weights, prefix_weight=2.0, feature_weight=0.05)

        # Weighting for each part of score
        self.wildcard_penalty = -10.0

    def _calculate_wildcard_score(self, original_entry) -> float:
        if '*' in original_entry:
            # if it was a wildcard search it's hard to rank - just add adjustment
            return self.wildcard_penalty
        else:
            return 0.0

    def set_weighting(self, token_weight: [], prefix_weight: float, feature_weight: float):
        """
        Set weighting of scoring components.  See match_score for details of weighting.  All weights are positive
        Args:
            token_weight:    List with Weights relative to City for County, State/Province, Country. City is 1.0   
            prefix_weight:   Weighting for prefix score
            feature_weight:  Weighting for Feature match score

        Returns:

        """
        self.token_weight = [0.0, 1.0]  # Set prefix weight to 0.0 and city to 1.0
        
        if len(token_weight) != 3:
            raise Exception('Token weight must have 3 elements: County, State/Province, Country')
        
        # Append weighting for each input term match -   adm2, adm1, country
        self.token_weight += list(token_weight)
        self.token_weight = [abs(item) for item in self.token_weight]
        self.logger.debug(f'{token_weight}')

        self.prefix_weight = abs(prefix_weight)
        self.feature_weight = abs(feature_weight)
        #  Feature weight must be less than 1.0.
        if self.feature_weight > 1.0:
            self.logger.error('Feature weight must be less than 1.0')
        self.input_weight = 1.0 - feature_weight

    def match_score(self, target_place: Loc, result_place: Loc) -> float:
        """
            Calculate a heuristic score for how well a result place name matches a target place name.  The score is based on
            percent of characters that didnt match in input and output (plus other items described below).
            Mismatch score is 0-100% reflecting the percent mismatch between the user input and the result.  This is then
            adjusted by Feature type (large city gives best score) plus other items to give a final heuristic where
            -10 is perfect match of a large city and 100 is no match.

            A) Heuristic:
            1) Create 5 part title (prefix, city, county, state/province, country)
            2) Normalize text - Normalize.normalize_for_scoring()
            3) Remove sequences of 2 chars or more that match in target and result
            4) Calculate inscore - percent of characters in input that didn't match result.  Weight by term (city,,county,state,ctry)
                    Exact match of city term gets a bonus
            5) Calculate result score - percent of characters in db result that didn't match input

            B) Score components (All are weighted in final score):   
            in_score - (0-100) - score for input that didnt match output   
            feature_score - (0-100)  More important features get lower score.   
            City with 1M population is zero.  Valley is 100.  Geodata.feature_priority().  
            wildcard_penalty - score is raised by X if it includes a wildcard   
            prefix_penalty -  score is raised by length of Prefix   

            C) A standard text difference, such as Levenstein, was not used because those treat both strings as equal,   
            whereas this treats the User text as more important than DB result text and also weights each token.  A user's   
            text might commonly be something like: Paris, France and a DB result of Paris, Paris, Ile De France, France.   
            The Levenstein distance would be large, but with this heuristic, the middle terms can have lower weights, and   
            having all the input matched can be weighted higher than mismatches on the county and province.  This heuristic gives   
            a score of -9 for Paris, France.   

        # Args:
            target_place:  Loc  with users entry.
            result_place:  Loc with DB result.
        # Returns:
            score
        """
        self.score_diags = ''  # Diagnostic text for scoring
        save_prefix = target_place.prefix
        #self.logger.debug(f'res type={result_place.place_type}')

        # Create full, normalized titles (prefix,city,county,state,country)
        result_title, result_tokens, target_title, target_tokens = _prepare_input(target_place, result_place)
        #self.logger.debug(f'Targ [{target_tokens}] Res [{result_tokens}]')

        # Calculate score for  percent of input target text that matched result
        in_score = self._calculate_weighted_score(target_tokens, result_tokens)

        # Calculate score for wildcard search - wildcard searches are missing letters and need special handling
        wildcard_score = self._calculate_wildcard_score(target_place.original_entry)

        # Calculate Prefix score.  Prefix is not used in search and longer is generally worse 
        prefix_score = _calculate_prefix_penalty(target_place.prefix)

        # Calculate Feature score - this ensures "important" places get higher rank (large city, etc)
        feature_score = Geodata.Geodata._feature_priority(result_place.feature)

        # Weight and add up scores - Each item is 0-100 and then weighted, except wildcard penalty
        score: float = in_score * self.input_weight + feature_score * self.feature_weight + \
                       prefix_score * self.prefix_weight + wildcard_score

        #print(f'SCORE {score:.1f} res=[{result_title}] pref=[{target_place.prefix}]'
        #                  f'inp=[{",".join(target_tokens)}]   '
        #                  f'inSc={in_score * self.input_weight:.1f}% feat={feature_score * self.feature_weight:.1f} {result_place.feature}  '
        #                  f'wild={wildcard_score} pref={prefix_score * self.prefix_weight:.1f}')

        # self.logger.debug(self.score_diags)
        target_place.prefix = save_prefix

        return score

    def _calculate_weighted_score(self, target_tokens: [], result_tokens: []) -> float:
        # Get score with tokens as is
        sc = self._weighted_score(target_tokens, result_tokens)

        # Get score with city and admin2 reversed
        sc2 = 1000.0
        #if target_tokens[1] in result_tokens[2]:
        if 100 - fuzz.ratio(target_tokens[1], result_tokens[2]) < 30:
            city = target_tokens[1]
            target_tokens[1] = target_tokens[2]
            target_tokens[2] = city
    
            sc2 = self._weighted_score(target_tokens, result_tokens) * 1.2
        return min(sc, sc2)

    def _weighted_score(self, target_tokens: [], result_tokens: []) -> float:
        num_inp_tokens = 0.0
        score = 0.0

        token_weight = copy.copy(self.token_weight)
        
        # Set weighting to half if target token for that term is blank
        #for idx, item in enumerate(target_tokens):
        #    if len(item) == 0:
        #        token_weight[idx] *= 0.5 
            
        #self.logger.debug(f'[{target_tokens}]  [{result_tokens}]')

        # Calculate difference each target segment to result segment (city, county, state/province, country)
        # Each segment can have a different weighting.  e.g. county can have lower weighting
        for idx, segment in enumerate(target_tokens):
            if idx < len(result_tokens):
                # Calculate fuzzy Levenstein distance between words
                ratio = 100 - fuzz.ratio(target_tokens[idx], result_tokens[idx])
                # Calculate fuzzy Levenstein distance between Soundex of words
                sd = 100 - fuzz.ratio(GeoUtil.get_soundex(target_tokens[idx]), GeoUtil.get_soundex(result_tokens[idx]))
                
                value = ratio * 0.7 + sd * 0.3
                # partial_ratio = 100-fuzz.partial_ratio(target_tokens[idx], result_tokens[idx])
                score += value * token_weight[idx]
                num_inp_tokens += 1.0 * token_weight[idx]
                self.logger.debug(f'{idx}) {value} {value * self.token_weight[idx]}[{target_tokens[idx]}] [{result_tokens[idx]}]')

        # Average over number of tokens (with fractional weight).  Gives 0-100% regardless of weighting and number of tokens
        if num_inp_tokens > 0:
            score = score / num_inp_tokens
        else:
            score = 0
        return score - (num_inp_tokens * 6)

    @staticmethod
    def _adjust_adm_score(score, feat):
        # Currently just pass thru score
        return score


def _calculate_prefix_penalty(prefix):
    # If the location has a prefix, it is not as good a match
    prefix_len = len(prefix)
    if prefix_len > 0:
        # reduce penalty if prefix is a street (contains digits or 'street' or 'road')
        penalty = 5 + prefix_len
        if is_street(prefix):
            penalty *= 0.5
    else:
        penalty =  0
    #print(f'PREF=[{prefix}] {penalty}')
    return penalty


def _prepare_input(target_place: Loc, result_place: Loc):
    # Create full, normalized  title (prefix,city,county,state,country)

    result_title = full_normalized_title(result_place)
    target_title = full_normalized_title(target_place)
    target_title, result_title = Normalize.remove_aliase(target_title, result_title)

    result_tokens = [item.strip(' ') for item in result_title.split(',')]
    target_tokens = [item.strip(' ') for item in target_title.split(',')]

    return result_title, result_tokens, target_title, target_tokens


def is_street(text) -> bool:
    # See if text looks like a street name
    street_patterns = [r'\d', 'street', 'avenue', 'road', 'rue ']
    for pattern in street_patterns:
        if bool(re.search(pattern, text)):
            return True
    return False


def remove_if_input_empty(target_tokens, res_tokens):
    # Remove terms in Result if input for that term was empty
    for ix, term in enumerate(target_tokens):
        if len(term) == 0 and ix < len(res_tokens) - 1 and ix > 1:
            res_tokens[ix] = ''


def full_normalized_title(place: Loc) -> str:
    # Create a full normalized five part title (includes prefix)
    # Clean up prefix - remove any words that are in city, admin1 or admin2 from Prefix
    place.prefix = Loc.Loc.matchscore_prefix(place.prefix, place.get_long_name(None))
    title = place.get_five_part_title()
    title = Normalize.normalize_for_scoring(title, place.country_iso)
    return title
