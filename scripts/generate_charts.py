"""Generate static presentation-ready charts for the ML pipeline results."""

import json
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

# Use seaborn aesthetics
sns.set_theme(style="whitegrid", context="talk")

def load_results(path="results/benchmark_results.json"):
    with open(path, "r") as f:
        return json.load(f)

def generate_benchmark_chart(results, output_dir):
    """Generate a grouped bar chart comparing MAE, RMSE, and MAPE across models, with R2 in a subplot."""
    models = results.get("models", {})
    if not models:
        print("No models found in results.")
        return

    # Prepare data
    data = []
    for model_name, metrics in models.items():
        if "error" in metrics:
            continue
        data.append({
            "Model": model_name.capitalize(),
            "MAE": metrics.get("mae_mean", 0),
            "RMSE": metrics.get("rmse_mean", 0),
            "MAPE": metrics.get("mape_mean", 0) / 100.0, # scale for visualization alongside others
            "R2": metrics.get("r2_mean", 0),
        })
    
    df = pd.DataFrame(data)
    
    # Create figure with 2 subplots (1 for errors, 1 for R2)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6), gridspec_kw={'width_ratios': [2, 1]})
    
    # Error metrics
    df_errors = df.melt(id_vars="Model", value_vars=["MAE", "RMSE", "MAPE"], var_name="Metric", value_name="Value")
    sns.barplot(data=df_errors, x="Model", y="Value", hue="Metric", ax=ax1, palette="viridis")
    ax1.set_title("Error Metrics by Model (Lower is Better)", fontweight='bold')
    ax1.set_ylabel("Error Value")
    ax1.set_xlabel("")
    
    # R2 metric
    sns.barplot(data=df, x="Model", y="R2", ax=ax2, palette="Blues_d")
    ax2.set_title("R² Score by Model (Higher is Better)", fontweight='bold')
    ax2.set_ylabel("R² Score")
    ax2.set_xlabel("")
    
    # Add values on top of R2 bars
    for i, p in enumerate(ax2.patches):
        ax2.annotate(f"{df['R2'].iloc[i]:.2f}", 
                     (p.get_x() + p.get_width() / 2., p.get_height()), 
                     ha='center', va='bottom', fontsize=12)

    plt.tight_layout()
    
    # Save
    out_path = Path(output_dir) / "benchmark_comparison.png"
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Saved {out_path}")
    plt.close()

def generate_feature_importance_chart(results, output_dir):
    """Generate a horizontal bar chart of the top features from the multimodal model."""
    models = results.get("models", {})
    if "multimodal" not in models or "feature_importance" not in models["multimodal"]:
        print("No multimodal feature importance found.")
        return
    
    fi = models["multimodal"]["feature_importance"]
    # Sort and take top 15
    sorted_fi = sorted(fi.items(), key=lambda x: x[1], reverse=True)[:15]
    
    # Define categories (Contextual vs Visual)
    visual_prefixes = ("vision_", "color_", "dominant_", "brightness", "saturation", "aspect_", "visual_", "is_")
    
    df = pd.DataFrame(sorted_fi, columns=["Feature", "Importance"])
    df["Category"] = df["Feature"].apply(lambda x: "Visual" if x.startswith(visual_prefixes) else "Contextual")
    
    plt.figure(figsize=(10, 8))
    
    # Set custom palette
    palette = {"Contextual": "#14b8a6", "Visual": "#a855f7"}
    
    ax = sns.barplot(data=df, x="Importance", y="Feature", hue="Category", dodge=False, palette=palette)
    plt.title("Top 15 Features Driving Engagement Rate", fontweight='bold', pad=20)
    plt.xlabel("Importance Score")
    plt.ylabel("")
    
    # Clean up feature names for display
    labels = [item.get_text().replace("_", " ").title() for item in ax.get_yticklabels()]
    ax.set_yticklabels(labels)
    
    plt.tight_layout()
    out_path = Path(output_dir) / "feature_importance.png"
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"Saved {out_path}")
    plt.close()

if __name__ == "__main__":
    out_dir = Path("results/charts")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        results = load_results()
        generate_benchmark_chart(results, out_dir)
        generate_feature_importance_chart(results, out_dir)
    except Exception as e:
        print(f"Error generating charts: {e}")
