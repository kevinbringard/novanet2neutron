#!/usr/bin/env python

import argparse
import ConfigParser
import MySQLdb

from novanet2neutron import common

def collect_args():
    parser = argparse.ArgumentParser(description='novanet2neutron.')

    parser.add_argument('-c', '--config', action='store',
                        default='novanet2neutron.conf', help="Config file")
    parser.add_argument('-z', '--zone', action='store',
                        help="AZ to migrate")
    return parser.parse_args()


def update_dhcp_ip(port_id, dhcp_server):
    cursor = MySQLdb.cursors.DictCursor(neutron_conn)
    cursor.execute("""
       UPDATE ipallocations
       SET ip_address = %s
       WHERE port_id = %s
    """, (dhcp_server, port_id))
    cursor.connection.commit()

def get_dhcp_port(network_id):
    cursor = MySQLdb.cursors.DictCursor(neutron_conn)
    cursor.execute(
       "SELECT ipallocations.port_id FROM ml2_port_bindings, ipallocations WHERE ml2_port_bindings.host LIKE 'neutron-dhcp%%' AND ipallocations.port_id = ml2_port_bindings.port_id AND network_id = '%s'" % network_id)
    dhcp_port = cursor.fetchall()

    return dhcp_port

def get_all_network_ids():
    cursor = MySQLdb.cursors.DictCursor(neutron_conn)
    cursor.execute(
       "SELECT id FROM networks")
    uuids = cursor.fetchall()

    return uuids

args = collect_args()
CONF = ConfigParser.ConfigParser()
common.load_config(CONF, args.config)

neutron_conn = MySQLdb.connect(
    host=CONF.get('neutron_db', 'host'),
    user=CONF.get('neutron_db', 'user'),
    passwd=CONF.get('neutron_db', 'password'),
    db=CONF.get('neutron_db', 'name'))

cursor = MySQLdb.cursors.DictCursor(neutron_conn)

networks = get_all_network_ids()
neutronc = common.get_neutron_client()
mappings = {}
for section in CONF.sections():
    if not section.startswith('network_'):
        continue
    mappings[section] = {}

    for option in CONF.options(section):
        mappings[section][option] = CONF.get(section, option)


    zone = CONF.get(section, 'zone')
    network_name = CONF.get(section, 'name')
    if zone == network_name:
        name = zone
    else:
        name = "%s" % (network_name)

    dhcp_server = CONF.get(section, 'dhcp_server')
    network_id = common.get_network(neutronc, name)
    # print mappings
    print "network: %s" % network_id
    print "dhcp_server: %s" % dhcp_server

    dhcp_port = get_dhcp_port(network_id)
    print "dhcp_port: %s" % dhcp_port[0]['port_id']
    update_dhcp_ip(dhcp_port[0]['port_id'], dhcp_server)
