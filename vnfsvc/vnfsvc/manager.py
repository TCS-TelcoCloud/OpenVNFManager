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

import weakref

from oslo_config import cfg

from vnfsvc.common import rpc as n_rpc
from vnfsvc.common import utils
from vnfsvc.openstack.common import importutils
from vnfsvc.openstack.common import log as logging
from vnfsvc.openstack.common import periodic_task
from vnfsvc.openstack.common.gettextutils import _

from stevedore import driver


LOG = logging.getLogger(__name__)


class Manager(n_rpc.RpcCallback, periodic_task.PeriodicTasks):

    # Set RPC API version to 1.0 by default.
    RPC_API_VERSION = '1.0'

    def __init__(self, host=None):
        if not host:
            host = cfg.CONF.host
        self.host = host
        super(Manager, self).__init__()

    def periodic_tasks(self, context, raise_on_error=False):
        self.run_periodic_tasks(context, raise_on_error=raise_on_error)

    def init_host(self):
        """Handle initialization if this is a standalone service.

        Child classes should override this method.

        """
        pass

    def after_start(self):
        """Handler post initialization stuff.

        Child classes can override this method.
        """
        pass


def validate_pre_plugin_load():
    """Checks if the configuration variables are valid.

    If the configuration is invalid then the method will return an error
    message. If all is OK then it will return None.
    """
    if cfg.CONF.core_plugin is None:
        msg = _('VNF core_plugin not configured!')
        return msg


class VNFSvcManager(object):
    """VNFSVC's Manager class.

    VNFSVC's Manager class is responsible for parsing a config file and
    instantiating the correct plugin that concretely implements
    vnfsvc_plugin_base class.
    The caller should make sure that VNFSvcManager is a singleton.
    """
    _instance = None

    def __init__(self, options=None, config_file=None):
        # If no options have been provided, create an empty dict
        if not options:
            options = {}

        msg = validate_pre_plugin_load()
        if msg:
            LOG.critical(msg)
            raise Exception(msg)

        plugin_provider = cfg.CONF.core_plugin
        LOG.info(_("Loading core plugin: %s"), plugin_provider)
        self.plugin = self._get_plugin_instance('vnfsvc.core_plugins',
                                                plugin_provider)

    def _get_plugin_instance(self, namespace, plugin_provider):
        try:
            # Try to resolve plugin by name
            mgr = driver.DriverManager(namespace, plugin_provider)
            plugin_class = mgr.driver
        except RuntimeError as e1:
            # fallback to class name
            try:
                plugin_class = importutils.import_class(plugin_provider)
            except ImportError as e2:
                LOG.exception(_("Error loading plugin by name, %s"), e1)
                LOG.exception(_("Error loading plugin by class, %s"), e2)
                raise ImportError(_("Plugin not found."))
        return plugin_class()

    @classmethod
    @utils.synchronized("manager")
    def _create_instance(cls):
        if not cls.has_instance():
            cls._instance = cls()

    @classmethod
    def has_instance(cls):
        return cls._instance is not None

    @classmethod
    def clear_instance(cls):
        cls._instance = None

    @classmethod
    def get_instance(cls):
        # double checked locking
        if not cls.has_instance():
            cls._create_instance()
        return cls._instance

    @classmethod
    def get_plugin(cls):
        # Return a weakref to minimize gc-preventing references.
        return weakref.proxy(cls.get_instance().plugin)
