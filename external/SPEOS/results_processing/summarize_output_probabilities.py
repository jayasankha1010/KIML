import os
import pandas as pd
import argparse

DEFAULT_DIR = "./results"  # Default directory path
DEFAULT_EXPERIMENT = "Exp_DEE_KIGNN"  # Default experiment prefix

def process_tsv_files(directory=DEFAULT_DIR, experiment=DEFAULT_EXPERIMENT):
    # Find all .tsv files starting with "Exp22" in the directory
    # experiment = "ExpC1"
    # experiment = "ExpB3_mantis_data_2022_all_without_mp"
    tsv_files = [file for file in os.listdir(directory) if file.startswith(experiment) and file.endswith(".tsv")]
    print("length : ", len(tsv_files))
    # experiments = ["Exp44", "Exp45", "Exp46", "Exp47", "Exp48", "Exp49", "Exp50", "Exp51", "Exp52", "Exp53"]
    # for experiment in experiments:
    #     print(experiment)
    #     tsvs = [file for file in os.listdir(directory) if file.startswith(experiment) and file.endswith(".tsv")]
    #     for tsv in tsvs:
    #         tsv_files.append(tsv)
        
    
    if not tsv_files:
        print("No files found starting with 'Exp22' in the specified directory.")
        return
    
    print("Number of results.tsv : ", len(tsv_files))
    
    combined_data = {}

    for file in tsv_files:
        file_path = os.path.join(directory, file)
        print(f"Processing file: {file_path}")
        # Read the file
        df = pd.read_csv(file_path, sep='\t')
        
        # Ensure required columns exist
        if not {'hgnc', 'truth', 'prediction', 'probability'}.issubset(df.columns):
            print(f"File {file} is missing required columns. Skipping.")
            continue
        
        for _, row in df.iterrows():
            hgnc = row['hgnc']
            truth = row['truth']
            prediction = row['prediction']
            probability = row['probability']
            
            if hgnc not in combined_data:
                combined_data[hgnc] = {'truth': truth, 'predictions': [], 'probabilities': []}
            
            combined_data[hgnc]['predictions'].append(prediction)
            combined_data[hgnc]['probabilities'].append(probability)
    
    # Compute averages
    result = []
    for hgnc, values in combined_data.items():
        avg_prediction = sum(values['predictions']) / len(values['predictions'])
        avg_probability = sum(values['probabilities']) / len(values['probabilities'])
        result.append({'hgnc': hgnc, 'truth': values['truth'], 'avg_prediction': avg_prediction, 'avg_probability': avg_probability})
    
    # Create a DataFrame and write to file
    result_df = pd.DataFrame(result)
    script_directory = os.path.dirname(os.path.abspath(__file__))
    output_file = os.path.join(script_directory, f"{experiment}_probabilities.tsv")
    result_df.to_csv(output_file, sep='\t', index=False)
    print(f"Averaged data has been written to {output_file}")

# Example usage
# directory_path = "./../results"  # Replace with the path to your directory

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process TSV files and compute average probabilities.")
    parser.add_argument('-d', '--directory', type=str, default=DEFAULT_DIR, help='Directory path containing TSV files')
    parser.add_argument('-e', '--experiment', type=str, default=DEFAULT_EXPERIMENT, help='Experiment prefix for TSV files')
    args = parser.parse_args()
    
    process_tsv_files(args.directory, args.experiment)
