FROM php:8.2-alpine

# Install required PHP extensions
RUN docker-php-ext-install curl json mbstring

# Copy your files
COPY autorazorpay.php /app/
COPY proxy.txt /app/

# Set working directory
WORKDIR /app

# Expose port
EXPOSE 10000

# Start PHP server
CMD ["php", "-S", "0.0.0.0:10000", "autorazorpay.php"]
