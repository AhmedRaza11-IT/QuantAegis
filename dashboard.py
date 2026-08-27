"""
dashboard.py — Launch script for the QuantAegis Interactive Web Dashboard.
"""
import os
import uvicorn
from quantaegis.dashboard.app import app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")
    print("\n" + "=" * 60)
    print("  🚀 QUANTAEGIS WEB DASHBOARD & DECISION PLATFORM")
    print("=" * 60)
    print(f"  🌐 Access the live dashboard on http://localhost:{port}")
    print("=" * 60 + "\n")
    uvicorn.run("quantaegis.dashboard.app:app", host=host, port=port, reload=False)
