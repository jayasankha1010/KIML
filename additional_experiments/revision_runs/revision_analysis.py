"""
Bootstrap confidence intervals and late fusion, over the manuscript's own predictions.

Two reviewer comments, one pass over the collected per-gene prediction files:

  R1.10  "Median rank is not enough to characterize a DGP method. Recall@K,
          Precision@K, confidence intervals are highly relevant and should be
          included in main results and not in supplementary only."

          Every metric is reported with a percentile bootstrap CI obtained by
          resampling the post-split target genes. This holds the model fixed and
          asks: how much of the reported value is an accident of which genes
          happened to be curated after the cutoff? That is the relevant
          uncertainty for a retrieval metric, and it needs no retraining.

  R1.5d / R4.1  "the current concatenation strategy versus learned or late
          fusion" and "this is precisely what Bayesian inference is about - a
          prior distribution integrated with a likelihood".

          Late fusion sums the log-odds of the knowledge-only model (C-GNN) and
          the experimental-only model (GNN). Under conditional independence that
          is exactly prior x likelihood, so one experiment answers both: it tests
          an alternative fusion strategy AND instantiates the Bayesian reading
          Reviewer 4 asked for. No retraining - it recombines predictions the
          manuscript already reports.

Metric definitions are copied from results_processing/evaluate_results.py so the
point estimates reproduce the published numbers exactly.

Usage:
    python additional_experiments/revision_runs/revision_analysis.py \
        --predictions additional_experiments/revision_runs/paper_predictions
"""

import argparse
import csv
import math
import os
import random

K_THRESHOLDS = [10, 25, 50, 100, 200, 250, 500, 1000]
PERCENTAGES = [1, 5, 10]

DISEASE_TARGETS = {
    "dee": "DEE-2025_03_vs_2022_09.txt",
    "ad_dee": "AD_DEE-2022_09_to_2025_03.txt",
    "ar_dee": "AR_DEE-2022_09_to_2025_03.txt",
    "microcephaly": "Microcephaly-2025_06_vs_2022_09.txt",
    "intellectual_disability": "Intellectual-disability-2025_06_vs_2022_09.txt",
    "mnd": "MND-2025_06_vs_2022_09.txt",
    "cp": "CP-2025_06_vs_2022_09.txt",
    "platelet_disorder": "Bleeding_and_Platelet_Disorders-2026-02_vs_2022-09.txt",
    "arthrogryposis": "Arthrogryposis-2025_06_vs_2022_09.txt",
}


# Mantis writes a different schema to SPEOS, but carries the same three facts.
# known_gene is a string flag rather than a 0/1 label; the values accepted here
# match results/evaluate_mantis_single.py so the two agree on what "already
# known" means.
# (gene, known-flag, score). Tried in order; the first whose columns are all
# present wins. Mantis has been exported in two shapes - the raw merged
# predictions that evaluate_mantis_single.py reads, and a human-readable export
# with spaced column names - so both are accepted.
SCHEMAS = [
    ("speos", ("hgnc", "truth", "avg_probability")),
    ("mantis", ("Gene_Name", "known_gene", "mantis_ml_proba")),
    ("mantis", ("Gene Name", "Known Gene", "Mantis-ml Prediction Probability")),
]
MANTIS_TRUE = {"1", "1.0", "true", "True", "TRUE"}


def load_predictions(path):
    """-> list of (gene, truth, probability), for either SPEOS or Mantis output."""
    delimiter = "," if path.lower().endswith(".csv") else "\t"
    rows = []
    with open(path, newline="") as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        fields = set(reader.fieldnames or [])
        match = next(((kind, cols) for kind, cols in SCHEMAS if set(cols) <= fields), None)
        if match is None:
            raise ValueError(
                "{}: no known schema matches columns {}".format(
                    os.path.basename(path), sorted(fields)[:8]))
        kind, (gene_key, truth_key, prob_key) = match
        mantis = kind == "mantis"
        for row in reader:
            try:
                probability = float(row[prob_key])
            except (TypeError, ValueError):
                continue
            raw = row[truth_key]
            if mantis:
                truth = 1.0 if str(raw).strip() in MANTIS_TRUE else 0.0
            else:
                try:
                    truth = float(raw)
                except (TypeError, ValueError):
                    continue
            rows.append((row[gene_key], truth, probability))
    return rows


