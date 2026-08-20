#### Machine inventory app works with CLI tools and web interface.
Before you do the install, 
- please update reservation.config file with correct server IP address.
- also check ip address and port in app.py to match it with server IP.


Install script will do the installation of machinesapp web service, reminder timer and reminder service as a systemd services/timers.
```
$ sudo bash ./install.sh
```

To uninstall the software do following,
```
sudo systemctl disable --now machine_reservation_reminder.timer
sudo systemctl stop machine_reservation_reminder.service
sudo systemctl stop machinesapp.service
sudo systemctl disable machinesapp.service

sudo rm -f /etc/systemd/system/machinesapp.service
sudo rm -f /etc/systemd/system/machine_reservation_reminder.service
sudo rm -f /etc/systemd/system/machine_reservation_reminder.service

sudo systemctl daemon-reload
sudo systemctl reset-failed

sudo rm -f /usr/local/etc/reservation.config
sudo rm -f /opt/machinesapp

systemctl list-timers | grep machine_reservation_reminder
systemctl status machine_reservation_reminder.timer
systemctl status machine_reservation_reminder.service
systemctl status machinesapp.service

```
