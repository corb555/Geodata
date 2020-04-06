def inc_key(text):
    return  text[0:-1] + chr(ord(text[-1]) + 1)

print(inc_key('apple'))