def rank_unseen(rows):
    """Rank genes not already positive, highest probability first.

    Mirrors evaluate_results.py: drop truth == 1, then rank by avg_probability
    descending with ties broken by order of appearance.
    """
    unseen = [(g, p) for g, t, p in rows if t != 1]
    unseen.sort(key=lambda item: -item[1])
    return {gene: i + 1 for i, (gene, _) in enumerate(unseen)}, len(unseen)


def metrics_from_ranks(hit_ranks, n_targets, universe_size):
    """Retrieval metrics for a set of target ranks. Same formulas as the paper."""
    out = {}
    if not hit_ranks or not n_targets:
        out["median_rank_unseen"] = float("nan")
        out["mean_rank_unseen"] = float("nan")
        for pct in PERCENTAGES:
            out["fold_enrichment_top_{}_pct".format(pct)] = 0.0
        for k in K_THRESHOLDS:
            out["recall_at_{}".format(k)] = 0.0
            out["precision_at_{}".format(k)] = 0.0
        return out

    ordered = sorted(hit_ranks)
    middle = len(ordered) // 2
    out["median_rank_unseen"] = (float(ordered[middle]) if len(ordered) % 2
                                 else (ordered[middle - 1] + ordered[middle]) / 2.0)
    out["mean_rank_unseen"] = sum(ordered) / len(ordered)

    for pct in PERCENTAGES:
        cutoff = int(universe_size * (pct / 100.0))
        recall = sum(1 for r in ordered if r <= cutoff) / n_targets
        out["fold_enrichment_top_{}_pct".format(pct)] = recall / (pct / 100.0)
    for k in K_THRESHOLDS:
        hits = sum(1 for r in ordered if r <= k)
        out["recall_at_{}".format(k)] = hits / n_targets
        out["precision_at_{}".format(k)] = hits / k
    return out


def bootstrap(hit_ranks, universe_size, n_boot, seed, alpha=0.05):
    """Percentile CI by resampling the target genes with replacement."""
    point = metrics_from_ranks(hit_ranks, len(hit_ranks), universe_size)
    if not hit_ranks:
        return point, {}

    rng = random.Random(seed)
    n = len(hit_ranks)
    draws = {key: [] for key in point}
    for _ in range(n_boot):
        sample = [hit_ranks[rng.randrange(n)] for _ in range(n)]
        for key, value in metrics_from_ranks(sample, n, universe_size).items():
            if not (isinstance(value, float) and math.isnan(value)):
                draws[key].append(value)

    bounds = {}
    lo_i = int(alpha / 2 * n_boot)
    hi_i = min(int((1 - alpha / 2) * n_boot), n_boot - 1)
    for key, values in draws.items():
        if not values:
            continue
        values.sort()
        bounds[key] = (values[min(lo_i, len(values) - 1)],
                       values[min(hi_i, len(values) - 1)])
    return point, bounds


