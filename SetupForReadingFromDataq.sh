#!/bin/bash
#Setup script and notes for working with DATAQ DI-4108 digitizer
#22 August 2018
#T. Golfinopoulos

#Install pyusb
sudo pip install pyusb
sudo pip3 install pyusb

#Create rules file for adjusting permissions
#for pyusb to communicate with dataq di-4108 device
my_file="/etc/udev/rules.d/99-usbftdi.rules"
sudo touch $my_file
sudo echo "# Set up rules to adjust permissions for communicating"  > $my_file

sudo echo "# with, e.g. di-4108 digitizer via pyusb" > $my_file

sudo echo "# $(date)" > $my_file

sudo echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="0683", MODE="0666"'  > $my_file
