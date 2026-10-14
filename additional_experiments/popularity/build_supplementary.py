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
    ("Popularity", "popularity", "", "Popularity (PubMed count)"),
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
    if source == "popularity":
        return popularity.get(disease, {}).get(metric)
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
        lines += [("4. Paper counts are restricted to publications before 2022-10-01, "
                   "matching the models' knowledge cutoff.", False)]
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
    ws.cell(row=2, column=1, value="Best value per disease per metric shaded green. Popularity column shaded amber.").font = Font(italic=True, size=9)

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
                if source == "popularity":
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
                if source == "popularity":
                    cell.fill = POP_FILL
                values.append(val)

            lo = popularity.get(key, {}).get(metric_key + "_lo")
            hi = popularity.get(key, {}).get(metric_key + "_hi")
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
                if source == "popularity":
                    cell.fill = POP_FILL
                values[name] = val

            # Compare against the top of the popularity band, not its median.
            pop_hi = popularity.get(key, {}).get(metric_key + "_hi")
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


def write_popularity_detail(ws, popularity, diseases):
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
        data = popularity.get(key)
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


def write_literature_bias(ws, popularity, diseases):
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
        data = popularity.get(key)
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


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.abspath(os.path.join(here, "..", ".."))

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--supp2", default=os.path.join(root, "rebuttal", "Supp_Data_2.xlsx"))
    parser.add_argument("--popularity", default=os.path.join(here, "popularity_rank_metrics.tsv"))
    parser.add_argument("-o", "--out", default=os.path.join(root, "rebuttal", "Supp_Data_3_popularity.xlsx"))
    parser.add_argument("--cutoff-applied", action="store_true",
                        help="set when the popularity TSV was produced with --articles")
    args = parser.parse_args()

    print("Reading manuscript results from {}".format(args.supp2))
    paper = load_paper_metrics(args.supp2)
    for (source, tag), table in sorted(paper.items()):
        print("  {:8} {:8} -> {} diseases".format(source, tag, len(table)))

    print("Reading popularity baseline from {}".format(args.popularity))
    popularity = load_popularity(args.popularity)
    print("  {} diseases".format(len(popularity)))

    all_diseases = PAPER_DISEASES + [d for d in EXTRA_DISEASES if d[0] in popularity]

    wb = openpyxl.Workbook()
    write_readme(wb.active, popularity, args.cutoff_applied)
    wb.active.title = "README"
    write_headline(wb.create_sheet("Headline comparison"), paper, popularity, PAPER_DISEASES)
    write_all_metrics(wb.create_sheet("All metrics"), paper, popularity, PAPER_DISEASES)
    write_recall_k(wb.create_sheet("Recall across K"), paper, popularity, PAPER_DISEASES)
    write_popularity_detail(wb.create_sheet("Popularity detail"), popularity, all_diseases)
    write_literature_bias(wb.create_sheet("Literature bias"), popularity, all_diseases)
    wb.save(args.out)
    print("\nWrote {}".format(args.out))
    print("Sheets: {}".format(", ".join(wb.sheetnames)))


if __name__ == "__main__":
    main()
