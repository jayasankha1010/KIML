"""
Build the popularity-baseline supplementary workbook for the Bioinformatics
Advances resubmission.

Joins the six manuscript configurations (RF / C-RF / KI-RF / GNN / C-GNN /
KI-GNN, read out of Supp_Data_2.xlsx) against the publication-count baseline
produced by popularity_baseline.py, for every disease and every metric.

This is the evidence for four reviewer comments:

  R1.5  "ablations separating ... literature-semantic information versus simple
         PubMed article-count/popularity signals"
  R1.6  "I could not find a simple control for publication count, literature
         coverage, or network degree"
  R1.10 "Median rank is not enough ... Recall@K, Precision@K, confidence
         intervals ... in main results"
  R1.11 "demonstrate that their conclusions are stable across multiple values
         of K"

Usage:
    python additional_experiments/popularity/build_supplementary.py
"""

import argparse
import csv
import os

import openpyxl
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# Manuscript naming: LL = experimental only, HL = knowledge only, LL+HL = KIML.
METHODS = [
    ("RF", "Mantis", "LL", "RF (experimental only)"),
    ("C-RF", "Mantis", "HL", "C-RF (knowledge only)"),
    ("KI-RF", "Mantis", "LL_HL", "KI-RF (KIML)"),
    ("GNN", "speos", "ll_only", "GNN (experimental only)"),
    ("C-GNN", "speos", "hl_only", "C-GNN (knowledge only)"),
    ("KI-GNN", "speos", "hl_ll", "KI-GNN (KIML)"),
    # Primary baseline: counts restricted to the models' knowledge cutoff.
    ("Popularity", "popularity", "", "Popularity (pre-2022-10 PubMed count)"),
    # Secondary: counts of all dates, including post-split literature the models
    # never saw. Deliberately favours the baseline; shown because losing even to
    # that version is the stronger claim.
    ("Pop (all dates)", "popularity_alldates", "", "Popularity (all-date PubMed count)"),
]

# Diseases reported in the manuscript, in manuscript order.
PAPER_DISEASES = [
    ("dee", "DEE", "Neurological"),
    ("ad_dee", "AD DEE", "Neurological"),
    ("ar_dee", "AR DEE", "Neurological"),
    ("microcephaly", "Microcephaly", "Neurological"),
    ("intellectual_disability", "Intellectual Disability", "Neurological"),
    ("mnd", "Motor Neuron Disease", "Neurological"),
    ("cp", "Cerebral Palsy", "Neurological"),
    ("platelet_disorder", "Bleeding and Platelet Disorder", "Non-neurological"),
    ("arthrogryposis", "Arthrogryposis", "Non-neurological"),
]

EXTRA_DISEASES = [
    ("aminoacidopathy", "Aminoacidopathy", "Not in manuscript"),
    ("ataxia", "Ataxia (paediatric)", "Not in manuscript"),
    ("bone_marrow_failure", "Bone Marrow Failure", "Not in manuscript"),
    ("cataract", "Cataract", "Not in manuscript"),
    ("skeletal_dysplasia", "Skeletal Dysplasia", "Not in manuscript"),
]

# Column order of the Mantis sheet (it has no header row). Mirrors
# results/RF_results/Mantis_Results_Consolidated.tsv with CSV_File replaced by
# the method tag.
MANTIS_COLUMNS = [
    "label", "method", "universe_size", "mean_rank_unseen", "median_rank_unseen",
    "num_targets_found", "avg_precision", "avg_reciprocal_rank_custom",
    "fold_enrichment_top_1_pct", "recall_top_1_pct",
    "fold_enrichment_top_5_pct", "recall_top_5_pct",
    "fold_enrichment_top_10_pct", "recall_top_10_pct",
    "precision_at_10", "recall_at_10", "precision_at_25", "recall_at_25",
    "precision_at_50", "recall_at_50", "precision_at_100", "recall_at_100",
    "precision_at_250", "recall_at_250", "precision_at_1000", "recall_at_1000",
]

MANTIS_LABEL_TO_DISEASE = {
    "dee": "dee", "ad dee": "ad_dee", "ar dee": "ar_dee",
    "microcephaly": "microcephaly", "intellectual disability": "intellectual_disability",
    "mnd": "mnd", "cp": "cp", "platelet disorder": "platelet_disorder",
    "arthrogryposis": "arthrogryposis", "arthogryposis": "arthrogryposis",
}

# Metrics to report, in display order. (key, label, number format, lower_is_better)
METRIC_SPEC = [
    ("median_rank_unseen", "Median rank", "0.0", True),
    ("mean_rank_unseen", "Mean rank", "0.0", True),
    ("avg_precision", "Average precision (AP)", "0.0000", False),
    ("avg_reciprocal_rank_custom", "Avg reciprocal rank", "0.0000", False),
    ("fold_enrichment_top_1_pct", "Fold enrichment @ top 1%", "0.00", False),
    ("fold_enrichment_top_5_pct", "Fold enrichment @ top 5%", "0.00", False),
    ("fold_enrichment_top_10_pct", "Fold enrichment @ top 10%", "0.00", False),
    ("recall_top_1_pct", "Recall @ top 1%", "0.0000", False),
    ("recall_top_5_pct", "Recall @ top 5%", "0.0000", False),
    ("recall_top_10_pct", "Recall @ top 10%", "0.0000", False),
    ("precision_at_10", "Precision @ 10", "0.0000", False),
    ("precision_at_25", "Precision @ 25", "0.0000", False),
    ("precision_at_50", "Precision @ 50", "0.0000", False),
    ("precision_at_100", "Precision @ 100", "0.0000", False),
    ("precision_at_250", "Precision @ 250", "0.0000", False),
    ("precision_at_1000", "Precision @ 1000", "0.0000", False),
    ("recall_at_10", "Recall @ 10", "0.0000", False),
    ("recall_at_25", "Recall @ 25", "0.0000", False),
    ("recall_at_50", "Recall @ 50", "0.0000", False),
    ("recall_at_100", "Recall @ 100", "0.0000", False),
    ("recall_at_250", "Recall @ 250", "0.0000", False),
    ("recall_at_1000", "Recall @ 1000", "0.0000", False),
]

HEADLINE = ["median_rank_unseen", "fold_enrichment_top_1_pct",
            "precision_at_100", "recall_at_100"]
RECALL_K = ["recall_at_10", "recall_at_25", "recall_at_50",
            "recall_at_100", "recall_at_250", "recall_at_1000"]

HDR_FILL = PatternFill("solid", fgColor="1F3864")
SUB_FILL = PatternFill("solid", fgColor="D9E2F3")
POP_FILL = PatternFill("solid", fgColor="FFF2CC")
BEST_FILL = PatternFill("solid", fgColor="C6E0B4")
GROUP_FILL = PatternFill("solid", fgColor="F2F2F2")
HDR_FONT = Font(bold=True, color="FFFFFF", size=10)
BOLD = Font(bold=True, size=10)
THIN = Side(style="thin", color="BFBFBF")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def load_paper_metrics(xlsx_path):
    """method -> disease -> {metric: value} for the six manuscript configs."""
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    out = {}

    ws = wb["speos_rank_metrics"]
    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    for row in ws.iter_rows(min_row=2, values_only=True):
        record = dict(zip(header, row))
        method, disease = record.get("comment"), record.get("disease")
        if not method or not disease:
            continue
        out.setdefault(("speos", method), {})[disease] = {
            k: v for k, v in record.items() if isinstance(v, (int, float))}

    ws = wb["Mantis_rank_metrics"]
    for row in ws.iter_rows(values_only=True):
        record = dict(zip(MANTIS_COLUMNS, row))
        label, method = record.get("label"), record.get("method")
        if not label or not method or not isinstance(record.get("universe_size"), (int, float)):
            continue
        # "DEE (+PubMed)" / "Platelet Disorder (only LL)" -> "dee"
        base = str(label).split("(")[0].strip().lower()
        disease = MANTIS_LABEL_TO_DISEASE.get(base)
        if disease is None:
            continue
        out.setdefault(("Mantis", method), {})[disease] = {
            k: v for k, v in record.items() if isinstance(v, (int, float))}

    return out


def load_popularity(tsv_path):
    with open(tsv_path) as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    table = {}
    for row in rows:
        values = {}
        for key, raw in row.items():
            try:
                values[key] = float(raw)
            except (TypeError, ValueError):
                values[key] = raw
        table[row["disease"]] = values
    return table


def get(paper, popularity, method_key, source, tag, disease, metric):
    """popularity is {source_name: {disease: {metric: value}}}."""
    if source in popularity:
        return popularity[source].get(disease, {}).get(metric)
    return paper.get((source, tag), {}).get(disease, {}).get(metric)


def style_header(ws, row_idx, n_cols):
    for col in range(1, n_cols + 1):
        cell = ws.cell(row=row_idx, column=col)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BOX


