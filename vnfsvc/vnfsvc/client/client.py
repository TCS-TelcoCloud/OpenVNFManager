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

from os import environ as env

from ceilometerclient import client as ceilometer
from heatclient import client as heat
from keystoneclient import exceptions as keystone_exceptions
from keystoneclient import discover as keystone_discover
from keystoneclient.v2_0 import client as keystone_v2
from keystoneclient.v3 import client as keystone_v3
from neutronclient.v2_0 import client as neutron
from novaclient import client as nova
from glanceclient import client as glance
from oslo_config import cfg
from vnfsvc.openstack.common.gettextutils import _
from vnfsvc.openstack.common import log as logging
from vnfsvc.client import utils

SERVICE_OPTS =[
    cfg.StrOpt('project_id', default='',
               help=_('project id used '
                      'by nova driver of service vm extension')),
    cfg.StrOpt('os_tenant_name',
               help=_(' Tenant name for connecting in admin context')),
    cfg.StrOpt('os_username',
               help=_(' User name for connecting in admin context')),
    cfg.StrOpt('os_password',
               help=_(' Password for connecting in admin context')),
    cfg.StrOpt('admin_auth_url', default='http://0.0.0.0:5000/v2.0',
               help=_('auth URL for connecting in admin context')),
    cfg.StrOpt('nova_url',
               default='http://127.0.0.1:8774',
               help=_('URL for connecting to nova')),
    cfg.StrOpt('neutron_url',
               default='http://127.0.0.1:9696',
               help=_('URL for connecting to neutron')),
    cfg.StrOpt('glance_url',
               default='http://127.0.0.1:9292',
               help=_('URL for connecting to glance')),
    cfg.FloatOpt("openstack_client_http_timeout", default=180.0,
                 help=_("HTTP timeout for any of OpenStack service in seconds")),
    cfg.BoolOpt("https_insecure", default=False,
                help=_("Use SSL for all OpenStack API interfaces")),
    cfg.StrOpt("https_cacert", default=None,
               help=_("Path to CA server cetrificate for SSL"))
]

cfg.CONF.register_opts(SERVICE_OPTS, group='service_credentials')

CONF = cfg.CONF.service_credentials


LOG = logging.getLogger(__name__)

def cached(func):
    """Cache client handles."""

    def wrapper(self, *args, **kwargs):
        key = '{0}{1}{2}'.format(func.__name__,
                                 str(args) if args else '',
                                 str(kwargs) if kwargs else '')

        #if key in self.cache:
        #    return self.cache[key]
        self.cache[key] = func(self, *args, **kwargs)
        return self.cache[key]

    return wrapper


def create_keystone_client(args):
    discover = keystone_discover.Discover(auth_url=args['auth_url'])
    for version_data in discover.version_data():
        version = version_data['version']
        if version[0] <= 2:
             return keystone_v2.Client(**args)
        elif version[0] == 3:
             return keystone_v3.Client(**args)


class Clients(object):

    def __init__(self):
       self.cache = {}

    def clear(self):
        """Remove all cached client handles."""
        self.cache = {}

    @cached
    def keystone(self):
        """ Returns keystone Client."""
        params = {
            'username': CONF.os_username,
            'password': CONF.os_password,
            'auth_url': CONF.admin_auth_url,
            'tenant_name': CONF.os_tenant_name
        }

        client = create_keystone_client(params);
        if client.auth_ref is None:
            client.authenticate()
        return client

    @cached
    def nova(self, context, admin='false', version='2'):
       """ Returns nova client."""
       """ Returns nova client."""
       if admin == 'false':
            endpoint = cfg.CONF.service_credentials.nova_url
            params = {
            'project_id': context.tenant,
            'auth_url': CONF.admin_auth_url,
            'service_type': 'compute'
            }
            client =  nova.Client(str(version), params)
            client.client.auth_token = context.auth_token
            client.client.auth_url = CONF.admin_auth_url
            client.client.tenant_id = context.tenant_id
            return client
       else:
            kc = self.keystone()
            compute_api_url = kc.service_catalog.url_for(service_type='compute')
            client =  nova.Client(version,
                                  auth_token=kc.auth_token,
                                  timeout=CONF.openstack_client_http_timeout,
                                  insecure=CONF.https_insecure,
                                  cacert=CONF.https_cacert)
            client.set_management_url(compute_api_url)
            return client

    @cached
    def neutron(self, context, admin='false'):
        """Instantiate a new neutron client.Client object."""
        if admin == 'false':
            endpoint = CONF.neutron_url
            params = {
            'endpoint_url': endpoint,
            'token': context.auth_token
            }
            return neutron.Client(**params)
        else:
            kc = self.keystone()
            network_api_url = kc.service_catalog.url_for(service_type='network')
            client = neutron.Client(token=kc.auth_token,
                                    endpoint_url=network_api_url,
                                    timeout=CONF.openstack_client_http_timeout,
                                    insecure=CONF.https_insecure)
                                   #cacert=CONF.https_cacert)

            return client

    @cached
    def generate_identity_headers(self, context, status='Confirmed'):
        return {
        'X-Auth-Token': getattr(context, 'auth_token', None),
        'X-User-Id': getattr(context, 'user', None),
        'X-Tenant-Id': getattr(context, 'tenant', None),
        'X-Identity-Status': status,
        }

    @cached
    def glance(self, context, version=1):
        """Instantiate a new glanceclient.Client object."""
        params = {}
        params['token'] = context.auth_token
        params['identity_headers'] = self.generate_identity_headers(context)
        endpoint = CONF.glance_url
        return glance.Client(str(version), endpoint, **params)

    @cached
    def ceilometer(self, version='2'):
        """ Returns ceilometer client."""
        kc = self.keystone()
        metering_api_url = kc.service_catalog.url_for(service_type='metering')
        auth_token = kc.auth_token
        if not hasattr(auth_token, '__call__'):
            # python-ceilometerclient requires auth_token to be a callable
            auth_token = lambda: kc.auth_token

        client = ceilometer.Client(version,
                                   endpoint=metering_api_url,
                                   token=auth_token,
                                   timeout=CONF.openstack_client_http_timeout,
                                   insecure=CONF.https_insecure,
                                   cacert=CONF.https_cacert)
        return client

