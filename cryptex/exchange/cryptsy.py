import datetime
from decimal import Decimal, InvalidOperation
import pytz

import cryptex.common as common
from cryptex.exception import CryptsyException
from cryptex.exchange import Exchange
from cryptex.trade import Sell, Buy
from cryptex.order import SellOrder, BuyOrder
from cryptex.transaction import Transaction, Deposit, Withdrawal
from cryptex.exchange.single_endpoint import SingleEndpoint, SignedSingleEndpoint


class CryptsyBase(object):
    def __init__(self):
        '''
        Can't get servertimezone via public API so hardcode to EST
        '''
        self.timezone = pytz.timezone(u'EST')

    def _get_info(self):
        raise NotImplementedError

    def _get_timezone(self):
        """
        Cryptsy seems to return all its timestamps in Eastern Standard Time,
        instead of doing the sane thing and returning UTC. But, the API does
        not make this a guarantee, so we do a request for getinfo and get the
        timezone then. We'll cache it, too.
        """
        if self.timezone is None:
            self.timezone = pytz.timezone(self._get_info()['servertimezone'])

        return self.timezone

    def _convert_datetime(self, time_str):
        """
        Convert cryptsy datetime to timezone-aware datetime object in UTC
        """
        naive_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        cryptsy_time = self._get_timezone()
        aware_time = cryptsy_time.normalize(cryptsy_time.localize(naive_time)).astimezone(pytz.utc)
        return aware_time

class CryptsyPublic(CryptsyBase, SingleEndpoint):
    API_ENDPOINT = 'http://pubapi.cryptsy.com/api.php'

    def perform_get_request(self, method='', params={}):
        return super(CryptsyPublic, self).perform_get_request(method, params)

    def get_market_data(self, market_id=None):
        '''
        General Market Data
        '''
        if market_id:
            params = {'method': 'singlemarketdata',
                    'marketid': market_id}
        else:
            params = {'method': 'marketdatav2'}

        market_data = {}
        for key, market in self.perform_get_request(params=params)['markets'].iteritems():
            market['lasttradetime'] = self._convert_datetime(market['lasttradetime'])
            for trade in market['recenttrades']:
                trade['time'] = self._convert_datetime(trade['time'])
            market_data[key] = market
        return market_data


    def get_order_data(self, market_id=None):
        '''
        General Orderbook Data
        '''
        if market_id:
            params = {'method': 'singleorderdata',
                    'marketid': market_id}
        else:
            params = {'method': 'orderdata'}
        return self.perform_get_request(params=params)