def write_readme(ws, popularity, cutoff_applied):
    lines = [
        ("Supplementary Data 3 - Publication-count (popularity) baseline", True),
        ("", False),
        ("Knowledge-Inclusive Machine Learning (KIML). Prepared for the "
         "Bioinformatics Advances resubmission of BIOINF-2026-2290.", False),
        ("", False),
        ("PURPOSE", True),
        ("A non-learned control that ranks genes by how many PubMed papers mention them, "
         "nothing else. It isolates how much of KIML's performance could be obtained from "
         "raw literature volume rather than from literature semantics.", False),
        ("", False),
        ("Reviewer comments addressed:", True),
        ("  R1.5   ablation: literature-semantic information vs simple PubMed "
         "article-count / popularity signals", False),
        ("  R1.6   a simple control for publication count / literature coverage", False),
        ("  R1.10  Recall@K, Precision@K and confidence intervals, not median rank alone", False),
        ("  R1.11  stability of conclusions across multiple values of K", False),
        ("", False),
        ("PROTOCOL", True),
        ("Per disease, matching results_processing/evaluate_results.py exactly so the "
         "numbers are comparable with the manuscript:", False),
        ("  universe  = all genes with a literature record, minus that disease's "
         "pre-split (2022-09) positives", False),
        ("  ranking   = descending PubMed paper count", False),
        ("  targets   = genes added to the panel after 2022-09", False),
        ("  recall@k  = hits in top k / targets present in the universe", False),
        ("", False),
        ("CONFIDENCE INTERVALS (R1.10)", True),
        ("The source file (ToppGene API) returns at most 100 PubMed IDs per gene, so the "
         "most-studied genes are tied rather than ordered. Every metric is therefore "
         "computed under 20 independent random tie-break orderings; the workbook reports "
         "the median with the [min-max] range. A metric whose range is wide is determined "
         "by tie-breaking, not by popularity, and should not be read as a point estimate.", False),
        ("", False),
        ("CAVEATS", True),
        ("1. The 100-PMID cap removes magnitude information at the well-studied end: a "
         "5,000-paper gene and a 100-paper gene are indistinguishable. This baseline "
         "therefore measures 'is this gene studied at all', not 'how heavily studied'. "
         "Uncapped counts (e.g. NCBI gene2pubmed) would sharpen it.", False),
        ("2. Universe sizes and target counts differ between methods, because each model "
         "drops genes with missing features. Fold enrichment and recall@k are normalised "
         "and remain comparable; absolute ranks should be compared with that in mind. "
         "Per-method universe sizes are given in the 'All metrics' sheet.", False),
        ("3. Where the manuscript sheets do not contain a configuration (GNN "
         "experimental-only for Bleeding and Platelet Disorder), the cell is left blank.", False),
        ("", False),
        ("RF-ARM NUMBERS DIFFER FROM Supp_Data_2 BY DESIGN", True),
        ("Every RF, C-RF and KI-RF figure here is computed on the POST-SPLIT target list "
         "(*_vs_2022_09.txt), the definition the GNN arm uses. The published RF-arm values "
         "used the FULL later-snapshot panel (e.g. DEE-2025_03.txt), which also contains "
         "genes already on the panel at 2022-09 - 58 of them for DEE. Confirmed by "
         "reproducing all 27 published values: 21 match only the full list, 6 match both "
         "because their universe already excludes the extras, none match the diff alone.", False),
        ("This is NOT leakage. Those genes carry Known Gene = 0, so Mantis never trained on "
         "them and scoring them is legitimate validation. The issue is comparability: of the "
         "58, only 7 exist in the GNN universe and all 7 are GNN TRAINING POSITIVES, excluded "
         "from GNN ranking, while the other 51 are absent from it altogether. The same gene is "
         "therefore a validation target for one arm and a training positive for the other, so "
         "Table 1's RF and GNN columns do not measure the same task.", False),
        ("It also matters for the temporal-split claim R1.7 challenges: a gene already on the "
         "2022-09 panel cannot evidence discovery after the partition date. Scoring the RF arm "
         "on the post-split diff is the conservative choice and strengthens that argument.", False),
        ("The correction does not change the conclusion. On the consistent basis KI-RF still "
         "beats RF on 7 of 9 diseases, exactly as published; only AD DEE flips, from +8 to -60 "
         "ranks, and a margin of 8 was never meaningful. RF's own figures improve throughout "
         "(DEE 2201 -> 1895, Intellectual Disability 2872 -> 2238, Platelet 250 -> 120).", False),
        ("Related, and worth a Methods sentence: three different counts of 'DEE positives at "
         "2022-09' are in play - 825 in DEE-2022_09.txt, 736 trained on by SPEOS after "
         "feature-coverage filtering, and 726 flagged by Mantis under its own seed curation. "
         "The arms train on overlapping but different positive sets.", False),
        ("", False),
        ("DISCREPANCY WITH Supp_Data_2 'Summary' SHEET - PLEASE READ", True),
        ("The fold-enrichment values here are taken from the per-run detail sheets "
         "(Mantis_rank_metrics / speos_rank_metrics), not from the 'Summary' sheet of "
         "Supp_Data_2. For all three RF configurations (RF, C-RF, KI-RF) and all nine "
         "diseases, the column headed 'Fold Enrichment 1%' in that Summary sheet contains "
         "fold_enrichment_top_5_pct, not top_1_pct. The GNN half of the same table is "
         "correct. The two halves of that row block are therefore different metrics and "
         "RF-vs-GNN comparisons drawn from it do not hold.", False),
        ("The error understates RF. Examples (Summary value -> true FE@1%): "
         "DEE RF 6.28 -> 10.34; KI-RF 7.50 -> 10.42; Platelet Disorder RF 12.50 -> 50.00; "
         "Intellectual Disability RF 4.53 -> 8.23. Note this flips at least one comparison: "
         "on DEE the Summary shows KI-GNN (7.81) ahead of KI-RF (7.50), whereas the correct "
         "FE@1% puts KI-RF (10.42) ahead. The manuscript's Table 1 and any text referring to "
         "1% fold enrichment for the RF arm should be rechecked before resubmission.", False),
    ]
    if cutoff_applied:
        lines += [
            ("4. The 'Popularity' column counts only publications before 2022-10-01, matching the "
             "models' knowledge cutoff. 'Pop (all dates)' counts papers of any date, including "
             "post-split literature the models never saw, and is reported alongside because losing "
             "even to that inflated version is the stronger claim. Post-split target genes gained "
             "post-cutoff papers faster than the gene population at large (mean 5.7 vs 3.6 for DEE), "
             "i.e. a gene accrues literature BECAUSE it is identified as a disease gene - which is "
             "exactly why the cutoff column is the fair comparator.", False),
            ("5. Applying the cutoff also collapsed the tie at the API cap from 5,378 genes (28.2%) "
             "to 162 (0.8%), so the confidence ranges in this workbook are far tighter than they "
             "would be on all-date counts. Ordering among the 5,378 genes that originally hit the "
             "cap still reflects which 100 papers the API returned rather than true publication "
             "volume; see caveat 1.", False)]
    else:
        lines += [("4. PROVISIONAL: counts currently include papers of ALL dates, including "
                   "those published after the temporal split. This favours the baseline "
                   "(a gene gains papers because it was identified as a disease gene). "
                   "Re-run popularity_baseline.py with --articles to apply the "
                   "2022-10-01 cutoff; the baseline can only get weaker.", False)]

    for i, (text, bold) in enumerate(lines, start=1):
        cell = ws.cell(row=i, column=1, value=text)
        cell.font = Font(bold=bold, size=12 if i == 1 else 10)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.column_dimensions["A"].width = 120
    for i in range(1, len(lines) + 1):
        ws.row_dimensions[i].height = 30 if len(lines[i - 1][0]) > 95 else 15


def write_headline(ws, paper, popularity, diseases):
    """Paper's Summary layout, with Popularity appended to each metric block."""
    labels = [m[0] for m in METHODS]
    ws.cell(row=1, column=1, value="Headline metrics: manuscript configurations vs popularity baseline").font = Font(bold=True, size=12)
    ws.cell(row=2, column=1,
            value="Best value per disease per metric shaded green. The two baseline columns are shaded amber: "
                  "'Popularity' respects the 2022-10-01 cutoff and is the fair comparator; 'Pop (all dates)' "
                  "also counts post-split papers the models never saw, and so favours the baseline."
            ).font = Font(italic=True, size=9)

    row = 4
    for metric_key in HEADLINE:
        label, fmt, lower_better = next(
            (l, f, lb) for k, l, f, lb in METRIC_SPEC if k == metric_key)
        ws.cell(row=row, column=1, value=label).font = Font(bold=True, size=11)
        row += 1

        ws.cell(row=row, column=1, value="Group")
        ws.cell(row=row, column=2, value="Disease")
        for j, name in enumerate(labels):
            ws.cell(row=row, column=3 + j, value=name)
        style_header(ws, row, 2 + len(labels))
        header_row = row
        row += 1

        for key, display, group in diseases:
            ws.cell(row=row, column=1, value=group).font = Font(size=9, italic=True)
            ws.cell(row=row, column=2, value=display).font = BOLD
            values = []
            for j, (name, source, tag, _) in enumerate(METHODS):
                val = get(paper, popularity, name, source, tag, key, metric_key)
                cell = ws.cell(row=row, column=3 + j, value=val)
                cell.number_format = fmt
                cell.border = BOX
                cell.alignment = Alignment(horizontal="center")
                if source.startswith("popularity"):
                    cell.fill = POP_FILL
                values.append(val)

            present = [v for v in values if isinstance(v, (int, float))]
            if present:
                best = min(present) if lower_better else max(present)
                for j, val in enumerate(values):
                    if val == best:
                        ws.cell(row=row, column=3 + j).fill = BEST_FILL
                        ws.cell(row=row, column=3 + j).font = BOLD
            row += 1
        row += 2
        ws.column_dimensions["A"].width = 18
        ws.column_dimensions["B"].width = 30
        for j in range(len(labels)):
            ws.column_dimensions[get_column_letter(3 + j)].width = 13
        ws.freeze_panes = ws.cell(row=header_row + 1, column=3)


