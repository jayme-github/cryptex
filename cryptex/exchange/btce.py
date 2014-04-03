import datetime
import pytz
import re
from decimal import Decimal

from cryptex.exchange import Exchange
from cryptex.trade import Sell, Buy
from cryptex.order import SellOrder, BuyOrder
from cryptex.transaction import Transaction, Deposit, Withdrawal
from cryptex.exchange.single_endpoint import SingleEndpoint, SignedSingleEndpoint
from cryptex.exception import APIException
import cryptex.common as common

class BTCEBase(object):
    @staticmethod
    def _format_timestamp(timestamp):
        return pytz.utc.localize(datetime.datetime.utcfromtimestamp(
            timestamp))

    @staticmethod
    def _pair_to_market(pair):
        return tuple([c.upper() for c in pair.split('_')])

    @staticmethod
    def _market_to_pair(market):
        return '_'.join((market[0].lower(), market[1].lower()))


class BTCEPublic(BTCEBase, SingleEndpoint):
    '''
    BTC-e public API https://btc-e.com/api/3/documentation
    All information is cached for 2 seconds on the server

    TODO: Add local caching to prevent frequent requests
    TODO: Format market pairs in output
    '''
    API_ENDPOINT = 'https://btc-e.com/api/3/'

    def _get_market_info(self, method, markets, limit=0, ignore_invalid=True):
        '''
        Takes a market as reported by the get_info() method -- meaning that it
        must be of the form currencyA_currencyB
        '''
        params = {}
        if limit:
            if limit > 2000:
                raise ValueError('Maximum limit is 2000')
            params['limit'] = limit
        
        if ignore_invalid:
            params['ignore_invalid'] = 1

        j = self.perform_get_request('/'.join((method, '-'.join(markets))), params=params)
        return {x: j[x] for x in j.keys() if x in markets}

    def get_info(self):
        '''
        Information about currently active pairs,
        such as the maximum number of digits after the decimal point in the auction,
        the minimum price, maximum price, minimum quantity purchase / sale,
        hidden=1whether the pair and the pair commission.
        '''
        j = self.perform_get_request('info')
        j['server_time'] = BTCEPublic._format_timestamp(j['server_time'])
        return j

    def get_ticker(self, markets, ignore_invalid=True):
        '''
        Information about bidding on a pair, such as:
        the highest price, lowest price, average price, trading volume,
        trading volume in the currency of the last deal, the price of buying and selling.

        All information is provided in the last 24 hours.
        FIXME: What does that mean?
        '''
        results = self._get_market_info('ticker', markets, ignore_invalid)

        for v in results:
            if v is dict:
                v['updated'] = BTCEPublic._format_timestamp(v['updated'])

        return results

    def get_depth(self, market, limit=150):
        '''
        Information on active warrants pair.
        Takes an optional parameter limit which indicates how many orders you want to display (default 150, max 2000).
        '''
        return self._get_market_info('depth', [market], limit)

    def get_trades(self, market, limit=150):
        '''
        Information on the latest deals.
        Takes an optional parameter limit which indicates how many orders you want to display (default 150, max 2000).
        '''
        j = self._get_market_info('trades', [market], limit)
        for t in j:
            t['timestamp'] = BTCEPublic._format_timestamp(t['timestamp'])
        return j