def paired_bootstrap(ranks_a, ranks_b, universe_a, universe_b,
                     n_boot, seed, alpha=0.05):
    """Bootstrap the DIFFERENCE between two models on the same target genes.

    Comparing two marginal confidence intervals is the wrong test and is badly
    under-powered: both models are scored on the same post-split gene set, so
    "these targets are hard for everyone" inflates both intervals and hides real
    differences. Resampling genes once per draw and taking the difference
    cancels that shared difficulty, which is the comparison the reviewer's
    question actually implies.

    Returns metric -> (difference, lo, hi, significant), where the difference is
    A minus B. For rank metrics, negative means A ranks targets higher.
    """
    shared = sorted(set(ranks_a) & set(ranks_b))
    if not shared:
        return {}, 0

    rng = random.Random(seed)
    n = len(shared)
    observed = {}
    point_a = metrics_from_ranks([ranks_a[g] for g in shared], n, universe_a)
    point_b = metrics_from_ranks([ranks_b[g] for g in shared], n, universe_b)
    for key in point_a:
        if not (math.isnan(point_a[key]) or math.isnan(point_b[key])):
            observed[key] = point_a[key] - point_b[key]

    draws = {key: [] for key in observed}
    for _ in range(n_boot):
        sample = [shared[rng.randrange(n)] for _ in range(n)]
        draw_a = metrics_from_ranks([ranks_a[g] for g in sample], n, universe_a)
        draw_b = metrics_from_ranks([ranks_b[g] for g in sample], n, universe_b)
        for key in draws:
            if not (math.isnan(draw_a[key]) or math.isnan(draw_b[key])):
                draws[key].append(draw_a[key] - draw_b[key])

    lo_i = int(alpha / 2 * n_boot)
    hi_i = min(int((1 - alpha / 2) * n_boot), n_boot - 1)
    out = {}
    for key, values in draws.items():
        if not values:
            continue
        values.sort()
        lo = values[min(lo_i, len(values) - 1)]
        hi = values[min(hi_i, len(values) - 1)]
        out[key] = (observed[key], lo, hi, lo > 0 or hi < 0)
    return out, n


def logit(p, eps=1e-9):
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def late_fusion(rows_a, rows_b):
    """Sum the log-odds of two models, on the genes they share.

    Under conditional independence this is the posterior combination Reviewer 4
    described: one model supplies the prior from background knowledge, the other
    the likelihood from experimental data.
    """
    a = {g: (t, p) for g, t, p in rows_a}
    b = {g: p for g, _, p in rows_b}
    shared = sorted(set(a) & set(b))
    fused = []
    for gene in shared:
        truth, p_a = a[gene]
        score = logit(p_a) + logit(b[gene])
        # Map back to a probability so downstream ranking is unchanged in order.
        fused.append((gene, truth, 1.0 / (1.0 + math.exp(-score))))
    return fused, len(shared), len(a), len(b)


def score_one(rows, targets, n_boot, seed):
    ranks, universe = rank_unseen(rows)
    # sorted(), not set order: Python randomises string hashing per process, so
    # iterating the target set directly gives a different ordering each run and
    # the seeded bootstrap resamples a differently-ordered list. Point estimates
    # are unaffected, but the intervals would not be reproducible.
    target_ranks = {g: ranks[g] for g in sorted(targets) if g in ranks}
    point, bounds = bootstrap(list(target_ranks.values()), universe, n_boot, seed)
    return point, bounds, target_ranks, universe


# Each arm has the same three-way structure: experimental only, knowledge only,
# and both combined. Late fusion is derived per arm from the two single-source
# models, so R1.5d and R4.1 are answered for the RF arm as well as the GNN one.
ARMS = {
    "GNN": {"experimental": "GNN", "knowledge": "C-GNN",
            "combined": "KI-GNN", "fusion": "Late-fusion-GNN"},
    "RF": {"experimental": "RF", "knowledge": "C-RF",
           "combined": "KI-RF", "fusion": "Late-fusion-RF"},
}

# R1.5b asks which half of KI-GNN does the work: the PubMed node features or
# the knowledge-graph edges. KI-GNN vs GNN changes both at once, so these four
# hold one factor fixed while varying the other, over the 2x2
# {expression, expression+PubMed} x {PPI graph, knowledge graph}.
# R1.5e asks what message passing itself contributes; KIMLP is KI-GNN with
# mp.n_layers = 0, identical in every other respect.
# All five cells come from the same code path and share a universe (16,546) and
# target count (192), so the grid is internally consistent. The published GNN
# and KI-GNN runs are kept separately for Table 1 reproduction; the "(rerun)"
# variants are the ones used here. Run-to-run variance measured against the
# published values is small - GNN +87, KI-GNN -50 ranks.
ABLATION_CONTRASTS = [
    ("KIGNN-PPI", "GNN (rerun)"),      # add PubMed features, PPI graph held fixed
    ("KI-GNN (rerun)", "GNN-KG"),      # add PubMed features, knowledge graph held fixed
    ("GNN-KG", "GNN (rerun)"),         # swap to knowledge graph, expression only
    ("KI-GNN (rerun)", "KIGNN-PPI"),   # swap to knowledge graph, both feature sets
    ("KIMLP", "KI-GNN (rerun)"),       # remove message passing entirely (R1.5e)
    # R1.4: identical to KI-GNN except the literature representation.
    ("KIGNN-TFIDF", "KI-GNN (rerun)"),
    ("KIGNN-TFIDF-TITLE", "KI-GNN (rerun)"),
    ("KIGNN-DOC2VEC", "KI-GNN (rerun)"),
    # Reproduction checks: same config, different run, no torch.manual_seed.
    ("GNN (rerun)", "GNN"),
    ("KI-GNN (rerun)", "KI-GNN"),
]

