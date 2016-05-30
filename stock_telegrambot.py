# coding=UTF-8
__author__ = 'fernandolourenco'

import datetime
import time

import telepot
import codecs
import sys
import os

import sqlite3

import pprint

from ConfigParser import SafeConfigParser

#Constants
SETTINGSFILE = 'stocks.ini'

global bot
global uid

global DATABASE

def handle(msg):
    #pprint.pprint(msg)
    message = msg['text'].upper()
    commands = message.split(" ")

    if commands[0] == '/SELL':
        try:
            qty = float(commands[1])
            stock = commands[2]
        except:
            bot.sendMessage(uid, text=u"Error. Correct syntax /sell quantity google_code" )
            return

        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        try:
            c.execute("select strategies.qty, strategies.id from strategies, stocks where symbolgoogle=:symbol and strategies.stockid=stocks.id;", {"symbol":stock})
            row = c.fetchone()
            if row['qty'] is None:
                qtyonhand = 0
            else:
                qtyonhand = float(row['qty'])

            strategyid = int(row['id'])

            if qtyonhand<qty:
                bot.sendMessage(uid, text=u"Error. Quantity on hand (%.2f) smaller than requested to sell (%.2f)" % (qtyonhand, qty) )
            else:
                c.execute("UPDATE strategies SET qty = ? WHERE id = ?;",  (qtyonhand-qty, strategyid)) #update quantity
                conn.commit()
                bot.sendMessage(uid, text=u"Success. Sold %.2f. New quantity on hand %.2f." % (qty, qtyonhand-qty) )

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
            bot.sendMessage(uid, text=u"Error. Correct syntax /buy quantity google_code price" )
            return

        conn = sqlite3.connect(DATABASE)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        try:
            c.execute("select strategies.qty, strategies.id, strategies.buyprice from strategies, stocks where symbolgoogle=:symbol and strategies.stockid=stocks.id;", {"symbol":stock})
            row = c.fetchone()
            if row['qty'] is None:
                qtyonhand = 0
            else:
                qtyonhand = float(row['qty'])

            strategyid = int(row['id'])

            if row['buyprice'] is None:
                buyprice=0
            else:
                buyprice = float(row['buyprice'])

            avgprice = (qtyonhand * buyprice + qty * price) / (qtyonhand + qty)
            c.execute("UPDATE strategies SET qty = ?, buyprice = ? WHERE id = ?;",  (qtyonhand+qty, avgprice, strategyid)) #update quantity and price
            conn.commit()
            bot.sendMessage(uid, text=u"Success. Bought %.2f %s @ %.3f. New quantity on hand %.2f. New averageprice %.3f" % (qty, stock, price, qtyonhand+qty, avgprice) )

        except Exception,e:
            #print str(e)
            bot.sendMessage(uid, text=u"Error. Unknown stock or not available to buy %s" % stock )
            return

        conn.close()
    elif commands[0] == '/STATUS':
        bot.sendMessage(uid, text=u"Ok. Running")
    elif commands[0] == '/START':
        bot.sendMessage(uid, text=u"Started. Time now\n%s" % datetime.datetime.now())
    elif commands[0] == '/HELP':
        bot.sendMessage(uid, text=u"Available commands for %s: /buy, /sell, /status" % os.path.basename(sys.argv[0]))
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