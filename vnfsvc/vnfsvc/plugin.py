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

import datetime
import json
import os
import uuid
import shutil
import six
import eventlet
import pexpect
import tarfile
import time
import sys 
import re
import yaml
import ast
import subprocess
import traceback
import pyaml
import requests
import urllib2
import importlib
import dicttoxml
import xml.etree.ElementTree as ET
import xmltodict
import datetime
from oslo_utils import timeutils


from collections import OrderedDict
from distutils import dir_util
from netaddr import IPAddress, IPNetwork
from oslo_config import cfg
import oslo_messaging as messaging

from ConfigParser import SafeConfigParser
from vnfsvc import constants
from vnfsvc import manager
from vnfsvc import constants as vm_constants
from vnfsvc import config
from vnfsvc import context
from vnfsvc import nsdmanager
from vnfsvc import utility

from vnfsvc.api.v2 import attributes
from vnfsvc.api.v2 import vnf
from vnfsvc.db.vnf import vnf_db

from vnfsvc.openstack.common.gettextutils import _
from vnfsvc.openstack.common import excutils
from vnfsvc.openstack.common import log as logging
from vnfsvc.openstack.common import importutils

from vnfsvc.client import client
from vnfsvc.client import utils as ovs_utils

from vnfsvc.common import driver_manager
from vnfsvc.common import exceptions
from vnfsvc.common import rpc as v_rpc
from vnfsvc.common import topics
from vnfsvc.agent.linux import utils
from vnfsvc.common import utils as vnfsvc_utils

LOG = logging.getLogger(__name__)
DEFAULT_OVS_VSCTL_TIMEOUT = 10

