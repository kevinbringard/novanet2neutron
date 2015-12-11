#!/usr/bin/env python

import ConfigParser
from netaddr import *
import MySQLdb
import os
import re

NOVA_CONF = "/etc/nova/nova.conf"
NEUTRON_CONF = "/etc/neutron/plugins/ml2/ml2_conf.ini"
ZONE = "nova"
PHYSNET = "vlan_net1"

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
	gateway_v4 = network_info[0]['gateway']
	dhcp_start = network_info[0]['dhcp_start']
	dhcp_end = get_dhcp_end(cidr_v4)
	dns_server1 = network_info[0]['dns1']
	dns_server2 = network_info[0]['dns2']
	tenant_id = network_info[0]['project_id']
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
	novanet2neutron_config.set(section, 'dns_servers', dns_servers)
	novanet2neutron_config.set(section, 'tenant_id', tenant_id)

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
