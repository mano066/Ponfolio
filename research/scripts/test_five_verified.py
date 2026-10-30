import unittest
from datetime import date,timedelta
from backtest_five_verified import Book,irr

class LedgerTests(unittest.TestCase):
 def book(self):
  b=Book(None,1);b.cash=100000;b.buy('ONGC',100000,1292.8,date(2011,1,3),'test');return b
 def test_combined_split_bonus_preserves_basis_and_fourfold_units(self):
  b=self.book();q=b.qty('ONGC');basis=b.basis('ONGC');cash=b.cash
  b.event(date(2011,2,8),'ONGC','combined',4,None)
  self.assertEqual(b.qty('ONGC'),q*4);self.assertAlmostEqual(b.basis('ONGC'),basis);self.assertEqual(b.cash,cash)
 def test_bonus_aggregate_rounding_and_new_maturity(self):
  b=Book(None,1);b.cash=1000
  b.buy('ITC',100,10,date(2011,1,3),'test');b.buy('ITC',100,10,date(2011,1,3),'test')
  b.event(date(2016,7,1),'ITC','bonus',.5,None)
  self.assertEqual(b.qty('ITC'),27)
  b.sell('ITC',27,10,date(2016,7,2),'test')
  self.assertEqual(b.qty('ITC'),9)
 def test_rights_do_not_create_free_shares(self):
  b=self.book();q=b.qty('ONGC');cash=b.cash
  b.event(date(2011,2,25),'ONGC','rights',.4,85)
  self.assertEqual(b.qty('ONGC'),q);self.assertEqual(b.cash,cash)
 def test_demerger_retains_parent_and_allocates_basis(self):
  b=self.book();q=b.qty('ONGC');basis=b.basis('ONGC')
  b.event(date(2023,3,31),'ONGC','demerger',1,('CHILD',.4032))
  self.assertEqual(b.qty('CHILD'),q);self.assertEqual(b.qty('ONGC'),q)
  self.assertAlmostEqual(b.basis('ONGC')+b.basis('CHILD'),basis)
 def test_budget_and_365_day_lock(self):
  b=self.book();q=b.qty('ONGC');self.assertGreaterEqual(b.cash,0)
  b.sell('ONGC',q,1500,date(2011,1,3)+timedelta(days=365),'test');self.assertEqual(b.qty('ONGC'),q)
  b.sell('ONGC',q,1500,date(2011,1,3)+timedelta(days=366),'test');self.assertEqual(b.qty('ONGC'),0)
 def test_known_xirr(self):
  self.assertAlmostEqual(irr([(date(2021,1,1),-100),(date(2022,1,1),110)]),10)

if __name__=='__main__':unittest.main()