class VNFPlugin(vnf_db.NetworkServicePluginDb):
    """VNFPlugin which provide support to OpenVNF framework"""

    OPTS = [
        cfg.MultiStrOpt(
            'vnf_driver', default=[],
            help=_('Hosting  drivers for vnf will use')),
        cfg.StrOpt(
            'templates', default='',
            help=_('Path to service templates')),
        cfg.StrOpt(
            'vnfmanager', default='',
            help=_('Path to VNF Manager')),
        cfg.StrOpt(
            'compute_hostname', default='',
            help=_('Compute Hostname')),
        cfg.StrOpt(
            'compute_ip', default=None,
            help=_('Compute Hostname')),
        cfg.StrOpt(
            'compute_user', default='',
            help=_('User name')),
        cfg.StrOpt(
            'vnfm_home_dir', default='',
            help=_('vnf_home_dir')),
        cfg.StrOpt(
            'compute_home_user', default='',
            help=_('compute_home_user')),
        cfg.StrOpt(
            'ssh_pwd', default='',
            help=_('ssh_pwd')),
        cfg.StrOpt(
            'ovs_bridge', default='br-int',
            help=_('ovs_bridge')),
        cfg.StrOpt(
            'neutron_rootwrap', default='',
            help=_('path to neutron rootwrap')),
        cfg.StrOpt(
            'neutron_rootwrapconf', default='',
            help=_('path to neutron rootwrap conf')),
        cfg.StrOpt(
            'vnfmconf', default='local',
            help=_('Vnf Manager Configuaration')),
        cfg.StrOpt(
            'service_cidr', default='0.0.0.0/0',
            help=_('Service Network CIDR')),

    ]
    cfg.CONF.register_opts(OPTS, 'vnf')
    cfg.CONF.register_opts(OPTS, 'service_network')

    conf = cfg.CONF

    def __init__(self):
        super(VNFPlugin, self).__init__()
        self._pool = eventlet.GreenPool()
        self.conf = cfg.CONF
        self.ns_dict = dict()
        config_file = '/etc/vnfsvc/config.ini'
        self.parser = SafeConfigParser()
        try:
            self.parser.read(config_file)
        except IOError:
            self.logger.critical("No Configuration File Exists")
        self.config_file = config_file

        config.register_root_helper(self.conf)
        self.root_helper = config.get_root_helper(self.conf)
        self.agent_mapping = dict()
        self.vsctl_timeout = DEFAULT_OVS_VSCTL_TIMEOUT

        self.endpoints = [VNFManagerCallbacks(self)]
        self.conn = v_rpc.create_connection(new=True)
        self.conn.create_consumer(
            topics.PLUGIN, self.endpoints, fanout=False)

        self.conn.consume_in_threads()
        self.service_cidr = self.conf.service_network.service_cidr


    def auth(fun):
        def inn(self,*args,**kwargs):
            #This decorator is used to obtain client for openstack projects
            context = args[0]
            self.novaclient = self._get_nova_client(context)
            self.glanceclient = self._get_glance_client(context)
            self.neutronclient = self._get_neutron_client(context)
            return fun(self,*args,**kwargs)
        return inn


    def spawn_n(self, function, *args, **kwargs):
        self._pool.spawn_n(function, *args, **kwargs)

    def _get_neutron_client(self, context):
        return client.NeutronClient(context)

    def _get_nova_client(self, context):
        return client.NovaClient(context)

    def _get_glance_client(self, context):
        return client.GlanceClient(context)

    def _get_networks(self, ns_info):
        return ns_info['attributes']['networks']

    def _get_router(self, ns_info):
        return ns_info['attributes']['router']

    def _get_subnets(self, ns_info):
        return ns_info['attributes']['subnets']

    def _get_qos(self, ns_info):
        return ns_info['quality_of_service']

    def _get_name(self, ns_info):
        return ns_info['name']

    def _ns_dict_init(self, service, nsd_id):
        ns_info = {}
        ns_info[nsd_id] = service['service']
        self.ns_dict[nsd_id]= {}
        self.ns_dict[nsd_id]['vnfds'] = {}
        self.ns_dict[nsd_id]['instances'] = {}
        self.ns_dict[nsd_id]['configured'] = []
        self.ns_dict[nsd_id]['image_list'] = []
        self.ns_dict[nsd_id]['flavor_list'] = []
        self.ns_dict[nsd_id]['puppet'] = ''

        self.ns_dict[nsd_id]['config-event'] = {}
        self.ns_dict[nsd_id]['config-event']['errored'] = []
        self.ns_dict[nsd_id]['config-event']['acknowledge_list'] = {}

        self.ns_dict[nsd_id]['conf_generated'] = []
        self.ns_dict[nsd_id]['errored'] = []
        self.ns_dict[nsd_id]['is_manager_invoked'] = False
        self.ns_dict[nsd_id]['vnfmanager_uuid'] = str(uuid.uuid4())
        self.ns_dict[nsd_id]['acknowledge_list'] = dict()
        self.ns_dict[nsd_id]['deployed_vdus'] = list()
        self.ns_dict[nsd_id]['vnfm_dir'] =  self.conf.state_path+'/'+ \
                                    self.ns_dict[nsd_id]['vnfmanager_uuid']
        self.ns_dict[nsd_id]['vnfm_conf'] = dict()
        self.ns_dict[nsd_id]['vnfm_conf']['vnfds'] = dict()
        self.lfevent_details = {}
        self.configured_instances = []


        if not os.path.exists(self.ns_dict[nsd_id]['vnfm_dir']):
            os.makedirs(self.ns_dict[nsd_id]['vnfm_dir'])
        self.ns_dict[nsd_id]['service_name'] = self._get_name(ns_info[nsd_id])
        self.ns_dict[nsd_id]['networks'] = self._get_networks(ns_info[nsd_id])
        self.ns_dict[nsd_id]['router'] = self._get_router(ns_info[nsd_id])
        self.ns_dict[nsd_id]['subnets'] = self._get_subnets(ns_info[nsd_id])
        self.ns_dict[nsd_id]['qos'] = self._get_qos(ns_info[nsd_id])
        self.ns_dict[nsd_id]['templates_json'] = json.load(
                                       open(self.conf.vnf.templates, 'r'))

        self.ns_dict[nsd_id]['nsd_template'] = yaml.load(open(
                          self.ns_dict[nsd_id]['templates_json']['nsd']\
                          [self.ns_dict[nsd_id]['service_name']], 'r'))['nsd']


    def create_activate(self, context, activate):
        """ This method is used to update the Status parameter in ServiceTemplate depending upon the input given by the user"""
        template = self.get_template_model(context, template_id=activate['activate']['template_id'], fields = None)
        db_activate = False
        if activate['activate']['enable'] == 'True':
           to_activate = True
        elif activate['activate']['enable'] == 'False':
           to_activate = False
        else:
           raise exceptions.StatusException(service = 'Provide either True/Flase as input to activate the Network Service')

        if 'True' in template.values():
           db_activate = True

        if db_activate:
             if to_activate:
                 raise exceptions.StatusException(service = 'Network Service status is already activated')
             else:
                 return self.get_status_update(context, activate, 'False')

        if not db_activate:
            if not to_activate:
                raise exceptions.StatusException(service = 'Network Service status is already de-activated')
            else:
                return self.get_status_update(context, activate, 'True')


    @auth    
    def create_service(self, context, service):
        #This is method is used to bring up a network service
        nsd_id = str(uuid.uuid4())
        nsd_dict = {}
        nsd_dict['id'] = nsd_id
        nsd_dict['check'] = ''
        
         
        template = self.get_template_model(context, template_name=service['service']['name'], fields=None)
        if template:
             if  not template['status']:
               raise exceptions.StatusException(service='Status is not activated')
        else :
           raise exceptions.StatusException(service='Service name is not found in catalog')

       
        try:
            self._ns_dict_init(service, nsd_id)
            self.ns_dict[nsd_id]['vnf_context'] = context
            self.template_id, parser, version = self.get_template_id(context, service['service']['name'])
            parser_path = self.parser.get('parser_paths', parser)
            nsd_cls_path = parser_path+'.nsdparser'+'.NetworkParser'+'_v'+version.split('.')[0]
            vnfd_cls_path = parser_path+'.vnfdparser'+'.VNFParser'+'_v'+version.split('.')[0]
            try:
                self.nsd_parser_obj = importutils.import_object(nsd_cls_path,
                                                        self.ns_dict[nsd_id]['vnf_context'],
                                                        self.ns_dict[nsd_id]['templates_json'],
                                                        self.ns_dict[nsd_id]['service_name'])
            except Exception:
                LOG.warn(_("%s nsd parser not Loaded"), nsd_cls_path)
                raise

            self.ns_dict[nsd_id]['nsd_template'] = self.nsd_parser_obj.parse(
                                             self.ns_dict[nsd_id]['qos'],
                                             self.ns_dict[nsd_id]['networks'] ,
                                             self.ns_dict[nsd_id]['router'],
                                             self.ns_dict[nsd_id]['subnets'])

            self.ns_dict[nsd_id]['nsd_template']['router'] = {}
            self.ns_dict[nsd_id]['nsd_template'] = nsdmanager.Configuration(
                               self.ns_dict[nsd_id]['vnf_context'],
                               self.ns_dict[nsd_id]['nsd_template']).preconfigure()

            for vnfd in self.ns_dict[nsd_id]['nsd_template']['vnfds']:
                vnfd_template = yaml.load(open(
                               self.ns_dict[nsd_id]['templates_json']['vnfd'][vnfd],
                               'r'))
                self.ns_dict[nsd_id]['vnfds'][vnfd] = dict()
                try:
                    self.vnfd_parser_obj = importutils.import_object(vnfd_cls_path,
                                                             self.ns_dict[nsd_id]['vnf_context'],
                                                             self.ns_dict[nsd_id]['templates_json']['vnfd'][vnfd],
                                                             self.ns_dict[nsd_id]['qos'],
                                                             self.ns_dict[nsd_id]['nsd_template']['vnfds'][vnfd],
                                                             vnfd,
                                                             self.ns_dict[nsd_id]['nsd_template'])
                except Exception:
                    LOG.warn(_("%s vnfd parser not Loaded"), vnfd_cls_path)
                    raise

                self.ns_dict[nsd_id]['vnfds'][vnfd] = self.vnfd_parser_obj.parse()

                self.ns_dict[nsd_id]['vnfds'][vnfd]['vnf_id'] = str(uuid.uuid4())
                self._extract_lfevents(nsd_id, self.ns_dict[nsd_id]['vnfds'])
            puppet_id = None
            if 'puppet-master' in self.ns_dict[nsd_id]['nsd_template']:
                puppet_id = self.ns_dict[nsd_id]['nsd_template']['puppet-master']['instance_id']


            db_dict = {
                'id': nsd_id,
                'nsd': self.ns_dict[nsd_id]['nsd_template'],
                'vnfds': self.ns_dict[nsd_id]['vnfds'],
                'networks': self.ns_dict[nsd_id]['networks'],
                'subnets': self.ns_dict[nsd_id]['subnets'],
                'vnfm_id': self.ns_dict[nsd_id]['vnfmanager_uuid'],
                'vnfm_host': "None",
                'service': service['service'],
                'puppet_id': puppet_id,
                'status': 'PENDING',
                'template_id': self.template_id,
                'flavour': self.ns_dict[nsd_id]['qos'],
                'lf_event': self.lfevent_details,
                'xml': ''
            }
            #Create DB Entry for the new service
            nsdb_dict = self.create_service_model(context, **db_dict)

            #Launch VNFDs
            self.spawn_n(self.deploy_vnfs, context, nsd_id, service['service']['name'])
        except Exception as e:
            LOG.debug(_('An exception occured while configuring NetworkService')) 
            traceback.print_exc(file=sys.stdout)
            nsd_dict['check'] = e
            return nsd_dict
        return nsdb_dict


    @auth
    def deploy_vnfs(self, context, nsd_id, servicename):
        self._create_vnfds(context,nsd_id)
        self.get_ns_config_details(context, nsd_id)
        self._modify_iptables(nsd_id)
        self.ns_postConfigure(context, nsd_id, self.ns_dict[nsd_id])

        self.update_nsd_status(context, nsd_id, 'ACTIVE')
        data = self.generate_ns_info(self.ns_dict[nsd_id], nsd_id)
        self.update_nsd_info(context, nsd_id, data)
        service_details=self.get_service_by_nsd_id(context, nsd_id) 

    @auth
    def ns_postConfigure(self, context, nsd_id, ns,vdus=None):
        if vdus:
           for vnf in ns['vnfds']:
               
               for vdu in ns['vnfds'][vnf]['vdus']:
                   if ns['vnfds'][vnf]['vdus'][vdu]['vm_details']['image_details']['name'] in vdus:
                       event ='config'
                       self.post_configure(context,event, vdu,nsd_id, vnf,ns)
        else:
            self.independent_vdus = list()
            for vdu in self.ns_dict[nsd_id]['dependency_dict'].keys():
                if len(self.ns_dict[nsd_id]['dependency_dict'][vdu]['updatesFrom']) == 0:
                    self.independent_vdus.append(vdu)
            for vdu in self.independent_vdus:
                vnf, vdu = vdu.split(':')
                event = 'config'
                self.post_configure(context,event, vdu,nsd_id, vnf,ns)

            while len(self.ns_dict[nsd_id]['nsd_template']['vdus']) != len(self.ns_dict[nsd_id]['config-event']['acknowledge_list']):
                event = 'config'
                vdus = list()

                for vdu in self.ns_dict[nsd_id]['dependency_dict'].keys():
                    vnf1,vdu1 = vdu.split(':')
                    if vdu1 in self.ns_dict[nsd_id]['config-event']['acknowledge_list']:
                        continue
                    else:
                        launched_dependencies = 0
                        actual_dependencies = len(self.ns_dict[nsd_id]['dependency_dict'][vdu]['updatesFrom'])
                        for dependent_vdu in self.ns_dict[nsd_id]['dependency_dict'][vdu]['updatesFrom']:
                            vnf2,dependent_vdu1=dependent_vdu.split(':')
                            if dependent_vdu1  in self.ns_dict[nsd_id]['config-event']['acknowledge_list']:
                                launched_dependencies += 1
                        if launched_dependencies == actual_dependencies:
                            vdus.append(vdu)

                for vdu in vdus:
                    vnf,vdu = vdu.split(':')
                    self.post_configure(context,event, vdu,nsd_id, vnf,ns)


    @auth
    def post_configure(self,context,event, vdu,nsd_id, vnf,ns):
        conf = {}
        conf['event'] = event
        conf['vdu'] = vdu
        conf['vnf'] = vnf
        conf['instances_list'] = ns['vnfds'][vnf]['vdus'][vdu]['instance_list']
        conf['mgmt-ip'] = ns['vnfds'][vnf]['vdus'][vdu]['mgmt-ip']
        conf['username'] = ns['vnfds'][vnf]['vdus'][vdu]['vm_details']['image_details']['username']
        conf['password'] = ns['vnfds'][vnf]['vdus'][vdu]['vm_details']['image_details']['password']

        for instance in conf['instances_list']:
            lf_events = self.get_lfevents(context, nsd_id, vdu)
            for event in lf_events:
                if event == 'config':
                    formatted_dict = {event : {}}
                    format_args = {'lf_event' : lf_events[event],
                                   'event' : event,
                                   'nsd_id' : nsd_id,
                                   'instance' : instance}
                    formatted_dict[event]['driver'] = lf_events[event]['driver']
                    formatted_dict[event]['data'] = self.format_lfevents(**format_args)
                    ns['vnfds'][vnf]['vdus'][vdu]['postconfigure']['lifecycle_events'].update(formatted_dict)
                    break

        conf['data'] = ns['vnfds'][vnf]['vdus'][vdu]['postconfigure']['lifecycle_events'][event]['data']
        conf['driver'] = ns['vnfds'][vnf]['vdus'][vdu]['postconfigure']['lifecycle_events'][event]['driver']

        if conf['data'] != "" and conf['driver'] != "":
            self.agent_mapping[ns['vnfmanager_uuid']].postConfigure(context, conf=conf)
            self.wait_for_acknowledgment([vdu], nsd_id, "postconfigure")
        else:
            if self.ns_dict[nsd_id]['config-event']['acknowledge_list'].get(vdu, None):
                self.ns_dict[nsd_id]['config-event']['acknowledge_list'][vdu].append(ns['vnfds'][vnf]['vdus'][vdu]['instances'])
            else:
                self.ns_dict[nsd_id]['config-event']['acknowledge_list'][vdu] = ns['vnfds'][vnf]['vdus'][vdu]['instances']

        print conf

    @auth
    def update_service(self, context, nsd_id, service):
        new_configuration = {service['service']['attributes']['method']: service['service']['attributes']['arguments']}
        vdu_name = service['service']['attributes']['vdu_name']
        LOG.debug(_("Service: %s updation taking place with the configuration %s"), nsd_id, new_configuration)
        """vnf_manager = self.get_manager_by_nsd_id(context, nsd_id)
        vdus_in_nsd = self.get_vdus_for_nsd_id(context, nsd_id)"""
        service_details_for_nsd = self.get_service_by_nsd_id(context, nsd_id)
        vnf_manager = service_details_for_nsd['vnfm_id']
        vdus_in_nsd = service_details_for_nsd['vdus']
        if vdu_name not in [vdu.split(':')[1] for vdu in eval(vdus_in_nsd).keys()]:
            raise exceptions.NoVduforNsd()
        self.agent_mapping[vnf_manager] =\
                      VNFManagerAgentApi(topics.get_topic_for_mgr(vnf_manager),
                                         cfg.CONF.host, self)
        status = self.agent_mapping[vnf_manager].update_vdu_configuration(context, vdu_name, new_configuration)
        updated_service = dict()
        updated_service['nsd_id'] = nsd_id
        updated_service['status'] = status
        return updated_service 
     
    def get_service_driver(self, context, nsd_id, **kwargs):
        service_driver = self.get_service_driver_details_by_nsd_id(context, nsd_id, fields=kwargs['fields'])
        return service_driver

    def get_service_drivers(self, context, **kwargs):
        kwargs['fields'].append('template_id')
        services = self.get_all_services(context, **kwargs)
        return [{'id': m['id'], 'template_id': m['template_id']} for m in services]

    @auth
    def delete_service(self, context, service):
        context = context
        self.novaclient = self._get_nova_client(context)
        self.glanceclient = self._get_glance_client(context)
        self.neutronclient = self._get_neutron_client(context)
        nsd_id = service
        service_db_dict = self.delete_service_model(context,service)
        try:
            self.delete_puppet_instance(service_db_dict)
            self.update_nsd_status(context, service, 'DELETING')
        except Exception as e:
            pass
        if service_db_dict is not None:
            self.spawn_n(self.delete_vnfs, context, service, service_db_dict)
        else:
            return

    @auth
    def delete_vnfs(self, context, service, service_db_dict):
        try:
            self.delete_vtap_and_vnfm(service_db_dict)
            self.delete_vdus(context, service_db_dict, service)
            time.sleep(15)
            self.delete_router_interfaces(service_db_dict)
            #self.delete_router(service_db_dict)
            self.delete_ports(service_db_dict)
            #self.delete_networks(context, service, service_db_dict)
            self.delete_db_dict(context, service)
        except Exception:
            raise

    def _extract_lfevents(self, nsdid, vnf_details):
        self.lfevent_details[nsdid]={}
        for vnf in vnf_details:
            self.lfevent_details[nsdid][vnf]={}
            for vdu in vnf_details[vnf]['vdus'].keys():
                if 'postconfigure' in vnf_details[vnf]['vdus'][vdu].keys():
                    self.lfevent_details[nsdid][vnf][vdu] = {}
                    self.lfevent_details[nsdid][vnf][vdu]['postconfigure']={}
                    self.lfevent_details[nsdid][vnf][vdu]['postconfigure']['unformat']={}
                    for prop in vnf_details[vnf]['vdus'][vdu]['postconfigure'].keys():
                        self.lfevent_details[nsdid][vnf][vdu]['postconfigure']['unformat'][prop]={}
                        for subprop in vnf_details[vnf]['vdus'][vdu]['postconfigure'][prop].keys():
                            vnf_details[vnf]['vdus'][vdu]['postconfigure'][prop]['unformat']={}
                            self.lfevent_details[nsdid][vnf][vdu]['postconfigure']['unformat'][prop][subprop] = vnf_details[vnf]['vdus'][vdu]['postconfigure'][prop][subprop]


    def _populate_details(self, vdu_details, port, subnets, ports):
        vdu_details['subnet_id'] = port['fixed_ips'][0]['subnet_id']
        vdu_details['mac_address'] = port['mac_address']
        vdu_details['network_id'] = port['network_id']
        vdu_details['ovs_port'] = self.get_port_ofport(vdu_details['vm_interface'])
        for subnet in subnets:
            if subnet['id'] == vdu_details['subnet_id']:
                vdu_details['gateway_ip'] = subnet['gateway_ip']
        for port in ports:
            if vdu_details['gateway_ip'] == port['fixed_ips'][0]['ip_address']:
                vdu_details['is_gateway'] = True

        return vdu_details

    def get_port_ofport(self, port_name):
        ofport = self.db_get_val("Interface", port_name, "ofport")
        # This can return a non-integer string, like '[]' so ensure a
        # common failure case
        try:
            int(ofport)
            return ofport
        except (ValueError, TypeError):
            return

    def db_get_val(self, table, record, column, check_error=False):
        output = self.run_vsctl(["get", table, record, column], check_error)
        if output: 
            return output.rstrip("\n\r")

    def run_vsctl(self, args, check_error=False):
        full_args = ["sudo", "ovs-vsctl", "--timeout=%d" % self.vsctl_timeout] + args
        try:
            return ovs_utils.execute(full_args, root_helper=None)
        except Exception as e:
            with excutils.save_and_reraise_exception() as ctxt:
                if not check_error:
                    ctxt.reraise = False

    @auth    
    def get_ns_config_details(self, context, nsd_id):
        self.neutronclient = self._get_neutron_client(context)
        subnets = self.neutronclient.get_subnets()
        ports = self.neutronclient.get_ports()
        self.ns_dict[nsd_id]['instance_details'] = dict()

        for vnfd in self.ns_dict[nsd_id]['nsd_template']['vnfds']:
            self.ns_dict[nsd_id]['instance_details'][vnfd] = dict()
            for vdu in self.ns_dict[nsd_id]['nsd_template']['vnfds'][vnfd]:
                vdu_name = vnfd + ":" + vdu
                for instance in self.ns_dict[nsd_id]['vnfds'][vnfd]['vdus'][vdu]['instances']:
                    instance_networks = instance.networks
                    for k,v in instance_networks.iteritems():
                        vdu_details = dict()
                        vdu_details['name'] = instance.name
                        vdu_details['hostname'] = instance.__dict__['OS-EXT-SRV-ATTR:host']
                        vdu_details['is_gateway'] = False
                        for port in ports:
                            if v[0] == port['fixed_ips'][0]['ip_address']:
                                vdu_details['port-id'] = port['id'] 
                                vdu_details['vm_interface'] = "qvo"+port['id'][:11]
                                vdu_details = self._populate_details(vdu_details, port, subnets, ports)
                                break
                        for key1,value1 in self.ns_dict[nsd_id]['nsd_template']['vdus'][vdu_name]['networks'].iteritems():
                            if vdu_details['subnet_id'] == value1['subnet-id']:
                                if not key1 in self.ns_dict[nsd_id]['instance_details'][vnfd].keys():
                                    self.ns_dict[nsd_id]['instance_details'][vnfd][key1] = []
                                self.ns_dict[nsd_id]['instance_details'][vnfd][key1].append(vdu_details)


    def _modify_iptables(self, nsd_id):
        ipt_cmd_list = []
        port = ""
        for vdu in self.ns_dict[nsd_id]['instance_details'].keys():
            for iface in self.ns_dict[nsd_id]['instance_details'][vdu].keys():
                if iface != "" :
                    for vm in self.ns_dict[nsd_id]['instance_details'][vdu][iface]:
                        port = str(vm['port-id'])
                        self.neutronclient.update_port(port, \
                               body={"port": {"allowed_address_pairs": [{"ip_address": "0.0.0.0/0"}]}})


    def delete_vtap_and_vnfm(self, service_db_dict):
        try:
            vnfm_id = service_db_dict['service_db'][0].vnfm_id
            vnfm_host = service_db_dict['service_db'][0].vnfm_host
            homedir = cfg.CONF.state_path + '/' + vnfm_id
            if vnfm_host == "local":
                vnfm_str = '`ps -eaf | grep vnf-manager | grep ' + vnfm_id +' | awk \'{print $2}\'`'
                with open(homedir+"/ovs.sh","r") as f:
                    data = f.readlines()
                subprocess.call(["sudo","ovs-vsctl","del-port",data[2].split(" ")[2]])
                subprocess.call(["sudo","kill","-9", vnfm_str])
            else:
                vnfm_home_dir =  '{{ ansible_env["HOME"] }}/.vnfm/' + vnfm_id

                ansible_dict=[{'tasks': [
                                {'ignore_errors': True, 'shell': 'sh '+ \
                                 vnfm_home_dir + '/del.sh', 'register': 'result1'},
                                {'debug': 'var=result1.stdout_lines'},
                              ], 'hosts': vnfm_host, 'remote_user': \
                              cfg.CONF.vnf.compute_user}]

                with open(homedir + '/delete-playbook.yaml', 'w') as yaml_file:
                    yaml_file.write(yaml.safe_dump(ansible_dict,
                                               default_flow_style=False))

                child = pexpect.spawn('ansible-playbook ' +\
                                      homedir + '/delete-playbook.yaml -i ' +\
                                      homedir  +'/hosts --ask-pass')
                child.expect('SSH password:')
                child.sendline(cfg.CONF.vnf.ssh_pwd)
                result =  child.readlines()

        except Exception as e:
            pass
    def delete_puppet_instance(self, service_db_dict):
        ns_list = service_db_dict['service_db']
        try:
            for nw_service in ns_list:
               puppet = nw_service['puppet_id']
               if puppet:
                    self.novaclient.delete(puppet)
        except Exception:
            LOG.debug(_("An Exception occured while deleting puppet instance"))
            pass

    @auth
    def delete_vdus(self, context, service_db_dict, nsd_id):
        instance_list = []
        for vdu in range(len(service_db_dict['instances'])):
            for instance in range(len(service_db_dict['instances'][vdu])): 
                instance_list = service_db_dict['instances'][vdu][instance].__dict__['instances'].split(',')
                flavor = service_db_dict['instances'][vdu][instance].__dict__['flavor']
                image = service_db_dict['instances'][vdu][instance].__dict__['image']
                vdu_id=service_db_dict['instances'][vdu][instance].__dict__['id']
                try:
                    for inst in instance_list:
                        self.novaclient.delete(inst)
                        vduname=self.vdu_fun(service_db_dict,vdu_id) 
                        vdu_name=vduname.split(':',1)[1] 
                        data={"vdu_name":vdu_name,"instances":inst} 

                except Exception:
                    LOG.debug(_("Exception occured while deleting VDU configuration in Network Service"))
                    pass


    def vdu_fun(self,service_db_dict,vdu_id):
        service_vdu_id = ast.literal_eval(service_db_dict['service_db'][0]['vdus'])
        dict1=dict((v,k) for k,v in service_vdu_id.iteritems())
        if vdu_id in dict1.keys():
            vdu_name=dict1[vdu_id]
            return vdu_name

        
    def delete_router_interfaces(self, service_db_dict):
        fixed_ips = []
        subnet_ids = []
        body = {}
        if service_db_dict['service_db'][0]['router']!= 'None': 
           networks = ast.literal_eval(service_db_dict['service_db'][0].router).keys() 
           router_id = ast.literal_eval(service_db_dict['service_db'][0].router)[networks[0]]['id']
           router_ports = self.neutronclient.list_router_ports(router_id)
           for r_port in range(len(router_ports['ports'])):
               fixed_ips.append(router_ports['ports'][r_port]['fixed_ips'])

           for ip in range(len(fixed_ips)):
               subnet_ids.append(fixed_ips[ip][0]['subnet_id'])

           for s_id in range(len(subnet_ids)):
               body['subnet_id']=subnet_ids[s_id]
               try:
                   self.neutronclient.remove_interface_router(router_id, body)
               except Exception as e:
                   pass
        else:
           pass



    def delete_router(self,service_db_dict): 
        if service_db_dict['service_db'][0]['router']!= 'None':
            networks = ast.literal_eval(service_db_dict['service_db'][0].router).keys()
            router_id = ast.literal_eval(service_db_dict['service_db'][0].router)[networks[0]]['id']
            try:
                self.neutronclient.delete_router(router_id)
            except Exception as e:
                pass
        else:
            pass
    
    def delete_ports(self,service_db_dict):
        net_ids = ast.literal_eval(service_db_dict['service_db'][0].networks).values()
        port_list=self.neutronclient.list_ports()

        for port in range(len(port_list['ports'])):
            if port_list['ports'][port]['network_id'] in net_ids:
               port_id = port_list['ports'][port]['id']
               try:
                   self.neutronclient.delete_port(port_id)
               except Exception as e:
                   pass

    @auth    
    def delete_networks(self, context, nsd_id, service_db_dict):
        net_ids = ast.literal_eval(service_db_dict['service_db'][0].networks).values()
        for net in range(len(net_ids)):
            try:
                self.neutronclient.delete_network(net_ids[net])
            except Exception as e:
                pass


    def remove_keys(self, temp_vdus, key_list):
        for vdu in key_list:
            del temp_vdus[vdu]
        return temp_vdus

    def create_dependency_dict(self, nsd_id):
        temp_vdus = self.ns_dict[nsd_id]['nsd_template']['vdus'].copy()
        self.ns_dict[nsd_id]['dependency_dict'] = dict()
        for vdu in temp_vdus.keys():
            self.ns_dict[nsd_id]['dependency_dict'][vdu] = {
                'updatesFrom': list(),
                'updatesTo': list(),
            }
        for vdu in temp_vdus.keys():
            if 'dependency' in temp_vdus[vdu].keys():
                temp_dependencies = temp_vdus[vdu]['dependency']
                for dependent_vdu  in temp_dependencies:
                    self.ns_dict[nsd_id]['dependency_dict'][vdu]['updatesFrom'].append(dependent_vdu)
                    if dependent_vdu in self.ns_dict[nsd_id]['dependency_dict'].keys():
                        self.ns_dict[nsd_id]['dependency_dict'][dependent_vdu]['updatesTo'].append(vdu)


    def _get_vnfds_no_dependency(self ,nsd_id):
        """ Returns all the vnfds which don't have dependency """
        temp_vnfds = list()
        for vnfd in self.ns_dict[nsd_id]['nsd_template']['vnfds']:
            for vdu in self.ns_dict[nsd_id]['nsd_template']['vnfds'][vnfd]:
                if 'dependency' not in self.ns_dict[nsd_id]['nsd_template']\
                                       ['vdus'][vnfd+':'+vdu].keys():
                    temp_vnfds.append(vnfd+':'+vdu)
        return temp_vnfds

    
    def _create_flavor(self, vnfd, vdu, nsd_id):

        """ Create a openstack flavor based on vnfd flavor """
        flavor_dict = self.vnfd_parser_obj.get_flavor_dict(
                             self.ns_dict[nsd_id]['vnfds'][vnfd]['vdus'][vdu])
        flavor_dict['name'] = vnfd+'_'+vdu+flavor_dict['name']
        try:
            new_flavor = self.novaclient.create_flavor(**flavor_dict)
        except Exception:
            new_flavor = self.novaclient.get_flavor('2')
        return new_flavor 


    @auth
    def _create_vnfds(self, context, nsd_id):
        self.create_dependency_dict(nsd_id)

        """ Deploy independent VNF/VNF'S """
        self.independent_vdus = list()
        for vdu in self.ns_dict[nsd_id]['dependency_dict'].keys():
            if len(self.ns_dict[nsd_id]['dependency_dict'][vdu]['updatesFrom']) == 0:
                self.independent_vdus.append(vdu)
        
        for vnfd in self.independent_vdus:
            self._launch_vnfds(context,vnfd, nsd_id)
        self._invoke_vnf_manager(context, nsd_id)


    def wait_for_acknowledgment(self, vdus, nsd_id, event=None):
        if event:
            acknowledged = False
            while not acknowledged:
                vdu_count = 0
                for vdu in vdus:
                    LOG.debug(_('Wait for acknowledgement for vdu : %s'), vdu)
                    if vdu in self.ns_dict[nsd_id]['config-event']['errored']:
                        raise exceptions.ConfigurationError
                    elif vdu in self.ns_dict[nsd_id]['config-event']['acknowledge_list']:
                        vdu_count = vdu_count + 1
                if vdu_count == len(vdus):
                    acknowledged = True
                else:
                    time.sleep(5)
        else:
            acknowledged = False
            while not acknowledged:
                vdu_count = 0
                for vdu in vdus:
                    LOG.debug(_('Wait for acknowledgement for vdu : %s'), vdu)
                    if vdu in self.ns_dict[nsd_id]['errored']:
                        raise exceptions.ConfigurationError
                    elif vdu in self.ns_dict[nsd_id]['configured']:
                        vdu_count = vdu_count + 1
                if vdu_count == len(vdus):
                    acknowledged = True
                else:
                    time.sleep(5)


    @auth
    def _resolve_dependency(self, context, nsd_id):
       self.wait_for_acknowledgment(self.independent_vdus, nsd_id)
       while len(self.ns_dict[nsd_id]['nsd_template']['vdus']) != len(self.ns_dict[nsd_id]['configured']):
           vdus = list()
           for vdu in self.ns_dict[nsd_id]['dependency_dict'].keys():
               if vdu in self.ns_dict[nsd_id]['configured']:
                   continue
               else:
                   launched_dependencies = 0
                   actual_dependencies = len(self.ns_dict[nsd_id]['dependency_dict'][vdu]['updatesFrom'])
                   for dependent_vdu in self.ns_dict[nsd_id]['dependency_dict'][vdu]['updatesFrom']:
                       if dependent_vdu  in self.ns_dict[nsd_id]['configured']:
                           launched_dependencies += 1
                   if launched_dependencies == actual_dependencies:
                       vdus.append(vdu)

           for vdu in vdus:
               self._launch_vnfds(context,vdu, nsd_id)
           conf =  self._generate_vnfm_conf(nsd_id, context)
           for vdu in vdus:
               self.ns_dict[nsd_id]['conf_generated'].append(vdu)
           self.agent_mapping[self.ns_dict[nsd_id]['vnfmanager_uuid']].\
                  configure_vdus(context, conf=conf)
           self.wait_for_acknowledgment(vdus, nsd_id)

    
    def _get_vm_details(self, context, vnfd_name, vdu_name, nsd_id):
        self.novaclient = self._get_nova_client(context)
        self.glanceclient = self._get_glance_client(context)
        self.neutronclient = self._get_neutron_client(context)

        vdu_data = self.get_vdu_details(context, self.template_id, vdu_name, self.ns_dict[nsd_id]['qos'])
        self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]\
                    ['flavor'] = vdu_data.vdu_flavor
        self.ns_dict[nsd_id]['flavor_list'].append(vdu_data.vdu_flavor)
        name = vnfd_name.lower()+'-'+vdu_name.lower()
        vm_details = self.vnfd_parser_obj.get_boot_details(
                                 self.ns_dict[nsd_id]['vnfds'][vnfd_name]\
                                 ['vdus'][vdu_name])
        vdu_userdata = self.get_vdu_userdata(context, nsd_id, vdu_name)
        if vdu_userdata:
            vm_details['userdata'] = vdu_userdata
        self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]\
                    ['img'] = vdu_data.image_id
        vm_details['name'] = name
        vm_details['flavor'] = vdu_data.vdu_flavor
        vm_details['image_created'] = vdu_data.image_id
        return vm_details         


    def _get_vm_image_details(self, vnfd_name, vdu_name, nsd_id):
        image_details = self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus']\
                                    [vdu_name]['vm_details']['image_details']
        if 'image-id' in image_details.keys():
            image = self.glanceclient.get_image(image_details['image-id'])
        else:
            image_details['data'] = open(image_details['image'], 'rb')
            image = self.glanceclient.create_image(**image_details)
            del image_details['data']
            while image.status!='active':
                time.sleep(5)
                image = self.glanceclient.get_image(image.id)
            self.ns_dict[nsd_id]['image_list'].append(image.id)
        self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]\
                    ['new_img'] = image.id
        
        return image    

    def _get_vm_network_details(self, vnfd_name, vdu_name, nsd_id):
        nics = []
        nw_ifaces = self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus']\
                                [vdu_name]['vm_details']['network_interfaces']
        for iface in nw_ifaces:
            if 'port_id' in nw_ifaces[iface].keys():
               nics.append({"subnet-id":nw_ifaces[iface]['subnet-id'],
                    "net-id": nw_ifaces[iface]['net-id'],
                    "port-id": nw_ifaces[iface]['port_id']})
            else:
                nics.append({"subnet-id": nw_ifaces[iface]['subnet-id'],
                             "net-id": nw_ifaces[iface]['net-id']})

        if 'mgmt-if' not in self.ns_dict[nsd_id]['networks']:
            self.ns_dict[nsd_id]['networks']['mgmt-if'] = None
            return nics

        mgmt_id =  self.ns_dict[nsd_id]['networks']['mgmt-if']
        for iface in range(len(nics)):
            if nics[iface]['net-id'] == mgmt_id:
               iface_net = nics[iface]
               del nics[iface]
               nics.insert(0, iface_net)
               break
        return nics


    
    def _launch_vnfds(self, context,vnfd, nsd_id, method='create'):
        '''
        1)create conf dict
        2)send conf dict to VNF Manager using RPC if VNF Manager was already invoked
        '''
        self.novaclient = self._get_nova_client(context)
        self.glanceclient = self._get_glance_client(context)
        self.neutronclient = self._get_neutron_client(context)

        vnfd_name, vdu_name = vnfd.split(':')[0],vnfd.split(':')[1]
        vm_details = self._get_vm_details(context, vnfd_name, vdu_name, nsd_id)
        vm_details['nics'] = self._get_vm_network_details(vnfd_name,
                                                          vdu_name,
                                                          nsd_id)

        vm_details['userdata'] = self.set_default_userdata(vm_details,
                                                           nsd_id)
        self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]\
                    ['vm_details']['userdata'] = vm_details['userdata']

        self.set_default_route(vm_details, nsd_id)
        with open(vm_details['userdata'], 'r') as ud_file:
            data = ud_file.readlines()
        data1 = []
        data1.append('#cloud-config\n')
        for line in data:
            data1.append(self.format_userdata(context, line, nsd_id, vdu_name))
        with open(vm_details['userdata'], 'w') as ud_file:
            ud_file.writelines(data1)

        vm_details['method']=method
        if method == 'create':
            self.update_vdu_details(context,
                                self.ns_dict[nsd_id]['vnfds'][vnfd_name]\
                                            ['vdus'][vdu_name]['flavor'],
                                self.ns_dict[nsd_id]['vnfds'][vnfd_name]\
                                            ['vdus'][vdu_name]['img'],
                                self.ns_dict[nsd_id]['nsd_template']['vdus']\
                                            [vnfd_name+':'+vdu_name]['id'])

        deployed_vdus = self._boot_vdu(context, vnfd, nsd_id, **vm_details)
        if method == 'create':
            if type(deployed_vdus) == type([]):
                self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]\
                        ['instances'] = deployed_vdus
            else:
                self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]\
                        ['instances'] = [deployed_vdus]


        self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]\
                        ['instance_list'] = []
        # Create dictionary with vdu and it's corresponding nova instance ID details
        self._populate_instances_id(vnfd_name, vdu_name, nsd_id)
        for instance in self.ns_dict[nsd_id]['vnfds'][vnfd_name]\
                             ['vdus'][vdu_name]['instances']:
            name = instance.name
            self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]\
                        ['instance_list'].append(name)
            data = {"vdu":vdu_name,
                    "instance":instance.name,
                    "host":instance._info['OS-EXT-SRV-ATTR:host'],
                    "instanceID": instance.id}

        self.ns_dict[nsd_id]['deployed_vdus'].append(vnfd)
        self._set_mgmt_ip(vnfd_name, vdu_name, nsd_id)
        self._set_instance_ip(vnfd_name, vdu_name, nsd_id)



    def set_default_userdata(self, vm_details, nsd_id):
        temp_dict = {'runcmd':[], 'manage_etc_hosts': 'localhost'}
        temp_dict['runcmd'].append('dhclient eth1')
        if 'cfg_engine' in self.ns_dict[nsd_id]['nsd_template']\
                                       ['preconfigure'].keys() and \
                           self.ns_dict[nsd_id]['nsd_template']\
                                       ['preconfigure']['cfg_engine'] != "":
            puppet_master_ip = self.ns_dict[nsd_id]['nsd_template']\
                                           ['puppet-master']['master-ip']
            puppet_master_hostname = self.ns_dict[nsd_id]['nsd_template']\
                                          ['puppet-master']['master-hostname']
            puppet_master_instance_id = self.ns_dict[nsd_id]['nsd_template']\
                                          ['puppet-master']['instance_id']
            self.ns_dict[nsd_id]['puppet'] = puppet_master_instance_id
            temp_dict['runcmd'].append('sudo echo '+ puppet_master_ip + \
                                       ' ' + puppet_master_hostname + \
                                       ' >> /etc/hosts')
        if 'userdata' in vm_details.keys() and vm_details['userdata'] != "":
            with open(vm_details['userdata'], 'r') as f:
                data = yaml.safe_load(f)
            if 'runcmd' in data.keys():
                temp_dict['runcmd'].extend(data['runcmd'])
                data['runcmd'] = temp_dict['runcmd']
            else:
                data['runcmd'] = temp_dict['runcmd']
            data['manage_etc_hosts'] = temp_dict['manage_etc_hosts']
            with open(self.ns_dict[nsd_id]['vnfm_dir']+'/userdata',
                      'w') as ud_file:
                yaml.safe_dump(data, ud_file)
        else:
          with open(self.ns_dict[nsd_id]['vnfm_dir']+ '/userdata',
                    'w') as ud_file:
              yaml.safe_dump(temp_dict, ud_file)
        return self.ns_dict[nsd_id]['vnfm_dir']+'/userdata'


    def set_default_route(self, vm_details, nsd_id):
        nics = vm_details['nics']
        cidr = ''
        for network in nics:
            if network['net-id'] != self.ns_dict[nsd_id]['networks']['mgmt-if']:
                 subnet_id = network['subnet-id']
                 cidr = self.neutronclient.show_subnet(subnet_id)\
                                           ['subnet']['cidr']
                 break
        if  cidr != ''  and 'userdata' in vm_details.keys():
            with open(vm_details['userdata'], 'r') as f:
                data = yaml.safe_load(f)
            ip  = cidr.split('/')[0]
            ip = ip[0:-1]+'1'
            data['runcmd'].insert(1,"sudo ip route del default")
            data['runcmd'].insert(2,"sudo ip route add default via "+ ip + \
                                    " dev eth1")
            with open(vm_details['userdata'], 'w') as userdata_file:
                yaml.safe_dump(data, userdata_file)


    def _populate_instances_id(self, vnfd_name, vdu_name, nsd_id):
        if not vnfd_name+':'+vdu_name in self.ns_dict[nsd_id]['instances'].keys():
            self.ns_dict[nsd_id]['instances'][vnfd_name+':'+vdu_name] = []
        for instance in self.ns_dict[nsd_id]['vnfds'][vnfd_name]\
                                    ['vdus'][vdu_name]['instances']:
            self.ns_dict[nsd_id]['instances'][vnfd_name+':'+vdu_name].\
                     append(instance.id)
    
    def get_configurables(self, string_to_search):
        empty = ""
        configurables = list()
        if string_to_search is None:
           return None
        keyword_start = [m.start()+1 for m in re.finditer('{',string_to_search)] 
        keyword_end = [m.start() for m in re.finditer('}',string_to_search)]
        
        if len(keyword_start) == len(keyword_end):
           for idx in xrange(0, len(keyword_start)):
               configurable = string_to_search[keyword_start[idx]:keyword_end[idx]]
               if configurable not in configurables:
                  configurables.append(configurable)
               else:
                  continue

        if not configurables:
            return None

        return configurables

    def get_network_interfaces(self, vdu_details_dict):
        return vdu_details_dict['vm_details']['network_interfaces']

    def configurables_dict(self, nsd_id, configurables, instance=None):
        format_data = dict()
        for configurable in configurables:
            Delimiter = '#'
            if instance.find(configurable.split('#')[0].lower())>=0:
               vm_name = instance
            else:
               vm_name = configurable.split(Delimiter)[0].lower()
            parameter = configurable.split(Delimiter)[1]
            vnfd_name = re.sub(r'\d+', '', configurable).split('-')[0]
            #vdu_name = vm_name[len(re.sub(r'\d+', '', vm_name).split('-')[0])+1:]
            vdu_name = configurable.split('#')[0].split('-')[1]
            vdu_dict = self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]
            network_ifaces = self.get_network_interfaces(vdu_dict)
            if parameter in network_ifaces.keys():
                if instance != None:
                    if vm_name.lower() in instance:
                        vm_name = instance
                format_data[configurable] = network_ifaces[parameter]['ips'][vm_name.lower()]
        return format_data


    def format_lfevents(self, **kwargs):
        event = kwargs['event']
        if event:
            method = 'format_'+event
            func = getattr(self, method, None)
            if func:
                return func(**kwargs)
            else:
                return ''
        else:
            return ''


    def format_config(self, **kwargs):
        return self.format_init(**kwargs)



    def format_init(self, **kwargs):
        lf_event = kwargs['lf_event']
        instance = kwargs['instance']
        nsd_id = kwargs['nsd_id']
        if lf_event['data']:
            string_to_search = str(lf_event['data'])
            if string_to_search != '' and string_to_search[0]!= '<' and type(eval(string_to_search)) is dict:
               string_to_search = string_to_search.replace("{'","$'").replace("'}","'$").replace('$}',"$$")
         
            if string_to_search != '':
                configurables =  self.get_configurables(string_to_search)
                if configurables is None:
                    return
                format_data = self.configurables_dict(nsd_id, configurables, instance)
                formatted_event = string_to_search.format(**format_data)
                if (str(formatted_event)[0]!= '<' and (type(eval(str(formatted_event).replace('"$','{').replace('$\'','{\'').replace('$$"','}}').replace('\'$','\'}')))) is dict):
                #if type(eval(str(formatted_event).replace('"$','{').replace('$\'','{\'').replace('$$"','}}').replace('\'$','\'}'))) is dict:
                    formatted_event = eval(str(formatted_event).replace('"$','{').replace('$\'','{\'').replace('$$"','}}').replace('\'$','\'}'))
                return formatted_event
        else: 
            return ""

    def format_userdata(self, context, data, nsd_id, vdu_name):
        string_to_search = data
        if string_to_search != '':
            configurables =  self.get_configurables(string_to_search)
            if configurables is None:
                return data
            for configurable in configurables:
                format_data = {}
                if 'instance_index' in configurable:
                    service = self.get_service_by_nsd_id(context, nsd_id)
                    vdus = eval(service['vdus'])
                    if service:
                        for vdu in vdus:
                            if vdu_name in vdu:
                                if vdu_name in configurable.split('#')[0]:
                                    instances = self.get_instance_ids(context, vdus[vdu])
                                    if instances:
                                        instance_list = instances.split(',')
                                        format_data[configurable] = len(instance_list) + 1
                                    else:
                                        format_data[configurable] = 1
                userdata = string_to_search.format(**format_data)
                return userdata
        else:
            return ""

    @auth
    def format_diagnostics(self, context, command, instance, nsd_id):
        string_to_search = command
        configurables =  self.get_configurables(string_to_search)
        if configurables is None:
            return
        format_data = self.configurables_dict(nsd_id, configurables, instance)
        iface_tap_map = utility.Utils(context)._get_port_iface_map(format_data)
        diagnostics = string_to_search.format(**iface_tap_map)
        return iface_tap_map,diagnostics


    def _generate_vnfm_conf(self, nsd_id, context):
        vnfm_dict = {}
        vnfm_dict['service'] = {}
        vnfm_dict['service']['nsd_id'] = nsd_id
        current_vnfs = [vdu for vdu in self.ns_dict[nsd_id]['deployed_vdus'] \
                        if vdu not in self.ns_dict[nsd_id]['conf_generated']]
        for vnf in current_vnfs:
            if not self.ns_dict[nsd_id]['is_manager_invoked']:
                vnfm_dict['service']['id'] = self.ns_dict[nsd_id]\
                                                  ['service_name']
                vnfm_dict['service']['fg'] = self.ns_dict[nsd_id]\
                                             ['nsd_template']\
                                             ['postconfigure']\
                                             ['forwarding_graphs']
            vnfd_name, vdu_name = vnf.split(':')[0],vnf.split(':')[1]
            if vnfd_name  not in vnfm_dict['service'].keys(): 
                vnfm_dict['service'][vnfd_name] = list()
            vdu_dict = {}
            vdu_dict['name'] = vdu_name
            vdu = self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]
            formatted_lfevents = {}
            for property in vdu:
                if property not in ['preconfigure', 'instances']:
                    if property == 'postconfigure':
                        if 'lifecycle_events' in vdu['postconfigure'].keys():
                            if vdu['postconfigure']['lifecycle_events'] != "" and vdu['postconfigure']['lifecycle_events'] is not None:
                                #formatted_lfevents['init'] = {}
                                for instance in vdu['instance_list']:
                                    if instance not in self.configured_instances:
                                       lf_events = self.get_lfevents(context, nsd_id, vdu_name)
                                       for event in lf_events:
                                           if event ==  'init':
                                               formatted_lfevents[event] = {}
                                               formatted_lfevents[event] = lf_events[event]
                                               format_args = {'lf_event' : lf_events[event],
                                                              'event' : event,
                                                              'nsd_id' : nsd_id,
                                                              'instance' : instance}
                                               formatted_lfevents[event]['data'] = self.format_lfevents(**format_args)
                                               formatted_lfevents[event]['driver'] = lf_events[event]['driver']  
                                       self.configured_instances.append(instance)
                            else:
                                formatted_lfevents = {'init': ''}
                            vdu['postconfigure']['lifecycle_events'] = formatted_lfevents
                            del formatted_lfevents
                        vdu_dict.update(vdu['postconfigure'])
                    else:
                        vdu_dict[property] = vdu[property]
            vnfm_dict['service'][vnfd_name].append(vdu_dict)
            self.ns_dict[nsd_id]['conf_generated'].append(vnf)

        return vnfm_dict
    
    def _boot_vdu(self, context, vnfd, nsd_id, **vm_details):
        
        self.novaclient = self._get_nova_client(context)
        self.glanceclient = self._get_glance_client(context)
        self.neutronclient = self._get_neutron_client(context)
        vdu_id = self.ns_dict[nsd_id]['nsd_template']['vdus'][vnfd]['id']
        launched_instances = self.get_instance_ids(context, vdu_id) 
        if launched_instances == '':
            instance = self.novaclient.server_create(vm_details)
        else:
            index = len(launched_instances.split(","))
            instance = self.novaclient.server_create(vm_details, index=index)
        if vm_details['num_instances'] == 1:
            instance = self.novaclient.get_server(instance.id)
            self.update_vdu_instance_details(context,
                                             instance.id,
                                             self.ns_dict[nsd_id]\
                                             ['nsd_template']['vdus']\
                                             [vnfd]['id'])
            while instance.status != 'ACTIVE' or \
                   all(not instance.networks[iface] \
                   for iface in instance.networks.keys()):
                time.sleep(3)
                instance = self.novaclient.get_server(instance.id)
                if instance.status == 'ERROR':
                    self.update_nsd_status(context, nsd_id, 'ERROR')
                    raise exceptions.InstanceException()
        else:
            instances_list = instance
            instance = list()
            instances_active = 0
            temp_instance = None
            for temp_instance in instances_list:
                self.update_vdu_instance_details(context, temp_instance.id,
                                self.ns_dict[nsd_id]['nsd_template']\
                                ['vdus'][vnfd]['id'])

            while instances_active != vm_details['num_instances'] or \
                  len(instances_list) > 0:
                for inst in instances_list:
                    temp_instance = self.novaclient.get_server(inst.id)
                    if temp_instance.status == 'ACTIVE':
                        instances_active += 1
                        instances_list.remove(inst)
                        instance.append(inst)
                    elif temp_instance.status == 'ERROR':
                        self.update_nsd_status(context, nsd_id, 'ERROR')
                        raise exceptions.InstanceException()
                    else:
                        time.sleep(3)

        return instance
 

    def _set_instance_ip(self, vnfd_name, vdu_name, nsd_id):
        instances = self.ns_dict[nsd_id]['vnfds'][vnfd_name]\
                      ['vdus'][vdu_name]['instances']
        ninterfaces = self.ns_dict[nsd_id]['vnfds'][vnfd_name]\
                        ['vdus'][vdu_name]['vm_details']['network_interfaces']
        for interface in ninterfaces:
            subnet =self.neutronclient.show_subnet(
                           ninterfaces[interface]['subnet-id'])
            cidr = subnet['subnet']['cidr']
            ninterfaces[interface]['ips'] = self._get_ips(instances, cidr)

        
    def _get_ips(self, instances, cidr):
        ip_list = {}
        for instance in instances:
            instance_name = instance.name
            networks = instance.addresses
            for network in networks.keys():
                for i in range(len(networks[network])):
                    ip = networks[network][i]['addr']
                    if IPAddress(ip) in IPNetwork(cidr):
                       ip_list[instance_name]= ip
        return ip_list 


    def _set_mgmt_ip(self,vnfd_name, vdu_name, nsd_id):
        instances = self.ns_dict[nsd_id]['vnfds'][vnfd_name]\
                         ['vdus'][vdu_name]['instances']
        self.ns_dict[nsd_id]['vnfds'][vnfd_name]\
                    ['vdus'][vdu_name]['mgmt-ip'] = {}
        if 'mgmt-cidr' not in self.ns_dict[nsd_id]['nsd_template']:
            return
        mgmt_cidr = self.ns_dict[nsd_id]['nsd_template']['mgmt-cidr']
        for instance in instances:
            networks = instance.addresses
            for network in networks.keys():
                for subnet in networks[network]:
                    ip = subnet['addr']
                    if IPAddress(ip) in IPNetwork(mgmt_cidr):
                        self.ns_dict[nsd_id]['vnfds'][vnfd_name]\
                             ['vdus'][vdu_name]['mgmt-ip'][instance.name] = ip


    def _copy_vnfmanager(self):
        src = self.conf.vnf.vnfmanager
        dest = '/tmp/vnfmanager'
        try:
            dir_util.copy_tree(src, dest)
            return dest
        except OSError as exc:
            raise


    def get_service(self, context, service, **kwargs):
        service = self.get_service_model(context, service, fields=None)
        return service

    def get_services(self,context, **kwargs):
        service=self.get_all_services(context, **kwargs)
        return service

    def get_diagnostic(self, context, nsd_id, **kwargs):
        return {nsd_id: ''}

    def get_diagnostics(self, context, **kwargs):
        service = self.get_all_services(context, **kwargs)
        return service

    def _get_manager_info(self, context):
        return self.get_manager_info(context)

    def _make_tar(self, vnfmanager_path):
        tar = tarfile.open(vnfmanager_path+'.tar.gz', 'w:gz')
        tar.add(vnfmanager_path)
        tar.close() 
        return vnfmanager_path+'.tar.gz'

    @auth
    def _invoke_vnf_manager(self, context, nsd_id):
        """Invokes VNF manager using ansible(if multihost)"""
        vnfm_conf_dict = self._generate_vnfm_conf(nsd_id, context)
        with open(self.ns_dict[nsd_id]['vnfm_dir'] + '/' + \
                  self.ns_dict[nsd_id]['vnfmanager_uuid']+'.yaml', 'w') as f:
            yaml.safe_dump(vnfm_conf_dict, f)
        vnfm_conf = self.ns_dict[nsd_id]['vnfm_dir'] + '/' + \
                    self.ns_dict[nsd_id]['vnfmanager_uuid']+'.yaml'
        vnfsvc_conf = cfg.CONF.config_file[0]
        vnfm_namespace = 'vnfm-'+self.ns_dict[nsd_id]['vnfmanager_uuid']

        mgmt_if_id = None
        if 'mgmt-if' in self.ns_dict[nsd_id]['nsd_template']['networks']:
            mgmt_if_id = self.ns_dict[nsd_id]['nsd_template']['networks']['mgmt-if']['id']

        ovs_path,p_id ,service_port_id = self._create_ovs_script(mgmt_if_id, nsd_id,vnfm_namespace)
        del_path = self._create_del_script(nsd_id, self.ns_dict[nsd_id]['vnfmanager_uuid'],vnfm_namespace,  p_id,service_port_id)

        host = None
        vnfm_host = None
        if cfg.CONF.vnf.compute_hostname:
            host = cfg.CONF.vnf.compute_hostname
            vnfm_host = self.novaclient.check_host(cfg.CONF.vnf.compute_hostname)
        if cfg.CONF.vnf.compute_ip:
            vnfm_host.host_ip = cfg.CONF.vnf.compute_ip
        if cfg.CONF.vnf.vnfmconf == "local":
            confcmd  = 'sudo ip netns exec '+vnfm_namespace+' vnf-manager ' + \
                       '--config-file /etc/vnfsvc/vnfsvc.conf'\
                       ' --vnfm-conf-dir ' + \
                       self.ns_dict[nsd_id]['vnfm_dir'] + \
                       '/ --log-file ' + self.ns_dict[nsd_id]['vnfm_dir'] + \
                       '/vnfm.log --uuid ' + \
                       self.ns_dict[nsd_id]['vnfmanager_uuid']


            host = 'local'
            ovscmd =  'sudo sh '+ self.ns_dict[nsd_id]['vnfm_dir'] + '/ovs.sh'
            proc = subprocess.Popen(ovscmd, shell=True)
            proc2 = subprocess.Popen(confcmd.split(),
                                     stderr=open('/dev/null', 'w'),
                                     stdout=open('/dev/null', 'w'))
        elif cfg.CONF.vnf.vnfmconf == "ansible":
            with open(self.ns_dict[nsd_id]['vnfm_dir']+'/hosts', 'w') as hosts_file:
                 hosts_file.write("[%s]\n%s\n"%(host, vnfm_host.host_ip))
            vnfm_home_dir =  '{{ ansible_env["HOME"] }}/.vnfm/' +self.ns_dict[nsd_id]\
                                                         ['vnfmanager_uuid']
            vnfmanager_path = cfg.CONF.vnf.vnfmanager
            ansible_dict=[{'tasks': [
                            {'ignore_errors': True, 'shell': 'mkdir -p '+\
                          vnfm_home_dir},
                            {'copy': 'src='+ vnfsvc_conf +' dest='+\
                          vnfm_home_dir+'/vnfsvc.conf'},
                            {'ignore_errors': True, 'shell': "pip freeze | grep 'vnf-manager'", 'name': 'check whether the vnf manager is installed or not', 'register': 'result'},
                            {'sudo': 'yes', 'copy': 'src='+vnfmanager_path+' dest='+\
                          vnfm_home_dir, 'name': 'move vnf manager', 'when': 'result.rc!=0'},
                            {'shell': 'cd '+vnfm_home_dir+'/vnfmanager && git init', 'sudo': 'yes', 'when': 'result.rc!=0'},
                            {'shell': 'cd '+vnfm_home_dir+'/vnfmanager && sudo python setup.py install', 'when': 'result.rc!=0', 'name': 'install manager'},
                            {'copy': 'src='+ vnfm_conf + ' dest=' + \
                          vnfm_home_dir + '/' + \
                          self.ns_dict[nsd_id]['vnfmanager_uuid'] + \
                          '.yaml'},
                            {'copy': 'src='+ ovs_path + ' dest=' + \
                          vnfm_home_dir + '/ovs.sh'},
                            {'copy': 'src='+ del_path + ' dest=' + \
                          vnfm_home_dir + '/del.sh'},
                            {'ignore_errors': True, 'shell': 'sh '+ \
                          vnfm_home_dir + '/ovs.sh', 'register': 'result1'},


                            {'sudo': 'yes','async': 1000000, 'poll': 0,
                         # 'command': 'vnf-manager --config-file '+ \
                          'shell': 'ip netns exec '+ vnfm_namespace +' vnf-manager --config-file '+ \
                          vnfm_home_dir + '/vnfsvc.conf --vnfm-conf-dir '+ \
                          vnfm_home_dir + '/ --log-file ' + vnfm_home_dir + \
                          '/vnfm.log --uuid %s'
                          % self.ns_dict[nsd_id]['vnfmanager_uuid'],
                          'name': 'run manager'},
                            {'debug': 'var=result1.stdout_lines'},
                        ], 'hosts': host, 'remote_user': \
                          cfg.CONF.vnf.compute_user}]

            with open(self.ns_dict[nsd_id]['vnfm_dir'] +\
                      '/vnfmanager-playbook.yaml', 'w') as yaml_file:
                yaml_file.write( yaml.dump(ansible_dict,
                                           default_flow_style=False))
            LOG.debug(_('----- Launching VNF Manager -----'))

            ansible_cmd = 'ansible-playbook ' +\
                    self.ns_dict[nsd_id]['vnfm_dir'] +\
                    '/vnfmanager-playbook.yaml -i ' +\
                    self.ns_dict[nsd_id]['vnfm_dir'] +\
                    '/hosts'

            if cfg.CONF.vnf.ssh_pwd:
                ansible_cmd += ' --ask-pass'
                child = pexpect.spawn(ansible_cmd, timeout=None)
                child.expect('SSH password:')
                child.sendline(cfg.CONF.vnf.ssh_pwd)
                result =  child.readlines()
            else:
                (result,status) = pexpect.runu('ansible-playbook ' +\
                                  self.ns_dict[nsd_id]['vnfm_dir'] +\
                                  '/vnfmanager-playbook.yaml -i ' +\
                                  self.ns_dict[nsd_id]['vnfm_dir'] +\
                                  '/hosts',
                                  events={u'SSH password:': unicode(cfg.CONF.vnf.ssh_pwd)},
                                  withexitstatus=True, timeout=120)
                LOG.debug(_('----STATUS %s ---' %status))
                LOG.debug(_('---RESULT %s --- ' % result))

        self.agent_mapping[self.ns_dict[nsd_id]['vnfmanager_uuid']] =\
                      VNFManagerAgentApi(topics.get_topic_for_mgr(
                                     self.ns_dict[nsd_id]['vnfmanager_uuid']),
                                         cfg.CONF.host, self)
        #nc = self.neutronclient
        self.update_ns_vnfm_host(self.ns_dict[nsd_id]['vnf_context'], nsd_id, host)
        body = {'port': {'binding:host_id': cfg.CONF.vnf.compute_hostname}}
        nc = self._get_neutron_client(context)
        if p_id:
            v_port_updated = nc.update_port(p_id,body)
        if service_port_id:
            s_port_updated = nc.update_port(service_port_id, body)

        self.ns_dict[nsd_id]['is_manager_invoked'] = True
        self._resolve_dependency(context, nsd_id)

    def _create_del_script(self, nsd_id, vnfm_id,vnfm_namespace, p_id,s_p_id):
        del_dict = []
        del_dict.append('#!/bin/sh\n')
        if p_id is not None:
            del_dict.append('sudo ovs-vsctl del-port vtap-%s \n' %(str(p_id)[:8]))
        if s_p_id is not None:
            del_dict.append('sudo ovs-vsctl del-port stap-%s \n' %(str(s_p_id)[:8]))
        del_dict.append('sudo kill -9 `ps -eaf | grep vnf-manager | grep %s | awk \'{print $2}\'` \n'%vnfm_id)
        del_dict.append('sudo ip netns del %s\n'%vnfm_namespace)


        with open(self.ns_dict[nsd_id]['vnfm_dir']+'/del.sh', 'w') as f:
             f.writelines(del_dict)
        return self.ns_dict[nsd_id]['vnfm_dir']+'/del.sh'

    def _create_ovs_script(self, mgmt_id, nsd_id,vnfm_namespace):
        if not mgmt_id:
            with open(self.ns_dict[nsd_id]['vnfm_dir']+'/ovs.sh', 'w') as f:
                f.writelines("")
            return self.ns_dict[nsd_id]['vnfm_dir']+'/ovs.sh',None    

        nc = self.neutronclient
        subs = nc.get_subnets()
        for sub in subs:
            if sub['cidr'] == self.service_cidr:
                self.service_network = sub['network_id']
        service_port = nc.create_port({'port':{'network_id': self.service_network}})
        #service_port = nc.create_port({'port':{'network_id': self.service_network, 'port_security_enabled': 'True'}})

        s_p_id = service_port['port']['id']
        service_mac_address = service_port['port']['mac_address']
        serv_mac_address_var = service_mac_address.replace(':', '\:')

        v_port = nc.create_port({'port':{'network_id': mgmt_id}})
        p_id = v_port['port']['id']
        mac_address = v_port['port']['mac_address']
        mac_address_var = mac_address.replace(':', '\:')
        lines_dict = []
        lines_dict.append('#!/bin/sh\n')
        lines_dict.append('sudo ovs-vsctl add-port br-int vtap-%s \
                -- set interface vtap-%s type=internal \
                -- set interface vtap-%s external-ids:iface-id=%s \
                -- set interface vtap-%s external-ids:iface-status=active \
                -- set interface vtap-%s external-ids:attached-mac=%s\
                -- set interface vtap-%s mac=\"%s\"\n'
                %(str(p_id)[:8],str(p_id)[:8],str(p_id)[:8],str(p_id),
                  str(p_id)[:8],str(p_id)[:8],str(mac_address), str(p_id)[:8], str(mac_address_var)))
        lines_dict.append('sudo ovs-vsctl add-port br-int stap-%s \
                -- set interface stap-%s type=internal \
                -- set interface stap-%s external-ids:iface-id=%s \
                -- set interface stap-%s external-ids:iface-status=active \
                -- set interface stap-%s external-ids:attached-mac=%s\
                -- set interface stap-%s mac=\"%s\"\n'
                %(str(s_p_id)[:8],str(s_p_id)[:8],str(s_p_id)[:8],str(s_p_id),
                  str(s_p_id)[:8],str(s_p_id)[:8],str(service_mac_address), str(s_p_id)[:8], str(serv_mac_address_var)))

        sudo_ip_namespace_wrapper = 'sudo ip netns'
        lines_dict.append('%s add %s\n'%(sudo_ip_namespace_wrapper, vnfm_namespace))
        lines_dict.append('sudo ip link set vtap-%s netns %s\n'%(str(p_id)[:8], vnfm_namespace))
        lines_dict.append('sudo ip link set stap-%s netns %s\n'%(str(s_p_id)[:8], vnfm_namespace))
        lines_dict.append('%s exec %s ifconfig vtap-%s %s up\n'
                %(sudo_ip_namespace_wrapper, vnfm_namespace, str(p_id)[:8],str(v_port['port']['fixed_ips'][0]\
                  ['ip_address'])))
        lines_dict.append('%s exec %s ifconfig stap-%s %s up\n'
                %(sudo_ip_namespace_wrapper, vnfm_namespace, str(s_p_id)[:8], str(service_port['port']['fixed_ips'][0]\
                  ['ip_address'])))



        with open(self.ns_dict[nsd_id]['vnfm_dir']+'/ovs.sh', 'w') as f:
            f.writelines(lines_dict)
        return self.ns_dict[nsd_id]['vnfm_dir']+'/ovs.sh', str(p_id), str(s_p_id)

  

    @auth
    def build_Ack(self,context, vnfd, vdu, instance, status, nsd_id, gen_conf, event=None):
        pass

    @auth
    def buildConfigAck(self, context, vnfd_name, vdu_name, instance, status, nsd_id, conf):
        if status == 'ERROR':
            self.ns_dict[nsd_id]['config-event']['errored'].append(vdu_name)
            self.update_nsd_status(context, nsd_id, 'ERROR')
        else:
            if self.ns_dict[nsd_id]['config-event']['acknowledge_list'].get(vdu_name, None):
                self.ns_dict[nsd_id]['config-event']['acknowledge_list'][vdu_name].append(instance)
            else:
                self.ns_dict[nsd_id]['config-event']['acknowledge_list'][vdu_name] = [instance]


    @auth
    def build_acknowledge_list(self, context, vnfd_name, vdu_name, instance, status, nsd_id, conf):
        vdu = vnfd_name+':'+vdu_name
        if status == 'ERROR':
            self.ns_dict[nsd_id]['errored'].append(vdu)
            self.update_nsd_status(context, nsd_id, 'ERROR')
        else:
            if self.ns_dict[nsd_id]['acknowledge_list'].get(vdu, None):
                self.ns_dict[nsd_id]['acknowledge_list'][vdu].append(instance)
            else:
                self.ns_dict[nsd_id]['acknowledge_list'][vdu] = [instance]

            # Check whether all the instances of a specific VDU 
            # are acknowledged
            vdu_instances = len(self.ns_dict[nsd_id]['vnfds'] \
                                [vnfd_name]['vdus'][vdu_name]['instances'])
            current_instances = len(self.ns_dict[nsd_id] \
                                    ['acknowledge_list'][vdu])
            self.ns_dict[nsd_id]['vnfm_conf']['vnfds'] = conf
            for i in range (0, len(self.ns_dict[nsd_id]['vnfm_conf']['vnfds'][vnfd_name])):
                if self.ns_dict[nsd_id]['vnfm_conf']['vnfds'][vnfd_name][i]['name'] == vdu_name:
                    self.ns_dict[nsd_id]['vnfm_conf']['vnfds'][vnfd_name][i].update(self.ns_dict[nsd_id]['vnfds'][vnfd_name]['vdus'][vdu_name]['preconfigure'])
            if vdu_instances <= current_instances:
                self.ns_dict[nsd_id]['configured'].append(vdu)


    @auth
    def create_template(self, context, template):
        if context.user_name != 'admin':
            LOG.debug(_("Not a privileged user !"))
            raise exceptions.NotAuthorized()
        template_id = str(uuid.uuid4())
        json_dict = {}
        specs_dict = {}
        template_db = {}
        template_db['id'] = template_id
        template_db['status'] = 'True'

        template_db['template_path'] = {}
        for files in template['template']['files']:
            if files.find('nsd') >=0:
               template_name = files
        template_db['parser'] = eval(template['template']['files'][template_name])['nsd']['parser']
        template_db['version'] = eval(template['template']['files'][template_name])['nsd']['version']
        template_json = json.load(open(self.conf.vnf.templates, 'r'))
        newpath = self.conf.state_path+"/templates/"+template['template']['name']
        vnf_conf_dict = {}
        if not os.path.exists(newpath):
            os.makedirs(newpath)
        for files in template['template']['files']:
            for key in template_json.keys():
                if files.find(key) == 0:
                    if key == 'nsd':
                        service = self.get_service_name(context, files[len(key)+1:files.find('.')])
                        if service:
                            raise exceptions.ServiceException()
        template_db['template_path']['nsd'] = []
        template_db['template_path']['vnfd'] = []
        for files in template['template']['files']:
            pyaml.dump(json.JSONDecoder(object_pairs_hook=OrderedDict).decode(template['template']['files'][files]),open(newpath+"/"+files,'w+'))
            for key in template_json.keys():
                if files.find(key) == 0:
                    if key == 'nsd':
                        template_db['service_type'] = files[len(key)+1:files.find('.')]
                        template_json[key][files[len(key)+1:files.find('.')]] = newpath+"/"+files
                        template_db['template_path']['nsd'].append(newpath+"/"+files)
                    else :
                        vnf_dict = template['template']['files'][files]
                        vnf_conf_dict[files[len(key)+1:files.find('.')]] = {}
                        vnf_conf_dict[files[len(key)+1:files.find('.')]]['conf'] = self.get_vnf_details(context, template_db['id'], vnf_dict,specs_dict)
                        template_db['specs']= specs_dict
                        template_json[key][files[len(key)+1:files.find('.')]] = newpath+"/"+files
                        template_db['template_path']['vnfd'].append(newpath+"/"+files)
            with open(self.conf.vnf.templates, 'w') as outfile:
                json.dump(template_json, outfile, indent=2, sort_keys=True)
        json_dict = self.populate_template_details(context,template_db)
        self.populate_vdu_configuration(context, template_id, vnf_conf_dict)
        return json_dict



    def _get_vdus_mgmt_ip(self, ns_id, vdu):
        mgmt_list = []
        req_vnf, req_vdu = vdu.split(':')
        if ns_id in self.ns_dict.keys():
            for vnf in self.ns_dict[ns_id]['vnfds']:
                if vnf == req_vnf:
                    for vdu in self.ns_dict[ns_id]['vnfds'][vnf]['vdus']:
                        if vdu == req_vdu:
                            for instance in self.ns_dict[ns_id]['vnfds'][vnf]['vdus'][vdu]['mgmt-ip'].keys():
                                mgmt_list.extend([self.ns_dict[ns_id]['vnfds'][vnf]['vdus'][vdu]['mgmt-ip'][instance]])
                            return mgmt_list
        else:
            return ''


    @auth
    def get_vnf_details(self, context, template_id, vnf_dict, specs_dict):
        try:
            vnf_details = json.loads(vnf_dict)
            config={}
            config['flavours']={}
            specs_dict['flavour']= {}

            image_list = {}
            image_list['image-id']=[]
            flavor_list = {}
            for flavour in vnf_details['vnfd']['flavours']:
                config['flavours'][flavour] = {}
                specs_dict['flavour'][flavour]= {}
 
                config['flavours'][flavour]['vdus'] = {}
                specs_dict['flavour'][flavour]['vdu']= {}

                for vdu in vnf_details['vnfd']['flavours'][flavour]['vdus']:
                    driverpath = vnfsvc_utils.getFromDict(vnf_details, ['vnfd', 'flavours', flavour, 'vdus', vdu, 'network-interfaces', 'management-interface', 'properties', 'driver'])
                    specs_dict['flavour'][flavour]['vdu'][vdu]= {}

                    config['flavours'][flavour]['vdus'][vdu]={}
                    config['flavours'][flavour]['vdus'][vdu]['vdu-config']=[]
                    conf_data = self.get_driver_details(driverpath)
                    config['flavours'][flavour]['vdus'][vdu]['vdu-config'] = conf_data
                    if 'image-id' in vnf_details['vnfd']['flavours'][flavour]['vdus'][vdu]['vm-spec'].keys():
                        image_id = vnf_details['vnfd']['flavours'][flavour]['vdus'][vdu]['vm-spec']['image-id']
                        if image_id:

                            if image_id not in image_list['image-id']:
                                image = self.get_vdu_image(context,
                                    vnf_details['vnfd']['flavours'][flavour]['vdus'][vdu]['vm-spec'])
                                config['flavours'][flavour]['vdus'][vdu]['image'] = image.id
                                image_list['image-id'].append(image.id)
                            else:
                                config['flavours'][flavour]['vdus'][vdu]['image'] = image_id
                    else:
                        image_path = vnf_details['vnfd']['flavours'][flavour]['vdus'][vdu]['vm-spec']['image']
                        if image_path:
                            if image_path not in image_list:
                                image = self.get_vdu_image(context,
                                    vnf_details['vnfd']['flavours'][flavour]['vdus'][vdu]['vm-spec'])
                                config['flavours'][flavour]['vdus'][vdu]['image'] = image.id
                                image_list[image_path] = image.id
                            else:
                                config['flavours'][flavour]['vdus'][vdu]['image'] = image_list[image_path]
                    vdu_flavor_dict = {}
                    vdu_flavor_dict['ram'] = vnf_details['vnfd']['flavours'][flavour]['vdus'][vdu]['memory']['total-memory-mb']
                    specs_dict['flavour'][flavour]['vdu'][vdu]['instances'] = vnf_details['vnfd']['flavours'][flavour]['vdus'][vdu]['num-instances']
                    specs_dict['flavour'][flavour]['vdu'][vdu]['ram']= vdu_flavor_dict['ram']


                    vdu_flavor_dict['vcpus'] = vnf_details['vnfd']['flavours'][flavour]['vdus'][vdu]['cpu']['num-vcpu']
                    specs_dict['flavour'][flavour]['vdu'][vdu]['vcpus']= vdu_flavor_dict['vcpus']
                    vdu_flavor_dict['disk'] = vnf_details['vnfd']['flavours'][flavour]['vdus'][vdu]['storage']
                    specs_dict['flavour'][flavour]['vdu'][vdu]['disk']= vdu_flavor_dict['disk']
                    if vdu_flavor_dict not in flavor_list.values():
                        vdu_flavor_dict['name'] = vnf_details['vnfd']['flavours'][flavour]['flavour-id']+'_'\
                                              +vnf_details['vnfd']['id']+'_'\
                                              +vnf_details['vnfd']['flavours'][flavour]['vdus'][vdu]['vdu-id']
                        flavor = self.novaclient.create_flavor(**vdu_flavor_dict)
                        config['flavours'][flavour]['vdus'][vdu]['flavor'] = flavor.id
                        del vdu_flavor_dict['name']
                        flavor_list[flavor.id] = vdu_flavor_dict
                    else:
                        config['flavours'][flavour]['vdus'][vdu]['flavor'] = flavor_list.keys()[flavor_list.values().index(vdu_flavor_dict)]
            return config
        except:
            LOG.debug(_("Exception occured while uploading template"))
            del image_list['image-id']
            self.template_cleanup(flavor_list.keys(), image_list)
            raise

    def template_cleanup(self, flavor, image_list):
        for flavor_id in flavor:
            self.novaclient.delete_flavor(flavor_id)
        for image_path in image_list:
            image = image_list[image_path]
            self.glanceclient.delete_image(image)

    def get_driver_details(self, driverpath):
        help_data = []
        if driverpath and driverpath != '':
            mod_drv,cls_drv=driverpath.rsplit(".",1)
            drv_object=getattr(importlib.import_module(mod_drv),cls_drv)
            drv_method = [x for x in dir(drv_object) if not x.startswith('_')]
            methods_supported = ['update', 'reconfigure']
            method_api = list(set(drv_method).intersection(set(methods_supported)))
            help_data = []
            for method in method_api:
                api_obj = getattr(drv_object, method)
                help_text = api_obj.__doc__
                help_data.append(method + ':' + str(help_text))
        else:
            help_data = "No Update is available for this VDU"
        return help_data

    @auth
    def get_vdu_image(self, context, vm_spec):
        image_details = vm_spec
        if 'image-id' in image_details:
            if image_details['image-id']:
                image = self.glanceclient.get_image(image_details['image-id'])
                if image.status != 'active':
                    LOG.debug(_("Requested image doesn't exists !!"))
                    raise Exception()
        else:
            image_details['data'] = open(image_details['image'], 'rb')
            image = self.glanceclient.create_image(**image_details)
            del image_details['data']
            while image.status!='active':
                time.sleep(5)
                image = self.glanceclient.get_image(image.id)
        return image

    def get_templates(self, context, filters, fields=None):
        template = self.get_all_template(context, filters, fields=None)
        return template


    def get_template(self,context, template, **kwargs):
        service=self.get_template_model(context, template_id=template, fields=None)
        return service

    @auth
    def delete_template(self, context, template_id):
        try:
            flavor = self.get_flavor_list(context, template_id)
            image  = self.get_image_list(context, template_id)
            for flavor_id in flavor:
                self.novaclient.delete_flavor(flavor_id)
            self.delete_template_info(context, template_id)
        except Exception:
            raise

    def create_diagnostic(self, context, **kwargs):
        self.novaclient = self._get_nova_client(context)
        vdus_list = []
        nsd_id = kwargs['diagnostic']['diagnostic']['nsd_id']
        files_dict = eval(kwargs['diagnostic']['diagnostic']['files_dict'])
        vdus_input = eval(kwargs['diagnostic']['diagnostic']['files_dict']).keys()
        nsd_dict = self.get_network_service_details(context, nsd_id)
        vdu_info = {}
        if nsd_dict is None:
            msg = _("No such network service %s found " %nsd_id)
            raise exc.HTTPBadRequest(explanation=msg)
        else:
            vdus_from_db = list()
            for name, vdu_id in ast.literal_eval(nsd_dict.vdus).iteritems():
                vdu_info[vdu_id] = name
                vdus_from_db.append(vdu_id)
        instance_list = self._get_vdu_instance_info(context, vdus_from_db, vdu_info)
        vdus_dict = eval(nsd_dict.__dict__['vdus'])
        if vdus_input != {}:
           vdus_list = vdus_input
        else :
            vdus_list = vdus_from_db
        for vdus in vdus_list:
            files_list = files_dict[vdus]
            for instance in instance_list[vdus]:
                diagnostics_map = dict()
                instance_name = self.novaclient.server_details(instance).name
                for vdu in vdus_dict:
                    if vdus_dict[vdu] == vdus:
                        vdu_name = vdu
                vnfd_name = vdu_name.split(':')[0]
                vdu = vdu_name.split(':')[1]
                diagnostics_list = []
                diagnostics_map['files_list'] = files_list
                if set(vdus_list).issubset(vdus_from_db):
                    if len(vdus_list) == len(vdus_from_db):
                        instances = self._get_vdu_instance_info(context, vdus_from_db, vdu_info)
                    else:
                        instances = self._get_vdu_instance_info(context, vdus_list, vdu_info)
                    dm = diagnostics.DiagnosticsManager(context, nsd_id, instances, vdu_info)
                    dm.start_diagnostics(vdus ,instance, diagnostics_map)
                    self.ns_dict[nsd_id]['diagnostics_obj'] = dm
                else:
                #raise exceptions.InvalidNsdAndVduCombinationException()
                    msg = _("No such combination of nsd and vdus were found ")
                    raise exc.HTTPBadRequest(explanation=msg)
        timestamp_path = dm.enable_diagnostics()
        return {
           'nsd_id': nsd_id,
           'status': 'started diagnostics on %s network service' % nsd_id,
           'diagnostics_path': timestamp_path
           }

    def delete_diagnostic(self, context, nsd):
        timestamp_path = self.ns_dict[nsd]['diagnostics_obj'].stop_diagnostics()
        return {'path': timestamp_path}

    def update_configuration(self, context, nsd_id, configuration):
        new_configuration = {'upgrade':''}
        vdu_name = configuration['configuration']['attributes']['vdu_name']
        cfg_engine = configuration['configuration']['attributes']['cfg_engine']
        #software = configuration['configuration']['attributes']['software']
        LOG.debug(_("configuration upgrade taking place for vdu %s"), vdu_name)
        service_details_for_nsd = self.get_service_by_nsd_id(context, nsd_id)
        vnf_manager = service_details_for_nsd['vnfm_id']
        vdus_in_nsd = service_details_for_nsd['vdus']
        if vdu_name not in [vdu.split(':')[1] for vdu in eval(vdus_in_nsd).keys()]:
            raise exceptions.NoVduforNsd()
        status = self.agent_mapping[vnf_manager].update_vdu_configuration(context, vdu_name, new_configuration, cfg_engine)
        updated_service = dict()
        updated_service['nsd_id'] = nsd_id
        updated_service['status'] = status
        return updated_service

    def get_configuration(self, context, service, **kwargs):
        configuration = self.get_service(context, service, **kwargs)
        return configuration

    def get_configurations(self,context, **kwargs):
        configuration = self.get_services(context, **kwargs)
        return configuration

    def generate_ns_info(self, data, nsdid):
        data['vnfm_conf'].update(data['nsd_template']['postconfigure'])
        data['vnfm_conf'].update(data['nsd_template']['preconfigure'])
        data['vnfm_conf'].update(data['nsd_template']['vnfds'])
	data['vnfm_conf']['nsd-id'] = nsdid
        data['vnfm_conf']['qos'] = data['qos']
        nsd_mappings = self._get_nsd_desc_dict()
        vnfd_mappings = self._get_vnfd_desc_dict()
        for key in nsd_mappings.keys():
            if key in data['vnfm_conf'].keys():
                new_key = nsd_mappings[key]
                if new_key != key:
                    data['vnfm_conf'][new_key] = data['vnfm_conf'][key]
                    del data['vnfm_conf'][key]
                if isinstance(data['vnfm_conf'][new_key], dict):
                    ns_info = self.ns_info_map(data['vnfm_conf'][new_key]) 
                    data['vnfm_conf'][new_key] = ns_info
        for vnf in data['vnfm_conf']['vnfds'].keys():
            for vdu in range(0,len(data['vnfm_conf']['vnfds'][vnf])):
                for key in vnfd_mappings.keys():
                    if key in data['vnfm_conf']['vnfds'][vnf][vdu].keys():
                        new_key = vnfd_mappings[key]
                        if new_key != key:
                            data['vnfm_conf']['vnfds'][vnf][vdu][new_key] = data['vnfm_conf']['vnfds'][vnf][vdu][key]
                            del data['vnfm_conf']['vnfds'][vnf][vdu][key]
                        if isinstance(data['vnfm_conf']['vnfds'][vnf][vdu][new_key], dict):
                            vnf_info = self.vnf_info_map(data['vnfm_conf']['vnfds'][vnf][vdu][new_key]) 
                            data['vnfm_conf']['vnfds'][vnf][vdu][new_key]= vnf_info
                for vnfInst in data['nsd_template']['vdus'].keys():
                    if data['vnfm_conf']['vnfds'][vnf][vdu]['name'] in vnfInst:
                        data['vnfm_conf']['vnfds'][vnf][vdu]['id'] = data['nsd_template']['vdus'][vnfInst]['id']
        xml_data = self._get_xml(data['vnfm_conf'])
        return xml_data

    def ns_info_map(self, info):
        nsd_mappings = self._get_nsd_desc_dict()
        for key in nsd_mappings.keys():
            if key in info.keys():
                new_key = nsd_mappings[key]
                if new_key != key:
                    info[new_key] = info[key]
                    del info[key]
                if isinstance(info[new_key], dict):
                    ns_info = self.ns_info_map(info[new_key])        
                    info[new_key] = ns_info
        return info

    def vnf_info_map(self, info):
        vnfd_mappings = self._get_vnfd_desc_dict()
        for key in vnfd_mappings.keys():
            if key in info.keys():
                new_key = vnfd_mappings[key]
                if new_key != key:
                    info[new_key] = info[key]
                    del info[key]
                if isinstance(info[new_key], dict):
                    vnf_info = self.vnf_info_map(info[new_key])
                    info[new_key] = vnf_info
        return info

    def _get_xml(self, data):
        xml = dicttoxml.dicttoxml(data, custom_root="ns", attr_type=False)
        return xml

    def _get_nsd_desc_dict(self):
        nsd_desc_dict = self.nsd_parser_obj.get_nsd_mapping_dict()
        rev_nsd_desc_dict = {v: k for k, v in nsd_desc_dict.items()}
        return rev_nsd_desc_dict

    def _get_vnfd_desc_dict(self):
        nsd_desc_dict = self.vnfd_parser_obj.get_vnfd_mapping_dict()
        rev_nsd_desc_dict = {v: k for k, v in nsd_desc_dict.items()}
        return rev_nsd_desc_dict
    
    def get_dumpxml(self, context, service, **kwargs):
        xml_data = self.get_network_service_xml(context, service)
        data = {}
        data[service] = xml_data
        return data

