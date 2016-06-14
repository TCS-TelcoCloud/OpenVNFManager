# Copyright 2014 Tata Consultancy Services, Inc.
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

"""
VNF Descriptor parser

"""

import uuid
import yaml

from vnfsvc.client import client
from vnfsvc.common import parser_utils_vnfd as parser_utils
"""
self.unavailable_keys = [
	'flavour-id', 'description', 'template',
	'vm_details', 'preconfigure', 'postconfigure', 
	'vnf-flavour', 'member-vnf-id', 'dependency', 'dependency_solved']

self.available_keys = {
    "lifecycle-events": "lifecycle_event",
    "endpoints": "endpoints",
    "assurance-params": "assurance_params",
    "cfg-engine": "cfg_engine",
    "diagnostics_params": "diagnostics_params",
    "vm_spec": "vm_details",
    "cpu": "cpu",
    "storage": "disk",
    "network_interfaces": "network_interfaces",
    "memory": "memory",
    "other_constraints": "other_constraints",
    "connection-point": "connection_point",
    "implementation_artifact": "implementation_artifact",
    "template": "template",
    "vdus": "vdus",
    "other_constraints": "other_constraints"
}
"""

class VNFParser_v1(object):

    def __init__(self, vnf_context, vnfd_template=None, flavour=None, vdu_list=None, vnfd_name=None, nsd=None):

        self.unavailable_keys = [
        'flavour-id', 'description', 'template',
        'vm_details', 'preconfigure', 'postconfigure',
        'vnf-flavour', 'member-vnf-id', 'dependency', 'dependency_solved']

        self.available_keys = {
        "lifecycle-events": "lifecycle_event",
        "endpoints": "endpoints",
        "assurance-params": "assurance_params",
        "cfg-engine": "cfg_engine",
        "diagnostics-params": "diagnostics_params",
        "vm-spec": "vm_details",
        "cpu": "vcpus",
        "storage": "disk",
        "network-interfaces": "network_interfaces",
        "memory": "memory",
        "other-constraints": "other_constraints",
        "connection-point": "connection_point",
        "implementation-artifact": "implementation_artifact",
        "template": "template",
        "vdus": "vdus",
        "other-constraints": "other_constraints",
        "num-instances": "num_instances"
}

        self.vnf_context = vnf_context
        self.new_vnfd = dict()
        vnfd = dict()
        vnfd['template'] = yaml.load(open(
                        vnfd_template,
                        'r'))
        
        if vnfd == None:
            self.vnfd = dict()
        else:
            self.vnfd_name = vnfd_name
            self.vdu_list = vdu_list
            self.nsd = nsd
            vnfd['template']['vnfd'] = self.remove_keys(vnfd['template']['vnfd'], ['id','vendor', 'description', 'version'])
            vnfd.update(vnfd['template']['vnfd']['flavours'][flavour])
            del vnfd['template']['vnfd']['flavours']
            self.vnfd = vnfd
            self.new_vnfd = dict()
            
            self.new_vnfd['preconfigure'] = dict()
            self.new_vnfd['postconfigure'] = dict()
            self.new_vnfd['vdu_keys'] = list()
            self.new_vnfd['vdus'] = dict()
            for vdu in self.vnfd['vdus']:
                if vdu not in vdu_list:
                    continue
                self.new_vnfd['vdu_keys'].append(vdu)
                self.new_vnfd['vdus'][vdu] = dict()
                self.new_vnfd['vdus'][vdu]['vm_details'] = dict()
                self.new_vnfd['vdus'][vdu]['preconfigure'] = dict()
                self.new_vnfd['vdus'][vdu]['postconfigure'] = dict()
    
    def remove_keys(self, dict, key_list):
        for key in key_list:
            del dict[key]
        return dict
        
    def parse(self):
        self.parser_obj = parser_utils.VNFDParserUtils(self.vnf_context, self.nsd, self.vnfd_name)
        for key in self.vnfd:
            if key not in self.unavailable_keys :
	            method_key = self.available_keys[key].replace('-','_')
                    getattr(self.parser_obj, method_key)(self.vnfd[key], self.new_vnfd, self)
        del self.vnfd['vdus']
        del self.vnfd['template']
        return self.new_vnfd

    def get_flavor_dict(self, vdu):
        flavor_dict = dict()
        flavor_dict['ram'] = vdu['vm_details']['ram']
        flavor_dict['vcpus'] = vdu['vm_details']['vcpus']
        flavor_dict['disk'] = vdu['vm_details']['disk']
        flavor_dict['name'] = str(uuid.uuid4()).split('-')[0]
        return flavor_dict

    def get_boot_details(self, vdu):
        """ Returns the dictionary that contains all necessary information to launch a VM """
        boot_dict = dict()
        boot_dict['image'] = vdu['vm_details']['image_details']
        boot_dict['num_instances'] = vdu['vm_details']['num-instances']        
        if 'userdata' in vdu['vm_details'].keys():
            boot_dict['userdata'] = vdu['vm_details']['userdata']
        return boot_dict

    def get_vnfd_mapping_dict(self):
        return self.available_keys
