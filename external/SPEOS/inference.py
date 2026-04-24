from speos.pipeline import InferencePipeline
import argparse

parser = argparse.ArgumentParser(description='Run Inference Pipeline.')

parser.add_argument('--config', "-c", type=str, default="",
                    help='Path to the config that should be used for the run.')

args = parser.parse_args()

pipeline = InferencePipeline(args.config)

pipeline.run()
