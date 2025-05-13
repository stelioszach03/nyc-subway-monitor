#!/bin/bash

# Δυναμική δημιουργία crontab με το προκαθορισμένο χρονοδιάγραμμα
echo "$TRAINING_SCHEDULE /app/train_cron.sh >> /var/log/training.log 2>&1" > /etc/cron.d/model-training
chmod 0644 /etc/cron.d/model-training
crontab /etc/cron.d/model-training

# Αρχική εκπαίδευση με την έναρξη
echo "Εκτέλεση αρχικής εκπαίδευσης..."
/app/train_cron.sh

# Έναρξη του cron service σε foreground mode
echo "Έναρξη υπηρεσίας cron με προγραμματισμό: $TRAINING_SCHEDULE"
cron -f