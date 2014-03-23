import datetime
import pytz

import cryptex.common as common
from cryptex.exchange import Exchange
from cryptex.trade import Sell, Buy
from cryptex.order import SellOrder, BuyOrder
from cryptex.transaction import Transaction, Deposit, Withdrawal
from cryptex.exchange.single_endpoint import SingleEndpoint, SignedSingleEndpoint
from cryptex.exception import APIException

class BTCEBase(object):
    @staticmethod
    def _format_timestamp(timestamp):
        return pytz.utc.localize(datetime.datetime.utcfromtimestamp(
            timestamp))

    @staticmethod
    def _pair_to_market(pair):
        '''
        Convert btc-e pair to cryptex market
        '''
        if isinstance(pair, (list, tuple)):
            # Looks like this is a market tuple
            return pair
        return tuple([c.upper() for c in pair.split('_')])

    @staticmethod
    def _market_to_pair(market):
        '''
        Convert btc-e pair to cryptex market
        '''
        if not isinstance(market, (list, tuple)):
            # Looks like this already is a pair
            return market
        return '_'.join((market[0].lower(), market[1].lower()))


class BTCEPublic(BTCEBase, SingleEndpoint):
    '''
    BTC-e public API https://btc-e.com/api/3/documentation
    All information is cached for 2 seconds on the server

    TODO: Add local caching to prevent frequent requests
    TODO: Format market pairs in output
    '''
    API_ENDPOINT = 'https://btc-e.com/api/3/'
    fee_cache = dict()

    def __init__(self):
        self._init_http_session()

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
        # FIXME: Needs merge of 16e33e261d9d5bd6b6dc5b23659e697ce6f213f5
        #j = self.perform_get_request('/'.join((method, '-'.join(markets))), params=params)
        #return {x: j[x] for x in j.keys() if x in markets}
        pair = BTCEPublic._market_to_pair(markets)
        j = self.perform_get_request('/'.join((method, pair)), params=params)
        return j[pair]

    def get_info(self):
        '''
        Information about currently active pairs,
        such as the maximum number of digits after the decimal point in the auction,
        the minimum price, maximum price, minimum quantity purchase / sale,
        hidden=1whether the pair and the pair commission.
        '''
        #FIXME: Needs parsing pair -> market
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

    def get_trade_fee(self, market, force_update=False):
        '''
        Return the fee associated with trades for a given market in percent

        FIXME: This really slows things up and would heavily profit from a persistent disc cache!
        '''
        if force_update or market not in self.fee_cache:
           self.fee_cache[market] = self._get_market_info('fee', market)
        return self.fee_cache[market]


class BTCE(BTCEBase, Exchange, SignedSingleEndpoint):
    API_ENDPOINT = 'https://btc-e.com/tapi'
    def __init__(self, key, secret):
        self._init_http_session()

        self.key = key
        self.secret = secret
        self.public = BTCEPublic()

    def perform_request(self, method, data={}):
        try:
            return super(BTCE, self).perform_request(method, data)
        except APIException as e:
            if e.message == 'no orders':
                return {}
            else:
                raise e

    def _calc_fee(self, amount, pair):
        '''
        Calculate the fees for a trade

        Calculating fees on server side only works via undocumentet ajax api
        and one needs to know the "pair id" (need to scrape it from webpage)
        curl 'https://btc-e.com/ajax/order' --data 'calculate=buy&btc_count=10&btc_price=0.02794&pair=10'
        '''
        fee_percent = self.public.get_trade_fee(pair)
        return common.quantize(fee_percent * amount / 100)

    def _format_trade(self, trade_id, trade):
        base, counter = BTCE._pair_to_market(trade['pair'])
        if trade['type'] == 'buy':
            trade_type = Buy
            fee_amount = self._calc_fee(trade['amount'], (base, counter))
            fee_currency = base
        else:
            trade_type = Sell
            fee_amount = self._calc_fee(trade['amount'] * trade['rate'], (base, counter))
            fee_currency = counter

        return trade_type(
            trade_id = trade_id,
            base_currency = base.upper(),
            counter_currency = counter.upper(),
            datetime = BTCE._format_timestamp(trade['timestamp']),
            order_id = trade['order_id'],
            amount = trade['amount'],
            price = trade['rate'],
            fee = fee_amount,
            fee_currency = fee_currency,
        )

    def get_my_trades(self, limit=None):
        trades = self.perform_request('TradeHistory')
        return [self._format_trade(t_id, t) for t_id, t in trades.iteritems()]

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

    def get_my_transactions(self, limit=1000):
        transactions = []
        for tid, t in self.perform_request('TransHistory', {'count': limit}).iteritems():
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
        return transactions

    def get_my_funds(self):
        funds = {}
        for key, value in self.perform_request('getInfo')['funds'].iteritems():
            funds[key.upper()] = value
        return funds

