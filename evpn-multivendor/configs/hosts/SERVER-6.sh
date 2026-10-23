ip addr flush dev eth0
ip addr add 10.10.10.106/24 dev eth0
ip link set eth0 up
ip route replace default via 10.10.10.1
