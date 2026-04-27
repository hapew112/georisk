#!/bin/bash

# Create logs directory if it doesn't exist
mkdir -p ~/georisk/logs/

echo "  GeoRisk Paper Trading — Cron Setup"
echo "  ════════════════════════════════════"
echo "  Add the following to your crontab using: crontab -e"
echo ""
echo "  # Run paper_trader.py every weekday at 9:00 AM KST"
echo "  0 9 * * 1-5 cd ~/georisk/backtest && source ~/georisk/.georisk_env && source venv/bin/activate && python paper_trader.py >> ~/georisk/logs/paper_trade.log 2>&1"
echo ""
echo "  Log file: ~/georisk/logs/paper_trade.log"
echo "  Paper history: ~/georisk/paper_log.json"
echo "  ════════════════════════════════════"
