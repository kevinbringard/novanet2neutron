#!/usr/bin/env python

import ConfigParser
from netaddr import *
import MySQLdb
import os
import re
import sys

NOVA_CONF = "/etc/nova/nova.conf"
NEUTRON_CONF = "/etc/neutron/plugins/ml2/ml2_conf.ini"
DNSMASQ_CONF="/etc/nova/dnsmasq.conf"
ZONE = "dev10"
PHYSNET = "bond0"

if ZONE is None or ZONE == "":
  print "You need to set ZONE in this script"
  sys.exit(1)
elif PHYSNET is None or PHYSNET == "":
  print "You need to set PHYSNET in this script"
  sys.exit(1)

if os.path.isfile(NOVA_CONF):
    nova_config = ConfigParser.ConfigParser()
    nova_config.read(NOVA_CONF)

if os.path.isfile(NEUTRON_CONF):
        neutron_config = ConfigParser.ConfigParser()
        neutron_config.read(NEUTRON_CONF)

novanet2neutron_config = ConfigParser.ConfigParser()

# print nova_config.sections()

nova_db_string = nova_config.get('DEFAULT', 'sql_connection')
neutron_db_string = neutron_config.get('database', 'connection')

def get_nova_db_info(db_string):
    # Get the DB Host and Name
    split_string = re.split(r':', db_string)
    split_string = re.split(r'@', split_string[-1])
    split_string = re.split(r'/', split_string[-1])
    db_host = split_string[0]
    split_string = re.split(r'\?', split_string[-1])
    db_name = split_string[0]

    # Start over to get the DB pass
    split_string = re.split(r':', db_string)
    db_pass = re.split(r'@', split_string[-1])

    # And finally, get the db_user
    split_string = re.split(r':', db_string)
    db_user = [ re.sub(r'//','', string) for string in split_string ]

    return db_host, db_name, db_pass[0], db_user[1]

def get_neutron_db_info(db_string):
        # Get the DB Host and Name
        split_string = re.split(r':', db_string)
        split_string = re.split(r'@', split_string[-1])
        split_string = re.split(r'/', split_string[-1])
        db_host = split_string[0]
        split_string = re.split(r'\?', split_string[-1])
        db_name = split_string[0]

        # Start over to get the DB pass
        split_string = re.split(r':', db_string)
        db_pass = re.split(r'@', split_string[-1])

        # And finally, get the db_user
        split_string = re.split(r':', db_string)
        db_user = [ re.sub(r'//','', string) for string in split_string ]

        return db_host, db_name, db_pass[0], db_user[1]

def get_free_ips_for_net(network_id):
    cursor = MySQLdb.cursors.DictCursor(conn)
    # select address from fixed_ips, networks where networks.id = fixed_ips.network_id and fixed_ips.reserved = 0 and networks.uuid = '02ad4c9b-ebe8-491a-b288-e33069ab4236';
    cursor.execute(
       "SELECT address FROM fixed_ips, networks WHERE networks.id = fixed_ips.network_id AND fixed_ips.reserved = 0 AND networks.uuid = '%s'" % network_id)
    free_ips = cursor.fetchall()

    return free_ips

def generate_dhcp_allocation_pools(network_id):
    free_ips = get_free_ips_for_net(network_id)
    ip_list = []
    for ip in free_ips:
        ip_list.append(IPAddress(ip['address']))
    merged_list = cidr_merge(ip_list)

    ip_ranges = ""
    for network in merged_list:
        allocation_pool = IPSet(network)
        if ip_ranges == "":
            ip_ranges = str(allocation_pool.iprange())
        else:
            ip_ranges = ip_ranges + "," + str(allocation_pool.iprange())

    return ip_ranges

def get_all_networks():
    cursor = MySQLdb.cursors.DictCursor(conn)
    cursor.execute(
       "SELECT uuid from networks where project_id != 'NULL'")
    uuids = cursor.fetchall()
    return uuids

def get_network_info(uuid):
    cursor = MySQLdb.cursors.DictCursor(conn)
    cursor.execute(
       "SELECT * from networks where uuid = '%s' and deleted = 0" % uuid)
    network = cursor.fetchall()
    return network

def get_dhcp_end(cidr):
    net = IPNetwork(cidr)
    return net[-2]

def get_dnsmasq_gateway(network):
    config_file = open(DNSMASQ_CONF)
    content = config_file.readlines()
    for line in content:
        if "router," in line:
            router_line = re.split(r',', line)
            # print router_line
            router_ip = router_line[-1].rstrip()
            for item in router_line:
                if "tag:" in item:
                    item = item.split(":")
                    if network == item[-1]:
                        return router_ip
                    else:
                        continue

