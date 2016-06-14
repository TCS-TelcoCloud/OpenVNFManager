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

from vnfmanager.common import rpc as n_rpc
from vnfmanager.common import utils
from vnfmanager.openstack.common import importutils
from vnfmanager.openstack.common import log as logging
from vnfmanager.openstack.common import periodic_task
from vnfmanager.openstack.common.gettextutils import _

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