class GlanceClient(Clients):

    def __init__(self, context):
        super(GlanceClient, self).__init__()
        self._client = super(GlanceClient, self).glance(context)

    def get_image(self, image_id):
        return self._client.images.get(image_id)

    def create_image(self, **kwargs):
        remove_keys = ['image', 'username', 'password']
        for key in remove_keys:
            del kwargs[key]
        image = self._client.images.create(**kwargs)
        return image

    def delete_image(self, image_id):
        self._client.images.delete(image_id)

class NovaClient(Clients):

    def __init__(self, context):
       super(NovaClient, self).__init__()
       self._client = super(NovaClient, self).nova(context)
       self._admin_client = super(NovaClient, self).nova(context, admin='true')

    @staticmethod
    def _safe_pop(d, name_list):
        res = None
        for name in name_list:
            if name in d:
                res = d.pop(name)
                break
        return res


    def list(self):
        """Lists the servers."""
        return self._client.servers.list()

    def create_vm(self, plugin, context, vm, vm_template):
        LOG.debug(_('vm %s'), vm)
        attrib = vm_template['attributes']
        name = self._safe_pop(attrib, ('name', ))
        image = self._safe_pop(attrib, ('image', 'imageRef'))
        flavor = self._safe_pop(attrib, ('flavor', 'flavorRef'))

        LOG.debug(_('service_context: %s'), vm.get('service_context', []))

        nics = []

        for sc_entry in vm['vnf']['service_contexts']:
            LOG.debug(_('sc_entry: %s'), sc_entry)

            nics.append({"net-id":sc_entry['network_id']})

        instance = self._client.servers.create(name, image, flavor, nics=nics)
        return instance.id

    def create(self, plugin, context, vnf):
        LOG.debug(_('vnf %s'), vnf)
        # flavor and image are specially treated by novaclient
        attrib = vnf['vnf_template']['attributes']
        name = self._safe_pop(attrib, ('name', ))
        if name is None:
            name = (__name__ + ':' + self.__class__.__name__ + '-' +
                    vnf['id'])
        image = self._safe_pop(attrib, ('image', 'imageRef'))
        flavor = self._safe_pop(attrib, ('flavor', 'flavorRef'))

        LOG.debug(_('service_context: %s'), vnf.get('service_context', []))
        nics = []
        user_data = vnf['user_data'];

        for sc_entry in vnf.get('service_context', []):
            LOG.debug(_('sc_entry: %s'), sc_entry)
            if sc_entry['port_id']:
                nics.append({"port-id":sc_entry['port_id']})
            if sc_entry['network_id']:
                nics.append({"net-id":sc_entry['network_id']})
        instance = self._client.servers.create(name, image, flavor, nics=nics, userdata=user_data)
        return instance.id


    def update_wait(self, plugin, context, vnf_id):
        # do nothing but checking if the instance exists at the moment
        self._client.servers.get(vnf_id)

    def create_flavor(self, **flavor_dict):
        name = flavor_dict['name']
        ram = flavor_dict['ram']
        vcpus = flavor_dict['vcpus']
        disk = flavor_dict['disk']
        return self._client.flavors.create(name, ram, vcpus, disk)

    def delete_flavor(self, flavor_id):
        return self._client.flavors.delete(flavor_id)

    def delete(self, vnf_id):
        return self._client.servers.delete(vnf_id)
       
    def find_instance(self,instance_name):
        return self._client.servers.find(name=str.lower(instance_name))

    def server_create(self, vm_details, index=0):
        name = vm_details['name']
        image = vm_details['image_created']
        flavor = vm_details['flavor']
        nics = vm_details['nics']
        num_instances = vm_details['num_instances']
        if 'userdata' in vm_details.keys():
            userdata = None
            user_data = vm_details['userdata']
            userdata = self.build_userdata(user_data)
        else:
            userdata = None
        if num_instances == 1:
            if index > 0:
                name = name + '_' + str(index)
            return self._client.servers.create(name, image, flavor, nics=nics, userdata=userdata, min_count=num_instances)
        else:
            instances_dict = []
            for i in range(index, index + num_instances):
                name = vm_details['name']+'_'+str(i)
                instances_dict.append(self._client.servers.create(name, image, flavor, nics=nics, userdata=userdata))
            return instances_dict

    def get_server(self, id):
        return self._client.servers.get(id)

    def get_image(self, id):
        self._client.images.get(id)

    def server_details(self,instance_id):
       instance = self._client.servers.get(instance_id)
       return instance

    def build_userdata(self,user_data):
        userdata = open(user_data, 'r').readlines()
        template = ''.join(userdata)
        return template

    def _find_hypervisor(self, hypervisor):
        """Get a hypervisor by name or ID."""
        return utils.find_resource(self._admin_client.hypervisors.list(), hypervisor, pattern='hypervisor_hostname')

    def check_host(self,hypervisor):
        """Display the details of the specified hypervisor."""
        hyper = self._find_hypervisor(hypervisor)
        return hyper

    def hypervisor_list(self, hostname):
        hypers = self._client.hypervisors.list()
        for hyper in hypers:
            if str(hyper.hypervisor_hostname) == hostname:
               return 'True'
            else:
               return 'False'
    def instance_get_all_by_host(self, hostname):
        """Returns list of instances on particular host."""
        search_opts = {'host': hostname, 'all_tenants': True}
        return self._with_flavor_and_image(self._client.servers.list(
            detailed=True,
            search_opts=search_opts))

    def _with_flavor_and_image(self, instances):
        flavor_cache = {}
        image_cache = {}
        for instance in instances:
            self._with_flavor(instance, flavor_cache)
            self._with_image(instance, image_cache)

        return instances

    def _with_flavor(self, instance, cache):
        fid = instance.flavor['id']
        if fid in cache:
            flavor = cache.get(fid)
        else:
            flavor = self._client.flavors.get(fid)
            cache[fid] = flavor

        attr_defaults = [('name', 'unknown-id-%s' % fid),
                         ('vcpus', 0), ('ram', 0), ('disk', 0),
                         ('ephemeral', 0)]

        for attr, default in attr_defaults:
            if not flavor:
                instance.flavor[attr] = default
                continue
            instance.flavor[attr] = getattr(flavor, attr, default)

    def _with_image(self, instance, cache):
        try:
            iid = instance.image['id']
        except TypeError:
            instance.image = None
            instance.kernel_id = None
            instance.ramdisk_id = None
            return

        if iid in cache:
            image = cache.get(iid)
        else:
            image = self._client.images.get(iid)
            cache[iid] = image

        attr_defaults = [('kernel_id', None),
                         ('ramdisk_id', None)]

        instance.image['name'] = (
            getattr(image, 'name') if image else 'unknown-id-%s' % iid)
        image_metadata = getattr(image, 'metadata', None)

        for attr, default in attr_defaults:
            ameta = image_metadata.get(attr) if image_metadata else default
            setattr(instance, attr, ameta)
  
    def get_server_interfaces(self, instance):
        return self._client.servers.interface_list(instance)