def write_all_metrics(ws, paper, popularity, diseases):
    """Long table: every disease x every metric x every method."""
    labels = [m[0] for m in METHODS]
    ws.cell(row=1, column=1, value="All metrics, all diseases, all configurations").font = Font(bold=True, size=12)
    ws.cell(row=2, column=1, value="Popularity values are the median over 20 tie-break orderings; "
                                   "see the 'Popularity detail' sheet for [min-max] ranges.").font = Font(italic=True, size=9)

    row = 4
    headers = ["Disease", "Metric"] + labels + ["Pop. range (min-max)"]
    for j, text in enumerate(headers, start=1):
        ws.cell(row=row, column=j, value=text)
    style_header(ws, row, len(headers))
    ws.freeze_panes = ws.cell(row=row + 1, column=3)
    row += 1

    for key, display, _ in diseases:
        first = row
        for metric_key, label, fmt, lower_better in METRIC_SPEC:
            ws.cell(row=row, column=1, value=display).font = Font(size=9)
            ws.cell(row=row, column=2, value=label)
            values = []
            for j, (name, source, tag, _) in enumerate(METHODS):
                val = get(paper, popularity, name, source, tag, key, metric_key)
                cell = ws.cell(row=row, column=3 + j, value=val)
                cell.number_format = fmt
                cell.border = BOX
                cell.alignment = Alignment(horizontal="center")
                if source.startswith("popularity"):
                    cell.fill = POP_FILL
                values.append(val)

            primary = popularity["popularity"]
            lo = primary.get(key, {}).get(metric_key + "_lo")
            hi = primary.get(key, {}).get(metric_key + "_hi")
            if isinstance(lo, float) and isinstance(hi, float):
                digits = 0 if "rank" in metric_key else (2 if "fold" in metric_key else 4)
                band = "{:.{d}f} - {:.{d}f}".format(lo, hi, d=digits)
                cell = ws.cell(row=row, column=3 + len(labels), value=band)
                cell.alignment = Alignment(horizontal="center")
                cell.font = Font(size=9, italic=True)
                # Flag bands wide enough that the point estimate is meaningless.
                if hi > 0 and lo / hi < 0.5 if lo else hi > 0:
                    cell.font = Font(size=9, italic=True, color="C00000")

            present = [v for v in values if isinstance(v, (int, float))]
            if present:
                best = min(present) if lower_better else max(present)
                for j, val in enumerate(values):
                    if val == best:
                        ws.cell(row=row, column=3 + j).fill = BEST_FILL
            row += 1

        # universe size / target count footer per disease
        ws.cell(row=row, column=2, value="Universe size").font = Font(size=9, italic=True)
        for j, (name, source, tag, _) in enumerate(METHODS):
            ws.cell(row=row, column=3 + j,
                    value=get(paper, popularity, name, source, tag, key, "universe_size")
                    ).font = Font(size=9, italic=True)
        row += 1
        ws.cell(row=row, column=2, value="Targets found").font = Font(size=9, italic=True)
        for j, (name, source, tag, _) in enumerate(METHODS):
            ws.cell(row=row, column=3 + j,
                    value=get(paper, popularity, name, source, tag, key, "num_targets_found")
                    ).font = Font(size=9, italic=True)
        row += 1

        for col in range(1, len(headers) + 1):
            ws.cell(row=first, column=col).border = Border(top=Side(style="medium", color="1F3864"))
        row += 1

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 24
    for j in range(len(labels)):
        ws.column_dimensions[get_column_letter(3 + j)].width = 12
    ws.column_dimensions[get_column_letter(3 + len(labels))].width = 20


def write_recall_k(ws, paper, popularity, diseases):
    """R1.11: is the conclusion stable across K?"""
    labels = [m[0] for m in METHODS]
    ws.cell(row=1, column=1, value="Recall@K across K (Reviewer 1, comment 11)").font = Font(bold=True, size=12)
    ws.cell(row=2, column=1, value="If the ordering of methods is preserved across K, the conclusion does not "
                                   "depend on an arbitrary threshold.").font = Font(italic=True, size=9)

    row = 4
    headers = ["Disease", "K"] + labels + ["KI-GNN beats popularity?"]
    for j, text in enumerate(headers, start=1):
        ws.cell(row=row, column=j, value=text)
    style_header(ws, row, len(headers))
    ws.freeze_panes = ws.cell(row=row + 1, column=3)
    row += 1

    for key, display, _ in diseases:
        for metric_key in RECALL_K:
            k = metric_key.rsplit("_", 1)[1]
            ws.cell(row=row, column=1, value=display).font = Font(size=9)
            ws.cell(row=row, column=2, value=int(k)).alignment = Alignment(horizontal="center")
            values = {}
            for j, (name, source, tag, _) in enumerate(METHODS):
                val = get(paper, popularity, name, source, tag, key, metric_key)
                cell = ws.cell(row=row, column=3 + j, value=val)
                cell.number_format = "0.0000"
                cell.border = BOX
                cell.alignment = Alignment(horizontal="center")
                if source.startswith("popularity"):
                    cell.fill = POP_FILL
                values[name] = val

            # Compare against the top of the popularity band, not its median.
            pop_hi = popularity["popularity"].get(key, {}).get(metric_key + "_hi")
            kignn = values.get("KI-GNN")
            verdict = ""
            if isinstance(kignn, (int, float)) and isinstance(pop_hi, (int, float)):
                verdict = "yes" if kignn > pop_hi else ("tie" if kignn == pop_hi else "no")
            cell = ws.cell(row=row, column=3 + len(labels), value=verdict)
            cell.alignment = Alignment(horizontal="center")
            if verdict == "yes":
                cell.fill = BEST_FILL
            elif verdict == "no":
                cell.fill = PatternFill("solid", fgColor="F8CBAD")
            row += 1
        row += 1

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 8
    for j in range(len(labels)):
        ws.column_dimensions[get_column_letter(3 + j)].width = 12
    ws.column_dimensions[get_column_letter(3 + len(labels))].width = 24


def write_popularity_detail(ws, primary, diseases):
    ws.cell(row=1, column=1, value="Popularity baseline - full output with tie-break ranges").font = Font(bold=True, size=12)
    ws.cell(row=2, column=1, value="Median [min - max] over 20 random tie-break orderings. A wide range means "
                                   "the metric is set by tie-breaking rather than by paper count.").font = Font(italic=True, size=9)

    row = 4
    headers = ["Disease", "Universe", "Targets", "% tied at cap",
               "Targets tied at cap"] + [label for _, label, _, _ in METRIC_SPEC]
    for j, text in enumerate(headers, start=1):
        ws.cell(row=row, column=j, value=text)
    style_header(ws, row, len(headers))
    ws.freeze_panes = ws.cell(row=row + 1, column=2)
    row += 1

    for key, display, group in diseases:
        data = primary.get(key)
        if not data:
            continue
        ws.cell(row=row, column=1, value=display).font = BOLD
        ws.cell(row=row, column=2, value=data.get("universe_size"))
        ws.cell(row=row, column=3, value=data.get("num_targets_found"))
        ws.cell(row=row, column=4, value=data.get("pct_tied_at_max")).number_format = "0.0"
        ws.cell(row=row, column=5, value=data.get("n_targets_tied_at_max"))
        for j, (metric_key, _, fmt, _) in enumerate(METRIC_SPEC):
            lo, hi = data.get(metric_key + "_lo"), data.get(metric_key + "_hi")
            digits = 0 if "rank" in metric_key else (2 if "fold" in metric_key else 4)
            text = "{:.{d}f}  [{:.{d}f} - {:.{d}f}]".format(
                data.get(metric_key, 0), lo or 0, hi or 0, d=digits)
            cell = ws.cell(row=row, column=6 + j, value=text)
            cell.alignment = Alignment(horizontal="center")
            cell.font = Font(size=9)
            if group == "Not in manuscript":
                cell.font = Font(size=9, color="808080")
        row += 1

    ws.column_dimensions["A"].width = 26
    for j in range(2, 6):
        ws.column_dimensions[get_column_letter(j)].width = 13
    for j in range(len(METRIC_SPEC)):
        ws.column_dimensions[get_column_letter(6 + j)].width = 22


def write_literature_bias(ws, primary, diseases):
    ws.cell(row=1, column=1, value="Literature-volume bias check (Reviewer 1, comment 6)").font = Font(bold=True, size=12)
    note = ("Median rank, on paper count alone, of genes already on the panel at 2022-09 "
            "('known') versus genes added afterwards ('new'). If curated disease genes were "
            "simply the well-studied genes, the 'known' column would sit near the top of the "
            "~19,000-gene list. CAVEAT: the 100-PMID cap compresses exactly the well-studied "
            "end, so this check is the one most weakened by the cap and should be repeated "
            "with uncapped counts before being relied upon.")
    cell = ws.cell(row=2, column=1, value=note)
    cell.font = Font(italic=True, size=9)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 55

    row = 4
    headers = ["Disease", "Known genes (n)", "Median rank of known",
               "New genes (n)", "Median rank of new", "Universe"]
    for j, text in enumerate(headers, start=1):
        ws.cell(row=row, column=j, value=text)
    style_header(ws, row, len(headers))
    row += 1

    for key, display, _ in diseases:
        data = primary.get(key)
        if not data:
            continue
        ws.cell(row=row, column=1, value=display).font = BOLD
        ws.cell(row=row, column=2, value=data.get("n_seen_true_positives"))
        ws.cell(row=row, column=3, value=data.get("median_rank_seen")).number_format = "0"
        ws.cell(row=row, column=4, value=data.get("num_targets_found"))
        ws.cell(row=row, column=5, value=data.get("median_rank_unseen")).number_format = "0"
        ws.cell(row=row, column=6, value=data.get("universe_size"))
        for col in range(1, len(headers) + 1):
            ws.cell(row=row, column=col).border = BOX
            if col > 1:
                ws.cell(row=row, column=col).alignment = Alignment(horizontal="center")
        row += 1

    ws.column_dimensions["A"].width = 26
    for j in range(2, len(headers) + 1):
        ws.column_dimensions[get_column_letter(j)].width = 20


