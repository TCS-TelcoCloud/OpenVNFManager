# Copyright (c) 2014 Tata Consultancy Services Limited(TCSL). 
# Copyright 2012 OpenStack Foundation
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

import os
import sys
import threading
import time
import yaml
import json
import importlib
import itertools
import eventlet
import datetime
eventlet.monkey_patch()

from stevedore import driver
from oslo_config import cfg
import oslo_messaging as messaging
from oslo_utils import timeutils

from vnfmanager import config
from vnfmanager import context
from vnfmanager import manager
from vnfmanager.openstack.common import loopingcall
from vnfmanager.openstack.common import service
from vnfmanager.openstack.common import log as logging
from vnfmanager.openstack.common.gettextutils import _

from vnfmanager.agent import rpc as agent_rpc
from vnfmanager.common import config as common_config
from vnfmanager.common import rpc as v_rpc
from vnfmanager.common import topics
from vnfmanager import service as vnfsvc_service
from vnfmanager.openstack.common import uuidutils as uuid
from vnfmanager.openstack.common import importutils
from vnfmanager.common import exceptions

LOG = logging.getLogger(__name__)

command_opts = [cfg.StrOpt('uuid', default=None, 
                help='VNF manager identifier'),
                cfg.StrOpt('vnfm-conf-dir', default=None,  
                help='VNF manager identifier')]
cfg.CONF.register_cli_opts(command_opts)

AGENT_VNF_MANAGER = 'VNF manager agent'
launchd_threads_info = dict()

class ImplThread(threading.Thread):
    def __init__(self, target, condition, *args, **kwargs):
        global launchd_threads_info
        self._id = kwargs['_id']
        self._condition = condition
        self._target = target
        self._args = args
        self._thr_info = launchd_threads_info
        threading.Thread.__init__(self)

    def run(self):
        try:
           self.return_vals = self._target(*self._args)
        except Exception:
           self.return_vals = 'Error'
        self._condition.acquire()
        self._thr_info[self._id]['result'] = self.return_vals
        self._condition.notify()
        self._condition.release()

