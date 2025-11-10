services:
  - type: web
    name: razorpay-php-api
    env: php
    buildCommand: chmod +x build.sh && ./build.sh
    startCommand: php -S 0.0.0.0:10000 autorazorpay.php
    envVars:
      - key: PORT
        value: 10000
    plan: free

  - type: web
    name: razorpay-python-monitor
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: python rz.py
    envVars:
      - key: PORT
        value: 5500
    plan: free
