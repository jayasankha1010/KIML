"""
Reduce the 1.2 GB date-filtered PubMed text dump to a small summary table.

Runs on Spartan, where gene_details_2022_09.csv lives. Emits one row per gene
(~1 MB total) that can be copied back to a laptop and analysed offline.

For each gene it reports:

  n_papers_total      papers in genes_to_ids.csv (all dates, capped at 100 by
                      the ToppGene API)
  n_papers_pre_cutoff papers surviving the 2022-10-01 filter, i.e. the row
                      length in gene_details_2022_09.csv
  <disease>_evidence  for each disease, how many of that gene's PRE-CUTOFF
                      papers mention the disease by keyword

The first two columns feed the popularity baseline (task 1) and the
article-count stratification (task 19).

The per-disease columns feed task 8 / Reviewer 1 comment 7: "A gene added to a
panel in 2024 may already have had substantial disease-related literature
before September 2022." A post-split target gene with a non-zero evidence count
already had disease literature before the cutoff, so for that gene the temporal
split is measuring curation lag rather than discovery. Splitting the metrics on
this column answers the comment directly.

Keyword matching is a proxy for a curated gene-disease assertion. It is
deliberately broad (favouring recall), so treat a non-zero count as "plausibly
had prior evidence" rather than proof, and read the zero stratum as the
conservative, genuinely-novel set.

It also reports the diagnostic described to the author: whether ToppGene returns
each gene's *most recent* 100 papers or an arbitrary/relevance-ranked 100. In
the "most recent" regime, date filtering strips proportionally more from
heavily-studied genes and would invert the popularity ranking instead of
refining it. See the DIAGNOSTIC block printed at the end.

Usage on Spartan, from the KIML root:

    python additional_experiments/popularity/extract_pubmed_counts.py \
        --gene-details /data/projects/punim2353/chathura/pubmed/gene_details_2022_09.csv \
        --genes-to-ids kiml/genes_to_ids.csv \
        -o additional_experiments/popularity/pubmed_counts_2022_09.tsv

Then copy the single output TSV back.
"""

import argparse
import csv
import os
import re
import sys

# Broad keyword sets, one per disease key used by popularity_baseline.py.
# Matched case-insensitively against the concatenated title+abstract text of
# each pre-cutoff paper. Substrings are intentional ("epilep" catches epilepsy,
# epileptic, epileptiform).
DISEASE_TERMS = {
    "dee": ["epilep", "encephalopath", "seizure", "infantile spasm", "convuls",
            "west syndrome", "dravet", "lennox-gastaut", "ohtahara"],
    "ad_dee": ["epilep", "encephalopath", "seizure", "infantile spasm", "convuls"],
    "ar_dee": ["epilep", "encephalopath", "seizure", "infantile spasm", "convuls"],
    "microcephaly": ["microcephal"],
    "intellectual_disability": ["intellectual disabilit", "mental retardation",
                                "developmental delay", "cognitive impairment",
                                "learning disabilit"],
    "mnd": ["motor neuron", "amyotrophic lateral", "spinal muscular atroph",
            "primary lateral sclerosis"],
    "cp": ["cerebral palsy", "spastic diplegia", "spastic quadriplegia"],
    "ataxia": ["ataxia", "ataxic", "cerebellar degener"],
    "arthrogryposis": ["arthrogryposis", "joint contracture", "multiple congenital contracture",
                       "distal arthrogryposis"],
    "cataract": ["cataract", "lens opacit"],
    "platelet_disorder": ["platelet", "thrombocytopen", "bleeding disorder",
                          "coagulopath", "haemorrhagic", "hemorrhagic diathesis"],
    "bone_marrow_failure": ["bone marrow failure", "aplastic anaem", "aplastic anem",
                            "pancytopen", "fanconi anem", "fanconi anaem"],
    "aminoacidopathy": ["aminoacidopath", "amino acid metabolism", "phenylketonuria",
                        "maple syrup urine", "homocystinuria", "tyrosinemia", "tyrosinaemia"],
    "skeletal_dysplasia": ["skeletal dysplas", "chondrodysplas", "osteochondrodysplas",
                           "achondroplas", "osteogenesis imperfecta"],
}


def build_patterns():
    return {disease: re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
            for disease, terms in DISEASE_TERMS.items()}


