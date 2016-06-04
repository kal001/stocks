#Tracks stocks to sqlite database
__author__ = 'fernandolourenco'
import version

from googlefinance import getQuotes
import ystockquote

import sqlite3

import datetime
import dateutil.parser
import pytz

import requests

import codecs
from ConfigParser import SafeConfigParser

import monitorstock

#Constants
##########################################################################
SETTINGSFILE = 'stocks.ini'
VERBOSE = False
##########################################################################

#Globals
##########################################################################
global DATABASE
##########################################################################

##########################################################################
def main():
    # Read config file
    parser = SafeConfigParser()

    # Open the file with the correct encoding
    with codecs.open(SETTINGSFILE, 'r', encoding='utf-8') as f:
        parser.readfp(f)

    global DATABASE
    DATABASE = parser.get('Database', 'File')

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    for row in c.execute("select * from stocks where tracked='True';"):

        stockid = row["id"]
        stockname = row["name"]

        if not(monitorstock.checkifmarketopen(row["exchangeid"], row["symbolgoogle"], stockname,conn)):
            continue

        if not(row["lastquotestamp"] is None):
            timestamp = dateutil.parser.parse(row["lastquotestamp"]) # get last quote timestamp and parse into time object
        else:
            timestamp = None
        interval = row["interval"]
        type= row["type"].upper()

        now = datetime.datetime.utcnow().replace(tzinfo = pytz.utc) # get current date and time in UTC with  timezone info
        if (timestamp is None) or (now> timestamp + datetime.timedelta(minutes=interval) ): #see if it is time to get a new quote
            if type == "CURRENCY":
                symbol = str(row["symbolyahoo"])
                quote = ystockquote.get_price(symbol) #get quote
            elif type == "STOCK":
                symbol = str(row["symbolgoogle"])
                quote = getQuotes(symbol)[0]["LastTradePrice"]  #get quote

            newtimestamp=datetime.datetime.utcnow().isoformat()+'Z' # all dates saved in UTC iso format
            c1 = conn.cursor()
            c1.execute("UPDATE stocks SET lastquotestamp = ? WHERE ID = ?;",  (newtimestamp, stockid)) #update last quote timestamp
            c1.execute("INSERT INTO quotes(stockid,timestamp,value) VALUES (?,?,?);", (stockid,newtimestamp,quote)) #create new quote
            conn.commit()

            if VERBOSE:
                print "Got new stock quote for %s(%s) of %s @%s" % (symbol,stockname,quote,newtimestamp)
##########################################################################



if __name__ == "__main__":
    main()