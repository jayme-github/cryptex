import cryptex.common as common

class Transaction(object):
    '''
    Transaction that is neither deopsit nor withdrawal
    Used for CryptsyPoint credit
    '''
    transaction_type = 0
    def __init__(self, transaction_id, datetime, currency, amount, address, fee=None):
        self.transaction_id = transaction_id
        self.datetime = datetime
        self.currency = currency
        self.amount = amount
        self.address = address
        self.fee = fee
    
    def type(self):
        return self.__class__.__name__

    def __str__(self):
        return '<%s transaction of %.8f %s>' % (self.type(),
                                                self.amount,
                                                self.currency)

    def netto_amount(self):
        '''
        Return the netto amount of this transaction
        '''
        raise NotImplemented

class Deposit(Transaction):
    transaction_type = 1

    def netto_amount(self):
        if self.fee:
            return common.quantize(self.amount - self.fee)
        return self.amount

class Withdrawal(Transaction):
    transaction_type = 2

    def netto_amount(self):
        if self.fee:
            return common.quantize(self.amount + self.fee)
        return self.amount