DISEASE_TARGET_FILES = {
    "dee": "DEE-2025_03_vs_2022_09.txt",
    "ad_dee": "AD_DEE-2022_09_to_2025_03.txt",
    "ar_dee": "AR_DEE-2022_09_to_2025_03.txt",
    "aminoacidopathy": "Aminoacidopathy-2025_06_vs_2022_09.txt",
    "arthrogryposis": "Arthrogryposis-2025_06_vs_2022_09.txt",
    "ataxia": "Ataxia_paed-2025_06_vs_2022_09.txt",
    "cp": "CP-2025_06_vs_2022_09.txt",
    "intellectual_disability": "Intellectual-disability-2025_06_vs_2022_09.txt",
    "microcephaly": "Microcephaly-2025_06_vs_2022_09.txt",
    "mnd": "MND-2025_06_vs_2022_09.txt",
    "skeletal_dysplasia": "Skeletal-dysplasia-diff-2025_06_vs_2022_09.txt",
    "platelet_disorder": "Bleeding_and_Platelet_Disorders-2026-02_vs_2022-09.txt",
    "bone_marrow_failure": "Bone_Marrow_Failure-2026-02_vs_2022-09.txt",
    "cataract": "Cataract-2026-02_vs_2022-09.txt",
}


def write_temporal_evidence(ws, counts_path, disease_dir, diseases):
    """R1.7: did post-split target genes already have disease literature pre-cutoff?"""
    ws.cell(row=1, column=1,
            value="Prior disease literature before the cutoff (Reviewer 1, comment 7)").font = Font(bold=True, size=12)
    note = ("R1.7: \"A gene added to a panel in 2024 may already have had substantial "
            "disease-related literature before September 2022 ... otherwise this experiment may "
            "partly measure prediction of subsequent panel inclusion rather than genuine feature "
            "discovery.\"  For every post-split target gene we counted its PRE-CUTOFF PubMed "
            "papers that mention the disease by keyword. Genes with zero such papers form the "
            "conservative 'genuinely novel' stratum, for which the temporal split cannot be "
            "measuring curation lag. Keyword matching favours recall, so the prior-evidence share "
            "is an UPPER bound and the novel stratum is correspondingly conservative. Note this is "
            "a proxy for a curated gene-disease assertion, not proof of one.")
    cell = ws.cell(row=2, column=1, value=note)
    cell.font = Font(italic=True, size=9)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 75

    with open(counts_path) as handle:
        counts = {r["gene"]: r for r in csv.DictReader(handle, delimiter="\t")}

    row = 4
    headers = ["Disease", "Targets", "With prior evidence", "% prior",
               "Genuinely novel", "% novel", "With >=3 prior papers"]
    for j, text in enumerate(headers, start=1):
        ws.cell(row=row, column=j, value=text)
    style_header(ws, row, len(headers))
    row += 1

    totals = [0, 0, 0]
    for key, display, _ in diseases:
        target_file = DISEASE_TARGET_FILES.get(key)
        if not target_file:
            continue
        path = os.path.join(disease_dir, target_file)
        if not os.path.exists(path):
            continue
        with open(path) as handle:
            targets = [g.strip() for g in handle if g.strip()]
        targets = [g for g in targets if g in counts]
        column = key + "_evidence"
        if not targets or column not in next(iter(counts.values())):
            continue
        prior = [g for g in targets if int(counts[g][column]) > 0]
        strong = [g for g in targets if int(counts[g][column]) >= 3]
        totals[0] += len(targets)
        totals[1] += len(prior)
        totals[2] += len(strong)

        ws.cell(row=row, column=1, value=display).font = BOLD
        ws.cell(row=row, column=2, value=len(targets))
        ws.cell(row=row, column=3, value=len(prior))
        ws.cell(row=row, column=4, value=len(prior) / len(targets)).number_format = "0%"
        ws.cell(row=row, column=5, value=len(targets) - len(prior))
        ws.cell(row=row, column=6, value=1 - len(prior) / len(targets)).number_format = "0%"
        ws.cell(row=row, column=7, value=len(strong))
        for col in range(1, len(headers) + 1):
            ws.cell(row=row, column=col).border = BOX
            if col > 1:
                ws.cell(row=row, column=col).alignment = Alignment(horizontal="center")
        # Flag diseases where most targets already had literature.
        if len(prior) / len(targets) >= 0.5:
            ws.cell(row=row, column=4).fill = PatternFill("solid", fgColor="F8CBAD")
        row += 1

    if totals[0]:
        ws.cell(row=row, column=1, value="ALL").font = BOLD
        ws.cell(row=row, column=2, value=totals[0]).font = BOLD
        ws.cell(row=row, column=3, value=totals[1]).font = BOLD
        ws.cell(row=row, column=4, value=totals[1] / totals[0]).number_format = "0%"
        ws.cell(row=row, column=5, value=totals[0] - totals[1]).font = BOLD
        ws.cell(row=row, column=6, value=1 - totals[1] / totals[0]).number_format = "0%"
        ws.cell(row=row, column=7, value=totals[2]).font = BOLD
        for col in range(1, len(headers) + 1):
            ws.cell(row=row, column=col).border = Border(top=Side(style="medium", color="1F3864"))
            if col > 1:
                ws.cell(row=row, column=col).alignment = Alignment(horizontal="center")
        row += 2

    ws.cell(row=row, column=1,
            value="OUTSTANDING: every reported metric still needs re-running separately on the "
                  "novel stratum versus the prior-evidence stratum. That is the actual answer to "
                  "R1.7 and requires the per-gene model prediction files.").font = Font(
        italic=True, size=9, color="C00000")

    ws.column_dimensions["A"].width = 30
    for j in range(2, len(headers) + 1):
        ws.column_dimensions[get_column_letter(j)].width = 20


REVISION_METRICS = [
    ("median_rank_unseen", "Median rank", 1, True),
    ("mean_rank_unseen", "Mean rank", 1, True),
    ("fold_enrichment_top_1_pct", "Fold enr. @1%", 2, False),
    ("fold_enrichment_top_5_pct", "Fold enr. @5%", 2, False),
    ("recall_at_50", "Recall @50", 4, False),
    ("recall_at_100", "Recall @100", 4, False),
    ("recall_at_250", "Recall @250", 4, False),
    ("recall_at_1000", "Recall @1000", 4, False),
]

REVISION_METHOD_ORDER = ["GNN", "C-GNN", "KI-GNN", "Late-fusion"]
CONTRAST_ORDER = ["KI-GNN - GNN", "KI-GNN - C-GNN", "Late-fusion - KI-GNN"]


def load_tsv(path):
    if not path or not os.path.exists(path):
        return []
    with open(path) as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def _number(row, key, digits):
    try:
        return round(float(row[key]), digits)
    except (TypeError, ValueError, KeyError):
        return None


def write_bootstrap_cis(ws, rows, diseases):
    """R1.10: every metric with a bootstrap confidence interval."""
    ws.cell(row=1, column=1,
            value="Bootstrap confidence intervals (Reviewer 1, comment 10)").font = Font(bold=True, size=12)
    note = ("R1.10 asks for confidence intervals in the main results. Each interval is a 95% "
            "percentile bootstrap over 2,000 resamples of that disease's post-split target "
            "genes, holding the model fixed. It answers: how much of the reported value is an "
            "accident of which genes happened to be curated after the cutoff? Point estimates "
            "reproduce the published numbers exactly - the metric code is copied from "
            "results_processing/evaluate_results.py. 'Late-fusion' is not a published "
            "configuration; see the 'Late fusion' sheet.")
    cell = ws.cell(row=2, column=1, value=note)
    cell.font = Font(italic=True, size=9)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 60

    indexed = {(r["disease"], r["method"]): r for r in rows}

    row = 4
    headers = ["Disease", "Method", "Experiment", "Targets"] + \
              [label for _, label, _, _ in REVISION_METRICS]
    for j, text in enumerate(headers, start=1):
        ws.cell(row=row, column=j, value=text)
    style_header(ws, row, len(headers))
    ws.freeze_panes = ws.cell(row=row + 1, column=3)
    row += 1

    for key, display, _ in diseases:
        first = row
        for method in REVISION_METHOD_ORDER:
            record = indexed.get((key, method))
            if not record:
                continue
            ws.cell(row=row, column=1, value=display).font = Font(size=9)
            ws.cell(row=row, column=2, value=method).font = (
                BOLD if method == "KI-GNN" else Font(size=10))
            ws.cell(row=row, column=3, value=record.get("experiment"))
            ws.cell(row=row, column=4, value=_number(record, "n_targets", 0))
            for j, (metric, _, digits, _) in enumerate(REVISION_METRICS):
                point = _number(record, metric, digits)
                lo = _number(record, metric + "_lo", digits)
                hi = _number(record, metric + "_hi", digits)
                if point is None:
                    continue
                text = "{:g}".format(point)
                if lo is not None and hi is not None:
                    text += "  [{:g}, {:g}]".format(lo, hi)
                cell = ws.cell(row=row, column=5 + j, value=text)
                cell.alignment = Alignment(horizontal="center")
                cell.font = Font(size=9)
                cell.border = BOX
                if method == "Late-fusion":
                    cell.fill = POP_FILL
            row += 1
        if row > first:
            for col in range(1, len(headers) + 1):
                ws.cell(row=first, column=col).border = Border(
                    top=Side(style="medium", color="1F3864"))

    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 13
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 9
    for j in range(len(REVISION_METRICS)):
        ws.column_dimensions[get_column_letter(5 + j)].width = 24


