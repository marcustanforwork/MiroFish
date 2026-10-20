"""
Export one finished simulation as JSON datasets for a results dashboard.

Usage (from backend/):
    uv run python scripts/export_simulation_results.py <simulation_id> --out <dir> \
        [--report-id <report_id>] [--label "Main run"]
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Config  # noqa: E402
from app.services.simulation_activity import SimulationActivityStore  # noqa: E402
from app.services.simulation_results_export import export_results  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("simulation_id")
    parser.add_argument("--out", required=True, help="folder to write the JSON files into")
    parser.add_argument("--report-id", help="include this report's title, summary and section leads")
    parser.add_argument("--label", default="", help="a name for the run, shown on the dashboard")
    args = parser.parse_args()

    store = SimulationActivityStore.for_simulation(args.simulation_id)
    if not store.agents:
        print(f"No simulation_config.json found for {args.simulation_id}", file=sys.stderr)
        return 1
    report_dir = os.path.join(Config.UPLOAD_FOLDER, "reports", args.report_id) if args.report_id else None
    for name in export_results(store, args.out, report_dir=report_dir, label=args.label):
        print(os.path.join(args.out, name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