def get_dhcp_server_address(network):
    # dhcp-option-force=tag:dev10-2199,option:classless-static-route,169.254.169.254/32,10.219.0.4
    print network
    config_file = open(DNSMASQ_CONF)
    content = config_file.readlines()
    for line in content:
        if "classless-static-route" in line:
            dhcp_line = re.split(r',', line)
            print dhcp_line
            dhcp_ip = dhcp_line[-1].rstrip()
            print dhcp_ip
            for item in dhcp_line:
                if "tag:" in item:
                    item = item.split(":")
                    if network == item[-1]:
                        return dhcp_ip
                    else:
                        continue
    return

# Pull the DB info out of the config files
nova_db_host, nova_db_name, nova_db_pass, nova_db_user = get_nova_db_info(nova_db_string)
neutron_db_host, neutron_db_name, neutron_db_pass, neutron_db_user = get_neutron_db_info(neutron_db_string)

conn = MySQLdb.connect(
    host=nova_db_host,
    user=nova_db_user,
    passwd=nova_db_pass,
    db=nova_db_name)

for network in get_all_networks():
    uuid = network['uuid']
    network_info = get_network_info(uuid)
    # print network_info
    name = network_info[0]['label']
    cidr_v4 = network_info[0]['cidr']
    if os.path.isfile(DNSMASQ_CONF):
        gateway_v4 = get_dnsmasq_gateway(name)
    else:
        gateway_v4 = network_info[0]['gateway']
    dhcp_start = network_info[0]['dhcp_start']
    dhcp_end = get_dhcp_end(cidr_v4)
    dns_server1 = network_info[0]['dns1']
    dns_server2 = network_info[0]['dns2']
    tenant_id = network_info[0]['project_id']
    vlan = network_info[0]['vlan']
    allocation_pools = generate_dhcp_allocation_pools(uuid)
    dhcp_server = get_dhcp_server_address(name)
    dns_servers = ""
    if dns_server1 and dns_server2:
        dns_servers = "%s,%s" % (dns_server1, dns_server2)
    elif dns_server1:
        dns_servers = dns_server1
    elif dns_server2:
        dns_servers = dns_server2

    section = "network_" + ZONE + ":" + name
    novanet2neutron_config.add_section(section)
    novanet2neutron_config.set(section, 'zone', ZONE)
    novanet2neutron_config.set(section, 'name', name)
    novanet2neutron_config.set(section, 'physnet', PHYSNET)
    novanet2neutron_config.set(section, 'cidr_v4', cidr_v4)
    novanet2neutron_config.set(section, 'gateway_v4', gateway_v4)
    novanet2neutron_config.set(section, 'dhcp_start', dhcp_start)
    novanet2neutron_config.set(section, 'dhcp_end', dhcp_end)
    novanet2neutron_config.set(section, 'allocation_pools', allocation_pools)
    novanet2neutron_config.set(section, 'dhcp_server', dhcp_server)
    novanet2neutron_config.set(section, 'dns_servers', dns_servers)
    novanet2neutron_config.set(section, 'tenant_id', tenant_id)
    novanet2neutron_config.set(section, 'vlan', vlan)

# Open our FH
cfgfile = open("novanet2neutron.conf", 'w')

# Create the [db] section
novanet2neutron_config.add_section('db')
novanet2neutron_config.set('db', 'host', nova_db_host)
novanet2neutron_config.set('db', 'name', nova_db_name)
novanet2neutron_config.set('db', 'user', nova_db_user)
novanet2neutron_config.set('db', 'password', nova_db_pass)

# Create the [nova_db] section
novanet2neutron_config.add_section('nova_db')
novanet2neutron_config.set('nova_db', 'host', nova_db_host)
novanet2neutron_config.set('nova_db', 'name', nova_db_name)
novanet2neutron_config.set('nova_db', 'user', nova_db_user)
novanet2neutron_config.set('nova_db', 'password', nova_db_pass)

# Create the [neutron_db] section
novanet2neutron_config.add_section('neutron_db')
novanet2neutron_config.set('neutron_db', 'host', neutron_db_host)
novanet2neutron_config.set('neutron_db', 'name', neutron_db_name)
novanet2neutron_config.set('neutron_db', 'user', neutron_db_user)
novanet2neutron_config.set('neutron_db', 'password', neutron_db_pass)

# Write the file and close the FH
novanet2neutron_config.write(cfgfile)
cfgfile.close()