def write_paired_contrasts(ws, rows, diseases):
    """R1.10 done properly: paired difference on the same genes."""
    ws.cell(row=1, column=1,
            value="Paired contrasts (Reviewer 1, comment 10)").font = Font(bold=True, size=12)
    note = ("Comparing two marginal confidence intervals is the wrong test and is badly "
            "under-powered: both models are scored on the SAME post-split genes, so "
            "'these targets are hard for everyone' inflates both intervals and masks real "
            "differences. Each row below resamples genes once per draw and takes the "
            "difference, which cancels that shared difficulty. Negative favours the first "
            "model for rank metrics (lower rank is better) and the second for recall and "
            "enrichment. 'Significant' means the 95% interval excludes zero. "
            "Validation: two models differing by a certain 50 ranks produced almost entirely "
            "overlapping marginal intervals, while this test recovered -50 [-50, -50].")
    cell = ws.cell(row=2, column=1, value=note)
    cell.font = Font(italic=True, size=9)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 75

    indexed = {(r["disease"], r["contrast"]): r for r in rows}

    row = 4
    headers = ["Disease", "Contrast", "Paired genes"] + \
              [label for _, label, _, _ in REVISION_METRICS]
    for j, text in enumerate(headers, start=1):
        ws.cell(row=row, column=j, value=text)
    style_header(ws, row, len(headers))
    ws.freeze_panes = ws.cell(row=row + 1, column=3)
    row += 1

    for key, display, _ in diseases:
        first = row
        for contrast in CONTRAST_ORDER:
            record = indexed.get((key, contrast))
            if not record:
                continue
            ws.cell(row=row, column=1, value=display).font = Font(size=9)
            ws.cell(row=row, column=2, value=contrast)
            ws.cell(row=row, column=3, value=_number(record, "n_paired_targets", 0))
            for j, (metric, _, digits, lower_better) in enumerate(REVISION_METRICS):
                difference = _number(record, metric, digits)
                lo = _number(record, metric + "_lo", digits)
                hi = _number(record, metric + "_hi", digits)
                if difference is None:
                    continue
                significant = record.get(metric + "_sig") == "yes"
                text = "{:+g}".format(difference)
                if lo is not None and hi is not None:
                    text += "  [{:+g}, {:+g}]".format(lo, hi)
                cell = ws.cell(row=row, column=4 + j, value=text)
                cell.alignment = Alignment(horizontal="center")
                cell.font = Font(size=9, bold=significant)
                cell.border = BOX
                if significant:
                    # Does the significant difference favour the first model?
                    favours_first = (difference < 0) if lower_better else (difference > 0)
                    cell.fill = BEST_FILL if favours_first else PatternFill(
                        "solid", fgColor="F8CBAD")
            row += 1
        if row > first:
            for col in range(1, len(headers) + 1):
                ws.cell(row=first, column=col).border = Border(
                    top=Side(style="medium", color="1F3864"))

    row += 1
    ws.cell(row=row, column=1,
            value="Green = significant and favours the first model. "
                  "Orange = significant and favours the second.").font = Font(italic=True, size=9)

    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 13
    for j in range(len(REVISION_METRICS)):
        ws.column_dimensions[get_column_letter(4 + j)].width = 26


def write_late_fusion(ws, metric_rows, contrast_rows, diseases):
    """R1.5d and R4.1: concatenation versus log-odds summation."""
    ws.cell(row=1, column=1,
            value="Late fusion vs concatenation (Reviewer 1 comment 5d; Reviewer 4 comment 1)").font = Font(bold=True, size=12)
    note = ("R1 asked for 'the current concatenation strategy versus learned or late fusion'. "
            "R4 asked for the two-context idea to be cast as Bayesian inference, a prior "
            "integrated with a likelihood. These are the same experiment: summing the "
            "log-odds of the knowledge-only model (C-GNN) and the experimental-only model "
            "(GNN) IS prior x likelihood under conditional independence. Late fusion is "
            "therefore both the alternative fusion strategy and the Bayesian formulation. "
            "It requires no retraining - it recombines predictions the manuscript already "
            "reports. Where concatenation (KI-GNN) wins, the conditional independence "
            "assumption is failing: literature-derived knowledge and experimental signal are "
            "correlated, and a jointly-learned representation captures structure that naive "
            "Bayesian combination cannot.")
    cell = ws.cell(row=2, column=1, value=note)
    cell.font = Font(italic=True, size=9)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 90

    by_method = {(r["disease"], r["method"]): r for r in metric_rows}
    by_contrast = {r["disease"]: r for r in contrast_rows
                   if r["contrast"] == "Late-fusion - KI-GNN"}

    row = 4
    headers = ["Disease", "GNN", "C-GNN", "KI-GNN (concat)", "Late fusion",
               "Difference (fusion - concat)", "95% CI", "Significant", "Winner"]
    for j, text in enumerate(headers, start=1):
        ws.cell(row=row, column=j, value=text)
    style_header(ws, row, len(headers))
    row += 1

    wins = {"concatenation": 0, "late fusion": 0, "no difference": 0}
    for key, display, _ in diseases:
        fusion = by_method.get((key, "Late-fusion"))
        concat = by_method.get((key, "KI-GNN"))
        if not fusion or not concat:
            continue
        contrast = by_contrast.get(key)

        ws.cell(row=row, column=1, value=display).font = BOLD
        for j, method in enumerate(["GNN", "C-GNN", "KI-GNN", "Late-fusion"]):
            record = by_method.get((key, method))
            ws.cell(row=row, column=2 + j,
                    value=_number(record, "median_rank_unseen", 1) if record else None
                    ).alignment = Alignment(horizontal="center")

        if contrast:
            difference = _number(contrast, "median_rank_unseen", 1)
            lo = _number(contrast, "median_rank_unseen_lo", 1)
            hi = _number(contrast, "median_rank_unseen_hi", 1)
            significant = contrast.get("median_rank_unseen_sig") == "yes"
            ws.cell(row=row, column=6, value=difference).alignment = Alignment(horizontal="center")
            ws.cell(row=row, column=7,
                    value="[{:+g}, {:+g}]".format(lo, hi) if lo is not None else ""
                    ).alignment = Alignment(horizontal="center")
            ws.cell(row=row, column=8, value="yes" if significant else "no"
                    ).alignment = Alignment(horizontal="center")
            if significant:
                winner = "concatenation" if difference > 0 else "late fusion"
            else:
                winner = "no difference"
            wins[winner] += 1
            cell = ws.cell(row=row, column=9, value=winner)
            cell.alignment = Alignment(horizontal="center")
            cell.font = Font(bold=significant, size=10)
            if winner == "concatenation":
                cell.fill = BEST_FILL
            elif winner == "late fusion":
                cell.fill = PatternFill("solid", fgColor="F8CBAD")

        for col in range(1, len(headers) + 1):
            ws.cell(row=row, column=col).border = BOX
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Significant wins:").font = BOLD
    ws.cell(row=row, column=2,
            value="concatenation {}, late fusion {}, no difference {}".format(
                wins["concatenation"], wins["late fusion"], wins["no difference"]))

    ws.column_dimensions["A"].width = 30
    for j in range(2, 6):
        ws.column_dimensions[get_column_letter(j)].width = 15
    ws.column_dimensions["F"].width = 28
    ws.column_dimensions["G"].width = 20
    ws.column_dimensions["H"].width = 12
    ws.column_dimensions["I"].width = 16


# The R1.5b 2x2: which half of KI-GNN does the work, the PubMed node features
# or the knowledge-graph edges? Cell -> (features, graph, method name).
# Uses the "(rerun)" variants so all four cells come from the same code path,
# universe (16,546) and target count (192). The published GNN and KI-GNN runs
# are reserved for Table 1 reproduction.
ABLATION_GRID = [
    ("expression only", "PPI graph", "GNN (rerun)"),
    ("expression only", "knowledge graph", "GNN-KG"),
    ("expression + PubMed", "PPI graph", "KIGNN-PPI"),
    ("expression + PubMed", "knowledge graph", "KI-GNN (rerun)"),
]
ABLATION_ROWS = ["expression only", "expression + PubMed"]
ABLATION_COLS = ["PPI graph", "knowledge graph"]

# (contrast label as written by revision_analysis.py, what it isolates)
ABLATION_CONTRAST_LABELS = [
    ("KIGNN-PPI - GNN (rerun)", "add PubMed features (PPI graph held fixed)"),
    ("KI-GNN (rerun) - GNN-KG", "add PubMed features (knowledge graph held fixed)"),
    ("GNN-KG - GNN (rerun)", "swap to knowledge graph (expression only)"),
    ("KI-GNN (rerun) - KIGNN-PPI", "swap to knowledge graph (both feature sets)"),
    ("KIMLP - KI-GNN (rerun)", "remove message passing entirely (R1.5e)"),
    ("GNN (rerun) - GNN", "reproduction check: same config, different run"),
    ("KI-GNN (rerun) - KI-GNN", "reproduction check: same config, different run"),
]

ABLATION_METRICS = [
    ("median_rank_unseen", "Median rank", 1, True),
    ("fold_enrichment_top_1_pct", "Fold enrichment @1%", 2, False),
    ("recall_at_100", "Recall @100", 4, False),
    ("recall_at_1000", "Recall @1000", 4, False),
]


