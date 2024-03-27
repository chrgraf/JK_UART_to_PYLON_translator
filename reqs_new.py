sudo apt-get install python3-pip
pip install cantools
pip install serial
pip install paho-mqtt



$ ramdisk
file /etc/fstab
tmpfs /mnt/ramdisk tmpfs nodev,nosuid,size=50M 0 0


sudo mkdir /mnt/ramdisk
sudo chmod 777 /mnt/ramdisk/
sudo chown behn:behn /mnt/ramdisk/



