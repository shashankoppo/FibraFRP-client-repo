# ── Stage 1: Builder ─────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

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
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/odoo

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Addon collections often ship their own Python requirements. Install every
# discovered requirements.txt so custom and third-party modules can load.
COPY custom_addons ./custom_addons
COPY third_party_addons ./third_party_addons
RUN find custom_addons third_party_addons -name requirements.txt -type f -print0 \
    | xargs -0 -r -n 1 pip install --no-cache-dir --prefix=/install -r

# ── Stage 2: Runtime ─────────────────────────────────────────────
FROM python:3.12-slim-bookworm

# Runtime-only system dependencies (no build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libldap-2.5-0 \
    libsasl2-2 \
    libxml2 \
    libxslt1.1 \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    postgresql-client \
    openssl \
    ca-certificates \
    curl \
    node-less \
    libmagic1 \
    xz-utils \
    && rm -rf /var/lib/apt/lists/*

# Install wkhtmltopdf (using the version for bookworm)
RUN curl -o wkhtmltox.deb -sSL https://github.com/wkhtmltopdf/packaging/releases/download/0.12.6.1-3/wkhtmltox_0.12.6.1-3.bookworm_amd64.deb \
    && apt-get update && apt-get install -y --no-install-recommends ./wkhtmltox.deb \
    && rm -rf /var/lib/apt/lists/* wkhtmltox.deb

# Copy pre-built Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root odoo user
RUN useradd --create-home --shell /bin/bash odoo \
    && mkdir -p /opt/odoo /etc/odoo /var/log/odoo \
    && chown -R odoo:odoo /opt/odoo /etc/odoo /var/log/odoo

# Set working directory
WORKDIR /opt/odoo

# Copy Odoo source code
COPY --chown=odoo:odoo . .

# Expose Odoo port
EXPOSE 8069

# Set default configuration file environment variable
ENV ODOO_RC=/etc/odoo/odoo.conf

# Use entrypoint script
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN sed -i 's/\r$//' /usr/local/bin/entrypoint.sh && chmod +x /usr/local/bin/entrypoint.sh

# Built-in health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=5 \
    CMD curl -fsS http://127.0.0.1:8069/web/health > /dev/null || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["python3", "odoo-bin"]
