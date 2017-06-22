"""
Utility to list all air pollution surveillance stations registered on Prevair.org France network
"""
import json
import urllib.request as request

def PrevAirAPI(url):
    try:
        response = request.urlopen(url)
        if response.status == 200:
            return json.loads(response.read().decode('utf-8'))
        else:
            print("http error = {}".format(response.status))
            return ""
    except:
        print("Error reaching '{}'".format(url))
        return ""

stations = PrevAirAPI("http://www2.prevair.org/ineris-web-services.php?url=stations&date=")
for station in stations:
    print(station)
