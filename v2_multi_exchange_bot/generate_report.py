import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import sys
import os
import itertools

def print_summary_statistics(df, pairs):
    """Prints summary statistics for net profits."""
    print("--- Arbitrage Summary Statistics ---")
    for ex1, ex2 in pairs:
        profit_col = f'net_profit_{ex1}_to_{ex2}'
        if profit_col in df.columns:
            series = pd.to_numeric(df[profit_col], errors='coerce').dropna()
            if not series.empty:
                stats = series[series > -1] 
                print(f"\nDirection: {ex1.upper()} -> {ex2.upper()}")
                print(f"  - Opportunities Found: {len(stats[stats > 0])}")
                print(f"  - Max Net Profit: {stats.max():.4%}")
                print(f"  - Mean Net Profit: {stats.mean():.4%}")
    print("="*50 + "\n")

def create_report(df, exchanges, pairs, csv_path):
    """Generates and saves plots for each symbol in the dataframe."""
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.set_index('timestamp')

    symbols = df['symbol'].unique()

    for symbol in symbols:
        symbol_df = df[df['symbol'] == symbol].copy()

        for ex1, ex2 in pairs:
            bid_col_1 = f'{ex1}_bid'
            ask_col_1 = f'{ex1}_ask'
            bid_col_2 = f'{ex2}_bid'
            ask_col_2 = f'{ex2}_ask'
            net_profit_col_1_2 = f'net_profit_{ex1}_to_{ex2}'
            net_profit_col_2_1 = f'net_profit_{ex2}_to_{ex1}'

            required_cols = [bid_col_1, ask_col_1, bid_col_2, ask_col_2, net_profit_col_1_2, net_profit_col_2_1]
            if not all(col in symbol_df.columns for col in required_cols):
                continue

            fig, axes = plt.subplots(3, 1, figsize=(18, 20), gridspec_kw={'height_ratios': [2, 1, 1]})
            fig.suptitle(f'Arbitrage Analysis: {symbol} | {ex1.upper()} vs {ex2.upper()}', fontsize=18, weight='bold')

            axes[0].plot(symbol_df.index, symbol_df[bid_col_1], label=f'{ex1.upper()} Bid', alpha=0.8)
            axes[0].plot(symbol_df.index, symbol_df[ask_col_1], label=f'{ex1.upper()} Ask', alpha=0.8, linestyle='--')
            axes[0].plot(symbol_df.index, symbol_df[bid_col_2], label=f'{ex2.upper()} Bid', alpha=0.8)
            axes[0].plot(symbol_df.index, symbol_df[ask_col_2], label=f'{ex2.upper()} Ask', alpha=0.8, linestyle='--')
            axes[0].set_title('Price Divergence Over Time', fontsize=14)
            axes[0].set_ylabel('Price (USDT)')
            axes[0].legend()
            axes[0].grid(True, which='both', linestyle='--', linewidth=0.5)

            profit_series_1_2 = symbol_df[net_profit_col_1_2].dropna()
            profit_series_2_1 = symbol_df[net_profit_col_2_1].dropna()
            axes[1].plot(profit_series_1_2.index, profit_series_1_2 * 100, label=f'Net Profit {ex1.upper()} -> {ex2.upper()}')
            axes[1].plot(profit_series_2_1.index, profit_series_2_1 * 100, label=f'Net Profit {ex2.upper()} -> {ex1.upper()}')
            axes[1].axhline(0, color='black', linestyle='--', linewidth=1)
            axes[1].set_title('Profitability Over Time', fontsize=14)
            axes[1].set_ylabel('Net Profit (%)')
            axes[1].legend()
            axes[1].grid(True, which='both', linestyle='--', linewidth=0.5)

            # Distribution of net profits (both directions), including negatives
            if not profit_series_1_2.empty or not profit_series_2_1.empty:
                sns.histplot((profit_series_1_2 * 100), bins=40, kde=True, ax=axes[2],
                             color='#1f77b4', alpha=0.35, label=f'{ex1.upper()} -> {ex2.upper()}')
                sns.histplot((profit_series_2_1 * 100), bins=40, kde=True, ax=axes[2],
                             color='#ff7f0e', alpha=0.35, label=f'{ex2.upper()} -> {ex1.upper()}')
            axes[2].axvline(0, color='black', linestyle='--', linewidth=1, label='Breakeven')
            axes[2].set_title('Distribution of Arbitrage Opportunities', fontsize=14)
            axes[2].set_xlabel('Net Profit (%)')
            axes[2].set_ylabel('Frequency')
            axes[2].legend()
            axes[2].grid(True, which='both', linestyle='--', linewidth=0.5)

            plt.tight_layout(rect=[0, 0.03, 1, 0.96])
            base_filename = os.path.basename(csv_path).replace('.csv', '')
            report_filename = f"{base_filename}_{symbol.replace('/', '-')}_{ex1}_vs_{ex2}.png"
            
            results_dir = os.path.dirname(csv_path)
            save_path = os.path.join(results_dir, report_filename)
            
            plt.savefig(save_path, dpi=150)
            plt.close()
            print(f"Successfully generated report: {save_path}")

