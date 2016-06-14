# Copyright 2014 Tata Consultancy Services Ltd.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import time

from oslo_config import cfg

from vnfsvc.openstack.common.gettextutils import _
from vnfsvc.client import client

class Configuration(object):
    #register vnf driver 
    OPTS = [
       cfg.StrOpt(
            'master_userdata_file', default='',
            help=_('Path to userdata file')),
       cfg.StrOpt(
            'puppet_master_image_id', default='',
            help=_('puppet master image id')),
       cfg.StrOpt(
            'puppet_master_hostname', default='',
            help=_('puppet master hostname')),
       cfg.IntOpt(
            'puppet_master_flavor_id', default='',
            help=_('puppet master flavor id')),
    ]
    cfg.CONF.register_opts(OPTS, 'vnf')
    conf = cfg.CONF

    def __init__(self, vnfcontext, nsd):
        self.nsd = nsd
        self.conf = cfg.CONF.vnf
        self.novaclient = client.NovaClient(vnfcontext)
        self.neutronclient = client.NeutronClient(vnfcontext)

    def preconfigure(self):
        for key in self.nsd['preconfigure']:
            method_key = key.replace('-','_')
            getattr(self, method_key)(self.nsd['preconfigure'][key])
        return self.nsd

    def router(self, data):
        for network in data:
            temp_dict = self.neutronclient.get_router(data[network]['name'])[0]
            router_id = temp_dict['id']
            if_name = data[network]['if_name']
            subnet_id = data[network]['subnet_id']
            try:
                temp_dict['interface'] = self.neutronclient.add_interface_router(router_id, subnet_id)
            except:
                pass
            self.nsd['router'][network] = dict()
            self.nsd['router'][network][if_name] =  temp_dict

    def cfg_engine(self, data):
        #pass
        #TODO: (tcs) Need enhancements.
        if data == "puppet":
            puppet_dict ={}
            puppet_dict['name'] = self.conf.puppet_master_hostname
            puppet_dict['image_created'] = self.conf.puppet_master_image_id
            puppet_dict['flavor'] = self.conf.puppet_master_flavor_id
            puppet_dict['userdata'] = self.conf.master_userdata_file
            puppet_dict['num_instances'] = 1
            puppet_dict['nics'] = [{ 'net-id': self.nsd['networks']['mgmt-if']['id'] }]
            #puppet_dict['nics'] = [{ 'net-id': self.nsd['networks']['mgmt-if']['id']},{ 'net-id': self.nsd['networks']['puppet']['id'] }]
            instance = self.novaclient.server_create(puppet_dict)
            instance = self.novaclient.get_server(instance.id)
            while instance.status != 'ACTIVE':
                time.sleep(3)
                instance = self.novaclient.get_server(instance.id)
            mgmt_ip = instance.addresses.keys()[0]
            master_ip = instance.addresses[mgmt_ip][0]["addr"]
            self.nsd['puppet-master'] = {
                'master-ip': master_ip, 
                'master-hostname': instance.name,
                'instance_id': instance.id
            }
            