class VNFManager(manager.Manager):

    def __init__(self, host=None):
        super(VNFManager, self).__init__(host=host)
        self.vplugin_rpc = VNFPluginCallbacks(topics.PLUGIN,
                                               cfg.CONF.host)
        self.needs_resync_reasons = []
        self.drv_conf = dict()
        self.conf = cfg.CONF
        self.ctx = context.get_admin_context_without_session()
        self.ns_config = dict()
        self.nsd_id = self.conf.vnfm_conf_d['service']['nsd_id']
        self._condition = threading.Condition()
        monitor_daemon = threading.Thread(target=self.monitor_thread_pool)
        monitor_daemon.setDaemon(True)
        LOG.warn(_("Waiter Daemon Starting"))
        self.configure_vdus(self.ctx, self.conf.vnfm_conf_d)
        monitor_daemon.start()

    def monitor_thread_pool(self, thread_info=None, condition=None):
        global launchd_threads_info
        if thread_info is None:
            thread_info = launchd_threads_info
        if condition is None:
            condition = self._condition
        while True:
            condition.acquire()
            for each_thread in iter(thread_info.keys()):
                if 'policy' in thread_info[each_thread].keys():
                    pass
                elif 'result' in thread_info[each_thread].keys():
                    LOG.debug(_("Worker Thread # for VNF configuration Ending"), thread_info[each_thread])
                    LOG.debug(_("%s"), thread_info)
                    status = 'ERROR' if 'ERROR' in str(thread_info[each_thread]['result']) else 'COMPLETE'
                    if ('event' in thread_info[each_thread]) and thread_info[each_thread]['event']:
                        self.vplugin_rpc.send_ack(self.ctx,
                                               thread_info[each_thread]['vnfd'],
                                               thread_info[each_thread]['vdu'],
                                               thread_info[each_thread]['vm_name'],
                                               status,
                                               self.nsd_id, thread_info[each_thread]['conf'],event=thread_info[each_thread]['event'])
                    else:
                        self.vplugin_rpc.send_ack(self.ctx,
                                               thread_info[each_thread]['vnfd'],
                                               thread_info[each_thread]['vdu'],
                                               thread_info[each_thread]['vm_name'],
                                               status,
                                               self.nsd_id, self.ns_config)
                    if status == "COMPLETE":
                        self.drv_conf[thread_info[each_thread]['vdu']]['COMPLETE'].append(thread_info[each_thread]['vm_name'])
                    if thread_info[each_thread]['thread_obj'].isAlive():
                        thread_info[each_thread]['thread_obj'].kill()
                    del(thread_info[each_thread])
            condition.wait()
            condition.release()

    def _extract_drivers(self, vnfm_conf):
        vnfds = list(set(vnfm_conf.keys()) - set(['id','nsd_id','fg']))
        vnfd_details = dict()
        for vnfd in vnfds:
            for vdu in range(0,len(vnfm_conf[vnfd])):
                vdu_name = vnfm_conf[vnfd][vdu]['name']
                if vdu_name not in self.drv_conf.keys():
                    vnfd_details[vdu_name] = dict()
                    vnfd_details[vdu_name]['_instances'] = vnfm_conf[vnfd][vdu]['instance_list']
                    for event in vnfm_conf[vnfd][vdu]['lifecycle_events']:
                       vnfd_details[vdu_name][event]={}
                       if 'driver' in vnfm_conf[vnfd][vdu]['lifecycle_events'][event] and vnfm_conf[vnfd][vdu]['lifecycle_events'][event]['driver'] is not '':
                           vnfd_details[vdu_name][event]['_driver'] = vnfm_conf[vnfd][vdu]['lifecycle_events'][event]['driver']
                       else:
                           vnfd_details[vdu_name][event]['_driver'] = None
                    vnfd_details[vdu_name]['_lc_events'] = vnfm_conf[vnfd][vdu]['lifecycle_events']
                    vnfd_details[vdu_name]['_vnfd'] = vnfd
                    vnfd_details[vdu_name]['idx'] = vdu
                    vnfd_details[vdu_name]['COMPLETE'] = list()
                    vnfd_details[vdu_name]['_username'] = vnfm_conf[vnfd][vdu]['vm_details']['image_details']['username']
                    vnfd_details[vdu_name]['_password'] = vnfm_conf[vnfd][vdu]['vm_details']['image_details']['password']
                    vnfd_details[vdu_name]['_mgmt_ips'] = vnfm_conf[vnfd][vdu]['mgmt-ip']
        return vnfd_details

    def update_drv_conf(self, vdu_name, configuration):
        lc_events = configuration.keys()
        if lc_events[0] in self.drv_conf[vdu_name]['_lc_events'].keys():
           self.drv_conf[vdu_name]['_lc_events'][lc_events[0]] = configuration[lc_events[0]]

    def update_vdu_configuration(self, context, vdu_name, configuration):
        try:
            vdu_name = vdu_name
            method = configuration.keys()[0]
            arguments = configuration.values()[0]
            """if configuration.keys()[0] in generic_configuration_events:
                self._configure_vdu(vdu_name, configuration_event, update=True)
            else:
                method = configuration_event 
                self._configure_vdu(vdu_name, configuration_event, method, update=True)"""
            self._configure_vdu(vdu_name, method, arguments ,update=True)
            status = 'UPDATED'
        except Exception:
            status = 'UPDATE FAILED'
        finally:
            return status

    def _generate_config_string(self, cfg_engine):
        commands = ["puppet agent --enable","puppet agent -t"]
        str1 = ''
        for command in commands:
            str1 = str1+'<'+'action'+'>'+command+'<'+'/'+'action'+'>'
        config_string = '<'+cfg_engine+'>'+str1+'<'+'/'+cfg_engine+'>'
        
        return config_string
    

    def _populate_vnfd_drivers(self, drv_conf):
        vnfd_drv_cls_path={}
        for event in drv_conf['_lc_events']:
         vnfd_drv_cls_path[event] = drv_conf[event]['_driver'] 
        username = drv_conf['_username']
        password = drv_conf['_password']
        lf_events = drv_conf['_lc_events']
        try:
            for event  in drv_conf['_lc_events']:
             kwargs = {'conf':self.ns_config, 'username': username, 'password' : password}

             drv_conf[event]['_drv_obj'] = importutils.import_object(vnfd_drv_cls_path[event],**kwargs)
        except Exception:
            LOG.warn(_("%s driver not Loaded"), vnfd_drv_cls_path[event])
            raise


    def _configure_service(self, vdu, instance, mgmt_ip, method, arguments,event):
        status = "ERROR"
        try:
            LOG.debug(_("Configuration of VNF being carried out on VDU:%s with IP:%s"), vdu, mgmt_ip)
            configurator = getattr(vdu[event]['_drv_obj'], event)
            drv_args = dict({'conf': arguments, 'mgmt-ip': mgmt_ip})
            status = configurator(**drv_args)
        except exceptions.DriverException or Exception:
            LOG.exception(_("Configuration of VNF Failed!!"))
        finally:
            return status

    def _get_vdu_from_conf(self, conf):
        return conf[conf.keys()[0]][0]['name']


    def configure_vdus(self, context, conf):
        curr_drv_conf = dict()
        vnfds = list(set(conf['service'].keys()) - set(['nsd_id' , 'id', 'fg']))
        for vnfd in vnfds:
            if vnfd not in self.ns_config.keys():
                self.ns_config[vnfd]= list()
            self.ns_config[vnfd].extend(conf['service'][vnfd])

        curr_drv_conf = self._extract_drivers(conf['service'])

        if curr_drv_conf:
            for vdu in curr_drv_conf:
                if not curr_drv_conf[vdu]['init']['_driver']:
                   self.drv_conf.update(curr_drv_conf)
                   continue
                self._populate_vnfd_drivers(curr_drv_conf[vdu])
                self.drv_conf.update(curr_drv_conf)

        LOG.info(self.ns_config)
        for vdu_name in curr_drv_conf:
            if not curr_drv_conf[vdu_name]['init']['_driver']:
                status = 'COMPLETE' 
                for instance in curr_drv_conf[vdu_name]['_instances']:
                    self.vplugin_rpc.send_ack(context, curr_drv_conf[vdu_name]['_vnfd'],
                                              vdu_name,
                                              instance,
                                              status,
                                              self.nsd_id, self.ns_config,event='init')
                    self.drv_conf[vdu_name][status].append(instance)
                continue
            else:
                self._configure_vdu(vdu_name, 'configure', self.drv_conf[vdu_name]['_lc_events']['init']['data'],event='init')

    def postConfigure(self, context, conf):
        LOG.debug(_(" In post configure"))
        for instance in conf['instances_list']:
            mgmt_ip = conf['mgmt-ip'][instance]
            _thr_id = str(uuid.generate_uuid()).split('-')[1]
            vdu = {}
            vdu['name'] = conf['vdu']
            kwargs = {'conf':self.ns_config, 'username': self.drv_conf[vdu['name']]['_username'], 'password' :self.drv_conf[vdu['name']]['_password']}

            drv_obj = importutils.import_object(conf['driver'],**kwargs)
            self.drv_conf[vdu['name']]['config'] = {}
            self.drv_conf[vdu['name']]['config']['_driver'] = conf['driver']
            vdu['config'] = {}
            vdu['config']['_drv_obj'] = drv_obj
            method = 'postconfigure'
            arguments = conf['data']
            configThread = ImplThread(self._configure_service, self._condition, vdu, instance, mgmt_ip, method, arguments, conf['event'], _id = _thr_id)
            self._condition.acquire()
            launchd_threads_info[_thr_id] = {'vm_name': instance, 'thread_obj': configThread, 'vnfd': conf['vnf'], 'vdu':conf['vdu'], 'conf': conf, 'event': "postconfigure"}
            self._condition.release()
            configThread.start()

    def _configure_vdu(self, vdu_name, method, arguments , event, update=False):   
       
        status = ""
        for instance in range(0,len(self.drv_conf[vdu_name]['_instances'])):
            instance_name = self.drv_conf[vdu_name]['_instances'][instance]
            if instance_name not in self.drv_conf[vdu_name]['COMPLETE'] or update:
                try:
                    if not self.drv_conf[vdu_name][event]['_driver']:
                        status = 'COMPLETE'
                        self.vplugin_rpc.send_ack(self.ctx, self.drv_conf[vdu_name]['_vnfd'],
                                              vdu_name,
                                              instance_name,
                                              status,
                                              self.nsd_id, self.ns_config)
                        self.drv_conf[vdu_name][status].append(instance_name)
                    else:
                        self._invoke_driver_thread(self.drv_conf[vdu_name],
                                               instance_name,
                                               vdu_name,
                                               self.drv_conf[vdu_name]['_mgmt_ips'][instance_name],
                                               method,
                                               arguments,
                                               event)
                                               
                        status = 'COMPLETE'
                except Exception:
                    status = 'ERROR'
                    LOG.warn(_("Configuration Failed for VNF %s"), instance_name)
                    self.vplugin_rpc.send_ack(self.ctx,
                                              self.drv_conf[vdu_name]['_vnfd'],
                                              vdu_name,
                                          instance_name,
                                          status,
                                          self.nsd_id, self.ns_config,event=event)
        return status


    def _invoke_driver_thread(self, vdu, instance, vdu_name, mgmt_ip, method, arguments,event):
        global launchd_threads_info
        LOG.debug(_("Configuration of the remote VNF %s being intiated"), instance)
        _thr_id = str(uuid.generate_uuid()).split('-')[1]   
        try:
            
            driver_thread = ImplThread(self._configure_service, self._condition, vdu, instance, mgmt_ip, method, arguments,event ,_id = _thr_id)
            self._condition.acquire()
            launchd_threads_info[_thr_id] = {'vm_name': instance, 'thread_obj': driver_thread, 'vnfd': vdu['_vnfd'], 'vdu':vdu_name}
            self._condition.release()
            driver_thread.start()
        except RuntimeError:
            LOG.warning(_("Configuration by the Driver Failed!"))

