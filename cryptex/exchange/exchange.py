class Exchange(object):
    def get_markets(self):
        """
        Returns a list of tuples of the form ('XXX', 'YYY') representing the 
        available markets on the exchange, where XXX and YYY are the currency 
        codes for the base currency and counter currency, respectively.
        """
        raise NotImplementedError

    def get_my_open_orders(self):
        """
        Returns a list of exchanges.order.Order that represent currently 
        unfulfilled trade orders.
        """
        raise NotImplementedError

    def get_my_trades(self, limit=None):
        """
        Returns a list of exchanges.trade.Trade that represent all the user's 
        trades.
        """
        raise NotImplementedError

    def cancel_order(self, order_id):
        """
        Given an order_id, cancels the order associeted with the id. Returns 
        None.
        """
        raise NotImplementedError
    
    def buy(self, market, quantity, price):
        raise NotImplementedError

    def sell(self, market, quantity, price):
        raise NotImplementedError

    def get_my_transactions(self, limit=None):
        raise NotImplementedError

    def get_my_funds(self):
        """
        Returns a dict that represent all the user's funds (not on orders) as {'CURRENCY': Decimal(<Value>), ...}.
        """
        raise NotImplementedError
