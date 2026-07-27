import argparse
import sys

from .run import run_pipeline

parser = argparse.ArgumentParser(description="Run the feed pipeline once")
parser.add_argument("--trigger", choices=["scheduled", "manual"], default="scheduled")
parser.add_argument("--run-id", type=int, default=None,
                    help="existing pipeline_runs row to attach to (used by the API server)")
args = parser.parse_args()

sys.exit(run_pipeline(trigger=args.trigger, run_id=args.run_id))