def write_ablations(ws, metric_rows, contrast_rows, diseases, disease="dee"):
    """R1.5b and R1.5e. Fills in as runs land; absent cells stay blank."""
    ws.cell(row=1, column=1,
            value="Component ablations (Reviewer 1, comments 5b and 5e)").font = Font(bold=True, size=12)
    note = ("R1.5b: \"ablations separating ... PubMed node features versus KG edges within "
            "KI-GNN\". KI-GNN differs from GNN in two ways at once - it adds PubMed node "
            "features AND swaps the baseline PPI graph for the knowledge graph - so the 2x2 "
            "below holds one factor fixed while varying the other. R1.5e: \"GNN message "
            "passing versus a non-graph model using exactly the same node features\"; KIMLP is "
            "KI-GNN with mp.n_layers = 0, so message passing is removed while features, "
            "pre/post-MP depth and width, training and folds are unchanged. "
            "All runs are {} unless noted.".format(disease.upper()))
    cell = ws.cell(row=2, column=1, value=note)
    cell.font = Font(italic=True, size=9)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 75

    by_method = {r["method"]: r for r in metric_rows if r["disease"] == disease}
    by_contrast = {r["contrast"]: r for r in contrast_rows if r["disease"] == disease}

    row = 4
    for metric, label, digits, lower_better in ABLATION_METRICS:
        ws.cell(row=row, column=1,
                value="{}  ({} is better)".format(
                    label, "lower" if lower_better else "higher")).font = Font(bold=True, size=11)
        row += 1
        ws.cell(row=row, column=1, value="")
        for j, column_label in enumerate(ABLATION_COLS):
            ws.cell(row=row, column=2 + j, value=column_label)
        style_header(ws, row, 1 + len(ABLATION_COLS))
        row += 1

        present = []
        for features in ABLATION_ROWS:
            ws.cell(row=row, column=1, value=features).font = BOLD
            for j, graph in enumerate(ABLATION_COLS):
                method = next((m for f, g, m in ABLATION_GRID
                               if f == features and g == graph), None)
                record = by_method.get(method)
                cell = ws.cell(row=row, column=2 + j)
                if record is None:
                    cell.value = "not yet run"
                    cell.font = Font(size=9, italic=True, color="808080")
                else:
                    value = _number(record, metric, digits)
                    lo = _number(record, metric + "_lo", digits)
                    hi = _number(record, metric + "_hi", digits)
                    text = "{:g}".format(value) if value is not None else ""
                    if lo is not None and hi is not None:
                        text += "  [{:g}, {:g}]".format(lo, hi)
                    cell.value = text
                    present.append((value, cell))
                cell.alignment = Alignment(horizontal="center")
                cell.border = BOX
            row += 1

        values = [v for v, _ in present if v is not None]
        if values:
            best = min(values) if lower_better else max(values)
            for value, cell in present:
                if value == best:
                    cell.fill = BEST_FILL
                    cell.font = BOLD
        row += 1

    # Paired contrasts: the actual test of each main effect.
    ws.cell(row=row, column=1,
            value="Paired contrasts - is the difference real?").font = Font(bold=True, size=11)
    row += 1
    ws.cell(row=row, column=1, value="Contrast")
    ws.cell(row=row, column=2, value="Isolates")
    for j, (_, label, _, _) in enumerate(ABLATION_METRICS):
        ws.cell(row=row, column=3 + j, value=label)
    style_header(ws, row, 2 + len(ABLATION_METRICS))
    row += 1

    for contrast, meaning in ABLATION_CONTRAST_LABELS:
        record = by_contrast.get(contrast)
        ws.cell(row=row, column=1, value=contrast).font = Font(size=9)
        ws.cell(row=row, column=2, value=meaning).font = Font(size=9, italic=True)
        for j, (metric, _, digits, lower_better) in enumerate(ABLATION_METRICS):
            cell = ws.cell(row=row, column=3 + j)
            if record is None:
                cell.value = "not yet run"
                cell.font = Font(size=9, italic=True, color="808080")
            else:
                difference = _number(record, metric, digits)
                lo = _number(record, metric + "_lo", digits)
                hi = _number(record, metric + "_hi", digits)
                significant = record.get(metric + "_sig") == "yes"
                text = "{:+g}".format(difference) if difference is not None else ""
                if lo is not None and hi is not None:
                    text += "  [{:+g}, {:+g}]".format(lo, hi)
                cell.value = text
                cell.font = Font(size=9, bold=significant)
                if significant and difference is not None:
                    favours_first = (difference < 0) if lower_better else (difference > 0)
                    cell.fill = BEST_FILL if favours_first else PatternFill(
                        "solid", fgColor="F8CBAD")
            cell.alignment = Alignment(horizontal="center")
            cell.border = BOX
        row += 1

    # R1.5e across every disease where the no-message-passing run exists.
    row += 1
    ws.cell(row=row, column=1,
            value="R1.5e across diseases - what does message passing contribute?").font = Font(bold=True, size=11)
    row += 1
    for j, text in enumerate(["Disease", "n targets", "KIMLP - KI-GNN (median rank)",
                              "95% CI", "Significant", "Reading"]):
        ws.cell(row=row, column=1 + j, value=text)
    style_header(ws, row, 6)
    row += 1
    for key, display, _ in diseases:
        record = next((r for r in contrast_rows
                       if r["disease"] == key
                       and r["contrast"] == "KIMLP - KI-GNN (rerun)"), None)
        if not record:
            continue
        difference = _number(record, "median_rank_unseen", 1)
        lo = _number(record, "median_rank_unseen_lo", 1)
        hi = _number(record, "median_rank_unseen_hi", 1)
        significant = record.get("median_rank_unseen_sig") == "yes"
        ws.cell(row=row, column=1, value=display).font = BOLD
        ws.cell(row=row, column=2, value=_number(record, "n_paired_targets", 0))
        ws.cell(row=row, column=3, value="{:+g}".format(difference))
        ws.cell(row=row, column=4, value="[{:+g}, {:+g}]".format(lo, hi))
        ws.cell(row=row, column=5, value="yes" if significant else "no")
        ws.cell(row=row, column=6,
                value="message passing helps" if significant
                      else "not detectable at this n")
        for col in range(1, 7):
            cell = ws.cell(row=row, column=col)
            cell.border = BOX
            if col > 1:
                cell.alignment = Alignment(horizontal="center")
            if significant:
                cell.font = BOLD
        row += 1

    row += 1
    for text in [
        "Positive differences mean the no-message-passing model ranks targets WORSE, i.e. "
        "message passing helps. The direction is the same on both diseases; only the "
        "magnitude and the power differ. The claim to make is therefore that message "
        "passing contributes significantly on Cerebral Palsy and is not detectable on DEE "
        "at n = 192 - not that it contributes nothing.",
        "Bold = 95% paired bootstrap interval excludes zero. Green favours the first model, "
        "orange the second. Negative differences favour the first model for rank metrics.",
        "All four grid cells come from the same code path, universe (16,546 genes) and "
        "target set (192), so the comparison is internally consistent. Run-to-run variance "
        "was measured directly by repeating the published configurations: GNN +87 and "
        "KI-GNN -50 ranks, neither significant. Both reproduce the published values, and "
        "the variance is smaller than the effects reported above.",
    ]:
        cell = ws.cell(row=row, column=1, value=text)
        cell.font = Font(italic=True, size=9)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[row].height = 28
        row += 1

    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 42
    for j in range(len(ABLATION_METRICS)):
        ws.column_dimensions[get_column_letter(3 + j)].width = 26


MODEL_CLASS_ORDER = ["Logistic regression", "Random forest", "Gradient boosting", "MLP"]
MODEL_CLASS_FEATURES = ["LL (expression)", "HL (PubMed)", "LL+HL (KIML)"]


