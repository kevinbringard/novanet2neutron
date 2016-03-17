===============================================
Scripts to migrate from nova-network -> Neutron
===============================================

These scripts will migrate an install a simple flat nova-network setup to Neutron.
It will use linuxbridge plugin.

"simple" and "flat" meaning one or more shared provider networks (neutron speak)

It requires that the control plane will be unavailable to users during the migration.
Instance traffic will largely be unaffected with a ~5 second downtime while renaming
the interfaces. The nova-api-metadata service will also be unavailable during the migration

This branch has been tested in an Icehouse environment.

Steps to migrate
================

Prep
----

* Setup neutron DB and server
* Create the neutron endpoints
* Collect all you network information
* install neutron ml2 linuxdridge on compute nodes. (ensure stopped)

Gameday
-------
* Lock down APIs - Ensure users can't access nova and neutron or anything that would in turn touch nova or neutron (eg. trove). Compute nodes and control infrastructure will still need access.
* Run create-conf.py to create novanet2neutron config. This needs to be done as a user which can read your nova config files.
* Run the 'generate_network_data.py' script. This will collect all network data and store in a DB table. This is required as duing the migration the network information coming from the API may disapear as instance info_cache network_info changes. You need to have admin credentials sourced so nova can list with --all-tenants
* Change compute driver on all your hypervisors to fake.FakeDriver and setup necessary configs in nova to use neutron. The details of this step are left as an exercise to the user based on their individual setup.
* Restart nova-compute and nova-api to make sure they're all setup for neutron and the fake compute driver.
* Stop nova-network and nova-api-metadata (if it's running) everywhere
* Start the neutron ML2 plugin everywhere. If you don't do this before creating ports, then they will usually end up in bind_failed state._
* Start the neutron-dhcp-plugin and the neutron-metadata plugins
* Run 'migrate-control.py' script, this will create the networks and subnets in neutron and also create all the ports. It will then simulate interface attaches (This is where the fake driver comes in). Make sure you set -z and -c to set your zone and config file.
* Verify the nets, subnets, and ports were created as you expect.
* Check the DB to make sure your ports are all bound properly: "SELECT * from neutron.ml2_port_bindings;"
* Run migrate-secgroup.py script
* Restart network node services neutron-*(metadata, dhcp, linuxbridge), to make sure they're all happy
* Set compute driver back from fakeDriver
* Your VMs should still have full network access up to this point
* Run generate-compute-conf.py on your controller node for each compute node using the -H option. This should generate per compute node config files, and is easily loopable.
* Copy these config files to their respective compute nodes
* Run 'migrate-compute.py' script on your compute nodes. Please be sure This will rename the interfaces the way neutron expects them to be. **This is when your VMs may incur a few seconds of downtime**
* Clear iptables and restart nova-compute and neutron-linuxbridge
* (May be needed) Add rule for metadata iptables -t nat -I PREROUTING -d 169.254.169.254/32 -p tcp -m tcp --dport 80 -j DNAT --to-destination <metadata_host>:80 - this may be needed depending on how your metadata works
* killall nova dnsmasq process


Gotchas
=======

* You can't migrate instances in suspended state, this is because the libvirt xml imformation is stored in binary in the .save file
* IPv6 hasn't been tested.
