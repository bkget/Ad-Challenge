# Interview Guide: Ad-Challenge Multimodal AdTech ML System

> Prepared for: Technical interview at an AdTech / advertising technology company  
> Role type: ML Engineer / Data Scientist / Applied Scientist

---

## 1. Elevator Pitch (30 seconds)

> "I built an end-to-end ML pipeline that predicts ad creative performance — specifically Engagement Rate and CTR — before a campaign goes live. It combines campaign metadata with computer vision features extracted from creative images using a pretrained ResNet50 (2048-dim embeddings, PCA-reduced to 32 dims). The key result: adding visual features improves R² from 0.44 to 0.53, a 19% relative gain, validated through GroupKFold cross-validation that prevents campaign-level data leakage. The system runs in about a minute locally and is Docker-packaged for reproducible deployment."

---

## 2. Problem Statement Q&A

**Q: What business problem does this solve?**

A/B testing ad creatives *after* media spend is expensive and slow. This system predicts which creative will perform best *before* launching — enabling pre-launch creative selection and Dynamic Creative Optimization (DCO). For a campaign with $100K budget, even a 10% ER improvement translates to significant incremental engagement.

**Q: Why engagement rate specifically?**

ER is the primary KPI for rich-media interstitial ads (the Adludio format in this dataset). Unlike CTR which can be gamed with clickbait, ER (first_dropped events / impressions) measures genuine user interaction — the user had to actively engage with the ad content.

**Q: What's the prediction grain?**

`(creative game_key) × (device_type, platform_os, geo_country)` — not just per-creative but per-context. This matters because the same creative performs differently on iOS vs Android, in USA vs Singapore.

---

## 3. Data Engineering Q&A

**Q: Walk me through the data pipeline.**

Five stages, each independently cacheable:

1. **Ingestion** — Load 422K impression/engagement events + 144 creative PNGs + campaign briefings. The `game_key` in inventory has format `slug/request_id`, which I parse to link images to campaign records.

2. **Entity Resolution** — Key challenge: 3 data sources with different identifiers. Inventory uses `slug/request_id`, design JSON uses MD5 hashes, image filenames use `slug-request_id.png`. I discovered this through diagnostic exploration and built the correct cross-source link.

3. **Vision Extraction** — ResNet50 (pretrained ImageNet) extracts 2048-dim embeddings → PCA reduces to 32 dims. Plus 10 handcrafted features: brightness, saturation, colorfulness (Hasler & Süsstrunk 2003), visual entropy, color diversity, aspect ratio.

4. **Feature Engineering** — Merge all sources into an 811-row × 91-col feature matrix. Label-encode categoricals, median-fill missing numerics.

5. **Benchmark + Training** — GroupKFold CV (5 splits, grouped by campaign_id), then train final model on all data for inference.

**Q: What's the hardest data engineering challenge?**

Entity resolution. The three data sources use completely different linking keys. I had to write a diagnostic script to discover that `game_key` in the inventory CSV has format `slug/request_id` — none of the documentation stated this. Once discovered, the join worked correctly.

**Q: How did you handle missing values?**

- Creatives with fewer than 10 impressions: filtered out (statistically unreliable)
- Missing vision features (image not matched to inventory): median imputed — this is a known limitation since only 25.6% of rows link to a creative PNG
- All-NaN numeric columns: zero-filled with RuntimeWarning suppressed

---

## 4. Machine Learning Q&A

**Q: Why GroupKFold instead of random train/test split?**

Standard `train_test_split` would leak creatives from the same campaign into both train and test sets. Since ER is correlated within campaigns (same audience, same flight period), this inflates metrics by 30-50%. `GroupKFold(groups=campaign_id)` simulates the real production scenario: predicting performance for campaigns the model has never seen.

**Q: Why LightGBM?**

- Fast CPU training (full benchmark in ~2 seconds)
- Handles mixed numeric/categorical features natively
- Strong feature importance output for explainability
- Comparable accuracy to neural approaches on tabular data of this scale (~800 rows)
- Native support for `min_child_samples` to prevent overfitting on small folds

**Q: Why ResNet50 instead of CLIP?**

ResNet50 is well-understood, small (~100MB), and CPU-friendly — reducing setup friction for the demo. For production: CLIP (image-text joint embeddings) would be better for matching ad copy to visual content. I could also fine-tune on an ad-specific dataset if we had labeled creative performance data at scale.

**Q: Why PCA after ResNet50?**

2048-dim embeddings are too high-dimensional relative to our 811 training samples (risk of overfitting). PCA(32) reduces to a manageable feature set while retaining ~71% of variance. The PCA is fit only on training data within each fold to prevent leakage.

**Q: What do the benchmark results mean?**

| Model | R² | Interpretation |
|-------|-----|----------------|
| Baseline (global mean) | -0.008 | Random predictions — the floor |
| Tabular only | 0.443 | Context (campaign duration, buy rate, volume) is strong |
| Vision only | 0.145 | Visual features carry real but noisier signal — only 144 images across 811 rows |
| **Multimodal** | **0.529** | **Best — combining both modalities adds ~19% relative lift** |

