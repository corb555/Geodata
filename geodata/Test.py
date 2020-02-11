def remove_item(pattern, text) -> str:
    # Find pattern in word in text and remove entire word
    segment_list = text.split(',')
    # Walk thru segments
    for seg_idx, segment in enumerate(segment_list):
        # Walk thru words
        word_list = segment.split(' ')
        for idx, word in enumerate(word_list):
            if pattern in word:
                # Remove entire word, not just pattern
                word_list[idx] = ''
        segment_list[seg_idx] = ' '.join(word_list)
    text = ','.join(segment_list)
    return text


print(f"{remove_item('shire', 'pembroke castle, hampshire, england, united kingdom')}")


