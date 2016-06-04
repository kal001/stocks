#monitor stocks and alert for buy/sell
# coding=UTF-8
__author__ = 'fernandolourenco'
import version

from googlefinance import getQuotes
from ystockquote import get_historical_prices
import operator

import sqlite3

import datetime
import dateutil.parser
import pytz

import ggetquote

import telepot

from ConfigParser import SafeConfigParser
import codecs
import sys
import os

#Constants
##########################################################################
CASH = 10000
TAXONDIVIDENDS = 0.26
COMISSION = 6.95* 1.04

VERBOSE = False

SETTINGSFILE = 'stocks.ini'
##########################################################################

#Globals
##########################################################################
global DATABASE
global newdayalert
##########################################################################

def main():
    global newdayalert

    # Read config file
    parser = SafeConfigParser()

    # Open the file with the correct encoding
    with codecs.open(SETTINGSFILE, 'r', encoding='utf-8') as f:
        parser.readfp(f)

    DATABASE = parser.get('Database', 'File')

    try:
        # Create access to bot
        bot = telepot.Bot(parser.get('Telegram', 'token'))
        uid = parser.get('Telegram', 'uid')
        # bot.sendMessage(uid, text=u"Start %s\n%s\n%s" % (os.path.basename(sys.argv[0]), version.__version__, datetime.datetime.now()))
    except:
        print u'Cannot access Telegram. Please do /start'
        sys.exit(1)

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    c = conn.cursor()

    for stock in c.execute("select id, stockid, lowcount, minreturn, lasttradedatetime, qty, buyprice from strategies where active='True';"):
        c1 = conn.cursor()
        c1.execute("select symbolgoogle,symbolyahoo,exchangeid,name from stocks where id=:id;", {"id":stock['stockid']})
        row = c1.fetchone()

        #Check if market open
        if not(ggetquote.checkifmarketopen(row["exchangeid"], row['symbolgoogle'], row['name'],conn)):
            continue

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

        #Get current quote
        quote = getQuotes(symbol)[0]
        datetradenow = dateutil.parser.parse(quote["LastTradeDateTimeLong"])  #get current last trade time on market
        nowquotevalue = float(quote['LastTradePrice']) #get last quote

        newdayalert = False

        if (lasttradedatetime is None) or datetradenow.date()<>lasttradedatetime.date():
            #New Day!
            bot.sendMessage(uid, text=u"New Day for stock %s" % row['name'])
            if VERBOSE:
                print "New Day for stock %s" % row['name']
            newdayalert = True

            #get last days of quotes
            quotes = get_historical_prices(row["symbolyahoo"], (datetradenow-datetime.timedelta(days=lowcount)).strftime("%Y-%m-%d"), (datetradenow-datetime.timedelta(days=1)).strftime("%Y-%m-%d"))
            sortedquotes = sorted(quotes.items(), key=operator.itemgetter(0))

            #check if number of days descending reached
            quoteant = 0.0
            countlow = 0
            for day in sortedquotes:
                #calculate day return
                if quoteant <> 0:
                    dayreturn = (float(day[1]["Close"])-quoteant)/quoteant
                else:
                    dayreturn = 0

                #increase number of consecutive days lowering
                if dayreturn<0.0:
                    countlow = countlow+1
                else:
                    countlow = 0

                quoteant = float(day[1]["Close"])

            #Number of days descending reached, and opend low
            if countlow>=lowcount and nowquotevalue<quoteant:
                qty = int((CASH-COMISSION)/nowquotevalue)
                bot.sendMessage(uid, text=u"Time to BUY %s (%s) Qty = %8.2f Price = %8.3f" % (row['name'], symbol, qty, nowquotevalue))
                if VERBOSE:
                    print "Time to BUY %s (%s) Qty = %8.2f Price = %8.3f" % (row['name'], symbol, qty, nowquotevalue)

            c2 = conn.cursor()
            c2.execute("UPDATE strategies SET lasttradedatetime = ? WHERE id = ?;",  (datetradenow, stock['id'])) #update last quote timestamp

        if qty>0 and nowquotevalue>=(1+minreturn)*buyprice and newdayalert:
            newdayalert = False
            bot.sendMessage(uid, text=u"Time to SELL %s (%s) Qty = %8.2f Price = %8.3f" % (row['name'], symbol, qty, nowquotevalue))
            if VERBOSE:
                print "Time to SELL %s (%s) Qty = %8.2f Price = %8.3f" % (row['name'], symbol, qty, nowquotevalue)

    conn.commit()

def buystock(symbol, qty, price, date, conn):

    if qty<=0:
        return

    if date is none:
        now = datetime.datetime.utcnow().replace(tzinfo = pytz.utc) # get current date and time in UTC with  timezone info
    else:
        now = date

    c = conn.cursor()

    #update movements
    c.execute("""
      insert into movements(stockid,date,qty,value,action)
      select stocks.id, ?, ?, ?, 'buy'
      from stocks
      where stocks.symbolgoogle=?;
      """, (now, qty, price, symbol))

    #update portfolio
    c.execute("""
        select portfolio.id from portfolio,stocks
        where stocks.symbolgoogle=:symbol and portfolio.stockid=stocks.id
        """, {"symbol":symbol})
    row = c.fetchone()

    try:
        portfolioid = row['id']
    except:
        portfolioid = None

    #stock is not yet in portfolio
    if portfolioid is None:
        #get stock id
        c1 = conn.cursor()
        c1.execute("select id from stocks where symbolgoogle=:id", {"id":symbol})
        row = c1.fetchone()
        stockid = row['id']

        #create new record in portfolio
        c.execute("""
        insert into portfolio(stockid,qty,cost)
        values(?,?,?)
        """, (stockid, qty, price))
    else:
        #stock is already in portfolio
        c.execute("""
        update portfolio
        set qty=qty+?, cost=(cost*qty+?*?)/(qty+?)
        where id=?
        """, (qty, qty,price, qty, portfolioid))

    conn.commit()

    return

def sellstock(symbol, qty, price, date, conn):
    success = False
    if qty<=0:
        return success

    if date is none:
        now = datetime.datetime.utcnow().replace(tzinfo = pytz.utc) # get current date and time in UTC with  timezone info
    else:
        now = date

    c = conn.cursor()

    #update portfolio
    c.execute("""
        select portfolio.id, portfolio.qty from portfolio,stocks
        where stocks.symbolgoogle=:symbol and portfolio.stockid=stocks.id
        """, {"symbol":symbol})
    row = c.fetchone()

    try:
        if float(row['qty'])<qty:
            return success

        portfolioid = int(row['id'])

        c.execute("""
        update portfolio
        set qty=qty-?
        where id=?
        """, (qty, portfolioid))

        #check if quantity on hand is 0, and if so, delete row from portfolio
        c.execute("""
        select qty from portfolio
        where id=:id
        """, {"id":portfolioid})
        row = c.fetchone()

        if float(row['qty']) <= 0:
            c.execute("delete from portfolio where id=?;", (portfolioid, ) )

        #update movements
        c.execute("""
            insert into movements(stockid,date,qty,value,action)
            select stocks.id, ?, ?, ?, 'sell'
            from stocks
            where stocks.symbolgoogle=?;
            """, (now, qty, price, symbol))

        success = True

    except Exception,e:
        #print str(e)
        if VERBOSE:
            print "Stock not in portfolio. Cannot sell"

    conn.commit()

    return success

if __name__ == "__main__":
    main()