def create_overall_distribution_report(df, exchanges, pairs, csv_path):
    """Create an aggregated distribution report across all symbols and directions."""
    import seaborn as sns
    plt.figure(figsize=(18, 10))
    plt.suptitle('Cross-Exchange Net Profit Distributions (Aggregated)', fontsize=18, weight='bold')

    n = len(pairs)
    cols = 2
    rows = (n + cols - 1) // cols

    for idx, (ex1, ex2) in enumerate(pairs, start=1):
        ax = plt.subplot(rows, cols, idx)
        net_profit_col_1_2 = f'net_profit_{ex1}_to_{ex2}'
        net_profit_col_2_1 = f'net_profit_{ex2}_to_{ex1}'

        s12 = pd.to_numeric(df.get(net_profit_col_1_2, pd.Series(dtype=float)), errors='coerce').dropna()
        s21 = pd.to_numeric(df.get(net_profit_col_2_1, pd.Series(dtype=float)), errors='coerce').dropna()

        if not s12.empty:
            sns.histplot(s12 * 100, bins=50, kde=True, ax=ax, color='#1f77b4', alpha=0.35, label=f'{ex1.upper()} -> {ex2.upper()}')
        if not s21.empty:
            sns.histplot(s21 * 100, bins=50, kde=True, ax=ax, color='#ff7f0e', alpha=0.35, label=f'{ex2.upper()} -> {ex1.upper()}')

        ax.axvline(0, color='black', linestyle='--', linewidth=1)
        ax.set_title(f'{ex1.upper()} vs {ex2.upper()}')
        ax.set_xlabel('Net Profit (%)')
        ax.set_ylabel('Frequency')
        ax.legend(fontsize=9)
        ax.grid(True, which='both', linestyle='--', linewidth=0.5)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    base_filename = os.path.basename(csv_path).replace('.csv', '')
    results_dir = os.path.dirname(csv_path)
    save_path = os.path.join(results_dir, f"{base_filename}_overall_distribution.png")
    plt.savefig(save_path, dpi=150)
    plt.close()
    print(f"Successfully generated aggregated cross-exchange report: {save_path}")

def main(csv_path):
    """Main function to generate report."""
    if not os.path.exists(csv_path):
        print(f"Error: File not found at {csv_path}")
        sys.exit(1)

    print(f"--- Generating Report for {csv_path} ---")
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            print("CSV file is empty. No report generated.")
            return
            
        exchanges = sorted(list(set([col.split('_')[0] for col in df.columns if '_bid' in col])))
        pairs = list(itertools.combinations(exchanges, 2))

        print_summary_statistics(df, list(itertools.permutations(exchanges, 2)))
        create_report(df, exchanges, pairs, csv_path)
        # Aggregated distribution report across all symbols/directions
        create_overall_distribution_report(df, exchanges, pairs, csv_path)

    except Exception as e:
        print(f"An error occurred while processing the CSV file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
        main(csv_path)
    else:
        print("Usage: python generate_report.py <path_to_csv_file>")
        sys.exit(1)
