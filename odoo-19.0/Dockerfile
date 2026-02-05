FROM python:3.12-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libldap2-dev \
    libsasl2-dev \
    libxml2-dev \
    libxslt1-dev \
    libpq-dev \
    libjpeg-dev \
    zlib1g-dev \
    python3-dev \
    postgresql-client \
    curl \
    node-less \
    && rm -rf /var/lib/apt/lists/*

# Install wkhtmltopdf (using the version for bookworm)
RUN curl -o wkhtmltox.deb -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_amd64.deb \
    && apt-get update && apt-get install -y --no-install-recommends ./wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/* wkhtmltox.deb

# Set working directory
WORKDIR /opt/odoo

# Copy requirements and install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Odoo source code
COPY . .

# Expose Odoo port
EXPOSE 8069

# Set default configuration file environment variable
ENV ODOO_RC /etc/odoo/odoo.conf

# Use entrypoint script
RUN chmod +x entrypoint.sh
ENTRYPOINT ["/opt/odoo/entrypoint.sh"]
CMD ["python3", "odoo-bin"]
