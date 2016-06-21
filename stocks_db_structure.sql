--
-- File generated with SQLiteStudio v3.0.6 on ter jun 7 22:27:00 2016
--
-- Text encoding used: UTF-8
--
PRAGMA foreign_keys = off;
BEGIN TRANSACTION;

-- Table: stocks
CREATE TABLE stocks (id INTEGER PRIMARY KEY NOT NULL UNIQUE, name TEXT, symbolgoogle TEXT NOT NULL UNIQUE, symbolyahoo TEXT NOT NULL UNIQUE, exchangeid INTEGER NOT NULL, tracked BOOLEAN NOT NULL DEFAULT False, interval INTEGER DEFAULT 5, lastquote REAL, lastquotestamp DATETIME, currencyid INTEGER REFERENCES currencies (id), type TEXT);

-- Table: strategies
CREATE TABLE strategies (id INTEGER PRIMARY KEY NOT NULL UNIQUE, stockid INTEGER REFERENCES stocks (id), active BOOLEAN, lowcount INTEGER, minreturn REAL);

-- Table: portfolio
CREATE TABLE portfolio (id INTEGER PRIMARY KEY UNIQUE NOT NULL, stockid INTEGER REFERENCES stocks (id) NOT NULL UNIQUE, qty REAL, cost REAL);

-- Table: movements
CREATE TABLE movements (id INTEGER PRIMARY KEY UNIQUE, stockid INTEGER REFERENCES stocks (id) NOT NULL, date DATETIME, qty REAL, value REAL, "action" STRING, options STRING);

-- Table: currencies
CREATE TABLE currencies (id INTEGER PRIMARY KEY NOT NULL UNIQUE, symbol TEXT NOT NULL UNIQUE, shortname TEXT);

-- Table: exchanges
CREATE TABLE exchanges (id INTEGER PRIMARY KEY NOT NULL UNIQUE, name TEXT, countrycode TEXT, shortnamegoogle TEXT, shortnameyahoo TEXT, openhour TIME, closehour TIME, workingdays TEXT, comission REAL, taxondividends REAL);

-- Table: dividends
CREATE TABLE dividends (id INTEGER PRIMARY KEY NOT NULL UNIQUE, stockid INTEGER REFERENCES stocks (id), date DATE, value DOUBLE);

-- Table: options
CREATE TABLE options (id INTEGER PRIMARY KEY NOT NULL UNIQUE, name TEXT, value TEXT);

-- Table: quotes
CREATE TABLE quotes (id INTEGER PRIMARY KEY NOT NULL UNIQUE, stockid INTEGER NOT NULL REFERENCES currencies (id), timestamp DATETIME NOT NULL, value FLOAT NOT NULL);

-- Table: hollidays
CREATE TABLE hollidays (id INTEGER PRIMARY KEY UNIQUE NOT NULL, country TEXT, zone TEXT, date DATETIME, holliday BOOLEAN);

-- Table: splits
DROP TABLE IF EXISTS splits;
CREATE TABLE splits (id INTEGER PRIMARY KEY NOT NULL UNIQUE, stockid INTEGER REFERENCES stocks (id), date DATE, value DOUBLE);

COMMIT TRANSACTION;
PRAGMA foreign_keys = on;
