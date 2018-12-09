from redeal import *

def compare_dictionaries(d1, d2):
    d1_keys = set(d1.keys())
    d2_keys = set(d2.keys())
    intersect_keys = d1_keys.intersection(d2_keys)
    if len(d1_keys) != len(intersect_keys):
        return False
    for key in intersect_keys:
        if d1[key] != d2[key]:
            return False
    return True

def verify_results(d1, d2):
    return compare_dictionaries(d1, d2)

def test_calc_tables():
    dealer = redeal.Deal.prepare(predeal={"N": "982 82 K94 Q7542", "S": "4 JT63 A753 AT63", "W": "AKQT6 KQ97 J2 J8", "E": "J753 A54 QT86 K9"})
    deal = dealer()
    ans = deal.dd_table()
    expected = {
        'north': { 'c': 8, 'd': 5, 'h': 3, 's': 3, 'n': 3},
        'south': { 'c': 8, 'd': 5, 'h': 3, 's': 3, 'n': 3},
        'east': { 'c': 5, 'd': 8, 'h': 10, 's': 10, 'n': 10},
        'west': { 'c': 5, 'd': 8, 'h': 10, 's': 10, 'n': 10} }
    assert compare_dictionaries(ans, expected)

    dealer = redeal.Deal.prepare(predeal={"N": "T43 A43 AJT984 7", "S": "AKQ85 J876 - KJ42", "W": "J76 KQ2 K73 AQ93", "E": "92 T95 Q652 T865"})
    deal = dealer()
    ans = deal.dd_table()
    expected = {
        'north': { 'c': 6, 'd': 7, 'h': 8, 's': 9, 'n': 7},
        'east': { 'c': 7, 'd': 6, 'h': 5, 's': 3, 'n': 5},
        'south': { 'c': 6, 'd': 7, 'h': 8, 's': 9, 'n': 8},
        'west': { 'c': 7, 'd': 6, 'h': 5, 's': 3, 'n': 5} }
    assert compare_dictionaries(ans, expected)
