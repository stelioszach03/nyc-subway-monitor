#!/bin/bash

# Καλύτερος χειρισμός σφαλμάτων
set -e

# Περιμένουμε λίγο για να εξασφαλίσουμε ότι τα άλλα services έχουν ξεκινήσει
echo "Waiting for other services to initialize..."
sleep 30

# Δημιουργία του crontab αρχείου δυναμικά από το env var
echo "Ρύθμιση cron με schedule: $TRAINING_SCHEDULE"
printf "%s python /app/train.py && curl -s -X POST http://ml:8000/reload-model\n" "$TRAINING_SCHEDULE" > /etc/crontabs/root
chmod 644 /etc/crontabs/root
crontab -l

# Αρχική εκπαίδευση με την έναρξη
echo "Εκτέλεση αρχικής εκπαίδευσης..."
for attempt in {1..3}; do
    echo "Training attempt $attempt..."
    if python /app/train.py; then
        echo "Initial training completed successfully!"
        # Ειδοποίηση ML service για επαναφόρτωση του μοντέλου
        curl -s -X POST http://ml:8000/reload-model
        break
    else
        echo "Training attempt $attempt failed"
        if [ $attempt -lt 3 ]; then
            echo "Waiting before retry..."
            sleep 60
        else
            echo "Warning: Initial training failed after 3 attempts. Will rely on scheduled training."
        fi
    fi
done

# Έναρξη του cron service σε foreground mode
echo "Starting cron service with schedule: $TRAINING_SCHEDULE"
cron -f