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

    print getstockreturn(9,conn)

    c = conn.cursor()
    for stock in c.execute("""
                select strategies.*, stocks.name, stocks.symbolgoogle, stocks.symbolyahoo, stocks.exchangeid, stocks.lastquotestamp
                from strategies, stocks
                where strategies.stockid=stocks.id and active='True';
                """):
        #Check if market open
        if not(checkifmarketopen(stock["exchangeid"], stock['symbolgoogle'], stock['name'],conn)):
            continue

        symbol = str(stock["symbolgoogle"])
        minreturn = float(stock['minreturn'])
        lowcount = int(stock['lowcount'])

        c1 = conn.cursor()
        c1.execute("""
                  select portfolio.*, stocks.lastquotestamp
                  from portfolio, stocks
                  where portfolio.stockid=:id and portfolio.stockid=stocks.id
                  """, {'id':stock['stockid']})
        stockinportfolio = c1.fetchone()

        try:
            qty = float(stockinportfolio['qty'])
            buyprice = float(stockinportfolio['cost'])
        except:
            qty = 0
            buyprice = 0

        try:
            lasttradedatetime = dateutil.parser.parse(stock['lastquotestamp'])
        except:
            lasttradedatetime = None

        #Get current quote
        quote = getQuotes(symbol)[0]
        datetradenow = dateutil.parser.parse(quote["LastTradeDateTimeLong"]) #get current last trade time on market
        nowquotevalue = float(quote['LastTradePrice']) #get last quote

        newdayalert = False

        if (lasttradedatetime is None) or datetradenow.date()<>lasttradedatetime.date():
            #New Day!
            bot.sendMessage(uid, text=u"New Day for stock %s" % stock['name'])
            if VERBOSE:
                print "New Day for stock %s" % stock['name']
            newdayalert = True

        if newdayalert:
            #Number of days descending reached, and opend low
            if checkiftimetobuy(stock['symbolyahoo'], lowcount, datetradenow, nowquotevalue):
                qty = int((CASH-COMISSION)/nowquotevalue)
                bot.sendMessage(uid, text=u"Time to BUY %s (%s) Qty = %8.2f Price = %8.3f" % (stock['name'], symbol, qty, nowquotevalue))
                if VERBOSE:
                    print "Time to BUY %s (%s) Qty = %8.2f Price = %8.3f" % (stock['name'], symbol, qty, nowquotevalue)

            checkifdividendday(datetradenow.date() ,conn)

            c2 = conn.cursor()
            c2.execute("UPDATE stocks SET lastquotestamp = ?, lastquote = ?  WHERE id = ?;",  (datetradenow, nowquotevalue, stock['stockid'])) #update last quote timestamp
            conn.commit()

        if qty>0 and nowquotevalue>=(1+minreturn)*buyprice and newdayalert:
            newdayalert = False
            bot.sendMessage(uid, text=u"Time to SELL %s (%s) Qty = %8.2f Price = %8.3f" % (stock['name'], symbol, qty, nowquotevalue))
            if VERBOSE:
                print "Time to SELL %s (%s) Qty = %8.2f Price = %8.3f" % (stock['name'], symbol, qty, nowquotevalue)

##########################################################################

##########################################################################
def checkifdividendday(today, conn):
    c = conn.cursor()
    for dividend in c.execute("select * from dividends where date=:date", {'date':today}):
        c1 = conn.cursor()
        c1.execute("select * from portfolio where stockid=:id", {'id':dividend['stockid']})
        portfolio = c1.fetchone()
        if not(portfolio is None):
            c2 = conn.cursor()
            c2.execute("""
            insert into movements(stockid,date,qty,value,action)
            values(?,?,?,?,?)
            """, (int(dividend['stockid']), today, float(portfolio['qty']), float(dividend['value']), 'dividend'))
##########################################################################

##########################################################################
def checkiftimetobuy(symbol, lowcount, datetradenow, nowquotevalue):
    #get last days of quotes
    quotes = get_historical_prices(symbol, (datetradenow-datetime.timedelta(days=lowcount)).strftime("%Y-%m-%d"), (datetradenow-datetime.timedelta(days=1)).strftime("%Y-%m-%d"))
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
        return True
    else:
        return False
##########################################################################

##########################################################################
def buystock(symbol, qty, price, date, conn):

    if qty<=0:
        return

    if date is None:
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
##########################################################################

##########################################################################
def sellstock(symbol, qty, price, date, conn):
    success = False
    if qty<=0:
        return success

    if date is None:
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
##########################################################################

