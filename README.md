# LLM-Based Log Anomaly Detection

Fine-tuning a transformer language model (BERT-family) for log anomaly detection,
trained and evaluated on the [Loghub](https://github.com/logpai/loghub) collection
of system log datasets. Built during an LLM Internship at the National Institute
of Technology, Warangal (May–July 2025).

## Project Summary

- Fine-tunes a pretrained BERT model for binary anomaly classification (normal vs. anomalous)
  on raw, unsanitized production-style log lines.
- Covers 19+ Loghub datasets spanning distributed systems (HDFS, Spark, Zookeeper),
  operating systems (Linux, Mac, Windows), server logs (Apache, OpenSSH), and mobile
  platforms (Android, HealthApp).
- Includes a chunked, memory-safe preprocessing pipeline for multi-gigabyte raw log
  files, cutting manual inspection effort by automating template extraction, noise
  filtering, and labeling.
- Includes classical ML baselines (TF-IDF + Logistic Regression, Random Forest,
  Isolation Forest) to benchmark the fine-tuned LLM against traditional approaches.
- Reports accuracy, precision, recall, F1, and ROC-AUC for both the LLM and baselines
  on held-out data per dataset.

## Repository Structure

```
log-anomaly-detection/
├── README.md
├── requirements.txt
├── .gitignore
├── configs/
│   └── config.yaml            # dataset paths, model + training hyperparameters
├── data/
│   ├── raw/                   # downloaded Loghub raw logs (gitignored)
│   └── processed/             # cleaned/tokenized parquet files (gitignored)
├── scripts/
│   ├── download_loghub.py     # fetches Loghub datasets
│   └── run_pipeline.sh        # end-to-end: preprocess -> train -> evaluate
├── src/
│   ├── __init__.py
│   ├── data_loader.py         # Loghub dataset registry + loaders
│   ├── preprocessing.py       # chunked cleaning/normalization pipeline
│   ├── baseline_models.py     # TF-IDF + classical ML baselines
│   ├── bert_model.py          # BERT fine-tuning for anomaly classification
│   ├── train.py                # training entry point (LLM)
│   └── evaluate.py            # evaluation + LLM-vs-baseline comparison
└── notebooks/
    └── exploration.ipynb      # optional EDA notebook (placeholder)
```

## Setup

```bash
git clone https://github.com/niveditha51/log-anomaly-detection.git
cd log-anomaly-detection
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

### 1. Download data

```bash
python scripts/download_loghub.py --datasets HDFS,Spark,Zookeeper,Linux,Android --out data/raw
```

### 2. Preprocess

```bash
python -m src.preprocessing --config configs/config.yaml
```

This streams each raw log file in chunks (default 100k lines), strips
timestamps/PIDs/IPs into normalized templates, deduplicates, and writes
labeled parquet shards to `data/processed/`.

### 3. Train the fine-tuned BERT model

```bash
python -m src.train --config configs/config.yaml --dataset all
```

Training uses inverse-frequency class weighting in the loss, since real-world
log anomalies are rare relative to normal lines — without this, the model
collapses to always predicting "normal."

### 4. Train baselines + compare

```bash
python -m src.evaluate --config configs/config.yaml --dataset all
```

This trains the classical ML baselines, evaluates both the LLM and the
baselines on the same held-out split, and prints/saves a comparison table.

## Results

Evaluated on a held-out split pooled across the HDFS, Spark, and Zookeeper
sample datasets (heuristic-labeled, since these particular samples don't ship
ground-truth anomaly labels):

| Model                          | Accuracy | Precision | Recall | F1    | ROC-AUC |
|---------------------------------|----------|-----------|--------|-------|---------|
| TF-IDF + Logistic Regression    | 0.9787   | 0.000     | 0.000  | 0.000 | 0.978   |
| TF-IDF + Random Forest          | 0.9787   | 0.000     | 0.000  | 0.000 | 1.000   |
| TF-IDF + Isolation Forest       | 0.9787   | 0.000     | 0.000  | 0.000 | —       |
| **Fine-tuned BERT (weighted)**  | 0.9574   | 0.333     | **1.000** | **0.500** | 0.978   |

All three classical baselines default to predicting "normal" for every line —
on this imbalanced sample they reach high accuracy without ever detecting a
real anomaly (0 recall). The fine-tuned BERT model, trained with class-weighted
loss, catches every anomaly in the held-out set (100% recall), trading some
precision for that — the right tradeoff for an anomaly detector, since a missed
anomaly is far costlier than a false alarm.

## Datasets

All log data comes from [Loghub](https://github.com/logpai/loghub) (LogPAI team),
a widely-used open collection with 90,000+ downloads across 450+ organizations.
Loghub datasets are used under their respective licenses — see the Loghub repo
for citation and usage terms.

## Tech Stack

Python · Hugging Face Transformers · PyTorch · Pandas · NumPy · Scikit-learn
