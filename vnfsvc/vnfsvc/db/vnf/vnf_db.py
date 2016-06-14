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

import uuid
import ast

import sqlalchemy as sa
from sqlalchemy import orm
from sqlalchemy.orm import exc as orm_exc

from vnfsvc.api.v2 import attributes
from vnfsvc.common import exceptions
from vnfsvc.db import common_db_mixin as base_db
from vnfsvc.db import model_base
from vnfsvc import manager
from vnfsvc.openstack.common import jsonutils
from vnfsvc.openstack.common import log as logging
from vnfsvc import constants
from vnfsvc.openstack.common import uuidutils
from vnfsvc.openstack.common.gettextutils import _
from vnfsvc.api.v2 import vnf

LOG = logging.getLogger(__name__)
_ACTIVE_UPDATE = (constants.ACTIVE, constants.PENDING_UPDATE)

service_db_dict={}
class HasTenant(object):
    """Tenant mixin, add to subclasses that have a tenant."""

    tenant_id = sa.Column(sa.String(255))


class HasId(object):
    """id mixin, add to subclasses that have an id."""

    id = sa.Column(sa.String(36),
                   primary_key=True,
                   default=uuidutils.generate_uuid)


class NetworkService(model_base.BASEV2):
    """Represents binding of Network service details
    """
    id = sa.Column(sa.String(36), primary_key=True, nullable=False)
    vnfm_id = sa.Column(sa.String(4000),nullable=False)
    vnfm_host = sa.Column(sa.String(4000),nullable=True)
    vdus = sa.Column(sa.String(4000), nullable=False)
    networks = sa.Column(sa.String(4000), nullable=False)
    subnets = sa.Column(sa.String(4000), nullable=False)
    router = sa.Column(sa.String(4000), nullable=False)
    service_type = sa.Column(sa.String(36), nullable=False)
    puppet_id = sa.Column(sa.String(36), nullable=False)
    status = sa.Column(sa.String(36), nullable=False)

    template_id = sa.Column(sa.String(36), nullable=False)
    flavour = sa.Column(sa.String(36), nullable=False)
    xml = sa.Column('xml',sa.Text(4000),nullable=False)



class Vdu(model_base.BASEV2):
    """Represents VDU details
    """
    id = sa.Column(sa.String(36), primary_key=True,nullable=False)
    instances = sa.Column(sa.String(4000),nullable=False)
    flavor = sa.Column(sa.String(36),nullable=False)
    image = sa.Column(sa.String(36),nullable=False)
    lf_event = sa.Column(sa.String(4000),nullable=False)
    userdata = sa.Column(sa.String(4000),nullable=True)

class ServiceTemplate(model_base.BASEV2):
    """Represents template details
    """
    id = sa.Column(sa.String(36), primary_key=True,nullable=False)
    service_type = sa.Column(sa.String(36),nullable=False)
    template_path = sa.Column(sa.String(4000),nullable=False)
    parser = sa.Column(sa.String(36),nullable=False)
    version = sa.Column(sa.String(36),nullable=False)
    status = sa.Column(sa.String(36), nullable=False)
    specs = sa.Column(sa.String(36), nullable=False)


class VduConfiguration(model_base.BASEV2):
    """Represents VDU configuration details
    """
    template_id = sa.Column(sa.String(36), sa.ForeignKey('servicetemplates.id'),primary_key=True,nullable=False)
    vdu_name = sa.Column(sa.String(36), primary_key=True, nullable=False)
    flavour = sa.Column(sa.String(36), primary_key=True, nullable=False)
    image_id = sa.Column(sa.String(36), nullable=False)
    vdu_flavor = sa.Column(sa.String(36), nullable=False)
    Configuration = sa.Column(sa.String(4000),nullable=False)


###########################################################################