def write_model_classes(ws, rows, diseases):
    """R1.3: is the knowledge benefit specific to RF and the GNN?"""
    ws.cell(row=1, column=1,
            value="Knowledge inclusion across model classes (Reviewer 1, comment 3)").font = Font(bold=True, size=12)
    note = ("R1.3: \"The framework is claimed to be general, but experimentally, it is highly "
            "selective towards RF and one GNN implementation ... I am not suggesting that the "
            "authors test all of these, but merely highlighting that the choice made by them "
            "needs to be defended well enough.\"  The question is therefore narrow: is the "
            "reported benefit a property of the knowledge features, or an artefact of the two "
            "model classes chosen? These runs use the manuscript's own feature files - the same "
            "cortical expression and PubMed embedding matrices the GNN consumes - and the same "
            "positive and target gene lists, passed through four deliberately untuned "
            "classifiers. Tuning is avoided on purpose: the claim under test is directional, and "
            "tuning would invite the benchmark comparison the reviewer said was unnecessary. "
            "Gradient boosting stands in for the XGBoost he named. Unlabelled genes are scored "
            "out of fold, so no gene is ranked by a model that used it as a negative.")
    cell = ws.cell(row=2, column=1, value=note)
    cell.font = Font(italic=True, size=9)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 100

    indexed = {(r["disease"], r["model"], r["features"]): r for r in rows}
    present = sorted({r["disease"] for r in rows})

    row = 4
    for key, display, _ in diseases:
        if key not in present:
            continue
        ws.cell(row=row, column=1, value=display).font = Font(bold=True, size=11)
        row += 1
        ws.cell(row=row, column=1, value="Model")
        for j, feature in enumerate(MODEL_CLASS_FEATURES):
            ws.cell(row=row, column=2 + j, value=feature)
        ws.cell(row=row, column=5, value="LL+HL minus LL")
        ws.cell(row=row, column=6, value="Knowledge helps?")
        style_header(ws, row, 6)
        row += 1

        helped = total = 0
        for model in MODEL_CLASS_ORDER:
            records = [indexed.get((key, model, f)) for f in MODEL_CLASS_FEATURES]
            if not any(records):
                continue
            ws.cell(row=row, column=1, value=model).font = BOLD
            values = []
            for j, record in enumerate(records):
                value = _number(record, "median_rank_unseen", 1) if record else None
                lo = _number(record, "median_rank_unseen_lo", 1) if record else None
                hi = _number(record, "median_rank_unseen_hi", 1) if record else None
                text = ""
                if value is not None:
                    text = "{:g}".format(value)
                    if lo is not None and hi is not None:
                        text += "  [{:g}, {:g}]".format(lo, hi)
                cell = ws.cell(row=row, column=2 + j, value=text)
                cell.alignment = Alignment(horizontal="center")
                cell.font = Font(size=9)
                cell.border = BOX
                values.append(value)

            ll, _hl, both = values
            if ll is not None and both is not None:
                delta = both - ll
                total += 1
                if delta < 0:
                    helped += 1
                cell = ws.cell(row=row, column=5, value=round(delta, 1))
                cell.number_format = "+0.0;-0.0"
                cell.alignment = Alignment(horizontal="center")
                cell.border = BOX
                verdict = ws.cell(row=row, column=6,
                                  value="yes" if delta < 0 else "no")
                verdict.alignment = Alignment(horizontal="center")
                verdict.border = BOX
                verdict.fill = BEST_FILL if delta < 0 else PatternFill(
                    "solid", fgColor="F8CBAD")
            row += 1

        ws.cell(row=row, column=1,
                value="knowledge inclusion improves median rank in {}/{} model classes".format(
                    helped, total)).font = Font(italic=True, size=9, bold=True)
        row += 2

    ws.cell(row=row, column=1,
            value="Lower median rank is better. Intervals are 95% bootstrap over the target "
                  "genes, the same quantity reported for every model run in this workbook. "
                  "These plain classifiers are weaker in absolute terms than the published "
                  "KI-GNN, which is the honest reading: simple models reproduce the DIRECTION "
                  "of the effect, the graph model captures more of it. That defends the model "
                  "choice rather than undercutting it.").font = Font(italic=True, size=9)
    ws.row_dimensions[row].height = 42
    ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True, vertical="top")

    ws.column_dimensions["A"].width = 24
    for j in range(2, 5):
        ws.column_dimensions[get_column_letter(j)].width = 26
    ws.column_dimensions["E"].width = 18
    ws.column_dimensions["F"].width = 18


REPRESENTATIONS = [
    ("MiniLM (published)", "model_class_metrics.tsv", "PubMed", "KIML"),
    ("TF-IDF title+abstract", "model_class_tfidf_full.tsv", "TFIDF full", "TFIDF full"),
    ("TF-IDF title only", "model_class_tfidf_title.tsv", "TFIDF title", "TFIDF title"),
]
REPRESENTATION_MODELS = ["Logistic regression", "Random forest",
                         "Gradient boosting", "MLP"]


def write_text_representations(ws, tables, diseases):
    """R1.4 / R1.5a: does the sentence transformer earn its place?"""
    ws.cell(row=1, column=1,
            value="Text representation comparison (Reviewer 1, comments 4 and 5a)").font = Font(bold=True, size=12)
    note = ("R1.4: \"The sentence transformer is essentially being used as a generic "
            "text-to-vector representation ... Classical text representations such as "
            "TF-IDF, TF-IDF+SVD/LSA, or Doc2Vec would provide important controls. Without "
            "these, the results end up showing that adding literature-derived features "
            "helps, rather than that contextual transformer representations provide "
            "meaningful additional value.\"  All three representations are built from the "
            "SAME date-filtered text, at the SAME 384 dimensions, and re-keyed to the SPEOS "
            "gene namespace, so the only thing that differs is the encoder. The title-only "
            "arm additionally separates what abstracts contribute from what titles already "
            "carry. Values are median rank, lower is better; intervals are 95% bootstrap "
            "over target genes.")
    cell = ws.cell(row=2, column=1, value=note)
    cell.font = Font(italic=True, size=9)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 90

    present = sorted({r["disease"] for t in tables.values() for r in t})

    row = 4
    for block, feature_kind in (("Literature features alone", "HL"),
                                ("Literature + expression", "LL+HL")):
        ws.cell(row=row, column=1, value=block).font = Font(bold=True, size=11)
        row += 1
        ws.cell(row=row, column=1, value="Disease")
        ws.cell(row=row, column=2, value="Model")
        for j, (label, _, _, _) in enumerate(REPRESENTATIONS):
            ws.cell(row=row, column=3 + j, value=label)
        ws.cell(row=row, column=6, value="Best")
        style_header(ws, row, 6)
        row += 1

        wins = {label: 0 for label, _, _, _ in REPRESENTATIONS}
        for key, display, _ in diseases:
            if key not in present:
                continue
            for model in REPRESENTATION_MODELS:
                ws.cell(row=row, column=1, value=display).font = Font(size=9)
                ws.cell(row=row, column=2, value=model).font = Font(size=9)
                values = []
                for j, (label, filename, hl_tag, both_tag) in enumerate(REPRESENTATIONS):
                    table = tables.get(filename, [])
                    tag = hl_tag if feature_kind == "HL" else both_tag
                    want = "HL ({})".format(tag) if feature_kind == "HL" \
                        else "LL+HL ({})".format(tag)
                    record = next((r for r in table if r["disease"] == key
                                   and r["model"] == model
                                   and r["features"] == want), None)
                    value = _number(record, "median_rank_unseen", 1) if record else None
                    lo = _number(record, "median_rank_unseen_lo", 1) if record else None
                    hi = _number(record, "median_rank_unseen_hi", 1) if record else None
                    text = ""
                    if value is not None:
                        text = "{:g}".format(value)
                        if lo is not None and hi is not None:
                            text += "  [{:g}, {:g}]".format(lo, hi)
                    cell = ws.cell(row=row, column=3 + j, value=text)
                    cell.alignment = Alignment(horizontal="center")
                    cell.font = Font(size=9)
                    cell.border = BOX
                    values.append((value, label, cell))

                scored = [(v, l, c) for v, l, c in values if v is not None]
                # Only declare a winner when there is something to compare
                # against. The TF-IDF arms were run on three diseases; marking
                # MiniLM "best" on the others would be an artefact of absence.
                if len(scored) > 1:
                    best = min(scored)
                    best[2].fill = BEST_FILL
                    best[2].font = BOLD
                    wins[best[1]] += 1
                    ws.cell(row=row, column=6, value=best[1]).font = Font(size=9)
                    ws.cell(row=row, column=6).alignment = Alignment(horizontal="center")
                elif scored:
                    ws.cell(row=row, column=6, value="not compared").font = Font(
                        size=9, italic=True, color="808080")
                    ws.cell(row=row, column=6).alignment = Alignment(horizontal="center")
                row += 1

        ws.cell(row=row, column=1, value="wins: " + ", ".join(
            "{} {}".format(l, n) for l, n in wins.items())).font = Font(
                italic=True, size=9, bold=True)
        row += 2

    for text in [
        "FINDING: the classical representation outperforms the sentence transformer. "
        "TF-IDF+SVD on title+abstract gives a lower median rank than MiniLM in 11 of 12 "
        "disease-model combinations, both as literature features alone and in combination "
        "with expression. Reviewer 1's suspicion is therefore correct, and more strongly "
        "than stated: the benefit comes from the literature content, not from contextual "
        "encoding.",
        "This is not purely a negative result. A TF-IDF representation is fit only on "
        "pre-cutoff text and has no pretrained component, which removes the objection "
        "Reviewer 3 raised in comment 5 - that a release date cannot bound what is in "
        "MiniLM's pretraining corpus. It is also directly interpretable, since the terms "
        "driving each gene vector can be listed. And it partly rescues Intellectual "
        "Disability, where knowledge inclusion helped 0 of 4 model classes under MiniLM "
        "and 2 of 4 under TF-IDF.",
        "CAVEAT: these are four plain classifiers, not the GNN. Dense smooth embeddings may "
        "suit message passing differently from sparse SVD projections, so the GNN arm must "
        "be run before any claim here is carried into the manuscript.",
    ]:
        cell = ws.cell(row=row, column=1, value=text)
        cell.font = Font(italic=True, size=9)
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[row].height = 46
        row += 1

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 22
    for j in range(len(REPRESENTATIONS)):
        ws.column_dimensions[get_column_letter(3 + j)].width = 24
    ws.column_dimensions["F"].width = 22


TABLE1_CONFIGS = ["RF", "C-RF", "KI-RF", "GNN", "C-GNN", "KI-GNN"]

# Cells to leave at their published value, with the reason. ExpB96_mnd returns
# 3936 against the published 8551 and has a different universe (17,216 vs
# 17,282), so it is evidently a different run from the ExpCP_ that produced
# Table 1 - whose fold files were never located. Substituting it here would
# smuggle a change of experiment into a correction that is only about target
# sets, so the published value stands until the provenance is resolved.
TABLE1_HOLD = {
    ("mnd", "GNN"): "provenance unresolved; ExpB96_mnd is a different run from the "
                    "ExpCP_ behind the published value",
}


