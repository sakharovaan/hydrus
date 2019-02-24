'''
script for converting danbooru dump json metadata to xmp
'''

import json
import os
import glob
from xml.sax.saxutils import escape

file_metadata = {}
files_list = []

XMP_TEMPLATE = """<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="XMP Core 4.4.0-Exiv2">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:xmp="http://ns.adobe.com/xap/1.0/"
    xmlns:digiKam="http://www.digikam.org/ns/1.0/"
    xmlns:MicrosoftPhoto="http://ns.microsoft.com/photo/1.0/"
    xmlns:lr="http://ns.adobe.com/lightroom/1.0/"
    xmlns:mediapro="http://ns.iview-multimedia.com/mediapro/1.0/"
    xmlns:acdsee="http://ns.acdsee.com/iptc/1.0/"
    xmlns:tiff="http://ns.adobe.com/tiff/1.0/"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmp:CreatorTool="digiKam-5.9.0"
   acdsee:categories="&lt;Categories&gt;&lt;Category Assigned=&quot;1&quot;&gt;366&lt;/Category&gt;&lt;Category Assigned=&quot;1&quot;&gt;123&lt;/Category&gt;&lt;/Categories&gt;"
   tiff:Software="digiKam-5.9.0">
   <digiKam:TagsList>
    <rdf:Seq>
{{ tags_list }}    </rdf:Seq>
   </digiKam:TagsList>
   <MicrosoftPhoto:LastKeywordXMP>
    <rdf:Bag>
{{ tags_list }}    </rdf:Bag>
   </MicrosoftPhoto:LastKeywordXMP>
   <lr:hierarchicalSubject>
    <rdf:Bag>
{{ tags_list }}    </rdf:Bag>
   </lr:hierarchicalSubject>
   <mediapro:CatalogSets>
    <rdf:Bag>
{{ tags_list }}    </rdf:Bag>
   </mediapro:CatalogSets>
   <dc:subject>
    <rdf:Bag>
{{ tags_list }}    </rdf:Bag>
   </dc:subject>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
<?xpacket end="w"?>"""

TAG_TEMPLATE = "     <rdf:li>%s</rdf:li>\n"

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

    with open(file + '.xmp', mode='w', encoding='utf-8') as f:
        if fileno in file_metadata:
            tags_filler = "".join(TAG_TEMPLATE % escape(t) for t in file_metadata[fileno])
            f.write(XMP_TEMPLATE.replace("{{ tags_list }}", tags_filler))
        else:
            print('FAIL ' + str(fileno))