class BTCE(BTCEBase, Exchange, SignedSingleEndpoint):
    API_ENDPOINT = 'https://btc-e.com/tapi'
    def __init__(self, key, secret):
        self.key = key
        self.secret = secret
        self.public = BTCEPublic()

        # Set up regular expressions for transaction parsing
        r_float = r'(?:\d+)\.?(?:\d+)?'
        r_currency_code = r'[A-Z\d]+'
        r_order = r'(:order:(?P<order_id>\d+):)'
        r_fee = r'(?:\(-(?P<fee_percent>{0})%\))'.format(r_float)
        r_amount_pair = r'(?P<amount>{0})\s+(?P<base_currency>{1})'.format(r_float,
                                                                            r_currency_code)
        r_price_pair = r'(?P<price>{0})\s+(?P<counter_currency>{1})'.format(r_float,
                                                                            r_currency_code)
        r_buy = r'{0}\s+{1}.*?{2}.*?{3}'.format(r_amount_pair,
                                                r_fee,
                                                r_order,
                                                r_price_pair)
        r_sell = r'{0}.*?{2}.*?{3}.*?(?P<total>{4})\s+(?:{5})\s+{1}'.format(r_amount_pair,
                                                                            r_fee,
                                                                            r_order,
                                                                            r_price_pair,
                                                                            r_float,
                                                                            r_currency_code)
        self.re_buy = re.compile(r_buy)
        self.re_sell = re.compile(r_sell)

    def perform_request(self, method, data={}):
        try:
            return super(BTCE, self).perform_request(method, data)
        except APIException as e:
            if e.message == 'no orders':
                return {}
            else:
                raise e

    def get_my_trades(self):
        return self._parse_transaction_history(parse_transactions=False)[1]

    @staticmethod
    def _format_order(order_id, order):
        if order['type'] == 'buy':
            order_type = BuyOrder
        else:
            order_type = SellOrder

        base, counter = BTCE._pair_to_market(order['pair'])

        return order_type(
            order_id = order_id,
            base_currency = base.upper(),
            counter_currency = counter.upper(),
            datetime = BTCE._format_timestamp(order['timestamp_created']),
            amount = order['amount'],
            price = order['rate']
        )

    def get_my_open_orders(self):
        orders = self.perform_request('ActiveOrders')
        return [BTCE._format_order(o_id, o) for o_id, o in orders.iteritems()]

    def cancel_order(self, order_id):
        self.perform_request('CancelOrder', {'order_id': order_id})
        return None

    def get_markets(self):
        return [
            BTCE._pair_to_market(pair)
            for pair in self.public.get_info()['pairs']
        ]

    def _create_order(self, market, order_type, quantity, price):
        params = {
            'pair': BTCE._market_to_pair(market),
            'type': order_type,
            'amount': quantity,
            'rate': price
        }
        return self.perform_request('Trade', params)

    def buy(self, market, quantity, price):
        response = self._create_order(market, 'buy', quantity, price)
        return response['order_id']

    def sell(self, market, quantity, price):
        response = self._create_order(market, 'sell', quantity, price)
        return response['order_id']

    def _parse_transaction_history(self, parse_transactions=True, parse_trades=True):
        '''
        Parse the transaction history ("TransHistory" API method) for
        transactions and/or trades

        :param parse_transactions: parse transactions
        :param parse_trades: parse trades
        :rtype: tuple of lists (transactions, trades)
        '''


        '''
        BTC-e types:
            1: deposit
            2: withdrawal
            3: not existent?
            4: buy and sell
            5: buy and sell
        '''

        if parse_trades:
            trade_history = self.perform_request('TradeHistory', {'count': 9999999999999})

        def get_trade_id(t, m):
            '''
            Get the trade_id as it is not provided via TransHistory method
            '''
            trades = filter(lambda v: int(v[1]['timestamp']) == int(t.get('timestamp')) and \
                            int(v[1]['order_id']) == int(m.groupdict().get('order_id')),
                            trade_history.iteritems())

            if len(trades) == 1:
                return int(trades[0][0])
            elif len(trades) > 1:
                # still more than one possible trade_id
                # use the id of the trade with the "most equal" amount
                # as the amount from TradeHistory may be rounded
                best = [None, None]
                for tid, trade in trades:
                    lookin = m.groupdict().get('amount')
                    lookfor = str(trade['amount'])
                    if lookfor == lookin:
                        return tid

                    score = 0
                    # Iterate over amount to see how many digits match
                    for idx in range(len(lookin)):
                        try:
                            if lookin[idx] != lookfor[idx]:
                                score = idx
                                break
                        except IndexError:
                            score = idx - 1
                            break

                    if best[0] is None or score > best[0]:
                        # This amount mathes better than the last one
                        best[0] = score
                        best[1] = tid
                if best[1] is not None:
                    return best[1]

            raise ValueError('No trade_id found')

        transactions = []
        trades = []
        for tid, t in self.perform_request('TransHistory', {'count': 9999999999999}).iteritems():
            if parse_transactions and t['type'] in (1, 2):
                if t['type'] == 1:
                    # Assume no fees for deopsit
                    transactions.append(Deposit(tid,
                                                self._format_timestamp(t['timestamp']),
                                                t['currency'],
                                                t['amount'],
                                                '',
                                                0
                                        ))
                elif t['type'] == 2:
                    idx = t['desc'].find('address ')
                    if idx:
                        address = t['desc'][idx+8:]
                    else:
                        address = ''
                    # Withdraw fees are not provided by BTC-e API
                    transactions.append(Withdrawal(tid,
                                                self._format_timestamp(t['timestamp']),
                                                t['currency'],
                                                t['amount'],
                                                address
                                        ))
            elif parse_trades and t['type'] in (4, 5):
                m = self.re_buy.search(t['desc'])
                if m:
                    # This is a buy transaction
                    amount = Decimal(m.groupdict().get('amount'))
                    trades.append(Buy(
                                        trade_id = get_trade_id(t, m),
                                        base_currency = m.groupdict().get('base_currency'),
                                        counter_currency = m.groupdict().get('counter_currency'),
                                        datetime = self._format_timestamp(t['timestamp']),
                                        order_id = int(m.groupdict().get('order_id')),
                                        amount = amount,
                                        price = Decimal(m.groupdict().get('price')),
                                        fee = common.quantize(Decimal(m.groupdict().get('fee_percent')) * amount / 100),
                                        fee_currency = m.groupdict().get('base_currency'),
                                        )
                                    )
                    continue

                m = self.re_sell.search(t['desc'])
                if m:
                    # This is a sell transation
                    amount = Decimal(m.groupdict().get('amount'))
                    price = Decimal(m.groupdict().get('price'))
                    trades.append(Sell(
                                        trade_id = get_trade_id(t, m),
                                        base_currency = m.groupdict().get('base_currency'),
                                        counter_currency = m.groupdict().get('counter_currency'),
                                        datetime = self._format_timestamp(t['timestamp']),
                                        order_id = int(m.groupdict().get('order_id')),
                                        amount = amount,
                                        price = price,
                                        fee = common.quantize(Decimal(m.groupdict().get('fee_percent')) * (amount * price) / 100),
                                        fee_currency = m.groupdict().get('counter_currency'),
                                        )
                                    )
                    continue
        return (transactions, trades)

    def get_my_transactions(self, limit=None):
        '''
        :param limit: Not used because "TransHistory" method conrains and coints cancelations etc. as transaction
        '''
        return self._parse_transaction_history(parse_trades=False)[0]

    def get_my_funds(self):
        funds = {}
        for key, value in self.perform_request('getInfo')['funds'].iteritems():
            funds[key.upper()] = value
        return funds
