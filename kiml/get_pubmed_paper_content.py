import csv
from datetime import datetime

def load_papers(paper_csv_filename, cutoff_date):
    """
    Load paper details from CSV into a dictionary mapping PubMed ID to its details.
    Only include papers with a publication date before the cutoff_date.
    """
    papers = {}
    with open(paper_csv_filename, newline='', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            pubmed_id = row["PubMed ID"].strip()
            sort_date_str = row["SortPubDate"].strip()
            try:
                sort_date = datetime.strptime(sort_date_str, "%Y/%m/%d %H:%M")
            except ValueError:
                # If the date doesn't match the expected format, skip this row.
                continue

            # Skip papers with publication dates on/after October 1, 2022.
            if sort_date >= cutoff_date:
                continue

            title = row["Title"].strip()
            abstract = row["Abstract"].strip()
            papers[pubmed_id] = {"date": sort_date, "title": title, "abstract": abstract}
    return papers

def load_gene_pubmed(gene_pubmed_filename):
    """
    Load the gene-to-PubMed IDs mapping from a CSV file.
    The first column is the gene name and the subsequent columns are PubMed IDs.
    """
    gene_pubmed_map = {}
    with open(gene_pubmed_filename, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        header = next(reader)  # Skip header row
        for row in reader:
            if not row:
                continue
            gene = row[0].strip()
            # Collect all non-empty PubMed ID fields
            pubmed_ids = [pid.strip() for pid in row[1:] if pid.strip()]
            gene_pubmed_map[gene] = pubmed_ids
    return gene_pubmed_map

def create_gene_paper_csv(gene_pubmed_map, papers, output_filename):
    """
    Create a new CSV file where each row starts with the gene name and subsequent columns
    contain paper details (title and abstract) for that gene.
    Commas in the title and abstract are removed.
    """
    with open(output_filename, "w", newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        # Write a simple header. (Note: The number of paper columns may vary.)
        writer.writerow(["Gene", "Paper Details (Title & Abstract)"])
        count=0
        for gene, pubmed_ids in gene_pubmed_map.items():
            count+=1
            print(count, gene)
            paper_details = []
            for pmid in pubmed_ids:
                if pmid in papers:
                    # Remove commas from title and abstract
                    title_clean = papers[pmid]['title'].replace(",", "")
                    abstract_clean = papers[pmid]['abstract'].replace(",", "")
                    # details = f"Title: {title_clean}\nAbstract: {abstract_clean}"
                    details = f"{title_clean} {abstract_clean}"
                    paper_details.append(details)
            # Write the row with the gene and its associated paper details.
            row = [gene] + paper_details
            writer.writerow(row)

def main():
    # Update these filenames as needed.
    gene_pubmed_filename = "genes_to_ids.csv"
    paper_details_filename = "pubmed_articles_v5.csv"
    output_filename = "gene_details_2022_09.csv"
    
    # Set the cutoff date to October 1, 2022 (i.e. ignore articles published after September 2022)
    cutoff_date = datetime(2022, 10, 1, 0, 0)
    
    # Load data from the CSV files.
    papers = load_papers(paper_details_filename, cutoff_date)
    gene_pubmed_map = load_gene_pubmed(gene_pubmed_filename)
    
    # Create the output CSV file.
    create_gene_paper_csv(gene_pubmed_map, papers, output_filename)
    
    print("CSV file created successfully:", output_filename)

if __name__ == "__main__":
    main()