class VNFManagerAgentApi(object):
    """Plugin side of plugin to agent RPC API."""

    API_VERSION = '1.0'

    def __init__(self, topic, host, plugin):
        target = messaging.Target(topic=topic, version=self.API_VERSION)
        self.client = v_rpc.get_client(target)
        self.host = host
        self.plugin = plugin


    def configure_vdus(self, context, conf):
        cctxt = self.client.prepare(fanout=False)
        return cctxt.cast(
            context,
            'configure_vdus',
            conf=conf)
    def update_vdu_configuration(self, context, vdu_name, conf, cfg_engine='generic'):
        cctxt = self.client.prepare(fanout=False)
        return cctxt.cast(
            context,
            'update_vdu_configuration',
            vdu_name=vdu_name,
            configuration=conf)


    def postConfigure(self, context, conf):
        cctxt = self.client.prepare(fanout=False)
        return cctxt.cast(
            context,
            'postConfigure',
            conf=conf)
class VNFManagerCallbacks(object):
    RPC_API_VERSION = '1.0'

    def __init__(self, plugin):
        super(VNFManagerCallbacks, self).__init__()
        self.plugin = plugin

    def send_ack(self, context, vnfd, vdu, instance, status, nsd_id, gen_conf, event=None):
        if event:
            if event == 'init' and status == 'COMPLETE':
                self.plugin.build_acknowledge_list(context, vnfd, vdu, instance,
                                               status, nsd_id, gen_conf)
                LOG.debug(_('ACK received from VNF Manager: '
                        'Configuration complete for VNF %s'), instance)

            elif event == 'init' and status!= 'COMPLETE':
                self.plugin.build_acknowledge_list(context, vnfd, vdu, instance,
                                               status, nsd_id, gen_conf)
                LOG.debug(_('ACK received from VNF Manager: '
                        'Configuration complete for VNF %s'), instance)

            if status == 'COMPLETE' and event!= 'init':
                self.plugin.build_Ack(context, vnfd, vdu, instance, status, nsd_id, gen_conf, event)

                self.plugin.buildConfigAck(context, vnfd, vdu, instance,
                                       status, nsd_id, gen_conf)
                LOG.debug(_('Config event ACK received from VNF Manager: '
                        'Configuration complete for VNF %s'), instance)
            elif event!= 'init':
                self.plugin.build_Ack(context, vnfd, vdu, instance, status, nsd_id, gen_conf, event)

                self.plugin.buildConfigAck(context, vnfd, vdu, instance,
                                       status, nsd_id, gen_conf)
                LOG.debug(_('Config event ACK received from VNF Manager: '
                        'Confguration failed for VNF %s'), instance)
        else:
            if status == 'COMPLETE':
                self.plugin.build_acknowledge_list(context, vnfd, vdu, instance,
                                               status, nsd_id, gen_conf)
                LOG.debug(_('ACK received from VNF Manager: '
                        'Configuration complete for VNF %s'), instance)
            else:
                self.plugin.build_acknowledge_list(context, vnfd, vdu, instance,
                                               status, nsd_id, gen_conf)
                LOG.debug(_('ACK received from VNF Manager: '
                        'Confguration failed for VNF %s'), instance)

