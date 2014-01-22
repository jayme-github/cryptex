#!/usr/bin/env python

import sys
from decimal import *
from cryptex.cryptsy import Cryptsy

if len(sys.argv) <= 1:
    print 'Give file containing api key and api secret (one per line) as argument'
    sys.exit(1)

key_file = open(sys.argv[1], 'r')
KEY, SECRET = [ l.strip() for l in key_file.readlines() ]
key_file.close()
cryptsy = Cryptsy(KEY, SECRET)
info = cryptsy._get_info()


def sell(amount, market):
    order_qantity = Decimal(0.0)
    for order in cryptsy.get_market_orders(market)['buyorders']:
        order_qantity += order['quantity']
        if order_qantity >= amount:
            # enough volume to sell to
            break
    sell_for = cryptsy.calculate_fee('Sell', amount, order['buyprice'])
    print '%.8f %s @ %.8f =~ %.8f %s' % (amount, market[0], order['buyprice'],
                                            sell_for['net'], market[1])
    return sell_for['net']



balances = {}
btc_estimate = Decimal(0.0)

for currency, value in info['balances_available'].iteritems():
    balances[currency] = [(value + info['balances_hold'][currency])]
    if balances[currency][0] > Decimal(0.0):
        if currency == 'BTC':
            btc_value = balances[currency][0]
        else:
            for counter_currenty in ('BTC', 'LTC', 'XPM'):
                market = filter(lambda c: c[0] == currency and c[1] == counter_currenty, cryptsy.get_markets())
                if market:
                    market = market[0]
                    break
            if market[1] == 'BTC':
                btc_value = sell(balances[currency][0], market)
            else:
                # sell for LTC or XPM fist, than BTC
                pre_value = sell(balances[currency][0], market)
                btc_value = sell(pre_value, (market[1], 'BTC'))
        
        btc_estimate += btc_value
        balances[currency].append(btc_value)
        print '%s:\t%.8f (~%.8f BTC)' % (currency, balances[currency][0], balances[currency][1])

print '\noverall balance estimate: %.8f BTC' % btc_estimate
