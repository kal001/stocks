# coding=UTF-8
__author__ = 'fernandolourenco'
import version

import datetime
import time

import telepot
import codecs
import sys
import os

import sqlite3

import pprint

import monitorstock

from ConfigParser import SafeConfigParser

#Constants
SETTINGSFILE = 'stocks.ini'

global bot
global uid

global DATABASE

def handle(msg):
    global DATABASE

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row

    #pprint.pprint(msg)
    message = msg['text'].upper()
    commands = message.split(" ")

    if commands[0] == '/SELL':
        try:
            qty = float(commands[1])
            stock = commands[2]
            price = float(commands[3])
        except:
            bot.sendMessage(uid, text=u"Error. Correct syntax /sell quantity google_code price [date]" )
            return

        try:
            date = commands[3]
        except:
            date = None

        c = conn.cursor()

        try:
            if monitorstock.sellstock(stock, qty, price, conn):
                c.execute("select portfolio.qty,portfolio.cost from portfolio, stocks where stocks.symbolgoogle=:symbol and portfolio.stockid=stocks.id", {'symbol':stock})
                row = c.fetchone()
                try:
                    qtyonhand = float(row['qty'])
                    bot.sendMessage(uid, text=u"Success. Sold %.2f. New quantity on hand %.2f." % (qty, qtyonhand) )
                except:
                    bot.sendMessage(uid, text=u"Success. Sold %.2f. Closed position." % (qty) )
            else:
                bot.sendMessage(uid, text=u"Error. Unknown stock; or not available; or not enough quantity to sell %s" % stock )
        except Exception,e:
            #print str(e)
            bot.sendMessage(uid, text=u"Error. Unknown stock or not available to sell %s" % stock )
            return

        conn.close()
    elif commands[0] == '/BUY':
        try:
            qty = float(commands[1])
            stock = commands[2]
            price = float(commands[3])
        except:
            bot.sendMessage(uid, text=u"Error. Correct syntax /buy quantity google_code price [date]" )
            return

        try:
            date = commands[4]
        except:
            date = None

        try:
            monitorstock.buystock(stock, qty, price, conn)

            c = conn.cursor()
            c.execute("select portfolio.qty,portfolio.cost from portfolio, stocks where stocks.symbolgoogle=:symbol and portfolio.stockid=stocks.id", {'symbol':stock})
            row = c.fetchone()
            qty = float(row['qty'])
            avgprice = float(row['cost'])
            bot.sendMessage(uid, text=u"Success. Bought %.2f %s @ %.3f. New quantity on hand %.2f. New averageprice %.3f" % (qty, stock, price, qty, avgprice) )

        except Exception,e:
            #print str(e)
            bot.sendMessage(uid, text=u"Error. Unknown stock or not available to buy %s" % stock )
            return

        conn.close()
    elif commands[0] == '/STATUS':
        bot.sendMessage(uid, text=u"Ok. Running")
    elif commands[0] == '/START':
        bot.sendMessage(uid, text=u"Started. Time now\n%s" % datetime.datetime.now())
    elif commands[0] == '/PORTFOLIO':
        bot.sendMessage(uid, text=u"QTY\tSTOCK\tPRICE")

        c = conn.cursor()
        for row in c.execute("select portfolio.qty,portfolio.cost, stocks.name, stocks.symbolgoogle from portfolio, stocks where portfolio.stockid=stocks.id"):
            bot.sendMessage(uid, text=u"%.2f\t%s (%s)\t%.3f" % (float(row['qty']), row['name'], row['symbolgoogle'], float(row['cost']) ))
    elif commands[0] == '/HELP':
        bot.sendMessage(uid, text=u"Available commands for %s: /buy, /sell, /status, /portfolio" % os.path.basename(sys.argv[0]))
    else:
        bot.sendMessage(uid, text=u"Unknown command" )

def main():
    global bot
    global uid

    # Read config file
    parser = SafeConfigParser()

    # Open the file with the correct encoding
    with codecs.open(SETTINGSFILE, 'r', encoding='utf-8') as f:
        parser.readfp(f)

    try:
        # Create access to bot
        bot = telepot.Bot(parser.get('Telegram', 'token'))
        bot.message_loop(handle)
        uid = parser.get('Telegram', 'uid')
        bot.sendMessage(uid, text=u"Start %s\n%s" % (os.path.basename(sys.argv[0]), datetime.datetime.now()))
    except:
        print u'Cannot access Telegram. Please do /start'
        sys.exit(1)

    global DATABASE
    DATABASE = parser.get('Database', 'File')

    # Keep the program running.
    while 1:
        time.sleep(10)

if __name__ == "__main__":
    main()