class VNFPluginCallbacks(object):
    """Manager side of the vnf manager to vnf Plugin RPC API."""

    API_VERSION = '1.0'
    def __init__(self, topic, host):
        RPC_API_VERSION = '1.0'
        target = messaging.Target(topic=topic, version=self.API_VERSION)
        self.client = v_rpc.get_client(target)

    def send_ack(self, context, vnfd, vdu, instance, status, nsd_id, gen_conf, event=None):
        cctxt = self.client.prepare(fanout=True)
        return cctxt.cast(
            context,
            'send_ack',
            vnfd=vnfd,
            vdu=vdu,
            instance=instance, status=status, nsd_id=nsd_id, gen_conf=gen_conf,event=event)

class VNFMgrWithStateReport(VNFManager):
    def __init__(self, host=None):
        super(VNFMgrWithStateReport, self).__init__(host=cfg.CONF.host)
        self.state_rpc = agent_rpc.PluginReportStateAPI(topics.PLUGIN)
        self.agent_state = {
            'binary': 'vnf-manager',
            'host': host,
            'topic': topics.set_topic_name(self.conf.uuid, prefix=topics.VNF_MANAGER),
            'configurations': {
                'agent_status': 'COMPLETE',
                'agent_id': cfg.CONF.uuid
                },
            'start_flag': True,
            'agent_type': AGENT_VNF_MANAGER}
        report_interval = 60
        self.use_call = True
        if report_interval:
            self.heartbeat = loopingcall.FixedIntervalLoopingCall(
                self._report_state)
            self.heartbeat.start(interval=report_interval)


    def _report_state(self):
        try:
            self.agent_state.get('configurations').update(
                self.cache.get_state())
            ctx = context.get_admin_context_without_session()
            self.state_rpc.report_state(ctx, self.agent_state, self.use_call)
        except AttributeError:
            # This means the server does not support report_state
            LOG.warn(_("VNF server does not support state report."
                       " State report for this agent will be disabled."))
            self.heartbeat.stop()
            return
        except Exception:
            LOG.exception(_("Failed reporting state!"))
            return


