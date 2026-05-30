import os
import random
import datetime
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "wsia.settings")
django.setup()

from reports.services.report_service import create_report
from reports.services.dedup_service import is_duplicate
from analytics.cleaner import normalize_report

def generate_mock_data():
    protocols = ["Vault", "Swap", "Finance", "Network", "Protocol", "Exchange", "Bridge", "DAO"]
    adjectives = ["Alpha", "Beta", "Gamma", "Omega", "Secure", "Fast", "Liquid", "Solid"]
    
    tags_pool = ["DeFi", "Flash Loan", "Reentrancy", "Access Control", "Phishing", "Rug Pull", "Bridge", "Oracle Manipulation", "Logic Error"]
    
    # 100 days of history
    base_date = datetime.datetime.now(datetime.timezone.utc)
    
    print("Generating 100 mock Rekt reports...")
    
    new_count = 0
    for i in range(1, 101):
        name = f"{random.choice(adjectives)}{random.choice(protocols)}"
        
        # Randomize severity by dollar amount
        severity_tier = random.choices(["critical", "high", "medium", "low"], weights=[10, 30, 40, 20])[0]
        
        if severity_tier == "critical":
            amount = random.randint(10_000_000, 500_000_000)
            desc_amount = f"${amount // 1_000_000}M"
        elif severity_tier == "high":
            amount = random.randint(1_000_000, 9_999_999)
            desc_amount = f"${amount // 1_000_000}M"
        elif severity_tier == "medium":
            amount = random.randint(100_000, 999_999)
            desc_amount = f"${amount // 1_000}K"
        else:
            amount = random.randint(10_000, 99_999)
            desc_amount = f"${amount // 1_000}K"
            
        cause = random.choice(tags_pool)
        
        article = {
            "title": f"{name} - Rekt",
            "description": f"The {name} smart contract was exploited via {cause.lower()}, resulting in a loss of {desc_amount}. The team is investigating.",
            "source_url": f"https://rekt.news/mock-{name.lower()}-{i}/",
            "source": "rekt.news",
            "published_at": (base_date - datetime.timedelta(days=i)).isoformat(),
            "raw_data": {"tags": random.sample(tags_pool, k=random.randint(1, 3))},
        }
        
        url = article["source_url"]
        if is_duplicate(url):
            continue
            
        try:
            report = create_report(**article)
            normalize_report(report)
            new_count += 1
        except Exception as e:
            print(f"Error: {e}")
            
    print(f"✅ Successfully generated and processed {new_count} new mock reports.")

if __name__ == "__main__":
    generate_mock_data()
