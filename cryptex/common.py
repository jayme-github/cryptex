import decimal

DECIMAL_PRECISION = decimal.Decimal(10) ** -8

def quantize(decimal_value):
	return decimal_value.quantize(DECIMAL_PRECISION)
