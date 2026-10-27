#!/bin/bash
# Generate NeDBIT features for our diseases, for XGDAG to consume.
#
# This is step 1 of the XGDAG comparison. It needs only Perl and a C compiler -
# no GPU, no PyTorch, no conda environment. The heavy dependencies (PyTorch
# 1.12 / PyG 2.1) are only needed later, for XGDAG's GNN and explainer stages.
#
# XGDAG's CreateGraph.py reads node features rather than computing them, and
# the 10 DisGeNET diseases it ships with do not overlap our panels - so these
# have to be generated. The tool that does it is NIAPU, by the same authors.
#
# Prerequisites:
#   git clone https://github.com/AndMastro/NIAPU.git
#   python additional_experiments/other_prioritizers/xgdag/make_seed_files.py \
#       --ppi <NIAPU>/data/biogrid_gene_pairs_clean_Hs_4_4_206.txt
#
# Usage:
#   bash additional_experiments/other_prioritizers/xgdag/run_nedbit.sh /path/to/NIAPU
#   bash .../run_nedbit.sh /path/to/NIAPU dee cp      # subset

set -euo pipefail

NIAPU="${1:?usage: run_nedbit.sh /path/to/NIAPU [disease ...]}"
shift || true

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEEDS="$HERE/seeds"
OUT="$HERE/features"
WORK="$HERE/.nedbit_work"

PPI="$NIAPU/data/biogrid_gene_pairs_clean_Hs_4_4_206.txt"
SRC="$NIAPU/src"

for f in "$PPI" "$SRC/preprocess.pl" "$SRC/nedbit_features_calculator.c"; do
    [ -f "$f" ] || { echo "[Error] missing: $f"; exit 1; }
done
[ -d "$SEEDS" ] || { echo "[Error] no seed files. Run make_seed_files.py first."; exit 1; }

mkdir -p "$OUT" "$WORK"

CALC="$WORK/nedbit_calc"
if [ ! -x "$CALC" ]; then
    echo "[+] compiling nedbit_features_calculator"
    # -DUNIX is REQUIRED, not optional. The seeding block is
    #     #ifndef FIXEDSEED
    #     #ifdef UNIX   ... srand48 ...
    #     #else         ... __mingw_fprintf ...
    # so without it the compiler takes the Windows branch and the link fails
    # with "undefined reference to __mingw_fprintf".
    #
    # -DFIXEDSEED makes the features REPRODUCIBLE. The randomness is not
    # cosmetic: cutSeedGenes() uses it to discard a random fraction of the
    # seed genes, so with time(NULL) seeding a different subset is dropped on
    # every run and the features - hence XGDAG's whole ranking - change each
    # time. Defining it skips the seeding block, leaving drand48 in its
    # default state. The source already declares a fixed default seed, so
    # this is the intended switch.
    gcc -O2 -DUNIX -DFIXEDSEED -o "$CALC" \
        "$SRC/nedbit_features_calculator.c" -lm
fi

if [ "$#" -gt 0 ]; then
    DISEASES="$*"
else
    DISEASES=$(ls "$SEEDS"/*_seed_genes.txt | sed 's|.*/||; s|_seed_genes.txt||')
fi

for disease in $DISEASES; do
    seed="$SEEDS/${disease}_seed_genes.txt"
    [ -f "$seed" ] || { echo "[skip] no seed file for $disease"; continue; }

    echo "[+] $disease  ($(wc -l < "$seed") seeds)"
    # preprocess.pl writes its outputs into the working directory, so give each
    # disease its own to avoid one run clobbering another.
    d="$WORK/$disease"
    mkdir -p "$d"
    perl "$SRC/preprocess.pl" "$PPI" "$seed" "$d/out_links" "$d/out_genes"
    "$CALC" "$d/out_links" "$d/out_genes" "$OUT/${disease}_features"

    if [ -s "$OUT/${disease}_features" ]; then
        echo "    -> $(( $(wc -l < "$OUT/${disease}_features") - 1 )) genes, $(head -1 "$OUT/${disease}_features")"
    else
        echo "    [Error] no features produced for $disease"
    fi
done

echo
echo "Features in $OUT"
echo "Next: copy them into XGDAG as Datasets/<DISEASE>_features, alongside"
echo "      Datasets/<DISEASE>_seed_genes.txt, then run CreateGraph.py."
echo
echo "Before trusting any of it, reproduce one of XGDAG's own diseases"
echo "end to end (e.g. C0011581) and check against its shipped Rankings/."
