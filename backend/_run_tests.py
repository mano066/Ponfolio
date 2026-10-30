import sys, os, unittest
from pathlib import Path
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))
os.chdir(_HERE)
mods = sys.argv[1:] or ["test_backtest_engine", "test_market_indices",
                        "test_stock_dip", "test_mf_dip", "test_opportunities",
                        "test_deploy_engine",
                        "test_deploy_endpoint", "test_write_helpers",
                        "test_price_source", "test_tradebook_import",
                        "test_rebalance_engine", "test_rebalance_endpoint",
                        "test_dashboard_connection", "test_kite_session",
                        "test_rebalance_categories", "test_research_sync",
                        "test_drive_sync", "test_dip_method_v2",
                        "test_conviction", "test_yf_cache_heal"]
suite = unittest.TestLoader().loadTestsFromNames(mods)
sys.exit(0 if unittest.TextTestRunner(verbosity=1).run(suite).wasSuccessful() else 1)
