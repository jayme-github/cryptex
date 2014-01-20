#!/usr/bin/env python

# Send DBUS notifications for new Buy/Sell orders

import sys
import os
import signal
import time
import notify2
import requests
from cryptex.cryptsy import Cryptsy

if len(sys.argv) <= 1:
    print 'Give file containing api key and api secret (one per line) as argument'
    sys.exit(1)

key_file = open(sys.argv[1], 'r')
KEY, SECRET = [ l.strip() for l in key_file.readlines() ]
key_file.close()
cryptsy = Cryptsy(KEY, SECRET)
BASESTR = 'Cryptsy Notification'

notify2.init(BASESTR)
notification = notify2.Notification(BASESTR, '')

status_file_path = os.path.join(os.path.dirname(__file__), __file__) + '.conf'
try:
    status_file = open(status_file_path, 'rb')
    last_trade_id = int(status_file.readline().strip())
    status_file.close()
except IOError:
    last_trade_id = -1
last_saved_id = last_trade_id

def save_state(signal=None, frame=None):
    global status_file_path, last_trade_id, last_saved_id
    if last_trade_id != last_saved_id:
        status_file = open(status_file_path, 'wb')
        status_file.write(str(last_trade_id) + '\n')
        status_file.close()
        last_saved_id = last_trade_id
    if signal:
        sys.exit(0)
signal.signal(signal.SIGINT, save_state)


while True:
    try:
        new_trades = sorted(filter(lambda x: x.trade_id > last_trade_id, cryptsy.get_my_trades()), key=lambda x: x.trade_id)
    except requests.exceptions.ConnectionError, e:
        time.sleep(10)
        continue
    if last_trade_id == -1:
        # Only show last 5 trades on first run
        new_trades = new_trades[:5]
    for t in new_trades:
        if t.trade_type == 0:
            what = 'bought'
        else:
            what = 'sold'
        msg = 'You %s %.8f %s @ %.8f (%.8f %s)' %(what, t.amount,
                                                t.base_currency,
                                                t.price,
                                                (t.amount * t.price) + t.fee,
                                                t.counter_currency)
        notification.update(BASESTR, msg)
        notification.show()
        last_trade_id = t.trade_id
        time.sleep(1)
    save_state()
    time.sleep(10)