class NeutronClient(Clients):

    def __init__(self, context):
        super(NeutronClient, self).__init__()
        self._client = super(NeutronClient, self).neutron(context) 
        self._admin_client = super(NeutronClient, self).neutron(context, admin='true')

    def get_networks(self):
        """Returns all networks."""
        resp = self._client.list_networks()
        return resp.get('networks')

    def get_subnets(self):
        """Returns all subnets."""
        resp = self._client.list_subnets()
        return resp.get('subnets')

    def get_port(self, port_id):
        resp = self._client.show_port(port_id)
        return resp.get('port')

    def get_ports(self):
        resp = self._client.list_ports()
        return resp.get('ports')

    def create_port(self, port):
        return self._client.create_port(body=port)

    def update_port(self, port, body=None):
        return self._admin_client.update_port(port,body=body)

    def delete_port(self,port):
        return self._client.delete_port(port)
  
    def delete_network(self,network):
        return self._client.delete_network(network)

    def list_ports(self):
        return self._client.list_ports()

    def list_router_ports(self,device_id):
        return self._client.list_ports(device_id=device_id)

    def delete_router(self, router):
        return self._client.delete_router(router)


    def create_device_template(self, device_template):
        return self._client.create_device_template(body=device_template)

    def create_device(self, device):
        return self._client.create_device(body=device)

    def mgmt_address(self, device, instance_ips):
        for sc_entry in device['service_context']:
            if sc_entry['role'] == constants.ROLE_MGMT :
                #network_id = sc_entry['network_id']
                port_id = sc_entry['port_id']
        #ports = self.get_ports()
        #for mgmt_port in ports:
        #    if mgmt_port['network_id'] == network_id and mgmt_port['fixed_ips'][0]['ip_address'] in instance_ips:
        #        port_id = mgmt_port['id']
        port = self._client.show_port(port_id).get('port')
        if not port:
            return
        mgmt_address = port['fixed_ips'][0]
        mgmt_address['network_id'] = port['network_id']
        mgmt_address['port_id'] = port['id']
        mgmt_address['mac_address'] = port['mac_address']

        return jsonutils.dumps(mgmt_address)

    def get_device(self, device_id):
        resp = self._client.show_device(device_id)
        return resp.get('device')

    def get_device_template(self, device_template_id):
        resp = self._client.show_device_template(device_template_id)
        return resp.get('device_template')

    def get_device_templates(self):
        resp = self._client.list_device_templates()
        return resp.get('device_templates')

    def delete_device_template(self, device_template_id):
        self._client.delete_device_template(device_template_id)

    def delete_device(self, device_id):
        self._client.delete_device(device_id)

    def get_router(self, router):
        return self._client.list_routers(name=router).get('routers')

    def add_interface_router(self, router_id, subnet_id):
        return self._client.add_interface_router(router_id, {'subnet_id':subnet_id})

    def remove_interface_router(self, router, body=None):
        return self._client.remove_interface_router(router, body=body)
    
    def show_subnet(self, subnet_id):
        return self._client.show_subnet(subnet_id)

    # def create_port(self, net_id, subnet_id, ip):
    #     port_dict = {'port':{}}
    #     port_dict['port']['network_id'] = net_id
    #     port_dict['port']['fixed_ips'] = [{
    #         'subnet_id': subnet_id,
    #         'ip_address': ip
    #     }]
    #     port_dict['port']['admin_state_up'] = True
    #     return self._client.create_port(port_dict)