def load_total_counts(path):
    """gene -> number of PubMed IDs in the unfiltered scrape."""
    counts = {}
    with open(path, newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if row:
                counts[row[0].strip()] = len([x for x in row[1:] if x.strip()])
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gene-details", required=True,
                        help="gene_details_2022_09.csv (date-filtered text dump)")
    parser.add_argument("--genes-to-ids", default=None,
                        help="genes_to_ids.csv, for the unfiltered comparison counts")
    parser.add_argument("-o", "--out", required=True)
    parser.add_argument("--cap", type=int, default=100,
                        help="ToppGene per-gene PMID cap, for the diagnostic (default 100)")
    args = parser.parse_args()

    # Rows hold up to 100 concatenated abstracts, so the default field limit is
    # far too small.
    csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))

    patterns = build_patterns()
    diseases = sorted(patterns)

    totals = {}
    if args.genes_to_ids and os.path.exists(args.genes_to_ids):
        print("Reading unfiltered counts from {}".format(args.genes_to_ids))
        totals = load_total_counts(args.genes_to_ids)
        print("  {} genes".format(len(totals)))
    else:
        print("[warn] genes_to_ids.csv not given; skipping the cap diagnostic.")

    print("Streaming {}".format(args.gene_details))
    rows = []
    with open(args.gene_details, newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for i, row in enumerate(reader, 1):
            if not row:
                continue
            gene = row[0].strip()
            papers = [p for p in row[1:] if p.strip()]
            record = {
                "gene": gene,
                "n_papers_total": totals.get(gene, ""),
                "n_papers_pre_cutoff": len(papers),
            }
            # Number of this gene's pre-cutoff papers mentioning each disease.
            for disease in diseases:
                search = patterns[disease].search
                record[disease + "_evidence"] = sum(1 for p in papers if search(p))
            rows.append(record)
            if i % 2000 == 0:
                print("  {} genes...".format(i))

    print("Parsed {} genes.".format(len(rows)))

    columns = ["gene", "n_papers_total", "n_papers_pre_cutoff"] + [d + "_evidence" for d in diseases]
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    print("Wrote {} ({} columns)".format(args.out, len(columns)))

    # ---- diagnostic: which regime is the ToppGene cap in? ----
    if totals:
        capped = [r for r in rows if r["n_papers_total"] == args.cap]
        uncapped = [r for r in rows if isinstance(r["n_papers_total"], int)
                    and 0 < r["n_papers_total"] < args.cap]
        print("\n" + "=" * 62)
        print(" DIAGNOSTIC: effect of the {}-PMID cap on date filtering".format(args.cap))
        print("=" * 62)

        def survival(group):
            if not group:
                return 0.0
            return sum(r["n_papers_pre_cutoff"] / r["n_papers_total"]
                       for r in group) / len(group)

        cap_rate, unc_rate = survival(capped), survival(uncapped)
        print("  genes at the cap        : {:>6}   mean pre-cutoff survival {:.1%}".format(
            len(capped), cap_rate))
        print("  genes below the cap     : {:>6}   mean pre-cutoff survival {:.1%}".format(
            len(uncapped), unc_rate))
        still_tied = sum(1 for r in capped if r["n_papers_pre_cutoff"] == args.cap)
        print("  still tied after filter : {:>6}".format(still_tied))
        print()
        if unc_rate > 0 and cap_rate < unc_rate * 0.75:
            print("  >> 'MOST RECENT' REGIME. Capped (heavily-studied) genes lose")
            print("     disproportionately to the date filter, so filtered counts")
            print("     UNDERSTATE exactly the genes that are best studied. Do not")
            print("     use these counts as a popularity ranking - it would be")
            print("     inverted. Uncapped counts (NCBI gene2pubmed) are required.")
        elif cap_rate > 0 and abs(cap_rate - unc_rate) < 0.1:
            print("  >> ARBITRARY/RELEVANCE REGIME. Both groups lose a similar")
            print("     fraction, so date filtering refines the ranking as intended.")
            print("     Filtered counts are usable; the cap still compresses")
            print("     magnitude at the top but does not invert the order.")
        else:
            print("  >> INTERMEDIATE. Inspect before relying on the filtered counts.")
        print("=" * 62)


if __name__ == "__main__":
    main()
