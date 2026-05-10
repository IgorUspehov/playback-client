#!/bin/bash
LOG="/home/igor/playback-client/view_counts.log"
TRACK="https://www.youtube.com/watch?v=01LUZ8zP_aQ"

echo "=== Старт мониторинга (logged_in=True): $(date) ===" >> "$LOG"

while true; do
    VIEWS=$(yt-dlp --print "%(view_count)s" "$TRACK" 2>/dev/null)
    echo "$(date '+%Y-%m-%d %H:%M:%S') | Views: $VIEWS" >> "$LOG"
    echo "$(date '+%H:%M:%S') | Views: $VIEWS"
    sleep 900
done
