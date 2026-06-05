#!/usr/bin/env bash
#SBATCH --job-name=gottcha2
#SBATCH --partition=bahl_p
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=16
#SBATCH --mem=120G
#SBATCH --time=12:00:00
#SBATCH --output=/scratch/sp96859/Meta-genome-data-analysis/Apptainer/Meta_MAVS/metamavs/run_20260604_235414/logs/gottcha2_%j.out
#SBATCH --error=/scratch/sp96859/Meta-genome-data-analysis/Apptainer/Meta_MAVS/metamavs/run_20260604_235414/logs/gottcha2_%j.err

set -euo pipefail

export PATH=/home/sp96859/.conda/envs/gottcha2_env/bin:$PATH

mkdir -p /scratch/sp96859/Meta-genome-data-analysis/Apptainer/Meta_MAVS/metamavs/run_20260604_235414/results/viral_detection /scratch/sp96859/Meta-genome-data-analysis/Apptainer/Meta_MAVS/metamavs/run_20260604_235414/work
gottcha2.py -i /scratch/sp96859/Meta-genome-data-analysis/Apptainer/data/short_reads/sample_72_0_01.fq.gz /scratch/sp96859/Meta-genome-data-analysis/Apptainer/data/short_reads/sample_72_0_02.fq.gz -d /scratch/sp96859/Meta-genome-data-analysis/Apptainer/databases/gottcha2_db/gottcha_db.species.fna -l species -t 8 -o /scratch/sp96859/Meta-genome-data-analysis/Apptainer/Meta_MAVS/metamavs/run_20260604_235414/work/Genome_72.gottcha2 -p Genome_72
cp /scratch/sp96859/Meta-genome-data-analysis/Apptainer/Meta_MAVS/metamavs/run_20260604_235414/work/Genome_72.gottcha2/Genome_72.tsv /scratch/sp96859/Meta-genome-data-analysis/Apptainer/Meta_MAVS/metamavs/run_20260604_235414/results/viral_detection/Genome_72.gottcha2.tsv
cp /scratch/sp96859/Meta-genome-data-analysis/Apptainer/Meta_MAVS/metamavs/run_20260604_235414/work/Genome_72.gottcha2/Genome_72.lineage.tsv /scratch/sp96859/Meta-genome-data-analysis/Apptainer/Meta_MAVS/metamavs/run_20260604_235414/results/viral_detection/Genome_72.gottcha2.lineage.tsv
