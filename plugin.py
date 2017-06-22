"""
Air quality monitoring for Domoticz - ONLY FOR FRANCE
Reads data published on the www.prevair.org website using the site API
Many thanks to user @Domo89 on the French easydomoticz forum who investigated this API with his php script
(see https://easydomoticz.com/forum/viewtopic.php?f=17&t=3366). some of the code below is derived from his script.

Author: Logread (aka 999LV on GitHub)
Version:    0.0.1: alpha
"""
"""
<plugin key="PrevAir" name="PrevAir France Air Quality Monitoring" author="logread" version="0.0.1" wikilink="http://www.domoticz.com/wiki/plugins/plugin.html" externallink="www.prevair.org">
    <params>
        <param field="Mode1" label="Prevair Station code" width="100px" required="false" default=""/>
        <param field="Mode2" label="Update period (hours)" width="25px" required="true" default=""/>
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug"/>
                <option label="False" value="Normal"  default="true" />
            </options>
        </param>
    </params>
</plugin>
"""
import Domoticz
import json
import math
import urllib.request as request
from datetime import datetime, timedelta

icons = {"prevairgreen": "prevairgreen icons.zip",
         "prevairorange": "prevairorange icons.zip",
         "prevairred": "prevairred icons.zip"}

class polluant:
    def __init__(self, name, code, unit, level, levelmax, green, red, index, used):
        self.name = name
        self.code = code
        self.unit = unit
        self.level = level
        self.levelmax = levelmax
        self.green = green  # max level for green status
        self.red = red  # min level for red status
        self.index = index
        self.used = used

class BasePlugin:

    def __init__(self):
        self.debug = False
        self.date = datetime.now()
        self.lastupdate = self.date
        self.updatefrequency = 1  # hours... we update the data once per hour (once a day is enough, but our sensors will then turn red...)
        self.stationcode = False
        self.stationINSEE = False
        self.stationname = False
        self.stationdistance = 0  # km from Domoticz system
        self.pollutants = []
        self.pollutants.append(polluant("Indice Global Jour", "IJ", "", 0, 0, 4, 8, 1, 1))
        self.pollutants.append(polluant("Indice Global Demain", "ID", "", 0, 0, 4, 8, 2, 1))
        self.pollutants.append(polluant("SO2", "01", "µg/m3", 0, 0, 159, 300, 3, 0))
        self.pollutants.append(polluant("NO2", "03", "µg/m3", 0, 0, 109, 200, 4, 0))
        self.pollutants.append(polluant("CO", "04", "mg/m3", 0, 0, 25, 50, 5, 0))
        self.pollutants.append(polluant("O3", "08", "µg/m3", 0, 0, 104, 180, 6, 0))
        self.pollutants.append(polluant("PM10", "24", "µg/m3", 0, 0, 39, 80, 7, 0))
        self.pollutants.append(polluant("PM25", "39", "µg/m3", 0, 0, 10, 25, 8, 0))
        return

    def onStart(self):
        Domoticz.Debug("onStart called")
        if Parameters["Mode6"] == 'Debug':
            self.debug = True
            Domoticz.Debugging(1)
            DumpConfigToLog()
        else:
            Domoticz.Debugging(0)

        # load custom icons
        for key, value in icons.items():
            if key not in Images:
                Domoticz.Image(value).Create()
                Domoticz.Debug("Added icon: " + key + " from file " + value)
        Domoticz.Debug("Number of icons loaded = " + str(len(Images)))
        for image in Images:
            Domoticz.Debug("Icon " + str(Images[image].ID) + " " + Images[image].Name)

        # check polling interval parameter
        try:
            temp = int(Parameters["Mode2"])
        except:
            Domoticz.Error("Invalid polling interval parameter")
        else:
            if temp < 1:
                temp = 1  # minimum polling interval
                Domoticz.Error("Specified polling interval too short: changed to 1 hour")
            elif temp > 24:
                temp = 24  # maximum polling interval is 1 day
                Domoticz.Error("Specified polling interval too long: changed to 24 hours")
            self.updatefrequency = temp
        Domoticz.Log("Using polling interval of {} hour(s)".format(str(self.updatefrequency)))

        # get the Prevair station
        if Parameters["Mode1"] == "":
            station = False
        else:
            station = Parameters["Mode1"]
        ListLL = Settings["Location"].split(";", 1)
        Latitude = float(ListLL[0])
        Longitude = float(ListLL[1])
        self.stationcode, self.stationINSEE, self.stationname, self.stationdistance = getStation(
            station, Latitude, Longitude)
        Domoticz.Log("using station {}/{} {} at {}km".format(
            self.stationcode, self.stationINSEE, self.stationname, self.stationdistance))

        # create (if needed) the device to display the selected station details
        if not (99 in Devices):
            Domoticz.Device(Name="PrevAir Station", Unit=99, TypeName="Text",
                            Used=1).Create()
        # update the device
        try:
            Devices[99].Update(nValue=0, sValue=self.stationname + " ({}/{}) at {}km".format(
                self.stationcode, self.stationINSEE, self.stationdistance))
        except:
            Domoticz.Error("Failed to update device unit 99")

    def onStop(self):
        Domoticz.Debug("onStop called")
        Domoticz.Debugging(0)

    def onHeartbeat(self):
        now = datetime.now()
        if now >= self.lastupdate:
            self.lastupdate = now + timedelta(hours=self.updatefrequency)
            # read the Prevair data
            if self.stationcode:
                strdate = now.strftime("%Y-%m-%d")
                for pollutant in self.pollutants:
                    if pollutant.code == "IJ":  # we are checking the overall air pollution index for today
                        pollutant.level = getIndex(self.stationINSEE, strdate)
                    elif pollutant.code == "ID":  # we are checking the overall air pollution index for tomorrow
                        tomorrow = now + timedelta(hours=24)
                        pollutant.level = getIndex(self.stationINSEE, tomorrow.strftime("%Y-%m-%d"))
                    else:  # we check each pollutant for data (or not) for today
                        pollutant.level, pollutant.levelmax = getPollutant(self.stationcode, strdate, pollutant.code)
            else:
                print("Error... no data")
            # display the data
            for pollutant in self.pollutants:
                Domoticz.Debug(
                    "Pollutant: {} = {} (max = {})".format(pollutant.name, pollutant.level, pollutant.levelmax))
                if pollutant.level:
                    # if device does not yet exist, then create it
                    if not (pollutant.index in Devices):
                        Domoticz.Device(Name=pollutant.name, Unit=pollutant.index, TypeName="Custom",
                                        Options={"Custom": "1;{}".format(pollutant.unit)}, Used=pollutant.used).Create()
                    # update the device
                    self.UpdateDevice(pollutant.index, pollutant.level, pollutant.green, pollutant.red)

    def UpdateDevice(self, Unit, Level, Green, Red):
        # Make sure that the Domoticz device still exists (they can be deleted) before updating it
        if Unit in Devices:
            airlevel = int(Level)
            if airlevel <= Green:
                icon = "prevairgreen"
            elif airlevel >= Red:
                icon = "prevairred"
            else:
                icon = "prevairorange"
            try:
                Devices[Unit].Update(nValue=0, sValue=str(Level), Image=Images[icon].ID)
            except:
                Domoticz.Error("Failed to update device unit " + str(Unit))
        return

