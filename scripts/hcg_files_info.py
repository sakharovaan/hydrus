lines = """
Angel Escalayer [AliceSoft] (039581)
[070518][PUZZLEBOX] 年上Lesson ～義母と叔母と女教師と～ (e09117)
[100625][Illusion] SchoolMate 2 (すくぅ～るメイト2)
[090925] [Twinkle] Tropical Kiss
"""

import re, glob, csv

def decide_name(line):
    if re.match(r'^[^\[].*\[.*\]\s*\(.*\)$', line): # Angel Escalayer [AliceSoft] (039581)
        match = re.match('^(?P<name>.*)\[(?P<copyright>.*)\].*$', line)

    elif re.match(r'^\[\d+\]\s*\[.*\]\s*.*\(.*$', line):
        # [070518][PUZZLEBOX] 年上Lesson ～義母と叔母と女教師と～ (e09117)
        # [100625][Illusion] SchoolMate 2 (すくぅ～るメイト2)
        match = re.match(r'^(?P<id>.*)\[(?P<copyright>.*)\]\s*(?P<name>.*)\(.*$', line)

    elif re.match(r'^\[\d+\]\s*\[.*\]\s*.*$', line):
        # [090925] [Twinkle] Tropical Kiss

        match = re.match(r'^(?P<id>.*)\[(?P<copyright>.*)\]\s*(?P<name>.*)$', line)
    else:
        match = None

    if match:
        return dict(
            name=match.group('name').strip(),
            copyright=match.group('copyright').strip()
        )

with open('sw_data_new.csv', 'w', encoding='utf8') as f:
    writer = csv.writer(f)

    for line in glob.iglob("G:\\import\\HCG Pack\\*"):
        name = line.split('\\')[3].strip()
        decided = decide_name(name) or {}
        writer.writerow([name, decided.get('name'), decided.get('copyright')])


