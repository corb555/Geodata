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


class MatchScore:
    """
    Calculate a heuristic score for how well a result place name matches a target place name. The score is based on percent
    of characters that didnt match plus other items - described in match_score()
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.token_weight = []
        self.prefix_weight = 0.0
        self.feature_weight = 0.0
        self.result_weight = 0.0
        self.input_weight = 0.0

        # Weighting for each input term match -  adm2, adm1, country
        token_weight = [.12, .1, .1]
        self.set_weighting(token_weight=token_weight, prefix_weight=.94, feature_weight=0.10, result_weight=0.3)

        # Weighting for each part of score
        self.wildcard_penalty = -10.0
        self.in_score = 99.0
        self.out_score = 99.0

    def set_weighting(self, token_weight: [], prefix_weight: float, feature_weight: float, result_weight: float):
        """
        Set weighting of score components
        Args:
            token_weight: List with Weights for match of County, State/Province, Country. City is always 1.0   
            prefix_weight:   Weighting for prefix
            feature_weight:  Weighting for Feature match
            result_weight:   Weighting for % of DB result that didnt match the target

        Returns:

        """
        self.token_weight = [0.0, 1.0]  # prefix weight is zero and city is 1.0
        # Weighting for each input term match -  city, adm2, adm1, country
        self.token_weight += list(token_weight)
        self.token_weight = [abs(ele) for ele in self.token_weight]

        self.prefix_weight = abs(prefix_weight)
        self.feature_weight = abs(feature_weight)
        self.result_weight = abs(result_weight)
        # Out weight + Feature weight must be less than 1.0.
        if self.result_weight + self.feature_weight > 1.0:
            self.logger.error('Out weight + Feature weight must be less than 1.0')
            self.result_weight = 1.0 - self.feature_weight
        self.input_weight = 1.0 - result_weight - feature_weight

    def remove_if_input_empty(self, target_tokens, res_tokens):
        # Remove terms in Result if input for that term was empty
        for ix, term in enumerate(target_tokens):
            if len(term) == 0 and ix < len(res_tokens):
                res_tokens[ix] = ''

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

            B) Score components (All are weighted except Prefix and Parse):   
            in_score - (0-100) - percent of characters in input that didnt match output   
            out_score - (0-100) - percent of characters in output that didnt match input   
            feature_score - (0-100)  More important features get lower result.   
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
        target_tkn_len = [0] * 20

        # Create full RESULT title (prefix,city,county,state,country)
        result_place.prefix = ' '
        result_words = result_place.get_five_part_title()
        result_words = Normalize.normalize_for_scoring(result_words, result_place.country_iso)
        result_place.original_entry = copy.copy(result_words)
        res_tokens = result_words.split(',')

        # Create full TARGET  title (prefix,city,county,state,country)
        # Clean up prefix - remove any words that are in city, admin1 or admin2 from Prefix
        target_words = target_place.get_five_part_title()
        target_words = Normalize.normalize_for_scoring(target_words, target_place.country_iso)
        target_tokens = target_words.split(',')

        # Remove terms in Result if input for that term was empty
        self.remove_if_input_empty(target_tokens, res_tokens)

        # update prefix
        target_tokens[0] = Loc.Loc.matchscore_prefix(target_tokens[0], result_words)

        target_words, result_words = Normalize.remove_aliase(target_words, result_words)

        # Store length of original tokens in target.  This is used for percent unmatched calculation
        for it, tk in enumerate(target_tokens):
            target_tokens[it] = target_tokens[it].strip(' ')
            target_tkn_len[it] = len(target_tokens[it])

        # Remove sequences that match in target and result
        result_words, target_words = GeoUtil.remove_matching_sequences(text1=result_words, text2=target_words, min_len=2)

        # Calculate score for input match
        self.in_score = self._calculate_input_score(target_tkn_len, target_tokens, target_words, res_tokens)

        # Calculate score for output match
        self.out_score = self._calculate_output_score(result_words, result_place.original_entry)

        if '*' in target_place.original_entry:
            # if it was a wildcard search it's hard to rank - add adjustment
            wildcard_penalty = self.wildcard_penalty
        else:
            wildcard_penalty = 0.0

        # Prefix penalty 
        prefix_penalty = self._calculate_prefix_penalty(target_tkn_len[0])

        # Feature score is to ensure "important" places get higher rank (large city, etc)
        feature_score = Geodata.Geodata._feature_priority(result_place.feature)

        # Add up scores - Each item is 0-100 and then weighted, except wildcard penalty
        score: float = self.in_score * self.input_weight + self.out_score * self.result_weight + feature_score * self.feature_weight + \
                       prefix_penalty * self.prefix_weight + wildcard_penalty

        # self.logger.info(f'Weights: city={self.token_weight[1]:.1f} cty={self.token_weight[2]:.1f} st={self.token_weight[3]:.1f}'
        #                 f' ctry={self.token_weight[4]:.1f} targ={self.input_weight:.1f} res={self.result_weight:.1f}'
        #                 f' pref={self.prefix_weight:.1f}')

        # self.logger.debug(f'SCORE {score:.1f} res=[{result_place.original_entry}] pref=[{target_place.prefix}]\n'
        #                  f'inp=[{",".join(target_tokens)}]  outSc={self.out_score * self.result_weight:.1f}% '
        #                  f'inSc={self.in_score * self.input_weight:.1f}% feat={feature_score * self.feature_weight:.1f} {result_place.feature}  '
        #                  f'wild={wildcard_penalty} pref={prefix_penalty * self.prefix_weight:.1f}')

        return score

    def _calculate_input_score(self, inp_len: [], inp_tokens: [], input_words, res_tokens: []) -> float:
        num_inp_tokens = 0.0
        in_score = 0

        # For each input token calculate percent of unmatched size vs original size
        unmatched_input_tokens = input_words.split(',')

        # Each token in place hierarchy gets a different weighting
        #      Prefix, city,county, state, country
        self.score_diags = ''
        unmatched_input_tokens[0] = inp_tokens[0]
        match_bonus = 0

        # Calculate percent of USER INPUT text that was unmatched, then apply weighting
        for idx, tk in enumerate(inp_tokens):
            if inp_len[idx] > 0 and idx < len(self.token_weight):
                unmatched_percent = int(100.0 * len(unmatched_input_tokens[idx].strip(' ')) / inp_len[idx])
                in_score += unmatched_percent * self.token_weight[idx]
                self.score_diags += f'  {idx}) [{tk}][{unmatched_input_tokens[idx]}] {unmatched_percent}% * {self.token_weight[idx]} '
                # self.logger.debug(f'{idx}) Rem=[{unmatched_input_tokens[idx].strip(" " )}] wgtd={unmatched_percent * self.weight[idx]}')
                num_inp_tokens += 1.0 * self.token_weight[idx]
                # self.logger.debug(f'{idx} [{inp_tokens2[idx]}:{inp_tokens[idx]}] rawscr={sc}% orig_len={inp_len[idx]} wgt={self.weight[idx]}')
                if idx == 1:
                    # If the full first or second token of the result is in input then improve score
                    # Bonus for a full match as against above partial matches
                    # if res_tokens[idx] in inp_tokens[idx]:
                    #    in_score -= self.first_token_match_bonus
                    # If exact match of term, give bonus
                    if inp_tokens[idx] == res_tokens[idx]:
                        if idx == 0:
                            match_bonus -= 9
                        else:
                            match_bonus -= 3

        # Average over number of tokens (with fractional weight).  Gives 0-100% regardless of weighting and number of tokens
        if num_inp_tokens > 0:
            in_score = in_score / num_inp_tokens
        else:
            in_score = 0

        return in_score + match_bonus + 10

    def _calculate_output_score(self, unmatched_result: str, original_result: str) -> float:
        """
        Calculate score for output (DB result).
        :param unmatched_result: The text of the DB result that didnt match the user's input
        :param original_result: The original DB result
        :return: 0=strong match, 100=no match
        """

        # Remove spaces and commas from original and unmatched result
        original_result = re.sub(r'[ ,]', '', original_result)
        unmatched = re.sub(r'[ ,]', '', unmatched_result)

        orig_res_len = len(original_result)
        if orig_res_len > 0:
            # number of chars of DB RESULT text that matched target - scaled from 0 (20 or more matched) to 100 (0 matched)
            out_score_1 = (20.0 - min((orig_res_len - len(unmatched)), 20.0)) * 5.0
            # self.logger.debug(f'matched {orig_res_len - len(unmatched)} [{unmatched}]')

            # Percent of unmatched
            out_score_2 = 100.0 * len(unmatched) / orig_res_len

            out_score = out_score_1 * 0.1 + out_score_2 * 0.9
        else:
            out_score = 0.0

        self.score_diags += f'\noutrem=[{unmatched}]'

        return out_score

    def _calculate_prefix_penalty(self, prefix_len):
        if prefix_len > 0:
            return 10
        else:
            return 0

    @staticmethod
    def _adjust_adm_score(score, feat):
        return score
