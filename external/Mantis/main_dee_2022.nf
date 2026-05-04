#!/usr/bin/env nextflow

nextflow.enable.dsl=2

// Define parameters
params.base_dir = "${workflow.projectDir}"
params.script = "${params.base_dir}/mantis_ml/modules/main/__main__.py"

params.python = "env python"
params.iter = 1
params.runname = "dee_2022_pubmed_only"  // "example_out"
params.threads_per_job = 38 // Number of threads per Mantis job
params.max_parallel = 5     // Number of parallel Mantis processes

process runMantis {
    maxForks params.max_parallel
    cpus params.threads_per_job
    
    input:
    val phenotype
    
    output:
    path "${phenotype}_complete.txt"
    
    script:
    """
    # 1. Save Nextflow's hidden work directory so we can return here later
    WORK_DIR=\$(pwd)

    # 2. Navigate to the Mantis root folder so relative paths work perfectly
    cd ${params.base_dir}

    # 3. Create output directory
    mkdir -p Mantis_Out/${phenotype}_${params.runname}_${params.iter}_iter_custom

    # 4. Run Mantis (Notice we removed the base_dir prefixes here because we are already in the directory)
    ${params.python} ${params.script} \
        -n ${params.threads_per_job} \
        -i ${params.iter} \
        -m xgb \
        -o Mantis_Out/${phenotype}_${params.runname}_${params.iter}_iter_custom \
        -c mantis_ml/conf/${phenotype}_config.yaml \
        -k Input_Files/${phenotype}.tsv

    # 5. Return to Nextflow's work directory to drop the completion marker
    cd \$WORK_DIR
    touch ${phenotype}_complete.txt
    """
}

workflow {
    phenotypes = Channel.fromList([
        // 'asd_monoallelic',
        'dee_2022'
        // 'dee_2025'
        // 'dee_2022_ar'
    ])

    runMantis(phenotypes)
}