import unittest
from datetime import date
import rebalance_engine as re

class RebalanceUserPolicyTests(unittest.TestCase):
    def positions(self):
        return [{'key': 'ITC', 'name': 'ITC', 'value': 200000, 'price': 100, 'units': 2000, 'lots': re.synthetic_lot(2000, 80, date(2026,9,11), '2026-06-01', equity=True)}] + [{'key': str(i), 'value': 80000, 'price': 100, 'units': 800, 'lots': []} for i in range(10)]
    def test_twenty_percent_exception(self):
        plan = re.plan_sleeve(self.positions(), as_of=date(2026,9,11), sleeve='stocks', asset_limits={'ITC':20})
        self.assertEqual(plan['actions'][0]['action'], 'HOLD')
    def test_short_term_waits(self):
        plan = re.plan_sleeve(self.positions(), as_of=date(2026,9,11), sleeve='stocks', long_term_only=True)
        self.assertEqual(plan['actions'][0]['action'], 'WAIT')
        self.assertEqual(plan['actions'][0]['amount'], 0)
    def test_short_term_opt_in_prices_tax(self):
        plan = re.plan_sleeve(self.positions(), as_of=date(2026,9,11), sleeve='stocks', long_term_only=False)
        self.assertEqual(plan['actions'][0]['action'], 'TRIM')
        self.assertGreater(plan['actions'][0]['tax'], 0)
    def test_metals_stay_in_funds(self):
        funds=[{'scheme_name':name,'category':'Mutual Fund','units':100,'nav':100,'current_value':10000} for name in ['Gold Fund','Silver Fund','Equity Fund']]
        plan=re.build_plan(funds=funds)
        self.assertEqual(plan['sleeves'][re.CAT_FUNDS]['total_value'],30000)
        self.assertAlmostEqual(sum(a['weight_pct'] for a in plan['actions']),100,places=1)
        self.assertFalse(plan['actions'][0]['equity_for_tax'])
    def test_funding_uses_net_sales(self):
        notes=re.funding_notes([{'selected':True,'action':'TRIM','name':'ITC','amount':16000,'tax':1000,'net_proceeds':15000},{'selected':True,'action':'ADD','name':'Fund','amount':20000}], {'available':True}, {}, {})
        self.assertIn('15000 from net trims, 5000 additional',notes[2]['body'])

    def test_custom_tax_rate_reaches_sale(self):
        plan = re.plan_sleeve(self.positions(), as_of=date(2026,9,11), sleeve='stocks', tax_rates={'equity_short_term':10})
        self.assertAlmostEqual(plan['actions'][0]['tax'],2080)

    def test_gold_etf_joins_funds(self):
        plan=re.build_plan(stocks=[{'symbol':'GOLDBEES.NS','name':'Gold ETF','shares':100,'current_price':100,'avg_cost':80,'total_value':10000}])
        self.assertEqual(plan['actions'][0]['category'],re.CAT_FUNDS)
        self.assertFalse(plan['actions'][0]['equity_for_tax'])
