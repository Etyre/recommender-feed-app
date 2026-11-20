import argparse
import sys

from .run import run_pipeline

parser = argparse.ArgumentParser(description="Run the feed pipeline once")
parser.add_argument("--trigger", choices=["scheduled", "manual"], default="scheduled")
parser.add_argument("--run-id", type=int, default=None,
                    help="existing pipeline_runs row to attach to (used by the API server)")
args = parser.parse_args()

# Exit 3 when the run started and chose to stop (another run holds the lock, or no network).
# The launchd job retries on any other non-zero exit, which means Python itself failed to start.
sys.exit(3 if run_pipeline(trigger=args.trigger, run_id=args.run_id) else 0)
