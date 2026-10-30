import unittest
from swing_trading import validate_recommendation, determine_fill


class EntryGuards(unittest.TestCase):
    def validate(self, **updates):
        values = dict(entry=100., buy_zone_low=98., buy_zone_high=104.,
                      stop_loss=95., target=120., current_price=100.,
                      max_entry_price=102., require_target=True)
        values.update(updates)
        return validate_recommendation(**values)[0]

    def test_maximum_entry_applies_inside_zone(self):
        self.assertEqual(self.validate(current_price=103.), 'MISSED_ENTRY')

    def test_broken_stop_is_invalid_not_wait(self):
        self.assertEqual(self.validate(current_price=94.), 'INVALID')

    def test_live_reward_risk_not_old_entry(self):
        self.assertEqual(self.validate(target=110., current_price=102.,
                                       min_reward_risk_ratio=2.), 'WAIT_FOR_ENTRY')

    def test_nonfinite_levels_rejected(self):
        for field in ('entry', 'stop_loss', 'current_price', 'buy_zone_low', 'buy_zone_high'):
            for value in (float('nan'), float('inf')):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.validate(**{field: value}), 'INVALID')

    def test_slippage_cannot_exceed_cap(self):
        result = determine_fill(buy_zone_low=98., buy_zone_high=102.,
                                max_entry_price=101., observed_price=101.)
        self.assertFalse(result['filled'])

    def test_normal_entry_still_fills(self):
        result = determine_fill(buy_zone_low=98., buy_zone_high=102.,
                                max_entry_price=102., observed_price=100.)
        self.assertTrue(result['filled'])
        self.assertEqual(result['fill_price'], 100.05)


if __name__ == '__main__':
    unittest.main()
