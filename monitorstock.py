#monitor stocks and alert for buy/sell
__author__ = 'fernandolourenco'

from googlefinance import getQuotes
from ystockquote import get_historical_prices
import operator

import sqlite3

import datetime
import dateutil.parser
import pytz

VERBOSE = True

#Strategy
LOWCOUNT = 4
MINRETURN = 0.05

#Constants
TAXONDIVIDENDS = 0.26
COMISSION = 6.95* 1.04

conn = sqlite3.connect('stockdata.sqlite')
conn.row_factory = sqlite3.Row

c = conn.cursor()

for stock in c.execute("select stockid, lowcount, minreturn, lasttradedatetime, qty, buyprice from strategies where active='True';"):
    c1 = conn.cursor()
    c1.execute("select symbolgoogle,symbolyahoo from stocks where id=:id;", {"id":stock['stockid']})
    row = c1.fetchone()

    symbol = str(row["symbolgoogle"])
    if not(stock['qty'] is None):
        qty = float(stock['qty'])
    else:
        qty = 0
    if not(stock['buyprice'] is None):
        buyprice = float(stock['buyprice'])
    else:
        buyprice = 0
    minreturn = float(stock['minreturn'])
    lowcount = int(stock['lowcount'])
    if not(stock['lasttradedatetime'] is None):
        lasttradedatetime = dateutil.parser.parse(stock['lasttradedatetime'])
    else:
        lasttradedatetime = None

    quote = getQuotes(symbol)[0]
    datetradenow = dateutil.parser.parse(quote["LastTradeDateTime"])  #get last trade
    nowquote = float(quote['LastTradePrice'])

    if (lasttradedatetime is None) or datetradenow.day>lasttradedatetime.day:
        if VERBOSE:
            print "New Day"

        c2 = conn.cursor()
        c2.execute("UPDATE strategies SET lasttradedatetime = ? WHERE stockid = ?;",  (datetradenow, stock['stockid'])) #update last quote timestamp
        conn.commit()

    #ToDo check if stock market is opened
    #Todo acknowledge that stock was sold
    if qty>0 and nowquote>=(1+minreturn)*buyprice:
        if VERBOSE:
            print "Time to sell %s Qty = %8.2f Price = %8.3f" % (row["symbolgoogle"], qty, nowquote)
