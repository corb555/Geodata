import re

names = [
    'mt kisco',
    'kamtown',
    ]

for text in names:
    text = re.sub(r'^mt ', 'mount ', text)
    print (text)
