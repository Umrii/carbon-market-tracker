"""
Pipeline runner.
Run directly to do a one-shot ingest, or keep running for scheduled daily updates.

Usage:
    python -m pipeline.runner          # one-shot ingest
    python -m pipeline.runner --schedule  # run continuously with daily refresh
"""

import argparse
import logging
import sys
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler

from pipeline.analytics import detect_alerts
from pipeline.database import get_alerts_df, get_prices_df, init_db, save_alert, upsert_prices
from pipeline.fetcher import fetch_eua_prices

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def run_pipeline():
    """Full pipeline: fetch → store → compute alerts."""
    logger.info("=" * 50)
    logger.info("Carbon Market Pipeline - Starting run")
    logger.info(f"Timestamp: {datetime.utcnow().isoformat()}")

    # 1. Fetch
    df = fetch_eua_prices(days=500)
    if df.empty:
        logger.error("No data fetched. Aborting.")
        return

    logger.info(f"Fetched {len(df)} days of EUA price data.")
    logger.info(f"Date range: {df['date'].min()} → {df['date'].max()}")
    logger.info(f"Latest close: €{df['close'].iloc[-1]:.2f}/t")

    # 2. Store
    inserted = upsert_prices(df)
    logger.info(f"Inserted {inserted} new records into DB.")

    # 3. Detect alerts on full stored history
    full_df = get_prices_df()
    alerts = detect_alerts(full_df)
    new_alerts = 0
    for alert in alerts:
        save_alert(
            alert_date=alert["date"],
            alert_type=alert["type"],
            message=alert["message"],
            price=alert["price"],
            change_pct=alert["change_pct"],
        )
        new_alerts += 1

    logger.info(f"Alert check complete. {new_alerts} total alert records processed.")
    logger.info("Pipeline run complete.")
    logger.info("=" * 50)


def main():
    parser = argparse.ArgumentParser(description="Carbon Market Data Pipeline")
    parser.add_argument(
        "--schedule",
        action="store_true",
        help="Run continuously with daily refresh at 18:00 UTC (after EU market close)",
    )
    args = parser.parse_args()

    # Initialise DB
    init_db()

    # Always run once immediately
    run_pipeline()

    if args.schedule:
        logger.info("Scheduler mode: will re-run daily at 18:00 UTC.")
        scheduler = BlockingScheduler(timezone="UTC")
        scheduler.add_job(run_pipeline, "cron", hour=18, minute=0)
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
