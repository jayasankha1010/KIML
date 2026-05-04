import csv
import numpy as np
from sentence_transformers import SentenceTransformer
from transformers import AutoTokenizer
tokenizer = AutoTokenizer.from_pretrained('sentence-transformers/all-MiniLM-L6-v2')

# Load the pre-trained sentence transformer model
model = SentenceTransformer('all-MiniLM-L6-v2')

# Define the input and output CSV file paths
# Define the input and output CSV file paths
input_csv = "./data/gene_details_2022_09.csv" 
output_csv = "./data/pubmed_features_2022_09.csv" 

# Read the CSV file using csv.reader
with open(input_csv, mode='r', encoding='utf-8') as file:
    csv_reader = csv.reader(file)
    header = next(csv_reader)  # Extract the header

    # Assuming the first column is the gene name and the rest are descriptions
    gene_column = header[0]

    # Initialize lists to store gene names and combined descriptions
    gene_names = []
    combined_descriptions = []

    for row in csv_reader:
        gene_name = row[0]
        print(gene_name)
        descriptions = row[1:]  # All columns except the first one

        # Combine the gene name with descriptions into a single string
        combined_description = gene_name + " " + " ".join(filter(None, descriptions))

        gene_names.append(gene_name)
        combined_descriptions.append(combined_description)
        

# Check the token count for each combined description
# for desc in combined_descriptions:
#     token_count = len(tokenizer.encode(desc))
#     if token_count > 256:
#         print(f"Warning: input length is {token_count} tokens, exceeding the 256-token limit.")

# Generate embeddings for each gene description
embeddings = model.encode(combined_descriptions, convert_to_numpy=True)

# Write embeddings to the output CSV file
with open(output_csv, mode='w', encoding='utf-8', newline='') as file:
    csv_writer = csv.writer(file)

    # Write the header for the embeddings file
    embedding_header = ["Gene"] + [f"Dim_{i}" for i in range(embeddings.shape[1])]
    csv_writer.writerow(embedding_header)

    # Write each gene and its corresponding embedding
    for gene, embedding in zip(gene_names, embeddings):
        csv_writer.writerow([gene] + embedding.tolist())

print(f"Embeddings for {len(gene_names)} genes have been saved to {output_csv}")
