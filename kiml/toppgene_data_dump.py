import requests
import csv
import os
import json
from concurrent.futures import ThreadPoolExecutor


def process_row(row, url):
    symbol = row['symbol']
    entrez_id = row['entrez_id']

    try:
        # Convert entrez_id to an integer
        entrez_id = int(entrez_id)
    except ValueError:
        print(f"Invalid entrez_id for symbol {symbol}: {entrez_id}")
        return

    # Prepare the POST request payload
    data = {
        "Genes": [entrez_id],
        "Categories": []
    }

    try:
        # Send the POST request
        response = requests.post(url, json=data)

        # Format the response as JSON and write to a file named {symbol}.json
        output_file = f"./data/{symbol}.json"
        with open(output_file, 'w') as output:
            formatted_response = json.dumps(response.json(), indent=4)
            output.write(formatted_response)
    except requests.exceptions.RequestException as e:
        print(f"Error for symbol {symbol}: {e}")
    except json.JSONDecodeError:
        print(f"Error decoding JSON for symbol {symbol}: {response.text}")

def send_post_request_and_save_responses_parallel(input_file, url, max_workers=10):
    try:
        # Open the input file and read it
        with open(input_file, 'r') as tsv_file:
            reader = csv.DictReader(tsv_file, delimiter='\t')
            rows = list(reader)

        # Process rows in parallel
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            executor.map(lambda row: process_row(row, url), rows)
    except Exception as e:
        print(f"An error occurred: {e}")



# Example usage
if __name__ == "__main__":
    # Point directly to the SPEOS HGNC list using a relative path
    input_file = "./../external/SPEOS/hgnc/hgnc_official_list.tsv" 
    url = "https://toppgene.cchmc.org/API/enrich" 

    send_post_request_and_save_responses_parallel(input_file, url)
    print("Done!!!!!")