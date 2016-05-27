__author__ = 'fernandolourenco'

import requests
import json

r = requests.get("http://kayaposoft.com/enrico/json/v1.0/?action=getPublicHolidaysForYear&year=2016&country=prt")
print json.dumps(r.json(), sort_keys=True,indent=4, separators=(',', ': '))

print r.json()[1]['date']
print r.json()[1]['localName']