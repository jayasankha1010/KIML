"""
Manifest for the Mantis/RF seed runs - the RF half of the main-table CIs.

Unlike the GNN arm, Mantis needs no generated config files: a per-disease YAML
and known-gene list already exist under external/Mantis. All a run needs is
which disease, which arm, and which seed, so the manifest is just one
<disease>:<arm>:<seed> triple per line and run_mantis.slurm resolves the rest.

Arms map to the --feature-mode flag added to mantis_ml:

    RF     core_only      Mantis's own features only
    C-RF   external_only  external (PubMed) features only
    KI-RF  combined       both

Ordering is disease-major so a single disease occupies a contiguous index
range and can be submitted on its own.

Usage:
    python additional_experiments/revision_runs/make_mantis_manifest.py --diseases dee --seeds 1
    python additional_experiments/revision_runs/make_mantis_manifest.py --seeds 5
"""

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
MANTIS = os.path.join(ROOT, "external", "Mantis")

# disease -> config/input stem under external/Mantis
STEMS = {
    "dee": "dee_2022",
    "ad_dee": "dee_2022_ad",
    "ar_dee": "dee_2022_ar",
    "microcephaly": "other_microcephaly",
    "intellectual_disability": "other_intellectual_disability",
    "mnd": "other_mnd",
    "cp": "other_cp",
    "platelet_disorder": "other_platelet_disorder",
    "arthrogryposis": "other_arthrogryposis",
}
ARMS = ["RF", "C-RF", "KI-RF"]


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--diseases", nargs="*", default=sorted(STEMS),
                        help="subset of {}".format(sorted(STEMS)))
    parser.add_argument("--arms", nargs="*", default=ARMS)
    parser.add_argument("--seeds", type=int, default=5)
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "mantis_manifest.txt"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--print-missing", action="store_true",
                        help="print ONLY a comma-separated list of array indices "
                             "whose output file does not yet exist, and exit. "
                             "Lets the whole thing be one command:\n"
                             "  sbatch --array=\"$(... --print-missing)%%6\" run_mantis.slurm\n"
                             "which avoids losing a shell variable between sessions.")
    args = parser.parse_args()

    missing = []
    lines = []
    for disease in args.diseases:
        stem = STEMS.get(disease)
        if stem is None:
            raise SystemExit("Unknown disease: {}".format(disease))
        # Fail here rather than three hours into a job array.
        for path in (os.path.join(MANTIS, "mantis_ml", "conf", stem + "_config.yaml"),
                     os.path.join(MANTIS, "Input_Files", stem + ".tsv")):
            if not os.path.exists(path):
                missing.append(path)
        for arm in args.arms:
            for seed in range(1, args.seeds + 1):
                lines.append("{}:{}:{}".format(disease, arm, seed))

    if missing:
        print("[Error] Missing Mantis inputs:")
        for path in missing:
            print("   {}".format(path))
        raise SystemExit(1)

    if args.print_missing:
        # Read the manifest already on disk rather than the freshly built list:
        # the indices must match what run_mantis.slurm will index into, and a
        # regenerated list could differ if --diseases/--arms/--seeds changed.
        if not os.path.exists(args.out):
            raise SystemExit("No manifest at {}; generate it first.".format(args.out))
        with open(args.out) as handle:
            existing = [l.strip() for l in handle if l.strip()]
        todo = []
        for index, line in enumerate(existing):
            disease, arm, seed = line.split(":")
            out = os.path.join(
                MANTIS, "Mantis_Out", "Mantis_{}_{}_s{}".format(disease, arm, seed),
                "Gene-Predictions", "RandomForestClassifier.mantis-ml_predictions.csv")
            if not os.path.exists(out):
                todo.append(str(index))
        if not todo:
            raise SystemExit("Nothing missing - all {} runs have output.".format(
                len(existing)))
        # stdout must carry the list and nothing else, for command substitution.
        print(",".join(todo))
        sys.stderr.write("{} of {} runs missing\n".format(len(todo), len(existing)))
        return

    if args.dry_run:
        for i, line in enumerate(lines):
            print("{:4d}  {}".format(i, line))
    else:
        with open(args.out, "w") as handle:
            handle.write("\n".join(lines) + "\n")

    print("\n{} runs ({} diseases x {} arms x {} seeds)".format(
        len(lines), len(args.diseases), len(args.arms), args.seeds))
    print("manifest -> {}".format(args.out))
    print("\nIndex ranges per disease:")
    start = 0
    for disease in args.diseases:
        n = len(args.arms) * args.seeds
        print("  {:26} {}-{}".format(disease, start, start + n - 1))
        start += n
    print("\nTime ONE run before submitting the rest:")
    print("  sbatch --account=punim2353 --array=0 \\")
    print("      additional_experiments/revision_runs/run_mantis.slurm")


if __name__ == "__main__":
    main()