class CeilometerClient(Clients):

    def __init__(self):
        super(CeilometerClient, self).__init__()
        self._client = super(CeilometerClient, self).ceilometer()

    def query_samples(self, meter_name, timestamp1, timestamp2):   #,period):   #, resource):
        """Returns the statistics of resource."""

        #request_body = { 'field': 'resource_id', 'value' : resource,
        #                 'type': '', 'op': 'eq'}
        request_body1 = { 'field': 'timestamp', 'value' : timestamp1,
                         'type': '', 'op': 'gt'}
        request_body2 = { 'field': 'timestamp', 'value' : timestamp2,
                         'type': '', 'op': 'lt'}

        #meter = 'cpu_util'
        #api_args = {'meter_name': meter,
        #            'groupby': ['resource_id']}
        return self._client.samples.list(meter_name=meter_name,
                                            q=[request_body1,request_body2])
                                            #groupby=groupby)
                                            #q=[request_body] )

#meter_name=meter_name,
                                            #q=[request_body]
                                            #period=period,
                                            #groupby)

    def query_statistics(self, meter_name, period, groupby=[]):   #,period):   #, resource):
        """Returns the statistics of resource."""

        #request_body = { 'field': 'resource_id', 'value' : resource,
        #                 'type': '', 'op': 'eq'}
        #meter = 'cpu_util'
        #api_args = {'meter_name': meter,
        #            'groupby': ['resource_id']}
        return self._client.statistics.list(meter_name=meter_name,
                                            period=period,
                                            groupby=groupby)
                                            #q=[request_body] )

#meter_name=meter_name,
                                            #q=[request_body]
                                            #period=period,
                                            #groupby)
