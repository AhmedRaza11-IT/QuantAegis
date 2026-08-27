"""
dashboard.py — Launch script for the QuantAegis Interactive Web Dashboard.
"""
import uvicorn
from quantaegis.dashboard.app import app

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  🚀 QUANTAEGIS WEB DASHBOARD & DECISION PLATFORM")
    print("=" * 60)
    print("  🌐 Access the live dashboard in your browser:")
    print("     👉 http://localhost:8000")
    print("     👉 http://127.0.0.1:8000")
    print("=" * 60 + "\n")
    uvicorn.run("quantaegis.dashboard.app:app", host="127.0.0.1", port=8000, reload=False)
