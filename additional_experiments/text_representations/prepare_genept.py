"""
Reduce the GenePT embedding table to the genes SPEOS can use.

GenePT (Chen & Zou) embeds each gene's NCBI Gene summary with OpenAI
text-embedding-ada-002: 1,536 dimensions for ~93,800 NCBI genes, 3 GB as CSV.
The KI-GNN arm only needs the 17,282 genes of the SPEOS universe, so this
streams the CSV once and keeps:

  - genes already named as SPEOS names them, and
  - genes whose current HGNC symbol has a previous/alias symbol that SPEOS
    uses, so align_to_speos_symbols.py can re-key them afterwards.

Everything else (non-coding RNAs, other species' names, unplaced loci) is
dropped here rather than in the aligner, because the aligner holds the whole
matrix in memory as text and would need ~9 GB for the full table.

Two properties of the GenePT file need care:
  - some gene names contain commas and are quoted, so the file must be read
    with a CSV parser, not split on commas;
  - the first column is the gene and the remaining 1,536 are the embedding;
    rows with any other width are reported and skipped, not padded.

The output has the same format as the other literature matrices (space-
separated, no header, gene first). Run align_to_speos_symbols.py on it next.

Note: GenePT summaries and ada-002 (Dec 2022) postdate the 2022-09 cutoff, so
this arm is a comparison of text sources, not a prospective result.

Usage:
    python additional_experiments/text_representations/prepare_genept.py
    python additional_experiments/text_representations/align_to_speos_symbols.py \
        --matrix additional_experiments/text_representations/genept_ada002_1536d.txt
"""

import argparse
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from align_to_speos_symbols import HGNC, REFERENCE, load_symbol_map  # noqa: E402

GENEPT = "/data/gpfs/projects/punim2353/chathura/data/genept_embeddings.csv"
DIMS = 1536

# GenePT values are floats; csv gives them back exactly as written, so they are
# passed through unchanged rather than re-formatted.
csv.field_size_limit(sys.maxsize)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--genept", default=GENEPT)
    parser.add_argument("--reference", default=REFERENCE,
                        help="file whose gene symbols define the SPEOS namespace")
    parser.add_argument("--hgnc", default=HGNC)
    parser.add_argument("-o", "--out",
                        default=os.path.join(HERE, "genept_ada002_1536d.txt"))
    args = parser.parse_args()

    reference = {line.split()[0] for line in open(args.reference) if line.strip()}
    keep = set(reference)
    for current, olds in load_symbol_map(args.hgnc).items():
        if olds & reference:
            keep.add(current)
    print("SPEOS namespace        : {} genes".format(len(reference)))
    print("symbols kept (incl. current names of renamed genes): {}".format(len(keep)))

    read = written = duplicates = bad_width = 0
    seen = set()
    with open(args.genept, newline="") as source, open(args.out, "w") as out:
        reader = csv.reader(source)
        header = next(reader)
        if len(header) != DIMS + 1:
            sys.exit("expected {} columns (gene + {} dims), header has {}".format(
                DIMS + 1, DIMS, len(header)))
        for row in reader:
            read += 1
            gene = row[0].strip()
            if gene not in keep:
                continue
            if len(row) != DIMS + 1:
                bad_width += 1
                continue
            if gene in seen:
                duplicates += 1
                continue
            seen.add(gene)
            out.write(gene + " " + " ".join(v.strip() for v in row[1:]) + "\n")
            written += 1

    print("GenePT rows read       : {}".format(read))
    print("rows written           : {}".format(written))
    print("  of which SPEOS names : {}".format(len(seen & reference)))
    print("duplicate genes skipped: {}".format(duplicates))
    print("wrong-width rows skipped (kept genes only): {}".format(bad_width))
    print("wrote {}".format(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
