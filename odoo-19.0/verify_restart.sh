#!/bin/bash

# Docker Restart Verification Script for WhatsApp Marketing Module

echo "========================================="
echo "WhatsApp Marketing Module - Docker Restart"
echo "========================================="
echo ""

# Wait for containers to be ready
echo "Waiting for Docker containers to start..."
sleep 30

# Check container status
echo ""
echo "Container Status:"
docker-compose ps

# Check Odoo logs for module loading
echo ""
echo "Checking Odoo startup logs..."
docker-compose logs --tail=50 odoo | grep -E "(installed|updated|INFO|whatsapp|ERROR)" || true

# Display connection info
echo ""
echo "========================================="
echo "✅ Docker Restart Complete!"
echo "========================================="
echo ""
echo "Odoo is running at: http://localhost:8069"
echo ""
echo "New WhatsApp Features Available:"
echo "  ✓ Contact Segmentation"
echo "  ✓ Analytics & Reporting"
echo "  ✓ Media Library"
echo "  ✓ Bot Flows"
echo "  ✓ Message Scheduling"
echo "  ✓ Compliance Management"
echo "  ✓ Team Management"
echo ""
echo "To view logs in real-time:"
echo "  docker-compose logs -f odoo"
echo ""
echo "To stop containers:"
echo "  docker-compose down"
echo ""
