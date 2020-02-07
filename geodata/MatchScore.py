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

from geodata import GeoUtil, Loc, Normalize, Geodata


class Score:
    VERY_GOOD = 30
    GOOD = 65
    POOR = 85
    VERY_POOR = 100


def _calculate_prefix_penalty(prefix):
    # If the location has a prefix, it is not as good a match
    prefix_len = len(prefix)
    if prefix_len > 0:
        # reduce penalty if prefix is a street (contains digits or 'street' or 'road')
        if is_street(prefix):
            penalty = 5 
        else:
            penalty = 5 + prefix_len
        return penalty
    else:
        return 0
    
def _prepare_input(target_place:Loc, result_place:Loc):
    # Create full, normalized  title (prefix,city,county,state,country)

    result_title = full_normalized_title(result_place)
    target_title = full_normalized_title(target_place)
    target_title, result_title = Normalize.remove_aliase(target_title, result_title)
    
    result_tokens = [item.strip(' ') for item in result_title.split(',')]
    target_tokens = [item.strip(' ') for item in target_title.split(',')]

    # Remove term in Result if input for that term was empty
    remove_if_input_empty(target_tokens, result_tokens)

    return result_title, result_tokens, target_title, target_tokens

def is_street(text)->bool:
    # See if text looks like a street name
    street_patterns = [r'\d', 'street', 'avenue', 'road']
    for pattern in street_patterns:
        if bool(re.search(pattern, text)):
            return True
    return False

def remove_if_input_empty(target_tokens, res_tokens):
    # Remove terms in Result if input for that term was empty
    for ix, term in enumerate(target_tokens):
        if len(term) == 0 and ix < len(res_tokens):
            res_tokens[ix] = ''


