#!/usr/bin/env bash

## YOU NEED TO SET ALL THIS OR THINGS WILL NOT WORK ##

FLAVOR_NAME=""
IMAGE_NAME=""
KEY_NAME=""
SECGROUP_NAME="default,ssh-icmp"
TENANTS="tenant1 tenant2 tenant3 tenant4 tenant5 tenant6 tenant7 tenant8"
PUBKEY=""
USER_NAME=""
ROLE_NAME="Member"
ADMIN_RC_FILE=""
AUTH_HOST="127.0.0.1"


source $ADMIN_RC_FILE admin admin

for i in $TENANTS; do

  echo "Creating tenant $i"
  keystone tenant-create --name $i
  echo "Creating user ${i}-user"
  keystone user-create --name ${i}-user --pass password --tenant $i
  echo "Adding ${i}-user as $ROLE_NAME to tenant $i"
  keystone user-role-add --user ${i}-user --role $ROLE_NAME --tenant $i
  echo "Creating creds file for ${i}-user in $i"
  echo "
unset SERVICE_ENDPOINT SERVICE_TOKEN OS_TENANT_ID
export OS_AUTH_URL=http://${AUTH_HOST}:5000/v2.0
export OS_USERNAME=${i}-user
export OS_PASSWORD=password
export OS_TENANT_NAME=$i
IGNORECASE=1
export OS_NO_CACHE=1
export NOVA_ENDPOINT_TYPE=internalURL" > ${i}.creds

done

for i in $TENANTS; do

  echo "Creating security groups for tenant $i"
  source ${i}.creds
  echo $PUBKEY > keypair && nova keypair-add --pub-key keypair $KEY_NAME && rm -f keypair
  nova secgroup-create "ssh-icmp" "Allow SSH and Ping"
  nova secgroup-add-rule ssh-icmp tcp 22 22 0.0.0.0/0
  nova secgroup-add-rule ssh-icmp icmp -1 -1 0.0.0.0/0

done

for i in $TENANTS; do

  echo "Creating VMs for tentant $i"
  source ${i}.creds
  nova boot --flavor $FLAVOR_NAME --image $IMAGE_NAME --key-name $KEY_NAME --security-groups $SECGROUP_NAME ${i}-vm1
  nova boot --flavor $FLAVOR_NAME --image $IMAGE_NAME --key-name $KEY_NAME --security-groups $SECGROUP_NAME ${i}-vm2

done