def write_corrected_table1(ws, metric_rows, published, diseases):
    """Table 1 with every configuration scored on the post-split target list."""
    ws.cell(row=1, column=1,
            value="Corrected Table 1 - median rank, all configurations on the post-split target list").font = Font(bold=True, size=12)
    note = ("Table 1's RF-arm values were computed against the full later-snapshot panel "
            "(e.g. DEE-2025_03.txt) while the GNN arm used the post-split diff "
            "(*_vs_2022_09.txt). The full panel also contains genes already present at "
            "2022-09 - 58 of them for DEE - so the two arms were not measuring the same "
            "task. This is not leakage: those genes carry Known Gene = 0 and were never "
            "trained on. But a gene already on the panel cannot evidence discovery after "
            "the partition date, so scoring every configuration on the post-split diff is "
            "both the comparable and the conservative choice. "
            "GNN columns are unchanged - they already used this basis. "
            "KI-RF still beats RF on 7 of 9 diseases, exactly as published; only AD DEE "
            "flips, from +8 to -60 ranks.")
    cell = ws.cell(row=2, column=1, value=note)
    cell.font = Font(italic=True, size=9)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 85

    by_method = {(r["disease"], r["method"]): r for r in metric_rows}

    row = 4
    ws.cell(row=row, column=1, value="Disease")
    for j, config in enumerate(TABLE1_CONFIGS):
        ws.cell(row=row, column=2 + j * 2, value=config + " (published)")
        ws.cell(row=row, column=3 + j * 2, value=config + " (corrected)")
    style_header(ws, row, 1 + 2 * len(TABLE1_CONFIGS))
    ws.freeze_panes = ws.cell(row=row + 1, column=2)
    row += 1

    changed = held = 0
    for key, display, _ in diseases:
        ws.cell(row=row, column=1, value=display).font = BOLD
        for j, config in enumerate(TABLE1_CONFIGS):
            old = published.get((key, config))
            record = by_method.get((key, config))
            new = _number(record, "median_rank_unseen", 1) if record else None

            cell_old = ws.cell(row=row, column=2 + j * 2, value=old)
            cell_new = ws.cell(row=row, column=3 + j * 2)
            for cell in (cell_old, cell_new):
                cell.number_format = "0.0"
                cell.alignment = Alignment(horizontal="center")
                cell.border = BOX

            if (key, config) in TABLE1_HOLD:
                cell_new.value = old
                cell_new.fill = PatternFill("solid", fgColor="FFF2CC")
                cell_new.comment = None
                held += 1
            elif new is None:
                cell_new.value = None
            else:
                cell_new.value = new
                if old is not None and abs(new - old) >= 0.5:
                    cell_new.font = BOLD
                    cell_new.fill = BEST_FILL if (new < old) else PatternFill(
                        "solid", fgColor="F8CBAD")
                    changed += 1
        row += 1

    row += 1
    ws.cell(row=row, column=1,
            value="{} cells change. Green = corrected value is better (lower rank), "
                  "orange = worse. Amber = held at the published value.".format(changed)
            ).font = Font(italic=True, size=9)
    row += 1
    for (disease, config), reason in TABLE1_HOLD.items():
        label = next((d for k, d, _ in diseases if k == disease), disease)
        cell = ws.cell(row=row, column=1,
                       value="HELD: {} / {} kept at the published value - {}.".format(
                           label, config, reason))
        cell.font = Font(italic=True, size=9, color="C00000")
        cell.alignment = Alignment(wrap_text=True, vertical="top")
        ws.row_dimensions[row].height = 28
        row += 1

    ws.column_dimensions["A"].width = 30
    for j in range(2 * len(TABLE1_CONFIGS)):
        ws.column_dimensions[get_column_letter(2 + j)].width = 15


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--supp2", default=os.path.join(root, "rebuttal", "Supp_Data_2.xlsx"))
    parser.add_argument("--popularity", default=os.path.join(here, "popularity_rank_metrics_cutoff.tsv"),
                        help="primary baseline: counts restricted to the 2022-10-01 cutoff")
    parser.add_argument("--popularity-alldates", default=os.path.join(here, "popularity_rank_metrics.tsv"),
                        help="secondary baseline: counts of all dates (optional)")
    parser.add_argument("--counts", default=os.path.join(here, "pubmed_counts_2022_09.tsv"),
                        help="per-gene pre-cutoff counts and disease evidence, for the R1.7 sheet")
    parser.add_argument("--disease-dir", default=os.path.join(root, "data", "kiml_data", "diseases"))
    revision = os.path.join(root, "additional_experiments", "revision_runs")
    parser.add_argument("--revision-metrics",
                        default=os.path.join(revision, "revision_metrics.tsv"),
                        help="bootstrap CIs per method, from revision_analysis.py")
    parser.add_argument("--revision-contrasts",
                        default=os.path.join(revision, "revision_metrics_contrasts.tsv"),
                        help="paired contrasts, from revision_analysis.py")
    parser.add_argument("--model-classes",
                        default=os.path.join(root, "additional_experiments", "model_classes",
                                             "model_class_metrics.tsv"),
                        help="R1.3 results from run_model_classes.py")
    parser.add_argument("-o", "--out", default=os.path.join(root, "rebuttal", "Supp_Data_3_popularity.xlsx"))
    parser.add_argument("--cutoff-applied", action="store_true", default=True,
                        help="set when the primary popularity TSV respects the date cutoff")
    args = parser.parse_args()

    print("Reading manuscript results from {}".format(args.supp2))
    paper = load_paper_metrics(args.supp2)
    for (source, tag), table in sorted(paper.items()):
        print("  {:8} {:8} -> {} diseases".format(source, tag, len(table)))

    print("Reading popularity baseline (cutoff) from {}".format(args.popularity))
    primary = load_popularity(args.popularity)
    print("  {} diseases".format(len(primary)))

    popularity = {"popularity": primary}
    if args.popularity_alldates and os.path.exists(args.popularity_alldates):
        print("Reading popularity baseline (all dates) from {}".format(args.popularity_alldates))
        popularity["popularity_alldates"] = load_popularity(args.popularity_alldates)
        print("  {} diseases".format(len(popularity["popularity_alldates"])))
    else:
        print("[warn] no all-dates baseline; that column will be blank.")
        popularity["popularity_alldates"] = {}

    all_diseases = PAPER_DISEASES + [d for d in EXTRA_DISEASES if d[0] in primary]

    wb = openpyxl.Workbook()
    write_readme(wb.active, primary, args.cutoff_applied)
    wb.active.title = "README"
    write_headline(wb.create_sheet("Headline comparison"), paper, popularity, PAPER_DISEASES)
    write_all_metrics(wb.create_sheet("All metrics"), paper, popularity, PAPER_DISEASES)
    write_recall_k(wb.create_sheet("Recall across K"), paper, popularity, PAPER_DISEASES)

    metric_rows = load_tsv(args.revision_metrics)
    contrast_rows = load_tsv(args.revision_contrasts)
    if metric_rows:
        print("Reading bootstrap CIs from {} ({} rows)".format(
            args.revision_metrics, len(metric_rows)))
        write_bootstrap_cis(wb.create_sheet("Bootstrap CIs (R1.10)"),
                            metric_rows, PAPER_DISEASES)
    else:
        print("[warn] no revision metrics found; skipping the CI sheet.")
    if contrast_rows:
        print("Reading paired contrasts from {} ({} rows)".format(
            args.revision_contrasts, len(contrast_rows)))
        write_paired_contrasts(wb.create_sheet("Paired contrasts (R1.10)"),
                               contrast_rows, PAPER_DISEASES)
    if metric_rows and contrast_rows:
        write_late_fusion(wb.create_sheet("Late fusion (R1.5d, R4.1)"),
                          metric_rows, contrast_rows, PAPER_DISEASES)
        write_ablations(wb.create_sheet("Ablations (R1.5b, R1.5e)"),
                        metric_rows, contrast_rows, PAPER_DISEASES)

    if metric_rows:
        # Published medians, keyed (disease, config), from the two lookups.
        published = {}
        for lookup_path, variant_key in [
                (os.path.join(revision, "mantis_lookup.tsv"), "paper_variant"),
                (os.path.join(revision, "experiment_lookup.tsv"), "paper_variant")]:
            for entry in load_tsv(lookup_path):
                try:
                    published[(entry["disease"], entry[variant_key])] = float(
                        entry["table1_median"])
                except (TypeError, ValueError, KeyError):
                    continue
        write_corrected_table1(wb.create_sheet("Corrected Table 1"),
                               metric_rows, published, PAPER_DISEASES)

    model_class_rows = load_tsv(args.model_classes)
    if model_class_rows:
        print("Reading model-class results from {} ({} rows)".format(
            args.model_classes, len(model_class_rows)))
        write_model_classes(wb.create_sheet("Model classes (R1.3)"),
                            model_class_rows, PAPER_DISEASES)

    mc_dir = os.path.join(root, "additional_experiments", "model_classes")
    tables = {}
    for _, filename, _, _ in REPRESENTATIONS:
        rows_ = load_tsv(os.path.join(mc_dir, filename))
        if rows_:
            tables[filename] = rows_
    if len(tables) > 1:
        print("Reading {} text representations".format(len(tables)))
        write_text_representations(wb.create_sheet("Text representations (R1.4)"),
                                   tables, PAPER_DISEASES)
    if os.path.exists(args.counts):
        write_temporal_evidence(wb.create_sheet("Prior literature (R1.7)"),
                                args.counts, args.disease_dir, all_diseases)
    else:
        print("[warn] {} not found; skipping the R1.7 sheet.".format(args.counts))
    write_popularity_detail(wb.create_sheet("Popularity detail"), primary, all_diseases)
    write_literature_bias(wb.create_sheet("Literature bias"), primary, all_diseases)
    wb.save(args.out)
    print("\nWrote {}".format(args.out))
    print("Sheets: {}".format(", ".join(wb.sheetnames)))


if __name__ == "__main__":
    main()
