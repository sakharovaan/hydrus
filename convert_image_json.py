'''
script for converting danbooru dump json metadata to xmp
'''

import json
import os
import glob

file_metadata = {}
files_list = []


cats = {
    "1" : "artist",
    "2" : "artist",
    "3" : "copyright",
    "4" : "character",
    "5" : "meta"
}

rating = {
    "s": "rating:safe",
    "q": "rating:questionable",
    "e": "rating:explicit"
}

for file in os.scandir('C:\\'):
    with open(file, encoding='utf-8') as f:
        print(file)
        for line in f.readlines():
            j = json.loads(line)

            file_metadata[j['id']] = []

            for tag in j['tags']:
                if tag['category'] in cats:
                    file_metadata[j['id']].append(cats[tag['category']] + ':' + tag['name'].replace("_", " "))
                else:
                    file_metadata[j['id']].append(tag['name'].replace("_", " "))

            file_metadata[j['id']].append(rating[j['rating']])

for file in glob.iglob("Y:\danbooru_dump\**\*", recursive=True):
    print(file)
    fileno = os.path.basename(os.path.splitext(file)[0])

    with open(file + '.txt', mode='w', encoding='utf-8') as f:
        if fileno in file_metadata:
            f.write('\n'.join(t for t in file_metadata[fileno]))
        else:
            print('FAIL ' + str(fileno))
