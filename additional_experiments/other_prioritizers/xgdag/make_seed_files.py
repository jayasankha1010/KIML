"""
Seed-gene files for NIAPU/XGDAG, in the BioGRID symbol namespace.

NIAPU's preprocess.pl wants "<gene> <score>" per line. Two wrinkles:

SCORES. XGDAG's shipped files carry DisGeNET gene-disease association scores
(e.g. "NAT1 0.31"). PanelApp green genes have no continuous equivalent, so
every seed gets 1.0. This is a real deviation from how the method was
published - NeDBIT deliberately weights seeds unequally - and has to be stated
when the comparison is reported, not buried.

SYMBOLS. NIAPU ships BioGRID 4.4.206, which predates a batch of HGNC renames.
Matching our panels naively loses ~4% of DEE seeds and ~9% of targets purely
to nomenclature: AARS1 was AARS, ATP5F1A was ATP5A1, ADGRL1 was LPHN1. Those
genes are in the network under their old names, so they are recoverable rather
than absent, and dropping them would shrink the evaluation for no good reason.
This maps current -> previous/alias symbols using the same HGNC table as
text_representations/align_to_speos_symbols.py.

Also writes the post-split target list in the same namespace, so the scoring
step compares like with like.

Usage:
    python additional_experiments/other_prioritizers/xgdag/make_seed_files.py \
        --ppi /path/to/NIAPU/data/biogrid_gene_pairs_clean_Hs_4_4_206.txt
"""

import argparse
import csv
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
DISEASES_DIR = os.path.join(ROOT, "data", "kiml_data", "diseases")
HGNC = os.path.join(ROOT, "external", "SPEOS", "hgnc", "hgnc_official_list.tsv")

# disease -> (2022-09 seed panel, post-split target list)
DISEASES = {
    "dee": ("DEE-2022_09.txt", "DEE-2025_03_vs_2022_09.txt"),
    "ad_dee": ("AD_DEE-2022_09.txt", "AD_DEE-2022_09_to_2025_03.txt"),
    "ar_dee": ("AR_DEE-2022_09.txt", "AR_DEE-2022_09_to_2025_03.txt"),
    "microcephaly": ("Microcephaly-2022-09.txt",
                     "Microcephaly-2025_06_vs_2022_09.txt"),
    "intellectual_disability": ("Intellectual-disability-2022-09.txt",
                                "Intellectual-disability-2025_06_vs_2022_09.txt"),
    "mnd": ("MND-2022-09.txt", "MND-2025_06_vs_2022_09.txt"),
    "cp": ("CP-2022-09.txt", "CP-2025_06_vs_2022_09.txt"),
    "platelet_disorder": ("Bleeding_and_Platelet_Disorders-2022-09.txt",
                          "Bleeding_and_Platelet_Disorders-2026-02_vs_2022-09.txt"),
    "arthrogryposis": ("Arthrogryposis-2022-09.txt",
                       "Arthrogryposis-2025_06_vs_2022_09.txt"),
}


def read_genes(path):
    with open(path) as handle:
        return [line.strip() for line in handle if line.strip()]


def load_aliases(path):
    """current symbol -> [previous/alias symbols]."""
    mapping = {}
    if not os.path.exists(path):
        return mapping
    with open(path) as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            current = (row.get("symbol") or "").strip()
            if not current:
                continue
            olds = []
            for field in ("prev_symbol", "alias_symbol"):
                raw = (row.get(field) or "").replace('"', "")
                olds.extend(s.strip() for s in raw.split("|") if s.strip())
            if olds:
                mapping[current] = olds
    return mapping


def resolve(genes, universe, aliases):
    """Map each gene into `universe`, via an alias if the direct name is absent."""
    resolved, renamed, missing = [], [], []
    seen = set()
    for gene in genes:
        name = None
        if gene in universe:
            name = gene
        else:
            for old in aliases.get(gene, []):
                if old in universe:
                    name = old
                    renamed.append((gene, old))
                    break
        if name is None:
            missing.append(gene)
        elif name not in seen:
            seen.add(name)
            resolved.append(name)
    return resolved, renamed, missing


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ppi", required=True,
                        help="NIAPU's biogrid_gene_pairs_clean_Hs_4_4_206.txt")
    parser.add_argument("--diseases", nargs="*", default=sorted(DISEASES))
    parser.add_argument("--score", default="1.0",
                        help="uniform seed score (default 1.0)")
    parser.add_argument("-o", "--out-dir", default=os.path.join(HERE, "seeds"))
    args = parser.parse_args()

    universe = set()
    with open(args.ppi) as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 2:
                universe.update(parts[:2])
    print("BioGRID universe: {} genes".format(len(universe)))

    aliases = load_aliases(HGNC)
    if not aliases:
        print("[warn] no HGNC table at {} - skipping alias recovery".format(HGNC))

    os.makedirs(args.out_dir, exist_ok=True)
    print("\n{:26}{:>8}{:>9}{:>9}{:>9}   {}".format(
        "disease", "seeds", "matched", "renamed", "lost", "targets matched"))
    print("-" * 86)

    for disease in args.diseases:
        seed_file, target_file = DISEASES[disease]
        seeds = read_genes(os.path.join(DISEASES_DIR, seed_file))
        targets = read_genes(os.path.join(DISEASES_DIR, target_file))

        s_ok, s_ren, s_miss = resolve(seeds, universe, aliases)
        t_ok, t_ren, t_miss = resolve(targets, universe, aliases)

        seed_path = os.path.join(args.out_dir, "{}_seed_genes.txt".format(disease))
        with open(seed_path, "w") as handle:
            for gene in s_ok:
                handle.write("{} {}\n".format(gene, args.score))

        target_path = os.path.join(args.out_dir, "{}_targets.txt".format(disease))
        with open(target_path, "w") as handle:
            for gene in t_ok:
                handle.write(gene + "\n")

        # Record what could not be mapped. XGDAG cannot rank these at all, and
        # the count has to be reported alongside the metrics - scoring a method
        # only on the genes it happens to cover flatters it.
        miss_path = os.path.join(args.out_dir, "{}_unmappable.txt".format(disease))
        with open(miss_path, "w") as handle:
            for gene in t_miss:
                handle.write(gene + "\n")

        print("{:26}{:>8}{:>9}{:>9}{:>9}   {}/{}".format(
            disease, len(seeds), len(s_ok), len(s_ren), len(s_miss),
            len(t_ok), len(targets)))

    print("\nWrote seed/target files -> {}".format(args.out_dir))
    print("\nNext, for each disease:")
    print("  perl $NIAPU/src/preprocess.pl \\")
    print("      $NIAPU/data/biogrid_gene_pairs_clean_Hs_4_4_206.txt \\")
    print("      {}/dee_seed_genes.txt out_links out_genes".format(args.out_dir))
    print("  ./nedbit_calc out_links out_genes dee_nedbit_features")


if __name__ == "__main__":
    main()