def load_vnfm_conf(conf_path):
    conf_doc = open(conf_path, 'r')
    conf_dict = yaml.load(conf_doc)
    OPTS = [cfg.DictOpt('vnfm_conf_d', default=conf_dict)]
    cfg.CONF.register_opts(OPTS)


def _register_opts(conf):
    config.register_agent_state_opts_helper(conf)
    config.register_root_helper(conf)


def read_sys_args(arg_list):
    """ Reads a command-line arguments and returns a dict 
        for easier processing of cmd args and useful when 
        a number of args need to specified for the service
        without ordering them in a specific order. """
    arg_l = [arg if uuid.is_uuid_like(arg) else \
                             arg.lstrip('-').replace('-','_') for arg in arg_list[1:]]
    return dict(itertools.izip_longest(*[iter(arg_l)] * 2, fillvalue=""))


def main(manager='vnfmanager.vnf_manager.VNFMgrWithStateReport'):

    # placebo func to replace the server/__init__ with project startup. 
    # pool of threads needed to spawn worker threads for RPC.
    # Default action for project's startup, explictly maintainly a pool
    # for manager as it cannot inherit the vnfsvc's thread pool.
    pool = eventlet.GreenPool()
    pool.waitall()

    conf_params = read_sys_args(sys.argv)
    _register_opts(cfg.CONF)
    common_config.init(sys.argv[1:])
    uuid = conf_params['uuid']
    config.setup_logging(cfg.CONF)
    LOG.warn(_("UUID: %s"), uuid)
    vnfm_conf_dir = conf_params['vnfm_conf_dir'].split("/")
    vnfm_conf_dir[-2] = uuid
    vnfm_conf_dir = "/".join(vnfm_conf_dir)
    vnfm_conf_path = vnfm_conf_dir+uuid+'.yaml'
    load_vnfm_conf(vnfm_conf_path)
    server = vnfsvc_service.Service.create(
                binary='vnf-manager',
                topic=topics.set_topic_name(uuid, prefix=topics.VNF_MANAGER),
                report_interval=60, manager=manager)
    service.launch(server).wait()

