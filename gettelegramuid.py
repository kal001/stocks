__author__ = 'fernandolourenco'

import telepot

from ConfigParser import SafeConfigParser
import codecs

import os
import sys

#Constants
##########################################################################
SETTINGSFILE = 'stocks.ini'
##########################################################################

# Read config file
parser = SafeConfigParser()

# Open the file with the correct encoding
with codecs.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGSFILE), 'r', encoding='utf-8') as f:
    parser.readfp(f)

try:
    # Create access to bot
    bot = telepot.Bot(parser.get('Telegram', 'token'))
except:
    print u'Cannot access Telegram. Please do /start'
    sys.exit(1)

message = bot.getUpdates()

print "User id = %s" % message[0]['message']['from']['id']