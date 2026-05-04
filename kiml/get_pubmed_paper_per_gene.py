import os
import json
import csv

# Define input directory containing .json files and output file path
input_directory = "./data"
output_file = "pubmed_data.csv"

# Open the output file in write mode
with open(output_file, mode="w", newline="", encoding="utf-8") as csvfile:
    csv_writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
    # Write the header row
    csv_writer.writerow(["Gene Name", "Pubmed Names"])

    count=0
    # Iterate through all .json files in the directory
    for filename in os.listdir(input_directory):
        if filename.endswith(".json"):
            count+=1
            print(count)
            gene_name = filename.rsplit(".", 1)[0]  # Extract gene name from the file name
            file_path = os.path.join(input_directory, filename)

            # Read and process the .json file
            try:
                with open(file_path, mode="r", encoding="utf-8") as json_file:
                    data = json.load(json_file)

                    # Check if "Annotations" key exists and is a list
                    if "Annotations" in data and isinstance(data["Annotations"], list):
                        # Filter annotations with "Category" = "Pubmed"
                        pubmed_entries = [entry["Name"].replace(",", "") for entry in data["Annotations"] if entry.get("Category") == "Pubmed"]

                        # Write to the CSV file if there are any Pubmed entries
                        if pubmed_entries:
                            csv_writer.writerow([gene_name] + pubmed_entries)

            except (json.JSONDecodeError, KeyError, IOError) as e:
                print(f"Error processing file {filename}: {e}")

print(f"Filtered data has been written to {output_file}")
