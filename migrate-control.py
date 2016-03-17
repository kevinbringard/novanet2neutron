#!/usr/bin/env python

import argparse
import ConfigParser
import MySQLdb
import sys
import time

from novanet2neutron import common

CONF = ConfigParser.ConfigParser()


def add_port(neutronc, instance, network_id, subnet_id,
             mac_address, ip_address):
    body_value = {
        "port": {
            "tenant_id": instance.tenant_id,
            "mac_address": mac_address,
            "fixed_ips": [
                {
                    "subnet_id": subnet_id,
                    "ip_address": ip_address,
                }],
            "network_id": network_id,
        }
    }
    ports = neutronc.list_ports(mac_address=mac_address, network_id=network_id)
    if ports['ports']:
        port = ports['ports'][0]
        print "Not creating port for %s already exists" % mac_address
    else:
        try:
            port = neutronc.create_port(body=body_value)['port']
        except Exception, e:
            print e

    instance_ports = neutronc.list_ports(device_id=instance.id,
                                         network_id=network_id)
    if not instance_ports['ports']:
        try:
            print "attach interface: %s" % port['id']
            instance.interface_attach(port['id'], None, None)
        except Exception, e:
            print e
    else:
        print "Not attaching, already attached %s" % instance.id


def add_ports(neutronc, cursor, mappings, instance, target_zone):
    #suspend = False
    #if instance.status == "SUSPENDED":
    #    instance.resume()
    #    time.sleep(2)
    #    suspend = True
    cursor.execute(
        "SELECT * from network_migration_info where uuid = '%s'" % instance.id)
    networks = cursor.fetchall()

    for network in networks:
        zone = network['availability_zone']
        if zone is None or zone == 'None':
            print "unknown zone for %s" % instance.id
            continue
        if zone != target_zone:
            continue

        network_name = network['network_name']
        ip_v4 = network['ip_v4']
        ip_v6 = network['ip_v6']
        mac_address = network['mac_address']
        network_info = mappings['network_%s:%s' % (zone, network_name)]
        neutron_network = network_info['network_id']
        subnet_v4 = network_info['subnet_v4_id']

        add_port(neutronc, instance, neutron_network,
                 subnet_v4, mac_address, ip_v4)
        if ip_v6 != "None":
            subnet_v6 = network_info['subnet_v6_id']
            add_port(neutronc, instance, neutron_network,
                     subnet_v6, mac_address, ip_v6)
    #if suspend:
    #    instance.suspend()


def create_networks(neutronc):
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
        physnet = CONF.get(section, 'physnet')
	tenant_id = CONF.get(section, 'tenant_id')
        network = common.get_network(neutronc, name)
        vlan = CONF.get(section, 'vlan')
        if not network:
            network = common.create_network(neutronc, name, tenant_id, vlan, physnet)
        mappings[section]['network_id'] = network
        subnet_v4 = common.get_subnet(neutronc, network, 4)
        try:
            gateway_v4 = CONF.get(section, 'gateway_v4')
        except:
            gateway_v4 = None
        if not subnet_v4:
            subnet_v4 = common.create_subnet(
                neutronc, network, 4,
                CONF.get(section, 'cidr_v4'),
                CONF.get(section, 'dns_servers').split(','),
                gateway_v4,
                CONF.get(section, 'tenant_id'),
                CONF.get(section, 'dhcp_start'),
                CONF.get(section, 'dhcp_end'))
        mappings[section]['subnet_v4_id'] = subnet_v4
        if 'cidr_v6' in CONF.options(section):
            subnet_v6 = common.create_subnet(
                neutronc, network, 6,
                CONF.get(section, 'cidr_v6'),
                CONF.get(section, 'dns_servers').split(','),
                CONF.get(section, 'gateway_v6'))
            mappings[section]['subnet_v6_id'] = subnet_v6

    return mappings


def check_hypervisors(novac):
    print "Checking all hypervisors are running fake driver"
    for h in novac.hypervisors.list():
        if h.hypervisor_type != 'fake':
            print 'Hypervisor %s is not fake' % h.hypervisor_hostname
            sys.exit(1)


def collect_args():
    parser = argparse.ArgumentParser(description='novanet2neutron.')

    parser.add_argument('-c', '--config', action='store',
                        default='novanet2neutron.conf', help="Config file")
    parser.add_argument('-z', '--zone', action='store',
                        help="AZ to migrate")
    return parser.parse_args()


def main():
    args = collect_args()
    common.load_config(CONF, args.config)
    target_zone = args.zone
    conn = MySQLdb.connect(
        host=CONF.get('db', 'host'),
        user=CONF.get('db', 'user'),
        passwd=CONF.get('db', 'password'),
        db=CONF.get('db', 'name'))

    cursor = MySQLdb.cursors.DictCursor(conn)
    novac = common.get_nova_client()
    check_hypervisors(novac)
    neutronc = common.get_neutron_client()
    print "creating networks"
    mappings = create_networks(neutronc)
    print "getting instances"
    instances = common.all_servers(novac)
    print "adding ports"

    for i in instances:
        add_ports(neutronc, cursor, mappings, i, target_zone)
    cursor.close()
    conn.close()


if __name__ == "__main__":
    main()
