import json
import os
from collections import defaultdict

def make_node_key(kind, identifier):
    """Create a composite key from a node's kind and identifier."""
    return f"{kind}_{identifier}"

def extract_direct_gene_gene_edges_by_type(json_file, output_dir):
    # Ensure the output directory exists
    os.makedirs(output_dir, exist_ok=True)

    # Load JSON data
    print(f"Loading Knowledge Graph from: {json_file}...")
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    nodes = data["nodes"]
    edges = data["edges"]
    
    # Build a lookup for Gene nodes: composite key -> human-readable gene name.
    gene_info = {}
    for node in nodes:
        if node["kind"] == "Gene":
            key = make_node_key(node["kind"], node["identifier"])
            gene_name = node.get("name", str(node["identifier"]))
            gene_info[key] = gene_name
    
    # Group direct Gene-Gene edges by edge type.
    edge_type_dict = defaultdict(list)
    for edge in edges:
        src_kind = edge["source_id"][0]
        tgt_kind = edge["target_id"][0]
        
        if src_kind == "Gene" and tgt_kind == "Gene":
            src_identifier = edge["source_id"][1]
            tgt_identifier = edge["target_id"][1]
            src_key = make_node_key(src_kind, src_identifier)
            tgt_key = make_node_key(tgt_kind, tgt_identifier)
            
            if src_key in gene_info and tgt_key in gene_info:
                gene1 = gene_info[src_key]
                gene2 = gene_info[tgt_key]
                edge_type = edge.get("kind", "unknown")
                edge_type_dict[edge_type].append((gene1, gene2))
    
    # Write each edge type to a text file in the designated output folder.
    for edge_type, pairs in edge_type_dict.items():
        # Clean the filename just in case there are weird characters in the edge type
        clean_edge_type = edge_type.replace(' ', '_').replace('/', '_')
        filename = os.path.join(output_dir, f"{clean_edge_type}.txt")
        
        with open(filename, "w", encoding="utf-8") as out:
            for gene1, gene2 in pairs:
                out.write(f"{gene1} {gene2}\n")
        print(f"Created network file: {filename}")

if __name__ == "__main__":
    # Point to the Hetionet file (assuming it's placed in the data folder)
    input_json = "data/hetionet-v1.0.json" 
    
    # Output directory for the network edge text files
    output_directory = "data/kiml_data/networks"
    
    if os.path.exists(input_json):
        extract_direct_gene_gene_edges_by_type(input_json, output_directory)
        print("Knowledge Graph extraction complete!")
    else:
        print(f"[Error] Could not find the network file at {input_json}. Please ensure it is downloaded.")