# Contrasts worth testing, as (A, B). Each asks "is A better than B?"
CONTRASTS = []
for _arm in ARMS.values():
    CONTRASTS += [
        (_arm["combined"], _arm["experimental"]),  # the manuscript's central claim
        (_arm["combined"], _arm["knowledge"]),     # does experimental data add anything?
        (_arm["fusion"], _arm["combined"]),        # R1.5d: late fusion vs concatenation
    ]
CONTRASTS += ABLATION_CONTRASTS


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--predictions", default=os.path.join(here, "paper_predictions"))
    parser.add_argument("--lookup", default=os.path.join(here, "experiment_lookup.tsv"),
                        help="GNN-arm lookup: disease, variant, experiment id")
    parser.add_argument("--mantis-lookup", default=os.path.join(here, "mantis_lookup.tsv"),
                        help="RF-arm lookup: disease, variant, predictions CSV")
    parser.add_argument("--mantis-predictions",
                        default=os.path.join(here, "mantis_predictions"),
                        help="directory holding the Mantis prediction CSVs")
    parser.add_argument("--disease-dir",
                        default=os.path.join(root, "data", "kiml_data", "diseases"))
    parser.add_argument("--n-boot", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("-o", "--out", default=os.path.join(here, "revision_metrics.tsv"))
    args = parser.parse_args()

    # Two lookups, one per arm. Each maps disease -> variant -> (label, path).
    by_disease = {}

    with open(args.lookup) as handle:
        for entry in csv.DictReader(handle, delimiter="\t"):
            experiment = entry["experiment_id"]
            path = os.path.join(args.predictions,
                                "{}_probabilities.tsv".format(experiment))
            by_disease.setdefault(entry["disease"], {})[entry["paper_variant"]] = (
                experiment, path)

    if args.mantis_lookup and os.path.exists(args.mantis_lookup):
        with open(args.mantis_lookup) as handle:
            for entry in csv.DictReader(handle, delimiter="\t"):
                path = os.path.join(args.mantis_predictions, entry["predictions_file"])
                by_disease.setdefault(entry["disease"], {})[entry["paper_variant"]] = (
                    entry["predictions_file"], path)
    else:
        print("[info] no Mantis lookup; scoring the GNN arm only.")

    results, contrasts = [], []
    print("{:24}{:12}{:>8}{:>10}  {}".format("disease", "method", "targets",
                                             "median", "95% CI"))
    print("-" * 74)

    for disease, variants in by_disease.items():
        target_file = DISEASE_TARGETS.get(disease)
        if not target_file:
            continue
        target_path = os.path.join(args.disease_dir, target_file)
        if not os.path.exists(target_path):
            print("  [skip] {}: no target list".format(disease))
            continue
        with open(target_path) as handle:
            targets = {line.strip() for line in handle if line.strip()}

        loaded = {}
        for variant, (label, path) in variants.items():
            if os.path.exists(path):
                try:
                    loaded[variant] = load_predictions(path)
                except ValueError as error:
                    print("  [skip] {} {}: {}".format(disease, variant, error))
            else:
                print("  [missing] {} {} ({})".format(disease, variant, label))

        # The published configurations, plus a late fusion per arm built from
        # that arm's two single-source models.
        to_score = dict(loaded)
        for arm in ARMS.values():
            if arm["experimental"] in loaded and arm["knowledge"] in loaded:
                fused, shared, n_a, n_b = late_fusion(
                    loaded[arm["experimental"]], loaded[arm["knowledge"]])
                to_score[arm["fusion"]] = fused
                # Fusion lives on the intersection. If that differs from either
                # model's universe, the fold-enrichment denominators differ too
                # and the fusion row is not directly comparable with the others.
                if shared != n_a or shared != n_b:
                    print("  [note] {}: {} defined on {} genes; {} has {}, "
                          "{} has {} - denominators differ".format(
                              disease, arm["fusion"], shared,
                              arm["experimental"], n_a, arm["knowledge"], n_b))

        scored = {}
        for method, rows in to_score.items():
            point, bounds, target_ranks, universe = score_one(
                rows, targets, args.n_boot, args.seed)
            scored[method] = (target_ranks, universe)
            n_targets = len(target_ranks)
            record = {"disease": disease, "method": method,
                      "experiment": variants.get(method, ("derived", ""))[0],
                      "n_targets": n_targets, "universe_size": universe,
                      "n_boot": args.n_boot}
            for key, value in point.items():
                record[key] = round(value, 4) if isinstance(value, float) else value
                if key in bounds:
                    record[key + "_lo"] = round(bounds[key][0], 4)
                    record[key + "_hi"] = round(bounds[key][1], 4)
            results.append(record)

            median = point["median_rank_unseen"]
            ci = bounds.get("median_rank_unseen")
            print("{:24}{:12}{:>8}{:>10}  {}".format(
                disease, method, n_targets,
                "-" if math.isnan(median) else "{:g}".format(median),
                "[{:g}, {:g}]".format(*ci) if ci else "-"))

        # Paired contrasts on the same genes, which is the properly powered
        # version of "does A beat B on this disease?".
        for a, b in CONTRASTS:
            if a not in scored or b not in scored:
                continue
            ranks_a, universe_a = scored[a]
            ranks_b, universe_b = scored[b]
            diffs, n_paired = paired_bootstrap(
                ranks_a, ranks_b, universe_a, universe_b, args.n_boot, args.seed)
            if not diffs:
                continue
            record = {"disease": disease, "contrast": "{} - {}".format(a, b),
                      "n_paired_targets": n_paired, "n_boot": args.n_boot}
            for key, (difference, lo, hi, significant) in diffs.items():
                record[key] = round(difference, 4)
                record[key + "_lo"] = round(lo, 4)
                record[key + "_hi"] = round(hi, 4)
                record[key + "_sig"] = "yes" if significant else "no"
            contrasts.append(record)

    if not results:
        print("\nNothing scored. Is --predictions pointing at the collected files?")
        return

    if contrasts:
        print("\n" + "=" * 86)
        print(" PAIRED CONTRASTS - difference in median rank on the same genes")
        print(" negative favours the first model; significant = 95% CI excludes zero")
        print("=" * 86)
        print("{:24}{:22}{:>7}{:>11}  {:24}{}".format(
            "disease", "contrast", "n", "difference", "95% CI", "significant"))
        for record in contrasts:
            key = "median_rank_unseen"
            if key not in record:
                continue
            print("{:24}{:22}{:>7}{:>11}  {:24}{}".format(
                record["disease"], record["contrast"], record["n_paired_targets"],
                "{:g}".format(record[key]),
                "[{:g}, {:g}]".format(record[key + "_lo"], record[key + "_hi"]),
                record[key + "_sig"]))
        print("=" * 86)

        columns = []
        for record in contrasts:
            for key in record:
                if key not in columns:
                    columns.append(key)
        contrast_path = args.out.replace(".tsv", "_contrasts.tsv")
        with open(contrast_path, "w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
            writer.writeheader()
            writer.writerows(contrasts)
        print("Wrote {} contrasts -> {}".format(len(contrasts), contrast_path))

    columns = list(results[0])
    for record in results:
        for key in record:
            if key not in columns:
                columns.append(key)
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, delimiter="\t")
        writer.writeheader()
        writer.writerows(results)
    print("\nWrote {} rows -> {}".format(len(results), args.out))


if __name__ == "__main__":
    main()
