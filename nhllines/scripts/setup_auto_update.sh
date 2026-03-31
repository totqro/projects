#!/bin/bash
# Setup automatic updates daily at 4pm using cron

echo "🤖 Setting up automatic NHL Lines updates"
echo "=========================================="
echo ""

# Create the cron job entry - runs daily at 4pm
CRON_JOB="0 16 * * * /bin/bash ~/Desktop/nhllines/auto_update_safe.sh"

# Check if cron job already exists
if crontab -l 2>/dev/null | grep -q "nhllines"; then
    echo "⚠️  Cron job already exists. Removing old one..."
    crontab -l 2>/dev/null | grep -v "nhllines" | crontab -
fi

# Add the new cron job
echo "Adding cron job to run daily at 4:00 PM..."
(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo ""
echo "✅ Automatic updates configured!"
echo ""
echo "Schedule: Daily at 4:00 PM"
echo ""
echo "Logs will be saved to: ~/Desktop/nhllines/cron.log"
echo ""
echo "To view your cron jobs:"
echo "  crontab -l"
echo ""
echo "To view the log:"
echo "  tail -f ~/Desktop/nhllines/cron.log"
echo ""
echo "To remove automatic updates:"
echo "  crontab -l | grep -v nhllines | crontab -"
echo ""
