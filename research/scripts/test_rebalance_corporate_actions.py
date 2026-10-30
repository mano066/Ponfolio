import unittest
from rebalance_corporate_actions import dividend_amount


class DividendTermsTests(unittest.TestCase):
    def test_included_special_is_not_paid_twice(self):
        self.assertEqual(dividend_amount('Dividend-Rs.8.50 Per Share (Including Special Dividend Of Rs.2/- Per Share).'),8.5)

    def test_additional_special_is_added(self):
        self.assertEqual(dividend_amount('Final Dividend Re.0.75 Per Share And Special Dividend Rs.1.25 Per Share'),2.0)

    def test_missing_currency_prefix(self):
        self.assertEqual(dividend_amount('Annual General Meeting/Dividend - 0.40 Per Share'),.4)
        self.assertEqual(dividend_amount('Int Div-Rs.11/- Per Share'),11.)

    def test_unstated_amount_is_not_invented(self):
        self.assertIsNone(dividend_amount('Dividend subject to approval'))
        self.assertIsNone(dividend_amount('Bonus Debentures 1:1'))


if __name__=='__main__':
    unittest.main()
