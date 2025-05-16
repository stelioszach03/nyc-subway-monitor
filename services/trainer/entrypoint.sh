#!/bin/bash

# Καλύτερος χειρισμός σφαλμάτων
set -e

# Καθαρισμός προηγούμενου crontab
crontab -r || true

# Δυναμική δημιουργία crontab με το προκαθορισμένο χρονοδιάγραμμα και προσθήκη username (root)
echo "$TRAINING_SCHEDULE root /app/train_cron.sh >> /var/log/training.log 2>&1" > /etc/cron.d/model-training
echo "*/30 * * * * root /app/train_cron.sh >> /var/log/training.log 2>&1" >> /etc/cron.d/model-training
echo "" >> /etc/cron.d/model-training  # Add empty line at the end of crontab
chmod 0644 /etc/cron.d/model-training
crontab /etc/cron.d/model-training

# Περιμένουμε λίγο για να εξασφαλίσουμε ότι τα άλλα services έχουν ξεκινήσει
echo "Waiting for other services to initialize..."
sleep 30

# Αρχική εκπαίδευση με την έναρξη
echo "Εκτέλεση αρχικής εκπαίδευσης..."
for attempt in {1..3}; do
    echo "Training attempt $attempt..."
    if /app/train_cron.sh; then
        echo "Initial training completed successfully!"
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
echo "Έναρξη υπηρεσίας cron με προγραμματισμό: $TRAINING_SCHEDULE και επιπλέον εκπαιδεύσεις κάθε 30 λεπτά"
cron -f