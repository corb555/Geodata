from geodata import GeoUtil, Normalize

places = [
    '12 baker st, Man!@#%^&(chester, , England',  # punctuation
    'department kathedrale of westphalia kommune ',  # normandie
    'archipel de saint augustin',
    'Le Mont Saint Michel',  # county of
    ]


noise_words = [
    # apply this list of regex substitutions for match scoring
    # (r'), '), '),'),
    (r'normandy american '                     , 'normandie american '),
    (r'nouveau brunswick'                      , ' '),
    (r'westphalia'                             , 'westfalen'),
    (r'departement'                            , 'department'),
    (r'royal borough of windsor and maidenhead', 'berkshire'),
    (r'regional municipality'                  , 'county'),
    (r'kathedrale'                             , 'cathedral'),
    (r'citta metropolitana di '                , ' '),
    (r'kommune'                                , ''),
    (r"politischer bezirk "                    , ' '),
    (r'regional'                               , ' '),
    (r'region'                                 , ' '),
    (r'abbey'                                  , 'abbey'),
    (r'priory'                                 , 'abbey'),
    (r'greater'                                , ' '),
    (r' de '                                   , ' '),
    (r' di '                                   , ' '),
    (r' du '                                   , ' '),
    (r' of '                                   , ' '),

    (r"l'"                                     , ''),

    (r'erry'                                   , 'ury'),
    (r'ery'                                    , 'ury'),
    (r'borg'                                   , 'burg'),
    (r'bourg'                                  , 'burg'),
    (r'urgh'                                   , 'urg'),
    (r'mound'                                  , 'mund'),
    (r'ourne'                                  , 'orn'),
    (r'ney'                                    , 'ny'),
    ]

phrase_cleanup = [
    # always apply this list of regex substitutions 
    (r'  +'                                             , ' '),  # Strip multiple space to single space
    (r'\bmt '                                           , 'mount '),

    (r'\br\.k\. |\br k '                                , 'roman catholic '),
    (r'\brooms katholieke\b'                            , 'roman catholic'),

    (r'sveti |saints |sainte |sint |saint |sankt |st\. ', 'st '),  # Normalize Saint to St
    (r' co\.'                                           , ' county'),  # Normalize County
    (r'united states of america'                        , 'usa'),  # Normalize to USA   begraafplaats
    (r'united states'                                   , 'usa'),  # Normalize to USA

    (r'cimetiere'                                       , 'cemetery'),  # 
    (r'begraafplaats'                                   , 'cemetery'),  # 

    (r'town of '                                        , ' '),  # - remove town of
    (r'city of '                                        , ' '),  # - remove city of

    (r'county of ([^,]+)'                               , r'\g<1> county'),  # Normalize 'Township of X' to 'X Township'
    (r'township of ([^,]+)'                             , r'\g<1> township'),  # Normalize 'Township of X' to 'X Township'
    (r'cathedral of ([^,]+)'                            , r'\g<1> cathedral'),  # Normalize 'Township of X' to 'X Township'
    (r'palace of ([^,]+)'                               , r'\g<1> palace'),  # Normalize 'Township of X' to 'X Township'
    (r'castle of ([^,]+)'                               , r'\g<1> castle'),  # Normalize 'Township of X' to 'X Township'

    (r"'(\w{2,})'"                                      , r"\g<1>"),  # remove single quotes around word, but leave apostrophes
    ]


no_punc_remove_commas = [
    # Regex to remove most punctuation including commas
    (r"[^a-z0-9 $*']+", " ")
    ]

no_punc_keep_commas = [
    # Regex to remove most punctuation but keep commas
    (r"[^a-z0-9 $*,']+" , " ")
    ]

"""
    r"[^a-z0-9 $*,']+" , " "

"""

# Regex to remove most punctuation including commas


# noise_rgx  - Combine phrase dictionary with Noise words dictionary and compile regex (this is used for match scoring)
# keys = sorted(dct.keys(), key=len, reverse=True)

phrase_rgx_keep_commas = GeoUtil.MultiRegex(no_punc_keep_commas + phrase_cleanup)
phrase_rgx_remove_commas = GeoUtil.MultiRegex(no_punc_remove_commas + phrase_cleanup)


#noise_rgx = GeoUtil.MultiRegex(phrase_cleanup + noise_words)
norm = Normalize.Normalize()

for txt in places:
    print(f'==== {txt} ====')
    print(f'  RESULT {phrase_rgx_remove_commas.sub(txt, lower=True, set_ascii=True)}')
    print(f' RESULT2 {norm.normalize(txt, False)}')
    
