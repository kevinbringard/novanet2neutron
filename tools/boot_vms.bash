#!/usr/bin/env bash

FLAVOR_NAME="m1.tiny"
IMAGE_NAME="cirros-0.3.4"
KEY_NAME="kevin"
SECGROUP_NAME="default,ssh-icmp"
TENANTS="tenant1 tenant2 tenant3 tenant4"

for i in $TENANTS; do

  echo "Creating VMs for tentant $i"
  source ${i}.creds
  nova boot --flavor $FLAVOR_NAME --image $IMAGE_NAME --key-name $KEY_NAME --security-groups $SECGROUP_NAME ${i}-vm1
  sleep 2
  nova boot --flavor $FLAVOR_NAME --image $IMAGE_NAME --key-name $KEY_NAME --security-groups $SECGROUP_NAME ${i}-vm2

done