class Cryptsy(CryptsyBase, Exchange, SignedSingleEndpoint):
    API_ENDPOINT = 'https://api.cryptsy.com/api'
    def __init__(self, key, secret):
        self.key = key
        self.secret = secret
        self.market_currency_map = None
        self.timezone = None

    def perform_request(self, method, data={}):
        return super(Cryptsy, self).perform_request(method, data)

    def _convert_datetime(self, time_str):
        """
        Convert cryptsy timestamp to timezone-aware datetime object in UTC
        """
        naive_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        cryptsy_time = self._get_timezone()
        aware_time = cryptsy_time.normalize(cryptsy_time.localize(naive_time)).astimezone(pytz.utc)
        return aware_time

    def _get_market_currency_map(self):
        if self.market_currency_map is None:
            markets = self.perform_request('getmarkets')
            self.market_currency_map = {
                m['marketid']:
                (m['primary_currency_code'], m['secondary_currency_code'])
                for m in markets
            }
        return self.market_currency_map

    def _get_currencies(self, market_id):
        """
        Cryptsy uses references to market_ids which uniquely identify markets.
        Given a market_id, this function returns a two-tuple containing the currencies involved.
        """
        market_id = self._get_market_id(market_id)
        return self._get_market_currency_map()[market_id]

    def _get_market_id(self, pair):
        if pair in self._get_market_currency_map():
            # looks like this already is a market_id
            return pair
        market = filter(lambda m: m[1] == pair, self._get_market_currency_map().iteritems())
        if not market:
            raise CryptsyException('Market not found')
        return market[0][0]

    def _get_info(self):
        return self.perform_request('getinfo')

    def get_markets(self):
        return [m[1] for m in self._get_market_currency_map().iteritems()]

    def _format_trade(self, trade):
        if trade['tradetype'] == 'Buy':
            trade_type = Buy
        else:
            trade_type = Sell

        base, counter = self._get_currencies(trade['marketid'])

        return trade_type(
            trade_id = trade['tradeid'],
            base_currency = base,
            counter_currency = counter,
            datetime = self._convert_datetime(trade['datetime']),
            order_id = trade['order_id'],
            amount = Decimal(trade['quantity']),
            price = Decimal(trade['tradeprice']),
            fee = Decimal(trade['fee']),
            # Cryptsy's fee is always taken from counter_currency
            fee_currency = counter,
        )

    def get_my_trades(self, limit=200, market=None):
        params = {'limit': limit}
        if market is None:
            trades = self.perform_request('allmytrades', params)
        else:
            params['marketid'] = self._get_market_id(market)
            trades = self.perform_request('mytrades', params)
            for index, trade in enumerate(trades):
                trade['marketid'] = params['marketid']
                trades[index] = trade
        return [self._format_trade(t) for t in trades]

    def _format_order(self, order):
        if order['ordertype'] == 'Buy':
            order_type = BuyOrder
        else:
            order_type = SellOrder

        base, counter = self._get_currencies(order['marketid'])

        return order_type(
            order_id = order['orderid'],
            order_type = order_type,
            base_currency = base,
            counter_currency = counter,
            datetime = self._convert_datetime(order['created']),
            amount = Decimal(order['quantity']),
            price = Decimal(order['price'])
        )

    def get_my_open_orders(self, market=None):
        if market:
            market_id = self._get_market_id(market)
            orders = self.perform_request('myorders', {'marketid': market_id})
            # response does not contain market_id
            for index, order in enumerate(orders):
                order[u'marketid'] = market_id
                orders[index] = order
        else:
            orders = self.perform_request('allmyorders')
        return [self._format_order(o) for o in orders]

    def get_market_orders(self, market):
        market_id = self._get_market_id(market)
        return self.perform_request('marketorders', {'marketid': market_id})

    def get_market_trades(self, market):
        market_id = self._get_market_id(market)
        trades = self.perform_request('markettrades', {'marketid': market_id})
        for index, trade in enumerate(trades):
            trade['datetime'] = self._convert_datetime(trade['datetime'])
            trades[index] = trade
        return trades

    def cancel_order(self, order_id):
        self.perform_request('cancelorder', {'orderid': order_id})
        return None

    def _create_order(self, market_id, order_type, quantity, price):
        params = {
            'marketid': market_id,
            'ordertype': order_type,
            'quantity': quantity,
            'price': price
        }
        return self.perform_request('createorder', params)

    def buy(self, market, quantity, price):
        market_id = self._get_market_id(market)
        response = self._create_order(market_id, 'Buy', quantity, price)
        return response['orderid']

    def sell(self, market, quantity, price):
        market_id = self._get_market_id(market)
        response = self._create_order(market_id, 'Sell', quantity, price)
        return response['orderid']

    def get_my_transactions(self, limit=None):
        transactions = []
        for t in self.perform_request('mytransactions'):
            tx_type = None
            if t['type'] == 'Withdrawal':
                tx_type = Withdrawal
            elif t['type'] == 'Deposit':
                if t['currency'] == 'Points':
                    # CryptyPoints ar'nt real deposits, so handle them as "unknown" transaction
                    tx_type = Transaction
                else:
                    tx_type = Deposit
            if tx_type:
                transactions.append(tx_type(t['trxid'],
                                            self._convert_datetime(t['datetime']),
                                            t['currency'],
                                            Decimal(t['amount']),
                                            t['address'],
                                            Decimal(t['fee']),
                                    ))
        transactions.extend(self._get_my_transfers())
        return transactions

    def get_my_funds(self):
        funds = self._get_info()['balances_available']
        for key, value in funds:
            funds[key] = Decimal(value)
        return funds

    def _get_my_transfers(self):
        '''
        Get Cryptsy's internal transactions/transfers and treat them as Deposit/Withdrawal
        TODO: May have an undocumented limit too
        '''

        # generate a "unique" hash used as hash as transaction_id
        generate_transaction_id =  lambda t: hash(frozenset(t.items()))

        transfers = []
        for t in self.perform_request('mytransfers'):
            if t['processed'] != 1:
                # Not processed yet, skipp
                continue
            t_type = Transaction
            if t['direction'] == 'in':
                t_type = Deposit
            elif t['direction'] == 'out':
                t_type = Withdrawal

            transfers.append(t_type(generate_transaction_id(t),
                                    self._convert_datetime(t['processed_timestamp']),
                                    t['currency'],
                                    Decimal(t['quantity']),
                                    t['to']))
        return transfers