##########################################################################
def checkifmarketopen(exchangeid, stocksymbol, stockname, conn):
    daytoday = str(datetime.datetime.utcnow().weekday())
    datetoday = datetime.datetime.utcnow().strftime("%Y-%m-%d")
    year = datetime.datetime.utcnow().year

    #see if the stock exchange is opened today
    exchangeid = int(exchangeid)
    c1 = conn.cursor()
    c1.execute("select * from exchanges where id=:id;", {"id":exchangeid})
    exchange = c1.fetchone()
    opendays = exchange["workingdays"].split(",")

    if not(daytoday in opendays): #if stockmarket closed, pass
        if VERBOSE:
            print "Stock market %s in weekend for stock %s(%s)" % (exchange['shortnamegoogle'], stocksymbol,stockname)
        return False

    #see if today is a holliday in the stock exchange
    country = exchange["countrycode"]

    isholliday = False

    #check to see if database knows if this date is holliday
    c2 = conn.cursor()
    c2.execute("select * from hollidays where country=:country and date=:date;", {"country":country, "date":datetoday})
    getholliday = c2.fetchone()
    if getholliday is None: # date is not yet in database for this country
        #check online to see if this date is holliday
        try:
            r = requests.get("http://kayaposoft.com/enrico/json/v1.0/?action=getPublicHolidaysForYear&year=%d&country=%s" % (year, country))
            for date in r.json():
                holliday = datetime.date(date['date']['year'], date['date']['month'], date['date']['day'])
                if datetime.datetime.today() == holliday:
                    isholliday = True
                    break
        except:
            pass

        #save date to database for this country
        c2 = conn.cursor()
        c2.execute("INSERT INTO hollidays(country,date,holliday) VALUES (?,?,?);", (country, datetoday, isholliday)) #save date as holliday
        conn.commit()

    else: # date is allready in database for this country
        isholliday = getholliday['holliday']

    if isholliday: #if today is holliday, pass
        if VERBOSE:
            print "Stock market %s in holliday for stock %s(%s)" % (exchange['shortnamegoogle'], stocksymbol,stockname)
        return False

    #see if the stock exchange is opened now
    now = datetime.datetime.utcnow().replace(tzinfo = pytz.utc) # get current date and time in UTC with  timezone info
    openhour = exchange["openhour"]
    closehour = exchange["closehour"]

    if not(openhour is None) and not(closehour is None):
        openhour = dateutil.parser.parse(openhour)
        closehour = dateutil.parser.parse(closehour)

        if (now<openhour) or (now>closehour): #if stockmarket closed, pass
            if VERBOSE:
                print "Stock market %s closed for stock %s(%s)" % (exchange['shortnamegoogle'], stocksymbol,stockname)
            return False

    return True
##########################################################################

##########################################################################
def getmarketoptions(stockid, conn):
    comission = 0.0
    taxondividends = 0.0

    c = conn.cursor()
    c.execute("""
                select comission, taxondividends
                from exchanges, stocks
                where exchanges.id=stocks.exchangeid and stocks.id=:id
                """, {'id':stockid})

    try:
        row = c.fetchone()
        comission = float(row['comission'])
        taxondividends = float(row['taxondividends'])
    except:
        pass

    return comission, taxondividends
##########################################################################

##########################################################################
def getexchangerate(stockid, date, conn):
    c = conn.cursor()
    c.execute("""
                select currencies.shortname
                from stocks, currencies
                where currencies.id=stocks.currencyid and stocks.id=:id
                """, {'id':stockid})
    stockcurrency = str(c.fetchone()['shortname'])
    c.execute("select value from options where name='Base Currency'")
    basecurrency = str(c.fetchone()['value'])

    if basecurrency == stockcurrency:
        return 1.0

    cross = basecurrency+stockcurrency
    date = dateutil.parser.parse(date).replace(hour=23,minute=59,second=59)
    c.execute("""
                select quotes.timestamp, quotes.value
                from quotes, stocks
                where quotes.stockid=stocks.id and stocks.symbolgoogle=:cross and quotes.timestamp<=:date
                order by timestamp desc
                """, {'cross':cross, 'date':date})

    exchange = 1.0

    try:
        row = c.fetchone()
        exchange = row['value']
        exchange = float(exchange)
    except:
        exchange = 1.0

    return exchange
##########################################################################

##########################################################################
def getstockreturn(stockid, conn):
    comission, taxondividends = getmarketoptions(stockid, conn)

    c = conn.cursor()
    c.execute("select * from movements where stockid=:id order by date ASC", {'id':int(stockid)})
    movements = c.fetchall()

    investment = 0.0
    cash = 0.0

    for movement in movements:
        exchange = getexchangerate(stockid,movement['date'],conn)

        if movement['action'].upper() == 'BUY':
            investment += movement['qty'] * movement['value'] / exchange + comission
        elif movement['action'].upper() == 'SELL':
            cash += movement['qty'] * movement['value'] / exchange - comission
        elif movement['action'].upper() == 'DIVIDEND':
            cash += movement['qty'] * movement['value'] / exchange * (1-taxondividends)

    c.execute("select symbolgoogle from stocks where id=:id", {'id':int(stockid)})
    symbol = str(c.fetchone()['symbolgoogle'])
    quote = getQuotes(symbol)[0]["LastTradePrice"]  #get quote
    c.execute("select qty from portfolio where stockid=:id", {'id':int(stockid)})
    qty = float(c.fetchone()['qty'])
    cash += qty * float(quote) / exchange

    if investment<>0:
        ireturn = (cash/investment-1)*100
    else:
        ireturn = 0

    return ireturn
##########################################################################

if __name__ == "__main__":
    main()