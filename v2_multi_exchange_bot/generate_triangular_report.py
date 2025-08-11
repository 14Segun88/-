import pandas as pd
import matplotlib.pyplot as plt
import sys
import os

def generate_triangular_report(csv_path):
    """Generates a PNG report from a triangular arbitrage CSV file with distributions."""
    print(f"--- Generating Triangular Arbitrage Report for {csv_path} ---")
    try:
        df = pd.read_csv(csv_path)
        if df.empty:
            print("CSV file is empty. No report generated.")
            return

        df['timestamp'] = pd.to_datetime(df['timestamp'])

        plt.style.use('dark_background')
        fig, axes = plt.subplots(2, 1, figsize=(16, 12), gridspec_kw={'height_ratios': [2, 1]})

        # Define colors for exchanges
        colors = {'binance': '#F3BA2F', 'kraken': '#5845D9'}
        
        # Scatter over time
        for exchange, group in df.groupby('exchange'):
            axes[0].scatter(group['timestamp'], group['profit_net_percent'], 
                            label=f"{exchange.capitalize()} ({len(group)} opps)", 
                            color=colors.get(exchange, '#FFFFFF'), alpha=0.7, s=15)

        axes[0].axhline(0, color='red', linestyle='--', linewidth=0.8, label='Breakeven')
        
        max_profit = df['profit_net_percent'].max()
        avg_profit = df['profit_net_percent'].mean()

        axes[0].set_title(f'Profitability Over Time\nMax Profit: {max_profit:.4f}% | Avg Profit: {avg_profit:.4f}%', fontsize=16)
        axes[0].set_xlabel('Timestamp', fontsize=12)
        axes[0].set_ylabel('Net Profit (%)', fontsize=12)
        axes[0].legend()
        axes[0].grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)

        # Distribution histograms by exchange
        try:
            import seaborn as sns
            for exchange, group in df.groupby('exchange'):
                sns.histplot(group['profit_net_percent'], bins=40, kde=True, ax=axes[1],
                             label=f"{exchange.capitalize()}", alpha=0.35, color=colors.get(exchange, '#FFFFFF'))
        except Exception:
            # fallback to matplotlib hist
            for exchange, group in df.groupby('exchange'):
                axes[1].hist(group['profit_net_percent'], bins=40, alpha=0.35, label=f"{exchange.capitalize()}",
                             color=colors.get(exchange, '#FFFFFF'))
        axes[1].axvline(0, color='white', linestyle='--', linewidth=1, label='Breakeven')
        axes[1].set_title('Distribution of Arbitrage Opportunities', fontsize=14)
        axes[1].set_xlabel('Net Profit (%)')
        axes[1].set_ylabel('Frequency')
        axes[1].legend()
        axes[1].grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)
        
        fig.tight_layout()

        output_filename = os.path.splitext(csv_path)[0] + '_report.png'
        plt.savefig(output_filename, dpi=150)
        print(f"Successfully generated report: {output_filename}")

        # Additionally, generate a per-exchange report PNG
        for exchange, group in df.groupby('exchange'):
            fig2, axes2 = plt.subplots(2, 1, figsize=(16, 12), gridspec_kw={'height_ratios': [2, 1]})
            fig2.suptitle(f'Triangular Arbitrage - {exchange.capitalize()}', fontsize=16)

            # time scatter
            axes2[0].scatter(group['timestamp'], group['profit_net_percent'],
                             color=colors.get(exchange, '#FFFFFF'), alpha=0.7, s=15,
                             label=f"{exchange.capitalize()} ({len(group)} opps)")
            axes2[0].axhline(0, color='red', linestyle='--', linewidth=0.8, label='Breakeven')
            axes2[0].set_title('Profitability Over Time')
            axes2[0].set_xlabel('Timestamp')
            axes2[0].set_ylabel('Net Profit (%)')
            axes2[0].legend()
            axes2[0].grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)

            # histogram
            try:
                import seaborn as sns
                sns.histplot(group['profit_net_percent'], bins=40, kde=True, ax=axes2[1],
                             color=colors.get(exchange, '#FFFFFF'), alpha=0.35, label=exchange.capitalize())
            except Exception:
                axes2[1].hist(group['profit_net_percent'], bins=40, alpha=0.35,
                              color=colors.get(exchange, '#FFFFFF'), label=exchange.capitalize())
            axes2[1].axvline(0, color='white', linestyle='--', linewidth=1, label='Breakeven')
            axes2[1].set_title('Distribution of Arbitrage Opportunities')
            axes2[1].set_xlabel('Net Profit (%)')
            axes2[1].set_ylabel('Frequency')
            axes2[1].legend()
            axes2[1].grid(True, which='both', linestyle='--', linewidth=0.5, alpha=0.5)

            fig2.tight_layout()
            per_exchange_filename = os.path.splitext(csv_path)[0] + f'_report_{exchange}.png'
            plt.savefig(per_exchange_filename, dpi=150)
            print(f"Successfully generated exchange report: {per_exchange_filename}")

    except Exception as e:
        print(f"Error generating report: {e}")

if __name__ == '__main__':
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
        generate_triangular_report(csv_file)
    else:
        print("Usage: python generate_triangular_report.py <path_to_csv_file>")
