import re


def is_street(text)->bool:
    street_patterns = [r'\d', 'street', 'avenue', 'road']
    for pattern in street_patterns:
        if bool(re.search(pattern, text)):
            return True
    return False

print(is_street('oak')) 
print(is_street('12 oak')) 
print(is_street('oak street')) 
print(is_street('12 oak road')) 