global _plugin
_plugin = BasePlugin()

def onStart():
    global _plugin
    _plugin.onStart()

def onStop():
    global _plugin
    _plugin.onStop()

def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()

# Plugin specific functions ---------------------------------------------------

def getDistance(latitude1, longitude1, latitude2, longitude2):
    earth_radius = 6378137
    rlo1 = math.radians(longitude1)
    rla1 = math.radians(latitude1)
    rlo2 = math.radians(longitude2)
    rla2 = math.radians(latitude2)
    dlo = (rlo2 - rlo1) / 2
    dla = (rla2 - rla1) / 2
    a = (math.sin(dla) * math.sin(dla)) + math.cos(rla1) * math.cos(rla2) *(math.sin(dlo) *math.sin(dlo))
    d = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return round((earth_radius * d) / 1000)

def PrevAirAPI(url):
    try:
        response = request.urlopen(url)
        if response.status == 200:
            return json.loads(response.read().decode('utf-8'))
        else:
            Domoticz.Error("http error = {}".format(response.status))
            return ""
    except:
        Domoticz.Error("Error reaching '{}'".format(url))
        return ""

def getStation(stationID, latitude, longitude):
    stations = PrevAirAPI("http://www2.prevair.org/ineris-web-services.php?url=stations&date=")
    mindistance = 99999  # km
    stationcode = False
    stationINSEE = False
    stationname = "Station Location Error"
    if stationID:
        for station in stations:
            if station[0] == stationID:
                mindistance = 0
                stationcode = stationID
                stationINSEE = station[3]
                stationname = station[4] + " - " + station[1]
                break
    else:
        for station in stations:
            #print(station[0], station[1], station[5], station[6])
            if station[0] != "Code station":  # skip first line of labels
                distance = getDistance(latitude, longitude, float(station[5]), float(station[6]))
                if mindistance > distance:
                    mindistance = distance
                    stationcode = station[0]
                    stationINSEE = station[3]
                    stationname = station[4] + " - " + station[1]
    return stationcode, stationINSEE, stationname, mindistance

def getPollutant(stationID, date, code):
    stations = PrevAirAPI(
        "http://www2.prevair.org/ineris-web-services.php?url=mesureJourna&date={}&code_polluant={}".format(date, code))
    level = False
    levelmax = False
    for station in stations:
        if station[0] == stationID:
            level = round(float(station[6]) + .5)
            levelmax = round(float(station[5]) + .5)
            break
    return level, levelmax

def getIndex(stationINSEE, date):
    stations = PrevAirAPI("http://www2.prevair.org/ineris-web-services.php?url=atmo&date={}".format(date))
    for station in stations:
        if station[1] == stationINSEE:
            return int(station[7])
            break

# Generic helper functions
def DumpConfigToLog():
    for x in Parameters:
        if Parameters[x] != "":
            Domoticz.Debug( "'" + x + "':'" + str(Parameters[x]) + "'")
    Domoticz.Debug("Device count: " + str(len(Devices)))
    for x in Devices:
        Domoticz.Debug("Device:           " + str(x) + " - " + str(Devices[x]))
        Domoticz.Debug("Device ID:       '" + str(Devices[x].ID) + "'")
        Domoticz.Debug("Device Name:     '" + Devices[x].Name + "'")
        Domoticz.Debug("Device nValue:    " + str(Devices[x].nValue))
        Domoticz.Debug("Device sValue:   '" + Devices[x].sValue + "'")
        Domoticz.Debug("Device LastLevel: " + str(Devices[x].LastLevel))
    return
