import os
import time
import json
import random
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

# Your existing monitoring functions here...
def check_url_and_capture(input_url: str):
    """Your existing monitoring function"""
    # [KEEP ALL YOUR ORIGINAL MONITORING LOGIC]
    try:
        # Simulate monitoring logic
        time.sleep(3)  # Simulate processing time
        
        # Simulate different outcomes
        outcomes = [
            {"3ds": True, "status": "Approved", "message": "Payment Captured Successfully ✅"},
            {"3ds": False, "status": "Declined", "message": "Payment Failed / Declined"},
            {"3ds": True, "status": "3DS Required", "message": "3DS Authentication Required"}
        ]
        
        result = random.choice(outcomes)
        result["url"] = input_url
        result["checked_at"] = time.time()
        
        return result
    except Exception as e:
        return {"error": str(e), "status": "Error"}

@app.route('/process')
def process_and_check():
    """Single endpoint that processes payment AND checks status"""
    lista = request.args.get('lista')
    amount = request.args.get('amount', '100')
    site = request.args.get('site')
    
    if not lista or not site:
        return jsonify({"error": "Missing parameters"}), 400
    
    # Start timing
    start_time = time.time()
    
    # Step 1: Process payment (simulate PHP functionality)
    processing_result = {
        "processing": {
            "success": True,
            "device_id": f"py_{random.randint(100000, 999999)}",
            "amount": amount,
            "card_used": lista.split('|')[0][-4:],  # Last 4 digits
            "site": site,
            "processed_at": time.time()
        }
    }
    
    # Step 2: Wait for payment to complete
    time.sleep(5)
    
    # Step 3: Check payment status
    monitoring_result = check_url_and_capture(site)
    
    # Combine both results
    final_result = {
        **processing_result,
        "status_check": monitoring_result,
        "summary": {
            "total_time": round(time.time() - start_time, 2),
            "final_status": monitoring_result.get("status", "Unknown"),
            "timestamp": time.time()
        }
    }
    
    return jsonify(final_result)

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5500))
    app.run(host="0.0.0.0", port=port, debug=False)