def full_normalized_title(place: Loc) -> str:
    # Create a full normalized five part title (includes prefix)
    # Clean up prefix - remove any words that are in city, admin1 or admin2 from Prefix
    place.prefix = Loc.Loc.matchscore_prefix(place.prefix, place.get_long_name(None))
    title = place.get_five_part_title()
    return Normalize.normalize_for_scoring(title, place.country_iso)


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
        self.result_weight = 0.0
        self.input_weight = 0.0

        # Weighting for each input term match -  adm2, adm1, country
        token_weight = [.12, .1, .1]
        self.set_weighting(token_weight=token_weight, prefix_weight=1.7, feature_weight=0.05, result_weight=0.3)

        # Weighting for each part of score
        self.wildcard_penalty = -10.0

    def _calculate_wildcard_score(self, original_entry) -> float:
        if '*' in original_entry:
            # if it was a wildcard search it's hard to rank - add adjustment
            return self.wildcard_penalty
        else:
            return 0.0

    def set_weighting(self, token_weight: [], prefix_weight: float, feature_weight: float, result_weight: float):
        """
        Set weighting of scoring components.  See match_score for details of weighting.  All weights are positive
        Args:
            token_weight:    List with Weights relative to City for County, State/Province, Country. City is 1.0   
            prefix_weight:   Weighting for prefix score
            feature_weight:  Weighting for Feature match score
            result_weight:   Weighting for % of DB result that didnt match the target

        Returns:

        """
        self.token_weight = [0.0, 1.0]  # Set prefix weight to 0.0 and city to 1.0
        # Weighting for each input term match -  city, adm2, adm1, country
        self.token_weight += list(token_weight)
        self.token_weight = [abs(item) for item in self.token_weight]

        self.prefix_weight = abs(prefix_weight)
        self.feature_weight = abs(feature_weight)
        self.result_weight = abs(result_weight)
        # Out weight + Feature weight must be less than 1.0.
        if self.result_weight + self.feature_weight > 1.0:
            self.logger.error('Out weight + Feature weight must be less than 1.0')
            self.result_weight = 1.0 - self.feature_weight
        self.input_weight = 1.0 - result_weight - feature_weight

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
            in_score - (0-100) - percent of characters in input that didnt match output   
            out_score - (0-100) - percent of characters in output that didnt match input   
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
        #result_place.prefix = ' '

        # Create full, normalized titles (prefix,city,county,state,country)
        result_title, result_tokens, target_title, target_tokens = _prepare_input(target_place, result_place)

        # Store original length of tokens in target.  This is used for percent unmatched calculation
        original_result_title = copy.copy(result_title)
        original_target_title = copy.copy(target_title)

        original_target_tkn_len = [len(tkn) for tkn in target_tokens]

        # Remove sequences that match in target and result
        result_title, target_title = GeoUtil.remove_matching_sequences(text1=result_title, text2=target_title, min_len=2)
        target_tokens = target_title.split(',')

        # Calculate score for  percent of input target text that matched result
        in_score = self._calculate_input_score(original_target_tkn_len, target_tokens, result_tokens)

        # Calculate score for percent of result that matched input target
        out_score = self._calculate_output_score(result_title, original_result_title, original_target_title)

        # Calculate score for wildcard search - wildcard searches are missing letters and need special handling
        wildcard_score = self._calculate_wildcard_score(target_place.original_entry)

        # Calculate Prefix score.  Prefix is not used in search and longer is generally worse 
        prefix_score = _calculate_prefix_penalty(target_place.prefix)

        # Calculate Feature score - this ensures "important" places get higher rank (large city, etc)
        feature_score = Geodata.Geodata._feature_priority(result_place.feature)

        # Weight and add up scores - Each item is 0-100 and then weighted, except wildcard penalty
        score: float = in_score * self.input_weight + out_score * self.result_weight + feature_score * self.feature_weight + \
                       prefix_score * self.prefix_weight + wildcard_score

        #self.logger.debug(f'SCORE {score:.1f} res=[{original_result_title}] pref=[{target_place.prefix}]\n'
        #                  f'inp=[{",".join(target_tokens)}]  outSc={out_score * self.result_weight:.1f}% '
        #                  f'inSc={in_score * self.input_weight:.1f}% feat={feature_score * self.feature_weight:.1f} {result_place.feature}  '
        #                  f'wild={wildcard_score} pref={prefix_score * self.prefix_weight:.1f}')

        #self.logger.debug(self.score_diags)
        target_place.prefix = save_prefix

        return score

    def _calculate_input_score(self, inp_len: [], inp_tokens: [], res_tokens: []) -> float:
        num_inp_tokens = 0.0
        in_score = 0
        
        # For each input token calculate percent of unmatched size vs original size
        unmatched_input_tokens = inp_tokens.copy()

        # Each token in place hierarchy gets a different weighting
        #      Prefix, city,county, state, country
        match_bonus = 0
        
        if len(inp_tokens) > len(res_tokens):
            self.logger.warning(f'Len mismatch. inp {inp_tokens} res {res_tokens}')
            
        # Calculate percent of USER INPUT text that did not match result, then apply weighting for each token
        for idx, tk in enumerate(inp_tokens):
            if inp_len[idx] > 0 and idx < len(res_tokens):
                unmatched_percent = int(100.0 * len(unmatched_input_tokens[idx].strip(' ')) / inp_len[idx])
                in_score += unmatched_percent * self.token_weight[idx]
                self.score_diags += f'  {idx}) [{tk}][{unmatched_input_tokens[idx]}] {unmatched_percent}% * {self.token_weight[idx]} '
                num_inp_tokens += 1.0 * self.token_weight[idx]

                # If exact match of term, give bonus
                if inp_tokens[idx] == res_tokens[idx]:
                    if idx == 0:
                        match_bonus -= 9
                    else:
                        match_bonus -= 3
            else:
                pass
                
        # Average over number of tokens (with fractional weight).  Gives 0-100% regardless of weighting and number of tokens
        if num_inp_tokens > 0:
            in_score = in_score / num_inp_tokens
        else:
            in_score = 0

        self.score_diags = ''

        return in_score + match_bonus

    def _calculate_output_score(self, unmatched_result: str, original_result: str, target: str) -> float:
        """
        Calculate score for output (DB result).
        :param unmatched_result: The text of the DB result that didnt match the user's input
        :param original_result: The original DB result
        :return: 0=strong match, 100=no match
        """

        # Remove spaces and commas from original and unmatched result
        original_result = re.sub(r'[ ,]', '', original_result)
        unmatched = re.sub(r'[ ,]', '', unmatched_result)
        targ = re.sub(r'[ ,]', '', target)

        orig_res_len = len(original_result)
        if orig_res_len > 0:
            # number of chars of DB RESULT text that matched target - scaled from 0 (20 or more matched) to 100 (0 matched)
            matched_bonus = (20.0 - min(float(orig_res_len - len(unmatched)), 20.0)) * 5.0
            
            # if first X chars of result are same as first X chars of target, give a bonus
            #self.logger.debug(f'first chars [{original_result[0:5]}] [{targ[0:5]}]')
            if original_result[0:5] == targ[0:5]:
                matched_bonus -= 10
                #self.logger.debug(f'front match.  bonus={matched_bonus}')
            else:
                matched_bonus += 5

            # Percent of unmatched
            unmatched_percent = 100.0 * len(unmatched) / orig_res_len
            #self.logger.debug(f'OUT [{original_result}] unm=[{unmatched}] matched chars={orig_res_len - len(unmatched)} unmatch %
            # ={unmatched_percent}')

            if unmatched_percent >  30:
                out_score = matched_bonus * 0.3 + unmatched_percent * 0.7
            else:
                out_score = unmatched_percent
        else:
            out_score = 0.0

        self.score_diags += f'\noutrem=[{unmatched}]'

        return out_score

    @staticmethod
    def _adjust_adm_score(score, feat):
        # Currently just pass thru score
        return score