The key interview finding: **visual features demonstrably improve predictions**, answering the core research question.

**Q: What are the model's limitations?**

1. **Small dataset**: 811 rows after filtering — results are directional, not statistically conclusive
2. **74% missing vision data**: Most inventory rows don't link to a Creative Asset PNG (different campaign periods), so vision features are NaN-imputed for most rows
3. **No temporal split**: GroupKFold groups by campaign but doesn't enforce time ordering — a strict temporal split using `start_date` would be more production-realistic
4. **Design metadata mismatch**: `global_design_data.json` uses different hash keys from inventory — so OCR labels and color metadata from the JSON aren't linking (0.1% match rate)

**Q: How would you improve this in production?**

1. Fine-tune the vision model on ad-specific data (needs labeled creative performance dataset — ResNet50 here is off-the-shelf ImageNet, not fine-tuned)
2. Add CLIP for image-text joint embeddings (match ad copy to visual content)
3. TF-IDF or sentence embeddings on OCR text from creative assets
4. Temporal cross-validation (split on campaign start_date, not just campaign_id)
5. Bayesian optimization for LightGBM hyperparameters
6. MLflow experiment tracking for reproducibility
7. Fix the design-JSON join so OCR/color metadata contributes (currently 0.1% match)

---

## 5. MLOps Q&A

**Q: How does the pipeline orchestration work?**

I replaced Apache Airflow (5-container setup: Webserver + Scheduler + Triggerer + Postgres + Redis) with a lightweight CLI runner. Each stage is an independently cacheable function — `--stage benchmark` re-runs only the benchmark using cached features. The business logic in `src/` is fully decoupled from the orchestrator and can be wrapped by Airflow `PythonOperator` trivially if production needs arise:

```python
t1 = PythonOperator(task_id="ingest", python_callable=run_ingestion)
```

**Q: How is the Docker setup?**

Multi-stage build: builder stage installs all Python deps, runtime stage copies only what's needed. Runs as non-root user. Single `docker compose up` runs the full pipeline. Image ~350MB vs 2.2GB for the full Airflow stack.

**Q: How do you prevent data leakage?**

- KPI targets computed BEFORE any train/test split
- GroupKFold prevents campaign records from crossing fold boundaries
- PCA fit ONLY on training data within each fold (PCA model saved separately for inference)
- Label encoders fit on training data, applied to test with unseen-category handling

---

## 6. System Design Q&A

**Q: How would you scale this to 100K creatives/day?**

| Component | Current | Production Change |
|-----------|---------|-------------------|
| Event aggregation | Pandas | Apache Spark (PySpark) |
| Vision extraction | CPU batch | GPU cluster (A100s), async queue |
| Feature store | Parquet files | Feast or Tecton feature platform |
| Model training | LightGBM local | Distributed LightGBM or XGBoost on Spark |
| Inference | Pickle + Python | FastAPI + Redis cache, Docker on K8s |
| Orchestration | CLI | Airflow + Celery workers |
| Monitoring | None | Evidently AI for data drift, MLflow for metrics |

**Q: How would you serve predictions in real-time?**

The `src/inference/predict.py` module is already structured as a prediction function. Wrap it in FastAPI:

```python
@app.post("/predict")
async def predict(request: CreativeRequest):
    artifacts = load_artifacts(models_dir, processed_dir)
    return predict_creative_performance(
        image_path=request.image_path,
        context=request.context,
        artifacts=artifacts,
        config=config
    )
```

Cache the loaded model artifacts in memory on startup. For high throughput, pre-compute embeddings for all known creatives and serve from Redis.

---

## 7. Key Numbers to Remember

| Metric | Value |
|--------|-------|
| Dataset | 422,387 events, 811 creative×context rows |
| Campaigns | 56 unique campaigns |
| Creative images | 144 PNGs |
| Multimodal R² | **0.529** |
| Tabular-only R² | 0.443 |
| Vision-only R² | 0.145 |
| MAE reduction vs baseline | **43%** (0.100 → 0.057) |
| Pipeline runtime | **~64 seconds** (first run, incl. ResNet50 inference) / **~16 seconds** (cached) |
| Vision match rate | 25.6% (limited by data availability) |
| PCA variance retained | 71.2% (32 components from 2048-dim ResNet50 embeddings) |
| Top feature | campaign_duration_days (~16% importance) |

---

## 8. Questions to Ask the Interviewer

These demonstrate strategic thinking:

1. "How do you currently evaluate creative performance before launch — is it purely A/B testing or are there pre-launch scoring systems?"
2. "What's the typical creative refresh cadence — daily, weekly, per-campaign? That affects what prediction horizon matters most."
3. "Do you have a labeled dataset of creative features + performance outcomes that's larger than this demo dataset? That would unlock fine-tuned vision models."
4. "Is the primary KPI engagement rate, or is there a downstream conversion metric (purchases, app installs) that we should be optimizing for?"
5. "How do you handle creative fatigue — does a creative's performance degrade predictably over its flight period?"