class NetworkServicePluginDb(base_db.CommonDbMixin):

    @property
    def _core_plugin(self):
        return manager.VnfsvcManager.get_plugin()


    def subnet_id_to_network_id(self, context, subnet_id):
        subnet = self._core_plugin.get_subnet(context, subnet_id)
        return subnet['network_id']


    def __init__(self):
        super(NetworkServicePluginDb, self).__init__()


    def _make_service_dict(self, service_db, fields=None):
        LOG.debug(_('service_db %s'), service_db)
        res = {}
        key_list = ('id', 'vnfm_id', 'vdus', 'networks', 'subnets','router','service_type','status')
        res.update((key, service_db[key]) for key in key_list)
        return self._fields(res, fields)



    def _make_template_dict(self, template_db, fields=None, single=False):
        LOG.debug(_('template_db %s'), template_db)
        res = {}
        if single:
            key_list = ('id', 'parser', 'version', 'service_type', 'template_path', 'status', 'specs')
        else:
            key_list = ('id', 'parser', 'version', 'service_type', 'template_path', 'status')
        res.update((key, template_db[key]) for key in key_list)
        return self._fields(res, fields)
    def _make_vdu_dict(self, vdu_info, fields=None):
        LOG.debug(_('vdu_info %s'), vdu_info)
        res = {}
        key_list = ('vdu_flavor', 'image_id')

        res.update((key,vdu_info[key]) for key in key_list)
        return self._fields(res, fields)

    def _make_service_dict_hosts(self, service_db, fields=None):
        LOG.debug(_('service_db %s'), service_db)
        res = {}
        key_list = ('host_ip', 'ssh_key')
        res.update((key, service_db[key]) for key in key_list)
        return self._fields(res, fields)


    def get_status_update(self, context, activate, enable):
        """This method updates the DB with given Status parameter"""
        template_db = self._model_query(context, ServiceTemplate).filter(ServiceTemplate.id == activate['activate']['template_id'])
        template_dict = template_db[0].__dict__
        service_type = template_dict['service_type']

        if service_type != activate['activate']['name']:
            msg = 'Service name ' + activate['activate']['name'] + ' does not match with the template service type'
            raise exceptions.StatusException(service=msg)
        template_db.update({'status':enable})
        template = self.get_template_model(context, template_id=activate['activate']['template_id'], fields = None)
        return template

    # ADDED BY ANIRUDH
    def _make_driver_configuration_dict(self, driver_configuration, fields=None):
        LOG.debug(_('driver configuration databse %s'), driver_configuration)
        res = {#'id': driver_configuration['template_id'],
               'catalog': driver_configuration['Configuration'],
               'flavour': driver_configuration['flavour'],
               'vdu_name': driver_configuration['vdu_name']}
        return self._fields(res, fields)
        # ENDS HERE

    def get_manager_info(self, context):
        services = self._model_query(context, NetworkService).all()
        ns_vnfm_dict = {}
        for service in services:
            ns_vnfm_dict[service.vnfm_id] = []
            vdus = ast.literal_eval(service.vdus)
            for vdu_name, id in vdus.iteritems():
                vdu = self._model_query(context, Vdu).filter(Vdu.id == id).all()[0]
                ns_vnfm_dict[service.vnfm_id].extend(vdu.instances.split(","))
        return ns_vnfm_dict

    def get_service_by_nsd_id(self, context, nsd_id):
        try:
            services = self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).first()
            if services:
                return self._make_service_dict(services)
            else:
                return ''
        except orm_exc.NoResultFound:
            raise exceptions.NotFound()
        except Exception:
            raise

    def get_service_driver_details_by_nsd_id(self, context, nsd_id, fields=None):
        service = self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).first()
        template_id = self._make_service_dict(service)['template_id']
        flavour = self._make_service_dict(service)['flavour']
        filters = {'template_id': [template_id], 'flavour': [flavour]}
        return {'driver_catalog': self._get_collection(context, VduConfiguration, self._make_driver_configuration_dict,
                                    filters=filters, fields=fields), 'id': nsd_id}

    def get_lfevents(self, context, nsd_id, vdu):
        service = self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).all()
        vdus_dict = eval(service[0].vdus)
        for vdus in vdus_dict:
            if vdus.find(vdu) >=0:
               vdu_id = vdus_dict[vdus]
        vdu_info = self._model_query(context, Vdu).filter(Vdu.id == vdu_id).all()[0]
        lf_event = vdu_info.lf_event
        return eval(lf_event)

    def get_instances_info(self,context):
        instances_list = []
        services = self._model_query(context, NetworkService).all()
        for service in services:
            vdus = ast.literal_eval(service.vdus)
            for vdu_name, id in vdus.iteritems():
                vdu = self._model_query(context, Vdu).filter(Vdu.id == id).all()[0]
                instances_list.append(vdu.instances.split(","))
        print instances_list

    def populate_vdu_details(self, context, nsd, vnfds):
        vdus = dict()
        with context.session.begin(subtransactions=True):
            for vnf in vnfds:
                for vdu in nsd['vdus']:
                    for vdu_name in vnfds[vnf]['vdus']:
                        if vdu_name in vdu:
                            vdus[vdu] = nsd['vdus'][vdu]['id']
                            vdu_userdata = vnfds[vnf]['vdus'][vdu_name]['vm_details']['userdata']
                            vdu_db = Vdu(id=vdus[vdu], instances='', flavor='', image='', lf_event='',
                                         userdata=vdu_userdata)
                            context.session.add(vdu_db)
        return vdus

    def update_vdu_details(self, context, flavor_id, image_id, vdu_id):
        with context.session.begin(subtransactions=True):
            vdu = self._model_query(context, Vdu).filter(Vdu.id==vdu_id).first()
            if vdu:
                vdu.update({
                    'flavor': flavor_id,
                    'image': image_id
                    })
            else:
                raise exceptions.NoSuchVDUException()
            context.session.add(vdu)

    def update_vdu_instance_details(self, context,instance_id, vdu_id):
        with context.session.begin(subtransactions=True):
            vdu = self._model_query(context, Vdu).filter(Vdu.id==vdu_id).first()
            if vdu:
                if vdu.instances!='':
                    instances = vdu.instances+','+instance_id
                else:
                    instances = instance_id
                vdu.update({
                    'instances': instances
                    })
            else:
                raise exceptions.NoSuchVDUException()
            context.session.add(vdu)

    def update_vdu_lf_event(self, context, vdus, lf_event):
        vdus = eval(vdus)
        with context.session.begin(subtransactions=True):
           for vnfd in lf_event:
             for vdu_details in lf_event[vnfd]:
                 for vdu_name in vdus:
                     if vdu_name.find(vdu_details) >= 0:
                        vdu_id = vdus[vdu_name]
                        break
                 vdu = self._model_query(context, Vdu).filter(Vdu.id==vdu_id).first()
                 if vdu:
                    vdu.update({
                        'lf_event': str(lf_event[vnfd][vdu_name.split(':')[1]]['postconfigure']['unformat']['lifecycle_events'])
                        #'lf_event': str(lf_event[vdu_details])
                        })
                 else:
                     raise exceptions.NoSuchVDUException()
                 context.session.add(vdu)

    def update_nsd_status(self, context, nsd_id, status):
        with context.session.begin(subtransactions=True):
            nsd = self._model_query(context, NetworkService).filter(NetworkService.id==nsd_id).first()
            if nsd:
                nsd.update({
                    'status': status
                    })
            else:
                raise exceptions.NoSuchNSDException()
            context.session.add(nsd)
 

    def create_service_model(self, context, **db_dict):
        nsd = db_dict['nsd']
        vnfds = db_dict['vnfds']

        with context.session.begin(subtransactions=True):
            id = db_dict['id'] 
            vnfm_id = db_dict['vnfm_id']
            lf_event = db_dict['lf_event'][id]
            networks = str(db_dict['networks'])
            subnets = str(db_dict['subnets'])
            router = nsd['preconfigure']['router']
            for network in router.keys():
                if_name = router[network]['if_name']
                router[network]['id'] = nsd['router'][network][if_name]['id']
            service_type = db_dict['service']['name']
            vdus = str(self.populate_vdu_details(context, nsd,vnfds))
            lf_event = str(self.update_vdu_lf_event(context, vdus, lf_event))
            puppet = nsd.get('puppet-master', None)
            if puppet:
                puppet_id = puppet.get('instance_id', '')
            else:
                puppet_id = ''
            status = db_dict['status']
            xml = db_dict['xml']

            service_db = NetworkService(id=id, vnfm_id=vnfm_id, networks=networks, subnets=subnets, 
                    vdus=vdus, router=str(router), service_type=service_type, puppet_id=puppet_id, status=status,template_id=db_dict['template_id'], flavour = db_dict['flavour'], xml=xml) 
            context.session.add(service_db)
            return self._make_service_dict(service_db)

    def delete_service_model(self, context, nsd_id):
        instances_list=[]
        try:
                service_db = self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).all()
                service_db_dict['service_db']=service_db
                service_dict = service_db[0].__dict__
                vduid_list = ast.literal_eval(service_dict['vdus']).values()
                for vdu_id in range(len(vduid_list)):
                   instances = self._model_query(context, Vdu).filter(Vdu.id == vduid_list[vdu_id]).all()
                   instances_list.append(instances)
                service_db_dict['instances']=instances_list

        except Exception as e:
            return None
        return service_db_dict



    def delete_db_dict(self, context, nsd_id):
        service_db = self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).all()
        service_dict = service_db[0].__dict__
        vduid_list = ast.literal_eval(service_dict['vdus']).values()
        for vdu_id in range(len(vduid_list)):
           instances = self._model_query(context, Vdu).filter(Vdu.id == vduid_list[vdu_id]).all()
           self._model_query(context, Vdu).filter(Vdu.id == vduid_list[vdu_id]).delete()
        self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).delete()


    def get_service_model(self, context, nsd_id, fields=None):
        try:
            service_db = self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).one()
            return self._make_service_dict(service_db, fields)
        except Exception:
            return {}

    def get_all_services(self, context, filters=None, fields=None):
        return self._get_collection(context, NetworkService, self._make_service_dict,
                                    filters=filters, fields=fields)

    def get_instance_ids(self, context, vdu_id):
        try:
            with context.session.begin(subtransactions=True):
                vdu = self._model_query(context, Vdu).filter(Vdu.id==vdu_id).first()
        except Exception as e:
            return None
        return vdu.instances


    def get_network_service_status(self, context, nsd_id):
        try:
            with context.session.begin(subtransactions=True):
                ns = self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).first()
        except Exception as e:
            return None
        return ns.status

    
    def get_network_service_details(self, context, nsd_id):
        try:
            with context.session.begin(subtransactions=True):
                ns = self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).first()
        except Exception as e:
            return None
        return ns

    def get_vdu_instance_info(self, context, vdu):
        return self._model_query(context, Vdu).filter(Vdu.id == vdu).all()[0]



    def get_vdu_userdata(self, context, nsd_id, vdu_name):
        try:
            with context.session.begin(subtransactions=True):
                service = self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).first()
                if service:
                    vdus = eval(service['vdus'])
                    for vdu in vdus:
                        if vdu_name in vdu:
                            vdu_db = self._model_query(context, Vdu).filter(Vdu.id==vdus[vdu]).first()
                            return vdu_db.userdata
        except Exception as e:
            return None
        return ''


    def populate_vdu_configuration(self, context, templateid, vdu_dict):
        with context.session.begin(subtransactions=True):
            for vnf in vdu_dict:
                for flavour in vdu_dict[vnf]['conf']['flavours']:
                    for vdu in vdu_dict[vnf]['conf']['flavours'][flavour]['vdus']:
                        vdu_config_db = VduConfiguration(template_id=templateid, vdu_name=vdu, flavour=flavour, image_id=str(vdu_dict[vnf]['conf']['flavours'][flavour]['vdus'][vdu]['image']), vdu_flavor=str(vdu_dict[vnf]['conf']['flavours'][flavour]['vdus'][vdu]['flavor']), Configuration=str(vdu_dict[vnf]['conf']['flavours'][flavour]['vdus'][vdu]['vdu-config']))
                        context.session.add(vdu_config_db)

    def populate_template_details(self, context, template_dict):
        with context.session.begin(subtransactions=True):
            template_db = ServiceTemplate(id=template_dict['id'],parser= template_dict['parser'], version= template_dict['version'], service_type=template_dict['service_type'], template_path=str(template_dict['template_path']),status=str(template_dict['status']),specs=str(template_dict['specs']))
            context.session.add(template_db)
            return self._make_template_dict(template_db)

    def get_service_name(self, context, service_name):
        try:
            with context.session.begin(subtransactions=True):
                service = self._model_query(context, ServiceTemplate).filter(ServiceTemplate.service_type == service_name).first()
        except Exception as e:
            return None
        return service

    def get_template_id(self, context, service_name):
        try:
            with context.session.begin(subtransactions=True):
                service = self._model_query(context, ServiceTemplate).filter(ServiceTemplate.service_type == service_name).first()
        except Exception as e:
            return None
        return service.id, service.parser, service.version

    def get_vdu_details(self, context, template_id, vdu, flavour):
        try:
            with context.session.begin(subtransactions=True):
                vdu_data = self._model_query(context, VduConfiguration).filter(VduConfiguration.template_id == template_id, VduConfiguration.vdu_name == vdu, VduConfiguration.flavour == flavour).first()
        except Exception as e:
            return None
        return vdu_data

    def delete_template_info(self, context, template_id):
        self._model_query(context, VduConfiguration).filter(VduConfiguration.template_id == template_id).delete()
        self._model_query(context, ServiceTemplate).filter(ServiceTemplate.id == template_id).delete()

    def get_flavor_list(self, context, template_id):
        try:
            with context.session.begin(subtransactions=True):
                vdu_info = self._model_query(context, VduConfiguration).filter(VduConfiguration.template_id == template_id).all()
                flavor_list = []
                vdu_list = []
                for vdu in vdu_info:
                    print vdu
                    vdu_list.append(vdu)
                for vdu in vdu_info:
                    if vdu.vdu_flavor not in flavor_list:
                        flavor_list.append(vdu.vdu_flavor)
                return flavor_list
        except Exception as e:
            return None

    def get_image_list(self, context, template_id):
        try:
            with context.session.begin(subtransactions=True):
                vdu_info = self._model_query(context, VduConfiguration).filter(VduConfiguration.template_id == template_id).all()
                image_list = []
                for element in range(0, len(vdu_info)):
                    if vdu_info[element].image_id not in image_list:
                        image_list.append(vdu_info[element].image_id)
                return image_list
        except Exception as e:
            return None

    def get_all_template(self, context, filters=None, fields=None):
        return self._get_collection(context, ServiceTemplate, self._make_template_dict,
                                    filters=filters, fields=fields)


    def get_template_model(self, context, template_id=None, template_name=None, fields=None):
        vdu_dict_new = {}
        template_db = {}
        try:
            if template_id:
                template_db = self._model_query(context, ServiceTemplate).filter(ServiceTemplate.id == template).one()
            if template_name:
                template_db = self._model_query(context, ServiceTemplate).filter(ServiceTemplate.service_type == template_name).one()

            template = template_db['id']

            vdu_info = self._model_query(context, VduConfiguration).filter(VduConfiguration.template_id == template).all()
            template_dict = self._make_template_dict(template_db, fields, single=True)
            flavors = []
            images = []
            for vdu in vdu_info:
                vdu_dict = self._make_vdu_dict(vdu ,fields)
                if vdu_dict['vdu_flavor'] not in flavors:
                   flavors.append(vdu_dict['vdu_flavor'])
                if vdu_dict['image_id'] not in images:
                   images.append(vdu_dict['image_id'])
            vdu_dict_new['flavor_details'] = flavors
            vdu_dict_new['image_details'] = images
            template_dict.update(vdu_dict_new)
            return template_dict
        except Exception:
            return {}


    def update_nsd_info(self, context, nsd_id, xml_info):
        with context.session.begin(subtransactions=True):
            nsd = self._model_query(context, NetworkService).filter(NetworkService.id==nsd_id).first()
            if nsd:
                nsd.update({
                    'xml': xml_info
                    })
            else:
                raise exceptions.NoSuchNSDException()
            context.session.add(nsd)

    def get_network_service_xml(self, context, nsd_id):
        try:
            with context.session.begin(subtransactions=True):
                ns = self._model_query(context, NetworkService).filter(NetworkService.id == nsd_id).first()
        except Exception as e:
            return None
        return ns.xml


    def update_ns_vnfm_host(self, context, nsd_id, vnfm_host):
        with context.session.begin(subtransactions=True):
            nsd = self._model_query(context, NetworkService).filter(NetworkService.id==nsd_id).first()
            if nsd:
                nsd.update({
                    'vnfm_host': vnfm_host
                    })
            else:
                raise exceptions.NoSuchNSDException()
            context.session.add(nsd)
