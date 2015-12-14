#!/usr/bin/env python

import ConfigParser
from netaddr import *
import MySQLdb
import os
import re

NOVA_CONF = "/etc/nova/nova.conf"
NEUTRON_ML2_CONF = "/etc/neutron/plugins/ml2/ml2_conf.ini"
NEUTRON_CONF = "/etc/neutron/neutron.conf"

if os.path.isfile(NOVA_CONF):
        nova_config = ConfigParser.ConfigParser()
        nova_config.read(NOVA_CONF)

if os.path.isfile(NEUTRON_CONF):
        neutron_config = ConfigParser.ConfigParser()
        neutron_config.read(NEUTRON_CONF)

if os.path.isfile(NEUTRON_ML2_CONF):
        neutron_ml2_config = ConfigParser.ConfigParser()
        neutron_ml2_config.read(NEUTRON_ML2_CONF)


novanet2neutron_config = ConfigParser.ConfigParser()

# print nova_config.sections()

nova_db_string = nova_config.get('DEFAULT', 'sql_connection')
neutron_db_string = neutron_ml2_config.get('database', 'connection')

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

def get_creds_info():
	auth_uri = neutron_config.get('keystone_authtoken','identity_uri')
	username = neutron_config.get('keystone_authtoken','admin_user')
	tenant = neutron_config.get('keystone_authtoken','admin_tenant_name')
	password = neutron_config.get('keystone_authtoken','admin_password')
	auth_version = 'v2.0'
	auth_url = auth_uri + "/" + auth_version
	return auth_url, username, tenant, password

def get_all_neutron_networks():
	cursor = MySQLdb.cursors.DictCursor(neutron_conn)
	cursor.execute(
	   "SELECT id from networks where tenant_id != 'NULL'")
	uuids = cursor.fetchall()
	return uuids

def get_all_nova_networks():
	cursor = MySQLdb.cursors.DictCursor(nova_conn)
	cursor.execute(
	   "SELECT uuid from networks where project_id != 'NULL'")
	uuids = cursor.fetchall()
	return uuids

def get_nova_network_info(uuid):
	cursor = MySQLdb.cursors.DictCursor(nova_conn)
	cursor.execute(
	   "SELECT * from networks where uuid = '%s' and deleted = 0" % uuid)
	nova_network = cursor.fetchall()
	return nova_network

def get_neutron_network_info(name):
	cursor = MySQLdb.cursors.DictCursor(neutron_conn)
	sql = "SELECT id from networks where name like '%%%s%%'" % name
	cursor.execute(sql)
	neutron_network = cursor.fetchall()
	return neutron_network

nova_db_host, nova_db_name, nova_db_pass, nova_db_user = get_nova_db_info(nova_db_string)
neutron_db_host, neutron_db_name, neutron_db_pass, neutron_db_user = get_neutron_db_info(neutron_db_string)
creds_auth_url, creds_username, creds_tenant, creds_password = get_creds_info()

nova_conn = MySQLdb.connect(
    host=nova_db_host,
    user=nova_db_user,
    passwd=nova_db_pass,
    db=nova_db_name)

neutron_conn = MySQLdb.connect(
    host=neutron_db_host,
    user=neutron_db_user,
    passwd=neutron_db_pass,
    db=neutron_db_name)

# Open our FH
cfgfile = open("compute.conf", 'w')

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

# Create the [creds] section
novanet2neutron_config.add_section('creds')
novanet2neutron_config.set('creds', 'username', creds_username)
novanet2neutron_config.set('creds', 'password', creds_password)
novanet2neutron_config.set('creds', 'tenant_name', creds_tenant)
novanet2neutron_config.set('creds', 'auth_url', creds_auth_url)

for network in get_all_nova_networks():
        uuid = network['uuid']
        network_info = get_nova_network_info(uuid)
        name = network_info[0]['label']
        device = network_info[0]['bridge_interface']
        bridge = network_info[0]['bridge']
        
        section = "network_" + name
        novanet2neutron_config.add_section(section)
        novanet2neutron_config.set(section, 'nova_name', name)
        novanet2neutron_config.set(section, 'device', device) 
        novanet2neutron_config.set(section, 'bridge', bridge)
	neutron_net_id = get_neutron_network_info(name)[0]['id']
	novanet2neutron_config.set(section, 'neutron_net_id', neutron_net_id)

# Write the file and close the FH
novanet2neutron_config.write(cfgfile)
cfgfile.close()
