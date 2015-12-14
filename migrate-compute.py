#!/usr/bin/env python

import ConfigParser
import socket
import argparse
import MySQLdb
import netifaces

from novanet2neutron import common
from novanet2neutron import utils
from novanet2neutron import virt


CONF = ConfigParser.ConfigParser()


def build_devmap():
    mappings = {}
    for device in netifaces.interfaces():
        try:
            mac = netifaces.ifaddresses(device)[netifaces.AF_LINK][0]['addr']
            mappings[mac] = device
        except:
            print("Skipping interface: %s" % device)
    return mappings


class NetworkMigration(object):

    def __init__(self, network, neutron_client):
        self.network = network
        self.neutron_client = neutron_client


class NeutronMigration(NetworkMigration):

    tap_prefix = 'vnet'

    def get_old_bridge(self):
        return self.network['bridge']

    def get_new_bridge(self):
        return utils.get_neutron_bridge_name(self.network['id'])

    def get_new_tap(self, instance, index):
        ports = self.neutron_client.list_ports(device_id=instance.id,
                                               network_id=self.network['id'])
        if not ports['ports']:
            print "%s ERROR no neutron port found, cannot migrate" % instance.id
            return None
        if len(ports['ports']) != 1:
            print "%s ERROR multiple neutron ports found, cannot migrate" % instance.id
            return None

        new_tap = utils.get_neutron_tap_device_name(ports['ports'][0].get('id'))
        return new_tap


class NovaMigration(NetworkMigration):

    tap_prefix = 'tap'

    def get_old_bridge(self):
        return utils.get_neutron_bridge_name(self.network['id'])

    def get_new_bridge(self):
        return self.network['bridge']

    def get_new_tap(self, instance, index):
        return utils.get_nova_vnet_name(index)


def migrate_interfaces(noop, migrate_manager, neutronc,
                       cursor, networks, instances):
    errors = False
    device_map = build_devmap()
    tap_index = 0
    for network in networks:
        manager = migrate_manager(network, neutronc)
        old_bridge = manager.get_old_bridge()
        new_bridge = manager.get_new_bridge()
        raw_device = network['device']

        # remove interfaces from bridge
        interfaces = utils.get_interfaces_on_bridge(old_bridge)
        for interface in interfaces:
            # Remove all instance taps from bridge
            if interface != raw_device and interface.startswith(manager.tap_prefix):
                utils.rm_dev_from_bridge(noop, old_bridge, interface)
        if not utils.device_exists(new_bridge):
            # Remove pyhsical interfce from bridge
            utils.rm_dev_from_bridge(noop, old_bridge, raw_device)
            # rename bridge
            utils.rename_net_dev(noop, old_bridge, new_bridge)

        interfaces = utils.get_interfaces_on_bridge(new_bridge)
        if raw_device not in interfaces:
            # Add raw device back onto bridge
            utils.add_dev_to_bridge(noop, new_bridge, raw_device)

        for instance in instances:
            print "Migrating %s" % instance.id
            mac_address = common.get_mac_db(cursor, instance, network['nova_name'])
            if not mac_address:
                continue
            if instance.status in ['SHUTOFF', 'SUSPENDED']:
                old_tap = None
            else:
                new_tap = manager.get_new_tap(instance, tap_index)
                if not new_tap:
                    errors = True
                    continue
                tap_index += 1
                if not utils.device_exists(new_tap):
                    # Rename tap
                    mac = mac_address.replace('fa:', 'fe:', 1)
                    old_tap = device_map[mac]
                    utils.rename_net_dev(noop, old_tap, new_tap)
                if new_tap not in interfaces:
                    # add interface to bridge
                    utils.add_dev_to_bridge(noop, new_bridge, new_tap)

            # Don't do this anymore as breaks RH based instances
            #if not virt.has_virt_device(instance, new_tap):
            #    virt.virt_switch_interface(noop, instance, mac_address,
            #                               old_bridge, old_tap,
            #                               new_bridge, new_tap)
    return errors


def collect_args():
    parser = argparse.ArgumentParser(description='novanet2neutron.')

    parser.add_argument('-f', '--for-realsies', action='store_true',
                        default=False, help="Actually do things")
    parser.add_argument('-d', '--direction', action='store',
                        default='neutron', required=True,
                        help="Either migrate to 'nova' or 'neutron'")
    parser.add_argument('-c', '--config', action='store',
                        default='compute.conf', help="Config file")
    return parser.parse_args()


def get_network(neutronc, net_id):
    network = neutronc.list_networks(id=net_id)['networks'][0]
    subnets = neutronc.list_subnets(network_id=network['id'])['subnets']
    for subnet in subnets:
        network['subnet_v%s' % subnet['ip_version']] = subnet['id']
    return network


def main():
    args = collect_args()
    common.load_config(CONF, args.config)
    noop = True
    if args.for_realsies:
        noop = False
    else:
        print "Running migration in noop mode, use -f to actually migrate things"
    direction = args.direction
    conn = MySQLdb.connect(
        host=CONF.get('db', 'host'),
        user=CONF.get('db', 'user'),
        passwd=CONF.get('db', 'password'),
        db=CONF.get('db', 'name'))

    cursor = MySQLdb.cursors.DictCursor(conn)

    url = CONF.get('creds', 'auth_url')
    username = CONF.get('creds', 'username')
    password = CONF.get('creds', 'password')
    tenant = CONF.get('creds', 'tenant_name')

    host = socket.gethostname()
    novac = common.get_nova_client(username=username,
                                   password=password,
                                   tenant=tenant,
                                   url=url)

    neutronc = common.get_neutron_client(username=username,
                                         password=password,
                                         tenant=tenant,
                                         url=url)

    networks = []
    for section in CONF.sections():
        if section.startswith('network_'):
            network_id = CONF.get(section, 'neutron_net_id')
            network = get_network(neutronc, network_id)
            for option in ('device', 'bridge', 'nova_name'):
                network[option] = CONF.get(section, option)
            print network
            networks.append(network)

    instances = common.all_servers(novac, host=host)
    if direction == 'neutron':
        manager = NeutronMigration
    elif direction == 'nova':
        manager = NovaMigration
    else:
        print "unknown direction"
    print "Running checks"
    errors = migrate_interfaces(True, manager, neutronc, cursor,
                                networks, instances)
    if not noop and not errors:
        print "running for real"
        migrate_interfaces(False, manager, neutronc,
                           cursor, networks, instances)
    if errors:
        print "ERROR: Cannot run due to errors"
    cursor.close()
    conn.close()
    print "SUCCESS!"

if __name__ == "__main__":
    main()
