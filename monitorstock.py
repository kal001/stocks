# coding=UTF-8
"""
.. module:: monitorstock
    :synopsis: This module acquires periodic quotes
.. moduleauthor:: Fernando Lourenco <fernando.lourenco@lourenco.eu>
"""
import version

from googlefinance import getQuotes
from ystockquote import get_historical_prices, get_price
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

import requests

#Constants
##########################################################################
VERBOSE = False
"""boolean: Variable to control output to stdout of messages during execution"""
SETTINGSFILE = 'stocks.ini'
"""string: Name of settings file"""
HOLIDAYSERVICE = "http://kayaposoft.com/enrico/json/v1.0/?action=getPublicHolidaysForYear&year=%d&country=%s"
"""string: Address of webservice to retreive holiday data"""
##########################################################################

#Globals
##########################################################################
global DATABASE
global newdayalert
global tzd #timezones object
##########################################################################

##########################################################################
def main():
    global newdayalert

    initializetz()

    # Read config file
    parser = SafeConfigParser()

    # Open the file with the correct encoding
    with codecs.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGSFILE), 'r', encoding='utf-8') as f:
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

    #sellstock('NASDAQ:QLIK', 10, 30,None,conn)

    c = conn.cursor()

    #Check if it is time to buy or sell in active strategies
    for stock in c.execute("""
                select strategies.*, stocks.name, stocks.symbolgoogle, stocks.symbolyahoo, stocks.exchangeid, stocks.lastquotestamp
                from strategies, stocks
                where strategies.stockid=stocks.id and strategies.active='True';
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
        correcteddate = quote["LastTradeDateTimeLong"]
        #parse uses posix stype for timezone offsets. ISO requires inversion in sign!!
        if correcteddate.find('+'):
            correcteddate=correcteddate.replace('+', '-')
        elif correcteddate.find('-'):
            correcteddate=correcteddate.replace('-', '+')
        datetradenow = dateutil.parser.parse(correcteddate, tzinfos=tzd) #get current last trade time on market
        nowquotevalue = float(quote['LastTradePrice']) #get last quote

        newdayalert = False

        if (lasttradedatetime is None) or datetradenow.date()!=lasttradedatetime.date():
            #New Day!
            bot.sendMessage(uid, text=u"New Day for stock %s" % stock['name'])
            if VERBOSE:
                print "New Day for stock %s" % stock['name']
            newdayalert = True

        if newdayalert:
            #Number of days descending reached, and opend low
            if checkiftimetobuy(stock['symbolyahoo'], lowcount, datetradenow, nowquotevalue):
                bot.sendMessage(uid, text=u"Time to BUY %s (%s) Price = %8.3f" % (stock['name'], symbol, nowquotevalue))
                if VERBOSE:
                    print "Time to BUY %s (%s) Price = %8.3f" % (stock['name'], symbol, nowquotevalue)

            checkifdividendday(datetradenow.date() ,conn)

            c2 = conn.cursor()
            c2.execute("UPDATE stocks SET lastquotestamp = ?, lastquote = ?  WHERE id = ?;",  (datetradenow.isoformat(), nowquotevalue, stock['stockid'])) #update last quote timestamp
            conn.commit()

        if qty>0 and nowquotevalue>=(1+minreturn)*buyprice and newdayalert:
            newdayalert = False
            bot.sendMessage(uid, text=u"Time to SELL %s (%s) Qty = %8.2f Price = %8.3f" % (stock['name'], symbol, qty, nowquotevalue))
            if VERBOSE:
                print "Time to SELL %s (%s) Qty = %8.2f Price = %8.3f" % (stock['name'], symbol, qty, nowquotevalue)

    #Update quotes in tracked stocks
    for stock in c.execute("select * from stocks where tracked='True'"):
        if not(checkifmarketopen(stock["exchangeid"], stock['symbolgoogle'], stock['name'],conn)):
            continue

        nowutc = datetime.datetime.utcnow().replace(tzinfo = pytz.utc)
        lastdateplus = dateutil.parser.parse(stock['lastquotestamp']) + datetime.timedelta( minutes=int(stock['interval'] ))
        if (stock['lastquotestamp'] is None) or (lastdateplus< nowutc):
            timestamp, nowquotevalue = savequote(int(stock['id']), stock['lastquotestamp'], conn)

    conn.commit()
##########################################################################

##########################################################################
def checkifdividendday(today, conn):
    """ Check if today is a dividend day, and add the dividend to the stocks
    in portfolio

    Args:
        today (date): date to check
        conn (connection): connection object to the database

    Returns:
        none
    """
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
    """ Check if it is time to suy a stock, by checking if stock closed low for
    a consecutive lowcount number of days, and today opend low again

    Args:

        symbol (string): yahoo finance symbol to check if it is time to buy
        lowcount (int): number of consecutive days of closing low to decide to buy
        datetradenow (datetime): date and time object with current quote
        nowquotevalue (float): current quote value
    Returns:
        boolean: True if it is time to buy stock
    """

    quotes = get_historical_prices(symbol, (datetradenow-datetime.timedelta(days=lowcount)).strftime("%Y-%m-%d"), (datetradenow-datetime.timedelta(days=1)).strftime("%Y-%m-%d"))
    sortedquotes = sorted(quotes.items(), key=operator.itemgetter(0))

    #check if number of days descending reached
    quoteant = 0.0
    countlow = 0
    for day in sortedquotes:
        #calculate day return
        if quoteant != 0:
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

    symbol = symbol.upper()

    c = conn.cursor()
    #get stock id
    c.execute("select id from stocks where symbolgoogle=:id", {"id":symbol})
    row = c.fetchone()
    stockid = row['id']

    if date is None:
        now = datetime.datetime.utcnow().isoformat()+'Z' #.replace(tzinfo = pytz.utc) # get current date and time in UTC with  timezone info

        #save currency exchange ratio
        cross, crossid = getexchangesymbol(stockid,conn)
        if cross !='':
            er = get_price(cross)
            c.execute("""
                  insert into quotes(stockid,timestamp,value)
                  values (?, ?, ?)
                  """, (crossid,now, er))

    else:
        now = dateutil.parser.parse(date) #.replace(tzinfo = pytz.utc)
        now = now.isoformat()

        #ToDo get historical exchange ratio

    #update quotes
    c.execute("""
      insert into quotes(stockid,timestamp,value)
      select stocks.id, ?, ?
      from stocks
      where stocks.symbolgoogle=?;
      """, (now, price, symbol))

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

    symbol = symbol.upper()

    c = conn.cursor()
    #get stock id
    c.execute("select id from stocks where symbolgoogle=:id", {"id":symbol})
    row = c.fetchone()
    stockid = row['id']

    if date is None:
        now = datetime.datetime.utcnow().isoformat()+'Z' #.replace(tzinfo = pytz.utc) # get current date and time in UTC with  timezone info

        #save currency exchange ratio
        cross, crossid = getexchangesymbol(stockid,conn)
        if cross !='':
            er = get_price(cross)
            c.execute("""
                  insert into quotes(stockid,timestamp,value)
                  values (?, ?, ?)
                  """, (crossid,now, er))
    else:
        now = dateutil.parser.parse(date) #.replace(tzinfo = pytz.utc)
        now = now.isoformat()

        #ToDo get historical exchange ratio

    #update quotes
    c.execute("""
      insert into quotes(stockid,timestamp,value)
      select stocks.id, ?, ?
      from stocks
      where stocks.symbolgoogle=?;
      """, (now, price, symbol))

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
            r = requests.get(HOLIDAYSERVICE % (year, country))
            for date in r.json():
                holliday = datetime.date(date['date']['year'], date['date']['month'], date['date']['day'])
                if datetoday == holliday.strftime("%Y-%m-%d"):
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
    timezone = exchange['timezone']

    if not(openhour is None) and not(closehour is None):
        openhour = pytz.timezone(timezone).localize(dateutil.parser.parse(openhour))
        closehour = pytz.timezone(timezone).localize(dateutil.parser.parse(closehour))

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
def getexchangesymbol(stockid, conn):
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
        return '', ''
    else:
        cross = basecurrency+stockcurrency+'=X'
        c = conn.cursor()
        c.execute("select id from stocks where symbolyahoo=:cross", {'cross':cross})
        crossid = int(c.fetchone()['id'])
        return cross, crossid
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

    # If stock in portfolio check its current martket value
    c.execute("select symbolgoogle from stocks where id=:id", {'id':int(stockid)})
    symbol = str(c.fetchone()['symbolgoogle'])
    quote = getQuotes(symbol)[0]["LastTradePrice"]  #get quote
    c.execute("select qty from portfolio where stockid=:id", {'id':int(stockid)})

    try:
        qty = float(c.fetchone()['qty'])
        cash += qty * float(quote) / exchange
    except:
        pass

    if investment!=0:
        ireturn = (cash/investment-1)*100
    else:
        ireturn = 0

    return ireturn
##########################################################################

##########################################################################
def savequote(stockid, lastquotestamp, conn):
    c = conn.cursor()

    c.execute("select symbolgoogle, symbolyahoo, type from stocks where id=:id", {'id':int(stockid)})

    row = c.fetchone()
    if row['type'].upper() == 'STOCK':
        symbol = str(row['symbolgoogle'])
        quote = getQuotes(symbol) #get quote
        value = quote[0]["LastTradePrice"]
        #parse uses posix stype for timezone offsets. ISO requires inversion in sign!!
        correcteddate = quote[0]["LastTradeDateTimeLong"]
        if correcteddate.find('+'):
            correcteddate=correcteddate.replace('+', '-')
        elif correcteddate.find('-'):
            correcteddate=correcteddate.replace('-', '+')
        date = dateutil.parser.parse(correcteddate, tzinfos=tzd)
        timestamp = date.isoformat()
        if date.tzinfo is None:
            timestamp += 'Z'

    elif row['type'].upper() == 'CURRENCY':
        symbol = str(row['symbolyahoo'])
        value = float(get_price(symbol)) #get quote
        date = datetime.datetime.utcnow().replace(tzinfo = pytz.utc)
        timestamp = date.isoformat()

    if (lastquotestamp is None) or (dateutil.parser.parse(lastquotestamp, tzinfos=tzd) != date):
        #Date changed since last quote => save to database
        c.execute("""
                insert into quotes(stockid,timestamp,value)
                values(?,?,?)
                """, (int(stockid), timestamp, float(value)))

        if not(timestamp is None):
            c = conn.cursor()
            c.execute("""
                UPDATE stocks
                SET lastquotestamp = ?, lastquote = ?
                WHERE id = ?;
                """,  (timestamp, float(value), int(stockid))) #update last quote timestamp

        conn.commit()

        return timestamp, float(value)
    else:
        return None, None
##########################################################################

##########################################################################
def initializetz():
    global tzd

    tz_str = '''-12 Y
    -11 X NUT SST
    -10 W CKT HAST HST TAHT TKT
    -9 V AKST GAMT GIT HADT HNY
    -8 U AKDT CIST HAY HNP PST PT
    -7 T HAP HNR MST PDT
    -6 S CST EAST GALT HAR HNC MDT
    -5 R CDT COT EASST ECT EST ET HAC HNE PET
    -4 Q AST BOT CLT COST EDT FKT GYT HAE HNA PYT
    -3 P ADT ART BRT CLST FKST GFT HAA PMST PYST SRT UYT WGT
    -2 O BRST FNT PMDT UYST WGST
    -1 N AZOT CVT EGT
    0 Z EGST GMT UTC WET WT
    1 A CET DFT WAT WEDT WEST
    2 B CAT CEDT CEST EET SAST WAST
    3 C EAT EEDT EEST IDT MSK
    4 D AMT AZT GET GST KUYT MSD MUT RET SAMT SCT
    5 E AMST AQTT AZST HMT MAWT MVT PKT TFT TJT TMT UZT YEKT
    6 F ALMT BIOT BTT IOT KGT NOVT OMST YEKST
    7 G CXT DAVT HOVT ICT KRAT NOVST OMSST THA WIB
    8 H ACT AWST BDT BNT CAST HKT IRKT KRAST MYT PHT SGT ULAT WITA WST
    9 I AWDT IRKST JST KST PWT TLT WDT WIT YAKT
    10 K AEST ChST PGT VLAT YAKST YAPT
    11 L AEDT LHDT MAGT NCT PONT SBT VLAST VUT
    12 M ANAST ANAT FJT GILT MAGST MHT NZST PETST PETT TVT WFT
    13 FJST NZDT
    11.5 NFT
    10.5 ACDT LHST
    9.5 ACST
    6.5 CCT MMT
    5.75 NPT
    5.5 SLT
    4.5 AFT IRDT
    3.5 IRST
    -2.5 HAT NDT
    -3.5 HNT NST NT
    -4.5 HLV VET
    -9.5 MART MIT'''

    tzd = {}
    for tz_descr in map(str.split, tz_str.split('\n')):
        tz_offset = int(float(tz_descr[0]) * 3600)
        for tz_code in tz_descr[1:]:
            tzd[tz_code] = tz_offset
##########################################################################

##########################################################################
if __name__ == "__main__":
    main()