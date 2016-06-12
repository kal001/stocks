#Tracks stocks to sqlite database
__author__ = 'fernandolourenco'
import version

from googlefinance import getQuotes
import ystockquote

import sqlite3

import datetime
import dateutil.parser
import pytz

import os

import codecs
from ConfigParser import SafeConfigParser

import monitorstock

#Constants
##########################################################################
SETTINGSFILE = 'stocks.ini'
VERBOSE = True
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
    with codecs.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGSFILE), 'r', encoding='utf-8') as f:
        parser.readfp(f)

    global DATABASE
    DATABASE = parser.get('Database', 'File')

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    #get quotes for all stocks marked to track
    for row in c.execute("select * from stocks where tracked='True';"):

        stockid = row["id"]
        stockname = row["name"]

        if VERBOSE:
            print "\n"

        if not(monitorstock.checkifmarketopen(row["exchangeid"], row["symbolgoogle"], stockname,conn)):
            if VERBOSE:
                print "Stock market CLOSED for %s(%s)"  % (row["symbolgoogle"],stockname)

                c1 = conn.cursor()
                c1.execute("select MAX(timestamp), value from quotes where stockid=:id", {'id':row['id']})
                newquote = c1.fetchone()
                quote = newquote['value']
                newtimestamp = newquote['MAX(timestamp)']
                print "LAST quote available in database for %s(%s) of %s @%s" % (row["symbolgoogle"],stockname,quote,newtimestamp)
            continue

        if not(row["lastquotestamp"] is None):
            timestamp = dateutil.parser.parse(row["lastquotestamp"]) # get last quote timestamp and parse into time object
        else:
            timestamp = None
        interval = row["interval"]

        now = datetime.datetime.utcnow().replace(tzinfo = pytz.utc) # get current date and time in UTC with  timezone info
        if (timestamp is None) or (now> timestamp + datetime.timedelta(minutes=interval) ): #see if it is time to get a new quote
            newtimestamp, quote = monitorstock.savequote(int(stockid), timestamp, conn)

            if VERBOSE:
                print "Got NEW quote for %s(%s) of %s @%s" % (row["symbolgoogle"],stockname,quote,newtimestamp)
        else:
            if VERBOSE:
                c1 = conn.cursor()
                c1.execute("select MAX(timestamp), value from quotes where stockid=:id", {'id':row['id']})
                newquote = c1.fetchone()
                quote = newquote['value']
                newtimestamp = newquote['MAX(timestamp)']
                print "RECENT quote available in database for %s(%s) of %s @%s" % (row["symbolgoogle"],stockname,quote,newtimestamp)

##########################################################################


if __name__ == "__main__":
    main()