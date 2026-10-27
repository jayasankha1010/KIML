#!/bin/bash
# Switch XGDAG's ranking script from the DIAMOnD variant to the standard one.
#
# WHY. ComputeRankingScript.py is hardcoded to the DIAMOnD variant:
#
#     model_name = 'GraphSAGE_' + disease_Id + '_diamond'
#     graph_path = PATH_TO_GRAPHS + 'grafo_diamond_nedbit_' + disease_Id + '.gml'
#     ... get_dataset_from_graph(..., from_diamond=True)
#
# but that path cannot run as shipped, because the code and the data disagree
# about filenames. CreateDatasetv2.get_dataset_from_graph builds
#
#     Datasets/Diamond_dataset/<id>_seed_genes.txt
#     Datasets/Diamond_dataset/<id>_ranking
#
# while the repository actually contains
#
#     Datasets/Diamond_dataset/<id>_seed_genes_scores_diamond.txt
#     Datasets/Diamond_dataset/<id>_diamond_ranking
#
# giving FileNotFoundError on the first read.
#
# The STANDARD variant is complete and consistent - Datasets/<id>_seed_genes.txt,
# <id>_ranking, <id>_features, Graphs/grafo_nedbit_<id>.gml and
# Models/GraphSAGE_<id>_40000_0_0005 all exist. It is also the variant we need:
# DIAMOnD-derived seeds are a different experiment, whereas we supply our own
# PanelApp seeds directly, which is exactly what the standard path expects.
#
# Idempotent, and keeps a .orig backup.
#
# Usage:
#   bash patch_xgdag.sh                      # default XGDAG location
#   XGDAG_DIR=/path/to/XGDAG bash patch_xgdag.sh
#   bash patch_xgdag.sh --revert

set -euo pipefail

XGDAG_DIR="${XGDAG_DIR:-/data/gpfs/projects/punim2353/chathura/tools/XGDAG}"
TARGET="$XGDAG_DIR/ComputeRankingScript.py"

[ -f "$TARGET" ] || { echo "[Error] not found: $TARGET"; exit 1; }

if [ "${1:-}" = "--revert" ]; then
    if [ -f "$TARGET.orig" ]; then
        mv "$TARGET.orig" "$TARGET"
        echo "[+] reverted $TARGET"
    else
        echo "[=] no backup to revert"
    fi
    exit 0
fi

if grep -q "KIML: switched to the standard" "$TARGET"; then
    echo "[=] already patched"
    exit 0
fi

cp "$TARGET" "$TARGET.orig"

python3 - "$TARGET" <<'PATCH'
import sys
path = sys.argv[1]
src = open(path).read()

note = ("    # KIML: switched to the standard variant. The DIAMOnD paths are\n"
        "    # hardcoded below in the original, but the shipped Diamond_dataset\n"
        "    # files are named <id>_seed_genes_scores_diamond.txt and\n"
        "    # <id>_diamond_ranking, while CreateDatasetv2 reads\n"
        "    # <id>_seed_genes.txt and <id>_ranking - so that path raises\n"
        "    # FileNotFoundError. The standard variant is complete and is what\n"
        "    # our own PanelApp seed files fit.\n")

subs = [
    ("    model_name  = 'GraphSAGE_' + disease_Id + '_diamond'",
     note + "    model_name  = 'GraphSAGE_' + disease_Id"),
    ("    graph_path  = PATH_TO_GRAPHS + 'grafo_diamond_nedbit_' + disease_Id + '.gml'",
     "    graph_path  = PATH_TO_GRAPHS + 'grafo_nedbit_' + disease_Id + '.gml'"),
    ("get_dataset_from_graph(graph_path, disease_Id, quartile=False, from_diamond=True)",
     "get_dataset_from_graph(graph_path, disease_Id, quartile=False, from_diamond=False)"),
    # The output filename hardcodes '_diamond_' regardless of which variant
    # actually ran, so our standard-variant output would be written over the
    # shipped Rankings/<id>_all_positives_diamond_xgdag_<method>.txt - one of
    # the authors' published reference files, and the thing we need to compare
    # against. Write somewhere unambiguous instead: nothing is clobbered, and
    # the name says whose run it is.
    ("    filename = PATH_TO_RANKINGS + disease_Id + '_all_positives_diamond_'",
     "    filename = PATH_TO_RANKINGS + disease_Id + '_kiml_'"),
]

missing = [old for old, _ in subs if old not in src]
if missing:
    print("[Error] expected lines not found - the script may have changed:")
    for m in missing:
        print("   " + m.strip())
    sys.exit(1)

for old, new in subs:
    src = src.replace(old, new, 1)

open(path, "w").write(src)
print("[+] patched " + path)
PATCH

echo
echo "Changed:"
echo "  model   GraphSAGE_<id>_diamond                 -> GraphSAGE_<id>"
echo "  graph   grafo_diamond_nedbit_<id>.gml          -> grafo_nedbit_<id>.gml"
echo "  data    from_diamond=True                      -> False"
echo "  output  Rankings/<id>_all_positives_diamond_*  -> Rankings/<id>_kiml_*"
echo
echo "Our runs now write Rankings/<id>_kiml_xgdag_<method>.txt, so the shipped"
echo "reference files are left intact for comparison."
echo
echo "Backup at $TARGET.orig  (bash patch_xgdag.sh --revert to undo)"
